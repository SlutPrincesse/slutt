"""
RPC Gateway - Distributed RPC communication layer
"""
import asyncio
import json
import uuid
import time
import threading
from typing import Dict, List, Optional, Any, Callable, Awaitable, Union
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import socket
import ssl


class RPCErrorCode(Enum):
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    SERVER_ERROR = -32000
    TIMEOUT = -32001
    CANCELLED = -32002


@dataclass
class RPCRequest:
    id: str
    method: str
    params: Optional[Union[List, Dict]] = None
    jsonrpc: str = "2.0"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "jsonrpc": self.jsonrpc,
            "method": self.method,
            "params": self.params,
            "id": self.id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RPCRequest':
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            method=data["method"],
            params=data.get("params"),
            jsonrpc=data.get("jsonrpc", "2.0"),
        )


@dataclass
class RPCResponse:
    id: str
    result: Any = None
    error: Optional[Dict[str, Any]] = None
    jsonrpc: str = "2.0"

    def to_dict(self) -> Dict[str, Any]:
        resp = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error:
            resp["error"] = self.error
        else:
            resp["result"] = self.result
        return resp

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RPCResponse':
        return cls(
            id=data["id"],
            result=data.get("result"),
            error=data.get("error"),
            jsonrpc=data.get("jsonrpc", "2.0"),
        )

    @classmethod
    def error_response(cls, id: str, code: int, message: str, data: Any = None) -> 'RPCResponse':
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return cls(id=id, error=error)


@dataclass
class RPCNotification:
    method: str
    params: Optional[Union[List, Dict]] = None
    jsonrpc: str = "2.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "jsonrpc": self.jsonrpc,
            "method": self.method,
            "params": self.params,
        }


class RPCMethod:
    def __init__(
        self,
        name: str,
        handler: Callable,
        description: str = "",
        params_schema: Optional[Dict] = None,
        return_schema: Optional[Dict] = None,
    ):
        self.name = name
        self.handler = handler
        self.description = description
        self.params_schema = params_schema
        self.return_schema = return_schema


class RPCGateway:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        ssl_context: Optional[ssl.SSLContext] = None,
    ):
        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self.methods: Dict[str, RPCMethod] = {}
        self.middlewares: List[Callable] = []
        self.server: Optional[asyncio.Server] = None
        self._running = False
        self._request_id = 0
        self._pending: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    def register(self, method: RPCMethod):
        self.methods[method.name] = method

    def unregister(self, name: str) -> bool:
        if name in self.methods:
            del self.methods[name]
            return True
        return False

    def add_middleware(self, middleware: Callable):
        self.middlewares.append(middleware)

    async def start(self):
        self._running = True
        self.server = await asyncio.start_server(
            self._handle_connection,
            self.host,
            self.port,
            ssl=self.ssl_context,
        )
        await self.server.start_serving()

    async def stop(self):
        self._running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            while self._running:
                data = await reader.readline()
                if not data:
                    break
                
                try:
                    request = json.loads(data.decode())
                    response = await self._process_request(request)
                    if response:
                        writer.write((json.dumps(response.to_dict()) + "\n").encode())
                        await writer.drain()
                except json.JSONDecodeError:
                    error = RPCResponse.error_response(
                        "", RPCErrorCode.PARSE_ERROR.value, "Parse error"
                    )
                    writer.write((json.dumps(error.to_dict()) + "\n").encode())
                    await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    async def _process_request(self, request_data: Dict) -> Optional[RPCResponse]:
        if "method" not in request_data:
            return RPCResponse.error_response(
                request_data.get("id", ""), RPCErrorCode.INVALID_REQUEST.value, "Invalid request"
            )

        request = RPCRequest.from_dict(request_data)
        
        for middleware in self.middlewares:
            request = await middleware(request) if asyncio.iscoroutinefunction(middleware) else middleware(request)

        if request.method not in self.methods:
            return RPCResponse.error_response(
                request.id, RPCErrorCode.METHOD_NOT_FOUND.value, f"Method not found: {request.method}"
            )

        method = self.methods[request.method]
        
        try:
            if asyncio.iscoroutinefunction(method.handler):
                result = await method.handler(request.params)
            else:
                result = method.handler(request.params)
            
            return RPCResponse(id=request.id, result=result)
        except Exception as e:
            return RPCResponse.error_response(
                request.id, RPCErrorCode.INTERNAL_ERROR.value, str(e)
            )

    async def call(
        self,
        host: str,
        port: int,
        method: str,
        params: Optional[Union[List, Dict]] = None,
        timeout: float = 30.0,
        use_ssl: bool = False,
    ) -> Any:
        request = RPCRequest(
            id=str(uuid.uuid4()),
            method=method,
            params=params,
        )

        future = asyncio.get_event_loop().create_future()
        async with self._lock:
            self._pending[request.id] = future

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, ssl=use_ssl),
                timeout=timeout,
            )

            writer.write((json.dumps(request.to_dict()) + "\n").encode())
            await writer.drain()

            response_data = await asyncio.wait_for(reader.readline(), timeout=timeout)
            response = RPCResponse.from_dict(json.loads(response_data.decode()))

            if response.error:
                raise Exception(f"RPC Error: {response.error['message']}")
            
            return response.result
        finally:
            writer.close()
            await writer.wait_closed()
            async with self._lock:
                self._pending.pop(request.id, None)

    def notify(self, host: str, port: int, method: str, params: Optional[Union[List, Dict]] = None):
        notification = RPCNotification(method=method, params=params)
        # Fire and forget - would need persistent connection pool in production
        pass


class RPCClient:
    def __init__(
        self,
        host: str,
        port: int,
        timeout: float = 30.0,
        use_ssl: bool = False,
        ssl_context: Optional[ssl.SSLContext] = None,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.use_ssl = use_ssl
        self.ssl_context = ssl_context
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._pending: Dict[str, asyncio.Future] = {}
        _lock = asyncio.Lock()

    async def connect(self):
        self._reader, self._writer = await asyncio.open_connection(
            self.host, self.port, ssl=self.ssl_context if self.use_ssl else None
        )
        asyncio.create_task(self._read_loop())

    async def _read_loop(self):
        while self._writer and not self._writer.is_closing():
            try:
                data = await self._reader.readline()
                if not data:
                    break
                response = RPCResponse.from_dict(json.loads(data.decode()))
                if response.id in self._pending:
                    future = self._pending.pop(response.id)
                    if response.error:
                        future.set_exception(Exception(response.error["message"]))
                    else:
                        future.set_result(response.result)
            except Exception:
                break

    async def call(self, method: str, params: Optional[Union[List, Dict]] = None) -> Any:
        if not self._writer or self._writer.is_closing():
            await self.connect()

        request = RPCRequest(id=str(uuid.uuid4()), method=method, params=params)
        future = asyncio.get_event_loop().create_future()
        self._pending[request.id] = future

        self._writer.write((json.dumps(request.to_dict()) + "\n").encode())
        await self._writer.drain()

        try:
            return await asyncio.wait_for(future, timeout=self.timeout)
        except asyncio.TimeoutError:
            self._pending.pop(request.id, None)
            raise TimeoutError(f"RPC call to {method} timed out")

    async def close(self):
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()


class ServiceRegistry:
    def __init__(self):
        self.services: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def register(self, name: str, host: str, port: int, metadata: Dict[str, Any] = None):
        with self._lock:
            self.services[name] = {
                "host": host,
                "port": port,
                "metadata": metadata or {},
                "registered_at": time.time(),
                "last_heartbeat": time.time(),
            }

    def unregister(self, name: str) -> bool:
        with self._lock:
            if name in self.services:
                del self.services[name]
                return True
        return False

    def discover(self, name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self.services.get(name)

    def list_services(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [{"name": k, **v} for k, v in self.services.items()]

    def heartbeat(self, name: str):
        with self._lock:
            if name in self.services:
                self.services[name]["last_heartbeat"] = time.time()

    def cleanup_stale(self, max_age: float = 60.0):
        now = time.time()
        with self._lock:
            stale = [k for k, v in self.services.items() if now - v["last_heartbeat"] > max_age]
            for k in stale:
                del self.services[k]