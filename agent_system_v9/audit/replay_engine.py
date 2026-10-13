"""
Audit Trail Replay Engine - Step-by-step playback engine using logs for forensic debugging
"""
import threading
import time
import json
from typing import Dict, List, Optional, Any, Callable, Iterator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from collections import defaultdict


class ReplayState(Enum):
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"
    STEP = "step"


@dataclass
class ReplayEvent:
    timestamp: float
    event_type: str
    component: str
    data: Dict[str, Any]
    trace_id: str = ""
    sequence: int = 0


@dataclass
class ReplaySession:
    session_id: str
    log_file: str
    start_time: float
    end_time: float
    total_events: int
    filtered_events: int
    state: ReplayState = ReplayState.STOPPED
    current_index: int = 0
    speed: float = 1.0
    filters: Dict[str, Any] = field(default_factory=dict)


class AuditTrailReplayEngine:
    def __init__(self, log_dir: str = "./logs"):
        self.log_dir = Path(log_dir)
        self._sessions: Dict[str, ReplaySession] = {}
        self._events_cache: Dict[str, List[ReplayEvent]] = {}
        self._lock = threading.RLock()
        self._playback_thread: Optional[threading.Thread] = None
        self._running = False
        self._callbacks: Dict[str, List[Callable]] = {
            "event": [],
            "state_change": [],
            "complete": [],
            "error": []
        }
    
    def create_session(self, log_file: str, 
                       start_time: float = None, end_time: float = None,
                       filters: Dict[str, Any] = None) -> ReplaySession:
        log_path = self.log_dir / log_file
        if not log_path.exists():
            raise FileNotFoundError(f"Log file not found: {log_path}")
        
        session_id = f"replay_{int(time.time() * 1000)}"
        
        events = self._load_events(log_path, start_time, end_time, filters)
        
        session = ReplaySession(
            session_id=session_id,
            log_file=log_file,
            start_time=events[0].timestamp if events else time.time(),
            end_time=events[-1].timestamp if events else time.time(),
            total_events=len(events),
            filtered_events=len(events),
            filters=filters or {}
        )
        
        with self._lock:
            self._sessions[session_id] = session
            self._events_cache[session_id] = events
        
        return session
    
    def _load_events(self, log_path: Path, start_time: float = None,
                     end_time: float = None, filters: Dict[str, Any] = None) -> List[ReplayEvent]:
        events = []
        sequence = 0
        
        with open(log_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    
                    # Apply time filters
                    timestamp = data.get("timestamp", 0)
                    if start_time and timestamp < start_time:
                        continue
                    if end_time and timestamp > end_time:
                        continue
                    
                    # Apply other filters
                    if filters:
                        if "level" in filters and data.get("level") != filters["level"]:
                            continue
                        if "component" in filters and data.get("component") != filters["component"]:
                            continue
                        if "event_type" in filters and data.get("event_type") != filters["event_type"]:
                            continue
                        if "trace_id" in filters and data.get("trace_id") != filters["trace_id"]:
                            continue
                    
                    event = ReplayEvent(
                        timestamp=timestamp,
                        event_type=data.get("event_type", ""),
                        component=data.get("component", ""),
                        data=data,
                        trace_id=data.get("trace_id", ""),
                        sequence=sequence
                    )
                    events.append(event)
                    sequence += 1
                    
                except json.JSONDecodeError:
                    continue
        
        return events
    
    def get_session(self, session_id: str) -> Optional[ReplaySession]:
        with self._lock:
            return self._sessions.get(session_id)
    
    def get_events(self, session_id: str, limit: int = 100, 
                   offset: int = 0) -> List[ReplayEvent]:
        with self._lock:
            events = self._events_cache.get(session_id, [])
            return events[offset:offset + limit]
    
    def play(self, session_id: str, speed: float = 1.0) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            
            if session.state == ReplayState.PLAYING:
                return True
            
            session.state = ReplayState.PLAYING
            session.speed = speed
        
        self._notify_state_change(session_id, ReplayState.PLAYING)
        
        if self._playback_thread and self._playback_thread.is_alive():
            return True
        
        self._running = True
        self._playback_thread = threading.Thread(target=self._playback_loop, args=(session_id,), daemon=True)
        self._playback_thread.start()
        
        return True
    
    def pause(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session or session.state != ReplayState.PLAYING:
                return False
            
            session.state = ReplayState.PAUSED
        
        self._notify_state_change(session_id, ReplayState.PAUSED)
        return True
    
    def stop(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            
            session.state = ReplayState.STOPPED
            session.current_index = 0
        
        self._running = False
        self._notify_state_change(session_id, ReplayState.STOPPED)
        return True
    
    def step(self, session_id: str, count: int = 1) -> List[ReplayEvent]:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return []
            
            events = self._events_cache.get(session_id, [])
            start = session.current_index
            end = min(start + count, len(events))
            
            session.current_index = end
            session.state = ReplayState.STEP
        
        stepped_events = events[start:end]
        for event in stepped_events:
            self._notify_event(session_id, event)
        
        return stepped_events
    
    def seek(self, session_id: str, index: int) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            
            events = self._events_cache.get(session_id, [])
            if index < 0 or index >= len(events):
                return False
            
            session.current_index = index
            return True
    
    def seek_to_time(self, session_id: str, timestamp: float) -> bool:
        with self._lock:
            events = self._events_cache.get(session_id, [])
            for i, event in enumerate(events):
                if event.timestamp >= timestamp:
                    return self.seek(session_id, i)
            return False
    
    def get_trace_events(self, session_id: str, trace_id: str) -> List[ReplayEvent]:
        with self._lock:
            events = self._events_cache.get(session_id, [])
            return [e for e in events if e.trace_id == trace_id]
    
    def get_component_timeline(self, session_id: str, component: str) -> List[ReplayEvent]:
        with self._lock:
            events = self._events_cache.get(session_id, [])
            return [e for e in events if e.component == component]
    
    def register_callback(self, event: str, callback: Callable):
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    def _playback_loop(self, session_id: str):
        while self._running:
            with self._lock:
                session = self._sessions.get(session_id)
                if not session or session.state != ReplayState.PLAYING:
                    break
                
                events = self._events_cache.get(session_id, [])
                if session.current_index >= len(events):
                    session.state = ReplayState.STOPPED
                    self._notify_state_change(session_id, ReplayState.STOPPED)
                    self._notify_complete(session_id)
                    break
                
                event = events[session.current_index]
                session.current_index += 1
            
            self._notify_event(session_id, event)
            
            # Calculate delay based on timestamps and speed
            if session.current_index < len(events):
                next_event = events[session.current_index]
                delay = (next_event.timestamp - event.timestamp) / session.speed
                if delay > 0:
                    time.sleep(min(delay, 1.0))  # Cap at 1 second
            else:
                time.sleep(0.1)
    
    def _notify_event(self, session_id: str, event: ReplayEvent):
        for cb in self._callbacks["event"]:
            try:
                cb(session_id, event)
            except Exception:
                pass
    
    def _notify_state_change(self, session_id: str, state: ReplayState):
        for cb in self._callbacks["state_change"]:
            try:
                cb(session_id, state)
            except Exception:
                pass
    
    def _notify_complete(self, session_id: str):
        for cb in self._callbacks["complete"]:
            try:
                cb(session_id)
            except Exception:
                pass
    
    def _notify_error(self, session_id: str, error: str):
        for cb in self._callbacks["error"]:
            try:
                cb(session_id, error)
            except Exception:
                pass
    
    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                self._events_cache.pop(session_id, None)
                return True
        return False
    
    def list_sessions(self) -> List[ReplaySession]:
        with self._lock:
            return list(self._sessions.values())


_replay_engine: Optional[AuditTrailReplayEngine] = None

def get_replay_engine() -> AuditTrailReplayEngine:
    global _replay_engine
    if _replay_engine is None:
        _replay_engine = AuditTrailReplayEngine()
    return _replay_engine