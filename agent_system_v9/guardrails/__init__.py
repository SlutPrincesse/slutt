"""
Anti-Slop Guardrails & Quality Enforcement (Section 28)
"""
from .pre_commit_validator import (
    PreCommitValidator,
    ValidationResult,
    ValidationSeverity,
    CommitHookRunner,
)
from .comment_stripper import (
    CommentStripper,
    DocstringStripper,
    LicenseHeaderManager,
    StripResult,
)
from .typing_guard import (
    TypingGuard,
    TypeHintLevel,
    TypingIssue,
    TypingReport,
    TypingVisitor,
    TypeAnnotationGenerator,
)
from .noop_detector import (
    NoOpDetector,
    NoOpType,
    NoOpIssue,
    NoOpReport,
    NoOpVisitor,
    DeadCodeAnalyzer,
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