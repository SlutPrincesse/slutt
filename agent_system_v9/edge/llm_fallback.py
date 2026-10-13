"""
LLM Fallback Gateway - Fallback and failover for LLM providers
"""
import asyncio
import hashlib
import time
import random
from typing import Dict, List, Optional, Any, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict


class FallbackReason(Enum):
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    ERROR = "error"
    QUOTA_EXCEEDED = "quota_exceeded"
    MODEL_UNAVAILABLE = "model_unavailable"
    CIRCUIT_OPEN = "circuit_open"


class ProviderStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    CIRCUIT_OPEN = "circuit_open"


@dataclass
class ProviderConfig:
    name: str
    priority: int = 0
    weight: int = 1
    max_retries: int = 3
    timeout: float = 30.0
    rate_limit: float = 100.0
    models: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMRequest:
    request_id: str
    prompt: str
    model: str = ""
    max_tokens: int = 1000
    temperature: float = 0.7
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    request_id: str
    text: str
    model: str
    provider: str
    usage: Dict[str, int] = field(default_factory=dict)
    latency: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderState:
    config: ProviderConfig
    status: ProviderStatus = ProviderStatus.HEALTHY
    consecutive_failures: int = 0
    last_success: float = 0
    last_failure: float = 0
    total_requests: int = 0
    total_errors: int = 0
    circuit_open_until: float = 0


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure = 0
        self.state = "closed"

    def record_success(self):
        self.failures = 0
        self.state = "closed"

    def record_failure(self):
        self.failures += 1
        self.last_failure = time.time()
        if self.failures >= self.failure_threshold:
            self.state = "open"

    def can_execute(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.time() - self.last_failure >= self.recovery_timeout:
                self.state = "half_open"
                return True
            return False
        return True


class LLMFallbackGateway:
    def __init__(self):
        self.providers: Dict[str, ProviderState] = {}
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.handlers: Dict[str, Callable] = {}
        self._lock = asyncio.Lock()
        self.request_history: List[Dict] = []

    def register_provider(self, config: ProviderConfig, handler: Callable):
        self.providers[config.name] = ProviderState(config=config)
        self.handlers[config.name] = handler
        self.circuit_breakers[config.name] = CircuitBreaker()

    def unregister_provider(self, name: str) -> bool:
        if name in self.providers:
            del self.providers[name]
            del self.handlers[name]
            del self.circuit_breakers[name]
            return True
        return False

    async def complete(self, request: LLMRequest) -> LLMResponse:
        providers = self._get_available_providers(request.model)
        
        if not providers:
            raise RuntimeError("No available providers")
        
        last_error = None
        for provider_name in providers:
            provider = self.providers[provider_name]
            cb = self.circuit_breakers[provider_name]
            
            if not cb.can_execute():
                continue
            
            if provider.status == ProviderStatus.CIRCUIT_OPEN:
                continue
            
            try:
                handler = self.handlers[provider_name]
                start = time.time()
                
                if asyncio.iscoroutinefunction(handler):
                    result = await asyncio.wait_for(
                        handler(request),
                        timeout=provider.config.timeout,
                    )
                else:
                    result = await asyncio.get_event_loop().run_in_executor(
                        None, handler, request
                    )
                
                latency = time.time() - start
                
                if isinstance(result, LLMResponse):
                    response = result
                else:
                    response = LLMResponse(
                        request_id=request.request_id,
                        text=str(result),
                        model=request.model,
                        provider=provider_name,
                        latency=latency,
                    )
                
                response.provider = provider_name
                response.latency = latency
                
                provider.consecutive_failures = 0
                provider.last_success = time.time()
                provider.total_requests += 1
                cb.record_success()
                
                self._record_request(request, response, provider_name, True)
                return response
                
            except asyncio.TimeoutError:
                last_error = "timeout"
                provider.consecutive_failures += 1
                provider.total_errors += 1
                cb.record_failure()
            except Exception as e:
                last_error = str(e)
                provider.consecutive_failures += 1
                provider.total_errors += 1
                cb.record_failure()
            
            if provider.consecutive_failures >= provider.config.max_retries:
                provider.status = ProviderStatus.CIRCUIT_OPEN
                provider.circuit_open_until = time.time() + 300
            
            self._record_request(request, None, provider_name, False, last_error)
        
        raise RuntimeError(f"All providers failed: {last_error}")

    def _get_available_providers(self, model: str) -> List[str]:
        available = []
        for name, state in self.providers.items():
            if state.status == ProviderStatus.UNAVAILABLE:
                continue
            if model and model not in state.config.models and state.config.models:
                continue
            if self.circuit_breakers[name].can_execute():
                available.append(name)
        
        available.sort(key=lambda n: -self.providers[n].config.priority)
        return available

    def _record_request(self, request: LLMRequest, response: LLMResponse, provider: str, success: bool, error: str = None):
        self.request_history.append({
            "request_id": request.request_id,
            "provider": provider,
            "model": request.model,
            "success": success,
            "error": error,
            "timestamp": time.time(),
        })
        if len(self.request_history) > 10000:
            self.request_history = self.request_history[-10000:]

    def get_provider_status(self, name: str) -> Optional[ProviderState]:
        return self.providers.get(name)

    def get_all_status(self) -> Dict[str, ProviderState]:
        return dict(self.providers)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_providers": len(self.providers),
            "healthy": sum(1 for p in self.providers.values() if p.status == ProviderStatus.HEALTHY),
            "total_requests": sum(p.total_requests for p in self.providers.values()),
            "total_errors": sum(p.total_errors for p in self.providers.values()),
            "recent_requests": len(self.request_history),
        }


class LoadBalancedGateway(LLMFallbackGateway):
    def _get_available_providers(self, model: str) -> List[str]:
        available = super()._get_available_providers(model)
        if not available:
            return available
        
        weighted = []
        for name in available:
            state = self.providers[name]
            for _ in range(state.config.weight):
                weighted.append(name)
        
        if not weighted:
            return available
        
        random.shuffle(weighted)
        return weighted


class StreamingGateway(LLMFallbackGateway):
    async def stream(self, request: LLMRequest):
        providers = self._get_available_providers(request.model)
        
        for provider_name in providers:
            provider = self.providers[provider_name]
            cb = self.circuit_breakers[provider_name]
            
            if not cb.can_execute() or provider.status == ProviderStatus.CIRCUIT_OPEN:
                continue
            
            try:
                handler = self.handlers[provider_name]
                if hasattr(handler, 'stream'):
                    async for chunk in handler.stream(request):
                        yield chunk
                    return
            except Exception:
                provider.consecutive_failures += 1
                provider.total_errors += 1
                cb.record_failure()
                if provider.consecutive_failures >= provider.config.max_retries:
                    provider.status = ProviderStatus.CIRCUIT_OPEN
                continue
        
        raise RuntimeError("All streaming providers failed")


class CacheLayer:
    def __init__(self, max_size: int = 1000, ttl: float = 3600):
        self.max_size = max_size
        self.ttl = ttl
        self.cache: Dict[str, tuple] = {}
        self._lock = asyncio.Lock()

    def _make_key(self, request: LLMRequest) -> str:
        return hashlib.md5(f"{request.prompt}:{request.model}:{request.max_tokens}:{request.temperature}".encode()).hexdigest()

    async def get(self, request: LLMRequest) -> Optional[LLMResponse]:
        key = self._make_key(request)
        async with self._lock:
            if key in self.cache:
                response, timestamp = self.cache[key]
                if time.time() - timestamp < self.ttl:
                    response.metadata["cached"] = True
                    return response
                del self.cache[key]
        return None

    async def set(self, request: LLMRequest, response: LLMResponse):
        key = self._make_key(request)
        async with self._lock:
            if len(self.cache) >= self.max_size:
                oldest = min(self.cache.items(), key=lambda x: x[1][1])[0]
                del self.cache[oldest]
            self.cache[key] = (response, time.time())

    async def invalidate(self, request: LLMRequest):
        key = self._make_key(request)
        async with self._lock:
            self.cache.pop(key, None)


class CachedGateway(LLMFallbackGateway):
    def __init__(self):
        super().__init__()
        self.cache = CacheLayer()

    async def complete(self, request: LLMRequest) -> LLMResponse:
        cached = await self.cache.get(request)
        if cached:
            return cached
        
        response = await super().complete(request)
        await self.cache.set(request, response)
        return response