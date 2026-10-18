"""
Integration tests for Cybersec-Toolkit integration
"""
import pytest

from agent_system_v9.integrations import (
    get_cybersec_toolkit_integration,
)


class TestCybersecToolkit:
    """Test Cybersec Toolkit integration."""

    def test_toolkit_creation(self):
        """Test toolkit integration creation."""
        ct = get_cybersec_toolkit_integration()
        assert ct is not None
        assert ct.tool_manager is not None

    def test_toolkit_has_modules(self):
        """Test toolkit has expected module categories."""
        ct = get_cybersec_toolkit_integration()
        modules = ct.tool_manager.get_all_modules()
        assert len(modules) >= 10

        expected = ['networking', 'web', 'recon', 'crypto', 'pwn']
        for exp in expected:
            assert exp in modules

    def test_toolkit_can_list_tools(self):
        """Test toolkit can list tools in a module."""
        ct = get_cybersec_toolkit_integration()
        tools = ct.tool_manager.get_tools_by_module('recon')
        assert isinstance(tools, list)
