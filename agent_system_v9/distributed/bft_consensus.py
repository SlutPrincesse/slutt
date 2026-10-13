"""
BFT Consensus - Byzantine Fault Tolerant consensus protocol
"""
import asyncio
import hashlib
import json
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ConsensusPhase(Enum):
    PRE_PREPARE = "pre_prepare"
    PREPARE = "prepare"
    COMMIT = "commit"
    REPLY = "reply"
    VIEW_CHANGE = "view_change"


class MessageType(Enum):
    PRE_PREPARE = "pre_prepare"
    PREPARE = "prepare"
    COMMIT = "commit"
    VIEW_CHANGE = "view_change"
    NEW_VIEW = "new_view"
    CHECKPOINT = "checkpoint"
    REQUEST = "request"
    REPLY = "reply"


@dataclass
class ConsensusMessage:
    msg_type: MessageType
    view: int
    sequence: int
    digest: str
    node_id: str
    timestamp: float = field(default_factory=time.time)
    payload: Any | None = None
    signature: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "msg_type": self.msg_type.value,
            "view": self.view,
            "sequence": self.sequence,
            "digest": self.digest,
            "node_id": self.node_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'ConsensusMessage':
        return cls(
            msg_type=MessageType(data["msg_type"]),
            view=data["view"],
            sequence=data["sequence"],
            digest=data["digest"],
            node_id=data["node_id"],
            timestamp=data.get("timestamp", time.time()),
            payload=data.get("payload"),
            signature=data.get("signature"),
        )


@dataclass
class ClientRequest:
    request_id: str
    client_id: str
    operation: Any
    timestamp: float = field(default_factory=time.time)
    signature: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "client_id": self.client_id,
            "operation": self.operation,
            "timestamp": self.timestamp,
            "signature": self.signature,
        }


@dataclass
class ConsensusState:
    view: int = 0
    sequence: int = 0
    primary: str = ""
    nodes: list[str] = field(default_factory=list)
    committed: dict[int, Any] = field(default_factory=dict)
    prepared: dict[int, set[str]] = field(default_factory=lambda: defaultdict(set))
    committed_certs: dict[int, set[str]] = field(default_factory=lambda: defaultdict(set))
    view_changes: dict[int, set[str]] = field(default_factory=lambda: defaultdict(set))
    last_checkpoint: int = 0


class BFTConsensus:
    def __init__(
        self,
        node_id: str,
        nodes: list[str],
        f: int = 1,
        checkpoint_interval: int = 100,
    ):
        self.node_id = node_id
        self.nodes = nodes
        self.n = len(nodes)
        self.f = f
        self.checkpoint_interval = checkpoint_interval

        if self.n < 3 * self.f + 1:
            raise ValueError(f"Need at least {3 * f + 1} nodes for f={f} Byzantine faults")

        self.state = ConsensusState(
            nodes=nodes,
            primary=nodes[0] if nodes else "",
        )

        self.message_log: list[ConsensusMessage] = []
        self.pending_requests: dict[str, ClientRequest] = {}
        self.execute_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._callbacks: list[Callable] = []
        self._lock = asyncio.Lock()

    def is_primary(self) -> bool:
        return self.state.primary == self.node_id

    def get_primary(self, view: int = None) -> str:
        view = view or self.state.view
        return self.nodes[view % self.n]

    def _quorum_size(self) -> int:
        return 2 * self.f + 1

    def _verify_signature(self, message: ConsensusMessage) -> bool:
        return message.signature is not None

    async def start(self):
        self._running = True
        asyncio.create_task(self._process_queue())
        asyncio.create_task(self._view_change_timer())

    async def stop(self):
        self._running = False

    async def propose(self, operation: Any) -> str:
        request_id = str(uuid.uuid4())
        request = ClientRequest(
            request_id=request_id,
            client_id=self.node_id,
            operation=operation,
        )
        self.pending_requests[request_id] = request

        if self.is_primary():
            await self._pre_prepare(request)

        return request_id

    async def _pre_prepare(self, request: ClientRequest):
        self.state.sequence += 1
        digest = self._compute_digest(request)

        msg = ConsensusMessage(
            msg_type=MessageType.PRE_PREPARE,
            view=self.state.view,
            sequence=self.state.sequence,
            digest=digest,
            node_id=self.node_id,
            payload=request.to_dict(),
        )

        await self._broadcast(msg)
        await self._handle_pre_prepare(msg)

    async def _handle_pre_prepare(self, msg: ConsensusMessage):
        if msg.node_id != self.state.primary:
            return

        if msg.view != self.state.view:
            return

        if msg.sequence <= self.state.last_checkpoint:
            return

        prepare_msg = ConsensusMessage(
            msg_type=MessageType.PREPARE,
            view=msg.view,
            sequence=msg.sequence,
            digest=msg.digest,
            node_id=self.node_id,
        )

        await self._broadcast(prepare_msg)

    async def _handle_prepare(self, msg: ConsensusMessage):
        if msg.view != self.state.view:
            return

        self.state.prepared[(msg.view, msg.sequence)].add(msg.node_id)

        if len(self.state.prepared[(msg.view, msg.sequence)]) >= self._quorum_size():
            commit_msg = ConsensusMessage(
                msg_type=MessageType.COMMIT,
                view=msg.view,
                sequence=msg.sequence,
                digest=msg.digest,
                node_id=self.node_id,
            )
            await self._broadcast(commit_msg)

    async def _handle_commit(self, msg: ConsensusMessage):
        if msg.view != self.state.view:
            return

        self.state.committed_certs[(msg.view, msg.sequence)].add(msg.node_id)

        if len(self.state.committed_certs[(msg.view, msg.sequence)]) >= self._quorum_size():
            await self._commit(msg)

    async def _commit(self, msg: ConsensusMessage):
        for req_id, request in self.pending_requests.items():
            if self._compute_digest(request) == msg.digest:
                self.state.committed[msg.sequence] = request.operation
                await self.execute_queue.put(request)
                del self.pending_requests[req_id]
                break

        if msg.sequence % self.checkpoint_interval == 0:
            await self._create_checkpoint(msg.sequence)

    async def _create_checkpoint(self, sequence: int):
        checkpoint_msg = ConsensusMessage(
            msg_type=MessageType.CHECKPOINT,
            view=self.state.view,
            sequence=sequence,
            digest=hashlib.sha256(str(self.state.committed).encode()).hexdigest(),
            node_id=self.node_id,
            payload={"committed": list(self.state.committed.keys())},
        )
        await self._broadcast(checkpoint_msg)

    async def _handle_checkpoint(self, msg: ConsensusMessage):
        pass

    async def _view_change_timer(self):
        while self._running:
            await asyncio.sleep(10.0)
            if not self.is_primary() and self.state.sequence > 0:
                await self._initiate_view_change()

    async def _initiate_view_change(self):
        self.state.view += 1
        self.state.primary = self.get_primary(self.state.view)

        vc_msg = ConsensusMessage(
            msg_type=MessageType.VIEW_CHANGE,
            view=self.state.view,
            sequence=self.state.sequence,
            digest="",
            node_id=self.node_id,
            payload={
                "prepared": list(self.state.prepared.keys()),
                "committed": list(self.state.committed.keys()),
            },
        )

        await self._broadcast(vc_msg)
        self.state.view_changes[self.state.view].add(self.node_id)

        if len(self.state.view_changes[self.state.view]) >= self._quorum_size():
            await self._handle_new_view()

    async def _handle_new_view(self):
        pass

    async def _process_queue(self):
        while self._running:
            try:
                request = await asyncio.wait_for(self.execute_queue.get(), timeout=1.0)
                await self._execute_request(request)
            except asyncio.TimeoutError:
                continue

    async def _execute_request(self, request: ClientRequest):
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(request.operation)
                else:
                    callback(request.operation)
            except Exception:
                pass

    def add_callback(self, callback: Callable):
        self._callbacks.append(callback)

    async def _broadcast(self, message: ConsensusMessage):
        self.message_log.append(message)
        pass

    def _compute_digest(self, request: ClientRequest) -> str:
        data = json.dumps(request.to_dict(), sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()

    def receive_message(self, message: ConsensusMessage):
        if not self._verify_signature(message):
            return

        asyncio.create_task(self._dispatch_message(message))

    async def _dispatch_message(self, message: ConsensusMessage):
        if message.msg_type == MessageType.PRE_PREPARE:
            await self._handle_pre_prepare(message)
        elif message.msg_type == MessageType.PREPARE:
            await self._handle_prepare(message)
        elif message.msg_type == MessageType.COMMIT:
            await self._handle_commit(message)
        elif message.msg_type == MessageType.CHECKPOINT:
            await self._handle_checkpoint(message)
        elif message.msg_type == MessageType.VIEW_CHANGE or message.msg_type == MessageType.NEW_VIEW:
            pass

    def get_state(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "view": self.state.view,
            "sequence": self.state.sequence,
            "primary": self.state.primary,
            "is_primary": self.is_primary(),
            "committed_count": len(self.state.committed),
            "pending_count": len(self.pending_requests),
        }


class PBFTNode:
    def __init__(self, node_id: str, cluster: list[str]):
        self.consensus = BFTConsensus(node_id, cluster)
        self.client_results: dict[str, asyncio.Future] = {}

    async def start(self):
        await self.consensus.start()

    async def stop(self):
        await self.consensus.stop()

    async def submit(self, operation: Any) -> Any:
        request_id = await self.consensus.propose(operation)
        future = asyncio.get_event_loop().create_future()
        self.client_results[request_id] = future
        return await future

    def handle_client_request(self, request: ClientRequest):
        asyncio.create_task(self.consensus.propose(request.operation))

    def handle_consensus_message(self, message: ConsensusMessage):
        self.consensus.receive_message(message)


class ConsensusCluster:
    def __init__(self, nodes: list[str]):
        self.nodes = {nid: PBFTNode(nid, nodes) for nid in nodes}

    async def start_all(self):
        for node in self.nodes.values():
            await node.start()

    async def stop_all(self):
        for node in self.nodes.values():
            await node.stop()

    def get_node(self, node_id: str) -> PBFTNode | None:
        return self.nodes.get(node_id)

    def broadcast_message(self, message: ConsensusMessage):
        for node in self.nodes.values():
            node.handle_consensus_message(message)
