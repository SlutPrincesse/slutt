"""
Canary Guard - Canary deployment and progressive rollout
"""
import asyncio
import hashlib
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CanaryPhase(Enum):
    INITIAL = "initial"
    CANARY = "canary"
    PROGRESSIVE = "progressive"
    FULL = "full"
    ROLLBACK = "rollback"
    COMPLETE = "complete"


class TrafficSplitStrategy(Enum):
    FIXED = "fixed"
    GRADUAL = "gradual"
    EXPONENTIAL = "exponential"
    CUSTOM = "custom"


@dataclass
class CanaryConfig:
    initial_traffic_percent: float = 5.0
    max_traffic_percent: float = 100.0
    step_increment: float = 10.0
    step_duration: float = 300.0
    success_threshold: float = 0.99
    error_rate_threshold: float = 0.01
    latency_p99_threshold: float = 1000.0
    min_samples: int = 100
    strategy: TrafficSplitStrategy = TrafficSplitStrategy.GRADUAL
    auto_promote: bool = True
    auto_rollback: bool = True


@dataclass
class ServiceVersion:
    version: str
    image: str
    config: dict[str, Any] = field(default_factory=dict)
    replicas: int = 1
    healthy: bool = True


@dataclass
class CanaryMetrics:
    version: str
    requests: int = 0
    errors: int = 0
    latencies: list[float] = field(default_factory=list)
    error_rate: float = 0.0
    p50_latency: float = 0.0
    p95_latency: float = 0.0
    p99_latency: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def add_request(self, latency: float, error: bool = False):
        self.requests += 1
        if error:
            self.errors += 1
        self.latencies.append(latency)
        self.error_rate = self.errors / max(self.requests, 1)
        if self.latencies:
            sorted_lat = sorted(self.latencies)
            self.p50_latency = sorted_lat[len(sorted_lat) // 2]
            self.p95_latency = sorted_lat[int(len(sorted_lat) * 0.95)]
            self.p99_latency = sorted_lat[int(len(sorted_lat) * 0.99)]


@dataclass
class CanaryDeployment:
    deployment_id: str
    service_name: str
    current_version: ServiceVersion
    canary_version: ServiceVersion
    config: CanaryConfig
    phase: CanaryPhase = CanaryPhase.INITIAL
    traffic_split: float = 0.0
    current_metrics: CanaryMetrics | None = None
    canary_metrics: CanaryMetrics | None = None
    started_at: float = field(default_factory=time.time)
    phase_started_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class TrafficRouter:
    def __init__(self):
        self.routes: dict[str, dict[str, float]] = {}

    def set_split(self, service: str, versions: dict[str, float]):
        total = sum(versions.values())
        if total > 0:
            self.routes[service] = {k: v / total for k, v in versions.items()}
        else:
            self.routes[service] = {}

    def get_split(self, service: str) -> dict[str, float]:
        return self.routes.get(service, {})

    def route_request(self, service: str) -> str:
        split = self.get_split(service)
        if not split:
            return "current"

        rand = random.random()
        cumulative = 0.0
        for version, weight in split.items():
            cumulative += weight
            if rand <= cumulative:
                return version
        return list(split.keys())[0] if split else "current"


class MetricsCollector:
    def __init__(self):
        self.metrics: dict[str, CanaryMetrics] = {}

    def record(self, deployment_id: str, version: str, latency: float, error: bool = False):
        key = f"{deployment_id}:{version}"
        if key not in self.metrics:
            self.metrics[key] = CanaryMetrics(version=version)
        self.metrics[key].add_request(latency, error)

    def get_metrics(self, deployment_id: str, version: str) -> CanaryMetrics | None:
        return self.metrics.get(f"{deployment_id}:{version}")

    def get_all_metrics(self, deployment_id: str) -> dict[str, CanaryMetrics]:
        return {k: v for k, v in self.metrics.items() if k.startswith(f"{deployment_id}:")}


class CanaryGuard:
    def __init__(self, router: TrafficRouter = None, collector: MetricsCollector = None):
        self.router = router or TrafficRouter()
        self.collector = collector or MetricsCollector()
        self.deployments: dict[str, CanaryDeployment] = {}
        self._running = False
        self._monitor_task: asyncio.Task | None = None
        self._callbacks: list[Callable] = []

    def on_phase_change(self, callback: Callable):
        self._callbacks.append(callback)

    async def start_canary(
        self,
        service_name: str,
        current_version: ServiceVersion,
        canary_version: ServiceVersion,
        config: CanaryConfig = None,
    ) -> CanaryDeployment:
        deployment = CanaryDeployment(
            deployment_id=hashlib.md5(f"{service_name}:{time.time()}".encode()).hexdigest()[:12],
            service_name=service_name,
            current_version=current_version,
            canary_version=canary_version,
            config=config or CanaryConfig(),
        )

        deployment.phase = CanaryPhase.CANARY
        deployment.traffic_split = deployment.config.initial_traffic_percent / 100.0

        self.router.set_split(service_name, {
            current_version.version: 1.0 - deployment.traffic_split,
            canary_version.version: deployment.traffic_split,
        })

        deployment.current_metrics = CanaryMetrics(version=current_version.version)
        deployment.canary_metrics = CanaryMetrics(version=canary_version.version)

        self.deployments[deployment.deployment_id] = deployment
        await self._notify_phase_change(deployment)

        if self.config.auto_promote:
            await self.start_monitoring()

        return deployment

    async def start_monitoring(self):
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop_monitoring(self):
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

    async def _monitor_loop(self):
        while self._running:
            for deployment in list(self.deployments.values()):
                await self._check_deployment(deployment)
            await asyncio.sleep(10)

    async def _check_deployment(self, deployment: CanaryDeployment):
        current_metrics = self.collector.get_metrics(deployment.deployment_id, deployment.current_version.version)
        canary_metrics = self.collector.get_metrics(deployment.deployment_id, deployment.canary_version.version)

        if current_metrics:
            deployment.current_metrics = current_metrics
        if canary_metrics:
            deployment.canary_metrics = canary_metrics

        if deployment.phase == CanaryPhase.CANARY:
            await self._check_canary_phase(deployment)
        elif deployment.phase == CanaryPhase.PROGRESSIVE:
            await self._check_progressive_phase(deployment)

    async def _check_canary_phase(self, deployment: CanaryDeployment):
        canary = deployment.canary_metrics
        if not canary or canary.requests < deployment.config.min_samples:
            return

        if canary.error_rate > deployment.config.error_rate_threshold:
            await self._rollback(deployment, f"Error rate {canary.error_rate:.2%} exceeds threshold")
            return

        if canary.p99_latency > deployment.config.latency_p99_threshold:
            await self._rollback(deployment, f"P99 latency {canary.p99_latency:.0f}ms exceeds threshold")
            return

        if canary.error_rate <= deployment.config.error_rate_threshold * 0.5:
            await self._promote_to_progressive(deployment)

    async def _check_progressive_phase(self, deployment: CanaryDeployment):
        canary = deployment.canary_metrics
        if not canary:
            return

        if deployment.traffic_split >= deployment.config.max_traffic_percent / 100.0:
            await self._complete(deployment)
            return

        if canary.error_rate > deployment.config.error_rate_threshold:
            await self._rollback(deployment, f"Error rate increased to {canary.error_rate:.2%}")
            return

        if time.time() - deployment.phase_started_at >= deployment.config.step_duration:
            await self._increase_traffic(deployment)

    async def _promote_to_progressive(self, deployment: CanaryDeployment):
        deployment.phase = CanaryPhase.PROGRESSIVE
        deployment.phase_started_at = time.time()
        await self._increase_traffic(deployment)
        await self._notify_phase_change(deployment)

    async def _increase_traffic(self, deployment: CanaryDeployment):
        new_split = min(
            deployment.traffic_split + deployment.config.step_increment / 100.0,
            deployment.config.max_traffic_percent / 100.0,
        )

        deployment.traffic_split = new_split

        self.router.set_split(deployment.service_name, {
            deployment.current_version.version: 1.0 - new_split,
            deployment.canary_version.version: new_split,
        })

        deployment.phase_started_at = time.time()

    async def _complete(self, deployment: CanaryDeployment):
        deployment.phase = CanaryPhase.COMPLETE
        deployment.traffic_split = 1.0

        self.router.set_split(deployment.service_name, {
            deployment.canary_version.version: 1.0,
        })

        deployment.current_version = deployment.canary_version
        await self._notify_phase_change(deployment)

    async def _rollback(self, deployment: CanaryDeployment, reason: str):
        deployment.phase = CanaryPhase.ROLLBACK
        deployment.traffic_split = 0.0

        self.router.set_split(deployment.service_name, {
            deployment.current_version.version: 1.0,
        })

        deployment.metadata["rollback_reason"] = reason
        await self._notify_phase_change(deployment)

    async def _notify_phase_change(self, deployment: CanaryDeployment):
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(deployment)
                else:
                    callback(deployment)
            except Exception:
                pass

    def record_request(self, deployment_id: str, version: str, latency: float, error: bool = False):
        self.collector.record(deployment_id, version, latency, error)

    def get_deployment(self, deployment_id: str) -> CanaryDeployment | None:
        return self.deployments.get(deployment_id)

    def get_status(self, deployment_id: str) -> dict[str, Any]:
        deployment = self.deployments.get(deployment_id)
        if not deployment:
            return {}

        return {
            "deployment_id": deployment.deployment_id,
            "service_name": deployment.service_name,
            "phase": deployment.phase.value,
            "traffic_split": deployment.traffic_split,
            "current_version": deployment.current_version.version,
            "canary_version": deployment.canary_version.version,
            "current_metrics": {
                "requests": deployment.current_metrics.requests if deployment.current_metrics else 0,
                "error_rate": deployment.current_metrics.error_rate if deployment.current_metrics else 0,
            } if deployment.current_metrics else {},
            "canary_metrics": {
                "requests": deployment.canary_metrics.requests if deployment.canary_metrics else 0,
                "error_rate": deployment.canary_metrics.error_rate if deployment.canary_metrics else 0,
                "p99_latency": deployment.canary_metrics.p99_latency if deployment.canary_metrics else 0,
            } if deployment.canary_metrics else {},
        }


class ProgressiveRollout:
    def __init__(self, guard: CanaryGuard):
        self.guard = guard

    async def rollout(
        self,
        service_name: str,
        versions: list[ServiceVersion],
        config: CanaryConfig,
    ) -> list[CanaryDeployment]:
        deployments = []
        current = versions[0]

        for canary in versions[1:]:
            deployment = await self.guard.start_canary(service_name, current, canary, config)
            deployments.append(deployment)

            while deployment.phase not in (CanaryPhase.COMPLETE, CanaryPhase.ROLLBACK):
                await asyncio.sleep(5)

            if deployment.phase == CanaryPhase.ROLLBACK:
                break

            current = canary

        return deployments


class FeatureFlagCanary:
    def __init__(self, guard: CanaryGuard):
        self.guard = guard
        self.flags: dict[str, dict[str, Any]] = {}

    def set_flag(self, flag_name: str, enabled_for: dict[str, float]):
        self.flags[flag_name] = enabled_for

    def is_enabled(self, flag_name: str, context: dict[str, Any]) -> bool:
        flag = self.flags.get(flag_name)
        if not flag:
            return False

        user_id = context.get("user_id", "")
        hash_val = int(hashlib.md5(f"{flag_name}:{user_id}".encode()).hexdigest(), 16)
        percentile = (hash_val % 100) / 100.0

        for version, weight in flag.items():
            if percentile < weight:
                return True
            percentile -= weight

        return False
