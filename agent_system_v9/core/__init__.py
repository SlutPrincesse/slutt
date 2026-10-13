"""
Core module - Central system components
"""
from .registry import SystemRegistry, ComponentMetadata, ComponentState, registry
from .events import EventBus, Event, EventPriority, event_bus
from .config import SystemConfig, SectionConfig, config
from .plugins import PluginManager, PluginMetadata, PluginState, PluginContext, plugin_manager

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