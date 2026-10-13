# Installation

## Requirements

- Python 3.10+
- Docker (for sandbox isolation)
- Git (for ShadowGit operations)

## Quick Install

```bash
pip install agent-system-v9
```

## Development Install

```bash
git clone https://github.com/your-org/agent-system-v9
cd agent-system-v9
pip install -e ".[dev]"
```

## Optional Dependencies

```bash
# ML/AI capabilities
pip install -e ".[ml]"

# Distributed systems
pip install -e ".[distributed]"

# Monitoring
pip install -e ".[monitoring]"

# Full installation
pip install -e ".[full]"
```

## System Dependencies

```bash
# Ubuntu/Debian
apt-get install -y docker.io git python3-yaml

# For TUI
pip install textual rich

# For web UI
cd integrations/redamon/webapp && npm install
```