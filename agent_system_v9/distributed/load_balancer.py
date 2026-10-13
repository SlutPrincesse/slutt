"""
Load Balancer - Distributed load balancing strategies
"""
import asyncio
import hashlib
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LoadBalancingAlgorithm(Enum):
    ROUND_ROBIN = "round_robin"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    LEAST_CONNECTIONS = "least_connections"
    WEIGHTED_LEAST_CONNECTIONS = "weighted_least_connections"
    IP_HASH = "ip_hash"
    CONSISTENT_HASH = "consistent_hash"
    LEAST_RESPONSE_TIME = "least_response_time"
    ADAPTIVE = "adaptive"


class BackendStatus(Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DRAINING = "draining"
    MAINTENANCE = "maintenance"


@dataclass
class Backend:
    backend_id: str
    host: str
    port: int
    weight: int = 1
    max_connections: int = 100
    status: BackendStatus = BackendStatus.HEALTHY
    current_connections: int = 0
    total_requests: int = 0
    total_errors: int = 0
    avg_response_time: float = 0.0
    last_health_check: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def is_available(self) -> bool:
        return self.status == BackendStatus.HEALTHY and self.current_connections < self.max_connections

    @property
    def load_factor(self) -> float:
        if self.max_connections == 0:
            return 1.0
        return self.current_connections / self.max_connections


@dataclass
class LoadBalancerConfig:
    algorithm: LoadBalancingAlgorithm = LoadBalancingAlgorithm.LEAST_CONNECTIONS
    health_check_interval: float = 10.0
    health_check_timeout: float = 5.0
    health_check_path: str = "/health"
    unhealthy_threshold: int = 3
    healthy_threshold: int = 2
    sticky_sessions: bool = False
    session_cookie: str = "lb_session"
    max_retries: int = 3
    retry_interval: float = 1.0


class HealthChecker:
    def __init__(self, config: LoadBalancerConfig):
        self.config = config
        self.checks: dict[str, deque] = defaultdict(lambda: deque(maxlen=10))
        self._lock = threading.RLock()

    def record_check(self, backend_id: str, success: bool, response_time: float = 0):
        with self._lock:
            self.checks[backend_id].append({
                "success": success,
                "response_time": response_time,
                "timestamp": time.time(),
            })

    def get_status(self, backend_id: str) -> BackendStatus:
        with self._lock:
            checks = self.checks.get(backend_id, [])
            if not checks:
                return BackendStatus.HEALTHY

            recent = list(checks)[-self.config.unhealthy_threshold:]
            if all(not c["success"] for c in recent):
                return BackendStatus.UNHEALTHY

            recent_healthy = list(checks)[-self.config.healthy_threshold:]
            if all(c["success"] for c in recent_healthy):
                return BackendStatus.HEALTHY

            return BackendStatus.UNHEALTHY

    def get_avg_response_time(self, backend_id: str) -> float:
        with self._lock:
            checks = self.checks.get(backend_id, [])
            if not checks:
                return 0.0
            successful = [c["response_time"] for c in checks if c["success"]]
            return sum(successful) / len(successful) if successful else 0.0


class LoadBalancer:
    def __init__(
        self,
        config: LoadBalancerConfig | None = None,
        backends: list[Backend] = None,
    ):
        self.config = config or LoadBalancerConfig()
        self.backends: dict[str, Backend] = {}
        self.health_checker = HealthChecker(self.config)
        self._rr_index = 0
        self._wrr_weights: dict[str, int] = {}
        self._wrr_current: dict[str, int] = {}
        self._consistent_hash_ring: list[tuple] = []
        self._lock = threading.RLock()
        self._running = False
        self._health_check_task: asyncio.Task | None = None

        if backends:
            for backend in backends:
                self.add_backend(backend)

    def add_backend(self, backend: Backend):
        with self._lock:
            self.backends[backend.backend_id] = backend
            self._update_weighted_round_robin()
            self._rebuild_consistent_hash_ring()

    def remove_backend(self, backend_id: str) -> bool:
        with self._lock:
            if backend_id in self.backends:
                del self.backends[backend_id]
                self._update_weighted_round_robin()
                self._rebuild_consistent_hash_ring()
                return True
        return False

    def get_backend(self, backend_id: str) -> Backend | None:
        with self._lock:
            return self.backends.get(backend_id)

    def list_backends(self) -> list[Backend]:
        with self._lock:
            return list(self.backends.values())

    def _update_weighted_round_robin(self):
        self._wrr_weights = {b.backend_id: b.weight for b in self.backends.values()}
        self._wrr_current = {b.backend_id: 0 for b in self.backends.values()}

    def _rebuild_consistent_hash_ring(self):
        self._consistent_hash_ring = []
        for backend in self.backends.values():
            if backend.is_available:
                for i in range(backend.weight * 100):
                    key = hashlib.md5(f"{backend.backend_id}:{i}".encode()).hexdigest()
                    self._consistent_hash_ring.append((key, backend.backend_id))
        self._consistent_hash_ring.sort(key=lambda x: x[0])

    def select_backend(self, client_ip: str = None, session_id: str = None) -> Backend | None:
        with self._lock:
            available = [b for b in self.backends.values() if b.is_available]
            if not available:
                return None

            if self.config.sticky_sessions and session_id:
                backend = self._get_sticky_backend(session_id)
                if backend and backend.is_available:
                    return backend

            if self.config.algorithm == LoadBalancingAlgorithm.ROUND_ROBIN:
                return self._round_robin(available)
            if self.config.algorithm == LoadBalancingAlgorithm.WEIGHTED_ROUND_ROBIN:
                return self._weighted_round_robin(available)
            if self.config.algorithm == LoadBalancingAlgorithm.LEAST_CONNECTIONS:
                return self._least_connections(available)
            if self.config.algorithm == LoadBalancingAlgorithm.WEIGHTED_LEAST_CONNECTIONS:
                return self._weighted_least_connections(available)
            if self.config.algorithm == LoadBalancingAlgorithm.IP_HASH:
                return self._ip_hash(available, client_ip)
            if self.config.algorithm == LoadBalancingAlgorithm.CONSISTENT_HASH:
                return self._consistent_hash(available, client_ip or session_id or "")
            if self.config.algorithm == LoadBalancingAlgorithm.LEAST_RESPONSE_TIME:
                return self._least_response_time(available)
            if self.config.algorithm == LoadBalancingAlgorithm.ADAPTIVE:
                return self._adaptive(available)

            return available[0]

    def _round_robin(self, available: list[Backend]) -> Backend:
        backend = available[self._rr_index % len(available)]
        self._rr_index += 1
        return backend

    def _weighted_round_robin(self, available: list[Backend]) -> Backend:
        max_score = -1
        selected = None
        for backend in available:
            bid = backend.backend_id
            self._wrr_current[bid] += self._wrr_weights[bid]
            if self._wrr_current[bid] > max_score:
                max_score = self._wrr_current[bid]
                selected = backend
        if selected:
            self._wrr_current[selected.backend_id] -= sum(self._wrr_weights.values())
        return selected

    def _least_connections(self, available: list[Backend]) -> Backend:
        return min(available, key=lambda b: b.current_connections)

    def _weighted_least_connections(self, available: list[Backend]) -> Backend:
        return min(available, key=lambda b: b.current_connections / max(b.weight, 1))

    def _ip_hash(self, available: list[Backend], client_ip: str) -> Backend:
        if not client_ip:
            return available[0]
        hash_val = int(hashlib.md5(client_ip.encode()).hexdigest(), 16)
        return available[hash_val % len(available)]

    def _consistent_hash(self, available: list[Backend], key: str) -> Backend:
        if not self._consistent_hash_ring:
            return available[0]

        hash_val = hashlib.md5(key.encode()).hexdigest()
        for ring_key, backend_id in self._consistent_hash_ring:
            if ring_key >= hash_val:
                backend = self.backends.get(backend_id)
                if backend and backend.is_available:
                    return backend

        return self.backends.get(self._consistent_hash_ring[0][1]) or available[0]

    def _least_response_time(self, available: list[Backend]) -> Backend:
        return min(available, key=lambda b: self.health_checker.get_avg_response_time(b.backend_id))

    def _adaptive(self, available: list[Backend]) -> Backend:
        def score(b: Backend) -> float:
            load = b.current_connections / max(b.max_connections, 1)
            rt = self.health_checker.get_avg_response_time(b.backend_id)
            error_rate = b.total_errors / max(b.total_requests, 1)
            return load * 0.4 + (rt / 1000) * 0.3 + error_rate * 0.3

        return min(available, key=score)

    def _get_sticky_backend(self, session_id: str) -> Backend | None:
        hash_val = int(hashlib.md5(session_id.encode()).hexdigest(), 16)
        available = [b for b in self.backends.values() if b.is_available]
        if not available:
            return None
        return available[hash_val % len(available)]

    def record_request(self, backend_id: str, success: bool, response_time: float):
        with self._lock:
            backend = self.backends.get(backend_id)
            if backend:
                backend.total_requests += 1
                if not success:
                    backend.total_errors += 1
                backend.avg_response_time = (
                    (backend.avg_response_time * (backend.total_requests - 1) + response_time)
                    / backend.total_requests
                )
                self.health_checker.record_check(backend_id, success, response_time)

    def acquire_connection(self, backend_id: str) -> bool:
        with self._lock:
            backend = self.backends.get(backend_id)
            if backend and backend.is_available:
                backend.current_connections += 1
                return True
        return False

    def release_connection(self, backend_id: str):
        with self._lock:
            backend = self.backends.get(backend_id)
            if backend:
                backend.current_connections = max(0, backend.current_connections - 1)

    async def start_health_checks(self):
        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())

    async def stop_health_checks(self):
        self._running = False
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

    async def _health_check_loop(self):
        while self._running:
            await asyncio.sleep(self.config.health_check_interval)
            await self._perform_health_checks()

    async def _perform_health_checks(self):
        for backend in list(self.backends.values()):
            if backend.status == BackendStatus.MAINTENANCE:
                continue

            try:
                success = await self._check_backend_health(backend)
                new_status = self.health_checker.get_status(backend.backend_id)
                if new_status != backend.status:
                    backend.status = new_status
                    self._rebuild_consistent_hash_ring()
            except Exception:
                self.health_checker.record_check(backend.backend_id, False)

    async def _check_backend_health(self, backend: Backend) -> bool:
        start = time.time()
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(backend.host, backend.port),
                timeout=self.config.health_check_timeout,
            )
            writer.close()
            await writer.wait_closed()
            response_time = time.time() - start
            self.health_checker.record_check(backend.backend_id, True, response_time)
            return True
        except Exception:
            return False

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "algorithm": self.config.algorithm.value,
                "total_backends": len(self.backends),
                "healthy_backends": sum(1 for b in self.backends.values() if b.status == BackendStatus.HEALTHY),
                "total_requests": sum(b.total_requests for b in self.backends.values()),
                "total_errors": sum(b.total_errors for b in self.backends.values()),
                "backends": {
                    b.backend_id: {
                        "address": b.address,
                        "weight": b.weight,
                        "status": b.status.value,
                        "connections": b.current_connections,
                        "requests": b.total_requests,
                        "errors": b.total_errors,
                        "avg_response_time": b.avg_response_time,
                    }
                    for b in self.backends.values()
                },
            }


class CircuitBreaker:
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
        self._lock = threading.RLock()

    def record_success(self):
        with self._lock:
            if self.state == "half_open":
                self.successes += 1
                if self.successes >= self.half_open_requests:
                    self.state = "closed"
                    self.failures = 0
                    self.successes = 0
            else:
                self.failures = 0

    def record_failure(self):
        with self._lock:
            self.failures += 1
            self.last_failure_time = time.time()
            if self.state == "half_open":
                self.state = "open"
                self.successes = 0
            elif self.failures >= self.failure_threshold:
                self.state = "open"

    def can_execute(self) -> bool:
        with self._lock:
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

    def get_state(self) -> str:
        with self._lock:
            return self.state
