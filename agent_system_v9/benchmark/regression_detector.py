"""
Regression Detector - Detects performance and functional regressions
"""
import hashlib
import time
import statistics
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from collections import defaultdict
import json


class RegressionType(Enum):
    PERFORMANCE = "performance"
    FUNCTIONAL = "functional"
    MEMORY = "memory"
    ACCURACY = "accuracy"


class Severity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class BenchmarkResult:
    benchmark_id: str
    name: str
    value: float
    unit: str
    timestamp: float = field(default_factory=time.time)
    commit_hash: str = ""
    branch: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "timestamp": self.timestamp,
            "commit_hash": self.commit_hash,
            "branch": self.branch,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BenchmarkResult':
        return cls(**data)


@dataclass
class Regression:
    regression_id: str
    regression_type: RegressionType
    severity: Severity
    benchmark_name: str
    current_value: float
    baseline_value: float
    change_percent: float
    threshold_percent: float
    commit_hash: str = ""
    detected_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "regression_id": self.regression_id,
            "regression_type": self.regression_type.value,
            "severity": self.severity.value,
            "benchmark_name": self.benchmark_name,
            "current_value": self.current_value,
            "baseline_value": self.baseline_value,
            "change_percent": self.change_percent,
            "threshold_percent": self.threshold_percent,
            "commit_hash": self.commit_hash,
            "detected_at": self.detected_at,
            "metadata": self.metadata,
        }


@dataclass
class RegressionConfig:
    performance_threshold: float = 10.0
    memory_threshold: float = 15.0
    accuracy_threshold: float = 1.0
    min_samples: int = 5
    window_size: int = 100


class RegressionDetector:
    def __init__(self, config: RegressionConfig = None):
        self.config = config or RegressionConfig()
        self.results: Dict[str, List[BenchmarkResult]] = defaultdict(list)
        self.regressions: List[Regression] = []
        self.baselines: Dict[str, float] = {}
        self._lock = None

    def record_result(self, result: BenchmarkResult):
        self.results[result.name].append(result)
        if len(self.results[result.name]) > self.config.window_size:
            self.results[result.name] = self.results[result.name][-self.config.window_size:]

    def set_baseline(self, benchmark_name: str, value: float):
        self.baselines[benchmark_name] = value

    def detect_regressions(self, benchmark_name: str = None) -> List[Regression]:
        detected = []
        names = [benchmark_name] if benchmark_name else list(self.results.keys())
        
        for name in names:
            results = self.results.get(name, [])
            if len(results) < self.config.min_samples:
                continue
            
            current_values = [r.value for r in results[-self.config.min_samples:]]
            current_avg = statistics.mean(current_values)
            
            if name in self.baselines:
                baseline = self.baselines[name]
            else:
                older_results = results[:-self.config.min_samples]
                if not older_results:
                    continue
                baseline = statistics.mean(r.value for r in older_values)
            
            change_percent = ((current_avg - baseline) / baseline) * 100 if baseline != 0 else 0
            
            threshold = self.config.performance_threshold
            
            if abs(change_percent) > threshold:
                severity = self._determine_severity(change_percent, threshold)
                regression = Regression(
                    regression_id=hashlib.md5(f"{name}:{time.time()}".encode()).hexdigest()[:12],
                    regression_type=RegressionType.PERFORMANCE,
                    severity=severity,
                    benchmark_name=name,
                    current_value=current_avg,
                    baseline_value=baseline,
                    change_percent=change_percent,
                    threshold_percent=threshold,
                )
                detected.append(regression)
        
        self.regressions.extend(detected)
        return detected

    def _determine_severity(self, change_percent: float, threshold: float) -> Severity:
        ratio = abs(change_percent) / threshold
        if ratio >= 5:
            return Severity.CRITICAL
        elif ratio >= 3:
            return Severity.HIGH
        elif ratio >= 2:
            return Severity.MEDIUM
        return Severity.LOW

    def get_regressions(self, since: float = 0) -> List[Regression]:
        return [r for r in self.regressions if r.detected_at >= since]

    def get_latest_results(self, benchmark_name: str, limit: int = 10) -> List[BenchmarkResult]:
        results = self.results.get(benchmark_name, [])
        return results[-limit:]

    def get_trend(self, benchmark_name: str, window: int = 20) -> Dict[str, Any]:
        results = self.results.get(benchmark_name, [])
        if len(results) < 2:
            return {}
        
        recent = results[-window:]
        values = [r.value for r in recent]
        
        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "stdev": statistics.stdev(values) if len(values) > 1 else 0,
            "trend": "improving" if values[-1] < values[0] else "degrading",
        }

    def export_results(self, path: str):
        data = {
            "results": {k: [r.to_dict() for r in v] for k, v in self.results.items()},
            "regressions": [r.to_dict() for r in self.regressions],
            "baselines": self.baselines,
        }
        Path(path).write_text(json.dumps(data, indent=2))

    def import_results(self, path: str):
        data = json.loads(Path(path).read_text())
        for k, v in data.get("results", {}).items():
            self.results[k] = [BenchmarkResult.from_dict(r) for r in v]
        self.regressions = [Regression(**r) for r in data.get("regressions", [])]
        self.baselines = data.get("baselines", {})


class StatisticalRegressionDetector(RegressionDetector):
    def __init__(self, config: RegressionConfig = None):
        super().__init__(config)
        self.control_charts: Dict[str, Dict] = {}

    def detect_regressions(self, benchmark_name: str = None) -> List[Regression]:
        detected = []
        names = [benchmark_name] if benchmark_name else list(self.results.keys())
        
        for name in names:
            results = self.results.get(name, [])
            if len(results) < self.config.min_samples:
                continue
            
            current_values = [r.value for r in results[-self.config.min_samples:]]
            older_results = results[:-self.config.min_samples]
            
            if not older_results:
                continue
            
            older_values = [r.value for r in older_results]
            
            stat, p_value = self._t_test(current_values, older_values)
            
            if p_value < 0.05:
                current_avg = statistics.mean(current_values)
                baseline_avg = statistics.mean(older_values)
                change_percent = ((current_avg - baseline_avg) / baseline_avg) * 100 if baseline_avg != 0 else 0
                
                severity = self._determine_severity(change_percent, self.config.performance_threshold)
                regression = Regression(
                    regression_id=hashlib.md5(f"{name}:{time.time()}".encode()).hexdigest()[:12],
                    regression_type=RegressionType.PERFORMANCE,
                    severity=severity,
                    benchmark_name=name,
                    current_value=current_avg,
                    baseline_value=baseline_avg,
                    change_percent=change_percent,
                    threshold_percent=self.config.performance_threshold,
                    metadata={"p_value": p_value, "t_statistic": stat},
                )
                detected.append(regression)
        
        self.regressions.extend(detected)
        return detected

    def _t_test(self, sample1: List[float], sample2: List[float]) -> tuple:
        n1, n2 = len(sample1), len(sample2)
        mean1, mean2 = statistics.mean(sample1), statistics.mean(sample2)
        var1 = statistics.variance(sample1) if n1 > 1 else 0
        var2 = statistics.variance(sample2) if n2 > 1 else 0
        
        pooled_var = ((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2) if n1 + n2 > 2 else 1
        std_err = (pooled_var * (1/n1 + 1/n2)) ** 0.5
        
        if std_err == 0:
            return 0, 1.0
        
        t_stat = (mean1 - mean2) / std_err
        
        import math
        df = n1 + n2 - 2
        p_value = 2 * (1 - self._t_cdf(abs(t_stat), df))
        
        return t_stat, p_value

    def _t_cdf(self, t: float, df: int) -> float:
        import math
        if df <= 0:
            return 0.5
        x = df / (t * t + df)
        return 1 - 0.5 * math.exp(-0.5 * t * t) * (1 + t * t / df) ** (-0.5 * (df + 1))


class ContinuousRegressionMonitor:
    def __init__(self, detector: RegressionDetector, check_interval: float = 60.0):
        self.detector = detector
        self.check_interval = check_interval
        self._running = False
        self._task = None
        self._callbacks: List[Callable] = []

    def on_regression(self, callback: Callable):
        self._callbacks.append(callback)

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _monitor_loop(self):
        while self._running:
            await asyncio.sleep(self.check_interval)
            regressions = self.detector.detect_regressions()
            for regression in regressions:
                for callback in self._callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(regression)
                        else:
                            callback(regression)
                    except Exception:
                        pass

    def record_benchmark(self, name: str, value: float, unit: str, **kwargs):
        result = BenchmarkResult(
            benchmark_id=hashlib.md5(f"{name}:{time.time()}".encode()).hexdigest()[:12],
            name=name,
            value=value,
            unit=unit,
            **kwargs,
        )
        self.detector.record_result(result)


import asyncio