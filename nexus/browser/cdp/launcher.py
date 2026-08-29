from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import subprocess
import tempfile
import weakref
from pathlib import Path
from typing import Any, cast

_STEALTH_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
)

_CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
]

_MACOS_APP = "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
_CACHED_CHROME_GLOBS = [
    f"~/Library/Caches/ms-playwright/chromium-*/chrome-mac*/{_MACOS_APP}",
    "~/Library/Caches/ms-playwright/chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
    "~/.cache/ms-playwright/chromium-*/chrome-linux/chrome",
    "~/.cache/puppeteer/chrome/*/chrome-linux64/chrome",
    f"~/.cache/puppeteer/chrome/*/chrome-mac*/{_MACOS_APP}",
]


_DEFAULT_LAUNCH_TIMEOUT = 10.0
_REAP_WAIT = 1.0
_STDERR_TAIL_BYTES = 4000


def default_launch_timeout() -> float:
    """Seconds to wait for Chrome's DevTools port, from NEXUS_BROWSER_CHROME_LAUNCH_TIMEOUT
    (with backward-compatible GRIP_CHROME_LAUNCH_TIMEOUT alias)."""
    for env_key in ("NEXUS_BROWSER_CHROME_LAUNCH_TIMEOUT", "GRIP_CHROME_LAUNCH_TIMEOUT"):
        raw = os.environ.get(env_key)
        if raw:
            try:
                value = float(raw)
                return value if value > 0 else _DEFAULT_LAUNCH_TIMEOUT
            except ValueError:
                return _DEFAULT_LAUNCH_TIMEOUT
    return _DEFAULT_LAUNCH_TIMEOUT


def _find_cached_chrome() -> str | None:
    for pattern in _CACHED_CHROME_GLOBS:
        expanded = Path(pattern).expanduser()
        root = Path(expanded.anchor)
        matches = sorted(str(p) for p in root.glob(str(expanded.relative_to(root))))
        if matches:
            return matches[-1]
    return None


def find_chrome() -> str | None:
    for env_key in ("NEXUS_CHROME_EXECUTABLE", "CHROME_EXECUTABLE"):
        if (exe := os.environ.get(env_key)) and Path(exe).exists():
            return exe
    for candidate in _CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    for name in ("google-chrome", "chromium", "chromium-browser"):
        if found := shutil.which(name):
            return found
    return _find_cached_chrome()


class ChromeLauncher:
    def __init__(
        self,
        user_data_dir: str | None = None,
        launch_timeout: float | None = None,
    ) -> None:
        exe = find_chrome()
        if not exe:
            raise RuntimeError(
                "Chrome/Chromium not found. Install Chrome or set NEXUS_CHROME_EXECUTABLE."
            )
        self.executable = exe
        self.port: int = 0
        self.launch_timeout = (
            launch_timeout if launch_timeout is not None else default_launch_timeout()
        )
        self._owns_user_data_dir = user_data_dir is None
        self._state: dict[str, Any] = {
            "process": None,
            "stderr_path": None,
            "user_data_dir": user_data_dir,
            "owns_user_data_dir": self._owns_user_data_dir,
        }
        self._finalizer = weakref.finalize(self, ChromeLauncher._reap, self._state)

    @property
    def _process(self) -> subprocess.Popen[bytes] | None:
        return cast("subprocess.Popen[bytes] | None", self._state["process"])

    @_process.setter
    def _process(self, value: subprocess.Popen[bytes] | None) -> None:
        self._state["process"] = value

    @property
    def _stderr_path(self) -> str | None:
        return cast("str | None", self._state["stderr_path"])

    @_stderr_path.setter
    def _stderr_path(self, value: str | None) -> None:
        self._state["stderr_path"] = value

    @property
    def _user_data_dir(self) -> str | None:
        return cast("str | None", self._state["user_data_dir"])

    @_user_data_dir.setter
    def _user_data_dir(self, value: str | None) -> None:
        self._state["user_data_dir"] = value

    def launch(
        self,
        headless: bool = True,
        proxy: str | None = None,
        stealth: bool = False,
    ) -> int:
        if self._owns_user_data_dir:
            self._user_data_dir = tempfile.mkdtemp(prefix="nexus_chrome_")
        else:
            assert self._user_data_dir is not None
            Path(self._user_data_dir).mkdir(parents=True, exist_ok=True)
            Path(self._user_data_dir, "DevToolsActivePort").unlink(missing_ok=True)
        args = [
            self.executable,
            "--remote-debugging-port=0",
            f"--user-data-dir={self._user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
        ]
        if headless:
            args.append("--headless=new")
        if proxy:
            args.append(f"--proxy-server={proxy}")
        if stealth:
            args.append("--disable-blink-features=AutomationControlled")
        stderr_fd, self._stderr_path = tempfile.mkstemp(prefix="nexus_chrome_stderr_")
        try:
            self._process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=stderr_fd,
            )
        finally:
            os.close(stderr_fd)
        try:
            self.port = self._read_port()
        except BaseException:
            self.terminate()
            raise
        return self.port

    def _stderr_tail(self) -> str:
        if not self._stderr_path:
            return ""
        try:
            data = Path(self._stderr_path).read_bytes()
        except OSError:
            return ""
        return data[-_STDERR_TAIL_BYTES:].decode("utf-8", "replace").strip()

    def _process_state(self) -> str:
        if self._process is None:
            return "process was never started"
        try:
            code = self._process.wait(timeout=_REAP_WAIT)
        except subprocess.TimeoutExpired:
            return "process still running"
        return f"process exited with code {code}"

    def _read_port(self) -> int:
        import time
        assert self._user_data_dir is not None
        port_file = Path(self._user_data_dir) / "DevToolsActivePort"
        deadline = time.monotonic() + self.launch_timeout

        def _port_now() -> int | None:
            if not port_file.exists():
                return None
            first_line = port_file.read_text().strip().split("\n")[0].strip()
            return int(first_line) if first_line.isdigit() else None

        died = False
        while time.monotonic() < deadline:
            if (port := _port_now()) is not None:
                return port
            if self._process is not None and self._process.poll() is not None:
                if (port := _port_now()) is not None:
                    return port
                died = True
                break
            time.sleep(0.05)
        state = self._process_state()
        stderr = self._stderr_tail()
        waited = (
            "Chrome died before writing it"
            if died
            else f"waited {self.launch_timeout:g}s"
        )
        raise RuntimeError(
            f"Chrome DevTools port never appeared — {waited} ({state}).\n"
            f"  executable: {self.executable}\n"
            f"  port file:  {port_file} (exists={port_file.exists()})\n"
            f"  chrome stderr: {stderr or '<empty>'}\n"
            "Raise NEXUS_BROWSER_CHROME_LAUNCH_TIMEOUT if the machine is just slow."
        )

    async def aterminate(self) -> None:
        await asyncio.to_thread(self.terminate)

    def terminate(self) -> None:
        self._reap(self._state)

    @staticmethod
    def _reap(state: dict[str, Any]) -> None:
        process = state["process"]
        if process:
            try:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    with contextlib.suppress(subprocess.TimeoutExpired):
                        process.wait(timeout=5)
            finally:
                state["process"] = None
        stderr_path = state["stderr_path"]
        if stderr_path:
            try:
                Path(stderr_path).unlink(missing_ok=True)
            finally:
                state["stderr_path"] = None
        user_data_dir = state["user_data_dir"]
        if user_data_dir and state["owns_user_data_dir"]:
            try:
                shutil.rmtree(user_data_dir, ignore_errors=True)
            finally:
                state["user_data_dir"] = None
