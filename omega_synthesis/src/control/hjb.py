from __future__ import annotations
import numpy as np
from typing import Callable, Optional
from ..core.backend import TensorBackend
from ..core.module import OmegaModule

class HJBSolver(OmegaModule):
    def __init__(self, dim: int, grid_size: int = 20, device: str = "cpu"):
        super().__init__(name="hjb_solver")
        self.dim = dim
        self.grid_size = grid_size
        self.device = device
        self.dx = 2.0 / (grid_size - 1)
        self.x_grid = np.linspace(-1, 1, grid_size, dtype=np.float64)
        self.V = np.zeros((grid_size, dim), dtype=np.float64)
        self.add_param("V", self.V)

    def dynamics(self, x: np.ndarray, u: np.ndarray) -> np.ndarray:
        return x + 0.1 * u

    def running_cost(self, x: np.ndarray, u: np.ndarray) -> np.ndarray:
        return np.sum(x ** 2, axis=-1) + 0.5 * np.sum(u ** 2, axis=-1)

    def solve_step(self, dt: float = 0.01) -> float:
        residual = 0.0
        V = self.V
        for i in range(self.dim):
            Vi = V[:, i]
            dV_dt = np.zeros_like(Vi)
            dV_dx = np.zeros_like(Vi)
            d2V_dx2 = np.zeros_like(Vi)
            dV_dx[1:-1] = (Vi[2:] - Vi[:-2]) / (2 * self.dx)
            d2V_dx2[1:-1] = (Vi[2:] - 2 * Vi[1:-1] + Vi[:-2]) / (self.dx ** 2)
            x = self.x_grid.reshape(-1, 1)
            u_opt = -dV_dx.reshape(-1, 1)
            f = self.dynamics(x, u_opt)
            L = self.running_cost(x, u_opt)
            dV_dt = L + dV_dx * f.flatten() + 0.5 * 0.1 ** 2 * d2V_dx2
            residual = max(residual, np.mean(dV_dt ** 2))
            self.V[:, i] = self.V[:, i] - dt * dV_dt
        return float(residual)

    def value_function(self, x: np.ndarray) -> np.ndarray:
        idx = np.clip(((x + 1.0) / 2.0 * (self.grid_size - 1)).astype(int), 0, self.grid_size - 1)
        return self.V[idx].sum(axis=-1)
