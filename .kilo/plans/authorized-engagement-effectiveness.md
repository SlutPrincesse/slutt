# Authorized Engagement Effectiveness Plan — AGENT_SYSTEM_V9

## Goal
Maximize detection accuracy, speed, and coverage for authorized, scoped
engagements while retaining safety-by-default (network gating, approval
guardrails, sandbox isolation).

## Phases

### 1. Recon Fidelity
- Parallel subfinder/amass/dnsx with dedup and rate limiting.
- HTTP probing with tech fingerprinting (wappalyzer-style) and screenshot capture.
- Asset graph in KnowledgeGraph with confidence scoring.

### 2. Vulnerability Detection
- Template-based scanning (nuclei) with custom V9 templates.
- Active verification of findings (no false positives) via re-request + diff.
- Severity scoring with CVSS + business impact.

### 3. Exploitation Verification (authorized only)
- Proof-of-concept generation in sandboxed containers.
- Impact demonstration without data exfiltration.
- Automatic rollback of any state changes.

### 4. Reporting
- Executive summary + technical details + remediation.
- Evidence bundle (screenshots, requests, responses).
- Compliance mapping (OWASP, PCI-DSS, etc.).

### 5. Distillation
- Ingest findings into KnowledgeGraph + CodeMemory.
- Distill successful techniques into reusable tools.
- Update provider routing based on detection success rates.

### 6. Safety (retained)
- Network gating per tool (opt-in).
- Approval guardrails for destructive actions.
- Sandbox isolation with read-only rootfs.
- Audit log of all actions.
- Scope enforcement (target allowlist).

## Success Metrics
- False positive rate < 5%.
- Coverage: ≥ 90% of known vulns in benchmark fixtures.
- Time to first finding < 5 min.
- Zero out-of-scope actions.
