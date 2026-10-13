# Quickstart

## Basic Usage

```python
import agent_system_v9 as v9

# Initialize core systems
results = v9.initialize_system()

# Access core components
registry = v9.registry
event_bus = v9.event_bus
config = v9.config

# Use plugins
from agent_system_v9 import plugin_manager, PluginMetadata, PluginState

metadata = PluginMetadata(
    name="my_plugin",
    version="1.0.0",
    description="My custom plugin",
    author="Me",
    capabilities=["custom"]
)
plugin_manager.register_plugin(metadata)
```

## RedAmon Integration

```python
from agent_system_v9.integrations import (
    get_orchestrator_integration,
    get_knowledge_base_integration,
    get_recon_integration,
)

# Orchestrator
orch = get_orchestrator_integration()
session = orch.create_session({'workspace': '/path/to/workspace'})

# Knowledge Base
kb_int = get_knowledge_base_integration()
kb = kb_int.create_knowledge_base('my_kb')
kb.add_documents([Document(id='1', content='Hello world')])
results = kb.search('hello')

# Recon
recon = get_recon_integration()
pipeline = recon.create_default_pipeline()
results = await pipeline.run(ReconTarget(target='example.com', target_type='domain'))
```

## Cybersec Toolkit

```python
from agent_system_v9.integrations import get_cybersec_toolkit_integration

ct = get_cybersec_toolkit_integration()
modules = ct.tool_manager.get_all_modules()
tools = ct.tool_manager.get_tools_by_module('networking')

# Run a tool
result = await ct.module_runner.run_tool('nmap', '-sS', '192.168.1.0/24')
```

## ShadowGit

```python
from agent_system_v9.shadowgit import ShadowGit, ShadowGitSync, RemoteConfig, RemoteProtocol

sg = ShadowGit('/path/to/repo')
sync = ShadowGitSync(sg, sg.index)

config = RemoteConfig(
    name='origin',
    url='https://github.com/user/repo.git',
    protocol=RemoteProtocol.HTTPS
)
sync.add_remote(config)

result = await sync.push('origin')
```

## TUI Interface

```bash
# Run the TUI
python -m agent_system_v9.tui
```

## Web UI

```bash
cd agent_system_v9/integrations/redamon/webapp
npm run dev
# Open http://localhost:3000
```