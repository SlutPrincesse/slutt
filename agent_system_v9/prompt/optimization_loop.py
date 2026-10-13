"""
Reinforcement Optimization Loop - Evaluates output quality against scores to auto-refine prompt templates
"""
import json
import threading
import time
import uuid
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import hashlib


class OptimizationStrategy(Enum):
    GRADIENT = "gradient"
    EVOLUTIONARY = "evolutionary"
    BAYESIAN = "bayesian"
    BANDIT = "bandit"


@dataclass
class PromptTemplate:
    template_id: str
    name: str
    content: str
    variables: List[str] = field(default_factory=list)
    version: int = 1
    parent_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class EvaluationResult:
    evaluation_id: str
    template_id: str
    input_data: Dict[str, Any]
    output: str
    score: float
    metrics: Dict[str, float] = field(default_factory=dict)
    feedback: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class OptimizationResult:
    optimization_id: str
    template_id: str
    strategy: OptimizationStrategy
    iterations: int
    best_score: float
    initial_score: float
    improved_template: PromptTemplate
    history: List[EvaluationResult] = field(default_factory=list)
    converged: bool = False
    duration: float = 0.0


class ReinforcementOptimizationLoop:
    def __init__(self, max_iterations: int = 10, convergence_threshold: float = 0.01,
                 strategy: OptimizationStrategy = OptimizationStrategy.EVOLUTIONARY):
        self.max_iterations = max_iterations
        self.convergence_threshold = convergence_threshold
        self.strategy = strategy
        
        self._templates: Dict[str, PromptTemplate] = {}
        self._evaluations: Dict[str, List[EvaluationResult]] = defaultdict(list)
        self._optimization_history: List[OptimizationResult] = []
        self._lock = threading.RLock()
        self._evaluator: Optional[Callable] = None
        self._mutator: Optional[Callable] = None
    
    def set_evaluator(self, evaluator: Callable[[str, Dict[str, Any]], Tuple[float, Dict[str, float], str]]):
        """Set custom evaluator function: (output, input_data) -> (score, metrics, feedback)"""
        self._evaluator = evaluator
    
    def set_mutator(self, mutator: Callable[[PromptTemplate, EvaluationResult], PromptTemplate]):
        """Set custom mutator function: (template, evaluation) -> new_template"""
        self._mutator = mutator
    
    def register_template(self, template: PromptTemplate) -> str:
        with self._lock:
            self._templates[template.template_id] = template
        return template.template_id
    
    def create_template(self, name: str, content: str, variables: List[str] = None,
                        metadata: Dict[str, Any] = None) -> PromptTemplate:
        template_id = hashlib.sha256(f"{name}{content}{time.time()}".encode()).hexdigest()[:12]
        template = PromptTemplate(
            template_id=template_id,
            name=name,
            content=content,
            variables=variables or [],
            metadata=metadata or {}
        )
        return self.register_template(template)
    
    def optimize(self, template_id: str, test_cases: List[Dict[str, Any]],
                 strategy: Optional[OptimizationStrategy] = None) -> OptimizationResult:
        start_time = time.time()
        strategy = strategy or self.strategy
        
        with self._lock:
            template = self._templates.get(template_id)
            if not template:
                raise ValueError(f"Template {template_id} not found")
        
        if not self._evaluator:
            raise RuntimeError("No evaluator set. Call set_evaluator() first.")
        
        # Initial evaluation
        initial_scores = []
        for test_case in test_cases:
            output = self._render_template(template, test_case)
            score, metrics, feedback = self._evaluator(output, test_case)
            initial_scores.append(score)
            
            eval_result = EvaluationResult(
                evaluation_id=str(uuid.uuid4())[:8],
                template_id=template_id,
                input_data=test_case,
                output=output,
                score=score,
                metrics=metrics,
                feedback=feedback
            )
            with self._lock:
                self._evaluations[template_id].append(eval_result)
        
        initial_avg = sum(initial_scores) / len(initial_scores) if initial_scores else 0.0
        best_score = initial_avg
        best_template = template
        history = []
        
        for iteration in range(self.max_iterations):
            # Generate candidate templates
            candidates = self._generate_candidates(best_template, history[-5:] if history else [])
            
            iteration_best_score = best_score
            iteration_best_template = best_template
            
            for candidate in candidates:
                scores = []
                for test_case in test_cases:
                    output = self._render_template(candidate, test_case)
                    score, metrics, feedback = self._evaluator(output, test_case)
                    scores.append(score)
                    
                    eval_result = EvaluationResult(
                        evaluation_id=str(uuid.uuid4())[:8],
                        template_id=candidate.template_id,
                        input_data=test_case,
                        output=output,
                        score=score,
                        metrics=metrics,
                        feedback=feedback
                    )
                    history.append(eval_result)
                    with self._lock:
                        self._evaluations[candidate.template_id].append(eval_result)
                
                avg_score = sum(scores) / len(scores) if scores else 0.0
                if avg_score > iteration_best_score:
                    iteration_best_score = avg_score
                    iteration_best_template = candidate
            
            # Check convergence
            improvement = iteration_best_score - best_score
            if improvement < self.convergence_threshold:
                break
            
            best_score = iteration_best_score
            best_template = iteration_best_template
        
        duration = time.time() - start_time
        
        result = OptimizationResult(
            optimization_id=str(uuid.uuid4())[:8],
            template_id=template_id,
            strategy=strategy,
            iterations=iteration + 1,
            best_score=best_score,
            initial_score=initial_avg,
            improved_template=best_template,
            history=history,
            converged=improvement < self.convergence_threshold,
            duration=duration
        )
        
        with self._lock:
            self._optimization_history.append(result)
            # Update the original template with improvements
            if best_template.template_id != template_id:
                best_template.parent_id = template_id
                self._templates[best_template.template_id] = best_template
        
        return result
    
    def _render_template(self, template: PromptTemplate, variables: Dict[str, Any]) -> str:
        content = template.content
        for var in template.variables:
            placeholder = f"{{{var}}}"
            value = variables.get(var, "")
            content = content.replace(placeholder, str(value))
        return content
    
    def _generate_candidates(self, base_template: PromptTemplate, 
                            recent_history: List[EvaluationResult]) -> List[PromptTemplate]:
        candidates = []
        
        if self._mutator:
            for eval_result in recent_history:
                try:
                    candidate = self._mutator(base_template, eval_result)
                    candidates.append(candidate)
                except Exception:
                    pass
        else:
            # Default mutation strategies
            candidates.extend(self._mutate_temperature(base_template))
            candidates.extend(self._mutate_structure(base_template))
            candidates.extend(self._mutate_instructions(base_template))
        
        return candidates[:5]  # Limit candidates per iteration
    
    def _mutate_temperature(self, template: PromptTemplate) -> List[PromptTemplate]:
        # Add temperature/creativity instructions
        mutations = []
        temps = ["low", "medium", "high"]
        for temp in temps:
            new_content = f"{template.content}\n\n[Temperature: {temp}]"
            mut = PromptTemplate(
                template_id=f"{template.template_id}_temp_{temp}",
                name=f"{template.name} (temp={temp})",
                content=new_content,
                variables=template.variables.copy(),
                version=template.version + 1,
                parent_id=template.template_id
            )
            mutations.append(mut)
        return mutations
    
    def _mutate_structure(self, template: PromptTemplate) -> List[PromptTemplate]:
        mutations = []
        
        # Add chain-of-thought
        cot_content = f"{template.content}\n\nThink step by step before answering."
        mut = PromptTemplate(
            template_id=f"{template.template_id}_cot",
            name=f"{template.name} (CoT)",
            content=cot_content,
            variables=template.variables.copy(),
            version=template.version + 1,
            parent_id=template.template_id
        )
        mutations.append(mut)
        
        # Add few-shot placeholder
        fs_content = f"{template.content}\n\nExamples:\n{{examples}}"
        mut = PromptTemplate(
            template_id=f"{template.template_id}_fewshot",
            name=f"{template.name} (few-shot)",
            content=fs_content,
            variables=template.variables + ["examples"],
            version=template.version + 1,
            parent_id=template.template_id
        )
        mutations.append(mut)
        
        return mutations
    
    def _mutate_instructions(self, template: PromptTemplate) -> List[PromptTemplate]:
        mutations = []
        
        instruction_variants = [
            "Be concise and precise.",
            "Provide detailed reasoning.",
            "Focus on practical implementation.",
            "Consider edge cases and error handling.",
            "Use best practices and design patterns.",
        ]
        
        for instr in instruction_variants:
            new_content = f"{template.content}\n\n{instr}"
            mut = PromptTemplate(
                template_id=f"{template.template_id}_instr_{hash(instr) % 1000}",
                name=f"{template.name} (+{instr[:20]})",
                content=new_content,
                variables=template.variables.copy(),
                version=template.version + 1,
                parent_id=template.template_id
            )
            mutations.append(mut)
        
        return mutations
    
    def get_template(self, template_id: str) -> Optional[PromptTemplate]:
        with self._lock:
            return self._templates.get(template_id)
    
    def get_evaluations(self, template_id: str) -> List[EvaluationResult]:
        with self._lock:
            return list(self._evaluations.get(template_id, []))
    
    def get_optimization_history(self, limit: int = 10) -> List[OptimizationResult]:
        with self._lock:
            return self._optimization_history[-limit:]
    
    def get_best_template(self, template_id: str) -> Optional[PromptTemplate]:
        with self._lock:
            template = self._templates.get(template_id)
            if not template:
                return None
            
            # Find best child
            best = template
            best_score = -1.0
            
            for t in self._templates.values():
                if t.parent_id == template_id or t.template_id == template_id:
                    evals = self._evaluations.get(t.template_id, [])
                    if evals:
                        avg_score = sum(e.score for e in evals) / len(evals)
                        if avg_score > best_score:
                            best_score = avg_score
                            best = t
            
            return best


_optimization_loop: Optional[ReinforcementOptimizationLoop] = None

def get_optimization_loop() -> ReinforcementOptimizationLoop:
    global _optimization_loop
    if _optimization_loop is None:
        _optimization_loop = ReinforcementOptimizationLoop()
    return _optimization_loop