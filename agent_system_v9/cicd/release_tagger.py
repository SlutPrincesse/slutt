"""
Release Tagger - Automated release tagging and versioning
"""
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class VersionScheme(Enum):
    SEMVER = "semver"
    CALVER = "calver"
    SERIAL = "serial"
    CUSTOM = "custom"


class ReleaseType(Enum):
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"
    PRE_RELEASE = "pre_release"
    BUILD = "build"


@dataclass
class Version:
    major: int
    minor: int
    patch: int
    pre_release: str = ""
    build: str = ""

    def __str__(self) -> str:
        version = f"{self.major}.{self.minor}.{self.patch}"
        if self.pre_release:
            version += f"-{self.pre_release}"
        if self.build:
            version += f"+{self.build}"
        return version

    @classmethod
    def parse(cls, version_str: str) -> 'Version':
        pattern = r'^(\d+)\.(\d+)\.(\d+)(?:-([^+]+))?(?:\+(.+))?$'
        match = re.match(pattern, version_str)
        if match:
            major, minor, patch, pre, build = match.groups()
            return cls(int(major), int(minor), int(patch), pre or "", build or "")
        return cls(0, 0, 0)


@dataclass
class ReleaseConfig:
    scheme: VersionScheme = VersionScheme.SEMVER
    branch_patterns: dict[str, ReleaseType] = field(default_factory=lambda: {
        "main": ReleaseType.PATCH,
        "release/*": ReleaseType.MINOR,
        "hotfix/*": ReleaseType.PATCH,
        "feature/*": ReleaseType.PRE_RELEASE,
    })
    tag_prefix: str = "v"
    auto_tag: bool = True
    sign_tags: bool = False
    gpg_key: str = ""
    changelog_path: str = "CHANGELOG.md"


@dataclass
class ReleaseNote:
    version: Version
    date: float = field(default_factory=time.time)
    commits: list[dict[str, Any]] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    fixes: list[str] = field(default_factory=list)
    breaking_changes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Release:
    version: Version
    tag_name: str
    commit_hash: str
    notes: ReleaseNote
    created_at: float = field(default_factory=time.time)
    published: bool = False
    assets: list[str] = field(default_factory=list)


class ReleaseTagger:
    def __init__(self, config: ReleaseConfig = None, repo_path: str = "."):
        self.config = config or ReleaseConfig()
        self.repo_path = Path(repo_path)
        self.releases: list[Release] = []
        self._load_releases()

    def _load_releases(self):
        try:
            result = subprocess.run(
                ["git", "tag", "-l", f"{self.config.tag_prefix}*"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )
            tags = result.stdout.strip().split('\n')

            for tag in tags:
                if tag:
                    version_str = tag[len(self.config.tag_prefix):]
                    version = Version.parse(version_str)
                    commit = self._get_commit_for_tag(tag)
                    self.releases.append(Release(
                        version=version,
                        tag_name=tag,
                        commit_hash=commit,
                        notes=self._generate_notes(version),
                    ))
        except Exception:
            pass

    def _get_commit_for_tag(self, tag: str) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-list", "-n", "1", tag],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()
        except Exception:
            return ""

    def _get_commits_since(self, since_tag: str = None) -> list[dict[str, Any]]:
        try:
            if since_tag:
                cmd = ["git", "log", f"{since_tag}..HEAD", "--pretty=format:%H|%s|%an|%ad"]
            else:
                cmd = ["git", "log", "-n", "50", "--pretty=format:%H|%s|%an|%ad"]

            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )

            commits = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split('|', 3)
                    if len(parts) == 4:
                        commits.append({
                            "hash": parts[0],
                            "message": parts[1],
                            "author": parts[2],
                            "date": parts[3],
                        })
            return commits
        except Exception:
            return []

    def _generate_notes(self, version: Version) -> ReleaseNote:
        previous = self._get_previous_version(version)
        commits = self._get_commits_since(f"{self.config.tag_prefix}{previous}" if previous else None)

        note = ReleaseNote(version=version, commits=commits)

        for commit in commits:
            msg = commit["message"].lower()
            if any(kw in msg for kw in ["feat", "feature"]):
                note.features.append(commit["message"])
            elif any(kw in msg for kw in ["fix", "bug"]):
                note.fixes.append(commit["message"])
            elif "breaking" in msg or "break" in msg:
                note.breaking_changes.append(commit["message"])

        return note

    def _get_previous_version(self, version: Version) -> Version | None:
        sorted_releases = sorted(self.releases, key=lambda r: (r.version.major, r.version.minor, r.version.patch))
        for release in reversed(sorted_releases):
            if (release.version.major, release.version.minor, release.version.patch) < (version.major, version.minor, version.patch):
                return release.version
        return None

    def determine_release_type(self, branch: str, commits: list[dict] = None) -> ReleaseType:
        for pattern, rtype in self.config.branch_patterns.items():
            if self._match_branch(branch, pattern):
                return rtype

        if commits:
            for commit in commits:
                msg = commit.get("message", "").lower()
                if "breaking" in msg or "break" in msg:
                    return ReleaseType.MAJOR
                if any(kw in msg for kw in ["feat", "feature"]):
                    return ReleaseType.MINOR

        return ReleaseType.PATCH

    def _match_branch(self, branch: str, pattern: str) -> bool:
        if pattern.endswith('/*'):
            prefix = pattern[:-2]
            return branch.startswith(prefix + '/')
        return branch == pattern

    def calculate_next_version(self, current: Version, release_type: ReleaseType) -> Version:
        if release_type == ReleaseType.MAJOR:
            return Version(current.major + 1, 0, 0)
        if release_type == ReleaseType.MINOR:
            return Version(current.major, current.minor + 1, 0)
        if release_type == ReleaseType.PATCH:
            return Version(current.major, current.minor, current.patch + 1)
        if release_type == ReleaseType.PRE_RELEASE:
            return Version(current.major, current.minor, current.patch, "rc.1")
        return Version(current.major, current.minor, current.patch + 1)

    def create_release(
        self,
        branch: str = None,
        release_type: ReleaseType = None,
        custom_version: Version = None,
    ) -> Release:
        if not branch:
            branch = self._get_current_branch()

        current = self.get_latest_version()

        if custom_version:
            next_version = custom_version
        else:
            if not release_type:
                commits = self._get_commits_since(f"{self.config.tag_prefix}{current}" if current else None)
                release_type = self.determine_release_type(branch, commits)
            next_version = self.calculate_next_version(current, release_type)

        tag_name = f"{self.config.tag_prefix}{next_version}"

        try:
            subprocess.run(
                ["git", "tag", "-a", tag_name, "-m", f"Release {tag_name}"],
                cwd=self.repo_path,
                check=True,
            )

            if self.config.sign_tags:
                subprocess.run(
                    ["git", "tag", "-s", tag_name, "-m", f"Release {tag_name}"],
                    cwd=self.repo_path,
                    check=True,
                )
        except subprocess.CalledProcessError:
            pass

        commit_hash = self._get_current_commit()
        notes = self._generate_notes(next_version)

        release = Release(
            version=next_version,
            tag_name=tag_name,
            commit_hash=commit_hash,
            notes=notes,
        )

        self.releases.append(release)
        return release

    def _get_current_branch(self) -> str:
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()
        except Exception:
            return "main"

    def _get_current_commit(self) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()
        except Exception:
            return ""

    def get_latest_version(self) -> Version:
        if not self.releases:
            return Version(0, 0, 0)
        return max(self.releases, key=lambda r: (r.version.major, r.version.minor, r.version.patch)).version

    def get_release(self, version: Version) -> Release | None:
        for release in self.releases:
            if release.version == version:
                return release
        return None

    def list_releases(self) -> list[Release]:
        return sorted(self.releases, key=lambda r: (r.version.major, r.version.minor, r.version.patch), reverse=True)

    def update_changelog(self, release: Release):
        if not self.config.changelog_path:
            return

        changelog_path = self.repo_path / self.config.changelog_path

        entry = f"\n## [{release.version}] - {time.strftime('%Y-%m-%d', time.localtime(release.created_at))}\n"

        if release.notes.features:
            entry += "\n### Added\n"
            for feat in release.notes.features:
                entry += f"- {feat}\n"

        if release.notes.fixes:
            entry += "\n### Fixed\n"
            for fix in release.notes.fixes:
                entry += f"- {fix}\n"

        if release.notes.breaking_changes:
            entry += "\n### Breaking Changes\n"
            for breaking in release.notes.breaking_changes:
                entry += f"- {breaking}\n"

        if changelog_path.exists():
            content = changelog_path.read_text()
            lines = content.split('\n')
            insert_idx = 1
            for i, line in enumerate(lines):
                if line.startswith('## ['):
                    insert_idx = i
                    break
            lines.insert(insert_idx, entry)
            changelog_path.write_text('\n'.join(lines))
        else:
            changelog_path.write_text(f"# Changelog{entry}\n")

    def push_tags(self, remote: str = "origin"):
        try:
            subprocess.run(
                ["git", "push", remote, "--tags"],
                cwd=self.repo_path,
                check=True,
            )
        except subprocess.CalledProcessError:
            pass


class VersionCalculator:
    def __init__(self, scheme: VersionScheme = VersionScheme.SEMVER):
        self.scheme = scheme

    def increment(self, version: Version, release_type: ReleaseType) -> Version:
        if self.scheme == VersionScheme.SEMVER:
            if release_type == ReleaseType.MAJOR:
                return Version(version.major + 1, 0, 0)
            if release_type == ReleaseType.MINOR:
                return Version(version.major, version.minor + 1, 0)
            if release_type == ReleaseType.PATCH:
                return Version(version.major, version.minor, version.patch + 1)
        elif self.scheme == VersionScheme.CALVER:
            now = time.localtime()
            return Version(now.tm_year, now.tm_mon, now.tm_mday)
        elif self.scheme == VersionScheme.SERIAL:
            return Version(version.major, version.minor, version.patch + 1)

        return version

    def compare(self, v1: Version, v2: Version) -> int:
        t1 = (v1.major, v1.minor, v1.patch)
        t2 = (v2.major, v2.minor, v2.patch)
        if t1 < t2: return -1
        if t1 > t2: return 1
        return 0


class ReleaseAutomator:
    def __init__(self, tagger: ReleaseTagger):
        self.tagger = tagger
        self.rules: list[Callable] = []

    def add_rule(self, condition: Callable, action: Callable):
        self.rules.append((condition, action))

    async def check_and_release(self, branch: str = None):
        for condition, action in self.rules:
            if condition(self.tagger, branch):
                await action(self.tagger, branch)


class GitHubReleasePublisher:
    def __init__(self, token: str, repo: str):
        self.token = token
        self.repo = repo

    async def publish(self, release: Release) -> bool:
        return True


class GitLabReleasePublisher:
    def __init__(self, token: str, project_id: str):
        self.token = token
        self.project_id = project_id

    async def publish(self, release: Release) -> bool:
        return True
