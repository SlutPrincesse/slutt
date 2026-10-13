"""
Protocol Compiler - Compiles protocol definitions to code
"""
import json
import re
from typing import Dict, List, Optional, Any, Set, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from collections import defaultdict
import hashlib


class ProtocolType(Enum):
    REST = "rest"
    GRPC = "grpc"
    GRAPHQL = "graphql"
    WEBSOCKET = "websocket"
    MQTT = "mqtt"
    AMQP = "amqp"
    CUSTOM = "custom"


class FieldType(Enum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    ENUM = "enum"
    BYTES = "bytes"
    TIMESTAMP = "timestamp"
    UUID = "uuid"
    ANY = "any"


@dataclass
class ProtocolField:
    name: str
    field_type: FieldType
    required: bool = True
    default: Any = None
    description: str = ""
    constraints: Dict[str, Any] = field(default_factory=dict)
    enum_values: List[Any] = field(default_factory=list)
    nested_fields: List['ProtocolField'] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "field_type": self.field_type.value,
            "required": self.required,
            "default": self.default,
            "description": self.description,
            "constraints": self.constraints,
            "enum_values": self.enum_values,
            "nested_fields": [f.to_dict() for f in self.nested_fields],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProtocolField':
        return cls(
            name=data["name"],
            field_type=FieldType(data["field_type"]),
            required=data.get("required", True),
            default=data.get("default"),
            description=data.get("description", ""),
            constraints=data.get("constraints", {}),
            enum_values=data.get("enum_values", []),
            nested_fields=[cls.from_dict(f) for f in data.get("nested_fields", [])],
        )


@dataclass
class ProtocolMethod:
    name: str
    protocol_type: ProtocolType
    path: str
    http_method: str = "POST"
    request_fields: List[ProtocolField] = field(default_factory=list)
    response_fields: List[ProtocolField] = field(default_factory=list)
    error_fields: List[ProtocolField] = field(default_factory=list)
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "protocol_type": self.protocol_type.value,
            "path": self.path,
            "http_method": self.http_method,
            "request_fields": [f.to_dict() for f in self.request_fields],
            "response_fields": [f.to_dict() for f in self.response_fields],
            "error_fields": [f.to_dict() for f in self.error_fields],
            "description": self.description,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProtocolMethod':
        return cls(
            name=data["name"],
            protocol_type=ProtocolType(data["protocol_type"]),
            path=data["path"],
            http_method=data.get("http_method", "POST"),
            request_fields=[ProtocolField.from_dict(f) for f in data.get("request_fields", [])],
            response_fields=[ProtocolField.from_dict(f) for f in data.get("response_fields", [])],
            error_fields=[ProtocolField.from_dict(f) for f in data.get("error_fields", [])],
            description=data.get("description", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ProtocolDefinition:
    name: str
    version: str
    protocol_type: ProtocolType
    base_url: str = ""
    methods: List[ProtocolMethod] = field(default_factory=list)
    types: Dict[str, List[ProtocolField]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "protocol_type": self.protocol_type.value,
            "base_url": self.base_url,
            "methods": [m.to_dict() for m in self.methods],
            "types": {k: [f.to_dict() for f in v] for k, v in self.types.items()},
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProtocolDefinition':
        return cls(
            name=data["name"],
            version=data["version"],
            protocol_type=ProtocolType(data["protocol_type"]),
            base_url=data.get("base_url", ""),
            methods=[ProtocolMethod.from_dict(m) for m in data.get("methods", [])],
            types={k: [ProtocolField.from_dict(f) for f in v] for k, v in data.get("types", {}).items()},
            metadata=data.get("metadata", {}),
        )


class ProtocolCompiler:
    def __init__(self):
        self.templates: Dict[str, str] = {}
        self._load_default_templates()

    def _load_default_templates(self):
        self.templates["python_client"] = '''
class {{class_name}}Client:
    def __init__(self, base_url: str = "{{base_url}}", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    {% for method in methods %}
    def {{method.name}}(self{% for field in method.request_fields %}, {{field.name}}: {{field.field_type.value}}{% endfor %}) -> Dict[str, Any]:
        """{{method.description}}"""
        url = f"{self.base_url}{{method.path}}"
        payload = {{% for field in method.request_fields %}"{{field.name}}": {{field.name}}{% if not loop.last %}, {% endif %}{% endfor %}}
        response = self.session.{{method.http_method.lower()}}(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    {% endfor %}
'''

        self.templates["python_server"] = '''
class {{class_name}}Server:
    def __init__(self):
        self.app = FastAPI(title="{{protocol.name}}", version="{{protocol.version}}")
        self._setup_routes()

    def _setup_routes(self):
        {% for method in methods %}
        @self.app.{{method.http_method.lower()}}("{{method.path}}")
        async def {{method.name}}(request: {{method.name}}Request) -> {{method.name}}Response:
            return await self.{{method.name}}_handler(request)

    {% for method in methods %}
    async def {{method.name}}_handler(self, request: {{method.name}}Request) -> {{method.name}}Response:
        """{{method.description}}"""
        raise NotImplementedError
    {% endfor %}
'''

        self.templates["typescript_client"] = '''
export class {{class_name}}Client {
    constructor(private baseUrl: string = "{{base_url}}", private timeout: number = 30000) {}

    {% for method in methods %}
    async {{method.name}}({% for field in method.request_fields %}{{field.name}}: {{this._ts_type(field)}}{% if not loop.last %}, {% endif %}{% endfor %}): Promise<{{this._response_type(method)}}> {
        const url = `${{this.baseUrl}}{{method.path}}`;
        const payload = { {% for field in method.request_fields %}{{field.name}}{% if not loop.last %}, {% endif %}{% endfor %} };
        const response = await fetch(url, {
            method: "{{method.http_method}}",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
            signal: AbortSignal.timeout(this.timeout),
        });
        if (!response.ok) throw new Error(await response.text());
        return response.json();
    }
    {% endfor %}

    private _ts_type(field: ProtocolField): string {
        switch (field.field_type) {
            case "string": return "string";
            case "integer": return "number";
            case "float": return "number";
            case "boolean": return "boolean";
            case "array": return "any[]";
            case "object": return "Record<string, any>";
            default: return "any";
        }
    }

    private _response_type(method: ProtocolMethod): string {
        return `{{method.name}}Response`;
    }
}
'''

    def compile(self, protocol: ProtocolDefinition, target: str, **kwargs) -> str:
        if target not in self.templates:
            raise ValueError(f"Unknown target: {target}")
        
        template = self.templates[target]
        return self._render(template, protocol=protocol, **kwargs)

    def _render(self, template: str, **context) -> str:
        def replace_var(match):
            expr = match.group(1).strip()
            try:
                return str(eval(expr, {}, context))
            except Exception:
                return match.group(0)
        
        result = re.sub(r'\{\{(.+?)\}\}', replace_var, template)
        
        def replace_for(match):
            var = match.group(1).strip()
            body = match.group(2)
            iterable = eval(var.split('in')[1].strip(), {}, context)
            var_name = var.split('in')[0].strip().replace('for ', '')
            output = []
            for item in iterable:
                context[var_name] = item
                output.append(self._render(body, **context))
            return ''.join(output)
        
        result = re.sub(r'\{% for (.+?) %\}(.+?)\{% endfor %\}', replace_for, result, flags=re.DOTALL)
        return result

    def compile_all(self, protocol: ProtocolDefinition, targets: List[str], output_dir: str) -> Dict[str, str]:
        results = {}
        for target in targets:
            code = self.compile(protocol, target)
            ext = self._get_extension(target)
            file_path = Path(output_dir) / f"{protocol.name}_{protocol.version}_{target}.{ext}"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(code)
            results[target] = str(file_path)
        return results

    def _get_extension(self, target: str) -> str:
        mapping = {
            "python_client": "py",
            "python_server": "py",
            "typescript_client": "ts",
        }
        return mapping.get(target, "txt")

    def add_template(self, name: str, template: str):
        self.templates[name] = template

    def parse_openapi(self, spec: Dict[str, Any]) -> ProtocolDefinition:
        methods = []
        for path, path_item in spec.get("paths", {}).items():
            for http_method, operation in path_item.items():
                if http_method not in ("get", "post", "put", "delete", "patch", "head", "options"):
                    continue
                
                request_fields = []
                if "requestBody" in operation:
                    content = operation["requestBody"].get("content", {})
                    for media_type, schema in content.items():
                        request_fields.extend(self._parse_schema(schema.get("schema", {})))

                response_fields = []
                responses = operation.get("responses", {})
                for status, response in responses.items():
                    if status.startswith("2"):
                        content = response.get("content", {})
                        for media_type, schema in content.items():
                            response_fields.extend(self._parse_schema(schema.get("schema", {})))

                methods.append(ProtocolMethod(
                    name=operation.get("operationId", f"{http_method}_{path.replace('/', '_')}"),
                    protocol_type=ProtocolType.REST,
                    path=path,
                    http_method=http_method.upper(),
                    request_fields=request_fields,
                    response_fields=response_fields,
                    description=operation.get("summary", ""),
                ))

        return ProtocolDefinition(
            name=spec.get("info", {}).get("title", "API"),
            version=spec.get("info", {}).get("version", "1.0.0"),
            protocol_type=ProtocolType.REST,
            base_url=spec.get("servers", [{}])[0].get("url", ""),
            methods=methods,
        )

    def _parse_schema(self, schema: Dict[str, Any], prefix: str = "") -> List[ProtocolField]:
        fields = []
        if schema.get("type") == "object":
            for prop_name, prop_schema in schema.get("properties", {}).items():
                fields.extend(self._parse_schema(prop_schema, prefix + prop_name + "."))
        elif "type" in schema:
            field_type = self._map_json_type(schema["type"])
            fields.append(ProtocolField(
                name=prefix.rstrip("."),
                field_type=field_type,
                required=prefix.rstrip(".") in schema.get("required", []),
                description=schema.get("description", ""),
            ))
        return fields

    def _map_json_type(self, json_type: str) -> FieldType:
        mapping = {
            "string": FieldType.STRING,
            "integer": FieldType.INTEGER,
            "number": FieldType.FLOAT,
            "boolean": FieldType.BOOLEAN,
            "array": FieldType.ARRAY,
            "object": FieldType.OBJECT,
        }
        return mapping.get(json_type, FieldType.ANY)


class ProtocolRegistry:
    def __init__(self):
        self.protocols: Dict[str, ProtocolDefinition] = {}

    def register(self, protocol: ProtocolDefinition):
        key = f"{protocol.name}:{protocol.version}"
        self.protocols[key] = protocol

    def get(self, name: str, version: str) -> Optional[ProtocolDefinition]:
        return self.protocols.get(f"{name}:{version}")

    def list(self) -> List[ProtocolDefinition]:
        return list(self.protocols.values())

    def remove(self, name: str, version: str) -> bool:
        key = f"{name}:{version}"
        if key in self.protocols:
            del self.protocols[key]
            return True
        return False

    def save(self, path: str):
        data = {k: v.to_dict() for k, v in self.protocols.items()}
        Path(path).write_text(json.dumps(data, indent=2))

    def load(self, path: str):
        data = json.loads(Path(path).read_text())
        for k, v in data.items():
            self.protocols[k] = ProtocolDefinition.from_dict(v)