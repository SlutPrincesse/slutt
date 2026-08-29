from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import urllib.parse
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nexus.browser.cdp.engine import CDPEngine
from nexus.browser.cdp.launcher import ChromeLauncher, _STEALTH_UA, default_launch_timeout
from nexus.browser.page import Page
from nexus.browser.security.policy import NavigationPolicy, enforce as enforce_navigation
from nexus.browser.trace import Trace

if TYPE_CHECKING:
    from nexus.browser.adapters.base import LLMAdapter
    from nexus.browser.runner import RunResult

logger = logging.getLogger(__name__)

_MACROS: dict[str, str] = {
    "@google_search":       "https://www.google.com/search?q={query}",
    "@youtube_search":      "https://www.youtube.com/results?search_query={query}",
    "@amazon_search":       "https://www.amazon.com/s?k={query}",
    "@github_search":       "https://github.com/search?q={query}",
    "@reddit_search":       "https://www.reddit.com/search/?q={query}",
    "@wikipedia_search":    "https://en.wikipedia.org/wiki/Special:Search?search={query}",
    "@twitter_search":      "https://twitter.com/search?q={query}",
    "@yelp_search":         "https://www.yelp.com/search?find_desc={query}",
    "@seekingalpha_search": "https://seekingalpha.com/search?q={query}",
    "@reuters_search":      "https://www.reuters.com/search/news?blob={query}",
    "@wsj_search":          "https://www.wsj.com/search?query={query}&mod=searchresults_viewallresults",
    "@reddit_wsb":          "https://www.reddit.com/r/wallstreetbets/search/?q={query}&restrict_sr=1&sort=new",
}

_DEFAULT_VIEWPORT: dict[str, Any] = {
    "width": 1280,
    "height": 800,
    "device_scale_factor": 1,
    "mobile": False,
    "touch": False,
}

_MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36"
)

_DEFAULT_PERMISSIONS: dict[str, bool] = {
    "notifications": False,
    "geolocation": False,
}


def _expand_macro(url: str, **kwargs: str) -> str:
    if not url.startswith("@"):
        return url
    template = _MACROS.get(url)
    if not template:
        raise ValueError(f"Unknown macro: {url!r}. Available: {sorted(_MACROS)}")
    query = urllib.parse.quote_plus(kwargs.get("query", ""))
    return template.format(query=query)


async def fetch_browser_ws_url(port: int, timeout: float | None = None) -> str:
    import time
    import urllib.request

    def _do_fetch() -> dict[str, Any]:
        with urllib.request.urlopen(
            f"http://localhost:{port}/json/version", timeout=2
        ) as resp:
            parsed: dict[str, Any] = json.loads(resp.read())
            return parsed

    deadline = time.monotonic() + (
        timeout if timeout is not None else default_launch_timeout()
    )
    while time.monotonic() < deadline:
        try:
            info = await asyncio.to_thread(_do_fetch)
            if ws_url := info.get("webSocketDebuggerUrl"):
                return str(ws_url)
        except Exception:
            pass
        await asyncio.sleep(0.2)
    raise RuntimeError(f"No Chrome browser endpoint found on port {port}")


class Browser:
    def __init__(
        self,
        llm: LLMAdapter | None = None,
        headless: bool = True,
        safe: bool = False,
        proxy: str | None = None,
        stealth: bool = False,
        block_resources: bool = False,
        allow_private: bool = False,
        allow_file: bool = False,
        allow_popups: bool = False,
        user_data_dir: str | None = None,
        cdp_url: str | None = None,
        launch_timeout: float | None = None,
        viewport: dict[str, Any] | None = None,
        permissions: dict[str, bool] | None = None,
        geolocation: dict[str, float] | None = None,
    ) -> None:
        self._llm = llm
        self._headless = headless
        self._safe = safe
        self._proxy = proxy
        self._stealth = stealth
        self._block_resources = block_resources
        self._policy = NavigationPolicy(
            allow_private=allow_private, allow_file=allow_file, allow_popups=allow_popups
        )
        self._user_data_dir = user_data_dir
        self._cdp_url = cdp_url
        self._launch_timeout = launch_timeout
        self._viewport: dict[str, Any] = {**_DEFAULT_VIEWPORT, **(viewport or {})}
        self._permissions: dict[str, bool] = {**_DEFAULT_PERMISSIONS, **(permissions or {})}
        if geolocation is not None and "geolocation" not in (permissions or {}):
            self._permissions["geolocation"] = True
        self._geolocation = geolocation
        self._stealth_ua: str | None = None
        self._launcher: ChromeLauncher | None = None
        self._engine: CDPEngine | None = None
        self._port: int = 0
        self._pages: list[Page] = []
        self._connect_lock = asyncio.Lock()
        self.trace = Trace()

    async def __aenter__(self) -> "Browser":
        await self._connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def _connect(self) -> None:
        if self._engine:
            return
        async with self._connect_lock:
            if self._engine:
                return
            if self._cdp_url:
                engine = CDPEngine()
                await engine.connect(self._cdp_url)
                await self._apply_permissions(engine)
                await self._resolve_stealth_ua(engine)
                self._engine = engine
                return
            launcher = ChromeLauncher(
                user_data_dir=self._user_data_dir,
                launch_timeout=self._launch_timeout,
            )
            await asyncio.to_thread(
                launcher.launch,
                headless=self._headless,
                proxy=self._proxy,
                stealth=self._stealth,
            )
            try:
                self._port = launcher.port
                ws_url = await fetch_browser_ws_url(
                    self._port, timeout=launcher.launch_timeout
                )
                engine = CDPEngine()
                await engine.connect(ws_url)
                await self._apply_permissions(engine)
                await self._resolve_stealth_ua(engine)
            except BaseException:
                launcher.terminate()
                raise
            self._launcher = launcher
            self._engine = engine

    async def _resolve_stealth_ua(self, engine: CDPEngine) -> None:
        if not self._stealth:
            return
        try:
            info = await engine.send("Browser.getVersion")
            real_ua = info.get("userAgent", "")
            self._stealth_ua = (
                real_ua.replace("HeadlessChrome/", "Chrome/") if real_ua else _STEALTH_UA
            )
        except Exception:
            logger.debug("Failed to resolve real UA for stealth mode", exc_info=True)
            self._stealth_ua = _STEALTH_UA

    async def _apply_permissions(self, engine: CDPEngine) -> None:
        for name, allowed in self._permissions.items():
            try:
                await engine.send(
                    "Browser.setPermission",
                    {
                        "permission": {"name": name},
                        "setting": "granted" if allowed else "denied",
                    },
                )
            except Exception:
                logger.debug("Failed to set permission %r", name, exc_info=True)

    async def open(self, url: str, **kwargs: str) -> Page:
        await self._connect()
        assert self._engine is not None

        url = _expand_macro(url, **kwargs)

        if not url.startswith(("http", "about:", "data:", "file:", "blob:")):
            url = "https://" + url

        enforce_navigation(self._policy, url)

        result = await self._engine.send("Target.createTarget", {"url": "about:blank"})
        target_id = result["targetId"]

        page_engine = CDPEngine()
        await page_engine.connect(self._page_ws_url(target_id))
        await self._apply_viewport(page_engine)
        if self._geolocation:
            await page_engine.send(
                "Emulation.setGeolocationOverride",
                {
                    "latitude": self._geolocation["latitude"],
                    "longitude": self._geolocation["longitude"],
                    "accuracy": self._geolocation.get("accuracy", 1),
                },
            )
        page = Page(
            engine=page_engine,
            trace=self.trace,
            target_id=target_id,
            safe=self._safe,
            closer=self._close_target,
            block_resources=self._block_resources,
            policy=self._policy,
            stealth_ua=self._stealth_ua,
        )
        self._pages.append(page)
        try:
            await page.goto(url)
        except BaseException:
            with contextlib.suppress(Exception):
                await asyncio.shield(asyncio.ensure_future(page.close()))
            raise
        return page

    async def _apply_viewport(self, engine: CDPEngine) -> None:
        vp = self._viewport
        await engine.send(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": vp["width"],
                "height": vp["height"],
                "deviceScaleFactor": vp["device_scale_factor"],
                "mobile": vp["mobile"],
            },
        )
        await engine.send("Emulation.setTouchEmulationEnabled", {"enabled": vp["touch"]})
        if vp["mobile"]:
            await engine.send("Network.setUserAgentOverride", {"userAgent": _MOBILE_UA})
        elif self._stealth_ua:
            await engine.send("Network.setUserAgentOverride", {"userAgent": self._stealth_ua})

    def _page_ws_url(self, target_id: str) -> str:
        if self._cdp_url:
            parts = urllib.parse.urlsplit(self._cdp_url)
            return urllib.parse.urlunsplit(
                (parts.scheme, parts.netloc, f"/devtools/page/{target_id}", parts.query, "")
            )
        return f"ws://localhost:{self._port}/devtools/page/{target_id}"

    async def _close_target(self, target_id: str) -> None:
        if self._engine:
            await self._engine.send("Target.closeTarget", {"targetId": target_id})
        self._pages = [p for p in self._pages if p._target_id != target_id]

    @property
    def pages(self) -> tuple[Page, ...]:
        return tuple(self._pages)

    def get_page(self, target_id: str) -> Page | None:
        for page in self._pages:
            if page._target_id == target_id:
                return page
        return None

    async def run(self, goal: str, url: str) -> RunResult:
        from nexus.browser.runner import Runner
        if self._llm is None:
            raise RuntimeError("Browser.run() requires an llm adapter")
        page = await self.open(url)
        runner = Runner(llm=self._llm, page=page, trace=self.trace)
        return await runner.run(goal)

    async def close(self) -> None:
        for page in list(self._pages):
            try:
                await page.close()
            except Exception:
                logger.debug("Failed to close tab %s", page._target_id, exc_info=True)
        self._pages.clear()
        try:
            if self._engine:
                await self._engine.disconnect()
        except Exception:
            logger.debug("Failed to disconnect the browser engine", exc_info=True)
        finally:
            self._engine = None
            if self._launcher:
                await self._launcher.aterminate()
                self._launcher = None

    @staticmethod
    def _origin_of(url: str) -> str | None:
        parts = urllib.parse.urlsplit(url)
        if not parts.scheme or not parts.netloc:
            return None
        return f"{parts.scheme}://{parts.netloc}"

    async def save_session(self, path: str) -> None:
        if not self._engine:
            raise RuntimeError("Browser is not connected. Use open() or async with first.")
        result = await self._engine.send("Storage.getCookies", {})
        cookies = result.get("cookies", [])

        origins: dict[str, dict[str, dict[str, str]]] = {}
        for page in self._pages:
            info = await self._engine.send(
                "Target.getTargetInfo", {"targetId": page._target_id}
            )
            origin = self._origin_of(info.get("targetInfo", {}).get("url", ""))
            if origin is None or origin in origins:
                continue
            local = await page._engine.send(
                "Runtime.evaluate",
                {
                    "expression": "JSON.stringify(Object.assign({}, window.localStorage))",
                    "returnByValue": True,
                },
            )
            raw = local.get("result", {}).get("value")
            if not raw:
                continue
            items = json.loads(raw)
            if items:
                origins[origin] = {"localStorage": items}

        def _write() -> None:
            fd = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600
            )
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump({"cookies": cookies, "origins": origins}, f, indent=2)

        await asyncio.to_thread(_write)

    async def load_session(self, path: str) -> None:
        if not self._engine:
            raise RuntimeError("Browser is not connected. Use open() or async with first.")

        def _read() -> Any:
            with Path(path).open() as f:
                data: Any = json.load(f)
                return data

        try:
            data = await asyncio.to_thread(_read)
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Session file not found: {path}") from e
        except json.JSONDecodeError as e:
            raise ValueError(f"Session file is not valid JSON: {path}") from e

        if isinstance(data, list):
            cookies: list[dict[str, Any]] = data
            origins: dict[str, dict[str, dict[str, str]]] = {}
        elif isinstance(data, dict):
            cookies = data.get("cookies", [])
            origins = data.get("origins", {})
        else:
            raise ValueError(
                f"Session file has an unrecognized shape: {path} "
                "(expected a cookie list or a {{cookies, origins}} object)"
            )

        if not isinstance(cookies, list):
            raise ValueError(f"Session file 'cookies' must be a list: {path}")
        if not isinstance(origins, dict):
            raise ValueError(f"Session file 'origins' must be an object: {path}")

        await self._engine.send("Storage.setCookies", {"cookies": cookies})

        for origin, storage in origins.items():
            if not isinstance(storage, dict):
                raise ValueError(
                    f"Session file 'origins[{origin!r}]' must be an object: {path}"
                )
            local_items = storage.get("localStorage", {})
            if not local_items:
                continue
            if not isinstance(local_items, dict):
                raise ValueError(
                    f"Session file 'origins[{origin!r}].localStorage' must be an "
                    f"object: {path}"
                )
            page = None
            for candidate in self._pages:
                info = await self._engine.send(
                    "Target.getTargetInfo", {"targetId": candidate._target_id}
                )
                if self._origin_of(info.get("targetInfo", {}).get("url", "")) == origin:
                    page = candidate
                    break
            opened_here = page is None
            if page is None:
                page = await self.open(origin)
            try:
                expr = "".join(
                    f"window.localStorage.setItem({json.dumps(k)}, {json.dumps(v)});"
                    for k, v in local_items.items()
                )
                await page._engine.send("Runtime.evaluate", {"expression": expr})
            finally:
                if opened_here:
                    await page.close()
