"""
Shadow-Broker Repository Scanner - Discovers repos using recency, star-count, and description filters
"""
import threading
import time
import subprocess
import json
import os
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class SortBy(Enum):
    RECENCY = "recency"
    STARS = "stars"
    FORKS = "forks"
    UPDATED = "updated"
    CREATED = "created"


@dataclass
class RepoCandidate:
    repo_id: str
    name: str
    full_name: str
    url: str
    description: str
    stars: int
    forks: int
    language: str
    topics: List[str]
    created_at: str
    updated_at: str
    pushed_at: str
    size_kb: int
    default_branch: str
    license: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


class ShadowBrokerScanner:
    def __init__(self, github_token: str = None, max_results: int = 100):
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN")
        self.max_results = max_results
        self._cache: Dict[str, List[RepoCandidate]] = {}
        self._lock = threading.RLock()
        self._scan_history: List[Dict[str, Any]] = []
    
    def search(self, query: str, language: str = None,
               min_stars: int = 0, max_stars: int = None,
               min_size: int = 0, max_size: int = None,
               topics: List[str] = None,
               sort_by: SortBy = SortBy.STARS,
               limit: int = 50) -> List[RepoCandidate]:
        
        cache_key = f"{query}:{language}:{min_stars}:{max_stars}:{sort_by.value}:{limit}"
        
        with self._lock:
            if cache_key in self._cache:
                return self._cache[cache_key][:limit]
        
        # Build GitHub search query
        gh_query = query
        if language:
            gh_query += f" language:{language}"
        if min_stars > 0:
            gh_query += f" stars:>={min_stars}"
        if max_stars:
            gh_query += f" stars:<={max_stars}"
        if min_size > 0:
            gh_query += f" size:>={min_size}"
        if max_size:
            gh_query += f" size:<={max_size}"
        if topics:
            for topic in topics:
                gh_query += f" topic:{topic}"
        
        candidates = self._search_github(gh_query, sort_by, limit)
        
        with self._lock:
            self._cache[cache_key] = candidates
            self._scan_history.append({
                "query": gh_query,
                "timestamp": time.time(),
                "results": len(candidates)
            })
        
        return candidates[:limit]
    
    def _search_github(self, query: str, sort_by: SortBy, limit: int) -> List[RepoCandidate]:
        candidates = []
        
        try:
            # Use gh CLI if available
            cmd = ["gh", "api", "/search/repositories", "-f", f"q={query}"]
            
            sort_map = {
                SortBy.STARS: "stars",
                SortBy.FORKS: "forks",
                SortBy.UPDATED: "updated",
                SortBy.CREATED: "created"
            }
            cmd.extend(["-f", f"sort={sort_map.get(sort_by, 'stars')}"])
            cmd.extend(["-f", "order=desc"])
            cmd.extend(["-f", f"per_page={min(limit, 100)}"])
            
            env = os.environ.copy()
            if self.github_token:
                env["GH_TOKEN"] = self.github_token
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for item in data.get("items", []):
                    candidate = RepoCandidate(
                        repo_id=str(item["id"]),
                        name=item["name"],
                        full_name=item["full_name"],
                        url=item["html_url"],
                        description=item["description"] or "",
                        stars=item["stargazers_count"],
                        forks=item["forks_count"],
                        language=item["language"] or "Unknown",
                        topics=item.get("topics", []),
                        created_at=item["created_at"],
                        updated_at=item["updated_at"],
                        pushed_at=item["pushed_at"],
                        size_kb=item["size"],
                        default_branch=item["default_branch"],
                        license=item["license"]["name"] if item.get("license") else None,
                        metadata={
                            "open_issues": item["open_issues_count"],
                            "watchers": item["watchers_count"],
                            "archived": item["archived"],
                            "disabled": item["disabled"]
                        }
                    )
                    candidates.append(candidate)
        
        except Exception:
            pass
        
        return candidates
    
    def get_repo_details(self, full_name: str) -> Optional[RepoCandidate]:
        try:
            cmd = ["gh", "api", f"/repos/{full_name}"]
            env = os.environ.copy()
            if self.github_token:
                env["GH_TOKEN"] = self.github_token
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, env=env)
            
            if result.returncode == 0:
                item = json.loads(result.stdout)
                return RepoCandidate(
                    repo_id=str(item["id"]),
                    name=item["name"],
                    full_name=item["full_name"],
                    url=item["html_url"],
                    description=item["description"] or "",
                    stars=item["stargazers_count"],
                    forks=item["forks_count"],
                    language=item["language"] or "Unknown",
                    topics=item.get("topics", []),
                    created_at=item["created_at"],
                    updated_at=item["updated_at"],
                    pushed_at=item["pushed_at"],
                    size_kb=item["size"],
                    default_branch=item["default_branch"],
                    license=item["license"]["name"] if item.get("license") else None,
                    metadata={
                        "open_issues": item["open_issues_count"],
                        "watchers": item["watchers_count"],
                        "archived": item["archived"],
                        "disabled": item["disabled"]
                    }
                )
        except Exception:
            pass
        return None
    
    def search_local(self, root_path: str, pattern: str = "*",
                     max_depth: int = 3) -> List[RepoCandidate]:
        candidates = []
        root = Path(root_path)
        
        for repo_path in root.rglob(pattern):
            if not repo_path.is_dir():
                continue
            
            git_dir = repo_path / ".git"
            if not git_dir.exists():
                continue
            
            try:
                # Get repo info
                result = subprocess.run(
                    ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
                    capture_output=True, text=True, timeout=5
                )
                url = result.stdout.strip() if result.returncode == 0 else ""
                
                result = subprocess.run(
                    ["git", "-C", str(repo_path), "log", "-1", "--format=%H|%s|%an|%ad"],
                    capture_output=True, text=True, timeout=5
                )
                last_commit = result.stdout.strip() if result.returncode == 0 else ""
                
                result = subprocess.run(
                    ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True, text=True, timeout=5
                )
                branch = result.stdout.strip() if result.returncode == 0 else "main"
                
                # Get size
                size = sum(f.stat().st_size for f in repo_path.rglob("*") if f.is_file())
                
                candidate = RepoCandidate(
                    repo_id=str(hash(str(repo_path))),
                    name=repo_path.name,
                    full_name=str(repo_path.relative_to(root)),
                    url=url,
                    description=f"Local repository at {repo_path}",
                    stars=0,
                    forks=0,
                    language=self._detect_language(repo_path),
                    topics=[],
                    created_at="",
                    updated_at="",
                    pushed_at=last_commit.split("|")[-1] if "|" in last_commit else "",
                    size_kb=size // 1024,
                    default_branch=branch,
                    metadata={
                        "local_path": str(repo_path),
                        "last_commit": last_commit
                    }
                )
                candidates.append(candidate)
                
            except Exception:
                continue
        
        return candidates
    
    def _detect_language(self, path: Path) -> str:
        extensions = {}
        for f in path.rglob("*"):
            if f.is_file() and f.suffix:
                ext = f.suffix.lower()
                extensions[ext] = extensions.get(ext, 0) + 1
        
        lang_map = {
            ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
            ".rs": "Rust", ".go": "Go", ".java": "Java", ".cpp": "C++",
            ".c": "C", ".cs": "C#", ".php": "PHP", ".rb": "Ruby"
        }
        
        for ext, count in sorted(extensions.items(), key=lambda x: -x[1]):
            if ext in lang_map:
                return lang_map[ext]
        
        return "Unknown"
    
    def score_candidates(self, candidates: List[RepoCandidate],
                        weights: Dict[str, float] = None) -> List[RepoCandidate]:
        weights = weights or {
            "stars": 0.4,
            "recency": 0.2,
            "activity": 0.2,
            "size": 0.1,
            "language_match": 0.1
        }
        
        now = time.time()
        
        for candidate in candidates:
            score = 0.0
            
            # Stars score (log scale)
            if candidate.stars > 0:
                import math
                score += weights.get("stars", 0.4) * min(1.0, math.log10(candidate.stars + 1) / 5)
            
            # Recency score
            if candidate.pushed_at:
                try:
                    from datetime import datetime
                    pushed = datetime.fromisoformat(candidate.pushed_at.replace("Z", "+00:00"))
                    days_old = (now - pushed.timestamp()) / 86400
                    score += weights.get("recency", 0.2) * max(0, 1 - days_old / 365)
                except Exception:
                    pass
            
            # Activity score (open issues, recent pushes)
            score += weights.get("activity", 0.2) * 0.5  # Placeholder
            
            # Size score (prefer moderate size)
            if candidate.size_kb > 0:
                import math
                size_score = 1.0 / (1.0 + math.log10(candidate.size_kb / 1000))
                score += weights.get("size", 0.1) * size_score
            
            candidate.score = score
        
        candidates.sort(key=lambda c: -c.score)
        return candidates
    
    def clear_cache(self):
        with self._lock:
            self._cache.clear()
    
    def get_scan_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            return self._scan_history[-limit:]


_shadow_broker: Optional[ShadowBrokerScanner] = None

def get_shadow_broker() -> ShadowBrokerScanner:
    global _shadow_broker
    if _shadow_broker is None:
        _shadow_broker = ShadowBrokerScanner()
    return _shadow_broker