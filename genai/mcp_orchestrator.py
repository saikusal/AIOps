import uuid
from typing import Any, Callable, Dict, Optional

from django.utils import timezone

from .mcp_client import MCPClient
from .mcp_registry import MCPRegistry
from .mcp_services import (
    applications_get_component_snapshot,
    applications_get_graph,
    incidents_get_timeline,
    logs_search,
    metrics_query_service_overview,
    runbooks_search,
    source_read_traceback,
    traces_search,
)
from .mcp_types import MCPToolCall, MCPToolDefinition, MCPToolResult


def _safe_json_payload(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_safe_json_payload(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _safe_json_payload(item) for key, item in value.items()}
    if hasattr(value, "incident_key"):
        return str(getattr(value, "incident_key"))
    return str(value)


class InvestigationMCPOrchestrator:
    def __init__(
        self,
        *,
        question: str,
        logger,
        incident_model,
        find_investigation_incident: Callable[[Dict[str, str], Any], Optional[Any]],
        build_application_overview: Callable[..., Dict[str, Any]],
        incident_timeline_payload: Callable[[Any], Dict[str, Any]],
        get_dependency_context: Callable[[str], Dict[str, Any]],
        application_graph_payload: Callable[[str], Optional[Dict[str, Any]]],
        fetch_elasticsearch_logs: Callable[[Optional[str], str], Dict[str, Any]],
        fetch_jaeger_traces: Callable[[Optional[str]], Dict[str, Any]],
        fetch_metrics_query: Callable[[str], Dict[str, Any]],
        chat_session=None,
        user=None,
        source_path_map: Optional[Dict[str, str]] = None,
        source_root: str = "",
    ) -> None:
        self.question = question
        self.logger = logger
        self.chat_session = chat_session
        self.user = user
        self.incident_model = incident_model
        self.find_investigation_incident = find_investigation_incident
        self.build_application_overview = build_application_overview
        self.incident_timeline_payload = incident_timeline_payload
        self.get_dependency_context = get_dependency_context
        self.application_graph_payload = application_graph_payload
        self.fetch_elasticsearch_logs = fetch_elasticsearch_logs
        self.fetch_jaeger_traces = fetch_jaeger_traces
        self.fetch_metrics_query = fetch_metrics_query
        self.source_path_map: Dict[str, str] = source_path_map or {}
        self.source_root: str = source_root
        self.registry = MCPRegistry()
        self.client = MCPClient(self.registry)
        self.investigation_run = None
        self.tool_results = []
        self._register_tools()

    def _register_tools(self) -> None:
        self.registry.register(MCPToolDefinition("incidents-mcp", "incidents.get_timeline", "Fetch incident timeline and summary", self._tool_incidents_get_timeline, endpoint_path="/genai/mcp/incidents/timeline/"))
        self.registry.register(MCPToolDefinition("applications-mcp", "applications.get_graph", "Fetch application graph", self._tool_applications_get_graph, endpoint_path="/genai/mcp/applications/graph/"))
        self.registry.register(MCPToolDefinition("applications-mcp", "applications.get_component_snapshot", "Fetch application component snapshot", self._tool_applications_get_component_snapshot, endpoint_path="/genai/mcp/applications/component/"))
        self.registry.register(MCPToolDefinition("topology-mcp", "topology.get_dependency_context", "Fetch dependency graph context", self._tool_topology_get_dependency_context))
        self.registry.register(MCPToolDefinition("metrics-mcp", "metrics.query_service_overview", "Fetch scoped VictoriaMetrics health queries", self._tool_metrics_query_service_overview, endpoint_path="/genai/mcp/metrics/service/"))
        self.registry.register(MCPToolDefinition("logs-mcp", "logs.search", "Search logs for host and question context", self._tool_logs_search, endpoint_path="/genai/mcp/logs/search/"))
        self.registry.register(MCPToolDefinition("traces-mcp", "traces.search", "Fetch recent traces for a service", self._tool_traces_search, endpoint_path="/genai/mcp/traces/search/"))
        self.registry.register(MCPToolDefinition("runbooks-mcp", "runbooks.search", "Search generated incident runbooks", self._tool_runbooks_search, endpoint_path="/genai/mcp/runbooks/search/"))
        self.registry.register(MCPToolDefinition("source-mcp", "source.read_traceback", "Parse Python tracebacks from logs and return live source snippets + SQL schema files for the referenced functions", self._tool_source_read_traceback))

    def start_run(self, scope: Dict[str, str]) -> None:
        incident = self.find_investigation_incident(scope, incident_model=self.incident_model)
        try:
            from .models import InvestigationRun

            self.investigation_run = InvestigationRun.objects.create(
                session=self.chat_session,
                user=self.user if getattr(self.user, "is_authenticated", False) else None,
                incident=incident,
                question=self.question,
                application=scope.get("application") or "",
                service=scope.get("service") or "",
                scope_json=scope,
                route="investigation",
                status="running",
            )
        except Exception as exc:
            self.logger.warning("Failed to create InvestigationRun: %s", exc)
            self.investigation_run = None

    def finish_run(self, *, status: str, context_summary: Optional[Dict[str, Any]] = None, target_host: str = "") -> None:
        if not self.investigation_run:
            return
        try:
            self.investigation_run.status = status
            self.investigation_run.target_host = target_host or self.investigation_run.target_host
            if context_summary:
                self.investigation_run.evidence_summary = _safe_json_payload(context_summary)
            self.investigation_run.completed_at = timezone.now()
            self.investigation_run.save(update_fields=["status", "target_host", "evidence_summary", "completed_at", "updated_at"])
        except Exception as exc:
            self.logger.warning("Failed to finalize InvestigationRun %s: %s", self.investigation_run.run_id, exc)

    def call_tool(self, tool_name: str, params: Dict[str, Any]) -> Any:
        definition = self.registry.get(tool_name)
        result = self.client.invoke(
            MCPToolCall(
                server_name=definition.server_name,
                tool_name=tool_name,
                params=params,
            )
        )
        self.tool_results.append(result)
        self._record_tool_invocation(result)
        if not result.ok:
            raise RuntimeError(f"{tool_name} failed: {result.error}")
        return result.content

    def tool_trace(self) -> Dict[str, Any]:
        return {
            "mode": "mcp",
            "run_id": str(self.investigation_run.run_id) if self.investigation_run else "",
            "tool_calls": [
                {
                    "server_name": result.server_name,
                    "tool_name": result.tool_name,
                    "latency_ms": result.latency_ms,
                    "ok": result.ok,
                }
                for result in self.tool_results
            ],
        }

    def _record_tool_invocation(self, result: MCPToolResult) -> None:
        try:
            from .models import ToolInvocation

            ToolInvocation.objects.create(
                investigation_run=self.investigation_run,
                session=self.chat_session,
                user=self.user if getattr(self.user, "is_authenticated", False) else None,
                incident=getattr(self.investigation_run, "incident", None),
                invocation_id=f"tool-{uuid.uuid4().hex}",
                server_name=result.server_name,
                tool_name=result.tool_name,
                request_json=_safe_json_payload(result.params) or {},
                response_json=_safe_json_payload(result.content) or {},
                status="success" if result.ok else "error",
                latency_ms=max(result.latency_ms, 0),
                error_detail=result.error[:4000],
            )
        except Exception as exc:
            self.logger.warning("Failed to persist ToolInvocation for %s: %s", result.tool_name, exc)

    def _tool_incidents_get_timeline(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return incidents_get_timeline(
            incident_key=str(params.get("incident_key") or ""),
            incident_model=self.incident_model,
            incident_timeline_payload=self.incident_timeline_payload,
        )

    def _tool_applications_get_graph(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return applications_get_graph(
            application=str(params.get("application") or ""),
            application_graph_payload=self.application_graph_payload,
        )

    def _tool_applications_get_component_snapshot(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return applications_get_component_snapshot(
            application=str(params.get("application") or ""),
            service=str(params.get("service") or ""),
            build_application_overview=self.build_application_overview,
        )

    def _tool_topology_get_dependency_context(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = str(params.get("service") or "")
        return self.get_dependency_context(service) or {}

    def _tool_metrics_query_service_overview(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return metrics_query_service_overview(
            service_name=str(params.get("service_name") or ""),
            fetch_metrics_query=self.fetch_metrics_query,
        )

    def _tool_logs_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return logs_search(
            target_host=str(params.get("target_host") or "") or None,
            query=str(params.get("query") or ""),
            fetch_elasticsearch_logs=self.fetch_elasticsearch_logs,
        ) or {}

    def _tool_traces_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return traces_search(
            service_name=str(params.get("service_name") or "") or None,
            fetch_jaeger_traces=self.fetch_jaeger_traces,
        ) or {}

    def _tool_runbooks_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from .models import Runbook

        return runbooks_search(
            query=str(params.get("query") or ""),
            incident_key=str(params.get("incident_key") or ""),
            incident_model=self.incident_model,
            runbook_model=Runbook,
        )

    def _tool_source_read_traceback(self, params: Dict[str, Any]) -> Dict[str, Any]:
        log_messages = params.get("log_messages") or []
        if isinstance(log_messages, str):
            log_messages = [log_messages]
        return source_read_traceback(
            log_messages=log_messages,
            path_prefix_map=self.source_path_map,
            source_root=self.source_root,
        )
