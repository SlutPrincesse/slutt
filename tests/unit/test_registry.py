"""
Unit tests for core SystemRegistry module.
"""
import pytest
from agent_system_v9.core.registry import SystemRegistry, ComponentState, ComponentMetadata


class TestSystemRegistry:
    """Tests for SystemRegistry singleton."""

    def test_singleton_instance(self, clean_registry):
        """Test that SystemRegistry is a singleton."""
        registry1 = SystemRegistry()
        registry2 = SystemRegistry()
        assert registry1 is registry2

    def test_register_component(self, clean_registry, sample_component_data):
        """Test component registration."""
        class TestComponent:
            def __init__(self):
                self.value = "test"

        instance = TestComponent()
        comp_id = clean_registry.register(instance=instance, **sample_component_data)

        assert comp_id == "test.test_component.1.0.0"
        metadata = clean_registry.get_metadata(comp_id)
        assert metadata is not None
        assert metadata.name == "test_component"
        assert metadata.version == "1.0.0"
        assert metadata.section == "test"
        assert metadata.state == ComponentState.ACTIVE

    def test_register_without_instance(self, clean_registry, sample_component_data):
        """Test registration without instance creates UNREGISTERED state."""
        sample_data = sample_component_data.copy()
        # Don't pass instance

        # We need to register with the registry directly
        comp_id = clean_registry.register(
            name=sample_data["name"],
            version=sample_data["version"],
            section=sample_data["section"],
            dependencies=sample_data["dependencies"],
            capabilities=sample_data["capabilities"],
            metadata=sample_data["metadata"],
        )

        metadata = clean_registry.get_metadata(comp_id)
        assert metadata.state == ComponentState.REGISTERING

    def test_unregister_component(self, clean_registry, sample_component_data):
        """Test component unregistration."""
        comp_id = clean_registry.register(**sample_component_data)
        result = clean_registry.unregister(comp_id)

        assert result is True
        assert clean_registry.get_metadata(comp_id) is None
        assert clean_registry.get_component(comp_id) is None

    def test_unregister_nonexistent(self, clean_registry):
        """Test unregistering non-existent component returns False."""
        result = clean_registry.unregister("nonexistent.component.1.0.0")
        assert result is False

    def test_get_by_section(self, clean_registry):
        """Test getting components by section."""
        clean_registry.register(name="comp1", version="1.0", section="test", capabilities=["cap1"])
        clean_registry.register(name="comp2", version="1.0", section="test", capabilities=["cap2"])
        clean_registry.register(name="comp3", version="1.0", section="other", capabilities=["cap3"])

        test_section = clean_registry.get_by_section("test")
        assert len(test_section) == 2
        assert all(c.section == "test" for c in test_section)

    def test_get_by_capability(self, clean_registry):
        """Test getting components by capability."""
        clean_registry.register(name="comp1", version="1.0", section="test", capabilities=["cap1", "cap2"])
        clean_registry.register(name="comp2", version="1.0", section="test", capabilities=["cap2", "cap3"])

        cap2_components = clean_registry.get_by_capability("cap2")
        assert len(cap2_components) == 2

        cap1_components = clean_registry.get_by_capability("cap1")
        assert len(cap1_components) == 1

    def test_health_scoring(self, clean_registry, sample_component_data):
        """Test health score updates and state transitions."""
        comp_id = clean_registry.register(**sample_component_data)

        # Update to degraded
        clean_registry.update_health(comp_id, 0.4)
        metadata = clean_registry.get_metadata(comp_id)
        assert metadata.state == ComponentState.DEGRADED
        assert metadata.health_score == 0.4

        # Update to failed
        clean_registry.update_health(comp_id, 0.1)
        metadata = clean_registry.get_metadata(comp_id)
        assert metadata.state == ComponentState.FAILED

        # Update to healthy
        clean_registry.update_health(comp_id, 0.9)
        metadata = clean_registry.get_metadata(comp_id)
        assert metadata.state == ComponentState.ACTIVE

    def test_heartbeat(self, clean_registry, sample_component_data):
        """Test heartbeat updates timestamp."""
        comp_id = clean_registry.register(**sample_component_data)
        import time

        before = time.time()
        clean_registry.heartbeat(comp_id)
        after = time.time()

        metadata = clean_registry.get_metadata(comp_id)
        assert before <= metadata.last_heartbeat <= after

    def test_dependency_tracking(self, clean_registry):
        """Test dependency graph tracking."""
        clean_registry.register(name="dep1", version="1.0", section="test")
        clean_registry.register(name="dep2", version="1.0", section="test")
        clean_registry.register(
            name="consumer",
            version="1.0",
            section="test",
            dependencies=["test.dep1.1.0", "test.dep2.1.0"]
        )

        deps = clean_registry.resolve_dependencies("test.consumer.1.0")
        assert "test.dep1.1.0" in deps
        assert "test.dep2.1.0" in deps

    def test_component_instance_storage(self, clean_registry, sample_component_data):
        """Test component instance storage and retrieval."""
        class TestComponent:
            def __init__(self):
                self.value = "test"

        instance = TestComponent()
        comp_id = clean_registry.register(instance=instance, **sample_component_data)

        retrieved = clean_registry.get_component(comp_id)
        assert retrieved is instance
        assert retrieved.value == "test"


class TestComponentMetadata:
    """Tests for ComponentMetadata dataclass."""

    def test_default_values(self):
        """Test default field values."""
        metadata = ComponentMetadata(
            component_id="test.comp.1.0",
            name="comp",
            version="1.0",
            section="test"
        )

        assert metadata.dependencies == []
        assert metadata.capabilities == []
        assert metadata.state == ComponentState.UNREGISTERED
        assert metadata.health_score == 1.0
        assert metadata.last_heartbeat == 0.0
        assert metadata.metadata == {}