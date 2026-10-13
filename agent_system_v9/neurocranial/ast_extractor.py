"""
AST Functional Node Extractor - Parses discovered codebases to extract functional nodes via AST
"""
import ast
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class NodeType(Enum):
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    ASYNC_FUNCTION = "async_function"
    GENERATOR = "generator"
    DECORATOR = "decorator"
    LAMBDA = "lambda"
    COMPREHENSION = "comprehension"
    IMPORT = "import"
    ASSIGNMENT = "assignment"


@dataclass
class FunctionalNode:
    node_id: str
    node_type: NodeType
    name: str
    qualified_name: str
    file_path: str
    line_start: int
    line_end: int
    source_code: str
    docstring: str = ""
    parameters: list[dict[str, Any]] = field(default_factory=list)
    returns: str | None = None
    decorators: list[str] = field(default_factory=list)
    complexity: int = 1
    calls: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ASTFunctionalExtractor:
    def __init__(self):
        self._lock = threading.RLock()
        self._extractors: dict[str, Callable] = {}
        self._register_default_extractors()

    def _register_default_extractors(self):
        self._extractors[".py"] = self._extract_python

    def extract_from_file(self, file_path: str) -> list[FunctionalNode]:
        path = Path(file_path)
        if not path.exists():
            return []

        ext = path.suffix
        extractor = self._extractors.get(ext)
        if not extractor:
            return []

        try:
            with Path(file_path).open(encoding='utf-8') as f:
                source = f.read()
            return extractor(source, file_path)
        except Exception:
            return []

    def extract_from_directory(self, dir_path: str, pattern: str = "*.py",
                               max_files: int = 1000) -> list[FunctionalNode]:
        nodes = []
        path = Path(dir_path)

        for file_path in path.rglob(pattern):
            if not file_path.is_file():
                continue
            if len(nodes) >= max_files:
                break
            nodes.extend(self.extract_from_file(str(file_path)))

        return nodes

    def _extract_python(self, source: str, file_path: str) -> list[FunctionalNode]:
        nodes = []

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return nodes

        visitor = FunctionalNodeVisitor(file_path, source)
        visitor.visit(tree)
        nodes.extend(visitor.nodes)

        return nodes

    def register_extractor(self, extension: str, extractor: Callable[[str, str], list[FunctionalNode]]):
        self._extractors[extension] = extractor

    def find_nodes_by_type(self, nodes: list[FunctionalNode],
                          node_type: NodeType) -> list[FunctionalNode]:
        return [n for n in nodes if n.node_type == node_type]

    def find_nodes_by_name(self, nodes: list[FunctionalNode],
                          name_pattern: str) -> list[FunctionalNode]:
        import fnmatch
        return [n for n in nodes if fnmatch.fnmatch(n.name, name_pattern)]

    def find_nodes_by_complexity(self, nodes: list[FunctionalNode],
                                min_complexity: int = 1,
                                max_complexity: int = None) -> list[FunctionalNode]:
        filtered = [n for n in nodes if n.complexity >= min_complexity]
        if max_complexity:
            filtered = [n for n in filtered if n.complexity <= max_complexity]
        return filtered

    def get_call_graph(self, nodes: list[FunctionalNode]) -> dict[str, list[str]]:
        graph = {}
        node_map = {n.qualified_name: n for n in nodes}

        for node in nodes:
            graph[node.qualified_name] = []
            for call in node.calls:
                if call in node_map:
                    graph[node.qualified_name].append(call)

        return graph


class FunctionalNodeVisitor(ast.NodeVisitor):
    def __init__(self, file_path: str, source: str):
        self.file_path = file_path
        self.source = source
        self.nodes: list[FunctionalNode] = []
        self._current_class = None
        self._source_lines = source.split('\n')

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._process_function(node, NodeType.FUNCTION)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._process_function(node, NodeType.ASYNC_FUNCTION)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        old_class = self._current_class
        self._current_class = node.name

        # Process methods
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._process_function(item, NodeType.METHOD)

        self._current_class = old_class
        self.generic_visit(node)

    def visit_Lambda(self, node: ast.Lambda):
        self._process_lambda(node)
        self.generic_visit(node)

    def _process_function(self, node: ast.FunctionDef, node_type: NodeType):
        qualified_name = f"{self._current_class}.{node.name}" if self._current_class else node.name

        # Get source code
        source_lines = self._source_lines[node.lineno - 1:node.end_lineno]
        source_code = '\n'.join(source_lines)

        # Get docstring
        docstring = ast.get_docstring(node) or ""

        # Get parameters
        parameters = []
        for arg in node.args.args:
            param_info = {
                "name": arg.arg,
                "annotation": ast.unparse(arg.annotation) if arg.annotation else None
            }
            parameters.append(param_info)

        # Get return annotation
        returns = ast.unparse(node.returns) if node.returns else None

        # Get decorators
        decorators = []
        for dec in node.decorator_list:
            try:
                decorators.append(ast.unparse(dec))
            except Exception:
                decorators.append(str(dec))

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        # Get calls
        calls = self._extract_calls(node)

        fn = FunctionalNode(
            node_id=f"{self.file_path}:{node.lineno}",
            node_type=node_type,
            name=node.name,
            qualified_name=qualified_name,
            file_path=self.file_path,
            line_start=node.lineno,
            line_end=node.end_lineno,
            source_code=source_code,
            docstring=docstring,
            parameters=parameters,
            returns=returns,
            decorators=decorators,
            complexity=complexity,
            calls=calls,
            metadata={
                "is_async": node_type == NodeType.ASYNC_FUNCTION,
                "is_method": self._current_class is not None,
                "class_name": self._current_class
            }
        )

        self.nodes.append(fn)

    def _process_lambda(self, node: ast.Lambda):
        qualified_name = f"<lambda>@{self.file_path}:{node.lineno}"

        source_line = self._source_lines[node.lineno - 1] if node.lineno <= len(self._source_lines) else ""

        fn = FunctionalNode(
            node_id=f"{self.file_path}:{node.lineno}",
            node_type=NodeType.LAMBDA,
            name="lambda",
            qualified_name=qualified_name,
            file_path=self.file_path,
            line_start=node.lineno,
            line_end=node.lineno,
            source_code=source_line.strip(),
            parameters=[{"name": arg.arg} for arg in node.args.args],
            complexity=1,
            metadata={"is_lambda": True}
        )

        self.nodes.append(fn)

    def _calculate_complexity(self, node: ast.FunctionDef) -> int:
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)) or isinstance(child, ast.ExceptHandler) or isinstance(child, (ast.And, ast.Or)) or isinstance(child, ast.Comprehension):
                complexity += 1
        return complexity

    def _extract_calls(self, node: ast.FunctionDef) -> list[str]:
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.append(child.func.attr)
        return list(set(calls))


_ast_extractor: ASTFunctionalExtractor | None = None


def get_ast_extractor() -> ASTFunctionalExtractor:
    global _ast_extractor
    if _ast_extractor is None:
        _ast_extractor = ASTFunctionalExtractor()
    return _ast_extractor
