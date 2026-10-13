"""
State Machine Guard - Formal state machine with validation
"""
import asyncio
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, TypeVar

T = TypeVar('T')
S = TypeVar('S')


class TransitionType(Enum):
    INTERNAL = "internal"
    EXTERNAL = "external"
    TIMEOUT = "timeout"
    CONDITIONAL = "conditional"


@dataclass
class State:
    name: str
    is_initial: bool = False
    is_final: bool = False
    on_enter: Callable | None = None
    on_exit: Callable | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        if isinstance(other, State):
            return self.name == other.name
        return self.name == other


@dataclass
class Transition:
    from_state: str
    to_state: str
    event: str
    condition: Callable | None = None
    action: Callable | None = None
    transition_type: TransitionType = TransitionType.EXTERNAL
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def matches(self, event: str, context: dict[str, Any]) -> bool:
        if self.event != event:
            return False
        if self.condition:
            try:
                return self.condition(context)
            except Exception:
                return False
        return True


@dataclass
class StateMachineConfig:
    allow_unknown_events: bool = False
    validate_transitions: bool = True
    log_transitions: bool = True
    max_history: int = 1000


class StateMachine(Generic[S]):
    def __init__(
        self,
        name: str,
        states: list[State],
        transitions: list[Transition],
        initial_state: str,
        config: StateMachineConfig = None,
    ):
        self.name = name
        self.states = {s.name: s for s in states}
        self.transitions = transitions
        self.initial_state = initial_state
        self.config = config or StateMachineConfig()

        self.current_state = initial_state
        self.history: list[dict[str, Any]] = []
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._task: asyncio.Task | None = None
        self._callbacks: list[Callable] = []
        self._lock = asyncio.Lock()

        self._build_transition_map()

    def _build_transition_map(self):
        self._transition_map: dict[str, dict[str, list[Transition]]] = defaultdict(lambda: defaultdict(list))
        for transition in self.transitions:
            self._transition_map[transition.from_state][transition.event].append(transition)

        for from_state in self._transition_map:
            for event in self._transition_map[from_state]:
                self._transition_map[from_state][event].sort(key=lambda t: -t.priority)

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._event_loop())
        await self._enter_state(self.initial_state)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _event_loop(self):
        while self._running:
            try:
                event, context = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
                await self._process_event(event, context)
            except asyncio.TimeoutError:
                continue

    async def send_event(self, event: str, context: dict[str, Any] = None):
        await self._event_queue.put((event, context or {}))

    async def _process_event(self, event: str, context: dict[str, Any]):
        transitions = self._transition_map.get(self.current_state, {}).get(event, [])

        if not transitions:
            if self.config.allow_unknown_events:
                return
            raise ValueError(f"No transition for event '{event}' in state '{self.current_state}'")

        for transition in transitions:
            if transition.matches(event, context):
                await self._execute_transition(transition, context)
                return

        if self.config.allow_unknown_events:
            return
        raise ValueError(f"No matching transition for event '{event}' in state '{self.current_state}'")

    async def _execute_transition(self, transition: Transition, context: dict[str, Any]):
        from_state_obj = self.states[self.current_state]
        to_state_obj = self.states[transition.to_state]

        if from_state_obj.on_exit:
            if asyncio.iscoroutinefunction(from_state_obj.on_exit):
                await from_state_obj.on_exit(context)
            else:
                from_state_obj.on_exit(context)

        if transition.action:
            if asyncio.iscoroutinefunction(transition.action):
                await transition.action(context)
            else:
                transition.action(context)

        self.current_state = transition.to_state

        if to_state_obj.on_enter:
            if asyncio.iscoroutinefunction(to_state_obj.on_enter):
                await to_state_obj.on_enter(context)
            else:
                to_state_obj.on_enter(context)

        self.history.append({
            "event": event,
            "from_state": from_state_obj.name,
            "to_state": to_state_obj.name,
            "transition": transition.metadata,
            "context": context,
            "timestamp": asyncio.get_event_loop().time(),
        })

        if len(self.history) > self.config.max_history:
            self.history = self.history[-self.config.max_history:]

        await self._notify_callbacks(event, from_state_obj.name, to_state_obj.name, context)

    async def _enter_state(self, state_name: str):
        state = self.states[state_name]
        if state.on_enter:
            if asyncio.iscoroutinefunction(state.on_enter):
                await state.on_enter({})
            else:
                state.on_enter({})

    async def _notify_callbacks(self, event: str, from_state: str, to_state: str, context: dict):
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event, from_state, to_state, context)
                else:
                    callback(event, from_state, to_state, context)
            except Exception:
                pass

    def on_transition(self, callback: Callable):
        self._callbacks.append(callback)

    def get_state(self) -> str:
        return self.current_state

    def is_in_state(self, state_name: str) -> bool:
        return self.current_state == state_name

    def can_transition(self, event: str) -> bool:
        return event in self._transition_map.get(self.current_state, {})

    def get_possible_events(self) -> list[str]:
        return list(self._transition_map.get(self.current_state, {}).keys())

    def get_history(self) -> list[dict[str, Any]]:
        return list(self.history)

    def reset(self):
        self.current_state = self.initial_state
        self.history.clear()


class HierarchicalStateMachine(StateMachine[S]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent: HierarchicalStateMachine | None = None
        self.children: dict[str, HierarchicalStateMachine] = {}
        self.active_child: str | None = None

    def add_child(self, name: str, child: 'HierarchicalStateMachine'):
        child.parent = self
        self.children[name] = child

    async def start(self):
        await super().start()
        if self.active_child and self.active_child in self.children:
            await self.children[self.active_child].start()

    async def stop(self):
        for child in self.children.values():
            await child.stop()
        await super().stop()

    async def _enter_state(self, state_name: str):
        await super()._enter_state(state_name)
        state = self.states[state_name]
        child_name = state.metadata.get("child")
        if child_name and child_name in self.children:
            self.active_child = child_name
            await self.children[child_name].start()


class StateMachineGuard:
    def __init__(self):
        self.machines: dict[str, StateMachine] = {}

    def register(self, machine: StateMachine) -> str:
        self.machines[machine.name] = machine
        return machine.name

    def unregister(self, name: str) -> bool:
        if name in self.machines:
            del self.machines[name]
            return True
        return False

    def get(self, name: str) -> StateMachine | None:
        return self.machines.get(name)

    async def start_all(self):
        for machine in self.machines.values():
            await machine.start()

    async def stop_all(self):
        for machine in self.machines.values():
            await machine.stop()

    def get_all_states(self) -> dict[str, str]:
        return {name: machine.get_state() for name, machine in self.machines.items()}


class StateMachineBuilder:
    def __init__(self, name: str):
        self.name = name
        self.states: list[State] = []
        self.transitions: list[Transition] = []
        self.initial_state: str | None = None
        self.config = StateMachineConfig()

    def add_state(
        self,
        name: str,
        is_initial: bool = False,
        is_final: bool = False,
        on_enter: Callable | None = None,
        on_exit: Callable | None = None,
        metadata: dict[str, Any] = None,
    ) -> 'StateMachineBuilder':
        state = State(name, is_initial, is_final, on_enter, on_exit, metadata)
        self.states.append(state)
        if is_initial:
            self.initial_state = name
        return self

    def add_transition(
        self,
        from_state: str,
        to_state: str,
        event: str,
        condition: Callable | None = None,
        action: Callable | None = None,
        transition_type: TransitionType = TransitionType.EXTERNAL,
        priority: int = 0,
        metadata: dict[str, Any] = None,
    ) -> 'StateMachineBuilder':
        transition = Transition(
            from_state=from_state,
            to_state=to_state,
            event=event,
            condition=condition,
            action=action,
            transition_type=transition_type,
            priority=priority,
            metadata=metadata or {},
        )
        self.transitions.append(transition)
        return self

    def set_config(self, config: StateMachineConfig) -> 'StateMachineBuilder':
        self.config = config
        return self

    def build(self) -> StateMachine:
        if not self.initial_state:
            raise ValueError("No initial state defined")
        return StateMachine(
            self.name,
            self.states,
            self.transitions,
            self.initial_state,
            self.config,
        )


class ProtocolStateMachine:
    def __init__(self):
        self.protocols: dict[str, StateMachine] = {}

    def define_protocol(self, name: str, states: list[str], transitions: list[dict[str, str]], initial: str):
        builder = StateMachineBuilder(name)

        for state_name in states:
            builder.add_state(state_name, is_initial=(state_name == initial))

        for trans in transitions:
            builder.add_transition(
                trans["from"],
                trans["to"],
                trans["event"],
            )

        self.protocols[name] = builder.build()

    def validate_trace(self, protocol_name: str, events: list[str]) -> bool:
        machine = self.protocols.get(protocol_name)
        if not machine:
            return False

        test_machine = StateMachine(
            f"test_{protocol_name}",
            machine.states.values(),
            machine.transitions,
            machine.initial_state,
        )

        for event in events:
            if not test_machine.can_transition(event):
                return False
            test_machine.current_state = machine._transition_map[test_machine.current_state][event][0].to_state

        return True
