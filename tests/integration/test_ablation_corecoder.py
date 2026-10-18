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
from agent_system_v9.tools.tool_registry import DynamicToolRegistry, ToolCategory
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
