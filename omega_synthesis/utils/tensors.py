import numpy as np
from typing import Union, List


class TensorOps:
    @staticmethod
    def normalize(x: np.ndarray, axis: int = -1) -> np.ndarray:
        norm = np.linalg.norm(x, axis=axis, keepdims=True)
        return x / (norm + 1e-8)

    @staticmethod
    def softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
        e_x = np.exp(x - np.max(x, axis=axis, keepdims=True))
        return e_x / np.sum(e_x, axis=axis, keepdims=True)

    @staticmethod
    def layer_norm(x: np.ndarray, eps: float = 1e-5) -> np.ndarray:
        mean = np.mean(x, axis=-1, keepdims=True)
        std = np.std(x, axis=-1, keepdims=True)
        return (x - mean) / (std + eps)

    @staticmethod
    def gelu(x: np.ndarray) -> np.ndarray:
        return 0.5 * x * (1 + np.tanh(np.sqrt(2 / np.pi) * (x + 0.044715 * x ** 3)))

    @staticmethod
    def swiglu(x: np.ndarray) -> np.ndarray:
        x1, x2 = np.split(x, 2, axis=-1)
        return x1 * (1 / (1 + np.exp(-x2)))

    @staticmethod
    def flatten_sequence(x: np.ndarray) -> np.ndarray:
        return x.reshape(x.shape[0], -1)

    @staticmethod
    def causal_mask(seq_len: int) -> np.ndarray:
        return np.triu(np.ones((seq_len, seq_len)), k=1)
