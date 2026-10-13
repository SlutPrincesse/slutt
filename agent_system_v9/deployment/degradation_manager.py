"""
Degradation Manager - Graceful degradation and fallback handling
"""
import asyncio
import time
from typing import Dict, List, Optional, Any, Callable, Awaitable, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from abc import ABC, abstractmethod


class DegradationLevel(Enum):
    NONE = 0
    MINOR = 1
    MODERATE = 2
    SEVERE = 3
    CRITICAL = 4


class FallbackStrategy(Enum):
    CACHE = "cache"
    STATIC = "static"
    REDUCED = "reduced"
    DISABLE = "disable"
    CIRCUIT_BREAKER = "circuit_breaker"
    CUSTOM = "custom"


@dataclass
class ServiceEndpoint:
    name: str
    handler: Callable
    fallbacks: List['FallbackConfig'] = field(default_factory=list)
    priority: int = 0
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FallbackConfig:
    strategy: FallbackStrategy
    handler: Optional[Callable] = None
    config: Dict[str, Any] = field(default_factory=dict)
    condition: Optional[Callable] = None
    priority: int = 0


@dataclass
class DegradationRule:
    name: str
    condition: Callable
    level: DegradationLevel
    affected_services: List[str]
    actions: List[Callable] = field(default_factory=list)
    cooldown: float = 60.0
    last_triggered: float = 0


@dataclass
class DegradationEvent:
    rule_name: str
    level: DegradationLevel
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolved_at: Optional[float] = None


class CacheFallback:
    def __init__(self, ttl: float = 300, max_size: int = 1000):
        self.ttl = ttl
        self.max_size = max_size
        self.cache: Dict[str, tuple] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key in self.cache:
                value, timestamp = self.cache[key]
                if time.time() - timestamp < self.ttl:
                    return value
                del self.cache[key]
        return None

    async def set(self, key: str, value: Any):
        async with self._lock:
            if len(self.cache) >= self.max_size:
                oldest = min(self.cache.items(), key=lambda x: x[1][1])[0]
                del self.cache[oldest]
            self.cache[key] = (value, time.time())

    async def invalidate(self, key: str):
        async with self._lock:
            self.cache.pop(key, None)


class StaticFallback:
    def __init__(self, static_data: Any):
        self.static_data = static_data

    async def get(self) -> Any:
        return self.static_data


class CircuitBreakerFallback:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_requests: int = 3,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_requests = half_open_requests
        self.failures = 0
        self.successes = 0
        self.state = "closed"
        self.last_failure_time = 0
        self._lock = asyncio.Lock()

    async def can_execute(self) -> bool:
        async with self._lock:
            if self.state == "closed":
                return True
            if self.state == "open":
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = "half_open"
                    self.successes = 0
                    return True
                return False
            if self.state == "half_open":
                return True
            return False

    async def record_success(self):
        async with self._lock:
            if self.state == "half_open":
                self.successes += 1
                if self.successes >= self.half_open_requests:
                    self.state = "closed"
                    self.failures = 0
                    self.successes = 0
            else:
                self.failures = 0

    async def record_failure(self):
        async with self._lock:
            self.failures += 1
            self.last_failure_time = time.time()
            if self.state == "half_open":
                self.state = "open"
                self.successes = 0
            elif self.failures >= self.failure_threshold:
                self.state = "open"

    def get_state(self) -> str:
        return self.state


class DegradationManager:
    def __init__(self):
        self.services: Dict[str, ServiceEndpoint] = {}
        self.rules: Dict[str, DegradationRule] = {}
        self.events: List[DegradationEvent] = []
        self.current_level = DegradationLevel.NONE
        self.cache_fallback = CacheFallback()
        self.circuit_breakers: Dict[str, CircuitBreakerFallback] = {}
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    def register_service(self, endpoint: ServiceEndpoint):
        self.services[endpoint.name] = endpoint
        endpoint.fallbacks.sort(key=lambda f: f.priority)

    def unregister_service(self, name: str) -> bool:
        if name in self.services:
            del self.services[name]
            return True
        return False

    def add_rule(self, rule: DegradationRule):
        self.rules[rule.name] = rule

    def remove_rule(self, name: str) -> bool:
        if name in self.rules:
            del self.rules[name]
            return True
        return False

    async def execute(self, service_name: str, *args, **kwargs) -> Any:
        service = self.services.get(service_name)
        if not service or not service.enabled:
            raise ValueError(f"Service not found or disabled: {service_name}")
        
        try:
            if asyncio.iscoroutinefunction(service.handler):
                result = await service.handler(*args, **kwargs)
            else:
                result = service.handler(*args, **kwargs)
            
            await self._record_success(service_name)
            return result
        except Exception as e:
            await self._record_failure(service_name)
            return await self._execute_fallback(service, *args, **kwargs)

    async def _execute_fallback(self, service: ServiceEndpoint, *args, **kwargs) -> Any:
        for fallback in service.fallbacks:
            if fallback.condition and not fallback.condition():
                continue
            
            try:
                if fallback.strategy == FallbackStrategy.CACHE:
                    cache_key = f"{service.name}:{hash(str(args))}"
                    cached = await self.cache_fallback.get(cache_key)
                    if cached is not None:
                        return cached
                elif fallback.strategy == FallbackStrategy.STATIC:
                    if fallback.config.get("static_value") is not None:
                        return fallback.config["static_value"]
                elif fallback.strategy == FallbackStrategy.REDUCED:
                    if fallback.handler:
                        if asyncio.iscoroutinefunction(fallback.handler):
                            return await fallback.handler(*args, **kwargs)
                        return fallback.handler(*args, **kwargs)
                elif fallback.strategy == FallbackStrategy.CIRCUIT_BREAKER:
                    cb = self.circuit_breakers.get(service.name)
                    if not cb:
                        cb = CircuitBreakerFallback()
                        self.circuit_breakers[service.name] = cb
                    
                    if await cb.can_execute():
                        if asyncio.iscoroutinefunction(fallback.handler):
                            result = await fallback.handler(*args, **kwargs)
                        else:
                            result = fallback.handler(*args, **kwargs)
                        await cb.record_success()
                        return result
                elif fallback.strategy == FallbackStrategy.CUSTOM and fallback.handler:
                    if asyncio.iscoroutinefunction(fallback.handler):
                        return await fallback.handler(*args, **kwargs)
                    return fallback.handler(*args, **kwargs)
            except Exception:
                continue
        
        raise RuntimeError(f"All fallbacks failed for service: {service.name}")

    async def _record_success(self, service_name: str):
        cb = self.circuit_breakers.get(service_name)
        if cb:
            await cb.record_success()

    async def _record_failure(self, service_name: str):
        cb = self.circuit_breakers.get(service_name)
        if cb:
            await cb.record_failure()

    async def check_rules(self):
        for rule in self.rules.values():
            if time.time() - rule.last_triggered < rule.cooldown:
                continue
            
            try:
                if rule.condition():
                    await self._trigger_degradation(rule)
            except Exception:
                pass

    async def _trigger_degradation(self, rule: DegradationRule):
        rule.last_triggered = time.time()
        
        if rule.level.value > self.current_level.value:
            self.current_level = rule.level
        
        event = DegradationEvent(
            rule_name=rule.name,
            level=rule.level,
            metadata={"affected_services": rule.affected_services},
        )
        self.events.append(event)
        
        for action in rule.actions:
            try:
                if asyncio.iscoroutinefunction(action):
                    await action()
                else:
                    action()
            except Exception:
                pass

    def get_current_level(self) -> DegradationLevel:
        return self.current_level

    def get_active_degradations(self) -> List[DegradationEvent]:
        return [e for e in self.events if not e.resolved]

    def get_service_status(self, name: str) -> Dict[str, Any]:
        service = self.services.get(name)
        if not service:
            return {"status": "not_found"}
        
        cb = self.circuit_breakers.get(name)
        return {
            "name": name,
            "enabled": service.enabled,
            "fallbacks": len(service.fallbacks),
            "circuit_breaker": cb.get_state() if cb else "none",
        }


class FeatureFlagDegradation:
    def __init__(self, manager: DegradationManager):
        self.manager = manager
        self.flags: Dict[str, bool] = {}

    def set_flag(self, name: str, enabled: bool):
        self.flags[name] = enabled
        if name in self.manager.services:
            self.manager.services[name].enabled = enabled

    def is_enabled(self, name: str) -> bool:
        return self.flags.get(name, True)

    async def auto_degrade(self, name: str, error_rate: float, threshold: float = 0.5):
        if error_rate > threshold and self.is_enabled(name):
            self.set_flag(name, False)
            self.manager.add_rule(DegradationRule(
                name=f"auto_degrade_{name}",
                condition=lambda: True,
                level=DegradationLevel.MODERATE,
                affected_services=[name],
            ))


class GracefulShutdown:
    def __init__(self, manager: DegradationManager):
        self.manager = manager
        self.shutdown_callbacks: List[Callable] = []
        self.force_shutdown = False

    def register_shutdown_callback(self, callback: Callable):
        self.shutdown_callbacks.append(callback)

    async def shutdown(self, timeout: float = 30.0):
        for service_name in self.manager.services:
            self.manager.services[service_name].enabled = False
        
        for callback in self.shutdown_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await asyncio.wait_for(callback(), timeout=timeout / len(self.shutdown_callbacks))
                else:
                    callback()
            except Exception:
                pass
        
        self.force_shutdown = True