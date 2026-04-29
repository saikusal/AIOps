from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


ToolHandler = Callable[[Dict[str, Any]], Any]


@dataclass(frozen=True)
class MCPToolDefinition:
    server_name: str
    tool_name: str
    description: str
    handler: ToolHandler
    endpoint_path: Optional[str] = None


@dataclass(frozen=True)
class MCPToolCall:
    server_name: str
    tool_name: str
    params: Dict[str, Any]


@dataclass(frozen=True)
class MCPToolResult:
    ok: bool
    server_name: str
    tool_name: str
    params: Dict[str, Any]
    content: Any
    latency_ms: int
    error: str = ""
