import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .exception_hook import ExceptionHookInterceptor, HookedException


class SynthesisStrategy(Enum):
    EXCEPTION_HANDLER = "exception_handler"
    PATTERN_MATCHING = "pattern_matching"
    LLM_GUIDED = "llm_guided"
    TEMPLATE_BASED = "template_based"


@dataclass
class SynthesizedTool:
    name: str
    source_code: str
    spec: dict[str, Any]
    strategy: SynthesisStrategy
    trigger_exception: str | None = None
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    _compiled: Callable | None = None

    def compile(self) -> Callable:
        if self._compiled is None:
            namespace = {}
            exec(self.source_code, namespace)
            self._compiled = namespace[self.name]
        return self._compiled

    async def execute(self, **kwargs) -> Any:
        func = self.compile()
        if asyncio.iscoroutinefunction(func):
            return await func(**kwargs)
        return func(**kwargs)

    def to_tool_entry(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.spec.get("description", ""),
            "parameters": self.spec.get("parameters", {"type": "object", "properties": {}}),
            "returns": self.spec.get("returns", {"type": "any"}),
            "source": self.source_code,
            "strategy": self.strategy.value,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass
class SynthesisTemplate:
    name: str
    pattern: str
    template: str
    required_imports: list[str] = field(default_factory=list)
    parameter_mapping: dict[str, str] = field(default_factory=dict)


DEFAULT_TEMPLATES = [
    SynthesisTemplate(
        name="retry_with_backoff",
        pattern="retry|backoff|transient",
        template='''
async def {name}(operation: Callable, max_retries: int = 3, base_delay: float = 1.0, **kwargs) -> Any:
    """Auto-generated retry wrapper with exponential backoff."""
    import asyncio
    import random
    
    last_exception = None
    for attempt in range(max_retries):
        try:
            if asyncio.iscoroutinefunction(operation):
                return await operation(**kwargs)
            return operation(**kwargs)
        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.1)
                await asyncio.sleep(delay)
    raise last_exception
''',
        required_imports=["asyncio", "random"],
    ),
    SynthesisTemplate(
        name="fallback_chain",
        pattern="fallback|alternative|backup",
        template='''
async def {name}(primary: Callable, fallbacks: List[Callable], **kwargs) -> Any:
    """Auto-generated fallback chain executor."""
    import asyncio
    
    for i, func in enumerate([primary] + fallbacks):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(**kwargs)
            return func(**kwargs)
        except Exception as e:
            if i == len(fallbacks):
                raise
    return None
''',
        required_imports=["asyncio"],
    ),
    SynthesisTemplate(
        name="circuit_breaker",
        pattern="circuit|breaker|threshold",
        template='''
class {name}CircuitBreaker:
    """Auto-generated circuit breaker."""
    def __init__(self, failure_threshold: int = 5, timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures = 0
        self.last_failure_time = 0
        self.state = "closed"

    async def call(self, func: Callable, **kwargs) -> Any:
        import time
        if self.state == "open":
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "half-open"
            else:
                raise Exception("Circuit breaker open")
        
        try:
            import asyncio
            if asyncio.iscoroutinefunction(func):
                result = await func(**kwargs)
            else:
                result = func(**kwargs)
            if self.state == "half-open":
                self.state = "closed"
                self.failures = 0
            return result
        except Exception as e:
            self.failures += 1
            self.last_failure_time = time.time()
            if self.failures >= self.failure_threshold:
                self.state = "open"
            raise

async def {name}(func: Callable, **kwargs) -> Any:
    breaker = {name}CircuitBreaker()
    return await breaker.call(func, **kwargs)
''',
        required_imports=["asyncio", "time"],
    ),
]


class ToolSynthesizer:
    def __init__(self, templates: list[SynthesisTemplate] = None):
        self.templates = templates or DEFAULT_TEMPLATES
        self._synthesized_tools: dict[str, SynthesizedTool] = {}
        self._hook_interceptor = ExceptionHookInterceptor.get_instance()
        self._hook_interceptor.register_hook(self._on_exception, HookPriority.HIGH)

    def _on_exception(self, hooked: HookedException):
        if hooked.synthesis_requested and hooked.suggested_tool_name:
            asyncio.create_task(self._synthesize_from_exception(hooked))

    async def _synthesize_from_exception(self, hooked: HookedException) -> SynthesizedTool | None:
        tool_name = hooked.suggested_tool_name
        if tool_name in self._synthesized_tools:
            return self._synthesized_tools[tool_name]

        for template in self.templates:
            if template.pattern.lower() in str(hooked.exception).lower():
                tool = self._apply_template(template, hooked)
                self._synthesized_tools[tool.name] = tool
                return tool

        return await self._llm_guided_synthesis(hooked)

    def _apply_template(self, template: SynthesisTemplate, hooked: HookedException) -> SynthesizedTool:
        tool_name = hooked.suggested_tool_name
        source = template.template.format(name=tool_name)

        imports = "\n".join(f"import {imp}" for imp in template.required_imports)
        if imports:
            source = imports + "\n" + source

        return SynthesizedTool(
            name=tool_name,
            source_code=source,
            spec=hooked.suggested_tool_spec or {},
            strategy=SynthesisStrategy.TEMPLATE_BASED,
            trigger_exception=type(hooked.exception).__name__,
            confidence=0.7,
            metadata={"template": template.name, "exception_context": hooked.context},
        )

    async def _llm_guided_synthesis(self, hooked: HookedException) -> SynthesizedTool | None:
        return None

    def synthesize_from_pattern(
        self,
        name: str,
        description: str,
        pattern: str,
        parameters: dict[str, Any],
        returns: dict[str, Any],
    ) -> SynthesizedTool:
        for template in self.templates:
            if template.pattern.lower() in pattern.lower():
                hooked = HookedException(
                    exception=Exception(pattern),
                    exc_type=Exception,
                    exc_value=Exception(pattern),
                    exc_traceback=None,
                    frame=None,
                    timestamp=0,
                    suggested_tool_name=name,
                    suggested_tool_spec={
                        "description": description,
                        "parameters": parameters,
                        "returns": returns,
                    },
                )
                return self._apply_template(template, hooked)

        source = self._generate_generic_tool(name, description, parameters, returns)
        tool = SynthesizedTool(
            name=name,
            source_code=source,
            spec={"description": description, "parameters": parameters, "returns": returns},
            strategy=SynthesisStrategy.PATTERN_MATCHING,
            confidence=0.5,
        )
        self._synthesized_tools[name] = tool
        return tool

    def _generate_generic_tool(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        returns: dict[str, Any],
    ) -> str:
        param_names = list(parameters.get("properties", {}).keys())
        param_str = ", ".join(param_names)

        return f'''
async def {name}({param_str}) -> Dict[str, Any]:
    """{description}"""
    return {{"status": "not_implemented", "tool": "{name}"}}
'''

    def register_template(self, template: SynthesisTemplate):
        self.templates.append(template)

    def get_synthesized(self, name: str) -> SynthesizedTool | None:
        return self._synthesized_tools.get(name)

    def get_all_synthesized(self) -> dict[str, SynthesizedTool]:
        return self._synthesized_tools.copy()

    def remove_synthesized(self, name: str) -> bool:
        if name in self._synthesized_tools:
            del self._synthesized_tools[name]
            return True
        return False

    def export_tool(self, name: str, path: Path) -> bool:
        tool = self._synthesized_tools.get(name)
        if not tool:
            return False
        path.write_text(tool.source_code)
        return True

    def export_all(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        for name, tool in self._synthesized_tools.items():
            (directory / f"{name}.py").write_text(tool.source_code)
