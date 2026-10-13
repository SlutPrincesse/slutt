import asyncio
import uuid
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class IsolationLevel(Enum):
    NONE = "none"
    TASK = "task"
    SESSION = "session"
    USER = "user"
    PROJECT = "project"
    SECURE = "secure"


@dataclass
class IsolationBoundary:
    id: str
    name: str
    level: IsolationLevel
    allowed_contexts: Set[str] = field(default_factory=set)
    denied_contexts: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:12]

    def allows(self, context_id: str) -> bool:
        if self.level == IsolationLevel.NONE:
            return True
        if self.level == IsolationLevel.SECURE:
            return context_id in self.allowed_contexts
        return context_id not in self.denied_contexts


class ContextIsolationLayer:
    def __init__(self):
        self.boundaries: Dict[str, IsolationBoundary] = {}
        self.context_boundaries: Dict[str, Set[str]] = {}
        self.default_level = IsolationLevel.TASK

    def create_boundary(
        self,
        name: str,
        level: IsolationLevel = IsolationLevel.TASK,
        allowed: List[str] = None,
        denied: List[str] = None,
    ) -> IsolationBoundary:
        boundary = IsolationBoundary(
            id="",
            name=name,
            level=level,
            allowed_contexts=set(allowed or []),
            denied_contexts=set(denied or []),
        )
        self.boundaries[boundary.id] = boundary
        return boundary

    def assign_context(self, context_id: str, boundary_ids: List[str]):
        self.context_boundaries[context_id] = set(boundary_ids)

    def can_access(self, source_context: str, target_context: str) -> bool:
        source_boundaries = self.context_boundaries.get(source_context, set())
        if not source_boundaries:
            return True
        
        for boundary_id in source_boundaries:
            boundary = self.boundaries.get(boundary_id)
            if boundary and not boundary.allows(target_context):
                return False
        return True

    def get_isolated_context(self, context_id: str, all_contexts: List[str]) -> List[str]:
        return [ctx for ctx in all_contexts if self.can_access(context_id, ctx)]

    def merge_contexts(self, context_ids: List[str], new_boundary_name: str) -> IsolationBoundary:
        allowed = set()
        for cid in context_ids:
            allowed.add(cid)
            bounds = self.context_boundaries.get(cid, set())
            for bid in bounds:
                boundary = self.boundaries.get(bid)
                if boundary:
                    allowed.update(boundary.allowed_contexts)
        
        boundary = self.create_boundary(
            name=new_boundary_name,
            level=IsolationLevel.SESSION,
            allowed=list(allowed),
        )
        
        for cid in context_ids:
            self.assign_context(cid, [boundary.id])
        
        return boundary

    def remove_boundary(self, boundary_id: str) -> bool:
        if boundary_id in self.boundaries:
            for context_id, bounds in self.context_boundaries.items():
                bounds.discard(boundary_id)
            del self.boundaries[boundary_id]
            return True
        return False

    def get_boundary(self, boundary_id: str) -> Optional[IsolationBoundary]:
        return self.boundaries.get(boundary_id)

    def list_boundaries(self) -> List[IsolationBoundary]:
        return list(self.boundaries.values())

    def get_context_boundaries(self, context_id: str) -> List[IsolationBoundary]:
        boundary_ids = self.context_boundaries.get(context_id, set())
        return [self.boundaries[bid] for bid in boundary_ids if bid in self.boundaries]