"""
Power Throttler - Power-aware execution throttling for edge devices
"""
import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

import psutil


class PowerProfile(Enum):
    PERFORMANCE = "performance"
    BALANCED = "balanced"
    POWER_SAVER = "power_saver"
    ULTRA_LOW = "ultra_low"


class ThrottleReason(Enum):
    BATTERY_LOW = "battery_low"
    TEMPERATURE_HIGH = "temperature_high"
    CPU_THROTTLING = "cpu_throttling"
    POWER_LIMIT = "power_limit"
    USER_REQUEST = "user_request"


@dataclass
class PowerState:
    battery_percent: float = 100.0
    charging: bool = True
    cpu_temp: float = 0.0
    cpu_freq: float = 0.0
    power_draw: float = 0.0
    profile: PowerProfile = PowerProfile.BALANCED
    throttle_level: float = 0.0


@dataclass
class ThrottleConfig:
    battery_threshold: float = 20.0
    temp_threshold: float = 80.0
    cpu_throttle_threshold: float = 0.8
    power_limit_watts: float = 15.0
    min_cpu_freq: float = 0.5
    max_cpu_freq: float = 1.0
    check_interval: float = 5.0


class PowerMonitor:
    def __init__(self):
        self.last_battery = None
        self.last_cpu_times = None
        self._init_sensors()

    def _init_sensors(self):
        try:
            self.battery = psutil.sensors_battery()
        except Exception:
            self.battery = None

        try:
            self.temps = psutil.sensors_temperatures()
        except Exception:
            self.temps = None

        try:
            self.cpu_freq = psutil.cpu_freq()
        except Exception:
            self.cpu_freq = None

    def get_power_state(self) -> PowerState:
        state = PowerState()

        try:
            battery = psutil.sensors_battery()
            if battery:
                state.battery_percent = battery.percent
                state.charging = battery.power_plugged
        except Exception:
            pass

        try:
            temps = psutil.sensors_temperatures()
            if temps:
                cpu_temps = temps.get('coretemp', temps.get('cpu_thermal', []))
                if cpu_temps:
                    state.cpu_temp = max(t.current for t in cpu_temps)
        except Exception:
            pass

        try:
            freq = psutil.cpu_freq()
            if freq:
                state.cpu_freq = freq.current / freq.max if freq.max > 0 else 1.0
        except Exception:
            pass

        try:
            state.power_draw = self._estimate_power_draw()
        except Exception:
            pass

        return state

    def _estimate_power_draw(self) -> float:
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            return cpu_percent * 0.15
        except Exception:
            return 0.0


class PowerThrottler:
    def __init__(self, config: ThrottleConfig = None):
        self.config = config or ThrottleConfig()
        self.monitor = PowerMonitor()
        self.current_state = PowerState()
        self.profile = PowerProfile.BALANCED
        self.throttle_callbacks: list[Callable] = []
        self._running = False
        self._monitor_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self.history: list[PowerState] = []

    def set_profile(self, profile: PowerProfile):
        self.profile = profile

    def get_profile(self) -> PowerProfile:
        return self.profile

    def add_throttle_callback(self, callback: Callable):
        self.throttle_callbacks.append(callback)

    async def start(self):
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop(self):
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

    async def _monitor_loop(self):
        while self._running:
            await self._check_power()
            await asyncio.sleep(self.config.check_interval)

    async def _check_power(self):
        state = self.monitor.get_power_state()
        state.profile = self.profile

        throttle_level = 0.0
        reasons = []

        if not state.charging and state.battery_percent <= self.config.battery_threshold:
            throttle_level = max(throttle_level, 1.0 - (state.battery_percent / self.config.battery_threshold))
            reasons.append(ThrottleReason.BATTERY_LOW)

        if state.cpu_temp >= self.config.temp_threshold:
            throttle_level = max(throttle_level, (state.cpu_temp - self.config.temp_threshold) / 20.0)
            reasons.append(ThrottleReason.TEMPERATURE_HIGH)

        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            if cpu_percent / 100.0 >= self.config.cpu_throttle_threshold:
                throttle_level = max(throttle_level, (cpu_percent / 100.0 - self.config.cpu_throttle_threshold) / (1.0 - self.config.cpu_throttle_threshold))
                reasons.append(ThrottleReason.CPU_THROTTLING)
        except Exception:
            pass

        if state.power_draw >= self.config.power_limit_watts:
            throttle_level = max(throttle_level, (state.power_draw - self.config.power_limit_watts) / self.config.power_limit_watts)
            reasons.append(ThrottleReason.POWER_LIMIT)

        throttle_level = min(max(throttle_level, 0.0), 1.0)

        if abs(throttle_level - self.current_state.throttle_level) > 0.1 or reasons:
            old_level = self.current_state.throttle_level
            self.current_state = state
            self.current_state.throttle_level = throttle_level

            for callback in self.throttle_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(self.current_state, reasons, old_level)
                    else:
                        callback(self.current_state, reasons, old_level)
                except Exception:
                    pass
        else:
            self.current_state = state

        self.history.append(state)
        if len(self.history) > 1000:
            self.history = self.history[-1000:]

    def get_throttle_factor(self) -> float:
        base_factor = 1.0 - self.current_state.throttle_level

        if self.profile == PowerProfile.PERFORMANCE:
            return max(base_factor, 0.8)
        if self.profile == PowerProfile.BALANCED:
            return max(base_factor, 0.5)
        if self.profile == PowerProfile.POWER_SAVER:
            return max(base_factor, 0.3)
        if self.profile == PowerProfile.ULTRA_LOW:
            return max(base_factor, 0.1)

        return base_factor

    def should_throttle(self) -> bool:
        return self.current_state.throttle_level > 0.1

    def get_recommended_cpu_freq(self) -> float:
        factor = self.get_throttle_factor()
        return self.config.min_cpu_freq + (self.config.max_cpu_freq - self.config.min_cpu_freq) * factor

    def get_stats(self) -> dict[str, Any]:
        return {
            "current_state": {
                "battery_percent": self.current_state.battery_percent,
                "charging": self.current_state.charging,
                "cpu_temp": self.current_state.cpu_temp,
                "cpu_freq": self.current_state.cpu_freq,
                "power_draw": self.current_state.power_draw,
                "throttle_level": self.current_state.throttle_level,
            },
            "profile": self.profile.value,
            "throttle_factor": self.get_throttle_factor(),
            "should_throttle": self.should_throttle(),
            "history_size": len(self.history),
        }


class AdaptiveThrottler(PowerThrottler):
    def __init__(self, config: ThrottleConfig = None):
        super().__init__(config)
        self.workload_history: list[dict] = []
        self.performance_target = 0.8
        self.adaptation_rate = 0.1

    async def _check_power(self):
        await super()._check_power()

        if self.workload_history:
            avg_performance = sum(w.get("performance", 1.0) for w in self.workload_history[-10:]) / min(10, len(self.workload_history))

            if avg_performance < self.performance_target and self.current_state.throttle_level > 0:
                self.current_state.throttle_level = max(0.0, self.current_state.throttle_level - self.adaptation_rate)
            elif avg_performance > self.performance_target * 1.2:
                self.current_state.throttle_level = min(1.0, self.current_state.throttle_level + self.adaptation_rate)

    def record_workload(self, workload_type: str, duration: float, performance: float):
        self.workload_history.append({
            "type": workload_type,
            "duration": duration,
            "performance": performance,
            "timestamp": time.time(),
        })
        if len(self.workload_history) > 100:
            self.workload_history = self.workload_history[-100:]


class WorkloadScheduler:
    def __init__(self, throttler: PowerThrottler):
        self.throttler = throttler
        self.scheduled_tasks: list[dict] = []
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._schedule_loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def schedule(self, coro: Callable, priority: int = 0, min_throttle_factor: float = 0.3):
        self.scheduled_tasks.append({
            "coro": coro,
            "priority": priority,
            "min_throttle_factor": min_throttle_factor,
            "scheduled_at": time.time(),
        })
        self.scheduled_tasks.sort(key=lambda x: -x["priority"])

    async def _schedule_loop(self):
        while self._running:
            throttle_factor = self.throttler.get_throttle_factor()

            if throttle_factor >= 0.3 and self.scheduled_tasks:
                ready_tasks = [t for t in self.scheduled_tasks if throttle_factor >= t["min_throttle_factor"]]

                if ready_tasks:
                    task = ready_tasks[0]
                    self.scheduled_tasks.remove(task)

                    try:
                        if asyncio.iscoroutinefunction(task["coro"]):
                            await task["coro"]()
                        else:
                            await asyncio.get_event_loop().run_in_executor(None, task["coro"])
                    except Exception:
                        pass

            await asyncio.sleep(1.0)


class BatteryAwareExecutor:
    def __init__(self, throttler: PowerThrottler):
        self.throttler = throttler

    async def execute(self, coro: Callable, min_battery: float = 10.0) -> Any:
        state = self.throttler.current_state

        if not state.charging and state.battery_percent < min_battery:
            raise RuntimeError(f"Battery too low: {state.battery_percent}%")

        throttle_factor = self.throttler.get_throttle_factor()

        if asyncio.iscoroutinefunction(coro):
            return await coro()
        return await asyncio.get_event_loop().run_in_executor(None, coro)

    def execute_sync(self, func: Callable, min_battery: float = 10.0) -> Any:
        state = self.throttler.current_state

        if not state.charging and state.battery_percent < min_battery:
            raise RuntimeError(f"Battery too low: {state.battery_percent}%")

        return func()


class ThermalManager:
    def __init__(self, throttler: PowerThrottler):
        self.throttler = throttler
        self.cooling_actions: list[Callable] = []

    def add_cooling_action(self, action: Callable, temp_threshold: float = 75.0):
        self.cooling_actions.append((action, temp_threshold))

    async def check_and_cool(self):
        state = self.throttler.current_state

        if state.cpu_temp >= 75.0:
            for action, threshold in self.cooling_actions:
                if state.cpu_temp >= threshold:
                    try:
                        if asyncio.iscoroutinefunction(action):
                            await action(state)
                        else:
                            action(state)
                    except Exception:
                        pass

    def get_thermal_status(self) -> dict[str, Any]:
        state = self.throttler.current_state
        return {
            "cpu_temp": state.cpu_temp,
            "throttling": state.cpu_temp >= 75.0,
            "critical": state.cpu_temp >= 90.0,
        }
