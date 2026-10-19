"""
Minimal MCP-style stdio server exposing DynamicToolRegistry tools.

Speaks newline-delimited JSON-RPC 2.0 over stdin/stdout. Supports:
  - initialize
  - tools/list
  - tools/call
"""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from .tool_registry import DynamicToolRegistry


class MCPServer:
    def __init__(self, registry: DynamicToolRegistry | None = None):
        self.registry = registry or DynamicToolRegistry.get_instance()

    async def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        method = request.get("method")
        rid = request.get("id")
        params = request.get("params") or {}

        if method == "initialize":
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "agent-system-v9", "version": "9.0.0"},
            }}

        if method == "tools/list":
            tools = []
            for entry in self.registry._tools.values():
                tools.append(entry.to_openai_function().get("function", {}))
            return {"jsonrpc": "2.0", "id": rid, "result": {"tools": tools}}

        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments", {}) or {}
            try:
                result = await self.registry.execute(name, args)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": json.dumps(result)}]}}
            except Exception as e:
                return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": str(e)}}

        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method not found: {method}"}}

    async def serve(self) -> None:
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)
        writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout
        )
        writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, asyncio.get_event_loop())

        while True:
            line = await reader.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                continue
            resp = await self.handle(req)
            writer.write((json.dumps(resp) + "\n").encode())
            await writer.drain()


def main() -> None:
    server = MCPServer()
    asyncio.run(server.serve())


if __name__ == "__main__":
    main()
