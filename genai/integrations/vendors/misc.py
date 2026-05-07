import datetime
from typing import Dict, List, Optional

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
    def test_connection(self) -> bool:
        try:
            headers = {"Api-Key": str(getattr(self.integration.credential, "secret_ref", "") or "")}
            response = requests.get(f"{self.integration.endpoint_url.rstrip('/')}/v1/accounts", headers=headers, timeout=5)
            return response.status_code in {200, 401, 403}
        except Exception:
            return False

    def fetch_metrics(self, query: str, time_range: tuple) -> List[NormalizedMetricResult]:
        return []

    def fetch_logs(self, query: str, time_range: tuple, limit: int = 100) -> List[NormalizedLogResult]:
        return []

    def fetch_traces(self, service_name: str, time_range: tuple, tags: Optional[Dict[str, str]] = None) -> List[NormalizedTraceResult]:
        return []


class NagiosAdapter(BaseAlertsAdapter):
    def test_connection(self) -> bool:
        try:
            response = requests.get(self.integration.endpoint_url.rstrip("/") or "", timeout=5)
            return response.status_code in {200, 401, 403}
        except Exception:
            return False

    def fetch_alert_state(self) -> List[NormalizedAlertResult]:
        return []


class AzureAdapter(BaseAdapter):
    def test_connection(self) -> bool:
        return True


class GCPAdapter(BaseAdapter):
    def test_connection(self) -> bool:
        return True


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
