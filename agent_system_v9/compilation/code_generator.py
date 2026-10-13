"""
Universal Code Generator - Multi-target code generation
"""
import ast
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class TargetLanguage(Enum):
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
class CodeTemplate:
    name: str
    language: TargetLanguage
    template: str
    parameters: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationContext:
    target: TargetLanguage
    output_dir: str
    variables: dict[str, Any] = field(default_factory=dict)
    imports: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class CodeGenerator(ABC):
    @abstractmethod
    def generate(self, ast_node: ast.AST, context: GenerationContext) -> str:
        pass

    @abstractmethod
    def get_file_extension(self) -> str:
        pass


class PythonCodeGenerator(CodeGenerator):
    def generate(self, ast_node: ast.AST, context: GenerationContext) -> str:
        if hasattr(ast, 'unparse'):
            return ast.unparse(ast_node)
        return ""

    def get_file_extension(self) -> str:
        return "py"


class JavaScriptCodeGenerator(CodeGenerator):
    def generate(self, ast_node: ast.AST, context: GenerationContext) -> str:
        return self._convert_ast(ast_node)

    def _convert_ast(self, node: ast.AST) -> str:
        if isinstance(node, ast.Module):
            return '\n'.join(self._convert_ast(n) for n in node.body)
        if isinstance(node, ast.FunctionDef):
            args = ', '.join(arg.arg for arg in node.args.args)
            body = '\n    '.join(self._convert_ast(n) for n in node.body)
            return f"function {node.name}({args}) {{\n    {body}\n}}"
        if isinstance(node, ast.Return):
            return f"return {self._convert_ast(node.value)};"
        if isinstance(node, ast.Call):
            func = self._convert_ast(node.func)
            args = ', '.join(self._convert_ast(arg) for arg in node.args)
            return f"{func}({args})"
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Constant):
            return repr(node.value)
        return ""

    def get_file_extension(self) -> str:
        return "js"


class TypeScriptCodeGenerator(JavaScriptCodeGenerator):
    def get_file_extension(self) -> str:
        return "ts"


class RustCodeGenerator(CodeGenerator):
    def generate(self, ast_node: ast.AST, context: GenerationContext) -> str:
        return self._convert_ast(ast_node)

    def _convert_ast(self, node: ast.AST) -> str:
        if isinstance(node, ast.Module):
            return '\n'.join(self._convert_ast(n) for n in node.body)
        if isinstance(node, ast.FunctionDef):
            args = ', '.join(f"{arg.arg}: i32" for arg in node.args.args)
            body = '\n    '.join(self._convert_ast(n) for n in node.body)
            return f"fn {node.name}({args}) -> i32 {{\n    {body}\n}}"
        if isinstance(node, ast.Return):
            return f"return {self._convert_ast(node.value)};"
        if isinstance(node, ast.Call):
            func = self._convert_ast(node.func)
            args = ', '.join(self._convert_ast(arg) for arg in node.args)
            return f"{func}({args})"
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Constant):
            if isinstance(node.value, int):
                return str(node.value)
            if isinstance(node.value, str):
                return f'"{node.value}"'
            return str(node.value)
        return ""

    def get_file_extension(self) -> str:
        return "rs"


class UniversalCodeGenerator:
    def __init__(self) -> None:
        self.generators: dict[TargetLanguage, CodeGenerator] = {
            TargetLanguage.PYTHON: PythonCodeGenerator(),
            TargetLanguage.JAVASCRIPT: JavaScriptCodeGenerator(),
            TargetLanguage.TYPESCRIPT: TypeScriptCodeGenerator(),
            TargetLanguage.RUST: RustCodeGenerator(),
        }
        self.templates: dict[str, CodeTemplate] = {}
        self._register_default_templates()

    def _register_default_templates(self) -> None:
        self.templates["function"] = CodeTemplate(
            name="function",
            language=TargetLanguage.PYTHON,
            template="def {{name}}({{args}}):\n    {{body}}",
            parameters=["name", "args", "body"],
        )

    def register_generator(self, language: TargetLanguage, generator: CodeGenerator) -> None:
        self.generators[language] = generator

    def register_template(self, template: CodeTemplate) -> None:
        self.templates[template.name] = template

    def generate_code(
        self,
        ast_node: ast.AST,
        target: TargetLanguage,
        context: GenerationContext | None = None,
    ) -> str:
        if target not in self.generators:
            raise ValueError(f"No generator for target: {target}")

        context = context or GenerationContext(target=target, output_dir=".")
        generator = self.generators[target]
        return generator.generate(ast_node, context)

    def generate_file(
        self,
        ast_node: ast.AST,
        target: TargetLanguage,
        file_path: str,
        context: GenerationContext | None = None,
    ) -> None:
        code = self.generate_code(ast_node, target, context)
        Path(file_path).write_text(code)

    def generate_from_template(
        self,
        template_name: str,
        variables: dict[str, Any],
        target: TargetLanguage | None = None,
    ) -> str:
        template = self.templates.get(template_name)
        if not template:
            raise ValueError(f"Template not found: {template_name}")

        target = target or template.language
        result = template.template
        for key, value in variables.items():
            result = result.replace(f"{{{{{key}}}}}", str(value))
        return result


class ASTToCodeConverter:
    def __init__(self, generator: UniversalCodeGenerator) -> None:
        self.generator = generator

    def convert_file(self, source_path: str, target: TargetLanguage, output_path: str | None = None) -> None:
        source = Path(source_path).read_text()
        tree = ast.parse(source)
        output = output_path or str(Path(source_path).with_suffix(f".{self.generator.generators[target].get_file_extension()}"))
        self.generator.generate_file(tree, target, output)


class IncrementalCodeGenerator:
    def __init__(self, generator: UniversalCodeGenerator) -> None:
        self.generator = generator
        self.cache: dict[str, str] = {}

    def generate_if_changed(self, source: str, target: TargetLanguage, cache_key: str) -> str | None:
        hash_val = hashlib.md5(source.encode()).hexdigest()
        if self.cache.get(cache_key) == hash_val:
            return None

        tree = ast.parse(source)
        code = self.generator.generate_code(tree, target)
        self.cache[cache_key] = hash_val
        return code