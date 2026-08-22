"""CLI orchestration for the MVP coding agent."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import preprocess, sharding, tools, agent


def cmd_preprocess(args):
    pp = preprocess.PreProcessor(args.root)
    task = args.task
    if args.disambiguate:
        phrase, options = preprocess.detect_vague(task)
        if phrase:
            print(f"Vague command detected: '{phrase}'. Options:")
            for i, o in enumerate(options, 1):
                print(f"  {i}. {o}")
            choice = input("Pick an option (or Enter to keep original): ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(options):
                task = options[int(choice) - 1]
    print(pp.build_context(task, top_k=args.top_k))
    if args.cleanup_dir:
        count = 0
        for p in Path(args.cleanup_dir).rglob("*"):
            if p.is_file() and p.suffix in {".py", ".js", ".ts", ".json", ".md", ".txt"}:
                text = p.read_text(errors="ignore")
                new = pp.cleanup_text(text)
                if new != text:
                    p.write_text(new)
                    count += 1
        print(f"Cleaned {count} files.")
    return 0


def cmd_run(args):
    sharder = sharding.WorktreeSharder(args.repo, n=args.n, branch=args.branch)
    worktrees = sharder.create()
    runner = agent.AgentRunner(command=args.agent_cmd, demo=args.demo)
    print(f"Spawned {len(worktrees)} worktrees. Running agents...")
    for i, wt in enumerate(worktrees):
        rc = runner.run(wt, args.task, seed=i)
        print(f"  worktree {i} ({wt}) -> agent rc={rc}")
    diffs = sharder.collect_diffs(worktrees)
    print("\n=== DIFF REVIEW (human-in-the-loop) ===")
    for i, (wt, d) in enumerate(diffs.items()):
        print(f"\n--- worktree {i}: {wt} ---\n{d[:4000]}")
    choice = input("\nAdopt which worktree? (0-N, or 'n' for none): ").strip()
    if choice.isdigit() and 0 <= int(choice) < len(worktrees):
        sharder.adopt(int(choice))
        print(f"Adopted worktree {choice} into {args.branch}.")
    else:
        print("No changes adopted.")
    sharder.cleanup(worktrees)
    return 0


def confirm(name: str, source: str) -> bool:
    ans = input(f"Approve installing tool '{name}' from {source}? [y/N] ").strip().lower()
    return ans == "y"


def cmd_tools(args):
    reg = tools.ToolRegistry()
    if args.tools_action == "list":
        for t in reg.list():
            print(f"{t['name']}: {t['installed']} ({t['sha256'][:12]})")
    elif args.tools_action == "install":
        if not args.name or not args.source:
            print("install requires --name and --source")
            return 1
        ok = reg.install(args.name, Path(args.source), approval=confirm)
        print("Installed." if ok else "Aborted by user.")
    elif args.tools_action == "remove":
        if not args.name:
            print("remove requires --name")
            return 1
        reg.remove(args.name)
        print(f"Removed {args.name}.")
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="neuro_mvp", description="Local-first coding agent MVP")
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("preprocess", help="Build a pruned context bundle from a project")
    pp.add_argument("--root", default=".", help="Project root to index")
    pp.add_argument("--task", required=True, help="Task description / query")
    pp.add_argument("--top-k", type=int, default=15)
    pp.add_argument("--disambiguate", action="store_true", help="Prompt on vague commands")
    pp.add_argument("--cleanup-dir", default=None, help="Apply deterministic cleanup to a dir")
    pp.set_defaults(func=cmd_preprocess)

    rn = sub.add_parser("run", help="Shard task across git worktrees and review diffs")
    rn.add_argument("--repo", default=".", help="Git repo root")
    rn.add_argument("--task", required=True)
    rn.add_argument("--n", type=int, default=3, help="Number of parallel worktrees")
    rn.add_argument("--branch", default="main")
    rn.add_argument(
        "--agent-cmd",
        default=None,
        help="Command template; supports {worktree},{task},{seed} or env vars",
    )
    rn.add_argument("--demo", action="store_true", help="Simulate agent changes (offline)")
    rn.set_defaults(func=cmd_run)

    tl = sub.add_parser("tools", help="Consent-gated tool registry")
    tl.add_argument("tools_action", choices=["list", "install", "remove"])
    tl.add_argument("--name", default=None)
    tl.add_argument("--source", default=None)
    tl.set_defaults(func=cmd_tools)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
