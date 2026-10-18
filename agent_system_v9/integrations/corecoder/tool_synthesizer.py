"""
CoreCoder Integration Module
Maps CoreCoder CLI to V9 DynamicToolRegistry tools
"""
import asyncio
import os
from dataclasses import dataclass
from typing import Any

from agent_system_v9.kernel.sandbox_isolator import SandboxIsolator
from agent_system_v9.memory.query_engine import QueryEngine
from agent_system_v9.tools.tool_registry import (
    DynamicToolRegistry,
    SandboxSpec,
    ToolCategory,
    ToolParameter,
)


@dataclass
class CoreCoderCommand:
    name: str
    description: str
    mode: str
    args_schema: dict[str, Any]
    sandbox_spec: SandboxSpec


CORECODER_COMMANDS = [
    CoreCoderCommand(
        name="corecoder_repl",
        description="Start CoreCoder REPL for interactive coding",
        mode="repl",
        args_schema={
            "type": "object",
            "properties": {
                "workspace": {"type": "string", "description": "Workspace directory"},
                "model": {"type": "string", "description": "Model to use"},
                "temperature": {"type": "number", "default": 0.7},
                "max_tokens": {"type": "integer", "default": 4096},
            },
            "required": ["workspace"],
        },
        sandbox_spec=SandboxSpec(
            image="python:3.11-slim",
            memory_limit="1g",
            cpu_limit="1.0",
            timeout_seconds=3600,
            network_enabled=True,
            volumes=["/workspace:/workspace"],
        ),
    ),
    CoreCoderCommand(
        name="corecoder_task",
        description="Execute CoreCoder one-shot task",
        mode="task",
        args_schema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Task prompt"},
                "workspace": {"type": "string", "description": "Workspace directory"},
                "model": {"type": "string", "description": "Model to use"},
                "temperature": {"type": "number", "default": 0.7},
                "max_tokens": {"type": "integer", "default": 4096},
                "auto_apply": {"type": "boolean", "default": True},
            },
            "required": ["prompt", "workspace"],
        },
        sandbox_spec=SandboxSpec(
            image="python:3.11-slim",
            memory_limit="1g",
            cpu_limit="1.0",
            timeout_seconds=600,
            network_enabled=True,
            volumes=["/workspace:/workspace"],
        ),
    ),
    CoreCoderCommand(
        name="corecoder_edit",
        description="Edit files using CoreCoder",
        mode="edit",
        args_schema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "File to edit"},
                "instruction": {"type": "string", "description": "Edit instruction"},
                "workspace": {"type": "string", "description": "Workspace directory"},
                "model": {"type": "string", "description": "Model to use"},
            },
            "required": ["file_path", "instruction", "workspace"],
        },
        sandbox_spec=SandboxSpec(
            image="python:3.11-slim",
            memory_limit="512m",
            cpu_limit="1.0",
            timeout_seconds=120,
            network_enabled=True,
            volumes=["/workspace:/workspace"],
        ),
    ),
    CoreCoderCommand(
        name="corecoder_test",
        description="Run tests with CoreCoder validation",
        mode="test",
        args_schema={
            "type": "object",
            "properties": {
                "test_path": {"type": "string", "description": "Test file or directory"},
                "workspace": {"type": "string", "description": "Workspace directory"},
                "model": {"type": "string", "description": "Model to use"},
            },
            "required": ["test_path", "workspace"],
        },
        sandbox_spec=SandboxSpec(
            image="python:3.11-slim",
            memory_limit="1g",
            cpu_limit="1.0",
            timeout_seconds=300,
            network_enabled=True,
            volumes=["/workspace:/workspace"],
        ),
    ),
]


class CoreCoderToolSynthesizer:
    def __init__(self, registry: DynamicToolRegistry, sandbox: SandboxIsolator, query_engine: QueryEngine):
        self.registry = registry
        self.sandbox = sandbox
        self.query_engine = query_engine
        self._registered = False

    def register_all(self) -> int:
        count = 0
        for cmd in CORECODER_COMMANDS:
            try:
                self._register_command(cmd)
                count += 1
            except Exception as e:
                print(f"Failed to register {cmd.name}: {e}")
        self._registered = True
        return count

    def _register_command(self, cmd: CoreCoderCommand):
        async def corecoder_wrapper(**kwargs) -> dict[str, Any]:
            workspace = kwargs.get("workspace", "/workspace")

            if cmd.mode == "repl":
                return await self._run_repl(kwargs, workspace)
            if cmd.mode == "task":
                return await self._run_task(kwargs, workspace)
            if cmd.mode == "edit":
                return await self._run_edit(kwargs, workspace)
            if cmd.mode == "test":
                return await self._run_test(kwargs, workspace)

            return {"error": f"Unknown mode: {cmd.mode}", "success": False}

        params = [
            ToolParameter(
                name=k,
                type=v.get("type", "string"),
                description=v.get("description", ""),
                required=k in cmd.args_schema.get("required", []),
                default=v.get("default"),
                enum=v.get("enum"),
            )
            for k, v in cmd.args_schema.get("properties", {}).items()
        ]

        self.registry.register(
            name=cmd.name,
            function=corecoder_wrapper,
            description=cmd.description,
            category=ToolCategory.CODE_GENERATION,
            parameters=params,
            sandbox_spec=cmd.sandbox_spec,
            tags=["corecoder", "code_generation", cmd.mode],
            metadata={"mode": cmd.mode},
        )

    async def _run_repl(self, kwargs: dict[str, Any], workspace: str) -> dict[str, Any]:
        return {"success": False, "error": "REPL mode not supported in tool context", "output": {}}

    async def _run_task(self, kwargs: dict[str, Any], workspace: str) -> dict[str, Any]:
        prompt = kwargs.get("prompt", "")
        model = kwargs.get("model", "gpt-4o")
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 4096)
        auto_apply = kwargs.get("auto_apply", True)

        cmd = [
            "corecoder",
            "-p", prompt,
            "--model", model,
            "--temperature", str(temperature),
            "--max-tokens", str(max_tokens),
        ]

        if auto_apply:
            cmd.append("--auto-apply")

        env = os.environ.copy()
        env["CORECODER_WORKSPACE"] = workspace

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workspace,
                env=env,
            )
            stdout, stderr = await proc.communicate()

            result = {
                "success": proc.returncode == 0,
                "output": stdout.decode(),
                "stderr": stderr.decode(),
                "returncode": proc.returncode,
            }

            if result["success"]:
                await self._ingest_result(kwargs, result)

            return result
        except Exception as e:
            return {"success": False, "error": str(e), "output": ""}

    async def _run_edit(self, kwargs: dict[str, Any], workspace: str) -> dict[str, Any]:
        file_path = kwargs.get("file_path", "")
        instruction = kwargs.get("instruction", "")
        model = kwargs.get("model", "gpt-4o")

        cmd = [
            "corecoder",
            "edit",
            "--file", file_path,
            "--instruction", instruction,
            "--model", model,
        ]

        env = os.environ.copy()
        env["CORECODER_WORKSPACE"] = workspace

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workspace,
                env=env,
            )
            stdout, stderr = await proc.communicate()

            return {
                "success": proc.returncode == 0,
                "output": stdout.decode(),
                "stderr": stderr.decode(),
                "returncode": proc.returncode,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "output": ""}

    async def _run_test(self, kwargs: dict[str, Any], workspace: str) -> dict[str, Any]:
        test_path = kwargs.get("test_path", "")
        model = kwargs.get("model", "gpt-4o")

        cmd = [
            "corecoder",
            "test",
            "--path", test_path,
            "--model", model,
        ]

        env = os.environ.copy()
        env["CORECODER_WORKSPACE"] = workspace

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workspace,
                env=env,
            )
            stdout, stderr = await proc.communicate()

            result = {
                "success": proc.returncode == 0,
                "output": stdout.decode(),
                "stderr": stderr.decode(),
                "returncode": proc.returncode,
            }

            if result["success"]:
                await self._ingest_test_result(kwargs, result)

            return result
        except Exception as e:
            return {"success": False, "error": str(e), "output": ""}

    async def _ingest_result(self, kwargs: dict[str, Any], result: dict[str, Any]):
        self.query_engine.ingest_corecoder_result(
            task=kwargs.get("prompt", ""),
            result={
                "success": result["success"],
                "output": result["output"],
                "files_modified": self._extract_modified_files(result["output"]),
            },
            source="corecoder_task",
        )

    async def _ingest_test_result(self, kwargs: dict[str, Any], result: dict[str, Any]):
        self.query_engine.ingest_corecoder_result(
            task=f"Test: {kwargs.get('test_path', '')}",
            result={
                "success": result["success"],
                "output": result["output"],
                "test_results": self._parse_test_output(result["output"]),
            },
            source="corecoder_test",
        )

    def _extract_modified_files(self, output: str) -> list[str]:
        import re
        files = re.findall(r'(?:modified|created|updated)\s+([^\s]+\.\w+)', output, re.IGNORECASE)
        return list(set(files))

    def _parse_test_output(self, output: str) -> dict[str, Any]:
        import re
        passed = len(re.findall(r'\bPASSED\b|\bpassed\b', output))
        failed = len(re.findall(r'\bFAILED\b|\bfailed\b', output))
        return {"passed": passed, "failed": failed, "total": passed + failed}


def register_corecoder_tools(
    registry: DynamicToolRegistry,
    sandbox: SandboxIsolator,
    query_engine: QueryEngine,
) -> int:
    synthesizer = CoreCoderToolSynthesizer(registry, sandbox, query_engine)
    return synthesizer.register_all()
