"""
Unified UI server
"""
from __future__ import annotations

import asyncio
from typing import Any


async def run_server(host: str = "127.0.0.1", port: int = 8765, bridge=None) -> Any:
    from .api import create_api, FASTAPI_AVAILABLE
    if not FASTAPI_AVAILABLE:
        return None
    try:
        import uvicorn
        app = create_api(bridge)
        config = uvicorn.Config(app, host=host, port=port, log_level="error")
        server = uvicorn.Server(config)
        asyncio.create_task(server.serve())
        return server
    except Exception:
        return None
