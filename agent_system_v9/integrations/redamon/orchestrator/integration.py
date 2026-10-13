"""
RedAmon Orchestrator Integration - Bridges RedAmon agentic orchestrator into AGENT_SYSTEM_V9
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AgentPhase(Enum):
    """Agent execution phases."""
    INIT = "init"
    PLAN = "plan"
    EXECUTE = "execute"
    VERIFY = "verify"
    COMPLETE = "complete"
    ERROR = "error"


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass
class AgentTask:
    """Represents a task in the agent workflow."""
    task_id: str
    name: str
    description: str
    phase: AgentPhase
    status: TaskStatus = TaskStatus.PENDING
    dependencies: list[str] = field(default_factory=list)
    result: Any | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentContext:
    """Execution context for agent operations."""
    session_id: str
    workspace_path: Path
    config: dict[str, Any]
    state: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class RedamonOrchestrator:
    """
    Integration wrapper for RedAmon's AgentOrchestrator.
    Provides AGENT_SYSTEM_V9 compatible interface.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.session_id = str(uuid.uuid4())[:8]
        self.workspace_path = Path(self.config.get("workspace", "/workspace"))
        self.workspace_path.mkdir(parents=True, exist_ok=True)

        self._tasks: dict[str, AgentTask] = {}
        self._context = AgentContext(
            session_id=self.session_id,
            workspace_path=self.workspace_path,
            config=self.config
        )
        self._running = False
        self._event_handlers: dict[str, list[Callable]] = {}

        # Import RedAmon components
        self._redamon_orchestrator = None
        self._redamon_state = None
        self._tools = None
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize the orchestrator and RedAmon components."""
        if self._initialized:
            return True

        try:
            # Import RedAmon modules
            from agent_system_v9.integrations.redamon.orchestrator.orchestrator import (
                AgentOrchestrator as RedamonAgentOrchestrator,
            )
            from agent_system_v9.integrations.redamon.orchestrator.state import AgentState
            from agent_system_v9.integrations.redamon.orchestrator.tools import ToolRegistry

            self._redamon_orchestrator = RedamonAgentOrchestrator()
            await self._redamon_orchestrator.initialize()

            self._redamon_state = AgentState()
            self._tools = ToolRegistry()

            self._initialized = True
            logger.info(f"RedAmon orchestrator initialized (session: {self.session_id})")
            return True

        except ImportError as e:
            logger.warning(f"RedAmon modules not available: {e}")
            self._initialized = False
            return False
        except Exception as e:
            logger.error(f"Failed to initialize RedAmon orchestrator: {e}")
            self._initialized = False
            return False

    async def execute_plan(self, plan: list[dict[str, Any]]) -> dict[str, Any]:
        """Execute a multi-phase plan."""
        if not self._initialized:
            await self.initialize()

        if not self._initialized:
            return {"success": False, "error": "Orchestrator not initialized"}

        results = {}
        for i, step in enumerate(plan):
            task_id = f"task_{i}_{step.get('name', 'unnamed')}"
            task = AgentTask(
                task_id=task_id,
                name=step.get("name", f"Step {i}"),
                description=step.get("description", ""),
                phase=AgentPhase(step.get("phase", "execute")),
                dependencies=step.get("dependencies", [])
            )
            self._tasks[task_id] = task

            # Check dependencies
            for dep_id in task.dependencies:
                if dep_id in self._tasks:
                    dep_task = self._tasks[dep_id]
                    if dep_task.status != TaskStatus.COMPLETED:
                        task.status = TaskStatus.FAILED
                        task.error = f"Dependency {dep_id} not completed"
                        results[task_id] = {"success": False, "error": task.error}
                        continue

            if task.status == TaskStatus.FAILED:
                continue

            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now()
            self._emit_event("task_started", {"task_id": task_id, "task": task})

            try:
                # Execute via RedAmon orchestrator if available
                if self._redamon_orchestrator:
                    result = await self._execute_via_redamon(task, step)
                else:
                    result = await self._execute_native(task, step)

                task.result = result
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now()
                results[task_id] = {"success": True, "result": result}
                self._emit_event("task_completed", {"task_id": task_id, "result": result})

            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                task.completed_at = datetime.now()
                results[task_id] = {"success": False, "error": str(e)}
                self._emit_event("task_failed", {"task_id": task_id, "error": str(e)})

        return {
            "success": all(r.get("success", False) for r in results.values()),
            "results": results,
            "session_id": self.session_id
        }

    async def _execute_via_redamon(self, task: AgentTask, step: dict[str, Any]) -> Any:
        """Execute task using RedAmon orchestrator."""
        # Convert to RedAmon format
        redamon_task = {
            "id": task.task_id,
            "name": task.name,
            "description": task.description,
            "action": step.get("action"),
            "params": step.get("params", {}),
            "tools": step.get("tools", [])
        }

        # Use RedAmon's execution
        result = await self._redamon_orchestrator.execute_task(redamon_task)
        return result

    async def _execute_native(self, task: AgentTask, step: dict[str, Any]) -> Any:
        """Execute task using native AGENT_SYSTEM_V9 capabilities."""
        action = step.get("action")
        params = step.get("params", {})

        if action == "shell":
            import subprocess
            cmd = params.get("command", "")
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=params.get("timeout", 30))
            return {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}

        if action == "tool":
            tool_name = params.get("tool")
            tool_params = params.get("params", {})
            if self._tools and hasattr(self._tools, "execute"):
                return await self._tools.execute(tool_name, tool_params)
            return {"error": f"Tool {tool_name} not available"}

        if action == "llm":
            # Delegate to AGENT_SYSTEM_V9 providers
            from agent_system_v9.providers import ProviderRegistry
            registry = ProviderRegistry.get_instance()
            provider = registry.get_default()
            if provider:
                prompt = params.get("prompt", "")
                response = await provider.complete(prompt)
                return {"response": response.text}
            return {"error": "No LLM provider configured"}

        return {"error": f"Unknown action: {action}"}

    def create_task(self, name: str, description: str, phase: AgentPhase,
                    dependencies: list[str] = None, **metadata) -> AgentTask:
        """Create a new task."""
        task_id = f"{name}_{uuid.uuid4().hex[:8]}"
        task = AgentTask(
            task_id=task_id,
            name=name,
            description=description,
            phase=phase,
            dependencies=dependencies or [],
            metadata=metadata
        )
        self._tasks[task_id] = task
        return task

    def get_task(self, task_id: str) -> AgentTask | None:
        """Get task by ID."""
        return self._tasks.get(task_id)

    def get_tasks_by_phase(self, phase: AgentPhase) -> list[AgentTask]:
        """Get all tasks in a phase."""
        return [t for t in self._tasks.values() if t.phase == phase]

    def get_context(self) -> AgentContext:
        """Get current execution context."""
        return self._context

    def update_context(self, key: str, value: Any):
        """Update context state."""
        self._context.state[key] = value

    def add_artifact(self, name: str, artifact: Any):
        """Add artifact to context."""
        self._context.artifacts[name] = artifact

    def on(self, event: str, handler: Callable):
        """Register event handler."""
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)

    def _emit_event(self, event: str, data: dict[str, Any]):
        """Emit event to handlers."""
        for handler in self._event_handlers.get(event, []):
            try:
                handler(data)
            except Exception as e:
                logger.error(f"Event handler error: {e}")

    async def shutdown(self):
        """Shutdown orchestrator."""
        if self._redamon_orchestrator:
            await self._redamon_orchestrator.shutdown()
        self._running = False


class OrchestratorIntegration:
    """
    High-level integration class for AGENT_SYSTEM_V9.
    """

    def __init__(self):
        self._orchestrator: RedamonOrchestrator | None = None
        self._active_sessions: dict[str, RedamonOrchestrator] = {}

    def create_session(self, config: dict[str, Any] | None = None) -> RedamonOrchestrator:
        """Create a new orchestrator session."""
        orchestrator = RedamonOrchestrator(config)
        self._active_sessions[orchestrator.session_id] = orchestrator
        return orchestrator

    def get_session(self, session_id: str) -> RedamonOrchestrator | None:
        """Get session by ID."""
        return self._active_sessions.get(session_id)

    def get_active_sessions(self) -> list[str]:
        """Get list of active session IDs."""
        return list(self._active_sessions.keys())

    async def close_session(self, session_id: str):
        """Close and cleanup session."""
        if session_id in self._active_sessions:
            await self._active_sessions[session_id].shutdown()
            del self._active_sessions[session_id]


# Singleton instance
_orchestrator_integration: OrchestratorIntegration | None = None


def get_orchestrator_integration() -> OrchestratorIntegration:
    """Get the global orchestrator integration instance."""
    global _orchestrator_integration
    if _orchestrator_integration is None:
        _orchestrator_integration = OrchestratorIntegration()
    return _orchestrator_integration


@asynccontextmanager
async def agent_session(config: dict[str, Any] | None = None):
    """Context manager for agent session."""
    integration = get_orchestrator_integration()
    orchestrator = integration.create_session(config)
    try:
        await orchestrator.initialize()
        yield orchestrator
    finally:
        await integration.close_session(orchestrator.session_id)
