"""Skill installation, removal, listing, and updates.

Port of pipx-skills with Nexus-branded paths and config integration.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from nexus.skills.constants import DEFAULT_BLACKLIST
from nexus.skills.session import SessionManager
from nexus.skills.index import SkillIndex

log = logging.getLogger(__name__)


def _safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)


def _skills_dir() -> Path:
    cfg = _load_config()
    skills_dir = getattr(cfg, "skills_dir", None)
    if skills_dir:
        p = Path(str(skills_dir)).expanduser()
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        else:
            p = p.resolve()
        return p
    return Path.home() / ".agents" / "skills"


def _load_config():
    from nexus.config import load_config
    return load_config()


def get_agents_home() -> Path:
    return Path.home() / ".agents"


def get_skills_dir() -> Path:
    skills_path = os.environ.get("HERMES_SKILLS_DIR")
    if skills_path:
        return Path(skills_path)
    home = Path.home()
    candidates = [
        home / ".agents" / "skills",
        home / ".hermes" / "skills",
        home / ".openclaw" / "skills",
    ]
    for path in candidates:
        if path.exists():
            return path
    return home / ".agents" / "skills"


def parse_skill_id(skill_id):
    if "/" in skill_id:
        parts = skill_id.split("/")
        if len(parts) == 2:
            return parts[0], parts[1]
    if skill_id == "nwc-agent":
        return "eddieoz", skill_id
    return None, skill_id


def fetch_skill_metadata(owner, name):
    try:
        url = f"https://raw.githubusercontent.com/{owner}/{name}/main/SKILL.md"
        req = _make_request(url, timeout=10)
        content = _read_response(req)
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                frontmatter = content[3:end].strip()
                metadata = {}
                for line in frontmatter.split("\n"):
                    if ":" in line and not line.startswith("#"):
                        key, val = line.split(":", 1)
                        metadata[key.strip()] = val.strip().strip('"').strip("'")
                return metadata
    except Exception:
        pass
    try:
        url = f"https://raw.githubusercontent.com/{owner}/{name}/main/README.md"
        req = _make_request(url, timeout=5)
        content = _read_response(req)
        lines = content.split("\n")
        title = lines[0].replace("# ", "").strip() if lines else name
        return {"name": name, "description": title[:60]}
    except Exception:
        pass
    return None


def _make_request(url, timeout=10):
    from urllib.request import Request, urlopen
    return Request(url, headers={"User-Agent": "nexus/0.1.0"})


def _read_response(req):
    from urllib.request import urlopen
    with urlopen(req, timeout=10) as response:
        return response.read().decode("utf-8")


def install_skill(skill_id, version=None, force=False, cfg=None):
    """Install a skill from GitHub to the skills directory."""
    owner, name = parse_skill_id(skill_id)
    if not owner:
        print(f"Error: Cannot resolve skill '{name}' without owner prefix", file=sys.stderr)
        print(f"Use format: nexus skill install owner/{name}", file=sys.stderr)
        sys.exit(1)

    repo_url = f"https://github.com/{owner}/{name}.git"
    skills_dir = get_skills_dir()
    skill_dir = skills_dir / name

    skills_dir.mkdir(parents=True, exist_ok=True)

    if skill_dir.exists():
        if force:
            print(f"Force removing existing skill at {skill_dir}")
            shutil.rmtree(skill_dir)
        else:
            print(f"Skill '{name}' already installed at {skill_dir}")
            print(f"Run: nexus skill install {skill_id} --force")
            return

    metadata = fetch_skill_metadata(owner, name)
    if metadata:
        desc = metadata.get("description", "N/A")
        if desc and len(desc) > 60:
            desc = desc[:60] + "..."
        print(f"Found skill: {metadata.get('name', name)}")
        print(f"  Description: {desc}")

    print(f"\nInstalling {owner}/{name}...")
    print(f"  Cloning from {repo_url}...")

    clone_cmd = ["git", "clone", "--depth", "1", "--quiet"]
    if version:
        clone_cmd.extend(["--branch", version])
    clone_cmd.extend([repo_url, str(skill_dir)])

    result = subprocess.run(clone_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error cloning: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    git_dir = skill_dir / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir)

    print(f"  -> Installed to {skill_dir}")

    req_file = skill_dir / "requirements.txt"
    if req_file.exists():
        print(f"  Installing Python dependencies...")
        pip_result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "-r", str(req_file)],
            capture_output=True, text=True
        )
        if pip_result.returncode == 0:
            print(f"  Dependencies installed")
        else:
            print(f"  Some dependencies may have failed", file=sys.stderr)

    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        print(f"  Skill manifest verified")
    else:
        print(f"  Warning: No SKILL.md found", file=sys.stderr)

    print(f"\nSuccessfully installed {owner}/{name}")
    print(f"\nNext steps:")
    print(f"  1. Start a new session or run /reload-skills")
    print(f"  2. The skill will be available automatically")


def remove_skill(skill_id):
    _, name = parse_skill_id(skill_id)
    skill_dir = get_skills_dir() / name

    if not skill_dir.exists():
        print(f"Skill '{name}' is not installed", file=sys.stderr)
        sys.exit(1)

    print(f"Removing {name}...")
    shutil.rmtree(skill_dir)
    print(f"Removed {name}")


def list_skills():
    skills_dir = get_skills_dir()
    if not skills_dir.exists():
        print(f"No skills directory at {skills_dir}")
        return

    print(f"Installed skills in {skills_dir}:\n")
    count = 0
    for item in sorted(os.listdir(skills_dir)):
        item_path = skills_dir / item
        if item_path.is_dir() and not item.startswith("."):
            skill_md = item_path / "SKILL.md"
            if skill_md.exists():
                print(f"  + {item}")
                count += 1
            else:
                print(f"  ? {item} (no SKILL.md)")

    if count == 0:
        print("  (no skills installed)")
    else:
        print(f"\n{count} skill(s) installed")


def update_skill(skill_id):
    _, name = parse_skill_id(skill_id)
    skill_dir = get_skills_dir() / name

    if not skill_dir.exists():
        print(f"Skill '{name}' is not installed", file=sys.stderr)
        sys.exit(1)

    print(f"Updating {name}...")
    install_skill(skill_id, force=True)
