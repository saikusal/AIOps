import requests
from typing import Dict, List, Optional
from ..base import BaseTracesAdapter, NormalizedTraceResult
from ..registry import IntegrationRegistry
from ...trace_backend import TempoBackend
import datetime


class TempoAdapter(BaseTracesAdapter):
    def test_connection(self) -> bool:
        try:
            url = f"{self.integration.endpoint_url.rstrip('/')}/ready"
            response = requests.get(url, timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def fetch_traces(self, service_name: str, time_range: tuple, tags: Optional[Dict[str, str]] = None) -> List[NormalizedTraceResult]:
        backend = TempoBackend(base_url=self.integration.endpoint_url or "http://tempo:3200")
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


IntegrationRegistry.register("tempo", TempoAdapter)
