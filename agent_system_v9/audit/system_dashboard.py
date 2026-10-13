"""
Terminal System Dashboard - TUI displaying resource usage, active memory, and execution traces
"""
import curses
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class WidgetType(Enum):
    TEXT = "text"
    BAR = "bar"
    GAUGE = "gauge"
    GRAPH = "graph"
    TABLE = "table"
    LOG = "log"


@dataclass
class DashboardWidget:
    widget_id: str
    title: str
    widget_type: WidgetType
    x: int
    y: int
    width: int
    height: int
    data: Any = None
    refresh_interval: float = 1.0
    visible: bool = True
    style: dict[str, Any] = field(default_factory=dict)


class TerminalSystemDashboard:
    def __init__(self, stdscr=None):
        self.stdscr = stdscr
        self._widgets: dict[str, DashboardWidget] = {}
        self._data_providers: dict[str, Callable[[], Any]] = {}
        self._running = False
        self._render_thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._color_pairs = {}
        self._layout: list[list[str]] = []  # widget_id grid
        self._last_render = 0
        self._min_render_interval = 0.1

        # Default data providers
        self._data_providers["cpu"] = self._get_cpu_usage
        self._data_providers["memory"] = self._get_memory_usage
        self._data_providers["disk"] = self._get_disk_usage
        self._data_providers["network"] = self._get_network_usage
        self._data_providers["processes"] = self._get_process_count

    def initialize_colors(self):
        if not self.stdscr:
            return
        curses.start_color()
        curses.use_default_colors()

        self._color_pairs = {
            "default": 1,
            "red": 2,
            "green": 3,
            "yellow": 4,
            "blue": 5,
            "cyan": 6,
            "magenta": 7,
            "white": 8,
        }

        for i, (name, _) in enumerate(self._color_pairs.items(), 1):
            try:
                if name == "default":
                    curses.init_pair(i, -1, -1)
                elif name == "red":
                    curses.init_pair(i, curses.COLOR_RED, -1)
                elif name == "green":
                    curses.init_pair(i, curses.COLOR_GREEN, -1)
                elif name == "yellow":
                    curses.init_pair(i, curses.COLOR_YELLOW, -1)
                elif name == "blue":
                    curses.init_pair(i, curses.COLOR_BLUE, -1)
                elif name == "cyan":
                    curses.init_pair(i, curses.COLOR_CYAN, -1)
                elif name == "magenta":
                    curses.init_pair(i, curses.COLOR_MAGENTA, -1)
                elif name == "white":
                    curses.init_pair(i, curses.COLOR_WHITE, -1)
            except Exception:
                pass

    def start(self):
        if self._running:
            return
        if not self.stdscr:
            raise RuntimeError("No curses window provided. Call in curses.wrapper()")

        self._running = True
        self.initialize_colors()
        self._render_thread = threading.Thread(target=self._render_loop, daemon=True)
        self._render_thread.start()

    def stop(self):
        self._running = False
        if self._render_thread:
            self._render_thread.join(timeout=2.0)

    def add_widget(self, widget: DashboardWidget):
        with self._lock:
            self._widgets[widget.widget_id] = widget

    def remove_widget(self, widget_id: str) -> bool:
        with self._lock:
            if widget_id in self._widgets:
                del self._widgets[widget_id]
                return True
        return False

    def update_widget_data(self, widget_id: str, data: Any):
        with self._lock:
            if widget_id in self._widgets:
                self._widgets[widget_id].data = data

    def register_data_provider(self, name: str, provider: Callable[[], Any]):
        self._data_providers[name] = provider

    def set_layout(self, layout: list[list[str]]):
        with self._lock:
            self._layout = layout

    def _render_loop(self):
        while self._running:
            now = time.time()
            if now - self._last_render >= self._min_render_interval:
                self._render()
                self._last_render = now
            time.sleep(0.05)

    def _render(self):
        if not self.stdscr:
            return

        try:
            self.stdscr.erase()
            max_y, max_x = self.stdscr.getmaxyx()

            with self._lock:
                widgets = list(self._widgets.values())

            for widget in widgets:
                if not widget.visible:
                    continue
                if widget.x + widget.width > max_x or widget.y + widget.height > max_y:
                    continue

                self._render_widget(widget)

            self.stdscr.refresh()
        except curses.error:
            pass
        except Exception:
            pass

    def _render_widget(self, widget: DashboardWidget):
        if not self.stdscr:
            return

        try:
            # Draw border
            self._draw_box(widget.x, widget.y, widget.width, widget.height, widget.title)

            # Render content based on type
            content_x = widget.x + 1
            content_y = widget.y + 1
            content_w = widget.width - 2
            content_h = widget.height - 2

            if widget.widget_type == WidgetType.TEXT:
                self._render_text(widget, content_x, content_y, content_w, content_h)
            elif widget.widget_type == WidgetType.BAR:
                self._render_bar(widget, content_x, content_y, content_w, content_h)
            elif widget.widget_type == WidgetType.GAUGE:
                self._render_gauge(widget, content_x, content_y, content_w, content_h)
            elif widget.widget_type == WidgetType.GRAPH:
                self._render_graph(widget, content_x, content_y, content_w, content_h)
            elif widget.widget_type == WidgetType.TABLE:
                self._render_table(widget, content_x, content_y, content_w, content_h)
            elif widget.widget_type == WidgetType.LOG:
                self._render_log(widget, content_x, content_y, content_w, content_h)
        except Exception:
            pass

    def _draw_box(self, x: int, y: int, w: int, h: int, title: str):
        if not self.stdscr:
            return

        try:
            # Top border
            self.stdscr.addstr(y, x, "┌" + "─" * (w - 2) + "┐")
            # Title
            if title:
                title_str = f" {title} "
                self.stdscr.addstr(y, x + 2, title_str[:w - 4])
            # Bottom border
            self.stdscr.addstr(y + h - 1, x, "└" + "─" * (w - 2) + "┘")
            # Side borders
            for i in range(1, h - 1):
                self.stdscr.addstr(y + i, x, "│")
                self.stdscr.addstr(y + i, x + w - 1, "│")
        except curses.error:
            pass

    def _render_text(self, widget: DashboardWidget, x: int, y: int, w: int, h: int):
        if not self.stdscr:
            return

        data = widget.data
        if callable(data):
            data = data()

        lines = str(data).split('\n')
        for i, line in enumerate(lines[:h]):
            if y + i < self.stdscr.getmaxyx()[0]:
                try:
                    self.stdscr.addstr(y + i, x, line[:w])
                except curses.error:
                    pass

    def _render_bar(self, widget: DashboardWidget, x: int, y: int, w: int, h: int):
        if not self.stdscr:
            return

        data = widget.data
        if callable(data):
            data = data()

        if isinstance(data, dict):
            value = data.get("value", 0)
            max_val = data.get("max", 100)
            label = data.get("label", "")
        else:
            value = float(data) if data else 0
            max_val = 100
            label = ""

        pct = min(1.0, max(0.0, value / max_val)) if max_val > 0 else 0
        bar_width = w - 4
        filled = int(bar_width * pct)

        bar = "█" * filled + "░" * (bar_width - filled)
        text = f"{label} [{bar}] {pct * 100:.1f}%"

        try:
            self.stdscr.addstr(y, x, text[:w])
        except curses.error:
            pass

    def _render_gauge(self, widget: DashboardWidget, x: int, y: int, w: int, h: int):
        # Similar to bar but circular/radial
        self._render_bar(widget, x, y, w, h)

    def _render_graph(self, widget: DashboardWidget, x: int, y: int, w: int, h: int):
        if not self.stdscr:
            return

        data = widget.data
        if callable(data):
            data = data()

        if not isinstance(data, list) or not data:
            return

        # Simple ASCII graph
        max_val = max(data) if data else 1
        min_val = min(data) if data else 0
        range_val = max_val - min_val if max_val != min_val else 1

        for i, val in enumerate(data[-(w - 2):]):
            normalized = (val - min_val) / range_val
            bar_h = int(normalized * (h - 1))
            char = "▁▂▃▄▅▆▇█"[min(7, bar_h)]
            try:
                self.stdscr.addstr(y + h - 1 - bar_h, x + i + 1, char)
            except curses.error:
                pass

    def _render_table(self, widget: DashboardWidget, x: int, y: int, w: int, h: int):
        if not self.stdscr:
            return

        data = widget.data
        if callable(data):
            data = data()

        if not isinstance(data, list):
            return

        for i, row in enumerate(data[:h]):
            if isinstance(row, (list, tuple)):
                line = " | ".join(str(c) for c in row)
            else:
                line = str(row)
            try:
                self.stdscr.addstr(y + i, x, line[:w])
            except curses.error:
                pass

    def _render_log(self, widget: DashboardWidget, x: int, y: int, w: int, h: int):
        if not self.stdscr:
            return

        data = widget.data
        if callable(data):
            data = data()

        if isinstance(data, deque):
            lines = list(data)[-h:]
        elif isinstance(data, list):
            lines = data[-h:]
        else:
            lines = str(data).split('\n')[-h:]

        for i, line in enumerate(lines):
            try:
                self.stdscr.addstr(y + i, x, str(line)[:w])
            except curses.error:
                pass

    def _get_cpu_usage(self) -> dict[str, Any]:
        try:
            import psutil
            return {"value": psutil.cpu_percent(), "max": 100, "label": "CPU"}
        except ImportError:
            return {"value": 0, "max": 100, "label": "CPU"}

    def _get_memory_usage(self) -> dict[str, Any]:
        try:
            import psutil
            mem = psutil.virtual_memory()
            return {"value": mem.used, "max": mem.total, "label": "MEM"}
        except ImportError:
            return {"value": 0, "max": 1, "label": "MEM"}

    def _get_disk_usage(self) -> dict[str, Any]:
        try:
            import psutil
            disk = psutil.disk_usage('/')
            return {"value": disk.used, "max": disk.total, "label": "DISK"}
        except ImportError:
            return {"value": 0, "max": 1, "label": "DISK"}

    def _get_network_usage(self) -> dict[str, Any]:
        try:
            import psutil
            net = psutil.net_io_counters()
            return {"sent": net.bytes_sent, "recv": net.bytes_recv}
        except ImportError:
            return {"sent": 0, "recv": 0}

    def _get_process_count(self) -> int:
        try:
            import psutil
            return len(psutil.pids())
        except ImportError:
            return 0


def create_default_dashboard(stdscr) -> TerminalSystemDashboard:
    dashboard = TerminalSystemDashboard(stdscr)

    # Add default widgets
    dashboard.add_widget(DashboardWidget(
        widget_id="cpu", title="CPU", widget_type=WidgetType.BAR,
        x=0, y=0, width=40, height=5, data=lambda: dashboard._data_providers["cpu"]()
    ))
    dashboard.add_widget(DashboardWidget(
        widget_id="memory", title="Memory", widget_type=WidgetType.BAR,
        x=40, y=0, width=40, height=5, data=lambda: dashboard._data_providers["memory"]()
    ))
    dashboard.add_widget(DashboardWidget(
        widget_id="disk", title="Disk", widget_type=WidgetType.BAR,
        x=80, y=0, width=40, height=5, data=lambda: dashboard._data_providers["disk"]()
    ))
    dashboard.add_widget(DashboardWidget(
        widget_id="processes", title="Processes", widget_type=WidgetType.TEXT,
        x=0, y=5, width=60, height=5, data=lambda: f"Active: {dashboard._data_providers['processes']()}"
    ))
    dashboard.add_widget(DashboardWidget(
        widget_id="network", title="Network", widget_type=WidgetType.TEXT,
        x=60, y=5, width=60, height=5,
        data=lambda: f"Sent: {dashboard._data_providers['network']()['sent'] / 1024 / 1024:.1f}MB Recv: {dashboard._data_providers['network']()['recv'] / 1024 / 1024:.1f}MB"
    ))

    return dashboard
