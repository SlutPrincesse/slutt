"""
Core module - Central system components
"""
from .config import SectionConfig, SystemConfig, config
from .events import Event, EventBus, EventPriority, event_bus
from .plugins import PluginContext, PluginManager, PluginMetadata, PluginState, plugin_manager
from .registry import ComponentMetadata, ComponentState, SystemRegistry, registry

__all__ = [
    "SystemRegistry",
    "ComponentMetadata",
    "ComponentState",
    "registry",
    "EventBus",
    "Event",
    "EventPriority",
    "event_bus",
    "SystemConfig",
    "SectionConfig",
    "config",
    "PluginManager",
    "PluginMetadata",
    "PluginState",
    "PluginContext",
    "plugin_manager",
]
