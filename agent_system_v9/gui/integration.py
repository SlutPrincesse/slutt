"""
GUI Integration - Wrapper for RedAmon Next.js webapp
Provides Python interface to launch and manage the web UI
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class WebappConfig:
    """Configuration for webapp."""
    host: str = "0.0.0.0"
    port: int = 3000
    webapp_dir: str = ""
    env: dict = None

    def __post_init__(self):
        if self.env is None:
            self.env = os.environ.copy()


class WebappManager:
    """Manages the RedAmon Next.js webapp process."""

    def __init__(self, config: WebappConfig | None = None):
        self.config = config or WebappConfig()
        self._process: subprocess.Popen | None = None
        self._running = False

        # Try to find webapp directory
        if not self.config.webapp_dir:
            possible_paths = [
                Path(__file__).parent.parent.parent / "integrations" / "redamon" / "webapp",
                Path("/workspace/app/agent_system_v9/integrations/redamon/webapp"),
                Path("/tmp/repo_ingest/redamon/webapp"),
            ]
            for path in possible_paths:
                if path.exists() and (path / "package.json").exists():
                    self.config.webapp_dir = str(path)
                    break

    @property
    def running(self) -> bool:
        return self._running and self._process is not None and self._process.poll() is None

    @property
    def url(self) -> str:
        return f"http://{self.config.host}:{self.config.port}"

    async def start(self, dev: bool = True) -> bool:
        """Start the webapp."""
        if self.running:
            logger.info("Webapp already running")
            return True

        if not self.config.webapp_dir:
            logger.error("Webapp directory not found")
            return False

        webapp_path = Path(self.config.webapp_dir)
        package_json = webapp_path / "package.json"

        if not package_json.exists():
            logger.error(f"package.json not found in {webapp_path}")
            return False

        # Check if dependencies installed
        node_modules = webapp_path / "node_modules"
        if not node_modules.exists():
            logger.info("Installing npm dependencies...")
            install_proc = await asyncio.create_subprocess_exec(
                "npm", "install",
                cwd=webapp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.config.env
            )
            await install_proc.communicate()
            if install_proc.returncode != 0:
                logger.error("npm install failed")
                return False

        # Start the webapp
        cmd = ["npm", "run", "dev"] if dev else ["npm", "run", "start"]

        logger.info(f"Starting webapp on {self.url}")

        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=webapp_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.config.env
        )

        self._running = True

        # Give it time to start
        await asyncio.sleep(3)

        if self._process.poll() is not None:
            stdout, stderr = await self._process.communicate()
            logger.error(f"Webapp failed to start: {stderr.decode()}")
            self._running = False
            return False

        logger.info(f"Webapp running at {self.url}")
        return True

    async def stop(self):
        """Stop the webapp."""
        if self._process and self._process.poll() is None:
            logger.info("Stopping webapp...")
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=10)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()

        self._running = False
        self._process = None
        logger.info("Webapp stopped")

    async def restart(self, dev: bool = True):
        """Restart the webapp."""
        await self.stop()
        await asyncio.sleep(1)
        await self.start(dev)

    def get_status(self) -> dict:
        """Get webapp status."""
        return {
            "running": self.running,
            "url": self.url if self.running else None,
            "pid": self._process.pid if self._process else None,
            "webapp_dir": self.config.webapp_dir
        }


class GUIIntegration:
    """High-level GUI integration for AGENT_SYSTEM_V9."""

    def __init__(self):
        self.webapp_manager = WebappManager()
        self._tui_task: asyncio.Task | None = None

    async def start_webapp(self, dev: bool = True) -> bool:
        """Start the web UI."""
        return await self.webapp_manager.start(dev)

    async def stop_webapp(self):
        """Stop the web UI."""
        await self.webapp_manager.stop()

    async def start_tui(self):
        """Start the TUI in background."""
        from agent_system_v9.tui import run_tui

        # Run TUI in executor to avoid blocking
        loop = asyncio.get_event_loop()
        self._tui_task = loop.run_in_executor(None, run_tui)
        return self._tui_task

    def get_status(self) -> dict:
        """Get overall GUI status."""
        return {
            "webapp": self.webapp_manager.get_status(),
            "tui_running": self._tui_task is not None and not self._tui_task.done()
        }


_webapp_manager: WebappManager | None = None
_gui_integration: GUIIntegration | None = None


def get_webapp_manager() -> WebappManager:
    """Get global webapp manager."""
    global _webapp_manager
    if _webapp_manager is None:
        _webapp_manager = WebappManager()
    return _webapp_manager


def get_gui_integration() -> GUIIntegration:
    """Get global GUI integration."""
    global _gui_integration
    if _gui_integration is None:
        _gui_integration = GUIIntegration()
    return _gui_integration


async def run_with_gui(dev: bool = True, tui: bool = False):
    """Run AGENT_SYSTEM_V9 with GUI and optionally TUI."""
    gui = get_gui_integration()

    # Start webapp
    await gui.start_webapp(dev)

    # Optionally start TUI
    if tui:
        await gui.start_tui()

    try:
        # Keep running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await gui.stop_webapp()


if __name__ == "__main__":
    import sys

    async def main():
        dev = "--prod" not in sys.argv
        tui = "--tui" in sys.argv
        await run_with_gui(dev=dev, tui=tui)

    asyncio.run(main())
