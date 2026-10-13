"""
Deep Auditor - Comprehensive security audit engine
"""
import asyncio
import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class AuditType(Enum):
    STATIC_ANALYSIS = "static_analysis"
    DYNAMIC_ANALYSIS = "dynamic_analysis"
    DEPENDENCY_SCAN = "dependency_scan"
    CONFIGURATION_AUDIT = "configuration_audit"
    SECRETS_DETECTION = "secrets_detection"
    LICENSE_COMPLIANCE = "license_compliance"


class Severity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class AuditFinding:
    finding_id: str
    audit_type: AuditType
    severity: Severity
    title: str
    description: str
    file_path: str = ""
    line_number: int = 0
    column: int = 0
    rule_id: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    remediation: str = ""
    references: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    false_positive: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "audit_type": self.audit_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "column": self.column,
            "rule_id": self.rule_id,
            "evidence": self.evidence,
            "remediation": self.remediation,
            "references": self.references,
            "timestamp": self.timestamp,
            "false_positive": self.false_positive,
        }


@dataclass
class AuditResult:
    audit_id: str
    audit_type: AuditType
    target: str
    findings: list[AuditFinding] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    completed_at: float = 0.0
    duration: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def complete(self):
        self.completed_at = time.time()
        self.duration = self.completed_at - self.started_at

    def get_summary(self) -> dict[str, int]:
        summary = {s.value: 0 for s in Severity}
        for finding in self.findings:
            summary[finding.severity.value] += 1
        return summary


class DeepAuditor:
    def __init__(self):
        self.rules: dict[str, Callable] = {}
        self.audit_history: list[AuditResult] = []
        self._register_default_rules()

    def _register_default_rules(self):
        self.rules["hardcoded_secret"] = self._check_hardcoded_secrets
        self.rules["sql_injection"] = self._check_sql_injection
        self.rules["xss_vulnerability"] = self._check_xss
        self.rules["path_traversal"] = self._check_path_traversal
        self.rules["weak_crypto"] = self._check_weak_crypto
        self.rules["insecure_deserialization"] = self._check_insecure_deserialization
        self.rules["debug_enabled"] = self._check_debug_enabled
        self.rules["default_credentials"] = self._check_default_credentials

    def register_rule(self, rule_id: str, checker: Callable):
        self.rules[rule_id] = checker

    async def audit(self, target: str, audit_types: list[AuditType] = None) -> AuditResult:
        audit_types = audit_types or list(AuditType)

        result = AuditResult(
            audit_id=hashlib.md5(f"{target}:{time.time()}".encode()).hexdigest()[:12],
            audit_type=audit_types[0] if audit_types else AuditType.STATIC_ANALYSIS,
            target=target,
        )

        target_path = Path(target)

        for audit_type in audit_types:
            if audit_type == AuditType.STATIC_ANALYSIS:
                await self._static_analysis(target_path, result)
            elif audit_type == AuditType.DEPENDENCY_SCAN:
                await self._dependency_scan(target_path, result)
            elif audit_type == AuditType.CONFIGURATION_AUDIT:
                await self._configuration_audit(target_path, result)
            elif audit_type == AuditType.SECRETS_DETECTION:
                await self._secrets_detection(target_path, result)
            elif audit_type == AuditType.LICENSE_COMPLIANCE:
                await self._license_compliance(target_path, result)

        result.complete()
        self.audit_history.append(result)
        return result

    async def _static_analysis(self, target: Path, result: AuditResult):
        if target.is_file() and target.suffix == '.py':
            await self._audit_python_file(target, result)
        elif target.is_dir():
            for py_file in target.rglob('*.py'):
                await self._audit_python_file(py_file, result)

    async def _audit_python_file(self, file_path: Path, result: AuditResult):
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            lines = content.split('\n')

            for rule_id, checker in self.rules.items():
                findings = checker(file_path, content, lines)
                for finding in findings:
                    finding.audit_type = AuditType.STATIC_ANALYSIS
                    result.findings.append(finding)
        except Exception as e:
            result.findings.append(AuditFinding(
                finding_id=hashlib.md5(f"error:{file_path}".encode()).hexdigest()[:12],
                audit_type=AuditType.STATIC_ANALYSIS,
                severity=Severity.INFO,
                title="Audit Error",
                description=f"Failed to audit {file_path}: {e}",
                file_path=str(file_path),
            ))

    def _check_hardcoded_secrets(self, file_path: Path, content: str, lines: list[str]) -> list[AuditFinding]:
        findings = []
        patterns = [
            (r'api[_-]?key\s*=\s*["\'][^"\']+["\']', "API Key"),
            (r'secret[_-]?key\s*=\s*["\'][^"\']+["\']', "Secret Key"),
            (r'password\s*=\s*["\'][^"\']+["\']', "Password"),
            (r'token\s*=\s*["\'][^"\']+["\']', "Token"),
            (r'aws[_-]?access[_-]?key\s*=\s*["\'][^"\']+["\']', "AWS Access Key"),
            (r'private[_-]?key\s*=\s*["\'][^"\']+["\']', "Private Key"),
        ]

        import re
        for i, line in enumerate(lines):
            for pattern, desc in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append(AuditFinding(
                        finding_id=hashlib.md5(f"{file_path}:{i}:{pattern}".encode()).hexdigest()[:12],
                        audit_type=AuditType.STATIC_ANALYSIS,
                        severity=Severity.HIGH,
                        title=f"Hardcoded {desc}",
                        description=f"Possible hardcoded {desc.lower()} detected in source code",
                        file_path=str(file_path),
                        line_number=i + 1,
                        rule_id="hardcoded_secret",
                        evidence={"line": line.strip()},
                        remediation="Move secrets to environment variables or secure vault",
                    ))
        return findings

    def _check_sql_injection(self, file_path: Path, content: str, lines: list[str]) -> list[AuditFinding]:
        findings = []
        patterns = [
            r'\.execute\s*\(\s*["\'].*%.*["\']',
            r'\.execute\s*\(\s*f["\']',
            r'cursor\.execute\s*\(\s*["\'].*\+.*["\']',
        ]

        import re
        for i, line in enumerate(lines):
            for pattern in patterns:
                if re.search(pattern, line):
                    findings.append(AuditFinding(
                        finding_id=hashlib.md5(f"{file_path}:{i}:sql".encode()).hexdigest()[:12],
                        audit_type=AuditType.STATIC_ANALYSIS,
                        severity=Severity.HIGH,
                        title="Potential SQL Injection",
                        description="String formatting used in SQL query",
                        file_path=str(file_path),
                        line_number=i + 1,
                        rule_id="sql_injection",
                        evidence={"line": line.strip()},
                        remediation="Use parameterized queries or ORM",
                    ))
        return findings

    def _check_xss(self, file_path: Path, content: str, lines: list[str]) -> list[AuditFinding]:
        findings = []
        patterns = [
            r'render_template_string\s*\(',
            r'Markup\s*\(',
            r'innerHTML\s*=',
            r'dangerouslySetInnerHTML',
        ]

        import re
        for i, line in enumerate(lines):
            for pattern in patterns:
                if re.search(pattern, line):
                    findings.append(AuditFinding(
                        finding_id=hashlib.md5(f"{file_path}:{i}:xss".encode()).hexdigest()[:12],
                        audit_type=AuditType.STATIC_ANALYSIS,
                        severity=Severity.MEDIUM,
                        title="Potential XSS Vulnerability",
                        description="User input rendered without proper escaping",
                        file_path=str(file_path),
                        line_number=i + 1,
                        rule_id="xss_vulnerability",
                        evidence={"line": line.strip()},
                        remediation="Use template auto-escaping or sanitize input",
                    ))
        return findings

    def _check_path_traversal(self, file_path: Path, content: str, lines: list[str]) -> list[AuditFinding]:
        findings = []
        patterns = [
            r'open\s*\(\s*["\'].*\.\./',
            r'path\.join\s*\(.*request\.',
            r'send_file\s*\(.*request\.',
        ]

        import re
        for i, line in enumerate(lines):
            for pattern in patterns:
                if re.search(pattern, line):
                    findings.append(AuditFinding(
                        finding_id=hashlib.md5(f"{file_path}:{i}:path".encode()).hexdigest()[:12],
                        audit_type=AuditType.STATIC_ANALYSIS,
                        severity=Severity.HIGH,
                        title="Potential Path Traversal",
                        description="User input used in file path without validation",
                        file_path=str(file_path),
                        line_number=i + 1,
                        rule_id="path_traversal",
                        evidence={"line": line.strip()},
                        remediation="Validate and sanitize file paths, use safe path joining",
                    ))
        return findings

    def _check_weak_crypto(self, file_path: Path, content: str, lines: list[str]) -> list[AuditFinding]:
        findings = []
        patterns = [
            (r'hashlib\.md5\s*\(', "MD5"),
            (r'hashlib\.sha1\s*\(', "SHA1"),
            (r'Crypto\.Hash\.MD5', "MD5"),
            (r'Crypto\.Hash\.SHA1', "SHA1"),
            (r'RSA\.generate\s*\(\s*512', "Weak RSA Key"),
            (r'RSA\.generate\s*\(\s*1024', "Weak RSA Key"),
        ]

        import re
        for i, line in enumerate(lines):
            for pattern, desc in patterns:
                if re.search(pattern, line):
                    findings.append(AuditFinding(
                        finding_id=hashlib.md5(f"{file_path}:{i}:crypto".encode()).hexdigest()[:12],
                        audit_type=AuditType.STATIC_ANALYSIS,
                        severity=Severity.MEDIUM,
                        title=f"Weak Cryptography: {desc}",
                        description=f"Use of cryptographically weak {desc}",
                        file_path=str(file_path),
                        line_number=i + 1,
                        rule_id="weak_crypto",
                        evidence={"line": line.strip()},
                        remediation=f"Replace {desc} with stronger alternative (SHA256, RSA 2048+)",
                    ))
        return findings

    def _check_insecure_deserialization(self, file_path: Path, content: str, lines: list[str]) -> list[AuditFinding]:
        findings = []
        patterns = [
            r'pickle\.loads?\s*\(',
            r'yaml\.load\s*\((?!\s*Loader=)',
            r'marshal\.loads?\s*\(',
            r'shelve\.open\s*\(',
        ]

        import re
        for i, line in enumerate(lines):
            for pattern in patterns:
                if re.search(pattern, line):
                    findings.append(AuditFinding(
                        finding_id=hashlib.md5(f"{file_path}:{i}:deserialize".encode()).hexdigest()[:12],
                        audit_type=AuditType.STATIC_ANALYSIS,
                        severity=Severity.HIGH,
                        title="Insecure Deserialization",
                        description="Unsafe deserialization of untrusted data",
                        file_path=str(file_path),
                        line_number=i + 1,
                        rule_id="insecure_deserialization",
                        evidence={"line": line.strip()},
                        remediation="Use safe serialization formats (JSON) or specify safe loaders",
                    ))
        return findings

    def _check_debug_enabled(self, file_path: Path, content: str, lines: list[str]) -> list[AuditFinding]:
        findings = []
        patterns = [
            r'DEBUG\s*=\s*True',
            r'app\.debug\s*=\s*True',
            r'FLASK_DEBUG\s*=\s*1',
        ]

        import re
        for i, line in enumerate(lines):
            for pattern in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append(AuditFinding(
                        finding_id=hashlib.md5(f"{file_path}:{i}:debug".encode()).hexdigest()[:12],
                        audit_type=AuditType.CONFIGURATION_AUDIT,
                        severity=Severity.LOW,
                        title="Debug Mode Enabled",
                        description="Debug mode enabled in production code",
                        file_path=str(file_path),
                        line_number=i + 1,
                        rule_id="debug_enabled",
                        evidence={"line": line.strip()},
                        remediation="Disable debug mode in production",
                    ))
        return findings

    def _check_default_credentials(self, file_path: Path, content: str, lines: list[str]) -> list[AuditFinding]:
        findings = []
        patterns = [
            (r'admin\s*:\s*admin', "admin:admin"),
            (r'root\s*:\s*root', "root:root"),
            (r'password\s*=\s*["\']password["\']', "password"),
            (r'username\s*=\s*["\']admin["\'].*password\s*=\s*["\']admin["\']', "admin/admin"),
        ]

        import re
        for i, line in enumerate(lines):
            for pattern, desc in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append(AuditFinding(
                        finding_id=hashlib.md5(f"{file_path}:{i}:default".encode()).hexdigest()[:12],
                        audit_type=AuditType.CONFIGURATION_AUDIT,
                        severity=Severity.CRITICAL,
                        title=f"Default Credentials: {desc}",
                        description=f"Default credentials detected: {desc}",
                        file_path=str(file_path),
                        line_number=i + 1,
                        rule_id="default_credentials",
                        evidence={"line": line.strip()},
                        remediation="Change default credentials immediately",
                    ))
        return findings

    async def _dependency_scan(self, target: Path, result: AuditResult):
        pass

    async def _configuration_audit(self, target: Path, result: AuditResult):
        pass

    async def _secrets_detection(self, target: Path, result: AuditResult):
        pass

    async def _license_compliance(self, target: Path, result: AuditResult):
        pass

    def get_history(self, limit: int = 100) -> list[AuditResult]:
        return self.audit_history[-limit:]

    def get_findings_by_severity(self, severity: Severity) -> list[AuditFinding]:
        findings = []
        for result in self.audit_history:
            findings.extend([f for f in result.findings if f.severity == severity])
        return findings


class AuditScheduler:
    def __init__(self, auditor: DeepAuditor):
        self.auditor = auditor
        self.schedules: dict[str, dict] = {}
        self._running = False
        self._task: asyncio.Task | None = None

    def add_schedule(self, name: str, target: str, audit_types: list[AuditType], interval_hours: float):
        self.schedules[name] = {
            "target": target,
            "audit_types": audit_types,
            "interval": interval_hours * 3600,
            "last_run": 0,
        }

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _scheduler_loop(self):
        while self._running:
            now = time.time()
            for name, schedule in self.schedules.items():
                if now - schedule["last_run"] >= schedule["interval"]:
                    await self.auditor.audit(schedule["target"], schedule["audit_types"])
                    schedule["last_run"] = now
            await asyncio.sleep(60)
