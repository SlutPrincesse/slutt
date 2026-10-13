"""
Core System Registry - Central component registration and discovery
"""
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ComponentState(Enum):
    UNREGISTERED = "unregistered"
    REGISTERING = "registering"
    ACTIVE = "active"
    DEGRADED = "degraded"
    FAILED = "failed"
    SHUTDOWN = "shutdown"


@dataclass
class ComponentMetadata:
    component_id: str
    name: str
    version: str
    section: str
    dependencies: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    state: ComponentState = ComponentState.UNREGISTERED
    health_score: float = 1.0
    last_heartbeat: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class SystemRegistry:
    _instance: Optional['SystemRegistry'] = None
    _lock = threading.RLock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._components: dict[str, ComponentMetadata] = {}
        self._component_instances: dict[str, Any] = {}
        self._section_index: dict[str, list[str]] = {}
        self._dependency_graph: dict[str, list[str]] = {}
        self._initialized = True

    def register(self, name: str, version: str, section: str,
                 instance: Any = None, dependencies: list[str] = None,
                 capabilities: list[str] = None, metadata: dict[str, Any] = None) -> str:
        component_id = f"{section}.{name}.{version}"
        comp_metadata = ComponentMetadata(
            component_id=component_id,
            name=name,
            version=version,
            section=section,
            dependencies=dependencies or [],
            capabilities=capabilities or [],
            state=ComponentState.REGISTERING,
            metadata=metadata or {}
        )
        with self._lock:
            self._components[component_id] = comp_metadata
            if instance:
                self._component_instances[component_id] = instance
                comp_metadata.state = ComponentState.ACTIVE

            if section not in self._section_index:
                self._section_index[section] = []
            self._section_index[section].append(component_id)

            for dep in comp_metadata.dependencies:
                if dep not in self._dependency_graph:
                    self._dependency_graph[dep] = []
                self._dependency_graph[dep].append(component_id)

        return component_id

    def unregister(self, component_id: str) -> bool:
        with self._lock:
            if component_id not in self._components:
                return False
            comp = self._components[component_id]
            comp.state = ComponentState.SHUTDOWN
            self._component_instances.pop(component_id, None)
            self._components.pop(component_id, None)
            if comp.section in self._section_index:
                self._section_index[comp.section] = [
                    cid for cid in self._section_index[comp.section] if cid != component_id
                ]
            return True

    def get_component(self, component_id: str) -> Any | None:
        return self._component_instances.get(component_id)

    def get_metadata(self, component_id: str) -> ComponentMetadata | None:
        return self._components.get(component_id)

    def get_by_section(self, section: str) -> list[ComponentMetadata]:
        return [self._components[cid] for cid in self._section_index.get(section, [])]

    def get_by_capability(self, capability: str) -> list[ComponentMetadata]:
        return [c for c in self._components.values() if capability in c.capabilities]

    def update_health(self, component_id: str, health_score: float):
        if component_id in self._components:
            self._components[component_id].health_score = health_score
            if health_score < 0.2:
                self._components[component_id].state = ComponentState.FAILED
            elif health_score < 0.5:
                self._components[component_id].state = ComponentState.DEGRADED
            else:
                self._components[component_id].state = ComponentState.ACTIVE

    def heartbeat(self, component_id: str):
        import time
        if component_id in self._components:
            self._components[component_id].last_heartbeat = time.time()

    def resolve_dependencies(self, component_id: str) -> list[str]:
        if component_id in self._components:
            return self._components[component_id].dependencies
        return []


registry = SystemRegistry()
