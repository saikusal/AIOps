import json
import re
from datetime import datetime, timezone

from typing import Any, Callable, Dict, List, Optional
from genai.code_context_extractors import extract_route_hint_from_text
from genai.mcp_orchestrator import InvestigationMCPOrchestrator
from genai.multi_step_workflow import (
    build_investigation_workflow,
    finalize_investigation_workflow,
)


def extract_investigation_scope(question: str, body: Dict[str, Any]) -> Dict[str, str]:
    text = " ".join(
        part for part in [
            question or "",
            str(body.get("application") or ""),
            str(body.get("service") or ""),
            str(body.get("incident") or ""),
        ]
        if part
    )
    scope = {"application": "", "service": "", "incident": ""}
    for key in ("application", "service", "incident"):
        match = re.search(rf"{key}=([A-Za-z0-9_\-:]+)", text, re.IGNORECASE)
        if match:
            scope[key] = match.group(1)
    return scope


def _infer_runtime_entities_from_question(
    question: str,
    *,
    build_application_overview: Callable[..., Dict[str, Any]],
) -> Dict[str, str]:
    text = (question or "").lower()
    if not text:
        return {"application": "", "service": ""}

    try:
        overview = build_application_overview(include_ai=False, include_predictions=False)
    except Exception:
        return {"application": "", "service": ""}

    best_application = ""
    best_service = ""
    best_score = 0

    for application in overview.get("results", []):
        if not isinstance(application, dict):
            continue
        app_key = str(application.get("application") or "")
        app_title = str(application.get("title") or "")
        app_tokens = {app_key.lower(), app_title.lower()}
        app_score = sum(3 for token in app_tokens if token and token in text)
        if app_score > best_score and app_key:
            best_score = app_score
            best_application = app_key

        for component in application.get("components", []):
            if not isinstance(component, dict):
                continue
            service_name = str(component.get("service") or "")
            target_host = str(component.get("target_host") or "")
            title = str(component.get("title") or "")
            tokens = {
                service_name.lower(),
                target_host.lower(),
                title.lower(),
                service_name.lower().replace("-", " "),
                service_name.lower().replace("app-", ""),
            }
            score = sum(4 if token == service_name.lower() else 3 for token in tokens if token and token in text)
            if score > best_score and service_name:
                best_score = score
                best_service = service_name
                best_application = app_key or best_application

    return {"application": best_application, "service": best_service}


_ACTIVE_INCIDENT_PHRASES = [
    "active incident", "current incident", "latest incident", "the incident",
    "open incident", "ongoing incident", "rca for", "rca", "blast radius",
    "what happened", "what is happening", "what went wrong",
    "highest-risk", "highest risk", "summarize",
]

LINKED_RECOMMENDATION_FRESHNESS_SECONDS = 600
_TRACEBACK_MARKER = ('File "/', 'Traceback (most recent')
_ERROR_TOKENS = (
    " error",
    " exception",
    " failed",
    " unavailable",
    " timeout",
    " connection refused",
    " operationalerror",
)
_DB_TOKENS = (
    "postgres",
    "psycopg2",
    "database",
    "db",
    "pg_",
    "sql",
)


def _extract_trace_span_hints(traces: Dict[str, Any]) -> List[str]:
    hints: List[str] = []
    for trace in (traces or {}).get("data") or []:
        if not isinstance(trace, dict):
            continue
        for span in trace.get("spans") or []:
            if not isinstance(span, dict):
                continue
            span_name = str(span.get("operationName") or "").strip()
            if span_name and span_name not in hints:
                hints.append(span_name)
    return hints[:5]


def _extract_route_hint(question: str, logs: Dict[str, Any]) -> str:
    route = extract_route_hint_from_text(question or "")
    if route:
        return route
    for message in _extract_log_messages(logs):
        route = extract_route_hint_from_text(message)
        if route:
            return route
    return ""


def _code_context_summary(code_context: Dict[str, Any]) -> str:
    owner = code_context.get("owner") or {}
    route_binding = code_context.get("route_binding") or {}
    span_binding = code_context.get("span_binding") or {}
    parts: List[str] = []
    if owner.get("repository"):
        parts.append(f"Repository {owner.get('repository')} owns service {owner.get('service_name') or ''}.".strip())
    if route_binding.get("handler"):
        parts.append(
            f"Route {route_binding.get('http_method') or ''} {route_binding.get('route') or ''} maps to handler {route_binding.get('handler')} in {route_binding.get('module_path') or 'unknown file'}.".strip()
        )
    if span_binding.get("symbol"):
        parts.append(
            f"Trace span {span_binding.get('span_name') or ''} maps to symbol {span_binding.get('symbol')} in {span_binding.get('module_path') or 'unknown file'}.".strip()
        )
    recent_changes = (code_context.get("recent_changes") or {}).get("recent_changes") or []
    if recent_changes:
        parts.append(f"{len(recent_changes)} recent code changes matched the likely failure path.")
    return " ".join(part for part in parts if part)


def _collect_code_snippet_targets(code_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    targets: List[Dict[str, Any]] = []
    for key in ("route_binding", "span_binding"):
        binding = code_context.get(key) or {}
        if binding.get("module_path"):
            targets.append(
                {
                    "module_path": str(binding.get("module_path") or ""),
                    "symbol": str(binding.get("handler") or binding.get("symbol") or ""),
                    "line_start": int(binding.get("line_start") or 0),
                    "line_end": int(binding.get("line_end") or 0),
                }
            )
    search_matches = (code_context.get("search_context") or {}).get("matches") or []
    for item in search_matches[:3]:
        if not isinstance(item, dict) or not item.get("module_path"):
            continue
        targets.append(
            {
                "module_path": str(item.get("module_path") or ""),
                "symbol": str(item.get("symbol") or ""),
                "line_start": int(item.get("line_start") or 0),
                "line_end": int(item.get("line_end") or 0),
            }
        )

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for target in targets:
        key = (target["module_path"], target["symbol"], target["line_start"], target["line_end"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(target)
    return deduped[:3]


def _llm_safe_investigation_context(context: Dict[str, Any]) -> Dict[str, Any]:
    incident = context.get("incident") or {}
    component_snapshot = context.get("component_snapshot") or {}
    dependency_graph = context.get("dependency_graph") or {}
    metrics = context.get("metrics") or {}
    logs = context.get("elasticsearch") or {}
    traces = context.get("jaeger") or {}
    code_context = context.get("code_context") or {}
    source_context = context.get("source_context") or {}
    runbooks = context.get("runbooks") or {}
    evidence_assessment = context.get("evidence_assessment") or {}

    log_messages = _extract_log_messages(logs)[:4]
    trace_spans = _extract_trace_span_hints(traces)[:4]
    prompt_code_context = {
        "summary": code_context.get("summary") or _code_context_summary(code_context),
        "owner": code_context.get("owner") or {},
        "route_binding": code_context.get("route_binding") or {},
        "span_binding": code_context.get("span_binding") or {},
        "recent_changes": ((code_context.get("recent_changes") or {}).get("recent_changes") or [])[:4],
        "recent_deployments": ((code_context.get("recent_deployments") or {}).get("recent_deployments") or [])[:4],
        "blast_radius": (code_context.get("blast_radius") or {}).get("blast_radius") or {},
        "search_matches": ((code_context.get("search_context") or {}).get("matches") or [])[:4],
        "snippets": (code_context.get("snippets") or [])[:3],
    }
    prompt_source_context = {
        "traceback_count": source_context.get("traceback_count") or 0,
        "files": [
            {
                "container_path": item.get("container_path"),
                "local_path": item.get("local_path"),
                "function_name": item.get("function_name"),
                "line_number": item.get("line_number"),
                "snippet": item.get("snippet"),
            }
            for item in (source_context.get("files") or [])[:2]
            if isinstance(item, dict)
        ],
    }
    return {
        "scope": context.get("scope") or {},
        "application": context.get("application") or "",
        "service_name": context.get("service_name") or "",
        "target_host": context.get("target_host") or "",
        "incident": {
            "incident_key": incident.get("incident_key") or "",
            "title": incident.get("title") or "",
            "status": incident.get("status") or "",
            "summary": incident.get("summary") or "",
            "reasoning": incident.get("reasoning") or "",
            "blast_radius": incident.get("blast_radius") or [],
            "business_impact": incident.get("business_impact") or {},
        },
        "component_snapshot": component_snapshot,
        "dependency_graph": {
            "depends_on": dependency_graph.get("depends_on") or [],
            "blast_radius": dependency_graph.get("blast_radius") or [],
            "summary": dependency_graph.get("summary") or "",
        },
        "metrics": metrics,
        "log_messages": log_messages,
        "trace_spans": trace_spans,
        "linked_recommendation": context.get("linked_recommendation") or {},
        "runbooks": {
            "count": runbooks.get("count") or 0,
            "results": (runbooks.get("results") or [])[:2],
        },
        "evidence_assessment": evidence_assessment,
        "code_context": prompt_code_context,
        "source_context": prompt_source_context,
    }


def _extract_deployment_hint(incident: Optional[Any], linked_recommendation: Optional[Dict[str, Any]]) -> Dict[str, str]:
    labels = {}
    if incident and isinstance(getattr(incident, "labels", None), dict):
        labels.update(incident.labels or {})
    if isinstance(linked_recommendation, dict) and isinstance(linked_recommendation.get("labels"), dict):
        labels.update(linked_recommendation.get("labels") or {})
    return {
        "environment": str(labels.get("environment") or labels.get("env") or ""),
        "version": str(labels.get("version") or labels.get("release") or labels.get("image_tag") or ""),
    }


def _component_aliases(component: str) -> List[str]:
    if not component:
        return []
    normalized = str(component).strip().lower()
    aliases = {normalized, normalized.replace("_", "-"), normalized.replace("-", "_")}
    if normalized.startswith("app-"):
        aliases.add(normalized.replace("app-", ""))
    if normalized == "db":
        aliases.update({"postgres", "postgresql", "database", "psycopg2", "sql", "pg_"})
    elif normalized == "gateway":
        aliases.update({"nginx", "proxy"})
    elif normalized == "frontend":
        aliases.update({"ui", "browser", "nginx"})
    elif normalized == "toxiproxy":
        aliases.update({"proxy", "toxiproxy"})
    return sorted(alias for alias in aliases if alias)


def _message_mentions_component(message: str, component: str) -> bool:
    haystack = (message or "").lower()
    return any(alias in haystack for alias in _component_aliases(component))


def _logs_contain_traceback(log_payload: Dict[str, Any]) -> List[str]:
    """Return log messages that contain Python traceback references."""
    hits = ((log_payload or {}).get("hits") or {}).get("hits") or []
    result = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        msg = (hit.get("_source") or {}).get("message") or ""
        if any(marker in msg for marker in _TRACEBACK_MARKER):
            result.append(msg)
    return result


def _question_implies_active_incident(question: str) -> bool:
    q = (question or "").lower()
    return any(phrase in q for phrase in _ACTIVE_INCIDENT_PHRASES)


def find_investigation_incident(
    scope: Dict[str, str],
    incident_model,
    question: str = "",
) -> Optional[Any]:
    incident_key = scope.get("incident") or ""
    if incident_key:
        incident = incident_model.objects.filter(incident_key=incident_key).first()
        if incident:
            return incident

    service = scope.get("service") or ""
    if service:
        incident = incident_model.objects.filter(primary_service=service).order_by("-updated_at").first()
        if incident:
            return incident

    application = scope.get("application") or ""
    if application:
        incident = incident_model.objects.filter(application=application).order_by("-updated_at").first()
        if incident:
            return incident

    # Fallback: scope is empty but question implies "the active/current incident" —
    # return the most recently updated open or investigating incident.
    if not incident_key and not service and not application and _question_implies_active_incident(question):
        incident = (
            incident_model.objects
            .filter(status__in=["open", "investigating"])
            .order_by("-updated_at")
            .first()
        )
        if incident:
            return incident
        # No open incident — fall back to most recent regardless of status
        return incident_model.objects.order_by("-updated_at").first()

    return None


def find_component_snapshot(
    application_key: str,
    service: str,
    build_application_overview: Callable[..., Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    overview = build_application_overview(include_ai=True, include_predictions=True)
    for application in overview.get("results", []):
        if application.get("application") != application_key:
            continue
        for component in application.get("components", []):
            if component.get("service") == service or component.get("target_host") == service:
                return component
    return None


def should_fetch_runbooks(question: str, incident: Optional[Any]) -> bool:
    text = (question or "").lower()
    runbook_tokens = [
        "runbook",
        "playbook",
        "kb",
        "knowledge base",
        "procedure",
        "how do we fix",
        "how to fix",
        "what should we do",
        "remediation",
    ]
    return bool(incident) or any(token in text for token in runbook_tokens)


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _recommendation_is_fresh(recommendation: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(recommendation, dict):
        return False
    observed_at = _parse_timestamp(recommendation.get("created_at") or recommendation.get("last_execution_at"))
    if not observed_at:
        return False
    return (datetime.now(timezone.utc) - observed_at).total_seconds() <= LINKED_RECOMMENDATION_FRESHNESS_SECONDS


def _extract_metric_sample(result: Any) -> Optional[float]:
    if not isinstance(result, dict):
        return None
    series = result.get("result")
    if not isinstance(series, list) or not series:
        return None
    first = series[0] if isinstance(series[0], dict) else {}
    value = first.get("value") if isinstance(first, dict) else None
    if not isinstance(value, list) or len(value) < 2:
        return None
    try:
        return float(value[1])
    except (TypeError, ValueError):
        return None


def _extract_log_messages(logs: Dict[str, Any]) -> List[str]:
    hits = ((logs or {}).get("hits") or {}).get("hits") or []
    messages: List[str] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        source = hit.get("_source") if isinstance(hit.get("_source"), dict) else {}
        message = source.get("message")
        if isinstance(message, str) and message.strip():
            messages.append(message.strip())
    return messages


def _trace_has_error(traces: Dict[str, Any], *, db_related: bool = False) -> bool:
    for trace in (traces or {}).get("data") or []:
        if not isinstance(trace, dict):
            continue
        processes = trace.get("processes") if isinstance(trace.get("processes"), dict) else {}
        for span in trace.get("spans") or []:
            if not isinstance(span, dict):
                continue
            process = processes.get(span.get("processID") or "", {}) if isinstance(processes, dict) else {}
            haystack = " ".join(
                part for part in [
                    str(span.get("operationName") or ""),
                    json.dumps(span.get("tags") or [], default=str),
                    json.dumps(span.get("logs") or [], default=str),
                    json.dumps(process.get("tags") or [], default=str) if isinstance(process, dict) else "",
                ]
                if part
            ).lower()
            has_error = any(token in haystack for token in _ERROR_TOKENS)
            if not has_error:
                continue
            if not db_related:
                return True
            if any(token in haystack for token in _DB_TOKENS):
                return True
    return False


def _trace_has_component_error(traces: Dict[str, Any], component: str) -> bool:
    aliases = _component_aliases(component)
    if not aliases:
        return False
    for trace in (traces or {}).get("data") or []:
        if not isinstance(trace, dict):
            continue
        processes = trace.get("processes") if isinstance(trace.get("processes"), dict) else {}
        for span in trace.get("spans") or []:
            if not isinstance(span, dict):
                continue
            process = processes.get(span.get("processID") or "", {}) if isinstance(processes, dict) else {}
            haystack = " ".join(
                part for part in [
                    str(span.get("operationName") or ""),
                    json.dumps(span.get("tags") or [], default=str),
                    json.dumps(span.get("logs") or [], default=str),
                    json.dumps(process.get("tags") or [], default=str) if isinstance(process, dict) else "",
                ]
                if part
            ).lower()
            has_error = any(token in haystack for token in _ERROR_TOKENS)
            if has_error and any(alias in haystack for alias in aliases):
                return True
    return False


def _build_evidence_assessment(
    *,
    logs: Dict[str, Any],
    traces: Dict[str, Any],
    metrics: Dict[str, Any],
    dependency_graph: Dict[str, Any],
    linked_recommendation: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    service_evidence: List[str] = []
    dependency_hard_evidence: Dict[str, List[str]] = {}
    missing_evidence: List[str] = []
    contradicting_evidence: List[str] = []

    error_rate = _extract_metric_sample((metrics or {}).get("error_rate") or {})
    latency_p95 = _extract_metric_sample((metrics or {}).get("latency_p95_seconds") or {})
    log_messages = _extract_log_messages(logs)
    db_log_error = any(
        any(db_token in message.lower() for db_token in _DB_TOKENS)
        and any(err_token in message.lower() for err_token in _ERROR_TOKENS)
        for message in log_messages
    )
    db_trace_error = _trace_has_error(traces, db_related=True)
    generic_trace_error = _trace_has_error(traces, db_related=False)
    depends_on = (dependency_graph or {}).get("depends_on") or []
    blast_radius = (dependency_graph or {}).get("blast_radius") or []

    if error_rate is not None:
        if error_rate > 0.1:
            service_evidence.append(f"Service 5xx error rate is elevated at {error_rate:.2f} req/s.")
        elif error_rate <= 0.01:
            contradicting_evidence.append("Current 5xx error rate is low, so there is no active failure signal.")
    else:
        missing_evidence.append("No current service error-rate sample was available.")

    if latency_p95 is not None and latency_p95 > 2:
        service_evidence.append(f"Service p95 latency is elevated at {latency_p95:.2f}s.")

    if db_log_error:
        dependency_hard_evidence.setdefault("db", []).append("Recent logs contain database-related timeout or connection failures.")
    if db_trace_error:
        dependency_hard_evidence.setdefault("db", []).append("Recent traces contain failing database-related spans.")
    elif generic_trace_error:
        service_evidence.append("Recent traces show service-level failures, but not specifically in database spans.")

    for dependency in depends_on:
        if not dependency:
            continue
        evidence: List[str] = dependency_hard_evidence.get(str(dependency), [])
        if any(_message_mentions_component(message, dependency) and any(err_token in message.lower() for err_token in _ERROR_TOKENS) for message in log_messages):
            evidence.append(f"Recent logs mention {dependency} failures directly.")
        if _trace_has_component_error(traces, dependency):
            evidence.append(f"Recent traces contain failing spans for {dependency}.")
        if evidence:
            dependency_hard_evidence[str(dependency)] = list(dict.fromkeys(evidence))
        elif len(blast_radius) > 1:
            missing_evidence.append(f"Shared dependency topology points toward {dependency}, but there is no direct evidence yet.")

    if linked_recommendation and not _recommendation_is_fresh(linked_recommendation):
        contradicting_evidence.append("A stale cached recommendation was ignored because it was older than the freshness window.")

    safe_action = "observe"
    confidence_reason = "No hard failure evidence is present; treat the signal as informational until confirmed."
    if service_evidence:
        safe_action = "diagnose"
        confidence_reason = "There are live service-failure signals, but dependency attribution still requires direct evidence."
    best_dependency_target = next(iter(dependency_hard_evidence), "")
    if best_dependency_target:
        safe_action = "diagnose"
        confidence_reason = f"Dependency attribution is supported by direct evidence on {best_dependency_target}."

    hard_evidence = service_evidence[:]
    for evidence in dependency_hard_evidence.values():
        hard_evidence.extend(evidence)

    return {
        "safe_action": safe_action,
        "confidence_reason": confidence_reason,
        "service_hard_evidence": service_evidence,
        "dependency_hard_evidence": dependency_hard_evidence,
        "best_dependency_target": best_dependency_target,
        "hard_evidence": hard_evidence,
        "missing_evidence": missing_evidence,
        "contradicting_evidence": contradicting_evidence,
        "allow_dependency_pivot": bool(best_dependency_target),
    }


def build_investigation_context(
    question: str,
    body: Dict[str, Any],
    *,
    incident_model,
    build_application_overview: Callable[..., Dict[str, Any]],
    incident_timeline_payload: Callable[[Any], Dict[str, Any]],
    get_dependency_context: Callable[[str], Dict[str, Any]],
    application_graph_payload: Callable[[str], Optional[Dict[str, Any]]],
    fetch_elasticsearch_logs: Callable[[Optional[str], str], Dict[str, Any]],
    fetch_jaeger_traces: Callable[[Optional[str]], Dict[str, Any]],
    fetch_metrics_query: Callable[[str], Dict[str, Any]],
    mcp_orchestrator: Optional[InvestigationMCPOrchestrator] = None,
) -> Dict[str, Any]:
    scope = extract_investigation_scope(question, body)
    incident = find_investigation_incident(scope, incident_model=incident_model, question=question)
    if incident is None and _question_implies_active_incident(question):
        incident = find_investigation_incident({}, incident_model=incident_model, question=question)
    linked_recommendation = None
    application_graph = None
    component_snapshot = None
    dependency_context: Dict[str, Any] = {}
    logs: Dict[str, Any] = {}
    traces: Dict[str, Any] = {}
    prometheus_context: Dict[str, Any] = {}
    runbooks: Dict[str, Any] = {}
    code_context: Dict[str, Any] = {}

    application_key = scope.get("application") or ""
    service = scope.get("service") or ""
    if not application_key or not service:
        inferred_scope = _infer_runtime_entities_from_question(
            question,
            build_application_overview=build_application_overview,
        )
        application_key = application_key or inferred_scope.get("application") or ""
        service = service or inferred_scope.get("service") or ""

    timeline_payload = incident_timeline_payload(incident) if incident else None
    if incident:
        timeline_payload = (
            mcp_orchestrator.call_tool(
                "incidents.get_timeline",
                {
                    "incident_key": str(incident.incident_key),
                    "application": incident.application,
                    "service": incident.primary_service or incident.target_host,
                },
            ) if mcp_orchestrator else incident_timeline_payload(incident)
        )
        linked_recommendation = timeline_payload.get("linked_recommendation")
        if linked_recommendation and not _recommendation_is_fresh(linked_recommendation):
            linked_recommendation = None
        dependency_context = (
            incident.dependency_graph
            or (
                mcp_orchestrator.call_tool(
                    "topology.get_dependency_context",
                    {"service": incident.primary_service or incident.target_host},
                ) if mcp_orchestrator else get_dependency_context(incident.primary_service or incident.target_host)
            )
        )
        application_key = application_key or incident.application or dependency_context.get("application") or ""
        service = service or incident.primary_service or incident.target_host or ""
    else:
        dependency_context = (
            mcp_orchestrator.call_tool(
                "topology.get_dependency_context",
                {"service": service or ""},
            ) if mcp_orchestrator else get_dependency_context(service or "")
        )

    if application_key:
        application_graph = (
            mcp_orchestrator.call_tool(
                "applications.get_graph",
                {"application": application_key},
            ) if mcp_orchestrator else application_graph_payload(application_key)
        )

    if application_key and service:
        component_snapshot = (
            mcp_orchestrator.call_tool(
                "applications.get_component_snapshot",
                {"application": application_key, "service": service},
            ) if mcp_orchestrator else find_component_snapshot(
                application_key,
                service,
                build_application_overview=build_application_overview,
            )
        )

    target_host = (
        (component_snapshot or {}).get("target_host")
        or (incident.target_host if incident else "")
        or service
        or scope.get("service")
        or ""
    )
    service_name = (
        (component_snapshot or {}).get("service")
        or (incident.primary_service if incident else "")
        or service
        or target_host
    )

    if target_host or service_name:
        logs = (
            mcp_orchestrator.call_tool(
                "logs.search",
                {"target_host": target_host, "query": question or service_name},
            ) if mcp_orchestrator else fetch_elasticsearch_logs(target_host, question or service_name)
        )
        traces = (
            mcp_orchestrator.call_tool(
                "traces.search",
                {"service_name": service_name},
            ) if mcp_orchestrator else fetch_jaeger_traces(service_name)
        )
        prometheus_context = (
            mcp_orchestrator.call_tool(
                "metrics.query_service_overview",
                {"service_name": service_name},
            ) if mcp_orchestrator and service_name else {
                "latency_p95_seconds": fetch_metrics_query(
                    f'histogram_quantile(0.95, sum by (le) (rate(flask_http_request_duration_seconds_bucket{{job="{service_name}"}}[5m])))'
                ) if service_name else {},
                "error_rate": fetch_metrics_query(
                    f'sum(rate(flask_http_request_total{{job="{service_name}",status=~"5.."}}[5m]))'
                ) if service_name else {},
            }
        )

    if mcp_orchestrator and should_fetch_runbooks(question, incident):
        runbook_params = (
            {"incident_key": str(incident.incident_key)}
            if incident
            else {"query": question or service_name or application_key}
        )
        runbooks = mcp_orchestrator.call_tool("runbooks.search", runbook_params)

    # Source code context — parse tracebacks from logs and read the live source
    source_context: Dict[str, Any] = {}
    if mcp_orchestrator:
        traceback_messages = _logs_contain_traceback(logs)
        if traceback_messages:
            try:
                source_context = mcp_orchestrator.call_tool(
                    "source.read_traceback",
                    {"log_messages": traceback_messages},
                ) or {}
            except Exception:
                source_context = {}

    route_hint = _extract_route_hint(question, logs)
    span_hints = _extract_trace_span_hints(traces)
    deployment_hint = _extract_deployment_hint(incident, linked_recommendation)
    if mcp_orchestrator and (service_name or route_hint):
        try:
            owner = mcp_orchestrator.call_tool(
                "code.find_service_owner",
                {"service_name": service_name, "application_name": application_key},
            ) or {}
        except Exception:
            owner = {}
        if owner:
            code_context["owner"] = owner

        if route_hint:
            try:
                route_binding = mcp_orchestrator.call_tool(
                    "code.route_to_handler",
                    {"service_name": service_name, "route": route_hint, "http_method": ""},
                ) or {}
            except Exception:
                route_binding = {}
            if route_binding:
                code_context["route_binding"] = route_binding
                if not service_name:
                    service_name = str(route_binding.get("service_name") or service_name or "")
                if not owner and route_binding.get("repository"):
                    owner = {
                        "ok": True,
                        "repository": route_binding.get("repository"),
                        "service_name": service_name,
                        "application_name": application_key,
                        "repository_path": "",
                        "ownership_confidence": route_binding.get("confidence") or 0.5,
                        "metadata": {"matched_by": "route_binding_repository"},
                    }
                    code_context["owner"] = owner

        if span_hints:
            try:
                span_binding = mcp_orchestrator.call_tool(
                    "code.span_to_symbol",
                    {"service_name": service_name, "span_name": span_hints[0]},
                ) or {}
            except Exception:
                span_binding = {}
            if span_binding:
                code_context["span_binding"] = span_binding

        if deployment_hint.get("environment") or deployment_hint.get("version"):
            try:
                recent_deployments = mcp_orchestrator.call_tool(
                    "code.find_recent_deployments",
                    {
                        "service_name": service_name,
                        "environment": deployment_hint.get("environment") or "",
                        "version": deployment_hint.get("version") or "",
                    },
                ) or {}
            except Exception:
                recent_deployments = {}
            if recent_deployments:
                code_context["recent_deployments"] = recent_deployments

        repository_name = str(((code_context.get("owner") or {}).get("repository") or (code_context.get("route_binding") or {}).get("repository") or ""))
        module_path = str(((code_context.get("route_binding") or {}).get("module_path") or (code_context.get("span_binding") or {}).get("module_path") or ""))
        symbol_name = str(((code_context.get("span_binding") or {}).get("symbol") or (code_context.get("route_binding") or {}).get("handler") or ""))
        if repository_name:
            try:
                search_context = mcp_orchestrator.call_tool(
                    "code.search_context",
                    {
                        "repository": repository_name,
                        "query": question,
                        "service_name": service_name,
                        "limit": 6,
                    },
                ) or {}
            except Exception:
                search_context = {}
            if search_context:
                code_context["search_context"] = search_context

            try:
                recent_changes = mcp_orchestrator.call_tool(
                    "code.recent_changes_for_component",
                    {
                        "repository": repository_name,
                        "module_path": module_path,
                        "symbol": symbol_name,
                        "hours": 72,
                    },
                ) or {}
            except Exception:
                recent_changes = {}
            if recent_changes:
                code_context["recent_changes"] = recent_changes

            if symbol_name:
                try:
                    blast_radius = mcp_orchestrator.call_tool(
                        "code.blast_radius",
                        {
                            "repository": repository_name,
                            "symbol": symbol_name,
                            "route": route_hint,
                        },
                    ) or {}
                except Exception:
                    blast_radius = {}
                if blast_radius:
                    code_context["blast_radius"] = blast_radius

            snippets: List[Dict[str, Any]] = []
            for target in _collect_code_snippet_targets(code_context):
                try:
                    snippet = mcp_orchestrator.call_tool(
                        "code.read_snippet",
                        {
                            "repository": repository_name,
                            "module_path": target.get("module_path") or "",
                            "symbol": target.get("symbol") or "",
                            "line_start": target.get("line_start") or 0,
                            "line_end": target.get("line_end") or 0,
                            "context_lines": 18,
                        },
                    ) or {}
                except Exception:
                    snippet = {}
                if snippet.get("ok") and snippet.get("snippet"):
                    snippets.append(snippet)
            if snippets:
                code_context["snippets"] = snippets
            code_context["summary"] = _code_context_summary(code_context)

    context = {
        "scope": scope,
        "incident": timeline_payload,
        "linked_recommendation": linked_recommendation,
        "application_graph": application_graph,
        "component_snapshot": component_snapshot,
        "dependency_graph": dependency_context,
        "metrics": prometheus_context,
        "runbooks": runbooks,
        "elasticsearch": logs,
        "jaeger": traces,
        "source_context": source_context,
        "code_context": code_context,
        "target_host": target_host,
        "service_name": service_name,
        "application": application_key,
    }
    context["evidence_assessment"] = _build_evidence_assessment(
        logs=logs,
        traces=traces,
        metrics=prometheus_context,
        dependency_graph=dependency_context,
        linked_recommendation=linked_recommendation,
    )
    if mcp_orchestrator:
        context["retrieval"] = mcp_orchestrator.tool_trace()
    return context


def run_investigation_route(
    question: str,
    body: Dict[str, Any],
    conversation_history: str,
    *,
    llm_query: Callable[[str], tuple],
    incident_model,
    build_application_overview: Callable[..., Dict[str, Any]],
    incident_timeline_payload: Callable[[Any], Dict[str, Any]],
    get_dependency_context: Callable[[str], Dict[str, Any]],
    application_graph_payload: Callable[[str], Optional[Dict[str, Any]]],
    fetch_elasticsearch_logs: Callable[[Optional[str], str], Dict[str, Any]],
    fetch_jaeger_traces: Callable[[Optional[str]], Dict[str, Any]],
    fetch_metrics_query: Callable[[str], Dict[str, Any]],
    compute_incident_revenue_impact: Callable[[Any], Dict[str, Any]],
    logger,
    chat_session=None,
    user=None,
    source_path_map: Optional[Dict[str, str]] = None,
    source_root: str = "",
) -> Dict[str, Any]:
    scope = extract_investigation_scope(question, body)
    mcp_orchestrator = InvestigationMCPOrchestrator(
        question=question,
        logger=logger,
        incident_model=incident_model,
        find_investigation_incident=find_investigation_incident,
        build_application_overview=build_application_overview,
        incident_timeline_payload=incident_timeline_payload,
        get_dependency_context=get_dependency_context,
        application_graph_payload=application_graph_payload,
        fetch_elasticsearch_logs=fetch_elasticsearch_logs,
        fetch_jaeger_traces=fetch_jaeger_traces,
        fetch_metrics_query=fetch_metrics_query,
        chat_session=chat_session,
        user=user,
        source_path_map=source_path_map,
        source_root=source_root,
    )
    mcp_orchestrator.start_run(scope)
    investigation_context = build_investigation_context(
        question,
        body,
        incident_model=incident_model,
        build_application_overview=build_application_overview,
        incident_timeline_payload=incident_timeline_payload,
        get_dependency_context=get_dependency_context,
        application_graph_payload=application_graph_payload,
        fetch_elasticsearch_logs=fetch_elasticsearch_logs,
        fetch_jaeger_traces=fetch_jaeger_traces,
        fetch_metrics_query=fetch_metrics_query,
        mcp_orchestrator=mcp_orchestrator,
    )
    workflow = build_investigation_workflow(
        question=question,
        scope=scope,
        context=investigation_context,
    )

    incident_data = investigation_context.get("incident") or {}
    business_impact = incident_data.get("business_impact") or {}
    if not business_impact and investigation_context.get("scope"):
        scope = investigation_context["scope"]
        inc = find_investigation_incident(scope, incident_model=incident_model)
        if inc:
            business_impact = compute_incident_revenue_impact(inc) or {}
        elif _question_implies_active_incident(question):
            inc = find_investigation_incident({}, incident_model=incident_model, question=question)
            if inc:
                business_impact = compute_incident_revenue_impact(inc) or {}

    prompt_context = _llm_safe_investigation_context(investigation_context)

    prompt = (
        "You are an AIOps incident investigation assistant. "
        "Use the incident context, metrics, logs, traces, dependency graph, code-context bindings, and any available runbook guidance to answer the user's question. "
        "Provide a concise RCA-oriented answer as JSON with exactly these keys: "
        "'answer', 'confidence', 'supporting_evidence', 'contradicting_evidence', 'next_verification_step', 'follow_up_questions'.\n"
        "- 'answer': explain the likely root cause, blast radius, strongest evidence, what the affected module/handler does, and the next best diagnostic step.\n"
        "- 'confidence': one of 'high', 'medium', or 'low'. Use 'high' only when multiple independent signals agree. Use 'low' when data is missing or ambiguous.\n"
        "- 'supporting_evidence': list of up to 4 short strings describing specific signals that support the root cause (e.g. metric spikes, log errors, trace failures).\n"
        "- 'contradicting_evidence': list of up to 3 short strings describing signals that weaken or contradict the hypothesis (e.g. other services still healthy, no correlated spikes). Empty list if none.\n"
        "- 'next_verification_step': single concrete action that would confirm or refute the root cause (e.g. a specific command to run, metric to check, or log to review).\n"
        "- 'follow_up_questions': list of 3-4 natural language follow-up questions an operator might ask next.\n"
        "- ALWAYS include revenue/business impact in 'answer' if available in the context.\n"
        "- If a linked recommendation or diagnostic command exists, mention it directly.\n"
        "- If runbook guidance is available, reference it in 'answer' and mark guidance as runbook-backed.\n"
        "- If code_context is available, explain the likely repository, handler, symbol, and module responsibility in plain language.\n"
        "- If code snippets are available, use them to explain what the affected code path appears to do and why it could produce the observed symptoms.\n"
        "- If recent code changes are available, use them as supporting evidence only when they plausibly touch the failing path.\n"
        "- When asked about remediation, use the code context to suggest the safest validation target after the fix, such as the route, span, handler, or file path to verify.\n"
        "- Use evidence_assessment as the safety policy. Do not claim a downstream/shared dependency root cause unless dependency_hard_evidence is non-empty.\n"
        "- If safe_action is 'observe' or hard_evidence is empty, explicitly say the current signal may reflect normal traffic/load and that remediation is not justified yet.\n"
        "- If service_hard_evidence exists but dependency_hard_evidence is empty, keep the hypothesis scoped to the impacted component and recommend verification, not dependency remediation.\n"
        "- Do not answer with raw PromQL unless the user explicitly asked for a Prometheus query.\n\n"
        f"RECENT CONVERSATION:\n{conversation_history or 'No prior conversation.'}\n\n"
        f"QUESTION: {question}\n\n"
        f"INVESTIGATION CONTEXT:\n{json.dumps(prompt_context, indent=2, default=str)[:5500]}\n\n"
        "Return JSON only."
    )
    ok, _status, body_text = llm_query(prompt)
    if not ok:
        mcp_orchestrator.finish_run(status="failed", context_summary=investigation_context, target_host=investigation_context.get("target_host") or "")
        raise RuntimeError(body_text)

    try:
        start_index = body_text.find("{")
        end_index = body_text.rfind("}")
        parsed = json.loads(body_text[start_index:end_index + 1]) if start_index != -1 and end_index != -1 else {}
    except json.JSONDecodeError:
        parsed = {"answer": body_text, "follow_up_questions": []}

    response = {
        "question": question,
        "answer": parsed.get("answer") or body_text,
        "confidence": parsed.get("confidence") or "medium",
        "confidence_reason": parsed.get("confidence_reason") or ((investigation_context.get("evidence_assessment") or {}).get("confidence_reason")) or "",
        "hard_evidence": parsed.get("hard_evidence") or ((investigation_context.get("evidence_assessment") or {}).get("hard_evidence")) or [],
        "missing_evidence": parsed.get("missing_evidence") or ((investigation_context.get("evidence_assessment") or {}).get("missing_evidence")) or [],
        "decision_policy": ((investigation_context.get("evidence_assessment") or {}).get("safe_action")) or "diagnose",
        "supporting_evidence": parsed.get("supporting_evidence") or [],
        "contradicting_evidence": parsed.get("contradicting_evidence") or [],
        "next_verification_step": parsed.get("next_verification_step") or "",
        "follow_up_questions": parsed.get("follow_up_questions") or [],
        "suggested_command": ((investigation_context.get("linked_recommendation") or {}).get("diagnostic_command")),
        "target_host": investigation_context.get("target_host"),
        "business_impact": business_impact,
        "cached": False,
        "code_context": investigation_context.get("code_context") or {},
        "retrieval": investigation_context.get("retrieval") or mcp_orchestrator.tool_trace(),
    }
    response["workflow"] = finalize_investigation_workflow(workflow, response)
    mcp_orchestrator.finish_run(status="completed", context_summary=response, target_host=investigation_context.get("target_host") or "")
    return response
