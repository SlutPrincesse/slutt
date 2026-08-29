# Nexus

**Unified AI Agent Infrastructure Platform**

Nexus consolidates seven open-source Python projects into a single, rebranded platform for building, running, and optimizing AI agents.

| Capability | Origin |
|---|---|
| Skill discovery & 7-layer matching | [skill-router](https://github.com/jingzy945/skill-router) |
| GitHub-based skill installer | [pipx-skills](https://github.com/eddieoz/pipx-skills) |
| Agent runtime + tools + Discord | [freeclaw](https://github.com/openconstruct/freeclaw) |
| OpenAI-compatible model proxy | [nim-model-router](https://github.com/cobusgreyling/nim-model-router) |
| Runtime dependency isolation | [depfix](https://github.com/agent0ai/depfix) |
| Code health analyzer | [codi](https://github.com/Ibnuawf/codi) |
| Token-efficient browser SDK | [grip-browser](https://github.com/nikolas-sapa/grip-browser) |

## Quick Start

```bash
# Install
pip install nexus[all]

# Run onboarding
nexus onboard

# Analyze code health
nexus analyze .

# Match skills to a task
nexus skill match "create a PDF report from Excel data" --top 5

# Start model routing proxy
nexus route serve

# Start agent runtime
nexus serve chat

# Open a browser snapshot
nexus browser open https://example.com
```

## CLI Reference

```
nexus
  nexus serve chat                    # Interactive agent runtime
  nexus serve run "<task>"            # Single-shot agent task
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
      nexus route serve               # OpenAI-compatible proxy
      nexus route models
      nexus route "<task>"
      nexus route catalog-sync
  nexus analyze <path>
      [--html REPORT] [--json] [--md] [--badge SVG]
      [--fail-under N] [--churn-since "3 months"]
  nexus browser
      nexus browser open <url>
      nexus browser snapshot <url>
      nexus browser read <url>
      nexus browser screenshot <url> -o FILE
      nexus browser run "<goal>" --url <url>
      nexus browser mcp
      nexus browser doctor
  nexus deps
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
      nexus config validate
      nexus config env-init
  nexus onboard
```

## Python API

```python
import nexus

# Skills
from nexus.skills import SkillIndex, SkillMatcher, SessionManager
idx = SkillIndex()
idx.build_index()
matcher = SkillMatcher(idx)
results = matcher.match("analyze this CSV data", top_k=5)

# Runtime
from nexus.runtime.agent import run_agent
from nexus.config import load_config
cfg = load_config()
result = run_agent(messages, cfg=cfg)

# Routing
from nexus.routing import ModelRouter, Settings
router = ModelRouter(registry)
decision = router.route_chat(messages, model="nexus/auto")

# Deps
from nexus.deps import import_module, using, default, patch_import
requests = import_module("requests==2.32.3")
patch_import()  # enable store fallback

# Analysis
from nexus.analysis import analyze_project, compute_health
files = analyze_project("./src")
health = compute_health(files, graph, clones=clones, dead=dead)

# Browser
from nexus.browser import Browser
async with Browser(headless=True) as browser:
    page = await browser.open("https://example.com")
    snap = await page.snapshot()
```

## License

MIT. See [LICENSE](LICENSE) for details.

## Attribution

Nexus is a consolidation of the following MIT-licensed projects:

- [skill-router](https://github.com/jingzy945/skill-router) by jingzy945
- [pipx-skills](https://github.com/eddieoz/pipx-skills) by eddieoz
- [freeclaw](https://github.com/openconstruct/freeclaw) by openconstruct
- [nim-model-router](https://github.com/cobusgreyling/nim-model-router) by cobusgreyling
- [depfix](https://github.com/agent0ai/depfix) by agent0ai
- [codi](https://github.com/Ibnuawf/codi) by Ibnuawf
- [grip-browser](https://github.com/nikolas-sapa/grip-browser) by nikolas-sapa
