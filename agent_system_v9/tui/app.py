"""
AGENT_SYSTEM_V9 TUI - Terminal User Interface for the Neuro-Cranial Overlord
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree
from rich.live import Live
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.columns import Columns
from rich.align import Align

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Header, Footer, Static, Button, Input, Log, DataTable,
    Tree as TextualTree, TabbedContent, TabPane, Label, Select
)
from textual.binding import Binding
from textual.reactive import reactive
from textual.screen import Screen

logger = logging.getLogger(__name__)


@dataclass
class SystemStatus:
    """System component status."""
    name: str
    status: str  # running, stopped, error, unknown
    details: str = ""
    last_update: datetime = field(default_factory=datetime.now)


class SystemOverview(Static):
    """System overview widget."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.statuses: Dict[str, SystemStatus] = {}
    
    def update_status(self, name: str, status: str, details: str = ""):
        self.statuses[name] = SystemStatus(name=name, status=status, details=details)
        self.refresh()
    
    def render(self):
        table = Table(title="AGENT_SYSTEM_V9 System Status", show_header=True)
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Details", style="dim")
        table.add_column("Last Update", style="dim")
        
        status_colors = {
            "running": "green",
            "stopped": "yellow", 
            "error": "red",
            "unknown": "dim"
        }
        
        for name, status in self.statuses.items():
            color = status_colors.get(status.status, "white")
            table.add_row(
                name,
                f"[{color}]{status.status}[/{color}]",
                status.details,
                status.last_update.strftime("%H:%M:%S")
            )
        
        return Panel(table, border_style="blue")


class ToolSelector(Static):
    """Tool selection and execution widget."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.tools: Dict[str, Dict[str, Any]] = {}
        self.selected_tool: Optional[str] = None
    
    def set_tools(self, tools: Dict[str, Dict[str, Any]]):
        self.tools = tools
        self.refresh()
    
    def render(self):
        if not self.tools:
            return Panel("No tools loaded", title="Tools", border_style="yellow")
        
        table = Table(title="Available Tools", show_header=True)
        table.add_column("Module", style="cyan")
        table.add_column("Tool", style="green")
        table.add_column("Method", style="yellow")
        table.add_column("Description", style="dim")
        
        for module, module_tools in self.tools.items():
            for tool in module_tools:
                table.add_row(
                    module,
                    tool.get("name", ""),
                    tool.get("method", ""),
                    tool.get("description", "")[:60]
                )
        
        return Panel(table, border_style="green")


class ReconPanel(Static):
    """Reconnaissance execution panel."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.running = False
        self.results: List[Dict] = []
    
    def render(self):
        if self.running:
            return Panel("Recon running...", title="Recon", border_style="blue")
        
        if not self.results:
            return Panel("No recon results", title="Recon", border_style="yellow")
        
        table = Table(title="Recon Results", show_header=True)
        table.add_column("Module", style="cyan")
        table.add_column("Target", style="green")
        table.add_column("Success", style="yellow")
        table.add_column("Findings", style="dim")
        
        for r in self.results:
            table.add_row(
                r.get("module", ""),
                r.get("target", ""),
                "✓" if r.get("success") else "✗",
                str(r.get("data", {}))[:60]
            )
        
        return Panel(table, border_style="blue")


class AgentV9TUI(App):
    """Main TUI application for AGENT_SYSTEM_V9."""
    
    CSS = """
    Screen {
        layout: vertical;
    }
    
    #header {
        height: 3;
        background: $primary;
        color: $text;
    }
    
    #main {
        layout: horizontal;
        height: 1fr;
    }
    
    #sidebar {
        width: 30;
        background: $surface;
        border-right: solid $primary;
    }
    
    #content {
        width: 1fr;
        layout: vertical;
    }
    
    #footer {
        height: 3;
        background: $primary;
        color: $text;
    }
    
    .panel {
        border: solid $primary;
        margin: 1;
        padding: 1;
    }
    
    Button {
        margin: 1;
    }
    
    #log {
        height: 1fr;
        border: solid $primary;
        margin: 1;
        padding: 1;
    }
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("t", "tools", "Tools"),
        Binding("s", "system", "System"),
        Binding("n", "recon", "Recon"),
        Binding("l", "logs", "Logs"),
    ]
    
    current_view = reactive("system")
    
    def __init__(self):
        super().__init__()
        self.console = Console()
        self.system_overview = SystemOverview(id="system_overview")
        self.tool_selector = ToolSelector(id="tool_selector")
        self.recon_panel = ReconPanel(id="recon_panel")
        self.log_widget = Log(id="log", highlight=True)
        self._init_system_status()
    
    def _init_system_status(self):
        """Initialize system component statuses."""
        components = [
            ("Core Registry", "running", "SystemRegistry active"),
            ("Event Bus", "running", "EventBus active"),
            ("Config", "running", "SystemConfig loaded"),
            ("Plugin Manager", "running", "PluginManager ready"),
            ("Providers", "unknown", "Not initialized"),
            ("Kernel", "unknown", "Not initialized"),
            ("Security", "unknown", "Not initialized"),
            ("Distributed", "unknown", "Not initialized"),
            ("Storage", "unknown", "Not initialized"),
            ("Workspace", "unknown", "Not initialized"),
            ("Evolution", "unknown", "Not initialized"),
            ("RedAmon Orchestrator", "unknown", "Not initialized"),
            ("RedAmon KB", "unknown", "Not initialized"),
            ("RedAmon Docker Broker", "unknown", "Not initialized"),
            ("RedAmon Recon", "unknown", "Not initialized"),
            ("Cybersec Toolkit", "unknown", "Not initialized"),
        ]
        
        for name, status, details in components:
            self.system_overview.update_status(name, status, details)
    
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        with Container(id="main"):
            with Vertical(id="sidebar"):
                yield Static("AGENT_SYSTEM_V9", id="header")
                yield Button("System", id="btn_system", variant="primary")
                yield Button("Tools", id="btn_tools", variant="default")
                yield Button("Recon", id="btn_recon", variant="default")
                yield Button("Evolution", id="btn_evolution", variant="default")
                yield Button("Security", id="btn_security", variant="default")
                yield Button("Logs", id="btn_logs", variant="default")
            
            with Vertical(id="content"):
                with TabbedContent(id="tabs"):
                    with TabPane("System", id="tab_system"):
                        yield self.system_overview
                    
                    with TabPane("Tools", id="tab_tools"):
                        yield self.tool_selector
                    
                    with TabPane("Recon", id="tab_recon"):
                        yield self.recon_panel
                    
                    with TabPane("Evolution", id="tab_evolution"):
                        yield Static("Evolution Engine - Coming Soon", id="evolution_panel")
                    
                    with TabPane("Security", id="tab_security"):
                        yield Static("Security Suite - Coming Soon", id="security_panel")
                    
                    with TabPane("Logs", id="tab_logs"):
                        yield self.log_widget
        
        yield Footer()
    
    def on_button_pressed(self, event: Button.Pressed):
        button_id = event.button.id
        tab_map = {
            "btn_system": "tab_system",
            "btn_tools": "tab_tools", 
            "btn_recon": "tab_recon",
            "btn_evolution": "tab_evolution",
            "btn_security": "tab_security",
            "btn_logs": "tab_logs",
        }
        
        if button_id in tab_map:
            tabs = self.query_one("#tabs", TabbedContent)
            tabs.active = tab_map[button_id]
            
            # Update button styles
            for btn_id in tab_map:
                btn = self.query_one(f"#{btn_id}", Button)
                btn.variant = "primary" if btn_id == button_id else "default"
    
    def action_refresh(self):
        self.log_widget.write_line(f"[{datetime.now().strftime('%H:%M:%S')}] Refreshing...")
        self._init_system_status()
    
    def action_tools(self):
        tabs = self.query_one("#tabs", TabbedContent)
        tabs.active = "tab_tools"
    
    def action_system(self):
        tabs = self.query_one("#tabs", TabbedContent)
        tabs.active = "tab_system"
    
    def action_recon(self):
        tabs = self.query_one("#tabs", TabbedContent)
        tabs.active = "tab_recon"
    
    def action_logs(self):
        tabs = self.query_one("#tabs", TabbedContent)
        tabs.active = "tab_logs"
    
    async def on_mount(self):
        """Load tools on mount."""
        await self._load_tools()
    
    async def _load_tools(self):
        """Load available tools from cybersec-toolkit integration."""
        try:
            from agent_system_v9.integrations import get_cybersec_toolkit_integration
            integration = get_cybersec_toolkit_integration()
            
            tools_by_module = {}
            for module in integration.tool_manager.get_all_modules():
                module_tools = integration.tool_manager.get_tools_by_module(module)
                tools_by_module[module] = [
                    {
                        "name": t.name,
                        "method": t.method,
                        "description": t.description
                    }
                    for t in module_tools
                ]
            
            self.tool_selector.set_tools(tools_by_module)
            self.log_widget.write_line(f"Loaded {sum(len(v) for v in tools_by_module.values())} tools from {len(tools_by_module)} modules")
        except Exception as e:
            self.log_widget.write_line(f"Error loading tools: {e}")
    
    async def run_recon(self, target: str):
        """Run reconnaissance on target."""
        self.recon_panel.running = True
        self.recon_panel.refresh()
        
        try:
            from agent_system_v9.integrations import get_recon_integration
            recon = get_recon_integration()
            
            pipeline = recon.create_default_pipeline()
            results = await pipeline.run(
                recon.ReconTarget(target=target, target_type="domain")
            )
            
            self.recon_panel.results = [
                {
                    "module": r.module,
                    "target": target,
                    "success": r.success,
                    "data": r.data
                }
                for r in results
            ]
            
            self.recon_panel.running = False
            self.recon_panel.refresh()
            self.log_widget.write_line(f"Recon complete for {target}: {len(results)} modules")
            
        except Exception as e:
            self.recon_panel.running = False
            self.recon_panel.refresh()
            self.log_widget.write_line(f"Recon error: {e}")


def run_tui():
    """Run the TUI application."""
    app = AgentV9TUI()
    app.run()


if __name__ == "__main__":
    run_tui()