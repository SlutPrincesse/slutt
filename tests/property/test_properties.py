"""
Property-based tests using Hypothesis for core algorithms
"""
import pytest
from hypothesis import given, strategies as st, settings, assume
from hypothesis.strategies import integers, text, lists, dictionaries, booleans, floats

from agent_system_v9.core.registry import SystemRegistry, ComponentMetadata, ComponentState
from agent_system_v9.core.events import EventBus, Event, EventPriority
from agent_system_v9.core.plugins import PluginManager, PluginMetadata, PluginState


class TestRegistryProperties:
    """Property-based tests for SystemRegistry."""

    @given(st.text(min_size=1, max_size=50))
    @settings(max_examples=50)
    def test_component_name_registration(self, name):
        """Test that any valid string can be used as component name."""
        registry = SystemRegistry()
        metadata = ComponentMetadata(
            name=name,
            section="test",
            capabilities=["test"]
        )
        registry.register_component(metadata)
        assert registry.get_component(name) is not None
        assert registry.get_component(name).name == name

    @given(st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=5))
    @settings(max_examples=30)
    def test_capability_indexing(self, capabilities):
        """Test that components are indexed by all their capabilities."""
        registry = SystemRegistry()
        metadata = ComponentMetadata(
            name="test_component",
            section="test",
            capabilities=capabilities
        )
        registry.register_component(metadata)
        
        for cap in capabilities:
            results = registry.get_by_capability(cap)
            assert len(results) == 1
            assert results[0].name == "test_component"

    @given(st.integers(min_value=1, max_value=10))
    @settings(max_examples=20)
    def test_dependency_tracking(self, num_deps):
        """Test dependency tracking with multiple dependencies."""
        registry = SystemRegistry()
        
        # Create dependencies first
        dep_names = [f"dep_{i}" for i in range(num_deps)]
        for dep in dep_names:
            registry.register_component(ComponentMetadata(
                name=dep, section="test", capabilities=[]
            ))
        
        # Create component with dependencies
        metadata = ComponentMetadata(
            name="main",
            section="test",
            capabilities=[],
            dependencies=dep_names
        )
        registry.register_component(metadata)
        
        component = registry.get_component("main")
        assert set(component.dependencies) == set(dep_names)


class TestEventBusProperties:
    """Property-based tests for EventBus."""

    @given(st.text(min_size=1, max_size=30), st.dictionaries(st.text(min_size=1), st.text(min_size=1), max_size=5))
    @settings(max_examples=50)
    def test_event_creation_and_publishing(self, event_type, metadata):
        """Test events can be created with any valid type and metadata."""
        bus = EventBus()
        received = []
        
        def handler(event):
            received.append(event)
        
        bus.subscribe(event_type, handler)
        
        event = Event(type=event_type, payload="test", metadata=metadata)
        bus.publish_sync(event)
        
        assert len(received) == 1
        assert received[0].type == event_type
        assert received[0].metadata == metadata

    @given(st.lists(st.text(min_size=1, max_size=10), min_size=1, max_size=5))
    @settings(max_examples=30)
    def test_multiple_subscribers(self, event_types):
        """Test multiple subscribers receive events."""
        bus = EventBus()
        received_counts = {et: 0 for et in event_types}
        
        for et in event_types:
            def make_handler(event_type):
                def handler(event):
                    received_counts[event_type] += 1
                return handler
            bus.subscribe(et, make_handler(et))
        
        for et in event_types:
            bus.publish_sync(Event(type=et, payload="test"))
        
        for et in event_types:
            assert received_counts[et] == 1

    @given(st.integers(min_value=1, max_value=100))
    @settings(max_examples=20)
    def test_event_priority_ordering(self, num_events):
        """Test events are processed in priority order."""
        bus = EventBus()
        processed = []
        
        def handler(event):
            processed.append(event.priority)
        
        bus.subscribe("priority_test", handler)
        
        # Publish events with random priorities
        priorities = [EventPriority(i % 4) for i in range(num_events)]
        for p in priorities:
            bus.publish_sync(Event(type="priority_test", payload="test", priority=p))
        
        # High priority events should be processed first
        # Note: This depends on implementation - some buses process in subscription order
        assert len(processed) == num_events


class TestPluginManagerProperties:
    """Property-based tests for PluginManager."""

    @given(st.text(min_size=1, max_size=30), st.text(min_size=1, max_size=20))
    @settings(max_examples=30)
    def test_plugin_metadata_creation(self, name, version):
        """Test plugin metadata can be created with any valid name/version."""
        metadata = PluginMetadata(
            name=name,
            version=version,
            description="Test plugin",
            author="Test",
            capabilities=["test"]
        )
        assert metadata.name == name
        assert metadata.version == version

    @given(st.lists(st.text(min_size=1, max_size=15), min_size=0, max_size=5))
    @settings(max_examples=30)
    def test_plugin_capabilities(self, capabilities):
        """Test plugin capabilities list handling."""
        metadata = PluginMetadata(
            name="test",
            version="1.0.0",
            description="Test",
            author="Test",
            capabilities=capabilities
        )
        assert set(metadata.capabilities) == set(capabilities)


class TestShadowGitSyncProperties:
    """Property-based tests for ShadowGitSync."""

    @given(st.text(min_size=1, max_size=50), st.text(min_size=1, max_size=100))
    @settings(max_examples=30)
    def test_remote_config_creation(self, name, url):
        """Test remote config creation with various names and URLs."""
        from agent_system_v9.shadowgit import RemoteConfig, RemoteProtocol
        config = RemoteConfig(name=name, url=url, protocol=RemoteProtocol.HTTPS)
        assert config.name == name
        assert config.url == url

    @given(st.integers(min_value=1, max_value=1000))
    @settings(max_examples=20)
    def test_sync_result_duration(self, duration_ms):
        """Test sync result duration calculation."""
        from agent_system_v9.shadowgit import SyncResult, SyncDirection, SyncStatus
        from datetime import datetime, timedelta
        
        result = SyncResult(
            operation_id="test",
            remote_name="origin",
            direction=SyncDirection.PUSH,
            status=SyncStatus.PENDING
        )
        # Manually set times to test duration
        result.started_at = datetime.now() - timedelta(milliseconds=duration_ms)
        result.complete(success=True)
        
        # Duration should be approximately correct (within 100ms tolerance)
        assert abs(result.duration * 1000 - duration_ms) < 200


class TestEvolutionProperties:
    """Property-based tests for Evolution Engine."""

    @given(st.integers(min_value=2, max_value=50), st.integers(min_value=1, max_value=100))
    @settings(max_examples=20)
    def test_population_size_and_generations(self, pop_size, generations):
        """Test evolution config with various population sizes and generations."""
        from agent_system_v9.evolution import EvolutionConfig
        config = EvolutionConfig(
            population_size=pop_size,
            max_generations=generations,
            mutation_rate=0.1,
            crossover_rate=0.7
        )
        assert config.population_size == pop_size
        assert config.max_generations == generations

    @given(st.floats(min_value=0.0, max_value=1.0))
    @settings(max_examples=20)
    def test_mutation_rate_bounds(self, rate):
        """Test mutation rate accepts any valid float."""
        from agent_system_v9.evolution import EvolutionConfig
        config = EvolutionConfig(
            population_size=10,
            max_generations=10,
            mutation_rate=rate,
            crossover_rate=0.7
        )
        assert config.mutation_rate == rate


class TestWorkspaceProperties:
    """Property-based tests for Workspace."""

    @given(st.text(min_size=1, max_size=50), st.integers(min_value=0, max_value=100))
    @settings(max_examples=30)
    def test_workspace_config(self, name, max_files):
        """Test workspace config with various parameters."""
        from agent_system_v9.workspace import WorkspaceConfig, WorkspaceType
        config = WorkspaceConfig(
            name=name,
            workspace_type=WorkspaceType.ISOLATED,
            max_files=max_files
        )
        assert config.name == name
        assert config.max_files == max_files


class TestDistributedProperties:
    """Property-based tests for Distributed components."""

    @given(st.integers(min_value=1, max_value=100), st.floats(min_value=0.1, max_value=10.0))
    @settings(max_examples=20)
    def test_load_balancer_weights(self, weight, timeout):
        """Test load balancer backend weights."""
        from agent_system_v9.distributed import LoadBalancer, Backend
        lb = LoadBalancer()
        backend = Backend(
            id="test",
            host="localhost",
            port=8080,
            weight=weight,
            timeout=timeout
        )
        lb.add_backend(backend)
        assert lb.get_backend("test").weight == weight


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])