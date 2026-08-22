"""Local-first coding agent MVP (pure stdlib Python).

Three proven mechanisms only:
  1. Local pre-processor  - prune context, normalize typos, disambiguate vague
                            commands, deterministic cleanup.
  2. Worktree sharding    - isolate parallel agents in git worktrees; human
                            picks the diff (no auto-merge).
  3. Consent-gated tools   - opt-in tool registry; never auto-fetch/execute.

No model, no network, no GUI. The "agent" is a pluggable command you supply.
"""

__version__ = "0.1.0"
