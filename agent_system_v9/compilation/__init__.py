"""
Runtime Dynamic Compilation & Reflection (Section 18)
Universal AST Code Generator, Dynamic Symbol & Export Inspector,
In-Memory Compilation Engine, Hot-Swappable Module Loader,
Cross-Language Type Marshaller
"""
from .code_generator import UniversalCodeGenerator, GeneratedCode
from .symbol_inspector import SymbolInspector, SymbolInfo
from .memory_compiler import MemoryCompiler, CompilationUnit
from .hot_swap import HotSwapLoader, SwapResult
from .type_marshaller import TypeMarshaller, MarshalledValue

__all__ = [
    "UniversalCodeGenerator",
    "GeneratedCode",
    "SymbolInspector",
    "SymbolInfo",
    "MemoryCompiler",
    "CompilationUnit",
    "HotSwapLoader",
    "SwapResult",
    "TypeMarshaller",
    "MarshalledValue",
]