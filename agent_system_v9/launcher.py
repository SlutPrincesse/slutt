"""
Launcher for AGENT_SYSTEM_V9 with model discovery and API management
"""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from .utils import find_gguf_models, get_api_config, set_api_config
from .tui import run_tui
from .gui import run_with_gui


def discover_and_select_model(models: List[Path]) -> Optional[Path]:
    """Interactively select a model."""
    if not models:
        return None
    print("Found GGUF models:")
    for i, m in enumerate(models):
        print(f"  [{i}] {m.name} ({m.parent})")
    try:
        choice = input(f"Select model [0-{len(models)-1}] (default: 0): ").strip()
        if not choice:
            return models[0]
        idx = int(choice)
        if 0 <= idx < len(models):
            return models[idx]
    except (ValueError, IndexError, EOFError):
        return models[0]
    return models[0]


def start_llama_server(model_path: str, host: str = "localhost", port: int = 8080,
                       ctx_size: int = 4096, threads: int = 8, ngl: int = 40) -> subprocess.Popen:
    """Start llama-server with optimal parameters."""
    cmd = [
        "llama-server",
        "--model", model_path,
        "--host", host,
        "--port", str(port),
        "--threads", str(threads),
        "--ctx-size", str(ctx_size),
        "--ngl", str(ngl),
        "--parallel", "2",
        "--ubatch-size", "512",
        "--keep", "2048",
    ]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


async def launch():
    parser = argparse.ArgumentParser(description="AGENT_SYSTEM_V9 Launcher")
    parser.add_argument("--tui", action="store_true", help="Start TUI")
    parser.add_argument("--gui", action="store_true", help="Start GUI with webapp")
    parser.add_argument("--llama-server", action="store_true", help="Start llama-server")
    parser.add_argument("--model", type=str, help="Path to GGUF model")
    parser.add_argument("--api-key", type=str, help="API key for OpenAI-compatible provider")
    parser.add_argument("--api-base", type=str, help="Base URL for OpenAI-compatible provider")
    parser.add_argument("--port", type=int, default=8080, help="Port for services")
    parser.add_argument("--host", type=str, default="localhost", help="Host for services")
    parser.add_argument("--interactive", action="store_true", help="Interactive model selection")
    parser.add_argument("--all", action="store_true", help="Start all components")
    args = parser.parse_args()

    # Set API config
    if args.api_key or args.api_base:
        set_api_config(args.api_key, args.api_base)

    # Start llama-server if requested
    if args.llama_server or args.all:
        models = find_gguf_models()
        model_path = args.model
        if not model_path and (args.interactive or args.all):
            selected = discover_and_select_model(models)
            if selected:
                model_path = str(selected)
        if not model_path:
            if models:
                model_path = str(models[0])
            else:
                print("No GGUF models found. Skipping llama-server.")
        if model_path:
            print(f"Starting llama-server with {model_path}")
            start_llama_server(model_path, args.host, args.port)
            await asyncio.sleep(2)

    # Start GUI/TUI
    if args.all or args.gui or args.tui:
        if args.gui:
            await run_with_gui(dev=True, tui=args.tui)
            return
        if args.tui:
            run_tui()
            return

    print("AGENT_SYSTEM_V9 ready. Use --tui, --gui, --llama-server, or --all")


def main():
    asyncio.run(launch())


if __name__ == "__main__":
    main()
