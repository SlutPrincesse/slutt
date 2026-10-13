"""
Telemetry Monitor - Deployment telemetry and monitoring
"""
import asyncio
import time
import hashlib
from typing import Dict, List, Optional, Any, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import statistics


class MetricType(Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Metric:
    name: str
    metric_type: MetricType
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.metric_type.value,
            "value": self.value,
            "labels": self.labels,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class Alert:
    alert_id: str
    name: str
    severity: AlertSeverity
    message: str
    metric_name: str
    threshold: float
    current_value: float
    labels: Dict[str, str] = field(default_factory=dict)
    active: bool = True
    fired_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "name": self.name,
            "severity": self.severity.value,
            "message": self.message,
            "metric_name": self.metric_name,
            "threshold": self.threshold,
            "current_value": self.current_value,
            "labels": self.labels,
            "active": self.active,
            "fired_at": self.fired_at,
            "resolved_at": self.resolved_at,
            "metadata": self.metadata,
        }


@dataclass
class AlertRule:
    name: str
    metric_name: str
    condition: Callable[[float], bool]
    severity: AlertSeverity
    message: str
    threshold: float
    cooldown: float = 300.0
    labels: Dict[str, str] = field(default_factory=dict)
    last_fired: float = 0


class MetricsCollector:
    def __init__(self, max_history: int = 10000):
        self.max_history = max_history
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        self.current_values: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def record(self, metric: Metric):
        async with self._lock:
            key = self._make_key(metric.name, metric.labels)
            self.metrics[key].append(metric)
            self.current_values[key] = metric.value

    async def get_current(self, name: str, labels: Dict[str, str] = None) -> Optional[float]:
        key = self._make_key(name, labels or {})
        return self.current_values.get(key)

    async def get_history(
        self,
        name: str,
        labels: Dict[str, str] = None,
        limit: int = 100,
    ) -> List[Metric]:
        key = self._make_key(name, labels or {})
        history = list(self.metrics.get(key, []))
        return history[-limit:]

    async def get_stats(
        self,
        name: str,
        labels: Dict[str, str] = None,
        window: int = 100,
    ) -> Dict[str, float]:
        history = await self.get_history(name, labels, window)
        if not history:
            return {}
        
        values = [m.value for m in history]
        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "stdev": statistics.stdev(values) if len(values) > 1 else 0,
            "sum": sum(values),
        }

    def _make_key(self, name: str, labels: Dict[str, str]) -> str:
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"


class AlertManager:
    def __init__(self, collector: MetricsCollector):
        self.collector = collector
        self.rules: Dict[str, AlertRule] = {}
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: List[Alert] = []
        self._running = False
        self._check_task: Optional[asyncio.Task] = None
        self._callbacks: List[Callable] = []

    def add_rule(self, rule: AlertRule):
        self.rules[rule.name] = rule

    def remove_rule(self, name: str) -> bool:
        if name in self.rules:
            del self.rules[name]
            return True
        return False

    def on_alert(self, callback: Callable):
        self._callbacks.append(callback)

    async def start(self, check_interval: float = 10.0):
        self._running = True
        self._check_task = asyncio.create_task(self._check_loop(check_interval))

    async def stop(self):
        self._running = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass

    async def _check_loop(self, interval: float):
        while self._running:
            await self._evaluate_rules()
            await asyncio.sleep(interval)

    async def _evaluate_rules():
        for rule in self.rules.values():
            current = await self.collector.get_current(rule.metric_name)
            if current is None:
                continue
            
            if time.time() - rule.last_fired < rule.cooldown:
                continue
            
            try:
                if rule.condition(current):
                    await self._fire_alert(rule, current)
            except Exception:
                pass

    async def _fire_alert(self, rule: AlertRule, current_value: float):
        alert = Alert(
            alert_id=hashlib.md5(f"{rule.name}:{time.time()}".encode()).hexdigest()[:12],
            name=rule.name,
            severity=rule.severity,
            message=rule.message,
            metric_name=rule.metric_name,
            threshold=rule.threshold,
            current_value=current_value,
            labels=rule.labels,
        )
        
        self.active_alerts[alert.alert_id] = alert
        self.alert_history.append(alert)
        rule.last_fired = time.time()
        
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(alert)
                else:
                    callback(alert)
            except Exception:
                pass

    def get_active_alerts(self) -> List[Alert]:
        return list(self.active_alerts.values())

    def resolve_alert(self, alert_id: str) -> bool:
        if alert_id in self.active_alerts:
            alert = self.active_alerts[alert_id]
            alert.active = False
            alert.resolved_at = time.time()
            del self.active_alerts[alert_id]
            return True
        return False


class TelemetryMonitor:
    def __init__(self, max_history: int = 10000):
        self.collector = MetricsCollector(max_history)
        self.alert_manager = AlertManager(self.collector)
        self.deployment_metrics: Dict[str, Any] = {}

    async def record_metric(
        self,
        name: str,
        value: float,
        metric_type: MetricType = MetricType.GAUGE,
        labels: Dict[str, str] = None,
        metadata: Dict[str, Any] = None,
    ):
        metric = Metric(
            name=name,
            metric_type=metric_type,
            value=value,
            labels=labels or {},
            metadata=metadata or {},
        )
        await self.collector.record(metric)

    async def increment_counter(
        self,
        name: str,
        value: float = 1,
        labels: Dict[str, str] = None,
    ):
        await self.record_metric(name, value, MetricType.COUNTER, labels)

    async def set_gauge(
        self,
        name: str,
        value: float,
        labels: Dict[str, str] = None,
    ):
        await self.record_metric(name, value, MetricType.GAUGE, labels)

    async def observe_histogram(
        self,
        name: str,
        value: float,
        labels: Dict[str, str] = None,
    ):
        await self.record_metric(name, value, MetricType.HISTOGRAM, labels)

    def add_alert_rule(
        self,
        name: str,
        metric_name: str,
        condition: Callable[[float], bool],
        severity: AlertSeverity,
        message: str,
        threshold: float,
        cooldown: float = 300.0,
        labels: Dict[str, str] = None,
    ):
        rule = AlertRule(
            name=name,
            metric_name=metric_name,
            condition=condition,
            severity=severity,
            message=message,
            threshold=threshold,
            cooldown=cooldown,
            labels=labels or {},
        )
        self.alert_manager.add_rule(rule)

    def on_alert(self, callback: Callable):
        self.alert_manager.on_alert(callback)

    async def start(self, check_interval: float = 10.0):
        await self.alert_manager.start(check_interval)

    async def stop(self):
        await self.alert_manager.stop()

    async def get_metric_stats(
        self,
        name: str,
        labels: Dict[str, str] = None,
        window: int = 100,
    ) -> Dict[str, float]:
        return await self.collector.get_stats(name, labels, window)

    def get_active_alerts(self) -> List[Alert]:
        return self.alert_manager.get_active_alerts()

    def record_deployment_metric(self, deployment_id: str, metric: str, value: Any):
        if deployment_id not in self.deployment_metrics:
            self.deployment_metrics[deployment_id] = {}
        self.deployment_metrics[deployment_id][metric] = {
            "value": value,
            "timestamp": time.time(),
        }

    def get_deployment_metrics(self, deployment_id: str) -> Dict[str, Any]:
        return self.deployment_metrics.get(deployment_id, {})


class DeploymentTracker:
    def __init__(self, monitor: TelemetryMonitor):
        self.monitor = monitor
        self.deployments: Dict[str, Dict[str, Any]] = {}

    async def start_deployment(self, deployment_id: str, metadata: Dict[str, Any] = None):
        self.deployments[deployment_id] = {
            "id": deployment_id,
            "status": "running",
            "started_at": time.time(),
            "metadata": metadata or {},
            "steps": [],
        }
        await self.monitor.increment_counter("deployments_started", labels={"deployment_id": deployment_id})

    async def record_step(
        self,
        deployment_id: str,
        step_name: str,
        status: str,
        duration: float,
        metadata: Dict[str, Any] = None,
    ):
        if deployment_id in self.deployments:
            self.deployments[deployment_id]["steps"].append({
                "name": step_name,
                "status": status,
                "duration": duration,
                "timestamp": time.time(),
                "metadata": metadata or {},
            })
        
        await self.monitor.record_metric(
            "deployment_step_duration",
            duration,
            MetricType.HISTOGRAM,
            labels={"deployment_id": deployment_id, "step": step_name, "status": status},
        )

    async def complete_deployment(
        self,
        deployment_id: str,
        status: str = "success",
        metadata: Dict[str, Any] = None,
    ):
        if deployment_id in self.deployments:
            deployment = self.deployments[deployment_id]
            deployment["status"] = status
            deployment["completed_at"] = time.time()
            deployment["total_duration"] = deployment["completed_at"] - deployment["started_at"]
            if metadata:
                deployment["metadata"].update(metadata)
        
        await self.monitor.increment_counter(
            "deployments_completed",
            labels={"deployment_id": deployment_id, "status": status},
        )
        
        if deployment_id in self.deployments:
            total_duration = self.deployments[deployment_id].get("total_duration", 0)
            await self.monitor.record_metric(
                "deployment_total_duration",
                total_duration,
                MetricType.HISTOGRAM,
                labels={"deployment_id": deployment_id, "status": status},
            )

    def get_deployment(self, deployment_id: str) -> Optional[Dict[str, Any]]:
        return self.deployments.get(deployment_id)

    def list_deployments(self, status: str = None) -> List[Dict[str, Any]]:
        deployments = list(self.deployments.values())
        if status:
            deployments = [d for d in deployments if d["status"] == status]
        return deployments