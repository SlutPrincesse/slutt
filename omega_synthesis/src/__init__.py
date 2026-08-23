from .core.backend import TensorBackend
from .core.module import OmegaModule
from .core.geometry import RiemannianGeometry
from .core.quantum import DensityMatrix
from .core.autodiff import NaturalGradient
from .cognitive.jspace import JSpace
from .cognitive.rwkv import RWKVTimeMixing, RWKVChannelMixing
from .cognitive.attention import HybridAttention
from .cognitive.projection import QuantumFreeRandomProjection
from .control.hjb import HJBSolver
from .control.active_inference import ActiveInference
from .control.aixi import AIXITractable
from .alignment.gauge import NonAbelianGauge
from .alignment.info_geo import InfoGeometry
from .alignment.safety import AlignmentSafety
from .physics.landauer import LandauerLimit
from .physics.lindblad import LindbladMasterEquation
from .category.cats import Category, Functor, Monad
from .category.quine import CognitiveQuine
from .training.loss import MasterActionFunctional
from .training.trainer import OmegaTrainer

__all__ = [
    "TensorBackend",
    "OmegaModule",
    "RiemannianGeometry",
    "DensityMatrix",
    "NaturalGradient",
    "JSpace",
    "RWKVTimeMixing",
    "RWKVChannelMixing",
    "HybridAttention",
    "QuantumFreeRandomProjection",
    "HJBSolver",
    "ActiveInference",
    "AIXITractable",
    "NonAbelianGauge",
    "InfoGeometry",
    "AlignmentSafety",
    "LandauerLimit",
    "LindbladMasterEquation",
    "Category",
    "Functor",
    "Monad",
    "CognitiveQuine",
    "MasterActionFunctional",
    "OmegaTrainer",
]
