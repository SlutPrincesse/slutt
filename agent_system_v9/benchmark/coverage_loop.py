"""
Coverage Loop - Test coverage analysis and enforcement
"""
import hashlib
import json
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class CoverageType(Enum):
    LINE = "line"
    BRANCH = "branch"
    FUNCTION = "function"
    STATEMENT = "statement"


@dataclass
class CoverageData:
    file_path: str
    line_coverage: dict[int, int] = field(default_factory=dict)
    branch_coverage: dict[str, int] = field(default_factory=dict)
    function_coverage: dict[str, int] = field(default_factory=dict)
    total_lines: int = 0
    covered_lines: int = 0
    total_branches: int = 0
    covered_branches: int = 0
    total_functions: int = 0
    covered_functions: int = 0

    def line_coverage_percent(self) -> float:
        if self.total_lines == 0:
            return 100.0
        return (self.covered_lines / self.total_lines) * 100

    def branch_coverage_percent(self) -> float:
        if self.total_branches == 0:
            return 100.0
        return (self.covered_branches / self.total_branches) * 100

    def function_coverage_percent(self) -> float:
        if self.total_functions == 0:
            return 100.0
        return (self.covered_functions / self.total_functions) * 100

    def overall_coverage(self) -> float:
        return (self.line_coverage_percent() + self.branch_coverage_percent() + self.function_coverage_percent()) / 3


@dataclass
class CoverageThreshold:
    min_line_coverage: float = 80.0
    min_branch_coverage: float = 70.0
    min_function_coverage: float = 90.0
    min_overall_coverage: float = 80.0
    enforce_on_new_code: bool = True
    new_code_threshold: float = 90.0


@dataclass
class CoverageReport:
    report_id: str
    timestamp: float = field(default_factory=time.time)
    files: list[CoverageData] = field(default_factory=list)
    total_coverage: CoverageData = field(default_factory=CoverageData)
    passed: bool = True
    failed_files: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "timestamp": self.timestamp,
            "files": [
                {
                    "file_path": f.file_path,
                    "line_coverage": f.line_coverage_percent(),
                    "branch_coverage": f.branch_coverage_percent(),
                    "function_coverage": f.function_coverage_percent(),
                    "total_lines": f.total_lines,
                    "covered_lines": f.covered_lines,
                }
                for f in self.files
            ],
            "total_coverage": {
                "line": self.total_coverage.line_coverage_percent(),
                "branch": self.total_coverage.branch_coverage_percent(),
                "function": self.total_coverage.function_coverage_percent(),
                "overall": self.total_coverage.overall_coverage(),
            },
            "passed": self.passed,
            "failed_files": self.failed_files,
            "metadata": self.metadata,
        }


class CoverageCollector:
    def __init__(self):
        self.data: dict[str, CoverageData] = {}

    def collect_from_pytest(self, project_path: str = ".") -> CoverageReport:
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "--cov=.", "--cov-report=json", "-q"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=300,
            )

            coverage_file = Path(project_path) / "coverage.json"
            if coverage_file.exists():
                data = json.loads(coverage_file.read_text())
                return self._parse_pytest_coverage(data)
        except Exception:
            pass

        return CoverageReport(
            report_id=hashlib.md5(f"coverage:{time.time()}".encode()).hexdigest()[:12],
            passed=False,
        )

    def _parse_pytest_coverage(self, data: dict) -> CoverageReport:
        report = CoverageReport(
            report_id=hashlib.md5(f"coverage:{time.time()}".encode()).hexdigest()[:12],
        )

        files_data = data.get("files", {})
        total = CoverageData()

        for file_path, file_data in files_data.items():
            coverage = CoverageData(file_path=file_path)

            executed_lines = file_data.get("executed_lines", [])
            missing_lines = file_data.get("missing_lines", [])

            all_lines = set(executed_lines) | set(missing_lines)
            coverage.total_lines = len(all_lines)
            coverage.covered_lines = len(executed_lines)

            for line in executed_lines:
                coverage.line_coverage[line] = 1
            for line in missing_lines:
                coverage.line_coverage[line] = 0

            summary = file_data.get("summary", {})
            coverage.total_branches = summary.get("num_branches", 0)
            coverage.covered_branches = summary.get("covered_branches", 0)

            report.files.append(coverage)
            total.total_lines += coverage.total_lines
            total.covered_lines += coverage.covered_lines
            total.total_branches += coverage.total_branches
            total.covered_branches += coverage.covered_branches

        report.total_coverage = total
        report.passed = total.line_coverage_percent() >= 80

        return report

    def collect_from_coverage_py(self, project_path: str = ".") -> CoverageReport:
        try:
            import coverage
            cov = coverage.Coverage()
            cov.load()

            report = CoverageReport(
                report_id=hashlib.md5(f"coverage:{time.time()}".encode()).hexdigest()[:12],
            )

            total = CoverageData()

            for file_path in cov.get_data().measured_files():
                file_cov = CoverageData(file_path=file_path)

                analysis = cov._analyze(file_path)
                if analysis:
                    executed = analysis.executed
                    missing = analysis.missing

                    all_lines = set(executed) | set(missing)
                    file_cov.total_lines = len(all_lines)
                    file_cov.covered_lines = len(executed)

                    for line in executed:
                        file_cov.line_coverage[line] = 1
                    for line in missing:
                        file_cov.line_coverage[line] = 0

                report.files.append(file_cov)
                total.total_lines += file_cov.total_lines
                total.covered_lines += file_cov.covered_lines

            report.total_coverage = total
            report.passed = total.line_coverage_percent() >= 80

            return report
        except ImportError:
            return CoverageReport(
                report_id=hashlib.md5(f"coverage:{time.time()}".encode()).hexdigest()[:12],
                passed=False,
            )


class CoverageAnalyzer:
    def __init__(self, thresholds: CoverageThreshold = None):
        self.thresholds = thresholds or CoverageThreshold()

    def analyze(self, report: CoverageReport) -> dict[str, Any]:
        results = {
            "passed": True,
            "file_results": [],
            "overall": {
                "line": report.total_coverage.line_coverage_percent(),
                "branch": report.total_coverage.branch_coverage_percent(),
                "function": report.total_coverage.function_coverage_percent(),
                "overall": report.total_coverage.overall_coverage(),
            },
        }

        if report.total_coverage.line_coverage_percent() < self.thresholds.min_line_coverage:
            results["passed"] = False

        if report.total_coverage.branch_coverage_percent() < self.thresholds.min_branch_coverage:
            results["passed"] = False

        if report.total_coverage.function_coverage_percent() < self.thresholds.min_function_coverage:
            results["passed"] = False

        if report.total_coverage.overall_coverage() < self.thresholds.min_overall_coverage:
            results["passed"] = False

        for file_cov in report.files:
            file_result = {
                "file": file_cov.file_path,
                "line_coverage": file_cov.line_coverage_percent(),
                "branch_coverage": file_cov.branch_coverage_percent(),
                "function_coverage": file_cov.function_coverage_percent(),
                "passed": True,
                "issues": [],
            }

            if file_cov.line_coverage_percent() < self.thresholds.min_line_coverage:
                file_result["passed"] = False
                file_result["issues"].append(f"Line coverage {file_cov.line_coverage_percent():.1f}% below threshold {self.thresholds.min_line_coverage}%")

            if file_cov.branch_coverage_percent() < self.thresholds.min_branch_coverage:
                file_result["passed"] = False
                file_result["issues"].append(f"Branch coverage {file_cov.branch_coverage_percent():.1f}% below threshold {self.thresholds.min_branch_coverage}%")

            if file_cov.function_coverage_percent() < self.thresholds.min_function_coverage:
                file_result["passed"] = False
                file_result["issues"].append(f"Function coverage {file_cov.function_coverage_percent():.1f}% below threshold {self.thresholds.min_function_coverage}%")

            results["file_results"].append(file_result)

        return results

    def get_uncovered_lines(self, report: CoverageReport, file_path: str) -> list[int]:
        for file_cov in report.files:
            if file_cov.file_path == file_path:
                return [line for line, covered in file_cov.line_coverage.items() if covered == 0]
        return []

    def get_coverage_gaps(self, report: CoverageReport) -> list[dict[str, Any]]:
        gaps = []
        for file_cov in report.files:
            if file_cov.line_coverage_percent() < 100:
                uncovered = self.get_uncovered_lines(report, file_cov.file_path)
                if uncovered:
                    gaps.append({
                        "file": file_cov.file_path,
                        "uncovered_lines": uncovered[:20],
                        "total_uncovered": len(uncovered),
                        "coverage_percent": file_cov.line_coverage_percent(),
                    })
        return gaps


class CoverageEnforcer:
    def __init__(self, analyzer: CoverageAnalyzer):
        self.analyzer = analyzer
        self.history: list[CoverageReport] = []

    def enforce(self, report: CoverageReport) -> bool:
        results = self.analyzer.analyze(report)

        if not results["passed"]:
            self.history.append(report)
            if len(self.history) > 100:
                self.history = self.history[-100:]
            return False

        self.history.append(report)
        if len(self.history) > 100:
            self.history = self.history[-100:]
        return True

    def enforce_on_diff(self, base_report: CoverageReport, head_report: CoverageReport) -> dict[str, Any]:
        base_files = {f.file_path: f for f in base_report.files}
        head_files = {f.file_path: f for f in head_report.files}

        new_files = set(head_files.keys()) - set(base_files.keys())
        modified_files = set()

        for path in head_files:
            if path in base_files:
                if head_files[path].line_coverage_percent() < base_files[path].line_coverage_percent():
                    modified_files.add(path)

        return {
            "new_files": list(new_files),
            "modified_files": list(modified_files),
            "new_files_coverage": {
                path: head_files[path].line_coverage_percent() for path in new_files
            },
            "enforce_new_code": self.analyzer.thresholds.enforce_on_new_code,
        }


class CoverageLoop:
    def __init__(
        self,
        collector: CoverageCollector = None,
        analyzer: CoverageAnalyzer = None,
        enforcer: CoverageEnforcer = None,
    ):
        self.collector = collector or CoverageCollector()
        self.analyzer = analyzer or CoverageAnalyzer()
        self.enforcer = enforcer or CoverageEnforcer(self.analyzer)
        self._running = False
        self._task = None
        self._callbacks: list[Callable] = []

    def on_coverage_check(self, callback: Callable):
        self._callbacks.append(callback)

    async def run_once(self, project_path: str = ".") -> CoverageReport:
        report = self.collector.collect_from_pytest(project_path)

        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(report)
                else:
                    callback(report)
            except Exception:
                pass

        return report

    async def start_loop(self, interval: float = 300.0, project_path: str = "."):
        self._running = True
        self._task = asyncio.create_task(self._loop(interval, project_path))

    async def stop_loop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self, interval: float, project_path: str):
        while self._running:
            await self.run_once(project_path)
            await asyncio.sleep(interval)

    def get_history(self) -> list[CoverageReport]:
        return self.enforcer.history

    def get_trend(self, file_path: str = None) -> dict[str, Any]:
        if not self.enforcer.history:
            return {}

        recent = self.enforcer.history[-20:]

        if file_path:
            coverages = [
                next((f.line_coverage_percent() for f in r.files if f.file_path == file_path), 0)
                for r in recent
            ]
        else:
            coverages = [r.total_coverage.line_coverage_percent() for r in recent]

        return {
            "samples": len(coverages),
            "current": coverages[-1] if coverages else 0,
            "average": sum(coverages) / len(coverages) if coverages else 0,
            "min": min(coverages) if coverages else 0,
            "max": max(coverages) if coverages else 0,
            "trend": "improving" if len(coverages) > 1 and coverages[-1] > coverages[0] else "stable",
        }


import asyncio
