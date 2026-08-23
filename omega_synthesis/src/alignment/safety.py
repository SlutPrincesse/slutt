from __future__ import annotations
import numpy as np
from ..core.backend import TensorBackend
from ..core.module import OmegaModule

class AlignmentSafety(OmegaModule):
    def __init__(self, device: str = "cpu"):
        super().__init__(name="alignment_safety")
        self.device = device
        self.safety_margin = np.array(0.1, dtype=np.float64)
        self.add_param("safety_margin", self.safety_margin)

    def c_safety(self, s: np.ndarray, a: np.ndarray) -> np.ndarray:
        return np.sum(s ** 2, axis=-1) + np.sum(a ** 2, axis=-1) - self.safety_margin

    def d_equality(self, a: np.ndarray, u_i: np.ndarray, u_j: np.ndarray) -> np.ndarray:
        return np.abs(np.sum(a * u_i, axis=-1) - np.sum(a * u_j, axis=-1))

    def i_blind(self, s: np.ndarray, h: np.ndarray) -> np.ndarray:
        mask = (h < 0).astype(np.float64)
        if s.ndim > 1:
            mask = mask.reshape(-1, 1)
        return np.where(mask > 0.5, np.zeros_like(s), np.ones_like(s))

    def forward(self, s: np.ndarray, a: np.ndarray, u_i: np.ndarray, u_j: np.ndarray, h: np.ndarray) -> dict:
        return {
            "C_safety": self.c_safety(s, a),
            "D_equality": self.d_equality(a, u_i, u_j),
            "I_blind": self.i_blind(s, h),
        }
