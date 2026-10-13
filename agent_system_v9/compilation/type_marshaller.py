"""
Type Marshaller - Cross-language type conversion and serialization
"""
import json
import struct
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional


class TypeKind(Enum):
    PRIMITIVE = "primitive"
    COMPOSITE = "composite"
    ARRAY = "array"
    MAP = "map"
    OPTIONAL = "optional"
    UNION = "union"
    ENUM = "enum"
    CUSTOM = "custom"


@dataclass
class TypeInfo:
    name: str
    kind: TypeKind
    python_type: type | None = None
    fields: dict[str, 'TypeInfo'] = field(default_factory=dict)
    item_type: Optional['TypeInfo'] = None
    key_type: Optional['TypeInfo'] = None
    value_type: Optional['TypeInfo'] = None
    union_types: list['TypeInfo'] = field(default_factory=list)
    enum_values: list[Any] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class Marshaller(ABC):
    @abstractmethod
    def marshal(self, value: Any, type_info: TypeInfo) -> bytes:
        pass

    @abstractmethod
    def unmarshal(self, data: bytes, type_info: TypeInfo) -> Any:
        pass


class JSONMarshaller(Marshaller):
    def marshal(self, value: Any, type_info: TypeInfo) -> bytes:
        return json.dumps(self._to_json_serializable(value), separators=(',', ':')).encode()

    def unmarshal(self, data: bytes, type_info: TypeInfo) -> Any:
        return json.loads(data.decode())

    def _to_json_serializable(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Decimal) or isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, Enum):
            return value.value
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, dict):
            return {k: self._to_json_serializable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._to_json_serializable(v) for v in value]
        if hasattr(value, '__dict__'):
            return self._to_json_serializable(value.__dict__)
        return str(value)


class BinaryMarshaller(Marshaller):
    def __init__(self) -> None:
        self.type_registry: dict[str, TypeInfo] = {}
        self._offset = 0
        self._data = b''
        self._register_primitives()

    def _register_primitives(self) -> None:
        primitives = {
            'bool': TypeInfo('bool', TypeKind.PRIMITIVE, bool),
            'int8': TypeInfo('int8', TypeKind.PRIMITIVE, int),
            'int16': TypeInfo('int16', TypeKind.PRIMITIVE, int),
            'int32': TypeInfo('int32', TypeKind.PRIMITIVE, int),
            'int64': TypeInfo('int64', TypeKind.PRIMITIVE, int),
            'uint8': TypeInfo('uint8', TypeKind.PRIMITIVE, int),
            'uint16': TypeInfo('uint16', TypeKind.PRIMITIVE, int),
            'uint32': TypeInfo('uint32', TypeKind.PRIMITIVE, int),
            'uint64': TypeInfo('uint64', TypeKind.PRIMITIVE, int),
            'float32': TypeInfo('float32', TypeKind.PRIMITIVE, float),
            'float64': TypeInfo('float64', TypeKind.PRIMITIVE, float),
            'string': TypeInfo('string', TypeKind.PRIMITIVE, str),
            'bytes': TypeInfo('bytes', TypeKind.PRIMITIVE, bytes),
        }
        for name, info in primitives.items():
            self.type_registry[name] = info

    def register_type(self, type_info: TypeInfo) -> None:
        self.type_registry[type_info.name] = type_info

    def marshal(self, value: Any, type_info: TypeInfo) -> bytes:
        if type_info.kind == TypeKind.PRIMITIVE:
            return self._marshal_primitive(value, type_info)
        if type_info.kind == TypeKind.COMPOSITE:
            return self._marshal_composite(value, type_info)
        if type_info.kind == TypeKind.ARRAY:
            return self._marshal_array(value, type_info)
        if type_info.kind == TypeKind.MAP:
            return self._marshal_map(value, type_info)
        if type_info.kind == TypeKind.OPTIONAL:
            return self._marshal_optional(value, type_info)
        return b''

    def _marshal_primitive(self, value: Any, type_info: TypeInfo) -> bytes:
        name = type_info.name
        if name == 'bool':
            return struct.pack('?', value)
        if name == 'int8':
            return struct.pack('b', value)
        if name == 'int16':
            return struct.pack('h', value)
        if name == 'int32':
            return struct.pack('i', value)
        if name == 'int64':
            return struct.pack('q', value)
        if name == 'uint8':
            return struct.pack('B', value)
        if name == 'uint16':
            return struct.pack('H', value)
        if name == 'uint32':
            return struct.pack('I', value)
        if name == 'uint64':
            return struct.pack('Q', value)
        if name == 'float32':
            return struct.pack('f', value)
        if name == 'float64':
            return struct.pack('d', value)
        if name == 'string':
            encoded = value.encode('utf-8')
            return struct.pack('I', len(encoded)) + encoded
        if name == 'bytes':
            return struct.pack('I', len(value)) + value
        return b''

    def _marshal_composite(self, value: Any, type_info: TypeInfo) -> bytes:
        result = b''
        for field_name, field_info in type_info.fields.items():
            field_value = getattr(value, field_name, None) if not isinstance(value, dict) else value.get(field_name)
            if field_value is None:
                result += struct.pack('?', False)
            else:
                result += struct.pack('?', True)
                result += self.marshal(field_value, field_info)
        return result

    def _marshal_array(self, value: list, type_info: TypeInfo) -> bytes:
        result = struct.pack('I', len(value))
        for item in value:
            result += self.marshal(item, type_info.item_type)
        return result

    def _marshal_map(self, value: dict, type_info: TypeInfo) -> bytes:
        result = struct.pack('I', len(value))
        for k, v in value.items():
            result += self.marshal(k, type_info.key_type)
            result += self.marshal(v, type_info.value_type)
        return result

    def _marshal_optional(self, value: Any, type_info: TypeInfo) -> bytes:
        if value is None:
            return struct.pack('?', False)
        return struct.pack('?', True) + self.marshal(value, type_info.union_types[0])

    def unmarshal(self, data: bytes, type_info: TypeInfo) -> Any:
        self._offset = 0
        self._data = data
        return self._unmarshal_value(type_info)

    def _unmarshal_value(self, type_info: TypeInfo) -> Any:
        if type_info.kind == TypeKind.PRIMITIVE:
            return self._unmarshal_primitive(type_info)
        if type_info.kind == TypeKind.COMPOSITE:
            return self._unmarshal_composite(type_info)
        if type_info.kind == TypeKind.ARRAY:
            return self._unmarshal_array(type_info)
        if type_info.kind == TypeKind.MAP:
            return self._unmarshal_map(type_info)
        if type_info.kind == TypeKind.OPTIONAL:
            return self._unmarshal_optional(type_info)
        return None

    def _read(self, fmt: str) -> Any:
        size = struct.calcsize(fmt)
        value = struct.unpack(fmt, self._data[self._offset:self._offset + size])[0]
        self._offset += size
        return value

    def _unmarshal_primitive(self, type_info: TypeInfo) -> Any:
        name = type_info.name
        if name == 'bool':
            return self._read('?')
        if name == 'int8':
            return self._read('b')
        if name == 'int16':
            return self._read('h')
        if name == 'int32':
            return self._read('i')
        if name == 'int64':
            return self._read('q')
        if name == 'uint8':
            return self._read('B')
        if name == 'uint16':
            return self._read('H')
        if name == 'uint32':
            return self._read('I')
        if name == 'uint64':
            return self._read('Q')
        if name == 'float32':
            return self._read('f')
        if name == 'float64':
            return self._read('d')
        if name == 'string':
            length = self._read('I')
            value = self._data[self._offset:self._offset + length].decode('utf-8')
            self._offset += length
            return value
        if name == 'bytes':
            length = self._read('I')
            value = self._data[self._offset:self._offset + length]
            self._offset += length
            return value
        return None

    def _unmarshal_composite(self, type_info: TypeInfo) -> Any:
        result: dict[str, Any] = {}
        for field_name, field_info in type_info.fields.items():
            present = self._read('?')
            if present:
                result[field_name] = self._unmarshal_value(field_info)
            else:
                result[field_name] = None
        return result

    def _unmarshal_array(self, type_info: TypeInfo) -> list:
        length = self._read('I')
        result = []
        for _ in range(length):
            result.append(self._unmarshal_value(type_info.item_type))
        return result

    def _unmarshal_map(self, type_info: TypeInfo) -> dict:
        length = self._read('I')
        result: dict[Any, Any] = {}
        for _ in range(length):
            key = self._unmarshal_value(type_info.key_type)
            value = self._unmarshal_value(type_info.value_type)
            result[key] = value
        return result

    def _unmarshal_optional(self, type_info: TypeInfo) -> Any:
        present = self._read('?')
        if not present:
            return None
        return self._unmarshal_value(type_info.union_types[0])


class TypeMarshaller:
    def __init__(self) -> None:
        self.marshallers: dict[str, Marshaller] = {
            'json': JSONMarshaller(),
            'binary': BinaryMarshaller(),
        }
        self.type_registry: dict[str, TypeInfo] = {}
        self._register_default_types()

    def _register_default_types(self) -> None:
        self.register_type(TypeInfo('bool', TypeKind.PRIMITIVE, bool))
        self.register_type(TypeInfo('int', TypeKind.PRIMITIVE, int))
        self.register_type(TypeInfo('float', TypeKind.PRIMITIVE, float))
        self.register_type(TypeInfo('str', TypeKind.PRIMITIVE, str))
        self.register_type(TypeInfo('bytes', TypeKind.PRIMITIVE, bytes))
        self.register_type(TypeInfo('datetime', TypeKind.PRIMITIVE, datetime))
        self.register_type(TypeInfo('uuid', TypeKind.PRIMITIVE, uuid.UUID))

    def register_marshaller(self, name: str, marshaller: Marshaller) -> None:
        self.marshallers[name] = marshaller

    def register_type(self, type_info: TypeInfo) -> None:
        self.type_registry[type_info.name] = type_info
        if 'binary' in self.marshallers:
            self.marshallers['binary'].register_type(type_info)

    def get_type_info(self, python_type: type) -> TypeInfo | None:
        for info in self.type_registry.values():
            if info.python_type == python_type:
                return info
        return None

    def marshal(self, value: Any, format: str = 'json', type_info: TypeInfo | None = None) -> bytes:
        if format not in self.marshallers:
            raise ValueError(f"Unknown format: {format}")

        if type_info is None:
            type_info = self._infer_type_info(value)

        return self.marshallers[format].marshal(value, type_info)

    def unmarshal(self, data: bytes, format: str = 'json', type_info: TypeInfo | None = None) -> Any:
        if format not in self.marshallers:
            raise ValueError(f"Unknown format: {format}")

        if type_info is None:
            raise ValueError("Type info required for unmarshaling")

        return self.marshallers[format].unmarshal(data, type_info)

    def _infer_type_info(self, value: Any) -> TypeInfo:
        if value is None:
            return TypeInfo('null', TypeKind.PRIMITIVE, type(None))
        if isinstance(value, bool):
            return self.type_registry['bool']
        if isinstance(value, int):
            return self.type_registry['int']
        if isinstance(value, float):
            return self.type_registry['float']
        if isinstance(value, str):
            return self.type_registry['str']
        if isinstance(value, bytes):
            return self.type_registry['bytes']
        if isinstance(value, datetime):
            return self.type_registry['datetime']
        if isinstance(value, uuid.UUID):
            return self.type_registry['uuid']
        if isinstance(value, list):
            item_info = self._infer_type_info(value[0]) if value else TypeInfo('any', TypeKind.PRIMITIVE)
            return TypeInfo('list', TypeKind.ARRAY, list, item_type=item_info)
        if isinstance(value, dict):
            key_info = self._infer_type_info(next(iter(value.keys()))) if value else TypeInfo('any', TypeKind.PRIMITIVE)
            val_info = self._infer_type_info(next(iter(value.values()))) if value else TypeInfo('any', TypeKind.PRIMITIVE)
            return TypeInfo('dict', TypeKind.MAP, dict, key_type=key_info, value_type=val_info)
        if is_dataclass(value):
            fields = {}
            for f in value.__dataclass_fields__.values():
                fields[f.name] = self._infer_type_info(getattr(value, f.name))
            return TypeInfo(value.__class__.__name__, TypeKind.COMPOSITE, value.__class__, fields=fields)
        if isinstance(value, Enum):
            return TypeInfo(value.__class__.__name__, TypeKind.ENUM, value.__class__, enum_values=[e.value for e in value.__class__])
        return TypeInfo('any', TypeKind.PRIMITIVE, type(value))

    def convert(self, value: Any, target_format: str, source_format: str = 'json') -> bytes:
        type_info = self._infer_type_info(value)
        return self.marshal(value, target_format, type_info)


class SchemaValidator:
    def __init__(self, marshaller: TypeMarshaller) -> None:
        self.marshaller = marshaller

    def validate(self, value: Any, type_info: TypeInfo) -> list[str]:
        errors: list[str] = []
        self._validate_value(value, type_info, "", errors)
        return errors

    def _validate_value(self, value: Any, type_info: TypeInfo, path: str, errors: list[str]) -> None:
        if type_info.kind == TypeKind.PRIMITIVE:
            if not self._check_primitive(value, type_info):
                errors.append(f"{path}: expected {type_info.name}, got {type(value).__name__}")
        elif type_info.kind == TypeKind.COMPOSITE:
            if not isinstance(value, dict) and not hasattr(value, '__dict__'):
                errors.append(f"{path}: expected object, got {type(value).__name__}")
            else:
                obj = value if isinstance(value, dict) else value.__dict__
                for field_name, field_info in type_info.fields.items():
                    if field_name not in obj:
                        errors.append(f"{path}.{field_name}: missing required field")
                    else:
                        self._validate_value(obj[field_name], field_info, f"{path}.{field_name}", errors)
        elif type_info.kind == TypeKind.ARRAY:
            if not isinstance(value, list):
                errors.append(f"{path}: expected array, got {type(value).__name__}")
            else:
                for i, item in enumerate(value):
                    self._validate_value(item, type_info.item_type, f"{path}[{i}]", errors)
        elif type_info.kind == TypeKind.MAP:
            if not isinstance(value, dict):
                errors.append(f"{path}: expected map, got {type(value).__name__}")
            else:
                for k, v in value.items():
                    self._validate_value(k, type_info.key_type, f"{path}.key", errors)
                    self._validate_value(v, type_info.value_type, f"{path}.value", errors)
        elif type_info.kind == TypeKind.ENUM:
            if value not in type_info.enum_values:
                errors.append(f"{path}: invalid enum value {value}, allowed: {type_info.enum_values}")

    def _check_primitive(self, value: Any, type_info: TypeInfo) -> bool:
        if type_info.python_type is None:
            return True
        if type_info.name == 'int' and isinstance(value, bool):
            return False
        return isinstance(value, type_info.python_type)


class CrossLanguageTypeMapper:
    def __init__(self) -> None:
        self.mappings: dict[str, dict[str, str]] = {
            'python': {
                'int': 'int64',
                'float': 'float64',
                'str': 'string',
                'bool': 'bool',
                'bytes': 'bytes',
                'list': 'array',
                'dict': 'map',
            },
            'typescript': {
                'int64': 'number',
                'float64': 'number',
                'string': 'string',
                'bool': 'boolean',
                'bytes': 'Uint8Array',
                'array': 'Array',
                'map': 'Record',
            },
            'rust': {
                'int64': 'i64',
                'float64': 'f64',
                'string': 'String',
                'bool': 'bool',
                'bytes': 'Vec<u8>',
                'array': 'Vec',
                'map': 'HashMap',
            },
            'go': {
                'int64': 'int64',
                'float64': 'float64',
                'string': 'string',
                'bool': 'bool',
                'bytes': '[]byte',
                'array': '[]',
                'map': 'map',
            },
        }

    def map_type(self, source_lang: str, target_lang: str, type_name: str) -> str:
        source_map = self.mappings.get(source_lang, {})
        canonical = source_map.get(type_name, type_name)

        target_map = self.mappings.get(target_lang, {})
        return target_map.get(canonical, canonical)

    def add_mapping(self, source_lang: str, source_type: str, target_lang: str, target_type: str) -> None:
        if source_lang not in self.mappings:
            self.mappings[source_lang] = {}
        self.mappings[source_lang][source_type] = target_type