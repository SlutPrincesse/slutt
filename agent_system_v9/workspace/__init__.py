"""
Workspace Isolation & Multilingual AST Engine (Section 27)
"""
from .function_mutator import (
    EvolutionaryMutator,
    FunctionMutator,
    Mutation,
    MutationResult,
    MutationTester,
    MutationType,
)
from .polyglot_ast_driver import (
    TREE_SITTER_AVAILABLE,
    ASTIndexer,
    ASTNode,
    ASTParser,
    ASTTransformer,
    Language,
    ParseResult,
    PolyglotASTDriver,
    TreeSitterConfig,
    TreeSitterManager,
)
from .workspace_manager import (
    Workspace,
    WorkspaceConfig,
    WorkspaceIsolation,
    WorkspaceManager,
    WorkspaceSnapshot,
    WorkspaceStatus,
    WorkspaceTemplate,
    WorkspaceType,
)
from .workspace_synchronizer import (
    ConflictResolver,
    ConflictStrategy,
    FileInfo,
    SyncConfig,
    SyncMode,
    SyncResult,
    SyncScheduler,
    WorkspaceReplicator,
    WorkspaceSynchronizer,
)

# Alias for AGENT_SYSTEM_V9 main package to avoid naming conflict with storage.ConflictResolver
WorkspaceConflictResolver = ConflictResolver
WorkspaceSyncResult = SyncResult

__all__ = [
    # Workspace Manager
    "WorkspaceManager",
    "WorkspaceConfig",
    "Workspace",
    "WorkspaceType",
    "WorkspaceStatus",
    "WorkspaceTemplate",
    "WorkspaceIsolation",
    "WorkspaceSnapshot",
    # Polyglot AST Driver
    "PolyglotASTDriver",
    "ASTParser",
    "ASTNode",
    "ParseResult",
    "Language",
    "ASTTransformer",
    "ASTIndexer",
    "TreeSitterManager",
    "TreeSitterConfig",
    "TREE_SITTER_AVAILABLE",
    # Function Mutator
    "FunctionMutator",
    "MutationTester",
    "EvolutionaryMutator",
    "Mutation",
    "MutationResult",
    "MutationType",
    # Workspace Synchronizer
    "WorkspaceSynchronizer",
    "WorkspaceReplicator",
    "SyncScheduler",
    "ConflictResolver",
    "WorkspaceConflictResolver",
    "SyncConfig",
    "SyncMode",
    "ConflictStrategy",
    "FileInfo",
    "SyncResult",
    "WorkspaceSyncResult",
]
