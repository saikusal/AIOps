import requests
from typing import List
from ..base import BaseLogsAdapter, NormalizedLogResult
from ..registry import IntegrationRegistry
import datetime


class OpenSearchAdapter(BaseLogsAdapter):
    def test_connection(self) -> bool:
        try:
            url = f"{self.integration.endpoint_url.rstrip('/')}/_cluster/health"
            response = requests.get(url, timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def fetch_logs(self, query: str, time_range: tuple, limit: int = 100) -> List[NormalizedLogResult]:
        if not self.integration.endpoint_url:
            return []
        body = {
            "size": max(1, min(int(limit or 100), 500)),
            "sort": [{"@timestamp": {"order": "desc"}}],
            "query": {
                "bool": {
                    "must": [{"match": {"message": query}}] if query else [{"match_all": {}}],
                }
            },
        }
        response = requests.post(
            f"{self.integration.endpoint_url.rstrip('/')}/_search",
            json=body,
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        rows: List[NormalizedLogResult] = []
        for hit in ((payload.get("hits") or {}).get("hits") or []):
            source = hit.get("_source") or {}
            timestamp_raw = source.get("@timestamp")
            try:
                timestamp = datetime.datetime.fromisoformat(str(timestamp_raw).replace("Z", "+00:00")) if timestamp_raw else datetime.datetime.now(datetime.timezone.utc)
            except ValueError:
                timestamp = datetime.datetime.now(datetime.timezone.utc)
            rows.append(
                NormalizedLogResult(
                    timestamp=timestamp,
                    message=str(source.get("message") or ""),
                    level=str(source.get("log.level") or source.get("level") or "info"),
                    source=str(source.get("service.name") or source.get("service_name") or source.get("target_name") or self.integration.name),
                    attributes=source,
                )
            )
        return rows


IntegrationRegistry.register("opensearch", OpenSearchAdapter)
