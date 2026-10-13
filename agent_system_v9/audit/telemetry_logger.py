"""
NDJSON Telemetry Logger - Append-only non-blocking logger for execution steps, hooks, and errors
"""
import threading
import time
import json
import os
import queue
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from collections import deque


class TelemetryLevel(Enum):
    DEBUG = 0
    INFO = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4


@dataclass
class TelemetryEvent:
    timestamp: float
    level: TelemetryLevel
    component: str
    event_type: str
    message: str
    trace_id: str = ""
    span_id: str = ""
    parent_span_id: str = ""
    tags: Dict[str, str] = field(default_factory=dict)
    fields: Dict[str, Any] = field(default_factory=dict)
    duration_ms: Optional[float] = None
    error: Optional[str] = None
    
    def to_ndjson(self) -> str:
        data = asdict(self)
        data["level"] = self.level.name
        return json.dumps(data, separators=(',', ':'))
    
    @classmethod
    def from_ndjson(cls, line: str) -> 'TelemetryEvent':
        data = json.loads(line)
        data["level"] = TelemetryLevel[data["level"]]
        return cls(**data)


class NDJSONTelemetryLogger:
    def __init__(self, log_dir: str = "./logs", batch_size: int = 100, 
                 flush_interval: float = 1.0, max_file_size: int = 100 * 1024 * 1024):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.max_file_size = max_file_size
        
        self._queue: queue.Queue = queue.Queue(maxsize=10000)
        self._current_file: Optional[Path] = None
        self._file_handle = None
        self._current_size = 0
        self._lock = threading.RLock()
        self._running = False
        self._writer_thread: Optional[threading.Thread] = None
        self._flush_thread: Optional[threading.Thread] = None
        self._stats = {
            "written": 0,
            "dropped": 0,
            "errors": 0,
            "bytes_written": 0
        }
        self._event_buffer: deque = deque(maxlen=1000)
    
    def start(self):
        if self._running:
            return
        self._running = True
        self._rotate_file()
        self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._writer_thread.start()
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()
    
    def stop(self):
        self._running = False
        self._flush()
        if self._writer_thread:
            self._writer_thread.join(timeout=5.0)
        if self._flush_thread:
            self._flush_thread.join(timeout=5.0)
        self._close_file()
    
    def log(self, level: TelemetryLevel, component: str, event_type: str, message: str,
            trace_id: str = "", span_id: str = "", parent_span_id: str = "",
            tags: Dict[str, str] = None, fields: Dict[str, Any] = None,
            duration_ms: float = None, error: str = None):
        event = TelemetryEvent(
            timestamp=time.time(),
            level=level,
            component=component,
            event_type=event_type,
            message=message,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            tags=tags or {},
            fields=fields or {},
            duration_ms=duration_ms,
            error=error
        )
        
        self._event_buffer.append(event)
        
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self._stats["dropped"] += 1
    
    def debug(self, component: str, event_type: str, message: str, **kwargs):
        self.log(TelemetryLevel.DEBUG, component, event_type, message, **kwargs)
    
    def info(self, component: str, event_type: str, message: str, **kwargs):
        self.log(TelemetryLevel.INFO, component, event_type, message, **kwargs)
    
    def warning(self, component: str, event_type: str, message: str, **kwargs):
        self.log(TelemetryLevel.WARNING, component, event_type, message, **kwargs)
    
    def error(self, component: str, event_type: str, message: str, error: str = None, **kwargs):
        self.log(TelemetryLevel.ERROR, component, event_type, message, error=error, **kwargs)
    
    def critical(self, component: str, event_type: str, message: str, error: str = None, **kwargs):
        self.log(TelemetryLevel.CRITICAL, component, event_type, message, error=error, **kwargs)
    
    def log_step(self, component: str, step: str, trace_id: str = "", 
                 span_id: str = "", parent_span_id: str = "", **fields):
        self.info(component, "step", f"Step: {step}", trace_id=trace_id,
                 span_id=span_id, parent_span_id=parent_span_id, fields=fields)
    
    def log_hook(self, component: str, hook_name: str, trace_id: str = "",
                 duration_ms: float = None, **fields):
        self.info(component, "hook", f"Hook: {hook_name}", trace_id=trace_id,
                 duration_ms=duration_ms, fields=fields)
    
    def log_tool_call(self, component: str, tool: str, trace_id: str = "",
                      duration_ms: float = None, success: bool = True, **fields):
        level = TelemetryLevel.INFO if success else TelemetryLevel.ERROR
        self.log(level, component, "tool_call", f"Tool: {tool}", trace_id=trace_id,
                duration_ms=duration_ms, fields={**fields, "tool": tool, "success": success})
    
    def _writer_loop(self):
        batch = []
        while self._running:
            try:
                event = self._queue.get(timeout=0.1)
                batch.append(event)
                
                if len(batch) >= self.batch_size:
                    self._write_batch(batch)
                    batch.clear()
            except queue.Empty:
                if batch:
                    self._write_batch(batch)
                    batch.clear()
            except Exception as e:
                self._stats["errors"] += 1
    
    def _flush_loop(self):
        while self._running:
            time.sleep(self.flush_interval)
            self._flush()
    
    def _write_batch(self, events: List[TelemetryEvent]):
        if not events:
            return
        
        with self._lock:
            if not self._file_handle:
                self._rotate_file()
            
            for event in events:
                line = event.to_ndjson() + '\n'
                self._file_handle.write(line)
                self._current_size += len(line)
                self._stats["written"] += 1
                self._stats["bytes_written"] += len(line)
            
            self._file_handle.flush()
            
            if self._current_size >= self.max_file_size:
                self._rotate_file()
    
    def _flush(self):
        with self._lock:
            if self._file_handle:
                self._file_handle.flush()
                os.fsync(self._file_handle.fileno())
    
    def _rotate_file(self):
        self._close_file()
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self._current_file = self.log_dir / f"telemetry_{timestamp}.ndjson"
        self._file_handle = open(self._current_file, 'a', buffering=8192)
        self._current_size = 0
    
    def _close_file(self):
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None
    
    def get_recent_events(self, limit: int = 100, level: TelemetryLevel = None,
                          component: str = None) -> List[TelemetryEvent]:
        events = list(self._event_buffer)
        
        if level:
            events = [e for e in events if e.level == level]
        if component:
            events = [e for e in events if e.component == component]
        
        return events[-limit:]
    
    def query_events(self, start_time: float = None, end_time: float = None,
                     level: TelemetryLevel = None, component: str = None,
                     event_type: str = None, trace_id: str = None,
                     limit: int = 1000) -> List[TelemetryEvent]:
        # For full query, would need to read from files
        # This returns from buffer only
        events = list(self._event_buffer)
        
        if start_time:
            events = [e for e in events if e.timestamp >= start_time]
        if end_time:
            events = [e for e in events if e.timestamp <= end_time]
        if level:
            events = [e for e in events if e.level == level]
        if component:
            events = [e for e in events if e.component == component]
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if trace_id:
            events = [e for e in events if e.trace_id == trace_id]
        
        return events[-limit:]
    
    def get_stats(self) -> Dict[str, Any]:
        return dict(self._stats)


_telemetry_logger: Optional[NDJSONTelemetryLogger] = None

def get_telemetry_logger() -> NDJSONTelemetryLogger:
    global _telemetry_logger
    if _telemetry_logger is None:
        from ..core.config import config
        batch = config.get_param("audit", "telemetry_batch_size", 100)
        _telemetry_logger = NDJSONTelemetryLogger(batch_size=batch)
        _telemetry_logger.start()
    return _telemetry_logger