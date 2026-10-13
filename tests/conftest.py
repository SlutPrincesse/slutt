"""
Pytest configuration and fixtures for AGENT_SYSTEM_V9
Provides fixtures for singleton isolation and common test utilities.
"""
import asyncio
import os
import sys
from typing import AsyncGenerator, Generator
from unittest.mock import patch

import pytest

# Ensure agent_system_v9 is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def reset_singletons() -> Generator[None, None, None]:
    """Reset all singleton instances before each test."""
    # Import here to avoid circular imports
    from agent_system_v9.core.registry import SystemRegistry
    from agent_system_v9.core.events import EventBus
    from agent_system_v9.core.config import SystemConfig
    from agent_system_v9.core.plugins import PluginManager

    # Store original instances
    original_registry = SystemRegistry._instance
    original_event_bus = EventBus._instance
    original_config = SystemConfig._instance
    original_plugin_manager = PluginManager._instance

    # Reset singletons
    SystemRegistry._instance = None
    EventBus._instance = None
    SystemConfig._instance = None
    PluginManager._instance = None

    yield

    # Restore original instances
    SystemRegistry._instance = original_registry
    EventBus._instance = original_event_bus
    SystemConfig._instance = original_config
    PluginManager._instance = original_plugin_manager


@pytest.fixture
def clean_registry() -> Generator:
    """Provide a clean SystemRegistry instance."""
    from agent_system_v9.core.registry import SystemRegistry, ComponentState

    registry = SystemRegistry()
    yield registry

    # Cleanup
    for comp_id in list(registry._components.keys()):
        registry.unregister(comp_id)


@pytest.fixture
def clean_event_bus() -> Generator:
    """Provide a clean EventBus instance."""
    from agent_system_v9.core.events import EventBus

    bus = EventBus()
    yield bus


@pytest.fixture
def clean_config() -> Generator:
    """Provide a clean SystemConfig instance."""
    from agent_system_v9.core.config import SystemConfig

    config = SystemConfig()
    yield config


@pytest.fixture
def sample_component_data() -> dict:
    """Sample component registration data."""
    return {
        "name": "test_component",
        "version": "1.0.0",
        "section": "test",
        "dependencies": [],
        "capabilities": ["test_capability"],
        "metadata": {"key": "value"},
    }


@pytest.fixture
def mock_async_handler():
    """Create a mock async handler for EventBus testing."""
    from unittest.mock import AsyncMock
    return AsyncMock()


@pytest.fixture
def mock_sync_handler():
    """Create a mock sync handler for EventBus testing."""
    from unittest.mock import Mock
    return Mock()


# Test markers
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "ml: Tests requiring ML dependencies")


# Async test utilities
class AsyncTestCase:
    """Base class for async test cases."""

    async def asyncSetUp(self):
        pass

    async def asyncTearDown(self):
        pass

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.asyncSetUp())

    def tearDown(self):
        self.loop.run_until_complete(self.asyncTearDown())
        self.loop.close()


def async_test(coro):
    """Decorator to run async test functions."""
    def wrapper(*args, **kwargs):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro(*args, **kwargs))
        finally:
            loop.close()
    return wrapper