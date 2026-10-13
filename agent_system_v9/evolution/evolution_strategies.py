"""
Evolution Strategies - Advanced evolutionary algorithms and strategies
"""
import hashlib
import random
import time
import math
from typing import Dict, List, Optional, Any, Callable, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from abc import ABC, abstractmethod


class StrategyType(Enum):
    CMA_ES = "cma_es"
    XNES = "xnes"
    SEP_CMA_ES = "sep_cma_es"
    BIPOP_CMA_ES = "bipop_cma_es"
    IPOP_CMA_ES = "ipop_cma_es"
    LM_CMA_ES = "lm_cma_es"
    VD_CMA_ES = "vd_cma_es"
    PSO = "pso"
    DE = "differential_evolution"
    ES_PLUS = "es_plus"
    ES_COMMA = "es_comma"


@dataclass
class StrategyConfig:
    population_size: int = 50
    dimension: int = 10
    sigma: float = 1.0
    max_iterations: int = 1000
    target_fitness: float = 1e-10
    restart_strategy: str = "ipop"
    seed: int = None


@dataclass
class StrategyResult:
    best_solution: List[float]
    best_fitness: float
    iterations: int
    function_evaluations: int
    converged: bool
    restart_count: int
    history: List[Dict] = field(default_factory=list)


class EvolutionStrategy(ABC):
    def __init__(self, config: StrategyConfig):
        self.config = config
        self.dimension = config.dimension
        self.population_size = config.population_size
        self.sigma = config.sigma
        self.max_iterations = config.max_iterations
        self.target_fitness = config.target_fitness
        
        self.mean = [0.0] * self.dimension
        self.covariance = [[1.0 if i == j else 0.0 for j in range(self.dimension)] for i in range(self.dimension)]
        self.eigenvalues = [1.0] * self.dimension
        self.eigenvectors = [[1.0 if i == j else 0.0 for j in range(self.dimension)] for i in range(self.dimension)]
        
        self.iteration = 0
        self.function_evaluations = 0
        self.best_solution = None
        self.best_fitness = float('inf')
        self.history = []
        
        if config.seed is not None:
            random.seed(config.seed)

    @abstractmethod
    def ask(self) -> List[List[float]]:
        pass

    @abstractmethod
    def tell(self, solutions: List[List[float]], fitnesses: List[float]):
        pass

    def optimize(self, objective: Callable[[List[float]], float]) -> StrategyResult:
        while self.iteration < self.max_iterations and self.best_fitness > self.target_fitness:
            solutions = self.ask()
            fitnesses = []
            
            for sol in solutions:
                fitness = objective(sol)
                fitnesses.append(fitness)
                self.function_evaluations += 1
                
                if fitness < self.best_fitness:
                    self.best_fitness = fitness
                    self.best_solution = sol[:]
            
            self.tell(solutions, fitnesses)
            self.iteration += 1
            
            self.history.append({
                "iteration": self.iteration,
                "best_fitness": self.best_fitness,
                "sigma": self.sigma,
            })
        
        return StrategyResult(
            best_solution=self.best_solution,
            best_fitness=self.best_fitness,
            iterations=self.iteration,
            function_evaluations=self.function_evaluations,
            converged=self.best_fitness <= self.target_fitness,
            restart_count=0,
            history=self.history,
        )


class CMAES(EvolutionStrategy):
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.weights = self._compute_weights()
        self.mueff = self._compute_mueff()
        self.cc = (4 + self.mueff / self.dimension) / (self.dimension + 4 + 2 * self.mueff / self.dimension)
        self.cs = (self.mueff + 2) / (self.dimension + self.mueff + 5)
        self.c1 = 2 / ((self.dimension + 1.3) ** 2 + self.mueff)
        self.cmu = min(1 - self.c1, 2 * (self.mueff - 2 + 1 / self.mueff) / ((self.dimension + 2) ** 2 + self.mueff))
        self.damps = 1 + 2 * max(0, math.sqrt((self.mueff - 1) / (self.dimension + 1)) - 1) + self.cs
        
        self.pc = [0.0] * self.dimension
        self.ps = [0.0] * self.dimension
        
        self._decompose_covariance()

    def _compute_weights(self) -> List[float]:
        mu = self.population_size // 2
        weights = [math.log(mu + 0.5) - math.log(i + 1) for i in range(mu)]
        total = sum(weights)
        return [w / total for w in weights]

    def _compute_mueff(self) -> float:
        weights = self._compute_weights()
        return 1.0 / sum(w * w for w in weights)

    def _decompose_covariance(self):
        self.eigenvalues = [1.0] * self.dimension
        self.eigenvectors = [[1.0 if i == j else 0.0 for j in range(self.dimension)] for i in range(self.dimension)]

    def ask(self) -> List[List[float]]:
        solutions = []
        for _ in range(self.population_size):
            z = [random.gauss(0, 1) for _ in range(self.dimension)]
            y = self._multiply_matrix_vector(self.eigenvectors, z)
            y = [y[i] * math.sqrt(self.eigenvalues[i]) for i in range(self.dimension)]
            x = [self.mean[i] + self.sigma * y[i] for i in range(self.dimension)]
            solutions.append(x)
        return solutions

    def tell(self, solutions: List[List[float]], fitnesses: List[float]):
        sorted_indices = sorted(range(len(fitnesses)), key=lambda i: fitnesses[i])
        mu = len(self.weights)
        
        old_mean = self.mean[:]
        self.mean = [0.0] * self.dimension
        for i in range(mu):
            idx = sorted_indices[i]
            w = self.weights[i]
            for j in range(self.dimension):
                self.mean[j] += w * solutions[idx][j]
        
        y_w = [(self.mean[j] - old_mean[j]) / self.sigma for j in range(self.dimension)]
        
        self.ps = [(1 - self.cs) * self.ps[j] + math.sqrt(self.cs * (2 - self.cs) * self.mueff) * y_w[j] for j in range(self.dimension)]
        
        hsig = 1.0 if sum(ps * ps for ps in self.ps) / (1 - (1 - self.cs) ** (2 * self.iteration / self.max_iterations)) < 2 + 4 / (self.dimension + 1) else 0.0
        
        self.pc = [(1 - self.cc) * self.pc[j] + hsig * math.sqrt(self.cc * (2 - self.cc) * self.mueff) * y_w[j] for j in range(self.dimension)]
        
        rank_one = [[self.pc[i] * self.pc[j] for j in range(self.dimension)] for i in range(self.dimension)]
        
        rank_mu = [[0.0 for _ in range(self.dimension)] for _ in range(self.dimension)]
        for i in range(mu):
            idx = sorted_indices[i]
            w = self.weights[i]
            y = [(solutions[idx][j] - old_mean[j]) / self.sigma for j in range(self.dimension)]
            for j1 in range(self.dimension):
                for j2 in range(self.dimension):
                    rank_mu[j1][j2] += w * y[j1] * y[j2]
        
        self.covariance = [[
            (1 - self.c1 - self.cmu) * self.covariance[i][j] + self.c1 * rank_one[i][j] + self.cmu * rank_mu[i][j]
            for j in range(self.dimension)
        ] for i in range(self.dimension)]
        
        self.sigma *= math.exp((self.cs / self.damps) * (math.sqrt(sum(ps * ps for ps in self.ps)) / self._chi_n() - 1))
        
        self._decompose_covariance()

    def _multiply_matrix_vector(self, matrix: List[List[float]], vector: List[float]) -> List[float]:
        return [sum(matrix[i][j] * vector[j] for j in range(self.dimension)) for i in range(self.dimension)]

    def _chi_n(self) -> float:
        return math.sqrt(self.dimension) * (1 - 1 / (4 * self.dimension) + 1 / (21 * self.dimension ** 2))


class ParticleSwarmOptimization(EvolutionStrategy):
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.w = 0.729
        self.c1 = 1.49445
        self.c2 = 1.49445
        
        self.particles = []
        self.velocities = []
        self.personal_best = []
        self.personal_best_fitness = []
        self.global_best = None
        self.global_best_fitness = float('inf')
        
        self._initialize_swarm()

    def _initialize_swarm(self):
        for _ in range(self.population_size):
            position = [random.uniform(-5, 5) for _ in range(self.dimension)]
            velocity = [random.uniform(-1, 1) for _ in range(self.dimension)]
            
            self.particles.append(position)
            self.velocities.append(velocity)
            self.personal_best.append(position[:])
            self.personal_best_fitness.append(float('inf'))

    def ask(self) -> List[List[float]]:
        return [p[:] for p in self.particles]

    def tell(self, solutions: List[List[float]], fitnesses: List[float]):
        for i, (pos, fit) in enumerate(zip(solutions, fitnesses)):
            if fit < self.personal_best_fitness[i]:
                self.personal_best_fitness[i] = fit
                self.personal_best[i] = pos[:]
            
            if fit < self.global_best_fitness:
                self.global_best_fitness = fit
                self.global_best = pos[:]
        
        for i in range(self.population_size):
            for d in range(self.dimension):
                r1 = random.random()
                r2 = random.random()
                
                self.velocities[i][d] = (
                    self.w * self.velocities[i][d] +
                    self.c1 * r1 * (self.personal_best[i][d] - self.particles[i][d]) +
                    self.c2 * r2 * (self.global_best[d] - self.particles[i][d])
                )
                
                self.particles[i][d] += self.velocities[i][d]


class DifferentialEvolution(EvolutionStrategy):
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.F = 0.8
        self.CR = 0.9
        
        self.population = []
        self._initialize_population()

    def _initialize_population(self):
        for _ in range(self.population_size):
            individual = [random.uniform(-5, 5) for _ in range(self.dimension)]
            self.population.append(individual)

    def ask(self) -> List[List[float]]:
        return [p[:] for p in self.population]

    def tell(self, solutions: List[List[float]], fitnesses: List[float]):
        new_population = []
        
        for i in range(self.population_size):
            idxs = [idx for idx in range(self.population_size) if idx != i]
            a, b, c = random.sample(idxs, 3)
            
            mutant = [
                self.population[a][d] + self.F * (self.population[b][d] - self.population[c][d])
                for d in range(self.dimension)
            ]
            
            trial = []
            for d in range(self.dimension):
                if random.random() < self.CR or d == random.randint(0, self.dimension - 1):
                    trial.append(mutant[d])
                else:
                    trial.append(self.population[i][d])
            
            new_population.append(trial)
        
        self.population = new_population


class EvolutionStrategyPlus(EvolutionStrategy):
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.lambda_ = config.population_size
        self.mu = config.population_size // 2
        
        self.population = []
        self._initialize_population()

    def _initialize_population(self):
        for _ in range(self.lambda_):
            individual = [random.uniform(-5, 5) for _ in range(self.dimension)]
            sigma = self.sigma
            self.population.append((individual, sigma))

    def ask(self) -> List[List[float]]:
        return [ind[0][:] for ind in self.population]

    def tell(self, solutions: List[List[float]], fitnesses: List[float]):
        combined = list(zip(solutions, fitnesses))
        combined.sort(key=lambda x: x[1])
        
        self.population = combined[:self.mu]
        
        while len(self.population) < self.lambda_:
            parent = random.choice(self.population[:self.mu])
            child = self._mutate(parent[0], parent[1])
            self.population.append((child, parent[1]))

    def _mutate(self, parent: List[float], sigma: float) -> List[float]:
        return [parent[d] + random.gauss(0, sigma) for d in range(self.dimension)]


class EvolutionStrategyComma(EvolutionStrategyPlus):
    def tell(self, solutions: List[List[float]], fitnesses: List[float]):
        combined = list(zip(solutions, fitnesses))
        combined.sort(key=lambda x: x[1])
        
        self.population = combined[:self.mu]
        
        while len(self.population) < self.lambda_:
            parent = random.choice(self.population[:self.mu])
            child = self._mutate(parent[0], parent[1])
            self.population.append((child, parent[1]))


class StrategySelector:
    def __init__(self):
        self.strategies = {
            StrategyType.CMA_ES: CMAES,
            StrategyType.PSO: ParticleSwarmOptimization,
            StrategyType.DE: DifferentialEvolution,
            StrategyType.ES_PLUS: EvolutionStrategyPlus,
            StrategyType.ES_COMMA: EvolutionStrategyComma,
        }

    def select(self, problem_type: str, dimension: int) -> StrategyType:
        if dimension > 100:
            return StrategyType.SEP_CMA_ES
        elif problem_type == "multimodal":
            return StrategyType.CMA_ES
        elif problem_type == "noisy":
            return StrategyType.PSO
        elif problem_type == "constrained":
            return StrategyType.DE
        return StrategyType.CMA_ES

    def create_strategy(self, strategy_type: StrategyType, config: StrategyConfig) -> EvolutionStrategy:
        if strategy_type in self.strategies:
            return self.strategies[strategy_type](config)
        return CMAES(config)


class AdaptiveStrategySelector(StrategySelector):
    def __init__(self):
        super().__init__()
        self.performance_history: Dict[StrategyType, List[float]] = defaultdict(list)

    def record_performance(self, strategy_type: StrategyType, fitness: float):
        self.performance_history[strategy_type].append(fitness)

    def select(self, problem_type: str, dimension: int) -> StrategyType:
        if len(self.performance_history) < 3:
            return super().select(problem_type, dimension)
        
        avg_performance = {}
        for stype, history in self.performance_history.items():
            if history:
                avg_performance[stype] = sum(history) / len(history)
        
        if avg_performance:
            return min(avg_performance, key=avg_performance.get)
        
        return super().select(problem_type, dimension)


class PortfolioOptimizer:
    def __init__(self, strategies: List[EvolutionStrategy]):
        self.strategies = strategies
        self.allocations = [1.0 / len(strategies)] * len(strategies)

    def run(self, objective: Callable[[List[float]], float], budget: int) -> StrategyResult:
        evaluations_per_strategy = budget // len(self.strategies)
        
        best_result = None
        best_fitness = float('inf')
        
        for i, strategy in enumerate(self.strategies):
            result = strategy.optimize(objective)
            
            if result.best_fitness < best_fitness:
                best_fitness = result.best_fitness
                best_result = result
        
        return best_result

    def update_allocations(self, performances: List[float]):
        total = sum(1.0 / (p + 1e-10) for p in performances)
        self.allocations = [(1.0 / (p + 1e-10)) / total for p in performances]