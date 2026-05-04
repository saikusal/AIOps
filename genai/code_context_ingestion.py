import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from django.utils import timezone

from .code_context_extractors import extract_python_artifacts
from .models import (
    CodeChangeRecord,
    DeploymentBinding,
    DiscoveredService,
    RepositoryIndex,
    RouteBinding,
    ServiceRepositoryBinding,
    SpanBinding,
    SymbolRelation,
    Target,
)


BUILTIN_CODE_CONTEXT_REPOS = [
    {
        "name": "customer-portal-demo",
        "relative_path": "demo",
        "application_name": "customer-portal",
        "team_name": "platform-demo",
        "service_names": ["frontend", "gateway", "app-orders", "app-inventory", "app-billing"],
    }
]


def _relative_repo_path(base_path: str, candidate: str) -> str:
    try:
        return str(Path(candidate).resolve().relative_to(Path(base_path).resolve()))
    except Exception:
        return candidate


def _git_output(repo_path: str, args: List[str]) -> str:
    git_binary = shutil.which("git")
    if not git_binary:
        return ""
    try:
        proc = subprocess.run(
            [git_binary, "-C", repo_path, *args],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def _recent_git_changes(repo_path: str, limit: int) -> List[Dict[str, Any]]:
    output = _git_output(
        repo_path,
        [
            "log",
            f"--max-count={limit}",
            "--date=iso-strict",
            "--name-only",
            "--pretty=format:__COMMIT__%n%H%n%an%n%ad%n%s",
        ],
    )
    if not output:
        return []

    results: List[Dict[str, Any]] = []
    for block in output.split("__COMMIT__"):
        lines = [line for line in block.splitlines() if line.strip()]
        if len(lines) < 4:
            continue
        commit_sha, author, committed_at_raw, title = lines[:4]
        changed_files = lines[4:]
        committed_at = None
        try:
            committed_at = datetime.fromisoformat(committed_at_raw)
        except ValueError:
            committed_at = None
        results.append(
            {
                "commit_sha": commit_sha,
                "author": author,
                "committed_at": committed_at,
                "title": title,
                "changed_files": changed_files,
            }
        )
    return results


def _default_branch(repo_path: str) -> str:
    branch = _git_output(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"])
    return branch or "main"


def _infer_service_names(repository: RepositoryIndex) -> List[str]:
    metadata = repository.metadata or {}
    names = metadata.get("service_names") or []
    if isinstance(names, str):
        names = [names]
    if not names:
        names = [repository.name]
    return [str(name).strip() for name in names if str(name).strip()]


def _split_env_list(raw_value: str) -> List[str]:
    return [item.strip() for item in (raw_value or "").split(",") if item.strip()]


def _candidate_repo_paths(*names: str) -> List[str]:
    roots = _split_env_list(os.getenv("AIOPS_CODE_CONTEXT_AUTO_ROOTS", ""))
    candidates: List[str] = []
    for root in roots:
        for name in names:
            if not name:
                continue
            for variant in {name, name.replace("_", "-"), name.replace("-", "_")}:
                candidate = os.path.join(root, variant)
                if candidate not in candidates:
                    candidates.append(candidate)
    return candidates


def _coerce_repo_specs(target: Target, discovered_services: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    specs: List[Dict[str, Any]] = []
    target_meta = target.metadata_json or {}
    explicit_specs = ((target_meta.get("code_context") or {}).get("repositories") or []) if isinstance(target_meta, dict) else []
    for item in explicit_specs:
        if isinstance(item, dict):
            specs.append(dict(item))

    top_level_repo_path = str(target_meta.get("repo_path") or target_meta.get("repository_path") or "").strip()
    if top_level_repo_path:
        specs.append(
            {
                "local_path": top_level_repo_path,
                "name": str(target_meta.get("repo_name") or target.name),
                "service_names": target_meta.get("service_names") or [],
                "application_name": str(target_meta.get("application_name") or ""),
                "team_name": str(target_meta.get("team_name") or ""),
            }
        )

    for service in discovered_services or []:
        if not isinstance(service, dict):
            continue
        meta = service.get("metadata_json") if isinstance(service.get("metadata_json"), dict) else {}
        service_name = str(service.get("service_name") or "").strip()
        repo_path = str(meta.get("repo_path") or meta.get("repository_path") or "").strip()
        repo_name = str(meta.get("repo_name") or service_name or "").strip()
        if repo_path:
            specs.append(
                {
                    "local_path": repo_path,
                    "name": repo_name or Path(repo_path).name,
                    "service_names": meta.get("service_names") or ([service_name] if service_name else []),
                    "application_name": str(meta.get("application_name") or ""),
                    "team_name": str(meta.get("team_name") or ""),
                    "service_name": service_name,
                    "version": str(meta.get("version") or ""),
                    "environment": str(meta.get("environment") or target.environment or ""),
                }
            )
            continue

        repo_names = [repo_name, service_name]
        for candidate_path in _candidate_repo_paths(*repo_names):
            if os.path.isdir(candidate_path):
                specs.append(
                    {
                        "local_path": candidate_path,
                        "name": repo_name or Path(candidate_path).name,
                        "service_names": meta.get("service_names") or ([service_name] if service_name else []),
                        "application_name": str(meta.get("application_name") or ""),
                        "team_name": str(meta.get("team_name") or ""),
                        "service_name": service_name,
                        "version": str(meta.get("version") or ""),
                        "environment": str(meta.get("environment") or target.environment or ""),
                    }
                )
                break
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for spec in specs:
        path = str(spec.get("local_path") or "").strip()
        if not path or path in seen:
            continue
        seen.add(path)
        deduped.append(spec)
    return deduped


def ensure_repository_index(*, local_path: str, name: str, metadata: Optional[Dict[str, Any]] = None) -> RepositoryIndex:
    defaults = {
        "name": name or Path(local_path).name,
        "metadata": metadata or {},
        "provider": "local",
        "repo_identifier": str((metadata or {}).get("repo_identifier") or ""),
        "is_active": True,
    }
    repository, created = RepositoryIndex.objects.get_or_create(local_path=local_path, defaults=defaults)
    if not created:
        changed = False
        if name and repository.name != name:
            repository.name = name
            changed = True
        merged_metadata = {**(repository.metadata or {}), **(metadata or {})}
        if repository.metadata != merged_metadata:
            repository.metadata = merged_metadata
            changed = True
        if not repository.is_active:
            repository.is_active = True
            changed = True
        if changed:
            repository.save(update_fields=["name", "metadata", "is_active", "updated_at"])
    return repository


def ensure_builtin_repository_indexes() -> List[RepositoryIndex]:
    repositories: List[RepositoryIndex] = []
    repo_root = Path(__file__).resolve().parent.parent
    for item in BUILTIN_CODE_CONTEXT_REPOS:
        local_path = str((repo_root / item["relative_path"]).resolve())
        if not os.path.isdir(local_path):
            continue
        repository = ensure_repository_index(
            local_path=local_path,
            name=item["name"],
            metadata={
                "service_names": item["service_names"],
                "application_name": item["application_name"],
                "team_name": item["team_name"],
                "bootstrap_mode": "builtin_application",
            },
        )
        for service_name in item["service_names"]:
            ServiceRepositoryBinding.objects.update_or_create(
                service_name=service_name,
                application_name=item["application_name"],
                repository_index=repository,
                defaults={
                    "team_name": item["team_name"],
                    "ownership_confidence": 0.85,
                    "metadata": {"matched_by": "builtin_application_bootstrap"},
                },
            )
        repositories.append(repository)
    return repositories


def auto_register_target_code_context(target: Target, *, discovered_services: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    if str(os.getenv("AIOPS_CODE_CONTEXT_ENABLED", "false")).lower() != "true":
        return []
    if str(os.getenv("AIOPS_CODE_CONTEXT_PROVIDER", "internal")).lower() != "internal":
        return []

    results: List[Dict[str, Any]] = []
    specs = _coerce_repo_specs(target, discovered_services=discovered_services)
    for spec in specs:
        local_path = str(spec.get("local_path") or "").strip()
        if not local_path or not os.path.isdir(local_path):
            results.append({"local_path": local_path, "error": "repository_path_not_found"})
            continue
        service_names = spec.get("service_names") or []
        if isinstance(service_names, str):
            service_names = [service_names]
        repository = ensure_repository_index(
            local_path=local_path,
            name=str(spec.get("name") or Path(local_path).name),
            metadata={
                "service_names": service_names,
                "application_name": str(spec.get("application_name") or ""),
                "team_name": str(spec.get("team_name") or ""),
                "auto_registered_from_target": str(target.target_id),
            },
        )
        for service_name in [str(item).strip() for item in service_names if str(item).strip()]:
            ServiceRepositoryBinding.objects.update_or_create(
                service_name=service_name,
                application_name=str(spec.get("application_name") or ""),
                repository_index=repository,
                defaults={
                    "team_name": str(spec.get("team_name") or ""),
                    "ownership_confidence": 0.8,
                    "metadata": {"matched_by": "target_auto_registration", "target_id": str(target.target_id)},
                },
            )
            version = str(spec.get("version") or "").strip()
            if version:
                DeploymentBinding.objects.update_or_create(
                    service_name=service_name,
                    environment=str(spec.get("environment") or target.environment or ""),
                    version=version,
                    repository_index=repository,
                    defaults={
                        "commit_sha": str(spec.get("commit_sha") or ""),
                        "deployed_at": timezone.now(),
                        "metadata": {"matched_by": "target_auto_registration", "target_id": str(target.target_id)},
                    },
                )
        sync_result = sync_repository_index(repository)
        results.append(sync_result)
    return results


def sync_repository_index(repository: RepositoryIndex, *, recent_commit_limit: Optional[int] = None) -> Dict[str, Any]:
    repo_path = repository.local_path
    if not repo_path or not os.path.isdir(repo_path):
        repository.index_status = "failed"
        repository.last_index_error = "Repository path does not exist."
        repository.save(update_fields=["index_status", "last_index_error", "updated_at"])
        raise FileNotFoundError(repository.last_index_error)

    recent_commit_limit = recent_commit_limit or int(os.getenv("AIOPS_CODE_CONTEXT_RECENT_COMMITS", "25") or "25")
    artifacts = extract_python_artifacts(repo_path)
    git_available = bool(shutil.which("git"))

    RouteBinding.objects.filter(repository_index=repository).delete()
    SpanBinding.objects.filter(repository_index=repository).delete()
    SymbolRelation.objects.filter(repository_index=repository).delete()
    CodeChangeRecord.objects.filter(repository_index=repository).delete()

    service_names = _infer_service_names(repository)
    RouteBinding.objects.bulk_create(
        [
            RouteBinding(
                repository_index=repository,
                service_name=service_names[0] if service_names else "",
                **binding,
            )
            for binding in artifacts["route_bindings"]
        ],
        ignore_conflicts=True,
    )
    SpanBinding.objects.bulk_create(
        [
            SpanBinding(
                repository_index=repository,
                service_name=service_names[0] if service_names else "",
                **binding,
            )
            for binding in artifacts["span_bindings"]
        ],
        ignore_conflicts=True,
    )
    SymbolRelation.objects.bulk_create(
        [
            SymbolRelation(
                repository_index=repository,
                **relation,
            )
            for relation in artifacts["symbol_relations"]
        ],
        ignore_conflicts=True,
    )

    recent_changes = _recent_git_changes(repo_path, recent_commit_limit)
    CodeChangeRecord.objects.bulk_create(
        [
            CodeChangeRecord(
                repository_index=repository,
                commit_sha=item["commit_sha"],
                author=item["author"],
                title=item["title"],
                changed_files=item["changed_files"],
                committed_at=item["committed_at"],
                metadata={},
            )
            for item in recent_changes
        ],
        ignore_conflicts=True,
    )

    if not ServiceRepositoryBinding.objects.filter(repository_index=repository).exists():
        ServiceRepositoryBinding.objects.bulk_create(
            [
                ServiceRepositoryBinding(
                    service_name=service_name,
                    application_name=str((repository.metadata or {}).get("application_name") or ""),
                    repository_index=repository,
                    team_name=str((repository.metadata or {}).get("team_name") or ""),
                    ownership_confidence=0.75,
                    metadata={"matched_by": "repository_metadata"},
                )
                for service_name in service_names
            ],
            ignore_conflicts=True,
        )

    repository.default_branch = (repository.default_branch or "").strip() or _default_branch(repo_path)
    repository.last_indexed_at = timezone.now()
    repository.index_status = "indexed"
    repository.last_index_error = ""
    repository.metadata = {
        **(repository.metadata or {}),
        "route_count": len(artifacts["route_bindings"]),
        "span_count": len(artifacts["span_bindings"]),
        "relation_count": len(artifacts["symbol_relations"]),
        "recent_commit_count": len(recent_changes),
        "git_available": git_available,
        "index_warnings": ([] if git_available else ["git_binary_unavailable_recent_change_enrichment_skipped"]),
    }
    repository.save(update_fields=["default_branch", "last_indexed_at", "index_status", "last_index_error", "metadata", "updated_at"])
    return {
        "repository": repository.name,
        "route_count": len(artifacts["route_bindings"]),
        "span_count": len(artifacts["span_bindings"]),
        "relation_count": len(artifacts["symbol_relations"]),
        "recent_commit_count": len(recent_changes),
    }


def sync_all_active_repositories(*, recent_commit_limit: Optional[int] = None) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if str(os.getenv("AIOPS_CODE_CONTEXT_ENABLED", "false")).lower() == "true":
        if str(os.getenv("AIOPS_CODE_CONTEXT_PROVIDER", "internal")).lower() == "internal":
            ensure_builtin_repository_indexes()
    for repository in RepositoryIndex.objects.filter(is_active=True):
        try:
            results.append(sync_repository_index(repository, recent_commit_limit=recent_commit_limit))
        except Exception as exc:
            repository.index_status = "failed"
            repository.last_index_error = str(exc)[:4000]
            repository.save(update_fields=["index_status", "last_index_error", "updated_at"])
            results.append({"repository": repository.name, "error": str(exc)})
    return results
