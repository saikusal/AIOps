import datetime
import requests
from typing import List
from ..base import BaseMetricsAdapter, NormalizedMetricResult
from ..registry import IntegrationRegistry


class PrometheusAdapter(BaseMetricsAdapter):
    def test_connection(self) -> bool:
        try:
            url = f"{self.integration.endpoint_url.rstrip('/')}/-/healthy"
            response = requests.get(url, timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def fetch_metrics(self, query: str, time_range: tuple) -> List[NormalizedMetricResult]:
        if not query or not self.integration.endpoint_url:
            return []
        start, end = time_range if isinstance(time_range, tuple) and len(time_range) == 2 else (None, None)
        if start and end:
            params = {
                "query": query,
                "start": start.timestamp(),
                "end": end.timestamp(),
                "step": max(15, int((end - start).total_seconds() // 30 or 15)),
            }
            url = f"{self.integration.endpoint_url.rstrip('/')}/api/v1/query_range"
        else:
            params = {"query": query}
            url = f"{self.integration.endpoint_url.rstrip('/')}/api/v1/query"
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json().get("data", {})
        results: List[NormalizedMetricResult] = []
        for row in payload.get("result") or []:
            metric_labels = {str(key): str(value) for key, value in (row.get("metric") or {}).items()}
            metric_name = metric_labels.get("__name__", query)
            samples = row.get("values") or ([row.get("value")] if row.get("value") else [])
            for sample in samples:
                if not sample or len(sample) < 2:
                    continue
                try:
                    timestamp = datetime.datetime.fromtimestamp(float(sample[0]), tz=datetime.timezone.utc)
                    value = float(sample[1])
                except (TypeError, ValueError, OSError):
                    continue
                results.append(
                    NormalizedMetricResult(
                        metric_name=metric_name,
                        value=value,
                        timestamp=timestamp,
                        labels=metric_labels,
                    )
                )
        return results


IntegrationRegistry.register("prometheus", PrometheusAdapter)
