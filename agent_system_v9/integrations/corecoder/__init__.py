"""
CoreCoder Integration
Lightweight coding agent as V9 tools
"""
from .tool_synthesizer import register_corecoder_tools, CoreCoderToolSynthesizer, CORECODER_COMMANDS

__all__ = [
    "register_corecoder_tools",
    "CoreCoderToolSynthesizer",
    "CORECODER_COMMANDS",
]