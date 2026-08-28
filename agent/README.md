# DarkPatternsAgent

A multi-provider, self-modifying bash agent with MAINFRAME control plane integration and LLM dark-pattern guards.

## Features

- **Multi-provider support**: OpenAI-compatible (GPT-4o, etc.) and Anthropic (Claude)
- **Autonomous self-development**: Read, write, and improve its own source code
- **MAINFRAME integration**: Shell policy gate, durable agent memory (AWM), reviewed Bash toolbox
- **Dark-pattern guards**: Sycophancy, vibes, wrap-up, AI-tells, disclaimer spam detection
- **Extensible skills**: Add capabilities via `.sh` skill files

## Quick Start

```bash
# Clone the agent
git clone <this-repo>
cd agent

# Set API key (OpenAI or Anthropic)
export OPENAI_API_KEY="your-key"
export LLM_PROVIDER=openai

# Run the agent
./agent.sh
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_PROVIDER` | `openai` or `anthropic` | `openai` |
| `OPENAI_API_KEY` / `LLM_API_KEY` | OpenAI API key | - |
| `OPENAI_API_BASE` | OpenAI-compatible base URL | `https://api.openai.com` |
| `OPENAI_MODEL` | Model name | `gpt-4o` |
| `ANTHROPIC_API_KEY` | Anthropic API key | - |
| `ANTHROPIC_MODEL` | Anthropic model | `claude-sonnet-4-20250514` |

## Tools

### Core Tools
- `read_file` / `list_files` / `edit_file` — filesystem operations
- `read_self` / `write_self` / `self_improve` — autonomous self-modification

### MAINFRAME Tools
- `mf_gate_check` — shell policy gate
- `mf_awm_checkpoint` / `mf_awm_discover` — durable memory
- `mf_search_tool` / `mf_invoke` — reviewed Bash toolbox

### Skill Tools
- `shell_policy_check` — enhanced pattern matching
- `code_review_check` — file review for issues
- `git_status_summary` / `git_diff_summary` — git operations

## Architecture

```
agent.sh (main loop)
  ├── OpenAI/Anthropic API client
  ├── Tool execution layer
  ├── Dark-pattern guard layer
  ├── MAINFRAME integration
  │   ├── Policy gate
  │   ├── AWM (Agent Working Memory)
  │   └── Function registry
  └── Skills system
```

## Self-Modification

The agent has full permissions to modify its own source code. Use:
- `read_self` — inspect current code
- `write_self` — overwrite with validated new content
- `self_improve` — analyze and apply improvements

All writes validate bash syntax before applying and create automatic backups.

## License

MIT
