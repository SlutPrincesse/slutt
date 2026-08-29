"""stdio MCP server exposing nexus browser to any MCP client."""
from __future__ import annotations

import asyncio
import base64
import contextlib
import dataclasses
import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from nexus.browser.adapters import adapter_from_env
from nexus.browser.browser import Browser
from nexus.browser.errors import BrowserException
from nexus.browser.page import Page

TOOL_NAMES = (
    "open", "goto", "snapshot", "click", "type", "select", "read", "screenshot", "run",
    "list_tabs", "switch_tab", "close_tab", "press", "upload", "links", "popups_blocked",
    "wait_for", "hover", "scroll",
)

_browser: Browser | None = None
_page: Page | None = None
_last_sent_version = 0
_lock = asyncio.Lock()


def reset_state() -> None:
    global _browser, _page, _last_sent_version
    _browser = None
    _page = None
    _last_sent_version = 0


async def _ensure_browser() -> Browser:
    global _browser
    if _browser is None:
        _browser = Browser()
    return _browser


def _require_page() -> Page:
    if _page is None:
        raise RuntimeError("call 'open' with a url first")
    return _page


def _with_dialog_note(page: Page, text: str) -> str:
    dialogs = page.consume_dialogs()
    if not dialogs:
        return text
    lines = [
        f"[dialog] {d['type']} auto-{'accepted' if d['accepted'] else 'dismissed'}: "
        f"{d['message']!r}"
        for d in dialogs
    ]
    return "\n".join(lines) + "\n\n" + text


async def call_tool(name: str, arguments: dict[str, Any]) -> str:
    async with _lock:
        try:
            return await _dispatch_tool(name, arguments)
        except BrowserException as e:
            recovery = ", ".join(a.name for a in e.error.recovery) or "none"
            enriched = dataclasses.replace(
                e.error, message=f"{e.error.message} (suggested recovery: {recovery})"
            )
            raise BrowserException(enriched) from e


async def _dispatch_tool(name: str, arguments: dict[str, Any]) -> str:
    global _page, _last_sent_version
    if name == "open":
        browser = await _ensure_browser()
        _page = await browser.open(arguments["url"])
        _last_sent_version = 0
        await _page.snapshot()
        text, _last_sent_version = _page.payload(_last_sent_version)
        return _with_dialog_note(_page, text)
    if name == "run":
        browser = await _ensure_browser()
        if browser._llm is None:
            try:
                browser._llm = adapter_from_env()
            except ImportError as e:
                raise RuntimeError(f"the 'run' tool needs an LLM adapter: {e}") from e
            if browser._llm is None:
                raise RuntimeError(
                    "the 'run' tool needs an LLM API key: set ANTHROPIC_API_KEY, "
                    "OPENAI_API_KEY, or GEMINI_API_KEY"
                )
        from nexus.browser.runner import Runner

        _page = await browser.open(arguments["url"])
        _last_sent_version = 0
        runner = Runner(llm=browser._llm, page=_page, trace=browser.trace)
        result = await runner.run(arguments["goal"])
        _last_sent_version = runner._last_sent_version
        if result.data is None:
            return (
                "run ended without calling done() — no result was produced "
                "(step limit, an LLM timeout, or the agent gave up). The page "
                "is left wherever it last navigated; 'snapshot' to see where."
            )
        return str(result.data)
    if name == "list_tabs":
        browser = await _ensure_browser()
        active_id = _page._target_id if _page is not None else None
        lines = [
            f"{p._target_id}\t{p._current_url or '(not yet loaded)'}"
            + ("\t[active]" if p._target_id == active_id else "")
            for p in browser.pages
        ]
        return "\n".join(lines) if lines else "(no open tabs)"
    if name == "switch_tab":
        browser = await _ensure_browser()
        target = browser.get_page(arguments["target_id"])
        if target is None:
            raise ValueError(f"no open tab with target_id {arguments['target_id']!r}")
        _page = target
        _last_sent_version = 0
        await _page.snapshot()
        text, _last_sent_version = _page.payload(_last_sent_version)
        return _with_dialog_note(_page, text)
    if name == "close_tab":
        browser = await _ensure_browser()
        target_id = arguments.get("target_id") or None
        closing = browser.get_page(target_id) if target_id else _require_page()
        if closing is None:
            raise ValueError(f"no open tab with target_id {target_id!r}")
        was_active = _page is not None and closing._target_id == _page._target_id
        await closing.close()
        if was_active:
            _page = None
            _last_sent_version = 0
        return f"closed {closing._target_id}"
    page = _require_page()
    if name == "links":
        snap = await page.snapshot()
        return "\n".join(f"{text}\t{url}" for text, url in snap.links) or "(no links)"
    if name == "popups_blocked":
        return str(page.popups_blocked)
    if name == "press":
        await page.press(arguments["key"])
        await page.snapshot()
        text, _last_sent_version = page.payload(_last_sent_version)
        return _with_dialog_note(page, text)
    if name == "upload":
        await page.upload(arguments["target"], *arguments["paths"])
        await page.snapshot()
        text, _last_sent_version = page.payload(_last_sent_version)
        return _with_dialog_note(page, text)
    if name == "goto":
        await page.goto(arguments["url"])
        await page.snapshot()
        text, _last_sent_version = page.payload(_last_sent_version)
        return _with_dialog_note(page, text)
    if name == "snapshot":
        await page.snapshot()
        text, _last_sent_version = page.payload(_last_sent_version)
        return _with_dialog_note(page, text)
    if name == "click":
        await page.click(arguments["target"])
        await page.snapshot()
        text, _last_sent_version = page.payload(_last_sent_version)
        return _with_dialog_note(page, text)
    if name == "type":
        await page.type(arguments["target"], arguments["text"])
        await page.snapshot()
        text, _last_sent_version = page.payload(_last_sent_version)
        return _with_dialog_note(page, text)
    if name == "select":
        await page.select(arguments["target"], arguments["value"])
        await page.snapshot()
        text, _last_sent_version = page.payload(_last_sent_version)
        return _with_dialog_note(page, text)
    if name == "hover":
        await page.hover(arguments["target"])
        await page.snapshot()
        text, _last_sent_version = page.payload(_last_sent_version)
        return _with_dialog_note(page, text)
    if name == "wait_for":
        await page.wait_for(
            text=arguments.get("text"),
            ref=arguments.get("ref"),
            selector=arguments.get("selector"),
            timeout=arguments.get("timeout", 10.0),
        )
        text, _last_sent_version = page.payload(_last_sent_version)
        return _with_dialog_note(page, text)
    if name == "scroll":
        pos = await page.scroll(
            arguments.get("direction", "down"),
            arguments.get("pages", 1.0),
            ref=arguments.get("ref"),
        )
        return (
            f"x={pos.x} y={pos.y} page_height={pos.page_height} "
            f"page_width={pos.page_width} viewport_height={pos.viewport_height} "
            f"viewport_width={pos.viewport_width}"
        )
    if name == "read":
        doc = await page.read()
        return str(doc.text)
    if name == "screenshot":
        shot = await page.screenshot()
        return shot.b64
    raise ValueError(f"unknown tool {name!r}")


@contextlib.asynccontextmanager
async def _lifespan(_server: Any) -> AsyncIterator[dict[str, Any]]:
    try:
        yield {}
    finally:
        global _browser, _page
        if _browser is not None:
            await _browser.close()
        _browser = None
        _page = None


def main() -> None:
    try:
        from mcp.server import MCPServer
    except ModuleNotFoundError as e:
        raise SystemExit(
            "nexus browser mcp needs the optional mcp package: "
            'pip install "nexus-browser[mcp]"'
        ) from e

    server = MCPServer("nexus-browser", lifespan=_lifespan)

    _SNAPSHOT_SHAPES = (
        "Returns a full page state (`PAGE: <title>` / `URL:` / `INTERACTIVE:` "
        "elements as `[tag:ref] 'label'`, e.g. `[btn:e5] 'Submit'`, CONTENT "
        "truncated to 2000 chars — use 'read' for the full prose) the first "
        "time, or `DELTA v<from>-><to>` (added/changed elements as `[tag:ref]`, "
        "removed as bare `[ref]`, plus CONTENT word-diff ops, or "
        "`DELTA vN->vM: no change`) once a baseline exists — falling back to a "
        "full snapshot whenever the delta wouldn't actually be smaller."
    )
    _TARGET_NOTE = (
        "target is an exact ref from the last snapshot (e.g. 'e5') or a "
        "case-insensitive substring of the element's text/role/placeholder."
    )

    @server.tool(
        name="open",
        description=f"Open a URL and return its snapshot. {_SNAPSHOT_SHAPES}",
    )
    async def _open(url: str) -> str:
        return await call_tool("open", {"url": url})

    @server.tool(name="goto", description="Navigate the current page to a URL.")
    async def _goto(url: str) -> str:
        return await call_tool("goto", {"url": url})

    @server.tool(name="snapshot", description=f"Re-snapshot the page. {_SNAPSHOT_SHAPES}")
    async def _snapshot() -> str:
        return await call_tool("snapshot", {})

    @server.tool(name="click", description=f"Click an element. {_TARGET_NOTE}")
    async def _click(target: str) -> str:
        return await call_tool("click", {"target": target})

    @server.tool(
        name="type",
        description=(
            f"Type text into an input/textarea. {_TARGET_NOTE} Matches only "
            "input/textarea/textbox elements (also against their placeholder)."
        ),
    )
    async def _type(target: str, text: str) -> str:
        return await call_tool("type", {"target": target, "text": text})

    @server.tool(
        name="select",
        description=(
            "Choose an option in a <select> dropdown, by visible option text "
            f"(preferred) or its value attribute. {_TARGET_NOTE} Matches only "
            "<select> elements."
        ),
    )
    async def _select(target: str, value: str) -> str:
        return await call_tool("select", {"target": target, "value": value})

    @server.tool(
        name="hover",
        description=(
            f"Move the pointer over an element without clicking it, to reveal "
            f"a hover-only menu/tooltip. {_TARGET_NOTE}"
        ),
    )
    async def _hover(target: str) -> str:
        return await call_tool("hover", {"target": target})

    @server.tool(
        name="wait_for",
        description=(
            "Block until a condition on the live page becomes true, then "
            "re-snapshot — for an SPA route change or an XHR-driven update "
            "that a plain snapshot right after click/type is too early to "
            "see. Pass exactly one of: text (a substring of the page's "
            "visible prose), ref (a substring of a specific element's own "
            "text/value/aria-label — the same match click/type use), or "
            "selector (a raw CSS selector). Raises a timeout error if the "
            "condition never becomes true."
        ),
    )
    async def _wait_for(
        text: str = "", ref: str = "", selector: str = "", timeout: float = 10.0,
    ) -> str:
        return await call_tool("wait_for", {
            "text": text or None, "ref": ref or None, "selector": selector or None,
            "timeout": timeout,
        })

    @server.tool(
        name="scroll",
        description=(
            "Scroll the viewport, or bring a specific element into view. "
            "direction is 'up'/'down'/'left'/'right' (default 'down'), pages "
            "is how many viewports to scroll (default 1.0). Pass ref (an "
            "exact ref or fuzzy description, same as click/type) to scroll "
            "that element into view instead — direction/pages are ignored "
            "when ref is given."
        ),
    )
    async def _scroll(
        direction: str = "down", pages: float = 1.0, ref: str = "",
    ) -> str:
        return await call_tool("scroll", {
            "direction": direction, "pages": pages, "ref": ref or None,
        })

    @server.tool(name="read", description="Read the page as citable prose blocks.")
    async def _read() -> str:
        return await call_tool("read", {})

    @server.tool(name="press", description="Press a key (e.g. 'Enter', 'Tab') on the page.")
    async def _press(key: str) -> str:
        return await call_tool("press", {"key": key})

    @server.tool(
        name="upload",
        description=(
            "Set one or more local file paths on a <input type=file>. "
            f"{_TARGET_NOTE}"
        ),
    )
    async def _upload(target: str, paths: list[str]) -> str:
        return await call_tool("upload", {"target": target, "paths": paths})

    @server.tool(
        name="links",
        description=(
            "Re-snapshot and list every fetchable link's text and absolute "
            "URL, tab-separated one per line — hrefs are left out of "
            "snapshot/DELTA text to keep the token budget down."
        ),
    )
    async def _links() -> str:
        return await call_tool("links", {})

    @server.tool(
        name="popups_blocked",
        description=(
            "Count of window.open()/target=\"_blank\" attempts refused by popup "
            "blocking so far. Nonzero after a click that should have opened a "
            "new tab explains why nothing happened."
        ),
    )
    async def _popups_blocked() -> str:
        return await call_tool("popups_blocked", {})

    @server.tool(
        name="screenshot",
        description=(
            "Capture a JPEG screenshot of the current page as an image "
            "content block (a file path if the client can't accept one)."
        ),
        structured_output=False,
    )
    async def _screenshot() -> Any:
        b64 = await call_tool("screenshot", {})
        data = base64.b64decode(b64)
        try:
            from mcp.server.mcpserver.utilities.types import Image
        except ImportError:
            fd, path = tempfile.mkstemp(prefix="nexus-screenshot-", suffix=".jpg")
            os.close(fd)
            Path(path).write_bytes(data)
            return path
        return Image(data=data, format="jpeg")

    @server.tool(
        name="list_tabs",
        description="List open tabs (target_id and url, active tab marked).",
    )
    async def _list_tabs() -> str:
        return await call_tool("list_tabs", {})

    @server.tool(
        name="switch_tab",
        description=(
            "Make an already-open tab active; snapshot/click/type/read/goto "
            "operate on it from then on."
        ),
    )
    async def _switch_tab(target_id: str) -> str:
        return await call_tool("switch_tab", {"target_id": target_id})

    @server.tool(
        name="close_tab",
        description=(
            "Close a tab by target_id, or the active tab if target_id is "
            "omitted. Closing the active tab requires 'switch_tab' or 'open' "
            "before the next snapshot/click/type call."
        ),
    )
    async def _close_tab(target_id: str = "") -> str:
        return await call_tool("close_tab", {"target_id": target_id})

    @server.tool(
        name="run",
        description=(
            "Drive the browser toward a goal autonomously (snapshot/click/type/"
            "read in a loop) and return the final result. Requires "
            "ANTHROPIC_API_KEY or OPENAI_API_KEY in the server's environment."
        ),
    )
    async def _run(goal: str, url: str) -> str:
        return await call_tool("run", {"goal": goal, "url": url})

    server.run("stdio")


if __name__ == "__main__":
    main()
