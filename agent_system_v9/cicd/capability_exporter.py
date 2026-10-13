"""
Capability Exporter - Exports capabilities and skills for reuse
"""
import hashlib
import inspect
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import yaml


class CapabilityType(Enum):
    FUNCTION = "function"
    CLASS = "class"
    MODULE = "module"
    PIPELINE = "pipeline"
    WORKFLOW = "workflow"
    SKILL = "skill"
    TOOL = "tool"
    AGENT = "agent"


class ExportFormat(Enum):
    JSON = "json"
    YAML = "yaml"
    PYTHON = "python"
    MARKDOWN = "markdown"
    OPENAPI = "openapi"


@dataclass
class CapabilityParameter:
    name: str
    type: str
    description: str = ""
    required: bool = True
    default: Any = None
    enum: list[Any] = field(default_factory=list)


@dataclass
class CapabilityExample:
    name: str
    description: str
    input: dict[str, Any]
    output: Any
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Capability:
    capability_id: str
    name: str
    description: str
    capability_type: CapabilityType
    version: str = "1.0.0"
    author: str = ""
    tags: list[str] = field(default_factory=list)
    parameters: list[CapabilityParameter] = field(default_factory=list)
    returns: CapabilityParameter | None = None
    examples: list[CapabilityExample] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    source_code: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "name": self.name,
            "description": self.description,
            "type": self.capability_type.value,
            "version": self.version,
            "author": self.author,
            "tags": self.tags,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                    "default": p.default,
                    "enum": p.enum,
                }
                for p in self.parameters
            ],
            "returns": {
                "name": self.returns.name,
                "type": self.returns.type,
                "description": self.returns.description,
            } if self.returns else None,
            "examples": [
                {
                    "name": e.name,
                    "description": e.description,
                    "input": e.input,
                    "output": e.output,
                }
                for e in self.examples
            ],
            "dependencies": self.dependencies,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class CapabilityPackage:
    package_id: str
    name: str
    version: str
    description: str
    capabilities: list[Capability] = field(default_factory=list)
    dependencies: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


class CapabilityExtractor:
    def __init__(self):
        self.type_hints_cache: dict[str, Any] = {}

    def extract_from_function(self, func: Callable) -> Capability:
        sig = inspect.signature(func)
        doc = inspect.getdoc(func) or ""

        parameters = []
        for param_name, param in sig.parameters.items():
            param_type = "Any"
            if param.annotation != inspect.Parameter.empty:
                param_type = self._get_type_name(param.annotation)

            default = param.default if param.default != inspect.Parameter.empty else None
            required = default is None

            parameters.append(CapabilityParameter(
                name=param_name,
                type=param_type,
                description=f"Parameter {param_name}",
                required=required,
                default=default,
            ))

        returns = None
        if sig.return_annotation != inspect.Signature.empty:
            returns = CapabilityParameter(
                name="return",
                type=self._get_type_name(sig.return_annotation),
                description="Return value",
            )

        capability_id = hashlib.md5(f"{func.__module__}.{func.__name__}".encode()).hexdigest()[:12]

        return Capability(
            capability_id=capability_id,
            name=func.__name__,
            description=doc.split('\n')[0] if doc else "",
            capability_type=CapabilityType.FUNCTION,
            parameters=parameters,
            returns=returns,
            source_code=inspect.getsource(func),
        )

    def extract_from_class(self, cls: type) -> Capability:
        doc = inspect.getdoc(cls) or ""
        methods = []

        for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
            if not name.startswith('_'):
                methods.append(name)

        capability_id = hashlib.md5(f"{cls.__module__}.{cls.__name__}".encode()).hexdigest()[:12]

        return Capability(
            capability_id=capability_id,
            name=cls.__name__,
            description=doc.split('\n')[0] if doc else "",
            capability_type=CapabilityType.CLASS,
            metadata={"methods": methods, "bases": [b.__name__ for b in cls.__bases__]},
            source_code=inspect.getsource(cls),
        )

    def extract_from_module(self, module) -> list[Capability]:
        capabilities = []

        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj) and obj.__module__ == module.__name__:
                capabilities.append(self.extract_from_function(obj))
            elif inspect.isclass(obj) and obj.__module__ == module.__name__:
                capabilities.append(self.extract_from_class(obj))

        return capabilities

    def _get_type_name(self, annotation: Any) -> str:
        if hasattr(annotation, '__name__'):
            return annotation.__name__
        return str(annotation)


class CapabilityRegistry:
    def __init__(self):
        self.capabilities: dict[str, Capability] = {}
        self.packages: dict[str, CapabilityPackage] = {}
        self.extractor = CapabilityExtractor()

    def register(self, capability: Capability):
        self.capabilities[capability.capability_id] = capability

    def unregister(self, capability_id: str) -> bool:
        if capability_id in self.capabilities:
            del self.capabilities[capability_id]
            return True
        return False

    def get(self, capability_id: str) -> Capability | None:
        return self.capabilities.get(capability_id)

    def search(self, query: str = "", tags: list[str] = None, capability_type: CapabilityType = None) -> list[Capability]:
        results = []
        for cap in self.capabilities.values():
            if query and query.lower() not in cap.name.lower() and query.lower() not in cap.description.lower():
                continue
            if tags and not any(tag in cap.tags for tag in tags):
                continue
            if capability_type and cap.capability_type != capability_type:
                continue
            results.append(cap)
        return results

    def create_package(self, name: str, version: str, capability_ids: list[str], description: str = "") -> CapabilityPackage:
        capabilities = [self.capabilities[cid] for cid in capability_ids if cid in self.capabilities]

        package = CapabilityPackage(
            package_id=hashlib.md5(f"{name}:{version}".encode()).hexdigest()[:12],
            name=name,
            version=version,
            description=description,
            capabilities=capabilities,
        )

        self.packages[package.package_id] = package
        return package

    def register_function(self, func: Callable) -> Capability:
        capability = self.extractor.extract_from_function(func)
        self.register(capability)
        return capability

    def register_class(self, cls: type) -> Capability:
        capability = self.extractor.extract_from_class(cls)
        self.register(capability)
        return capability

    def register_module(self, module) -> list[Capability]:
        capabilities = self.extractor.extract_from_module(module)
        for cap in capabilities:
            self.register(cap)
        return capabilities


class CapabilityExporter:
    def __init__(self, registry: CapabilityRegistry):
        self.registry = registry

    def export(self, capability_ids: list[str], format: ExportFormat = ExportFormat.JSON) -> str:
        capabilities = [self.registry.get(cid) for cid in capability_ids if self.registry.get(cid)]

        if format == ExportFormat.JSON:
            return self._export_json(capabilities)
        if format == ExportFormat.YAML:
            return self._export_yaml(capabilities)
        if format == ExportFormat.PYTHON:
            return self._export_python(capabilities)
        if format == ExportFormat.MARKDOWN:
            return self._export_markdown(capabilities)
        if format == ExportFormat.OPENAPI:
            return self._export_openapi(capabilities)

        return ""

    def _export_json(self, capabilities: list[Capability]) -> str:
        return json.dumps([c.to_dict() for c in capabilities], indent=2)

    def _export_yaml(self, capabilities: list[Capability]) -> str:
        return yaml.dump([c.to_dict() for c in capabilities], default_flow_style=False)

    def _export_python(self, capabilities: list[Capability]) -> str:
        lines = [
            "# Auto-generated capability exports",
            "from typing import Any, Dict, List, Optional",
            "",
        ]

        for cap in capabilities:
            if cap.source_code:
                lines.append(cap.source_code)
                lines.append("")

        return "\n".join(lines)

    def _export_markdown(self, capabilities: list[Capability]) -> str:
        lines = ["# Capability Catalog", ""]

        for cap in capabilities:
            lines.append(f"## {cap.name}")
            lines.append(f"**ID:** {cap.capability_id}")
            lines.append(f"**Type:** {cap.capability_type.value}")
            lines.append(f"**Version:** {cap.version}")
            lines.append(f"**Description:** {cap.description}")
            lines.append("")

            if cap.parameters:
                lines.append("### Parameters")
                for param in cap.parameters:
                    req = " (required)" if param.required else " (optional)"
                    lines.append(f"- **{param.name}** ({param.type}){req}: {param.description}")
                lines.append("")

            if cap.returns:
                lines.append(f"### Returns: {cap.returns.type}")
                lines.append(f"{cap.returns.description}")
                lines.append("")

            if cap.examples:
                lines.append("### Examples")
                for ex in cap.examples:
                    lines.append(f"#### {ex.name}")
                    lines.append(f"{ex.description}")
                    lines.append(f"**Input:** `{json.dumps(ex.input)}`")
                    lines.append(f"**Output:** `{json.dumps(ex.output)}`")
                    lines.append("")

        return "\n".join(lines)

    def _export_openapi(self, capabilities: list[Capability]) -> str:
        paths = {}

        for cap in capabilities:
            if cap.capability_type == CapabilityType.FUNCTION:
                path = f"/capabilities/{cap.name}"
                params = []
                for param in cap.parameters:
                    params.append({
                        "name": param.name,
                        "in": "query",
                        "required": param.required,
                        "schema": {"type": param.type.lower()},
                        "description": param.description,
                    })

                paths[path] = {
                    "post": {
                        "summary": cap.description,
                        "operationId": cap.name,
                        "parameters": params,
                        "responses": {
                            "200": {
                                "description": "Successful response",
                                "content": {
                                    "application/json": {
                                        "schema": {"type": cap.returns.type.lower()} if cap.returns else {}
                                    }
                                }
                            }
                        }
                    }
                }

        spec = {
            "openapi": "3.0.0",
            "info": {
                "title": "Capability API",
                "version": "1.0.0",
            },
            "paths": paths,
        }

        return yaml.dump(spec, default_flow_style=False)

    def export_package(self, package_id: str, format: ExportFormat = ExportFormat.JSON) -> str:
        package = self.registry.packages.get(package_id)
        if not package:
            return ""

        return self.export([c.capability_id for c in package.capabilities], format)


class CapabilityImporter:
    def __init__(self, registry: CapabilityRegistry):
        self.registry = registry

    def import_from_json(self, json_str: str) -> list[Capability]:
        data = json.loads(json_str)
        capabilities = []

        for item in data:
            cap = Capability(
                capability_id=item["capability_id"],
                name=item["name"],
                description=item["description"],
                capability_type=CapabilityType(item["type"]),
                version=item["version"],
                author=item.get("author", ""),
                tags=item.get("tags", []),
                parameters=[
                    CapabilityParameter(**p) for p in item.get("parameters", [])
                ],
                returns=CapabilityParameter(**item["returns"]) if item.get("returns") else None,
                examples=[
                    CapabilityExample(**e) for e in item.get("examples", [])
                ],
                dependencies=item.get("dependencies", []),
                metadata=item.get("metadata", {}),
                created_at=item.get("created_at", time.time()),
                updated_at=item.get("updated_at", time.time()),
            )
            self.registry.register(cap)
            capabilities.append(cap)

        return capabilities

    def import_from_yaml(self, yaml_str: str) -> list[Capability]:
        data = yaml.safe_load(yaml_str)
        return self.import_from_json(json.dumps(data))

    def import_from_package(self, package_data: dict) -> CapabilityPackage:
        package = CapabilityPackage(
            package_id=package_data["package_id"],
            name=package_data["name"],
            version=package_data["version"],
            description=package_data["description"],
            capabilities=[
                Capability(**c) for c in package_data.get("capabilities", [])
            ],
            dependencies=package_data.get("dependencies", {}),
            metadata=package_data.get("metadata", {}),
        )

        for cap in package.capabilities:
            self.registry.register(cap)

        self.registry.packages[package.package_id] = package
        return package
