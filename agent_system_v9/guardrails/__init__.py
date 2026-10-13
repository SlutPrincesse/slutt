"""
Anti-Slop Guardrails & Quality Enforcement (Section 28)
Anti-Slop Pre-Commit Validator, Redundant Comment Stripper,
Strict Typing & Cyclomatic Complexity Guard, AST No-Op Detector
"""
from .precommit_validator import PreCommitValidator, ValidationResult
from .comment_stripper import CommentStripper, StripResult
from .typing_guard import TypingGuard, TypingViolation
from .noop_detector import NoOpDetector, NoOpFinding

__all__ = [
    "PreCommitValidator",
    "ValidationResult",
    "CommentStripper",
    "StripResult",
    "TypingGuard",
    "TypingViolation",
    "NoOpDetector",
    "NoOpFinding",
]