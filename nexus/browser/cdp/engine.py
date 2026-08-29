from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable
from typing import Any

import websockets

from nexus.browser.errors.types import BrowserError, ErrorType, BrowserException, RecoveryAction

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0
INSPECTOR_ENABLE_TIMEOUT = 5.0


class CDPEngine:
    def __init__(self, default_timeout: float = DEFAULT_TIMEOUT) -> None:
        self._ws: websockets.ClientConnection | None = None
        self._id = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._listeners: dict[str, list[Callable[[dict[str, Any]], None]]] = {}
        self._receive_task: asyncio.Task[None] | None = None
        self._closed_reason: BrowserError | None = None
        self.default_timeout = default_timeout

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    @property
    def closed(self) -> bool:
        return self._closed_reason is not None

    @property
    def closed_reason(self) -> BrowserError | None:
        return self._closed_reason

    async def connect(self, url: str) -> None:
        self._ws = await websockets.connect(url, max_size=50 * 1024 * 1024)
        self._receive_task = asyncio.create_task(self._receive_loop())
        self.on("Inspector.targetCrashed", self._handle_target_crashed)
        try:
            await self.send("Inspector.enable", timeout=INSPECTOR_ENABLE_TIMEOUT)
        except Exception:
            logger.debug("Inspector.enable failed; crash events will not surface", exc_info=True)

    async def disconnect(self) -> None:
        if self._receive_task:
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receive_task
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def send(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        session_id: str | None = None,
        timeout: float | None = None,
    ) -> Any:
        if self._ws is None:
            raise RuntimeError("CDPEngine is not connected. Call connect() first.")
        if self._closed_reason is not None:
            raise BrowserException(self._closed_reason)
        msg_id = self._next_id()
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = fut
        message: dict[str, Any] = {"id": msg_id, "method": method, "params": params or {}}
        if session_id is not None:
            message["sessionId"] = session_id
        payload = json.dumps(message)
        await self._ws.send(payload)
        effective_timeout = timeout if timeout is not None else self.default_timeout
        try:
            return await asyncio.wait_for(fut, timeout=effective_timeout)
        except TimeoutError as e:
            self._pending.pop(msg_id, None)
            raise TimeoutError(f"CDP command {method} timed out") from e

    def on(self, event: str, callback: Callable[[dict[str, Any]], None]) -> None:
        self._listeners.setdefault(event, []).append(callback)

    def off(self, event: str, callback: Callable[[dict[str, Any]], None]) -> None:
        listeners = self._listeners.get(event, [])
        if callback in listeners:
            listeners.remove(callback)

    def _handle_target_crashed(self, params: dict[str, Any]) -> None:
        reason = params.get("reason", "unknown")
        error_code = params.get("errorCode")
        detail = f"reason={reason}"
        if error_code is not None:
            detail += f", errorCode={error_code}"
        self._fail_pending(BrowserError(
            type=ErrorType.BROWSER_CRASHED,
            message=f"Renderer process crashed ({detail})",
            confidence=1.0,
            recovery=[RecoveryAction.RETRY],
        ))

    def _as_crash_error(self, exc: BaseException) -> BrowserError:
        return BrowserError(
            type=ErrorType.BROWSER_CRASHED,
            message=f"CDP connection lost: {exc}",
            confidence=0.9,
            recovery=[RecoveryAction.RETRY],
        )

    async def _receive_loop(self) -> None:
        try:
            await self._receive_forever()
        except asyncio.CancelledError:
            raise
        except BaseException as e:
            logger.debug("CDP receive loop ended: %s", e)
            self._fail_pending(self._as_crash_error(e))
        else:
            self._fail_pending(self._as_crash_error(ConnectionError("CDP receive loop ended")))

    def _fail_pending(self, error: BrowserError) -> None:
        self._closed_reason = error
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(BrowserException(error))
        self._pending.clear()

    async def _receive_forever(self) -> None:
        assert self._ws is not None
        async for raw in self._ws:
            msg = json.loads(raw)
            if "id" in msg:
                fut = self._pending.pop(msg["id"], None)
                if fut and not fut.done():
                    if "error" in msg:
                        fut.set_exception(RuntimeError(msg["error"]["message"]))
                    else:
                        fut.set_result(msg.get("result", {}))
            elif "method" in msg:
                for cb in self._listeners.get(msg["method"], []):
                    try:
                        cb(msg.get("params", {}))
                    except Exception:
                        logger.exception("CDP listener error for %s", msg["method"])
