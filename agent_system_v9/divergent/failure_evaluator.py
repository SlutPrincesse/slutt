"""
Sub-1B Failure-Trace ICRL Evaluator - Lightweight model adjusting ICRL reward weights from error traces
"""
import hashlib
import json
import pathlib
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ICRLWeights:
    correctness: float = 0.4
    performance: float = 0.2
    memory: float = 0.2
    anti_slop: float = 0.2

    def to_dict(self) -> dict[str, float]:
        return {
            "correctness": self.correctness,
            "performance": self.performance,
            "memory": self.memory,
            "anti_slop": self.anti_slop
        }

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> 'ICRLWeights':
        return cls(
            correctness=data.get("correctness", 0.4),
            performance=data.get("performance", 0.2),
            memory=data.get("memory", 0.2),
            anti_slop=data.get("anti_slop", 0.2)
        )


@dataclass
class FailureTrace:
    trace_id: str
    error_type: str
    error_message: str
    stack_trace: str
    context: dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    execution_id: str = ""
    weights_before: ICRLWeights = field(default_factory=ICRLWeights)
    weights_after: ICRLWeights = field(default_factory=ICRLWeights)


class FailureTraceEvaluator:
    def __init__(self, model_path: str = None):
        self.model_path = model_path
        self._traces: list[FailureTrace] = []
        self._weights = ICRLWeights()
        self._lock = threading.RLock()
        self._pattern_weights: dict[str, ICRLWeights] = defaultdict(ICRLWeights)
        self._learning_rate = 0.01

    def record_failure(self, error_type: str, error_message: str,
                      stack_trace: str, context: dict[str, Any],
                      execution_id: str = "") -> FailureTrace:

        trace_id = hashlib.sha256(
            f"{error_type}{error_message}{execution_id}{time.time()}".encode()
        ).hexdigest()[:12]

        trace = FailureTrace(
            trace_id=trace_id,
            error_type=error_type,
            error_message=error_message,
            stack_trace=stack_trace,
            context=context,
            execution_id=execution_id,
            weights_before=ICRLWeights(**self._weights.to_dict())
        )

        # Update weights based on failure
        self._update_weights(trace)

        trace.weights_after = ICRLWeights(**self._weights.to_dict())

        with self._lock:
            self._traces.append(trace)
            # Keep last 1000 traces
            if len(self._traces) > 1000:
                self._traces = self._traces[-1000:]

        return trace

    def _update_weights(self, trace: FailureTrace):
        error_type = trace.error_type.lower()

        # Adjust weights based on error patterns
        if "timeout" in error_type or "performance" in error_type:
            self._weights.performance = min(0.5, self._weights.performance + self._learning_rate)
            self._weights.correctness = max(0.1, self._weights.correctness - self._learning_rate * 0.5)

        elif "memory" in error_type or "oom" in error_type:
            self._weights.memory = min(0.5, self._weights.memory + self._learning_rate)
            self._weights.performance = max(0.1, self._weights.performance - self._learning_rate * 0.5)

        elif "syntax" in error_type or "type" in error_type or "slop" in error_type:
            self._weights.anti_slop = min(0.5, self._weights.anti_slop + self._learning_rate)
            self._weights.correctness = max(0.1, self._weights.correctness - self._learning_rate * 0.5)

        else:
            # General correctness issues
            self._weights.correctness = min(0.5, self._weights.correctness + self._learning_rate)

        # Normalize
        total = (self._weights.correctness + self._weights.performance +
                self._weights.memory + self._weights.anti_slop)
        if total > 0:
            self._weights.correctness /= total
            self._weights.performance /= total
            self._weights.memory /= total
            self._weights.anti_slop /= total

        # Store pattern-specific weights
        self._pattern_weights[error_type] = ICRLWeights(**self._weights.to_dict())

    def get_weights(self) -> ICRLWeights:
        with self._lock:
            return ICRLWeights(**self._weights.to_dict())

    def get_pattern_weights(self, error_type: str) -> ICRLWeights:
        with self._lock:
            return self._pattern_weights.get(error_type, ICRLWeights())

    def evaluate_fitness(self, result: dict[str, Any], weights: ICRLWeights = None) -> float:
        w = weights or self._weights

        score = 0.0

        # Correctness (0-1)
        if result.get("success", False):
            score += w.correctness * 1.0
        elif "partial" in result:
            score += w.correctness * 0.5

        # Performance (0-1, lower is better)
        if "duration_ms" in result:
            perf_score = max(0, 1 - result["duration_ms"] / 10000)
            score += w.performance * perf_score

        # Memory (0-1, lower is better)
        if "memory_mb" in result:
            mem_score = max(0, 1 - result["memory_mb"] / 1024)
            score += w.memory * mem_score

        # Anti-slop (0-1)
        if "slop_score" in result:
            score += w.anti_slop * (1 - result["slop_score"])
        elif result.get("success", False):
            score += w.anti_slop * 0.8  # Assume decent if successful

        return min(1.0, score)

    def get_traces(self, limit: int = 100, error_type: str = None) -> list[FailureTrace]:
        with self._lock:
            traces = self._traces
            if error_type:
                traces = [t for t in traces if error_type.lower() in t.error_type.lower()]
            return traces[-limit:]

    def save_model(self, path: str):
        data = {
            "weights": self._weights.to_dict(),
            "pattern_weights": {k: v.to_dict() for k, v in self._pattern_weights.items()},
            "learning_rate": self._learning_rate
        }
        with pathlib.Path(path).open('w') as f:
            json.dump(data, f, indent=2)

    def load_model(self, path: str):
        with pathlib.Path(path).open() as f:
            data = json.load(f)

        self._weights = ICRLWeights.from_dict(data.get("weights", {}))
        self._pattern_weights = {
            k: ICRLWeights.from_dict(v)
            for k, v in data.get("pattern_weights", {}).items()
        }
        self._learning_rate = data.get("learning_rate", 0.01)


_failure_evaluator: FailureTraceEvaluator | None = None


def get_failure_evaluator() -> FailureTraceEvaluator:
    global _failure_evaluator
    if _failure_evaluator is None:
        _failure_evaluator = FailureTraceEvaluator()
    return _failure_evaluator
