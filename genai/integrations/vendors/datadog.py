import datetime
import requests
from typing import List
from ..base import BaseMetricsAdapter, NormalizedMetricResult, BaseLogsAdapter, NormalizedLogResult
from ..registry import IntegrationRegistry
from .common import credential_metadata, credential_secret, parse_timestamp


class DatadogAdapter(BaseMetricsAdapter, BaseLogsAdapter):
    def test_connection(self) -> bool:
        try:
            url = f"{self.integration.endpoint_url.rstrip('/')}/api/v1/validate"
            headers = self._headers()
            response = requests.get(url, headers=headers, timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def _headers(self):
        metadata = credential_metadata(self.integration)
        headers = {"DD-API-KEY": credential_secret(self.integration)}
        app_key = str(metadata.get("application_key") or "")
        if app_key:
            headers["DD-APPLICATION-KEY"] = app_key
        return {key: value for key, value in headers.items() if value}

    def fetch_metrics(self, query: str, time_range: tuple) -> List[NormalizedMetricResult]:
        if not query or not self.integration.endpoint_url:
            return []
        start, end = time_range if isinstance(time_range, tuple) and len(time_range) == 2 else (None, None)
        now = datetime.datetime.now(datetime.timezone.utc)
        start = start or (now - datetime.timedelta(minutes=30))
        end = end or now
        response = requests.get(
            f"{self.integration.endpoint_url.rstrip('/')}/api/v1/query",
            params={"query": query, "from": int(start.timestamp()), "to": int(end.timestamp())},
            headers=self._headers(),
            timeout=15,
        )
        response.raise_for_status()
        series = ((response.json().get("series") or []))
        rows: List[NormalizedMetricResult] = []
        for item in series:
            labels = {str(key): str(value) for key, value in (item.get("scope") or item.get("tag_set") or {}).items()} if isinstance(item.get("scope") or item.get("tag_set"), dict) else {}
            points = item.get("pointlist") or []
            for point in points:
                if not point or len(point) < 2 or point[1] is None:
                    continue
                rows.append(
                    NormalizedMetricResult(
                        metric_name=str(item.get("metric") or query),
                        value=float(point[1]),
                        timestamp=parse_timestamp(float(point[0]) / 1000),
                        labels=labels,
                    )
                )
        return rows

    def fetch_logs(self, query: str, time_range: tuple, limit: int = 100) -> List[NormalizedLogResult]:
        if not self.integration.endpoint_url:
            return []
        start, end = time_range if isinstance(time_range, tuple) and len(time_range) == 2 else (None, None)
        now = datetime.datetime.now(datetime.timezone.utc)
        body = {
            "filter": {
                "query": query or "*",
                "from": (start or (now - datetime.timedelta(minutes=30))).isoformat(),
                "to": (end or now).isoformat(),
            },
            "page": {"limit": max(1, min(int(limit or 100), 500))},
            "sort": "-timestamp",
        }
        response = requests.post(
            f"{self.integration.endpoint_url.rstrip('/')}/api/v2/logs/events/search",
            json=body,
            headers={**self._headers(), "Content-Type": "application/json"},
            timeout=20,
        )
        response.raise_for_status()
        rows: List[NormalizedLogResult] = []
        for item in response.json().get("data") or []:
            attrs = item.get("attributes") or {}
            rows.append(
                NormalizedLogResult(
                    timestamp=parse_timestamp(attrs.get("timestamp")),
                    message=str(attrs.get("message") or ""),
                    level=str((attrs.get("status") or attrs.get("level") or "info")),
                    source=str(attrs.get("service") or self.integration.name),
                    attributes=attrs,
                )
            )
        return rows


IntegrationRegistry.register("datadog", DatadogAdapter)
