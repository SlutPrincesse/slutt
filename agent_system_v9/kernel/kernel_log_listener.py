"""
Kernel Log Listener - Tail system logs (dmesg, syslog) to capture hardware faults and OOM events
"""
import os
import re
import threading
import time
import subprocess
from typing import Dict, List, Optional, Callable, Any, Pattern
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
from pathlib import Path


class LogSource(Enum):
    DMESG = "dmesg"
    SYSLOG = "syslog"
    JOURNALD = "journald"
    KERNEL = "kernel"
    CUSTOM = "custom"


class LogSeverity(Enum):
    DEBUG = 0
    INFO = 1
    NOTICE = 2
    WARNING = 3
    ERROR = 4
    CRITICAL = 5
    ALERT = 6
    EMERGENCY = 7


@dataclass
class LogEvent:
    event_id: str
    source: LogSource
    severity: LogSeverity
    timestamp: float
    message: str
    raw_line: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)


class KernelLogListener:
    DMESG_PATTERNS = {
        LogSeverity.CRITICAL: [
            r"Out of memory",
            r"OOM killer",
            r"Kernel panic",
            r"Hardware Error",
            r"Machine check",
            r"NMI watchdog",
            r"BUG:",
            r"CRITICAL",
        ],
        LogSeverity.ERROR: [
            r"error",
            r"fail",
            r"fault",
            r"corrupt",
            r"segfault",
            r"divide error",
            r"invalid opcode",
        ],
        LogSeverity.WARNING: [
            r"warn",
            r"retry",
            r"timeout",
            r"throttl",
            r"degraded",
        ],
    }
    
    SYSLOG_PATTERNS = {
        LogSeverity.CRITICAL: [
            r"emerg",
            r"panic",
            r"halt",
        ],
        LogSeverity.ERROR: [
            r"err",
            r"error",
            r"fail",
            r"critical",
        ],
        LogSeverity.WARNING: [
            r"warn",
            r"warning",
        ],
    }
    
    def __init__(self, tail_lines: int = 1000):
        self.tail_lines = tail_lines
        self._sources: Dict[LogSource, Dict[str, Any]] = {}
        self._patterns: Dict[LogSource, Dict[LogSeverity, List[Pattern]]] = {}
        self._event_buffer: deque = deque(maxlen=10000)
        self._lock = threading.RLock()
        self._monitor_threads: Dict[LogSource, threading.Thread] = {}
        self._running = False
        self._callbacks: Dict[str, List[Callable]] = {
            "event": [],
            "critical": [],
            "error": [],
            "warning": [],
            "oom": [],
            "hardware_fault": [],
        }
        self._compile_patterns()
    
    def _compile_patterns(self):
        for source, patterns in [(LogSource.DMESG, self.DMESG_PATTERNS), 
                                  (LogSource.SYSLOG, self.SYSLOG_PATTERNS)]:
            self._patterns[source] = {}
            for severity, regexes in patterns.items():
                self._patterns[source][severity] = [re.compile(r, re.IGNORECASE) for r in regexes]
    
    def start(self):
        if self._running:
            return
        self._running = True
        
        if self._check_dmesg():
            self._start_dmesg_monitor()
        if self._check_syslog():
            self._start_syslog_monitor()
        if self._check_journald():
            self._start_journald_monitor()
    
    def stop(self):
        self._running = False
        for thread in self._monitor_threads.values():
            thread.join(timeout=2.0)
        self._monitor_threads.clear()
    
    def _check_dmesg(self) -> bool:
        try:
            subprocess.run(["dmesg", "--version"], capture_output=True, check=True, timeout=2)
            return True
        except Exception:
            return False
    
    def _check_syslog(self) -> bool:
        for path in ["/var/log/syslog", "/var/log/messages", "/var/log/kern.log"]:
            if Path(path).exists():
                return True
        return False
    
    def _check_journald(self) -> bool:
        try:
            subprocess.run(["journalctl", "--version"], capture_output=True, check=True, timeout=2)
            return True
        except Exception:
            return False
    
    def _start_dmesg_monitor(self):
        thread = threading.Thread(target=self._dmesg_loop, daemon=True)
        self._monitor_threads[LogSource.DMESG] = thread
        thread.start()
    
    def _dmesg_loop(self):
        last_seq = 0
        while self._running:
            try:
                result = subprocess.run(
                    ["dmesg", "-T", "--since", f"{self.tail_lines} lines ago"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                for line in result.stdout.strip().split('\n'):
                    if line:
                        self._process_line(LogSource.DMESG, line)
            except Exception:
                pass
            time.sleep(2.0)
    
    def _start_syslog_monitor(self):
        thread = threading.Thread(target=self._syslog_loop, daemon=True)
        self._monitor_threads[LogSource.SYSLOG] = thread
        thread.start()
    
    def _syslog_loop(self):
        log_files = ["/var/log/syslog", "/var/log/messages", "/var/log/kern.log"]
        positions = {f: 0 for f in log_files if Path(f).exists()}
        
        for f in positions:
            try:
                with open(f, 'r') as fp:
                    fp.seek(0, 2)
                    positions[f] = fp.tell()
            except Exception:
                pass
        
        while self._running:
            for log_file, pos in positions.items():
                try:
                    with open(log_file, 'r') as fp:
                        fp.seek(pos)
                        lines = fp.readlines()
                        positions[log_file] = fp.tell()
                        for line in lines:
                            self._process_line(LogSource.SYSLOG, line.strip())
                except Exception:
                    pass
            time.sleep(1.0)
    
    def _start_journald_monitor(self):
        thread = threading.Thread(target=self._journald_loop, daemon=True)
        self._monitor_threads[LogSource.JOURNALD] = thread
        thread.start()
    
    def _journald_loop(self):
        cursor = None
        while self._running:
            try:
                cmd = ["journalctl", "-k", "-f", "-n", "100", "-o", "short-iso"]
                if cursor:
                    cmd.extend(["--after-cursor", cursor])
                
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                
                for line in proc.stdout:
                    if not self._running:
                        break
                    if line.strip():
                        self._process_line(LogSource.JOURNALD, line.strip())
                
                proc.wait()
            except Exception:
                pass
            time.sleep(1.0)
    
    def _process_line(self, source: LogSource, line: str):
        severity = self._classify_severity(source, line)
        tags = self._extract_tags(source, line)
        
        event = LogEvent(
            event_id=f"{source.value}_{int(time.time() * 1000)}",
            source=source,
            severity=severity,
            timestamp=time.time(),
            message=line,
            raw_line=line,
            tags=tags
        )
        
        with self._lock:
            self._event_buffer.append(event)
        
        self._notify_event(event)
        
        if severity >= LogSeverity.CRITICAL:
            self._notify_critical(event)
        elif severity >= LogSeverity.ERROR:
            self._notify_error(event)
        elif severity >= LogSeverity.WARNING:
            self._notify_warning(event)
        
        if any(tag in tags for tag in ["oom", "out_of_memory"]):
            self._notify_oom(event)
        if any(tag in tags for tag in ["hardware_fault", "machine_check", "nmi"]):
            self._notify_hardware_fault(event)
    
    def _classify_severity(self, source: LogSource, line: str) -> LogSeverity:
        patterns = self._patterns.get(source, {})
        for severity in [LogSeverity.CRITICAL, LogSeverity.ERROR, LogSeverity.WARNING, 
                         LogSeverity.INFO, LogSeverity.DEBUG]:
            for pattern in patterns.get(severity, []):
                if pattern.search(line):
                    return severity
        return LogSeverity.INFO
    
    def _extract_tags(self, source: LogSource, line: str) -> List[str]:
        tags = []
        line_lower = line.lower()
        
        tag_patterns = {
            "oom": ["out of memory", "oom killer", "oom_score"],
            "hardware_fault": ["hardware error", "machine check", "mce", "nmi"],
            "kernel_panic": ["kernel panic"],
            "filesystem": ["ext4", "xfs", "btrfs", "filesystem", "inode"],
            "network": ["tcp", "udp", "network", "eth", "wlan"],
            "storage": ["scsi", "sata", "nvme", "block", "disk"],
            "memory": ["page", "slab", "kmalloc", "vmalloc", "memory"],
            "cpu": ["cpu", "core", "smp", "scheduler"],
            "driver": ["driver", "module", "firmware"],
            "security": ["selinux", "apparmor", "audit", "capability"],
        }
        
        for tag, patterns in tag_patterns.items():
            if any(p in line_lower for p in patterns):
                tags.append(tag)
        
        return tags
    
    def get_events(self, limit: int = 100, source: Optional[LogSource] = None,
                   severity: Optional[LogSeverity] = None, tags: Optional[List[str]] = None) -> List[LogEvent]:
        with self._lock:
            events = list(self._event_buffer)
        
        if source:
            events = [e for e in events if e.source == source]
        if severity:
            events = [e for e in events if e.severity >= severity]
        if tags:
            events = [e for e in events if any(t in e.tags for t in tags)]
        
        return events[-limit:]
    
    def get_recent_critical(self, limit: int = 10) -> List[LogEvent]:
        return self.get_events(limit=limit, severity=LogSeverity.CRITICAL)
    
    def get_oom_events(self, limit: int = 10) -> List[LogEvent]:
        return self.get_events(limit=limit, tags=["oom"])
    
    def get_hardware_faults(self, limit: int = 10) -> List[LogEvent]:
        return self.get_events(limit=limit, tags=["hardware_fault"])
    
    def register_callback(self, event: str, callback: Callable):
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    def _notify_event(self, event: LogEvent):
        for cb in self._callbacks["event"]:
            try:
                cb(event)
            except Exception:
                pass
    
    def _notify_critical(self, event: LogEvent):
        for cb in self._callbacks["critical"]:
            try:
                cb(event)
            except Exception:
                pass
    
    def _notify_error(self, event: LogEvent):
        for cb in self._callbacks["error"]:
            try:
                cb(event)
            except Exception:
                pass
    
    def _notify_warning(self, event: LogEvent):
        for cb in self._callbacks["warning"]:
            try:
                cb(event)
            except Exception:
                pass
    
    def _notify_oom(self, event: LogEvent):
        for cb in self._callbacks["oom"]:
            try:
                cb(event)
            except Exception:
                pass
    
    def _notify_hardware_fault(self, event: LogEvent):
        for cb in self._callbacks["hardware_fault"]:
            try:
                cb(event)
            except Exception:
                pass


_kernel_log_listener: Optional[KernelLogListener] = None

def get_kernel_log_listener() -> KernelLogListener:
    global _kernel_log_listener
    if _kernel_log_listener is None:
        from ..core.config import config
        tail = config.get_param("kernel", "log_tail_lines", 1000)
        _kernel_log_listener = KernelLogListener(tail_lines=tail)
        _kernel_log_listener.start()
    return _kernel_log_listener