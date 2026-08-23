from __future__ import annotations
import numpy as np
from typing import Optional
from ..core.backend import TensorBackend
from ..core.module import OmegaModule

class LindbladMasterEquation(OmegaModule):
    def __init__(self, dim: int, device: str = "cpu"):
        super().__init__(name="lindblad_master_equation")
        self.dim = dim
        self.device = device
        self.H = np.random.randn(dim, dim).astype(np.float64)
        self.H = (self.H + self.H.T) / 2
        self.L_ops = [np.random.randn(dim, dim).astype(np.float64) for _ in range(3)]
        self.add_param("H", self.H)
        for i, L in enumerate(self.L_ops):
            self.add_param(f"L_{i}", L)

    def dissipator(self, rho: np.ndarray, L: np.ndarray) -> np.ndarray:
        L_dag = np.conj(L).T
        term1 = np.matmul(np.matmul(L, rho), L_dag)
        term2 = 0.5 * np.matmul(L_dag, L)
        term2 = 0.5 * (np.matmul(term2, rho) + np.matmul(rho, term2))
        return term1 - term2

    def step(self, rho: np.ndarray, dt: float = 0.01) -> np.ndarray:
        if rho.ndim == 2:
            rho = rho.reshape(1, rho.shape[0], rho.shape[1])
        B = rho.shape[0]
        H = self.H
        unitary_term = -1j * (np.matmul(H.reshape(1, self.dim, self.dim).repeat(B, axis=0), rho) - np.matmul(rho, H.reshape(1, self.dim, self.dim).repeat(B, axis=0))) * dt
        dissip = np.zeros_like(rho)
        for L in self.L_ops:
            for b in range(B):
                dissip[b] = dissip[b] + self.dissipator(rho[b], L)
        rho_next = rho + unitary_term + dissip * dt
        trace = np.trace(rho_next, axis1=1, axis2=2).reshape(-1, 1, 1)
        return rho_next / trace
