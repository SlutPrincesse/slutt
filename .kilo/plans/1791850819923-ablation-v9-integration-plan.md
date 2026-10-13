# AGENT_SYSTEM_V9 Integration Plan (Option 1: Capability Plugin)

## Goal
Integrate Ablation's reverse engineering capabilities and CoreCoder's lightweight agent as plugins into AGENT_SYSTEM_V9's tool registry, with OpenAI-compatible provider abstraction and llama.cpp optimization.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    AGENT_SYSTEM_V9                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ DynamicTool │  │ Sandbox     │  │ SemanticIndexer         │  │
│  │ Registry    │──▶│ Isolator    │──▶│ (Knowledge Graph)       │  │
│  │ (Section 29)│  │ (Section 1) │  │ (Section 15)            │  │
│  └──────┬──────┘  └─────────────┘  └───────────┬─────────────┘  │
│         │                                     │                 │
│         ▼                                     ▼                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              ABLATION (External CLI)                     │   │
│  │  ablation lift | taint | search | crypto | decompile     │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              CORECODER (External CLI)                    │   │
│  │  corecoder -p "task" | corecoder REPL                    │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Integration Points

| V9 Component | Ablation Capability | CoreCoder Capability | Mechanism |
|--------------|---------------------|----------------------|-----------|
| DynamicToolRegistry | All Ablation CLI commands | CoreCoder REPL / one-shot | ToolEntry registration + wrapper generation |
| SandboxIsolator | Binary analysis execution | Simple code edits/tests | Ephemeral container execution |
| PromptAssembler | Context injection for RE workflows | Plan mode + hooks reference | PromptSnippet registration |
| SemanticIndexer | Finding ingestion | Test validation results | CodeMemory + EpisodicStore |
| EventBus | Async completion routing | Tool execution events | Event subscription |

---

## Phase 1: Provider Abstraction Layer (Week 1)

### 1.1 Unified Provider Interface
- [ ] Create `agent_system_v9/providers/base.py` - Abstract base class
```python
class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, messages: List[Dict], tools: List[Dict]) -> LLMResponse
    @abstractmethod
    async def stream_chat(self, messages: List[Dict], tools: List[Dict]) -> AsyncIterator[LLMChunk]
    @abstractmethod
    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float
    @abstractmethod
    def get_model_info(self) -> ModelInfo
```

### 1.2 OpenAI-Compatible Provider
- [ ] Create `agent_system_v9/providers/openai_compatible.py`
- [ ] Support: OpenAI, DeepSeek, Kimi, Qwen, OpenRouter, OmniRoute
- [ ] Config via env vars: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `MODEL`
- [ ] Features: streaming, retries, cost tracking, fallback chain

### 1.3 llama.cpp Optimized Provider
- [ ] Create `agent_system_v9/providers/llamacpp.py`
- [ ] Support: llama.cpp server (`--server`), llama-cpp-python bindings
- [ ] Optimizations:
  - KV cache reuse across requests
  - Batch inference for parallel tool calls
  - Speculative decoding (draft model)
  - Context splitting for long contexts
  - GGUF model auto-discovery
- [ ] Config: `LLAMACPP_BASE_URL`, `LLAMACPP_N_GPU_LAYERS`, `LLAMACPP_CTX_SIZE`, `LLAMACPP_BATCH_SIZE`

### 1.4 Provider Registry & Factory
- [ ] Create `agent_system_v9/providers/registry.py`
- [ ] Auto-detect provider from env vars
- [ ] Health checks + model capability probing
- [ ] Cost comparison for auto-selection

---

## Phase 2: Ablation Plugin (Week 2)

### 2.1 Ablation CLI Inventory
- [ ] Map all Ablation subcommands to ToolEntry definitions
- [ ] Categorize: `lift`, `taint`, `search`, `crypto`, `decompile`, `diff`, `firmware`, `mcp-scan`

### 2.2 Dynamic Tool Wrapper Generation
- [ ] Create `agent_system_v9/integrations/ablation/tool_synthesizer.py`
- [ ] Generate async wrappers with SandboxIsolator
- [ ] Register with `DynamicToolRegistry.auto_load_generated()`

### 2.3 Sandbox Spec for Ablation
- [ ] Base image: `ablation-tool/ablation:latest` (or build from source)
- [ ] Resource limits: 2GB RAM, 2 CPU, 300s timeout
- [ ] No network (security policy)

### 2.4 Knowledge Graph Ingestion
- [ ] Map Ablation outputs → V9's `CodeMemory` + `Episode`
- [ ] Taint paths, decompiled functions, crypto findings, firmware keys

---

## Phase 3: CoreCoder Plugin (Week 2-3)

### 3.1 CoreCoder CLI Mapping
- [ ] Map CoreCoder commands: `corecoder` (REPL), `corecoder -p "task"` (one-shot)
- [ ] ToolEntry definitions with appropriate sandbox specs

### 3.2 Lightweight Code Execution Wrapper
- [ ] Sandbox: Python 3.11 slim, 512MB RAM, 30s timeout
- [ ] Support: file read/write, bash, test execution
- [ ] Plan mode + hooks as PromptSnippets for V9

### 3.3 Testbed Integration
- [ ] Register CoreCoder's 224 tests as V9 validation suite
- [ ] Run on V9 tool registry changes
- [ ] Reference implementations for Section 29 tool synthesis

---

## Phase 4: Validation & Testing (Week 3)

### 4.1 Provider Tests
- [ ] OpenAI-compatible: streaming, retries, cost tracking, fallback
- [ ] llama.cpp: KV cache reuse, batch inference, speculative decoding
- [ ] Provider switching without code changes

### 4.2 Plugin Tests
- [ ] Ablation: end-to-end binary analysis → findings in knowledge graph
- [ ] CoreCoder: simple coding task → file edits → test pass
- [ ] Concurrent: multiple analyses in parallel sandboxes

### 4.2 Integration Tests
- [ ] V9 Agent → DynamicToolRegistry → Ablation/CoreCoder → Knowledge Graph
- [ ] Provider fallback chain works under load
- [ ] llama.cpp optimization benchmarks vs baseline

---

## Data Flow

```
User Request
     │
     ▼
V9 Agent → PromptAssembler (injects Ablation/CoreCoder workflow snippets)
     │
     ▼
DynamicToolRegistry.ablation.taint() OR corecoder.edit()
     │
     ▼
SandboxIsolator.create_sandbox(Spec(provider_optimized_image))
     │
     ▼
Tool executes in container (with provider optimization)
     │
     ▼
Results → KnowledgeIngestor → SemanticIndexer + EpisodicStore
     │
     ▼
Returned to V9 Agent + indexed for future queries
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Provider API changes | Medium | High | Version pinning + schema validation |
| llama.cpp optimization complexity | High | Medium | Start with basic server mode, optimize incrementally |
| Sandbox resource exhaustion | Low | High | Strict cgroup limits, timeout enforcement |
| Ablation/CoreCoder CLI changes | Medium | High | Version pinning + output schema validation |
| Knowledge graph bloat | Medium | Medium | TTL-based cleanup, importance scoring |

---

## Success Criteria
1. ✅ All 8 major Ablation commands invokable as V9 tools
2. ✅ CoreCoder REPL and one-shot invokable as V9 tools
3. ✅ OpenAI-compatible provider works with 5+ providers
3. ✅ llama.cpp provider shows >2x throughput vs baseline
4. ✅ Findings queryable via V9's semantic search
5. ✅ 90%+ test coverage on integration paths
6. ✅ Zero modifications to Ablation/CoreCoder source code

---

## Dependencies
- Ablation: `pip install git+https://github.com/Ablation-Tool/ablation`
- CoreCoder: `pip install corecoder` or `pip install git+https://github.com/he-yufeng/CoreCoder`
- llama.cpp: `pip install llama-cpp-python` or llama.cpp server binary
- V9 core: DynamicToolRegistry, SandboxIsolator, SemanticIndexer, PromptAssembler, EventBus
- Docker runtime for sandbox execution

---

## Open Questions
1. **Provider config**: Single unified config file vs per-provider env vars?
2. **llama.cpp deployment**: Embedded bindings vs external server?
3. **Model routing**: Auto-select based on task type (coding vs analysis)?
4. **Sandbox images**: Pre-built vs on-demand build?
5. **Finding deduplication**: Same finding across multiple Ablation analyses?

---

## Next Steps
1. Confirm plan approach
2. Implementation agent begins Phase 1 (Provider Abstraction)
3. Weekly sync on integration progress