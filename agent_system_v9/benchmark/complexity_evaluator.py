"""
Complexity Evaluator - Code complexity analysis and metrics
"""
import ast
import hashlib
from typing import Dict, List, Optional, Any, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from collections import defaultdict


class ComplexityMetric(Enum):
    CYCLOMATIC = "cyclomatic"
    COGNITIVE = "cognitive"
    HALSTEAD = "halstead"
    MAINTAINABILITY = "maintainability"
    LINES_OF_CODE = "lines_of_code"
    NESTING_DEPTH = "nesting_depth"
    PARAMETER_COUNT = "parameter_count"


@dataclass
class ComplexityResult:
    function_name: str
    file_path: str
    line_number: int
    metrics: Dict[ComplexityMetric, float] = field(default_factory=dict)
    overall_score: float = 0.0
    grade: str = "A"
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "function_name": self.function_name,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "metrics": {k.value: v for k, v in self.metrics.items()},
            "overall_score": self.overall_score,
            "grade": self.grade,
            "recommendations": self.recommendations,
        }


@dataclass
class FileComplexity:
    file_path: str
    total_lines: int
    code_lines: int
    comment_lines: int
    blank_lines: int
    functions: List[ComplexityResult] = field(default_factory=list)
    classes: List[ComplexityResult] = field(default_factory=list)
    overall_metrics: Dict[ComplexityMetric, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_lines": self.total_lines,
            "code_lines": self.code_lines,
            "comment_lines": self.comment_lines,
            "blank_lines": self.blank_lines,
            "functions": [f.to_dict() for f in self.functions],
            "classes": [c.to_dict() for c in self.classes],
            "overall_metrics": {k.value: v for k, v in self.overall_metrics.items()},
        }


class CyclomaticComplexityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.complexity = 1
        self.current_function = None
        self.results: Dict[str, int] = {}

    def visit_FunctionDef(self, node: ast.FunctionDef):
        old_complexity = self.complexity
        old_function = self.current_function
        self.complexity = 1
        self.current_function = node.name
        self.generic_visit(node)
        self.results[node.name] = self.complexity
        self.complexity = old_complexity
        self.current_function = old_function

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.visit_FunctionDef(node)

    def visit_If(self, node: ast.If):
        self.complexity += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For):
        self.complexity += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While):
        self.complexity += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        self.complexity += 1
        self.generic_visit(node)

    def visit_With(self, node: ast.With):
        self.complexity += 1
        self.generic_visit(node)

    def visit_Comprehension(self, node: ast.comprehension):
        self.complexity += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp):
        self.complexity += len(node.values) - 1
        self.generic_visit(node)


class CognitiveComplexityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.complexity = 0
        self.nesting = 0
        self.current_function = None
        self.results: Dict[str, int] = {}

    def visit_FunctionDef(self, node: ast.FunctionDef):
        old_complexity = self.complexity
        old_nesting = self.nesting
        old_function = self.current_function
        self.complexity = 0
        self.nesting = 0
        self.current_function = node.name
        self.generic_visit(node)
        self.results[node.name] = self.complexity
        self.complexity = old_complexity
        self.nesting = old_nesting
        self.current_function = old_function

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.visit_FunctionDef(node)

    def visit_If(self, node: ast.If):
        self.complexity += 1 + self.nesting
        old_nesting = self.nesting
        self.nesting += 1
        self.generic_visit(node)
        self.nesting = old_nesting

    def visit_For(self, node: ast.For):
        self.complexity += 1 + self.nesting
        old_nesting = self.nesting
        self.nesting += 1
        self.generic_visit(node)
        self.nesting = old_nesting

    def visit_While(self, node: ast.While):
        self.complexity += 1 + self.nesting
        old_nesting = self.nesting
        self.nesting += 1
        self.generic_visit(node)
        self.nesting = old_nesting

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        self.complexity += 1 + self.nesting
        old_nesting = self.nesting
        self.nesting += 1
        self.generic_visit(node)
        self.nesting = old_nesting

    def visit_With(self, node: ast.With):
        self.complexity += 1 + self.nesting
        old_nesting = self.nesting
        self.nesting += 1
        self.generic_visit(node)
        self.nesting = old_nesting


class HalsteadMetrics:
    def __init__(self):
        self.operators: Dict[str, int] = defaultdict(int)
        self.operands: Dict[str, int] = defaultdict(int)

    def visit(self, node: ast.AST):
        if isinstance(node, ast.BinOp):
            self.operators[type(node.op).__name__] += 1
            self.visit(node.left)
            self.visit(node.right)
        elif isinstance(node, ast.UnaryOp):
            self.operators[type(node.op).__name__] += 1
            self.visit(node.operand)
        elif isinstance(node, ast.Compare):
            for op in node.ops:
                self.operators[type(op).__name__] += 1
            self.visit(node.left)
            for comparator in node.comparators:
                self.visit(comparator)
        elif isinstance(node, ast.BoolOp):
            self.operators[type(node.op).__name__] += len(node.values) - 1
            for value in node.values:
                self.visit(value)
        elif isinstance(node, ast.Call):
            self.operators["Call"] += 1
            self.visit(node.func)
            for arg in node.args:
                self.visit(arg)
        elif isinstance(node, ast.Name):
            self.operands[node.id] += 1
        elif isinstance(node, ast.Constant):
            self.operands[str(node.value)] += 1
        elif isinstance(node, ast.Attribute):
            self.operands[node.attr] += 1
        
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, (ast.BinOp, ast.UnaryOp, ast.Compare, ast.BoolOp, ast.Call, ast.Name, ast.Constant, ast.Attribute)):
                self.visit(child)

    def calculate(self) -> Dict[str, float]:
        n1 = len(self.operators)
        n2 = len(self.operands)
        N1 = sum(self.operators.values())
        N2 = sum(self.operands.values())
        
        vocabulary = n1 + n2
        length = N1 + N2
        volume = length * (vocabulary.bit_length() if vocabulary > 0 else 0)
        difficulty = (n1 / 2) * (N2 / n2) if n2 > 0 else 0
        effort = difficulty * volume
        time = effort / 18
        bugs = volume / 3000
        
        return {
            "vocabulary": vocabulary,
            "length": length,
            "volume": volume,
            "difficulty": difficulty,
            "effort": effort,
            "time": time,
            "bugs": bugs,
        }


class NestingDepthVisitor(ast.NodeVisitor):
    def __init__(self):
        self.max_depth = 0
        self.current_depth = 0
        self.current_function = None
        self.results: Dict[str, int] = {}

    def visit_FunctionDef(self, node: ast.FunctionDef):
        old_max = self.max_depth
        old_current = self.current_depth
        old_function = self.current_function
        self.max_depth = 0
        self.current_depth = 0
        self.current_function = node.name
        self.generic_visit(node)
        self.results[node.name] = self.max_depth
        self.max_depth = old_max
        self.current_depth = old_current
        self.current_function = old_function

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.visit_FunctionDef(node)

    def visit_If(self, node: ast.If):
        self.current_depth += 1
        self.max_depth = max(self.max_depth, self.current_depth)
        self.generic_visit(node)
        self.current_depth -= 1

    def visit_For(self, node: ast.For):
        self.current_depth += 1
        self.max_depth = max(self.max_depth, self.current_depth)
        self.generic_visit(node)
        self.current_depth -= 1

    def visit_While(self, node: ast.While):
        self.current_depth += 1
        self.max_depth = max(self.max_depth, self.current_depth)
        self.generic_visit(node)
        self.current_depth -= 1

    def visit_With(self, node: ast.With):
        self.current_depth += 1
        self.max_depth = max(self.max_depth, self.current_depth)
        self.generic_visit(node)
        self.current_depth -= 1

    def visit_Try(self, node: ast.Try):
        self.current_depth += 1
        self.max_depth = max(self.max_depth, self.current_depth)
        self.generic_visit(node)
        self.current_depth -= 1


class ComplexityEvaluator:
    def __init__(self):
        self.thresholds = {
            ComplexityMetric.CYCLOMATIC: {10: "B", 20: "C", 30: "D", 50: "F"},
            ComplexityMetric.COGNITIVE: {15: "B", 30: "C", 50: "D", 75: "F"},
            ComplexityMetric.NESTING_DEPTH: {4: "B", 6: "C", 8: "D", 10: "F"},
            ComplexityMetric.PARAMETER_COUNT: {5: "B", 7: "C", 10: "D", 15: "F"},
        }

    def evaluate_file(self, file_path: str) -> FileComplexity:
        source = Path(file_path).read_text(encoding='utf-8', errors='ignore')
        tree = ast.parse(source)
        
        lines = source.split('\n')
        total_lines = len(lines)
        code_lines = sum(1 for l in lines if l.strip() and not l.strip().startswith('#'))
        comment_lines = sum(1 for l in lines if l.strip().startswith('#'))
        blank_lines = total_lines - code_lines - comment_lines
        
        cyclomatic_visitor = CyclomaticComplexityVisitor()
        cyclomatic_visitor.visit(tree)
        
        cognitive_visitor = CognitiveComplexityVisitor()
        cognitive_visitor.visit(tree)
        
        nesting_visitor = NestingDepthVisitor()
        nesting_visitor.visit(tree)
        
        halstead = HalsteadMetrics()
        halstead.visit(tree)
        halstead_metrics = halstead.calculate()
        
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                result = self._evaluate_function(node, file_path, cyclomatic_visitor.results, 
                                                cognitive_visitor.results, nesting_visitor.results,
                                                halstead_metrics)
                functions.append(result)
        
        classes = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                result = self._evaluate_class(node, file_path)
                classes.append(result)
        
        overall = self._calculate_overall(functions)
        
        return FileComplexity(
            file_path=file_path,
            total_lines=total_lines,
            code_lines=code_lines,
            comment_lines=comment_lines,
            blank_lines=blank_lines,
            functions=functions,
            classes=classes,
            overall_metrics=overall,
        )

    def _evaluate_function(
        self,
        node: ast.FunctionDef,
        file_path: str,
        cyclomatic_results: Dict,
        cognitive_results: Dict,
        nesting_results: Dict,
        halstead_metrics: Dict,
    ) -> ComplexityResult:
        metrics = {}
        
        metrics[ComplexityMetric.CYCLOMATIC] = cyclomatic_results.get(node.name, 1)
        metrics[ComplexityMetric.COGNITIVE] = cognitive_results.get(node.name, 0)
        metrics[ComplexityMetric.NESTING_DEPTH] = nesting_results.get(node.name, 0)
        metrics[ComplexityMetric.PARAMETER_COUNT] = len(node.args.args)
        metrics[ComplexityMetric.LINES_OF_CODE] = getattr(node, 'end_lineno', node.lineno) - node.lineno + 1
        
        overall_score = self._calculate_score(metrics)
        grade = self._calculate_grade(overall_score)
        recommendations = self._generate_recommendations(metrics)
        
        return ComplexityResult(
            function_name=node.name,
            file_path=file_path,
            line_number=node.lineno,
            metrics=metrics,
            overall_score=overall_score,
            grade=grade,
            recommendations=recommendations,
        )

    def _evaluate_class(self, node: ast.ClassDef, file_path: str) -> ComplexityResult:
        method_count = sum(1 for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
        
        metrics = {
            ComplexityMetric.PARAMETER_COUNT: len(node.bases),
            ComplexityMetric.LINES_OF_CODE: getattr(node, 'end_lineno', node.lineno) - node.lineno + 1,
        }
        
        overall_score = self._calculate_score(metrics)
        grade = self._calculate_grade(overall_score)
        
        return ComplexityResult(
            function_name=node.name,
            file_path=file_path,
            line_number=node.lineno,
            metrics=metrics,
            overall_score=overall_score,
            grade=grade,
            recommendations=[f"Class has {method_count} methods"] if method_count > 20 else [],
        )

    def _calculate_score(self, metrics: Dict[ComplexityMetric, float]) -> float:
        weights = {
            ComplexityMetric.CYCLOMATIC: 0.3,
            ComplexityMetric.COGNITIVE: 0.3,
            ComplexityMetric.NESTING_DEPTH: 0.2,
            ComplexityMetric.PARAMETER_COUNT: 0.1,
            ComplexityMetric.LINES_OF_CODE: 0.1,
        }
        
        score = 0
        for metric, weight in weights.items():
            value = metrics.get(metric, 0)
            thresholds = self.thresholds.get(metric, {})
            for threshold, grade in sorted(thresholds.items()):
                if value <= threshold:
                    grade_score = {"A": 100, "B": 80, "C": 60, "D": 40, "F": 20}[grade]
                    score += grade_score * weight
                    break
            else:
                score += 20 * weight
        
        return score

    def _calculate_grade(self, score: float) -> str:
        if score >= 90: return "A"
        if score >= 80: return "B"
        if score >= 70: return "C"
        if score >= 60: return "D"
        return "F"

    def _generate_recommendations(self, metrics: Dict[ComplexityMetric, float]) -> List[str]:
        recs = []
        if metrics.get(ComplexityMetric.CYCLOMATIC, 0) > 10:
            recs.append("Consider breaking down complex function")
        if metrics.get(ComplexityMetric.COGNITIVE, 0) > 15:
            recs.append("Reduce cognitive complexity - simplify control flow")
        if metrics.get(ComplexityMetric.NESTING_DEPTH, 0) > 4:
            recs.append("Reduce nesting depth - use early returns or extract methods")
        if metrics.get(ComplexityMetric.PARAMETER_COUNT, 0) > 5:
            recs.append("Reduce parameter count - use parameter object or builder pattern")
        if metrics.get(ComplexityMetric.LINES_OF_CODE, 0) > 50:
            recs.append("Function too long - extract smaller functions")
        return recs

    def _calculate_overall(self, functions: List[ComplexityResult]) -> Dict[ComplexityMetric, float]:
        if not functions:
            return {}
        
        overall = {}
        for metric in ComplexityMetric:
            values = [f.metrics.get(metric, 0) for f in functions]
            if values:
                overall[metric] = sum(values) / len(values)
        return overall

    def evaluate_project(self, root_path: str, extensions: List[str] = None) -> List[FileComplexity]:
        if extensions is None:
            extensions = ['.py']
        
        results = []
        for ext in extensions:
            for file_path in Path(root_path).rglob(f'*{ext}'):
                try:
                    results.append(self.evaluate_file(str(file_path)))
                except Exception:
                    pass
        
        return results


class ComplexityReporter:
    def __init__(self, evaluator: ComplexityEvaluator):
        self.evaluator = evaluator

    def generate_report(self, results: List[FileComplexity], format: str = "text") -> str:
        if format == "json":
            return self._json_report(results)
        return self._text_report(results)

    def _text_report(self, results: List[FileComplexity]) -> str:
        lines = ["# Complexity Analysis Report", ""]
        
        for file_result in results:
            lines.append(f"## {file_result.file_path}")
            lines.append(f"- Total Lines: {file_result.total_lines}")
            lines.append(f"- Code Lines: {file_result.code_lines}")
            lines.append(f"- Functions: {len(file_result.functions)}")
            lines.append(f"- Classes: {len(file_result.classes)}")
            lines.append("")
            
            for func in file_result.functions:
                lines.append(f"### {func.function_name} (Grade: {func.grade})")
                for metric, value in func.metrics.items():
                    lines.append(f"- {metric.value}: {value}")
                if func.recommendations:
                    lines.append("- Recommendations:")
                    for rec in func.recommendations:
                        lines.append(f"  - {rec}")
                lines.append("")
        
        return "\n".join(lines)

    def _json_report(self, results: List[FileComplexity]) -> str:
        import json
        return json.dumps([r.to_dict() for r in results], indent=2)