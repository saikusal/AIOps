import datetime
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class NormalizedMetricResult:
    metric_name: str
    value: float
    timestamp: datetime.datetime
    labels: Dict[str, str]


@dataclass
class NormalizedLogResult:
    timestamp: datetime.datetime
    message: str
    level: str
    source: str
    attributes: Dict[str, Any]


@dataclass
class NormalizedTraceResult:
    trace_id: str
    span_id: str
    service_name: str
    operation_name: str
    duration_ms: float
    start_time: datetime.datetime
    tags: Dict[str, Any]


@dataclass
class NormalizedAlertResult:
    alert_name: str
    status: str
    severity: str
    description: str
    starts_at: datetime.datetime
    labels: Dict[str, str]


@dataclass
class NormalizedTopologyResult:
    node_id: str
    node_type: str
    name: str
    status: str
    attributes: Dict[str, Any]
    relations: List[Dict[str, str]]


class BaseAdapter:
    """Base class for all integrations adapters."""
    def __init__(self, integration_model):
        self.integration = integration_model

    def test_connection(self) -> bool:
        """Test the connection to the external integration."""
        raise NotImplementedError("test_connection must be implemented by subclasses.")


class BaseMetricsAdapter(BaseAdapter):
    """Base class for metrics backend adapters."""
    def fetch_metrics(self, query: str, time_range: tuple) -> List[NormalizedMetricResult]:
        raise NotImplementedError("fetch_metrics must be implemented by subclasses.")


class BaseLogsAdapter(BaseAdapter):
    """Base class for logs backend adapters."""
    def fetch_logs(self, query: str, time_range: tuple, limit: int = 100) -> List[NormalizedLogResult]:
        raise NotImplementedError("fetch_logs must be implemented by subclasses.")


class BaseTracesAdapter(BaseAdapter):
    """Base class for trace backend adapters."""
    def fetch_traces(self, service_name: str, time_range: tuple, tags: Optional[Dict[str, str]] = None) -> List[NormalizedTraceResult]:
        raise NotImplementedError("fetch_traces must be implemented by subclasses.")


class BaseAlertsAdapter(BaseAdapter):
    """Base class for alert backend adapters."""
    def fetch_alert_state(self) -> List[NormalizedAlertResult]:
        raise NotImplementedError("fetch_alert_state must be implemented by subclasses.")

