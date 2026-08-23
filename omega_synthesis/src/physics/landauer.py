from __future__ import annotations
import numpy as np
from ..core.backend import TensorBackend
from ..core.module import OmegaModule

class LandauerLimit(OmegaModule):
    def __init__(self, temperature: float = 300.0, device: str = "cpu"):
        super().__init__(name="landauer_limit")
        self.temperature = temperature
        self.device = device
        self.k_B = 1.380649e-23
        self.ln2 = np.log(2.0)

    def dissipation_penalty(self, delta_info: np.ndarray) -> np.ndarray:
        return self.k_B * self.temperature * self.ln2 * np.abs(delta_info)

    def total_energy(self, I_t: np.ndarray, V_t: np.ndarray) -> np.ndarray:
        return I_t * V_t + self.dissipation_penalty(np.abs(I_t))

    def flops_per_watt(self, flops: np.ndarray, watts: np.ndarray) -> np.ndarray:
        return flops / (watts + 1e-8)
