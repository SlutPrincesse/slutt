import asyncio
import hashlib
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from collections import OrderedDict


class HeadType(Enum):
    LOCAL = "local"
    GLOBAL = "global"
    TASK = "task"
    MEMORY = "memory"
    TOOL = "tool"
    CROSS_REFERENCE = "cross_reference"


@dataclass
class AttentionHead:
    id: str
    head_type: HeadType
    weight: float = 1.0
    focus_tokens: List[int] = field(default_factory=list)
    context_window: int = 4096
    metadata: Dict[str, Any] = field(default_factory=dict)
    active: bool = True

    def __post_init__(self):
        if not self.id:
            self.id = hashlib.sha256(f"{self.head_type.value}:{datetime.utcnow().isoformat()}".encode()).hexdigest()[:12]


class AttentionAllocator:
    def __init__(self, max_heads: int = 8, total_context: int = 128000):
        self.max_heads = max_heads
        self.total_context = total_context
        self.heads: Dict[str, AttentionHead] = {}
        self._head_order: List[str] = []
        self._allocated_tokens = 0

    def allocate(self, head_type: HeadType, weight: float = 1.0, context_window: int = None) -> AttentionHead:
        if len(self.heads) >= self.max_heads:
            self._evict_lowest_priority()
        
        window = context_window or min(4096, self.total_context // self.max_heads)
        head = AttentionHead(
            id="",
            head_type=head_type,
            weight=weight,
            context_window=window,
        )
        
        self.heads[head.id] = head
        self._head_order.append(head.id)
        self._allocated_tokens += window
        return head

    def _evict_lowest_priority(self):
        if not self._head_order:
            return
        lowest = min(self._head_order, key=lambda h: self.heads[h].weight)
        head = self.heads.pop(lowest)
        self._head_order.remove(lowest)
        self._allocated_tokens -= head.context_window

    def get_head(self, head_id: str) -> Optional[AttentionHead]:
        return self.heads.get(head_id)

    def get_heads_by_type(self, head_type: HeadType) -> List[AttentionHead]:
        return [h for h in self.heads.values() if h.head_type == head_type]

    def update_weight(self, head_id: str, weight: float):
        if head_id in self.heads:
            self.heads[head_id].weight = weight

    def update_focus(self, head_id: str, tokens: List[int]):
        if head_id in self.heads:
            self.heads[head_id].focus_tokens = tokens

    def deallocate(self, head_id: str) -> bool:
        if head_id in self.heads:
            head = self.heads.pop(head_id)
            self._head_order.remove(head_id)
            self._allocated_tokens -= head.context_window
            return True
        return False

    def get_allocation_summary(self) -> Dict[str, Any]:
        return {
            "total_heads": len(self.heads),
            "max_heads": self.max_heads,
            "allocated_tokens": self._allocated_tokens,
            "total_context": self.total_context,
            "utilization": self._allocated_tokens / self.total_context,
            "by_type": {ht.value: len(self.get_heads_by_type(ht)) for ht in HeadType},
        }

    def rebalance(self):
        if not self.heads:
            return
        total_weight = sum(h.weight for h in self.heads.values())
        if total_weight == 0:
            return
        
        for head in self.heads.values():
            new_window = int((head.weight / total_weight) * self.total_context)
            head.context_window = max(512, min(new_window, 8192))