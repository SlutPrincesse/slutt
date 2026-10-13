"""
GUI Package for AGENT_SYSTEM_V9
"""
from .integration import (
    GUIIntegration,
    WebappConfig,
    WebappManager,
    get_gui_integration,
    get_webapp_manager,
    run_with_gui,
)

__all__ = [
    "WebappManager",
    "WebappConfig",
    "GUIIntegration",
    "get_webapp_manager",
    "get_gui_integration",
    "run_with_gui",
]
