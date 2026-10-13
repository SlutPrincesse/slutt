"""
Test Generator - Autonomous test case generation
"""
import ast
import hashlib
import random
import string
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TestType(Enum):
    UNIT = "unit"
    INTEGRATION = "integration"
    PROPERTY = "property"
    FUZZ = "fuzz"
    REGRESSION = "regression"
    PERFORMANCE = "performance"


class TestFramework(Enum):
    PYTEST = "pytest"
    UNITTEST = "unittest"
    HYPOTHESIS = "hypothesis"


@dataclass
class TestCase:
    name: str
    test_type: TestType
    target_function: str
    input_data: Any
    expected_output: Any = None
    expected_exception: type[Exception] | None = None
    setup_code: str = ""
    teardown_code: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "test_type": self.test_type.value,
            "target_function": self.target_function,
            "input_data": self.input_data,
            "expected_output": self.expected_output,
            "expected_exception": self.expected_exception.__name__ if self.expected_exception else None,
            "setup_code": self.setup_code,
            "teardown_code": self.teardown_code,
            "metadata": self.metadata,
        }


@dataclass
class TestSuite:
    name: str
    test_cases: list[TestCase] = field(default_factory=list)
    framework: TestFramework = TestFramework.PYTEST
    fixtures: dict[str, str] = field(default_factory=dict)

    def add_test(self, test: TestCase):
        self.test_cases.append(test)

    def to_code(self) -> str:
        lines = [
            f"# Auto-generated test suite: {self.name}",
            "import pytest",
            "",
        ]

        for fixture_name, fixture_code in self.fixtures.items():
            lines.append(fixture_code)
            lines.append("")

        for test in self.test_cases:
            lines.append(self._generate_test_code(test))
            lines.append("")

        return "\n".join(lines)

    def _generate_test_code(self, test: TestCase) -> str:
        lines = [
            f"def test_{test.name}():",
        ]

        if test.setup_code:
            for line in test.setup_code.split('\n'):
                lines.append(f"    {line}")

        if test.expected_exception:
            lines.append(f"    with pytest.raises({test.expected_exception.__name__}):")
            lines.append(f"        {test.target_function}({test._format_input(test.input_data)})")
        elif test.expected_output is not None:
            lines.append(f"    result = {test.target_function}({test._format_input(test.input_data)})")
            lines.append(f"    assert result == {repr(test.expected_output)}")
        else:
            lines.append(f"    {test.target_function}({test._format_input(test.input_data)})")

        if test.teardown_code:
            for line in test.teardown_code.split('\n'):
                lines.append(f"    {line}")

        return "\n".join(lines)

    def _format_input(self, data: Any) -> str:
        if isinstance(data, str):
            return f'"{data}"'
        if isinstance(data, (list, tuple)):
            return f"[{', '.join(self._format_input(d) for d in data)}]"
        if isinstance(data, dict):
            return f"{{{', '.join(f'{self._format_input(k)}: {self._format_input(v)}' for k, v in data.items())}}}"
        return str(data)


class TestGenerator:
    def __init__(self):
        self.generators: dict[str, Callable] = {}
        self.templates: dict[str, str] = {}
        self._register_default_generators()

    def _register_default_generators(self):
        self.generators["int"] = lambda: random.randint(-1000, 1000)
        self.generators["float"] = lambda: random.uniform(-1000.0, 1000.0)
        self.generators["str"] = lambda: ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(1, 20)))
        self.generators["bool"] = lambda: random.choice([True, False])
        self.generators["list"] = lambda: [random.randint(1, 10) for _ in range(random.randint(0, 10))]
        self.generators["dict"] = lambda: {f"key{i}": random.randint(1, 100) for i in range(random.randint(0, 5))}
        self.generators["none"] = lambda: None

    def register_generator(self, type_name: str, generator: Callable):
        self.generators[type_name] = generator

    def generate_for_function(
        self,
        func_name: str,
        signature: dict[str, Any],
        num_tests: int = 10,
    ) -> list[TestCase]:
        tests = []

        for i in range(num_tests):
            input_data = {}
            for param_name, param_info in signature.get("parameters", {}).items():
                param_type = param_info.get("type", "int")
                if param_type in self.generators:
                    input_data[param_name] = self.generators[param_type]()
                else:
                    input_data[param_name] = self.generators.get("int", lambda: 0)()

            test = TestCase(
                name=f"{func_name}_{hashlib.md5(str(input_data).encode()).hexdigest()[:8]}",
                test_type=TestType.UNIT,
                target_function=func_name,
                input_data=input_data,
            )
            tests.append(test)

        return tests

    def generate_property_tests(
        self,
        func_name: str,
        signature: dict[str, Any],
        properties: list[Callable],
        num_tests: int = 100,
    ) -> list[TestCase]:
        tests = []

        for i in range(num_tests):
            input_data = {}
            for param_name, param_info in signature.get("parameters", {}).items():
                param_type = param_info.get("type", "int")
                if param_type in self.generators:
                    input_data[param_name] = self.generators[param_type]()

            for prop in properties:
                test = TestCase(
                    name=f"{func_name}_property_{prop.__name__}_{i}",
                    test_type=TestType.PROPERTY,
                    target_function=func_name,
                    input_data=input_data,
                    metadata={"property": prop.__name__},
                )
                tests.append(test)

        return tests

    def generate_fuzz_tests(
        self,
        func_name: str,
        signature: dict[str, Any],
        num_tests: int = 50,
    ) -> list[TestCase]:
        fuzz_generators = {
            "int": lambda: random.choice([-2**31, 2**31 - 1, 0, -1, 1, random.randint(-10000, 10000)]),
            "float": lambda: random.choice([float('inf'), float('-inf'), float('nan'), 0.0, -0.0, random.uniform(-1e10, 1e10)]),
            "str": lambda: random.choice(["", "a" * 10000, "\x00\x01\x02", "🚀" * 100, "'; DROP TABLE users; --"]),
            "list": lambda: random.choice([[], [None] * 1000, list(range(10000))]),
            "dict": lambda: random.choice([{}, {"key": "value"} * 100, {i: i for i in range(1000)}]),
        }

        tests = []

        for i in range(num_tests):
            input_data = {}
            for param_name, param_info in signature.get("parameters", {}).items():
                param_type = param_info.get("type", "int")
                if param_type in fuzz_generators:
                    input_data[param_name] = fuzz_generators[param_type]()
                else:
                    input_data[param_name] = fuzz_generators.get("int", lambda: 0)()

            test = TestCase(
                name=f"{func_name}_fuzz_{i}",
                test_type=TestType.FUZZ,
                target_function=func_name,
                input_data=input_data,
                expected_exception=Exception,
            )
            tests.append(test)

        return tests

    def generate_from_ast(self, source_code: str) -> list[TestCase]:
        tree = ast.parse(source_code)
        tests = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                signature = self._extract_signature(node)
                tests.extend(self.generate_for_function(node.name, signature))

        return tests

    def _extract_signature(self, node: ast.FunctionDef) -> dict[str, Any]:
        parameters = {}
        for arg in node.args.args:
            param_type = "int"
            if arg.annotation:
                if isinstance(arg.annotation, ast.Name):
                    param_type = arg.annotation.id
                elif isinstance(arg.annotation, ast.Constant):
                    param_type = str(arg.annotation.value)
            parameters[arg.arg] = {"type": param_type}

        return {"parameters": parameters, "name": node.name}


class MutationTestGenerator:
    def __init__(self, generator: TestGenerator):
        self.generator = generator

    def generate_mutants(self, source_code: str) -> list[str]:
        mutants = []
        tree = ast.parse(source_code)

        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp):
                mutants.extend(self._mutate_binop(tree, node))
            elif isinstance(node, ast.Compare):
                mutants.extend(self._mutate_compare(tree, node))
            elif isinstance(node, ast.If):
                mutants.extend(self._mutate_if(tree, node))

        return mutants

    def _mutate_binop(self, tree: ast.AST, target: ast.BinOp) -> list[str]:
        mutants = []
        ops = [ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow]

        for op_class in ops:
            if not isinstance(target.op, op_class):
                mutant_tree = self._copy_and_replace(tree, target, target.op, op_class())
                mutants.append(ast.unparse(mutant_tree) if hasattr(ast, 'unparse') else "")

        return mutants

    def _mutate_compare(self, tree: ast.AST, target: ast.Compare) -> list[str]:
        mutants = []
        ops = [ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE]

        for op_class in ops:
            if not any(isinstance(op, op_class) for op in target.ops):
                mutant_tree = self._copy_and_replace(tree, target, target.ops[0], op_class())
                mutants.append(ast.unparse(mutant_tree) if hasattr(ast, 'unparse') else "")

        return mutants

    def _mutate_if(self, tree: ast.AST, target: ast.If) -> list[str]:
        mutants = []

        mutant_tree = self._copy_and_replace(tree, target, target.test, ast.Constant(value=True))
        mutants.append(ast.unparse(mutant_tree) if hasattr(ast, 'unparse') else "")

        mutant_tree = self._copy_and_replace(tree, target, target.test, ast.Constant(value=False))
        mutants.append(ast.unparse(mutant_tree) if hasattr(ast, 'unparse') else "")

        return mutants

    def _copy_and_replace(self, tree: ast.AST, target: ast.AST, old: ast.AST, new: ast.AST) -> ast.AST:
        import copy
        new_tree = copy.deepcopy(tree)

        def replace(node: ast.AST):
            for field, value in ast.iter_fields(node):
                if value is old:
                    setattr(node, field, new)
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        if item is old:
                            value[i] = new
                        elif isinstance(item, ast.AST):
                            replace(item)
                elif isinstance(value, ast.AST):
                    replace(value)

        replace(new_tree)
        return new_tree
