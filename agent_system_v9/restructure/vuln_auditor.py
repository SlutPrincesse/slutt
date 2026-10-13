"""
Automated Vulnerability Cron Auditor - Scheduled worker auditing local binaries against origins for patches
"""
import hashlib
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class VulnerabilityReport:
    report_id: str
    binary_name: str
    binary_path: str
    current_version: str
    latest_version: str
    vulnerabilities: list[dict[str, Any]]
    severity: Severity
    scan_time: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class VulnerabilityAuditor:
    def __init__(self, scan_interval: float = 3600):
        self.scan_interval = scan_interval
        self._running = False
        self._scan_thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._reports: list[VulnerabilityReport] = []
        self._binary_sources: dict[str, dict[str, Any]] = {}
        self._callbacks: dict[str, list[Callable]] = {
            "scan_started": [],
            "scan_completed": [],
            "vulnerability_found": [],
            "patch_available": []
        }

    def start(self):
        if self._running:
            return
        self._running = True
        self._scan_thread = threading.Thread(target=self._scan_loop, daemon=True)
        self._scan_thread.start()

    def stop(self):
        self._running = False
        if self._scan_thread:
            self._scan_thread.join(timeout=5.0)

    def register_binary(self, name: str, path: str, source: dict[str, Any]):
        with self._lock:
            self._binary_sources[name] = {"path": path, "source": source}

    def scan_now(self) -> list[VulnerabilityReport]:
        reports = []
        with self._lock:
            sources = dict(self._binary_sources)

        for name, info in sources.items():
            report = self._scan_binary(name, info["path"], info["source"])
            if report:
                reports.append(report)
                self._notify_vulnerability_found(report)

        with self._lock:
            self._reports.extend(reports)

        return reports

    def _scan_loop(self):
        while self._running:
            time.sleep(self.scan_interval)
            if self._running:
                self.scan_now()

    def _scan_binary(self, name: str, path: str, source: dict) -> VulnerabilityReport | None:
        try:
            current_version = self._get_version(path)
            latest_version = self._get_latest_version(source)

            if not latest_version or current_version == latest_version:
                return None

            vulns = self._check_vulnerabilities(name, current_version, latest_version)

            if not vulns:
                return None

            severity = self._calculate_severity(vulns)

            return VulnerabilityReport(
                report_id=f"vuln_{hashlib.md5(f'{name}{time.time()}'.encode()).hexdigest()[:8]}",
                binary_name=name,
                binary_path=path,
                current_version=current_version,
                latest_version=latest_version,
                vulnerabilities=vulns,
                severity=severity
            )
        except Exception:
            return None

    def _get_version(self, path: str) -> str:
        try:
            result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                import re
                match = re.search(r'(\d+\.\d+\.\d+)', result.stdout)
                if match:
                    return match.group(1)
        except Exception:
            pass
        return "unknown"

    def _get_latest_version(self, source: dict) -> str | None:
        # Would query package registry, GitHub releases, etc.
        return source.get("latest_version")

    def _check_vulnerabilities(self, name: str, current: str, latest: str) -> list[dict]:
        # Would check CVE databases, security advisories
        return [{"cve": "CVE-2024-XXXX", "description": "Example vulnerability", "fixed_in": latest}]

    def _calculate_severity(self, vulns: list[dict]) -> Severity:
        return Severity.HIGH

    def get_reports(self, limit: int = 100) -> list[VulnerabilityReport]:
        with self._lock:
            return self._reports[-limit:]

    def register_callback(self, event: str, callback: Callable):
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def _notify_scan_started(self):
        for cb in self._callbacks["scan_started"]:
            try:
                cb()
            except Exception:
                pass

    def _notify_scan_completed(self, reports: list):
        for cb in self._callbacks["scan_completed"]:
            try:
                cb(reports)
            except Exception:
                pass

    def _notify_vulnerability_found(self, report: VulnerabilityReport):
        for cb in self._callbacks["vulnerability_found"]:
            try:
                cb(report)
            except Exception:
                pass

    def _notify_patch_available(self, report: VulnerabilityReport):
        for cb in self._callbacks["patch_available"]:
            try:
                cb(report)
            except Exception:
                pass


_vuln_auditor: VulnerabilityAuditor | None = None


def get_vulnerability_auditor() -> VulnerabilityAuditor:
    global _vuln_auditor
    if _vuln_auditor is None:
        from ..core.config import config
        interval = config.get_param("restructure", "vulnerability_scan_interval", 3600)
        _vuln_auditor = VulnerabilityAuditor(scan_interval=interval)
        _vuln_auditor.start()
    return _vuln_auditor
