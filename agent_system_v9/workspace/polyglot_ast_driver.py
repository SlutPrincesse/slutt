"""
Polyglot AST Driver - Multi-language AST operations for workspace
"""
import ast
import hashlib
import importlib.util
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

try:
    from tree_sitter import Language as TSLanguage
    from tree_sitter import Parser as TSParser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    TSLanguage = None
    TSParser = None


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


@dataclass
class TreeSitterConfig:
    language: Language
    lib_path: str
    language_name: str
    queries: dict[str, str] = field(default_factory=dict)


class TreeSitterManager:
    _instance = None
    _languages: dict[Language, TSLanguage] = {}
    _parsers: dict[Language, TSParser] = {}

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        if not TREE_SITTER_AVAILABLE:
            return
        self._load_languages()

    def _load_languages(self):
        language_configs = {
            Language.PYTHON: ("tree_sitter_python", "python"),
            Language.JAVASCRIPT: ("tree_sitter_javascript", "javascript"),
            Language.TYPESCRIPT: ("tree_sitter_typescript", "typescript"),
            Language.RUST: ("tree_sitter_rust", "rust"),
            Language.GO: ("tree_sitter_go", "go"),
            Language.JAVA: ("tree_sitter_java", "java"),
            Language.CPP: ("tree_sitter_cpp", "cpp"),
        }

        for lang, (module_name, lang_name) in language_configs.items():
            try:
                module = importlib.import_module(module_name)
                ts_lang = TSLanguage(module.language())
                self._languages[lang] = ts_lang
                parser = TSParser()
                parser.set_language(ts_lang)
                self._parsers[lang] = parser
            except ImportError:
                pass

    def get_parser(self, language: Language) -> TSParser | None:
        return self._parsers.get(language)

    def get_language(self, language: Language) -> TSLanguage | None:
        return self._languages.get(language)

    def is_available(self, language: Language) -> bool:
        return language in self._parsers

    @classmethod
    def available_languages(cls) -> list[Language]:
        return list(cls._parsers.keys())


@dataclass
class ASTNode:
    node_id: str
    node_type: str
    language: Language
    name: str | None = None
    value: Any | None = None
    file_path: str = ""
    line: int = 0
    column: int = 0
    end_line: int | None = None
    end_column: int | None = None
    children: list['ASTNode'] = field(default_factory=list)
    parent: Optional['ASTNode'] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_child(self, child: 'ASTNode'):
        child.parent = self
        self.children.append(child)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "language": self.language.value,
            "name": self.name,
            "value": self.value,
            "file_path": self.file_path,
            "line": self.line,
            "column": self.column,
            "end_line": self.end_line,
            "end_column": self.end_column,
            "children": [c.to_dict() for c in self.children],
            "metadata": self.metadata,
        }


@dataclass
class ParseResult:
    file_path: str
    language: Language
    ast: ASTNode | None = None
    errors: list[str] = field(default_factory=list)
    parse_time: float = 0.0


class ASTParser:
    def __init__(self):
        self.parsers: dict[Language, Callable] = {}
        self._register_default_parsers()

    def _register_default_parsers(self):
        self.parsers[Language.PYTHON] = self._parse_python

        if TREE_SITTER_AVAILABLE:
            ts_manager = TreeSitterManager.get_instance()
            for lang in [Language.JAVASCRIPT, Language.TYPESCRIPT, Language.RUST, Language.GO, Language.JAVA, Language.CPP]:
                if ts_manager.is_available(lang):
                    self.parsers[lang] = lambda content, path, l=lang: self._parse_with_tree_sitter(content, path, l)

    def register_parser(self, language: Language, parser: Callable):
        self.parsers[language] = parser

    def parse_file(self, file_path: str, language: Language = None) -> ParseResult:
        if language is None:
            language = self._detect_language(file_path)

        start = time.time()

        try:
            content = Path(file_path).read_text(encoding='utf-8', errors='ignore')
        except Exception as e:
            return ParseResult(file_path, language, errors=[f"Read error: {e}"], parse_time=time.time() - start)

        return self.parse_string(content, file_path, language)

    def parse_string(self, content: str, file_path: str, language: Language) -> ParseResult:
        start = time.time()

        if language not in self.parsers:
            return ParseResult(file_path, language, errors=[f"No parser for {language}"], parse_time=time.time() - start)

        try:
            ast_node = self.parsers[language](content, file_path)
            return ParseResult(file_path, language, ast=ast_node, parse_time=time.time() - start)
        except Exception as e:
            return ParseResult(file_path, language, errors=[f"Parse error: {e}"], parse_time=time.time() - start)

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
        return mapping.get(ext, Language.PYTHON)

    def _parse_python(self, content: str, file_path: str) -> ASTNode:
        if TREE_SITTER_AVAILABLE:
            ts_manager = TreeSitterManager.get_instance()
            if ts_manager.is_available(Language.PYTHON):
                return self._parse_with_tree_sitter(content, file_path, Language.PYTHON)

        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            return ASTNode(
                node_id=hashlib.md5(f"error:{file_path}".encode()).hexdigest()[:12],
                node_type="ERROR",
                language=Language.PYTHON,
                name="parse_error",
                value=str(e),
                file_path=file_path,
            )

        root = ASTNode(
            node_id=hashlib.md5(f"module:{file_path}".encode()).hexdigest()[:12],
            node_type="MODULE",
            language=Language.PYTHON,
            name=Path(file_path).name,
            file_path=file_path,
            line=1,
            column=0,
        )

        self._convert_python_ast(tree, root, content, file_path)
        return root

    def _parse_with_tree_sitter(self, content: str, file_path: str, language: Language) -> ASTNode:
        ts_manager = TreeSitterManager.get_instance()
        parser = ts_manager.get_parser(language)
        if not parser:
            return self._parse_python(content, file_path)

        tree = parser.parse(bytes(content, 'utf8'))
        root_node = tree.root_node

        root = ASTNode(
            node_id=hashlib.md5(f"module:{file_path}".encode()).hexdigest()[:12],
            node_type="MODULE",
            language=language,
            name=Path(file_path).name,
            file_path=file_path,
            line=1,
            column=0,
        )

        self._convert_tree_sitter_ast(root_node, root, content, file_path, language)
        return root

    def _convert_tree_sitter_ast(self, ts_node, parent: ASTNode, content: str, file_path: str, language: Language):
        node_type = ts_node.type
        start_line = ts_node.start_point[0] + 1
        start_col = ts_node.start_point[1]
        end_line = ts_node.end_point[0] + 1
        end_col = ts_node.end_point[1]

        ast_node = ASTNode(
            node_id=hashlib.md5(f"{node_type}:{file_path}:{start_line}".encode()).hexdigest()[:12],
            node_type=node_type.upper(),
            language=language,
            file_path=file_path,
            line=start_line,
            column=start_col,
            end_line=end_line,
            end_column=end_col,
        )

        if ts_node.child_count == 0:
            text = content[ts_node.start_byte:ts_node.end_byte]
            if text.strip():
                ast_node.value = text
                if node_type in ('identifier', 'function_name', 'class_name', 'variable_name'):
                    ast_node.name = text

        parent.add_child(ast_node)

        for child in ts_node.children:
            self._convert_tree_sitter_ast(child, ast_node, content, file_path, language)

    def _convert_python_ast(self, node: ast.AST, parent: ASTNode, content: str, file_path: str):
        node_type = type(node).__name__
        ast_node = ASTNode(
            node_id=hashlib.md5(f"{node_type}:{file_path}:{getattr(node, 'lineno', 0)}".encode()).hexdigest()[:12],
            node_type=self._map_python_node_type(node_type),
            language=Language.PYTHON,
            file_path=file_path,
            line=getattr(node, 'lineno', 1),
            column=getattr(node, 'col_offset', 0),
            end_line=getattr(node, 'end_lineno', None),
            end_column=getattr(node, 'end_col_offset', None),
        )

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            ast_node.name = node.name
        elif isinstance(node, ast.Name):
            ast_node.name = node.id
            ast_node.value = node.id
        elif isinstance(node, ast.Constant):
            ast_node.value = node.value
        elif isinstance(node, ast.Import):
            for alias in node.names:
                child = ASTNode(
                    node_id=hashlib.md5(f"import:{alias.name}".encode()).hexdigest()[:12],
                    node_type="IMPORT",
                    language=Language.PYTHON,
                    name=alias.name,
                    value=alias.asname,
                    file_path=file_path,
                    line=node.lineno,
                    column=node.col_offset,
                )
                ast_node.add_child(child)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                child = ASTNode(
                    node_id=hashlib.md5(f"import:{module}.{alias.name}".encode()).hexdigest()[:12],
                    node_type="IMPORT",
                    language=Language.PYTHON,
                    name=f"{module}.{alias.name}",
                    value=alias.asname,
                    file_path=file_path,
                    line=node.lineno,
                    column=node.col_offset,
                )
                ast_node.add_child(child)

        parent.add_child(ast_node)

        for field_name, value in ast.iter_fields(node):
            if isinstance(value, ast.AST):
                self._convert_python_ast(value, ast_node, content, file_path)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, ast.AST):
                        self._convert_python_ast(item, ast_node, content, file_path)

    def _map_python_node_type(self, py_type: str) -> str:
        mapping = {
            'Module': 'MODULE',
            'FunctionDef': 'FUNCTION',
            'AsyncFunctionDef': 'FUNCTION',
            'ClassDef': 'CLASS',
            'Return': 'RETURN',
            'If': 'IF',
            'For': 'FOR',
            'While': 'WHILE',
            'Call': 'CALL',
            'Assign': 'ASSIGNMENT',
            'BinOp': 'BINARY_OP',
            'UnaryOp': 'UNARY_OP',
            'Name': 'IDENTIFIER',
            'Constant': 'LITERAL',
            'Attribute': 'ATTRIBUTE',
            'Subscript': 'SUBSCRIPT',
            'Lambda': 'LAMBDA',
            'Try': 'TRY',
            'ExceptHandler': 'EXCEPT',
            'With': 'WITH',
            'Match': 'MATCH',
            'MatchCase': 'CASE',
            'Yield': 'YIELD',
            'GeneratorExp': 'GENERATOR',
            'ListComp': 'COMPREHENSION',
            'SetComp': 'COMPREHENSION',
            'DictComp': 'COMPREHENSION',
            'Expr': 'EXPRESSION',
        }
        return mapping.get(py_type, py_type)


class PolyglotASTDriver:
    def __init__(self):
        self.parser = ASTParser()
        self.ast_cache: dict[str, ASTNode] = {}

    def parse_file(self, file_path: str, language: Language = None) -> ParseResult:
        result = self.parser.parse_file(file_path, language)
        if result.ast:
            self.ast_cache[file_path] = result.ast
        return result

    def parse_directory(self, dir_path: str, extensions: list[str] = None) -> list[ParseResult]:
        if extensions is None:
            extensions = ['.py', '.js', '.ts', '.java', '.go', '.rs', '.cpp', '.cs']

        results = []
        for ext in extensions:
            for file_path in Path(dir_path).rglob(f'*{ext}'):
                results.append(self.parse_file(str(file_path)))
        return results

    def get_ast(self, file_path: str) -> ASTNode | None:
        return self.ast_cache.get(file_path)

    def query_ast(self, file_path: str, query: Callable[[ASTNode], bool]) -> list[ASTNode]:
        ast = self.get_ast(file_path)
        if not ast:
            result = self.parse_file(file_path)
            if result.ast:
                ast = result.ast
            else:
                return []

        results = []
        self._traverse(ast, query, results)
        return results

    def _traverse(self, node: ASTNode, query: Callable, results: list[ASTNode]):
        if query(node):
            results.append(node)
        for child in node.children:
            self._traverse(child, query, results)

    def find_functions(self, file_path: str) -> list[ASTNode]:
        return self.query_ast(file_path, lambda n: n.node_type == "FUNCTION")

    def find_classes(self, file_path: str) -> list[ASTNode]:
        return self.query_ast(file_path, lambda n: n.node_type == "CLASS")

    def find_imports(self, file_path: str) -> list[ASTNode]:
        return self.query_ast(file_path, lambda n: n.node_type == "IMPORT")

    def find_calls(self, file_path: str, function_name: str = None) -> list[ASTNode]:
        if function_name:
            return self.query_ast(file_path, lambda n: n.node_type == "CALL" and n.name == function_name)
        return self.query_ast(file_path, lambda n: n.node_type == "CALL")

    def get_dependencies(self, file_path: str) -> list[str]:
        imports = self.find_imports(file_path)
        deps = []
        for imp in imports:
            if imp.name:
                deps.append(imp.name)
            if imp.value:
                deps.append(imp.value)
        return deps

    def get_call_graph(self, dir_path: str) -> dict[str, list[str]]:
        call_graph = defaultdict(list)

        for file_path in Path(dir_path).rglob('*.py'):
            result = self.parse_file(str(file_path))
            if not result.ast:
                continue

            calls = self.query_ast(str(file_path), lambda n: n.node_type == "CALL")
            funcs = self.query_ast(str(file_path), lambda n: n.node_type == "FUNCTION")

            current_func = None
            for call in calls:
                if call.parent and call.parent.node_type == "FUNCTION":
                    current_func = call.parent.name
                    if call.name:
                        call_graph[f"{file_path}:{current_func}"].append(call.name)

        return dict(call_graph)


class ASTTransformer:
    def __init__(self, driver: PolyglotASTDriver):
        self.driver = driver

    def transform(self, file_path: str, transformer: Callable[[ASTNode], ASTNode]) -> ASTNode | None:
        ast = self.driver.get_ast(file_path)
        if not ast:
            result = self.driver.parse_file(file_path)
            if not result.ast:
                return None
            ast = result.ast

        return self._transform_node(ast, transformer)

    def _transform_node(self, node: ASTNode, transformer: Callable) -> ASTNode:
        new_node = transformer(node)
        new_children = []
        for child in node.children:
            new_child = self._transform_node(child, transformer)
            if new_child:
                new_child.parent = new_node
                new_children.append(new_child)
        new_node.children = new_children
        return new_node

    def rename_identifier(self, file_path: str, old_name: str, new_name: str) -> bool:
        def transformer(node: ASTNode) -> ASTNode:
            if node.name == old_name and node.node_type in ("IDENTIFIER", "FUNCTION", "CLASS"):
                node.name = new_name
            return node

        new_ast = self.transform(file_path, transformer)
        if new_ast:
            self.driver.ast_cache[file_path] = new_ast
            return True
        return False

    def extract_function(self, file_path: str, function_name: str) -> str | None:
        ast = self.driver.get_ast(file_path)
        if not ast:
            return None

        for node in ast.children:
            if node.node_type == "FUNCTION" and node.name == function_name:
                return self._node_to_code(node)
        return None

    def _node_to_code(self, node: ASTNode) -> str:
        if node.node_type == "FUNCTION":
            params = []
            for child in node.children:
                if child.node_type == "IDENTIFIER":
                    params.append(child.name)
            return f"def {node.name}({', '.join(params)}):\n    pass"
        return ""


class ASTIndexer:
    def __init__(self, driver: PolyglotASTDriver):
        self.driver = driver
        self.index: dict[str, list[tuple[str, ASTNode]]] = defaultdict(list)

    def index_file(self, file_path: str) -> int:
        result = self.driver.parse_file(file_path)
        if not result.ast:
            return 0

        count = 0
        self._index_node(file_path, result.ast, count)
        return count

    def _index_node(self, file_path: str, node: ASTNode, count: int):
        if node.name:
            self.index[node.name].append((file_path, node))
            count += 1
        for child in node.children:
            self._index_node(file_path, child, count)

    def index_directory(self, dir_path: str, extensions: list[str] = None) -> int:
        total = 0
        for ext in extensions or ['.py']:
            for file_path in Path(dir_path).rglob(f'*{ext}'):
                total += self.index_file(str(file_path))
        return total

    def lookup(self, name: str) -> list[tuple[str, ASTNode]]:
        return self.index.get(name, [])

    def find_definition(self, name: str, file_path: str = None) -> list[tuple[str, ASTNode]]:
        results = self.lookup(name)
        if file_path:
            results = [(fp, n) for fp, n in results if fp == file_path]
        return results


import time
