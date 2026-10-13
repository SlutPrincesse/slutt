"""
Shadow Git Kernel & Zero-Regression Engine (Section 30)
"""
from .shadowgit_core import (
    ShadowGit,
    ShadowGitRemote,
    ShadowFile,
    ShadowCommit,
    ShadowBranch,
    ShadowDiff,
    ShadowGitStatus,
)
from .shadowgit_index import (
    ShadowIndex,
    IndexMerger,
    IndexEntry,
    IndexEntryStatus,
    IndexTree,
)

__all__ = [
    "ShadowGit",
    "ShadowGitRemote",
    "ShadowFile",
    "ShadowCommit",
    "ShadowBranch",
    "ShadowDiff",
    "ShadowGitStatus",
    "ShadowIndex",
    "IndexMerger",
    "IndexEntry",
    "IndexEntryStatus",
    "IndexTree",
]