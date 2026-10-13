"""
Append-Only Transaction Journaling - Logs all file writes and API calls for post-mortem analysis
"""
import threading
import time
import json
import os
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path


class TransactionType(Enum):
    FILE_WRITE = "file_write"
    FILE_READ = "file_read"
    FILE_DELETE = "file_delete"
    API_CALL = "api_call"
    TOOL_CALL = "tool_call"
    PROCESS_SPAWN = "process_spawn"
    MEMORY_ALLOC = "memory_alloc"
    STATE_CHANGE = "state_change"


@dataclass
class JournalEntry:
    entry_id: str
    timestamp: float
    transaction_type: TransactionType
    actor: str  # component/tool/process that performed the action
    operation: str
    target: str
    payload: Dict[str, Any] = field(default_factory=dict)
    result: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: str = ""
    duration_ms: float = 0
    correlation_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class TransactionJournal:
    def __init__(self, journal_dir: str = "./transaction_journal", 
                 max_file_size: int = 100 * 1024 * 1024):
        self.journal_dir = Path(journal_dir)
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.max_file_size = max_file_size
        self._current_file: Optional[Path] = None
        self._file_handle = None
        self._current_size = 0
        self._lock = threading.RLock()
        self._buffer: List[JournalEntry] = []
        self._buffer_size = 100
        self._flush_interval = 1.0
        self._running = False
        self._flush_thread: Optional[threading.Thread] = None
        self._stats = {"entries": 0, "bytes": 0, "errors": 0}
        self._rotate_file()
    
    def start(self):
        if self._running:
            return
        self._running = True
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()
    
    def stop(self):
        self._running = False
        self.flush()
        if self._flush_thread:
            self._flush_thread.join(timeout=5.0)
        self._close_file()
    
    def log(self, transaction_type: TransactionType, actor: str, operation: str,
            target: str, payload: Dict[str, Any] = None, result: Dict[str, Any] = None,
            success: bool = True, error: str = "", duration_ms: float = 0,
            correlation_id: str = "", metadata: Dict[str, Any] = None) -> str:
        
        entry_id = f"txn_{int(time.time() * 1000000)}"
        
        entry = JournalEntry(
            entry_id=entry_id,
            timestamp=time.time(),
            transaction_type=transaction_type,
            actor=actor,
            operation=operation,
            target=target,
            payload=payload or {},
            result=result or {},
            success=success,
            error=error,
            duration_ms=duration_ms,
            correlation_id=correlation_id,
            metadata=metadata or {}
        )
        
        with self._lock:
            self._buffer.append(entry)
            if len(self._buffer) >= self._buffer_size:
                self._flush_buffer()
        
        return entry_id
    
    def log_file_write(self, actor: str, path: str, size: int, 
                      correlation_id: str = "", success: bool = True, error: str = "") -> str:
        return self.log(
            TransactionType.FILE_WRITE, actor, "write", path,
            payload={"size": size}, result={"bytes_written": size},
            success=success, error=error, correlation_id=correlation_id
        )
    
    def log_file_read(self, actor: str, path: str, size: int,
                     correlation_id: str = "", success: bool = True) -> str:
        return self.log(
            TransactionType.FILE_READ, actor, "read", path,
            payload={"size": size}, result={"bytes_read": size},
            success=success, correlation_id=correlation_id
        )
    
    def log_api_call(self, actor: str, endpoint: str, method: str,
                    payload: Dict = None, result: Dict = None,
                    success: bool = True, error: str = "", duration_ms: float = 0,
                    correlation_id: str = "") -> str:
        return self.log(
            TransactionType.API_CALL, actor, method, endpoint,
            payload=payload or {}, result=result or {},
            success=success, error=error, duration_ms=duration_ms,
            correlation_id=correlation_id
        )
    
    def log_tool_call(self, actor: str, tool: str, params: Dict,
                     result: Dict = None, success: bool = True,
                     error: str = "", duration_ms: float = 0,
                     correlation_id: str = "") -> str:
        return self.log(
            TransactionType.TOOL_CALL, actor, "call", tool,
            payload=params, result=result or {},
            success=success, error=error, duration_ms=duration_ms,
            correlation_id=correlation_id
        )
    
    def _flush_loop(self):
        while self._running:
            time.sleep(self._flush_interval)
            self.flush()
    
    def flush(self):
        with self._lock:
            self._flush_buffer()
    
    def _flush_buffer(self):
        if not self._buffer:
            return
        
        entries = self._buffer[:]
        self._buffer.clear()
        
        try:
            with self._lock:
                if self._current_size >= self.max_file_size:
                    self._rotate_file()
                
                for entry in entries:
                    line = json.dumps(self._entry_to_dict(entry)) + '\n'
                    self._file_handle.write(line)
                    self._current_size += len(line)
                
                self._file_handle.flush()
                os.fsync(self._file_handle.fileno())
                
                self._stats["entries"] += len(entries)
                self._stats["bytes"] += sum(len(json.dumps(self._entry_to_dict(e))) for e in entries)
        except Exception as e:
            self._stats["errors"] += 1
            # Re-add to buffer
            with self._lock:
                self._buffer = entries + self._buffer
    
    def _entry_to_dict(self, entry: JournalEntry) -> Dict[str, Any]:
        data = asdict(entry)
        data["transaction_type"] = entry.transaction_type.value
        return data
    
    def _rotate_file(self):
        self._close_file()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self._current_file = self.journal_dir / f"journal_{timestamp}.jsonl"
        self._file_handle = open(self._current_file, 'a', buffering=8192)
        self._current_size = 0
    
    def _close_file(self):
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None
    
    def query(self, start_time: float = None, end_time: float = None,
              transaction_type: TransactionType = None, actor: str = None,
              target: str = None, correlation_id: str = None,
              limit: int = 1000) -> List[JournalEntry]:
        # Read from journal files (simplified - reads current buffer + recent files)
        entries = []
        
        with self._lock:
            entries.extend(self._buffer)
        
        # Apply filters
        if start_time:
            entries = [e for e in entries if e.timestamp >= start_time]
        if end_time:
            entries = [e for e in entries if e.timestamp <= end_time]
        if transaction_type:
            entries = [e for e in entries if e.transaction_type == transaction_type]
        if actor:
            entries = [e for e in entries if e.actor == actor]
        if target:
            entries = [e for e in entries if e.target == target]
        if correlation_id:
            entries = [e for e in entries if e.correlation_id == correlation_id]
        
        return entries[-limit:]
    
    def get_stats(self) -> Dict[str, Any]:
        return dict(self._stats)
    
    def replay(self, correlation_id: str) -> List[JournalEntry]:
        return self.query(correlation_id=correlation_id)


_transaction_journal: Optional[TransactionJournal] = None

def get_transaction_journal() -> TransactionJournal:
    global _transaction_journal
    if _transaction_journal is None:
        _transaction_journal = TransactionJournal()
        _transaction_journal.start()
    return _transaction_journal