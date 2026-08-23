from __future__ import annotations
import numpy as np
from typing import Callable, Optional
from ..core.backend import TensorBackend
from ..core.module import OmegaModule

class RiemannianGeometry(OmegaModule):
    def __init__(self, dim: int, device: str = "cpu"):
        super().__init__(name="riemannian_geometry")
        self.dim = dim
        self.device = device

    def metric_tensor(self, z: np.ndarray) -> np.ndarray:
        if z.ndim == 1:
            z = z.reshape(1, -1)
        B = z.shape[0]
        g = np.eye(self.dim, dtype=np.float64).reshape(1, self.dim, self.dim).repeat(B, axis=0)
        for i in range(self.dim):
            for j in range(i, self.dim):
                g[:, i, j] = 1.0 + 0.1 * np.sin(z[:, i]) * np.cos(z[:, j])
                g[:, j, i] = g[:, i, j]
        return g

    def christoffel_symbols(self, z: np.ndarray, g: np.ndarray) -> np.ndarray:
        B = z.shape[0] if z.ndim > 1 else 1
        z = z.reshape(B, -1)
        dg = np.zeros((B, self.dim, self.dim, self.dim), dtype=np.float64)
        eps = 1e-5
        for mu in range(self.dim):
            for i in range(self.dim):
                for j in range(self.dim):
                    z_plus = z.copy()
                    z_plus[:, mu] += eps
                    z_minus = z.copy()
                    z_minus[:, mu] -= eps
                    g_plus = self.metric_tensor(z_plus)
                    g_minus = self.metric_tensor(z_minus)
                    dg[:, mu, i, j] = (g_plus[:, i, j] - g_minus[:, i, j]) / (2 * eps)
        Gamma = np.zeros((B, self.dim, self.dim, self.dim), dtype=np.float64)
        for b in range(B):
            g_inv = np.linalg.inv(g[b])
            for k in range(self.dim):
                for i in range(self.dim):
                    for j in range(self.dim):
                        for l in range(self.dim):
                            Gamma[b, k, i, j] += 0.5 * g_inv[k, l] * (dg[b, i, l, j] + dg[b, j, l, i] - dg[b, l, i, j])
        return Gamma

    def geodesic_ode(self, t: float, state: np.ndarray, z_init: np.ndarray) -> np.ndarray:
        z = state[:, : self.dim]
        v = state[:, self.dim :]
        g = self.metric_tensor(z)
        Gamma = self.christoffel_symbols(z, g)
        dz = v.copy()
        dv = np.zeros_like(v)
        for k in range(self.dim):
            for b in range(z.shape[0]):
                acc = 0.0
                for i in range(self.dim):
                    for j in range(self.dim):
                        acc += Gamma[b, k, i, j] * v[b, i] * v[b, j]
                dv[b, k] = -acc
        return np.concatenate([dz, dv], axis=1)

    def solve_geodesic(self, z0: np.ndarray, v0: np.ndarray, t_span: np.ndarray) -> np.ndarray:
        from scipy.integrate import odeint
        state0 = np.concatenate([z0.flatten(), v0.flatten()])
        def ode_np(s, t):
            s = s.reshape(1, -1)
            ds = self.geodesic_ode(t, s, z0.reshape(1, -1))
            return ds.flatten()
        sol = odeint(ode_np, state0, t_span)
        return sol
