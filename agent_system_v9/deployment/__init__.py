"""
Deployment Lifecycle & Handover Automation (Section 20)
Pre-Flight Health Verifier, Autonomous Deployment Handshake,
Graceful Degradation Manager, Self-Contained Artifact Bundler,
Post-Deployment Telemetry Monitor
"""
from .health_verifier import HealthVerifier, HealthCheck
from .deployment_handshake import DeploymentHandshake, HandshakeState
from .degradation import DegradationManager, DegradationLevel
from .artifact_bundler import ArtifactBundler, BundleManifest
from .telemetry_monitor import TelemetryMonitor, TelemetrySnapshot

__all__ = [
    "HealthVerifier",
    "HealthCheck",
    "DeploymentHandshake",
    "HandshakeState",
    "DegradationManager",
    "DegradationLevel",
    "ArtifactBundler",
    "BundleManifest",
    "TelemetryMonitor",
    "TelemetrySnapshot",
]