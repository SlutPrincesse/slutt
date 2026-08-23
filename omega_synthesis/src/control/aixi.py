from __future__ import annotations
import numpy as np
from ..core.backend import TensorBackend
from ..core.module import OmegaModule

class AIXITractable(OmegaModule):
    def __init__(self, num_models: int = 5, horizon: int = 5, state_dim: int = 4, action_dim: int = 2, device: str = "cpu"):
        super().__init__(name="aixi_tractable")
        self.num_models = num_models
        self.horizon = horizon
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.device = device
        self.input_dim = state_dim + action_dim
        self.models = []
        self.model_weights = np.ones(num_models, dtype=np.float64) / num_models
        for i in range(num_models):
            W1 = np.random.randn(self.input_dim, 32).astype(np.float64) * 0.1
            W2 = np.random.randn(32, 32).astype(np.float64) * 0.1
            W3 = np.random.randn(32, action_dim).astype(np.float64) * 0.1
            self.models.append({"W1": W1, "W2": W2, "W3": W3})
            self.add_param(f"model_{i}_W1", W1)
            self.add_param(f"model_{i}_W2", W2)
            self.add_param(f"model_{i}_W3", W3)
        self.add_param("model_weights", self.model_weights)

    def simulate(self, model_idx: int, state: np.ndarray, action: np.ndarray) -> np.ndarray:
        m = self.models[model_idx]
        x = np.concatenate([state, action], axis=-1)
        h1 = np.tanh(np.matmul(x, m["W1"]))
        h2 = np.tanh(np.matmul(h1, m["W2"]))
        out = np.matmul(h2, m["W3"])
        next_state = np.concatenate([state[:, :self.state_dim], out], axis=-1)
        return next_state[:, :self.state_dim]

    def thompson_sampling(self, state: np.ndarray) -> np.ndarray:
        idx = int(np.random.choice(self.num_models, p=self.model_weights / self.model_weights.sum()))
        action = self.simulate(idx, state, np.zeros((state.shape[0], self.action_dim), dtype=state.dtype))
        return action[:, :self.action_dim]

    def forward(self, state: np.ndarray) -> np.ndarray:
        actions = []
        s = state.copy()
        for _ in range(self.horizon):
            a = self.thompson_sampling(s)
            actions.append(a)
            s = self.simulate(0, s, a)
        return np.stack(actions, axis=1)
