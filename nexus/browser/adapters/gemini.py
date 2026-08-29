from __future__ import annotations

import ast
import json
from typing import Any

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

from nexus.browser.adapters.base import LLMResponse, ToolCall


def _parse_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    try:
        return dict(json.loads(raw))
    except (json.JSONDecodeError, TypeError, ValueError, RecursionError):
        pass
    try:
        parsed = ast.literal_eval(raw)
        return dict(parsed) if isinstance(parsed, dict) else {}
    except (ValueError, SyntaxError, RecursionError):
        return {}


def _to_contents(
    messages: list[dict[str, Any]],
) -> tuple[str | None, list[Any]]:
    system_instruction: str | None = None
    contents: list[Any] = []
    call_names: dict[str, str] = {}

    for msg in messages:
        role = msg.get("role")
        if role == "system":
            system_instruction = msg.get("content")
            continue
        if role == "user":
            contents.append(
                genai_types.Content(
                    role="user", parts=[genai_types.Part.from_text(text=msg.get("content") or "")]
                )
            )
        elif role == "assistant":
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                parts = []
                for tc in tool_calls:
                    fn = tc["function"]
                    call_names[tc.get("id", "")] = fn["name"]
                    parts.append(
                        genai_types.Part.from_function_call(
                            name=fn["name"], args=_parse_args(fn.get("arguments"))
                        )
                    )
                contents.append(genai_types.Content(role="model", parts=parts))
            else:
                content = msg.get("content")
                if content:
                    part = genai_types.Part.from_text(text=content)
                    contents.append(genai_types.Content(role="model", parts=[part]))
        elif role == "tool":
            name = call_names.get(msg.get("tool_call_id", ""), "")
            contents.append(
                genai_types.Content(
                    role="user",
                    parts=[
                        genai_types.Part.from_function_response(
                            name=name, response={"result": msg.get("content")}
                        )
                    ],
                )
            )

    return system_instruction, contents


def _to_gemini_tools(tools: list[dict[str, Any]]) -> list[Any]:
    declarations = []
    for tool in tools:
        fn = tool["function"]
        params = fn.get("parameters")
        kwargs: dict[str, Any] = {"name": fn["name"], "description": fn.get("description")}
        if params and params.get("properties"):
            kwargs["parameters_json_schema"] = params
        declarations.append(genai_types.FunctionDeclaration(**kwargs))
    return [genai_types.Tool(function_declarations=declarations)]


class GeminiAdapter:
    def __init__(self, api_key: str | None = None, model: str = "gemini-2.0-flash") -> None:
        if genai is None:
            raise ImportError("pip install google-genai")
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> LLMResponse:
        system_instruction, contents = _to_contents(messages)
        config = genai_types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=_to_gemini_tools(tools) if tools else None,
        )
        response = await self._client.aio.models.generate_content(
            model=self._model, contents=contents, config=config
        )
        function_calls = response.function_calls
        if function_calls:
            fc = function_calls[0]
            return LLMResponse(
                content=None,
                tool_call=ToolCall(name=fc.name or "", arguments=fc.args or {}),
            )
        return LLMResponse(content=response.text, tool_call=None)
