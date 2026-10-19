"""
Coding Excellence - core-native generate → test → fix loop.

Builds on existing V9 primitives (DynamicToolRegistry, SandboxIsolator,
WorkspaceManager) without external CLIs. Registers file I/O and test-runner
tools plus a `code_solve` tool that iterates generation/test/fix.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_system_v9.kernel.sandbox_isolator import SandboxIsolator
from agent_system_v9.workspace.workspace_manager import WorkspaceManager
from agent_system_v9.tools.tool_registry import (
    DynamicToolRegistry,
    ToolCategory,
    ToolParameter,
)

try:
    from agent_system_v9.context.context_window import ContextWindow
except Exception:
    ContextWindow = None  # type: ignore

try:
    from agent_system_v9.prompt.dynamic_assembler import get_prompt_assembler
except Exception:
    get_prompt_assembler = None  # type: ignore

try:
    from agent_system_v9.providers.registry import ProviderRegistry
except Exception:
    ProviderRegistry = None  # type: ignore


@dataclass
class CodeResult:
    success: bool
    task: str
    workspace: str
    files_modified: list[str] = field(default_factory=list)
    test_passed: bool = False
    test_output: str = ""
    iterations: int = 0
    error: str | None = None


class CodingAgent:
    """Generate → test → fix coding loop using V9 core primitives."""

    def __init__(
        self,
        registry: DynamicToolRegistry | None = None,
        sandbox: SandboxIsolator | None = None,
        workspace_manager: WorkspaceManager | None = None,
        max_iterations: int = 5,
        context_window=None,
        prompt_assembler=None,
        provider_registry=None,
    ):
        self.registry = registry or DynamicToolRegistry.get_instance()
        self.sandbox = sandbox or SandboxIsolator()
        self.workspace_manager = workspace_manager or WorkspaceManager()
        self.max_iterations = max_iterations
        self.context_window = context_window
        self.prompt_assembler = prompt_assembler
        self.provider_registry = provider_registry
        self._tools_registered = False

    def _ensure_tools(self):
        if self._tools_registered:
            return
        register_core_code_tools(self.registry, self.sandbox)
        self._tools_registered = True

    async def solve(self, task: str, workspace: str | None = None) -> CodeResult:
        self._ensure_tools()
        if workspace is None:
            try:
                workspace = self.workspace_manager.create_workspace("code_task")
            except Exception:
                workspace = tempfile.mkdtemp(prefix="v9_code_")
        Path(workspace).mkdir(parents=True, exist_ok=True)

        if self.context_window is not None:
            try:
                self.context_window.append("user", task)
            except Exception:
                pass

        last_error: str | None = None
        test_output = ""
        files_modified: list[str] = []

        for iteration in range(1, self.max_iterations + 1):
            prompt = self._build_prompt(task, workspace, last_error, iteration)
            result = await self._generate(prompt, workspace, last_error)
            files_modified = result.get("files_modified", [])

            test_result = await self.registry.execute(
                "run_tests",
                {"cwd": workspace, "timeout": 120},
                sandbox=True,
            )
            test_output = str(test_result.get("output", ""))
            test_passed = bool(test_result.get("success", False))

            if self.context_window is not None:
                try:
                    self.context_window.append("assistant", test_output[:2000])
                except Exception:
                    pass

            if test_passed:
                return CodeResult(
                    success=True,
                    task=task,
                    workspace=workspace,
                    files_modified=files_modified,
                    test_passed=True,
                    test_output=test_output,
                    iterations=iteration,
                )

            last_error = test_result.get("error", test_output)
            if last_error is None:
                last_error = test_output
            if self.context_window is not None:
                try:
                    self.context_window.append("user", f"Test failure: {str(last_error)[:1000]}")
                except Exception:
                    pass

        return CodeResult(
            success=False,
            task=task,
            workspace=workspace,
            files_modified=files_modified,
            test_passed=False,
            test_output=test_output,
            iterations=self.max_iterations,
            error=last_error,
        )

    def _build_prompt(
        self, task: str, workspace: str, last_error: str | None, iteration: int
    ) -> str:
        memory = ""
        if self.context_window is not None:
            try:
                msgs = self.context_window.get_messages_for_model()
                memory = "\n".join(m.get("content", "") for m in msgs if isinstance(m, dict))
            except Exception:
                memory = ""
        base = (
            f"Task: {task}\nWorkspace: {workspace}\n"
            "Write clean Python files under the workspace. "
            "Prefer standard-library-only code unless requirements.txt is present.\n"
        )
        if memory:
            base += f"Context memory:\n{memory}\n"
        if iteration == 1:
            return base + "Return a summary of files changed."
        return (
            base
            + f"Previous attempt failed:\n{last_error}\n"
            "Fix the code so tests pass. Return a summary of files changed."
        )

    async def _generate(self, prompt: str, workspace: str, last_error: str | None = None) -> dict[str, Any]:
        # Try LLM provider if available
        provider = None
        if self.provider_registry is not None:
            try:
                healthy = self.provider_registry.get_healthy()
                if healthy:
                    provider = list(healthy.values())[0]
            except Exception:
                provider = None
        if provider is not None:
            try:
                from agent_system_v9.prompt.dynamic_assembler import AssemblyContext
                messages = [{"role": "user", "content": prompt}]
                if self.prompt_assembler is not None:
                    try:
                        ctx = AssemblyContext(memory_context={})
                        assembled = self.prompt_assembler.assemble(ctx)
                        messages = [{"role": "system", "content": assembled}, {"role": "user", "content": prompt}]
                    except Exception:
                        pass
                resp = await provider.chat(messages)
                content = getattr(resp, "content", None) or str(resp)
                starter = os.path.join(workspace, "solution.py")
                Path(starter).write_text(content, encoding="utf-8")
                return {"files_modified": [starter], "output": "wrote llm solution"}
            except Exception:
                pass

        # Fallback deterministic starter
        starter = os.path.join(workspace, "solution.py")
        Path(starter).write_text(
            'def answer() -> int:\n    """Placeholder solution."""\n    return 0\n',
            encoding="utf-8",
        )
        return {"files_modified": [starter], "output": "wrote starter"}


async def solve_code(task: str, workspace: str | None = None) -> CodeResult:
    agent = CodingAgent()
    return await agent.solve(task, workspace)


def register_core_code_tools(
    registry: DynamicToolRegistry | None = None,
    sandbox: SandboxIsolator | None = None,
) -> dict[str, int]:
    registry = registry or DynamicToolRegistry.get_instance()
    sandbox = sandbox or SandboxIsolator()

    async def file_read(**kwargs) -> dict[str, Any]:
        path = Path(kwargs.get("path", ""))
        if not path.exists():
            return {"success": False, "error": f"not found: {path}"}
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            return {"success": True, "content": content, "lines": len(content.splitlines())}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def file_write(**kwargs) -> dict[str, Any]:
        path = Path(kwargs.get("path", ""))
        content = kwargs.get("content", "")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return {"success": True, "path": str(path), "size": len(content)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def file_list(**kwargs) -> dict[str, Any]:
        path = Path(kwargs.get("path", "."))
        recursive = kwargs.get("recursive", False)
        try:
            if recursive:
                files = [str(p) for p in path.rglob("*") if p.is_file()]
            else:
                files = [str(p) for p in path.iterdir() if p.is_file()]
            return {"success": True, "files": sorted(files)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def run_tests(**kwargs) -> dict[str, Any]:
        cwd = kwargs.get("cwd", ".")
        timeout = float(kwargs.get("timeout", 120))
        try:
            proc = await asyncio.create_subprocess_exec(
                "python3", "-m", "pytest", "-q", ".",
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy(),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return {
                "success": proc.returncode == 0,
                "output": (stdout + stderr).decode(errors="replace"),
                "returncode": proc.returncode,
            }
        except asyncio.TimeoutError:
            return {"success": False, "error": "timeout", "returncode": -1}
        except FileNotFoundError:
            return {"success": False, "error": "pytest not found", "returncode": -1}
        except Exception as e:
            return {"success": False, "error": str(e), "returncode": -1}

    registry.register(
        "file_read", file_read, "Read text file", ToolCategory.FILE_OPERATION,
        parameters=[ToolParameter("path", "string", "File path", required=True)],
        tags=["io", "core"],
    )
    registry.register(
        "file_write", file_write, "Write text file", ToolCategory.FILE_OPERATION,
        parameters=[
            ToolParameter("path", "string", "File path", required=True),
            ToolParameter("content", "string", "Content", required=True),
        ],
        tags=["io", "core"],
    )
    registry.register(
        "file_list", file_list, "List files", ToolCategory.FILE_OPERATION,
        parameters=[
            ToolParameter("path", "string", "Directory", required=False, default="."),
            ToolParameter("recursive", "boolean", "Recursive", required=False, default=False),
        ],
        tags=["io", "core"],
    )
    registry.register(
        "run_tests", run_tests, "Run pytest", ToolCategory.CODE_GENERATION,
        parameters=[
            ToolParameter("cwd", "string", "Working dir", required=False, default="."),
            ToolParameter("timeout", "number", "Timeout s", required=False, default=120),
        ],
        tags=["test", "core"],
    )

    return {"file_read": 1, "file_write": 1, "file_list": 1, "run_tests": 1}


def register_coding_tools(
    registry: DynamicToolRegistry | None = None,
    sandbox: SandboxIsolator | None = None,
    workspace_manager: WorkspaceManager | None = None,
) -> int:
    registry = registry or DynamicToolRegistry.get_instance()
    sandbox = sandbox or SandboxIsolator()
    workspace_manager = workspace_manager or WorkspaceManager()

    async def code_solve_wrapper(**kwargs) -> dict[str, Any]:
        agent = CodingAgent(registry, sandbox, workspace_manager)
        result = await agent.solve(kwargs.get("task", ""), kwargs.get("workspace"))
        return {
            "success": result.success,
            "task": result.task,
            "workspace": result.workspace,
            "files_modified": result.files_modified,
            "test_passed": result.test_passed,
            "test_output": result.test_output,
            "iterations": result.iterations,
            "error": result.error,
        }

    registry.register(
        name="code_solve",
        function=code_solve_wrapper,
        description="Generate → test → fix coding loop using V9 core primitives",
        category=ToolCategory.CODE_GENERATION,
        parameters=[
            ToolParameter("task", "string", "Coding task to solve", required=True),
            ToolParameter("workspace", "string", "Workspace directory", required=False),
        ],
        tags=["coding", "core"],
    )
    return 1
