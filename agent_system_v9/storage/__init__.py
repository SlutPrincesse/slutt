"""
Resource Agnostic Storage & Artifact Management (Section 19)
Virtual Object Repository, Deduplicating Artifact Content Store,
Differential Workspace Delta Synchronizer, Ephemeral Asset Lifecycler,
Immutable Build Ledger
"""
from .virtual_repo import VirtualObjectRepo, VirtualObject
from .content_store import ContentAddressableStore, Artifact
from .delta_sync import DeltaSync, DeltaPatch
from .asset_lifecycler import AssetLifecycler, AssetRecord
from .build_ledger import BuildLedger, BuildRecord

__all__ = [
    "VirtualObjectRepo",
    "VirtualObject",
    "ContentAddressableStore",
    "Artifact",
    "DeltaSync",
    "DeltaPatch",
    "AssetLifecycler",
    "AssetRecord",
    "BuildLedger",
    "BuildRecord",
]