from __future__ import annotations
import numpy as np
from typing import Callable, Optional
from ..core.backend import TensorBackend
from ..core.module import OmegaModule

class NaturalGradient(OmegaModule):
    def __init__(self, device: str = "cpu", eps: float = 1e-6):
        super().__init__(name="natural_gradient")
        self.device = device
        self.eps = eps

    def fisher_information_matrix(self, log_prob_fn: Callable, params: np.ndarray, n_samples: int = 50) -> np.ndarray:
        grads = []
        for _ in range(n_samples):
            sample = params.copy()
            log_prob = log_prob_fn(sample)
            eps = 1e-5
            g = np.zeros_like(sample)
            for i in range(sample.shape[0]):
                sample_p = sample.copy()
                sample_p[i] += eps
                g[i] = (log_prob_fn(sample_p) - log_prob) / eps
            grads.append(g.reshape(1, -1))
        grads = np.concatenate(grads, axis=0)
        F = np.matmul(grads.T, grads) / n_samples
        F = F + self.eps * np.eye(F.shape[0])
        return F

    def natural_gradient_step(self, loss_fn: Callable, params: np.ndarray, lr: float = 1e-3) -> np.ndarray:
        eps = 1e-5
        loss = loss_fn(params)
        grad = np.zeros_like(params)
        for i in range(params.shape[0]):
            p = params.copy()
            p[i] += eps
            grad[i] = (loss_fn(p) - loss) / eps
        F = self.fisher_information_matrix(lambda p: -loss_fn(p), params, n_samples=20)
        F_inv = np.linalg.inv(F)
        natural_grad = np.matmul(F_inv, grad.reshape(-1, 1)).flatten()
        return params - lr * natural_grad
