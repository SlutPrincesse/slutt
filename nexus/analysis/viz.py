"""Inline SVG visualizations for the HTML report (no JS libraries).

Everything here returns an SVG string computed in pure Python: a circular
dependency graph, a squarified-ish treemap of files, and a health trend
chart from history entries.
"""

from __future__ import annotations

import html
import math

from .analyzer import FileMetrics
from .graph import DependencyGraph

_GRADE_COLORS = {"A": "#22c55e", "B": "#84cc16", "C": "#eab308", "D": "#f97316", "F": "#ef4444"}


def _cx_color(avg_cx: float) -> str:
    """Green→red color for a file's average complexity."""
    if avg_cx <= 3:
        return "#22c55e"
    if avg_cx <= 6:
        return "#84cc16"
    if avg_cx <= 10:
        return "#eab308"
    if avg_cx <= 15:
        return "#f97316"
    return "#ef4444"


def dependency_svg(graph: DependencyGraph, cycles: list[list[str]], size: int = 640) -> str:
    """Circular-layout dependency graph; cycle edges drawn red."""
    modules = sorted(graph.edges)
    if not modules:
        return ""
    n = len(modules)
    cx = cy = size / 2
    radius = size / 2 - 110
    pos = {
        m: (cx + radius * math.cos(2 * math.pi * i / n - math.pi / 2),
            cy + radius * math.sin(2 * math.pi * i / n - math.pi / 2))
        for i, m in enumerate(modules)
    }
    cycle_edges = {
        (c[i], c[i + 1]) for c in cycles for i in range(len(c) - 1)
    }
    fan_in = graph.fan_in()

    parts = [f'<svg viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg" '
             f'style="max-width:{size}px;width:100%;height:auto">']
    parts.append('<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" '
                 'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
                 '<path d="M0 0L10 5L0 10z" fill="#475569"/></marker>'
                 '<marker id="arrbad" viewBox="0 0 10 10" refX="9" refY="5" '
                 'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
                 '<path d="M0 0L10 5L0 10z" fill="#ef4444"/></marker></defs>')
    parts.extend(_edge_lines(graph, pos, cycle_edges))
    parts.extend(_node_dots(modules, pos, fan_in, cx, cy, radius))
    parts.append("</svg>")
    return "".join(parts)


def _edge_lines(graph: DependencyGraph, pos: dict, cycle_edges: set) -> list[str]:
    """SVG lines for every import edge, red when part of a cycle."""
    lines = []
    for src, targets in graph.edges.items():
        x1, y1 = pos[src]
        for dst in targets:
            x2, y2 = pos[dst]
            # shorten the line so the arrowhead lands on the node ring
            dx, dy = x2 - x1, y2 - y1
            dist = math.hypot(dx, dy) or 1
            pad = 14
            xa, ya = x1 + dx / dist * pad, y1 + dy / dist * pad
            xb, yb = x2 - dx / dist * pad, y2 - dy / dist * pad
            bad = (src, dst) in cycle_edges
            stroke, marker, width = (
                ("#ef4444", "arrbad", "2") if bad else ("#475569", "arr", "1.2")
            )
            lines.append(f'<line x1="{xa:.1f}" y1="{ya:.1f}" x2="{xb:.1f}" y2="{yb:.1f}" '
                         f'stroke="{stroke}" stroke-width="{width}" opacity="0.8" '
                         f'marker-end="url(#{marker})"/>')
    return lines


def _node_dots(modules: list[str], pos: dict, fan_in: dict,
               cx: float, cy: float, radius: float) -> list[str]:
    """SVG circles and outward labels for every module node."""
    max_fan = max(fan_in.values(), default=1) or 1
    dots = []
    for m in modules:
        x, y = pos[m]
        r = 6 + 8 * fan_in.get(m, 0) / max_fan
        label = html.escape(m.rsplit(".", 1)[-1])
        # place the label outward from the circle center
        lx = cx + (radius + 26) * (x - cx) / radius
        ly = cy + (radius + 26) * (y - cy) / radius
        anchor = "start" if lx > cx + 5 else ("end" if lx < cx - 5 else "middle")
        dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="#38bdf8" '
                    f'stroke="#0f172a" stroke-width="2"><title>{html.escape(m)} '
                    f'(fan-in {fan_in.get(m, 0)})</title></circle>')
        dots.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
                    f'fill="#94a3b8" font-size="12">{label}</text>')
    return dots


def treemap_svg(files: list[FileMetrics], width: int = 1040, height: int = 320) -> str:
    """Slice-and-dice treemap: area = SLOC, color = avg complexity."""
    items = sorted((f for f in files if f.sloc > 0), key=lambda f: f.sloc, reverse=True)
    if not items:
        return ""
    total = sum(f.sloc for f in items)
    parts = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
             f'style="width:100%;height:auto">']
    x, y, w, h = 0.0, 0.0, float(width), float(height)
    horizontal = w >= h
    for i, f in enumerate(items):
        frac = f.sloc / total
        remaining = sum(g.sloc for g in items[i:]) / total or 1e-9
        share = frac / remaining
        if horizontal:
            rw, rh = w * share, h
            rx, ry = x, y
            x += rw
            w -= rw
        else:
            rw, rh = w, h * share
            rx, ry = x, y
            y += rh
            h -= rh
        horizontal = w >= h
        color = _cx_color(f.avg_complexity)
        name = html.escape(f.path.rsplit("/", 1)[-1])
        parts.append(f'<rect x="{rx:.1f}" y="{ry:.1f}" width="{max(rw, 1):.1f}" '
                     f'height="{max(rh, 1):.1f}" fill="{color}" stroke="#0f172a" '
                     f'stroke-width="2" rx="4" opacity="0.85">'
                     f'<title>{html.escape(f.path)} — {f.sloc} SLOC, '
                     f'avg CC {f.avg_complexity:.1f}</title></rect>')
        if rw > 70 and rh > 24:
            parts.append(f'<text x="{rx + 8:.1f}" y="{ry + 18:.1f}" fill="#0f172a" '
                         f'font-size="12" font-weight="700">{name}</text>')
            if rh > 42:
                parts.append(f'<text x="{rx + 8:.1f}" y="{ry + 34:.1f}" fill="#0f172a" '
                             f'font-size="11">{f.sloc} sloc</text>')
    parts.append("</svg>")
    return "".join(parts)


def trend_svg(entries: list[dict], width: int = 1040, height: int = 180) -> str:
    """Health-score line chart over recorded history runs."""
    scores = [e.get("score") for e in entries if isinstance(e.get("score"), (int, float))]
    if len(scores) < 2:
        return ""
    pad = 30
    n = len(scores)
    xs = [pad + (width - 2 * pad) * i / (n - 1) for i in range(n)]
    ys = [height - pad - (height - 2 * pad) * s / 100 for s in scores]
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    grid = "".join(
        f'<line x1="{pad}" y1="{height - pad - (height - 2 * pad) * g / 100:.1f}" '
        f'x2="{width - pad}" y2="{height - pad - (height - 2 * pad) * g / 100:.1f}" '
        f'stroke="#334155" stroke-width="1" stroke-dasharray="4 4"/>'
        f'<text x="{pad - 6}" y="{height - pad - (height - 2 * pad) * g / 100 + 4:.1f}" '
        f'text-anchor="end" fill="#64748b" font-size="10">{g}</text>'
        for g in (25, 50, 75, 100)
    )
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="#38bdf8">'
        f'<title>{html.escape(str(e.get("date", "")))}: {s}</title></circle>'
        for x, y, s, e in zip(xs, ys, scores, entries)
    )
    area = f"{pad},{height - pad} {pts} {width - pad},{height - pad}"
    return (
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;height:auto">{grid}'
        f'<polygon points="{area}" fill="#38bdf8" opacity="0.12"/>'
        f'<polyline points="{pts}" fill="none" stroke="#38bdf8" stroke-width="2.5" '
        f'stroke-linejoin="round"/>{dots}</svg>'
    )
