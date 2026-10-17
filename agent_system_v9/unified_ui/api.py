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

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                await ws.receive_text()
        except Exception:
            pass

    return app
