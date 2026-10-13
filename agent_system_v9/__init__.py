"""
AGENT_SYSTEM_V9 (NEURO-CRANIAL OVERLORD) - Main Package
Master Technical Architecture Specification & Consolidated Implementation Roadmap
"""
from typing import Any

# Core
from .core import (
    SystemRegistry,
    EventBus,
    Event,
    EventPriority,
    SystemConfig,
    SectionConfig,
    registry,
    event_bus,
    config,
    PluginManager,
    PluginMetadata,
    PluginState,
    PluginContext,
    plugin_manager,
)

# Providers (Phase 1)
from .providers import (
    LLMProvider, ModelInfo, LLMResponse, LLMChunk, ProviderType,
    ProviderError, RateLimitError, AuthenticationError, ModelNotFoundError,
    OpenAICompatibleProvider, OpenAICompatibleConfig, create_openai_compatible_provider,
    LlamaCppProvider, LlamaCppConfig, create_llamacpp_provider,
    ProviderRegistry, ProviderFactory, ProviderRegistration, SelectionStrategy,
    initialize_provider_registry
)

# Kernel (Section 01)
from .kernel import (
    ProcessSupervisor, PTYManager, IPCAuditor, SandboxIsolator,
    KernelLogListener, ResourceThrottle, CgroupController,
)

# Prompt Infrastructure (Section 02)
from .prompt import (
    PromptFileSystem, ReinforcementOptimizationLoop, DynamicPromptAssembler,
    TokenDensityCompressor, DynamicTokenBudgetAllocator,
)

# Multi-Modal (Section 03)
from .multimodal import (
    StreamingAudioPipeline, ImageGenerationGateway, DOMSpatialInspector,
    DocumentExtractor,
)

# Audit (Section 04)
from .audit import (
    NDJSONTelemetryLogger, PrometheusMetricsExporter, TerminalSystemDashboard,
    AuditTrailReplayEngine, PIIKeyRedactor,
)

# Neuro-Cranial (Section 05)
from .neurocranial import (
    CorpusCallosum, DualStreamSplitter, ShadowBrokerScanner,
    ASTFunctionalExtractor, ApprovalModalGuardrail, CLISchemaGenerator,
    GlobalBinaryManager,
)

# Divergent Evolution (Section 06)
from .divergent import (
    DivergentExecutor, ASTNodeMerger, FailureTraceEvaluator,
    StateSerializer, TransactionJournal, MemoryPartition,
)

# Cranial HUD (Section 07)
from .hud import (
    TaskGraphVisualizer, AmbientShaderPipeline, NudgeMonitor,
    LinguisticDisambiguator, ASTContextPruner,
)

# Behavioral Framework (COM-B)
from .behavioral_framework import (
    COMModel, COMComponent, CapabilityType, OpportunityType, MotivationType,
    COMFactor, Behavior, Intervention, BCTTaxonomy,
    NudgeEngine, BehavioralDesigner,
)

# Restructuring (Section 08)
from .restructure import (
    VulnerabilityAuditor, StealthProxyExecutor, IntentResolver,
    FailoverStateMachine, AutonomousLockIn,
)

# Prometheus-9 (Section 09)
from .prometheus9 import (
    MCPRouter, ASTStateGatekeeper, SurgicalASTMutator,
    ReactiveCallbackEngine, PredictiveTokenCompressor,
)

# Recovery (Section 10)
from .recovery import (
    OPPEVELoop, StderrInterceptor, MergeCore, IngestRepo, LexicalNormalizer,
)

# Syntax (Section 11)
from .syntax import (
    ISAEngine, Sanitizer, PathNormalizer, JSONNormalizer,
    MemorySerializer, BlueprintExporter,
)

# Threat (Section 12/25)
from .threat import (
    ThreatSeeder, ThreatSeed,
    DeepAuditor, TimingValidator, RBACInspector, StressSimulator,
    BinaryAnalyzer, BinaryInfo, FunctionInfo, BinaryFormat, Architecture, AnalysisTool,
    GhidraAnalyzer, Radare2Analyzer, GDBController,
    BinaryASTMapper, PackerDetector, AntiDebugDetector, BinaryAnalysisOrchestrator,
    ControlFlowGraph, CFGNode,
)

# Blueprint (Section 13/26)
from .blueprint import (
    PolyglotASTGenerator, ProtocolCompiler, FFIMapper,
    TraceabilityInspector, CoreStdLib,
)

# Distributed (Section 14)
from .distributed import (
    RPCGateway, DAGScheduler, BFTConsensus, LoadBalancer, CRDTStore,
)

# Reasoning (Section 15)
from .reasoning import (
    ConceptAbstractor, Concept, ContextSerializer, OntologyUpdater, OntologyConcept,
)

# Memory (Section 15 - Knowledge Graph)
from .memory import (
    CodeMemory, CodeNode, CodeEdge,
    EpisodicStore as MemoryEpisodicStore, Episode, EpisodeType,
    SemanticIndexer as MemorySemanticIndexer, IndexConfig, SearchResult,
    KnowledgeGraph, Entity, Relation, GraphQuery,
    QueryEngine, QueryPlan, QueryResult
)

# Security (Section 16)
from .security import (
    ZeroTrustGatekeeper, EntropyDetector, VulnerabilityScanner,
    EgressProxy, IntegrityVerifier
)

# Reactive (Section 17)
from .reactive import (
    MessageBus, InMemoryMessageBus, KafkaAdapter, RedisAdapter, MessageBusFactory,
    Message, MessagePriority, Subscription,
    BackpressureController, BackpressureConfig, BackpressureStrategy,
    AsyncBuffer, TokenBucket, LeakyBucket, FlowController, FlowMetrics,
    ReactiveStream, BufferFullException, BackpressureSignal,
    HookEngine, PipelineHookEngine, ConditionalHookEngine, AsyncHookEngine,
    Hook, HookContext, HookPhase, HookPriority, HookMetrics, DecoratorHooks,
    StateMachine, HierarchicalStateMachine, StateMachineGuard,
    StateMachineBuilder, ProtocolStateMachine, State, Transition, TransitionType, StateMachineConfig,
    IdempotentConsumer, ExactlyOnceProcessor, MessageDeduplicator,
    TransactionalOutbox, DistributedLock, DeduplicationStore,
    InMemoryDeduplicationStore, RedisDeduplicationStore,
    DeduplicationStrategy, ProcessingResult, IdempotencyKey
)

# Compilation (Section 18)
from .compilation import (
    UniversalCodeGenerator, CodeGenerator, PythonCodeGenerator, JavaScriptCodeGenerator,
    TypeScriptCodeGenerator, RustCodeGenerator, CodeTemplate, GenerationContext,
    TargetLanguage, ASTToCodeConverter, IncrementalCodeGenerator,
    SymbolInspector, SymbolTable, Symbol, SymbolReference, Scope, SymbolType, Visibility, CrossFileAnalyzer,
    JITCompiler, HotReloader, CompilationPipeline, IncrementalCompiler,
    CompilationUnit, CompilationResult, CompilationTarget, CompilationStatus,
    BaseCompiler, BytecodeCompiler, ASTCompiler, MemoryCache,
    HotSwapLoader, CompilationPluginManager, IsolatedLoader, LazyLoader, LazyModuleProxy,
    ModuleInfo, ReloadEvent, LoadStatus, temporary_module,
    TypeMarshaller, Marshaller, JSONMarshaller, BinaryMarshaller,
    TypeInfo, TypeKind, SchemaValidator, CrossLanguageTypeMapper
)

# Storage (Section 19)
from .storage import (
    VirtualObjectRepository, ObjectStore, VersionedObjectStore, ObjectSerializer,
    ContentAddressableStore, ObjectId, ObjectType, ObjectMetadata, VersionedObject, ObjectVersion,
    DeltaGenerator, DeltaApplier, SyncEngine, ConflictResolver,
    AssetLifecycler, BuildLedger,
    Delta, DeltaType, DeltaOperation, SyncState, DeltaEncoder,
    BlobStore, Chunker, Blob, Chunk, ChunkingStrategy, CASConfig,
    DeltaSync, CASDeltaSync,
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

# Feature Engineering (Section 25+)
from .featuretools_engine import (
    PrimitiveLibrary, Primitive, PrimitiveType, DataType,
    Entity as FeatureEntity, Relationship, EntitySet, Feature, FeatureVector,
    DeepFeatureSynthesis, FeatureToolsEngine,
    ExecutionLogFeatureExtractor,
    DaskFeatureEngine,
)

# CI/CD (Section 24)
from .cicd import (
    SelfModifyingPipeline, ReleaseTagger, CanaryGuard,
    CapabilityExporter, KnowledgeExtractor
)

# Workspace (Section 27)
from .workspace import (
    WorkspaceManager, WorkspaceConfig, Workspace, WorkspaceType, WorkspaceStatus,
    WorkspaceTemplate, WorkspaceIsolation, WorkspaceSnapshot,
    PolyglotASTDriver, ASTParser, ASTNode, ParseResult, Language,
    ASTTransformer, ASTIndexer,
    TreeSitterManager, TreeSitterConfig, TREE_SITTER_AVAILABLE,
    FunctionMutator, MutationTester, EvolutionaryMutator,
    Mutation, MutationResult, MutationType,
    WorkspaceSynchronizer, WorkspaceReplicator, SyncScheduler, WorkspaceConflictResolver,
    SyncConfig, SyncMode, ConflictStrategy, FileInfo, WorkspaceSyncResult,
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
    ShadowGit, ShadowGitRemote, ShadowFile, ShadowCommit, ShadowBranch, ShadowDiff, ShadowGitStatus,
    ShadowIndex, IndexMerger, IndexEntry, IndexEntryStatus, IndexTree,
    ShadowGitSync, ShadowGitLFS, SyncDirection, SyncStatus, RemoteProtocol,
    RemoteConfig, SyncOptions, SyncResult, SyncConflict,
)

# Evolution (Section 31)
from .evolution import (
    EvolutionEngine, EvolutionConfig, EvolutionResult, Individual,
    FitnessFunction, EvolutionStrategyEnum, SelectionMethod,
    MultiObjectiveEvolution, AdaptiveEvolution,
    CodeEvolutionEngine, CodeEvolutionConfig, CodeIndividual, CodeMutationType,
    CodeOptimizer, RefactoringEvolution,
    ArchitectureEvolutionEngine, ArchitectureEvolutionConfig, ArchitectureIndividual,
    ArchitectureDecision, ArchitecturePattern, QualityAttribute,
    ArchitectureFitnessFunction, ArchitectureOptimizer, EvolutionaryArchitectureReviewer,
    EvolutionStrategy as EvoStrategy, CMAES, ParticleSwarmOptimization,
    DifferentialEvolution, EvolutionStrategyPlus, EvolutionStrategyComma,
    StrategyConfig, StrategyResult, StrategySelector, AdaptiveStrategySelector, PortfolioOptimizer, StrategyType,
)

# Integrations: Ablation, CoreCoder, RedAmon, Cybersec-Toolkit
from .integrations import (
    register_ablation_tools, AblationToolSynthesizer, ABLATION_COMMANDS,
    register_corecoder_tools, CoreCoderToolSynthesizer, CORECODER_COMMANDS,
    # RedAmon
    RedamonOrchestrator, AgentTask, AgentContext, AgentPhase, TaskStatus,
    OrchestratorIntegration, get_orchestrator_integration, agent_session,
    KnowledgeBase, Document, KBSearchResult, EmbeddingProvider, VectorStore,
    InMemoryVectorStore, KnowledgeBaseIntegration, get_knowledge_base_integration,
    DockerBroker, DockerBrokerConfig, DockerBrokerIntegration, get_docker_broker_integration,
    ReconModule, ReconPipeline, ReconTarget, ReconResult, ReconModuleType,
    SubdomainEnumModule, PortScanModule, HTTPProbeModule, NucleiScanModule,
    KatanaCrawlModule, GraphQLScannerModule, ReconIntegration, get_recon_integration,
    # Cybersec-Toolkit
    ToolManager, ToolConfig, ModuleRunner,
    CybersecToolkitIntegration, get_cybersec_toolkit_integration,
)

# TUI & GUI
from .tui import AgentV9TUI, run_tui
from .gui import WebappManager, WebappConfig, GUIIntegration, get_webapp_manager, get_gui_integration, run_with_gui

__version__ = "9.0.0"
__codename__ = "NEURO-CRANIAL OVERLORD"

__all__ = [
    # Core
    "SystemRegistry", "EventBus", "Event", "EventPriority", "SystemConfig", "SectionConfig",
    "registry", "event_bus", "config",
    "PluginManager", "PluginMetadata", "PluginState", "PluginContext", "plugin_manager",
    # Providers (Phase 1)
    "LLMProvider", "ModelInfo", "LLMResponse", "LLMChunk", "ProviderType",
    "ProviderError", "RateLimitError", "AuthenticationError", "ModelNotFoundError",
    "OpenAICompatibleProvider", "OpenAICompatibleConfig", "create_openai_compatible_provider",
    "LlamaCppProvider", "LlamaCppConfig", "create_llamacpp_provider",
    "ProviderRegistry", "ProviderFactory", "ProviderRegistration", "SelectionStrategy",
    "initialize_provider_registry",
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
    # Behavioral Framework (COM-B)
    "COMModel", "COMComponent", "CapabilityType", "OpportunityType", "MotivationType",
    "COMFactor", "Behavior", "Intervention", "BCTTaxonomy",
    "NudgeEngine", "BehavioralDesigner",
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
    "ThreatSeeder", "ThreatSeed",
    "DeepAuditor", "TimingValidator", "RBACInspector", "StressSimulator",
    "BinaryAnalyzer", "BinaryInfo", "FunctionInfo", "BinaryFormat", "Architecture", "AnalysisTool",
    "GhidraAnalyzer", "Radare2Analyzer", "GDBController",
    "BinaryASTMapper", "PackerDetector", "AntiDebugDetector", "BinaryAnalysisOrchestrator",
    "ControlFlowGraph", "CFGNode",
    # Blueprint
    "PolyglotASTGenerator", "ProtocolCompiler", "FFIMapper",
    "TraceabilityInspector", "CoreStdLib",
    # Distributed
    "RPCGateway", "DAGScheduler", "BFTConsensus", "LoadBalancer", "CRDTStore",
    # Reasoning
    "ConceptAbstractor", "Concept", "ContextSerializer", "OntologyUpdater", "OntologyConcept",
    # Memory
    "CodeMemory", "CodeNode", "CodeEdge",
    "MemoryEpisodicStore", "Episode", "EpisodeType",
    "MemorySemanticIndexer", "IndexConfig", "SearchResult",
    "KnowledgeGraph", "Entity", "Relation", "GraphQuery",
    "QueryEngine", "QueryPlan", "QueryResult",
    # Security
    "ZeroTrustGatekeeper", "EntropyDetector", "VulnerabilityScanner",
    "EgressProxy", "IntegrityVerifier",
    # Reactive
    "MessageBus", "InMemoryMessageBus", "KafkaAdapter", "RedisAdapter", "MessageBusFactory",
    "Message", "MessagePriority", "Subscription",
    "BackpressureController", "BackpressureConfig", "BackpressureStrategy",
    "AsyncBuffer", "TokenBucket", "LeakyBucket", "FlowController", "FlowMetrics",
    "ReactiveStream", "BufferFullException", "BackpressureSignal",
    "HookEngine", "PipelineHookEngine", "ConditionalHookEngine", "AsyncHookEngine",
    "Hook", "HookContext", "HookPhase", "HookPriority", "HookMetrics", "DecoratorHooks",
    "StateMachine", "HierarchicalStateMachine", "StateMachineGuard",
    "StateMachineBuilder", "ProtocolStateMachine", "State", "Transition", "TransitionType", "StateMachineConfig",
    "IdempotentConsumer", "ExactlyOnceProcessor", "MessageDeduplicator",
    "TransactionalOutbox", "DistributedLock", "DeduplicationStore",
    "InMemoryDeduplicationStore", "RedisDeduplicationStore",
    "DeduplicationStrategy", "ProcessingResult", "IdempotencyKey",
    # Compilation
    "UniversalCodeGenerator", "CodeGenerator", "PythonCodeGenerator", "JavaScriptCodeGenerator",
    "TypeScriptCodeGenerator", "RustCodeGenerator", "CodeTemplate", "GenerationContext",
    "TargetLanguage", "ASTToCodeConverter", "IncrementalCodeGenerator",
    "SymbolInspector", "SymbolTable", "Symbol", "SymbolReference", "Scope", "SymbolType", "Visibility", "CrossFileAnalyzer",
    "JITCompiler", "HotReloader", "CompilationPipeline", "IncrementalCompiler",
    "CompilationUnit", "CompilationResult", "CompilationTarget", "CompilationStatus",
    "BaseCompiler", "BytecodeCompiler", "ASTCompiler", "MemoryCache",
    "HotSwapLoader", "CompilationPluginManager", "IsolatedLoader", "LazyLoader", "LazyModuleProxy",
    "ModuleInfo", "ReloadEvent", "LoadStatus", "temporary_module",
    "TypeMarshaller", "Marshaller", "JSONMarshaller", "BinaryMarshaller",
    "TypeInfo", "TypeKind", "SchemaValidator", "CrossLanguageTypeMapper",
    # Storage
    "VirtualObjectRepository", "ObjectStore", "VersionedObjectStore", "ObjectSerializer",
    "ContentAddressableStore", "ObjectId", "ObjectType", "ObjectMetadata", "VersionedObject", "ObjectVersion",
    "DeltaGenerator", "DeltaApplier", "SyncEngine", "ConflictResolver",
    "AssetLifecycler", "BuildLedger",
    "Delta", "DeltaType", "DeltaOperation", "SyncState", "DeltaEncoder",
    "BlobStore", "Chunker", "Blob", "Chunk", "ChunkingStrategy", "CASConfig",
    "DeltaSync", "CASDeltaSync",
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
    # Feature Engineering
    "PrimitiveLibrary", "Primitive", "PrimitiveType", "DataType",
    "FeatureEntity", "Relationship", "EntitySet", "Feature", "FeatureVector",
    "DeepFeatureSynthesis", "FeatureToolsEngine",
    "ExecutionLogFeatureExtractor",
    "DaskFeatureEngine",
    # CI/CD
    "SelfModifyingPipeline", "ReleaseTagger", "CanaryGuard",
    "CapabilityExporter", "KnowledgeExtractor",
    # Workspace
    "WorkspaceManager", "WorkspaceConfig", "Workspace", "WorkspaceType", "WorkspaceStatus",
    "WorkspaceTemplate", "WorkspaceIsolation", "WorkspaceSnapshot",
    "PolyglotASTDriver", "ASTParser", "ASTNode", "ParseResult", "Language",
    "ASTTransformer", "ASTIndexer",
    "TreeSitterManager", "TreeSitterConfig", "TREE_SITTER_AVAILABLE",
    "FunctionMutator", "MutationTester", "EvolutionaryMutator",
    "Mutation", "MutationResult", "MutationType",
    "WorkspaceSynchronizer", "WorkspaceReplicator", "SyncScheduler", "WorkspaceConflictResolver",
    "SyncConfig", "SyncMode", "ConflictStrategy", "FileInfo", "SyncResult",
    # Guardrails
    "PreCommitValidator", "CommentStripper", "TypingGuard", "NoOpDetector",
    # Tools
    "ExceptionHookInterceptor", "ToolSynthesizer", "DynamicToolRegistry",
    # ShadowGit
    "ShadowGit", "ShadowGitRemote", "ShadowFile", "ShadowCommit", "ShadowBranch", "ShadowDiff", "ShadowGitStatus",
    "ShadowIndex", "IndexMerger", "IndexEntry", "IndexEntryStatus", "IndexTree",
    # Evolution
    "EvolutionEngine", "EvolutionConfig", "EvolutionResult", "Individual",
    "FitnessFunction", "EvolutionStrategy", "SelectionMethod",
    "MultiObjectiveEvolution", "AdaptiveEvolution",
    "CodeEvolutionEngine", "CodeEvolutionConfig", "CodeIndividual", "CodeMutationType",
    "CodeOptimizer", "RefactoringEvolution",
    "ArchitectureEvolutionEngine", "ArchitectureEvolutionConfig", "ArchitectureIndividual",
    "ArchitectureDecision", "ArchitecturePattern", "QualityAttribute",
    "ArchitectureFitnessFunction", "ArchitectureOptimizer", "EvolutionaryArchitectureReviewer",
    "EvolutionStrategy", "CMAES", "ParticleSwarmOptimization",
    "DifferentialEvolution", "EvolutionStrategyPlus", "EvolutionStrategyComma",
    "StrategyConfig", "StrategyResult", "StrategySelector", "AdaptiveStrategySelector", "PortfolioOptimizer", "StrategyType",
    # Integrations
    "register_ablation_tools", "AblationToolSynthesizer", "ABLATION_COMMANDS",
    "register_corecoder_tools", "CoreCoderToolSynthesizer", "CORECODER_COMMANDS",
    # RedAmon Orchestrator
    "RedamonOrchestrator", "AgentTask", "AgentContext", "AgentPhase", "TaskStatus",
    "OrchestratorIntegration", "get_orchestrator_integration", "agent_session",
    # RedAmon Knowledge Base
    "KnowledgeBase", "Document", "KBSearchResult", "EmbeddingProvider", "VectorStore",
    "InMemoryVectorStore", "KnowledgeBaseIntegration", "get_knowledge_base_integration",
    # RedAmon Docker Broker
    "DockerBroker", "DockerBrokerConfig", "DockerBrokerIntegration", "get_docker_broker_integration",
    # RedAmon Recon
    "ReconModule", "ReconPipeline", "ReconTarget", "ReconResult", "ReconModuleType",
    "SubdomainEnumModule", "PortScanModule", "HTTPProbeModule", "NucleiScanModule",
    "KatanaCrawlModule", "GraphQLScannerModule", "ReconIntegration", "get_recon_integration",
    # Cybersec-Toolkit
    "ToolManager", "ToolConfig", "ModuleRunner",
    "CybersecToolkitIntegration", "get_cybersec_toolkit_integration",
    # TUI & GUI
    "AgentV9TUI", "run_tui",
    "WebappManager", "WebappConfig", "GUIIntegration",
    "get_webapp_manager", "get_gui_integration", "run_with_gui",
]


def initialize_system() -> dict[str, Any]:
    """Initialize all core system components"""
    results = {}

    # Initialize core
    results["core"] = {
        "registry": registry,
        "events": event_bus,
        "config": config
    }

    # Initialize providers (Phase 1)
    results["providers"] = {
        "registry": ProviderRegistry.get_instance(),
    }

    # Kernel services (classes available for instantiation)
    results["kernel"] = {
        "ProcessSupervisor": ProcessSupervisor,
        "PTYManager": PTYManager,
        "IPCAuditor": IPCAuditor,
        "SandboxIsolator": SandboxIsolator,
        "KernelLogListener": KernelLogListener,
        "ResourceThrottle": ResourceThrottle,
        "CgroupController": CgroupController,
    }

    # Prompt services (classes available for instantiation)
    results["prompt"] = {
        "PromptFileSystem": PromptFileSystem,
        "ReinforcementOptimizationLoop": ReinforcementOptimizationLoop,
        "DynamicPromptAssembler": DynamicPromptAssembler,
        "TokenDensityCompressor": TokenDensityCompressor,
        "DynamicTokenBudgetAllocator": DynamicTokenBudgetAllocator,
    }

    # Audit services (classes available for instantiation)
    results["audit"] = {
        "NDJSONTelemetryLogger": NDJSONTelemetryLogger,
        "PrometheusMetricsExporter": PrometheusMetricsExporter,
        "TerminalSystemDashboard": TerminalSystemDashboard,
        "AuditTrailReplayEngine": AuditTrailReplayEngine,
        "PIIKeyRedactor": PIIKeyRedactor,
    }

    # Neurocranial services (classes available for instantiation)
    results["neurocranial"] = {
        "CorpusCallosum": CorpusCallosum,
        "DualStreamSplitter": DualStreamSplitter,
        "ShadowBrokerScanner": ShadowBrokerScanner,
        "ASTFunctionalExtractor": ASTFunctionalExtractor,
        "ApprovalModalGuardrail": ApprovalModalGuardrail,
        "CLISchemaGenerator": CLISchemaGenerator,
        "GlobalBinaryManager": GlobalBinaryManager,
    }

    return results


def shutdown_system():
    """Gracefully shutdown all system components"""
    # Stop in reverse order
    pass
