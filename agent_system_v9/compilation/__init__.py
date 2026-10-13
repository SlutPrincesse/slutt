"""
Runtime Dynamic Compilation & Reflection (Section 18)
"""
from .code_generator import (
    ASTToCodeConverter,
    CodeGenerator,
    CodeTemplate,
    GenerationContext,
    IncrementalCodeGenerator,
    JavaScriptCodeGenerator,
    PythonCodeGenerator,
    RustCodeGenerator,
    TargetLanguage,
    TypeScriptCodeGenerator,
    UniversalCodeGenerator,
)
from .hot_swap import (
    HotSwapLoader,
    IsolatedLoader,
    LazyLoader,
    LazyModuleProxy,
    LoadStatus,
    ModuleInfo,
    PluginManager,
    ReloadEvent,
    temporary_module,
)

# Alias for AGENT_SYSTEM_V9 main package to avoid naming conflict with core.plugins.PluginManager
CompilationPluginManager = PluginManager
from .memory_compiler import (
    ASTCompiler,
    BaseCompiler,
    BytecodeCompiler,
    CompilationPipeline,
    CompilationResult,
    CompilationStatus,
    CompilationTarget,
    CompilationUnit,
    HotReloader,
    IncrementalCompiler,
    JITCompiler,
    MemoryCache,
)
from .symbol_inspector import (
    CrossFileAnalyzer,
    Scope,
    Symbol,
    SymbolInspector,
    SymbolReference,
    SymbolTable,
    SymbolType,
    Visibility,
)
from .type_marshaller import (
    BinaryMarshaller,
    CrossLanguageTypeMapper,
    JSONMarshaller,
    Marshaller,
    SchemaValidator,
    TypeInfo,
    TypeKind,
    TypeMarshaller,
)

__all__ = [
    # Code Generator
    "UniversalCodeGenerator",
    "CodeGenerator",
    "PythonCodeGenerator",
    "JavaScriptCodeGenerator",
    "TypeScriptCodeGenerator",
    "RustCodeGenerator",
    "CodeTemplate",
    "GenerationContext",
    "TargetLanguage",
    "ASTToCodeConverter",
    "IncrementalCodeGenerator",
    # Symbol Inspector
    "SymbolInspector",
    "SymbolTable",
    "Symbol",
    "SymbolReference",
    "Scope",
    "SymbolType",
    "Visibility",
    "CrossFileAnalyzer",
    # Memory Compiler
    "JITCompiler",
    "HotReloader",
    "CompilationPipeline",
    "IncrementalCompiler",
    "CompilationUnit",
    "CompilationResult",
    "CompilationTarget",
    "CompilationStatus",
    "BaseCompiler",
    "BytecodeCompiler",
    "ASTCompiler",
    "MemoryCache",
    # Hot Swap
    "HotSwapLoader",
    "PluginManager",
    "CompilationPluginManager",
    "IsolatedLoader",
    "LazyLoader",
    "LazyModuleProxy",
    "ModuleInfo",
    "ReloadEvent",
    "LoadStatus",
    "temporary_module",
    # Type Marshaller
    "TypeMarshaller",
    "Marshaller",
    "JSONMarshaller",
    "BinaryMarshaller",
    "TypeInfo",
    "TypeKind",
    "SchemaValidator",
    "CrossLanguageTypeMapper",
]
