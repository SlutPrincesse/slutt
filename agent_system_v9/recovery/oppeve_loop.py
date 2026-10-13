"""
OPPEVE DAG Loop - Execution state machine (Observe, Plan, Provision, Execute, Verify, Evolve)
"""
import threading
import time
import uuid
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict


class OPPEVEState(Enum):
    OBSERVE = "observe"
    PLAN = "plan"
    PROVISION = "provision"
    EXECUTE = "execute"
    VERIFY = "verify"
    EVOLVE = "evolve"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class OPPEVEPhase:
    name: str
    state: OPPEVEState
    handler: Callable
    timeout: float = 30.0
    retry_count: int = 0
    max_retries: int = 3


class OPPEVELoop:
    def __init__(self):
        self._phases: List[OPPEVEPhase] = []
        self._current_phase: Optional[OPPEVEPhase] = None
        self._state = OPPEVEState.OBSERVE
        self._lock = threading.RLock()
        self._running = False
        self._loop_thread: Optional[threading.Thread] = None
        self._context: Dict[str, Any] = {}
        self._dag: Dict[str, List[str]] = defaultdict(list)  # phase -> dependencies
        self._results: Dict[str, Any] = {}
        self._callbacks: Dict[str, List[Callable]] = {
            "phase_started": [],
            "phase_completed": [],
            "phase_failed": [],
            "loop_completed": [],
            "loop_failed": []
        }
        self._register_default_phases()
    
    def _register_default_phases(self):
        self._phases = [
            OPPEVEPhase("observe", OPPEVEState.OBSERVE, self._observe, timeout=10.0),
            OPPEVEPhase("plan", OPPEVEState.PLAN, self._plan, timeout=30.0),
            OPPEVEPhase("provision", OPPEVEState.PROVISION, self._provision, timeout=60.0),
            OPPEVEPhase("execute", OPPEVEState.EXECUTE, self._execute, timeout=120.0),
            OPPEVEPhase("verify", OPPEVEState.VERIFY, self._verify, timeout=30.0),
            OPPEVEPhase("evolve", OPPEVEState.EVOLVE, self._evolve, timeout=30.0),
        ]
        
        # Define DAG dependencies
        self._dag = {
            "observe": [],
            "plan": ["observe"],
            "provision": ["plan"],
            "execute": ["provision"],
            "verify": ["execute"],
            "evolve": ["verify"]
        }
    
    def start(self, context: Dict[str, Any] = None):
        if self._running:
            return
        
        if context:
            self._context = context
        
        self._running = True
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._loop_thread.start()
    
    def stop(self):
        self._running = False
        if self._loop_thread:
            self._loop_thread.join(timeout=5.0)
    
    def _run_loop(self):
        while self._running:
            for phase in self._phases:
                if not self._running:
                    break
                
                if not self._check_dependencies(phase.name):
                    continue
                
                self._current_phase = phase
                self._state = phase.state
                self._notify_phase_started(phase)
                
                try:
                    result = self._run_phase(phase)
                    self._results[phase.name] = result
                    self._notify_phase_completed(phase, result)
                except Exception as e:
                    self._notify_phase_failed(phase, str(e))
                    if phase.retry_count < phase.max_retries:
                        phase.retry_count += 1
                        time.sleep(1.0)
                        continue
                    else:
                        self._state = OPPEVEState.FAILED
                        self._notify_loop_failed(str(e))
                        return
            
            if self._running:
                self._state = OPPEVEState.COMPLETE
                self._notify_loop_completed()
                self._running = False
    
    def _check_dependencies(self, phase_name: str) -> bool:
        deps = self._dag.get(phase_name, [])
        for dep in deps:
            if dep not in self._results:
                return False
            if isinstance(self._results[dep], Exception):
                return False
        return True
    
    def _run_phase(self, phase: OPPEVEPhase) -> Any:
        start = time.time()
        
        # Run with timeout
        result = None
        exception = None
        
        def target():
            nonlocal result, exception
            try:
                result = phase.handler(self._context)
            except Exception as e:
                exception = e
        
        thread = threading.Thread(target=target)
        thread.start()
        thread.join(timeout=phase.timeout)
        
        if thread.is_alive():
            raise TimeoutError(f"Phase {phase.name} timed out")
        
        if exception:
            raise exception
        
        return result
    
    def _observe(self, context: Dict) -> Dict:
        return {"timestamp": time.time(), "system_state": "observed"}
    
    def _plan(self, context: Dict) -> Dict:
        return {"plan": "generated", "steps": []}
    
    def _provision(self, context: Dict) -> Dict:
        return {"resources": "provisioned"}
    
    def _execute(self, context: Dict) -> Dict:
        return {"execution": "completed"}
    
    def _verify(self, context: Dict) -> Dict:
        return {"verified": True}
    
    def _evolve(self, context: Dict) -> Dict:
        return {"evolved": True}
    
    def get_state(self) -> OPPEVEState:
        with self._lock:
            return self._state
    
    def get_results(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._results)
    
    def register_callback(self, event: str, callback: Callable):
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    def _notify_phase_started(self, phase: OPPEVEPhase):
        for cb in self._callbacks["phase_started"]:
            try:
                cb(phase.name)
            except Exception:
                pass
    
    def _notify_phase_completed(self, phase: OPPEVEPhase, result: Any):
        for cb in self._callbacks["phase_completed"]:
            try:
                cb(phase.name, result)
            except Exception:
                pass
    
    def _notify_phase_failed(self, phase: OPPEVEPhase, error: str):
        for cb in self._callbacks["phase_failed"]:
            try:
                cb(phase.name, error)
            except Exception:
                pass
    
    def _notify_loop_completed(self):
        for cb in self._callbacks["loop_completed"]:
            try:
                cb(self._results)
            except Exception:
                pass
    
    def _notify_loop_failed(self, error: str):
        for cb in self._callbacks["loop_failed"]:
            try:
                cb(error)
            except Exception:
                pass


_oppeve_loop: Optional[OPPEVELoop] = None

def get_oppeve_loop() -> OPPEVELoop:
    global _oppeve_loop
    if _oppeve_loop is None:
        _oppeve_loop = OPPEVELoop()
    return _oppeve_loop