import json
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class EpisodeType(Enum):
    TASK_EXECUTION = "task_execution"
    TOOL_INVOCATION = "tool_invocation"
    CODE_ANALYSIS = "code_analysis"
    ERROR_RECOVERY = "error_recovery"
    DECISION = "decision"
    OBSERVATION = "observation"
    PLANNING = "planning"
    REFLECTION = "reflection"
    EXTERNAL_EVENT = "external_event"
    USER_INTERACTION = "user_interaction"


class EpisodeStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class Episode:
    id: str
    episode_type: EpisodeType
    title: str
    description: str
    status: EpisodeStatus = EpisodeStatus.PENDING
    parent_id: str | None = None
    children_ids: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    ended_at: str | None = None
    duration_ms: float | None = None
    embedding: list[float] | None = None
    importance: float = 1.0

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["episode_type"] = self.episode_type.value
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Episode":
        data["episode_type"] = EpisodeType(data["episode_type"])
        data["status"] = EpisodeStatus(data["status"])
        return cls(**data)

    def mark_completed(self, output: dict[str, Any] = None):
        self.status = EpisodeStatus.COMPLETED
        self.ended_at = datetime.utcnow().isoformat()
        if output:
            self.output_data = output
        if self.started_at:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.ended_at)
            self.duration_ms = (end - start).total_seconds() * 1000

    def mark_failed(self, error: str):
        self.status = EpisodeStatus.FAILED
        self.ended_at = datetime.utcnow().isoformat()
        self.error = error
        if self.started_at:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.ended_at)
            self.duration_ms = (end - start).total_seconds() * 1000


class EpisodicStore:
    def __init__(self, storage_path: Path | None = None, max_episodes: int = 10000):
        self.episodes: dict[str, Episode] = {}
        self._type_index: dict[EpisodeType, set[str]] = defaultdict(set)
        self._status_index: dict[EpisodeStatus, set[str]] = defaultdict(set)
        self._tag_index: dict[str, set[str]] = defaultdict(set)
        self._parent_index: dict[str, set[str]] = defaultdict(set)
        self._time_index: list[str] = []
        self.storage_path = storage_path
        self.max_episodes = max_episodes

        if storage_path and storage_path.exists():
            self.load(storage_path)

    def add_episode(self, episode: Episode) -> str:
        if len(self.episodes) >= self.max_episodes:
            self._evict_oldest()

        self.episodes[episode.id] = episode
        self._index_episode(episode)
        return episode.id

    def _index_episode(self, episode: Episode):
        self._type_index[episode.episode_type].add(episode.id)
        self._status_index[episode.status].add(episode.id)
        for tag in episode.tags:
            self._tag_index[tag].add(episode.id)
        if episode.parent_id:
            self._parent_index[episode.parent_id].add(episode.id)
        self._time_index.append(episode.id)

    def _evict_oldest(self):
        if not self._time_index:
            return
        oldest_id = self._time_index.pop(0)
        self.remove_episode(oldest_id)

    def get_episode(self, episode_id: str) -> Episode | None:
        return self.episodes.get(episode_id)

    def get_episodes_by_type(self, episode_type: EpisodeType) -> list[Episode]:
        ids = self._type_index.get(episode_type, set())
        return [self.episodes[eid] for eid in ids if eid in self.episodes]

    def get_episodes_by_status(self, status: EpisodeStatus) -> list[Episode]:
        ids = self._status_index.get(status, set())
        return [self.episodes[eid] for eid in ids if eid in self.episodes]

    def get_episodes_by_tag(self, tag: str) -> list[Episode]:
        ids = self._tag_index.get(tag, set())
        return [self.episodes[eid] for eid in ids if eid in self.episodes]

    def get_children(self, parent_id: str) -> list[Episode]:
        ids = self._parent_index.get(parent_id, set())
        return [self.episodes[eid] for eid in ids if eid in self.episodes]

    def get_recent(self, limit: int = 100, episode_type: EpisodeType = None) -> list[Episode]:
        ids = self._time_index[-limit:]
        episodes = [self.episodes[eid] for eid in reversed(ids) if eid in self.episodes]
        if episode_type:
            episodes = [e for e in episodes if e.episode_type == episode_type]
        return episodes

    def search(self, query: str, limit: int = 50) -> list[Episode]:
        query_lower = query.lower()
        results = []
        for episode in self.episodes.values():
            if (query_lower in episode.title.lower() or
                query_lower in episode.description.lower() or
                any(query_lower in str(v).lower() for v in episode.context.values()) or
                any(query_lower in str(v).lower() for v in episode.input_data.values()) or
                any(query_lower in str(v).lower() for v in episode.output_data.values())):
                results.append(episode)
                if len(results) >= limit:
                    break
        return results

    def search_by_embedding(self, embedding: list[float], limit: int = 10, threshold: float = 0.7) -> list[Episode]:
        import numpy as np

        query_vec = np.array(embedding)
        scored = []
        for episode in self.episodes.values():
            if episode.embedding is not None:
                ep_vec = np.array(episode.embedding)
                similarity = np.dot(query_vec, ep_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(ep_vec))
                if similarity >= threshold:
                    scored.append((similarity, episode))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [ep for _, ep in scored[:limit]]

    def update_episode(self, episode_id: str, **kwargs) -> bool:
        if episode_id not in self.episodes:
            return False
        episode = self.episodes[episode_id]

        old_status = episode.status
        old_tags = set(episode.tags)

        for key, value in kwargs.items():
            if hasattr(episode, key):
                setattr(episode, key, value)

        if "status" in kwargs and kwargs["status"] != old_status:
            self._status_index[old_status].discard(episode_id)
            self._status_index[episode.status].add(episode_id)

        if "tags" in kwargs:
            new_tags = set(kwargs["tags"])
            for tag in old_tags - new_tags:
                self._tag_index[tag].discard(episode_id)
            for tag in new_tags - old_tags:
                self._tag_index[tag].add(episode_id)

        return True

    def decay_importance(self, factor: float = 0.95) -> None:
        """Decay importance of all episodes by factor."""
        for ep in self.episodes.values():
            ep.importance = max(0.0, ep.importance * factor)

    def prune(self, threshold: float = 0.1) -> int:
        """Remove episodes below importance threshold. Returns count."""
        to_remove = [eid for eid, ep in self.episodes.items() if ep.importance < threshold]
        for eid in to_remove:
            self.remove_episode(eid)
        return len(to_remove)

    def remove_episode(self, episode_id: str) -> bool:
        if episode_id not in self.episodes:
            return False
        episode = self.episodes[episode_id]

        self._type_index[episode.episode_type].discard(episode_id)
        self._status_index[episode.status].discard(episode_id)
        for tag in episode.tags:
            self._tag_index[tag].discard(episode_id)
        if episode.parent_id:
            self._parent_index[episode.parent_id].discard(episode_id)
        if episode_id in self._time_index:
            self._time_index.remove(episode_id)

        for child_id in episode.children_ids:
            child = self.episodes.get(child_id)
            if child:
                child.parent_id = None

        del self.episodes[episode_id]
        return True

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_episodes": len(self.episodes),
            "by_type": {k.value: len(v) for k, v in self._type_index.items()},
            "by_status": {k.value: len(v) for k, v in self._status_index.items()},
            "by_tag": {k: len(v) for k, v in self._tag_index.items()},
        }

    def save(self, path: Path = None):
        path = path or self.storage_path
        if not path:
            return
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "episodes": {k: v.to_dict() for k, v in self.episodes.items()},
        }
        path.write_text(json.dumps(data, indent=2))

    def load(self, path: Path):
        data = json.loads(path.read_text())
        for eid, edata in data.get("episodes", {}).items():
            episode = Episode.from_dict(edata)
            self.episodes[eid] = episode
            self._index_episode(episode)

    def clear(self):
        self.episodes.clear()
        self._type_index.clear()
        self._status_index.clear()
        self._tag_index.clear()
        self._parent_index.clear()
        self._time_index.clear()
