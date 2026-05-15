import datetime
from typing import Any, Dict, List, Optional

import requests

from ..base import (
    BaseAdapter,
    BaseAlertsAdapter,
    BaseLogsAdapter,
    BaseMetricsAdapter,
    BaseTracesAdapter,
    NormalizedAlertResult,
    NormalizedLogResult,
    NormalizedMetricResult,
    NormalizedTraceResult,
)
from ..registry import IntegrationRegistry
from .prometheus import PrometheusAdapter
from .opensearch import OpenSearchAdapter
from ...trace_backend import JaegerBackend
from .common import credential_metadata, credential_secret, parse_timestamp


class VictoriaMetricsAdapter(PrometheusAdapter):
    def test_connection(self) -> bool:
        base = (self.integration.endpoint_url or "").rstrip("/")
        for suffix in ("/health", "/api/v1/status/tsdb"):
            try:
                response = requests.get(f"{base}{suffix}", timeout=5)
                if response.status_code == 200:
                    return True
            except Exception:
                continue
        return False


class ElasticsearchAdapter(OpenSearchAdapter):
    pass


class JaegerAdapter(BaseTracesAdapter):
    def test_connection(self) -> bool:
        return bool(JaegerBackend(base_url=self.integration.endpoint_url or "http://jaeger:16686").health_check().get("healthy"))

    def fetch_traces(self, service_name: str, time_range: tuple, tags: Optional[Dict[str, str]] = None) -> List[NormalizedTraceResult]:
        backend = JaegerBackend(base_url=self.integration.endpoint_url or "http://jaeger:16686")
        start, end = time_range if isinstance(time_range, tuple) and len(time_range) == 2 else (None, None)
        traces = backend.search_traces(service_name, from_ts=start, to_ts=end, limit=25, tags=tags)
        results: List[NormalizedTraceResult] = []
        for trace in traces:
            trace_id = str(trace.get("trace_id") or "")
            for span in trace.get("spans") or []:
                start_time = span.get("start_time") or 0
                duration_us = float(span.get("duration_us") or 0)
                results.append(
                    NormalizedTraceResult(
                        trace_id=trace_id,
                        span_id=str(span.get("span_id") or ""),
                        service_name=str((span.get("tags") or {}).get("service.name") or trace.get("root_service") or service_name),
                        operation_name=str(span.get("operation") or trace.get("root_operation") or ""),
                        duration_ms=round(duration_us / 1000.0, 3),
                        start_time=datetime.datetime.fromtimestamp(float(start_time) / 1_000_000, tz=datetime.timezone.utc) if start_time else datetime.datetime.now(datetime.timezone.utc),
                        tags=span.get("tags") or {},
                    )
                )
        return results


class LokiAdapter(BaseLogsAdapter):
    def test_connection(self) -> bool:
        try:
            response = requests.get(f"{self.integration.endpoint_url.rstrip('/')}/loki/api/v1/labels", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def fetch_logs(self, query: str, time_range: tuple, limit: int = 100) -> List[NormalizedLogResult]:
        if not self.integration.endpoint_url:
            return []
        params = {"query": query or '{job=~".+"}', "limit": max(1, min(int(limit or 100), 500))}
        response = requests.get(f"{self.integration.endpoint_url.rstrip('/')}/loki/api/v1/query", params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()
        results: List[NormalizedLogResult] = []
        for stream in (((payload.get("data") or {}).get("result")) or []):
            labels = stream.get("stream") or {}
            for value in stream.get("values") or []:
                if len(value) < 2:
                    continue
                timestamp_ns, message = value[0], value[1]
                try:
                    timestamp = datetime.datetime.fromtimestamp(float(timestamp_ns) / 1_000_000_000, tz=datetime.timezone.utc)
                except (TypeError, ValueError, OSError):
                    timestamp = datetime.datetime.now(datetime.timezone.utc)
                results.append(
                    NormalizedLogResult(
                        timestamp=timestamp,
                        message=str(message or ""),
                        level=str(labels.get("level") or "info"),
                        source=str(labels.get("service_name") or labels.get("service") or self.integration.name),
                        attributes=labels,
                    )
                )
        return results


class NewRelicAdapter(BaseMetricsAdapter, BaseLogsAdapter, BaseTracesAdapter):
    def _headers(self) -> Dict[str, str]:
        secret = credential_secret(self.integration)
        return {"Api-Key": secret, "Content-Type": "application/json"} if secret else {"Content-Type": "application/json"}

    def _account_id(self) -> str:
        return str((self.integration.metadata_json or {}).get("account_id") or (credential_metadata(self.integration).get("account_id")) or "")

    def test_connection(self) -> bool:
        try:
            response = requests.post(
                self.integration.endpoint_url.rstrip("/") or "https://api.newrelic.com/graphql",
                headers=self._headers(),
                json={"query": "{ actor { user { name } } }"},
                timeout=8,
            )
            return response.status_code == 200 and not response.json().get("errors")
        except Exception:
            return False

    def _nrql(self, nrql: str) -> List[Dict[str, Any]]:
        account_id = self._account_id()
        if not account_id:
            return []
        query = """
        query($accountId: Int!, $nrql: Nrql!) {
          actor { account(id: $accountId) { nrql(query: $nrql) { results } } }
        }
        """
        response = requests.post(
            self.integration.endpoint_url.rstrip("/") or "https://api.newrelic.com/graphql",
            headers=self._headers(),
            json={"query": query, "variables": {"accountId": int(account_id), "nrql": nrql}},
            timeout=20,
        )
        response.raise_for_status()
        return (((response.json().get("data") or {}).get("actor") or {}).get("account") or {}).get("nrql", {}).get("results") or []

    def fetch_metrics(self, query: str, time_range: tuple) -> List[NormalizedMetricResult]:
        rows: List[NormalizedMetricResult] = []
        for item in self._nrql(query):
            for key, value in item.items():
                if isinstance(value, (int, float)):
                    rows.append(
                        NormalizedMetricResult(
                            metric_name=str(key),
                            value=float(value),
                            timestamp=parse_timestamp(item.get("timestamp")),
                            labels={k: str(v) for k, v in item.items() if not isinstance(v, (dict, list))},
                        )
                    )
        return rows

    def fetch_logs(self, query: str, time_range: tuple, limit: int = 100) -> List[NormalizedLogResult]:
        nrql = query if str(query or "").lower().startswith("select ") else f"SELECT timestamp, message, level, service.name FROM Log WHERE message LIKE '%{str(query or '')[:80]}%' LIMIT {max(1, min(int(limit or 100), 500))}"
        rows: List[NormalizedLogResult] = []
        for item in self._nrql(nrql):
            rows.append(
                NormalizedLogResult(
                    timestamp=parse_timestamp(item.get("timestamp")),
                    message=str(item.get("message") or ""),
                    level=str(item.get("level") or "info"),
                    source=str(item.get("service.name") or item.get("serviceName") or self.integration.name),
                    attributes=item,
                )
            )
        return rows

    def fetch_traces(self, service_name: str, time_range: tuple, tags: Optional[Dict[str, str]] = None) -> List[NormalizedTraceResult]:
        nrql = f"SELECT trace.id, span.id, name, duration.ms, timestamp FROM Span WHERE service.name = '{service_name}' LIMIT 100"
        rows: List[NormalizedTraceResult] = []
        for item in self._nrql(nrql):
            rows.append(
                NormalizedTraceResult(
                    trace_id=str(item.get("trace.id") or ""),
                    span_id=str(item.get("span.id") or ""),
                    service_name=service_name,
                    operation_name=str(item.get("name") or ""),
                    duration_ms=float(item.get("duration.ms") or item.get("duration") or 0),
                    start_time=parse_timestamp(item.get("timestamp")),
                    tags=item,
                )
            )
        return rows


class NagiosAdapter(BaseAlertsAdapter):
    def test_connection(self) -> bool:
        try:
            response = requests.get(self.integration.endpoint_url.rstrip("/") or "", timeout=5)
            return response.status_code in {200, 401, 403}
        except Exception:
            return False

    def fetch_alert_state(self) -> List[NormalizedAlertResult]:
        if not self.integration.endpoint_url:
            return []
        response = requests.get(self.integration.endpoint_url.rstrip("/"), timeout=15)
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        alerts = payload.get("alerts") or payload.get("services") or []
        results: List[NormalizedAlertResult] = []
        for item in alerts if isinstance(alerts, list) else []:
            labels = {str(k): str(v) for k, v in (item.get("labels") or item).items() if not isinstance(v, (dict, list))}
            status = str(item.get("status") or item.get("state") or "unknown").lower()
            results.append(
                NormalizedAlertResult(
                    alert_name=str(item.get("alert_name") or item.get("host_name") or item.get("service_description") or "NagiosAlert"),
                    status="firing" if status not in {"ok", "up", "0"} else "resolved",
                    severity=str(item.get("severity") or item.get("state") or "warning"),
                    description=str(item.get("plugin_output") or item.get("description") or ""),
                    starts_at=parse_timestamp(item.get("last_state_change") or item.get("last_check")),
                    labels=labels,
                )
            )
        return results


class AzureAdapter(BaseAdapter):
    def test_connection(self) -> bool:
        metadata = credential_metadata(self.integration)
        return bool(metadata.get("tenant_id") and metadata.get("client_id") and credential_secret(self.integration))


class GCPAdapter(BaseAdapter):
    def test_connection(self) -> bool:
        metadata = credential_metadata(self.integration)
        return bool(metadata.get("project_id") and (credential_secret(self.integration) or metadata.get("service_account_json")))


class CustomAdapter(BaseAdapter):
    def test_connection(self) -> bool:
        return bool(self.integration.endpoint_url)


IntegrationRegistry.register("victoriametrics", VictoriaMetricsAdapter)
IntegrationRegistry.register("elasticsearch", ElasticsearchAdapter)
IntegrationRegistry.register("jaeger", JaegerAdapter)
IntegrationRegistry.register("loki", LokiAdapter)
IntegrationRegistry.register("newrelic", NewRelicAdapter)
IntegrationRegistry.register("nagios", NagiosAdapter)
IntegrationRegistry.register("azure", AzureAdapter)
IntegrationRegistry.register("gcp", GCPAdapter)
IntegrationRegistry.register("custom", CustomAdapter)
