import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from .code_context_services import (
    blast_radius as _code_blast_radius,
    find_recent_deployments as _code_find_recent_deployments,
    find_related_symbols as _code_find_related_symbols,
    find_service_owner as _code_find_service_owner,
    queue_to_consumers as _code_queue_to_consumers,
    read_code_snippet as _code_read_code_snippet,
    recent_changes_for_component as _code_recent_changes_for_component,
    route_to_handler as _code_route_to_handler,
    search_code_context as _code_search_code_context,
    span_to_symbol as _code_span_to_symbol,
)

# ---------------------------------------------------------------------------
# source_read_traceback
# ---------------------------------------------------------------------------
_TRACEBACK_FILE_RE = re.compile(r'File "([^"]+)", line (\d+), in (\S+)')
_SCHEMA_EXTENSIONS = (".sql", ".prisma", ".dbml")
_SOURCE_CONTEXT_LINES = 40


def _map_container_path(container_path: str, path_prefix_map: Dict[str, str]) -> Optional[str]:
    for prefix, replacement in (path_prefix_map or {}).items():
        if container_path.startswith(prefix):
            return replacement + container_path[len(prefix):]
    return None


def _read_source_snippet(local_path: str, line_number: int, context: int = _SOURCE_CONTEXT_LINES) -> str:
    try:
        lines = Path(local_path).read_text(errors="replace").splitlines()
        start = max(0, line_number - context - 1)
        end = min(len(lines), line_number + context)
        numbered = [f"{i + 1:4d}{'>>>' if i + 1 == line_number else '   '} | {ln}"
                    for i, ln in enumerate(lines[start:end], start=start)]
        return "\n".join(numbered)
    except OSError:
        return ""


def _scan_schema_files(source_root: str) -> List[Dict[str, str]]:
    results = []
    try:
        for root, _, files in os.walk(source_root):
            for fname in files:
                if fname.endswith(_SCHEMA_EXTENSIONS):
                    fpath = os.path.join(root, fname)
                    try:
                        content = Path(fpath).read_text(errors="replace")
                        results.append({"path": fpath, "content": content[:3000]})
                    except OSError:
                        pass
    except OSError:
        pass
    return results


def source_read_traceback(
    *,
    log_messages: List[str],
    path_prefix_map: Optional[Dict[str, str]] = None,
    source_root: str = "",
) -> Dict[str, Any]:
    """Parse Python tracebacks from log messages, read the relevant source
    snippets from the mapped host filesystem, and return any SQL/schema files
    found in *source_root*.

    Parameters
    ----------
    log_messages:
        Raw log message strings (typically from Elasticsearch ``_source.message``).
    path_prefix_map:
        Container-path prefix → host-path prefix mapping.
        Example: ``{"/app": "/source/demo/app"}``.
    source_root:
        Directory to scan for SQL/schema files (e.g. ``/source/demo``).
    """
    if not log_messages:
        return {}

    combined = "\n".join(log_messages)
    matches = _TRACEBACK_FILE_RE.findall(combined)
    if not matches:
        return {}

    seen: Dict[str, Dict[str, Any]] = {}
    for container_path, line_str, func_name in matches:
        if container_path in seen:
            continue
        line_number = int(line_str)
        local_path = _map_container_path(container_path, path_prefix_map or {})
        snippet = _read_source_snippet(local_path, line_number) if local_path else ""
        seen[container_path] = {
            "container_path": container_path,
            "local_path": local_path or "",
            "function_name": func_name,
            "line_number": line_number,
            "snippet": snippet,
            "readable": bool(snippet),
        }

    schema_files = _scan_schema_files(source_root) if source_root else []
    return {
        "files": list(seen.values()),
        "schema_files": schema_files,
        "traceback_count": len(matches),
        "readable_files": sum(1 for f in seen.values() if f["readable"]),
    }


def incidents_get_summary(
    *,
    incident_key: str,
    incident_model,
    incident_summary_payload: Callable[[Any], Dict[str, Any]],
) -> Dict[str, Any]:
    incident = incident_model.objects.filter(incident_key=incident_key).first()
    if not incident:
        return {}
    return incident_summary_payload(incident)


def incidents_get_timeline(
    *,
    incident_key: str,
    incident_model,
    incident_timeline_payload: Callable[[Any], Dict[str, Any]],
) -> Dict[str, Any]:
    incident = incident_model.objects.filter(incident_key=incident_key).first()
    if not incident:
        return {}
    return incident_timeline_payload(incident)


def applications_get_overview(
    *,
    build_application_overview: Callable[..., Dict[str, Any]],
    application: str = "",
) -> Dict[str, Any]:
    overview = build_application_overview(include_ai=True, include_predictions=True)
    if not application:
        return overview
    filtered = [item for item in overview.get("results", []) if item.get("application") == application]
    return {"count": len(filtered), "results": filtered}


def applications_get_graph(
    *,
    application: str,
    application_graph_payload: Callable[[str], Optional[Dict[str, Any]]],
) -> Dict[str, Any]:
    return application_graph_payload(application) or {}


def applications_get_component_snapshot(
    *,
    application: str,
    service: str,
    build_application_overview: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    overview = build_application_overview(include_ai=True, include_predictions=True)
    for app in overview.get("results", []):
        if app.get("application") != application:
            continue
        for component in app.get("components", []):
            if component.get("service") == service or component.get("target_host") == service:
                return component
    return {}


def metrics_query_service_overview(
    *,
    service_name: str,
    fetch_metrics_query: Callable[[str], Dict[str, Any]],
) -> Dict[str, Any]:
    if not service_name:
        return {}
    return {
        "latency_p95_seconds": fetch_metrics_query(
            f'histogram_quantile(0.95, sum by (le) (rate(flask_http_request_duration_seconds_bucket{{job="{service_name}"}}[5m])))'
        ),
        "error_rate": fetch_metrics_query(
            f'sum(rate(flask_http_request_total{{job="{service_name}",status=~"5.."}}[5m]))'
        ),
    }


def metrics_query_raw(
    *,
    query: str,
    fetch_metrics_query: Callable[[str], Dict[str, Any]],
) -> Dict[str, Any]:
    if not query:
        return {}
    return fetch_metrics_query(query)


def logs_search(
    *,
    target_host: Optional[str],
    query: str,
    fetch_elasticsearch_logs: Callable[[Optional[str], str], Dict[str, Any]],
) -> Dict[str, Any]:
    if not target_host and not query:
        return {}
    return fetch_elasticsearch_logs(target_host, query)


def traces_search(
    *,
    service_name: Optional[str],
    fetch_jaeger_traces: Callable[[Optional[str]], Dict[str, Any]],
) -> Dict[str, Any]:
    if not service_name:
        return {}
    return fetch_jaeger_traces(service_name)


def runbooks_search(
    *,
    query: str = "",
    incident_key: str = "",
    incident_model=None,
    runbook_model=None,
) -> Dict[str, Any]:
    if incident_key and incident_model is not None:
        incident = incident_model.objects.filter(incident_key=incident_key).first()
        if not incident:
            return {"count": 0, "results": []}
        runbooks = incident.runbooks.order_by("-created_at")[:5]
    elif runbook_model is not None and query:
        runbooks = runbook_model.objects.filter(title__icontains=query).order_by("-created_at")[:10]
        if not runbooks:
            runbooks = runbook_model.objects.filter(content__icontains=query).order_by("-created_at")[:10]
    else:
        return {"count": 0, "results": []}

    results = []
    for runbook in runbooks:
        results.append(
            {
                "runbook_id": runbook.id,
                "incident_key": str(runbook.incident.incident_key) if getattr(runbook, "incident", None) else "",
                "title": runbook.title,
                "content_preview": (runbook.content or "")[:500],
                "created_at": runbook.created_at.isoformat(),
            }
        )
    return {"count": len(results), "results": results}


def code_find_service_owner(*, service_name: str, application_name: str = "") -> Dict[str, Any]:
    return _code_find_service_owner(service_name=service_name, application_name=application_name)


def code_route_to_handler(*, service_name: str, route: str, http_method: str = "") -> Dict[str, Any]:
    return _code_route_to_handler(service_name=service_name, route=route, http_method=http_method)


def code_span_to_symbol(*, service_name: str, span_name: str) -> Dict[str, Any]:
    return _code_span_to_symbol(service_name=service_name, span_name=span_name)


def code_recent_changes_for_component(*, repository: str, module_path: str = "", symbol: str = "", hours: int = 72) -> Dict[str, Any]:
    return _code_recent_changes_for_component(repository=repository, module_path=module_path, symbol=symbol, hours=hours)


def code_find_recent_deployments(*, service_name: str, environment: str = "", version: str = "") -> Dict[str, Any]:
    return _code_find_recent_deployments(service_name=service_name, environment=environment, version=version)


def code_find_related_symbols(*, repository: str, symbol: str) -> Dict[str, Any]:
    return _code_find_related_symbols(repository=repository, symbol=symbol)


def code_blast_radius_lookup(*, repository: str, symbol: str = "", route: str = "") -> Dict[str, Any]:
    return _code_blast_radius(repository=repository, symbol=symbol, route=route)


def code_queue_consumers(*, repository: str, queue_name: str) -> Dict[str, Any]:
    return _code_queue_to_consumers(repository=repository, queue_name=queue_name)


def code_search_context(*, repository: str, query: str, service_name: str = "", limit: int = 6) -> Dict[str, Any]:
    return _code_search_code_context(repository=repository, query=query, service_name=service_name, limit=limit)


def code_read_snippet(
    *,
    repository: str,
    module_path: str = "",
    symbol: str = "",
    line_start: int = 0,
    line_end: int = 0,
    context_lines: int = 18,
) -> Dict[str, Any]:
    return _code_read_code_snippet(
        repository=repository,
        module_path=module_path,
        symbol=symbol,
        line_start=line_start,
        line_end=line_end,
        context_lines=context_lines,
    )
