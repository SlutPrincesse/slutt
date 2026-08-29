from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import math
import random
import re
import time
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nexus.browser.cdp.engine import CDPEngine
from nexus.browser.cdp.shadow import (
    CLICK_ELEMENT_JS,
    CLICK_REVEAL_JS,
    CLOSED_SHADOW_PATCH_JS,
    DISCOVER_ELEMENTS_JS,
    PAGE_TEXT_JS,
    PROBE_CLICKABLE_JS,
    READ_CONTENT_JS,
    SCROLL_BOTTOM_JS,
    TYPE_ELEMENT_JS,
    _RESOLVE_JS,
)
from nexus.browser.challenge import (
    POINT_PROBE_JS,
    SLIDER_PROBE_JS,
    TOKEN_PROBE_JS,
    ChallengeResult,
    ChallengeStage,
    detect_challenge_from_html,
    frame_urls,
    is_solvable,
    needs_vision,
)
from nexus.browser.compression.delta import SnapshotDelta, build_delta, format_delta, is_worth_sending
from nexus.browser.compression.refs import RefRegistry
from nexus.browser.compression.summarizer import Element, PageSnapshot, Summarizer
from nexus.browser.errors.classifier import RAW_TEXT_PROBE_FLOOR, ErrorClassifier
from nexus.browser.errors.types import BrowserError, ErrorType, BrowserException, RecoveryAction
from nexus.browser.input import RESOLVE_POINT_JS, bezier_path, move_delay, press_dwell
from nexus.browser.reader import Block, Document
from nexus.browser.resources import BLOCKED_RESOURCE_PATTERNS
from nexus.browser.security.injection import InjectionDetector
from nexus.browser.security.policy import NavigationPolicy, enforce as enforce_navigation
from nexus.browser.security.sanitizer import RawElement
from nexus.browser.trace import Trace, TraceEntry

logger = logging.getLogger(__name__)

_ELIDED = "[elided: detected instruction-like text]"

_CLICK_LISTENER_TYPES = frozenset({"click"})

_PROBE_TIMEOUT_S = 2.0
_PROBE_OBJECT_GROUP = "grip-probe"

_INTERCEPTED_RESOURCE_TYPES = ("Document", "XHR", "Fetch")

_VALID_HANDLE_RE = re.compile(r"^h\d+$")


def _is_trusted_handle(handle: str) -> bool:
    return bool(_VALID_HANDLE_RE.match(handle))


_SETTLE_TIMEOUT_S = 0.5
_SETTLE_POLL_S = 0.05
_SETTLE_QUIET_POLLS = 2

_SETTLE_SIGNATURE_JS = (
    "JSON.stringify({href: location.href, rs: document.readyState,"
    " n: document.getElementsByTagName('*').length})"
)

_NAMED_KEYS: dict[str, tuple[str, int]] = {
    "Enter": ("Enter", 13),
    "Tab": ("Tab", 9),
    "Escape": ("Escape", 27),
    "Backspace": ("Backspace", 8),
    "Delete": ("Delete", 46),
    "ArrowUp": ("ArrowUp", 38),
    "ArrowDown": ("ArrowDown", 40),
    "ArrowLeft": ("ArrowLeft", 37),
    "ArrowRight": ("ArrowRight", 39),
    "Home": ("Home", 36),
    "End": ("End", 35),
    "PageUp": ("PageUp", 33),
    "PageDown": ("PageDown", 34),
    " ": ("Space", 32),
    "Space": ("Space", 32),
}

_MODIFIER_BITS = {
    "alt": 1, "option": 1,
    "ctrl": 2, "control": 2,
    "meta": 4, "cmd": 4, "command": 4,
    "shift": 8,
}


def _modifiers_bitmask(modifiers: list[str] | None) -> int:
    if not modifiers:
        return 0
    bits = 0
    for m in modifiers:
        bits |= _MODIFIER_BITS.get(m.lower(), 0)
    return bits


def _has_click_listener(listeners: list[dict[str, Any]]) -> bool:
    return any(
        (listener or {}).get("type") in _CLICK_LISTENER_TYPES
        for listener in listeners
    )

_FIND_FILE_INPUTS_JS = """
(function () {
  function stamp(el) {
    let h = el.getAttribute('data-grip-h');
    if (!h) {
      window.__gripHandleSeq = (window.__gripHandleSeq || 0) + 1;
      h = 'h' + window.__gripHandleSeq;
      el.setAttribute('data-grip-h', h);
    }
    return h;
  }
  function labelFor(el) {
    if (el.id) {
      const lbl = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
      if (lbl) return (lbl.innerText || '').trim();
    }
    const wrap = el.closest('label');
    return wrap ? (wrap.innerText || '').trim() : '';
  }
  const out = [];
  document.querySelectorAll('input[type="file"]').forEach(function (el) {
    out.push({
      handle: stamp(el),
      label: labelFor(el),
      aria: el.getAttribute('aria-label') || '',
      name: el.getAttribute('name') || '',
      id: el.id || '',
    });
  });
  return JSON.stringify(out);
})();
"""

_RESOLVE_FILE_INPUT_JS = """
function (handle) {
  return document.querySelector('[data-grip-h="' + CSS.escape(handle) + '"]');
}
"""

_SELECT_OPTION_JS = """
function(handle, expectedTag, optionValue) {
""" + _RESOLVE_JS + """
  const r = gripResolve(handle, expectedTag, '');
  if (!r.el) return { ok: false, reason: r.reason };
  const el = r.el;
  if (el.tagName.toLowerCase() !== 'select') {
    return { ok: false, reason: 'not_a_select', tag: el.tagName.toLowerCase() };
  }
  const options = Array.prototype.filter.call(el.options, function (o) { return !o.disabled; });
  const wanted = optionValue.trim().toLowerCase();
  let match = null;
  for (const opt of options) {
    if ((opt.text || '').trim().toLowerCase() === wanted) { match = opt; break; }
  }
  if (!match) {
    for (const opt of options) {
      if ((opt.value || '').toLowerCase() === wanted) { match = opt; break; }
    }
  }
  if (!match) {
    const hits = options.filter(function (opt) {
      return (opt.text || '').trim().toLowerCase().includes(wanted);
    });
    if (hits.length === 1) match = hits[0];
  }
  if (!match) {
    return {
      ok: false, reason: 'no_such_option',
      options: options.map(function (o) { return (o.text || '').trim(); }),
    };
  }
  el.selectedIndex = match.index;
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return { ok: true, reason: '' };
}
"""


def _same_document(current: str, requested: str) -> bool:
    if not current or not requested:
        return False
    return current.rstrip("/") == requested.rstrip("/")


def render_payload(
    snap: PageSnapshot | None,
    delta: SnapshotDelta | None,
    last_sent_version: int,
    summarizer: Summarizer,
) -> tuple[str, int]:
    if snap is None:
        raise RuntimeError(
            "payload() called before any snapshot; the page has no state to send"
        )
    rendered_snapshot = summarizer.format(snap)
    if delta is not None and delta.previous_version == last_sent_version:
        rendered_delta = format_delta(delta)
        if is_worth_sending(rendered_delta, rendered_snapshot):
            return rendered_delta, delta.version
    return rendered_snapshot, snap.version


@dataclass
class Screenshot:
    data: bytes
    tokens_estimated: int

    @property
    def b64(self) -> str:
        return base64.b64encode(self.data).decode()

    def save(self, path: str) -> None:
        Path(path).write_bytes(self.data)


_SCROLL_BY_JS = """
function (direction, pages) {
  var vw = window.innerWidth, vh = window.innerHeight;
  var dx = 0, dy = 0;
  if (direction === 'down') dy = vh * pages;
  else if (direction === 'up') dy = -vh * pages;
  else if (direction === 'right') dx = vw * pages;
  else if (direction === 'left') dx = -vw * pages;
  window.scrollBy(dx, dy);
  var doc = document.documentElement;
  return {
    ok: true,
    x: window.scrollX, y: window.scrollY,
    pageHeight: doc.scrollHeight, pageWidth: doc.scrollWidth,
    viewportHeight: vh, viewportWidth: vw
  };
}
"""

_SCROLL_TO_REF_JS = """
function(handle, expectedTag, expectedText) {
""" + _RESOLVE_JS + """
  const r = gripResolve(handle, expectedTag, expectedText);
  if (!r.el) return { ok: false, reason: r.reason };
  r.el.scrollIntoView({ block: 'center', inline: 'nearest' });
  var doc = document.documentElement;
  return {
    ok: true,
    x: window.scrollX, y: window.scrollY,
    pageHeight: doc.scrollHeight, pageWidth: doc.scrollWidth,
    viewportHeight: window.innerHeight, viewportWidth: window.innerWidth
  };
}
"""

_SCROLL_METRICS_JS = """
(function () {
  var doc = document.documentElement;
  return JSON.stringify({
    x: window.scrollX, y: window.scrollY,
    pageHeight: doc.scrollHeight, pageWidth: doc.scrollWidth,
    viewportHeight: window.innerHeight, viewportWidth: window.innerWidth
  });
})();
"""

_WAIT_TEXT_JS = """
function (needle) {
  var body = document.body;
  if (!body) return false;
  return (body.innerText || '').toLowerCase().indexOf(needle.toLowerCase()) !== -1;
}
"""

_WAIT_ELEMENT_JS = """
function (needle) {
  var want = needle.toLowerCase();
  var nodes = document.querySelectorAll(
    'a,button,input,select,textarea,[role],[onclick],[tabindex]'
  );
  for (var i = 0; i < nodes.length; i++) {
    var el = nodes[i];
    var text = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim();
    if (text.toLowerCase().indexOf(want) !== -1) return true;
  }
  return false;
}
"""

_WAIT_SELECTOR_JS = """
function (selector) {
  try { return !!document.querySelector(selector); }
  catch (e) { return false; }
}
"""

_CONSENT_ACCEPT_PHRASES = (
    "accept", "accept all", "accept all cookies", "accept cookies",
    "i agree", "agree", "allow all", "allow all cookies", "got it", "ok",
)

_CONSENT_DISMISS_JS = """
function (phrases) {
  var nodes = document.querySelectorAll('button, a[role="button"], [role="button"]');
  for (var i = 0; i < nodes.length; i++) {
    var el = nodes[i];
    var rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) continue;
    var text = (el.innerText || el.textContent || '').trim().toLowerCase();
    if (phrases.indexOf(text) !== -1) {
      el.click();
      return { clicked: true, text: text };
    }
  }
  return { clicked: false, text: '' };
}
"""

_DEFAULT_DIALOG_POLICY: dict[str, bool] = {
    "alert": True, "confirm": True, "beforeunload": True, "prompt": False,
}


@dataclass
class PopupInfo:
    target_id: str
    url: str
    session_id: str


@dataclass
class ScrollPosition:
    x: int
    y: int
    page_height: int
    page_width: int
    viewport_height: int
    viewport_width: int


class Page:
    def __init__(
        self,
        engine: CDPEngine,
        trace: Trace,
        target_id: str = "",
        safe: bool = False,
        closer: Callable[[str], Awaitable[None]] | None = None,
        block_resources: bool = False,
        policy: NavigationPolicy | None = None,
        settle_timeout: float = _SETTLE_TIMEOUT_S,
        dialog_policy: dict[str, bool] | None = None,
        dismiss_consent_banners: bool = True,
        stealth_ua: str | None = None,
    ) -> None:
        self._engine = engine
        self._trace = trace
        self._target_id = target_id
        self._safe = safe
        self._closer = closer
        self._stealth_ua = stealth_ua
        self._policy = policy if policy is not None else NavigationPolicy()
        self._closed = False
        self._version = 0
        self._current_snapshot: PageSnapshot | None = None
        self._summarizer = Summarizer()
        self._previous_snapshot: PageSnapshot | None = None
        self.delta: SnapshotDelta | None = None
        self._injector = InjectionDetector()
        self._classifier = ErrorClassifier()
        self._initialized = False
        self._refs = RefRegistry()
        self._current_url: str = ""
        self._status_code: int = 0
        self._content_probed_url: str = ""
        self._block_resources = block_resources
        self._settle_timeout = settle_timeout
        self._pointer_x = 0
        self._pointer_y = 0
        self._fetch_enabled = False
        self._doc_refusal_hook: Callable[[str], None] | None = None
        self._popup_block_armed = False
        self._popups_blocked = 0
        self._bg_tasks: set[asyncio.Task[None]] = set()
        self._download_dir: Path | None = None
        self._download_events_armed = False
        self._download_queue: asyncio.Queue[Path | None] | None = None
        self._page_domain_enabled = False
        self._closed_shadow_patch_armed = False
        self._dialog_handling_armed = False
        self._dialog_policy: dict[str, bool] = {
            **_DEFAULT_DIALOG_POLICY, **(dialog_policy or {}),
        }
        self._pending_dialogs: list[dict[str, Any]] = []
        self._nav_invalidation_armed = False
        self._dismiss_consent_banners = dismiss_consent_banners
        self._consent_dismissed_this_nav = False
        self._popup_queue: asyncio.Queue[PopupInfo] = asyncio.Queue()

    @property
    def popups_blocked(self) -> int:
        return self._popups_blocked

    def _assert_not_safe(self, action: str) -> None:
        if self._safe:
            raise BrowserException(BrowserError(
                type=ErrorType.SAFE_MODE_VIOLATION,
                message=f"{action}() is not allowed in safe mode",
                confidence=1.0,
                recovery=[],
            ))

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await self._engine.send("Runtime.enable")
            self._initialized = True
        await self._ensure_fetch_interception()
        await self._ensure_dialog_handling()
        await self._ensure_nav_invalidation()
        await self._ensure_closed_shadow_patch()

    async def _ensure_closed_shadow_patch(self) -> None:
        if self._closed_shadow_patch_armed:
            return
        self._closed_shadow_patch_armed = True
        await self._engine.send(
            "Page.addScriptToEvaluateOnNewDocument", {"source": CLOSED_SHADOW_PATCH_JS}
        )

    async def _ensure_fetch_interception(self) -> None:
        if self._fetch_enabled or self._policy.allow_private:
            return
        self._fetch_enabled = True
        self._engine.on("Fetch.requestPaused", self._on_fetch_paused)
        await self._engine.send(
            "Fetch.enable",
            {"patterns": [
                {"urlPattern": "*", "resourceType": rt, "requestStage": "Request"}
                for rt in _INTERCEPTED_RESOURCE_TYPES
            ]},
        )

    def _spawn_bg(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.ensure_future(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    def _on_fetch_paused(self, params: dict[str, Any]) -> None:
        request_id = params.get("requestId", "")
        url = params.get("request", {}).get("url", "")
        reason = self._policy.check(url)
        if reason is None:
            self._spawn_bg(self._continue_fetch(request_id))
            return
        is_main_frame = not self._target_id or params.get("frameId") == self._target_id
        if (
            params.get("resourceType") == "Document"
            and self._doc_refusal_hook is not None
            and is_main_frame
        ):
            self._doc_refusal_hook(url)
        self._spawn_bg(self._fail_fetch(request_id))

    async def _continue_fetch(self, request_id: str) -> None:
        with contextlib.suppress(Exception):
            await self._engine.send("Fetch.continueRequest", {"requestId": request_id})

    async def _fail_fetch(self, request_id: str) -> None:
        with contextlib.suppress(Exception):
            await self._engine.send(
                "Fetch.failRequest",
                {"requestId": request_id, "errorReason": "AccessDenied"},
            )

    async def _ensure_page_domain(self) -> None:
        if self._page_domain_enabled:
            return
        self._page_domain_enabled = True
        await self._engine.send("Page.enable")

    async def _ensure_dialog_handling(self) -> None:
        if self._dialog_handling_armed:
            return
        self._dialog_handling_armed = True
        await self._ensure_page_domain()
        self._engine.on("Page.javascriptDialogOpening", self._on_dialog_opening)

    def _on_dialog_opening(self, params: dict[str, Any]) -> None:
        dialog_type = params.get("type", "")
        message = params.get("message", "")
        accept = self._dialog_policy.get(dialog_type, True)
        logger.info(
            "javascript dialog %r auto-%s: %r",
            dialog_type, "accepted" if accept else "dismissed", message,
        )
        self._pending_dialogs.append({
            "type": dialog_type, "message": message, "accepted": accept,
        })
        self._trace.add(TraceEntry(
            timestamp=time.time(),
            action="dialog",
            input={"type": dialog_type, "message": message},
            output={"accepted": accept},
            tokens_consumed=0,
            duration_ms=0,
        ))
        args: dict[str, Any] = {"accept": accept}
        if dialog_type == "prompt" and accept:
            args["promptText"] = ""
        self._spawn_bg(self._handle_dialog(args))

    async def _handle_dialog(self, args: dict[str, Any]) -> None:
        with contextlib.suppress(Exception):
            await self._engine.send("Page.handleJavaScriptDialog", args)

    def consume_dialogs(self) -> list[dict[str, Any]]:
        dialogs, self._pending_dialogs = self._pending_dialogs, []
        return dialogs

    async def _ensure_nav_invalidation(self) -> None:
        if self._nav_invalidation_armed:
            return
        self._nav_invalidation_armed = True
        await self._ensure_page_domain()
        self._engine.on("Page.frameNavigated", self._on_frame_navigated)
        self._engine.on(
            "Page.navigatedWithinDocument", self._on_navigated_within_document
        )

    def _on_frame_navigated(self, params: dict[str, Any]) -> None:
        frame = params.get("frame", {})
        if frame.get("parentId"):
            return
        self._invalidate_snapshot_cache()

    def _on_navigated_within_document(self, params: dict[str, Any]) -> None:
        frame_id = params.get("frameId", "")
        if self._target_id and frame_id != self._target_id:
            return
        self._invalidate_snapshot_cache()

    def _invalidate_snapshot_cache(self) -> None:
        self._current_snapshot = None
        self._previous_snapshot = None
        self.delta = None
        self._consent_dismissed_this_nav = False

    async def _maybe_dismiss_consent_banner(self) -> None:
        if not self._dismiss_consent_banners or self._consent_dismissed_this_nav:
            return
        self._consent_dismissed_this_nav = True
        try:
            outcome = await self._eval(
                f"({_CONSENT_DISMISS_JS})({json.dumps(_CONSENT_ACCEPT_PHRASES)})"
            )
        except Exception:
            return
        if not isinstance(outcome, dict) or not outcome.get("clicked"):
            return
        text = outcome.get("text", "")
        logger.info("consent banner dismissed: clicked button labeled %r", text)
        self._trace.add(TraceEntry(
            timestamp=time.time(),
            action="consent_dismissed",
            input={},
            output={"text": text},
            tokens_consumed=0,
            duration_ms=0,
        ))
        await self._settle()

    async def _ensure_popup_blocking(self) -> None:
        if self._popup_block_armed or self._policy.allow_private:
            return
        self._popup_block_armed = True
        self._engine.on("Target.attachedToTarget", self._on_target_attached)
        await self._engine.send(
            "Target.setAutoAttach",
            {"autoAttach": True, "waitForDebuggerOnStart": True, "flatten": True},
        )

    def _on_target_attached(self, params: dict[str, Any]) -> None:
        target_info = params.get("targetInfo", {})
        session_id = params.get("sessionId", "")
        if target_info.get("type") == "page":
            target_id = target_info.get("targetId", "")
            popup_url = target_info.get("url", "")
            if not self._policy.allow_popups:
                self._popups_blocked += 1
                logger.warning(
                    "popup blocked: window.open()/target=_blank to %r was "
                    "refused (NavigationPolicy.allow_popups=False, the "
                    "default) — pass allow_popups=True to permit popups, at "
                    "the cost of Fetch interception inside them",
                    popup_url,
                )
                self._trace.add(TraceEntry(
                    timestamp=time.time(),
                    action="popup_blocked",
                    input={"url": popup_url},
                    output={},
                    tokens_consumed=0,
                    duration_ms=0,
                ))
                if target_id:
                    self._spawn_bg(self._close_popup_target(target_id))
                return
            self._trace.add(TraceEntry(
                timestamp=time.time(),
                action="popup_opened",
                input={},
                output={"url": popup_url, "target_id": target_id},
                tokens_consumed=0,
                duration_ms=0,
            ))
            self._popup_queue.put_nowait(
                PopupInfo(target_id=target_id, url=popup_url, session_id=session_id)
            )
            self._spawn_bg(self._resume_popup_target(session_id))
            return
        self._spawn_bg(self._resume_attached_target(session_id))

    async def wait_for_popup(self, timeout: float = 10.0) -> PopupInfo:
        if not self._policy.allow_popups:
            raise ValueError(
                "wait_for_popup() needs NavigationPolicy(allow_popups=True) "
                "- with the default policy every popup is blocked outright "
                "(see Page.popups_blocked)."
            )
        await self._ensure_popup_blocking()
        try:
            async with asyncio.timeout(timeout):
                return await self._popup_queue.get()
        except TimeoutError as e:
            raise BrowserException(BrowserError(
                type=ErrorType.NETWORK_TIMEOUT,
                message=f"No popup opened within {timeout}s.",
                confidence=0.6,
                recovery=[RecoveryAction.RETRY],
            )) from e

    async def _close_popup_target(self, target_id: str) -> None:
        with contextlib.suppress(Exception):
            await self._engine.send("Target.closeTarget", {"targetId": target_id})

    async def _resume_attached_target(self, session_id: str) -> None:
        with contextlib.suppress(Exception):
            await self._engine.send(
                "Runtime.runIfWaitingForDebugger", {}, session_id=session_id
            )

    async def _resume_popup_target(self, session_id: str) -> None:
        if self._stealth_ua:
            with contextlib.suppress(Exception):
                await self._engine.send(
                    "Network.setUserAgentOverride",
                    {"userAgent": self._stealth_ua},
                    session_id=session_id,
                )
        await self._resume_attached_target(session_id)

    async def goto(self, url: str, timeout: float = 30.0) -> None:
        load_event = asyncio.Event()
        refusal_holder: list[str | None] = [None]

        def on_refusal(url: str) -> None:
            refusal_holder[0] = url

        self._doc_refusal_hook = on_refusal

        def on_load(params: dict[str, Any]) -> None:
            frame = params.get("frame", {})
            if not frame.get("parentId"):
                load_event.set()

        await self._ensure_initialized()
        await self._ensure_popup_blocking()

        self._engine.on("Page.frameNavigated", on_load)

        self._invalidate_snapshot_cache()
        self._current_url = url
        self._version += 1
        self._previous_snapshot = None
        self.delta = None
        self._refs.reset()

        enforce_navigation(self._policy, url)

        try:
            async with asyncio.timeout(timeout):
                await self._engine.send("Page.enable")
                await self._engine.send("Network.enable")
                await self._engine.send("Runtime.enable")
                await self._ensure_fetch_interception()
                await self._ensure_popup_blocking()
                await self._ensure_closed_shadow_patch()

                await self._engine.send("Page.navigate", {"url": url})

                try:
                    await load_event.wait()
                except TimeoutError:
                    pass

                if refusal_holder[0] is not None:
                    raise BrowserException(BrowserError(
                        type=ErrorType.NAVIGATION_REFUSED,
                        message=f"navigation refused: {refusal_holder[0]}",
                        confidence=1.0,
                        recovery=[],
                    ))
        finally:
            self._engine.off("Page.frameNavigated", on_load)
            self._doc_refusal_hook = None

    async def _eval(self, expression: str, *, return_by_value: bool = True) -> Any:
        result = await self._engine.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": return_by_value},
        )
        if "exceptionDetails" in result:
            raise RuntimeError(f"JS eval failed: {result['exceptionDetails']}")
        return result.get("result", {}).get("value")

    async def _eval_object(self, expression: str) -> str:
        result = await self._engine.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": False, "objectGroup": _PROBE_OBJECT_GROUP},
        )
        if "exceptionDetails" in result:
            raise RuntimeError(f"JS eval failed: {result['exceptionDetails']}")
        return result.get("result", {}).get("objectId", "")

    async def snapshot(self) -> PageSnapshot:
        await self._ensure_initialized()
        await self._maybe_dismiss_consent_banner()

        raw_elements = await self._discover_elements()
        probe_elements = await self._discover_probe_elements()
        all_raw = raw_elements + probe_elements

        page_text = await self._eval(PAGE_TEXT_JS)
        title = await self._eval("document.title")
        url = await self._eval("location.href")

        self._version += 1
        snapshot = self._summarizer.build(
            version=self._version,
            url=url or "",
            title=title or "",
            raw_elements=all_raw,
            page_text=page_text or "",
        )

        live_handles = {el.handle for el in all_raw if el.handle}
        self._refs.evict(live_handles)
        for el in snapshot.elements:
            if el.handle:
                el.ref = self._refs.assign(el.handle)

        snapshot.tokens_estimated = self._summarizer.count_tokens(
            self._summarizer.format(snapshot)
        )

        self._previous_snapshot = self._current_snapshot
        self._current_snapshot = snapshot

        if self._previous_snapshot is not None:
            self.delta = build_delta(self._previous_snapshot, snapshot)
        else:
            self.delta = None

        scroll_metrics = await self._get_scroll_metrics()
        if scroll_metrics:
            snapshot.scroll_top = scroll_metrics["y"]
            snapshot.scroll_left = scroll_metrics["x"]
            snapshot.scroll_height = scroll_metrics["pageHeight"]
            snapshot.client_height = scroll_metrics["viewportHeight"]

        return snapshot

    async def _get_scroll_metrics(self) -> dict[str, int] | None:
        try:
            raw = await self._eval(_SCROLL_METRICS_JS)
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return None

    async def _discover_elements(self) -> list[RawElement]:
        raw = await self._eval(DISCOVER_ELEMENTS_JS)
        if not raw:
            return []
        items = json.loads(raw)
        return [RawElement(
            tag=item.get("tag", ""),
            role=item.get("role", ""),
            text=item.get("text", ""),
            placeholder=item.get("placeholder"),
            in_shadow_dom=item.get("inShadowDom", False),
            cx=item.get("cx", 0),
            cy=item.get("cy", 0),
            computed_display="",
            computed_visibility="",
            computed_opacity="",
            aria_hidden=False,
            width=1,
            height=1,
            href=item.get("href"),
            handle=item.get("handle", ""),
            disabled=item.get("disabled", False),
            required=item.get("required", False),
            checked=item.get("checked"),
            selected=item.get("selected"),
            value=item.get("value"),
            canvas_width=item.get("canvasWidth"),
            canvas_height=item.get("canvasHeight"),
            is_combobox=item.get("isCombobox", False),
            combobox_expanded=item.get("comboboxExpanded"),
            combobox_options=item.get("comboboxOptions"),
            closed_shadow_unreadable=item.get("closedShadowUnreadable", False),
        ) for item in items]

    async def _discover_probe_elements(self) -> list[RawElement]:
        try:
            async with asyncio.timeout(_PROBE_TIMEOUT_S):
                raw = await self._eval(PROBE_CLICKABLE_JS)
                if not raw:
                    return []
                items = json.loads(raw)

                object_ids = []
                for item in items:
                    handle = item.get("handle", "")
                    if _is_trusted_handle(handle):
                        object_ids.append(await self._eval_object(
                            f"document.querySelector('[data-grip-h=\"{handle}\"]')"
                        ))

                confirmed = []
                for i, item in enumerate(items):
                    if i < len(object_ids) and object_ids[i]:
                        try:
                            listeners = await self._engine.send(
                                "DOMDebugger.getEventListeners", {"objectId": object_ids[i]}
                            )
                            if _has_click_listener(listeners.get("listeners", [])):
                                confirmed.append(item)
                        except Exception:
                            pass

                return [RawElement(
                    tag=item.get("tag", ""),
                    role=item.get("role", ""),
                    text=item.get("text", ""),
                    placeholder=None,
                    in_shadow_dom=item.get("inShadowDom", False),
                    cx=item.get("cx", 0),
                    cy=item.get("cy", 0),
                    computed_display="",
                    computed_visibility="",
                    computed_opacity="",
                    aria_hidden=False,
                    width=1,
                    height=1,
                    handle=item.get("handle", ""),
                ) for item in confirmed]
        except (TimeoutError, Exception):
            return []

    async def payload(self, last_sent_version: int) -> tuple[str, int]:
        return render_payload(
            self._current_snapshot,
            self.delta,
            last_sent_version,
            self._summarizer,
        )

    async def click(self, target: str, *, human: bool = False) -> None:
        self._assert_not_safe("click")
        await self._ensure_initialized()

        element = await self._resolve_target(target)
        if human:
            result = await self._eval(f"({RESOLVE_POINT_JS})({json.dumps(element.handle)}, {json.dumps(element.tag)}, {json.dumps(element.text)})")
            if not result or not result.get("ok"):
                raise BrowserException(self._classifier.classify_semantic_miss(target))
            x, y = result["x"], result["y"]
            await self._human_click(x, y)
        else:
            result = await self._eval(
                f"({CLICK_ELEMENT_JS})({json.dumps(element.handle)}, {json.dumps(element.tag)}, {json.dumps(element.text)})"
            )
            if not result or not result.get("ok"):
                reason = result.get("reason", "unknown") if result else "unknown"
                if reason == "not_found":
                    raise BrowserException(self._classifier.classify_semantic_miss(target))
                raise BrowserException(BrowserError(
                    type=ErrorType.ELEMENT_NOT_FOUND,
                    message=f"click failed: {reason}",
                    confidence=0.8,
                    recovery=[RecoveryAction.RE_SNAPSHOT, RecoveryAction.RETRY],
                ))

        await self._settle()

    async def _resolve_target(self, target: str) -> Element:
        if not self._current_snapshot:
            await self.snapshot()

        snapshot = self._current_snapshot
        assert snapshot is not None

        if self._refs.is_stale(target):
            raise BrowserException(self._classifier.classify_stale_ref(target))

        for el in snapshot.elements:
            if el.ref == target:
                return el

        matches = []
        target_lower = target.lower()
        for el in snapshot.elements:
            text_match = target_lower in el.text.lower()
            placeholder_match = el.placeholder and target_lower in el.placeholder.lower()
            role_match = target_lower in el.role.lower()
            if text_match or placeholder_match or role_match:
                matches.append(el)

        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            candidates = [(el.ref, el.text) for el in matches]
            raise BrowserException(self._classifier.classify_ambiguous_target(target, candidates))

        raise BrowserException(self._classifier.classify_semantic_miss(target))

    async def _human_click(self, x: int, y: int) -> None:
        path = bezier_path((self._pointer_x, self._pointer_y), (x, y))
        for px, py in path:
            await self._engine.send("Input.dispatchMouseEvent", {
                "type": "mouseMoved",
                "x": px,
                "y": py,
            })
            await asyncio.sleep(move_delay())

        await self._engine.send("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1,
        })
        await asyncio.sleep(press_dwell())
        await self._engine.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1,
        })
        self._pointer_x = x
        self._pointer_y = y

    async def _settle(self) -> None:
        deadline = time.monotonic() + self._settle_timeout
        quiet = 0
        last_sig = ""
        while time.monotonic() < deadline:
            try:
                sig = await self._eval(_SETTLE_SIGNATURE_JS)
            except Exception:
                break
            if sig == last_sig:
                quiet += 1
                if quiet >= _SETTLE_QUIET_POLLS:
                    break
            else:
                quiet = 0
                last_sig = sig
            await asyncio.sleep(_SETTLE_POLL_S)

    async def type(self, target: str, text: str) -> None:
        self._assert_not_safe("type")
        await self._ensure_initialized()

        element = await self._resolve_target(target)
        result = await self._eval(
            f"({TYPE_ELEMENT_JS})({json.dumps(element.handle)}, {json.dumps(text)}, {json.dumps(element.tag)}, {json.dumps(element.text)})"
        )
        if not result or not result.get("ok"):
            reason = result.get("reason", "unknown") if result else "unknown"
            if reason == "not_found":
                raise BrowserException(self._classifier.classify_semantic_miss(target))
            raise BrowserException(BrowserError(
                type=ErrorType.ELEMENT_NOT_FOUND,
                message=f"type failed: {reason}",
                confidence=0.8,
                recovery=[RecoveryAction.RE_SNAPSHOT, RecoveryAction.RETRY],
            ))

        self._trace.add(TraceEntry(
            timestamp=time.time(),
            action="type",
            input={"target": target, "text": text},
            output={"ok": True},
            tokens_consumed=0,
            duration_ms=0,
        ))

        await self._settle()

    async def select(self, target: str, value: str) -> None:
        self._assert_not_safe("select")
        await self._ensure_initialized()

        element = await self._resolve_target(target)
        result = await self._eval(
            f"({_SELECT_OPTION_JS})({json.dumps(element.handle)}, {json.dumps(element.tag)}, {json.dumps(value)})"
        )
        if not result or not result.get("ok"):
            reason = result.get("reason", "unknown") if result else "unknown"
            if reason == "not_found":
                raise BrowserException(self._classifier.classify_semantic_miss(target))
            if reason == "not_a_select":
                raise BrowserException(self._classifier.classify_not_a_select(target, result.get("tag", "")))
            if reason == "no_such_option":
                raise BrowserException(self._classifier.classify_invalid_option(target, value, result.get("options", [])))
            raise BrowserException(BrowserError(
                type=ErrorType.ELEMENT_NOT_FOUND,
                message=f"select failed: {reason}",
                confidence=0.8,
                recovery=[RecoveryAction.RE_SNAPSHOT, RecoveryAction.RETRY],
            ))

        await self._settle()

    async def hover(self, target: str) -> None:
        self._assert_not_safe("hover")
        await self._ensure_initialized()

        element = await self._resolve_target(target)
        result = await self._eval(f"({RESOLVE_POINT_JS})({json.dumps(element.handle)}, {json.dumps(element.tag)}, {json.dumps(element.text)})")
        if not result or not result.get("ok"):
            raise BrowserException(self._classifier.classify_semantic_miss(target))

        x, y = result["x"], result["y"]
        await self._engine.send("Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": x,
            "y": y,
        })
        self._pointer_x = x
        self._pointer_y = y

    async def press(self, key: str, modifiers: list[str] | None = None) -> None:
        self._assert_not_safe("press")
        await self._ensure_initialized()

        mod_bits = _modifiers_bitmask(modifiers)
        if key in _NAMED_KEYS:
            code, vk = _NAMED_KEYS[key]
        else:
            code, vk = key, 0

        await self._engine.send("Input.dispatchKeyEvent", {
            "type": "keyDown",
            "key": key,
            "code": code,
            "windowsVirtualKeyCode": vk,
            "modifiers": mod_bits,
        })
        await self._engine.send("Input.dispatchKeyEvent", {
            "type": "keyUp",
            "key": key,
            "code": code,
            "windowsVirtualKeyCode": vk,
            "modifiers": mod_bits,
        })

    async def upload(self, target: str, *paths: str) -> None:
        self._assert_not_safe("upload")
        await self._ensure_initialized()

        raw = await self._eval(_FIND_FILE_INPUTS_JS)
        if not raw:
            raise BrowserException(self._classifier.classify_semantic_miss(target))
        inputs = json.loads(raw)

        target_lower = target.lower()
        matched = None
        for inp in inputs:
            if (target_lower in inp.get("label", "").lower() or
                target_lower in inp.get("aria", "").lower() or
                target_lower in inp.get("name", "").lower() or
                target_lower in inp.get("id", "").lower()):
                matched = inp
                break

        if not matched:
            raise BrowserException(self._classifier.classify_semantic_miss(target))

        handle = matched.get("handle", "")
        if not _is_trusted_handle(handle):
            raise BrowserException(self._classifier.classify_semantic_miss(target))

        object_id = await self._eval_object(f"({_RESOLVE_FILE_INPUT_JS})({json.dumps(handle)})")
        if not object_id:
            raise BrowserException(self._classifier.classify_semantic_miss(target))

        await self._engine.send("DOM.setFileInputFiles", {
            "objectId": object_id,
            "files": list(paths),
        })

    async def scroll(
        self,
        direction: str = "down",
        pages: float = 1.0,
        ref: str | None = None,
    ) -> ScrollPosition:
        self._assert_not_safe("scroll")
        await self._ensure_initialized()

        if ref:
            element = await self._resolve_target(ref)
            result = await self._eval(
                f"({_SCROLL_TO_REF_JS})({json.dumps(element.handle)}, {json.dumps(element.tag)}, {json.dumps(element.text)})"
            )
        else:
            result = await self._eval(
                f"({_SCROLL_BY_JS})({json.dumps(direction)}, {json.dumps(pages)})"
            )

        if not result or not result.get("ok"):
            raise BrowserException(BrowserError(
                type=ErrorType.ELEMENT_NOT_FOUND,
                message="scroll failed",
                confidence=0.7,
                recovery=[RecoveryAction.RE_SNAPSHOT],
            ))

        return ScrollPosition(
            x=result.get("x", 0),
            y=result.get("y", 0),
            page_height=result.get("pageHeight", 0),
            page_width=result.get("pageWidth", 0),
            viewport_height=result.get("viewportHeight", 0),
            viewport_width=result.get("viewportWidth", 0),
        )

    async def read(self, max_chars: int | None = None) -> Document:
        self._assert_not_safe("read")
        await self._ensure_initialized()

        raw = await self._eval(READ_CONTENT_JS)
        if not raw:
            return Document(title="", url="", blocks=[])

        data = json.loads(raw)
        blocks: list[Block] = []
        for i, b in enumerate(data.get("blocks", [])):
            block = Block(
                id=i,
                kind=b.get("kind", "text"),
                text=b.get("text", ""),
                path=b.get("path", []),
                level=b.get("level", 0),
            )
            blocks.append(block)

        doc = Document(
            title=data.get("title", ""),
            url=data.get("url", ""),
            blocks=blocks,
        )

        if max_chars is not None:
            doc = self._truncate(doc, max_chars)

        return doc

    def _truncate(self, doc: Document, max_chars: int) -> Document:
        total = 0
        kept: list[Block] = []
        for block in doc.blocks:
            if total + len(block.text) > max_chars:
                break
            kept.append(block)
            total += len(block.text) + 2
        return Document(title=doc.title, url=doc.url, blocks=kept)

    async def screenshot(self) -> Screenshot:
        self._assert_not_safe("screenshot")
        await self._ensure_initialized()

        result = await self._engine.send("Page.captureScreenshot", {"format": "jpeg", "quality": 50})
        data = base64.b64decode(result.get("data", ""))
        tokens_estimated = len(data) // 1000
        return Screenshot(data=data, tokens_estimated=tokens_estimated)

    async def wait_for(
        self,
        *,
        text: str | None = None,
        ref: str | None = None,
        selector: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._assert_not_safe("wait_for")
        await self._ensure_initialized()

        if sum(1 for x in (text, ref, selector) if x) != 1:
            raise ValueError("wait_for() requires exactly one of text/ref/selector")

        if text:
            js = f"({_WAIT_TEXT_JS})({json.dumps(text)})"
        elif ref:
            js = f"({_WAIT_ELEMENT_JS})({json.dumps(ref)})"
        else:
            js = f"({_WAIT_SELECTOR_JS})({json.dumps(selector)})"

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                result = await self._eval(js)
                if result:
                    await self._settle()
                    return
            except Exception:
                pass
            await asyncio.sleep(0.1)

        raise BrowserException(self._classifier.classify_timeout())

    async def detect_challenge(self) -> ChallengeResult:
        await self._ensure_initialized()

        html = await self._eval("document.documentElement.outerHTML")
        frame_tree = await self._engine.send("Page.getFrameTree", {})
        frames = frame_urls(frame_tree)
        stage = detect_challenge_from_html(html or "", frames)

        if stage == ChallengeStage.NONE:
            return ChallengeResult(status="none", stage=stage)

        if needs_vision(stage):
            shot = await self.screenshot()
            return ChallengeResult(
                status="needs_vision",
                stage=stage,
                screenshot=shot,
            )

        return ChallengeResult(status="detected", stage=stage)

    async def solve_challenge(self, timeout: float = 30.0) -> ChallengeResult:
        await self._ensure_initialized()

        detection = await self.detect_challenge()
        if detection.status == "none":
            return ChallengeResult(status="none", stage=ChallengeStage.NONE)
        if detection.status == "needs_vision":
            return detection

        stage = detection.stage
        if not is_solvable(stage):
            return ChallengeResult(status="unsupported", stage=stage)

        deadline = time.monotonic() + timeout

        if stage == ChallengeStage.CHECKBOX:
            result = await self._eval(POINT_PROBE_JS)
            if not result:
                return ChallengeResult(status="unsupported", stage=stage, detail="no anchor found")
            x, y = result["x"], result["y"]
            await self._human_click(x, y)
        elif stage == ChallengeStage.TURNSTILE:
            result = await self._eval(POINT_PROBE_JS)
            if not result:
                return ChallengeResult(status="unsupported", stage=stage, detail="no widget found")
            x, y = result["x"], result["y"]
            await self._human_click(x, y)
        elif stage == ChallengeStage.SLIDER:
            result = await self._eval(SLIDER_PROBE_JS)
            if not result or "reason" in result:
                return ChallengeResult(status="unsupported", stage=stage, detail=result.get("reason", "unknown"))
            x, y = result["x"], result["y"]
            end_x = result["endX"]
            await self._drag(x, y, end_x, y)

        while time.monotonic() < deadline:
            token = await self._eval(TOKEN_PROBE_JS)
            if token:
                return ChallengeResult(status="solved", stage=stage)

            html = await self._eval("document.documentElement.outerHTML")
            frame_tree = await self._engine.send("Page.getFrameTree", {})
            frames = frame_urls(frame_tree)
            current = detect_challenge_from_html(html or "", frames)
            if current == ChallengeStage.NONE:
                return ChallengeResult(status="solved", stage=stage)

            await asyncio.sleep(0.5)

        return ChallengeResult(status="timeout", stage=stage)

    async def _drag(self, start_x: int, start_y: int, end_x: int, end_y: int) -> None:
        path = bezier_path((start_x, start_y), (end_x, end_y), steps=30)
        for px, py in path:
            await self._engine.send("Input.dispatchMouseEvent", {
                "type": "mouseMoved",
                "x": px,
                "y": py,
            })
            await asyncio.sleep(move_delay())

        await self._engine.send("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": end_x,
            "y": end_y,
            "button": "left",
            "clickCount": 1,
        })
        await asyncio.sleep(press_dwell())

        for px, py in path:
            await self._engine.send("Input.dispatchMouseEvent", {
                "type": "mouseMoved",
                "x": px,
                "y": py,
            })
            await asyncio.sleep(move_delay())

        await self._engine.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": end_x,
            "y": end_y,
            "button": "left",
            "clickCount": 1,
        })

    async def enable_downloads(self, path: str) -> None:
        self._assert_not_safe("enable_downloads")
        await self._ensure_initialized()

        self._download_dir = Path(path)
        self._download_dir.mkdir(parents=True, exist_ok=True)

        if not self._download_events_armed:
            self._download_events_armed = True
            self._download_queue = asyncio.Queue()
            self._engine.on("Page.downloadWillBegin", self._on_download_will_begin)
            self._engine.on("Page.downloadProgress", self._on_download_progress)

        await self._engine.send("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": str(self._download_dir),
        })

    def _on_download_will_begin(self, params: dict[str, Any]) -> None:
        self._spawn_bg(self._track_download(params.get("guid", ""), params.get("suggestedFilename", "")))

    def _on_download_progress(self, params: dict[str, Any]) -> None:
        if params.get("state") == "completed":
            self._spawn_bg(self._complete_download(params.get("guid", "")))

    async def _track_download(self, guid: str, filename: str) -> None:
        pass

    async def _complete_download(self, guid: str) -> None:
        if self._download_queue:
            await self._download_queue.put(self._download_dir / f"{guid}")  # Placeholder

    async def wait_for_download(self, timeout: float = 30.0) -> Path:
        if not self._download_queue:
            raise RuntimeError("enable_downloads() must be called before wait_for_download()")
        try:
            async with asyncio.timeout(timeout):
                result = await self._download_queue.get()
                return result
        except TimeoutError as e:
            raise BrowserException(self._classifier.classify_timeout()) from e

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._closer:
            await self._closer(self._target_id)
        await self._engine.disconnect()
