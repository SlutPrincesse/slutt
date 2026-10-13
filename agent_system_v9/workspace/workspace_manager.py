"""
Workspace Manager - Manages isolated workspaces for development
"""
import asyncio
import hashlib
import os
import shutil
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class WorkspaceType(Enum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"
    EXPERIMENTAL = "experimental"


class WorkspaceStatus(Enum):
    CREATING = "creating"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"
    DELETING = "deleting"
    ERROR = "error"


@dataclass
class WorkspaceConfig:
    name: str
    workspace_type: WorkspaceType = WorkspaceType.DEVELOPMENT
    base_path: str = "./workspaces"
    template: str = ""
    environment: dict[str, str] = field(default_factory=dict)
    resource_limits: dict[str, Any] = field(default_factory=dict)
    auto_cleanup: bool = True
    max_age_hours: float = 168.0  # 1 week


@dataclass
class Workspace:
    workspace_id: str
    config: WorkspaceConfig
    path: Path
    status: WorkspaceStatus = WorkspaceStatus.CREATING
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    resources: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "name": self.config.name,
            "type": self.config.workspace_type.value,
            "path": str(self.path),
            "status": self.status.value,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "metadata": self.metadata,
        }


@dataclass
class WorkspaceTemplate:
    name: str
    description: str
    files: dict[str, str] = field(default_factory=dict)
    directories: list[str] = field(default_factory=list)
    setup_commands: list[str] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)


class WorkspaceManager:
    def __init__(self, base_path: str = "./workspaces"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.workspaces: dict[str, Workspace] = {}
        self.templates: dict[str, WorkspaceTemplate] = {}
        self._lock = asyncio.Lock()
        self._running = False
        self._cleanup_task: asyncio.Task | None = None
        self._register_default_templates()

    def _register_default_templates(self):
        self.templates["python"] = WorkspaceTemplate(
            name="python",
            description="Python development workspace",
            files={
                "requirements.txt": "",
                "README.md": "# Workspace\n",
                ".gitignore": "__pycache__\n*.pyc\n.env\n",
            },
            directories=["src", "tests", "docs"],
            setup_commands=["python -m venv venv", "source venv/bin/activate"],
        )

        self.templates["node"] = WorkspaceTemplate(
            name="node",
            description="Node.js development workspace",
            files={
                "package.json": '{"name": "workspace", "version": "1.0.0"}',
                "README.md": "# Workspace\n",
                ".gitignore": "node_modules\n.env\n",
            },
            directories=["src", "tests"],
            setup_commands=["npm init -y"],
        )

        self.templates["rust"] = WorkspaceTemplate(
            name="rust",
            description="Rust development workspace",
            files={
                "Cargo.toml": '[package]\nname = "workspace"\nversion = "0.1.0"\nedition = "2021"',
                "README.md": "# Workspace\n",
                ".gitignore": "target\n.env\n",
            },
            directories=["src"],
            setup_commands=["cargo init"],
        )

    def register_template(self, template: WorkspaceTemplate):
        self.templates[template.name] = template

    async def create_workspace(self, config: WorkspaceConfig) -> Workspace:
        async with self._lock:
            workspace_id = hashlib.md5(f"{config.name}:{time.time()}".encode()).hexdigest()[:12]
            workspace_path = self.base_path / workspace_id
            workspace_path.mkdir(parents=True, exist_ok=True)

            workspace = Workspace(
                workspace_id=workspace_id,
                config=config,
                path=workspace_path,
                status=WorkspaceStatus.CREATING,
            )

            await self._apply_template(workspace)
            workspace.status = WorkspaceStatus.ACTIVE

            self.workspaces[workspace_id] = workspace
            return workspace

    async def _apply_template(self, workspace: Workspace):
        template = self.templates.get(workspace.config.template)
        if not template:
            return

        for rel_path, content in template.files.items():
            file_path = workspace.path / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)

        for dir_name in template.directories:
            (workspace.path / dir_name).mkdir(parents=True, exist_ok=True)

        for cmd in template.setup_commands:
            try:
                process = await asyncio.create_subprocess_shell(
                    cmd,
                    cwd=workspace.path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await process.communicate()
            except Exception:
                pass

        for key, value in template.environment.items():
            os.environ[key] = value

    async def get_workspace(self, workspace_id: str) -> Workspace | None:
        async with self._lock:
            workspace = self.workspaces.get(workspace_id)
            if workspace:
                workspace.last_accessed = time.time()
            return workspace

    async def list_workspaces(self, status: WorkspaceStatus = None) -> list[Workspace]:
        async with self._lock:
            workspaces = list(self.workspaces.values())
            if status:
                workspaces = [w for w in workspaces if w.status == status]
            return workspaces

    async def delete_workspace(self, workspace_id: str, force: bool = False) -> bool:
        async with self._lock:
            workspace = self.workspaces.get(workspace_id)
            if not workspace:
                return False

            workspace.status = WorkspaceStatus.DELETING

            try:
                if workspace.path.exists():
                    shutil.rmtree(workspace.path)
            except Exception:
                if not force:
                    workspace.status = WorkspaceStatus.ERROR
                    return False

            del self.workspaces[workspace_id]
            return True

    async def pause_workspace(self, workspace_id: str) -> bool:
        async with self._lock:
            workspace = self.workspaces.get(workspace_id)
            if workspace:
                workspace.status = WorkspaceStatus.PAUSED
                return True
        return False

    async def resume_workspace(self, workspace_id: str) -> bool:
        async with self._lock:
            workspace = self.workspaces.get(workspace_id)
            if workspace and workspace.status == WorkspaceStatus.PAUSED:
                workspace.status = WorkspaceStatus.ACTIVE
                return True
        return False

    async def archive_workspace(self, workspace_id: str) -> bool:
        async with self._lock:
            workspace = self.workspaces.get(workspace_id)
            if workspace:
                workspace.status = WorkspaceStatus.ARCHIVED
                return True
        return False

    async def clone_workspace(self, workspace_id: str, new_name: str) -> Workspace:
        async with self._lock:
            workspace = self.workspaces.get(workspace_id)
            if not workspace:
                raise ValueError(f"Workspace not found: {workspace_id}")

            new_config = WorkspaceConfig(
                name=new_name,
                workspace_type=workspace.config.workspace_type,
                base_path=workspace.config.base_path,
                template=workspace.config.template,
                environment=workspace.config.environment.copy(),
            )

            new_workspace = await self.create_workspace(new_config)

            for item in workspace.path.rglob('*'):
                if item.is_file():
                    rel = item.relative_to(workspace.path)
                    dst = new_workspace.path / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dst)

            return new_workspace

    async def start_cleanup(self, interval: float = 3600.0):
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop(interval))

    async def stop_cleanup(self):
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _cleanup_loop(self, interval: float):
        while self._running:
            await asyncio.sleep(interval)
            await self._cleanup_expired()

    async def _cleanup_expired(self):
        now = time.time()
        async with self._lock:
            to_delete = []
            for ws_id, workspace in self.workspaces.items():
                if workspace.config.auto_cleanup:
                    age_hours = (now - workspace.last_accessed) / 3600
                    if age_hours > workspace.config.max_age_hours:
                        to_delete.append(ws_id)

            for ws_id in to_delete:
                workspace = self.workspaces[ws_id]
                workspace.status = WorkspaceStatus.DELETING
                try:
                    if workspace.path.exists():
                        shutil.rmtree(workspace.path)
                except Exception:
                    pass
                del self.workspaces[ws_id]

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_workspaces": len(self.workspaces),
            "active": sum(1 for w in self.workspaces.values() if w.status == WorkspaceStatus.ACTIVE),
            "paused": sum(1 for w in self.workspaces.values() if w.status == WorkspaceStatus.PAUSED),
            "archived": sum(1 for w in self.workspaces.values() if w.status == WorkspaceStatus.ARCHIVED),
            "templates": len(self.templates),
        }


class WorkspaceIsolation:
    def __init__(self, manager: WorkspaceManager):
        self.manager = manager

    async def run_in_workspace(self, workspace_id: str, command: str, env: dict = None) -> dict[str, Any]:
        workspace = await self.manager.get_workspace(workspace_id)
        if not workspace:
            raise ValueError(f"Workspace not found: {workspace_id}")

        merged_env = {**os.environ, **workspace.config.environment, **(env or {})}

        process = await asyncio.create_subprocess_shell(
            command,
            cwd=workspace.path,
            env=merged_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        return {
            "returncode": process.returncode,
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
        }

    async def sync_workspace(self, workspace_id: str, source: str, exclude: list[str] = None):
        workspace = await self.manager.get_workspace(workspace_id)
        if not workspace:
            raise ValueError(f"Workspace not found: {workspace_id}")

        exclude = exclude or ['.git', '__pycache__', 'node_modules', '.venv', 'venv']

        rsync_exclude = ' '.join(f'--exclude={e}' for e in exclude)
        cmd = f"rsync -av {rsync_exclude} {source}/ {workspace.path}/"

        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()


class WorkspaceSnapshot:
    def __init__(self, manager: WorkspaceManager):
        self.manager = manager
        self.snapshots: dict[str, dict] = {}

    async def create_snapshot(self, workspace_id: str, name: str = None) -> str:
        workspace = await self.manager.get_workspace(workspace_id)
        if not workspace:
            raise ValueError(f"Workspace not found: {workspace_id}")

        snapshot_id = hashlib.md5(f"{workspace_id}:{time.time()}".encode()).hexdigest()[:12]
        snapshot_path = self.manager.base_path / ".snapshots" / snapshot_id
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)

        shutil.copytree(workspace.path, snapshot_path)

        snapshot_info = {
            "snapshot_id": snapshot_id,
            "workspace_id": workspace_id,
            "name": name or f"snapshot_{snapshot_id}",
            "created_at": time.time(),
            "path": str(snapshot_path),
            "size": self._get_dir_size(snapshot_path),
        }

        self.snapshots[snapshot_id] = snapshot_info
        return snapshot_id

    def _get_dir_size(self, path: Path) -> int:
        total = 0
        for item in path.rglob('*'):
            if item.is_file():
                total += item.stat().st_size
        return total

    async def restore_snapshot(self, snapshot_id: str, target_workspace_id: str = None) -> bool:
        snapshot = self.snapshots.get(snapshot_id)
        if not snapshot:
            return False

        target_id = target_workspace_id or snapshot["workspace_id"]
        target = await self.manager.get_workspace(target_id)
        if not target:
            return False

        if target.path.exists():
            shutil.rmtree(target.path)

        shutil.copytree(snapshot["path"], target.path)
        return True

    def list_snapshots(self, workspace_id: str = None) -> list[dict]:
        snapshots = list(self.snapshots.values())
        if workspace_id:
            snapshots = [s for s in snapshots if s["workspace_id"] == workspace_id]
        return snapshots
