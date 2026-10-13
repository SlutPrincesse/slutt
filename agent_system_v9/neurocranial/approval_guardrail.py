"""
Approval Modal Guardrail - Non-blocking visual confirmation before tool plans commit to global registry
"""
import threading
import time
import uuid
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import deque


class ApprovalState(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    AUTO_APPROVED = "auto_approved"


class ApprovalLevel(Enum):
    LOW = "low"           # Auto-approve
    MEDIUM = "medium"     # Notify only
    HIGH = "high"         # Require explicit approval
    CRITICAL = "critical" # Require multiple approvals


@dataclass
class ApprovalRequest:
    request_id: str
    tool_name: str
    action: str
    parameters: Dict[str, Any]
    level: ApprovalLevel
    requester: str
    timestamp: float = field(default_factory=time.time)
    expires_at: float = 0
    state: ApprovalState = ApprovalState.PENDING
    approvers: List[str] = field(default_factory=list)
    required_approvals: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)
    callback: Optional[Callable] = None


class ApprovalModalGuardrail:
    def __init__(self, default_timeout: float = 5.0, auto_approve_low: bool = True):
        self.default_timeout = default_timeout
        self.auto_approve_low = auto_approve_low
        self._requests: Dict[str, ApprovalRequest] = {}
        self._pending_queue: deque = deque()
        self._lock = threading.RLock()
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._callbacks: Dict[str, List[Callable]] = {
            "request_created": [],
            "request_approved": [],
            "request_rejected": [],
            "request_expired": [],
            "request_auto_approved": []
        }
        self._level_config = {
            ApprovalLevel.LOW: {"timeout": 1.0, "auto_approve": True, "required": 0},
            ApprovalLevel.MEDIUM: {"timeout": 5.0, "auto_approve": False, "required": 0},
            ApprovalLevel.HIGH: {"timeout": 30.0, "auto_approve": False, "required": 1},
            ApprovalLevel.CRITICAL: {"timeout": 60.0, "auto_approve": False, "required": 2}
        }
    
    def start(self):
        if self._running:
            return
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
    
    def stop(self):
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2.0)
    
    def request_approval(self, tool_name: str, action: str, parameters: Dict[str, Any],
                        level: ApprovalLevel = ApprovalLevel.MEDIUM,
                        requester: str = "system",
                        timeout: float = None,
                        required_approvals: int = None,
                        callback: Callable = None,
                        metadata: Dict[str, Any] = None) -> str:
        
        request_id = str(uuid.uuid4())[:8]
        config = self._level_config.get(level, {})
        
        request = ApprovalRequest(
            request_id=request_id,
            tool_name=tool_name,
            action=action,
            parameters=parameters,
            level=level,
            requester=requester,
            expires_at=time.time() + (timeout or config.get("timeout", self.default_timeout)),
            required_approvals=required_approvals or config.get("required", 1),
            callback=callback,
            metadata=metadata or {}
        )
        
        with self._lock:
            self._requests[request_id] = request
            self._pending_queue.append(request_id)
        
        # Auto-approve low level
        if level == ApprovalLevel.LOW and self.auto_approve_low:
            self.approve(request_id, "auto")
        
        self._notify_request_created(request)
        return request_id
    
    def approve(self, request_id: str, approver: str) -> bool:
        with self._lock:
            request = self._requests.get(request_id)
            if not request or request.state != ApprovalState.PENDING:
                return False
            
            if approver not in request.approvers:
                request.approvers.append(approver)
            
            if len(request.approvers) >= request.required_approvals:
                request.state = ApprovalState.APPROVED
                self._execute_callback(request)
                self._notify_request_approved(request)
            else:
                # Still pending, more approvals needed
                pass
        
        return True
    
    def reject(self, request_id: str, approver: str) -> bool:
        with self._lock:
            request = self._requests.get(request_id)
            if not request or request.state != ApprovalState.PENDING:
                return False
            
            request.state = ApprovalState.REJECTED
            self._notify_request_rejected(request)
        
        return True
    
    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        with self._lock:
            return self._requests.get(request_id)
    
    def get_pending(self, requester: str = None) -> List[ApprovalRequest]:
        with self._lock:
            requests = list(self._requests.values())
        
        if requester:
            requests = [r for r in requests if r.requester == requester]
        
        return [r for r in requests if r.state == ApprovalState.PENDING]
    
    def wait_for_approval(self, request_id: str, timeout: float = None) -> ApprovalState:
        request = self.get_request(request_id)
        if not request:
            return ApprovalState.EXPIRED
        
        start = time.time()
        max_wait = timeout or (request.expires_at - request.timestamp)
        
        while time.time() - start < max_wait:
            request = self.get_request(request_id)
            if request and request.state in (ApprovalState.APPROVED, ApprovalState.REJECTED):
                return request.state
            time.sleep(0.1)
        
        return ApprovalState.EXPIRED
    
    def register_callback(self, event: str, callback: Callable):
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    def configure_level(self, level: ApprovalLevel, timeout: float = None,
                       auto_approve: bool = None, required: int = None):
        if level in self._level_config:
            if timeout is not None:
                self._level_config[level]["timeout"] = timeout
            if auto_approve is not None:
                self._level_config[level]["auto_approve"] = auto_approve
            if required is not None:
                self._level_config[level]["required"] = required
    
    def _monitor_loop(self):
        while self._running:
            time.sleep(0.5)
            self._check_expirations()
    
    def _check_expirations(self):
        now = time.time()
        expired = []
        
        with self._lock:
            for request_id, request in self._requests.items():
                if request.state == ApprovalState.PENDING and now >= request.expires_at:
                    expired.append(request_id)
        
        for request_id in expired:
            with self._lock:
                request = self._requests.get(request_id)
                if request:
                    config = self._level_config.get(request.level, {})
                    if config.get("auto_approve", False):
                        request.state = ApprovalState.AUTO_APPROVED
                        self._execute_callback(request)
                        self._notify_request_auto_approved(request)
                    else:
                        request.state = ApprovalState.EXPIRED
                        self._notify_request_expired(request)
    
    def _execute_callback(self, request: ApprovalRequest):
        if request.callback:
            try:
                request.callback(request)
            except Exception:
                pass
    
    def _notify_request_created(self, request: ApprovalRequest):
        for cb in self._callbacks["request_created"]:
            try:
                cb(request)
            except Exception:
                pass
    
    def _notify_request_approved(self, request: ApprovalRequest):
        for cb in self._callbacks["request_approved"]:
            try:
                cb(request)
            except Exception:
                pass
    
    def _notify_request_rejected(self, request: ApprovalRequest):
        for cb in self._callbacks["request_rejected"]:
            try:
                cb(request)
            except Exception:
                pass
    
    def _notify_request_expired(self, request: ApprovalRequest):
        for cb in self._callbacks["request_expired"]:
            try:
                cb(request)
            except Exception:
                pass
    
    def _notify_request_auto_approved(self, request: ApprovalRequest):
        for cb in self._callbacks["request_auto_approved"]:
            try:
                cb(request)
            except Exception:
                pass
    
    def cleanup_old(self, max_age: float = 3600):
        now = time.time()
        with self._lock:
            to_remove = [
                rid for rid, req in self._requests.items()
                if now - req.timestamp > max_age and req.state != ApprovalState.PENDING
            ]
            for rid in to_remove:
                del self._requests[rid]


_approval_guardrail: Optional[ApprovalModalGuardrail] = None

def get_approval_guardrail() -> ApprovalModalGuardrail:
    global _approval_guardrail
    if _approval_guardrail is None:
        from ..core.config import config
        timeout = config.get_param("neurocranial", "approval_timeout", 5.0)
        _approval_guardrail = ApprovalModalGuardrail(default_timeout=timeout)
        _approval_guardrail.start()
    return _approval_guardrail