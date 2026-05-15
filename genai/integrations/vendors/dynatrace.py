import requests
import datetime
from typing import Dict, List, Optional
from ..base import BaseTracesAdapter, NormalizedTraceResult, NormalizedTopologyResult
from ..registry import IntegrationRegistry
from .common import credential_secret, parse_timestamp


class DynatraceAdapter(BaseTracesAdapter):
    def _headers(self):
        token = credential_secret(self.integration)
        return {"Authorization": f"Api-Token {token}"} if token else {}

    def test_connection(self) -> bool:
        try:
            url = f"{self.integration.endpoint_url.rstrip('/')}/api/v1/time"
            response = requests.get(url, headers=self._headers(), timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def fetch_traces(self, service_name: str, time_range: tuple, tags: Optional[Dict[str, str]] = None) -> List[NormalizedTraceResult]:
        if not self.integration.endpoint_url:
            return []
        start, end = time_range if isinstance(time_range, tuple) and len(time_range) == 2 else (None, None)
        now = datetime.datetime.now(datetime.timezone.utc)
        params = {
            "from": (start or (now - datetime.timedelta(minutes=30))).isoformat(),
            "to": (end or now).isoformat(),
            "pageSize": 100,
        }
        if service_name:
            params["filter"] = f'contains(service.name,"{service_name}")'
        response = requests.get(
            f"{self.integration.endpoint_url.rstrip('/')}/api/v2/spans",
            params=params,
            headers=self._headers(),
            timeout=20,
        )
        if response.status_code == 404:
            return []
        response.raise_for_status()
        rows: List[NormalizedTraceResult] = []
        for span in response.json().get("spans") or response.json().get("data") or []:
            tags_payload = span.get("attributes") or span.get("tags") or {}
            rows.append(
                NormalizedTraceResult(
                    trace_id=str(span.get("traceId") or span.get("trace_id") or ""),
                    span_id=str(span.get("spanId") or span.get("span_id") or ""),
                    service_name=str(tags_payload.get("service.name") or service_name),
                    operation_name=str(span.get("name") or span.get("operationName") or ""),
                    duration_ms=float(span.get("duration") or span.get("duration_ms") or 0),
                    start_time=parse_timestamp(span.get("startTime") or span.get("start_time")),
                    tags=tags_payload,
                )
            )
        return rows

    def fetch_topology(self) -> List[NormalizedTopologyResult]:
        if not self.integration.endpoint_url:
            return []
        response = requests.get(
            f"{self.integration.endpoint_url.rstrip('/')}/api/v2/entities",
            params={"pageSize": 100, "entitySelector": 'type("SERVICE")'},
            headers=self._headers(),
            timeout=20,
        )
        response.raise_for_status()
        rows: List[NormalizedTopologyResult] = []
        for entity in response.json().get("entities") or []:
            rows.append(
                NormalizedTopologyResult(
                    node_id=str(entity.get("entityId") or ""),
                    node_type="service",
                    name=str(entity.get("displayName") or entity.get("entityId") or ""),
                    status=str(entity.get("managementZones") or "unknown"),
                    attributes=entity,
                    relations=[],
                )
            )
        return rows


IntegrationRegistry.register("dynatrace", DynatraceAdapter)
