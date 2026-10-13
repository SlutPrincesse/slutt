"""
Autonomous Recovery Loop & High-Density Triggers (Section 10)
OPPEVE DAG Loop, Automated Stderr Interceptor & Patcher, Recursive Core Synthesis (MERGE_CORE),
Batch Repo Ingestion (INGEST_REPO), Lexical Normalization Pipeline (LEX_NORM)
"""
from .ingest_repo import IngestionResult, IngestRepo
from .lex_norm import LexicalNormalizer, NormalizationResult
from .merge_core import MergeCore, MergeResult
from .oppeve_loop import OPPEVELoop, OPPEVEState
from .stderr_interceptor import PatchResult, StderrInterceptor

__all__ = [
    "OPPEVELoop",
    "OPPEVEState",
    "StderrInterceptor",
    "PatchResult",
    "MergeCore",
    "MergeResult",
    "IngestRepo",
    "IngestionResult",
    "LexicalNormalizer",
    "NormalizationResult",
]
