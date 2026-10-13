"""
Cybersec-Toolkit Integration - Security tools and modules for AGENT_SYSTEM_V9
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ToolConfig:
    """Configuration for a security tool."""
    name: str
    method: str  # apt, pipx, go, git, binary, cargo, gem, docker, source
    module: str  # blueteam, recon, web, networking, etc.
    url: str
    version: str = ""
    description: str = ""
    dependencies: list[str] = field(default_factory=list)
    install_args: list[str] = field(default_factory=list)
    verify_cmd: str = ""


class ToolManager:
    """
    Manages installation and execution of security tools.
    Integrates cybersec-toolkit's tools_config.json and module scripts.
    """

    def __init__(self, config_path: str | None = None):
        self.config_path = config_path or "/workspace/app/agent_system_v9/integrations/cybersec_toolkit/tools_config.json"
        self.tools: dict[str, ToolConfig] = {}
        self.modules: dict[str, list[str]] = {}
        self._load_config()

    def _load_config(self):
        """Load tools configuration."""
        try:
            with Path(self.config_path).open('r') as f:
                data = json.load(f)

            for tool_data in data:
                tool = ToolConfig(**tool_data)
                self.tools[tool.name] = tool

                if tool.module not in self.modules:
                    self.modules[tool.module] = []
                self.modules[tool.module].append(tool.name)

        except Exception as e:
            logger.error(f"Failed to load tools config: {e}")

    def get_tool(self, name: str) -> ToolConfig | None:
        """Get tool configuration."""
        return self.tools.get(name)

    def get_tools_by_module(self, module: str) -> list[ToolConfig]:
        """Get all tools in a module."""
        tool_names = self.modules.get(module, [])
        return [self.tools[name] for name in tool_names if name in self.tools]

    def get_all_modules(self) -> list[str]:
        """Get all module names."""
        return list(self.modules.keys())

    async def install_tool(self, name: str, force: bool = False) -> bool:
        """Install a tool."""
        tool = self.tools.get(name)
        if not tool:
            logger.error(f"Tool not found: {name}")
            return False

        if await self.is_installed(name) and not force:
            logger.info(f"Tool already installed: {name}")
            return True

        logger.info(f"Installing {name} via {tool.method}...")

        try:
            if tool.method == "apt":
                return await self._install_apt(tool)
            if tool.method == "pipx":
                return await self._install_pipx(tool)
            if tool.method == "go":
                return await self._install_go(tool)
            if tool.method == "git":
                return await self._install_git(tool)
            if tool.method == "binary":
                return await self._install_binary(tool)
            if tool.method == "cargo":
                return await self._install_cargo(tool)
            if tool.method == "gem":
                return await self._install_gem(tool)
            if tool.method == "docker":
                return await self._install_docker(tool)
            if tool.method == "source":
                return await self._install_source(tool)
            logger.error(f"Unknown install method: {tool.method}")
            return False
        except Exception as e:
            logger.error(f"Failed to install {name}: {e}")
            return False

    async def install_module(self, module: str, force: bool = False) -> dict[str, bool]:
        """Install all tools in a module."""
        results = {}
        tools = self.get_tools_by_module(module)

        for tool in tools:
            results[tool.name] = await self.install_tool(tool.name, force)

        return results

    async def is_installed(self, name: str) -> bool:
        """Check if tool is installed."""
        tool = self.tools.get(name)
        if not tool:
            return False

        verify_cmd = tool.verify_cmd or f"which {name}"
        try:
            proc = await asyncio.create_subprocess_shell(
                verify_cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await proc.communicate()
            return proc.returncode == 0
        except Exception:
            return False

    async def _install_apt(self, tool: ToolConfig) -> bool:
        """Install via apt."""
        cmd = ["apt-get", "update", "&&", "apt-get", "install", "-y", tool.name]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return proc.returncode == 0

    async def _install_pipx(self, tool: ToolConfig) -> bool:
        """Install via pipx."""
        cmd = ["pipx", "install", tool.name]
        if tool.install_args:
            cmd.extend(tool.install_args)
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return proc.returncode == 0

    async def _install_go(self, tool: ToolConfig) -> bool:
        """Install via go."""
        # Extract package from URL
        if tool.url.startswith("https://github.com/"):
            pkg = tool.url.replace("https://github.com/", "github.com/")
            cmd = ["go", "install", f"{pkg}@latest"]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            return proc.returncode == 0
        return False

    async def _install_git(self, tool: ToolConfig) -> bool:
        """Install via git clone."""
        install_dir = Path.home() / ".local" / "tools" / tool.name
        install_dir.parent.mkdir(parents=True, exist_ok=True)

        if install_dir.exists():
            import shutil
            shutil.rmtree(install_dir)

        cmd = ["git", "clone", tool.url, str(install_dir)]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()

        if proc.returncode == 0 and tool.install_args:
            # Run install script if provided
            for arg in tool.install_args:
                script = install_dir / arg
                if script.exists():
                    proc = await asyncio.create_subprocess_exec(
                        "bash", str(script),
                        cwd=str(install_dir),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await proc.communicate()

        return proc.returncode == 0

    async def _install_binary(self, tool: ToolConfig) -> bool:
        """Install binary from GitHub releases."""
        # This is a simplified version - real implementation would parse releases
        logger.warning(f"Binary install not fully implemented for {tool.name}")
        return False

    async def _install_cargo(self, tool: ToolConfig) -> bool:
        """Install via cargo."""
        # Extract crate name from URL
        if tool.url.startswith("https://crates.io/crates/"):
            crate = tool.url.replace("https://crates.io/crates/", "")
            cmd = ["cargo", "install", crate]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            return proc.returncode == 0
        return False

    async def _install_gem(self, tool: ToolConfig) -> bool:
        """Install via gem."""
        cmd = ["gem", "install", tool.name]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return proc.returncode == 0

    async def _install_docker(self, tool: ToolConfig) -> bool:
        """Pull docker image."""
        image = tool.url.replace("https://hub.docker.com/r/", "")
        cmd = ["docker", "pull", image]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return proc.returncode == 0

    async def _install_source(self, tool: ToolConfig) -> bool:
        """Install from source."""
        logger.warning(f"Source install not fully implemented for {tool.name}")
        return False

    async def execute_tool(self, name: str, args: list[str] = None,
                           input_data: str = None) -> dict[str, Any]:
        """Execute an installed tool."""
        tool = self.tools.get(name)
        if not tool:
            return {"success": False, "error": f"Tool not found: {name}"}

        if not await self.is_installed(name):
            return {"success": False, "error": f"Tool not installed: {name}"}

        cmd = [name]
        if args:
            cmd.extend(args)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE if input_data else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate(input_data.encode() if input_data else None)

            return {
                "success": proc.returncode == 0,
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
                "returncode": proc.returncode
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class ModuleRunner:
    """
    Runs cybersec-toolkit module scripts.
    """

    def __init__(self, modules_dir: str | None = None):
        self.modules_dir = Path(modules_dir or
            "/workspace/app/agent_system_v9/integrations/cybersec_toolkit/modules")
        self.scripts_dir = Path(
            "/workspace/app/agent_system_v9/integrations/cybersec_toolkit/scripts")
        self.lib_dir = Path(
            "/workspace/app/agent_system_v9/integrations/cybersec_toolkit/lib")

    def get_available_modules(self) -> list[str]:
        """Get list of available module scripts."""
        modules = []
        for f in self.modules_dir.glob("*.sh"):
            modules.append(f.stem)
        return modules

    def get_available_scripts(self) -> list[str]:
        """Get list of available utility scripts."""
        scripts = []
        for f in self.scripts_dir.glob("*.sh"):
            scripts.append(f.stem)
        for f in self.scripts_dir.glob("*.py"):
            scripts.append(f.stem)
        return scripts

    async def run_module(self, module: str, args: list[str] = None) -> dict[str, Any]:
        """Run a module script."""
        script = self.modules_dir / f"{module}.sh"
        if not script.exists():
            return {"success": False, "error": f"Module not found: {module}"}

        cmd = ["bash", str(script)]
        if args:
            cmd.extend(args)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            return {
                "success": proc.returncode == 0,
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
                "returncode": proc.returncode
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def run_script(self, script: str, args: list[str] = None) -> dict[str, Any]:
        """Run a utility script."""
        # Try .sh first, then .py
        script_path = self.scripts_dir / f"{script}.sh"
        if not script_path.exists():
            script_path = self.scripts_dir / f"{script}.py"

        if not script_path.exists():
            return {"success": False, "error": f"Script not found: {script}"}

        if script_path.suffix == ".py":
            cmd = ["python3", str(script_path)]
        else:
            cmd = ["bash", str(script_path)]

        if args:
            cmd.extend(args)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            return {
                "success": proc.returncode == 0,
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
                "returncode": proc.returncode
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class CybersecToolkitIntegration:
    """High-level integration for AGENT_SYSTEM_V9."""

    def __init__(self):
        self.tool_manager = ToolManager()
        self.module_runner = ModuleRunner()
        self._installed_cache: set[str] = set()

    async def ensure_module(self, module: str) -> dict[str, bool]:
        """Ensure all tools in a module are installed."""
        return await self.tool_manager.install_module(module)

    async def run_recon(self, target: str, modules: list[str] = None) -> dict[str, Any]:
        """Run reconnaissance modules."""
        results = {}
        target_modules = modules or ["recon", "networking", "web"]

        for module in target_modules:
            module_results = await self.tool_manager.install_module(module)
            results[module] = module_results

        return results

    async def run_blueteam_audit(self, target: str = "") -> dict[str, Any]:
        """Run blue team audit tools."""
        return await self.tool_manager.install_module("blueteam")

    async def run_forensics(self, target: str) -> dict[str, Any]:
        """Run forensics tools."""
        return await self.tool_manager.install_module("forensics")

    def get_tool_status(self) -> dict[str, dict[str, Any]]:
        """Get status of all tools."""
        status = {}
        for name, tool in self.tool_manager.tools.items():
            status[name] = {
                "module": tool.module,
                "method": tool.method,
                "installed": name in self._installed_cache
            }
        return status


_cybersec_integration: CybersecToolkitIntegration | None = None


def get_cybersec_toolkit_integration() -> CybersecToolkitIntegration:
    """Get global cybersec-toolkit integration."""
    global _cybersec_integration
    if _cybersec_integration is None:
        _cybersec_integration = CybersecToolkitIntegration()
    return _cybersec_integration
