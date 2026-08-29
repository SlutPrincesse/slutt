# Nexus: Unified Agent Infrastructure — Consolidation Plan

## 1. Goal

Merge 7 open-source Python repositories into a single, rebranded project called **Nexus** that provides a complete AI agent infrastructure platform: skill discovery/installation, agent runtime with tools, intelligent model routing, runtime dependency isolation, code-health analysis, and token-efficient browser automation.

**Constraint:** Every unique capability from every source repo must be preserved. Overlapping implementations must be consolidated, not duplicated.

---

## 2. Source Repository Summary

| Repo | LOC | Tests | Role in Nexus |
|------|-----|-------|---------------|
| `jingzy945/skill-router` | ~2,100 | 0 | Skill discovery, 7-layer relevance scoring, interactive session lifecycle |
| `eddieoz/pipx-skills` | ~265 | 0 | GitHub-based skill installer (clone + metadata fetch + dep install) |
| `openconstruct/freeclaw` | ~8,000–10,000 | 0 | Agent runtime loop, multi-provider LLM clients, tools framework, Discord bot, task timer, memory, Google integration |
| `cobusgreyling/nim-model-router` | ~2,200 source / ~1,500 tests | ~11 test files | OpenAI-compatible proxy, task-based model classification, fallback routing, Prometheus metrics |
| `agent0ai/depfix` | ~17,500 source / ~8,500 tests | ~12 test files | Runtime dependency isolation — multiple package versions coexist in one process |
| `Ibnuawf/codi` | ~2,200–2,500 source / ~800 tests | ~9 test files | Zero-dep code-health analyzer: complexity, clones, dead code, dependency cycles, churn risk, HTML reports |
| `nikolas-sapa/grip-browser` | ~15,000–20,000 | 318 unit + 74 integration | CDP-native browser SDK, ~16x token compression vs raw HTML, fuzzy matching, shadow DOM, challenge detection, LLM adapters, MCP server |

**Common baseline:** All are MIT-licensed Python. Python version floor is **3.11+** (depfix and grip require 3.11; all others work on 3.11+).

---

## 3. Proposed Architecture

```
nexus/
├── nexus/
│   ├── __init__.py          # Public API surface
│   ├── cli.py               # Unified Typer/argparse CLI
│   ├── config.py            # Unified config (env + JSON/TOML + defaults)
│   ├── logging.py           # Rotating file + stderr logging
│   │
│   ├── skills/              # Skill system (skill-router + pipx-skills)
│   │   ├── __init__.py
│   │   ├── index.py         # SkillIndex — scan + parse SKILL.md
│   │   ├── matcher.py       # SkillMatcher — 7-layer scoring
│   │   ├── session.py       # SessionManager — activate/track/review
│   │   ├── installer.py     # GitHub clone + metadata fetch + pip install
│   │   ├── aliases.py       # SKILL_NAME_ALIASES + CN_EN_KEYWORD_MAP
│   │   └── constants.py     # CATEGORY_KEYWORDS, STOP_WORDS, etc.
│   │
│   ├── runtime/             # Agent runtime (freeclaw core)
│   │   ├── __init__.py
│   │   ├── agent.py         # run_agent() loop
│   │   ├── providers/       # LLM provider clients (NIM, OpenRouter, Groq)
│   │   │   ├── __init__.py
│   │   │   ├── base.py      # ChatClient protocol
│   │   │   ├── nim.py
│   │   │   ├── openrouter.py
│   │   │   └── groq.py
│   │   ├── tools/           # Tool implementations
│   │   │   ├── registry.py  # tool_schemas() + dispatch_tool_call()
│   │   │   ├── fs.py        # fs_read/write/list/mkdir/rm/mv/cp
│   │   │   ├── shell.py     # sh_exec
│   │   │   ├── search.py    # text_search
│   │   │   ├── web.py       # web_search, web_fetch
│   │   │   ├── http.py      # http_request_json
│   │   │   ├── memory.py    # SQLite memory
│   │   │   ├── tasks.py     # task_scheduler (tasks.md)
│   │   │   ├── docs.py      # doc_ingest/search
│   │   │   ├── google.py    # gmail/calendar
│   │   │   ├── timer_api.py # local timer-api queries
│   │   │   └── custom.py    # JSON-spec custom tools
│   │   ├── discord.py       # Discord bot (discord.py optional)
│   │   ├── memory.py        # memory store facade
│   │   ├── task_timer.py    # TaskTimer runtime
│   │   └── onboarding.py    # First-run wizard + agent profiles
│   │
│   ├── routing/             # Model router (nim-model-router)
│   │   ├── __init__.py
│   │   ├── proxy.py         # FastAPI proxy server
│   │   ├── router.py        # ModelRouter — task → model resolution
│   │   ├── classifier.py    # Request classification (keyword + optional LLM)
│   │   ├── policies.py      # Cost guards, prompt limits
│   │   ├── fallback.py      # Fallback chains + A/B testing
│   │   ├── client.py        # NimClient — upstream HTTP with retry
│   │   ├── cost.py          # Token-cost estimation
│   │   ├── metrics.py       # Prometheus metrics
│   │   ├── catalog.py       # NIM catalog sync
│   │   ├── auth.py          # Optional API-key middleware
│   │   ├── config.py        # Settings + YAML registry loader
│   │   ├── types.py         # Pydantic models
│   │   ├── logging_store.py # Request logging
│   │   └── models.yaml      # Task→model mapping (ported)
│   │
│   ├── deps/                # Dependency manager (depfix)
│   │   ├── __init__.py      # Public API: import_module, using, default, patch_import
│   │   ├── cli.py           # depfix subcommands
│   │   ├── manager.py       # Request coordinator
│   │   ├── resolver.py      # uv-backed root resolution
│   │   ├── runtime.py       # DepfixRuntime + BoundImporter
│   │   ├── dispatcher.py    # Process-wide import hook
│   │   ├── cache.py         # Shared on-disk store
│   │   ├── scanner.py       # AST scanner for static depfix calls
│   │   ├── settings.py      # Settings precedence
│   │   ├── manifest.py      # LockedGraph read/write
│   │   ├── models.py        # Artifact, Node, Alias, LockedGraph
│   │   ├── uv_backend.py    # UvBackend adapter
│   │   ├── sync.py          # sync_graph
│   │   ├── wheel.py         # Wheel inspection
│   │   ├── sources.py       # PEP 508 + scheme parsing
│   │   ├── requirements.py  # Requirements-file parsing
│   │   ├── boundaries.py    # Realm boundary guards
│   │   ├── scopes.py        # default/using/default_requirements
│   │   ├── aliases.py       # IDE alias generation
│   │   ├── handles.py       # PackageHandle
│   │   ├── errors.py        # Typed exception hierarchy
│   │   ├── progress.py      # ProgressReporter
│   │   └── project.py       # export/install/bundle/verify
│   │
│   ├── analysis/            # Code health analyzer (codi)
│   │   ├── __init__.py
│   │   ├── cli.py           # codi subcommands
│   │   ├── analyzer.py      # File discovery + AST parsing
│   │   ├── complexity.py    # Cyclomatic complexity visitor
│   │   ├── cognitive.py     # Cognitive complexity + Halstead + MI
│   │   ├── scoring.py       # Health score blending + hotspot ranking
│   │   ├── graph.py         # Import dependency graph + cycle detection
│   │   ├── deadcode.py      # Dead-function detection
│   │   ├── duplication.py   # Clone detection (type-2)
│   │   ├── churn.py         # Git churn collection + risk ranking
│   │   ├── baseline.py      # Snapshot save/load + delta
│   │   ├── history.py       # Trend log + sparkline
│   │   ├── report.py        # HTML + JSON report rendering
│   │   ├── markdown.py      # GitHub-flavored markdown + SVG badge
│   │   ├── viz.py           # Inline SVG visualizations
│   │   ├── gha.py           # GitHub Actions annotation emission
│   │   └── config.py        # codi.toml / pyproject.toml [tool.codi]
│   │
│   └── browser/             # Browser SDK (grip-browser)
│       ├── __init__.py
│       ├── browser.py       # Browser — Chrome process + tab management
│       ├── page.py          # Page — snapshot, click, type, read, screenshot
│       ├── runner.py        # Runner — autonomous LLM agent loop
│       ├── cli.py           # grip subcommands
│       ├── cdp/
│       │   ├── engine.py    # CDP websocket engine
│       │   ├── launcher.py  # Chrome process launcher
│       │   └── shadow.py    # Shadow DOM traversal JS
│       ├── compression/
│       │   ├── summarizer.py # PageSnapshot + Element formatting
│       │   ├── delta.py      # Snapshot delta compression
│       │   └── refs.py       # Reference registry
│       ├── adapters/
│       │   ├── base.py       # LLMAdapter protocol
│       │   ├── openai.py     # OpenAI adapter
│       │   ├── anthropic.py  # Anthropic adapter
│       │   └── gemini.py     # Gemini adapter
│       ├── security/
│       │   ├── injection.py  # Prompt injection detection
│       │   ├── policy.py     # Navigation policy enforcement
│       │   └── sanitizer.py  # Element sanitization
│       ├── errors/
│       │   ├── types.py      # ErrorType + BrowserError
│       │   └── classifier.py # Error classification
│       ├── challenge.py      # CAPTCHA detection + solving
│       ├── input.py          # Human-like input (Bézier paths)
│       ├── reader.py         # Document read mode
│       ├── resources.py      # Resource blocking
│       ├── trace.py          # Audit tracing
│       └── mcp/
│           └── server.py     # MCP server implementation
│
├── tests/                   # Unified test suite
│   ├── conftest.py
│   ├── skills/
│   ├── runtime/
│   ├── routing/
│   ├── deps/                 # Ported from depfix tests
│   ├── analysis/
│   └── browser/
│
├── docs/                    # Consolidated documentation
├── benchmarks/              # Ported benchmarks (grip, nim-router)
├── pyproject.toml           # Single build config
├── README.md                # Rebranded readme
├── LICENSE                  # MIT (with multi-author attribution)
└── CHANGELOG.md             # Consolidated changelog
```

---

## 4. Implementation Phases

### Phase 1: Scaffold & Core Infrastructure
**Goal:** Create the Nexus repo with unified build, config, logging, and CLI skeleton.

**Tasks:**
1. Initialize repo: `git init`, add `.gitignore`, `LICENSE` (MIT + attribution block).
2. Create `pyproject.toml`:
   - `name = "nexus"`
   - `requires-python = ">=3.11"`
   - Core dependencies: `fastapi`, `httpx`, `pydantic`, `pydantic-settings`, `pyyaml`, `tiktoken`, `websockets`, `packaging`, `pathspec`, `platformdirs`, `uv`, `typer`, `rich`, `prometheus-client`
   - Optional extras: `[discord]` → `discord.py`, `pypdf`; `[web]` → `ddgs`; `[browser-llm]` → `openai`, `anthropic`, `google-genai`, `mcp`
3. Create `nexus/__init__.py` with version.
4. Create `nexus/config.py` — unified config layer:
   - Precedence: CLI args > env vars > `config/config.json` > `config/.env` > defaults
   - Adopt freeclaw's `ClawConfig` dataclass pattern; extend with sections for routing, deps, analysis, browser.
5. Create `nexus/logging.py` — adopt freeclaw's rotating file logger (100KB, 3 backups).
6. Create `nexus/cli.py` — Typer app skeleton with subcommand groups: `skill`, `serve`, `route`, `analyze`, `browser`, `deps`, `config`, `onboard`.
7. Add `tests/conftest.py` and a minimal smoke test.

**Validation:** `python -m nexus --help` renders all subcommand groups. `pytest tests/` passes.

---

### Phase 2: Skill System
**Goal:** Port skill-router + pipx-skills into `nexus/skills/`.

**Tasks:**
1. Port `skill_router.py` → split into:
   - `nexus/skills/index.py` (`SkillIndex`)
   - `nexus/skills/matcher.py` (`SkillMatcher`)
   - `nexus/skills/session.py` (`SessionManager`)
   - `nexus/skills/constants.py` (all hardcoded maps/thresholds)
   - `nexus/skills/aliases.py` (alias + CN/EN maps)
2. Update all internal imports to `nexus.skills.*`. Replace `argparse` CLI dispatch in `main()` with Typer subcommands under `nexus skill *`.
3. Port `pipx-skills/__init__.py` → `nexus/skills/installer.py`:
   - `install_skill()`, `remove_skill()`, `list_skills()`, `update_skill()`
   - Replace `subprocess` git/pip calls with the same logic (no wrapper library needed).
   - Resolve skills dir via unified config (`nexus.config.get_skills_dir()`).
4. Add skill subcommands:
   - `nexus skill list`
   - `nexus skill match "<task>" --top 5`
   - `nexus skill install owner/repo`
   - `nexus skill remove <name>`
   - `nexus skill update <name>`
   - `nexus skill session start/activate/deactivate/track/review/end`
5. Replace pickle cache with JSON (portability + security). Keep MD5(mtime) invalidation.

**Validation:** All original skill-router CLI modes produce identical output. `nexus skill install` works against a test skill repo.

---

### Phase 3: Agent Runtime
**Goal:** Port freeclaw's agent loop, tools, memory, and integrations into `nexus/runtime/`.

**Tasks:**
1. Port provider clients:
   - `nexus/runtime/providers/base.py` (`ChatClient` protocol)
   - `nexus/runtime/providers/nim.py` (`NimChatClient`)
   - `nexus/runtime/providers/openrouter.py`
   - `nexus/runtime/providers/groq.py`
2. Port tools framework:
   - `nexus/runtime/tools/registry.py` — `tool_schemas()` + `dispatch_tool_call()`
   - `nexus/runtime/tools/fs.py`, `shell.py`, `search.py`, `web.py`, `http.py`, `memory.py`, `tasks.py`, `docs.py`, `google.py`, `timer_api.py`, `custom.py`
   - Integrate grip-browser's `Browser` as a new tool: `browser_open`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_read`, `browser_screenshot`, `browser_run` (wraps `grip.browser.Browser`).
3. Port `nexus/runtime/agent.py` — `run_agent()` loop.
4. Port `nexus/runtime/task_timer.py` + `nexus/runtime/onboarding.py`.
5. Port Discord integration as optional `nexus/runtime/discord.py` (requires `discord.py`).
6. Wire skill system into runtime: agent can call `nexus.skills.matcher.match()` during system-prompt construction.

**Validation:** `nexus serve chat` runs a basic agent loop with tools. Skill discovery works inside runtime.

---

### Phase 4: Model Routing
**Goal:** Integrate nim-model-router as the model-selection layer for both the agent runtime and the standalone proxy.

**Tasks:**
1. Port routing core:
   - `nexus/routing/router.py` (`ModelRouter`)
   - `nexus/routing/classifier.py`
   - `nexus/routing/policies.py`
   - `nexus/routing/fallback.py`
   - `nexus/routing/client.py` (`NimClient`)
   - `nexus/routing/cost.py`, `metrics.py`, `catalog.py`, `auth.py`, `logging_store.py`
2. Port `nexus/routing/proxy.py` — FastAPI server (standalone `nexus route serve`).
3. Port `nexus/routing/config.py` + `models.yaml`.
4. **Integration point:** In `nexus/runtime/agent.py`, before calling a provider, route through `ModelRouter` when model is `auto` or an alias like `nexus/auto`, `nexus/agentic`, etc. This replaces freeclaw's simple auto-detect with nim-router's richer classification.
5. Port CLI:
   - `nexus route serve` — start proxy
   - `nexus route models` — show registry
   - `nexus route "<task>"` — dry-run classification

**Validation:** Proxy forwards to NIM/OpenRouter/Groq. Agent runtime auto-routes tool-heavy prompts to `agentic` model. All original nim-router tests pass after import updates.

---

### Phase 5: Dependency Management
**Goal:** Port depfix into `nexus/deps/` and make it available as both a library and CLI.

**Tasks:**
1. Port all `src/depfix/*.py` → `nexus/deps/*.py`.
2. Update imports from `depfix.*` → `nexus.deps.*`.
3. Port CLI: `nexus deps <subcommand>` maps to original `depfix` commands (`install`, `list`, `tree`, `cache cleanup`, `export`, `run`, etc.).
4. Ensure `nexus.deps` can be imported without side effects (lazy `__getattr__` facade like original).
5. Run original depfix test suite (12 test files) against renamed package.

**Validation:** `nexus deps import_module("requests==2.32.3")` works. All original depfix tests pass.

---

### Phase 6: Code Analysis
**Goal:** Port codi into `nexus/analysis/`.

**Tasks:**
1. Port `codi/*.py` → `nexus/analysis/*.py`.
2. Update imports. Keep zero-dep guarantee (no new runtime deps).
3. Port CLI:
   - `nexus analyze <path>` — terminal summary
   - `nexus analyze <path> --html report.html`
   - `nexus analyze <path> --json -`
   - `nexus analyze <path> --md -`
   - `nexus analyze <path> --badge health.svg`
   - `nexus analyze <path> --history history.json`
   - `nexus analyze <path> --fail-under 70`
4. Integrate `nexus analyze` as an optional agent tool (`code_analyze`) so the agent can run health checks on its own code.

**Validation:** `nexus analyze nexus/ --fail-under 70` gates CI. All original codi tests pass.

---

### Phase 7: Browser Automation
**Goal:** Port grip-browser into `nexus/browser/`.

**Tasks:**
1. Port `grip/*.py` → `nexus/browser/*.py`.
2. Update imports. Keep `websockets` and `tiktoken` as core deps.
3. Port CLI:
   - `nexus browser open <url>`
   - `nexus browser snapshot <url>`
   - `nexus browser read <url>`
   - `nexus browser screenshot <url> -o shot.jpg`
   - `nexus browser run "<goal>" --url <url>`
   - `nexus browser doctor`
4. Port MCP server: `nexus browser mcp` (optional extra `mcp`).
5. Integrate `Browser` as a runtime tool in Phase 3 (already planned).

**Validation:** `nexus browser open https://example.com` produces a snapshot. All unit tests pass; integration tests run against local Chrome.

---

### Phase 8: Integration, Rebranding & Polish
**Goal:** Unify branding, docs, CI, and release.

**Tasks:**
1. **Rebrand all user-facing strings:**
   - Package name: `nexus`
   - CLI command: `nexus`
   - User-Agent: `nexus/<version>`
   - Log prefixes: `nexus`
   - Default assistant name/tone: update in config defaults
   - README, docs, help text
2. **License attribution:** Single `LICENSE` (MIT) with a `NOTICE` or attribution section listing all 7 original authors/repos.
3. **Consolidated README:** Write a new `README.md` explaining Nexus as a unified platform, with a section mapping each subcommand to its originating repo.
4. **Consolidated CHANGELOG:** Seed with entries noting the consolidation and listing source repos.
5. **CI/CD:**
   - GitHub Actions matrix: Linux + Windows, Python 3.11–3.13.
   - Jobs: lint (`ruff`), type-check (`mypy --strict`), unit tests, integration tests (browser), `nexus analyze nexus/ --fail-under 70` (dogfood).
6. **Release:** `python -m build`, publish to PyPI as `nexus`.

**Validation:** Full CI green. `pip install nexus[all]` installs everything. `nexus --help` is coherent.

---

## 5. CLI Surface (Final)

```
nexus
  nexus serve                      # Start interactive agent (freeclaw run/chat)
  nexus skill
      nexus skill list
      nexus skill match "<task>"
      nexus skill install owner/repo
      nexus skill remove <name>
      nexus skill update <name>
      nexus skill session start
      nexus skill session activate <name>
      nexus skill session deactivate <name>
      nexus skill session track <name>
      nexus skill session review
      nexus skill session end
  nexus route
      nexus route serve            # Start OpenAI-compatible proxy (nim-router)
      nexus route models
      nexus route "<task>"         # Dry-run classification
      nexus route catalog-sync     # Sync NIM catalog suggestions
  nexus analyze <path>             # Code health (codi)
      [--html REPORT] [--json] [--md] [--badge SVG] [--history JSON]
      [--fail-under N] [--churn-since "3 months"]
  nexus browser
      nexus browser open <url>
      nexus browser snapshot <url>
      nexus browser read <url>
      nexus browser screenshot <url> -o FILE
      nexus browser run "<goal>" --url <url>
      nexus browser mcp            # Start MCP server
      nexus browser doctor
  nexus deps                       # Dependency isolation (depfix)
      nexus deps install <spec>
      nexus deps list
      nexus deps tree
      nexus deps uninstall <spec>
      nexus deps cache cleanup
      nexus deps export . -o lock
      nexus deps run <script>
  nexus config
      nexus config init
      nexus config show
      nexus config set <key> <val>
      nexus config validate
      nexus config env-init
  nexus onboard                    # First-run wizard
```

---

## 6. Dependency Strategy

**Core install (`pip install nexus`):**
- `fastapi`, `uvicorn`, `httpx`, `pydantic`, `pydantic-settings`, `pyyaml`
- `tiktoken`, `websockets`
- `packaging`, `pathspec`, `platformdirs`, `uv`
- `typer`, `rich`, `prometheus-client`

**Extras:**
- `nexus[discord]` → `discord.py`, `pypdf`
- `nexus[web]` → `ddgs`
- `nexus[browser-llm]` → `openai`, `anthropic`, `google-genai`, `mcp`

**Note:** `depfix` itself is shipped as a submodule (`nexus.deps`) and depends on `uv`. The outer project uses standard `pip`/`uv` for its own installation; `nexus.deps` is the runtime isolation layer available to users.

---

## 7. Test Strategy

1. **Port existing tests:**
   - depfix: 12 test files → `tests/deps/`
   - nim-router: 11 test files → `tests/routing/`
   - grip: 318 unit + 74 integration → `tests/browser/`
   - codi: 9 test files → `tests/analysis/`
2. **Update imports** in all ported tests from old package names to `nexus.*`.
3. **Add new tests:**
   - Skills integration: match + install round-trip.
   - Runtime + routing integration: agent loop with auto-routed model.
   - Runtime + browser integration: agent uses `browser_open` tool.
4. **Dogfood:** Run `nexus analyze nexus/ --fail-under 70` in CI.
5. **CI matrix:** Linux + Windows, Python 3.11–3.13, with `pytest -m 'not network'` for default and a separate `network` job for grip integration tests.

---

## 8. Rebranding Checklist

- [ ] Package name: `nexus`
- [ ] CLI entry point: `nexus`
- [ ] User-Agent strings: `nexus/<version>`
- [ ] Log prefixes and default assistant name/tone
- [ ] README title, description, badges
- [ ] All help text and docstrings
- [ ] License: MIT with multi-author `NOTICE`
- [ ] GitHub repo name: `nexus`
- [ ] PyPI package name: `nexus`
- [ ] Docker image name: `nexus`
- [ ] Environment variable prefix: `NEXUS_*` (migrate from `FREECLAW_*`, `NIM_*`, `DEPFIX_*`, `GRIP_*`, `CODI_*` with backward-compatible aliases in Phase 1)

**Backward-compatibility aliases:** During a transition period, accept old env-var names (`FREECLAW_PROVIDER`, `DEPFIX_CACHE_DIR`, etc.) and map them to new `NEXUS_*` names. Document deprecation timeline.

---

## 9. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Dependency bloat** | High | Medium | Keep optional extras lean. depfix + uv + fastapi are the heaviest; accept them as core because nim-router and depfix need them. |
| **Import-path breakage** | Medium | High | Mechanical rename with `sed`/`rope`. Add a compatibility shim in Phase 1 that imports old names and emits `DeprecationWarning`. |
| **Config merge conflicts** | Medium | Medium | Adopt freeclaw's layered env+JSON config as the base; add YAML support for routing registry; add TOML for analysis. One `nexus.config` facade hides backends. |
| **Test porting effort** | High | Medium | Prioritize depfix, nim-router, and grip tests (largest suites). Codify a 2-pass approach: first pass makes tests importable, second pass fixes failures. |
| **Python 3.11 floor** | Low | Medium | All source repos work on 3.11+. Cod i supports 3.10+; dropping 3.10 is acceptable given depfix/grip requirements. |
| **License attribution gaps** | Low | Low | All 7 repos are MIT. Single `LICENSE` + `NOTICE` file listing all original authors/repos is sufficient. |
| **Scope creep** | Medium | High | Strict phase gating. Each phase must pass its validation checklist before the next begins. |

---

*Plan finalized. Project name confirmed: **Nexus**.*
