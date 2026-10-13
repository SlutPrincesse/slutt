# Architecture

## System Overview

AGENT_SYSTEM_V9 consists of 34 major subsystems organized into layers:

```
┌─────────────────────────────────────────────────────────────┐
│                    TUI / GUI Layer                           │
├─────────────────────────────────────────────────────────────┤
│                  Integration Layer                           │
│  ┌─────────────┐ ┌──────────────┐ ┌─────────────────────┐  │
│  │   RedAmon   │ │ Cybersec-    │ │ Ablation / CoreCoder │  │
│  │ Orchestrator│ │ Toolkit      │ │ (via DynamicToolReg) │  │
│  └─────────────┘ └──────────────┘ └─────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                     Core Services                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │ Registry │ │ EventBus │ │ Config   │ │ Plugin Mgr   │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                    Subsystems (Sections 01-31)               │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐    │
│  │Blueprint│ │Distrib │ │Security│ │Reactive│ │Compile │    │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘    │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐    │
│  │Storage │ │Deploy  │ │Context │ │Bench   │ │Edge    │    │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘    │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐    │
│  │Workspc │ │Guard   │ │Tools   │ │Shadow  │ │Evolut  │    │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘    │
├─────────────────────────────────────────────────────────────┤
│                  Provider / Kernel Layer                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │ Providers│ │ Kernel   │ │ Prompt   │ │ Multi-Modal  │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Section Map

| Section | Name | Description |
|---------|------|-------------|
| 01 | Kernel | Process supervision, PTY, IPC, sandbox isolation |
| 02 | Prompt | Prompt filesystem, reinforcement optimization |
| 03 | Multi-Modal | Audio, image, DOM, document extraction |
| 04 | Audit | Telemetry, metrics, dashboard, replay, PII redaction |
| 05 | Neuro-Cranial | Corpus callosum, dual-stream, shadow broker |
| 06 | Divergent | Executor, AST merger, failure evaluation |
| 07 | Cranial HUD | Task graph, ambient shader, nudge monitor |
| 13/26 | Blueprint | Polyglot AST, protocol compiler, FFI mapper |
| 14 | Distributed | RPC, DAG scheduler, BFT consensus, load balancer, CRDT |
| 15 | Reasoning | Concept abstraction, ontology, context serialization |
| 16 | Security | Zero-trust, entropy, vuln scanner, egress proxy, integrity |
| 17 | Reactive | Message bus, backpressure, hooks, state machine, idempotent |
| 18 | Compilation | Code gen, JIT, hot swap, symbol inspector, type marshaller |
| 19 | Storage | Virtual objects, CAS, delta sync, asset lifecycle |
| 20 | Deployment | Health verify, handshake, degradation, artifact bundler |
| 27 | Workspace | Manager, polyglot AST driver, function mutator, sync |
| 28 | Guardrails | Pre-commit, comment stripper, typing guard, no-op detector |
| 29 | Tools | Dynamic registry, tool synthesizer, exception hook |
| 30 | ShadowGit | Shadow git kernel, index, sync, LFS |
| 31 | Evolution | Engine, code/arch evolution, CMAES, PSO, DE |

## Data Flow

```
User Request → Orchestrator → Task Planning → Tool Execution → Result Aggregation
                    ↓
            Knowledge Base ←→ Recon/Scanner
                    ↓
            Sandbox Isolation (OverlayFS/CGroups)
                    ↓
            Evolution/Compilation Pipeline
                    ↓
            ShadowGit Version Control
                    ↓
            Deployment/Monitoring
```

## Key Design Patterns

1. **Singleton Services** - Registry, EventBus, Config, PluginManager
2. **Capability-Based Discovery** - Components register capabilities for dynamic lookup
3. **Plugin Architecture** - All extensibility through PluginManager
4. **Event-Driven** - EventBus for decoupled communication
5. **Isolation by Default** - SandboxIsolator with multiple runtimes
6. **Git-Native State** - ShadowGit for all mutable state