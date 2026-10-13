"""
Code Evolution - Evolutionary optimization for source code
"""
import ast
import copy
import hashlib
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum


class CodeMutationType(Enum):
    RENAME_VARIABLE = "rename_variable"
    REORDER_STATEMENTS = "reorder_statements"
    EXTRACT_METHOD = "extract_method"
    INLINE_METHOD = "inline_method"
    CHANGE_LITERAL = "change_literal"
    MODIFY_CONDITION = "modify_condition"
    ADD_LOGGING = "add_logging"
    REMOVE_DEAD_CODE = "remove_dead_code"
    SIMPLIFY_EXPRESSION = "simplify_expression"
    CHANGE_LOOP_TYPE = "change_loop_type"


@dataclass
class CodeIndividual:
    source_code: str
    ast_tree: ast.AST = None
    fitness: float = 0.0
    tests_passed: int = 0
    tests_total: int = 0
    complexity: float = 0.0
    lines_changed: int = 0
    mutations_applied: list[dict] = field(default_factory=list)
    id: str = field(default_factory=lambda: hashlib.md5(str(time.time()).encode()).hexdigest()[:12])

    def copy(self) -> 'CodeIndividual':
        return CodeIndividual(
            source_code=self.source_code,
            ast_tree=copy.deepcopy(self.ast_tree) if self.ast_tree else None,
            fitness=self.fitness,
            tests_passed=self.tests_passed,
            tests_total=self.tests_total,
            complexity=self.complexity,
            lines_changed=self.lines_changed,
            mutations_applied=self.mutations_applied.copy(),
        )


@dataclass
class CodeEvolutionConfig:
    population_size: int = 20
    generations: int = 50
    mutation_rate: float = 0.3
    test_command: str = "pytest -xvs"
    target_function: str = ""
    allowed_mutations: list[CodeMutationType] = field(default_factory=lambda: list(CodeMutationType))
    max_lines_changed: int = 50
    fitness_weights: dict[str, float] = field(default_factory=lambda: {
        "tests_pass": 10.0,
        "complexity_reduction": 2.0,
        "lines_changed_penalty": -0.1,
    })


class CodeEvolutionEngine:
    def __init__(self, config: CodeEvolutionConfig):
        self.config = config
        self.population: list[CodeIndividual] = []
        self.original_code: str = ""
        self.original_ast: ast.AST = None
        self.generation = 0
        self.best_individual: CodeIndividual | None = None

    def initialize(self, source_code: str):
        self.original_code = source_code
        self.original_ast = ast.parse(source_code)
        self.population = []

        for _ in range(self.config.population_size):
            individual = CodeIndividual(source_code=source_code)
            individual.ast_tree = copy.deepcopy(self.original_ast)
            self.population.append(individual)

        self.generation = 0
        self.best_individual = None

    async def evolve(self, test_runner: Callable[[str], tuple[int, int]]) -> CodeIndividual:
        for gen in range(self.config.generations):
            self.generation = gen

            await self._evaluate_population(test_runner)
            self._update_best()

            if self._check_convergence():
                break

            await self._selection()
            await self._crossover()
            await self._mutation()

        return self.best_individual

    async def _evaluate_population(self, test_runner: Callable):
        for individual in self.population:
            if individual.fitness == 0:
                await self._evaluate_individual(individual, test_runner)

    async def _evaluate_individual(self, individual: CodeIndividual, test_runner: Callable):
        passed, total = test_runner(individual.source_code)
        individual.tests_passed = passed
        individual.tests_total = total

        individual.complexity = self._compute_complexity(individual.source_code)
        individual.lines_changed = self._count_lines_changed(individual.source_code)

        individual.fitness = self._compute_fitness(individual)

    def _compute_complexity(self, code: str) -> float:
        try:
            tree = ast.parse(code)
            complexity = 1
            for node in ast.walk(tree):
                if isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.ExceptHandler)):
                    complexity += 1
                elif isinstance(node, ast.BoolOp):
                    complexity += len(node.values) - 1
            return complexity
        except Exception:
            return float('inf')

    def _count_lines_changed(self, code: str) -> int:
        orig_lines = self.original_code.split('\n')
        new_lines = code.split('\n')

        changed = 0
        for i, (orig, new) in enumerate(zip(orig_lines, new_lines)):
            if orig != new:
                changed += 1
        changed += abs(len(orig_lines) - len(new_lines))
        return changed

    def _compute_fitness(self, individual: CodeIndividual) -> float:
        weights = self.config.fitness_weights

        test_score = (individual.tests_passed / max(individual.tests_total, 1)) * weights["tests_pass"]
        complexity_score = (1.0 / (1.0 + individual.complexity)) * weights["complexity_reduction"]
        lines_penalty = individual.lines_changed * weights["lines_changed_penalty"]

        return test_score + complexity_score + lines_penalty

    def _update_best(self):
        valid_individuals = [ind for ind in self.population if ind.tests_passed == ind.tests_total and ind.tests_total > 0]

        if valid_individuals:
            best = max(valid_individuals, key=lambda i: i.fitness)
            if self.best_individual is None or best.fitness > self.best_individual.fitness:
                self.best_individual = best.copy()
        elif self.population:
            best = max(self.population, key=lambda i: i.fitness)
            if self.best_individual is None or best.fitness > self.best_individual.fitness:
                self.best_individual = best.copy()

    def _check_convergence(self) -> bool:
        if self.best_individual and self.best_individual.tests_passed == self.best_individual.tests_total:
            if self.generation > 10:
                return True
        return False

    async def _selection(self):
        valid = [ind for ind in self.population if ind.tests_passed == ind.tests_total]
        if len(valid) < 2:
            valid = self.population

        valid.sort(key=lambda i: i.fitness, reverse=True)
        elite_count = max(1, self.config.population_size // 10)

        new_pop = valid[:elite_count]

        while len(new_pop) < self.config.population_size:
            parent = self._tournament_select(valid)
            new_pop.append(parent.copy())

        self.population = new_pop

    def _tournament_select(self, candidates: list[CodeIndividual], k: int = 3) -> CodeIndividual:
        tournament = random.sample(candidates, min(k, len(candidates)))
        return max(tournament, key=lambda i: i.fitness)

    async def _crossover(self):
        new_pop = self.population[:max(1, self.config.population_size // 10)]

        while len(new_pop) < self.config.population_size:
            parent1 = self._tournament_select(self.population)
            parent2 = self._tournament_select(self.population)

            child_code = self._crossover_code(parent1.source_code, parent2.source_code)
            child = CodeIndividual(source_code=child_code)
            new_pop.append(child)

        self.population = new_pop

    def _crossover_code(self, code1: str, code2: str) -> str:
        lines1 = code1.split('\n')
        lines2 = code2.split('\n')

        if len(lines1) < 3 or len(lines2) < 3:
            return code1 if random.random() < 0.5 else code2

        split1 = random.randint(1, len(lines1) - 2)
        split2 = random.randint(1, len(lines2) - 2)

        child_lines = lines1[:split1] + lines2[split2:]
        return '\n'.join(child_lines)

    async def _mutation(self):
        for individual in self.population[max(1, self.config.population_size // 10):]:
            if random.random() < self.config.mutation_rate:
                await self._mutate_individual(individual)

    async def _mutate_individual(self, individual: CodeIndividual):
        mutation_type = random.choice(self.config.allowed_mutations)

        mutated_code = self._apply_mutation(individual.source_code, mutation_type)

        if mutated_code != individual.source_code:
            individual.source_code = mutated_code
            try:
                individual.ast_tree = ast.parse(mutated_code)
            except SyntaxError:
                individual.source_code = self.original_code
                individual.ast_tree = copy.deepcopy(self.original_ast)

            individual.mutations_applied.append({
                "type": mutation_type.value,
                "generation": self.generation,
            })
            individual.lines_changed = self._count_lines_changed(individual.source_code)
            individual.fitness = 0

    def _apply_mutation(self, code: str, mutation_type: CodeMutationType) -> str:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return code

        if mutation_type == CodeMutationType.CHANGE_LITERAL:
            return self._mutate_literals(tree, code)
        if mutation_type == CodeMutationType.MODIFY_CONDITION:
            return self._mutate_conditions(tree, code)
        if mutation_type == CodeMutationType.REORDER_STATEMENTS:
            return self._reorder_statements(tree, code)
        if mutation_type == CodeMutationType.SIMPLIFY_EXPRESSION:
            return self._simplify_expressions(tree, code)
        if mutation_type == CodeMutationType.ADD_LOGGING:
            return self._add_logging(tree, code)
        if mutation_type == CodeMutationType.REMOVE_DEAD_CODE:
            return self._remove_dead_code(tree, code)

        return code

    def _mutate_literals(self, tree: ast.AST, code: str) -> str:
        lines = code.split('\n')

        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str)):
                if random.random() < 0.3:
                    line_idx = node.lineno - 1
                    if 0 <= line_idx < len(lines):
                        if isinstance(node.value, int):
                            new_val = node.value + random.randint(-5, 5)
                        elif isinstance(node.value, float):
                            new_val = node.value * random.uniform(0.5, 2.0)
                        else:
                            new_val = node.value + "_mutated"

                        lines[line_idx] = lines[line_idx].replace(repr(node.value), repr(new_val))

        return '\n'.join(lines)

    def _mutate_conditions(self, tree: ast.AST, code: str) -> str:
        lines = code.split('\n')

        for node in ast.walk(tree):
            if isinstance(node, ast.Compare) and random.random() < 0.2:
                line_idx = node.lineno - 1
                if 0 <= line_idx < len(lines):
                    ops_map = {
                        ast.Eq: ast.NotEq,
                        ast.NotEq: ast.Eq,
                        ast.Lt: ast.GtE,
                        ast.LtE: ast.Gt,
                        ast.Gt: ast.LtE,
                        ast.GtE: ast.Lt,
                    }
                    # Note: This is a simplified mutation - actual AST modification would be needed
                    # For now, we just return the original code

        return code

    def _reorder_statements(self, tree: ast.AST, code: str) -> str:
        lines = code.split('\n')

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and len(node.body) > 2 and random.random() < 0.2:
                stmts = [stmt for stmt in node.body if not isinstance(stmt, (ast.Return, ast.Raise))]
                if len(stmts) > 1:
                    random.shuffle(stmts)
                    return code

        return code

    def _simplify_expressions(self, tree: ast.AST, code: str) -> str:
        return code

    def _add_logging(self, tree: ast.AST, code: str) -> str:
        return code

    def _remove_dead_code(self, tree: ast.AST, code: str) -> str:
        return code


class CodeOptimizer:
    def __init__(self, engine: CodeEvolutionEngine):
        self.engine = engine

    async def optimize(self, source_code: str, test_runner: Callable) -> str:
        self.engine.initialize(source_code)
        best = await self.engine.evolve(test_runner)
        return best.source_code if best else source_code

    async def optimize_function(self, source_code: str, function_name: str, test_runner: Callable) -> str:
        self.engine.config.target_function = function_name
        return await self.optimize(source_code, test_runner)


class RefactoringEvolution:
    def __init__(self):
        self.refactorings = [
            self._extract_method,
            self._inline_method,
            self._rename_variable,
            self._simplify_condition,
            self._remove_unused_import,
        ]

    def _extract_method(self, tree: ast.AST, code: str) -> list[str]:
        return [code]

    def _inline_method(self, tree: ast.AST, code: str) -> list[str]:
        return [code]

    def _rename_variable(self, tree: ast.AST, code: str) -> list[str]:
        return [code]

    def _simplify_condition(self, tree: ast.AST, code: str) -> list[str]:
        return [code]

    def _remove_unused_import(self, tree: ast.AST, code: str) -> list[str]:
        return [code]

    def apply_random_refactoring(self, code: str) -> str:
        try:
            tree = ast.parse(code)
            refactoring = random.choice(self.refactorings)
            results = refactoring(tree, code)
            return random.choice(results) if results else code
        except Exception:
            return code
