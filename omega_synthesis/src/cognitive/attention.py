from __future__ import annotations
import numpy as np
from ..core.module import OmegaModule
from ..core.backend import TensorBackend
from .rwkv import RWKVTimeMixing

class HybridAttention(OmegaModule):
    def __init__(self, dim: int, num_heads: int = 4, alpha: float = 0.5, device: str = "cpu"):
        super().__init__(name="hybrid_attention")
        self.dim = dim
        self.num_heads = num_heads
        self.alpha = alpha
        self.device = device
        self.head_dim = dim // num_heads
        self.W_q = TensorBackend.randn(dim, dim) * 0.1
        self.W_k = TensorBackend.randn(dim, dim) * 0.1
        self.W_v = TensorBackend.randn(dim, dim) * 0.1
        self.W_o = TensorBackend.randn(dim, dim) * 0.1
        self.add_param("W_q", self.W_q)
        self.add_param("W_k", self.W_k)
        self.add_param("W_v", self.W_v)
        self.add_param("W_o", self.W_o)
        self.rwkv = RWKVTimeMixing(dim, device=device)
        self.add_module("rwkv", self.rwkv)

    def forward(self, x: np.ndarray, mask: Optional[np.ndarray] = None) -> np.ndarray:
        B, T, _ = x.shape
        q = np.matmul(x, self.W_q).reshape(B, T, self.num_heads, self.head_dim).transpose(0, 2, 1, 3)
        k = np.matmul(x, self.W_k).reshape(B, T, self.num_heads, self.head_dim).transpose(0, 2, 1, 3)
        v = np.matmul(x, self.W_v).reshape(B, T, self.num_heads, self.head_dim).transpose(0, 2, 1, 3)
        scale = self.head_dim ** -0.5
        attn = np.matmul(q, k.transpose(0, 1, 3, 2)) * scale
        if mask is not None:
            attn = attn * mask + (1 - mask) * (-1e9)
        attn = TensorBackend.softmax(attn, dim=-1)
        attn_out = np.matmul(attn, v).transpose(0, 2, 1, 3).reshape(B, T, -1)
        rwkv_out = self.rwkv(x)
        return np.matmul(self.alpha * rwkv_out + (1 - self.alpha) * attn_out, self.W_o)
