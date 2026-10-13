"""
Evolution Engine - Core evolutionary algorithms for code optimization
"""
import asyncio
import hashlib
import random
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EvolutionStrategy(Enum):
    GENETIC_ALGORITHM = "genetic_algorithm"
    EVOLUTIONARY_STRATEGIES = "evolutionary_strategies"
    DIFFERENTIAL_EVOLUTION = "differential_evolution"
    PARTICLE_SWARM = "particle_swarm"
    SIMULATED_ANNEALING = "simulated_annealing"


class SelectionMethod(Enum):
    TOURNAMENT = "tournament"
    ROULETTE = "roulette"
    RANK = "rank"
    TRUNCATION = "truncation"
    BOLTZMANN = "boltzmann"


@dataclass
class Individual:
    genome: dict[str, Any]
    fitness: float = 0.0
    age: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: hashlib.md5(str(time.time()).encode()).hexdigest()[:12])

    def copy(self) -> 'Individual':
        return Individual(
            genome=self.genome.copy(),
            fitness=self.fitness,
            age=self.age,
            metadata=self.metadata.copy(),
        )


@dataclass
class EvolutionConfig:
    population_size: int = 50
    generations: int = 100
    mutation_rate: float = 0.1
    crossover_rate: float = 0.7
    elite_size: int = 2
    selection_method: SelectionMethod = SelectionMethod.TOURNAMENT
    tournament_size: int = 3
    strategy: EvolutionStrategy = EvolutionStrategy.GENETIC_ALGORITHM
    maximize: bool = True
    early_stopping: int = 20
    diversity_threshold: float = 0.01


@dataclass
class EvolutionResult:
    best_individual: Individual
    best_fitness: float
    generations_run: int
    population_history: list[list[Individual]]
    fitness_history: list[float]
    converged: bool
    convergence_generation: int


class FitnessFunction(ABC):
    @abstractmethod
    def evaluate(self, individual: Individual) -> float:
        pass


class EvolutionEngine:
    def __init__(self, config: EvolutionConfig = None):
        self.config = config or EvolutionConfig()
        self.population: list[Individual] = []
        self.generation = 0
        self.fitness_history: list[float] = []
        self.population_history: list[list[Individual]] = []
        self.best_individual: Individual | None = None
        self.best_fitness = float('-inf') if self.config.maximize else float('inf')
        self._stagnation_counter = 0

    def initialize_population(self, generator: Callable[[], dict[str, Any]]):
        self.population = []
        for _ in range(self.config.population_size):
            genome = generator()
            individual = Individual(genome=genome)
            self.population.append(individual)
        self.generation = 0
        self.fitness_history = []
        self.population_history = []
        self._stagnation_counter = 0

    async def evolve(self, fitness_fn: FitnessFunction) -> EvolutionResult:
        for gen in range(self.config.generations):
            self.generation = gen

            await self._evaluate_population(fitness_fn)
            self._update_best()
            self._record_history()

            if self._check_convergence():
                break

            await self._selection()
            await self._crossover()
            await self._mutation()

            self._age_population()

        return EvolutionResult(
            best_individual=self.best_individual,
            best_fitness=self.best_fitness,
            generations_run=self.generation + 1,
            population_history=self.population_history,
            fitness_history=self.fitness_history,
            converged=self._stagnation_counter >= self.config.early_stopping,
            convergence_generation=self.generation - self._stagnation_counter if self._stagnation_counter >= self.config.early_stopping else -1,
        )

    async def _evaluate_population(self, fitness_fn: FitnessFunction):
        tasks = [self._evaluate_individual(ind, fitness_fn) for ind in self.population]
        await asyncio.gather(*tasks)

    async def _evaluate_individual(self, individual: Individual, fitness_fn: FitnessFunction):
        individual.fitness = fitness_fn.evaluate(individual)

    def _update_best(self):
        sorted_pop = sorted(self.population, key=lambda i: i.fitness, reverse=self.config.maximize)
        current_best = sorted_pop[0]

        is_better = (current_best.fitness > self.best_fitness) if self.config.maximize else (current_best.fitness < self.best_fitness)

        if is_better:
            self.best_individual = current_best.copy()
            self.best_fitness = current_best.fitness
            self._stagnation_counter = 0
        else:
            self._stagnation_counter += 1

    def _record_history(self):
        self.fitness_history.append(self.best_fitness)
        self.population_history.append([ind.copy() for ind in self.population])

    def _check_convergence(self) -> bool:
        if len(self.fitness_history) < 2:
            return False

        recent = self.fitness_history[-self.config.early_stopping:]
        if len(recent) < self.config.early_stopping:
            return False

        improvement = max(recent) - min(recent) if self.config.maximize else min(recent) - max(recent)
        return improvement < self.config.diversity_threshold

    async def _selection(self):
        if self.config.selection_method == SelectionMethod.TOURNAMENT:
            self.population = await self._tournament_selection()
        elif self.config.selection_method == SelectionMethod.ROULETTE:
            self.population = await self._roulette_selection()
        elif self.config.selection_method == SelectionMethod.RANK:
            self.population = await self._rank_selection()
        elif self.config.selection_method == SelectionMethod.TRUNCATION:
            self.population = await self._truncation_selection()

    async def _tournament_selection(self) -> list[Individual]:
        new_pop = []
        sorted_pop = sorted(self.population, key=lambda i: i.fitness, reverse=self.config.maximize)
        new_pop.extend(sorted_pop[:self.config.elite_size])

        while len(new_pop) < self.config.population_size:
            tournament = random.sample(self.population, min(self.config.tournament_size, len(self.population)))
            winner = max(tournament, key=lambda i: i.fitness) if self.config.maximize else min(tournament, key=lambda i: i.fitness)
            new_pop.append(winner.copy())

        return new_pop

    async def _roulette_selection(self) -> list[Individual]:
        fitnesses = [ind.fitness for ind in self.population]
        if self.config.maximize:
            min_fit = min(fitnesses)
            adjusted = [f - min_fit + 1 for f in fitnesses]
        else:
            max_fit = max(fitnesses)
            adjusted = [max_fit - f + 1 for f in fitnesses]

        total = sum(adjusted)
        if total == 0:
            return self.population[:self.config.population_size]

        probs = [f / total for f in adjusted]
        new_pop = []
        sorted_pop = sorted(self.population, key=lambda i: i.fitness, reverse=self.config.maximize)
        new_pop.extend(sorted_pop[:self.config.elite_size])

        while len(new_pop) < self.config.population_size:
            idx = self._roulette_wheel(probs)
            new_pop.append(self.population[idx].copy())

        return new_pop

    def _roulette_wheel(self, probs: list[float]) -> int:
        r = random.random()
        cumsum = 0
        for i, p in enumerate(probs):
            cumsum += p
            if r <= cumsum:
                return i
        return len(probs) - 1

    async def _rank_selection(self) -> list[Individual]:
        sorted_pop = sorted(self.population, key=lambda i: i.fitness, reverse=self.config.maximize)
        ranks = list(range(1, len(sorted_pop) + 1))
        total = sum(ranks)
        probs = [r / total for r in ranks]

        new_pop = sorted_pop[:self.config.elite_size]

        while len(new_pop) < self.config.population_size:
            idx = self._roulette_wheel(probs)
            new_pop.append(sorted_pop[idx].copy())

        return new_pop

    async def _truncation_selection(self) -> list[Individual]:
        sorted_pop = sorted(self.population, key=lambda i: i.fitness, reverse=self.config.maximize)
        truncate_size = max(self.config.elite_size, self.config.population_size // 2)
        selected = sorted_pop[:truncate_size]

        new_pop = selected[:self.config.elite_size]

        while len(new_pop) < self.config.population_size:
            parent = random.choice(selected)
            new_pop.append(parent.copy())

        return new_pop

    async def _crossover(self):
        if self.config.strategy != EvolutionStrategy.GENETIC_ALGORITHM:
            return

        new_pop = self.population[:self.config.elite_size]

        while len(new_pop) < self.config.population_size:
            if random.random() < self.config.crossover_rate:
                parent1 = random.choice(self.population)
                parent2 = random.choice(self.population)
                child = self._crossover_genomes(parent1.genome, parent2.genome)
                new_pop.append(Individual(genome=child))
            else:
                parent = random.choice(self.population)
                new_pop.append(parent.copy())

        self.population = new_pop

    def _crossover_genomes(self, genome1: dict, genome2: dict) -> dict:
        child = {}
        all_keys = set(genome1.keys()) | set(genome2.keys())

        for key in all_keys:
            if key in genome1 and key in genome2:
                if random.random() < 0.5:
                    child[key] = genome1[key]
                else:
                    child[key] = genome2[key]
            elif key in genome1:
                child[key] = genome1[key]
            else:
                child[key] = genome2[key]

        return child

    async def _mutation(self):
        for individual in self.population[self.config.elite_size:]:
            await self._mutate_individual(individual)

    async def _mutate_individual(self, individual: Individual):
        for key, value in individual.genome.items():
            if random.random() < self.config.mutation_rate:
                individual.genome[key] = self._mutate_value(value)

    def _mutate_value(self, value: Any) -> Any:
        if isinstance(value, (int, float)):
            if isinstance(value, int):
                return value + random.randint(-10, 10)
            return value + random.gauss(0, abs(value) * 0.1 + 0.01)
        if isinstance(value, str):
            return value + random.choice(['_mut', '_v2', '_opt', ''])
        if isinstance(value, bool):
            return not value
        if isinstance(value, list):
            if value:
                idx = random.randint(0, len(value) - 1)
                value = value.copy()
                value[idx] = self._mutate_value(value[idx])
            return value
        if isinstance(value, dict):
            if value:
                key = random.choice(list(value.keys()))
                value = value.copy()
                value[key] = self._mutate_value(value[key])
            return value
        return value

    def _age_population(self):
        for ind in self.population:
            ind.age += 1


class MultiObjectiveEvolution(EvolutionEngine):
    def __init__(self, config: EvolutionConfig = None, objectives: list[FitnessFunction] = None):
        super().__init__(config)
        self.objectives = objectives or []
        self.pareto_front: list[Individual] = []

    def _update_best(self):
        self._compute_pareto_front()

        if self.pareto_front:
            if self.config.maximize:
                self.best_individual = max(self.pareto_front, key=lambda i: sum(obj.evaluate(i) for obj in self.objectives)).copy()
                self.best_fitness = sum(obj.evaluate(self.best_individual) for obj in self.objectives)
            else:
                self.best_individual = min(self.pareto_front, key=lambda i: sum(obj.evaluate(i) for obj in self.objectives)).copy()
                self.best_fitness = sum(obj.evaluate(self.best_individual) for obj in self.objectives)

            self._stagnation_counter = 0
        else:
            self._stagnation_counter += 1

    def _compute_pareto_front(self):
        self.pareto_front = []

        for ind in self.population:
            dominated = False
            for other in self.population:
                if other is ind:
                    continue
                if self._dominates(other, ind):
                    dominated = True
                    break
            if not dominated:
                self.pareto_front.append(ind)

    def _dominates(self, a: Individual, b: Individual) -> bool:
        a_scores = [obj.evaluate(a) for obj in self.objectives]
        b_scores = [obj.evaluate(b) for obj in self.objectives]

        if self.config.maximize:
            return all(a_s >= b_s for a_s, b_s in zip(a_scores, b_scores)) and any(a_s > b_s for a_s, b_s in zip(a_scores, b_scores))
        return all(a_s <= b_s for a_s, b_s in zip(a_scores, b_scores)) and any(a_s < b_s for a_s, b_s in zip(a_scores, b_scores))


class AdaptiveEvolution(EvolutionEngine):
    def __init__(self, config: EvolutionConfig = None):
        super().__init__(config)
        self.mutation_rate_history: list[float] = []
        self.diversity_history: list[float] = []

    async def _mutation(self):
        diversity = self._compute_diversity()
        self.diversity_history.append(diversity)

        if diversity < self.config.diversity_threshold:
            self.config.mutation_rate = min(0.5, self.config.mutation_rate * 1.2)
        elif diversity > self.config.diversity_threshold * 10:
            self.config.mutation_rate = max(0.01, self.config.mutation_rate * 0.9)

        self.mutation_rate_history.append(self.config.mutation_rate)
        await super()._mutation()

    def _compute_diversity(self) -> float:
        if len(self.population) < 2:
            return 0.0

        total_distance = 0.0
        count = 0

        for i in range(len(self.population)):
            for j in range(i + 1, len(self.population)):
                total_distance += self._genome_distance(self.population[i].genome, self.population[j].genome)
                count += 1

        return total_distance / count if count > 0 else 0.0

    def _genome_distance(self, g1: dict, g2: dict) -> float:
        all_keys = set(g1.keys()) | set(g2.keys())
        if not all_keys:
            return 0.0

        diff = 0
        for key in all_keys:
            v1 = g1.get(key)
            v2 = g2.get(key)
            if v1 != v2:
                diff += 1

        return diff / len(all_keys)
