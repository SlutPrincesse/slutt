from __future__ import annotations
import numpy as np
from typing import Optional
from .backend import TensorBackend
from .module import OmegaModule

class DensityMatrix(OmegaModule):
    def __init__(self, dim: int, device: str = "cpu"):
        super().__init__(name="density_matrix")
        self.dim = dim
        self.device = device

    def random_density(self, batch_size: int = 1) -> np.ndarray:
        A = np.random.randn(batch_size, self.dim, self.dim).astype(np.float64)
        rho = np.matmul(A, np.conj(A).transpose(0, 2, 1))
        trace = np.trace(rho, axis1=1, axis2=2).reshape(-1, 1, 1)
        return rho / trace

    def unitary(self, batch_size: int = 1) -> np.ndarray:
        result = np.zeros((batch_size, self.dim, self.dim), dtype=np.float64)
        for b in range(batch_size):
            X = np.random.randn(self.dim, self.dim).astype(np.float64)
            Q, R = np.linalg.qr(X)
            diag = np.diag(np.sign(np.diag(R)))
            result[b] = np.matmul(Q, diag)
        return result

    def apply_unitary(self, rho: np.ndarray, U: np.ndarray) -> np.ndarray:
        return np.matmul(np.matmul(U, rho), np.conj(U).transpose(0, 2, 1))

    def measurement_projector(self, state: np.ndarray) -> np.ndarray:
        ket = state.reshape(state.shape[0], -1, 1)
        bra = np.conj(ket).transpose(0, 2, 1)
        return np.matmul(ket, bra)

    def partial_trace(self, rho: np.ndarray, dim_a: int, dim_b: int) -> np.ndarray:
        if rho.ndim == 2:
            rho = rho.reshape(1, dim_a, dim_b, dim_a, dim_b)
        return np.trace(rho, axis1=2, axis2=4)
