"""
Shadow Git Kernel & Zero-Regression Engine (Section 30)
"""
from .shadowgit_core import (
    ShadowBranch,
    ShadowCommit,
    ShadowDiff,
    ShadowFile,
    ShadowGit,
    ShadowGitRemote,
    ShadowGitStatus,
)
from .shadowgit_index import (
    IndexEntry,
    IndexEntryStatus,
    IndexMerger,
    IndexTree,
    ShadowIndex,
)
from .shadowgit_sync import (
    ShadowGitSync,
    ShadowGitLFS,
    SyncDirection,
    SyncStatus,
    RemoteProtocol,
    RemoteConfig,
    SyncOptions,
    SyncResult,
    SyncConflict,
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
    "ShadowGitSync",
    "ShadowGitLFS",
    "SyncDirection",
    "SyncStatus",
    "RemoteProtocol",
    "RemoteConfig",
    "SyncOptions",
    "SyncResult",
    "SyncConflict",
]
