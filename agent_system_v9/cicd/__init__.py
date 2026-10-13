"""
Continuous Integration & Self-Evolution Pipeline (Section 24)
Self-Modifying System Pipeline, Automated Release Tagging & Changelog Engine,
Canary Task Execution Guard, Agent Capability Schema Exporter,
Post-Mortem Knowledge Extractor
"""
from .self_modifying import SelfModifyingPipeline, Modification
from .release_tagger import ReleaseTagger, ReleaseInfo
from .canary_guard import CanaryGuard, CanaryResult
from .capability_exporter import CapabilityExporter, CapabilitySchema
from .knowledge_extractor import KnowledgeExtractor, ExtractedKnowledge

__all__ = [
    "SelfModifyingPipeline",
    "Modification",
    "ReleaseTagger",
    "ReleaseInfo",
    "CanaryGuard",
    "CanaryResult",
    "CapabilityExporter",
    "CapabilitySchema",
    "KnowledgeExtractor",
    "ExtractedKnowledge",
]