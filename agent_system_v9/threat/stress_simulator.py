"""
Stress Simulator - Load testing and stress simulation for system resilience
"""
import asyncio
import hashlib
import random
import statistics
import time
from typing import Dict, List, Optional, Any, Callable, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import threading


class StressType(Enum):
    CPU = "cpu"
    MEMORY = "memory"
    NETWORK = "network"
    DISK_IO = "disk_io"
    DATABASE = "database"
    API = "api"
    CONCURRENT_USERS = "concurrent_users"
    REQUEST_RATE = "request_rate"


class StressPhase(Enum):
    WARMUP = "warmup"
    RAMP_UP = "ramp_up"
    STEADY = "steady"
    SPIKE = "spike"
    RAMP_DOWN = "ramp_down"
    COOLDOWN = "cooldown"


@dataclass
class StressConfig:
    stress_type: StressType
    target: str
    duration_seconds: float = 60.0
    intensity: float = 0.5
    ramp_up_seconds: float = 10.0
    ramp_down_seconds: float = 10.0
    threads: int = 10
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StressMetrics:
    timestamp: float
    stress_type: StressType
    phase: StressPhase
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    network_mbps: float = 0.0
    disk_iops: float = 0.0
    requests_per_second: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    latency_p99_ms: float = 0.0
    error_rate: float = 0.0
    throughput_mbps: float = 0.0
    active_connections: int = 0
    queue_depth: int = 0
    custom_metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class StressResult:
    config: StressConfig
    start_time: float
    end_time: float
    metrics: List[StressMetrics] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    passed: bool = True
    thresholds: Dict[str, float] = field(default_factory=dict)

    def get_summary(self) -> Dict[str, Any]:
        if not self.metrics:
            return {}
        
        latencies = [m.latency_p50_ms for m in self.metrics if m.latency_p50_ms > 0]
        error_rates = [m.error_rate for m in self.metrics]
        
        return {
            "duration": self.end_time - self.start_time,
            "avg_latency_p50": statistics.mean(latencies) if latencies else 0,
            "max_latency_p99": max((m.latency_p99_ms for m in self.metrics), default=0),
            "avg_error_rate": statistics.mean(error_rates) if error_rates else 0,
            "max_error_rate": max(error_rates) if error_rates else 0,
            "avg_throughput": statistics.mean([m.throughput_mbps for m in self.metrics]),
            "peak_connections": max((m.active_connections for m in self.metrics), default=0),
            "thresholds_passed": all(
                getattr(self, f"_{k}", 0) <= v for k, v in self.thresholds.items()
            ),
        }


class StressSimulator:
    def __init__(self):
        self.running = False
        self.current_stress: Optional[StressConfig] = None
        self.metrics_history: List[StressMetrics] = []
        self.results_history: List[StressResult] = []
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=50)
        self._monitor_task: Optional[asyncio.Task] = None
        self._callbacks: Dict[StressPhase, List[Callable]] = defaultdict(list)

    def register_callback(self, phase: StressPhase, callback: Callable):
        self._callbacks[phase].append(callback)

    async def run_stress(self, config: StressConfig) -> StressResult:
        with self._lock:
            if self.running:
                raise RuntimeError("Stress test already running")
            self.running = True
            self.current_stress = config
        
        result = StressResult(
            config=config,
            start_time=time.time(),
            end_time=0.0,
        )
        
        try:
            await self._execute_stress(config, result)
        except Exception as e:
            result.errors.append(str(e))
            result.passed = False
        finally:
            result.end_time = time.time()
            self.running = False
            self.current_stress = None
            self.results_history.append(result)
        
        return result

    async def _execute_stress(self, config: StressConfig, result: StressResult):
        phases = [
            (StressPhase.WARMUP, config.ramp_up_seconds * 0.1),
            (StressPhase.RAMP_UP, config.ramp_up_seconds),
            (StressPhase.STEADY, config.duration_seconds - config.ramp_up_seconds - config.ramp_down_seconds),
            (StressPhase.RAMP_DOWN, config.ramp_down_seconds),
            (StressPhase.COOLDOWN, config.ramp_up_seconds * 0.1),
        ]
        
        for phase, duration in phases:
            if duration <= 0:
                continue
            
            await self._run_phase(phase, config, duration, result)
            
            for callback in self._callbacks[phase]:
                try:
                    callback(result)
                except Exception:
                    pass

    async def _run_phase(self, phase: StressPhase, config: StressConfig, duration: float, result: StressResult):
        intensity = config.intensity
        if phase == StressPhase.RAMP_UP:
            intensity = config.intensity * 0.1
        elif phase == StressPhase.RAMP_DOWN:
            intensity = config.intensity * 0.1
        elif phase == StressPhase.WARMUP or phase == StressPhase.COOLDOWN:
            intensity = config.intensity * 0.05
        
        start = time.time()
        interval = 1.0
        
        while time.time() - start < duration:
            metrics = await self._collect_metrics(config.stress_type, phase, intensity)
            result.metrics.append(metrics)
            self.metrics_history.append(metrics)
            
            await self._apply_stress(config.stress_type, intensity, config.parameters)
            
            await asyncio.sleep(interval)
            
            if phase == StressPhase.RAMP_UP:
                elapsed = time.time() - start
                intensity = config.intensity * (elapsed / duration)
            elif phase == StressPhase.RAMP_DOWN:
                elapsed = time.time() - start
                intensity = config.intensity * (1 - elapsed / duration)

    async def _collect_metrics(self, stress_type: StressType, phase: StressPhase, intensity: float) -> StressMetrics:
        import psutil
        
        cpu = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory().percent
        net_io = psutil.net_io_counters()
        disk_io = psutil.disk_io_counters()
        
        return StressMetrics(
            timestamp=time.time(),
            stress_type=stress_type,
            phase=phase,
            cpu_percent=cpu,
            memory_percent=memory,
            network_mbps=(net_io.bytes_sent + net_io.bytes_recv) / 1e6 if net_io else 0,
            disk_iops=(disk_io.read_count + disk_io.write_count) if disk_io else 0,
        )

    async def _apply_stress(self, stress_type: StressType, intensity: float, parameters: Dict[str, Any]):
        if stress_type == StressType.CPU:
            await self._stress_cpu(intensity, parameters)
        elif stress_type == StressType.MEMORY:
            await self._stress_memory(intensity, parameters)
        elif stress_type == StressType.NETWORK:
            await self._stress_network(intensity, parameters)
        elif stress_type == StressType.DISK_IO:
            await self._stress_disk_io(intensity, parameters)
        elif stress_type == StressType.API:
            await self._stress_api(intensity, parameters)
        elif stress_type == StressType.CONCURRENT_USERS:
            await self._stress_concurrent_users(intensity, parameters)
        elif stress_type == StressType.REQUEST_RATE:
            await self._stress_request_rate(intensity, parameters)

    async def _stress_cpu(self, intensity: float, parameters: Dict):
        workers = int(parameters.get("workers", 4) * intensity)
        
        def cpu_work():
            end = time.time() + 1
            while time.time() < end:
                _ = sum(i * i for i in range(10000))
        
        tasks = [asyncio.get_event_loop().run_in_executor(self._executor, cpu_work) for _ in range(workers)]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _stress_memory(self, intensity: float, parameters: Dict):
        target_mb = parameters.get("target_mb", 100) * intensity
        chunk_size = 10 * 1024 * 1024
        chunks = int(target_mb / 10)
        
        data = []
        for _ in range(chunks):
            data.append(bytearray(chunk_size))
            await asyncio.sleep(0.01)
        
        await asyncio.sleep(1)
        data.clear()

    async def _stress_network(self, intensity: float, parameters: Dict):
        pass

    async def _stress_disk_io(self, intensity: float, parameters: Dict):
        import tempfile
        import os
        
        file_size = parameters.get("file_size_mb", 10) * intensity
        block_size = parameters.get("block_size_kb", 4) * 1024
        
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
            for _ in range(int(file_size * 1024 / (block_size / 1024))):
                f.write(os.urandom(block_size))
        
        try:
            with open(temp_path, 'rb') as f:
                while f.read(block_size):
                    pass
        finally:
            os.unlink(temp_path)

    async def _stress_api(self, intensity: float, parameters: Dict):
        endpoint = parameters.get("endpoint", "http://localhost:8080/health")
        requests_per_second = parameters.get("rps", 100) * intensity
        
        async def make_request():
            import aiohttp
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(endpoint) as resp:
                        await resp.read()
                except Exception:
                    pass
        
        interval = 1.0 / requests_per_second if requests_per_second > 0 else 1.0
        end = time.time() + 1
        
        while time.time() < end:
            asyncio.create_task(make_request())
            await asyncio.sleep(interval)

    async def _stress_concurrent_users(self, intensity: float, parameters: Dict):
        user_count = int(parameters.get("users", 100) * intensity)
        
        async def simulate_user():
            await asyncio.sleep(random.uniform(0.1, 2.0))
        
        tasks = [simulate_user() for _ in range(user_count)]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _stress_request_rate(self, intensity: float, parameters: Dict):
        pass

    def stop(self):
        self.running = False

    def get_current_metrics(self) -> Optional[StressMetrics]:
        return self.metrics_history[-1] if self.metrics_history else None

    def get_results(self, limit: int = 100) -> List[StressResult]:
        return self.results_history[-limit:]


class ChaosEngine:
    def __init__(self, simulator: StressSimulator):
        self.simulator = simulator
        self.experiments: List[Dict] = []

    def define_experiment(self, name: str, stress_configs: List[StressConfig], 
                         hypothesis: str, rollback: Callable = None) -> str:
        exp_id = hashlib.md5(f"{name}:{time.time()}".encode()).hexdigest()[:12]
        self.experiments.append({
            "id": exp_id,
            "name": name,
            "configs": stress_configs,
            "hypothesis": hypothesis,
            "rollback": rollback,
            "results": [],
        })
        return exp_id

    async def run_experiment(self, exp_id: str) -> Dict[str, Any]:
        experiment = next((e for e in self.experiments if e["id"] == exp_id), None)
        if not experiment:
            return {"error": "Experiment not found"}
        
        results = []
        for config in experiment["configs"]:
            result = await self.simulator.run_stress(config)
            results.append(result)
        
        experiment["results"] = results
        return {
            "experiment_id": exp_id,
            "hypothesis": experiment["hypothesis"],
            "results": [r.get_summary() for r in results],
            "passed": all(r.passed for r in results),
        }


class LoadTestOrchestrator:
    def __init__(self):
        self.simulators: Dict[str, StressSimulator] = {}
        self.test_suites: Dict[str, List[StressConfig]] = {}

    def add_simulator(self, name: str, simulator: StressSimulator):
        self.simulators[name] = simulator

    def create_test_suite(self, name: str, configs: List[StressConfig]):
        self.test_suites[name] = configs

    async def run_test_suite(self, suite_name: str) -> Dict[str, List[StressResult]]:
        configs = self.test_suites.get(suite_name, [])
        results = {}
        
        for config in configs:
            simulator = self.simulators.get("default", StressSimulator())
            result = await simulator.run_stress(config)
            results.setdefault(config.stress_type.value, []).append(result)
        
        return results

    def generate_report(self, results: Dict[str, List[StressResult]]) -> str:
        lines = ["# Load Test Report\n"]
        
        for stress_type, suite_results in results.items():
            lines.append(f"## {stress_type}\n")
            for result in suite_results:
                summary = result.get_summary()
                lines.append(f"- **Config**: {result.config.target} (intensity: {result.config.intensity})")
                lines.append(f"  - Duration: {summary.get('duration', 0):.1f}s")
                lines.append(f"  - Avg Latency (p50): {summary.get('avg_latency_p50', 0):.1f}ms")
                lines.append(f"  - Max Latency (p99): {summary.get('max_latency_p99', 0):.1f}ms")
                lines.append(f"  - Avg Error Rate: {summary.get('avg_error_rate', 0):.2%}")
                lines.append(f"  - Passed: {'✓' if result.passed else '✗'}\n")
        
        return "\n".join(lines)