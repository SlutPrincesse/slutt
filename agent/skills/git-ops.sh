#!/usr/bin/env bash
# Skill: git-ops
# Provides reviewed git operations

git_status_summary() {
  local dir="${1:-.}"
  
  if [[ ! -d "$dir/.git" ]]; then
    echo "ERROR: not a git repository: $dir" >&2
    return 1
  fi
  
  cd "$dir"
  
  local branch
  branch=$(git symbolic-ref --short HEAD 2>/dev/null || echo "detached")
  
  local changes
  changes=$(git status --short 2>/dev/null | wc -l)
  
  local ahead behind
  ahead=$(git rev-list --count @{upstream}..HEAD 2>/dev/null || echo "0")
  behind=$(git rev-list --count HEAD..@{upstream} 2>/dev/null || echo "0")
  
  echo "{\"branch\":\"$branch\",\"changes\":$changes,\"ahead\":$ahead,\"behind\":$behind}"
}

git_diff_summary() {
  local file="${1:-}"
  
  if [[ -n "$file" ]]; then
    git diff --stat "$file" 2>/dev/null || echo "No diff available"
  else
    git diff --stat 2>/dev/null || echo "No diff available"
  fi
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo '[
    {
      "type": "function",
      "function": {
        "name": "git_status_summary",
        "description": "Get a JSON summary of git repository status including branch, changes, and ahead/behind counts.",
        "parameters": {
          "type": "object",
          "properties": {
            "dir": {
              "type": "string",
              "description": "Optional directory path. Defaults to current directory."
            }
          }
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "git_diff_summary",
        "description": "Get a diff stat summary for the repository or a specific file.",
        "parameters": {
          "type": "object",
          "properties": {
            "file": {
              "type": "string",
              "description": "Optional file path. If omitted, shows repo-wide diff."
            }
          }
        }
      }
    }
  ]'
else
  export -f git_status_summary git_diff_summary
fi
