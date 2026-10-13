"""
Restructuring & Continuous Compilation (Section 08)
Automated Vulnerability Cron Auditor, Stealth Proxy Execution & Identity Randomizer,
Zero-Latency Intent Resolution Pipeline, Dual-Hemisphere Failover State Machine,
Autonomous Lock-In Handshake
"""
from .vuln_auditor import VulnerabilityAuditor, VulnerabilityReport
from .proxy_executor import StealthProxyExecutor, ProxyConfig
from .intent_resolver import IntentResolver, IntentMatch
from .failover import FailoverStateMachine, FailoverState
from .lockin import AutonomousLockIn, LockInConfig

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