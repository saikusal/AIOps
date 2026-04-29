from typing import Dict, Iterable

from .mcp_types import MCPToolDefinition


class MCPRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, MCPToolDefinition] = {}

    def register(self, definition: MCPToolDefinition) -> None:
        self._tools[definition.tool_name] = definition

    def get(self, tool_name: str) -> MCPToolDefinition:
        return self._tools[tool_name]

    def has(self, tool_name: str) -> bool:
        return tool_name in self._tools

    def list_tools(self) -> Iterable[MCPToolDefinition]:
        return self._tools.values()
