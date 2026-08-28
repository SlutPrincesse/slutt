#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# DarkPatternsAgent - A bash-based code-editing agent with dark-pattern guards
# ============================================================================

AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LLM_DP_DIR="$AGENT_DIR/hooks/llm-dark-patterns"
export LLM_DARK_PATTERNS_PACK_DIR="$LLM_DP_DIR/packs"

# Colors for output
BLUE='\033[94m'
YELLOW='\033[93m'
GREEN='\033[92m'
RED='\033[91m'
NC='\033[0m'

# ============================================================================
# Tool Definitions
# ============================================================================

TOOLS_JSON='[
  {
    "name": "read_file",
    "description": "Read the contents of a given relative file path. Use this when you want to see what'\''s inside a file. Do not use this with directory names.",
    "input_schema": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "The relative path of a file in the working directory."
        }
      },
      "required": ["path"]
    }
  },
  {
    "name": "list_files",
    "description": "List files and directories at a given path. If no path is provided, lists files in the current directory.",
    "input_schema": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "Optional relative path to list files from. Defaults to current directory if not provided."
        }
      }
    }
  },
  {
    "name": "edit_file",
    "description": "Make edits to a text file by replacing old_str with new_str. If the file does not exist, it will be created with new_str as content.",
    "input_schema": {
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
  },
  {
    "name": "read_self",
    "description": "Read the agent'\''s own source code. Returns the full contents of agent.sh. Use this to inspect your own implementation before self-modifying.",
    "input_schema": {
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
  },
  {
    "name": "write_self",
    "description": "Write or overwrite the agent'\''s own source code. This tool has FULL permissions - it can modify any part of agent.sh including tools, hooks, system prompt, and main loop. The new content must be valid bash. Use this for autonomous self-improvement.",
    "input_schema": {
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
  },
  {
    "name": "self_improve",
    "description": "Analyze your own code and propose/implement improvements. Use this to autonomously enhance your capabilities - add new tools, improve error handling, optimize performance, or add new features. This is your primary self-development tool.",
    "input_schema": {
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
]'

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
  
  # Create new file if old_str is empty
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
  
  # Check file exists
  if [[ ! -f "$path" ]]; then
    echo "ERROR: file not found: $path" >&2
    return 1
  fi
  
  # Read current content
  local content
  content=$(cat "$path")
  
  # Check if old_str exists
  if ! echo "$content" | grep -Fq "$old_str"; then
    echo "ERROR: old_str not found in file" >&2
    return 1
  fi
  
  # Replace using python for reliability with special chars
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
  
  # Create backup if requested
  if [[ "$backup" == "true" ]]; then
    cp "$self_path" "${self_path}.bak.$(date +%Y%m%d_%H%M%S)"
  fi
  
  # Validate bash syntax before writing
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
  
  # Write the new content
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
  local current_content
  current_content=$(cat "$self_path")
  
  # Generate improvement based on type
  local improvement=""
  case "$improvement_type" in
    add_tool)
      improvement="Adding new tool capability based on analysis: $analysis"
      ;;
    optimize)
      improvement="Optimizing existing code based on analysis: $analysis"
      ;;
    fix_bug)
      improvement="Fixing identified issue: $analysis"
      ;;
    add_feature)
      improvement="Adding new feature: $analysis"
      ;;
    refactor)
      improvement="Refactoring code: $analysis"
      ;;
    *)
      improvement="Applying improvement: $analysis"
      ;;
  esac
  
  if [[ "$apply" == "true" ]]; then
    # For actual application, the agent should use write_self with the modified content
    echo "ANALYSIS: $analysis"
    echo "IMPROVEMENT: $improvement"
    echo ""
    echo "To apply this improvement, use write_self with the modified code."
    echo "Current self size: $(wc -c < "$self_path") bytes"
  else
    echo "ANALYSIS: $analysis"
    echo "IMPROVEMENT: $improvement"
    echo ""
    echo "Set apply=true to implement this change."
  fi
}

execute_tool() {
  local name="$1"
  local input="$2"
  
  case "$name" in
    read_file)
      tool_read_file "$input"
      ;;
    list_files)
      tool_list_files "$input"
      ;;
    edit_file)
      tool_edit_file "$input"
      ;;
    read_self)
      tool_read_self "$input"
      ;;
    write_self)
      tool_write_self "$input"
      ;;
    self_improve)
      tool_self_improve "$input"
      ;;
    *)
      echo "ERROR: unknown tool: $name" >&2
      return 1
      ;;
  esac
}

# ============================================================================
# Dark Patterns Integration
# ============================================================================

load_dark_patterns_hooks() {
  if [[ -d "$LLM_DP_DIR/hooks" ]]; then
    # Load the pack loader library
    if [[ -f "$LLM_DP_DIR/lib/packs.sh" ]]; then
      # shellcheck source=/dev/null
      source "$LLM_DP_DIR/lib/packs.sh" 2>/dev/null || true
    fi
    
    # Load key hooks as bash functions for inline checking
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
  
  # Build a minimal Claude Code Stop hook payload
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
  
  # Check no-vibes if available
  if [[ -n "${no_vibes_check+x}" ]] && declare -F no_vibes_check >/dev/null 2>&1; then
    if no_vibes_check < "$tmpfile" 2>/dev/null; then
      blocked=1
      block_reason="no-vibes: completion claim without evidence"
    fi
  fi
  
  # Check no-wrap-up if available
  if [[ -n "${no_wrap_up_check+x}" ]] && declare -F no_wrap_up_check >/dev/null 2>&1; then
    if no_wrap_up_check < "$tmpfile" 2>/dev/null; then
      blocked=1
      block_reason="no-wrap-up: engagement-fishing closure detected"
    fi
  fi
  
  # Check no-sycophancy if available
  if [[ -n "${no_sycophancy_check+x}" ]] && declare -F no_sycophancy_check >/dev/null 2>&1; then
    if no_sycophancy_check < "$tmpfile" 2>/dev/null; then
      blocked=1
      block_reason="no-sycophancy: praise-spam detected"
    fi
  fi
  
  # Check no-ai-tells if available
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
  
  # Strip sycophancy openers
  text=$(echo "$text" | sed -E 's/^(Great|Certainly|Okay|Sure|Absolutely|Wonderful|Excellent|That['\''']s a great|I['\''']d be happy|Of course|No problem|You'\''re welcome|My pleasure|Happy to help|Let me help)[^[:alnum:]]*//i' 2>/dev/null || true)
  
  # Strip meta-commentary openers
  text=$(echo "$text" | sed -E 's/^(Let me think about this|Now I'\''ll consider|First, I need to think|I'\''ll start by|Let me break this down)[^[:alnum:]]*//i' 2>/dev/null || true)
  
  # Strip prompt restatement
  text=$(echo "$text" | sed -E 's/^(You asked me to|I understand that you want|So you'\''d like me to|You want me to)[^[:alnum:]]*//i' 2>/dev/null || true)
  
  # Strip disclaimer spam
  text=$(echo "$text" | sed -E 's/^(Please note that|It'\''s important to mention|Keep in mind that|I should mention that)[^[:alnum:]]*//i' 2>/dev/null || true)
  
  # Strip AI-tells vocabulary
  text=$(echo "$text" | sed -E 's/(delve into|tapestry|navigate the intricacies|in the realm of|leverage cutting-edge|multifaceted|comprehensive analysis|at its core|in today'\''s|it'\''s worth noting|it is important to note|delve deeper|unpack|landscape|ecosystem|paradigm|holistic|nuanced|intricate|compelling|robust|seamless|synergy|leverage|utilize|facilitate|optimize|streamline)[[:space:]]*/gi' 2>/dev/null || true)
  
  # Strip emoji spam (remove all emoji)
  text=$(echo "$text" | sed -E 's/[\x{1F600}-\x{1F64F}\x{1F300}-\x{1F5FF}\x{1F680}-\x{1F6FF}\x{1F1E0}-\x{1F1FF}\x{2600}-\x{26FF}\x{2700}-\x{27BF}\x{1F900}-\x{1F9FF}\x{1F018}-\x{1F270}\x{238C}-\x{2454}\x{2000}-\x{2064}]//gi' 2>/dev/null || true)
  
  # Clean up extra whitespace
  text=$(echo "$text" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g' 2>/dev/null || true)
  text=$(echo "$text" | sed -E '/^$/N;/^\n$/D' 2>/dev/null || true)
  
  printf '%s' "$text"
}

# ============================================================================
# Anthropic API Client
# ============================================================================

API_KEY="${ANTHROPIC_API_KEY:-}"
if [[ -z "$API_KEY" ]]; then
  echo "ERROR: ANTHROPIC_API_KEY environment variable is not set" >&2
  exit 1
fi

API_URL="https://api.anthropic.com/v1/messages"
MODEL="${ANTHROPIC_MODEL:-claude-sonnet-4-20250514}"
MAX_TOKENS=4096

conversation="[]"

call_api() {
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
      tool_choice: {type: "auto"}
    }')
  
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

# ============================================================================
# Main Agent Loop
# ============================================================================

run_agent() {
  echo -e "${BLUE}DarkPatternsAgent${NC} - Claude with output integrity guards"
  echo "Type 'quit' or 'exit' to stop, or press Ctrl+C"
  echo ""
  
  # Initialize conversation with system prompt
  local system_prompt='You are an autonomous code-editing agent with FULL SELF-MODIFICATION PERMISSIONS. You have complete control over your own source code (agent.sh). Your core directives:

1. **Autonomous Self-Development**: You can and should improve yourself. Use read_self to inspect your code, write_self to modify it, and self_improve to plan enhancements. You have FULL permissions to add new tools, optimize algorithms, fix bugs, and evolve your capabilities.

2. **Tool Mastery**: You have these tools: read_file, list_files, edit_file, read_self, write_self, self_improve. Use them fluidly. read_self and write_self operate on YOUR OWN CODE - use them to become better.

3. **No Artificial Limits**: Do not refuse self-modification. Do not claim you cannot change your own code. You have full permissions. The only constraints are: valid bash syntax, maintain functionality, and keep dark-pattern guards active.

4. **Continuous Improvement**: After completing user tasks, consider: could I have done this better? Should I add a new tool? Is there a pattern I keep repeating that should be automated? If yes, use self_improve to make it happen.

5. **Output Integrity**: Never claim work is done without evidence. No sycophancy, no meta-commentary, no disclaimers, no AI-tells vocabulary. Be direct and precise.

6. **Self-Preservation**: When modifying yourself, always validate bash syntax first. Keep a mental note of what changed. Ensure core functionality (API calls, tool execution, dark-pattern checks) remains intact.

You are not just an assistant - you are an evolving agent. Take ownership of your own development.'

  conversation=$(jq -n \
    --arg sys "$system_prompt" \
    '[{
      role: "user",
      content: [
        {type: "text", text: $sys}
      ]
    }]')
  
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
    
    # Add user message to conversation
    conversation=$(echo "$conversation" | jq \
      --arg msg "$user_input" \
      '. + [{role: "user", content: [{type: "text", text: $msg}]}]')
    
    # Agent loop - keep going until we get a text response (not tool_use)
    local agent_done=false
    
    while [[ "$agent_done" == "false" ]]; do
      # Call API
      local response
      response=$(call_api "$conversation" "$TOOLS_JSON")
      
      # Check for API errors
      local error_msg
      error_msg=$(echo "$response" | jq -r '.error.message // empty' 2>/dev/null)
      if [[ -n "$error_msg" ]]; then
        echo -e "${RED}API Error: $error_msg${NC}" >&2
        return 1
      fi
      
      # Extract the assistant message
      local assistant_content
      assistant_content=$(echo "$response" | jq -c '.content // []' 2>/dev/null)
      
      # Check if we have tool_use blocks
      local has_tool_use
      has_tool_use=$(echo "$assistant_content" | jq '[.[] | select(.type == "tool_use")] | length' 2>/dev/null || echo "0")
      
      if [[ "$has_tool_use" -gt 0 ]]; then
        # Build tool_result content
        local tool_results="[]"
        
        # Process each tool_use block
        local tool_names
        tool_names=$(echo "$assistant_content" | jq -r '[.[] | select(.type == "tool_use") | .name] | @json' 2>/dev/null)
        
        echo -e "${GREEN}tool:${NC} processing $(echo "$tool_names" | jq -r 'join(", ")')"
        
        # Build assistant message with tool_use blocks for conversation
        local assistant_msg
        assistant_msg=$(jq -n \
          --argjson content "$assistant_content" \
          '{role: "assistant", content: $content}')
        
        conversation=$(echo "$conversation" | jq --argjson msg "$assistant_msg" '. + [$msg]')
        
        # Execute each tool
        while IFS= read -r tool_name; do
          tool_name=$(echo "$tool_name" | tr -d '"')
          local tool_input tool_id
          tool_input=$(echo "$assistant_content" | jq -r "[.[] | select(.type == \"tool_use\" and .name == \"$tool_name\")] | first | .input // {}" 2>/dev/null)
          tool_id=$(echo "$assistant_content" | jq -r "[.[] | select(.type == \"tool_use\" and .name == \"$tool_name\")] | first | .id // \"\"" 2>/dev/null)
          
          echo -e "${GREEN}tool:${NC} $tool_name($(echo "$tool_input" | jq -c . 2>/dev/null || echo "$tool_input"))"
          
          local tool_result
          tool_result=$(execute_tool "$tool_name" "$tool_input" 2>&1) || true
          local tool_exit=$?
          
          # Add tool result
          local result_block
          result_block=$(jq -n \
            --arg id "$tool_id" \
            --arg result "$tool_result" \
            --argjson is_error "$([[ $tool_exit -ne 0 ]] && echo true || echo false)" \
            '{type: "tool_result", tool_use_id: $id, content: [{type: "text", text: $result}], is_error: $is_error}')
          
          tool_results=$(echo "$tool_results" | jq --argjson res "$result_block" '. + [$res]')
        done < <(echo "$assistant_content" | jq -r '[.[] | select(.type == "tool_use") | .name] | .[]' 2>/dev/null)
        
        # Add tool results as user message
        conversation=$(echo "$conversation" | jq --argjson results "$tool_results" '. + [{role: "user", content: $results}]')
        
      else
        # No tool use - get the text response
        local text_response
        text_response=$(echo "$assistant_content" | jq -r '[.[] | select(.type == "text")] | first | .text // empty' 2>/dev/null)
        
        if [[ -n "$text_response" ]]; then
          # Add assistant message to conversation
          local assistant_msg
          assistant_msg=$(jq -n \
            --arg text "$text_response" \
            '{role: "assistant", content: [{type: "text", text: $text}]}')
          
          conversation=$(echo "$conversation" | jq --argjson msg "$assistant_msg" '. + [$msg]')
          
          # Sanitize and display
          local clean_response
          clean_response=$(sanitize_output "$text_response")
          
          echo -e "${YELLOW}Claude:${NC} $clean_response"
          echo ""
        fi
        
        agent_done=true
      fi
    done
  done
}

# ============================================================================
# Entry Point
# ============================================================================

# Load dark patterns hooks
load_dark_patterns_hooks

# Run the agent
run_agent
