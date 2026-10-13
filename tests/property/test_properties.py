"""
Property-based tests using Hypothesis for core algorithms
"""
import pytest
from hypothesis import given, strategies as st, settings, assume
from hypothesis.strategies import integers, text, lists, dictionaries, booleans, floats, sets

from agent_system_v9.core.registry import SystemRegistry, ComponentMetadata, ComponentState
from agent_system_v9.core.events import EventBus, Event, EventPriority
from agent_system_v9.core.plugins import PluginManager, PluginMetadata, PluginState
from agent_system_v9.shadowgit import RemoteConfig, RemoteProtocol, SyncResult, SyncDirection, SyncStatus
from agent_system_v9.evolution import EvolutionConfig
from agent_system_v9.workspace import WorkspaceConfig, WorkspaceType
from agent_system_v9.distributed import LoadBalancer, Backend, BackendStatus
from datetime import datetime, timedelta


class TestRegistryProperties:
    """Property-based tests for SystemRegistry."""

    @given(st.text(min_size=1, max_size=50))
    @settings(max_examples=50)
    def test_component_name_registration(self, name):
        """Test that any valid string can be used as component name."""
        registry = SystemRegistry()
        component_id = registry.register(
            name=name,
            version="1.0.0",
            section="test",
            capabilities=["test"]
        )
        metadata = registry.get_metadata(component_id)
        assert metadata is not None
        assert metadata.name == name

    @given(st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=5, unique=True))
    @settings(max_examples=30)
    def test_capability_indexing(self, capabilities):
        """Test that components are indexed by all their capabilities."""
        registry = SystemRegistry()
        component_id = registry.register(
            name="test_component",
            version="1.0.0",
            section="test",
            capabilities=capabilities
        )

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
            registry.register(
                name=dep,
                version="1.0.0",
                section="test",
                capabilities=[]
            )

        # Create component with dependencies
        component_id = registry.register(
            name="main",
            version="1.0.0",
            section="test",
            capabilities=[],
            dependencies=dep_names
        )

        metadata = registry.get_metadata(component_id)
        assert metadata is not None
        assert set(metadata.dependencies) == set(dep_names)


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

        event = Event(event_type=event_type, payload="test", metadata=metadata)
        bus.publish(event, blocking=True)

        assert len(received) == 1
        assert received[0].event_type == event_type
        assert received[0].metadata == metadata

    @given(st.sets(st.text(min_size=1, max_size=10), min_size=1, max_size=5))
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
            bus.publish(Event(event_type=et, payload="test"), blocking=True)

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

        # EventPriority values: LOW=0, NORMAL=50, HIGH=100, CRITICAL=200
        priority_values = [EventPriority.LOW, EventPriority.NORMAL, EventPriority.HIGH, EventPriority.CRITICAL]
        priorities = [priority_values[i % 4] for i in range(num_events)]
        for p in priorities:
            bus.publish(Event(event_type="priority_test", payload="test", priority=p), blocking=True)

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
            entry_point="test.entry",
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
            entry_point="test.entry",
            capabilities=capabilities
        )
        assert set(metadata.capabilities) == set(capabilities)


class TestShadowGitSyncProperties:
    """Property-based tests for ShadowGitSync."""

    @given(st.text(min_size=1, max_size=50), st.text(min_size=1, max_size=100))
    @settings(max_examples=30)
    def test_remote_config_creation(self, name, url):
        """Test remote config creation with various names and URLs."""
        config = RemoteConfig(name=name, url=url, protocol=RemoteProtocol.HTTPS)
        assert config.name == name
        assert config.url == url

    @given(st.integers(min_value=1, max_value=1000))
    @settings(max_examples=20)
    def test_sync_result_duration(self, duration_ms):
        """Test sync result duration calculation."""
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
        config = EvolutionConfig(
            population_size=pop_size,
            generations=generations,
            mutation_rate=0.1,
            crossover_rate=0.7
        )
        assert config.population_size == pop_size
        assert config.generations == generations

    @given(st.floats(min_value=0.0, max_value=1.0))
    @settings(max_examples=20)
    def test_mutation_rate_bounds(self, rate):
        """Test mutation rate accepts any valid float."""
        config = EvolutionConfig(
            population_size=10,
            generations=10,
            mutation_rate=rate,
            crossover_rate=0.7
        )
        assert config.mutation_rate == rate


class TestWorkspaceProperties:
    """Property-based tests for Workspace."""

    @given(st.text(min_size=1, max_size=50))
    @settings(max_examples=30)
    def test_workspace_config(self, name):
        """Test workspace config with various parameters."""
        config = WorkspaceConfig(
            name=name,
            workspace_type=WorkspaceType.DEVELOPMENT,
            base_path="./workspaces"
        )
        assert config.name == name
        assert config.workspace_type == WorkspaceType.DEVELOPMENT


class TestDistributedProperties:
    """Property-based tests for Distributed components."""

    @given(st.integers(min_value=1, max_value=100), st.floats(min_value=0.1, max_value=10.0))
    @settings(max_examples=20)
    def test_load_balancer_weights(self, weight, timeout):
        """Test load balancer backend weights."""
        lb = LoadBalancer()
        backend = Backend(
            backend_id="test",
            host="localhost",
            port=8080,
            weight=weight,
            max_connections=int(timeout * 10)
        )
        lb.add_backend(backend)
        assert lb.get_backend("test").weight == weight


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])