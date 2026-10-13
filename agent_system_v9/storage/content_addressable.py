"""
Content Addressable Store - CAS with deduplication
"""
import asyncio
import hashlib
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ChunkingStrategy(Enum):
    FIXED = "fixed"
    VARIABLE = "variable"
    RABIN = "rabin"
    FASTCDC = "fastcdc"


@dataclass
class Chunk:
    hash: str
    data: bytes
    size: int
    offset: int
    strategy: ChunkingStrategy = ChunkingStrategy.FIXED

    def __hash__(self):
        return hash(self.hash)

    def __eq__(self, other):
        return self.hash == other.hash if isinstance(other, Chunk) else False


@dataclass
class Blob:
    blob_id: str
    chunks: list[Chunk] = field(default_factory=list)
    total_size: int = 0
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_chunk(self, chunk: Chunk):
        self.chunks.append(chunk)
        self.total_size += chunk.size

    def to_dict(self) -> dict[str, Any]:
        return {
            "blob_id": self.blob_id,
            "chunks": [{"hash": c.hash, "size": c.size, "offset": c.offset} for c in self.chunks],
            "total_size": self.total_size,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass
class CASConfig:
    chunk_size: int = 64 * 1024  # 64KB default
    min_chunk_size: int = 4 * 1024
    max_chunk_size: int = 256 * 1024
    strategy: ChunkingStrategy = ChunkingStrategy.FIXED
    enable_deduplication: bool = True
    compression: bool = False


class Chunker:
    def __init__(self, config: CASConfig):
        self.config = config

    def chunk(self, data: bytes) -> list[Chunk]:
        if self.config.strategy == ChunkingStrategy.FIXED:
            return self._fixed_chunk(data)
        if self.config.strategy == ChunkingStrategy.VARIABLE:
            return self._variable_chunk(data)
        if self.config.strategy == ChunkingStrategy.RABIN:
            return self._rabin_chunk(data)
        return self._fixed_chunk(data)

    def _fixed_chunk(self, data: bytes) -> list[Chunk]:
        chunks = []
        chunk_size = self.config.chunk_size
        for i in range(0, len(data), chunk_size):
            chunk_data = data[i:i + chunk_size]
            chunk_hash = hashlib.sha256(chunk_data).hexdigest()
            chunks.append(Chunk(
                hash=chunk_hash,
                data=chunk_data,
                size=len(chunk_data),
                offset=i,
            ))
        return chunks

    def _variable_chunk(self, data: bytes) -> list[Chunk]:
        chunks = []
        min_size = self.config.min_chunk_size
        max_size = self.config.max_chunk_size
        target_size = self.config.chunk_size

        i = 0
        while i < len(data):
            remaining = len(data) - i
            if remaining <= max_size:
                chunk_data = data[i:]
            else:
                chunk_end = i + target_size
                chunk_data = data[i:chunk_end]

            chunk_hash = hashlib.sha256(chunk_data).hexdigest()
            chunks.append(Chunk(
                hash=chunk_hash,
                data=chunk_data,
                size=len(chunk_data),
                offset=i,
            ))
            i += len(chunk_data)

        return chunks

    def _rabin_chunk(self, data: bytes) -> list[Chunk]:
        chunks = []
        window_size = 48
        mask = 0xFFFF
        polynomial = 0x100000001

        fingerprint = 0
        i = 0
        chunk_start = 0

        while i < len(data):
            byte = data[i]
            fingerprint = ((fingerprint << 1) & 0xFFFFFFFFFFFFFFFF) | (byte & 1)

            if i - chunk_start >= self.config.min_chunk_size:
                if (fingerprint & mask) == 0 or i - chunk_start >= self.config.max_chunk_size:
                    chunk_data = data[chunk_start:i + 1]
                    chunk_hash = hashlib.sha256(chunk_data).hexdigest()
                    chunks.append(Chunk(
                        hash=chunk_hash,
                        data=chunk_data,
                        size=len(chunk_data),
                        offset=chunk_start,
                    ))
                    chunk_start = i + 1
                    fingerprint = 0

            i += 1

        if chunk_start < len(data):
            chunk_data = data[chunk_start:]
            chunk_hash = hashlib.sha256(chunk_data).hexdigest()
            chunks.append(Chunk(
                hash=chunk_hash,
                data=chunk_data,
                size=len(chunk_data),
                offset=chunk_start,
            ))

        return chunks


class ContentAddressableStore:
    def __init__(self, root_path: str, config: CASConfig = None):
        self.config = config or CASConfig()
        self.root_path = Path(root_path)
        self.root_path.mkdir(parents=True, exist_ok=True)

        self.chunks_dir = self.root_path / "chunks"
        self.chunks_dir.mkdir(exist_ok=True)
        self.blobs_dir = self.root_path / "blobs"
        self.blobs_dir.mkdir(exist_ok=True)

        self.chunker = Chunker(self.config)
        self.chunk_index: dict[str, Chunk] = {}
        self.blob_index: dict[str, Blob] = {}
        self.ref_counts: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def put(self, data: bytes, metadata: dict[str, Any] = None) -> Blob:
        async with self._lock:
            chunks = self.chunker.chunk(data)
            blob_chunks = []
            blob_hash_parts = []

            for chunk in chunks:
                blob_hash_parts.append(chunk.hash)

                if self.config.enable_deduplication and chunk.hash in self.chunk_index:
                    self.ref_counts[chunk.hash] += 1
                    blob_chunks.append(self.chunk_index[chunk.hash])
                else:
                    self.chunk_index[chunk.hash] = chunk
                    self.ref_counts[chunk.hash] = 1
                    await self._store_chunk(chunk)
                    blob_chunks.append(chunk)

            blob_hash = hashlib.sha256(''.join(blob_hash_parts).encode()).hexdigest()

            blob = Blob(
                blob_id=blob_hash,
                chunks=blob_chunks,
                total_size=len(data),
                metadata=metadata or {},
            )

            self.blob_index[blob_hash] = blob
            await self._store_blob(blob)

            return blob

    async def _store_chunk(self, chunk: Chunk):
        chunk_dir = self.chunks_dir / chunk.hash[:2]
        chunk_dir.mkdir(exist_ok=True)
        chunk_file = chunk_dir / chunk.hash[2:]
        if not chunk_file.exists():
            chunk_file.write_bytes(chunk.data)

    async def _store_blob(self, blob: Blob):
        blob_dir = self.blobs_dir / blob.blob_id[:2]
        blob_dir.mkdir(exist_ok=True)
        blob_file = blob_dir / blob.blob_id[2:]
        blob_file.write_text(json.dumps(blob.to_dict()))

    async def get(self, blob_id: str) -> bytes | None:
        if blob_id not in self.blob_index:
            await self._load_blob(blob_id)

        if blob_id not in self.blob_index:
            return None

        blob = self.blob_index[blob_id]
        data_parts = []

        for chunk in blob.chunks:
            chunk_data = await self._load_chunk(chunk.hash)
            if chunk_data is None:
                return None
            data_parts.append(chunk_data)

        return b''.join(data_parts)

    async def _load_blob(self, blob_id: str) -> bool:
        blob_dir = self.blobs_dir / blob_id[:2]
        blob_file = blob_dir / blob_id[2:]
        if blob_file.exists():
            data = json.loads(blob_file.read_text())
            blob = Blob(
                blob_id=data["blob_id"],
                total_size=data["total_size"],
                created_at=data["created_at"],
                metadata=data["metadata"],
            )
            for chunk_data in data["chunks"]:
                chunk_hash = chunk_data["hash"]
                if chunk_hash in self.chunk_index:
                    blob.chunks.append(self.chunk_index[chunk_hash])
                else:
                    chunk = await self._load_chunk_meta(chunk_hash)
                    if chunk:
                        blob.chunks.append(chunk)
            self.blob_index[blob_id] = blob
            return True
        return False

    async def _load_chunk(self, chunk_hash: str) -> bytes | None:
        if chunk_hash in self.chunk_index:
            return self.chunk_index[chunk_hash].data

        chunk = await self._load_chunk_meta(chunk_hash)
        if chunk:
            self.chunk_index[chunk_hash] = chunk
            return chunk.data
        return None

    async def _load_chunk_meta(self, chunk_hash: str) -> Chunk | None:
        chunk_dir = self.chunks_dir / chunk_hash[:2]
        chunk_file = chunk_dir / chunk_hash[2:]
        if chunk_file.exists():
            data = chunk_file.read_bytes()
            chunk = Chunk(
                hash=chunk_hash,
                data=data,
                size=len(data),
                offset=0,
            )
            self.chunk_index[chunk_hash] = chunk
            return chunk
        return None

    async def delete(self, blob_id: str) -> bool:
        async with self._lock:
            if blob_id not in self.blob_index:
                await self._load_blob(blob_id)

            if blob_id not in self.blob_index:
                return False

            blob = self.blob_index[blob_id]

            for chunk in blob.chunks:
                self.ref_counts[chunk.hash] -= 1
                if self.ref_counts[chunk.hash] <= 0:
                    del self.ref_counts[chunk.hash]
                    del self.chunk_index[chunk.hash]
                    await self._delete_chunk(chunk.hash)

            del self.blob_index[blob_id]
            await self._delete_blob(blob_id)
            return True

    async def _delete_chunk(self, chunk_hash: str):
        chunk_dir = self.chunks_dir / chunk_hash[:2]
        chunk_file = chunk_dir / chunk_hash[2:]
        if chunk_file.exists():
            chunk_file.unlink()

    async def _delete_blob(self, blob_id: str):
        blob_dir = self.blobs_dir / blob_id[:2]
        blob_file = blob_dir / blob_id[2:]
        if blob_file.exists():
            blob_file.unlink()

    async def exists(self, blob_id: str) -> bool:
        if blob_id in self.blob_index:
            return True
        return await self._load_blob(blob_id)

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_chunks": len(self.chunk_index),
            "total_blobs": len(self.blob_index),
            "unique_chunks": len(self.chunk_index),
            "deduplication_ratio": sum(self.ref_counts.values()) / max(len(self.chunk_index), 1),
            "total_size": sum(b.total_size for b in self.blob_index.values()),
        }


class BlobStore:
    def __init__(self, cas: ContentAddressableStore):
        self.cas = cas

    async def put_blob(self, data: bytes, metadata: dict[str, Any] = None) -> Blob:
        return await self.cas.put(data, metadata)

    async def get_blob(self, blob_id: str) -> bytes | None:
        return await self.cas.get(blob_id)

    async def delete_blob(self, blob_id: str) -> bool:
        return await self.cas.delete(blob_id)

    async def list_blobs(self, prefix: str = "") -> list[Blob]:
        results = []
        for blob_id, blob in self.cas.blob_index.items():
            if blob_id.startswith(prefix):
                results.append(blob)
        return results


class DeltaSync:
    def __init__(self, cas: ContentAddressableStore):
        self.cas = cas

    async def create_delta(self, old_blob_id: str, new_data: bytes) -> dict[str, Any]:
        old_data = await self.cas.get(old_blob_id)
        if old_data is None:
            return {"type": "full", "data": new_data}

        old_chunks = self.cas.chunker.chunk(old_data)
        new_chunks = self.cas.chunker.chunk(new_data)

        old_hashes = {c.hash: c for c in old_chunks}
        new_hashes = {c.hash: c for c in new_chunks}

        added = []
        removed = []

        for hash_val, chunk in new_hashes.items():
            if hash_val not in old_hashes:
                added.append({"offset": chunk.offset, "hash": chunk.hash, "data": chunk.data})

        for hash_val in old_hashes:
            if hash_val not in new_hashes:
                removed.append({"hash": hash_val})

        if not added and not removed:
            return {"type": "unchanged"}

        return {
            "type": "delta",
            "base_blob": old_blob_id,
            "added": added,
            "removed": removed,
        }

    async def apply_delta(self, delta: dict[str, Any]) -> bytes:
        if delta["type"] == "full":
            return delta["data"]
        if delta["type"] == "unchanged":
            return await self.cas.get(delta["base_blob"])
        if delta["type"] == "delta":
            base_data = await self.cas.get(delta["base_blob"])
            if base_data is None:
                raise ValueError("Base blob not found")

            result = bytearray(base_data)

            for removed in delta["removed"]:
                pass

            for added in delta["added"]:
                pass

            return bytes(result)


class GarbageCollector:
    def __init__(self, cas: ContentAddressableStore):
        self.cas = cas

    async def collect(self, dry_run: bool = False) -> dict[str, Any]:
        orphaned_chunks = []
        for chunk_hash, count in self.cas.ref_counts.items():
            if count <= 0:
                orphaned_chunks.append(chunk_hash)

        if not dry_run:
            for chunk_hash in orphaned_chunks:
                await self.cas._delete_chunk(chunk_hash)
                if chunk_hash in self.cas.chunk_index:
                    del self.cas.chunk_index[chunk_hash]
                del self.cas.ref_counts[chunk_hash]

        return {
            "orphaned_chunks": len(orphaned_chunks),
            "freed_space": sum(
                self.cas.chunk_index.get(h, Chunk(h, b"", 0, 0)).size
                for h in orphaned_chunks
            ),
            "dry_run": dry_run,
        }
