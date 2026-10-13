"""
Core Plugin Manager - Capability plugin system for AGENT_SYSTEM_V9
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type


@dataclass
class PluginMetadata:
    """Metadata for a registered plugin."""
    name: str
    version: str
    description: str
    entry_point: str
    capabilities: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    config_schema: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0


class PluginState:
    """Plugin lifecycle states."""
    UNREGISTERED = "unregistered"
    LOADED = "loaded"
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"
    UNLOADING = "unloading"


@dataclass
class PluginContext:
    """Context provided to plugin factories."""
    config: Any
    registry: Any
    event_bus: Any
    logger: Any


class _PluginInfo:
    """Internal plugin information."""
    def __init__(
        self,
        metadata: PluginMetadata,
        factory: Callable[[PluginContext], Any],
        instance: Any = None,
        state: str = PluginState.LOADED,
    ):
        self.metadata = metadata
        self.factory = factory
        self.instance = instance
        self.state = state


class PluginManager:
    """Singleton plugin manager for capability plugins."""

    _instance: Optional["PluginManager"] = None
    _lock = threading.Lock()

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
        self._plugins: Dict[str, _PluginInfo] = {}
        self._capability_index: Dict[str, List[str]] = {}
        self._dependency_graph: Dict[str, List[str]] = {}
        self._initialized = True

    @classmethod
    def get_instance(cls) -> "PluginManager":
        return cls()

    def register_plugin(
        self,
        metadata: PluginMetadata,
        factory: Callable[[PluginContext], Any],
    ) -> str:
        """Register a plugin with its factory function."""
        plugin_id = f"{metadata.name}.{metadata.version}"

        if plugin_id in self._plugins:
            raise ValueError(f"Plugin {plugin_id} already registered")

        self._plugins[plugin_id] = _PluginInfo(metadata, factory)

        for cap in metadata.capabilities:
            if cap not in self._capability_index:
                self._capability_index[cap] = []
            self._capability_index[cap].append(plugin_id)

        self._dependency_graph[plugin_id] = metadata.dependencies.copy()

        return plugin_id

    def load_plugin(self, plugin_id: str, context: Optional[PluginContext] = None) -> Any:
        """Load and instantiate a plugin."""
        if plugin_id not in self._plugins:
            raise KeyError(f"Plugin {plugin_id} not registered")

        info = self._plugins[plugin_id]

        if info.state == PluginState.ACTIVE:
            return info.instance

        self._load_dependencies(plugin_id)

        if context is None:
            from agent_system_v9 import config, registry, event_bus
            context = PluginContext(
                config=config,
                registry=registry,
                event_bus=event_bus,
                logger=None,
            )

        info.instance = info.factory(context)
        info.state = PluginState.ACTIVE

        return info.instance

    def _load_dependencies(self, plugin_id: str):
        """Load plugin dependencies first."""
        for dep_id in self._dependency_graph.get(plugin_id, []):
            if dep_id in self._plugins:
                dep_info = self._plugins[dep_id]
                if dep_info.state != PluginState.ACTIVE:
                    self.load_plugin(dep_id)

    def unload_plugin(self, plugin_id: str) -> bool:
        """Unload a plugin."""
        if plugin_id not in self._plugins:
            return False

        info = self._plugins[plugin_id]

        for other_id, other_info in self._plugins.items():
            if other_info.state == PluginState.ACTIVE and plugin_id in self._dependency_graph.get(other_id, []):
                return False

        info.instance = None
        info.state = PluginState.LOADED
        return True

    def enable_plugin(self, plugin_id: str):
        """Enable a disabled plugin."""
        if plugin_id in self._plugins:
            self._plugins[plugin_id].state = PluginState.ACTIVE

    def disable_plugin(self, plugin_id: str):
        """Disable an active plugin."""
        if plugin_id in self._plugins:
            self._plugins[plugin_id].state = PluginState.DISABLED

    def get_plugin(self, plugin_id: str) -> Optional[Any]:
        """Get plugin instance."""
        info = self._plugins.get(plugin_id)
        return info.instance if info else None

    def get_plugin_info(self, plugin_id: str) -> Optional[Dict[str, Any]]:
        """Get plugin metadata and state."""
        info = self._plugins.get(plugin_id)
        if not info:
            return None
        return {
            "metadata": info.metadata,
            "state": info.state,
            "instance": info.instance,
        }

    def get_by_capability(self, capability: str) -> List[str]:
        """Get plugin IDs by capability."""
        return self._capability_index.get(capability, [])

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        """Get all plugins info."""
        return {
            pid: {
                "metadata": info.metadata,
                "state": info.state,
            }
            for pid, info in self._plugins.items()
        }

    def health_check(self) -> Dict[str, bool]:
        """Run health check on all active plugins."""
        results = {}
        for pid, info in self._plugins.items():
            if info.state == PluginState.ACTIVE and info.instance:
                if hasattr(info.instance, "health_check"):
                    try:
                        results[pid] = info.instance.health_check()
                    except Exception:
                        results[pid] = False
                else:
                    results[pid] = True
        return results


plugin_manager = PluginManager()