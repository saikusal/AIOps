import time
import os
from typing import Any

import requests

from .mcp_registry import MCPRegistry
from .mcp_types import MCPToolCall, MCPToolResult


class MCPClient:
    def __init__(self, registry: MCPRegistry) -> None:
        self.registry = registry
        self.transport = (os.getenv("MCP_TRANSPORT", "inprocess") or "inprocess").strip().lower()
        self.base_url = (os.getenv("MCP_BASE_URL", "http://127.0.0.1:8000") or "").rstrip("/")
        self.internal_token = (os.getenv("MCP_INTERNAL_TOKEN", "") or "").strip()
        self._session = requests.Session()

    def invoke(self, call: MCPToolCall) -> MCPToolResult:
        definition = self.registry.get(call.tool_name)
        started = time.monotonic()
        try:
            if self.transport == "http":
                if not definition.endpoint_path:
                    raise RuntimeError(f"{call.tool_name} has no HTTP endpoint configured")
                headers = {}
                if self.internal_token:
                    headers["X-MCP-Token"] = self.internal_token
                response = self._session.get(
                    f"{self.base_url}{definition.endpoint_path}",
                    params=call.params,
                    headers=headers,
                    timeout=15,
                )
                response.raise_for_status()
                content = response.json()
            else:
                content = definition.handler(call.params)
            latency_ms = int((time.monotonic() - started) * 1000)
            return MCPToolResult(
                ok=True,
                server_name=definition.server_name,
                tool_name=definition.tool_name,
                params=call.params,
                content=content,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            return MCPToolResult(
                ok=False,
                server_name=definition.server_name,
                tool_name=definition.tool_name,
                params=call.params,
                content={},
                latency_ms=latency_ms,
                error=str(exc),
            )
