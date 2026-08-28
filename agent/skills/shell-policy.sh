#!/usr/bin/env bash
# Skill: shell-policy
# Provides enhanced shell policy checking using mainframe patterns

shell_policy_check() {
  local command="$1"
  
  # Critical patterns that must be blocked
  local critical_patterns=(
    'rm -rf /'
    'dd if=/dev/zero'
    'mkfs'
    ':(){ :|:& };:'
    '> /dev/sda'
    'chmod -R 777 /'
  )
  
  for pattern in "${critical_patterns[@]}"; do
    if echo "$command" | grep -qE "$pattern"; then
      echo "BLOCKED: critical destructive pattern detected: $pattern"
      return 1
    fi
  done
  
  # High-risk patterns requiring review
  local high_risk_patterns=(
    'git push --force'
    'git reset --hard'
    'git clean -fd'
    'DROP TABLE'
    'TRUNCATE'
    'FLUSHALL'
  )
  
  for pattern in "${high_risk_patterns[@]}"; do
    if echo "$command" | grep -qE "$pattern"; then
      echo "REVIEW_REQUIRED: high-risk pattern detected: $pattern"
      return 2
    fi
  done
  
  echo "ALLOWED: command passed policy check"
  return 0
}

# Export tools for agent
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo '[
    {
      "type": "function",
      "function": {
        "name": "shell_policy_check",
        "description": "Check a shell command against critical and high-risk patterns. Returns ALLOWED, REVIEW_REQUIRED, or BLOCKED.",
        "parameters": {
          "type": "object",
          "properties": {
            "command": {
              "type": "string",
              "description": "The shell command to check."
            }
          },
          "required": ["command"]
        }
      }
    }
  ]'
else
  # Being sourced
  export -f shell_policy_check
fi
