#!/usr/bin/env bash
# Skill: code-review
# Provides basic code review capabilities

code_review_check() {
  local file="$1"
  
  if [[ ! -f "$file" ]]; then
    echo "ERROR: file not found: $file" >&2
    return 1
  fi
  
  local issues=""
  
  # Check for common issues
  if grep -qE 'console\.log\(|print\(|puts ' "$file" 2>/dev/null; then
    issues="${issues}WARNING: debug output statements found\n"
  fi
  
  if grep -qE 'TODO|FIXME|HACK|XXX' "$file" 2>/dev/null; then
    issues="${issues}INFO: code contains TODO/FIXME markers\n"
  fi
  
  if grep -qE 'password\s*=|api_key\s*=|secret\s*=|token\s*=' "$file" 2>/dev/null; then
    issues="${issues}CRITICAL: potential credential exposure detected\n"
  fi
  
  if grep -qE 'eval\(|exec\(|system\(' "$file" 2>/dev/null; then
    issues="${issues}WARNING: dangerous dynamic code execution detected\n"
  fi
  
  if [[ -z "$issues" ]]; then
    echo "CLEAN: no obvious issues found in $file"
  else
    echo -e "REVIEW for $file:\n$issues"
  fi
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo '[
    {
      "type": "function",
      "function": {
        "name": "code_review_check",
        "description": "Review a file for common issues: debug statements, TODOs, credentials, dangerous eval/exec.",
        "parameters": {
          "type": "object",
          "properties": {
            "file": {
              "type": "string",
              "description": "The file path to review."
            }
          },
          "required": ["file"]
        }
      }
    }
  ]'
else
  export -f code_review_check
fi
