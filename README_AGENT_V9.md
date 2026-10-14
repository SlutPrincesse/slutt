# AGENT_SYSTEM_V9 - NEURO-CRANIAL OVERLORD

## Quick Start

```bash
# Show version
python3 main.py --version

# Start TUI
python3 main.py --tui

# Start GUI with webapp
python3 main.py --gui

# Start GUI + TUI together
python3 main.py --gui --tui

# Discover and start llama-server with GGUF models
python3 main.py --llama-server --interactive

# Start with specific model
python3 main.py --llama-server --model ~/Downloads/model.gguf

# Start with OpenAI-compatible API
python3 main.py --api-key YOUR_KEY --api-base https://api.provider.com/v1 --tui

# Start everything
python3 main.py --all --interactive
```

## Features

- **TUI Interface**: Full terminal UI with system monitoring, recon, tools, etc.
- **GUI/Webapp**: Browser-based interface for remote access
- **GGUF Model Discovery**: Automatically finds models in Downloads, Documents, common dirs
- **llama-server Integration**: Starts llama-server with optimal parameters
- **OpenAI-compatible API**: Configure with API key and base URL
- **Complete v9 Agent System**: 34 sections, 665 Python files, 122 passing tests
