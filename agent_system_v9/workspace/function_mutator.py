"""
Function Mutator - Mutates functions for testing and evolution
"""
import ast
import hashlib
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MutationType(Enum):
    ARITHMETIC = "arithmetic"
    COMPARISON = "comparison"
    LOGICAL = "logical"
    CONSTANT = "constant"
    STATEMENT_DELETION = "statement_deletion"
    VARIABLE_REPLACEMENT = "variable_replacement"
    FUNCTION_CALL = "function_call"
    RETURN_VALUE = "return_value"
    CONDITIONAL_BOUNDARY = "conditional_boundary"
    LOOP_MUTATION = "loop_mutation"


@dataclass
class Mutation:
    mutation_id: str
    mutation_type: MutationType
    original_code: str
    mutated_code: str
    file_path: str
    line: int
    column: int
    description: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MutationResult:
    function_name: str
    mutations: list[Mutation]
    killed_mutants: int = 0
    survived_mutants: int = 0
    total_mutants: int = 0
    mutation_score: float = 0.0


class FunctionMutator:
    def __init__(self):
        self.mutators: dict[MutationType, Callable] = {
            MutationType.ARITHMETIC: self._mutate_arithmetic,
            MutationType.COMPARISON: self._mutate_comparison,
            MutationType.LOGICAL: self._mutate_logical,
            MutationType.CONSTANT: self._mutate_constant,
            MutationType.STATEMENT_DELETION: self._mutate_statement_deletion,
            MutationType.RETURN_VALUE: self._mutate_return_value,
            MutationType.CONDITIONAL_BOUNDARY: self._mutate_conditional_boundary,
        }
        self.mutations: list[Mutation] = []

    def mutate_function(self, source: str, function_name: str = None,
                       mutation_types: list[MutationType] = None) -> MutationResult:
        tree = ast.parse(source)

        if function_name:
            target_node = self._find_function(tree, function_name)
            if not target_node:
                return MutationResult(function_name=function_name or "unknown", mutations=[])
        else:
            target_node = tree

        mutations = []
        for mut_type in mutation_types or list(self.mutators.keys()):
            if mut_type in self.mutators:
                mutations.extend(self.mutators[mut_type](target_node, source))

        self.mutations = mutations

        return MutationResult(
            function_name=function_name or "module",
            mutations=mutations,
            total_mutants=len(mutations),
        )

    def _find_function(self, tree: ast.AST, name: str) -> ast.AST | None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return node
        return None

    def _mutate_arithmetic(self, node: ast.AST, source: str) -> list[Mutation]:
        mutations = []
        operators = {
            ast.Add: [ast.Sub, ast.Mult, ast.Div],
            ast.Sub: [ast.Add, ast.Mult, ast.Div],
            ast.Mult: [ast.Add, ast.Sub, ast.Div],
            ast.Div: [ast.Add, ast.Sub, ast.Mult],
            ast.Mod: [ast.Add, ast.Sub, ast.Mult],
            ast.Pow: [ast.Mult, ast.Div],
        }

        for n in ast.walk(node):
            if isinstance(n, ast.BinOp) and type(n.op) in operators:
                for replacement in operators[type(n.op)]:
                    mutation = self._create_mutation(
                        n, source, f"Replace {type(n.op).__name__} with {replacement.__name__}",
                        MutationType.ARITHMETIC,
                    )
                    mutations.append(mutation)

        return mutations

    def _mutate_comparison(self, node: ast.AST, source: str) -> list[Mutation]:
        mutations = []
        operators = {
            ast.Eq: [ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE],
            ast.NotEq: [ast.Eq, ast.Lt, ast.LtE, ast.Gt, ast.GtE],
            ast.Lt: [ast.Eq, ast.NotEq, ast.LtE, ast.Gt, ast.GtE],
            ast.LtE: [ast.Eq, ast.NotEq, ast.Lt, ast.Gt, ast.GtE],
            ast.Gt: [ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.GtE],
            ast.GtE: [ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt],
            ast.In: [ast.NotIn],
            ast.NotIn: [ast.In],
            ast.Is: [ast.IsNot],
            ast.IsNot: [ast.Is],
        }

        for n in ast.walk(node):
            if isinstance(n, ast.Compare):
                for op in n.ops:
                    if type(op) in operators:
                        for replacement in operators[type(op)]:
                            mutation = self._create_mutation(
                                n, source, f"Replace {type(op).__name__} with {replacement.__name__}",
                                MutationType.COMPARISON,
                            )
                            mutations.append(mutation)

        return mutations

    def _mutate_logical(self, node: ast.AST, source: str) -> list[Mutation]:
        mutations = []
        operators = {
            ast.And: [ast.Or],
            ast.Or: [ast.And],
        }

        for n in ast.walk(node):
            if isinstance(n, ast.BoolOp) and type(n.op) in operators:
                for replacement in operators[type(n.op)]:
                    mutation = self._create_mutation(
                        n, source, f"Replace {type(n.op).__name__} with {replacement.__name__}",
                        MutationType.LOGICAL,
                    )
                    mutations.append(mutation)

        return mutations

    def _mutate_constant(self, node: ast.AST, source: str) -> list[Mutation]:
        mutations = []
        constant_replacements = {
            True: False,
            False: True,
            0: 1,
            1: 0,
            -1: 1,
            "": "mutated",
            None: 0,
        }

        for n in ast.walk(node):
            if isinstance(n, ast.Constant) and n.value in constant_replacements:
                mutation = self._create_mutation(
                    n, source, f"Replace constant {repr(n.value)} with {repr(constant_replacements[n.value])}",
                    MutationType.CONSTANT,
                )
                mutations.append(mutation)

        return mutations

    def _mutate_statement_deletion(self, node: ast.AST, source: str) -> list[Mutation]:
        mutations = []

        for n in ast.walk(node):
            if isinstance(n, (ast.Expr, ast.Assign, ast.AugAssign, ast.Pass, ast.Break, ast.Continue)):
                if not self._is_critical(n):
                    mutation = self._create_mutation(
                        n, source, f"Delete statement {type(n).__name__}",
                        MutationType.STATEMENT_DELETION,
                    )
                    mutations.append(mutation)

        return mutations

    def _is_critical(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Name) and func.id in ('print', 'logging', 'log'):
                return True
            if isinstance(func, ast.Attribute) and func.attr in ('log', 'error', 'warning'):
                return True
        return False

    def _mutate_return_value(self, node: ast.AST, source: str) -> list[Mutation]:
        mutations = []

        for n in ast.walk(node):
            if isinstance(n, ast.Return) and n.value:
                if isinstance(n.value, ast.Constant):
                    replacements = {
                        True: False,
                        False: True,
                        0: 1,
                        1: 0,
                        "": "mutated",
                        None: 0,
                    }
                    if n.value.value in replacements:
                        mutation = self._create_mutation(
                            n, source, f"Change return value from {repr(n.value.value)} to {repr(replacements[n.value.value])}",
                            MutationType.RETURN_VALUE,
                        )
                        mutations.append(mutation)
                elif isinstance(n.value, ast.Name):
                    mutation = self._create_mutation(
                        n, source, f"Change return variable {n.value.id} to None",
                        MutationType.RETURN_VALUE,
                    )
                    mutations.append(mutation)

        return mutations

    def _mutate_conditional_boundary(self, node: ast.AST, source: str) -> list[Mutation]:
        mutations = []

        for n in ast.walk(node):
            if isinstance(n, ast.Compare):
                for op in n.ops:
                    if isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)):
                        mutation = self._create_mutation(
                            n, source, f"Mutate boundary condition {type(op).__name__}",
                            MutationType.CONDITIONAL_BOUNDARY,
                        )
                        mutations.append(mutation)

        return mutations

    def _create_mutation(self, node: ast.AST, source: str, description: str, mut_type: MutationType) -> Mutation:
        lines = source.split('\n')
        line = getattr(node, 'lineno', 1)
        column = getattr(node, 'col_offset', 0)

        start = max(0, line - 3)
        end = min(len(lines), line + 2)
        original = '\n'.join(lines[start:end])

        return Mutation(
            mutation_id=hashlib.md5(f"{description}:{line}:{column}".encode()).hexdigest()[:12],
            mutation_type=mut_type,
            original_code=original,
            mutated_code=f"# MUTATED: {description}\n{original}",
            file_path="<source>",
            line=line,
            column=column,
            description=description,
        )

    def apply_mutation(self, source: str, mutation: Mutation) -> str:
        lines = source.split('\n')
        line_idx = mutation.line - 1
        if 0 <= line_idx < len(lines):
            lines[line_idx] = f"# MUTATED: {mutation.description}\n{lines[line_idx]}"
        return '\n'.join(lines)

    def generate_mutants(self, source: str, function_name: str = None,
                        max_mutants: int = 100) -> list[str]:
        result = self.mutate_function(source, function_name)
        mutants = []

        for mutation in result.mutations[:max_mutants]:
            mutant = self.apply_mutation(source, mutation)
            mutants.append(mutant)

        return mutants


class MutationTester:
    def __init__(self, mutator: FunctionMutator):
        self.mutator = mutator

    def test_mutants(self, source: str, test_func: Callable,
                    function_name: str = None) -> MutationResult:
        result = self.mutator.mutate_function(source, function_name)

        for mutation in result.mutations:
            mutant_code = self.mutator.apply_mutation(source, mutation)

            try:
                exec(mutant_code)
                test_func()
                result.survived_mutants += 1
            except AssertionError:
                result.killed_mutants += 1
            except Exception:
                result.survived_mutants += 1

        result.mutation_score = result.killed_mutants / max(result.total_mutants, 1)
        return result


class EvolutionaryMutator:
    def __init__(self, mutator: FunctionMutator):
        self.mutator = mutator
        self.population: list[str] = []
        self.fitness_scores: dict[str, float] = {}

    def initialize_population(self, source: str, function_name: str, size: int = 20):
        mutants = self.mutator.generate_mutants(source, function_name, size)
        self.population = mutants
        for mutant in mutants:
            self.fitness_scores[mutant] = 0.0

    def evaluate_fitness(self, test_func: Callable) -> dict[str, float]:
        for mutant in self.population:
            try:
                exec(mutant)
                test_func()
                self.fitness_scores[mutant] = 1.0
            except AssertionError:
                self.fitness_scores[mutant] = 0.0
            except Exception:
                self.fitness_scores[mutant] = 0.5

        return self.fitness_scores

    def evolve(self, generations: int = 10, test_func: Callable = None) -> list[str]:
        for _ in range(generations):
            if test_func:
                self.evaluate_fitness(test_func)

            sorted_pop = sorted(self.population, key=lambda m: self.fitness_scores.get(m, 0), reverse=True)
            elite = sorted_pop[:len(sorted_pop) // 4]

            new_pop = list(elite)
            while len(new_pop) < len(self.population):
                parent1 = random.choice(elite)
                parent2 = random.choice(elite)
                child = self._crossover(parent1, parent2)
                if random.random() < 0.1:
                    child = self._mutate(child)
                new_pop.append(child)

            self.population = new_pop

        return self.population

    def _crossover(self, parent1: str, parent2: str) -> str:
        lines1 = parent1.split('\n')
        lines2 = parent2.split('\n')
        min_len = min(len(lines1), len(lines2))
        if min_len < 2:
            return parent1
        crossover_point = random.randint(1, min_len - 1)
        return '\n'.join(lines1[:crossover_point] + lines2[crossover_point:])

    def _mutate(self, code: str) -> str:
        return code
