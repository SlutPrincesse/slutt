"""
Anti-Slop Guardrails & Quality Enforcement (Section 28)
"""
from .comment_stripper import (
    CommentStripper,
    DocstringStripper,
    LicenseHeaderManager,
    StripResult,
)
from .noop_detector import (
    DeadCodeAnalyzer,
    NoOpDetector,
    NoOpIssue,
    NoOpReport,
    NoOpType,
    NoOpVisitor,
)
from .pre_commit_validator import (
    CommitHookRunner,
    PreCommitValidator,
    ValidationResult,
    ValidationSeverity,
)
from .typing_guard import (
    TypeAnnotationGenerator,
    TypeHintLevel,
    TypingGuard,
    TypingIssue,
    TypingReport,
    TypingVisitor,
)

__all__ = [
    # Pre-Commit Validator
    "PreCommitValidator",
    "ValidationResult",
    "ValidationSeverity",
    "CommitHookRunner",
    # Comment Stripper
    "CommentStripper",
    "DocstringStripper",
    "LicenseHeaderManager",
    "StripResult",
    # Typing Guard
    "TypingGuard",
    "TypeHintLevel",
    "TypingIssue",
    "TypingReport",
    "TypingVisitor",
    "TypeAnnotationGenerator",
    # No-Op Detector
    "NoOpDetector",
    "NoOpType",
    "NoOpIssue",
    "NoOpReport",
    "NoOpVisitor",
    "DeadCodeAnalyzer",
]
