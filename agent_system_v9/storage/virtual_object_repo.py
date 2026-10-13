"""
Virtual Object Repository - Object storage with versioning
"""
import asyncio
import hashlib
import json
import pickle
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ObjectType(Enum):
    BLOB = "blob"
    TREE = "tree"
    COMMIT = "commit"
    TAG = "tag"
    CUSTOM = "custom"


@dataclass
class ObjectId:
    hash: str
    type: ObjectType = ObjectType.BLOB

    def __str__(self) -> str:
        return self.hash

    def short(self, length: int = 8) -> str:
        return self.hash[:length]


@dataclass
class ObjectMetadata:
    object_id: ObjectId
    size: int
    created_at: float = field(default_factory=time.time)
    tags: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    content_type: str = "application/octet-stream"


@dataclass
class VersionedObject:
    object_id: ObjectId
    versions: list['ObjectVersion'] = field(default_factory=list)
    current_version: int = 0

    def add_version(self, version: 'ObjectVersion'):
        self.versions.append(version)
        self.current_version = len(self.versions) - 1


@dataclass
class ObjectVersion:
    version: int
    object_id: ObjectId
    data: bytes
    metadata: ObjectMetadata
    parent_version: int | None = None
    message: str = ""
    author: str = ""
    timestamp: float = field(default_factory=time.time)


class ObjectStore:
    def __init__(self, root_path: str):
        self.root_path = Path(root_path)
        self.root_path.mkdir(parents=True, exist_ok=True)
        self.objects_dir = self.root_path / "objects"
        self.objects_dir.mkdir(exist_ok=True)
        self.index: dict[str, ObjectId] = {}
        self.versioned: dict[str, VersionedObject] = {}
        self._lock = asyncio.Lock()

    def _compute_hash(self, data: bytes, obj_type: ObjectType = ObjectType.BLOB) -> ObjectId:
        content = f"{obj_type.value} {len(data)}\0".encode() + data
        return ObjectId(hashlib.sha256(content).hexdigest(), obj_type)

    async def put(self, data: bytes, obj_type: ObjectType = ObjectType.BLOB, metadata: ObjectMetadata = None) -> ObjectId:
        obj_id = self._compute_hash(data, obj_type)

        async with self._lock:
            obj_dir = self.objects_dir / obj_id.hash[:2]
            obj_dir.mkdir(exist_ok=True)
            obj_file = obj_dir / obj_id.hash[2:]

            if not obj_file.exists():
                obj_file.write_bytes(data)

            if metadata is None:
                metadata = ObjectMetadata(object_id=obj_id, size=len(data))

            meta_file = obj_dir / f"{obj_id.hash[2:]}.meta"
            meta_file.write_text(json.dumps({
                "object_id": str(obj_id),
                "size": metadata.size,
                "created_at": metadata.created_at,
                "tags": metadata.tags,
                "attributes": metadata.attributes,
                "content_type": metadata.content_type,
            }))

            self.index[str(obj_id)] = obj_id
            return obj_id

    async def get(self, obj_id: ObjectId) -> bytes | None:
        obj_dir = self.objects_dir / obj_id.hash[:2]
        obj_file = obj_dir / obj_id.hash[2:]
        if obj_file.exists():
            return obj_file.read_bytes()
        return None

    async def get_metadata(self, obj_id: ObjectId) -> ObjectMetadata | None:
        obj_dir = self.objects_dir / obj_id.hash[:2]
        meta_file = obj_dir / f"{obj_id.hash[2:]}.meta"
        if meta_file.exists():
            data = json.loads(meta_file.read_text())
            return ObjectMetadata(
                object_id=ObjectId(data["object_id"]),
                size=data["size"],
                created_at=data["created_at"],
                tags=data["tags"],
                attributes=data["attributes"],
                content_type=data["content_type"],
            )
        return None

    async def exists(self, obj_id: ObjectId) -> bool:
        obj_dir = self.objects_dir / obj_id.hash[:2]
        obj_file = obj_dir / obj_id.hash[2:]
        return obj_file.exists()

    async def delete(self, obj_id: ObjectId) -> bool:
        obj_dir = self.objects_dir / obj_id.hash[:2]
        obj_file = obj_dir / obj_id.hash[2:]
        meta_file = obj_dir / f"{obj_id.hash[2:]}.meta"

        deleted = False
        if obj_file.exists():
            obj_file.unlink()
            deleted = True
        if meta_file.exists():
            meta_file.unlink()
            deleted = True

        if str(obj_id) in self.index:
            del self.index[str(obj_id)]

        return deleted

    async def list_objects(self, prefix: str = "") -> list[ObjectId]:
        results = []
        for obj_dir in self.objects_dir.iterdir():
            if obj_dir.is_dir():
                for obj_file in obj_dir.iterdir():
                    if not obj_file.name.endswith('.meta'):
                        obj_hash = obj_dir.name + obj_file.name
                        if obj_hash.startswith(prefix):
                            results.append(ObjectId(obj_hash))
        return results


class VersionedObjectStore(ObjectStore):
    def __init__(self, root_path: str):
        super().__init__(root_path)
        self.versions_dir = self.root_path / "versions"
        self.versions_dir.mkdir(exist_ok=True)

    async def put_versioned(
        self,
        key: str,
        data: bytes,
        message: str = "",
        author: str = "",
        parent_version: int = None,
    ) -> ObjectVersion:
        async with self._lock:
            if key not in self.versioned:
                self.versioned[key] = VersionedObject(object_id=ObjectId(""))

            versioned_obj = self.versioned[key]
            new_version_num = len(versioned_obj.versions)

            obj_id = await self.put(data)

            metadata = ObjectMetadata(object_id=obj_id, size=len(data))
            version = ObjectVersion(
                version=new_version_num,
                object_id=obj_id,
                data=data,
                metadata=metadata,
                parent_version=parent_version if parent_version is not None else (new_version_num - 1 if new_version_num > 0 else None),
                message=message,
                author=author,
            )

            versioned_obj.add_version(version)
            await self._save_versioned(key, versioned_obj)

            return version

    async def get_version(self, key: str, version: int = -1) -> ObjectVersion | None:
        if key not in self.versioned:
            await self._load_versioned(key)

        if key not in self.versioned:
            return None

        versioned_obj = self.versioned[key]
        if version == -1:
            version = versioned_obj.current_version

        if 0 <= version < len(versioned_obj.versions):
            return versioned_obj.versions[version]
        return None

    async def get_latest(self, key: str) -> ObjectVersion | None:
        return await self.get_version(key, -1)

    async def get_history(self, key: str) -> list[ObjectVersion]:
        if key not in self.versioned:
            await self._load_versioned(key)

        if key not in self.versioned:
            return []

        return list(self.versioned[key].versions)

    async def _save_versioned(self, key: str, versioned_obj: VersionedObject):
        version_file = self.versions_dir / f"{key}.json"
        data = {
            "object_id": str(versioned_obj.object_id),
            "current_version": versioned_obj.current_version,
            "versions": [
                {
                    "version": v.version,
                    "object_id": str(v.object_id),
                    "metadata": {
                        "object_id": str(v.metadata.object_id),
                        "size": v.metadata.size,
                        "created_at": v.metadata.created_at,
                        "tags": v.metadata.tags,
                        "attributes": v.metadata.attributes,
                        "content_type": v.metadata.content_type,
                    },
                    "parent_version": v.parent_version,
                    "message": v.message,
                    "author": v.author,
                    "timestamp": v.timestamp,
                }
                for v in versioned_obj.versions
            ],
        }
        version_file.write_text(json.dumps(data))

    async def _load_versioned(self, key: str):
        version_file = self.versions_dir / f"{key}.json"
        if version_file.exists():
            data = json.loads(version_file.read_text())
            versioned_obj = VersionedObject(
                object_id=ObjectId(data["object_id"]),
                current_version=data["current_version"],
            )
            for v_data in data["versions"]:
                versioned_obj.versions.append(ObjectVersion(
                    version=v_data["version"],
                    object_id=ObjectId(v_data["object_id"]),
                    data=b"",
                    metadata=ObjectMetadata(
                        object_id=ObjectId(v_data["metadata"]["object_id"]),
                        size=v_data["metadata"]["size"],
                        created_at=v_data["metadata"]["created_at"],
                        tags=v_data["metadata"]["tags"],
                        attributes=v_data["metadata"]["attributes"],
                        content_type=v_data["metadata"]["content_type"],
                    ),
                    parent_version=v_data["parent_version"],
                    message=v_data["message"],
                    author=v_data["author"],
                    timestamp=v_data["timestamp"],
                ))
            self.versioned[key] = versioned_obj


class VirtualObjectRepository:
    def __init__(self, root_path: str):
        self.store = VersionedObjectStore(root_path)
        self.collections: dict[str, set[str]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def put_object(self, collection: str, key: str, data: bytes, **kwargs) -> ObjectId:
        full_key = f"{collection}/{key}"
        obj_id = await self.store.put(data, **kwargs)

        async with self._lock:
            self.collections[collection].add(key)

        return obj_id

    async def get_object(self, collection: str, key: str) -> bytes | None:
        full_key = f"{collection}/{key}"
        version = await self.store.get_latest(full_key)
        if version:
            return await self.store.get(version.object_id)
        return None

    async def put_versioned_object(
        self,
        collection: str,
        key: str,
        data: bytes,
        message: str = "",
        author: str = "",
    ) -> ObjectVersion:
        full_key = f"{collection}/{key}"

        async with self._lock:
            self.collections[collection].add(key)

        return await self.store.put_versioned(full_key, data, message, author)

    async def get_versioned_object(self, collection: str, key: str, version: int = -1) -> ObjectVersion | None:
        full_key = f"{collection}/{key}"
        return await self.store.get_version(full_key, version)

    async def get_object_history(self, collection: str, key: str) -> list[ObjectVersion]:
        full_key = f"{collection}/{key}"
        return await self.store.get_history(full_key)

    async def list_collection(self, collection: str) -> list[str]:
        return list(self.collections.get(collection, set()))

    async def delete_object(self, collection: str, key: str) -> bool:
        full_key = f"{collection}/{key}"
        version = await self.store.get_latest(full_key)
        if version:
            async with self._lock:
                self.collections[collection].discard(key)
            return await self.store.delete(version.object_id)
        return False


class ObjectSerializer:
    @staticmethod
    def serialize(obj: Any) -> bytes:
        return pickle.dumps(obj)

    @staticmethod
    def deserialize(data: bytes) -> Any:
        return pickle.loads(data)

    @staticmethod
    def serialize_json(obj: Any) -> bytes:
        return json.dumps(obj, default=str).encode()

    @staticmethod
    def deserialize_json(data: bytes) -> Any:
        return json.loads(data.decode())


class ContentAddressableStore:
    def __init__(self, repo: VirtualObjectRepository):
        self.repo = repo

    async def store(self, data: bytes, collection: str = "blobs") -> ObjectId:
        return await self.repo.put_object(collection, "", data)

    async def retrieve(self, obj_id: ObjectId) -> bytes | None:
        return await self.repo.store.get(obj_id)

    async def store_json(self, obj: Any, collection: str = "json") -> ObjectId:
        data = ObjectSerializer.serialize_json(obj)
        return await self.store(data, collection)

    async def retrieve_json(self, obj_id: ObjectId) -> Any:
        data = await self.retrieve(obj_id)
        if data:
            return ObjectSerializer.deserialize_json(data)
        return None
