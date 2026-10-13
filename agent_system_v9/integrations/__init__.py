"""
Integrations for AGENT_SYSTEM_V9 - External system integrations
"""
from .ablation import (
    ABLATION_COMMANDS,
    AblationToolSynthesizer,
    register_ablation_tools,
)
from .corecoder import (
    CORECODER_COMMANDS,
    CoreCoderToolSynthesizer,
    register_corecoder_tools,
)
from .cybersec_toolkit import (
    CybersecToolkitIntegration,
    ModuleRunner,
    ToolConfig,
    ToolManager,
    get_cybersec_toolkit_integration,
)
from .redamon import (
    AgentContext,
    AgentPhase,
    AgentTask,
    # Docker Broker
    DockerBroker,
    DockerBrokerConfig,
    DockerBrokerIntegration,
    Document,
    EmbeddingProvider,
    GraphQLScannerModule,
    HTTPProbeModule,
    InMemoryVectorStore,
    KatanaCrawlModule,
    # Knowledge Base
    KBSearchResult,
    KnowledgeBase,
    KnowledgeBaseIntegration,
    NucleiScanModule,
    OrchestratorIntegration,
    PortScanModule,
    ReconIntegration,
    # Recon
    ReconModule,
    ReconModuleType,
    ReconPipeline,
    ReconResult,
    ReconTarget,
    # Orchestrator
    RedamonOrchestrator,
    SearchResult,
    SubdomainEnumModule,
    TaskStatus,
    VectorStore,
    agent_session,
    get_docker_broker_integration,
    get_knowledge_base_integration,
    get_orchestrator_integration,
    get_recon_integration,
)

__all__ = [
    # Ablation
    "register_ablation_tools", "AblationToolSynthesizer", "ABLATION_COMMANDS",
    # CoreCoder
    "register_corecoder_tools", "CoreCoderToolSynthesizer", "CORECODER_COMMANDS",
    # RedAmon Orchestrator
    "RedamonOrchestrator", "AgentTask", "AgentContext", "AgentPhase", "TaskStatus",
    "OrchestratorIntegration", "get_orchestrator_integration", "agent_session",
    # RedAmon Knowledge Base
    "KnowledgeBase", "Document", "SearchResult", "KBSearchResult", "EmbeddingProvider", "VectorStore",
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
]
