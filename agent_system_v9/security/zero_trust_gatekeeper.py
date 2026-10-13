"""
Zero-Trust Gatekeeper - Continuous security policy enforcement
"""
import hashlib
import time
import threading
from typing import Dict, List, Optional, Any, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
from collections import defaultdict
import json


class PolicyDecision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    QUARANTINE = "quarantine"


class ResourceType(Enum):
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    NETWORK_OUTBOUND = "network_outbound"
    NETWORK_INBOUND = "network_inbound"
    PROCESS_EXEC = "process_exec"
    ENV_VAR_ACCESS = "env_var_access"
    SECRET_ACCESS = "secret_access"
    SYSTEM_CALL = "system_call"


@dataclass
class ExecutionContext:
    actor_id: str
    session_id: str
    resource_type: ResourceType
    resource_path: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    caller_stack: List[str] = field(default_factory=list)
    trust_score: float = 1.0


@dataclass
class PolicyRule:
    rule_id: str
    name: str
    resource_types: Set[ResourceType]
    conditions: Dict[str, Any]
    decision: PolicyDecision
    priority: int = 0
    requires_approval_from: List[str] = field(default_factory=list)
    expires_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def matches(self, context: ExecutionContext) -> bool:
        if context.resource_type not in self.resource_types:
            return False
        for key, expected in self.conditions.items():
            actual = context.metadata.get(key)
            if actual != expected:
                return False
        if self.expires_at and time.time() > self.expires_at:
            return False
        return True


@dataclass
class PolicyDecisionRecord:
    context: ExecutionContext
    decision: PolicyDecision
    matched_rules: List[PolicyRule]
    approved_by: Optional[str] = None
    approval_timestamp: Optional[float] = None
    timestamp: float = field(default_factory=time.time)


class ApprovalCallback(ABC):
    @abstractmethod
    def request_approval(self, context: ExecutionContext, rules: List[PolicyRule]) -> PolicyDecision:
        pass


class DefaultApprovalCallback(ApprovalCallback):
    def __init__(self, auto_approve: bool = False):
        self.auto_approve = auto_approve
        self.pending_approvals: Dict[str, PolicyDecision] = {}

    def request_approval(self, context: ExecutionContext, rules: List[PolicyRule]) -> PolicyDecision:
        if self.auto_approve:
            return PolicyDecision.ALLOW
        return PolicyDecision.DENY


class AuditLogger:
    def __init__(self, log_path: Optional[str] = None):
        self.log_path = log_path
        self.records: List[PolicyDecisionRecord] = []
        self._lock = threading.Lock()

    def log(self, record: PolicyDecisionRecord):
        with self._lock:
            self.records.append(record)
            if self.log_path:
                self._write_to_file(record)

    def _write_to_file(self, record: PolicyDecisionRecord):
        try:
            with open(self.log_path, 'a') as f:
                f.write(json.dumps({
                    "timestamp": record.timestamp,
                    "actor_id": record.context.actor_id,
                    "session_id": record.context.session_id,
                    "resource_type": record.context.resource_type.value,
                    "resource_path": record.context.resource_path,
                    "decision": record.decision.value,
                    "matched_rules": [r.rule_id for r in record.matched_rules],
                    "approved_by": record.approved_by,
                }) + '\n')
        except Exception:
            pass

    def get_recent(self, limit: int = 100) -> List[PolicyDecisionRecord]:
        with self._lock:
            return self.records[-limit:]


class MetricsCollector:
    def __init__(self):
        self.counters = defaultdict(int)
        self._lock = threading.Lock()

    def increment(self, key: str, value: int = 1):
        with self._lock:
            self.counters[key] += value

    def get(self, key: str) -> int:
        with self._lock:
            return self.counters.get(key, 0)

    def get_all(self) -> Dict[str, int]:
        with self._lock:
            return dict(self.counters)


class PolicyBuilder:
    def __init__(self, gatekeeper: 'ZeroTrustGatekeeper'):
        self.gatekeeper = gatekeeper
        self.current_rule: Optional[PolicyRule] = None

    def new_rule(self, rule_id: str, name: str) -> 'PolicyBuilder':
        self.current_rule = PolicyRule(
            rule_id=rule_id,
            name=name,
            resource_types=set(),
            conditions={},
            decision=PolicyDecision.ALLOW,
        )
        return self

    def for_resources(self, *resource_types: ResourceType) -> 'PolicyBuilder':
        if self.current_rule:
            self.current_rule.resource_types.update(resource_types)
        return self

    def when(self, **conditions) -> 'PolicyBuilder':
        if self.current_rule:
            self.current_rule.conditions.update(conditions)
        return self

    def allow(self) -> 'PolicyBuilder':
        if self.current_rule:
            self.current_rule.decision = PolicyDecision.ALLOW
        return self

    def deny(self) -> 'PolicyBuilder':
        if self.current_rule:
            self.current_rule.decision = PolicyDecision.DENY
        return self

    def require_approval(self, approvers: List[str] = None) -> 'PolicyBuilder':
        if self.current_rule:
            self.current_rule.decision = PolicyDecision.REQUIRE_APPROVAL
            self.current_rule.requires_approval_from = approvers or []
        return self

    def quarantine(self) -> 'PolicyBuilder':
        if self.current_rule:
            self.current_rule.decision = PolicyDecision.QUARANTINE
        return self

    def with_priority(self, priority: int) -> 'PolicyBuilder':
        if self.current_rule:
            self.current_rule.priority = priority
        return self

    def expires_in(self, seconds: float) -> 'PolicyBuilder':
        if self.current_rule:
            self.current_rule.expires_at = time.time() + seconds
        return self

    def build(self) -> PolicyRule:
        if not self.current_rule:
            raise ValueError("No rule in progress")
        rule = self.current_rule
        self.current_rule = None
        self.gatekeeper.add_rule(rule)
        return rule


class ZeroTrustGatekeeper:
    def __init__(
        self,
        approval_callback: Optional[ApprovalCallback] = None,
        audit_log_path: Optional[str] = None,
        default_decision: PolicyDecision = PolicyDecision.DENY,
    ):
        self.rules: List[PolicyRule] = []
        self.approval_callback = approval_callback or DefaultApprovalCallback()
        self.audit_logger = AuditLogger(audit_log_path)
        self.metrics = MetricsCollector()
        self.default_decision = default_decision
        self._lock = threading.RLock()
        self._initialize_default_policies()

    def _initialize_default_policies(self):
        builder = PolicyBuilder(self)
        
        builder.new_rule("default-file-read", "Default File Read") \
            .for_resources(ResourceType.FILE_READ) \
            .allow() \
            .with_priority(-100) \
            .build()
        
        builder.new_rule("default-file-write", "Default File Write") \
            .for_resources(ResourceType.FILE_WRITE) \
            .require_approval() \
            .with_priority(-100) \
            .build()
        
        builder.new_rule("default-network-outbound", "Default Network Outbound") \
            .for_resources(ResourceType.NETWORK_OUTBOUND) \
            .require_approval() \
            .with_priority(-100) \
            .build()
        
        builder.new_rule("default-process-exec", "Default Process Execution") \
            .for_resources(ResourceType.PROCESS_EXEC) \
            .deny() \
            .with_priority(-100) \
            .build()
        
        builder.new_rule("default-secret-access", "Default Secret Access") \
            .for_resources(ResourceType.SECRET_ACCESS) \
            .deny() \
            .with_priority(-100) \
            .build()

    def add_rule(self, rule: PolicyRule):
        with self._lock:
            self.rules.append(rule)
            self.rules.sort(key=lambda r: -r.priority)

    def remove_rule(self, rule_id: str) -> bool:
        with self._lock:
            for i, rule in enumerate(self.rules):
                if rule.rule_id == rule_id:
                    self.rules.pop(i)
                    return True
        return False

    def check(self, context: ExecutionContext) -> PolicyDecisionRecord:
        matched_rules = []
        with self._lock:
            for rule in self.rules:
                if rule.matches(context):
                    matched_rules.append(rule)

        if not matched_rules:
            decision = self.default_decision
        else:
            highest_priority = max(r.priority for r in matched_rules)
            top_rules = [r for r in matched_rules if r.priority == highest_priority]
            decisions = [r.decision for r in top_rules]
            
            if PolicyDecision.DENY in decisions:
                decision = PolicyDecision.DENY
            elif PolicyDecision.QUARANTINE in decisions:
                decision = PolicyDecision.QUARANTINE
            elif PolicyDecision.REQUIRE_APPROVAL in decisions:
                decision = PolicyDecision.REQUIRE_APPROVAL
            else:
                decision = PolicyDecision.ALLOW

        if decision == PolicyDecision.REQUIRE_APPROVAL:
            approvers = set()
            for r in matched_rules:
                if r.decision == PolicyDecision.REQUIRE_APPROVAL:
                    approvers.update(r.requires_approval_from)
            
            if approvers:
                decision = self.approval_callback.request_approval(context, matched_rules)

        record = PolicyDecisionRecord(
            context=context,
            decision=decision,
            matched_rules=matched_rules,
        )
        
        self.audit_logger.log(record)
        self.metrics.increment(f"decision.{decision.value}")
        self.metrics.increment("total_checks")
        
        return record

    def authorize(
        self,
        actor_id: str,
        session_id: str,
        resource_type: ResourceType,
        resource_path: str,
        **metadata
    ) -> bool:
        context = ExecutionContext(
            actor_id=actor_id,
            session_id=session_id,
            resource_type=resource_type,
            resource_path=resource_path,
            metadata=metadata,
        )
        record = self.check(context)
        return record.decision == PolicyDecision.ALLOW

    def get_policy_builder(self) -> PolicyBuilder:
        return PolicyBuilder(self)

    def get_audit_log(self, limit: int = 100) -> List[PolicyDecisionRecord]:
        return self.audit_logger.get_recent(limit)

    def get_metrics(self) -> Dict[str, int]:
        return self.metrics.get_all()

    def list_rules(self) -> List[PolicyRule]:
        with self._lock:
            return list(self.rules)