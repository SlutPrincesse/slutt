"""
Integration tests for Ablation and CoreCoder plugin registration.
"""
import pytest

from agent_system_v9.integrations import (
    register_ablation_tools,
    register_corecoder_tools,
    register_all_integrations,
    ABLATION_COMMANDS,
    CORECODER_COMMANDS,
)
from agent_system_v9.tools.tool_registry import (
    DynamicToolRegistry,
    ToolCategory,
    ToolMetrics,
)
from agent_system_v9.kernel.sandbox_isolator import SandboxIsolator
from agent_system_v9.memory.query_engine import QueryEngine


class TestAblationIntegration:
    """Test Ablation tool registration into DynamicToolRegistry."""

    def test_ablation_command_count(self):
        """All 8 ablation commands are defined."""
        assert len(ABLATION_COMMANDS) == 8

    def test_ablation_register_all(self):
        """Registering all ablation tools succeeds."""
        registry = DynamicToolRegistry.get_instance()
        registry._tools.clear()
        for cat in registry._categories:
            registry._categories[cat] = set()
        sandbox = SandboxIsolator()
        query_engine = QueryEngine()

        count = register_ablation_tools(registry, sandbox, query_engine)
        assert count == 8

        for cmd in ABLATION_COMMANDS:
            entry = registry.get(cmd.name)
            assert entry is not None
            assert entry.category == ToolCategory.ANALYSIS
            assert "ablation" in entry.tags
            assert entry.sandbox_spec is not None

    @pytest.mark.asyncio
    async def test_ablation_wrapper_executes(self):
        """Ablation wrapper calls sandbox.execute_tool."""
        registry = DynamicToolRegistry.get_instance()
        registry._tools.clear()
        for cat in registry._categories:
            registry._categories[cat] = set()
        sandbox = SandboxIsolator()
        query_engine = QueryEngine()

        register_ablation_tools(registry, sandbox, query_engine)

        entry = registry.get("ablation_lift")
        assert entry is not None

        result = await registry.execute(
            "ablation_lift",
            {"binary_path": "/fake/bin"},
            sandbox=True,
        )
        assert result["success"] is False
        assert "error" in result or "returncode" in result


class TestCoreCoderIntegration:
    """Test CoreCoder tool registration into DynamicToolRegistry."""

    def test_corecoder_command_count(self):
        """CoreCoder commands are defined."""
        assert len(CORECODER_COMMANDS) == 4

    def test_corecoder_register_all(self):
        """Registering all corecoder tools succeeds."""
        registry = DynamicToolRegistry.get_instance()
        registry._tools.clear()
        for cat in registry._categories:
            registry._categories[cat] = set()
        sandbox = SandboxIsolator()
        query_engine = QueryEngine()

        count = register_corecoder_tools(registry, sandbox, query_engine)
        assert count == 4
        for cmd in CORECODER_COMMANDS:
            entry = registry.get(cmd.name)
            assert entry is not None
            assert entry.category == ToolCategory.CODE_GENERATION
            assert "corecoder" in entry.tags


class TestAllIntegrations:
    """Test the combined registration convenience function."""

    def test_register_all_integrations(self):
        """register_all_integrations wires sandbox and registers both."""
        registry = DynamicToolRegistry.get_instance()
        registry._tools.clear()
        for cat in registry._categories:
            registry._categories[cat] = set()

        counts = register_all_integrations(registry=registry)
        assert counts["ablation"] == 8
        assert counts["corecoder"] == 4

        assert registry.get("ablation_lift") is not None
        assert registry.get("corecoder_task") is not None

    def test_sandbox_isolator_wired(self):
        """DynamicToolRegistry has sandbox isolator set after registration."""
        registry = DynamicToolRegistry.get_instance()
        registry._tools.clear()
        for cat in registry._categories:
            registry._categories[cat] = set()

        register_all_integrations(registry=registry)
        assert registry._sandbox_isolator is not None


class TestSandboxHardening:
    """Test SandboxIsolator.execute_tool hardening (timeouts, error shapes)."""

    @pytest.mark.asyncio
    async def test_execute_tool_enforces_timeout(self):
        """A tool that runs longer than the spec timeout returns a timed-out result."""
        sandbox = SandboxIsolator()

        async def slow_tool() -> dict:
            import asyncio

            await asyncio.sleep(10)
            return {"success": True}

        result = await sandbox.execute_tool(
            "slow_tool",
            slow_tool,
            {},
            {"timeout_seconds": 0.1, "memory_limit": "512m", "cpu_limit": "1.0"},
        )
        assert result["success"] is False
        assert "timed out" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_execute_tool_returns_dict_result(self):
        """A tool returning a dict passes it through unchanged."""
        sandbox = SandboxIsolator()

        def add(a: int, b: int) -> dict:
            return {"success": True, "result": a + b}

        result = await sandbox.execute_tool(
            "add",
            add,
            {"a": 2, "b": 3},
            {"timeout_seconds": 30, "memory_limit": "512m", "cpu_limit": "1.0"},
        )
        assert result == {"success": True, "result": 5}

    @pytest.mark.asyncio
    async def test_execute_tool_catches_exception(self):
        """A tool that raises returns an error result rather than propagating."""
        sandbox = SandboxIsolator()

        def boom() -> dict:
            raise RuntimeError("kaboom")

        result = await sandbox.execute_tool(
            "boom",
            boom,
            {},
            {"timeout_seconds": 30, "memory_limit": "512m", "cpu_limit": "1.0"},
        )
        assert result["success"] is False
        assert "kaboom" in result["error"]

    def test_parse_mem_and_cpu(self):
        """Memory/CPU spec parsing handles common suffixes."""
        sandbox = SandboxIsolator()
        assert sandbox._parse_mem("512m") == 512 * 1024 * 1024
        assert sandbox._parse_mem("2g") == 2 * 1024 ** 3
        assert sandbox._parse_mem("1mi") == 1024 ** 2
        assert sandbox._parse_cpu("2.0") == 2.0
        assert sandbox._parse_cpu("1") == 1.0


class TestToolMetrics:
    """Test DynamicToolRegistry metrics recording."""

    def test_metrics_record_success_and_error(self):
        """Metrics track executions, errors, and latency per tool."""
        registry = DynamicToolRegistry.get_instance()
        registry.metrics = ToolMetrics()

        async def good() -> dict:
            return {"ok": True}

        async def bad() -> dict:
            raise ValueError("nope")

        registry.register(
            "good_tool", good, "a tool", category=ToolCategory.SYSTEM
        )
        registry.register(
            "bad_tool", bad, "a tool", category=ToolCategory.SYSTEM
        )

        import asyncio

        asyncio.get_event_loop().run_until_complete(
            registry.execute("good_tool", {}, sandbox=False)
        )
        try:
            asyncio.get_event_loop().run_until_complete(
                registry.execute("bad_tool", {}, sandbox=False)
            )
        except ValueError:
            pass

        m = registry.metrics
        assert m.total_executions == 2
        assert m.total_errors == 1
        assert m.by_tool["good_tool"]["executions"] == 1
        assert m.by_tool["good_tool"]["errors"] == 0
        assert m.by_tool["bad_tool"]["errors"] == 1
        assert m.total_latency_ms >= 0
