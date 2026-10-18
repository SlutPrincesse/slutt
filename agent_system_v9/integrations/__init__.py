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
    # Convenience
    "register_all_integrations",
]


def register_all_integrations(
    registry=None,
    sandbox=None,
    query_engine=None,
) -> dict[str, int]:
    """Register Ablation and CoreCoder tools into the DynamicToolRegistry.

    Wires the SandboxIsolator and QueryEngine into both integrations and
    returns the number of tools registered per integration.
    """
    from agent_system_v9.tools.tool_registry import DynamicToolRegistry
    from agent_system_v9.kernel.sandbox_isolator import SandboxIsolator
    from agent_system_v9.memory.query_engine import QueryEngine

    registry = registry or DynamicToolRegistry.get_instance()
    sandbox = sandbox or SandboxIsolator()
    query_engine = query_engine or QueryEngine()

    registry.set_sandbox_isolator(sandbox)

    ablation_count = register_ablation_tools(registry, sandbox, query_engine)
    corecoder_count = register_corecoder_tools(registry, sandbox, query_engine)

    return {"ablation": ablation_count, "corecoder": corecoder_count}
