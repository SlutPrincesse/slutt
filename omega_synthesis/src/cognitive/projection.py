from __future__ import annotations
import numpy as np
from ..core.module import OmegaModule
from ..core.backend import TensorBackend
from ..core.quantum import DensityMatrix

class QuantumFreeRandomProjection(OmegaModule):
    def __init__(self, input_dim: int, output_dim: int, device: str = "cpu"):
        super().__init__(name="quantum_free_random_projection")
        self.input_dim = input_dim
        self.output_dim = output_dim
        self.device = device
        self.R = np.random.randn(output_dim, input_dim).astype(np.float64) / (output_dim ** 0.5)
        self.add_param("R", self.R)
        self.density = DensityMatrix(output_dim, device=device)
        self.add_module("density", self.density)
        self.unitary_history = []

    def project(self, x: np.ndarray) -> np.ndarray:
        return np.matmul(x, self.R.T)

    def unitary_evolution(self, rho: np.ndarray, steps: int = 1) -> np.ndarray:
        for _ in range(steps):
            U = self.density.unitary(rho.shape[0])
            rho = self.density.apply_unitary(rho, U)
            self.unitary_history.append(U)
        return rho

    def forward(self, x: np.ndarray) -> np.ndarray:
        x_proj = self.project(x)
        batch_size = x.shape[0]
        rho = self.density.random_density(batch_size)
        rho_evolved = self.unitary_evolution(rho, steps=3)
        flat = x_proj.reshape(x_proj.shape[0], -1)
        if flat.shape[1] < self.output_dim:
            pad = np.zeros((flat.shape[0], self.output_dim - flat.shape[1]), dtype=flat.dtype)
            flat = np.concatenate([flat, pad], axis=-1)
        elif flat.shape[1] > self.output_dim:
            flat = flat[:, : self.output_dim]
        trace = np.trace(rho_evolved, axis1=1, axis2=2).reshape(-1, 1)
        return flat * np.real(trace)
