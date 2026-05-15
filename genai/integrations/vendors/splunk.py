import datetime
import requests
from typing import List
from ..base import BaseLogsAdapter, NormalizedLogResult
from ..registry import IntegrationRegistry
from .common import credential_secret, request_json_lines


class SplunkAdapter(BaseLogsAdapter):
    def test_connection(self) -> bool:
        try:
            url = f"{self.integration.endpoint_url.rstrip('/')}/services/server/info?output_mode=json"
            headers = {"Authorization": f"Bearer {self.integration.credential.secret_ref}"} if hasattr(self.integration, 'credential') else {}
            response = requests.get(url, headers=headers, timeout=5, verify=False)
            return response.status_code == 200
        except Exception:
            return False

    def fetch_logs(self, query: str, time_range: tuple, limit: int = 100) -> List[NormalizedLogResult]:
        if not self.integration.endpoint_url:
            return []
        start, end = time_range if isinstance(time_range, tuple) and len(time_range) == 2 else (None, None)
        search = query if str(query or "").strip().lower().startswith("search ") else f"search {query or '*'}"
        data = {
            "search": search,
            "output_mode": "json",
            "exec_mode": "oneshot",
            "count": max(1, min(int(limit or 100), 500)),
        }
        if start:
            data["earliest_time"] = start.isoformat()
        if end:
            data["latest_time"] = end.isoformat()
        response = requests.post(
            f"{self.integration.endpoint_url.rstrip('/')}/services/search/jobs/export",
            data=data,
            headers={"Authorization": f"Bearer {credential_secret(self.integration)}"} if credential_secret(self.integration) else {},
            timeout=20,
            verify=False,
            stream=True,
        )
        response.raise_for_status()
        rows: List[NormalizedLogResult] = []
        for item in request_json_lines(response):
            result = item.get("result") or {}
            raw = str(result.get("_raw") or result.get("message") or "")
            timestamp_raw = result.get("_time")
            try:
                timestamp = datetime.datetime.fromisoformat(str(timestamp_raw).replace("Z", "+00:00")) if timestamp_raw else datetime.datetime.now(datetime.timezone.utc)
            except ValueError:
                timestamp = datetime.datetime.now(datetime.timezone.utc)
            rows.append(
                NormalizedLogResult(
                    timestamp=timestamp,
                    message=raw,
                    level=str(result.get("level") or result.get("severity") or "info"),
                    source=str(result.get("source") or result.get("host") or self.integration.name),
                    attributes=result,
                )
            )
        return rows


IntegrationRegistry.register("splunk", SplunkAdapter)
