"""
No-Op Detector - Detects dead code and no-op operations
"""
import ast
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class NoOpType(Enum):
    UNUSED_VARIABLE = "unused_variable"
    UNUSED_FUNCTION = "unused_function"
    UNUSED_IMPORT = "unused_import"
    DEAD_CODE = "dead_code"
    NO_EFFECT_STATEMENT = "no_effect_statement"
    REDUNDANT_ASSIGNMENT = "redundant_assignment"
    UNREACHABLE_CODE = "unreachable_code"
    EMPTY_BLOCK = "empty_block"
    USELESS_EXCEPTION = "useless_exception"
    IDENTITY_OPERATION = "identity_operation"
    TRAILING_WHITESPACE = "trailing_whitespace"


@dataclass
class NoOpIssue:
    file_path: str
    line_number: int
    column: int
    op_type: NoOpType
    message: str
    severity: str
    code_snippet: str = ""
    suggestion: str = ""
    auto_fixable: bool = False


@dataclass
class NoOpReport:
    file_path: str
    issues: list[NoOpIssue] = field(default_factory=list)
    total_issues: int = 0

    def __post_init__(self):
        self.total_issues = len(self.issues)

    def by_type(self) -> dict[NoOpType, int]:
        counts: dict[NoOpType, int] = defaultdict(int)
        for issue in self.issues:
            counts[issue.op_type] += 1
        return dict(counts)

    def by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for issue in self.issues:
            counts[issue.severity] += 1
        return dict(counts)


class NoOpDetector:
    def __init__(self):
        self.ignore_private = True
        self.ignore_test_files = True
        self.check_unused_variables = True
        self.check_unused_functions = True
        self.check_dead_code = True
        self.check_unreachable = True

    def check_file(self, file_path: str) -> NoOpReport:
        path = Path(file_path)
        content = path.read_text(encoding='utf-8', errors='ignore')
        return self.check_string(content, file_path)

    def check_string(self, content: str, file_path: str = "<string>") -> NoOpReport:
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            return NoOpReport(file_path=file_path, issues=[NoOpIssue(
                file_path=file_path,
                line_number=e.lineno or 0,
                column=e.offset or 0,
                op_type=NoOpType.DEAD_CODE,
                message=f"Syntax error: {e.msg}",
                severity="error",
            )])

        report = NoOpReport(file_path=file_path)
        lines = content.split('\n')

        visitor = NoOpVisitor(report, self, lines)
        visitor.visit(tree)

        return report

    def check_directory(self, dir_path: str, pattern: str = "*.py") -> dict[str, NoOpReport]:
        reports = {}
        for file_path in Path(dir_path).rglob(pattern):
            if self.ignore_test_files and ('test' in str(file_path).lower() or 'spec' in str(file_path).lower()):
                continue
            reports[str(file_path)] = self.check_file(str(file_path))
        return reports

    def get_summary(self, reports: dict[str, NoOpReport]) -> dict[str, Any]:
        all_issues = []
        for report in reports.values():
            all_issues.extend(report.issues)

        by_type: dict[str, int] = defaultdict(int)
        by_severity: dict[str, int] = defaultdict(int)

        for issue in all_issues:
            by_type[issue.op_type.value] += 1
            by_severity[issue.severity] += 1

        return {
            "files_checked": len(reports),
            "total_issues": len(all_issues),
            "by_type": dict(by_type),
            "by_severity": dict(by_severity),
            "auto_fixable": sum(1 for i in all_issues if i.auto_fixable),
        }

    def auto_fix(self, file_path: str, dry_run: bool = True) -> tuple[int, list[str]]:
        path = Path(file_path)
        content = path.read_text(encoding='utf-8', errors='ignore')

        report = self.check_string(content, file_path)
        fixes_applied = 0
        changes = []

        lines = content.split('\n')

        for issue in sorted(report.issues, key=lambda x: x.line_number, reverse=True):
            if issue.auto_fixable:
                if issue.op_type == NoOpType.UNUSED_IMPORT:
                    if self._remove_unused_import(lines, issue):
                        fixes_applied += 1
                        changes.append(f"Removed unused import at line {issue.line_number}")
                elif issue.op_type == NoOpType.TRAILING_WHITESPACE:
                    if self._fix_trailing_whitespace(lines, issue):
                        fixes_applied += 1
                        changes.append(f"Fixed trailing whitespace at line {issue.line_number}")

        if not dry_run and fixes_applied > 0:
            path.write_text('\n'.join(lines))

        return fixes_applied, changes

    def _remove_unused_import(self, lines: list[str], issue: NoOpIssue) -> bool:
        line_idx = issue.line_number - 1
        if 0 <= line_idx < len(lines):
            lines[line_idx] = ''
            return True
        return False

    def _fix_trailing_whitespace(self, lines: list[str], issue: NoOpIssue) -> bool:
        line_idx = issue.line_number - 1
        if 0 <= line_idx < len(lines):
            lines[line_idx] = lines[line_idx].rstrip()
            return True
        return False


class NoOpVisitor(ast.NodeVisitor):
    def __init__(self, report: NoOpReport, detector: NoOpDetector, lines: list[str]):
        self.report = report
        self.detector = detector
        self.lines = lines
        self.defined_names: set[str] = set()
        self.used_names: set[str] = set()
        self.imported_names: dict[str, tuple[int, int]] = {}
        self.current_function: str | None = None
        self.in_loop = False
        self.in_function = False
        self.returned = False

    def visit_Module(self, node: ast.Module):
        self.generic_visit(node)
        self._check_unused()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        if self.detector.ignore_private and node.name.startswith('_') and not node.name.startswith('__'):
            self.generic_visit(node)
            return

        old_function = self.current_function
        old_returned = self.returned
        self.current_function = node.name
        self.returned = False
        self.in_function = True

        for arg in node.args.args:
            self.defined_names.add(arg.arg)

        self.generic_visit(node)

        if not self.returned and node.name != '__init__':
            if not any(isinstance(n, ast.Return) for n in ast.walk(node) if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
                self.report.issues.append(NoOpIssue(
                    file_path=self.report.file_path,
                    line_number=node.lineno,
                    column=node.col_offset,
                    op_type=NoOpType.UNUSED_FUNCTION,
                    message=f"Function '{node.name}' has no return statement",
                    severity="info",
                    code_snippet=self._get_snippet(node.lineno),
                    suggestion="Add return statement or remove function if not needed",
                ))

        self.current_function = old_function
        self.returned = old_returned
        self.in_function = False

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.visit_FunctionDef(node)

    def visit_Return(self, node: ast.Return):
        self.returned = True
        self.generic_visit(node)

    def visit_For(self, node: ast.For):
        old_in_loop = self.in_loop
        self.in_loop = True
        self.generic_visit(node)
        self.in_loop = old_in_loop

    def visit_While(self, node: ast.While):
        old_in_loop = self.in_loop
        self.in_loop = True
        self.generic_visit(node)
        self.in_loop = old_in_loop

    def visit_Assign(self, node: ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.defined_names.add(target.id)

                if isinstance(node.value, ast.Constant) and node.value.value is None:
                    self.report.issues.append(NoOpIssue(
                        file_path=self.report.file_path,
                        line_number=node.lineno,
                        column=node.col_offset,
                        op_type=NoOpType.REDUNDANT_ASSIGNMENT,
                        message=f"Assignment of None to '{target.id}'",
                        severity="info",
                        code_snippet=self._get_snippet(node.lineno),
                        suggestion="Remove redundant None assignment",
                        auto_fixable=True,
                    ))

        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Load):
            self.used_names.add(node.id)
        elif isinstance(node.ctx, ast.Store):
            self.defined_names.add(node.id)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            name = alias.asname or alias.name.split('.')[0]
            self.imported_names[name] = (node.lineno, node.col_offset)
            self.defined_names.add(name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        for alias in node.names:
            name = alias.asname or alias.name
            self.imported_names[name] = (node.lineno, node.col_offset)
            self.defined_names.add(name)
        self.generic_visit(node)

    def visit_Pass(self, node: ast.Pass):
        if self.current_function:
            func_node = None
            for n in ast.walk(self.report.__dict__.get('_tree', None) or []):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.lineno <= node.lineno <= getattr(n, 'end_lineno', node.lineno):
                    func_node = n
                    break

            if func_node and len(func_node.body) == 1:
                self.report.issues.append(NoOpIssue(
                    file_path=self.report.file_path,
                    line_number=node.lineno,
                    column=node.col_offset,
                    op_type=NoOpType.EMPTY_BLOCK,
                    message=f"Function '{self.current_function}' contains only 'pass'",
                    severity="warning",
                    code_snippet=self._get_snippet(node.lineno),
                    suggestion="Implement the function or raise NotImplementedError",
                    auto_fixable=False,
                ))
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try):
        for handler in node.handlers:
            if handler.type is None:
                self.report.issues.append(NoOpIssue(
                    file_path=self.report.file_path,
                    line_number=handler.lineno,
                    column=handler.col_offset,
                    op_type=NoOpType.USELESS_EXCEPTION,
                    message="Bare 'except:' catches all exceptions",
                    severity="warning",
                    code_snippet=self._get_snippet(handler.lineno),
                    suggestion="Specify exception type",
                ))
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare):
        if len(node.ops) == 1 and len(node.comparators) == 1:
            if isinstance(node.ops[0], (ast.Is, ast.IsNot)):
                left = node.left
                right = node.comparators[0]
                if (isinstance(left, ast.Name) and isinstance(right, ast.Name) and left.id == right.id) or \
                   (isinstance(left, ast.Constant) and isinstance(right, ast.Constant) and left.value == right.value):
                    self.report.issues.append(NoOpIssue(
                        file_path=self.report.file_path,
                        line_number=node.lineno,
                        column=node.col_offset,
                        op_type=NoOpType.IDENTITY_OPERATION,
                        message="Identity comparison (x is x) is always True/False",
                        severity="warning",
                        code_snippet=self._get_snippet(node.lineno),
                        suggestion="Remove redundant comparison",
                    ))
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant):
        self.generic_visit(node)

    def _check_unused(self):
        unused = self.defined_names - self.used_names

        for name in unused:
            if name in self.imported_names:
                lineno, col = self.imported_names[name]
                self.report.issues.append(NoOpIssue(
                    file_path=self.report.file_path,
                    line_number=lineno,
                    column=col,
                    op_type=NoOpType.UNUSED_IMPORT,
                    message=f"Unused import: {name}",
                    severity="warning",
                    code_snippet=self._get_snippet(lineno),
                    suggestion="Remove unused import",
                    auto_fixable=True,
                ))
            elif not name.startswith('_'):
                self.report.issues.append(NoOpIssue(
                    file_path=self.report.file_path,
                    line_number=0,
                    column=0,
                    op_type=NoOpType.UNUSED_VARIABLE,
                    message=f"Potentially unused variable: {name}",
                    severity="info",
                    suggestion="Use the variable or prefix with '_'",
                ))

    def _get_snippet(self, line_number: int) -> str:
        idx = line_number - 1
        if 0 <= idx < len(self.lines):
            return self.lines[idx].strip()
        return ""


class DeadCodeAnalyzer:
    def __init__(self):
        self.detector = NoOpDetector()

    def analyze(self, file_path: str) -> dict[str, Any]:
        report = self.detector.check_file(file_path)

        unreachable = [i for i in report.issues if i.op_type == NoOpType.UNREACHABLE_CODE]
        dead = [i for i in report.issues if i.op_type == NoOpType.DEAD_CODE]
        empty = [i for i in report.issues if i.op_type == NoOpType.EMPTY_BLOCK]

        return {
            "file": file_path,
            "unreachable_count": len(unreachable),
            "dead_code_count": len(dead),
            "empty_block_count": len(empty),
            "total_issues": report.total_issues,
            "issues": [self._issue_to_dict(i) for i in report.issues],
        }

    def _issue_to_dict(self, issue: NoOpIssue) -> dict[str, Any]:
        return {
            "type": issue.op_type.value,
            "line": issue.line_number,
            "column": issue.column,
            "message": issue.message,
            "severity": issue.severity,
            "snippet": issue.code_snippet,
            "suggestion": issue.suggestion,
            "auto_fixable": issue.auto_fixable,
        }