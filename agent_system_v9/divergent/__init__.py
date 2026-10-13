"""
Divergent Evolution & Self-Healing Engine (Section 06)
Worktree-Isolated Divergent Execution, AST Node-Merging Engine, Sub-1B Failure-Trace ICRL Evaluator,
Pre-Destruction State Serializer, Append-Only Transaction Journaling, Secure Memory Space Partitioning
"""
from .divergent_execution import DivergentExecutor, WorktreeConfig, ExecutionResult
from .ast_merger import ASTNodeMerger, MergeResult, MergeStrategy
from .failure_evaluator import FailureTraceEvaluator, ICRLWeights
from .state_serializer import StateSerializer, SerializedState
from .transaction_journal import TransactionJournal, JournalEntry
from .memory_partition import MemoryPartition, PartitionConfig

__all__ = [
    "DivergentExecutor",
    "WorktreeConfig",
    "ExecutionResult",
    "ASTNodeMerger",
    "MergeResult",
    "MergeStrategy",
    "FailureTraceEvaluator",
    "ICRLWeights",
    "StateSerializer",
    "SerializedState",
    "TransactionJournal",
    "JournalEntry",
    "MemoryPartition",
    "PartitionConfig",
]