"""
Continuous Security & Zero-Trust Isolation (Section 16)
"""
from .egress_proxy import (
    ApprovalHandler,
    EgressAction,
    EgressDecision,
    EgressLogger,
    EgressProxy,
    EgressRequest,
    EgressRule,
    Protocol,
    SocketInterceptor,
)
from .egress_proxy import (
    MetricsCollector as EgressMetricsCollector,
)
from .entropy_detector import EntropyDetector, SecretMatch, SecretType
from .integrity_verifier import (
    FileIntegrityRecord,
    HashAlgorithm,
    Hasher,
    IntegrityReport,
    IntegrityStatus,
    IntegrityStore,
    IntegrityVerifier,
    VerificationResult,
)
from .vulnerability_scanner import (
    ASTAnalyzer,
    DependencyChecker,
    PatternMatcher,
    ScanResult,
    Severity,
    Vulnerability,
    VulnerabilityScanner,
    VulnerabilityType,
)
from .zero_trust_gatekeeper import (
    ApprovalCallback,
    AuditLogger,
    DefaultApprovalCallback,
    ExecutionContext,
    MetricsCollector,
    PolicyBuilder,
    PolicyDecision,
    PolicyDecisionRecord,
    PolicyRule,
    ResourceType,
    ZeroTrustGatekeeper,
)

__all__ = [
    # Entropy Detector
    "EntropyDetector",
    "SecretMatch",
    "SecretType",
    # Zero Trust Gatekeeper
    "ZeroTrustGatekeeper",
    "PolicyDecision",
    "ResourceType",
    "ExecutionContext",
    "PolicyRule",
    "PolicyBuilder",
    "PolicyDecisionRecord",
    "ApprovalCallback",
    "DefaultApprovalCallback",
    "AuditLogger",
    "MetricsCollector",
    # Vulnerability Scanner
    "VulnerabilityScanner",
    "Vulnerability",
    "VulnerabilityType",
    "Severity",
    "ScanResult",
    "PatternMatcher",
    "ASTAnalyzer",
    "DependencyChecker",
    # Egress Proxy
    "EgressProxy",
    "EgressRule",
    "EgressRequest",
    "EgressDecision",
    "EgressAction",
    "Protocol",
    "ApprovalHandler",
    "EgressLogger",
    "EgressMetricsCollector",
    "SocketInterceptor",
    # Integrity Verifier
    "IntegrityVerifier",
    "IntegrityStore",
    "FileIntegrityRecord",
    "VerificationResult",
    "IntegrityReport",
    "IntegrityStatus",
    "HashAlgorithm",
    "Hasher",
]
