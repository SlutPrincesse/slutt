"""
Typing Guard - Enforces type hints in Python code
"""
import ast
import sys
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class TypeHintLevel(Enum):
    NONE = "none"
    BASIC = "basic"
    STRICT = "strict"
    FULL = "full"


@dataclass
class TypingIssue:
    file_path: str
    line_number: int
    column: int
    issue_type: str
    message: str
    severity: str
    suggestion: str = ""
    auto_fixable: bool = False


@dataclass
class TypingReport:
    file_path: str
    total_functions: int = 0
    typed_functions: int = 0
    total_parameters: int = 0
    typed_parameters: int = 0
    total_returns: int = 0
    typed_returns: int = 0
    issues: List[TypingIssue] = None
    
    def __post_init__(self):
        if self.issues is None:
            self.issues = []
    
    @property
    def function_coverage(self) -> float:
        return self.typed_functions / max(self.total_functions, 1)
    
    @property
    def parameter_coverage(self) -> float:
        return self.typed_parameters / max(self.total_parameters, 1)
    
    @property
    def return_coverage(self) -> float:
        return self.typed_returns / max(self.total_returns, 1)
    
    @property
    def overall_coverage(self) -> float:
        return (self.function_coverage + self.parameter_coverage + self.return_coverage) / 3


class TypingGuard:
    def __init__(self, level: TypeHintLevel = TypeHintLevel.BASIC):
        self.level = level
        self.ignore_private = True
        self.ignore_dunder = True
        self.ignore_overload = True
        self.ignore_protocol = True

    def check_file(self, file_path: str) -> TypingReport:
        path = Path(file_path)
        content = path.read_text(encoding='utf-8', errors='ignore')
        return self.check_string(content, file_path)

    def check_string(self, content: str, file_path: str = "<string>") -> TypingReport:
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            return TypingReport(file_path=file_path, issues=[TypingIssue(
                file_path=file_path,
                line_number=e.lineno or 0,
                column=e.offset or 0,
                issue_type="syntax_error",
                message=f"Syntax error: {e.msg}",
                severity="error",
            )])
        
        report = TypingReport(file_path=file_path)
        visitor = TypingVisitor(report, self)
        visitor.visit(tree)
        return report

    def check_directory(self, dir_path: str, pattern: str = "*.py") -> Dict[str, TypingReport]:
        reports = {}
        for file_path in Path(dir_path).rglob(pattern):
            reports[str(file_path)] = self.check_file(str(file_path))
        return reports

    def get_summary(self, reports: Dict[str, TypingReport]) -> Dict[str, Any]:
        total_functions = sum(r.total_functions for r in reports.values())
        total_typed = sum(r.typed_functions for r in reports.values())
        total_params = sum(r.total_parameters for r in reports.values())
        total_typed_params = sum(r.typed_parameters for r in reports.values())
        total_returns = sum(r.total_returns for r in reports.values())
        total_typed_returns = sum(r.typed_returns for r in reports.values())
        
        all_issues = []
        for report in reports.values():
            all_issues.extend(report.issues)
        
        by_severity = {}
        for issue in all_issues:
            by_severity[issue.severity] = by_severity.get(issue.severity, 0) + 1
        
        return {
            "files_checked": len(reports),
            "total_functions": total_functions,
            "typed_functions": total_typed,
            "function_coverage": total_typed / max(total_functions, 1),
            "total_parameters": total_params,
            "typed_parameters": total_typed_params,
            "parameter_coverage": total_typed_params / max(total_params, 1),
            "total_returns": total_returns,
            "typed_returns": total_typed_returns,
            "return_coverage": total_typed_returns / max(total_returns, 1),
            "issues_by_severity": by_severity,
            "total_issues": len(all_issues),
        }

    def auto_fix(self, file_path: str, dry_run: bool = True) -> Tuple[int, List[str]]:
        path = Path(file_path)
        content = path.read_text(encoding='utf-8', errors='ignore')
        
        report = self.check_string(content, file_path)
        fixes_applied = 0
        changes = []
        
        lines = content.split('\n')
        
        for issue in report.issues:
            if issue.auto_fixable and issue.issue_type == "missing_return_type":
                if self._fix_missing_return(lines, issue):
                    fixes_applied += 1
                    changes.append(f"Added return type at line {issue.line_number}")
        
        if not dry_run and fixes_applied > 0:
            path.write_text('\n'.join(lines))
        
        return fixes_applied, changes

    def _fix_missing_return(self, lines: List[str], issue: TypingIssue) -> bool:
        line_idx = issue.line_number - 1
        if line_idx >= len(lines):
            return False
        
        line = lines[line_idx]
        if '->' not in line and ':' in line:
            if 'def ' in line:
                lines[line_idx] = line.replace('):', ') -> Any:')
                return True
        return False


class TypingVisitor(ast.NodeVisitor):
    def __init__(self, report: TypingReport, guard: TypingGuard):
        self.report = report
        self.guard = guard
        self.current_class = None

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._check_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._check_function(node)
        self.generic_visit(node)

    def _check_function(self, node: ast.FunctionDef):
        if self.guard.ignore_private and node.name.startswith('_') and not node.name.startswith('__'):
            return
        if self.guard.ignore_dunder and node.name.startswith('__') and node.name.endswith('__'):
            return
        if self.guard.ignore_overload:
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Name) and decorator.id == 'overload':
                    return
        
        self.report.total_functions += 1
        
        has_any_param_type = False
        has_all_param_types = True
        
        for arg in node.args.args:
            if arg.arg == 'self' or arg.arg == 'cls':
                continue
            
            self.report.total_parameters += 1
            if arg.annotation:
                self.report.typed_parameters += 1
                has_any_param_type = True
            else:
                has_all_param_types = False
        
        if has_all_param_types and self.report.total_parameters > 0:
            self.report.typed_functions += 1
        
        if node.returns:
            self.report.typed_returns += 1
        else:
            self.report.total_returns += 1
            
            if self.guard.level in (TypeHintLevel.STRICT, TypeHintLevel.FULL):
                self.report.issues.append(TypingIssue(
                    file_path=self.report.file_path,
                    line_number=node.lineno,
                    column=node.col_offset,
                    issue_type="missing_return_type",
                    message=f"Function '{node.name}' missing return type annotation",
                    severity="warning" if self.guard.level == TypeHintLevel.STRICT else "error",
                    suggestion="Add return type annotation (e.g., '-> int')",
                    auto_fixable=True,
                ))
        
        if self.guard.level == TypeHintLevel.FULL:
            if not has_any_param_type and self.report.total_parameters > 0:
                self.report.issues.append(TypingIssue(
                    file_path=self.report.file_path,
                    line_number=node.lineno,
                    column=node.col_offset,
                    issue_type="missing_parameter_types",
                    message=f"Function '{node.name}' missing parameter type annotations",
                    severity="warning",
                    suggestion="Add type annotations to parameters",
                ))

    def visit_ClassDef(self, node: ast.ClassDef):
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class


class TypeAnnotationGenerator:
    def __init__(self):
        self.common_patterns = {
            'list': 'List[Any]',
            'dict': 'Dict[str, Any]',
            'set': 'Set[Any]',
            'tuple': 'Tuple[Any, ...]',
            'str': 'str',
            'int': 'int',
            'float': 'float',
            'bool': 'bool',
            'none': 'None',
        }

    def infer_type_from_default(self, default: ast.AST) -> str:
        if isinstance(default, ast.Constant):
            if isinstance(default.value, str):
                return 'str'
            elif isinstance(default.value, int):
                return 'int'
            elif isinstance(default.value, float):
                return 'float'
            elif isinstance(default.value, bool):
                return 'bool'
            elif default.value is None:
                return 'Optional[Any]'
        elif isinstance(default, ast.List):
            return 'List[Any]'
        elif isinstance(default, ast.Dict):
            return 'Dict[str, Any]'
        elif isinstance(default, ast.Set):
            return 'Set[Any]'
        elif isinstance(default, ast.Tuple):
            return 'Tuple[Any, ...]'
        return 'Any'

    def suggest_return_type(self, node: ast.FunctionDef) -> str:
        for stmt in node.body:
            if isinstance(stmt, ast.Return) and stmt.value:
                return self._infer_from_expression(stmt.value)
        return 'None'

    def _infer_from_expression(self, expr: ast.AST) -> str:
        if isinstance(expr, ast.Constant):
            if isinstance(expr.value, str):
                return 'str'
            elif isinstance(expr.value, int):
                return 'int'
            elif isinstance(expr.value, float):
                return 'float'
            elif isinstance(expr.value, bool):
                return 'bool'
            elif expr.value is None:
                return 'None'
        elif isinstance(expr, ast.List):
            return 'List[Any]'
        elif isinstance(expr, ast.Dict):
            return 'Dict[str, Any]'
        elif isinstance(expr, ast.Set):
            return 'Set[Any]'
        elif isinstance(expr, ast.Call):
            if isinstance(expr.func, ast.Name):
                return expr.func.id
        elif isinstance(expr, ast.BinOp):
            left = self._infer_from_expression(expr.left)
            right = self._infer_from_expression(expr.right)
            if left == right:
                return left
        return 'Any'