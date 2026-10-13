"""
Autonomous Recovery Loop & High-Density Triggers (Section 10)
OPPEVE DAG Loop, Automated Stderr Interceptor & Patcher, Recursive Core Synthesis (MERGE_CORE),
Batch Repo Ingestion (INGEST_REPO), Lexical Normalization Pipeline (LEX_NORM)
"""
from .oppeve_loop import OPPEVELoop, OPPEVEState
from .stderr_interceptor import StderrInterceptor, PatchResult
from .merge_core import MergeCore, MergeResult
from .ingest_repo import IngestRepo, IngestionResult
from .lex_norm import LexicalNormalizer, NormalizationResult

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