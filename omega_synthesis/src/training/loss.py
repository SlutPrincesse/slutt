from __future__ import annotations
import numpy as np
from typing import Dict, Any, Optional
from ..core.backend import TensorBackend
from ..core.module import OmegaModule

class MasterActionFunctional(OmegaModule):
    def __init__(self, device: str = "cpu"):
        super().__init__(name="master_action_functional")
        self.device = device
        self.registry: Dict[str, OmegaModule] = {}
        self.weights: Dict[str, float] = {}
        self.breakdown: Dict[str, float] = {}

    def register(self, key: str, module: OmegaModule, weight: float = 1.0):
        self.registry[key] = module
        self.weights[key] = weight
        self.add_module(key, module)
        return self

    def forward(self, state: Dict[str, Any]) -> float:
        total = 0.0
        breakdown = {}
        for key, module in self.registry.items():
            try:
                inp = state.get(key, state)
                out = module(inp)
                if isinstance(out, tuple):
                    val = out[0]
                    if isinstance(val, np.ndarray):
                        val = float(val.mean())
                    else:
                        val = float(val)
                elif isinstance(out, dict):
                    vals = [float(v) for v in out.values() if isinstance(v, (np.ndarray, float))]
                    val = sum(vals) / len(vals) if vals else 0.0
                elif isinstance(out, np.ndarray):
                    val = float(out.mean())
                else:
                    val = float(out)
                breakdown[key] = val
                total += self.weights[key] * val
            except Exception as e:
                breakdown[key] = float("nan")
        self.breakdown = breakdown
        return float(total)
