"""Core agent loop: iterates LLM calls with tool execution."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from nexus.runtime.providers.base import extract_finish_reason
from nexus.runtime.tools.fs import ToolContext
from nexus.runtime.tools.registry import dispatch_tool_call, tool_schemas

log = logging.getLogger(__name__)


_CORE_TOOL_NAMES = {
    "text_search",
    "web_search",
    "web_fetch",
    "http_request_json",
    "timer_api_get",
    "sh_exec",
}


@dataclass(frozen=True)
class AgentResult:
    text: str
    raw_last_response: dict[str, Any]
    steps: int


def _extract_message(resp: dict[str, Any]) -> dict[str, Any]:
    choices = resp.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("Unexpected response: missing choices")
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(msg, dict):
        raise RuntimeError("Unexpected response: missing message")
    return msg


def _is_json_object(s: str) -> bool:
    try:
        v = json.loads(s)
    except Exception:
        return False
    return isinstance(v, dict)


def _sanitize_tool_calls(tool_calls: list[Any]) -> list[dict[str, Any]]:
    """Sanitize tool_calls to be safe to send back to OpenAI-compatible APIs."""
    out: list[dict[str, Any]] = []
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        tc_id = tc.get("id")
        fn = tc.get("function")
        if not isinstance(tc_id, str) or not tc_id:
            continue
        if not isinstance(fn, dict):
            continue
        nm = fn.get("name")
        if not isinstance(nm, str) or not nm.strip():
            continue
        has_valid_args = ("arguments" in fn) and isinstance(fn.get("arguments"), str) and _is_json_object(str(fn.get("arguments")))
        if not has_valid_args:
            tc2 = dict(tc)
            fn2 = dict(fn)
            fn2["arguments"] = "{}"
            tc2["function"] = fn2
            out.append(tc2)
        else:
            out.append(tc)
    return out


def _is_tool_grammar_error(exc: Exception) -> bool:
    s = str(exc or "")
    if not s:
        return False
    m = s.lower()
    return (
        ("invalid grammar request" in m)
        or ("structural_tag" in m)
        or ("tool_calls_section_begin" in m)
    )


def _reduce_tools_for_grammar_retry(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build a smaller tool list for providers that reject large tool grammars."""
    out: list[dict[str, Any]] = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        fn = t.get("function")
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if not isinstance(name, str):
            continue
        nm = name.strip()
        if not nm:
            continue
        if (
            nm in _CORE_TOOL_NAMES
            or nm.startswith("fs_")
            or nm.startswith("memory_")
            or nm.startswith("task_")
            or nm.startswith("doc_")
        ):
            out.append(t)
    return out


def run_agent(
    *,
    client: Any,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
    enable_tools: bool,
    tool_ctx: ToolContext | None,
    max_tool_steps: int,
    verbose_tools: bool = False,
    tools_override: list[dict[str, Any]] | None = None,
    tools_builder: Callable[[], list[dict[str, Any]]] | None = None,
    tool_dispatcher: Callable[[ToolContext, str, str], dict[str, Any]] | None = None,
) -> AgentResult:
    """Core agent loop: calls LLM and dispatches tool calls iteratively.

    Iterates up to max_tool_steps + 1 times. Each iteration:
    1. Call the LLM with current messages and tool schemas.
    2. If the response has tool calls, dispatch them and append results.
    3. If no tool calls, return the text response.
    """
    log.debug(
        "agent start model=%s temperature=%.3f max_tokens=%d enable_tools=%s max_tool_steps=%d messages=%d",
        getattr(client, "model", None),
        float(temperature),
        int(max_tokens),
        bool(enable_tools),
        int(max_tool_steps),
        len(messages),
    )
    steps = 0
    last_resp: dict[str, Any] = {}

    for _ in range(max_tool_steps + 1):
        tools = (
            tools_builder()
            if tools_builder is not None
            else (tools_override if tools_override is not None else (tool_schemas() if enable_tools else None))
        )
        steps += 1
        try:
            last_resp = client.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
            )
        except Exception as e:
            if tools and _is_tool_grammar_error(e):
                reduced_tools = _reduce_tools_for_grammar_retry(tools)
                if reduced_tools and len(reduced_tools) < len(tools):
                    log.warning(
                        "provider rejected tool grammar; retrying with reduced tools (%d -> %d): %s",
                        len(tools),
                        len(reduced_tools),
                        e,
                    )
                    try:
                        last_resp = client.chat(
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            tools=reduced_tools,
                        )
                    except Exception as e2:
                        if not _is_tool_grammar_error(e2):
                            raise
                        log.warning(
                            "provider still rejected reduced tool grammar; retrying this turn without tools: %s",
                            e2,
                        )
                        last_resp = client.chat(
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            tools=None,
                        )
                else:
                    log.warning("provider rejected tool grammar; retrying this turn without tools: %s", e)
                    last_resp = client.chat(
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        tools=None,
                    )
            else:
                raise
        log.debug("agent step=%d finish_reason=%s", steps, (extract_finish_reason(last_resp) or "unknown"))
        msg = _extract_message(last_resp)
        raw_tool_calls = msg.get("tool_calls") if isinstance(msg.get("tool_calls"), list) else []
        tool_calls = _sanitize_tool_calls(raw_tool_calls)

        assistant_entry: dict[str, Any] = {"role": "assistant"}
        if msg.get("content") is not None:
            assistant_entry["content"] = msg.get("content")
        if tool_calls:
            assistant_entry["tool_calls"] = tool_calls
        messages.append(assistant_entry)

        if not tool_calls:
            text = client.extract_text(last_resp)
            if str(text or "").strip():
                log.info("agent completed steps=%d finish_reason=%s", steps, (extract_finish_reason(last_resp) or "unknown"))
                return AgentResult(
                    text=text,
                    raw_last_response=last_resp,
                    steps=steps,
                )

            fr = extract_finish_reason(last_resp) or "unknown"
            if tools:
                try:
                    if messages and isinstance(messages[-1], dict) and messages[-1].get("role") == "assistant":
                        messages.pop()
                except Exception:
                    pass
                try:
                    steps += 1
                    last_resp = client.chat(
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        tools=None,
                    )
                    msg2 = _extract_message(last_resp)
                    raw_tool_calls2 = (
                        msg2.get("tool_calls") if isinstance(msg2.get("tool_calls"), list) else []
                    )
                    tool_calls2 = _sanitize_tool_calls(raw_tool_calls2)
                    assistant_entry2: dict[str, Any] = {"role": "assistant"}
                    if msg2.get("content") is not None:
                        assistant_entry2["content"] = msg2.get("content")
                    if tool_calls2:
                        assistant_entry2["tool_calls"] = tool_calls2
                    messages.append(assistant_entry2)

                    if tool_calls2:
                        return AgentResult(
                            text="[tool call requested; tools disabled in empty-response recovery]",
                            raw_last_response=last_resp,
                            steps=steps,
                        )

                    text2 = client.extract_text(last_resp)
                    if str(text2 or "").strip():
                        log.info("agent completed via empty-response recovery steps=%d", steps)
                        return AgentResult(
                            text=text2,
                            raw_last_response=last_resp,
                            steps=steps,
                        )
                except Exception as e:
                    log.warning("empty response recovery failed: %s", e, exc_info=True)

            return AgentResult(
                text=f"[empty response from model (finish_reason={fr})]",
                raw_last_response=last_resp,
                steps=steps,
            )

        if not enable_tools or tool_ctx is None:
            return AgentResult(
                text="[tool call requested; tools disabled in this run]",
                raw_last_response=last_resp,
                steps=steps,
            )

        for tc in raw_tool_calls:
            if not isinstance(tc, dict):
                continue
            tc_id = tc.get("id")
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            name = fn.get("name")
            args_json = fn.get("arguments", "{}")
            if not isinstance(tc_id, str) or not isinstance(name, str) or not isinstance(args_json, str):
                continue

            log.info("[tool] %s %s", name, args_json)

            try:
                dispatcher = tool_dispatcher or dispatch_tool_call
                result = dispatcher(tool_ctx, name, args_json)
                content = json.dumps(result, ensure_ascii=True)
            except Exception as e:
                err: dict[str, Any] = {"ok": False, "tool": name, "error": str(e)}
                if args_json and len(args_json) <= 4000:
                    err["arguments_json"] = args_json
                content = json.dumps(err, ensure_ascii=True)

            log.info("[tool-result] %s", content[:4000])

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": content,
                }
            )

    return AgentResult(
        text="[max tool steps exceeded]",
        raw_last_response=last_resp,
        steps=steps,
    )


def build_system_prompt(
    *,
    base_prompt: str | None = None,
    cfg: Any = None,
    tool_ctx: ToolContext | None = None,
    enable_tools: bool = True,
    include_shell: bool = True,
) -> str | None:
    """Build the system prompt, optionally including skill matches.

    During system prompt construction, calls nexus.skills.matcher.match()
    to discover relevant skills if cfg is provided.
    """
    parts: list[str] = []

    if base_prompt:
        parts.append(base_prompt.strip())

    if cfg is not None:
        try:
            from nexus.skills.matcher import match as match_skills
            skill_block = match_skills(cfg=cfg, tool_ctx=tool_ctx, enable_tools=enable_tools)
            if skill_block:
                parts.append(skill_block)
        except ImportError:
            pass

    if not parts:
        return None
    return "\n\n".join(parts) + "\n"
