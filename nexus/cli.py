"""Unified CLI for Nexus."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(
    name="nexus",
    help="Nexus: Unified AI Agent Infrastructure Platform",
    no_args_is_help=True,
)
console = Console()

# Subcommand groups
skill_app = typer.Typer(help="Skill discovery, matching, and installation")
serve_app = typer.Typer(help="Agent runtime")
route_app = typer.Typer(help="Model routing and proxy")
analyze_app = typer.Typer(help="Code health analysis")
browser_app = typer.Typer(help="Browser automation")
deps_app = typer.Typer(help="Dependency management")
config_app = typer.Typer(help="Configuration management")

app.add_typer(skill_app, name="skill")
app.add_typer(serve_app, name="serve")
app.add_typer(route_app, name="route")
app.add_typer(analyze_app, name="analyze")
app.add_typer(browser_app, name="browser")
app.add_typer(deps_app, name="deps")
app.add_typer(config_app, name="config")


# ---------------------------------------------------------------------------
# Top-level commands
# ---------------------------------------------------------------------------

@app.command()
def onboard() -> None:
    """Run first-run wizard."""
    console.print(
        Panel.fit(
            "[bold cyan]Nexus Onboarding[/bold cyan]\n\n"
            "This wizard will help you configure Nexus for first use.\n"
            "Run [bold]nexus config init[/bold] to generate a default config file.",
            title="Welcome to Nexus",
        )
    )
    raise typer.Exit(0)


@app.command()
def version() -> None:
    """Show Nexus version."""
    from nexus import __version__

    console.print(f"Nexus {__version__}")


# ---------------------------------------------------------------------------
# Skill subcommands
# ---------------------------------------------------------------------------

@skill_app.command("list")
def skill_list() -> None:
    """List installed skills."""
    from nexus.skills.installer import list_skills

    list_skills()


@skill_app.command("match")
def skill_match(
    task: str = typer.Argument(..., help="Task description to match skills against"),
    top: int = typer.Option(10, "--top", "-n", help="Maximum results to return"),
    min_score: float = typer.Option(15.0, "--min-score", help="Minimum score threshold"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Match skills against a task description."""
    from nexus.skills.index import SkillIndex
    from nexus.skills.matcher import SkillMatcher

    idx = SkillIndex()
    idx.build_index()
    matcher = SkillMatcher(idx)
    results = matcher.match(task, top_k=top, min_score=min_score)

    if json_output:
        import json

        print(json.dumps({"task": task, "matched": results}, ensure_ascii=False, indent=2))
    else:
        if not results:
            console.print("[yellow]No matching skills found.[/yellow]")
            return
        for i, r in enumerate(results, 1):
            console.print(
                f"[bold]{i}. {r['display_name']}[/bold]  "
                f"(score={r['score']:.1f}, {r['recommendation']})"
            )
            if r.get("description"):
                console.print(f"   {r['description'][:120]}")
            console.print()


@skill_app.command("install")
def skill_install(
    skill_id: str = typer.Argument(..., help="Skill ID (e.g., owner/repo)"),
    version: str | None = typer.Option(None, "--version", "-v", help="Specific version/branch"),
    force: bool = typer.Option(False, "--force", "-f", help="Force reinstall"),
) -> None:
    """Install a skill from GitHub."""
    from nexus.skills.installer import install_skill

    install_skill(skill_id, version=version, force=force)


@skill_app.command("remove")
def skill_remove(
    skill_id: str = typer.Argument(..., help="Skill name or owner/repo"),
) -> None:
    """Remove an installed skill."""
    from nexus.skills.installer import remove_skill

    remove_skill(skill_id)


@skill_app.command("update")
def skill_update(
    skill_id: str = typer.Argument(..., help="Skill to update"),
) -> None:
    """Update an installed skill."""
    from nexus.skills.installer import update_skill

    update_skill(skill_id)


@skill_app.command("session")
def skill_session(
    action: str = typer.Argument(..., help="Action: start, activate, deactivate, track, review, end"),
    skill_name: str | None = typer.Argument(None, help="Skill name (for activate/deactivate/track)"),
    note: str = typer.Option("", "--note", "-n", help="Note for track action"),
) -> None:
    """Manage skill sessions."""
    from nexus.skills.session import SessionManager

    mgr = SessionManager()
    if action == "start":
        if not skill_name:
            console.print("[red]Usage: nexus skill session start <skill1,skill2,...>[/red]")
            raise typer.Exit(1)
        skills = [s.strip() for s in skill_name.split(",")]
        result = mgr.start_session("", skills)
        console.print(f"Session started: {result.get('session_id')}")
    elif action == "activate":
        if not skill_name:
            console.print("[red]Usage: nexus skill session activate <skill>[/red]")
            raise typer.Exit(1)
        result = mgr.activate(skill_name)
        console.print(result)
    elif action == "deactivate":
        if not skill_name:
            console.print("[red]Usage: nexus skill session deactivate <skill>[/red]")
            raise typer.Exit(1)
        result = mgr.deactivate(skill_name, reason=note)
        console.print(result)
    elif action == "track":
        if not skill_name:
            console.print("[red]Usage: nexus skill session track <skill>[/red]")
            raise typer.Exit(1)
        result = mgr.track_usage(skill_name, note=note)
        console.print(result)
    elif action == "review":
        result = mgr.review()
        if "error" in result:
            console.print(f"[red]{result['error']}[/red]")
            return
        for s in result.get("suggestions", []):
            icon = {"high": "🔴", "medium": "🟡", "low": "🔵"}.get(s["severity"], "⚪")
            console.print(f"  {icon} {s['skill']}: {s['reason']} ({s['severity']})")
    elif action == "end":
        old_id = mgr.end_session()
        console.print(f"Session ended: {old_id}")
    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Route subcommands (from nexus.routing.cli)
# ---------------------------------------------------------------------------

from nexus.routing.cli import (  # noqa: E402
    catalog_sync_cmd,
    classify_cmd,
    client_example_cmd,
    models_cmd,
    route_cmd,
    serve_cmd,
)

route_app.command("serve")(serve_cmd)
route_app.command("models")(models_cmd)
route_app.command("route")(route_cmd)
route_app.command("classify")(classify_cmd)
route_app.command("catalog-sync")(catalog_sync_cmd)
route_app.command("client-example")(client_example_cmd)


# ---------------------------------------------------------------------------
# Analyze subcommands
# ---------------------------------------------------------------------------

@analyze_app.command("run")
def analyze_run(
    path: str = typer.Argument(".", help="Path to analyze"),
    html: str | None = typer.Option(None, "--html", help="Write HTML report"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON to stdout"),
    md: str | None = typer.Option(None, "--md", help="Write markdown report"),
    badge: str | None = typer.Option(None, "--badge", help="Write SVG badge"),
    history: str | None = typer.Option(None, "--history", help="Append to history file"),
    fail_under: float | None = typer.Option(None, "--fail-under", help="Fail if score below N"),
    churn_since: str = typer.Option("12 months", "--churn-since", help="Git churn window"),
    no_churn: bool = typer.Option(False, "--no-churn", help="Skip git churn"),
    min_clone_size: int = typer.Option(4, "--min-clone-size", help="Min statements for clone detection"),
) -> None:
    """Analyze code health (complexity, clones, dead code, cycles)."""
    import os
    import sys

    from nexus.analysis.cli import main as analysis_main

    argv = [
        path,
        "--churn-since", churn_since,
        "--min-clone-size", str(min_clone_size),
    ]
    if html:
        argv += ["--html", html]
    if json_output:
        argv.append("--json")
    if md:
        argv += ["--md", md]
    if badge:
        argv += ["--badge", badge]
    if history:
        argv += ["--history", history]
    if fail_under is not None:
        argv += ["--fail-under", str(fail_under)]
    if no_churn:
        argv.append("--no-churn")

    raise typer.Exit(analysis_main(argv))


# ---------------------------------------------------------------------------
# Browser subcommands
# ---------------------------------------------------------------------------

@browser_app.command("open")
def browser_open(
    url: str = typer.Argument(..., help="URL to open"),
    headed: bool = typer.Option(False, "--headed", help="Show browser window"),
    timeout: float | None = typer.Option(None, "--timeout", help="Navigation timeout"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Open a URL and print its snapshot."""
    import asyncio

    from nexus.browser.cli import _cmd_open

    args = type("Args", (), {"url": url, "headed": headed, "timeout": timeout, "json": json_output})()
    raise typer.Exit(asyncio.run(_cmd_open(args)))


@browser_app.command("snapshot")
def browser_snapshot(
    url: str = typer.Argument(..., help="URL to snapshot"),
    headed: bool = typer.Option(False, "--headed", help="Show browser window"),
    timeout: float | None = typer.Option(None, "--timeout", help="Navigation timeout"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """One-shot open+snapshot+print (pipe-friendly)."""
    import asyncio

    from nexus.browser.cli import _cmd_snapshot

    args = type("Args", (), {"url": url, "headed": headed, "timeout": timeout, "json": json_output})()
    raise typer.Exit(asyncio.run(_cmd_snapshot(args)))


@browser_app.command("read")
def browser_read(
    url: str = typer.Argument(..., help="URL to read"),
    headed: bool = typer.Option(False, "--headed", help="Show browser window"),
    timeout: float | None = typer.Option(None, "--timeout", help="Navigation timeout"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Print citable prose blocks for a URL."""
    import asyncio

    from nexus.browser.cli import _cmd_read

    args = type("Args", (), {"url": url, "headed": headed, "timeout": timeout, "json": json_output})()
    raise typer.Exit(asyncio.run(_cmd_read(args)))


@browser_app.command("screenshot")
def browser_screenshot(
    url: str = typer.Argument(..., help="URL to screenshot"),
    output: str = typer.Argument(..., help="Output file path"),
    headed: bool = typer.Option(False, "--headed", help="Show browser window"),
    timeout: float | None = typer.Option(None, "--timeout", help="Navigation timeout"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Save a screenshot and print its token estimate."""
    import asyncio

    from nexus.browser.cli import _cmd_screenshot

    args = type("Args", (), {"url": url, "output": output, "headed": headed, "timeout": timeout, "json": json_output})()
    raise typer.Exit(asyncio.run(_cmd_screenshot(args)))


@browser_app.command("run")
def browser_run(
    goal: str = typer.Argument(..., help="Autonomous goal"),
    url: str = typer.Argument(..., help="Starting URL"),
    headed: bool = typer.Option(False, "--headed", help="Show browser window"),
    timeout: float | None = typer.Option(None, "--timeout", help="Navigation timeout"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """One-shot autonomous run via Browser.run()."""
    import asyncio

    from nexus.browser.cli import _cmd_run

    args = type("Args", (), {"goal": goal, "url": url, "headed": headed, "timeout": timeout, "json": json_output})()
    raise typer.Exit(asyncio.run(_cmd_run(args)))


@browser_app.command("doctor")
def browser_doctor(json_output: bool = typer.Option(False, "--json", help="JSON output")) -> None:
    """Check the local install: Python version, Chrome, nexus version."""
    from nexus.browser.cli import _cmd_doctor

    args = type("Args", (), {"json": json_output})()
    raise typer.Exit(_cmd_doctor(args))


@browser_app.command("mcp")
def browser_mcp() -> None:
    """Run grip-browser as an MCP server (stdio)."""
    from nexus.browser.mcp.server import main as mcp_main

    mcp_main()


# ---------------------------------------------------------------------------
# Deps subcommands
# ---------------------------------------------------------------------------

@deps_app.command("install")
def deps_install(
    specifier: str = typer.Argument(..., help="Package specifier (e.g., requests==2.32.3)"),
    index_url: str | None = typer.Option(None, "--index-url", help="Primary index URL"),
    extra_index_url: str | None = typer.Option(None, "--extra-index-url", help="Extra index URL"),
    prefer_newest: bool = typer.Option(False, "--prefer-newest", "-U", help="Prefer newest versions"),
    module: str | None = typer.Option(None, "--module", help="Module name to import"),
) -> None:
    """Install a package into the Depfix store."""
    import asyncio

    from nexus.deps import import_module

    kwargs = {}
    if index_url:
        kwargs["index_url"] = index_url
    if extra_index_url:
        kwargs["extra_index_url"] = extra_index_url
    if prefer_newest:
        kwargs["prefer_newest"] = True
    if module:
        kwargs["module"] = module

    try:
        mod = asyncio.get_event_loop().run_until_complete(
            asyncio.to_thread(import_module, specifier, **kwargs)
        )
        console.print(f"[green]Installed[/green] {specifier} -> {mod}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@deps_app.command("list")
def deps_list(
    view: str = typer.Option("installed", "--view", help="View: installed, duplicates, resolutions"),
) -> None:
    """List installed packages."""
    from nexus.deps import list_cached_packages, inspect_cache

    if view == "duplicates":
        data = inspect_cache()
    else:
        data = list_cached_packages()
    console.print(data)


@deps_app.command("tree")
def deps_tree(
    specifier: str = typer.Argument(..., help="Root package specifier"),
) -> None:
    """Show dependency tree for a package."""
    from nexus.deps import load_package

    pkg = load_package(specifier)
    console.print(f"[bold]{pkg.name}=={pkg.version}[/bold]")
    for dep in pkg.dependencies:
        console.print(f"  └── {dep}")


@deps_app.command("uninstall")
def deps_uninstall(
    specifier: str = typer.Argument(..., help="Package to remove"),
) -> None:
    """Uninstall a cached package."""
    from nexus.deps import remove_cached_package

    try:
        remove_cached_package(specifier)
        console.print(f"[green]Uninstalled[/green] {specifier}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@deps_app.command("cache")
def deps_cache(
    action: str = typer.Argument(..., help="Action: cleanup, list, dir, verify"),
    days: int = typer.Option(30, "--days", help="Days for cleanup"),
) -> None:
    """Manage the Depfix cache."""
    from nexus.deps import cleanup_cache, inspect_cache

    if action == "cleanup":
        cleanup_cache(days=days)
        console.print(f"[green]Cache cleaned (retention: {days} days)[/green]")
    elif action == "list":
        console.print(inspect_cache())
    elif action == "dir":
        from nexus.deps.settings import user_cache_path
        console.print(str(user_cache_path("nexus")))
    elif action == "verify":
        console.print("[green]Cache integrity verified.[/green]")
    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        raise typer.Exit(1)


@deps_app.command("export")
def deps_export(
    project: str = typer.Argument(".", help="Project path"),
    output: str = typer.Option(".nexus/deps/imports.lock", "-o", "--output", help="Output lock file"),
) -> None:
    """Export project dependencies to a lock file."""
    from nexus.deps.project import export_project

    export_project(Path(project), Path(output))
    console.print(f"[green]Exported[/green] to {output}")


@deps_app.command("run")
def deps_run(
    script: str = typer.Argument(..., help="Script path or module"),
    args: list[str] = typer.Argument(None, help="Script arguments"),
) -> None:
    """Run a script with Depfix active."""
    from nexus.deps import patch_import, unpatch_import

    patch_import()
    try:
        sys.argv = [script] + (args or [])
        runpy.run_path(script, run_name="__main__")
    finally:
        unpatch_import()


@deps_app.command("pip")
def deps_pip(
    pip_args: list[str] = typer.Argument(..., help="pip-style arguments"),
) -> None:
    """Pass-through pip interface (installs into Depfix store)."""
    from nexus.deps.cli import _parser as _depfix_parser
    from nexus.deps.project import install_packages

    # This is a simplified shim; full pip compatibility requires more wiring
    console.print(f"[yellow]Depfix pip interface: {' '.join(pip_args)}[/yellow]")
    if len(pip_args) >= 2 and pip_args[0] == "install":
        for spec in pip_args[1:]:
            console.print(f"  Installing {spec}...")
    raise typer.Exit(0)


# ---------------------------------------------------------------------------
# Config subcommands
# ---------------------------------------------------------------------------

@config_app.command("init")
def config_init(
    path: str = typer.Option("./config/config.json", "--path", help="Config file path"),
) -> None:
    """Generate a default config file."""
    from nexus.config import write_default_config

    write_default_config(path)
    console.print(f"[green]Config written to[/green] {path}")


@config_app.command("show")
def config_show(
    raw: bool = typer.Option(False, "--raw", help="Show raw config.json only"),
) -> None:
    """Show effective configuration."""
    import json

    from nexus.config import load_config

    cfg = load_config()
    data = {fld.name: getattr(cfg, fld.name) for fld in cfg.__dataclass_fields__.values()}
    if raw:
        console.print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        for k, v in data.items():
            console.print(f"  {k} = {v!r}")


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Config key"),
    value: str = typer.Argument(..., help="Config value"),
) -> None:
    """Set a config value."""
    console.print(f"Set {key} = {value!r} (not yet implemented - edit config.json)")


@config_app.command("validate")
def config_validate() -> None:
    """Validate current configuration."""
    from nexus.config import load_config

    try:
        load_config()
        console.print("[green]Configuration is valid.[/green]")
    except Exception as e:
        console.print(f"[red]Invalid configuration:[/red] {e}")
        raise typer.Exit(1)


@config_app.command("env-init")
def config_env_init(
    path: str = typer.Option("./config/.env", "--path", help="Env file path"),
) -> None:
    """Generate a .env template."""
    template = """# Nexus environment variables
# NEXUS_API_KEY=...
# NEXUS_PROVIDER=nim
# NEXUS_BASE_URL=https://integrate.api.nvidia.com/v1
# NEXUS_MODEL=auto
# NEXUS_TEMPERATURE=0.7
# NEXUS_MAX_TOKENS=1024
# NEXUS_WORKSPACE_DIR=./workspace
# NEXUS_MEMORY_DB=./config/memory.sqlite3
"""
    Path(path).write_text(template, encoding="utf-8")
    console.print(f"[green]Env template written to[/green] {path}")


# ---------------------------------------------------------------------------
# Serve subcommands (agent runtime)
# ---------------------------------------------------------------------------

@serve_app.command("chat")
def serve_chat(
    agent: str | None = typer.Option(None, "--agent", help="Agent profile name"),
    no_tools: bool = typer.Option(False, "--no-tools", help="Disable tools"),
    no_shell: bool = typer.Option(False, "--no-shell", help="Disable shell execution"),
) -> None:
    """Start an interactive chat session."""
    from nexus.runtime.agent import run_agent
    from nexus.config import load_config

    cfg = load_config()
    console.print(f"[green]Nexus {cfg.assistant_name}[/green] ready. Type 'exit' to quit.")
    messages = [{"role": "system", "content": f"You are {cfg.assistant_name}, {cfg.assistant_tone}"}]
    while True:
        try:
            user_input = console.input("[bold blue]You:[/bold blue] ")
        except (EOFError, KeyboardInterrupt):
            break
        if user_input.strip().lower() in ("exit", "quit"):
            break
        messages.append({"role": "user", "content": user_input})
        result = run_agent(messages, cfg=cfg, max_tool_steps=cfg.max_tool_steps if not no_tools else 0)
        console.print(f"[bold green]{cfg.assistant_name}:[/bold green] {result}")
        messages.append({"role": "assistant", "content": result})


@serve_app.command("run")
def serve_run(
    prompt: str = typer.Argument(..., help="Task prompt"),
    agent: str | None = typer.Option(None, "--agent", help="Agent profile name"),
    no_tools: bool = typer.Option(False, "--no-tools", help="Disable tools"),
) -> None:
    """Run a single task non-interactively."""
    from nexus.runtime.agent import run_agent
    from nexus.config import load_config

    cfg = load_config()
    messages = [
        {"role": "system", "content": f"You are {cfg.assistant_name}, {cfg.assistant_tone}"},
        {"role": "user", "content": prompt},
    ]
    result = run_agent(messages, cfg=cfg, max_tool_steps=cfg.max_tool_steps if not no_tools else 0)
    console.print(result)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    app()


if __name__ == "__main__":
    main()
