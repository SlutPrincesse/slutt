"""
Polyglot AST Generator - Language-agnostic AST representation
"""
import ast
import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class Language(Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    GO = "go"
    RUST = "rust"
    CPP = "cpp"
    CSHARP = "csharp"
    RUBY = "ruby"
    PHP = "php"
    SWIFT = "swift"
    KOTLIN = "kotlin"
    UNKNOWN = "unknown"


class NodeType(Enum):
    MODULE = "module"
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    VARIABLE = "variable"
    CONSTANT = "constant"
    IMPORT = "import"
    EXPORT = "export"
    CALL = "call"
    ASSIGNMENT = "assignment"
    BINARY_OP = "binary_op"
    UNARY_OP = "unary_op"
    IF = "if"
    FOR = "for"
    WHILE = "while"
    RETURN = "return"
    EXPRESSION = "expression"
    LITERAL = "literal"
    IDENTIFIER = "identifier"
    ATTRIBUTE = "attribute"
    SUBSCRIPT = "subscript"
    LAMBDA = "lambda"
    DECORATOR = "decorator"
    ANNOTATION = "annotation"
    TYPE = "type"
    COMMENT = "comment"
    DOCSTRING = "docstring"
    TRY = "try"
    EXCEPT = "except"
    FINALLY = "finally"
    WITH = "with"
    MATCH = "match"
    CASE = "case"
    ASYNC = "async"
    AWAIT = "await"
    YIELD = "yield"
    GENERATOR = "generator"
    COMPREHENSION = "comprehension"
    UNKNOWN = "unknown"


@dataclass
class SourceLocation:
    file_path: str
    line: int
    column: int
    end_line: int | None = None
    end_column: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "line": self.line,
            "column": self.column,
            "end_line": self.end_line,
            "end_column": self.end_column,
        }


@dataclass
class PolyglotNode:
    node_id: str
    node_type: NodeType
    language: Language
    name: str | None = None
    value: Any | None = None
    location: SourceLocation | None = None
    children: list['PolyglotNode'] = field(default_factory=list)
    parent: Optional['PolyglotNode'] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    annotations: list[str] = field(default_factory=list)
    type_annotation: str | None = None
    docstring: str | None = None

    def add_child(self, child: 'PolyglotNode'):
        child.parent = self
        self.children.append(child)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "language": self.language.value,
            "name": self.name,
            "value": self.value,
            "location": self.location.to_dict() if self.location else None,
            "children": [c.to_dict() for c in self.children],
            "metadata": self.metadata,
            "annotations": self.annotations,
            "type_annotation": self.type_annotation,
            "docstring": self.docstring,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'PolyglotNode':
        node = cls(
            node_id=data["node_id"],
            node_type=NodeType(data["node_type"]),
            language=Language(data["language"]),
            name=data.get("name"),
            value=data.get("value"),
            location=SourceLocation(**data["location"]) if data.get("location") else None,
            metadata=data.get("metadata", {}),
            annotations=data.get("annotations", []),
            type_annotation=data.get("type_annotation"),
            docstring=data.get("docstring"),
        )
        for child_data in data.get("children", []):
            child = cls.from_dict(child_data)
            node.add_child(child)
        return node


class PolyglotASTGenerator:
    def __init__(self):
        self.parsers: dict[Language, Callable] = {}
        self._register_default_parsers()

    def _register_default_parsers(self):
        self.parsers[Language.PYTHON] = self._parse_python

    def register_parser(self, language: Language, parser: Callable):
        self.parsers[language] = parser

    def parse(self, code: str, language: Language, file_path: str = "<string>") -> PolyglotNode:
        if language not in self.parsers:
            raise ValueError(f"No parser for language: {language}")
        return self.parsers[language](code, file_path)

    def parse_file(self, file_path: str, language: Language | None = None) -> PolyglotNode:
        if language is None:
            language = self._detect_language(file_path)
        with Path(file_path).open(encoding='utf-8', errors='ignore') as f:
            code = f.read()
        return self.parse(code, language, file_path)

    def _detect_language(self, file_path: str) -> Language:
        ext = Path(file_path).suffix.lower()
        mapping = {
            '.py': Language.PYTHON,
            '.js': Language.JAVASCRIPT,
            '.ts': Language.TYPESCRIPT,
            '.jsx': Language.JAVASCRIPT,
            '.tsx': Language.TYPESCRIPT,
            '.java': Language.JAVA,
            '.go': Language.GO,
            '.rs': Language.RUST,
            '.cpp': Language.CPP,
            '.cc': Language.CPP,
            '.cxx': Language.CPP,
            '.cs': Language.CSHARP,
            '.rb': Language.RUBY,
            '.php': Language.PHP,
            '.swift': Language.SWIFT,
            '.kt': Language.KOTLIN,
        }
        return mapping.get(ext, Language.UNKNOWN)

    def _parse_python(self, code: str, file_path: str) -> PolyglotNode:
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return self._create_error_node(str(e), file_path, Language.PYTHON)

        root = PolyglotNode(
            node_id=self._gen_id("module"),
            node_type=NodeType.MODULE,
            language=Language.PYTHON,
            name=file_path,
            location=SourceLocation(file_path, 1, 0),
        )

        self._convert_python_ast(tree, root, code, file_path)
        return root

    def _convert_python_ast(self, node: ast.AST, parent: PolyglotNode, code: str, file_path: str):
        polyglot_node = self._create_polyglot_node(node, file_path)
        parent.add_child(polyglot_node)

        for field_name, value in ast.iter_fields(node):
            if isinstance(value, ast.AST):
                self._convert_python_ast(value, polyglot_node, code, file_path)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, ast.AST):
                        self._convert_python_ast(item, polyglot_node, code, file_path)

    def _create_polyglot_node(self, node: ast.AST, file_path: str) -> PolyglotNode:
        node_type = self._map_python_node_type(type(node).__name__)
        location = SourceLocation(
            file_path=file_path,
            line=getattr(node, 'lineno', 1),
            column=getattr(node, 'col_offset', 0),
            end_line=getattr(node, 'end_lineno', None),
            end_column=getattr(node, 'end_col_offset', None),
        )

        name = None
        value = None
        annotations = []
        type_annotation = None
        docstring = None

        if isinstance(node, ast.FunctionDef):
            name = node.name
            if node.returns:
                type_annotation = ast.unparse(node.returns) if hasattr(ast, 'unparse') else str(node.returns)
            for dec in node.decorator_list:
                annotations.append(ast.unparse(dec) if hasattr(ast, 'unparse') else str(dec))
            docstring = ast.get_docstring(node)

        elif isinstance(node, ast.ClassDef):
            name = node.name
            for dec in node.decorator_list:
                annotations.append(ast.unparse(dec) if hasattr(ast, 'unparse') else str(dec))
            docstring = ast.get_docstring(node)

        elif isinstance(node, ast.Name):
            name = node.id

        elif isinstance(node, ast.Constant):
            value = node.value

        elif isinstance(node, ast.Import):
            for alias in node.names:
                child = PolyglotNode(
                    node_id=self._gen_id("import"),
                    node_type=NodeType.IMPORT,
                    language=Language.PYTHON,
                    name=alias.name,
                    value=alias.asname,
                    location=location,
                )
                polyglot_node.add_child(child)

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                child = PolyglotNode(
                    node_id=self._gen_id("import"),
                    node_type=NodeType.IMPORT,
                    language=Language.PYTHON,
                    name=f"{module}.{alias.name}",
                    value=alias.asname,
                    location=location,
                )
                polyglot_node.add_child(child)

        return PolyglotNode(
            node_id=self._gen_id(node_type.value),
            node_type=node_type,
            language=Language.PYTHON,
            name=name,
            value=value,
            location=location,
            annotations=annotations,
            type_annotation=type_annotation,
            docstring=docstring,
        )

    def _map_python_node_type(self, py_type: str) -> NodeType:
        mapping = {
            'Module': NodeType.MODULE,
            'FunctionDef': NodeType.FUNCTION,
            'AsyncFunctionDef': NodeType.FUNCTION,
            'ClassDef': NodeType.CLASS,
            'Return': NodeType.RETURN,
            'If': NodeType.IF,
            'For': NodeType.FOR,
            'While': NodeType.WHILE,
            'Call': NodeType.CALL,
            'Assign': NodeType.ASSIGNMENT,
            'BinOp': NodeType.BINARY_OP,
            'UnaryOp': NodeType.UNARY_OP,
            'Name': NodeType.IDENTIFIER,
            'Constant': NodeType.LITERAL,
            'Attribute': NodeType.ATTRIBUTE,
            'Subscript': NodeType.SUBSCRIPT,
            'Lambda': NodeType.LAMBDA,
            'Try': NodeType.TRY,
            'ExceptHandler': NodeType.EXCEPT,
            'With': NodeType.WITH,
            'Match': NodeType.MATCH,
            'MatchCase': NodeType.CASE,
            'Yield': NodeType.YIELD,
            'YieldFrom': NodeType.YIELD,
            'GeneratorExp': NodeType.GENERATOR,
            'ListComp': NodeType.COMPREHENSION,
            'SetComp': NodeType.COMPREHENSION,
            'DictComp': NodeType.COMPREHENSION,
            'Expr': NodeType.EXPRESSION,
        }
        return mapping.get(py_type, NodeType.UNKNOWN)

    def _create_error_node(self, error: str, file_path: str, language: Language) -> PolyglotNode:
        return PolyglotNode(
            node_id=self._gen_id("error"),
            node_type=NodeType.UNKNOWN,
            language=language,
            name="parse_error",
            value=error,
            location=SourceLocation(file_path, 1, 0),
        )

    def _gen_id(self, prefix: str) -> str:
        return f"{prefix}_{hashlib.md5(f'{prefix}{time.time()}'.encode()).hexdigest()[:8]}"


import time


class ASTDiffer:
    def __init__(self, generator: PolyglotASTGenerator):
        self.generator = generator

    def diff(self, old_code: str, new_code: str, language: Language, file_path: str = "<string>") -> dict[str, Any]:
        old_ast = self.generator.parse(old_code, language, file_path)
        new_ast = self.generator.parse(new_code, language, file_path)
        return self._diff_nodes(old_ast, new_ast)

    def _diff_nodes(self, old: PolyglotNode, new: PolyglotNode) -> dict[str, Any]:
        changes = {
            "added": [],
            "removed": [],
            "modified": [],
            "moved": [],
        }

        old_children = {c.node_id: c for c in old.children}
        new_children = {c.node_id: c for c in new.children}

        for node_id, child in new_children.items():
            if node_id not in old_children:
                changes["added"].append(child.to_dict())
            else:
                diff = self._diff_nodes(old_children[node_id], child)
                if any(diff.values()):
                    changes["modified"].append({
                        "node_id": node_id,
                        "changes": diff,
                    })

        for node_id, child in old_children.items():
            if node_id not in new_children:
                changes["removed"].append(child.to_dict())

        return changes
