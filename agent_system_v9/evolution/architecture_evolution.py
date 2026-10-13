"""
Architecture Evolution - Evolutionary architecture optimization
"""
import hashlib
import json
import random
import time
from typing import Dict, List, Optional, Any, Callable, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from collections import defaultdict
from abc import ABC, abstractmethod


class ArchitecturePattern(Enum):
    LAYERED = "layered"
    MICROSERVICES = "microservices"
    EVENT_DRIVEN = "event_driven"
    CQRS = "cqrs"
    HEXAGONAL = "hexagonal"
    CLEAN = "clean"
    MONOLITHIC = "monolithic"
    MODULAR_MONOLITH = "modular_monolith"


class QualityAttribute(Enum):
    PERFORMANCE = "performance"
    SCALABILITY = "scalability"
    MAINTAINABILITY = "maintainability"
    TESTABILITY = "testability"
    DEPLOYABILITY = "deployability"
    SECURITY = "security"
    OBSERVABILITY = "observability"
    RESILIENCE = "resilience"


@dataclass
class ArchitectureDecision:
    decision_id: str
    context: str
    decision: str
    consequences: List[str] = field(default_factory=list)
    quality_impact: Dict[QualityAttribute, float] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    status: str = "proposed"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "context": self.context,
            "decision": self.decision,
            "consequences": self.consequences,
            "quality_impact": {k.value: v for k, v in self.quality_impact.items()},
            "timestamp": self.timestamp,
            "status": self.status,
        }


@dataclass
class ArchitectureIndividual:
    components: Dict[str, Dict] = field(default_factory=dict)
    connections: List[Tuple[str, str, str]] = field(default_factory=list)
    patterns: List[ArchitecturePattern] = field(default_factory=list)
    decisions: List[ArchitectureDecision] = field(default_factory=list)
    fitness: float = 0.0
    quality_scores: Dict[QualityAttribute, float] = field(default_factory=dict)
    id: str = field(default_factory=lambda: hashlib.md5(str(time.time()).encode()).hexdigest()[:12])

    def copy(self) -> 'ArchitectureIndividual':
        return ArchitectureIndividual(
            components={k: v.copy() for k, v in self.components.items()},
            connections=self.connections.copy(),
            patterns=self.patterns.copy(),
            decisions=[d for d in self.decisions],
            fitness=self.fitness,
            quality_scores=self.quality_scores.copy(),
        )


@dataclass
class ArchitectureEvolutionConfig:
    population_size: int = 30
    generations: int = 100
    mutation_rate: float = 0.2
    crossover_rate: float = 0.6
    target_qualities: Dict[QualityAttribute, float] = field(default_factory=dict)
    constraints: List[Callable] = field(default_factory=list)
    available_patterns: List[ArchitecturePattern] = field(default_factory=lambda: list(ArchitecturePattern))


class ArchitectureFitnessFunction:
    def __init__(self, config: ArchitectureEvolutionConfig):
        self.config = config
        self.weights = config.target_qualities or {q: 1.0 for q in QualityAttribute}

    def evaluate(self, individual: ArchitectureIndividual) -> float:
        total_fitness = 0.0
        
        for quality, target in self.weights.items():
            actual = individual.quality_scores.get(quality, 0.0)
            diff = abs(actual - target)
            total_fitness += (1.0 / (1.0 + diff)) * target
        
        penalty = 0.0
        for constraint in self.config.constraints:
            if not constraint(individual):
                penalty += 10.0
        
        return total_fitness - penalty


class ArchitectureEvolutionEngine:
    def __init__(self, config: ArchitectureEvolutionConfig):
        self.config = config
        self.fitness_fn = ArchitectureFitnessFunction(config)
        self.population: List[ArchitectureIndividual] = []
        self.generation = 0
        self.best_individual: Optional[ArchitectureIndividual] = None
        self.best_fitness = float('-inf')
        self.history: List[Dict] = []

    def initialize_population(self, generator: Callable[[], ArchitectureIndividual]):
        self.population = []
        for _ in range(self.config.population_size):
            individual = generator()
            self._compute_quality_scores(individual)
            self.population.append(individual)
        self.generation = 0
        self.best_individual = None
        self.best_fitness = float('-inf')

    def _compute_quality_scores(self, individual: ArchitectureIndividual):
        scores = {}
        
        num_components = len(individual.components)
        num_connections = len(individual.connections)
        coupling = num_connections / max(num_components, 1)
        
        scores[QualityAttribute.MAINTAINABILITY] = 1.0 / (1.0 + coupling * 2)
        scores[QualityAttribute.TESTABILITY] = 1.0 / (1.0 + coupling * 1.5)
        scores[QualityAttribute.DEPLOYABILITY] = 1.0 / (1.0 + num_components * 0.1)
        
        pattern_bonus = {
            ArchitecturePattern.MICROSERVICES: {QualityAttribute.SCALABILITY: 0.3, QualityAttribute.DEPLOYABILITY: 0.2},
            ArchitecturePattern.EVENT_DRIVEN: {QualityAttribute.SCALABILITY: 0.2, QualityAttribute.RESILIENCE: 0.3},
            ArchitecturePattern.CQRS: {QualityAttribute.PERFORMANCE: 0.2, QualityAttribute.SCALABILITY: 0.2},
            ArchitecturePattern.HEXAGONAL: {QualityAttribute.MAINTAINABILITY: 0.2, QualityAttribute.TESTABILITY: 0.3},
            ArchitecturePattern.CLEAN: {QualityAttribute.MAINTAINABILITY: 0.3, QualityAttribute.TESTABILITY: 0.2},
            ArchitecturePattern.MODULAR_MONOLITH: {QualityAttribute.MAINTAINABILITY: 0.2, QualityAttribute.DEPLOYABILITY: 0.3},
        }
        
        for pattern in individual.patterns:
            if pattern in pattern_bonus:
                for quality, bonus in pattern_bonus[pattern].items():
                    scores[quality] = min(1.0, scores.get(quality, 0) + bonus)
        
        scores[QualityAttribute.PERFORMANCE] = scores.get(QualityAttribute.PERFORMANCE, 0.5)
        scores[QualityAttribute.SECURITY] = scores.get(QualityAttribute.SECURITY, 0.5)
        scores[QualityAttribute.OBSERVABILITY] = scores.get(QualityAttribute.OBSERVABILITY, 0.5)
        scores[QualityAttribute.RESILIENCE] = scores.get(QualityAttribute.RESILIENCE, 0.5)
        
        individual.quality_scores = scores

    async def evolve(self) -> ArchitectureIndividual:
        for gen in range(self.config.generations):
            self.generation = gen
            
            await self._evaluate_population()
            self._update_best()
            self._record_history()
            
            if self._check_convergence():
                break
            
            await self._selection()
            await self._crossover()
            await self._mutation()
        
        return self.best_individual

    async def _evaluate_population(self):
        for individual in self.population:
            individual.fitness = self.fitness_fn.evaluate(individual)

    def _update_best(self):
        best = max(self.population, key=lambda i: i.fitness)
        if best.fitness > self.best_fitness:
            self.best_individual = best.copy()
            self.best_fitness = best.fitness

    def _record_history(self):
        avg_fitness = sum(i.fitness for i in self.population) / len(self.population)
        self.history.append({
            "generation": self.generation,
            "best_fitness": self.best_fitness,
            "avg_fitness": avg_fitness,
            "best_quality": self.best_individual.quality_scores if self.best_individual else {},
        })

    def _check_convergence(self) -> bool:
        if len(self.history) < 10:
            return False
        
        recent_best = [h["best_fitness"] for h in self.history[-10:]]
        improvement = max(recent_best) - min(recent_best)
        return improvement < 0.01

    async def _selection(self):
        sorted_pop = sorted(self.population, key=lambda i: i.fitness, reverse=True)
        elite_size = max(1, self.config.population_size // 10)
        
        new_pop = sorted_pop[:elite_size]
        
        while len(new_pop) < self.config.population_size:
            parent = self._tournament_select()
            new_pop.append(parent.copy())
        
        self.population = new_pop

    def _tournament_select(self, k: int = 3) -> ArchitectureIndividual:
        tournament = random.sample(self.population, min(k, len(self.population)))
        return max(tournament, key=lambda i: i.fitness)

    async def _crossover(self):
        new_pop = self.population[:max(1, self.config.population_size // 10)]
        
        while len(new_pop) < self.config.population_size:
            parent1 = self._tournament_select()
            parent2 = self._tournament_select()
            
            if random.random() < self.config.crossover_rate:
                child = self._crossover_architectures(parent1, parent2)
            else:
                child = parent1.copy()
            
            new_pop.append(child)
        
        self.population = new_pop

    def _crossover_architectures(self, parent1: ArchitectureIndividual, parent2: ArchitectureIndividual) -> ArchitectureIndividual:
        child = ArchitectureIndividual()
        
        all_components = set(parent1.components.keys()) | set(parent2.components.keys())
        for comp in all_components:
            if comp in parent1.components and comp in parent2.components:
                child.components[comp] = random.choice([parent1.components[comp], parent2.components[comp]])
            elif comp in parent1.components:
                child.components[comp] = parent1.components[comp]
            else:
                child.components[comp] = parent2.components[comp]
        
        all_connections = set(parent1.connections) | set(parent2.connections)
        child.connections = list(all_connections)
        
        child.patterns = list(set(parent1.patterns) | set(parent2.patterns))
        
        self._compute_quality_scores(child)
        
        return child

    async def _mutation(self):
        for individual in self.population[max(1, self.config.population_size // 10):]:
            if random.random() < self.config.mutation_rate:
                await self._mutate_architecture(individual)

    async def _mutate_architecture(self, individual: ArchitectureIndividual):
        mutation_type = random.choice([
            "add_component", "remove_component", "modify_component",
            "add_connection", "remove_connection", "change_pattern",
            "add_decision",
        ])
        
        if mutation_type == "add_component":
            comp_name = f"Component_{len(individual.components) + 1}"
            individual.components[comp_name] = {
                "type": random.choice(["service", "repository", "handler", "controller"]),
                "responsibilities": [],
            }
        elif mutation_type == "remove_component" and individual.components:
            comp = random.choice(list(individual.components.keys()))
            del individual.components[comp]
            individual.connections = [c for c in individual.connections if comp not in c[:2]]
        elif mutation_type == "modify_component" and individual.components:
            comp = random.choice(list(individual.components.keys()))
            individual.components[comp]["type"] = random.choice(["service", "repository", "handler", "controller"])
        elif mutation_type == "add_connection" and len(individual.components) >= 2:
            comps = list(individual.components.keys())
            src = random.choice(comps)
            dst = random.choice([c for c in comps if c != src])
            conn_type = random.choice(["sync", "async", "event"])
            individual.connections.append((src, dst, conn_type))
        elif mutation_type == "remove_connection" and individual.connections:
            individual.connections.pop(random.randint(0, len(individual.connections) - 1))
        elif mutation_type == "change_pattern":
            if individual.patterns:
                individual.patterns[random.randint(0, len(individual.patterns) - 1)] = random.choice(self.config.available_patterns)
            else:
                individual.patterns.append(random.choice(self.config.available_patterns))
        elif mutation_type == "add_decision":
            decision = ArchitectureDecision(
                decision_id=hashlib.md5(f"decision_{time.time()}".encode()).hexdigest()[:8],
                context="Evolved architecture decision",
                decision=f"Applied {mutation_type}",
                consequences=["Improved modularity"],
            )
            individual.decisions.append(decision)
        
        self._compute_quality_scores(individual)
        individual.fitness = 0


class ArchitectureOptimizer:
    def __init__(self, engine: ArchitectureEvolutionEngine):
        self.engine = engine

    def generate_initial_architecture(self, requirements: Dict[str, Any]) -> ArchitectureIndividual:
        individual = ArchitectureIndividual()
        
        for comp_name, comp_spec in requirements.get("components", {}).items():
            individual.components[comp_name] = comp_spec
        
        for conn in requirements.get("connections", []):
            individual.connections.append(tuple(conn))
        
        for pattern in requirements.get("patterns", []):
            if isinstance(pattern, str):
                individual.patterns.append(ArchitecturePattern(pattern))
            else:
                individual.patterns.append(pattern)
        
        self.engine._compute_quality_scores(individual)
        return individual

    async def optimize(self, requirements: Dict[str, Any]) -> ArchitectureIndividual:
        initial = self.generate_initial_architecture(requirements)
        
        def generator():
            return initial.copy()
        
        self.engine.initialize_population(generator)
        return await self.engine.evolve()

    def export_architecture(self, individual: ArchitectureIndividual, format: str = "json") -> str:
        if format == "json":
            return json.dumps({
                "components": individual.components,
                "connections": individual.connections,
                "patterns": [p.value for p in individual.patterns],
                "decisions": [d.to_dict() for d in individual.decisions],
                "quality_scores": {k.value: v for k, v in individual.quality_scores.items()},
                "fitness": individual.fitness,
            }, indent=2)
        elif format == "mermaid":
            return self._to_mermaid(individual)
        return ""

    def _to_mermaid(self, individual: ArchitectureIndividual) -> str:
        lines = ["graph TD"]
        
        for comp_name, comp_info in individual.components.items():
            lines.append(f"    {comp_name}[{comp_name}: {comp_info.get('type', '')}]")
        
        for src, dst, conn_type in individual.connections:
            arrow = "-->" if conn_type == "sync" else "-.->" if conn_type == "async" else "==>"
            lines.append(f"    {src} {arrow} {dst}")
        
        return "\n".join(lines)


class EvolutionaryArchitectureReviewer:
    def __init__(self):
        self.patterns_knowledge: Dict[ArchitecturePattern, Dict] = self._load_patterns_knowledge()

    def _load_patterns_knowledge(self) -> Dict[ArchitecturePattern, Dict]:
        return {
            ArchitecturePattern.LAYERED: {
                "pros": ["Simple", "Clear separation", "Easy to understand"],
                "cons": ["Performance overhead", "Rigid", "Cascading changes"],
                "best_for": ["Simple applications", "Small teams"],
            },
            ArchitecturePattern.MICROSERVICES: {
                "pros": ["Independent deployment", "Technology diversity", "Scalability"],
                "cons": ["Complexity", "Network latency", "Distributed transactions"],
                "best_for": ["Large systems", "Multiple teams", "High scalability needs"],
            },
            ArchitecturePattern.EVENT_DRIVEN: {
                "pros": ["Loose coupling", "Scalability", "Resilience"],
                "cons": ["Eventual consistency", "Debugging complexity", "Event ordering"],
                "best_for": ["Real-time systems", "High throughput", "Integration"],
            },
            ArchitecturePattern.HEXAGONAL: {
                "pros": ["Testability", "Framework independence", "Clear boundaries"],
                "cons": ["Complexity", "Learning curve", "Over-engineering risk"],
                "best_for": ["Complex domains", "Long-lived systems", "High testability needs"],
            },
        }

    def review(self, individual: ArchitectureIndividual) -> Dict[str, Any]:
        issues = []
        suggestions = []
        
        for pattern in individual.patterns:
            if pattern in self.patterns_knowledge:
                knowledge = self.patterns_knowledge[pattern]
                
                for con in knowledge["cons"]:
                    issues.append(f"{pattern.value}: {con}")
        
        coupling = len(individual.connections) / max(len(individual.components), 1)
        if coupling > 0.5:
            issues.append(f"High coupling: {coupling:.2f} connections per component")
            suggestions.append("Consider event-driven or mediator pattern to reduce coupling")
        
        if not individual.patterns:
            issues.append("No explicit architecture pattern defined")
            suggestions.append("Consider adopting a recognized architecture pattern")
        
        quality_scores = individual.quality_scores
        for quality, score in quality_scores.items():
            if score < 0.4:
                issues.append(f"Low {quality.value}: {score:.2f}")
        
        return {
            "issues": issues,
            "suggestions": suggestions,
            "quality_assessment": {k.value: v for k, v in quality_scores.items()},
            "overall_score": sum(quality_scores.values()) / len(quality_scores) if quality_scores else 0,
        }