"""
Unit tests for core PluginManager module.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch

from agent_system_v9.core.plugins import PluginManager, PluginMetadata, PluginState, PluginContext
from agent_system_v9.core.registry import SystemRegistry, ComponentState


class TestPluginManager:
    """Tests for PluginManager."""

    def test_singleton_instance(self, clean_registry):
        """Test that PluginManager is a singleton."""
        mgr1 = PluginManager()
        mgr2 = PluginManager()
        assert mgr1 is mgr2

    def test_register_plugin(self, clean_registry):
        """Test plugin registration."""
        mgr = PluginManager()

        def dummy_factory(context):
            return Mock()

        metadata = PluginMetadata(
            name="test_plugin",
            version="1.0.0",
            description="Test plugin",
            entry_point="test.module:factory",
            capabilities=["cap1"],
            dependencies=["dep1"],
        )

        plugin_id = mgr.register_plugin(metadata, dummy_factory)

        assert plugin_id == "test_plugin.1.0.0"
        loaded = mgr.get_plugin_info("test_plugin.1.0.0")
        assert loaded is not None
        assert loaded["metadata"].name == "test_plugin"
        assert loaded["state"] == PluginState.LOADED

    def test_load_plugin(self, clean_registry):
        """Test plugin loading and instantiation."""
        mgr = PluginManager()

        instance = Mock()
        instance.name = "loaded_instance"

        def factory(context):
            return instance

        metadata = PluginMetadata(
            name="load_test",
            version="1.0.0",
            description="Test",
            entry_point="test:factory",
        )

        plugin_id = mgr.register_plugin(metadata, factory)
        loaded_instance = mgr.load_plugin(plugin_id)

        assert loaded_instance is instance
        loaded = mgr.get_plugin_info(plugin_id)
        assert loaded["state"] == PluginState.ACTIVE
        assert loaded["instance"] is instance

    def test_load_dependencies_first(self, clean_registry):
        """Test that dependencies are loaded before plugin."""
        mgr = PluginManager()

        dep_instance = Mock()
        dep_instance.name = "dependency"

        plugin_instance = Mock()
        plugin_instance.name = "plugin"

        def dep_factory(context):
            return dep_instance

        def plugin_factory(context):
            return plugin_instance

        dep_metadata = PluginMetadata(
            name="dependency",
            version="1.0.0",
            description="Dep",
            entry_point="dep:factory",
        )

        plugin_metadata = PluginMetadata(
            name="plugin",
            version="1.0.0",
            description="Plugin",
            entry_point="plugin:factory",
            dependencies=["dependency.1.0.0"],
        )

        dep_id = mgr.register_plugin(dep_metadata, dep_factory)
        plugin_id = mgr.register_plugin(plugin_metadata, plugin_factory)

        loaded = mgr.load_plugin(plugin_id)

        assert loaded is plugin_instance
        dep_loaded = mgr.get_plugin_info(dep_id)
        assert dep_loaded["state"] == PluginState.ACTIVE

    def test_unload_plugin(self, clean_registry):
        """Test plugin unloading."""
        mgr = PluginManager()

        instance = Mock()

        def factory(context):
            return instance

        metadata = PluginMetadata(
            name="unload_test",
            version="1.0.0",
            description="Test",
            entry_point="test:factory",
        )

        plugin_id = mgr.register_plugin(metadata, factory)
        mgr.load_plugin(plugin_id)

        result = mgr.unload_plugin(plugin_id)

        assert result is True
        loaded = mgr.get_plugin_info(plugin_id)
        assert loaded["state"] == PluginState.LOADED
        assert loaded["instance"] is None

    def test_unload_with_dependents_fails(self, clean_registry):
        """Test unloading plugin with active dependents fails."""
        mgr = PluginManager()

        dep_instance = Mock()
        plugin_instance = Mock()

        def dep_factory(context):
            return dep_instance

        def plugin_factory(context):
            return plugin_instance

        dep_metadata = PluginMetadata(
            name="dependency",
            version="1.0.0",
            description="Dep",
            entry_point="dep:factory",
        )

        plugin_metadata = PluginMetadata(
            name="plugin",
            version="1.0.0",
            description="Plugin",
            entry_point="plugin:factory",
            dependencies=["dependency.1.0.0"],
        )

        dep_id = mgr.register_plugin(dep_metadata, dep_factory)
        plugin_id = mgr.register_plugin(plugin_metadata, plugin_factory)

        mgr.load_plugin(plugin_id)  # This loads both

        # Try to unload dependency while plugin is active
        result = mgr.unload_plugin(dep_id)

        assert result is False  # Should fail

    def test_enable_disable_plugin(self, clean_registry):
        """Test plugin enable/disable."""
        mgr = PluginManager()

        instance = Mock()
        instance.enabled = True

        def factory(context):
            return instance

        metadata = PluginMetadata(
            name="toggle_test",
            version="1.0.0",
            description="Test",
            entry_point="test:factory",
        )

        plugin_id = mgr.register_plugin(metadata, factory)
        mgr.load_plugin(plugin_id)

        # Disable
        mgr.disable_plugin(plugin_id)
        loaded = mgr.get_plugin_info(plugin_id)
        assert loaded["state"] == PluginState.DISABLED

        # Enable
        mgr.enable_plugin(plugin_id)
        loaded = mgr.get_plugin_info(plugin_id)
        assert loaded["state"] == PluginState.ACTIVE

    def test_get_by_capability(self, clean_registry):
        """Test getting plugins by capability."""
        mgr = PluginManager()

        def factory(context):
            return Mock()

        metadata1 = PluginMetadata(
            name="plugin1",
            version="1.0.0",
            description="Test",
            entry_point="p1:factory",
            capabilities=["cap1", "cap2"],
        )

        metadata2 = PluginMetadata(
            name="plugin2",
            version="1.0.0",
            description="Test",
            entry_point="p2:factory",
            capabilities=["cap2", "cap3"],
        )

        mgr.register_plugin(metadata1, factory)
        mgr.register_plugin(metadata2, factory)

        cap2_plugins = mgr.get_by_capability("cap2")
        assert len(cap2_plugins) == 2

    def test_health_check(self, clean_registry):
        """Test plugin health check."""
        mgr = PluginManager()

        healthy_instance = Mock()
        healthy_instance.health_check = Mock(return_value=True)

        unhealthy_instance = Mock()
        unhealthy_instance.health_check = Mock(return_value=False)

        def healthy_factory(context):
            return healthy_instance

        def unhealthy_factory(context):
            return unhealthy_instance

        meta1 = PluginMetadata(name="healthy", version="1.0", description="", entry_point="h:f", capabilities=[])
        meta2 = PluginMetadata(name="unhealthy", version="1.0", description="", entry_point="u:f", capabilities=[])

        id1 = mgr.register_plugin(meta1, healthy_factory)
        id2 = mgr.register_plugin(meta2, unhealthy_factory)

        mgr.load_plugin(id1)
        mgr.load_plugin(id2)

        health = mgr.health_check()

        assert health["healthy.1.0"] is True
        assert health["unhealthy.1.0"] is False

    def test_get_all_plugins(self, clean_registry):
        """Test getting all plugins."""
        mgr = PluginManager()

        def factory(context):
            return Mock()

        meta1 = PluginMetadata(name="p1", version="1.0", description="", entry_point="1:f", capabilities=[])
        meta2 = PluginMetadata(name="p2", version="1.0", description="", entry_point="2:f", capabilities=[])

        mgr.register_plugin(meta1, factory)
        mgr.register_plugin(meta2, factory)

        all_plugins = mgr.get_all()
        assert len(all_plugins) == 2

    def test_plugin_context(self, clean_registry):
        """Test PluginContext provides required services."""
        mgr = PluginManager()

        context_received = {}

        def factory(context):
            context_received["config"] = context.config
            context_received["registry"] = context.registry
            context_received["event_bus"] = context.event_bus
            return Mock()

        metadata = PluginMetadata(
            name="context_test",
            version="1.0.0",
            description="Test",
            entry_point="test:factory",
        )

        plugin_id = mgr.register_plugin(metadata, factory)
        mgr.load_plugin(plugin_id)

        assert context_received["config"] is not None
        assert context_received["registry"] is not None
        assert context_received["event_bus"] is not None

    def test_load_nonexistent_plugin(self, clean_registry):
        """Test loading non-existent plugin raises error."""
        mgr = PluginManager()

        with pytest.raises(KeyError):
            mgr.load_plugin("nonexistent.1.0.0")

    def test_register_duplicate_name_version(self, clean_registry):
        """Test registering duplicate plugin name/version raises error."""
        mgr = PluginManager()

        def factory(context):
            return Mock()

        metadata = PluginMetadata(
            name="duplicate",
            version="1.0.0",
            description="Test",
            entry_point="test:factory",
        )

        mgr.register_plugin(metadata, factory)

        with pytest.raises(ValueError):
            mgr.register_plugin(metadata, factory)


class TestPluginMetadata:
    """Tests for PluginMetadata dataclass."""

    def test_defaults(self):
        """Test default values."""
        metadata = PluginMetadata(
            name="test",
            version="1.0.0",
            description="Test plugin",
            entry_point="test:factory",
        )

        assert metadata.capabilities == []
        assert metadata.dependencies == []
        assert metadata.config_schema == {}
        assert metadata.metadata == {}
        assert metadata.priority == 0


class TestPluginContext:
    """Tests for PluginContext."""

    def test_context_creation(self, clean_registry):
        """Test context creation with services."""
        context = PluginContext(
            config=Mock(),
            registry=Mock(),
            event_bus=Mock(),
            logger=Mock(),
        )

        assert context.config is not None
        assert context.registry is not None
        assert context.event_bus is not None
        assert context.logger is not None