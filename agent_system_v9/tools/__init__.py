"""
Dynamic Tool Synthesis via Exception Hooks (Section 29)
Runtime Exception Hook Interceptor, Meta-Prompt Tool Synthesizer,
Dynamic Tool Registry Auto-Loader
"""
from .exception_hook import ExceptionHookInterceptor, HookedException
from .tool_registry import (
    DynamicToolRegistry,
    ToolEntry,
    ToolMetrics,
)
from .tool_synthesizer import SynthesizedTool, ToolSynthesizer
from .computer_use import ApprovalGuard, ComputerUseLoop
from .mcp_server import MCPServer

__all__ = [
    "ExceptionHookInterceptor",
    "HookedException",
    "ToolSynthesizer",
    "SynthesizedTool",
    "DynamicToolRegistry",
    "ToolEntry",
    "ToolMetrics",
    "ApprovalGuard",
    "ComputerUseLoop",
    "MCPServer",
]
