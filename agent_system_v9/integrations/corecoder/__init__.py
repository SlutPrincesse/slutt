"""
CoreCoder Integration
Lightweight coding agent as V9 tools
"""
from .tool_synthesizer import CORECODER_COMMANDS, CoreCoderToolSynthesizer, register_corecoder_tools

__all__ = [
    "register_corecoder_tools",
    "CoreCoderToolSynthesizer",
    "CORECODER_COMMANDS",
]
