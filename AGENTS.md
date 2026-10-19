# AGENTS.md — AGENT_SYSTEM_V9

## Commands

- Install: `pip install -e .` (core) or `pip install -e .[full]` (all extras)
- Lint: `ruff check agent_system_v9` (F,E excluding E501)
- Typecheck: `mypy agent_system_v9` (optional)
- Tests: `python3 -m pytest tests/ -q`
- Security scan: `bandit -r agent_system_v9/`

## Context Budget

- Default budget: 4000 tokens (`V9_CONTEXT_BUDGET_TOKENS`)
- Verbatim tail: 8 most recent messages (`V9_CONTEXT_VERBATIM_TAIL`)
- Older messages compressed into a single rolling summary via `ContextWindow`.

## Adding a Provider

Register via `ProviderRegistry.get_instance().register(name, provider)` or
`initialize_provider_registry(config)`. Coding loop uses healthy providers
automatically; falls back to deterministic starter when none available.

## Adding a Tool

Use `DynamicToolRegistry.get_instance().register(name, fn, description, ...)`.
Expose as OpenAI function via `ToolEntry.to_openai_function()`. For sandboxed
execution, pass `sandbox_spec=SandboxSpec(...)` and call `registry.execute(name, args, sandbox=True)`.

## Sandbox Images

Default runtime is namespace (always available on Linux). Docker/Podman/bubblewrap
used when available. Network disabled by default; opt in per tool via
`network_enabled=True`.

## Pentest Tools

Registered via `register_pentest_tools(registry, network_enabled=False)`.
Binaries missing in the environment are skipped (recorded in `_skipped`).
Findings ingested via `ingest_findings(knowledge_graph, findings)`.
