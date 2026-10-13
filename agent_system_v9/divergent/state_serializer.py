"""
Pre-Destruction State Serializer - Snapshots heap, variables, and stack to persistent storage before reset
"""
import json
import pickle
import threading
import time
import sys
import traceback
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SerializedState:
    state_id: str
    timestamp: float
    frame_count: int
    variables: Dict[str, Any]
    stack_trace: List[str]
    heap_snapshot: Dict[str, Any]
    thread_states: Dict[int, Dict[str, Any]]
    metadata: Dict[str, Any] = field(default_factory=dict)


class StateSerializer:
    def __init__(self, storage_dir: str = "./state_snapshots", max_snapshots: int = 100):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.max_snapshots = max_snapshots
        self._lock = threading.RLock()
        self._custom_serializers: Dict[type, Callable] = {}
        self._register_default_serializers()
    
    def _register_default_serializers(self):
        self._custom_serializers[set] = lambda x: list(x)
        self._custom_serializers[frozenset] = lambda x: list(x)
        self._custom_serializers[complex] = lambda x: {"real": x.real, "imag": x.imag}
    
    def register_serializer(self, obj_type: type, serializer: Callable[[Any], Any]):
        self._custom_serializers[obj_type] = serializer
    
    def snapshot(self, state_id: str = None, include_heap: bool = True,
                include_threads: bool = True) -> SerializedState:
        
        if state_id is None:
            state_id = f"state_{int(time.time() * 1000)}"
        
        # Capture stack trace
        stack_trace = traceback.format_stack()
        
        # Capture local variables from current frame
        frame = sys._getframe(1)
        variables = self._capture_variables(frame)
        
        # Capture heap snapshot
        heap_snapshot = {}
        if include_heap:
            heap_snapshot = self._capture_heap()
        
        # Capture thread states
        thread_states = {}
        if include_threads:
            thread_states = self._capture_threads()
        
        state = SerializedState(
            state_id=state_id,
            timestamp=time.time(),
            frame_count=len(stack_trace),
            variables=variables,
            stack_trace=stack_trace,
            heap_snapshot=heap_snapshot,
            thread_states=thread_states,
            metadata={
                "python_version": sys.version,
                "platform": sys.platform
            }
        )
        
        # Save to disk
        self._save_state(state)
        
        return state
    
    def _capture_variables(self, frame) -> Dict[str, Any]:
        variables = {}
        
        # Local variables
        for name, value in frame.f_locals.items():
            if not name.startswith('__'):
                try:
                    variables[f"local.{name}"] = self._serialize_value(value)
                except Exception:
                    variables[f"local.{name}"] = f"<unserializable: {type(value).__name__}>"
        
        # Global variables (limited)
        for name, value in frame.f_globals.items():
            if not name.startswith('__') and name not in ('sys', 'os', 'builtins'):
                try:
                    variables[f"global.{name}"] = self._serialize_value(value)
                except Exception:
                    pass
        
        return variables
    
    def _serialize_value(self, value: Any) -> Any:
        # Check custom serializers
        for typ, serializer in self._custom_serializers.items():
            if isinstance(value, typ):
                return serializer(value)
        
        # Basic types
        if isinstance(value, (str, int, float, bool, type(None))):
            return value
        elif isinstance(value, (list, tuple)):
            return [self._serialize_value(v) for v in value]
        elif isinstance(value, dict):
            return {str(k): self._serialize_value(v) for k, v in value.items()}
        elif hasattr(value, '__dict__'):
            return {
                "__class__": type(value).__name__,
                "__module__": type(value).__module__,
                **{k: self._serialize_value(v) for k, v in value.__dict__.items() if not k.startswith('_')}
            }
        else:
            return f"<{type(value).__name__}>"
    
    def _capture_heap(self) -> Dict[str, Any]:
        # Simplified heap snapshot
        import gc
        objects = gc.get_objects()
        type_counts = {}
        for obj in objects[:10000]:  # Limit for performance
            typ = type(obj).__name__
            type_counts[typ] = type_counts.get(typ, 0) + 1
        
        return {
            "total_objects": len(objects),
            "type_distribution": dict(sorted(type_counts.items(), key=lambda x: -x[1])[:50])
        }
    
    def _capture_threads(self) -> Dict[int, Dict[str, Any]]:
        thread_states = {}
        for thread_id, frame in sys._current_frames().items():
            try:
                thread_states[thread_id] = {
                    "stack_depth": len(traceback.extract_stack(frame)),
                    "current_file": frame.f_code.co_filename,
                    "current_function": frame.f_code.co_name,
                    "current_line": frame.f_lineno
                }
            except Exception:
                pass
        return thread_states
    
    def _save_state(self, state: SerializedState):
        filepath = self.storage_dir / f"{state.state_id}.json"
        try:
            with open(filepath, 'w') as f:
                json.dump({
                    "state_id": state.state_id,
                    "timestamp": state.timestamp,
                    "frame_count": state.frame_count,
                    "variables": state.variables,
                    "stack_trace": state.stack_trace,
                    "heap_snapshot": state.heap_snapshot,
                    "thread_states": state.thread_states,
                    "metadata": state.metadata
                }, f, indent=2)
        except Exception:
            pass
        
        # Cleanup old snapshots
        self._cleanup_old()
    
    def _cleanup_old(self):
        snapshots = sorted(self.storage_dir.glob("state_*.json"), 
                          key=lambda p: p.stat().st_mtime)
        while len(snapshots) > self.max_snapshots:
            snapshots.pop(0).unlink(missing_ok=True)
    
    def load_state(self, state_id: str) -> Optional[SerializedState]:
        filepath = self.storage_dir / f"{state_id}.json"
        if not filepath.exists():
            return None
        
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            return SerializedState(**data)
        except Exception:
            return None
    
    def list_snapshots(self) -> List[Dict[str, Any]]:
        snapshots = []
        for filepath in sorted(self.storage_dir.glob("state_*.json"),
                              key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                snapshots.append({
                    "state_id": data["state_id"],
                    "timestamp": data["timestamp"],
                    "frame_count": data["frame_count"],
                    "variable_count": len(data["variables"])
                })
            except Exception:
                pass
        return snapshots
    
    def delete_state(self, state_id: str) -> bool:
        filepath = self.storage_dir / f"{state_id}.json"
        try:
            filepath.unlink()
            return True
        except Exception:
            return False


_state_serializer: Optional[StateSerializer] = None

def get_state_serializer() -> StateSerializer:
    global _state_serializer
    if _state_serializer is None:
        _state_serializer = StateSerializer()
    return _state_serializer