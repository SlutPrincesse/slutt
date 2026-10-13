"""
Resource Agnostic Storage & Artifact Management (Section 19)
"""
from .virtual_object_repo import (
    VirtualObjectRepository,
    ObjectStore,
    VersionedObjectStore,
    ObjectSerializer,
    ContentAddressableStore,
    ObjectId,
    ObjectType,
    ObjectMetadata,
    VersionedObject,
    ObjectVersion,
)
from .delta_sync import (
    DeltaGenerator,
    DeltaApplier,
    SyncEngine,
    ConflictResolver,
    AssetLifecycler,
    BuildLedger,
    Delta,
    DeltaType,
    DeltaOperation,
    SyncState,
    DeltaEncoder,
)
from .content_addressable import (
    ContentAddressableStore as CASContentAddressableStore,
    BlobStore,
    DeltaSync as CASDeltaSync,
    DeltaSync,  # Export as both names
    GarbageCollector as CASGarbageCollector,
    Blob,
    Chunk,
    ChunkingStrategy,
    CASConfig,
    Chunker,
)

__all__ = [
    # Virtual Object Repo
    "VirtualObjectRepository",
    "ObjectStore",
    "VersionedObjectStore",
    "ObjectSerializer",
    "ContentAddressableStore",
    "ObjectId",
    "ObjectType",
    "ObjectMetadata",
    "VersionedObject",
    "ObjectVersion",
    # Delta Sync
    "DeltaGenerator",
    "DeltaApplier",
    "SyncEngine",
    "ConflictResolver",
    "AssetLifecycler",
    "BuildLedger",
    "Delta",
    "DeltaType",
    "DeltaOperation",
    "SyncState",
    "DeltaEncoder",
    # Content Addressable (CAS)
    "BlobStore",
    "DeltaSync",
    "CASDeltaSync",
    "CASGarbageCollector",
    "Blob",
    "Chunk",
    "ChunkingStrategy",
    "CASConfig",
    "Chunker",
]