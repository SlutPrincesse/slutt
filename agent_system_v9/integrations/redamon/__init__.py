"""
RedAmon Integrations for AGENT_SYSTEM_V9
"""
from .docker_broker.integration import (
    DockerBroker,
    DockerBrokerConfig,
    DockerBrokerIntegration,
    get_docker_broker_integration,
)
from .knowledge_base.integration import (
    Document,
    EmbeddingProvider,
    InMemoryVectorStore,
    KnowledgeBase,
    KnowledgeBaseIntegration,
    KBSearchResult,
    SearchResult,
    VectorStore,
    get_knowledge_base_integration,
)
from .orchestrator.integration import (
    AgentContext,
    AgentPhase,
    AgentTask,
    OrchestratorIntegration,
    RedamonOrchestrator,
    TaskStatus,
    agent_session,
    get_orchestrator_integration,
)
from .recon.integration import (
    GraphQLScannerModule,
    HTTPProbeModule,
    KatanaCrawlModule,
    NucleiScanModule,
    PortScanModule,
    ReconIntegration,
    ReconModule,
    ReconModuleType,
    ReconPipeline,
    ReconResult,
    ReconTarget,
    SubdomainEnumModule,
    get_recon_integration,
)

__all__ = [
    # Orchestrator
    "RedamonOrchestrator",
    "AgentTask",
    "AgentContext",
    "AgentPhase",
    "TaskStatus",
    "OrchestratorIntegration",
    "get_orchestrator_integration",
    "agent_session",
    # Knowledge Base
    "KnowledgeBase",
    "Document",
    "SearchResult",
    "KBSearchResult",
    "EmbeddingProvider",
    "VectorStore",
    "InMemoryVectorStore",
    "KnowledgeBaseIntegration",
    "get_knowledge_base_integration",
    # Docker Broker
    "DockerBroker",
    "DockerBrokerConfig",
    "DockerBrokerIntegration",
    "get_docker_broker_integration",
    # Recon
    "ReconModule",
    "ReconPipeline",
    "ReconTarget",
    "ReconResult",
    "ReconModuleType",
    "SubdomainEnumModule",
    "PortScanModule",
    "HTTPProbeModule",
    "NucleiScanModule",
    "KatanaCrawlModule",
    "GraphQLScannerModule",
    "ReconIntegration",
    "get_recon_integration",
]
