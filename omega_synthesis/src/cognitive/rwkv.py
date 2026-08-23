from __future__ import annotations
import numpy as np
from ..core.module import OmegaModule
from ..core.backend import TensorBackend

class RWKVTimeMixing(OmegaModule):
    def __init__(self, dim: int, device: str = "cpu"):
        super().__init__(name="rwkv_time_mixing")
        self.dim = dim
        self.device = device
        self.W_w = TensorBackend.randn(dim, dim) * 0.1
        self.W_k = TensorBackend.randn(dim, dim) * 0.1
        self.W_v = TensorBackend.randn(dim, dim) * 0.1
        self.W_r = TensorBackend.randn(dim, dim) * 0.1
        self.u = np.ones(dim, dtype=np.float64)
        self.add_param("W_w", self.W_w)
        self.add_param("W_k", self.W_k)
        self.add_param("W_v", self.W_v)
        self.add_param("W_r", self.W_r)
        self.add_param("u", self.u)
        self.state = None

    def forward(self, x: np.ndarray) -> np.ndarray:
        B, T, _ = x.shape
        w = np.matmul(x, self.W_w)
        k = np.matmul(x, self.W_k)
        v = np.matmul(x, self.W_v)
        r = np.matmul(x, self.W_r)
        if self.state is None:
            self.state = {
                "aa": np.zeros((B, self.dim), dtype=np.float64),
                "bb": np.zeros((B, self.dim), dtype=np.float64),
            }
        aa = self.state["aa"]
        bb = self.state["bb"]
        w = -np.exp(np.clip(w, -20, 0))
        k_t = k.transpose(0, 2, 1)
        v_t = v.transpose(0, 2, 1)
        o = np.zeros_like(x)
        for t in range(T):
            kv = k_t[:, :, t] * v_t[:, :, t]
            aa = aa * w[:, t, :] + kv
            bb = bb * w[:, t, :] + k_t[:, :, t]
            wkv = aa / (bb + 1e-8)
            o[:, t, :] = 1.0 / (1.0 + np.exp(-r[:, t, :])) * (self.u.reshape(1, -1) * wkv + wkv)
        self.state["aa"] = aa
        self.state["bb"] = bb
        return o

class RWKVChannelMixing(OmegaModule):
    def __init__(self, dim: int, hidden_dim: Optional[int] = None, device: str = "cpu"):
        super().__init__(name="rwkv_channel_mixing")
        self.dim = dim
        self.hidden_dim = hidden_dim if hidden_dim is not None else dim * 4
        self.device = device
        self.W_k = TensorBackend.randn(dim, self.hidden_dim) * 0.1
        self.W_v = TensorBackend.randn(self.hidden_dim, dim) * 0.1
        self.mu_k = np.ones(self.hidden_dim, dtype=np.float64)
        self.add_param("W_k", self.W_k)
        self.add_param("W_v", self.W_v)
        self.add_param("mu_k", self.mu_k)

    def forward(self, x: np.ndarray) -> np.ndarray:
        k = np.matmul(x, self.W_k)
        v = np.matmul(self.mu_k * np.maximum(0, k) ** 2, self.W_v)
        return x + v
