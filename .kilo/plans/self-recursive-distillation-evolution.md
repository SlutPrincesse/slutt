# Self-Recursive Distillation Evolution Plan — AGENT_SYSTEM_V9

## Vision
Transform AGENT_SYSTEM_V9 into a top-tier, self-improving agent harness that
recursively distills its own traces, tools, and outcomes into better policies,
prompts, and tools, closing the loop between execution and improvement.

## Core Principle: Recursive Distillation
Every agent run produces a trace. Traces are distilled into:
- Compressed memory (context rot defense) — already Phase 1.
- Reusable skills/tools (tool synthesis) — existing tool_synthesizer.
- Improved prompts (prompt optimization loop) — existing optimization_loop.
- Better routing/selection (provider + tool metrics).
- Evaluation datasets (benchmark harness).
Each distillation feeds back into the next run, creating a self-improvement loop.

## Architecture of the Loop
```
Run → Trace → Evaluate → Distill → Update (prompts/tools/memory/policy) → Run
```

## Phases

### Phase A: Trace & Telemetry Foundation
1. Standardize trace schema: every tool call, LLM call, decision, outcome, latency, cost.
2. Persist traces to EpisodicStore + structured JSONL logs.
3. Add OpenTelemetry spans for each step (optional dep).
4. Metrics aggregation: per-tool success rate, latency percentiles, cost.

### Phase B: Distillation Engine
1. Trace distiller: cluster successful traces by task type; extract reusable patterns.
2. Prompt distiller: A/B test prompt variants; keep winners (existing optimization_loop).
3. Tool distiller: synthesize new tools from repeated code patterns (tool_synthesizer).
4. Memory distiller: compress episodic memory into semantic knowledge graph with decay.
5. Policy distiller: update provider selection weights and tool routing based on outcomes.

### Phase C: Evaluation & Regression
1. SWE-bench-lite harness integration (existing benchmark.py).
2. Pass@k measurement with statistical significance.
3. Red-team fuzzing: tool args, sandbox escape, prompt injection.
4. Regression suite: golden traces replayed on every change.
5. Auto-rollback if metrics regress.

### Phase D: Recursive Self-Improvement
1. Nightly distillation job: process accumulated traces → propose prompt/tool updates.
2. Human-in-the-loop approval for high-impact changes (ApprovalGuard).
3. Canary deployment: test new policy on subset of tasks.
4. Promote if better; revert if worse.
5. Track lineage: which distillation produced which improvement.

### Phase E: Top-Tier Capabilities
1. Frontier model integration with cost-aware routing (done partially).
2. Semantic code understanding (tree-sitter + LSP + vector retrieval).
3. Multi-agent consensus (planner/coder/tester/reviewer) with voting.
4. Streaming UX + human oversight.
5. Containerized sandboxes by default.
6. Cross-session learning memory.

## Implementation Order (Recursive)
Iteration 1: Traces + basic distillation (prompts).
Iteration 2: Tool synthesis from traces.
Iteration 3: Memory distillation + decay.
Iteration 4: Evaluation harness + regression.
Iteration 5: Policy auto-tuning.
Iteration 6: Canary + promotion.
Each iteration feeds the next with real data.

## Success Metrics
- Pass@1 improvement ≥ 10% per iteration on SWE-bench-lite subset.
- Context token usage reduced ≥ 30% via compression.
- Tool success rate ≥ 95%.
- Zero sandbox escapes in red-team.
- Cost per task reduced ≥ 20%.

## Risk Mitigations
- Human approval gates for destructive changes.
- Canary + auto-rollback.
- Immutable baseline for comparison.
- Audit log of all distillation decisions.
