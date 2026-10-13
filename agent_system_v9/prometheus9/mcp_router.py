"""
Model Context Protocol (MCP) Stateless Router - Connects agent hooks via MCP spec
"""
import threading
import time
import uuid
import json
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum


class MCPMessageType(Enum):
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    ERROR = "error"


@dataclass
class MCPRequest:
    request_id: str
    method: str
    params: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class MCPResponse:
    request_id: str
    result: Any = None
    error: Optional[Dict[str, Any]] = None
    headers: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class MCPRouter:
    def __init__(self, max_roundtrips: int = 5):
        self.max_roundtrips = max_roundtrips
        self._handlers: Dict[str, Callable] = {}
        self._middleware: List[Callable] = []
        self._lock = threading.RLock()
        self._pending_requests: Dict[str, Dict] = {}
        self._stats = {"requests": 0, "responses": 0, "errors": 0, "roundtrips": 0}
    
    def register_handler(self, method: str, handler: Callable[[MCPRequest], MCPResponse]):
        with self._lock:
            self._handlers[method] = handler
    
    def add_middleware(self, middleware: Callable[[MCPRequest], Optional[MCPRequest]]):
        with self._lock:
            self._middleware.append(middleware)
    
    def route(self, request: MCPRequest) -> MCPResponse:
        with self._lock:
            self._stats["requests"] += 1
        
        # Apply middleware
        processed_request = request
        for middleware in self._middleware:
            try:
                processed_request = middleware(processed_request)
                if processed_request is None:
                    return MCPResponse(request_id=request.request_id, error={
                        "code": -32603, "message": "Middleware rejected request"
                    })
            except Exception as e:
                return MCPResponse(request_id=request.request_id, error={
                    "code": -32603, "message": f"Middleware error: {e}"
                })
        
        # Find handler
        with self._lock:
            handler = self._handlers.get(processed_request.method)
        
        if not handler:
            return MCPResponse(request_id=request.request_id, error={
                "code": -32601, "message": f"Method not found: {processed_request.method}"
            })
        
        # Execute handler
        try:
            response = handler(processed_request)
            with self._lock:
                self._stats["responses"] += 1
            return response
        except Exception as e:
            with self._lock:
                self._stats["errors"] += 1
            return MCPResponse(request_id=request.request_id, error={
                "code": -32603, "message": f"Handler error: {e}"
            })
    
    def create_request(self, method: str, params: Dict = None, headers: Dict = None) -> MCPRequest:
        return MCPRequest(
            request_id=str(uuid.uuid4()),
            method=method,
            params=params or {},
            headers=headers or {}
        )
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._stats)


_mcp_router: Optional[MCPRouter] = None

def get_mcp_router() -> MCPRouter:
    global _mcp_router
    if _mcp_router is None:
        from ..core.config import config
        max_rt = config.get_param("prometheus9", "mcp_max_roundtrips", 5)
        _mcp_router = MCPRouter(max_roundtrips=max_rt)
    return _mcp_router