"""
Egress Proxy - Network egress control and monitoring
"""
import socket
import threading
import time
import json
from typing import Dict, List, Optional, Any, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from urllib.parse import urlparse
import ipaddress


class EgressAction(Enum):
    ALLOW = "allow"
    BLOCK = "block"
    LOG = "log"
    REDIRECT = "redirect"
    REQUIRE_APPROVAL = "require_approval"


class Protocol(Enum):
    HTTP = "http"
    HTTPS = "https"
    TCP = "tcp"
    UDP = "udp"
    DNS = "dns"
    SSH = "ssh"
    FTP = "ftp"


@dataclass
class EgressRule:
    rule_id: str
    name: str
    protocols: Set[Protocol]
    destinations: List[str]
    ports: List[int]
    action: EgressAction
    priority: int = 0
    redirect_to: Optional[str] = None
    requires_approval_from: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def matches(self, protocol: Protocol, destination: str, port: int) -> bool:
        if not self.enabled:
            return False
        if protocol not in self.protocols:
            return False
        if self.destinations and not self._match_destination(destination):
            return False
        if self.ports and port not in self.ports:
            return False
        return True

    def _match_destination(self, destination: str) -> bool:
        for pattern in self.destinations:
            if pattern == "*":
                return True
            if pattern.startswith("*."):
                if destination.endswith(pattern[1:]):
                    return True
            elif pattern == destination:
                return True
            try:
                if ipaddress.ip_address(destination) in ipaddress.ip_network(pattern, strict=False):
                    return True
            except ValueError:
                pass
        return False


@dataclass
class EgressRequest:
    request_id: str
    actor_id: str
    session_id: str
    protocol: Protocol
    destination: str
    port: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class EgressDecision:
    request: EgressRequest
    action: EgressAction
    matched_rules: List[EgressRule]
    redirect_to: Optional[str] = None
    approved_by: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


class ApprovalHandler:
    def __init__(self):
        self.handlers: Dict[str, Callable] = {}

    def register(self, name: str, handler: Callable):
        self.handlers[name] = handler

    def request(self, handler_name: str, request: EgressRequest, rules: List[EgressRule]) -> EgressAction:
        if handler_name in self.handlers:
            return self.handlers[handler_name](request, rules)
        return EgressAction.BLOCK


class EgressLogger:
    def __init__(self, log_path: Optional[str] = None):
        self.log_path = log_path
        self.records: List[EgressDecision] = []
        self._lock = threading.Lock()

    def log(self, decision: EgressDecision):
        with self._lock:
            self.records.append(decision)
            if self.log_path:
                self._write_to_file(decision)

    def _write_to_file(self, decision: EgressDecision):
        try:
            with open(self.log_path, 'a') as f:
                f.write(json.dumps({
                    "timestamp": decision.timestamp,
                    "request_id": decision.request.request_id,
                    "actor_id": decision.request.actor_id,
                    "session_id": decision.request.session_id,
                    "protocol": decision.request.protocol.value,
                    "destination": decision.request.destination,
                    "port": decision.request.port,
                    "action": decision.action.value,
                    "matched_rules": [r.rule_id for r in decision.matched_rules],
                    "redirect_to": decision.redirect_to,
                    "approved_by": decision.approved_by,
                }) + '\n')
        except Exception:
            pass

    def get_recent(self, limit: int = 100) -> List[EgressDecision]:
        with self._lock:
            return self.records[-limit:]


class MetricsCollector:
    def __init__(self):
        self.counters = defaultdict(int)
        self._lock = threading.Lock()

    def increment(self, key: str, value: int = 1):
        with self._lock:
            self.counters[key] += value

    def get_all(self) -> Dict[str, int]:
        with self._lock:
            return dict(self.counters)


class EgressProxy:
    def __init__(
        self,
        approval_handler: Optional[ApprovalHandler] = None,
        log_path: Optional[str] = None,
        default_action: EgressAction = EgressAction.BLOCK,
    ):
        self.rules: List[EgressRule] = []
        self.approval_handler = approval_handler or ApprovalHandler()
        self.logger = EgressLogger(log_path)
        self.metrics = MetricsCollector()
        self.default_action = default_action
        self._lock = threading.RLock()
        self._initialize_default_rules()

    def _initialize_default_rules(self):
        self.add_rule(EgressRule(
            rule_id="default-dns",
            name="Allow DNS",
            protocols={Protocol.DNS},
            destinations=["*"],
            ports=[53],
            action=EgressAction.ALLOW,
            priority=-100,
        ))
        
        self.add_rule(EgressRule(
            rule_id="default-https",
            name="Allow HTTPS to trusted",
            protocols={Protocol.HTTPS},
            destinations=["api.github.com", "pypi.org", "registry.npmjs.org"],
            ports=[443],
            action=EgressAction.ALLOW,
            priority=-50,
        ))
        
        self.add_rule(EgressRule(
            rule_id="default-http",
            name="Allow HTTP to localhost",
            protocols={Protocol.HTTP},
            destinations=["localhost", "127.0.0.1"],
            ports=[80, 8080, 8000],
            action=EgressAction.ALLOW,
            priority=-50,
        ))

    def add_rule(self, rule: EgressRule):
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

    def check(self, request: EgressRequest) -> EgressDecision:
        matched_rules = []
        with self._lock:
            for rule in self.rules:
                if rule.matches(request.protocol, request.destination, request.port):
                    matched_rules.append(rule)

        if not matched_rules:
            action = self.default_action
        else:
            highest_priority = max(r.priority for r in matched_rules)
            top_rules = [r for r in matched_rules if r.priority == highest_priority]
            actions = [r.action for r in top_rules]
            
            if EgressAction.BLOCK in actions:
                action = EgressAction.BLOCK
            elif EgressAction.REQUIRE_APPROVAL in actions:
                action = EgressAction.REQUIRE_APPROVAL
            elif EgressAction.REDIRECT in actions:
                action = EgressAction.REDIRECT
            elif EgressAction.LOG in actions:
                action = EgressAction.LOG
            else:
                action = EgressAction.ALLOW

        redirect_to = None
        approved_by = None
        
        if action == EgressAction.REQUIRE_APPROVAL:
            approvers = set()
            for r in matched_rules:
                if r.action == EgressAction.REQUIRE_APPROVAL:
                    approvers.update(r.requires_approval_from)
            
            if approvers:
                for approver in approvers:
                    action = self.approval_handler.request(approver, request, matched_rules)
                    if action == EgressAction.ALLOW:
                        approved_by = approver
                        break
        
        if action == EgressAction.REDIRECT:
            for r in matched_rules:
                if r.action == EgressAction.REDIRECT and r.redirect_to:
                    redirect_to = r.redirect_to
                    break

        decision = EgressDecision(
            request=request,
            action=action,
            matched_rules=matched_rules,
            redirect_to=redirect_to,
            approved_by=approved_by,
        )
        
        self.logger.log(decision)
        self.metrics.increment(f"action.{action.value}")
        self.metrics.increment("total_requests")
        
        return decision

    def authorize(
        self,
        actor_id: str,
        session_id: str,
        protocol: Protocol,
        destination: str,
        port: int,
        **metadata
    ) -> EgressDecision:
        request = EgressRequest(
            request_id=f"egress-{int(time.time()*1000)}",
            actor_id=actor_id,
            session_id=session_id,
            protocol=protocol,
            destination=destination,
            port=port,
            metadata=metadata,
        )
        return self.check(request)

    def is_allowed(self, actor_id: str, session_id: str, protocol: Protocol, destination: str, port: int) -> bool:
        decision = self.authorize(actor_id, session_id, protocol, destination, port)
        return decision.action == EgressAction.ALLOW

    def get_rules(self) -> List[EgressRule]:
        with self._lock:
            return list(self.rules)

    def get_logs(self, limit: int = 100) -> List[EgressDecision]:
        return self.logger.get_recent(limit)

    def get_metrics(self) -> Dict[str, int]:
        return self.metrics.get_all()


class SocketInterceptor:
    def __init__(self, proxy: EgressProxy):
        self.proxy = proxy
        self.original_socket = socket.socket
        self._patched = False

    def patch(self):
        if self._patched:
            return
        
        original_connect = socket.socket.connect
        original_connect_ex = socket.socket.connect_ex
        
        def patched_connect(self_sock, address):
            host, port = address[0], address[1]
            decision = self.proxy.authorize(
                actor_id="system",
                session_id="socket",
                protocol=Protocol.TCP,
                destination=host,
                port=port,
            )
            if decision.action != EgressAction.ALLOW:
                raise PermissionError(f"Egress blocked: {host}:{port}")
            return original_connect(self_sock, address)
        
        def patched_connect_ex(self_sock, address):
            host, port = address[0], address[1]
            decision = self.proxy.authorize(
                actor_id="system",
                session_id="socket",
                protocol=Protocol.TCP,
                destination=host,
                port=port,
            )
            if decision.action != EgressAction.ALLOW:
                return 13  # EACCES
            return original_connect_ex(self_sock, address)
        
        socket.socket.connect = patched_connect
        socket.socket.connect_ex = patched_connect_ex
        self._patched = True

    def unpatch(self):
        if not self._patched:
            return
        # Note: In practice, you'd need to store originals properly
        self._patched = False