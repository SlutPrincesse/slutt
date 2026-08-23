from __future__ import annotations
import numpy as np
from ..core.backend import TensorBackend
from ..core.module import OmegaModule

class ActiveInference(OmegaModule):
    def __init__(self, obs_dim: int, state_dim: int, device: str = "cpu"):
        super().__init__(name="active_inference")
        self.obs_dim = obs_dim
        self.state_dim = state_dim
        self.device = device
        self.W_g1 = TensorBackend.randn(state_dim, 128) * 0.1
        self.W_g2 = TensorBackend.randn(128, obs_dim) * 0.1
        self.W_r1 = TensorBackend.randn(obs_dim, 128) * 0.1
        self.W_r2 = TensorBackend.randn(128, state_dim * 2) * 0.1
        self.add_param("W_g1", self.W_g1)
        self.add_param("W_g2", self.W_g2)
        self.add_param("W_r1", self.W_r1)
        self.add_param("W_r2", self.W_r2)

    def prior(self, batch_size: int) -> np.ndarray:
        return np.zeros((batch_size, self.state_dim), dtype=np.float64)

    def generative(self, s: np.ndarray) -> np.ndarray:
        h = np.maximum(0, np.matmul(s, self.W_g1))
        return np.matmul(h, self.W_g2)

    def recognition(self, o: np.ndarray) -> np.ndarray:
        h = np.maximum(0, np.matmul(o, self.W_r1))
        return np.matmul(h, self.W_r2)

    def variational_free_energy(self, o: np.ndarray, q_mu: np.ndarray, q_logvar: np.ndarray) -> np.ndarray:
        q_std = np.exp(0.5 * q_logvar)
        eps = np.random.randn(*q_std.shape)
        s = q_mu + eps * q_std
        recon = self.generative(s)
        recon_loss = np.sum((o - recon) ** 2, axis=-1)
        kl = -0.5 * np.sum(1 + q_logvar - q_mu ** 2 - np.exp(q_logvar), axis=-1)
        return recon_loss + kl

    def forward(self, o: np.ndarray) -> tuple:
        q_params = self.recognition(o)
        q_mu = q_params[:, : self.state_dim]
        q_logvar = q_params[:, self.state_dim :]
        F = self.variational_free_energy(o, q_mu, q_logvar)
        return np.mean(F), (q_mu, q_logvar)
