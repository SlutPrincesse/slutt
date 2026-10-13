"""
Ablation Integration Module
Maps Ablation CLI commands to V9 DynamicToolRegistry tools
"""
import asyncio
import json
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
class AblationCommand:
    name: str
    description: str
    subcommand: str
    args_schema: dict[str, Any]
    sandbox_spec: SandboxSpec
    output_parser: str = "json"


ABLATION_COMMANDS = [
    AblationCommand(
        name="ablation_lift",
        description="Lift binary to intermediate representation (IR)",
        subcommand="lift",
        args_schema={
            "type": "object",
            "properties": {
                "binary_path": {"type": "string", "description": "Path to binary file"},
                "output_format": {"type": "string", "enum": ["json", "protobuf", "text"], "default": "json"},
                "architecture": {"type": "string", "description": "Target architecture (auto-detect if omitted)"},
                "entry_point": {"type": "string", "description": "Entry point address or symbol"},
            },
            "required": ["binary_path"],
        },
        sandbox_spec=SandboxSpec(
            image="ablation-tool/ablation:latest",
            memory_limit="2g",
            cpu_limit="2.0",
            timeout_seconds=300,
            network_enabled=False,
        ),
    ),
    AblationCommand(
        name="ablation_taint",
        description="Perform taint analysis on binary",
        subcommand="taint",
        args_schema={
            "type": "object",
            "properties": {
                "binary_path": {"type": "string", "description": "Path to binary file"},
                "source": {"type": "string", "description": "Taint source (e.g., 'argv', 'stdin', 'network')"},
                "sink": {"type": "string", "description": "Taint sink to track"},
                "output_format": {"type": "string", "enum": ["json", "graphviz"], "default": "json"},
                "max_depth": {"type": "integer", "default": 100},
            },
            "required": ["binary_path", "source"],
        },
        sandbox_spec=SandboxSpec(
            image="ablation-tool/ablation:latest",
            memory_limit="2g",
            cpu_limit="2.0",
            timeout_seconds=300,
            network_enabled=False,
        ),
    ),
    AblationCommand(
        name="ablation_search",
        description="Search for patterns in binary",
        subcommand="search",
        args_schema={
            "type": "object",
            "properties": {
                "binary_path": {"type": "string", "description": "Path to binary file"},
                "pattern": {"type": "string", "description": "Search pattern (regex or bytes)"},
                "pattern_type": {"type": "string", "enum": ["regex", "bytes", "yaml"], "default": "regex"},
                "output_format": {"type": "string", "enum": ["json", "text"], "default": "json"},
            },
            "required": ["binary_path", "pattern"],
        },
        sandbox_spec=SandboxSpec(
            image="ablation-tool/ablation:latest",
            memory_limit="2g",
            cpu_limit="2.0",
            timeout_seconds=120,
            network_enabled=False,
        ),
    ),
    AblationCommand(
        name="ablation_crypto",
        description="Identify cryptographic constants and algorithms",
        subcommand="crypto",
        args_schema={
            "type": "object",
            "properties": {
                "binary_path": {"type": "string", "description": "Path to binary file"},
                "output_format": {"type": "string", "enum": ["json", "text"], "default": "json"},
                "deep_scan": {"type": "boolean", "default": False},
            },
            "required": ["binary_path"],
        },
        sandbox_spec=SandboxSpec(
            image="ablation-tool/ablation:latest",
            memory_limit="2g",
            cpu_limit="2.0",
            timeout_seconds=180,
            network_enabled=False,
        ),
    ),
    AblationCommand(
        name="ablation_decompile",
        description="Decompile functions to pseudo-code",
        subcommand="decompile",
        args_schema={
            "type": "object",
            "properties": {
                "binary_path": {"type": "string", "description": "Path to binary file"},
                "function_address": {"type": "string", "description": "Function address or name"},
                "output_format": {"type": "string", "enum": ["json", "c", "pseudocode"], "default": "json"},
            },
            "required": ["binary_path"],
        },
        sandbox_spec=SandboxSpec(
            image="ablation-tool/ablation:latest",
            memory_limit="2g",
            cpu_limit="2.0",
            timeout_seconds=180,
            network_enabled=False,
        ),
    ),
    AblationCommand(
        name="ablation_diff",
        description="Compare two binaries",
        subcommand="diff",
        args_schema={
            "type": "object",
            "properties": {
                "binary1": {"type": "string", "description": "First binary path"},
                "binary2": {"type": "string", "description": "Second binary path"},
                "output_format": {"type": "string", "enum": ["json", "html"], "default": "json"},
            },
            "required": ["binary1", "binary2"],
        },
        sandbox_spec=SandboxSpec(
            image="ablation-tool/ablation:latest",
            memory_limit="2g",
            cpu_limit="2.0",
            timeout_seconds=300,
            network_enabled=False,
        ),
    ),
    AblationCommand(
        name="ablation_firmware",
        description="Analyze firmware images",
        subcommand="firmware",
        args_schema={
            "type": "object",
            "properties": {
                "firmware_path": {"type": "string", "description": "Path to firmware image"},
                "analysis_type": {"type": "string", "enum": ["full", "filesystem", "kernel", "bootloader"], "default": "full"},
                "output_format": {"type": "string", "enum": ["json", "tar"], "default": "json"},
            },
            "required": ["firmware_path"],
        },
        sandbox_spec=SandboxSpec(
            image="ablation-tool/ablation:latest",
            memory_limit="4g",
            cpu_limit="4.0",
            timeout_seconds=600,
            network_enabled=False,
        ),
    ),
    AblationCommand(
        name="ablation_mcp_scan",
        description="Scan for MCP (Model Context Protocol) vulnerabilities",
        subcommand="mcp-scan",
        args_schema={
            "type": "object",
            "properties": {
                "target_path": {"type": "string", "description": "Path to scan"},
                "output_format": {"type": "string", "enum": ["json", "sarif"], "default": "json"},
            },
            "required": ["target_path"],
        },
        sandbox_spec=SandboxSpec(
            image="ablation-tool/ablation:latest",
            memory_limit="2g",
            cpu_limit="2.0",
            timeout_seconds=180,
            network_enabled=False,
        ),
    ),
]


class AblationToolSynthesizer:
    def __init__(self, registry: DynamicToolRegistry, sandbox: SandboxIsolator, query_engine: QueryEngine):
        self.registry = registry
        self.sandbox = sandbox
        self.query_engine = query_engine
        self._registered = False

    def register_all(self) -> int:
        count = 0
        for cmd in ABLATION_COMMANDS:
            try:
                self._register_command(cmd)
                count += 1
            except Exception as e:
                print(f"Failed to register {cmd.name}: {e}")
        self._registered = True
        return count

    def _register_command(self, cmd: AblationCommand):
        async def ablation_wrapper(**kwargs) -> dict[str, Any]:
            binary_path = kwargs.get("binary_path") or kwargs.get("firmware_path") or kwargs.get("target_path") or kwargs.get("binary1")
            if not binary_path:
                return {"error": "binary_path required", "success": False}

            args = [cmd.subcommand]

            for key, value in kwargs.items():
                if key in ("binary_path", "firmware_path", "target_path", "binary1", "binary2"):
                    continue
                if value is not None:
                    args.extend([f"--{key.replace('_', '-')}", str(value)])

            args.append(binary_path)
            if "binary2" in kwargs:
                args.append(kwargs["binary2"])

            result = await self.sandbox.execute_tool(
                tool_name=cmd.name,
                func=self._run_ablation,
                args={"args": args, "binary_path": binary_path},
                spec=cmd.sandbox_spec.__dict__,
            )

            if result.get("success"):
                await self._ingest_findings(cmd.name, result.get("output", {}), binary_path)

            return result

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
            function=ablation_wrapper,
            description=cmd.description,
            category=ToolCategory.ANALYSIS,
            parameters=params,
            sandbox_spec=cmd.sandbox_spec,
            tags=["ablation", "reverse_engineering", cmd.subcommand],
            metadata={"subcommand": cmd.subcommand, "output_parser": cmd.output_parser},
        )

    async def _run_ablation(self, args: list[str], binary_path: str) -> dict[str, Any]:
        try:
            cmd = ["ablation"] + args
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            return {
                "success": proc.returncode == 0,
                "output": json.loads(stdout.decode()) if stdout else {},
                "stderr": stderr.decode(),
                "returncode": proc.returncode,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "output": {}}

    async def _ingest_findings(self, tool_name: str, output: dict[str, Any], binary_path: str):
        findings = self._parse_output(tool_name, output)
        if findings:
            self.query_engine.ingest_ablation_findings(findings, source=f"ablation_{tool_name}")

    def _parse_output(self, tool_name: str, output: dict[str, Any]) -> list[dict[str, Any]]:
        findings = []

        if "taint" in tool_name and "taint_paths" in output:
            for path in output["taint_paths"]:
                findings.append({
                    "type": "taint_path",
                    "source": path.get("source"),
                    "sink": path.get("sink"),
                    "path": path.get("instructions", []),
                    "confidence": path.get("confidence", 0.8),
                    "location": {"file": path.get("binary"), "address": path.get("address")},
                })

        elif "crypto" in tool_name and "findings" in output:
            for finding in output["findings"]:
                findings.append({
                    "type": "crypto_finding",
                    "algorithm": finding.get("algorithm"),
                    "constants": finding.get("constants", []),
                    "location": {"file": finding.get("file"), "address": finding.get("address")},
                    "confidence": finding.get("confidence", 0.9),
                })

        elif "search" in tool_name and "matches" in output:
            for match in output["matches"]:
                findings.append({
                    "type": "pattern_match",
                    "pattern": match.get("pattern"),
                    "location": {"file": match.get("file"), "offset": match.get("offset")},
                    "context": match.get("context", ""),
                    "confidence": 0.7,
                })

        elif "decompile" in tool_name and "functions" in output:
            for func in output["functions"]:
                findings.append({
                    "type": "decompiled_function",
                    "name": func.get("name"),
                    "address": func.get("address"),
                    "pseudocode": func.get("pseudocode"),
                    "location": {"file": func.get("binary"), "address": func.get("address")},
                    "confidence": 0.8,
                })

        return findings


async def register_ablation_tools(
    registry: DynamicToolRegistry,
    sandbox: SandboxIsolator,
    query_engine: QueryEngine,
) -> int:
    synthesizer = AblationToolSynthesizer(registry, sandbox, query_engine)
    return synthesizer.register_all()
