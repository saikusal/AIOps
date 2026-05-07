import requests
from typing import List
from ..base import BaseMetricsAdapter, NormalizedMetricResult, BaseLogsAdapter, NormalizedLogResult
from ..registry import IntegrationRegistry


class DatadogAdapter(BaseMetricsAdapter, BaseLogsAdapter):
    def test_connection(self) -> bool:
        try:
            url = f"{self.integration.endpoint_url.rstrip('/')}/api/v1/validate"
            # In a real implementation we'd handle DD-API-KEY and DD-APPLICATION-KEY
            headers = {"DD-API-KEY": self.integration.credential.secret_ref} if hasattr(self.integration, 'credential') else {}
            response = requests.get(url, headers=headers, timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def fetch_metrics(self, query: str, time_range: tuple) -> List[NormalizedMetricResult]:
        return []

    def fetch_logs(self, query: str, time_range: tuple, limit: int = 100) -> List[NormalizedLogResult]:
        return []


IntegrationRegistry.register("datadog", DatadogAdapter)
