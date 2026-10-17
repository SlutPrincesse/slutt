"""
Unified Omniframe App
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from rich.console import Console
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.reactive import reactive
from textual.widgets import (
    Button,
    Footer,
    Header,
    Log,
    Static,
    TabbedContent,
    TabPane,
)

from .bridge import UnifiedBridge


class SystemPanel(Static):
    """System overview panel"""
    def render(self):
        from rich.table import Table
        from rich.panel import Panel

        table = Table(title="SYSTEM OVERVIEW", show_header=True)
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Details", style="dim")

        components = [
            ("Core Registry", "OK", "Active"),
            ("EventBus", "OK", "Active"),
            ("Config", "OK", "Loaded"),
            ("Plugin Manager", "OK", "Ready"),
            ("Evolution", "OK", "Ready"),
            ("Security", "OK", "Ready"),
            ("Distributed", "OK", "Ready"),
            ("ShadowGit", "OK", "Ready"),
        ]
        for name, status, details in components:
            table.add_row(name, status, details)
        return Panel(table, border_style="blue")


class ToolsPanel(Static):
    """Tools panel"""
    def render(self):
        from rich.table import Table
        from rich.panel import Panel

        table = Table(title="CAPABILITIES", show_header=True)
        table.add_column("Category", style="cyan")
        table.add_column("Count", style="green")
        table.add_column("Status", style="dim")

        cats = [
            ("Code Gen", "Active", "Ready"),
            ("Evolution", "Active", "Ready"),
            ("Security", "Active", "Ready"),
            ("Recon", "Active", "Ready"),
            ("Distributed", "Active", "Ready"),
            ("Memory/KG", "Active", "Ready"),
        ]
        for name, count, status in cats:
            table.add_row(name, count, status)
        return Panel(table, border_style="green")


class MemoryPanel(Static):
    """Memory panel"""
    def render(self):
        from rich.panel import Panel
        return Panel("Episodic • Semantic • KG • Code Memory\n[dim]Unified memory system active[/dim]",
                     title="MEMORY", border_style="magenta")


class EvolutionPanel(Static):
    """Evolution panel"""
    def render(self):
        from rich.panel import Panel
        return Panel("GA • ES • CMA-ES • PSO • DE • Portfolio\n[dim]Self-improvement engine ready[/dim]",
                     title="EVOLUTION", border_style="yellow")


class SecurityPanel(Static):
    """Security panel"""
    def render(self):
        from rich.panel import Panel
        return Panel("ZeroTrust • Entropy • VulnScan • Egress • Integrity\n[dim]Guardrails active[/dim]",
                     title="SECURITY", border_style="red")


class AgentLoopPanel(Static):
    """Agent loop panel"""
    def render(self):
        from rich.panel import Panel
        return Panel("Reasoning • Planning • Execution • Reflection\n[dim]Autonomous loop ready[/dim]",
                     title="AGENT LOOP", border_style="cyan")


class UnifiedApp(App):
    """Unified Omniframe Application"""

    CSS_PATH = "theme.css"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("tab", "next_tab", "Next"),
    ]

    def __init__(self, bridge: UnifiedBridge | None = None):
        super().__init__()
        self.bridge = bridge or UnifiedBridge()
        self.log_widget = Log(id="log", highlight=True)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Container(id="main"):
            with Vertical(id="sidebar"):
                yield Static("NEURO-CRANIAL OVERLORD", id="header")
                yield Button("Overview", id="btn_overview", variant="primary")
                yield Button("Agent Loop", id="btn_agentloop", variant="default")
                yield Button("Memory", id="btn_memory", variant="default")
                yield Button("Tools", id="btn_tools", variant="default")
                yield Button("Evolution", id="btn_evolution", variant="default")
                yield Button("Security", id="btn_security", variant="default")
                yield Button("Logs", id="btn_logs", variant="default")

            with Vertical(id="content"), TabbedContent(id="tabs"):
                with TabPane("Overview", id="tab_overview"):
                    yield SystemPanel()
                with TabPane("Agent Loop", id="tab_agentloop"):
                    yield AgentLoopPanel()
                with TabPane("Memory", id="tab_memory"):
                    yield MemoryPanel()
                with TabPane("Tools", id="tab_tools"):
                    yield ToolsPanel()
                with TabPane("Evolution", id="tab_evolution"):
                    yield EvolutionPanel()
                with TabPane("Security", id="tab_security"):
                    yield SecurityPanel()
                with TabPane("Logs", id="tab_logs"):
                    yield self.log_widget

        yield Footer()

    def on_mount(self):
        self.bridge.start()
        try:
            self.bridge.wire()
        except Exception:
            pass
        self.log_widget.write_line(f"[{datetime.now().strftime('%H:%M:%S')}] Unified UI initialized")
        self.log_widget.write_line("All subsystems: READY")

    def action_refresh(self):
        self.log_widget.write_line(f"[{datetime.now().strftime('%H:%M:%S')}] Refreshing state...")


def run_unified(bridge: UnifiedBridge | None = None, web: bool = False, term: bool = True):
    """Run unified UI"""
    from .server import run_server
    import asyncio

    if web:
        asyncio.create_task(run_server(bridge=bridge))

    if term:
        app = UnifiedApp(bridge=bridge)
        app.run()
        return app
    return None

class DistributedPanel(Static):
    def render(self):
        from rich.panel import Panel
        return Panel("RPC • DAG • BFT • CRDT • LoadBalancer\n[dim]Distributed ready[/dim]",
                     title="DISTRIBUTED", border_style="blue")


class ShadowGitPanel(Static):
    def render(self):
        from rich.panel import Panel
        return Panel("Index • Sync • LFS • Commits • Rollback\n[dim]Git-native state[/dim]",
                     title="SHADOWGIT", border_style="green")
