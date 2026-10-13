"""
Symbol Inspector - Symbol table and semantic analysis
"""
import ast
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class SymbolType(Enum):
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    CONSTANT = "constant"
    PARAMETER = "parameter"
    IMPORT = "import"
    TYPE = "type"
    ATTRIBUTE = "attribute"


class Visibility(Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    PROTECTED = "protected"
    INTERNAL = "internal"


@dataclass
class Symbol:
    name: str
    symbol_type: SymbolType
    scope: str
    file_path: str
    line: int
    column: int
    visibility: Visibility = Visibility.PUBLIC
    type_annotation: str | None = None
    docstring: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    references: list['SymbolReference'] = field(default_factory=list)
    children: list['Symbol'] = field(default_factory=list)
    parent: Optional['Symbol'] = None

    def add_child(self, child: 'Symbol') -> None:
        child.parent = self
        self.children.append(child)

    def get_full_name(self) -> str:
        parts: list[str] = []
        current: Optional[Symbol] = self
        while current:
            parts.append(current.name)
            current = current.parent
        return '.'.join(reversed(parts))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "symbol_type": self.symbol_type.value,
            "scope": self.scope,
            "file_path": self.file_path,
            "line": self.line,
            "column": self.column,
            "visibility": self.visibility.value,
            "type_annotation": self.type_annotation,
            "docstring": self.docstring,
            "metadata": self.metadata,
            "full_name": self.get_full_name(),
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class SymbolReference:
    symbol: Symbol
    file_path: str
    line: int
    column: int
    context: str = ""
    is_definition: bool = False


@dataclass
class Scope:
    name: str
    scope_type: str
    parent: Optional['Scope'] = None
    symbols: dict[str, Symbol] = field(default_factory=dict)
    children: list['Scope'] = field(default_factory=list)

    def add_symbol(self, symbol: Symbol) -> None:
        self.symbols[symbol.name] = symbol

    def get_symbol(self, name: str) -> Symbol | None:
        if name in self.symbols:
            return self.symbols[name]
        if self.parent:
            return self.parent.get_symbol(name)
        return None


class SymbolTable:
    def __init__(self):
        self.global_scope = Scope("global", "module")
        self.current_scope = self.global_scope
        self.all_symbols: dict[str, Symbol] = {}
        self.file_symbols: dict[str, list[Symbol]] = defaultdict(list)

    def enter_scope(self, name: str, scope_type: str) -> None:
        new_scope = Scope(name, scope_type, self.current_scope)
        self.current_scope.children.append(new_scope)
        self.current_scope = new_scope

    def exit_scope(self) -> None:
        if self.current_scope.parent:
            self.current_scope = self.current_scope.parent

    def define(self, symbol: Symbol) -> None:
        self.current_scope.add_symbol(symbol)
        key = f"{symbol.file_path}:{symbol.line}:{symbol.column}"
        self.all_symbols[key] = symbol
        self.file_symbols[symbol.file_path].append(symbol)

    def resolve(self, name: str) -> Symbol | None:
        return self.current_scope.get_symbol(name)

    def get_symbols_in_file(self, file_path: str) -> list[Symbol]:
        return self.file_symbols.get(file_path, [])

    def get_all_symbols(self) -> list[Symbol]:
        return list(self.all_symbols.values())


class SymbolInspector:
    def __init__(self):
        self.symbol_table = SymbolTable()
        self.references: list[SymbolReference] = []

    def inspect_file(self, file_path: str) -> list[Symbol]:
        try:
            source = Path(file_path).read_text(encoding='utf-8', errors='ignore')
            tree = ast.parse(source)
            return self.inspect_ast(tree, file_path)
        except Exception:
            return []

    def inspect_ast(self, tree: ast.AST, file_path: str) -> list[Symbol]:
        self.symbol_table = SymbolTable()
        self.references = []
        self._visit(tree, file_path)
        return self.symbol_table.get_symbols_in_file(file_path)

    def _visit(self, node: ast.AST, file_path: str) -> None:
        if isinstance(node, ast.Module):
            self.symbol_table.enter_scope("module", "module")
            for child in node.body:
                self._visit(child, file_path)
            self.symbol_table.exit_scope()

        elif isinstance(node, ast.FunctionDef):
            returns_annotation: str | None = None
            if node.returns and hasattr(ast, 'unparse'):
                try:
                    returns_annotation = ast.unparse(node.returns)
                except Exception:
                    pass

            symbol = Symbol(
                name=node.name,
                symbol_type=SymbolType.FUNCTION,
                scope=self.symbol_table.current_scope.name,
                file_path=file_path,
                line=node.lineno,
                column=node.col_offset,
                visibility=Visibility.PRIVATE if node.name.startswith('_') else Visibility.PUBLIC,
                type_annotation=returns_annotation,
                docstring=ast.get_docstring(node),
            )
            self.symbol_table.define(symbol)
            self.symbol_table.enter_scope(node.name, "function")
            for child in node.body:
                self._visit(child, file_path)
            self.symbol_table.exit_scope()

        elif isinstance(node, ast.AsyncFunctionDef):
            returns_annotation = None
            if node.returns and hasattr(ast, 'unparse'):
                try:
                    returns_annotation = ast.unparse(node.returns)
                except Exception:
                    pass

            symbol = Symbol(
                name=node.name,
                symbol_type=SymbolType.FUNCTION,
                scope=self.symbol_table.current_scope.name,
                file_path=file_path,
                line=node.lineno,
                column=node.col_offset,
                visibility=Visibility.PRIVATE if node.name.startswith('_') else Visibility.PUBLIC,
                type_annotation=returns_annotation,
                docstring=ast.get_docstring(node),
                metadata={"async": True},
            )
            self.symbol_table.define(symbol)
            self.symbol_table.enter_scope(node.name, "function")
            for child in node.body:
                self._visit(child, file_path)
            self.symbol_table.exit_scope()

        elif isinstance(node, ast.ClassDef):
            symbol = Symbol(
                name=node.name,
                symbol_type=SymbolType.CLASS,
                scope=self.symbol_table.current_scope.name,
                file_path=file_path,
                line=node.lineno,
                column=node.col_offset,
                visibility=Visibility.PRIVATE if node.name.startswith('_') else Visibility.PUBLIC,
                docstring=ast.get_docstring(node),
            )
            self.symbol_table.define(symbol)
            self.symbol_table.enter_scope(node.name, "class")
            for child in node.body:
                self._visit(child, file_path)
            self.symbol_table.exit_scope()

        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    value_annotation: str | None = None
                    if hasattr(ast, 'unparse'):
                        try:
                            value_annotation = ast.unparse(node.value)
                        except Exception:
                            pass

                    symbol = Symbol(
                        name=target.id,
                        symbol_type=SymbolType.VARIABLE,
                        scope=self.symbol_table.current_scope.name,
                        file_path=file_path,
                        line=node.lineno,
                        column=target.col_offset,
                        type_annotation=value_annotation,
                    )
                    self.symbol_table.define(symbol)

        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                annotation_str: str | None = None
                if node.annotation and hasattr(ast, 'unparse'):
                    try:
                        annotation_str = ast.unparse(node.annotation)
                    except Exception:
                        pass

                symbol = Symbol(
                    name=node.target.id,
                    symbol_type=SymbolType.VARIABLE,
                    scope=self.symbol_table.current_scope.name,
                    file_path=file_path,
                    line=node.lineno,
                    column=node.target.col_offset,
                    type_annotation=annotation_str,
                )
                self.symbol_table.define(symbol)

        elif isinstance(node, ast.Import):
            for alias in node.names:
                symbol = Symbol(
                    name=alias.asname or alias.name,
                    symbol_type=SymbolType.IMPORT,
                    scope=self.symbol_table.current_scope.name,
                    file_path=file_path,
                    line=node.lineno,
                    column=node.col_offset,
                    metadata={"module": alias.name, "alias": alias.asname},
                )
                self.symbol_table.define(symbol)

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                symbol = Symbol(
                    name=alias.asname or alias.name,
                    symbol_type=SymbolType.IMPORT,
                    scope=self.symbol_table.current_scope.name,
                    file_path=file_path,
                    line=node.lineno,
                    column=node.col_offset,
                    metadata={"module": module, "alias": alias.asname},
                )
                self.symbol_table.define(symbol)

        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load):
                ref = SymbolReference(
                    symbol=Symbol(name=node.id, symbol_type=SymbolType.VARIABLE, scope="", file_path="", line=0, column=0),
                    file_path=file_path,
                    line=node.lineno,
                    column=node.col_offset,
                )
                self.references.append(ref)

        for child in ast.iter_child_nodes(node):
            self._visit(child, file_path)

    def find_references(self, symbol_name: str, file_path: str | None = None) -> list[SymbolReference]:
        results: list[SymbolReference] = []
        for ref in self.references:
            if ref.symbol.name == symbol_name:
                if file_path is None or ref.file_path == file_path:
                    results.append(ref)
        return results

    def get_call_graph(self, file_path: str | None = None) -> dict[str, list[str]]:
        call_graph: dict[str, list[str]] = defaultdict(list)
        for ref in self.references:
            if file_path is None or ref.file_path == file_path:
                caller = self._find_enclosing_function(ref)
                if caller:
                    call_graph[caller].append(ref.symbol.name)
        return dict(call_graph)

    def _find_enclosing_function(self, ref: SymbolReference) -> str | None:
        return None

    def analyze_complexity(self, file_path: str) -> dict[str, Any]:
        symbols = self.symbol_table.get_symbols_in_file(file_path)
        functions = [s for s in symbols if s.symbol_type == SymbolType.FUNCTION]
        classes = [s for s in symbols if s.symbol_type == SymbolType.CLASS]

        return {
            "total_symbols": len(symbols),
            "functions": len(functions),
            "classes": len(classes),
            "imports": len([s for s in symbols if s.symbol_type == SymbolType.IMPORT]),
            "avg_function_length": 0,
        }


class CrossFileAnalyzer:
    def __init__(self):
        self.inspector = SymbolInspector()
        self.file_symbols: dict[str, list[Symbol]] = {}

    def analyze_project(self, root_path: str, extensions: list[str] | None = None) -> dict[str, Any]:
        if extensions is None:
            extensions = ['.py']

        all_symbols: dict[str, list[dict[str, Any]]] = {}
        for ext in extensions:
            for file_path in Path(root_path).rglob(f'*{ext}'):
                symbols = self.inspector.inspect_file(str(file_path))
                self.file_symbols[str(file_path)] = symbols
                all_symbols[str(file_path)] = [s.to_dict() for s in symbols]

        return {
            "files_analyzed": len(self.file_symbols),
            "total_symbols": sum(len(s) for s in self.file_symbols.values()),
            "symbols": all_symbols,
        }

    def find_unused_symbols(self) -> list[Symbol]:
        unused: list[Symbol] = []
        for file_path, symbols in self.file_symbols.items():
            for symbol in symbols:
                refs = self.inspector.find_references(symbol.name, file_path)
                if not refs or len(refs) == 1:
                    unused.append(symbol)
        return unused

    def find_circular_imports(self) -> list[list[str]]:
        imports: dict[str, set[str]] = defaultdict(set)
        for file_path, symbols in self.file_symbols.items():
            for symbol in symbols:
                if symbol.symbol_type == SymbolType.IMPORT:
                    module = symbol.metadata.get("module")
                    if module:
                        imports[file_path].add(module)

        cycles: list[list[str]] = []
        visited: set[str] = set()
        path: list[str] = []

        def dfs(node: str) -> None:
            visited.add(node)
            path.append(node)
            for neighbor in imports.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in path:
                    idx = path.index(neighbor)
                    cycles.append(path[idx:] + [neighbor])
            path.pop()

        for node in imports:
            if node not in visited:
                dfs(node)

        return cycles