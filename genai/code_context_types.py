from typing import Any, Dict, List, TypedDict


class CodeContextResult(TypedDict, total=False):
    ok: bool
    repository: str
    service_name: str
    application_name: str
    team_name: str
    ownership_confidence: float
    handler: str
    symbol: str
    module_path: str
    line_start: int
    line_end: int
    confidence: float
    matched_by: str
    supporting_context: List[str]
    recent_changes: List[Dict[str, Any]]
    recent_deployments: List[Dict[str, Any]]
    related_symbols: List[Dict[str, Any]]
    queue_consumers: List[Dict[str, Any]]
    blast_radius: Dict[str, Any]
    message: str

