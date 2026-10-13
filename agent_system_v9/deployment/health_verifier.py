"""
Health Verifier - Deployment health checks and validation
"""
import asyncio
import hashlib
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class CheckType(Enum):
    LIVENESS = "liveness"
    READINESS = "readiness"
    STARTUP = "startup"
    CUSTOM = "custom"


@dataclass
class HealthCheck:
    name: str
    check_type: CheckType
    handler: Callable
    timeout: float = 5.0
    interval: float = 30.0
    failure_threshold: int = 3
    success_threshold: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    async def execute(self) -> 'HealthCheckResult':
        start = time.time()
        try:
            if asyncio.iscoroutinefunction(self.handler):
                result = await asyncio.wait_for(self.handler(), timeout=self.timeout)
            else:
                result = self.handler()

            if isinstance(result, HealthCheckResult):
                return result

            return HealthCheckResult(
                check_name=self.name,
                status=HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY,
                duration=time.time() - start,
            )
        except asyncio.TimeoutError:
            return HealthCheckResult(
                check_name=self.name,
                status=HealthStatus.UNHEALTHY,
                duration=time.time() - start,
                error="Check timed out",
            )
        except Exception as e:
            return HealthCheckResult(
                check_name=self.name,
                status=HealthStatus.UNHEALTHY,
                duration=time.time() - start,
                error=str(e),
            )


@dataclass
class HealthCheckResult:
    check_name: str
    status: HealthStatus
    duration: float
    message: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_name": self.check_name,
            "status": self.status.value,
            "duration": self.duration,
            "message": self.message,
            "error": self.error,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


@dataclass
class ComponentHealth:
    name: str
    status: HealthStatus
    checks: list[HealthCheckResult] = field(default_factory=list)
    last_check: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "checks": [c.to_dict() for c in self.checks],
            "last_check": self.last_check,
            "metadata": self.metadata,
        }


class HealthVerifier:
    def __init__(self):
        self.checks: dict[str, HealthCheck] = {}
        self.component_health: dict[str, ComponentHealth] = {}
        self.history: list[dict[str, Any]] = []
        self._running = False
        self._check_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    def register_check(self, check: HealthCheck):
        self.checks[check.name] = check

    def unregister_check(self, name: str) -> bool:
        if name in self.checks:
            del self.checks[name]
            return True
        return False

    async def run_check(self, name: str) -> HealthCheckResult | None:
        check = self.checks.get(name)
        if not check:
            return None

        result = await check.execute()
        await self._record_result(name, result)
        return result

    async def run_all_checks(self, check_type: CheckType = None) -> dict[str, HealthCheckResult]:
        results = {}
        for name, check in self.checks.items():
            if check_type is None or check.check_type == check_type:
                results[name] = await self.run_check(name)
        return results

    async def _record_result(self, name: str, result: HealthCheckResult):
        async with self._lock:
            if name not in self.component_health:
                self.component_health[name] = ComponentHealth(name=name, status=HealthStatus.UNKNOWN)

            component = self.component_health[name]
            component.checks.append(result)
            component.last_check = time.time()

            if len(component.checks) > 100:
                component.checks = component.checks[-100:]

            healthy_count = sum(1 for c in component.checks[-check.failure_threshold:] if c.status == HealthStatus.HEALTHY)
            unhealthy_count = len(component.checks) - healthy_count

            if unhealthy_count >= check.failure_threshold:
                component.status = HealthStatus.UNHEALTHY
            elif healthy_count >= check.success_threshold:
                component.status = HealthStatus.HEALTHY
            else:
                component.status = HealthStatus.DEGRADED

            self.history.append({
                "check_name": name,
                "result": result.to_dict(),
                "component_status": component.status.value,
                "timestamp": time.time(),
            })

            if len(self.history) > 1000:
                self.history = self.history[-1000:]

    async def start_periodic_checks(self, interval: float = 30.0):
        self._running = True
        self._check_task = asyncio.create_task(self._periodic_check_loop(interval))

    async def stop_periodic_checks(self):
        self._running = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass

    async def _periodic_check_loop(self, interval: float):
        while self._running:
            await self.run_all_checks()
            await asyncio.sleep(interval)

    def get_overall_health(self) -> HealthStatus:
        if not self.component_health:
            return HealthStatus.UNKNOWN

        statuses = [c.status for c in self.component_health.values()]
        if all(s == HealthStatus.HEALTHY for s in statuses):
            return HealthStatus.HEALTHY
        if any(s == HealthStatus.UNHEALTHY for s in statuses):
            return HealthStatus.UNHEALTHY
        return HealthStatus.DEGRADED

    def get_component_health(self, name: str) -> ComponentHealth | None:
        return self.component_health.get(name)

    def get_all_health(self) -> dict[str, ComponentHealth]:
        return dict(self.component_health)

    def get_history(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.history[-limit:]


class DependencyChecker:
    def __init__(self, verifier: HealthVerifier):
        self.verifier = verifier
        self.dependencies: dict[str, list[str]] = defaultdict(list)

    def add_dependency(self, component: str, depends_on: str):
        self.dependencies[component].append(depends_on)

    async def check_dependencies(self, component: str) -> bool:
        for dep in self.dependencies.get(component, []):
            dep_health = self.verifier.get_component_health(dep)
            if not dep_health or dep_health.status != HealthStatus.HEALTHY:
                return False
        return True

    def get_dependency_graph(self) -> dict[str, list[str]]:
        return dict(self.dependencies)


class HealthEndpoint:
    def __init__(self, verifier: HealthVerifier):
        self.verifier = verifier

    async def liveness(self) -> dict[str, Any]:
        results = await self.verifier.run_all_checks(CheckType.LIVENESS)
        return {
            "status": self.verifier.get_overall_health().value,
            "checks": {k: v.to_dict() for k, v in results.items()},
        }

    async def readiness(self) -> dict[str, Any]:
        results = await self.verifier.run_all_checks(CheckType.READINESS)
        return {
            "status": self.verifier.get_overall_health().value,
            "checks": {k: v.to_dict() for k, v in results.items()},
        }

    async def startup(self) -> dict[str, Any]:
        results = await self.verifier.run_all_checks(CheckType.STARTUP)
        return {
            "status": self.verifier.get_overall_health().value,
            "checks": {k: v.to_dict() for k, v in results.items()},
        }

    async def full_health(self) -> dict[str, Any]:
        results = await self.verifier.run_all_checks()
        return {
            "status": self.verifier.get_overall_health().value,
            "components": {k: v.to_dict() for k, v in self.verifier.get_all_health().items()},
            "checks": {k: v.to_dict() for k, v in results.items()},
        }


def create_http_check(url: str, expected_status: int = 200) -> HealthCheck:
    async def handler():
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as resp:
                    return resp.status == expected_status
        except Exception:
            return False

    return HealthCheck(
        name=f"http_{hashlib.md5(url.encode()).hexdigest()[:8]}",
        check_type=CheckType.READINESS,
        handler=handler,
    )


def create_tcp_check(host: str, port: int) -> HealthCheck:
    async def handler():
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=5
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False

    return HealthCheck(
        name=f"tcp_{host}_{port}",
        check_type=CheckType.READINESS,
        handler=handler,
    )


def create_disk_check(path: str, min_free_gb: float = 1.0) -> HealthCheck:
    def handler():
        import shutil
        total, used, free = shutil.disk_usage(path)
        return (free / (1024**3)) >= min_free_gb

    return HealthCheck(
        name=f"disk_{path.replace('/', '_')}",
        check_type=CheckType.LIVENESS,
        handler=handler,
    )


def create_memory_check(max_percent: float = 90.0) -> HealthCheck:
    def handler():
        import psutil
        mem = psutil.virtual_memory()
        return mem.percent < max_percent

    return HealthCheck(
        name="memory",
        check_type=CheckType.LIVENESS,
        handler=handler,
    )
