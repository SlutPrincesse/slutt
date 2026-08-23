from __future__ import annotations
import numpy as np
from typing import Callable, Optional
from ..core.backend import TensorBackend
from ..core.module import OmegaModule
from ..core.autodiff import NaturalGradient

class InfoGeometry(OmegaModule):
    def __init__(self, device: str = "cpu"):
        super().__init__(name="info_geometry")
        self.device = device
        self.natural_grad = NaturalGradient(device=device)

    def fisher_metric(self, log_prob_fn: Callable, params: np.ndarray, n_samples: int = 50) -> np.ndarray:
        return self.natural_grad.fisher_information_matrix(log_prob_fn, params, n_samples=n_samples)

    def natural_gradient_step(self, loss_fn: Callable, params: np.ndarray, lr: float = 1e-3) -> np.ndarray:
        return self.natural_grad.natural_gradient_step(loss_fn, params, lr=lr)

    def wasserstein_distance(self, p: np.ndarray, q: np.ndarray) -> np.ndarray:
        mu_p = p.mean(axis=0) if p.ndim > 1 else p
        mu_q = q.mean(axis=0) if q.ndim > 1 else q
        diff = mu_p - mu_q
        return np.sum(diff ** 2)
