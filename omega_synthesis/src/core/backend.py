from __future__ import annotations
import numpy as np
from typing import Union, Optional

Tensor = Union[np.ndarray]

class TensorBackend:
    _impl = np

    @classmethod
    def zeros(cls, *shape, dtype=None, device=None):
        return np.zeros(shape, dtype=np.float64 if dtype is None else dtype)

    @classmethod
    def ones(cls, *shape, dtype=None, device=None):
        return np.ones(shape, dtype=np.float64 if dtype is None else dtype)

    @classmethod
    def eye(cls, n, dtype=None, device=None):
        return np.eye(n, dtype=np.float64 if dtype is None else dtype)

    @classmethod
    def randn(cls, *shape, dtype=None, device=None):
        return np.random.randn(*shape).astype(np.float64 if dtype is None else dtype)

    @classmethod
    def rand(cls, *shape, dtype=None, device=None):
        return np.random.rand(*shape).astype(np.float64 if dtype is None else dtype)

    @classmethod
    def exp(cls, x):
        return np.exp(x)

    @classmethod
    def log(cls, x):
        return np.log(x)

    @classmethod
    def sqrt(cls, x):
        return np.sqrt(x)

    @classmethod
    def norm(cls, x, p="fro", dim=None, keepdim=False):
        return np.linalg.norm(x, ord=p, axis=dim)

    @classmethod
    def trace(cls, x):
        return np.trace(x)

    @classmethod
    def transpose(cls, x, dim0, dim1):
        return np.swapaxes(x, dim0, dim1)

    @classmethod
    def matmul(cls, a, b):
        return np.matmul(a, b)

    @classmethod
    def solve(cls, a, b):
        return np.linalg.solve(a, b)

    @classmethod
    def eigh(cls, a):
        return np.linalg.eigh(a)

    @classmethod
    def det(cls, a):
        return np.linalg.det(a)

    @classmethod
    def stack(cls, tensors, dim=0):
        return np.stack(tensors, axis=dim)

    @classmethod
    def cat(cls, tensors, dim=0):
        return np.concatenate(tensors, axis=dim)

    @classmethod
    def sum(cls, x, dim=None, keepdim=False):
        return np.sum(x, axis=dim, keepdims=keepdim)

    @classmethod
    def mean(cls, x, dim=None, keepdim=False):
        return np.mean(x, axis=dim, keepdims=keepdim)

    @classmethod
    def var(cls, x, dim=None, keepdim=False, unbiased=True):
        return np.var(x, axis=dim, ddof=1 if unbiased else 0, keepdims=keepdim)

    @classmethod
    def diag(cls, x):
        if x.ndim == 1:
            return np.diag(x)
        return np.diagonal(x, axis1=-2, axis2=-1)

    @classmethod
    def sigmoid(cls, x):
        return 1.0 / (1.0 + np.exp(-x))

    @classmethod
    def relu(cls, x):
        return np.maximum(0, x)

    @classmethod
    def softmax(cls, x, dim=-1):
        e = np.exp(x - np.max(x, axis=dim, keepdims=True))
        return e / np.sum(e, axis=dim, keepdims=True)

    @classmethod
    def cos(cls, x):
        return np.cos(x)

    @classmethod
    def sin(cls, x):
        return np.sin(x)

    @classmethod
    def arange(cls, start, end, step=1, dtype=None, device=None):
        return np.arange(start, end, step=step, dtype=np.float64 if dtype is None else dtype)

    @classmethod
    def tensor(cls, data, dtype=None, device=None):
        arr = np.array(data, dtype=np.float64 if dtype is None else dtype)
        return arr

    @classmethod
    def complex(cls, real, imag=None):
        if imag is None:
            return real.view(np.complex128) if real.dtype == np.float64 else real.view(np.complex64)
        return real + 1j * imag

    @classmethod
    def real(cls, x):
        return np.real(x)

    @classmethod
    def imag(cls, x):
        return np.imag(x)

    @classmethod
    def adjoint(cls, x):
        return np.conj(x.T)

    @classmethod
    def mm(cls, a, b):
        return np.matmul(a, b)

    @classmethod
    def bmm(cls, a, b):
        return np.matmul(a, b)
