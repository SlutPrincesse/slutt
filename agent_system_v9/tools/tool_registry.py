import asyncio
import inspect
import hashlib
import json
import uuid
from typing import Any, Dict, List, Optional, Callable, Set, Type, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from datetime import datetime
import importlib.util
import sys

from .tool_synthesizer import SynthesizedTool, ToolSynthesizer, SynthesisStrategy


class ToolCategory(Enum):
    SYSTEM = "system"
    ANALYSIS = "analysis"
    CODE_GENERATION = "code_generation"
    FILE_OPERATION = "file_operation"
    NETWORK = "network"
    COMPUTATION = "computation"
    INTEGRATION = "integration"
    SYNTHESIZED = "synthesized"
    EXTERNAL = "external"


class ToolStatus(Enum):
    REGISTERED = "registered"
    LOADING = "loading"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ERROR = "error"
    UNLOADED = "unloaded"


@dataclass
class ToolParameter:
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[List[Any]] = None


@dataclass
class ToolEntry:
    name: str
    description: str
    category: ToolCategory
    function: Callable
    parameters: List[ToolParameter] = field(default_factory=list)
    returns: Dict[str, Any] = field(default_factory=dict)
    status: ToolStatus = ToolStatus.REGISTERED
    version: str = "1.0.0"
    author: str = "system"
    tags: List[str] = field(default_factory=list)
    sandbox_spec: Optional[Dict[str, Any]] = None
    provider_hints: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    usage_count: int = 0
    last_used: Optional[str] = None
    avg_latency_ms: float = 0.0
    error_count: int = 0
    synthesized_from: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["category"] = self.category.value
        data["status"] = self.status.value
        data["function"] = self.function.__name__ if self.function else None
        return data

    def to_openai_function(self) -> Dict[str, Any]:
        properties = {}
        required = []
        for param in self.parameters:
            prop = {"type": param.type, "description": param.description}
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default
            properties[param.name] = prop
            if param.required:
                required.append(param.name)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def validate_args(self, args: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        for param in self.parameters:
            if param.required and param.name not in args:
                return False, f"Missing required parameter: {param.name}"
            if param.name in args:
                value = args[param.name]
                if param.enum and value not in param.enum:
                    return False, f"Invalid value for {param.name}: must be one of {param.enum}"
        return True, None


@dataclass
class SandboxSpec:
    image: str = "python:3.11-slim"
    memory_limit: str = "512m"
    cpu_limit: str = "0.5"
    timeout_seconds: int = 30
    network_enabled: bool = False
    volumes: List[str] = field(default_factory=list)
    environment: Dict[str, str] = field(default_factory=dict)
    working_dir: str = "/workspace"
    user: str = "nobody"
    capabilities: List[str] = field(default_factory=list)
    seccomp_profile: Optional[str] = None


class DynamicToolRegistry:
    _instance: Optional["DynamicToolRegistry"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._tools: Dict[str, ToolEntry] = {}
        self._categories: Dict[ToolCategory, Set[str]] = {cat: set() for cat in ToolCategory}
        self._synthesizer = ToolSynthesizer()
        self._sandbox_isolator = None
        self._event_bus = None
        self._auto_load_paths: List[Path] = []
        self._tool_loaders: Dict[str, Callable] = {}
        self._initialized = True

    @classmethod
    def get_instance(cls) -> "DynamicToolRegistry":
        if cls._instance is None:
            cls._instance = DynamicToolRegistry()
        return cls._instance

    def set_sandbox_isolator(self, isolator):
        self._sandbox_isolator = isolator

    def set_event_bus(self, event_bus):
        self._event_bus = event_bus

    def register(
        self,
        name: str,
        function: Callable,
        description: str,
        category: ToolCategory = ToolCategory.SYSTEM,
        parameters: List[ToolParameter] = None,
        returns: Dict[str, Any] = None,
        sandbox_spec: SandboxSpec = None,
        tags: List[str] = None,
        version: str = "1.0.0",
        author: str = "system",
        **metadata
    ) -> ToolEntry:
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")

        if parameters is None:
            parameters = self._infer_parameters(function)

        entry = ToolEntry(
            name=name,
            description=description,
            category=category,
            function=function,
            parameters=parameters,
            returns=returns or {},
            sandbox_spec=sandbox_spec.__dict__ if sandbox_spec else None,
            tags=tags or [],
            version=version,
            author=author,
            metadata=metadata,
        )

        self._tools[name] = entry
        self._categories[category].add(name)
        self._emit_event("tool_registered", {"tool": name, "category": category.value})
        return entry

    def _infer_parameters(self, function: Callable) -> List[ToolParameter]:
        sig = inspect.signature(function)
        params = []
        for name, param in sig.parameters.items():
            if name in ("self", "cls"):
                continue
            param_type = "any"
            if param.annotation != inspect.Parameter.empty:
                param_type = self._type_to_json_schema(param.annotation)
            required = param.default == inspect.Parameter.empty
            default = None if required else param.default
            params.append(ToolParameter(
                name=name,
                type=param_type,
                description=f"Parameter {name}",
                required=required,
                default=default,
            ))
        return params

    def _type_to_json_schema(self, annotation: Any) -> str:
        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
            type(None): "null",
        }
        if hasattr(annotation, "__origin__"):
            origin = annotation.__origin__
            if origin in (list, List):
                return "array"
            if origin in (dict, Dict):
                return "object"
            if origin is Union:
                args = annotation.__args__
                non_none = [a for a in args if a != type(None)]
                if len(non_none) == 1:
                    return self._type_to_json_schema(non_none[0])
        return type_map.get(annotation, "any")

    def unregister(self, name: str) -> bool:
        if name not in self._tools:
            return False
        entry = self._tools[name]
        self._categories[entry.category].discard(name)
        del self._tools[name]
        self._emit_event("tool_unregistered", {"tool": name})
        return True

    def get(self, name: str) -> Optional[ToolEntry]:
        return self._tools.get(name)

    def get_by_category(self, category: ToolCategory) -> List[ToolEntry]:
        return [self._tools[name] for name in self._categories.get(category, set())]

    def search(self, query: str, category: ToolCategory = None) -> List[ToolEntry]:
        query_lower = query.lower()
        results = []
        for entry in self._tools.values():
            if category and entry.category != category:
                continue
            if (query_lower in entry.name.lower() or 
                query_lower in entry.description.lower() or
                any(query_lower in tag.lower() for tag in entry.tags)):
                results.append(entry)
        return results

    def list_all(self) -> List[ToolEntry]:
        return list(self._tools.values())

    async def execute(
        self,
        name: str,
        args: Dict[str, Any],
        sandbox: bool = False,
        provider: str = None,
    ) -> Any:
        entry = self._tools.get(name)
        if not entry:
            raise ValueError(f"Tool not found: {name}")

        valid, error = entry.validate_args(args)
        if not valid:
            raise ValueError(error)

        entry.usage_count += 1
        entry.last_used = datetime.utcnow().isoformat()

        try:
            if sandbox and self._sandbox_isolator:
                result = await self._execute_in_sandbox(entry, args)
            else:
                result = await self._execute_direct(entry, args)
            
            self._emit_event("tool_executed", {"tool": name, "success": True})
            return result
        except Exception as e:
            entry.error_count += 1
            self._emit_event("tool_executed", {"tool": name, "success": False, "error": str(e)})
            raise

    async def _execute_direct(self, entry: ToolEntry, args: Dict[str, Any]) -> Any:
        func = entry.function
        if asyncio.iscoroutinefunction(func):
            return await func(**args)
        return func(**args)

    async def _execute_in_sandbox(self, entry: ToolEntry, args: Dict[str, Any]) -> Any:
        if not self._sandbox_isolator:
            raise RuntimeError("Sandbox isolator not configured")
        
        spec = entry.sandbox_spec or SandboxSpec().__dict__
        return await self._sandbox_isolator.execute_tool(entry.name, entry.function, args, spec)

    def register_synthesized(self, tool: SynthesizedTool) -> ToolEntry:
        func = tool.compile()
        entry = self.register(
            name=tool.name,
            function=func,
            description=tool.spec.get("description", ""),
            category=ToolCategory.SYNTHESIZED,
            parameters=self._spec_to_parameters(tool.spec.get("parameters", {})),
            returns=tool.spec.get("returns", {}),
            tags=["synthesized", tool.strategy.value],
            synthesized_from=tool.trigger_exception,
            metadata={"confidence": tool.confidence, "strategy": tool.strategy.value},
        )
        return entry

    def _spec_to_parameters(self, spec: Dict[str, Any]) -> List[ToolParameter]:
        params = []
        properties = spec.get("properties", {})
        required = spec.get("required", [])
        for name, prop in properties.items():
            params.append(ToolParameter(
                name=name,
                type=prop.get("type", "any"),
                description=prop.get("description", ""),
                required=name in required,
                default=prop.get("default"),
                enum=prop.get("enum"),
            ))
        return params

    def auto_load_generated(self, directory: Path = None) -> int:
        if directory is None:
            directory = Path(__file__).parent / "generated"
        
        if not directory.exists():
            return 0

        count = 0
        for py_file in directory.glob("*.py"):
            try:
                spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
                module = importlib.util.module_from_spec(spec)
                sys.modules[py_file.stem] = module
                spec.loader.exec_module(module)
                
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if callable(attr) and hasattr(attr, "_tool_spec"):
                        spec = attr._tool_spec
                        self.register(
                            name=spec["name"],
                            function=attr,
                            description=spec.get("description", ""),
                            category=ToolCategory.SYNTHESIZED,
                            tags=["auto_loaded"],
                        )
                        count += 1
            except Exception:
                pass
        
        return count

    def register_loader(self, pattern: str, loader: Callable[[Path], List[ToolEntry]]):
        self._tool_loaders[pattern] = loader

    async def load_from_path(self, path: Path) -> int:
        for pattern, loader in self._tool_loaders.items():
            if path.match(pattern):
                entries = loader(path)
                for entry in entries:
                    self._tools[entry.name] = entry
                    self._categories[entry.category].add(entry.name)
                return len(entries)
        return 0

    def get_openai_functions(self, category: ToolCategory = None) -> List[Dict[str, Any]]:
        tools = self.get_by_category(category) if category else self.list_all()
        return [t.to_openai_function() for t in tools if t.status == ToolStatus.ACTIVE]

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_tools": len(self._tools),
            "by_category": {cat.value: len(names) for cat, names in self._categories.items()},
            "by_status": {},
            "total_executions": sum(t.usage_count for t in self._tools.values()),
            "total_errors": sum(t.error_count for t in self._tools.values()),
        }

    def _emit_event(self, event_type: str, data: Dict[str, Any]):
        if self._event_bus:
            try:
                self._event_bus.publish(f"tool.{event_type}", data)
            except Exception:
                pass

    async def close(self):
        for entry in self._tools.values():
            if hasattr(entry.function, "close"):
                try:
                    if asyncio.iscoroutinefunction(entry.function.close):
                        await entry.function.close()
                    else:
                        entry.function.close()
                except Exception:
                    pass
        self._tools.clear()
        for cat_set in self._categories.values():
            cat_set.clear()


def tool(
    name: str = None,
    description: str = "",
    category: ToolCategory = ToolCategory.SYSTEM,
    parameters: List[ToolParameter] = None,
    sandbox: SandboxSpec = None,
    tags: List[str] = None,
):
    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__
        registry = DynamicToolRegistry.get_instance()
        registry.register(
            name=tool_name,
            function=func,
            description=description or func.__doc__ or "",
            category=category,
            parameters=parameters,
            sandbox_spec=sandbox,
            tags=tags,
        )
        func._tool_spec = {
            "name": tool_name,
            "description": description or func.__doc__ or "",
        }
        return func
    return decorator