"""
MCP (Model Context Protocol) wire types — JSON-RPC 2.0 layer.

Protocol spec: https://spec.modelcontextprotocol.io/specification/2024-11-05/
Transport: in-process (no socket/stdio needed for local use; extend later if required).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

MCP_PROTOCOL_VERSION = "2024-11-05"


# ── JSON-RPC 2.0 primitives ───────────────────────────────────────────────────

@dataclass
class Request:
    method: str
    id: Any                              # int | str | None per JSON-RPC 2.0 spec
    params: Dict[str, Any] = field(default_factory=dict)
    jsonrpc: str = "2.0"


@dataclass
class Response:
    id: Any
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    jsonrpc: str = "2.0"

    def to_dict(self) -> dict:
        """Serialize to a JSON-RPC 2.0 response dict (result XOR error)."""
        d: dict = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error is not None:
            d["error"] = self.error
        else:
            d["result"] = self.result
        return d


# ── MCP tool descriptor ───────────────────────────────────────────────────────

@dataclass
class ToolDefinition:
    """
    Single source of truth for one tool: its MCP schema and its Python handler
    live together so they can never drift apart.
    """
    name: str
    description: str
    input_schema: Dict[str, Any]   # JSON Schema (type: "object", properties, required)
    handler: Callable              # Python callable; field excluded from repr

    def to_mcp_dict(self) -> dict:
        """Wire format emitted in tools/list responses."""
        return {
            "name":        self.name,
            "description": self.description,
            "inputSchema": self.input_schema,   # MCP key name
        }

    def to_openai_dict(self) -> dict:
        """Format expected by Groq / OpenAI function-calling API."""
        return {
            "type": "function",
            "function": {
                "name":        self.name,
                "description": self.description,
                "parameters":  self.input_schema,  # OpenAI key name — same schema object
            },
        }


# ── Standard error codes ──────────────────────────────────────────────────────

class ErrorCode:
    # JSON-RPC 2.0 reserved codes
    PARSE_ERROR      = -32700
    INVALID_REQUEST  = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS   = -32602
    INTERNAL_ERROR   = -32603
    # MCP application-level codes
    TOOL_NOT_FOUND   = -32001
    TOOL_EXEC_ERROR  = -32002
