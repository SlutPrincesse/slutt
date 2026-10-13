"""
AGENT_SYSTEM_V9 (NEURO-CRANIAL OVERLORD) - Main Package
Master Technical Architecture Specification & Consolidated Implementation Roadmap
"""

# Core
from .core import SystemRegistry, EventBus, SystemConfig, registry, event_bus, config

# Kernel (Section 01)
from .kernel import (
    ProcessSupervisor, PTYManager, IPCAuditor, SandboxIsolator,
    KernelLogListener, ResourceThrottle, CgroupController,
    get_process_supervisor, get_pty_manager, get_ipc_auditor,
    get_sandbox_isolator, get_kernel_log_listener, get_resource_throttle
)

# Prompt Infrastructure (Section 02)
from .prompt import (
    PromptFileSystem, ReinforcementOptimizationLoop, DynamicPromptAssembler,
    TokenDensityCompressor, DynamicTokenBudgetAllocator,
    get_prompt_filesystem, get_optimization_loop, get_prompt_assembler,
    get_token_compressor, get_budget_allocator
)

# Multi-Modal (Section 03)
from .multimodal import (
    StreamingAudioPipeline, ImageGenerationGateway, DOMSpatialInspector,
    DocumentExtractor, get_audio_pipeline, get_image_gateway,
    get_dom_inspector, get_document_extractor
)

# Audit (Section 04)
from .audit import (
    NDJSONTelemetryLogger, PrometheusMetricsExporter, TerminalSystemDashboard,
    AuditTrailReplayEngine, PIIKeyRedactor,
    get_telemetry_logger, get_metrics_exporter, get_replay_engine, get_redactor
)

# Neuro-Cranial (Section 05)
from .neurocranial import (
    CorpusCallosum, DualStreamSplitter, ShadowBrokerScanner,
    ASTFunctionalExtractor, ApprovalModalGuardrail, CLISchemaGenerator,
    GlobalBinaryManager,
    get_corpus_callosum, get_dual_stream_splitter, get_shadow_broker,
    get_ast_extractor, get_approval_guardrail, get_cli_schema_generator,
    get_binary_manager
)

# Divergent Evolution (Section 06)
from .divergent import (
    DivergentExecutor, ASTNodeMerger, FailureTraceEvaluator,
    StateSerializer, TransactionJournal, MemoryPartition,
    get_divergent_executor, get_ast_merger, get_failure_evaluator,
    get_state_serializer, get_transaction_journal, get_memory_partition
)

# Cranial HUD (Section 07)
from .hud import (
    TaskGraphVisualizer, AmbientShaderPipeline, NudgeMonitor,
    LinguisticDisambiguator, ASTContextPruner,
    get_task_graph_visualizer, get_shader_pipeline, get_nudge_monitor,
    get_disambiguator, get_context_pruner
)

# Restructuring (Section 08)
from .restructure import (
    VulnerabilityAuditor, StealthProxyExecutor, IntentResolver,
    FailoverStateMachine, AutonomousLockIn,
    get_vulnerability_auditor, get_proxy_executor, get_intent_resolver,
    get_failover, get_lockin
)

# Prometheus-9 (Section 09)
from .prometheus9 import (
    MCPRouter, ASTStateGatekeeper, SurgicalASTMutator,
    ReactiveCallbackEngine, PredictiveTokenCompressor,
    get_mcp_router, get_ast_gatekeeper, get_ast_mutator,
    get_reactive_engine, get_predictive_compressor
)

# Recovery (Section 10)
from .recovery import (
    OPPEVELoop, StderrInterceptor, MergeCore, IngestRepo, LexicalNormalizer,
    get_oppeve_loop, get_stderr_interceptor, get_merge_core,
    get_ingest_repo, get_lexical_normalizer
)

# Syntax (Section 11)
from .syntax import (
    ISAEngine, Sanitizer, PathNormalizer, JSONNormalizer,
    MemorySerializer, BlueprintExporter,
    get_isa_engine, get_sanitizer, get_path_normalizer,
    get_json_normalizer, get_memory_serializer, get_blueprint_exporter
)

# Threat (Section 12/25)
from .threat import (
    ThreatSeeder, DeepAuditor, TimingValidator, RBACInspector, StressSimulator,
    get_threat_seeder
)

# Blueprint (Section 13/26)
from .blueprint import (
    PolyglotASTGenerator, ProtocolCompiler, FFIMapper,
    TraceabilityInspector, CoreStdLib,
    get_polyglot_ast, get_protocol_compiler, get_ffi_mapper,
    get_traceability_inspector, get_core_stdlib
)

# Distributed (Section 14)
from .distributed import (
    RPCGateway, DAGScheduler, BFTConsensus, LoadBalancer, CRDTStore,
    get_rpc_gateway, get_dag_scheduler, get_bft_consensus,
    get_load_balancer, get_crdt_store
)

# Reasoning (Section 15)
from .reasoning import (
    SemanticIndexer, EpisodicStore, ConceptAbstractor,
    ContextSerializer, OntologyUpdater
)

# Security (Section 16)
from .security import (
    ZeroTrustGatekeeper, EntropyDetector, VulnerabilityScanner,
    EgressProxy, IntegrityVerifier
)

# Reactive (Section 17)
from .reactive import (
    MessageBusAdapter, BackpressureController, HookEngine,
    StateMachineGuard, IdempotentConsumer
)

# Compilation (Section 18)
from .compilation import (
    UniversalCodeGenerator, SymbolInspector, MemoryCompiler,
    HotSwapLoader, TypeMarshaller
)

# Storage (Section 19)
from .storage import (
    VirtualObjectRepo, ContentAddressableStore, DeltaSync,
    AssetLifecycler, BuildLedger
)

# Deployment (Section 20)
from .deployment import (
    HealthVerifier, DeploymentHandshake, DegradationManager,
    ArtifactBundler, TelemetryMonitor
)

# Context (Section 21)
from .context import (
    AttentionAllocator, HierarchicalSummarizer, CacheInvalidator,
    BoundaryMonitor, ContextIsolationLayer
)

# Benchmark (Section 22)
from .benchmark import (
    TestGenerator, ComplexityEvaluator, PerformanceProfiler,
    RegressionDetector, CoverageLoop
)

# Edge (Section 23)
from .edge import (
    LLMFallbackGateway, OfflineCache, DeferredQueue,
    PowerThrottler, DeltaSyncer
)

# CI/CD (Section 24)
from .cicd import (
    SelfModifyingPipeline, ReleaseTagger, CanaryGuard,
    CapabilityExporter, KnowledgeExtractor
)

# Workspace (Section 27)
from .workspace import (
    WorkspaceManager, PolyglotASTDriver, FunctionMutator, ASTDiffEmitter
)

# Guardrails (Section 28)
from .guardrails import (
    PreCommitValidator, CommentStripper, TypingGuard, NoOpDetector
)

# Tools (Section 29)
from .tools import (
    ExceptionHookInterceptor, ToolSynthesizer, DynamicToolRegistry
)

# ShadowGit (Section 30)
from .shadowgit import (
    ShadowGit, MutationCheckpoint, ZeroRollback
)

# Evolution (Section 31)
from .evolution import (
    OrthogonalProjection, CloneOrchestrator, FitnessEvaluator, MergeSelector
)

__version__ = "9.0.0"
__codename__ = "NEURO-CRANIAL OVERLORD"

__all__ = [
    # Core
    "SystemRegistry", "EventBus", "SystemConfig", "registry", "event_bus", "config",
    # Kernel
    "ProcessSupervisor", "PTYManager", "IPCAuditor", "SandboxIsolator",
    "KernelLogListener", "ResourceThrottle", "CgroupController",
    # Prompt
    "PromptFileSystem", "ReinforcementOptimizationLoop", "DynamicPromptAssembler",
    "TokenDensityCompressor", "DynamicTokenBudgetAllocator",
    # Multimodal
    "StreamingAudioPipeline", "ImageGenerationGateway", "DOMSpatialInspector",
    "DocumentExtractor",
    # Audit
    "NDJSONTelemetryLogger", "PrometheusMetricsExporter", "TerminalSystemDashboard",
    "AuditTrailReplayEngine", "PIIKeyRedactor",
    # NeuroCranial
    "CorpusCallosum", "DualStreamSplitter", "ShadowBrokerScanner",
    "ASTFunctionalExtractor", "ApprovalModalGuardrail", "CLISchemaGenerator",
    "GlobalBinaryManager",
    # Divergent
    "DivergentExecutor", "ASTNodeMerger", "FailureTraceEvaluator",
    "StateSerializer", "TransactionJournal", "MemoryPartition",
    # HUD
    "TaskGraphVisualizer", "AmbientShaderPipeline", "NudgeMonitor",
    "LinguisticDisambiguator", "ASTContextPruner",
    # Restructure
    "VulnerabilityAuditor", "StealthProxyExecutor", "IntentResolver",
    "FailoverStateMachine", "AutonomousLockIn",
    # Prometheus9
    "MCPRouter", "ASTStateGatekeeper", "SurgicalASTMutator",
    "ReactiveCallbackEngine", "PredictiveTokenCompressor",
    # Recovery
    "OPPEVELoop", "StderrInterceptor", "MergeCore", "IngestRepo", "LexicalNormalizer",
    # Syntax
    "ISAEngine", "Sanitizer", "PathNormalizer", "JSONNormalizer",
    "MemorySerializer", "BlueprintExporter",
    # Threat
    "ThreatSeeder", "DeepAuditor", "TimingValidator", "RBACInspector", "StressSimulator",
    # Blueprint
    "PolyglotASTGenerator", "ProtocolCompiler", "FFIMapper",
    "TraceabilityInspector", "CoreStdLib",
    # Distributed
    "RPCGateway", "DAGScheduler", "BFTConsensus", "LoadBalancer", "CRDTStore",
    # Reasoning
    "SemanticIndexer", "EpisodicStore", "ConceptAbstractor",
    "ContextSerializer", "OntologyUpdater",
    # Security
    "ZeroTrustGatekeeper", "EntropyDetector", "VulnerabilityScanner",
    "EgressProxy", "IntegrityVerifier",
    # Reactive
    "MessageBusAdapter", "BackpressureController", "HookEngine",
    "StateMachineGuard", "IdempotentConsumer",
    # Compilation
    "UniversalCodeGenerator", "SymbolInspector", "MemoryCompiler",
    "HotSwapLoader", "TypeMarshaller",
    # Storage
    "VirtualObjectRepo", "ContentAddressableStore", "DeltaSync",
    "AssetLifecycler", "BuildLedger",
    # Deployment
    "HealthVerifier", "DeploymentHandshake", "DegradationManager",
    "ArtifactBundler", "TelemetryMonitor",
    # Context
    "AttentionAllocator", "HierarchicalSummarizer", "CacheInvalidator",
    "BoundaryMonitor", "ContextIsolationLayer",
    # Benchmark
    "TestGenerator", "ComplexityEvaluator", "PerformanceProfiler",
    "RegressionDetector", "CoverageLoop",
    # Edge
    "LLMFallbackGateway", "OfflineCache", "DeferredQueue",
    "PowerThrottler", "DeltaSyncer",
    # CI/CD
    "SelfModifyingPipeline", "ReleaseTagger", "CanaryGuard",
    "CapabilityExporter", "KnowledgeExtractor",
    # Workspace
    "WorkspaceManager", "PolyglotASTDriver", "FunctionMutator", "ASTDiffEmitter",
    # Guardrails
    "PreCommitValidator", "CommentStripper", "TypingGuard", "NoOpDetector",
    # Tools
    "ExceptionHookInterceptor", "ToolSynthesizer", "DynamicToolRegistry",
    # ShadowGit
    "ShadowGit", "MutationCheckpoint", "ZeroRollback",
    # Evolution
    "OrthogonalProjection", "CloneOrchestrator", "FitnessEvaluator", "MergeSelector",
]

def initialize_system() -> Dict[str, Any]:
    """Initialize all core system components"""
    results = {}
    
    # Initialize core
    results["core"] = {
        "registry": registry,
        "events": event_bus,
        "config": config
    }
    
    # Start kernel services
    results["kernel"] = {
        "process_supervisor": get_process_supervisor(),
        "pty_manager": get_pty_manager(),
        "ipc_auditor": get_ipc_auditor(),
        "sandbox_isolator": get_sandbox_isolator(),
        "kernel_log_listener": get_kernel_log_listener(),
        "resource_throttle": get_resource_throttle()
    }
    
    # Start prompt services
    results["prompt"] = {
        "filesystem": get_prompt_filesystem(),
        "optimization_loop": get_optimization_loop(),
        "assembler": get_prompt_assembler(),
        "compressor": get_token_compressor(),
        "budget_allocator": get_budget_allocator()
    }
    
    # Start audit services
    results["audit"] = {
        "telemetry": get_telemetry_logger(),
        "metrics": get_metrics_exporter(),
        "replay": get_replay_engine(),
        "redactor": get_redactor()
    }
    
    # Start neurocranial services
    results["neurocranial"] = {
        "corpus_callosum": get_corpus_callosum(),
        "dual_stream": get_dual_stream_splitter(),
        "shadow_broker": get_shadow_broker(),
        "ast_extractor": get_ast_extractor(),
        "approval_guardrail": get_approval_guardrail(),
        "cli_schema": get_cli_schema_generator(),
        "binary_manager": get_binary_manager()
    }
    
    return results


def shutdown_system():
    """Gracefully shutdown all system components"""
    # Stop in reverse order
    pass