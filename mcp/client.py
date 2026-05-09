"""
MCP client — bridges the server to the agent loop.

Responsibilities:
  1. Perform the MCP handshake (initialize).
  2. Fetch tool schemas and convert them to Groq / OpenAI function-calling format
     so the LLM can autonomously choose which tool to invoke and with what args.
  3. Invoke tools via the MCP protocol and return their output as a JSON string
     (the format the chat API expects in 'tool' role messages).

Transport: in-process.  All communication goes through server.handle() using
well-formed JSON-RPC 2.0 dicts — identical to what a real stdio/SSE transport
would send over the wire.
"""
from __future__ import annotations

import json
import threading
from typing import Any, Dict, List

from mcp.server import MCPServer


class MCPClient:
    def __init__(self, server: MCPServer) -> None:
        self._server = server
        self._initialized = False
        self._request_counter = 0
        self._counter_lock = threading.Lock()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _next_id(self) -> int:
        with self._counter_lock:
            self._request_counter += 1
            return self._request_counter

    def _send(self, method: str, params: dict | None = None) -> dict:
        """
        Send a JSON-RPC 2.0 request to the server.
        Returns the result dict on success; raises RuntimeError on protocol errors.
        """
        response = self._server.handle({
            "jsonrpc": "2.0",
            "id":      self._next_id(),
            "method":  method,
            "params":  params or {},
        })
        if "error" in response:
            err = response["error"]
            raise RuntimeError(f"MCP error {err['code']}: {err['message']}")
        return response.get("result", {})

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def initialize(self) -> dict:
        """Perform the MCP handshake and record that the client is ready."""
        result = self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "clientInfo":      {"name": "goodfoods-agent", "version": "2.0.0"},
            "capabilities":    {},
        })
        self._initialized = True
        return result

    # ── Tool discovery ────────────────────────────────────────────────────────

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return raw MCP tool descriptors: [{name, description, inputSchema}, …]."""
        return self._send("tools/list").get("tools", [])

    def get_llm_tools(self) -> List[dict]:
        """
        Convert MCP tool descriptors to the Groq / OpenAI function-calling format.

        MCP uses the key 'inputSchema'; OpenAI uses 'parameters'.
        They are structurally identical JSON Schema objects — only the key name differs.

        The LLM receives these schemas and autonomously decides:
          • whether to call a tool at all
          • which tool to call
          • what arguments to pass
        No intent routing logic lives in the agent code.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name":        t["name"],
                    "description": t["description"],
                    "parameters":  t["inputSchema"],   # MCP → OpenAI key rename
                },
            }
            for t in self.list_tools()
        ]

    # ── Tool invocation ───────────────────────────────────────────────────────

    def call_tool(self, name: str, arguments: dict) -> str:
        """
        Invoke a tool by name via the MCP tools/call protocol.

        Returns a JSON string — the format the chat API expects in 'tool' role
        message content.  Protocol-level errors (unknown tool, bad params) are
        caught here and returned as {"error": "..."} so the agent loop never
        crashes on a bad tool call.
        """
        try:
            result = self._send("tools/call", {"name": name, "arguments": arguments})
        except RuntimeError as exc:
            return json.dumps({"error": str(exc)})

        content = result.get("content", [])
        if content and isinstance(content, list):
            first = content[0]
            if first.get("type") == "text":
                return first["text"]
        return json.dumps({"error": "Empty content block in MCP tools/call response"})
