from __future__ import annotations
import numpy as np
from typing import Dict, Any, Optional
from ..core.module import OmegaModule
from .loss import MasterActionFunctional

class OmegaTrainer(OmegaModule):
    def __init__(self, master_loss: MasterActionFunctional, lr: float = 1e-3, device: str = "cpu"):
        super().__init__(name="omega_trainer")
        self.master_loss = master_loss
        self.lr = lr
        self.device = device

    def train_step(self, state: Dict[str, Any]) -> Dict[str, float]:
        loss_val = self.master_loss(state)
        param_list = self.master_loss.parameters()
        for p in param_list:
            grad = np.zeros_like(p)
            eps = 1e-5
            p_flat = p.flatten()
            grad_flat = np.zeros_like(p_flat)
            for i in range(min(20, p_flat.shape[0])):
                p_pert = p.copy()
                unravel_idx = np.unravel_index(i, p.shape)
                p_pert[unravel_idx] += eps
                old_val = p.copy()
                p[...] = p_pert
                loss_plus = self.master_loss(state)
                p[...] = old_val
                grad_flat[i] = (loss_plus - loss_val) / eps
            p[...] = p - self.lr * grad_flat.reshape(p.shape)
        return {"loss": float(loss_val), **{k: float(v) for k, v in self.master_loss.breakdown.items()}}

    def fit(self, state: Dict[str, Any], steps: int = 10) -> Dict[str, list]:
        history = {k: [] for k in self.master_loss.registry.keys()}
        history["loss"] = []
        for _ in range(steps):
            metrics = self.train_step(state)
            for k, v in metrics.items():
                history.setdefault(k, []).append(v)
        return history
