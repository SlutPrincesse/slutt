"""
Restructuring & Continuous Compilation (Section 08)
Automated Vulnerability Cron Auditor, Stealth Proxy Execution & Identity Randomizer,
Zero-Latency Intent Resolution Pipeline, Dual-Hemisphere Failover State Machine,
Autonomous Lock-In Handshake
"""
from .failover import FailoverState, FailoverStateMachine
from .intent_resolver import IntentMatch, IntentResolver
from .lockin import AutonomousLockIn, LockInConfig
from .proxy_executor import ProxyConfig, StealthProxyExecutor
from .vuln_auditor import VulnerabilityAuditor, VulnerabilityReport

__all__ = [
    "VulnerabilityAuditor",
    "VulnerabilityReport",
    "StealthProxyExecutor",
    "ProxyConfig",
    "IntentResolver",
    "IntentMatch",
    "FailoverStateMachine",
    "FailoverState",
    "AutonomousLockIn",
    "LockInConfig",
]
