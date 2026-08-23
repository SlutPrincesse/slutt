from __future__ import annotations
import numpy as np
from typing import Dict, List, Tuple, Any, Optional

class OmegaModule:
    def __init__(self, name: str = ""):
        self.name = name
        self._params: Dict[str, np.ndarray] = {}
        self._constraints: Dict[str, Any] = {}
        self._modules: Dict[str, "OmegaModule"] = {}

    def forward(self, *args, **kwargs):
        raise NotImplementedError

    def __call__(self, *args, **kwargs):
        return self.forward(*args, **kwargs)

    def add_param(self, key: str, value: np.ndarray):
        self._params[key] = value
        return self

    def add_module(self, key: str, module: "OmegaModule"):
        self._modules[key] = module
        return self

    def parameters(self) -> List[np.ndarray]:
        params = list(self._params.values())
        for m in self._modules.values():
            params.extend(m.parameters())
        return params

    def constraints(self) -> Dict[str, Any]:
        c = dict(self._constraints)
        for m in self._modules.values():
            c.update(m.constraints())
        return c

    def add_constraint(self, key: str, value: Any):
        self._constraints[key] = value
        return self

    def clip_gradients(self, grads: Dict[str, np.ndarray], max_norm: float = 1.0) -> Dict[str, np.ndarray]:
        for key, g in grads.items():
            norm = np.linalg.norm(g)
            if norm > max_norm:
                grads[key] = g * (max_norm / norm)
        return grads

    def zero_grad(self):
        for p in self.parameters():
            if hasattr(p, "grad"):
                p.grad = None
