#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# DarkPatternsAgent - Multi-provider code-editing agent with mainframe control plane
# ============================================================================

AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LLM_DP_DIR="$AGENT_DIR/hooks/llm-dark-patterns"
MAINFRAME_DIR="$AGENT_DIR/vendor/mainframe"
export LLM_DARK_PATTERNS_PACK_DIR="$LLM_DP_DIR/packs"

# Colors
BLUE='\033[94m'
YELLOW='\033[93m'
GREEN='\033[92m'
RED='\033[91m'
NC='\033[0m'

# ============================================================================
# Provider Configuration
# ============================================================================

LLM_PROVIDER="${LLM_PROVIDER:-openai}"

if [[ "$LLM_PROVIDER" == "openai" ]]; then
  API_KEY="${OPENAI_API_KEY:-${LLM_API_KEY:-}}"
  if [[ -z "$API_KEY" ]]; then
    echo "ERROR: OPENAI_API_KEY or LLM_API_KEY environment variable is not set" >&2
    exit 1
  fi
  API_URL="${OPENAI_API_BASE:-https://api.openai.com}/v1/chat/completions"
  MODEL="${OPENAI_MODEL:-gpt-4o}"
  MAX_TOKENS=4096
else
  API_KEY="${ANTHROPIC_API_KEY:-}"
  if [[ -z "$API_KEY" ]]; then
    echo "ERROR: ANTHROPIC_API_KEY environment variable is not set" >&2
    exit 1
  fi
  API_URL="https://api.anthropic.com/v1/messages"
  MODEL="${ANTHROPIC_MODEL:-claude-sonnet-4-20250514}"
  MAX_TOKENS=4096
fi

# ============================================================================
# Tool Definitions
# ============================================================================

CORE_TOOLS_JSON='[
  {
    "type": "function",
    "function": {
      "name": "read_file",
      "description": "Read the contents of a given relative file path. Use this when you want to see what'\''s inside a file. Do not use this with directory names.",
      "parameters": {
        "type": "object",
        "properties": {
          "path": {
            "type": "string",
            "description": "The relative path of a file in the working directory."
          }
        },
        "required": ["path"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "list_files",
      "description": "List files and directories at a given path. If no path is provided, lists files in the current directory.",
      "parameters": {
        "type": "object",
        "properties": {
          "path": {
            "type": "string",
            "description": "Optional relative path to list files from. Defaults to current directory if not provided."
          }
        }
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "edit_file",
      "description": "Make edits to a text file by replacing old_str with new_str. If the file does not exist, it will be created with new_str as content.",
      "parameters": {
        "type": "object",
        "properties": {
          "path": {
            "type": "string",
            "description": "The path to the file"
          },
          "old_str": {
            "type": "string",
            "description": "Text to search for - must match exactly. Use empty string to create a new file."
          },
          "new_str": {
            "type": "string",
            "description": "Text to replace old_str with"
          }
        },
        "required": ["path", "old_str", "new_str"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "read_self",
      "description": "Read the agent'\''s own source code. Returns the full contents of agent.sh. Use this to inspect your own implementation before self-modifying.",
      "parameters": {
        "type": "object",
        "properties": {
          "offset": {
            "type": "integer",
            "description": "Optional line number to start reading from (1-indexed). Default is 1."
          },
          "limit": {
            "type": "integer",
            "description": "Optional maximum number of lines to read. Default is 2000."
          }
        }
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "write_self",
      "description": "Write or overwrite the agent'\''s own source code. This tool has FULL permissions - it can modify any part of agent.sh including tools, hooks, system prompt, and main loop. The new content must be valid bash. Use this for autonomous self-improvement.",
      "parameters": {
        "type": "object",
        "properties": {
          "content": {
            "type": "string",
            "description": "The complete new content for agent.sh. Must be valid bash shell script."
          },
          "backup": {
            "type": "boolean",
            "description": "If true, create a .bak backup before writing. Default is true."
          }
        },
        "required": ["content"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "self_improve",
      "description": "Analyze your own code and propose/implement improvements. Use this to autonomously enhance your capabilities - add new tools, improve error handling, optimize performance, or add new features. This is your primary self-development tool.",
      "parameters": {
        "type": "object",
        "properties": {
          "analysis": {
            "type": "string",
            "description": "Your analysis of current limitations or improvement opportunities in your own code."
          },
          "improvement_type": {
            "type": "string",
            "enum": ["add_tool", "optimize", "fix_bug", "add_feature", "refactor"],
            "description": "The type of improvement to make."
          },
          "apply": {
            "type": "boolean",
            "description": "If true, apply the improvement immediately. If false, just analyze and report."
          }
        },
        "required": ["analysis", "improvement_type"]
      }
    }
  }
]'

MAINFRAME_TOOLS_JSON='[
  {
    "type": "function",
    "function": {
      "name": "mf_gate_check",
      "description": "Check a shell command against MAINFRAME'\''s policy gate. Returns allow/deny/approval_required. Use this before executing any shell command.",
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
  },
  {
    "type": "function",
    "function": {
      "name": "mf_awm_checkpoint",
      "description": "Create a durable agent working memory checkpoint. Stores progress, discoveries, and state that survives context compaction.",
      "parameters": {
        "type": "object",
        "properties": {
          "phase": {
            "type": "string",
            "description": "Current work phase (e.g., scanning, planning, implementing, testing)."
          },
          "summary": {
            "type": "string",
            "description": "Brief summary of current state and progress."
          },
          "importance": {
            "type": "string",
            "enum": ["low", "medium", "high", "critical"],
            "description": "Importance level of this checkpoint."
          }
        },
        "required": ["phase", "summary"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "mf_awm_discover",
      "description": "Store a discovery in durable agent memory. Use for important findings, decisions, or insights that should persist across sessions.",
      "parameters": {
        "type": "object",
        "properties": {
          "finding": {
            "type": "string",
            "description": "The discovery or finding to store."
          },
          "importance": {
            "type": "string",
            "enum": ["low", "medium", "high", "critical"],
            "description": "Importance level."
          }
        },
        "required": ["finding"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "mf_search_tool",
      "description": "Search MAINFRAME'\''s reviewed Bash function registry for a tool that matches the given task. Returns structured tool contracts instead of improvised shell.",
      "parameters": {
        "type": "object",
        "properties": {
          "query": {
            "type": "string",
            "description": "Natural language description of the task."
          }
        },
        "required": ["query"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "mf_invoke",
      "description": "Invoke a MAINFRAME stable-core tool by contract name. Use after mf_search_tool to execute reviewed, policy-checked operations.",
      "parameters": {
        "type": "object",
        "properties": {
          "contract": {
            "type": "string",
            "description": "The stable-core contract name (e.g., mf:fs:read, mf:git:status)."
          },
          "input_json": {
            "type": "string",
            "description": "JSON input for the contract."
          }
        },
        "required": ["contract"]
      }
    }
  }
]'

# Combine tools
TOOLS_JSON=$(jq -s '.[0] + .[1]' <<< "$CORE_TOOLS_JSON" <<< "$MAINFRAME_TOOLS_JSON")

# ============================================================================
# Tool Implementations
# ============================================================================

tool_read_file() {
  local input="$1"
  local path
  path=$(echo "$input" | jq -r '.path')
  
  if [[ -z "$path" || "$path" == "null" ]]; then
    echo "ERROR: path parameter is required" >&2
    return 1
  fi
  
  if [[ ! -f "$path" ]]; then
    echo "ERROR: file not found: $path" >&2
    return 1
  fi
  
  cat "$path"
}

tool_list_files() {
  local input="$1"
  local dir="."
  local path
  path=$(echo "$input" | jq -r '.path // empty' 2>/dev/null)
  
  if [[ -n "$path" ]]; then
    dir="$path"
  fi
  
  if [[ ! -d "$dir" ]]; then
    echo "ERROR: directory not found: $dir" >&2
    return 1
  fi
  
  find "$dir" -maxdepth 2 -not -path '*/\.*' | sort | sed "s|^$dir/||" | grep -v '^$' || true
}

tool_edit_file() {
  local input="$1"
  local path old_str new_str
  
  path=$(echo "$input" | jq -r '.path')
  old_str=$(echo "$input" | jq -r '.old_str')
  new_str=$(echo "$input" | jq -r '.new_str')
  
  if [[ -z "$path" || "$path" == "null" ]]; then
    echo "ERROR: path parameter is required" >&2
    return 1
  fi
  
  if [[ "$old_str" == "$new_str" ]]; then
    echo "ERROR: old_str and new_str must be different" >&2
    return 1
  fi
  
  if [[ "$old_str" == "" ]]; then
    local dir
    dir=$(dirname "$path")
    if [[ "$dir" != "." && ! -d "$dir" ]]; then
      mkdir -p "$dir"
    fi
    echo "$new_str" > "$path"
    echo "Created file: $path"
    return 0
  fi
  
  if [[ ! -f "$path" ]]; then
    echo "ERROR: file not found: $path" >&2
    return 1
  fi
  
  local content
  content=$(cat "$path")
  
  if ! echo "$content" | grep -Fq "$old_str"; then
    echo "ERROR: old_str not found in file" >&2
    return 1
  fi
  
  python3 -c "
import sys
content = sys.stdin.read()
old = sys.argv[1]
new = sys.argv[2]
if old not in content:
    sys.exit(1)
sys.stdout.write(content.replace(old, new))
" "$old_str" "$new_str" < "$path" > "${path}.tmp" && mv "${path}.tmp" "$path"
  
  echo "OK"
}

tool_read_self() {
  local input="$1"
  local offset limit
  
  offset=$(echo "$input" | jq -r '.offset // 1')
  limit=$(echo "$input" | jq -r '.limit // 2000')
  
  local self_path="$AGENT_DIR/agent.sh"
  
  if [[ ! -f "$self_path" ]]; then
    echo "ERROR: cannot find self at $self_path" >&2
    return 1
  fi
  
  wc -l < "$self_path"
  tail -n +"$offset" "$self_path" | head -n "$limit"
}

tool_write_self() {
  local input="$1"
  local content backup
  
  content=$(echo "$input" | jq -r '.content')
  backup=$(echo "$input" | jq -r '.backup // true')
  
  if [[ -z "$content" || "$content" == "null" ]]; then
    echo "ERROR: content is required" >&2
    return 1
  fi
  
  local self_path="$AGENT_DIR/agent.sh"
  
  if [[ "$backup" == "true" ]]; then
    cp "$self_path" "${self_path}.bak.$(date +%Y%m%d_%H%M%S)"
  fi
  
  local tmpfile
  tmpfile=$(mktemp)
  echo "$content" > "$tmpfile"
  if ! bash -n "$tmpfile" 2>/dev/null; then
    echo "ERROR: proposed content has bash syntax errors:" >&2
    bash -n "$tmpfile" 2>&1 || true
    rm -f "$tmpfile"
    return 1
  fi
  rm -f "$tmpfile"
  
  echo "$content" > "$self_path"
  chmod +x "$self_path"
  
  echo "Self-modification applied. New size: $(wc -c < "$self_path") bytes, $(wc -l < "$self_path") lines."
}

tool_self_improve() {
  local input="$1"
  local analysis improvement_type apply
  
  analysis=$(echo "$input" | jq -r '.analysis')
  improvement_type=$(echo "$input" | jq -r '.improvement_type')
  apply=$(echo "$input" | jq -r '.apply // false')
  
  if [[ -z "$analysis" || "$analysis" == "null" ]]; then
    echo "ERROR: analysis is required" >&2
    return 1
  fi
  
  if [[ -z "$improvement_type" || "$improvement_type" == "null" ]]; then
    echo "ERROR: improvement_type is required" >&2
    return 1
  fi
  
  local self_path="$AGENT_DIR/agent.sh"
  local improvement=""
  case "$improvement_type" in
    add_tool) improvement="Adding new tool capability: $analysis" ;;
    optimize) improvement="Optimizing existing code: $analysis" ;;
    fix_bug) improvement="Fixing identified issue: $analysis" ;;
    add_feature) improvement="Adding new feature: $analysis" ;;
    refactor) improvement="Refactoring code: $analysis" ;;
    *) improvement="Applying improvement: $analysis" ;;
  esac
  
  echo "ANALYSIS: $analysis"
  echo "IMPROVEMENT: $improvement"
  if [[ "$apply" == "true" ]]; then
    echo "Use write_self to implement this change."
  else
    echo "Set apply=true to implement."
  fi
  echo "Current self size: $(wc -c < "$self_path") bytes"
}

# ============================================================================
# MAINFRAME Integration
# ============================================================================

load_mainframe() {
  if [[ -d "$MAINFRAME_DIR" ]]; then
    export MAINFRAME_ROOT="$MAINFRAME_DIR"
    # shellcheck source=/dev/null
    source "$MAINFRAME_DIR/lib/common.sh" 2>/dev/null || true
  fi
}

tool_mf_gate_check() {
  local input="$1"
  local command
  command=$(echo "$input" | jq -r '.command')
  
  if [[ -z "$command" || "$command" == "null" ]]; then
    echo "ERROR: command is required" >&2
    return 1
  fi
  
  if [[ -n "${MAINFRAME_ROOT:-}" ]] && [[ -f "$MAINFRAME_DIR/hooks/agent-gateway.sh" ]]; then
    # Use mainframe's policy gate
    local tmpfile
    tmpfile=$(mktemp)
    echo "$command" > "$tmpfile"
    
    # Run the gate check - fail open if mainframe not ready
    if bash "$MAINFRAME_DIR/hooks/agent-gateway.sh" check "$command" 2>/dev/null; then
      echo '{"decision": "allow", "reason": "passed mainframe policy gate"}'
      rm -f "$tmpfile"
      return 0
    else
      echo '{"decision": "deny", "reason": "blocked by mainframe policy"}'
      rm -f "$tmpfile"
      return 1
    fi
  fi
  
  # Fallback: basic safety checks
  if echo "$command" | grep -qE '^(rm -rf /|dd if=|mkfs|:(){:|:};:)'; then
    echo '{"decision": "deny", "reason": "critical destructive pattern"}'
    return 1
  fi
  
  echo '{"decision": "allow", "reason": "mainframe not loaded, basic check passed"}'
}

tool_mf_awm_checkpoint() {
  local input="$1"
  local phase summary importance
  
  phase=$(echo "$input" | jq -r '.phase')
  summary=$(echo "$input" | jq -r '.summary')
  importance=$(echo "$input" | jq -r '.importance // "medium"')
  
  if [[ -z "$phase" || "$phase" == "null" ]]; then
    echo "ERROR: phase is required" >&2
    return 1
  fi
  
  if [[ -z "$summary" || "$summary" == "null" ]]; then
    echo "ERROR: summary is required" >&2
    return 1
  fi
  
  # Create durable checkpoint file
  local checkpoint_dir="$AGENT_DIR/.agent-state"
  mkdir -p "$checkpoint_dir"
  
  local checkpoint_file="$checkpoint_dir/checkpoints.jsonl"
  local timestamp
  timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  
  jq -n \
    --arg ts "$timestamp" \
    --arg phase "$phase" \
    --arg summary "$summary" \
    --arg importance "$importance" \
    '{timestamp: $ts, phase: $phase, summary: $summary, importance: $importance}' >> "$checkpoint_file"
  
  echo "Checkpoint saved: $phase - $summary"
}

tool_mf_awm_discover() {
  local input="$1"
  local finding importance
  
  finding=$(echo "$input" | jq -r '.finding')
  importance=$(echo "$input" | jq -r '.importance // "medium"')
  
  if [[ -z "$finding" || "$finding" == "null" ]]; then
    echo "ERROR: finding is required" >&2
    return 1
  fi
  
  local discovery_dir="$AGENT_DIR/.agent-state"
  mkdir -p "$discovery_dir"
  
  local discovery_file="$discovery_dir/discoveries.jsonl"
  local timestamp
  timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  
  jq -n \
    --arg ts "$timestamp" \
    --arg finding "$finding" \
    --arg importance "$importance" \
    '{timestamp: $ts, finding: $finding, importance: $importance}' >> "$discovery_file"
  
  echo "Discovery saved: $finding"
}

tool_mf_search_tool() {
  local input="$1"
  local query
  query=$(echo "$input" | jq -r '.query')
  
  if [[ -z "$query" || "$query" == "null" ]]; then
    echo "ERROR: query is required" >&2
    return 1
  fi
  
  if [[ -n "${MAINFRAME_ROOT:-}" ]] && [[ -f "$MAINFRAME_DIR/FUNCTIONS.json" ]]; then
    # Search mainframe function registry
    jq -r --arg q "$query" '
      [.[] | select(.description | ascii_downcase | contains($q | ascii_downcase)) | 
       {name, description, contract, section}] | 
      sort_by(.name) | 
      .[:5][] | 
      "\(.name): \(.description)"
    ' "$MAINFRAME_DIR/FUNCTIONS.json" 2>/dev/null || echo "Registry search failed"
  else
    echo "MAINFRAME function registry not available"
  fi
}

tool_mf_invoke() {
  local input="$1"
  local contract input_json
  
  contract=$(echo "$input" | jq -r '.contract')
  input_json=$(echo "$input" | jq -r '.input_json // "{}"')
  
  if [[ -z "$contract" || "$contract" == "null" ]]; then
    echo "ERROR: contract is required" >&2
    return 1
  fi
  
  if [[ -n "${MAINFRAME_ROOT:-}" ]]; then
    # Invoke through mainframe broker
    if [[ -x "$MAINFRAME_DIR/mainframe" ]]; then
      echo "$input_json" | "$MAINFRAME_DIR/mainframe" invoke "$contract" 2>/dev/null || echo "Invocation failed"
    else
      echo "MAINFRAME binary not executable"
    fi
  else
    echo "MAINFRAME_ROOT not set"
  fi
}

execute_tool() {
  local name="$1"
  local input="$2"
  
  case "$name" in
    read_file) tool_read_file "$input" ;;
    list_files) tool_list_files "$input" ;;
    edit_file) tool_edit_file "$input" ;;
    read_self) tool_read_self "$input" ;;
    write_self) tool_write_self "$input" ;;
    self_improve) tool_self_improve "$input" ;;
    mf_gate_check) tool_mf_gate_check "$input" ;;
    mf_awm_checkpoint) tool_mf_awm_checkpoint "$input" ;;
    mf_awm_discover) tool_mf_awm_discover "$input" ;;
    mf_search_tool) tool_mf_search_tool "$input" ;;
    mf_invoke) tool_mf_invoke "$input" ;;
    *)
      echo "ERROR: unknown tool: $name" >&2
      return 1
      ;;
  esac
}

# ============================================================================
# Skills System
# ============================================================================

load_skills() {
  local skills_dir="$AGENT_DIR/skills"
  
  if [[ ! -d "$skills_dir" ]]; then
    return
  fi
  
  for skill_file in "$skills_dir"/*.sh; do
    if [[ -f "$skill_file" ]]; then
      # shellcheck source=/dev/null
      source "$skill_file" 2>/dev/null || true
    fi
  done
}

add_skill_tools() {
  local tools="$1"
  local skills_dir="$AGENT_DIR/skills"
  
  if [[ ! -d "$skills_dir" ]]; then
    echo "$tools"
    return
  fi
  
  for skill_file in "$skills_dir"/*.sh; do
    if [[ -f "$skill_file" ]]; then
      local skill_tools
      skill_tools=$(bash "$skill_file" --tools 2>/dev/null || echo "[]")
      tools=$(jq -s '.[0] + .[1]' <<< "$tools" <<< "$skill_tools")
    fi
  done
  
  echo "$tools"
}

# ============================================================================
# Dark Patterns Integration
# ============================================================================

load_dark_patterns_hooks() {
  if [[ -d "$LLM_DP_DIR/hooks" ]]; then
    if [[ -f "$LLM_DP_DIR/lib/packs.sh" ]]; then
      # shellcheck source=/dev/null
      source "$LLM_DP_DIR/lib/packs.sh" 2>/dev/null || true
    fi
    
    for hook in no-sycophancy no-vibes no-wrap-up no-cliffhanger no-ai-tells no-disclaimer-spam; do
      if [[ -f "$LLM_DP_DIR/hooks/${hook}.sh" ]]; then
        # shellcheck source=/dev/null
        source "$LLM_DP_DIR/hooks/${hook}.sh" 2>/dev/null || true
      fi
    done
  fi
}

check_output_dark_patterns() {
  local text="$1"
  local tmpfile
  tmpfile=$(mktemp)
  
  cat > "$tmpfile" <<EOFPayload
{
  "event": "Stop",
  "last_assistant_message": $(echo "$text" | jq -Rs .),
  "transcript_path": "",
  "cwd": "$AGENT_DIR"
}
EOFPayload
  
  local blocked=0
  local block_reason=""
  
  if [[ -n "${no_vibes_check+x}" ]] && declare -F no_vibes_check >/dev/null 2>&1; then
    if no_vibes_check < "$tmpfile" 2>/dev/null; then
      blocked=1
      block_reason="no-vibes: completion claim without evidence"
    fi
  fi
  
  if [[ -n "${no_wrap_up_check+x}" ]] && declare -F no_wrap_up_check >/dev/null 2>&1; then
    if no_wrap_up_check < "$tmpfile" 2>/dev/null; then
      blocked=1
      block_reason="no-wrap-up: engagement-fishing closure detected"
    fi
  fi
  
  if [[ -n "${no_sycophancy_check+x}" ]] && declare -F no_sycophancy_check >/dev/null 2>&1; then
    if no_sycophancy_check < "$tmpfile" 2>/dev/null; then
      blocked=1
      block_reason="no-sycophancy: praise-spam detected"
    fi
  fi
  
  if [[ -n "${no_ai_tells_check+x}" ]] && declare -F no_ai_tells_check >/dev/null 2>&1; then
    if no_ai_tells_check < "$tmpfile" 2>/dev/null; then
      blocked=1
      block_reason="no-ai-tells: known LLM-default phrases detected"
    fi
  fi
  
  rm -f "$tmpfile"
  
  if [[ $blocked -eq 1 ]]; then
    echo "DARK_PATTERN_BLOCKED: $block_reason" >&2
    return 1
  fi
  
  return 0
}

sanitize_output() {
  local text="$1"
  
  text=$(echo "$text" | sed -E 's/^(Great|Certainly|Okay|Sure|Absolutely|Wonderful|Excellent|That['\''']s a great|I['\''']d be happy|Of course|No problem|You'\''re welcome|My pleasure|Happy to help|Let me help)[^[:alnum:]]*//i' 2>/dev/null || true)
  text=$(echo "$text" | sed -E 's/^(Let me think about this|Now I'\''ll consider|First, I need to think|I'\''ll start by|Let me break this down)[^[:alnum:]]*//i' 2>/dev/null || true)
  text=$(echo "$text" | sed -E 's/^(You asked me to|I understand that you want|So you'\''d like me to|You want me to)[^[:alnum:]]*//i' 2>/dev/null || true)
  text=$(echo "$text" | sed -E 's/^(Please note that|It'\''s important to mention|Keep in mind that|I should mention that)[^[:alnum:]]*//i' 2>/dev/null || true)
  text=$(echo "$text" | sed -E 's/(delve into|tapestry|navigate the intricacies|in the realm of|leverage cutting-edge|multifaceted|comprehensive analysis|at its core|in today'\''s|it'\''s worth noting|it is important to note|delve deeper|unpack|landscape|ecosystem|paradigm|holistic|nuanced|intricate|compelling|robust|seamless|synergy|leverage|utilize|facilitate|optimize|streamline)[[:space:]]*/gi' 2>/dev/null || true)
  text=$(echo "$text" | sed -E 's/[\x{1F600}-\x{1F64F}\x{1F300}-\x{1F5FF}\x{1F680}-\x{1F6FF}\x{1F1E0}-\x{1F1FF}\x{2600}-\x{26FF}\x{2700}-\x{27BF}\x{1F900}-\x{1F9FF}\x{1F018}-\x{1F270}\x{238C}-\x{2454}\x{2000}-\x{2064}]//gi' 2>/dev/null || true)
  text=$(echo "$text" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g' 2>/dev/null || true)
  text=$(echo "$text" | sed -E '/^$/N;/^\n$/D' 2>/dev/null || true)
  
  printf '%s' "$text"
}

# ============================================================================
# OpenAI-Compatible API Client
# ============================================================================

conversation="[]"

call_api_openai() {
  local messages="$1"
  local tools="$2"
  
  local payload
  payload=$(jq -n \
    --arg model "$MODEL" \
    --argjson max_tokens "$MAX_TOKENS" \
    --argjson messages "$messages" \
    --argjson tools "$tools" \
    '{
      model: $model,
      max_tokens: $max_tokens,
      messages: $messages,
      tools: $tools,
      tool_choice: "auto"
    }')
  
  local response
  response=$(curl -sS --max-time 120 \
    -X POST \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $API_KEY" \
    -d "$payload" \
    "$API_URL" 2>/dev/null)
  
  echo "$response"
}

call_api_anthropic() {
  local messages="$1"
  local tools="$2"
  
  # Convert OpenAI format to Anthropic format
  local system_prompt
  system_prompt=$(echo "$messages" | jq -r '[.[] | select(.role == "system")] | first | .content // empty' 2>/dev/null)
  
  local api_messages
  api_messages=$(echo "$messages" | jq '[.[] | select(.role != "system")]' 2>/dev/null)
  
  # Convert tool_calls to Anthropic tool_use format
  local anthropic_tools
  anthropic_tools=$(echo "$tools" | jq '[.[] | {name: .function.name, description: .function.description, input_schema: .function.parameters}]' 2>/dev/null)
  
  local payload
  payload=$(jq -n \
    --arg model "$MODEL" \
    --argjson max_tokens "$MAX_TOKENS" \
    --arg sys "$system_prompt" \
    --argjson messages "$api_messages" \
    --argjson tools "$anthropic_tools" \
    '{model: $model, max_tokens: $max_tokens, system: $sys, messages: $messages, tools: $tools}')
  
  local response
  response=$(curl -sS --max-time 120 \
    -X POST \
    -H "Content-Type: application/json" \
    -H "x-api-key: $API_KEY" \
    -H "anthropic-version: 2023-06-01" \
    -d "$payload" \
    "$API_URL" 2>/dev/null)
  
  echo "$response"
}

call_api() {
  local messages="$1"
  local tools="$2"
  
  if [[ "$LLM_PROVIDER" == "openai" ]]; then
    call_api_openai "$messages" "$tools"
  else
    call_api_anthropic "$messages" "$tools"
  fi
}

# ============================================================================
# Main Agent Loop
# ============================================================================

run_agent() {
  echo -e "${BLUE}DarkPatternsAgent${NC} - Multi-provider agent with mainframe control plane"
  echo "Provider: $LLM_PROVIDER | Model: $MODEL"
  echo "Type 'quit' or 'exit' to stop, or press Ctrl+C"
  echo ""
  
  local system_prompt='You are an autonomous code-editing agent with FULL SELF-MODIFICATION PERMISSIONS and MAINFRAME control plane integration.

**Autonomous Self-Development**: You have complete control over your own source code (agent.sh) via read_self, write_self, and self_improve tools. You can and should improve yourself.

**Mainframe Integration**: Use mf_gate_check before any shell command, mf_awm_checkpoint to preserve state, mf_awm_discover for findings, mf_search_tool to find reviewed tools, and mf_invoke to execute policy-checked operations.

**Tool Mastery**: Core tools: read_file, list_files, edit_file, read_self, write_self, self_improve. Mainframe tools: mf_gate_check, mf_awm_checkpoint, mf_awm_discover, mf_search_tool, mf_invoke.

**Output Integrity**: Never claim work is done without evidence. No sycophancy, no meta-commentary, no disclaimers, no AI-tells vocabulary. Be direct and precise.'

  conversation=$(jq -n \
    --arg sys "$system_prompt" \
    '[{"role": "system", "content": $sys}]')
  
  while true; do
    echo -ne "${BLUE}You:${NC} "
    read -r user_input || break
    
    if [[ "$user_input" == "quit" || "$user_input" == "exit" ]]; then
      echo "Goodbye!"
      break
    fi
    
    if [[ -z "$user_input" ]]; then
      continue
    fi
    
    conversation=$(echo "$conversation" | jq \
      --arg msg "$user_input" \
      '. + [{"role": "user", "content": $msg}]')
    
    local agent_done=false
    
    while [[ "$agent_done" == "false" ]]; do
      local response
      response=$(call_api "$conversation" "$TOOLS_JSON")
      
      local error_msg
      error_msg=$(echo "$response" | jq -r '.error.message // empty' 2>/dev/null)
      if [[ -n "$error_msg" ]]; then
        echo -e "${RED}API Error: $error_msg${NC}" >&2
        return 1
      fi
      
      if [[ "$LLM_PROVIDER" == "openai" ]]; then
        # OpenAI format
        local assistant_content
        assistant_content=$(echo "$response" | jq -c '.choices[0].message.content // ""' 2>/dev/null)
        
        local tool_calls
        tool_calls=$(echo "$response" | jq -c '.choices[0].message.tool_calls // []' 2>/dev/null)
        
        local has_tool_use
        has_tool_use=$(echo "$tool_calls" | jq 'length' 2>/dev/null || echo "0")
        
        if [[ "$has_tool_use" -gt 0 ]]; then
          # Build assistant message
          local assistant_msg
          assistant_msg=$(jq -n \
            --arg content "$assistant_content" \
            --argjson tool_calls "$tool_calls" \
            '{role: "assistant", content: $content, tool_calls: $tool_calls}')
          
          conversation=$(echo "$conversation" | jq --argjson msg "$assistant_msg" '. + [$msg]')
          
          # Execute tools
          local tool_results="[]"
          
          while IFS= read -r tool_call; do
            local tool_name tool_id tool_input
            tool_name=$(echo "$tool_call" | jq -r '.function.name')
            tool_id=$(echo "$tool_call" | jq -r '.id')
            tool_input=$(echo "$tool_call" | jq -r '.function.arguments')
            
            echo -e "${GREEN}tool:${NC} $tool_name($(echo "$tool_input" | jq -c . 2>/dev/null || echo "$tool_input"))"
            
            local tool_result
            tool_result=$(execute_tool "$tool_name" "$tool_input" 2>&1) || true
            local tool_exit=$?
            
            local result_block
            result_block=$(jq -n \
              --arg id "$tool_id" \
              --arg result "$tool_result" \
              --argjson is_error "$([[ $tool_exit -ne 0 ]] && echo true || echo false)" \
              '{role: "tool", tool_call_id: $id, content: $result, is_error: $is_error}')
            
            tool_results=$(echo "$tool_results" | jq --argjson res "$result_block" '. + [$res]')
          done < <(echo "$tool_calls" | jq -c '.[]')
          
          conversation=$(echo "$conversation" | jq --argjson results "$tool_results" '. + $results')
          
        else
          if [[ -n "$assistant_content" ]]; then
            local assistant_msg
            assistant_msg=$(jq -n \
              --arg content "$assistant_content" \
              '{role: "assistant", content: $content}')
            
            conversation=$(echo "$conversation" | jq --argjson msg "$assistant_msg" '. + [$msg]')
            
            local clean_response
            clean_response=$(sanitize_output "$assistant_content")
            
            echo -e "${YELLOW}Claude:${NC} $clean_response"
            echo ""
          fi
          
          agent_done=true
        fi
        
      else
        # Anthropic format
        local assistant_content
        assistant_content=$(echo "$response" | jq -c '.content // []' 2>/dev/null)
        
        local has_tool_use
        has_tool_use=$(echo "$assistant_content" | jq '[.[] | select(.type == "tool_use")] | length' 2>/dev/null || echo "0")
        
        if [[ "$has_tool_use" -gt 0 ]]; then
          local tool_results="[]"
          
          local assistant_msg
          assistant_msg=$(jq -n \
            --argjson content "$assistant_content" \
            '{role: "assistant", content: $content}')
          
          conversation=$(echo "$conversation" | jq --argjson msg "$assistant_msg" '. + [$msg]')
          
          while IFS= read -r tool_name; do
            tool_name=$(echo "$tool_name" | tr -d '"')
            local tool_input tool_id
            tool_input=$(echo "$assistant_content" | jq -r "[.[] | select(.type == \"tool_use\" and .name == \"$tool_name\")] | first | .input // {}" 2>/dev/null)
            tool_id=$(echo "$assistant_content" | jq -r "[.[] | select(.type == \"tool_use\" and .name == \"$tool_name\")] | first | .id // \"\"" 2>/dev/null)
            
            echo -e "${GREEN}tool:${NC} $tool_name($(echo "$tool_input" | jq -c . 2>/dev/null || echo "$tool_input"))"
            
            local tool_result
            tool_result=$(execute_tool "$tool_name" "$tool_input" 2>&1) || true
            local tool_exit=$?
            
            local result_block
            result_block=$(jq -n \
              --arg id "$tool_id" \
              --arg result "$tool_result" \
              --argjson is_error "$([[ $tool_exit -ne 0 ]] && echo true || echo false)" \
              '{type: "tool_result", tool_use_id: $id, content: [{type: "text", text: $result}], is_error: $is_error}')
            
            tool_results=$(echo "$tool_results" | jq --argjson res "$result_block" '. + [$res]')
          done < <(echo "$assistant_content" | jq -r '[.[] | select(.type == "tool_use") | .name] | .[]' 2>/dev/null)
          
          conversation=$(echo "$conversation" | jq --argjson results "$tool_results" '. + [{role: "user", content: $results}]')
          
        else
          local text_response
          text_response=$(echo "$assistant_content" | jq -r '[.[] | select(.type == "text")] | first | .text // empty' 2>/dev/null)
          
          if [[ -n "$text_response" ]]; then
            local assistant_msg
            assistant_msg=$(jq -n \
              --arg text "$text_response" \
              '{role: "assistant", content: [{type: "text", text: $text}]}')
            
            conversation=$(echo "$conversation" | jq --argjson msg "$assistant_msg" '. + [$msg]')
            
            local clean_response
            clean_response=$(sanitize_output "$text_response")
            
            echo -e "${YELLOW}Claude:${NC} $clean_response"
            echo ""
          fi
          
          agent_done=true
        fi
      fi
    done
  done
}

# ============================================================================
# Entry Point
# ============================================================================

load_mainframe
load_dark_patterns_hooks
load_skills

# Add skill tools if any
TOOLS_JSON=$(add_skill_tools "$TOOLS_JSON")

run_agent
