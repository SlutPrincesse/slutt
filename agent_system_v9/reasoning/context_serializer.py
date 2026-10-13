import json
import uuid
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path


class SerializationFormat(Enum):
    JSON = "json"
    MSGPACK = "msgpack"
    PICKLE = "pickle"
    YAML = "yaml"


@dataclass
class SerializedContext:
    id: str
    session_id: str
    format: SerializationFormat
    data: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    size_bytes: int = 0
    checksum: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:12]


class ContextSerializer:
    def __init__(self, default_format: SerializationFormat = SerializationFormat.JSON):
        self.default_format = default_format
        self._serializers = {
            SerializationFormat.JSON: self._serialize_json,
            SerializationFormat.MSGPACK: self._serialize_msgpack,
            SerializationFormat.PICKLE: self._serialize_pickle,
            SerializationFormat.YAML: self._serialize_yaml,
        }
        self._deserializers = {
            SerializationFormat.JSON: self._deserialize_json,
            SerializationFormat.MSGPACK: self._deserialize_msgpack,
            SerializationFormat.PICKLE: self._deserialize_pickle,
            SerializationFormat.YAML: self._deserialize_yaml,
        }

    def _serialize_json(self, data: Dict[str, Any]) -> bytes:
        return json.dumps(data, default=str).encode()

    def _deserialize_json(self, data: bytes) -> Dict[str, Any]:
        return json.loads(data.decode())

    def _serialize_msgpack(self, data: Dict[str, Any]) -> bytes:
        try:
            import msgpack
            return msgpack.packb(data, use_bin_type=True)
        except ImportError:
            return self._serialize_json(data)

    def _deserialize_msgpack(self, data: bytes) -> Dict[str, Any]:
        try:
            import msgpack
            return msgpack.unpackb(data, raw=False)
        except ImportError:
            return self._deserialize_json(data)

    def _serialize_pickle(self, data: Dict[str, Any]) -> bytes:
        import pickle
        return pickle.dumps(data)

    def _deserialize_pickle(self, data: bytes) -> Dict[str, Any]:
        import pickle
        return pickle.loads(data)

    def _serialize_yaml(self, data: Dict[str, Any]) -> bytes:
        try:
            import yaml
            return yaml.dump(data).encode()
        except ImportError:
            return self._serialize_json(data)

    def _deserialize_yaml(self, data: bytes) -> Dict[str, Any]:
        try:
            import yaml
            return yaml.safe_load(data.decode())
        except ImportError:
            return self._deserialize_json(data)

    def serialize(
        self,
        session_id: str,
        context_data: Dict[str, Any],
        format: SerializationFormat = None,
        metadata: Dict[str, Any] = None,
    ) -> SerializedContext:
        fmt = format or self.default_format
        serializer = self._serializers[fmt]
        data_bytes = serializer(context_data)
        
        import hashlib
        checksum = hashlib.sha256(data_bytes).hexdigest()[:16]
        
        return SerializedContext(
            id="",
            session_id=session_id,
            format=fmt,
            data=context_data,
            metadata=metadata or {},
            size_bytes=len(data_bytes),
            checksum=checksum,
        )

    def deserialize(self, serialized: SerializedContext) -> Dict[str, Any]:
        deserializer = self._deserializers[serialized.format]
        return deserializer(json.dumps(serialized.data).encode())

    def to_bytes(self, serialized: SerializedContext) -> bytes:
        serializer = self._serializers[serialized.format]
        return serializer(serialized.data)

    def from_bytes(self, data: bytes, format: SerializationFormat = None) -> Dict[str, Any]:
        fmt = format or self.default_format
        deserializer = self._deserializers[fmt]
        return deserializer(data)

    def save(self, serialized: SerializedContext, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "id": serialized.id,
            "session_id": serialized.session_id,
            "format": serialized.format.value,
            "data": serialized.data,
            "metadata": serialized.metadata,
            "created_at": serialized.created_at,
            "size_bytes": serialized.size_bytes,
            "checksum": serialized.checksum,
        }
        path.write_text(json.dumps(data, indent=2))

    def load(self, path: Path) -> SerializedContext:
        data = json.loads(path.read_text())
        return SerializedContext(
            id=data["id"],
            session_id=data["session_id"],
            format=SerializationFormat(data["format"]),
            data=data["data"],
            metadata=data["metadata"],
            created_at=data["created_at"],
            size_bytes=data["size_bytes"],
            checksum=data["checksum"],
        )

    def verify_checksum(self, serialized: SerializedContext) -> bool:
        data_bytes = self.to_bytes(serialized)
        import hashlib
        checksum = hashlib.sha256(data_bytes).hexdigest()[:16]
        return checksum == serialized.checksum