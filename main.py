#!/usr/bin/env python3
"""
AGENT_SYSTEM_V9 - Main Entry Point
NEURO-CRANIAL OVERLORD v9.0.0
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

try:
    from agent_system_v9 import __codename__, __version__
    from agent_system_v9 import run_tui
    from agent_system_v9.gui import run_with_gui
except ImportError:
    pass


def find_gguf_models() -> list[Path]:
    """Find GGUF model files in common locations."""
    common_locations = [
        Path.home() / "Downloads",
        Path.home() / "Documents",
        Path.home() / ".cache" / "lmdeploy",
        Path.home() / ".local" / "share" / "llama.cpp",
        Path("/models"),
        Path("/opt/models"),
        Path.cwd() / "models",
    ]

    models = []
    for loc in common_locations:
        if loc.exists():
            try:
                for ext in ["*.gguf", "*.GGUF"]:
                    models.extend(loc.glob(ext))
                for p in loc.rglob("*.gguf"):
                    models.append(p)
            except Exception:
                continue
    # Deduplicate
    seen = set()
    unique = []
    for m in models:
        if str(m) not in seen:
            seen.add(str(m))
            unique.append(m)
    return unique


def start_llama_server(model_path: str, host: str = "localhost", port: int = 8080) -> None:
    """Start llama-server with optimal parameters."""
    cmd = [
        "llama-server",
        "--model", model_path,
        "--host", host,
        "--port", str(port),
        "--threads", "8",
        "--ctx-size", "4096",
        "--ngl", "40",
        "--parallel", "2",
        "--ubatch-size", "512",
        "--keep", "2048",
    ]
    # Use subprocess to start
    import subprocess
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


async def main():
    parser = argparse.ArgumentParser(description="AGENT_SYSTEM_V9 - NEURO-CRANIAL OVERLORD")
    parser.add_argument("--version", action="store_true", help="Show version")
    parser.add_argument("--tui", action="store_true", help="Start TUI")
    parser.add_argument("--gui", action="store_true", help="Start GUI with webapp")
    parser.add_argument("--llama-server", action="store_true", help="Start llama-server")
    parser.add_argument("--model", type=str, help="Path to GGUF model")
    parser.add_argument("--api-key", type=str, help="API key for OpenAI-compatible provider")
    parser.add_argument("--api-base", type=str, help="Base URL for OpenAI-compatible provider")
    parser.add_argument("--port", type=int, default=8080, help="Port for services")
    parser.add_argument("--host", type=str, default="localhost", help="Host for services")
    parser.add_argument("--unified", action="store_true", help="Start unified UI (default)")
    parser.add_argument("--term-only", action="store_true", help="Unified UI terminal only")
    parser.add_argument("--web-only", action="store_true", help="Unified UI web only")

    args = parser.parse_args()

    if args.version:
        print(f"{__codename__} v{__version__}")
        return

    # Set API config if provided
    if args.api_key:
        os.environ["OPENAI_API_KEY"] = args.api_key
    if args.api_base:
        os.environ["OPENAI_API_BASE"] = args.api_base

    if args.llama_server:
        models = find_gguf_models()
        if args.model:
            model_path = args.model
        elif models:
            print("Found GGUF models:")
            for i, m in enumerate(models):
                print(f"{i}: {m}")
            choice = input("Select model: ").strip()
            try:
                model_path = str(models[int(choice)])
            except Exception:
                model_path = str(models[0])
        else:
            print("No GGUF models found. Please specify --model")
            return
        start_llama_server(model_path, args.host, args.port)
        return

    # Unified UI (default)
    use_unified = args.unified or (not any([args.tui, args.gui, args.llama_server]))
    if use_unified and run_unified:
        run_unified(term=not args.web_only, web=args.web_only or False)
        return

    if args.gui:
        await run_with_gui(dev=True, tui=args.tui)
        return

    if args.tui:
        run_tui()
        return

    print(f"{__codename__} v{__version__}")
    print("\nUsage:")
    print("  python main.py              Start unified UI (default)")
    print("  python main.py --unified    Start unified UI")
    print("  python main.py --tui         Start TUI")
    print("  python main.py --gui         Start GUI + webapp")
    print("  python main.py --gui --tui  Start GUI + TUI")
    print("  python main.py --llama-server  Start llama-server")
    print("  python main.py --version     Show version")


if __name__ == "__main__":
    asyncio.run(main())

# Add unified UI support
try:
    from agent_system_v9 import run_unified
except Exception:
    run_unified = None
