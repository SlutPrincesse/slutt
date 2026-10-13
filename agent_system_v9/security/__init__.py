"""
Continuous Security & Zero-Trust Isolation (Section 16)
"""
from .entropy_detector import EntropyDetector, SecretMatch, SecretType
from .zero_trust_gatekeeper import (
    ZeroTrustGatekeeper,
    PolicyDecision,
    ResourceType,
    ExecutionContext,
    PolicyRule,
    PolicyBuilder,
    PolicyDecisionRecord,
    ApprovalCallback,
    DefaultApprovalCallback,
    AuditLogger,
    MetricsCollector,
)
from .vulnerability_scanner import (
    VulnerabilityScanner,
    Vulnerability,
    VulnerabilityType,
    Severity,
    ScanResult,
    PatternMatcher,
    ASTAnalyzer,
    DependencyChecker,
)
from .egress_proxy import (
    EgressProxy,
    EgressRule,
    EgressRequest,
    EgressDecision,
    EgressAction,
    Protocol,
    ApprovalHandler,
    EgressLogger,
    MetricsCollector as EgressMetricsCollector,
    SocketInterceptor,
)
from .integrity_verifier import (
    IntegrityVerifier,
    IntegrityStore,
    FileIntegrityRecord,
    VerificationResult,
    IntegrityReport,
    IntegrityStatus,
    HashAlgorithm,
    Hasher,
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