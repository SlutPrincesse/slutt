"""
FastAPI bridge for unified UI
"""
from __future__ import annotations

from typing import Any, Dict

try:
    from fastapi import FastAPI, WebSocket
    from fastapi.responses import HTMLResponse
    FASTAPI_AVAILABLE = True
except Exception:
    FASTAPI_AVAILABLE = False
    FastAPI = None


def create_api(bridge) -> Any:
    if not FASTAPI_AVAILABLE:
        return None
    app = FastAPI(title="AGENT_SYSTEM_V9 Unified API")

    @app.get("/api/status")
    async def status() -> Dict[str, Any]:
        return {"status": "ok", "codename": "NEURO-CRANIAL OVERLORD", "version": "9.0.0"}

    @app.get("/api/events")
    async def events() -> Dict[str, Any]:
        evs = list(bridge.state.events) if hasattr(bridge, "state") else []
        return {"events": evs}

    @app.get("/api/tools")
    async def tools() -> Dict[str, Any]:
        from agent_system_v9.tools.tool_registry import DynamicToolRegistry
        reg = DynamicToolRegistry.get_instance()
        return {"tools": [e.to_dict() for e in reg._tools.values()]}

    @app.post("/api/chat")
    async def chat(payload: Dict[str, Any]) -> Dict[str, Any]:
        msg = payload.get("message", "")
        from agent_system_v9.unified_orchestrator import UnifiedOrchestrator
        orch = UnifiedOrchestrator()
        result = await orch.handle(msg)
        events = list(bridge.state.events) if hasattr(bridge, "state") else []
        return {"response": result, "events": events}

    @app.get("/")
    async def root():
        from .web import HTML
        return HTMLResponse(HTML)

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                data = await ws.receive_text()
                from agent_system_v9.unified_orchestrator import UnifiedOrchestrator
                orch = UnifiedOrchestrator()
                result = await orch.handle(data)
                await ws.send_json({"type": "result", "data": result})
                if hasattr(bridge, "state"):
                    await ws.send_json({"type": "events", "data": list(bridge.state.events)[-20:]})
        except Exception as e:
            try:
                await ws.send_json({"type": "error", "data": str(e)})
            except Exception:
                pass

    return app
