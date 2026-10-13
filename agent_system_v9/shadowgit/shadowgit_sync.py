"""
Shadow Git Sync - Remote synchronization and push/pull operations
"""
from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .shadowgit_index import ShadowIndex

logger = logging.getLogger(__name__)


class SyncDirection(Enum):
    """Direction of sync operation."""
    PUSH = "push"
    PULL = "pull"
    FETCH = "fetch"


class SyncStatus(Enum):
    """Status of sync operation."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CONFLICT = "conflict"


class RemoteProtocol(Enum):
    """Supported remote protocols."""
    HTTPS = "https"
    SSH = "ssh"
    GIT = "git"
    LOCAL = "local"


@dataclass
class RemoteConfig:
    """Configuration for a remote repository."""
    name: str
    url: str
    protocol: RemoteProtocol = RemoteProtocol.HTTPS
    username: str | None = None
    token: str | None = None
    ssh_key_path: str | None = None
    fetch_refspec: str = "+refs/heads/*:refs/remotes/{name}/*"
    push_refspec: str = "refs/heads/*:refs/heads/*"
    verify_ssl: bool = True
    timeout: int = 300


@dataclass
class SyncOptions:
    """Options for sync operation."""
    direction: SyncDirection
    remote_name: str
    refspec: str | None = None
    force: bool = False
    prune: bool = False
    tags: bool = False
    atomic: bool = True
    dry_run: bool = False
    progress_callback: Any = None


@dataclass
class SyncResult:
    """Result of a sync operation."""
    operation_id: str
    remote_name: str
    direction: SyncDirection
    status: SyncStatus
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    duration: float = 0.0
    objects_transferred: int = 0
    bytes_transferred: int = 0
    refs_updated: list[str] = field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def complete(self, success: bool = True, error: str | None = None):
        """Mark sync as completed."""
        self.completed_at = datetime.now()
        self.duration = (self.completed_at - self.started_at).total_seconds()
        self.status = SyncStatus.COMPLETED if success else SyncStatus.FAILED
        self.error = error


@dataclass
class SyncConflict:
    """Represents a sync conflict."""
    conflict_id: str
    local_ref: str
    remote_ref: str
    local_oid: str
    remote_oid: str
    conflict_type: str  # divergent, deleted, modified
    resolution: str | None = None
    resolved: bool = False


class ShadowGitSync:
    """
    Shadow Git synchronization engine.
    Handles push, pull, fetch operations with remote repositories.
    """

    def __init__(self, shadow_git, index: ShadowIndex):
        """
        Initialize sync engine.

        Args:
            shadow_git: Parent ShadowGit instance
            index: ShadowIndex instance for object storage
        """
        self._shadow_git = shadow_git
        self._index = index
        self._remotes: dict[str, RemoteConfig] = {}
        self._sync_history: list[SyncResult] = []
        self._active_syncs: dict[str, SyncResult] = {}
        self._conflicts: dict[str, SyncConflict] = {}

    # Remote management
    def add_remote(self, config: RemoteConfig) -> None:
        """Add a remote repository."""
        self._remotes[config.name] = config
        logger.info(f"Added remote: {config.name} -> {config.url}")

    def remove_remote(self, name: str) -> bool:
        """Remove a remote repository."""
        if name in self._remotes:
            del self._remotes[name]
            logger.info(f"Removed remote: {name}")
            return True
        return False

    def get_remote(self, name: str) -> RemoteConfig | None:
        """Get remote configuration."""
        return self._remotes.get(name)

    def list_remotes(self) -> list[RemoteConfig]:
        """List all configured remotes."""
        return list(self._remotes.values())

    def update_remote_url(self, name: str, url: str) -> bool:
        """Update remote URL."""
        if name in self._remotes:
            self._remotes[name].url = url
            return True
        return False

    # Sync operations
    async def push(  # noqa: PLR0913
        self,
        remote_name: str,
        refspec: str | None = None,
        force: bool = False,
        tags: bool = False,
        atomic: bool = True,
        dry_run: bool = False,
        progress_callback: Any = None
    ) -> SyncResult:
        """Push commits to remote."""
        options = SyncOptions(
            direction=SyncDirection.PUSH,
            remote_name=remote_name,
            refspec=refspec,
            force=force,
            tags=tags,
            atomic=atomic,
            dry_run=dry_run,
            progress_callback=progress_callback
        )
        return await self._execute_sync(options)

    async def pull(  # noqa: PLR0913
        self,
        remote_name: str,
        refspec: str | None = None,
        force: bool = False,
        prune: bool = False,
        tags: bool = False,
        progress_callback: Any = None
    ) -> SyncResult:
        """Pull commits from remote."""
        options = SyncOptions(
            direction=SyncDirection.PULL,
            remote_name=remote_name,
            refspec=refspec,
            force=force,
            prune=prune,
            tags=tags,
            progress_callback=progress_callback
        )
        return await self._execute_sync(options)

    async def fetch(
        self,
        remote_name: str,
        refspec: str | None = None,
        prune: bool = False,
        tags: bool = False,
        progress_callback: Any = None
    ) -> SyncResult:
        """Fetch from remote without merging."""
        options = SyncOptions(
            direction=SyncDirection.FETCH,
            remote_name=remote_name,
            refspec=refspec,
            prune=prune,
            tags=tags,
            progress_callback=progress_callback
        )
        return await self._execute_sync(options)

    async def _execute_sync(self, options: SyncOptions) -> SyncResult:
        """Execute sync operation."""
        remote = self._remotes.get(options.remote_name)
        if not remote:
            raise ValueError(f"Remote not found: {options.remote_name}")

        operation_id = f"sync_{options.direction.value}_{options.remote_name}_{int(datetime.now().timestamp())}"
        result = SyncResult(
            operation_id=operation_id,
            remote_name=options.remote_name,
            direction=options.direction
        )

        self._active_syncs[operation_id] = result

        await self._run_sync_operation(remote, options, result, operation_id)

        return result

    async def _run_sync_operation(
        self,
        remote: RemoteConfig,
        options: SyncOptions,
        result: SyncResult,
        operation_id: str
    ):
        """Execute the sync operation based on direction."""
        try:
            if options.direction == SyncDirection.PUSH:
                await self._push_impl(remote, options, result)
            elif options.direction == SyncDirection.PULL:
                await self._pull_impl(remote, options, result)
            elif options.direction == SyncDirection.FETCH:
                await self._fetch_impl(remote, options, result)

            result.complete(success=True)
            logger.info(f"Sync completed: {operation_id}")

        except Exception as e:
            logger.exception(f"Sync failed: {operation_id}")
            result.complete(success=False, error=str(e))

        finally:
            self._sync_history.append(result)
            if operation_id in self._active_syncs:
                del self._active_syncs[operation_id]

    async def _push_impl(self, remote: RemoteConfig, options: SyncOptions, result: SyncResult):
        """Implementation of push operation."""
        if options.progress_callback:
            await options.progress_callback(0.1, "Preparing push...")

        # Get local refs to push
        local_refs = await self._get_local_refs(options.refspec)

        if options.progress_callback:
            await options.progress_callback(0.3, "Compressing objects...")

        # Compress and prepare objects
        objects_to_send = await self._prepare_objects_for_push(local_refs)

        if options.progress_callback:
            await options.progress_callback(0.5, f"Sending {len(objects_to_send)} objects...")

        if not options.dry_run:
            # Send objects to remote
            await self._send_objects(remote, objects_to_send)
            result.objects_transferred = len(objects_to_send)
            result.bytes_transferred = sum(len(obj) for obj in objects_to_send)

            # Update remote refs
            await self._update_remote_refs(remote, local_refs, options.force)
            result.refs_updated = list(local_refs.keys())

        if options.progress_callback:
            await options.progress_callback(1.0, "Push complete")

    async def _pull_impl(self, remote: RemoteConfig, options: SyncOptions, result: SyncResult):
        """Implementation of pull operation."""
        # Fetch first
        fetch_result = await self._fetch_impl(remote, SyncOptions(
            direction=SyncDirection.FETCH,
            remote_name=options.remote_name,
            refspec=options.refspec,
            prune=options.prune,
            tags=options.tags,
            progress_callback=options.progress_callback
        ), result)

        if fetch_result.status != SyncStatus.COMPLETED:
            return

        if options.progress_callback:
            await options.progress_callback(0.6, "Merging changes...")

        # Merge fetched changes
        merge_result = await self._merge_fetched_changes(remote, options)

        result.refs_updated = merge_result.get("refs_updated", [])
        result.objects_transferred = merge_result.get("objects_received", 0)

    async def _fetch_impl(self, remote: RemoteConfig, options: SyncOptions, result: SyncResult) -> SyncResult:
        """Implementation of fetch operation."""
        if options.progress_callback:
            await options.progress_callback(0.1, "Connecting to remote...")

        # Get remote refs
        remote_refs = await self._get_remote_refs(remote, options.refspec)

        if options.progress_callback:
            await options.progress_callback(0.3, f"Fetching {len(remote_refs)} refs...")

        # Fetch missing objects
        missing_objects = await self._find_missing_objects(remote_refs)

        if options.progress_callback:
            await options.progress_callback(0.5, f"Downloading {len(missing_objects)} objects...")

        if not options.dry_run and missing_objects:
            await self._download_objects(remote, missing_objects)
            result.objects_transferred = len(missing_objects)
            result.bytes_transferred = sum(obj.get("size", 0) for obj in missing_objects)

        # Update remote tracking refs
        if not options.dry_run:
            await self._update_tracking_refs(remote, remote_refs, options.prune)
            result.refs_updated = list(remote_refs.keys())

        if options.progress_callback:
            await options.progress_callback(1.0, "Fetch complete")

        return result

    # Helper methods
    @staticmethod
    async def _get_local_refs(refspec: str | None) -> dict[str, str]:
        """Get local refs matching refspec."""
        # This would integrate with ShadowGit's ref storage
        refs = {}
        if refspec:
            # Parse refspec and get matching refs
            pass
        return refs

    @staticmethod
    async def _get_remote_refs(_remote: RemoteConfig, _refspec: str | None) -> dict[str, str]:
        """Get refs from remote repository."""
        # This would use git protocol (HTTP/SSH) to fetch refs
        # For now, return empty dict as placeholder
        return {}

    @staticmethod
    async def _prepare_objects_for_push(_local_refs: dict[str, str]) -> list[bytes]:
        """Prepare objects for push (create packfile)."""
        # This would create a packfile with necessary objects
        return []

    @staticmethod
    async def _send_objects(_remote: RemoteConfig, _objects: list[bytes]):
        """Send objects to remote via git protocol."""
        # Implementation would use git push protocol
        pass

    @staticmethod
    async def _find_missing_objects(_remote_refs: dict[str, str]) -> list[dict]:
        """Find objects we don't have locally."""
        return []

    @staticmethod
    async def _download_objects(_remote: RemoteConfig, _objects: list[dict]):
        """Download objects from remote."""
        pass

    @staticmethod
    async def _update_remote_refs(_remote: RemoteConfig, _refs: dict[str, str], _force: bool):
        """Update refs on remote."""
        pass

    @staticmethod
    async def _update_tracking_refs(_remote: RemoteConfig, _refs: dict[str, str], _prune: bool):
        """Update local tracking refs."""
        pass

    @staticmethod
    async def _merge_fetched_changes(_remote: RemoteConfig, _options: SyncOptions) -> dict:
        """Merge fetched changes into local branches."""
        return {"refs_updated": [], "objects_received": 0}

    # Conflict resolution
    def register_conflict(self, conflict: SyncConflict) -> None:
        """Register a sync conflict."""
        self._conflicts[conflict.conflict_id] = conflict

    def get_conflict(self, conflict_id: str) -> SyncConflict | None:
        """Get a conflict by ID."""
        return self._conflicts.get(conflict_id)

    def list_conflicts(self, resolved: bool | None = None) -> list[SyncConflict]:
        """List conflicts."""
        conflicts = list(self._conflicts.values())
        if resolved is not None:
            conflicts = [c for c in conflicts if c.resolved == resolved]
        return conflicts

    def resolve_conflict(self, conflict_id: str, resolution: str) -> bool:
        """Mark conflict as resolved."""
        conflict = self._conflicts.get(conflict_id)
        if conflict:
            conflict.resolution = resolution
            conflict.resolved = True
            return True
        return False

    # History and status
    def get_sync_history(self, limit: int = 50) -> list[SyncResult]:
        """Get sync history."""
        return self._sync_history[-limit:]

    def get_active_syncs(self) -> list[SyncResult]:
        """Get currently active sync operations."""
        return list(self._active_syncs.values())

    def get_last_sync(self, remote_name: str) -> SyncResult | None:
        """Get last sync for a remote."""
        for result in reversed(self._sync_history):
            if result.remote_name == remote_name:
                return result
        return None


class ShadowGitLFS:
    """
    Shadow Git Large File Storage support.
    Handles large binary files separately from the main repository.
    """

    def __init__(self, shadow_git, sync: ShadowGitSync):
        self._shadow_git = shadow_git
        self._sync = sync
        self._lfs_config: dict[str, Any] = {}
        self._tracked_patterns: list[str] = []

    def configure_lfs(self, endpoint: str, config: dict[str, Any] | None = None):
        """Configure LFS endpoint."""
        self._lfs_config = {
            "endpoint": endpoint,
            **(config or {})
        }

    def track(self, pattern: str):
        """Track file pattern with LFS."""
        if pattern not in self._tracked_patterns:
            self._tracked_patterns.append(pattern)

    def untrack(self, pattern: str):
        """Stop tracking pattern with LFS."""
        if pattern in self._tracked_patterns:
            self._tracked_patterns.remove(pattern)

    def is_tracked(self, filepath: str) -> bool:
        """Check if file should be tracked by LFS."""
        return any(fnmatch.fnmatch(filepath, pattern) for pattern in self._tracked_patterns)

    async def upload_lfs_objects(self, remote_name: str, objects: list[dict]) -> dict:  # noqa: PLR6301
        """Upload LFS objects to remote."""
        # Implementation would use LFS API
        return {"uploaded": len(objects)}

    async def download_lfs_objects(self, remote_name: str, objects: list[dict]) -> dict:  # noqa: PLR6301
        """Download LFS objects from remote."""
        # Implementation would use LFS API
        return {"downloaded": len(objects)}


__all__ = [
    "ShadowGitSync",
    "ShadowGitLFS",
    "SyncDirection",
    "SyncStatus",
    "RemoteProtocol",
    "RemoteConfig",
    "SyncOptions",
    "SyncResult",
    "SyncConflict",
]
