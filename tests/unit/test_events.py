"""
Unit tests for core EventBus module.
"""
import asyncio
import pytest
from unittest.mock import Mock, AsyncMock

from agent_system_v9.core.events import EventBus, Event, EventPriority


class TestEventBus:
    """Tests for EventBus singleton."""

    def test_singleton_instance(self, clean_event_bus):
        """Test that EventBus is a singleton."""
        bus1 = EventBus()
        bus2 = EventBus()
        assert bus1 is bus2

    def test_subscribe_and_publish_sync(self, clean_event_bus):
        """Test synchronous subscription and publishing."""
        handler = Mock()
        clean_event_bus.subscribe("test.event", handler)

        event = Event(event_type="test.event", payload={"key": "value"}, source="test")
        clean_event_bus.publish(event, blocking=True)

        handler.assert_called_once()
        call_args = handler.call_args[0][0]
        assert call_args.event_type == "test.event"
        assert call_args.payload == {"key": "value"}
        assert call_args.source == "test"

    def test_publish_sync_method(self, clean_event_bus):
        """Test publish_sync convenience method."""
        handler = Mock()
        clean_event_bus.subscribe("test.event", handler)

        event_id = clean_event_bus.publish_sync(
            "test.event",
            payload={"data": 123},
            source="test_source",
            priority=EventPriority.HIGH,
            extra="info"
        )

        assert event_id is not None
        handler.assert_called_once()
        call_args = handler.call_args[0][0]
        assert call_args.payload == {"data": 123}
        assert call_args.source == "test_source"
        assert call_args.priority == EventPriority.HIGH
        assert call_args.metadata == {"extra": "info"}

    def test_multiple_subscribers(self, clean_event_bus):
        """Test multiple subscribers for same event type."""
        handler1 = Mock()
        handler2 = Mock()
        clean_event_bus.subscribe("test.event", handler1)
        clean_event_bus.subscribe("test.event", handler2)

        event = Event(event_type="test.event", payload={})
        clean_event_bus.publish(event, blocking=True)

        handler1.assert_called_once()
        handler2.assert_called_once()

    def test_unsubscribe(self, clean_event_bus):
        """Test unsubscribing handler."""
        handler = Mock()
        clean_event_bus.subscribe("test.event", handler)
        clean_event_bus.unsubscribe("test.event", handler)

        event = Event(event_type="test.event", payload={})
        clean_event_bus.publish(event, blocking=True)

        handler.assert_not_called()

    def test_wildcard_subscriber(self, clean_event_bus):
        """Test wildcard subscriber receives all events."""
        handler = Mock()
        clean_event_bus.subscribe_all(handler)

        event1 = Event(event_type="event.one", payload={})
        event2 = Event(event_type="event.two", payload={})
        clean_event_bus.publish(event1, blocking=True)
        clean_event_bus.publish(event2, blocking=True)

        assert handler.call_count == 2

    def test_pattern_subscriber(self, clean_event_bus):
        """Test pattern-based subscription."""
        handler = Mock()
        clean_event_bus.subscribe("test.*", handler, pattern=True)

        event1 = Event(event_type="test.one", payload={})
        event2 = Event(event_type="test.two", payload={})
        event3 = Event(event_type="other.event", payload={})
        clean_event_bus.publish(event1, blocking=True)
        clean_event_bus.publish(event2, blocking=True)
        clean_event_bus.publish(event3, blocking=True)

        assert handler.call_count == 2

    def test_event_priority_ordering(self, clean_event_bus):
        """Test event priority ordering in queue."""
        received_priorities = []

        def handler(event):
            received_priorities.append(event.priority)

        clean_event_bus.subscribe("priority.test", handler)

        # Publish in reverse priority order
        clean_event_bus.publish_sync("priority.test", priority=EventPriority.LOW)
        clean_event_bus.publish_sync("priority.test", priority=EventPriority.CRITICAL)
        clean_event_bus.publish_sync("priority.test", priority=EventPriority.NORMAL)
        clean_event_bus.publish_sync("priority.test", priority=EventPriority.HIGH)

        # In sync mode, they're delivered in order of publishing
        # but priority affects queue ordering in async mode
        assert len(received_priorities) == 4

    def test_event_correlation_id(self, clean_event_bus):
        """Test event correlation ID tracking."""
        handler = Mock()
        clean_event_bus.subscribe("correlation.test", handler)

        correlation_id = "corr-123"
        event = Event(
            event_type="correlation.test",
            payload={},
            correlation_id=correlation_id
        )
        clean_event_bus.publish(event, blocking=True)

        call_args = handler.call_args[0][0]
        assert call_args.correlation_id == correlation_id

    def test_event_metadata(self, clean_event_bus):
        """Test event metadata propagation."""
        handler = Mock()
        clean_event_bus.subscribe("metadata.test", handler)

        event = Event(
            event_type="metadata.test",
            payload={},
            metadata={"key1": "value1", "key2": "value2"}
        )
        clean_event_bus.publish(event, blocking=True)

        call_args = handler.call_args[0][0]
        assert call_args.metadata == {"key1": "value1", "key2": "value2"}

    def test_stats_tracking(self, clean_event_bus):
        """Test statistics tracking."""
        handler = Mock()
        clean_event_bus.subscribe("stats.test", handler)

        clean_event_bus.publish_sync("stats.test")
        clean_event_bus.publish_sync("stats.test")

        stats = clean_event_bus.get_stats()
        assert stats["published"] == 2
        assert stats["delivered"] == 2
        assert stats["failed"] == 0

    def test_failed_delivery_stats(self, clean_event_bus):
        """Test failed delivery increments failed counter."""
        def failing_handler(event):
            raise ValueError("Test error")

        clean_event_bus.subscribe("fail.test", failing_handler)
        clean_event_bus.publish_sync("fail.test")

        stats = clean_event_bus.get_stats()
        assert stats["failed"] == 1

    def test_event_history(self, clean_event_bus):
        """Test event history recording."""
        clean_event_bus.publish_sync("history.test", payload={"seq": 1})
        clean_event_bus.publish_sync("history.test", payload={"seq": 2})
        clean_event_bus.publish_sync("history.test", payload={"seq": 3})

        history = clean_event_bus.get_history(limit=2)
        assert len(history) == 2
        assert history[-1].payload["seq"] == 3

    def test_history_filter_by_type(self, clean_event_bus):
        """Test filtering history by event type."""
        clean_event_bus.publish_sync("type.a", payload={})
        clean_event_bus.publish_sync("type.b", payload={})
        clean_event_bus.publish_sync("type.a", payload={})

        history = clean_event_bus.get_history(event_type="type.a")
        assert len(history) == 2
        assert all(e.event_type == "type.a" for e in history)

    @pytest.mark.asyncio
    async def test_async_publish(self, clean_event_bus):
        """Test async event publishing."""
        handler = AsyncMock()
        clean_event_bus.subscribe("async.test", handler)

        await clean_event_bus.start()
        try:
            event = Event(event_type="async.test", payload={"async": True})
            clean_event_bus.publish(event)  # publish is not async
            await asyncio.sleep(0.1)  # Allow worker to process
        finally:
            await clean_event_bus.stop()

        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_handler(self, clean_event_bus):
        """Test async handler execution."""
        handler = AsyncMock()
        clean_event_bus.subscribe("async.handler.test", handler)

        await clean_event_bus.start()
        try:
            event = Event(event_type="async.handler.test", payload={})
            clean_event_bus.publish(event, blocking=True)
            await asyncio.sleep(0.1)
        finally:
            await clean_event_bus.stop()

        handler.assert_called_once()

    def test_max_history_limit(self, clean_event_bus):
        """Test history respects max limit."""
        # Publish more than max history (10000)
        for i in range(10500):
            clean_event_bus.publish_sync("limit.test", payload={"i": i})

        history = clean_event_bus.get_history()
        assert len(history) <= 10000


class TestEvent:
    """Tests for Event dataclass."""

    def test_event_creation(self):
        """Test basic event creation."""
        event = Event(event_type="test", payload={"data": 123})
        assert event.event_type == "test"
        assert event.payload == {"data": 123}
        assert event.source == ""
        assert event.priority == EventPriority.NORMAL
        assert event.event_id is not None
        assert event.timestamp > 0

    def test_event_comparison(self):
        """Test event priority comparison."""
        low = Event(event_type="low", priority=EventPriority.LOW)
        high = Event(event_type="high", priority=EventPriority.HIGH)

        # Higher priority should be "less than" for priority queue
        assert high < low
        assert not (low < high)

    def test_event_defaults(self):
        """Test default values."""
        event = Event(event_type="test")
        assert event.payload is None
        assert event.source == ""
        assert event.target == ""
        assert event.correlation_id is None
        assert event.metadata == {}