#!/usr/bin/env python3
"""
pipx-skills - Python-native skill installer for Hermes/OpenClaw agents

Usage:
    pipx-skills add eddieoz/nwc-agent
    pipx-skills add owner/repo --version v1.0.0 --force
    pipx-skills list
    pipx-skills remove nwc-agent

This is the Python equivalent of `npx skills add` but for pure Python projects.
It installs skills to ~/.agents/skills/ by default (universal location for all agents).
"""
import argparse
import os
import subprocess
import sys
from urllib.request import urlopen, Request
from urllib.error import HTTPError

def get_agents_home():
    """Get agents home directory."""
    return os.path.join(os.path.expanduser("~"), ".agents")

def get_skills_dir():
    """Get skills directory from env or default.
    
    Priority:
    1. HERMES_SKILLS_DIR env var (for backward compat)
    2. Existing ~/.agents/skills
    3. Existing ~/.hermes/skills (Hermes)
    4. Existing ~/.openclaw/skills (OpenClaw)
    5. Default: ~/.agents/skills (universal)
    """
    # Priority 1: Environment variable
    skills_path = os.environ.get("HERMES_SKILLS_DIR")
    if skills_path:
        return skills_path
    
    # Priority 2-4: Check existing installations
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, ".agents", "skills"),
        os.path.join(home, ".hermes", "skills"),
        os.path.join(home, ".openclaw", "skills"),
    ]
    
    for path in candidates:
        if os.path.exists(path):
            return path
    
    # Priority 5: Default to universal ~/.agents/skills
    return os.path.join(get_agents_home(), "skills")

def parse_skill_id(skill_id):
    """Parse skill ID like 'eddieoz/nwc-agent' or 'nwc-agent'."""
    if "/" in skill_id:
        parts = skill_id.split("/")
        if len(parts) == 2:
            return parts[0], parts[1]
    # Try known owners
    if skill_id == "nwc-agent":
        return "eddieoz", skill_id
    return None, skill_id

def fetch_skill_metadata(owner, name):
    """Fetch skill metadata from GitHub."""
    try:
        url = f"https://raw.githubusercontent.com/{owner}/{name}/main/SKILL.md"
        req = Request(url, headers={"User-Agent": "pipx-skills/1.0"})
        with urlopen(req, timeout=10) as response:
            content = response.read().decode('utf-8')
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
    # Try README.md as fallback
    try:
        url = f"https://raw.githubusercontent.com/{owner}/{name}/main/README.md"
        req = Request(url, headers={"User-Agent": "pipx-skills/1.0"})
        with urlopen(req, timeout=5) as response:
            content = response.read().decode('utf-8')
            lines = content.split("\n")
            title = lines[0].replace("# ", "").strip() if lines else name
            return {"name": name, "description": title[:60]}
    except Exception:
        pass
    return None

def install_skill(skill_id, version=None, force=False):
    """Install a skill from GitHub to the skills directory."""
    owner, name = parse_skill_id(skill_id)
    
    if not owner:
        print(f"Error: Cannot resolve skill '{name}' without owner prefix", file=sys.stderr)
        print(f"Use format: pipx-skills add owner/{name}", file=sys.stderr)
        print(f"Example: pipx-skills add eddieoz/nwc-agent", file=sys.stderr)
        sys.exit(1)
    
    repo_url = f"https://github.com/{owner}/{name}.git"
    skills_dir = get_skills_dir()
    skill_dir = os.path.join(skills_dir, name)
    
    os.makedirs(skills_dir, exist_ok=True)
    
    # Check if already exists
    if os.path.exists(skill_dir):
        if force:
            print(f"Force removing existing skill at {skill_dir}")
            subprocess.run(["rm", "-rf", skill_dir], check=True)
        else:
            print(f"✗ Skill '{name}' already installed at {skill_dir}")
            print(f"Run: pipx-skills add {skill_id} --force")
            return
    
    # Fetch metadata
    metadata = fetch_skill_metadata(owner, name)
    if metadata:
        desc = metadata.get('description', 'N/A')
        if desc and len(desc) > 60:
            desc = desc[:60] + "..."
        print(f"Found skill: {metadata.get('name', name)}")
        print(f"  Description: {desc}")
    
    print(f"\nInstalling {owner}/{name}...")
    print(f"  Cloning from {repo_url}...")
    
    # Clone
    clone_cmd = ["git", "clone", "--depth", "1", "--quiet"]
    if version:
        clone_cmd.extend(["--branch", version])
    clone_cmd.extend([repo_url, skill_dir])
    
    result = subprocess.run(clone_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"✗ Error cloning: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    
    # Remove .git to save space
    git_dir = os.path.join(skill_dir, ".git")
    if os.path.exists(git_dir):
        subprocess.run(["rm", "-rf", git_dir], capture_output=True)
    
    print(f"  → Installed to {skill_dir}")
    
    # Install dependencies
    req_file = os.path.join(skill_dir, "requirements.txt")
    if os.path.exists(req_file):
        print(f"  Installing Python dependencies...")
        pip_result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "-r", req_file],
            capture_output=True, text=True
        )
        if pip_result.returncode == 0:
            print(f"  ✓ Dependencies installed")
        else:
            print(f"  ⚠ Some dependencies may have failed", file=sys.stderr)
    
    # Verify SKILL.md
    skill_md = os.path.join(skill_dir, "SKILL.md")
    if os.path.exists(skill_md):
        print(f"  ✓ Skill manifest verified")
    else:
        print(f"  ⚠ Warning: No SKILL.md found", file=sys.stderr)
    
    print(f"\n✓ Successfully installed {owner}/{name}")
    print(f"\nNext steps:")
    print(f"  1. Start a new Hermes session or run /reload-skills")
    print(f"  2. The skill will be available automatically")

def remove_skill(skill_id):
    """Remove an installed skill."""
    _, name = parse_skill_id(skill_id)
    skill_dir = os.path.join(get_skills_dir(), name)
    
    if not os.path.exists(skill_dir):
        print(f"✗ Skill '{name}' is not installed", file=sys.stderr)
        sys.exit(1)
    
    print(f"Removing {name}...")
    subprocess.run(["rm", "-rf", skill_dir], check=True)
    print(f"✓ Removed {name}")

def list_skills():
    """List installed skills."""
    skills_dir = get_skills_dir()
    if not os.path.exists(skills_dir):
        print(f"No skills directory at {skills_dir}")
        return
    
    print(f"Installed skills in {skills_dir}:\n")
    count = 0
    for item in sorted(os.listdir(skills_dir)):
        item_path = os.path.join(skills_dir, item)
        if os.path.isdir(item_path) and not item.startswith("."):
            skill_md = os.path.join(item_path, "SKILL.md")
            if os.path.exists(skill_md):
                print(f"  ✓ {item}")
                count += 1
            else:
                print(f"  ? {item} (no SKILL.md)")
    
    if count == 0:
        print("  (no skills installed)")
    else:
        print(f"\n{count} skill(s) installed")

def update_skill(skill_id):
    """Update a skill to latest version."""
    _, name = parse_skill_id(skill_id)
    skill_dir = os.path.join(get_skills_dir(), name)
    
    if not os.path.exists(skill_dir):
        print(f"✗ Skill '{name}' is not installed", file=sys.stderr)
        sys.exit(1)
    
    print(f"Updating {name}...")
    # Re-install with force
    install_skill(skill_id, force=True)

def main():
    parser = argparse.ArgumentParser(
        prog="pipx-skills",
        description="Python-native skill installer for Hermes/OpenClaw agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  pipx-skills add eddieoz/nwc-agent            Install a skill
  pipx-skills add eddieoz/nwc-agent --force    Reinstall a skill
  pipx-skills list                             List installed skills
  pipx-skills remove nwc-agent                 Remove a skill

Environment:
  HERMES_SKILLS_DIR    Override skills directory (default: ~/.agents/skills)
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Add
    add = subparsers.add_parser("add", help="Install a skill from GitHub")
    add.add_argument("skill", help="Skill ID (e.g., eddieoz/nwc-agent)")
    add.add_argument("--version", "-v", help="Specific version/branch")
    add.add_argument("--force", "-f", action="store_true", help="Force reinstall")
    
    # Remove
    remove = subparsers.add_parser("remove", help="Remove an installed skill")
    remove.add_argument("skill", help="Skill name")
    
    # List
    subparsers.add_parser("list", help="List installed skills")
    
    # Update
    update = subparsers.add_parser("update", help="Update installed skills")
    update.add_argument("skill", nargs="?", help="Skill to update (default: all)")
    
    args = parser.parse_args()
    
    if args.command == "add":
        install_skill(args.skill, version=args.version, force=args.force)
    elif args.command == "remove":
        remove_skill(args.skill)
    elif args.command == "list":
        list_skills()
    elif args.command == "update":
        if args.skill:
            update_skill(args.skill)
        else:
            print("Update all: not yet implemented")
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
