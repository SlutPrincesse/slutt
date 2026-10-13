"""
Dynamic Token Budget Allocator - Allocates tokens across context, memory, tools, and response buffers
"""
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BudgetCategory(Enum):
    CONTEXT = "context"
    MEMORY = "memory"
    TOOLS = "tools"
    RESPONSE = "response"
    SYSTEM = "system"
    OVERHEAD = "overhead"


class AllocationStrategy(Enum):
    PROPORTIONAL = "proportional"
    PRIORITY = "priority"
    ADAPTIVE = "adaptive"
    FIXED = "fixed"


@dataclass
class BudgetAllocation:
    category: BudgetCategory
    allocated: int
    used: int = 0
    reserved: int = 0
    priority: int = 50
    min_allocation: int = 0
    max_allocation: int = 0
    strategy: AllocationStrategy = AllocationStrategy.PROPORTIONAL
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenBudget:
    total_budget: int
    allocations: dict[BudgetCategory, BudgetAllocation] = field(default_factory=dict)
    strategy: AllocationStrategy = AllocationStrategy.ADAPTIVE
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class DynamicTokenBudgetAllocator:
    DEFAULT_ALLOCATIONS = {
        BudgetCategory.CONTEXT: BudgetAllocation(
            category=BudgetCategory.CONTEXT,
            allocated=0,
            priority=90,
            min_allocation=1000,
            max_allocation=50000,
            strategy=AllocationStrategy.ADAPTIVE
        ),
        BudgetCategory.MEMORY: BudgetAllocation(
            category=BudgetCategory.MEMORY,
            allocated=0,
            priority=70,
            min_allocation=500,
            max_allocation=20000,
            strategy=AllocationStrategy.PROPORTIONAL
        ),
        BudgetCategory.TOOLS: BudgetAllocation(
            category=BudgetCategory.TOOLS,
            allocated=0,
            priority=80,
            min_allocation=1000,
            max_allocation=15000,
            strategy=AllocationStrategy.PRIORITY
        ),
        BudgetCategory.RESPONSE: BudgetAllocation(
            category=BudgetCategory.RESPONSE,
            allocated=0,
            priority=95,
            min_allocation=2000,
            max_allocation=30000,
            strategy=AllocationStrategy.ADAPTIVE
        ),
        BudgetCategory.SYSTEM: BudgetAllocation(
            category=BudgetCategory.SYSTEM,
            allocated=0,
            priority=100,
            min_allocation=500,
            max_allocation=5000,
            strategy=AllocationStrategy.FIXED
        ),
        BudgetCategory.OVERHEAD: BudgetAllocation(
            category=BudgetCategory.OVERHEAD,
            allocated=0,
            priority=10,
            min_allocation=100,
            max_allocation=2000,
            strategy=AllocationStrategy.FIXED
        ),
    }

    def __init__(self, default_total_budget: int = 100000):
        self.default_total_budget = default_total_budget
        self._budgets: dict[str, TokenBudget] = {}
        self._lock = threading.RLock()
        self._usage_history: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._adaptation_enabled = True
        self._min_response_tokens = 2000

    def create_budget(self, budget_id: str, total_budget: int = None,
                      custom_allocations: dict[BudgetCategory, BudgetAllocation] = None) -> TokenBudget:
        total = total_budget or self.default_total_budget

        allocations = {}
        for cat, default_alloc in self.DEFAULT_ALLOCATIONS.items():
            if custom_allocations and cat in custom_allocations:
                alloc = custom_allocations[cat]
                alloc = BudgetAllocation(
                    category=cat,
                    allocated=0,
                    priority=alloc.priority,
                    min_allocation=alloc.min_allocation,
                    max_allocation=alloc.max_allocation,
                    strategy=alloc.strategy,
                    metadata=alloc.metadata.copy()
                )
            else:
                alloc = BudgetAllocation(
                    category=cat,
                    allocated=0,
                    priority=default_alloc.priority,
                    min_allocation=default_alloc.min_allocation,
                    max_allocation=default_alloc.max_allocation,
                    strategy=default_alloc.strategy,
                    metadata=default_alloc.metadata.copy()
                )
            allocations[cat] = alloc

        budget = TokenBudget(
            total_budget=total,
            allocations=allocations,
            strategy=AllocationStrategy.ADAPTIVE
        )

        self._allocate(budget)

        with self._lock:
            self._budgets[budget_id] = budget

        return budget

    def _allocate(self, budget: TokenBudget):
        total = budget.total_budget
        allocations = budget.allocations

        # First pass: satisfy minimums
        remaining = total
        for cat, alloc in allocations.items():
            min_alloc = min(alloc.min_allocation, remaining)
            alloc.allocated = min_alloc
            remaining -= min_alloc

        if remaining <= 0:
            return

        # Second pass: allocate based on strategy
        if budget.strategy == AllocationStrategy.PROPORTIONAL:
            self._allocate_proportional(allocations, remaining)
        elif budget.strategy == AllocationStrategy.PRIORITY:
            self._allocate_priority(allocations, remaining)
        elif budget.strategy == AllocationStrategy.ADAPTIVE:
            self._allocate_adaptive(budget, remaining)
        elif budget.strategy == AllocationStrategy.FIXED:
            self._allocate_fixed(allocations, remaining)

    def _allocate_proportional(self, allocations: dict[BudgetCategory, BudgetAllocation], remaining: int):
        # Distribute by priority weights
        total_priority = sum(a.priority for a in allocations.values() if a.allocated < a.max_allocation)
        if total_priority == 0:
            return

        for cat, alloc in allocations.items():
            if alloc.allocated >= alloc.max_allocation:
                continue

            share = int(remaining * alloc.priority / total_priority)
            available = alloc.max_allocation - alloc.allocated
            alloc.allocated += min(share, available)

    def _allocate_priority(self, allocations: dict[BudgetCategory, BudgetAllocation], remaining: int):
        # Allocate to highest priority first
        sorted_cats = sorted(allocations.items(), key=lambda x: -x[1].priority)

        for cat, alloc in sorted_cats:
            if remaining <= 0:
                break
            if alloc.allocated >= alloc.max_allocation:
                continue

            needed = alloc.max_allocation - alloc.allocated
            give = min(needed, remaining)
            alloc.allocated += give
            remaining -= give

    def _allocate_adaptive(self, budget: TokenBudget, remaining: int):
        budget_id = id(budget)
        history = self._usage_history.get(str(budget_id), [])

        if not history:
            # No history, use proportional
            self._allocate_proportional(budget.allocations, remaining)
            return

        # Analyze usage patterns
        avg_usage = defaultdict(float)
        for record in history[-10:]:  # Last 10 records
            for cat, usage in record.items():
                avg_usage[cat] += usage

        for cat in avg_usage:
            avg_usage[cat] /= min(len(history), 10)

        # Allocate based on predicted usage + buffer
        for cat, alloc in budget.allocations.items():
            if alloc.allocated >= alloc.max_allocation:
                continue

            predicted = avg_usage.get(cat, 0)
            buffer = predicted * 0.2  # 20% buffer
            target = int(predicted + buffer)
            target = max(alloc.min_allocation, min(target, alloc.max_allocation))

            if target > alloc.allocated:
                give = min(target - alloc.allocated, remaining)
                alloc.allocated += give
                remaining -= give

        # Distribute any remaining
        if remaining > 0:
            self._allocate_proportional(budget.allocations, remaining)

    def _allocate_fixed(self, allocations: dict[BudgetCategory, BudgetAllocation], remaining: int):
        # Fixed allocations don't change after minimums
        pass

    def get_budget(self, budget_id: str) -> TokenBudget | None:
        with self._lock:
            return self._budgets.get(budget_id)

    def get_allocation(self, budget_id: str, category: BudgetCategory) -> BudgetAllocation | None:
        budget = self.get_budget(budget_id)
        if budget:
            return budget.allocations.get(category)
        return None

    def reserve(self, budget_id: str, category: BudgetCategory, tokens: int) -> bool:
        with self._lock:
            budget = self._budgets.get(budget_id)
            if not budget:
                return False

            alloc = budget.allocations.get(category)
            if not alloc:
                return False

            available = alloc.allocated - alloc.used - alloc.reserved
            if available >= tokens:
                alloc.reserved += tokens
                return False
        return False

    def use(self, budget_id: str, category: BudgetCategory, tokens: int) -> bool:
        with self._lock:
            budget = self._budgets.get(budget_id)
            if not budget:
                return False

            alloc = budget.allocations.get(category)
            if not alloc:
                return False

            available = alloc.allocated - alloc.used
            if available >= tokens:
                alloc.used += tokens
                alloc.reserved = max(0, alloc.reserved - tokens)
                return True
        return False

    def release(self, budget_id: str, category: BudgetCategory, tokens: int) -> bool:
        with self._lock:
            budget = self._budgets.get(budget_id)
            if not budget:
                return False

            alloc = budget.allocations.get(category)
            if not alloc:
                return False

            alloc.used = max(0, alloc.used - tokens)
            return True

    def record_usage(self, budget_id: str, usage: dict[BudgetCategory, int]):
        with self._lock:
            self._usage_history[budget_id].append({cat.value: used for cat, used in usage.items()})
            # Keep last 100 records
            if len(self._usage_history[budget_id]) > 100:
                self._usage_history[budget_id] = self._usage_history[budget_id][-100:]

    def rebalance(self, budget_id: str) -> bool:
        with self._lock:
            budget = self._budgets.get(budget_id)
            if not budget:
                return False

        # Reset used/reserved for rebalancing
        for alloc in budget.allocations.values():
            alloc.used = 0
            alloc.reserved = 0

        self._allocate(budget)
        budget.updated_at = time.time()
        return True

    def get_available(self, budget_id: str, category: BudgetCategory) -> int:
        alloc = self.get_allocation(budget_id, category)
        if not alloc:
            return 0
        return max(0, alloc.allocated - alloc.used - alloc.reserved)

    def get_usage_stats(self, budget_id: str) -> dict[str, Any]:
        budget = self.get_budget(budget_id)
        if not budget:
            return {}

        stats = {
            "total_budget": budget.total_budget,
            "total_allocated": sum(a.allocated for a in budget.allocations.values()),
            "total_used": sum(a.used for a in budget.allocations.values()),
            "total_reserved": sum(a.reserved for a in budget.allocations.values()),
            "by_category": {}
        }

        for cat, alloc in budget.allocations.items():
            stats["by_category"][cat.value] = {
                "allocated": alloc.allocated,
                "used": alloc.used,
                "reserved": alloc.reserved,
                "available": max(0, alloc.allocated - alloc.used - alloc.reserved),
                "utilization": alloc.used / alloc.allocated if alloc.allocated > 0 else 0,
                "priority": alloc.priority,
                "strategy": alloc.strategy.value
            }

        return stats

    def estimate_response_budget(self, budget_id: str, context_tokens: int,
                                memory_tokens: int, tool_tokens: int) -> int:
        budget = self.get_budget(budget_id)
        if not budget:
            return self._min_response_tokens

        # Calculate remaining for response
        used = context_tokens + memory_tokens + tool_tokens
        system_alloc = budget.allocations[BudgetCategory.SYSTEM].allocated
        overhead_alloc = budget.allocations[BudgetCategory.OVERHEAD].allocated

        remaining = budget.total_budget - used - system_alloc - overhead_alloc
        response_min = budget.allocations[BudgetCategory.RESPONSE].min_allocation
        response_max = budget.allocations[BudgetCategory.RESPONSE].max_allocation

        return max(response_min, min(response_max, remaining))

    def set_adaptation_enabled(self, enabled: bool):
        self._adaptation_enabled = enabled

    def delete_budget(self, budget_id: str) -> bool:
        with self._lock:
            if budget_id in self._budgets:
                del self._budgets[budget_id]
                self._usage_history.pop(budget_id, None)
                return True
        return False


_budget_allocator: DynamicTokenBudgetAllocator | None = None


def get_budget_allocator() -> DynamicTokenBudgetAllocator:
    global _budget_allocator
    if _budget_allocator is None:
        from ..core.config import config
        max_budget = config.get_param("prompt", "max_token_budget", 100000)
        _budget_allocator = DynamicTokenBudgetAllocator(default_total_budget=max_budget)
    return _budget_allocator
