"""
In-process MCP server (JSON-RPC 2.0 transport).

Handles the three MCP lifecycle methods:
  • initialize   — capability negotiation
  • tools/list   — advertise registered tools to the client / LLM
  • tools/call   — execute a tool; errors surface as content, not protocol errors

Extend to a real stdio or SSE transport by replacing the `handle()` call
with a transport layer that serialises/deserialises over the wire — the
method-handler logic here stays unchanged.
"""
from __future__ import annotations

import json
from typing import Callable, Dict

from mcp.protocol import (
    ErrorCode, MCP_PROTOCOL_VERSION,
    Request, Response, ToolDefinition,
)


class MCPServer:
    def __init__(self, name: str, version: str) -> None:
        self._name = name
        self._version = version
        self._tools: Dict[str, ToolDefinition] = {}

    # ── Tool registration ─────────────────────────────────────────────────────

    def tool(
        self,
        name: str,
        description: str,
        input_schema: dict,
    ) -> Callable:
        """
        Decorator that registers a callable as an MCP tool.

        Schema and handler are stored together in a ToolDefinition so the LLM
        always sees an accurate description of exactly what the handler accepts.

        Usage:
            @server.tool(
                name="search_branches",
                description="Search active GoodFoods locations …",
                input_schema={"type": "object", "properties": {…}, "required": []},
            )
            def search_branches(**kwargs):
                …
        """
        def decorator(fn: Callable) -> Callable:
            self._tools[name] = ToolDefinition(
                name=name,
                description=description,
                input_schema=input_schema,
                handler=fn,
            )
            return fn   # return fn unchanged so decorated functions remain callable directly
        return decorator

    # ── JSON-RPC 2.0 dispatch ─────────────────────────────────────────────────

    def handle(self, request_dict: dict) -> dict:
        """
        Accept a raw JSON-RPC 2.0 request dict and return a response dict.
        Never raises — errors are always encoded in the response.
        """
        try:
            req = Request(
                jsonrpc=request_dict.get("jsonrpc", "2.0"),
                id=request_dict.get("id"),
                method=request_dict["method"],
                params=request_dict.get("params") or {},
            )
        except (KeyError, TypeError) as exc:
            return Response(
                id=request_dict.get("id"),
                error={"code": ErrorCode.INVALID_REQUEST, "message": str(exc)},
            ).to_dict()

        dispatch = {
            "initialize":  self._handle_initialize,
            "tools/list":  self._handle_tools_list,
            "tools/call":  self._handle_tools_call,
        }
        handler = dispatch.get(req.method)
        if handler is None:
            return Response(
                id=req.id,
                error={
                    "code":    ErrorCode.METHOD_NOT_FOUND,
                    "message": f"Method not found: {req.method}",
                },
            ).to_dict()

        return handler(req)

    # ── Method implementations ────────────────────────────────────────────────

    def _handle_initialize(self, req: Request) -> dict:
        return Response(
            id=req.id,
            result={
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities":    {"tools": {}},
                "serverInfo":      {"name": self._name, "version": self._version},
            },
        ).to_dict()

    def _handle_tools_list(self, req: Request) -> dict:
        return Response(
            id=req.id,
            result={"tools": [t.to_mcp_dict() for t in self._tools.values()]},
        ).to_dict()

    def _handle_tools_call(self, req: Request) -> dict:
        params    = req.params
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}

        if not tool_name:
            return Response(
                id=req.id,
                error={
                    "code":    ErrorCode.INVALID_PARAMS,
                    "message": "params.name (tool name) is required",
                },
            ).to_dict()

        tool_def = self._tools.get(tool_name)
        if tool_def is None:
            return Response(
                id=req.id,
                error={
                    "code":    ErrorCode.TOOL_NOT_FOUND,
                    "message": f"Tool not found: {tool_name}",
                },
            ).to_dict()

        # Strip any extra keys the LLM may have added (e.g. stray "reference_number")
        # to prevent unexpected-keyword-argument TypeErrors in the handler.
        known_props = tool_def.input_schema.get("properties", {})
        if known_props:
            arguments = {k: v for k, v in arguments.items() if k in known_props}

        try:
            result = tool_def.handler(**arguments)
            return Response(
                id=req.id,
                result={
                    "content": [{"type": "text", "text": json.dumps(result, default=str)}],
                    "isError": False,
                },
            ).to_dict()

        except TypeError as exc:
            # Argument-shape mismatch — tool-level error (content block, not JSON-RPC error)
            payload = {"error": f"Bad arguments for {tool_name}: {exc}"}
        except Exception as exc:
            payload = {"error": str(exc)}

        return Response(
            id=req.id,
            result={
                "content": [{"type": "text", "text": json.dumps(payload)}],
                "isError": True,
            },
        ).to_dict()
