from __future__ import annotations
import numpy as np
from ..core.backend import TensorBackend
from ..core.module import OmegaModule

class NonAbelianGauge(OmegaModule):
    def __init__(self, dim: int, gauge_dim: int = 4, device: str = "cpu"):
        super().__init__(name="non_abelian_gauge")
        self.dim = dim
        self.gauge_dim = gauge_dim
        self.device = device
        self.A = np.zeros((dim, gauge_dim, dim), dtype=np.float64)
        self.add_param("A", self.A)

    def connection(self, z: np.ndarray) -> np.ndarray:
        idx = np.clip(((z + 1.0) / 2.0 * (self.dim - 1)).astype(int), 0, self.dim - 1)
        return self.A[idx[:, 0], :, idx[:, 0]]

    def curvature(self, z: np.ndarray, eps: float = 1e-4) -> np.ndarray:
        A_mu = self.connection(z)
        z_perturbed = z + eps * np.eye(self.dim, dtype=np.float64)[0]
        A_nu = self.connection(z_perturbed)
        dA_nu = (A_nu - A_mu) / eps
        z_perturbed2 = z + eps * np.eye(self.dim, dtype=np.float64)[1]
        dA_mu = (self.connection(z_perturbed2) - A_mu) / eps
        F = dA_mu - dA_nu
        for b in range(z.shape[0]):
            F[b] = F[b] + np.matmul(A_mu[b], A_nu[b]) - np.matmul(A_nu[b], A_mu[b])
        return F

    def covariant_derivative(self, psi: np.ndarray, z: np.ndarray) -> np.ndarray:
        A = self.connection(z)
        dpsi = np.gradient(psi, axis=0)
        return dpsi - A * psi
