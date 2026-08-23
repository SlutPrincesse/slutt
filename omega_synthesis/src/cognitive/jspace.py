from __future__ import annotations
import numpy as np
from typing import Optional
from ..core.backend import TensorBackend
from ..core.module import OmegaModule
from ..core.geometry import RiemannianGeometry

class JSpace(OmegaModule):
    def __init__(self, input_dim: int, latent_dim: int, device: str = "cpu"):
        super().__init__(name="jspace")
        self.input_dim = input_dim
        self.latent_dim = latent_dim
        self.device = device
        self.geometry = RiemannianGeometry(latent_dim, device=device)
        self.W = TensorBackend.randn(input_dim, latent_dim) * 0.1
        self.add_param("W", self.W)
        self.wasserstein_alpha = np.array(1.0, dtype=np.float64)
        self.add_param("wasserstein_alpha", self.wasserstein_alpha)

    def phi(self, x: np.ndarray) -> np.ndarray:
        return np.matmul(x, self.W)

    def forward(self, x: np.ndarray) -> tuple:
        z = self.phi(x)
        g = self.geometry.metric_tensor(z)
        return z, g

    def wasserstein_distance(self, z1: np.ndarray, z2: np.ndarray) -> np.ndarray:
        mu1 = z1.mean(axis=0) if z1.ndim > 1 else z1
        mu2 = z2.mean(axis=0) if z2.ndim > 1 else z2
        c1 = z1 - mu1
        c2 = z2 - mu2
        S1 = np.cov(c1.T) if c1.shape[0] > 1 else np.eye(c1.shape[1])
        S2 = np.cov(c2.T) if c2.shape[0] > 1 else np.eye(c2.shape[1])
        diff = mu1 - mu2
        trace_term = np.trace(S1) + np.trace(S2) - 2 * np.trace(np.sqrtm(np.matmul(np.matmul(S1, S2), S1)).real)
        return np.sum(diff ** 2) + trace_term
