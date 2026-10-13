"""
Dual-Hemisphere Failover State Machine - Shifts execution to background shadow nodes during crashes
"""
import threading
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum


class FailoverState(Enum):
    PRIMARY = "primary"        # Normal operation on primary
    DEGRADED = "degraded"      # Primary degraded, monitoring
    FAILOVER = "failover"      # Transitioning to backup
    SECONDARY = "secondary"    # Running on backup
    RECOVERING = "recovering"  # Attempting to restore primary
    FAILED = "failed"          # Both primary and secondary failed


@dataclass
class HealthCheck:
    component: str
    healthy: bool
    latency_ms: float
    error: str = ""
    timestamp: float = field(default_factory=time.time)


class FailoverStateMachine:
    def __init__(self, health_check_interval: float = 5.0,
                 failure_threshold: int = 3,
                 recovery_threshold: int = 2):
        self.health_check_interval = health_check_interval
        self.failure_threshold = failure_threshold
        self.recovery_threshold = recovery_threshold
        
        self._state = FailoverState.PRIMARY
        self._failure_count = 0
        self._success_count = 0
        self._lock = threading.RLock()
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._health_checks: Dict[str, Callable[[], HealthCheck]] = {}
        self._failover_handlers: Dict[FailoverState, Callable] = {}
        self._callbacks: Dict[str, List[Callable]] = {
            "state_changed": [],
            "health_check_failed": [],
            "failover_triggered": [],
            "recovery_started": [],
            "recovery_completed": []
        }
        
        self._primary_components: List[str] = []
        self._secondary_components: List[str] = []
    
    def start(self):
        if self._running:
            return
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
    
    def stop(self):
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
    
    def register_component(self, name: str, health_check: Callable[[], HealthCheck],
                          is_primary: bool = True):
        with self._lock:
            self._health_checks[name] = health_check
            if is_primary:
                self._primary_components.append(name)
            else:
                self._secondary_components.append(name)
    
    def register_failover_handler(self, state: FailoverState, handler: Callable):
        self._failover_handlers[state] = handler
    
    def _monitor_loop(self):
        while self._running:
            time.sleep(self.health_check_interval)
            self._check_health()
    
    def _check_health(self):
        failed_components = []
        
        for name, check in self._health_checks.items():
            try:
                result = check()
                if not result.healthy:
                    failed_components.append(name)
                    self._notify_health_check_failed(result)
            except Exception as e:
                failed_components.append(name)
                self._notify_health_check_failed(HealthCheck(
                    component=name, healthy=False, latency_ms=0, error=str(e)
                ))
        
        with self._lock:
            if failed_components:
                self._failure_count += 1
                self._success_count = 0
                
                if self._state == FailoverState.PRIMARY and self._failure_count >= self.failure_threshold:
                    self._trigger_failover()
                elif self._state == FailoverState.SECONDARY:
                    self._state = FailoverState.FAILED
                    self._notify_state_changed()
            else:
                self._success_count += 1
                self._failure_count = 0
                
                if self._state == FailoverState.SECONDARY and self._success_count >= self.recovery_threshold:
                    self._start_recovery()
                elif self._state == FailoverState.DEGRADED:
                    self._state = FailoverState.PRIMARY
                    self._notify_state_changed()
    
    def _trigger_failover(self):
        with self._lock:
            old_state = self._state
            self._state = FailoverState.FAILOVER
        
        self._notify_state_changed()
        self._notify_failover_triggered()
        
        # Execute failover handler
        if FailoverState.FAILOVER in self._failover_handlers:
            try:
                self._failover_handlers[FailoverState.FAILOVER]()
            except Exception:
                pass
        
        with self._lock:
            self._state = FailoverState.SECONDARY
        self._notify_state_changed()
    
    def _start_recovery(self):
        with self._lock:
            old_state = self._state
            self._state = FailoverState.RECOVERING
        
        self._notify_state_changed()
        self._notify_recovery_started()
        
        # Execute recovery handler
        if FailoverState.RECOVERING in self._failover_handlers:
            try:
                self._failover_handlers[FailoverState.RECOVERING]()
            except Exception:
                pass
        
        # Verify primary is healthy
        all_healthy = True
        for name in self._primary_components:
            if name in self._health_checks:
                try:
                    if not self._health_checks[name]().healthy:
                        all_healthy = False
                        break
                except Exception:
                    all_healthy = False
                    break
        
        with self._lock:
            if all_healthy:
                self._state = FailoverState.PRIMARY
            else:
                self._state = FailoverState.SECONDARY
        
        self._notify_state_changed()
        if all_healthy:
            self._notify_recovery_completed()
    
    def get_state(self) -> FailoverState:
        with self._lock:
            return self._state
    
    def force_failover(self):
        with self._lock:
            self._failure_count = self.failure_threshold
        self._trigger_failover()
    
    def force_recovery(self):
        with self._lock:
            self._success_count = self.recovery_threshold
        self._start_recovery()
    
    def register_callback(self, event: str, callback: Callable):
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    def _notify_state_changed(self):
        with self._lock:
            state = self._state
        for cb in self._callbacks["state_changed"]:
            try:
                cb(state)
            except Exception:
                pass
    
    def _notify_health_check_failed(self, check: HealthCheck):
        for cb in self._callbacks["health_check_failed"]:
            try:
                cb(check)
            except Exception:
                pass
    
    def _notify_failover_triggered(self):
        for cb in self._callbacks["failover_triggered"]:
            try:
                cb()
            except Exception:
                pass
    
    def _notify_recovery_started(self):
        for cb in self._callbacks["recovery_started"]:
            try:
                cb()
            except Exception:
                pass
    
    def _notify_recovery_completed(self):
        for cb in self._callbacks["recovery_completed"]:
            try:
                cb()
            except Exception:
                pass


_failover: Optional[FailoverStateMachine] = None

def get_failover() -> FailoverStateMachine:
    global _failover
    if _failover is None:
        _failover = FailoverStateMachine()
        _failover.start()
    return _failover