import re
from pathlib import Path
from datetime import timedelta
from typing import Any, Dict, List, Optional

from django.db.models import Q
from django.utils import timezone

from .models import (
    CodeChangeRecord,
    DeploymentBinding,
    RepositoryIndex,
    RouteBinding,
    ServiceRepositoryBinding,
    SpanBinding,
    SymbolRelation,
)


def _normalize(value: str) -> str:
    return (value or "").strip().lower().replace("_", "-")


def _repository_for_name(repository: str) -> Optional[RepositoryIndex]:
    if not repository:
        return None
    return RepositoryIndex.objects.filter(name__iexact=repository).first()


def _resolve_repo_file(repo: RepositoryIndex, module_path: str) -> Optional[Path]:
    if not repo or not module_path:
        return None
    candidate = (Path(repo.local_path) / module_path).resolve()
    try:
        candidate.relative_to(Path(repo.local_path).resolve())
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate


def _render_numbered_snippet(file_path: Path, *, line_start: int = 0, line_end: int = 0, context_lines: int = 18) -> str:
    try:
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""

    if line_start and line_end:
        start_index = max(0, line_start - context_lines - 1)
        end_index = min(len(lines), line_end + context_lines)
        focus_start = line_start
        focus_end = line_end
    elif line_start:
        start_index = max(0, line_start - context_lines - 1)
        end_index = min(len(lines), line_start + context_lines)
        focus_start = line_start
        focus_end = line_start
    else:
        start_index = 0
        end_index = min(len(lines), context_lines * 2)
        focus_start = 0
        focus_end = 0

    rendered: List[str] = []
    for index in range(start_index, end_index):
        line_number = index + 1
        marker = ">>>" if focus_start and focus_start <= line_number <= max(focus_end, focus_start) else "   "
        rendered.append(f"{line_number:4d}{marker} | {lines[index]}")
    return "\n".join(rendered)


def _binding_repo_payload(binding: ServiceRepositoryBinding) -> Dict[str, Any]:
    return {
        "repository": binding.repository_index.name,
        "repository_id": binding.repository_index.repository_id,
        "repository_path": binding.repository_index.local_path,
        "repository_index_status": binding.repository_index.index_status,
        "repository_last_indexed_at": binding.repository_index.last_indexed_at.isoformat() if binding.repository_index.last_indexed_at else None,
        "service_name": binding.service_name,
        "application_name": binding.application_name,
        "team_name": binding.team_name,
        "ownership_confidence": binding.ownership_confidence,
        "metadata": binding.metadata or {},
    }


def find_service_owner(*, service_name: str, application_name: str = "") -> Dict[str, Any]:
    normalized_service = _normalize(service_name)
    normalized_app = _normalize(application_name)
    bindings = list(ServiceRepositoryBinding.objects.select_related("repository_index").filter(service_name__iexact=service_name))
    if application_name:
        bindings = [
            binding for binding in bindings
            if _normalize(binding.application_name) in {"", normalized_app}
        ]
    if not bindings and normalized_service:
        bindings = [
            binding
            for binding in ServiceRepositoryBinding.objects.select_related("repository_index").all()
            if _normalize(binding.service_name) == normalized_service
        ]
    if bindings:
        best = sorted(bindings, key=lambda item: item.ownership_confidence, reverse=True)[0]
        return {**_binding_repo_payload(best), "ok": True}

    repository = RepositoryIndex.objects.filter(name__iexact=service_name).first()
    if repository:
        return {
            "ok": True,
            "repository": repository.name,
            "repository_id": repository.repository_id,
            "repository_path": repository.local_path,
            "repository_index_status": repository.index_status,
            "repository_last_indexed_at": repository.last_indexed_at.isoformat() if repository.last_indexed_at else None,
            "service_name": service_name,
            "application_name": application_name,
            "team_name": str((repository.metadata or {}).get("team_name") or ""),
            "ownership_confidence": 0.4,
            "metadata": {"matched_by": "repository_name_fallback"},
        }
    return {"ok": False, "message": "No repository binding found."}


def route_to_handler(*, service_name: str, route: str, http_method: str = "") -> Dict[str, Any]:
    normalized_route = (route or "").strip()
    method = (http_method or "ANY").upper()
    query = RouteBinding.objects.select_related("repository_index").filter(route_pattern=normalized_route)
    if service_name:
        query = query.filter(Q(service_name__iexact=service_name) | Q(service_name=""))
    if http_method:
        query = query.filter(Q(http_method=method) | Q(http_method="ANY"))
    binding = query.order_by("-confidence").first()
    if not binding and normalized_route:
        candidates = RouteBinding.objects.select_related("repository_index").all()
        scored = []
        for item in candidates:
            if service_name and item.service_name and _normalize(item.service_name) != _normalize(service_name):
                continue
            score = 0
            if item.route_pattern == normalized_route:
                score += 3
            elif normalized_route and item.route_pattern and normalized_route.rstrip("/") == item.route_pattern.rstrip("/"):
                score += 2
            elif item.route_pattern and normalized_route.startswith(item.route_pattern.rstrip("/")):
                score += 1
            if method and item.http_method in {method, "ANY"}:
                score += 1
            if score:
                scored.append((score, item))
        if scored:
            scored.sort(key=lambda entry: (entry[0], entry[1].confidence), reverse=True)
            binding = scored[0][1]
    if not binding:
        return {"ok": False, "message": "No route binding found."}
    return {
        "ok": True,
        "repository": binding.repository_index.name,
        "repository_index_status": binding.repository_index.index_status,
        "repository_last_indexed_at": binding.repository_index.last_indexed_at.isoformat() if binding.repository_index.last_indexed_at else None,
        "service_name": binding.service_name or service_name,
        "route": binding.route_pattern,
        "http_method": binding.http_method,
        "handler": binding.handler_name,
        "module_path": binding.handler_file_path,
        "line_start": binding.line_start,
        "line_end": binding.line_end,
        "confidence": binding.confidence,
        "supporting_context": [f"Matched route {binding.route_pattern}", f"Handler {binding.handler_name}"],
        "metadata": binding.metadata or {},
    }


def span_to_symbol(*, service_name: str, span_name: str) -> Dict[str, Any]:
    if not span_name:
        return {"ok": False, "message": "No span name provided."}
    query = SpanBinding.objects.select_related("repository_index").filter(span_name__iexact=span_name)
    if service_name:
        query = query.filter(Q(service_name__iexact=service_name) | Q(service_name=""))
    binding = query.order_by("-confidence").first()
    if not binding:
        candidates = [
            item for item in SpanBinding.objects.select_related("repository_index").all()
            if span_name.lower() in item.span_name.lower()
            and (not service_name or not item.service_name or _normalize(item.service_name) == _normalize(service_name))
        ]
        candidates.sort(key=lambda item: item.confidence, reverse=True)
        binding = candidates[0] if candidates else None
    if not binding:
        return {"ok": False, "message": "No span binding found."}
    return {
        "ok": True,
        "repository": binding.repository_index.name,
        "repository_index_status": binding.repository_index.index_status,
        "repository_last_indexed_at": binding.repository_index.last_indexed_at.isoformat() if binding.repository_index.last_indexed_at else None,
        "service_name": binding.service_name or service_name,
        "span_name": binding.span_name,
        "symbol": binding.symbol_name,
        "module_path": binding.symbol_file_path,
        "line_start": binding.line_start,
        "line_end": binding.line_end,
        "confidence": binding.confidence,
        "matched_by": str((binding.metadata or {}).get("matched_by") or "span_binding"),
    }


def find_related_symbols(*, repository: str, symbol: str) -> Dict[str, Any]:
    repo = _repository_for_name(repository)
    if not repo or not symbol:
        return {"ok": False, "message": "Repository or symbol not found."}
    relations = SymbolRelation.objects.filter(repository_index=repo).filter(
        Q(source_symbol__icontains=symbol) | Q(target_symbol__icontains=symbol)
    )[:20]
    return {
        "ok": True,
        "repository": repo.name,
        "symbol": symbol,
        "related_symbols": [
            {
                "source_symbol": relation.source_symbol,
                "source_file_path": relation.source_file_path,
                "target_symbol": relation.target_symbol,
                "target_file_path": relation.target_file_path,
                "relation_type": relation.relation_type,
                "confidence": relation.confidence,
            }
            for relation in relations
        ],
    }


def recent_changes_for_component(*, repository: str, module_path: str = "", symbol: str = "", hours: int = 72) -> Dict[str, Any]:
    repo = _repository_for_name(repository)
    if not repo:
        return {"ok": False, "message": "Repository not found."}
    cutoff = timezone.now() - timedelta(hours=max(hours, 1))
    records = CodeChangeRecord.objects.filter(repository_index=repo)
    if records.model._meta.get_field("committed_at"):
        records = records.filter(Q(committed_at__gte=cutoff) | Q(committed_at__isnull=True))
    matched: List[CodeChangeRecord] = []
    for record in records[:50]:
        files = record.changed_files or []
        if module_path and any(module_path in file_path for file_path in files):
            matched.append(record)
            continue
        if symbol and any(symbol.lower() in file_path.lower() for file_path in files):
            matched.append(record)
    if not matched:
        matched = list(records[:10])
    return {
        "ok": True,
        "repository": repo.name,
        "recent_changes": [
            {
                "commit_sha": record.commit_sha,
                "author": record.author,
                "title": record.title,
                "changed_files": record.changed_files,
                "committed_at": record.committed_at.isoformat() if record.committed_at else None,
            }
            for record in matched[:10]
        ],
    }


def find_recent_deployments(*, service_name: str, environment: str = "", version: str = "") -> Dict[str, Any]:
    query = DeploymentBinding.objects.select_related("repository_index").filter(service_name__iexact=service_name)
    if environment:
        query = query.filter(environment__iexact=environment)
    if version:
        query = query.filter(version__iexact=version)
    bindings = query.order_by("-deployed_at", "-created_at")[:10]
    return {
        "ok": True,
        "service_name": service_name,
        "recent_deployments": [
            {
                "repository": binding.repository_index.name,
                "environment": binding.environment,
                "version": binding.version,
                "commit_sha": binding.commit_sha,
                "deployed_at": binding.deployed_at.isoformat() if binding.deployed_at else None,
            }
            for binding in bindings
        ],
    }


def blast_radius(*, repository: str, symbol: str = "", route: str = "") -> Dict[str, Any]:
    related = find_related_symbols(repository=repository, symbol=symbol or route)
    if not related.get("ok"):
        return related
    items = related.get("related_symbols") or []
    return {
        "ok": True,
        "repository": repository,
        "blast_radius": {
            "affected_symbol_count": len(items),
            "affected_paths": sorted(
                {
                    item.get("source_file_path") or item.get("target_file_path") or ""
                    for item in items
                    if item.get("source_file_path") or item.get("target_file_path")
                }
            )[:20],
            "risk_level": "high" if len(items) >= 8 else "medium" if len(items) >= 3 else "low",
            "related_symbols": items[:10],
        },
    }


def queue_to_consumers(*, repository: str, queue_name: str) -> Dict[str, Any]:
    repo = _repository_for_name(repository)
    if not repo:
        return {"ok": False, "message": "Repository not found."}
    matches = [
        binding
        for binding in SpanBinding.objects.filter(repository_index=repo)
        if queue_name.lower() in ((binding.metadata or {}).get("queue_name") or "").lower()
    ]
    return {
        "ok": True,
        "repository": repo.name,
        "queue_consumers": [
            {
                "queue_name": (binding.metadata or {}).get("queue_name") or queue_name,
                "symbol": binding.symbol_name,
                "module_path": binding.symbol_file_path,
                "confidence": binding.confidence,
            }
            for binding in matches
        ],
    }


def read_code_snippet(
    *,
    repository: str,
    module_path: str = "",
    symbol: str = "",
    line_start: int = 0,
    line_end: int = 0,
    context_lines: int = 18,
) -> Dict[str, Any]:
    repo = _repository_for_name(repository)
    if not repo:
        return {"ok": False, "message": "Repository not found."}

    resolved_line_start = max(int(line_start or 0), 0)
    resolved_line_end = max(int(line_end or 0), 0)
    resolved_module_path = module_path

    if not resolved_module_path and symbol:
        span_binding = (
            SpanBinding.objects.filter(repository_index=repo)
            .filter(Q(symbol_name__iexact=symbol) | Q(span_name__iexact=symbol))
            .order_by("-confidence")
            .first()
        )
        if span_binding:
            resolved_module_path = span_binding.symbol_file_path
            resolved_line_start = resolved_line_start or int(span_binding.line_start or 0)
            resolved_line_end = resolved_line_end or int(span_binding.line_end or 0)
        else:
            route_binding = (
                RouteBinding.objects.filter(repository_index=repo, handler_name__iexact=symbol)
                .order_by("-confidence")
                .first()
            )
            if route_binding:
                resolved_module_path = route_binding.handler_file_path
                resolved_line_start = resolved_line_start or int(route_binding.line_start or 0)
                resolved_line_end = resolved_line_end or int(route_binding.line_end or 0)

    file_path = _resolve_repo_file(repo, resolved_module_path)
    if not file_path:
        return {"ok": False, "message": "Code file not found.", "repository": repo.name, "module_path": resolved_module_path}

    snippet = _render_numbered_snippet(
        file_path,
        line_start=resolved_line_start,
        line_end=resolved_line_end,
        context_lines=max(int(context_lines or 18), 4),
    )
    if not snippet:
        return {"ok": False, "message": "Unable to read code snippet.", "repository": repo.name, "module_path": resolved_module_path}

    return {
        "ok": True,
        "repository": repo.name,
        "module_path": resolved_module_path,
        "symbol": symbol,
        "line_start": resolved_line_start or None,
        "line_end": resolved_line_end or None,
        "snippet": snippet,
    }


def search_code_context(
    *,
    repository: str,
    query: str,
    service_name: str = "",
    limit: int = 6,
) -> Dict[str, Any]:
    repo = _repository_for_name(repository)
    if not repo:
        return {"ok": False, "message": "Repository not found."}

    normalized_query = (query or "").strip().lower()
    tokens = [token for token in re.split(r"[^a-zA-Z0-9_./:-]+", normalized_query) if len(token) >= 3]
    if service_name:
        tokens.extend([service_name.lower(), service_name.lower().replace("-", "_"), service_name.lower().replace("_", "-")])

    scored: List[Dict[str, Any]] = []

    for binding in RouteBinding.objects.filter(repository_index=repo):
        haystack = " ".join(
            [
                binding.route_pattern or "",
                binding.handler_name or "",
                binding.handler_file_path or "",
                binding.http_method or "",
            ]
        ).lower()
        score = 0
        for token in tokens:
            if token in haystack:
                score += 3 if token in (binding.route_pattern or "").lower() else 2
        if score:
            scored.append(
                {
                    "kind": "route",
                    "score": score + binding.confidence,
                    "label": f"{binding.http_method} {binding.route_pattern}",
                    "module_path": binding.handler_file_path,
                    "symbol": binding.handler_name,
                    "line_start": binding.line_start,
                    "line_end": binding.line_end,
                }
            )

    for binding in SpanBinding.objects.filter(repository_index=repo):
        haystack = " ".join([binding.span_name or "", binding.symbol_name or "", binding.symbol_file_path or ""]).lower()
        score = 0
        for token in tokens:
            if token in haystack:
                score += 3 if token in (binding.symbol_name or "").lower() or token in (binding.span_name or "").lower() else 2
        if score:
            scored.append(
                {
                    "kind": "span",
                    "score": score + binding.confidence,
                    "label": binding.span_name,
                    "module_path": binding.symbol_file_path,
                    "symbol": binding.symbol_name,
                    "line_start": binding.line_start,
                    "line_end": binding.line_end,
                }
            )

    for relation in SymbolRelation.objects.filter(repository_index=repo)[:250]:
        haystack = " ".join(
            [
                relation.source_symbol or "",
                relation.target_symbol or "",
                relation.source_file_path or "",
                relation.target_file_path or "",
            ]
        ).lower()
        score = 0
        for token in tokens:
            if token in haystack:
                score += 1
        if score:
            scored.append(
                {
                    "kind": "relation",
                    "score": score + relation.confidence,
                    "label": f"{relation.source_symbol} -> {relation.target_symbol}",
                    "module_path": relation.source_file_path or relation.target_file_path,
                    "symbol": relation.source_symbol,
                    "line_start": None,
                    "line_end": None,
                }
            )

    scored.sort(key=lambda item: item["score"], reverse=True)
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in scored:
        key = (item["kind"], item["module_path"], item["symbol"], item["label"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= max(int(limit or 6), 1):
            break

    return {
        "ok": True,
        "repository": repo.name,
        "query": query,
        "matches": deduped,
    }
