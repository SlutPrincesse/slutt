"""Command-line interface for Codi."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .analyzer import analyze_project, read_sources
from .baseline import compare, save_baseline
from .churn import churn_risk, collect_churn
from .config import apply_config, load_config
from .gha import emit_annotations
from .deadcode import find_dead_functions
from .duplication import find_clones
from .graph import DependencyGraph
from .history import append_history, sparkline
from .markdown import render_badge, render_markdown
from .report import render_html, render_json
from .scoring import compute_health

_GRADE_ICON = {"A": "🟢", "B": "🟢", "C": "🟡", "D": "🟠", "F": "🔴"}


def _print_summary(target: str, health, files) -> None:
    """Render the terminal health summary with hotspots and cycles."""
    bar_len = 30
    filled = int(bar_len * health.score / 100)
    bar = "█" * filled + "░" * (bar_len - filled)
    print()
    print(f"  Codi v{__version__} — {target}")
    print(f"  {'─' * 60}")
    print(f"  Health  {bar}  {health.score}/100  grade {health.grade}")
    print(f"  Files: {health.total_files}   SLOC: {health.total_sloc:,}   "
          f"Functions: {health.total_functions}   Avg CC: {health.avg_complexity}")
    print(f"  Docstrings: {health.docstring_coverage:.0%}   "
          f"Type hints: {health.annotation_coverage:.0%}   "
          f"Import cycles: {len(health.cycles)}   Parse errors: {len(health.parse_errors)}")
    if health.hotspots:
        print(f"\n  Top refactoring hotspots:")
        for h in health.hotspots[:5]:
            icon = _GRADE_ICON.get(h.function.grade, "⚪")
            print(f"   {icon} {h.function.qualname}  ({h.file}:{h.function.lineno})  "
                  f"CC={h.function.complexity}  — {'; '.join(h.reasons)}")
            if h.advice:
                print(f"      ↳ {h.advice}")
    if health.clone_groups:
        print(f"\n  Duplicated code ({health.duplication:.0%} of functions):")
        for g in health.clone_groups[:5]:
            where = ", ".join(f"{s.file}:{s.lineno} {s.qualname}" for s in g.sites)
            print(f"   ⧉ {len(g.sites)} copies × {g.size} statements — {where}")
    if health.dead_functions:
        print(f"\n  Possibly dead code (never referenced):")
        for d in health.dead_functions[:8]:
            print(f"   ✂ {d.qualname}  ({d.file}:{d.lineno})")
    for cycle in health.cycles:
        print(f"\n  ⚠ circular import: {' → '.join(cycle)}")
    print()


def _print_deltas(deltas) -> None:
    """Show baseline comparison as improved/regressed metric lines."""
    if not deltas:
        print("  Baseline: no metric changes.")
        return
    print("  Changes vs baseline:")
    for d in deltas:
        arrow = "▲" if d.change > 0 else "▼"
        mark = "✓" if d.improved else "✗"
        print(f"   {mark} {d.metric}: {d.before} → {d.after}  ({arrow} {abs(d.change)})")
    print()


def _print_extras(churn_ranking, history, deltas) -> None:
    """Terminal sections for churn risk, trend sparkline and baseline deltas."""
    if churn_ranking:
        print("  Churn risk (git commits × complexity — fix these first):")
        for path, commits, cx, risk in churn_ranking[:5]:
            print(f"   🔥 {path}  {commits} commits × CC {cx:.1f}  = risk {risk}")
        print()
    if history and len(history) >= 2:
        scores = [e["score"] for e in history if isinstance(e.get("score"), (int, float))]
        print(f"  Trend ({len(scores)} runs): {sparkline(scores)}  "
              f"{scores[0]} → {scores[-1]}")
        print()
    if deltas is not None:
        _print_deltas(deltas)


def _collect_extras(args, root: Path, files, health, extra):
    """Gather churn ranking, history entries and baseline deltas per flags."""
    churn_ranking = None
    if not args.no_churn:
        churn = collect_churn(root, since=args.churn_since)
        if churn:
            complexity_by_file = {f.path: f.avg_complexity for f in files}
            churn_ranking = churn_risk(churn, complexity_by_file) or None
    history = args.history and append_history(Path(args.history), health, extra) or None
    deltas = None
    if args.baseline and Path(args.baseline).exists():
        deltas = compare(Path(args.baseline), health, extra)
    return churn_ranking, history, deltas


def _configure_console() -> None:
    """Legacy Windows consoles default to cp1252; keep unicode output safe."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _build_parser() -> argparse.ArgumentParser:
    """Define the codi command-line interface."""
    parser = argparse.ArgumentParser(
        prog="codi",
        description="Zero-dependency Python code-health analyzer: "
        "complexity, hotspots, dependency graph, HTML report.",
    )
    parser.add_argument("path", nargs="?", default=".", help="file or directory to analyze")
    parser.add_argument("--html", metavar="FILE", help="write a self-contained HTML report")
    parser.add_argument("--json", metavar="FILE", help="write a JSON report ('-' for stdout)")
    parser.add_argument("--md", metavar="FILE",
                        help="write a markdown report for PR comments ('-' for stdout)")
    parser.add_argument("--badge", metavar="FILE", help="write an SVG health badge")
    parser.add_argument("--history", metavar="FILE",
                        help="append this run to a trend history file (shows sparkline + chart)")
    parser.add_argument("--no-churn", action="store_true",
                        help="skip git churn analysis")
    parser.add_argument("--gha", action="store_true",
                        help="emit GitHub Actions ::warning annotations "
                             "(automatic when GITHUB_ACTIONS=true)")
    parser.add_argument("--churn-since", default="12 months", metavar="WINDOW",
                        help="git log window for churn (default '12 months')")
    parser.add_argument("--fail-under", type=float, metavar="SCORE",
                        help="exit non-zero if health score is below SCORE (for CI gates)")
    parser.add_argument("--save-baseline", metavar="FILE",
                        help="save this run's metrics as a baseline snapshot")
    parser.add_argument("--baseline", metavar="FILE",
                        help="compare this run against a saved baseline")
    parser.add_argument("--min-clone-size", type=int, default=4, metavar="N",
                        help="minimum statements for clone detection (default 4)")
    parser.add_argument("--version", action="version", version=f"codi {__version__}")
    return parser


def _emit_reports(args, target: str, files, graph, health,
                  churn_ranking=None, history=None, deltas=None) -> None:
    """Write any requested HTML/JSON/markdown/badge outputs."""
    if args.html:
        Path(args.html).write_text(
            render_html(target, files, graph, health,
                        churn_ranking=churn_ranking, history=history),
            encoding="utf-8",
        )
        print(f"HTML report written to {args.html}")
    if args.json == "-":
        print(render_json(target, files, graph, health, churn_ranking))
    elif args.json:
        Path(args.json).write_text(
            render_json(target, files, graph, health, churn_ranking), encoding="utf-8"
        )
        print(f"JSON report written to {args.json}")
    if args.md == "-":
        print(render_markdown(target, health, churn_ranking, deltas))
    elif args.md:
        Path(args.md).write_text(
            render_markdown(target, health, churn_ranking, deltas), encoding="utf-8"
        )
        print(f"Markdown report written to {args.md}")
    if args.badge:
        Path(args.badge).write_text(render_badge(health), encoding="utf-8")
        print(f"Badge written to {args.badge}")


def main(argv: list[str] | None = None) -> int:
    """Entry point: parse args, analyze, emit reports, apply CI gate."""
    _configure_console()
    parser = _build_parser()
    args = parser.parse_args(argv)

    root = Path(args.path).resolve()
    if not root.exists():
        parser.error(f"path does not exist: {root}")

    defaults = {a.dest: parser.get_default(a.dest) for a in parser._actions}
    apply_config(args, load_config(root), defaults)

    files = analyze_project(root)
    if not files:
        print(f"No Python files found under {root}", file=sys.stderr)
        return 1

    sources = read_sources(root, files)
    graph = DependencyGraph.build(files)
    clones = find_clones(files, sources, min_statements=args.min_clone_size)
    dead = find_dead_functions(files, sources)
    health = compute_health(files, graph, clones=clones, dead=dead)
    target = str(root)
    extra = {"clone_groups": len(clones), "dead_functions": len(dead)}

    churn_ranking, history, deltas = _collect_extras(args, root, files, health, extra)

    _emit_reports(args, target, files, graph, health,
                  churn_ranking=churn_ranking, history=history, deltas=deltas)

    if args.json != "-" and args.md != "-":
        _print_summary(target, health, files)
        _print_extras(churn_ranking, history, deltas)

    if args.gha or os.environ.get("GITHUB_ACTIONS") == "true":
        for line in emit_annotations(health):
            print(line)
    if args.save_baseline:
        save_baseline(Path(args.save_baseline), health, extra)
        print(f"Baseline saved to {args.save_baseline}")

    if args.fail_under is not None and health.score < args.fail_under:
        print(f"FAIL: health score {health.score} is below threshold {args.fail_under}",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
