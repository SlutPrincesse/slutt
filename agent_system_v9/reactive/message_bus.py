"""
Message Bus Adapter - Reactive message bus integration
"""
import asyncio
import json
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MessagePriority(Enum):
    LOW = 0
    NORMAL = 50
    HIGH = 100
    CRITICAL = 200


@dataclass
class Message:
    message_id: str
    topic: str
    payload: Any
    headers: dict[str, str] = field(default_factory=dict)
    priority: MessagePriority = MessagePriority.NORMAL
    timestamp: float = field(default_factory=time.time)
    correlation_id: str | None = None
    reply_to: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "topic": self.topic,
            "payload": self.payload,
            "headers": self.headers,
            "priority": self.priority.value,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
            "reply_to": self.reply_to,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'Message':
        return cls(
            message_id=data["message_id"],
            topic=data["topic"],
            payload=data["payload"],
            headers=data.get("headers", {}),
            priority=MessagePriority(data.get("priority", MessagePriority.NORMAL.value)),
            timestamp=data.get("timestamp", time.time()),
            correlation_id=data.get("correlation_id"),
            reply_to=data.get("reply_to"),
        )


@dataclass
class Subscription:
    subscription_id: str
    topic: str
    handler: Callable
    filter_expr: str | None = None
    priority: MessagePriority = MessagePriority.NORMAL
    active: bool = True


class MessageBus(ABC):
    @abstractmethod
    async def publish(self, topic: str, payload: Any, **kwargs) -> str:
        pass

    @abstractmethod
    async def subscribe(self, topic: str, handler: Callable, **kwargs) -> str:
        pass

    @abstractmethod
    async def unsubscribe(self, subscription_id: str) -> bool:
        pass

    @abstractmethod
    async def request(self, topic: str, payload: Any, timeout: float = 30.0) -> Any:
        pass

    @abstractmethod
    async def start(self):
        pass

    @abstractmethod
    async def stop(self):
        pass


class InMemoryMessageBus(MessageBus):
    def __init__(self):
        self.subscriptions: dict[str, list[Subscription]] = defaultdict(list)
        self.pending_requests: dict[str, asyncio.Future] = {}
        self._running = False
        self._lock = asyncio.Lock()

    async def start(self):
        self._running = True

    async def stop(self):
        self._running = False
        for futures in self.pending_requests.values():
            for f in futures:
                if not f.done():
                    f.cancel()
        self.pending_requests.clear()

    async def publish(self, topic: str, payload: Any, **kwargs) -> str:
        message = Message(
            message_id=str(uuid.uuid4()),
            topic=topic,
            payload=payload,
            headers=kwargs.get("headers", {}),
            priority=kwargs.get("priority", MessagePriority.NORMAL),
            correlation_id=kwargs.get("correlation_id"),
            reply_to=kwargs.get("reply_to"),
        )

        subscriptions = self.subscriptions.get(topic, [])
        for sub in subscriptions:
            if sub.active:
                try:
                    if asyncio.iscoroutinefunction(sub.handler):
                        await sub.handler(message)
                    else:
                        sub.handler(message)
                except Exception:
                    pass

        if message.reply_to and message.correlation_id:
            future = self.pending_requests.get(message.correlation_id)
            if future and not future.done():
                future.set_result(message)

        return message.message_id

    async def subscribe(self, topic: str, handler: Callable, **kwargs) -> str:
        subscription = Subscription(
            subscription_id=str(uuid.uuid4()),
            topic=topic,
            handler=handler,
            filter_expr=kwargs.get("filter_expr"),
            priority=kwargs.get("priority", MessagePriority.NORMAL),
        )
        self.subscriptions[topic].append(subscription)
        return subscription.subscription_id

    async def unsubscribe(self, subscription_id: str) -> bool:
        for topic, subs in self.subscriptions.items():
            for i, sub in enumerate(subs):
                if sub.subscription_id == subscription_id:
                    subs.pop(i)
                    return True
        return False

    async def request(self, topic: str, payload: Any, timeout: float = 30.0) -> Any:
        correlation_id = str(uuid.uuid4())
        reply_topic = f"reply.{correlation_id}"

        future = asyncio.get_event_loop().create_future()
        self.pending_requests[correlation_id] = future

        await self.subscribe(reply_topic, lambda m: None)
        await self.publish(topic, payload, correlation_id=correlation_id, reply_to=reply_topic)

        try:
            response = await asyncio.wait_for(future, timeout=timeout)
            return response.payload
        finally:
            self.pending_requests.pop(correlation_id, None)
            await self.unsubscribe(reply_topic)


class KafkaAdapter(MessageBus):
    def __init__(self, bootstrap_servers: str, group_id: str):
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self._consumer = None
        self._producer = None
        self._handlers: dict[str, Callable] = {}
        self._running = False

    async def start(self):
        try:
            from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode(),
            )
            await self._producer.start()

            self._consumer = AIOKafkaConsumer(
                *self._handlers.keys(),
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                value_deserializer=lambda v: json.loads(v.decode()),
            )
            await self._consumer.start()

            self._running = True
            asyncio.create_task(self._consume_loop())
        except ImportError:
            raise RuntimeError("aiokafka not installed")

    async def stop(self):
        self._running = False
        if self._consumer:
            await self._consumer.stop()
        if self._producer:
            await self._producer.stop()

    async def publish(self, topic: str, payload: Any, **kwargs) -> str:
        if not self._producer:
            raise RuntimeError("Not started")
        await self._producer.send_and_wait(topic, payload)
        return str(uuid.uuid4())

    async def subscribe(self, topic: str, handler: Callable, **kwargs) -> str:
        self._handlers[topic] = handler
        if self._running and self._consumer:
            await self._consumer.subscribe(topics=list(self._handlers.keys()))
        return str(uuid.uuid4())

    async def unsubscribe(self, subscription_id: str) -> bool:
        return False

    async def request(self, topic: str, payload: Any, timeout: float = 30.0) -> Any:
        raise NotImplementedError("Request-reply not supported in Kafka adapter")

    async def _consume_loop(self):
        async for msg in self._consumer:
            if not self._running:
                break
            handler = self._handlers.get(msg.topic)
            if handler:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(msg.value)
                    else:
                        handler(msg.value)
                except Exception:
                    pass


class RedisAdapter(MessageBus):
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self._redis = None
        self._pubsub = None
        self._handlers: dict[str, Callable] = {}
        self._running = False

    async def start(self):
        try:
            import redis.asyncio as redis
            self._redis = redis.from_url(self.redis_url)
            self._pubsub = self._redis.pubsub()
            self._running = True
            asyncio.create_task(self._listen_loop())
        except ImportError:
            raise RuntimeError("redis not installed")

    async def stop(self):
        self._running = False
        if self._pubsub:
            await self._pubsub.close()
        if self._redis:
            await self._redis.close()

    async def publish(self, topic: str, payload: Any, **kwargs) -> str:
        if not self._redis:
            raise RuntimeError("Not started")
        await self._redis.publish(topic, json.dumps(payload))
        return str(uuid.uuid4())

    async def subscribe(self, topic: str, handler: Callable, **kwargs) -> str:
        self._handlers[topic] = handler
        if self._pubsub:
            await self._pubsub.subscribe(topic)
        return str(uuid.uuid4())

    async def unsubscribe(self, subscription_id: str) -> bool:
        return False

    async def request(self, topic: str, payload: Any, timeout: float = 30.0) -> Any:
        raise NotImplementedError("Request-reply not supported in Redis adapter")

    async def _listen_loop(self):
        async for message in self._pubsub.listen():
            if not self._running:
                break
            if message["type"] == "message":
                topic = message["channel"]
                handler = self._handlers.get(topic)
                if handler:
                    try:
                        payload = json.loads(message["data"])
                        if asyncio.iscoroutinefunction(handler):
                            await handler(payload)
                        else:
                            handler(payload)
                    except Exception:
                        pass


class MessageBusFactory:
    @staticmethod
    def create(bus_type: str, **kwargs) -> MessageBus:
        if bus_type == "memory":
            return InMemoryMessageBus()
        if bus_type == "kafka":
            return KafkaAdapter(kwargs.get("bootstrap_servers", "localhost:9092"), kwargs.get("group_id", "default"))
        if bus_type == "redis":
            return RedisAdapter(kwargs.get("redis_url", "redis://localhost:6379"))
        raise ValueError(f"Unknown bus type: {bus_type}")
