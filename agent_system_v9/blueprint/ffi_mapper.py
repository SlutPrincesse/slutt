"""
FFI Mapper - Foreign Function Interface mapping between languages
"""
import ctypes
import platform
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class CallingConvention(Enum):
    CDECL = "cdecl"
    STDCALL = "stdcall"
    FASTCALL = "fastcall"
    THISCALL = "thiscall"
    SYSV_AMD64 = "sysv_amd64"
    WIN64 = "win64"


class FFIBasicType(Enum):
    VOID = "void"
    BOOL = "bool"
    INT8 = "int8"
    UINT8 = "uint8"
    INT16 = "int16"
    UINT16 = "uint16"
    INT32 = "int32"
    UINT32 = "uint32"
    INT64 = "int64"
    UINT64 = "uint64"
    FLOAT32 = "float32"
    FLOAT64 = "float64"
    POINTER = "pointer"
    STRING = "string"
    WSTRING = "wstring"


@dataclass
class FFIType:
    name: str
    basic_type: FFIBasicType | None = None
    is_pointer: bool = False
    is_array: bool = False
    array_size: int | None = None
    struct_fields: list['FFIType'] = field(default_factory=list)
    enum_values: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "basic_type": self.basic_type.value if self.basic_type else None,
            "is_pointer": self.is_pointer,
            "is_array": self.is_array,
            "array_size": self.array_size,
            "struct_fields": [f.to_dict() for f in self.struct_fields],
            "enum_values": self.enum_values,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'FFIType':
        return cls(
            name=data["name"],
            basic_type=FFIBasicType(data["basic_type"]) if data.get("basic_type") else None,
            is_pointer=data.get("is_pointer", False),
            is_array=data.get("is_array", False),
            array_size=data.get("array_size"),
            struct_fields=[cls.from_dict(f) for f in data.get("struct_fields", [])],
            enum_values=data.get("enum_values", {}),
            metadata=data.get("metadata", {}),
        )


@dataclass
class FFIFunction:
    name: str
    return_type: FFIType
    parameters: list[FFIType] = field(default_factory=list)
    calling_convention: CallingConvention = CallingConvention.CDECL
    is_variadic: bool = False
    library: str = ""
    symbol: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "return_type": self.return_type.to_dict(),
            "parameters": [p.to_dict() for p in self.parameters],
            "calling_convention": self.calling_convention.value,
            "is_variadic": self.is_variadic,
            "library": self.library,
            "symbol": self.symbol,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'FFIFunction':
        return cls(
            name=data["name"],
            return_type=FFIType.from_dict(data["return_type"]),
            parameters=[FFIType.from_dict(p) for p in data.get("parameters", [])],
            calling_convention=CallingConvention(data.get("calling_convention", "cdecl")),
            is_variadic=data.get("is_variadic", False),
            library=data.get("library", ""),
            symbol=data.get("symbol", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class FFILibrary:
    name: str
    path: str
    functions: list[FFIFunction] = field(default_factory=list)
    types: dict[str, FFIType] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "functions": [f.to_dict() for f in self.functions],
            "types": {k: v.to_dict() for k, v in self.types.items()},
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'FFILibrary':
        return cls(
            name=data["name"],
            path=data["path"],
            functions=[FFIFunction.from_dict(f) for f in data.get("functions", [])],
            types={k: FFIType.from_dict(v) for k, v in data.get("types", {}).items()},
            metadata=data.get("metadata", {}),
        )


class FFIMapper:
    def __init__(self):
        self.libraries: dict[str, FFILibrary] = {}
        self.type_mappings: dict[str, Any] = {}
        self._init_ctypes_mappings()

    def _init_ctypes_mappings(self):
        self.type_mappings = {
            FFIBasicType.VOID: None,
            FFIBasicType.BOOL: ctypes.c_bool,
            FFIBasicType.INT8: ctypes.c_int8,
            FFIBasicType.UINT8: ctypes.c_uint8,
            FFIBasicType.INT16: ctypes.c_int16,
            FFIBasicType.UINT16: ctypes.c_uint16,
            FFIBasicType.INT32: ctypes.c_int32,
            FFIBasicType.UINT32: ctypes.c_uint32,
            FFIBasicType.INT64: ctypes.c_int64,
            FFIBasicType.UINT64: ctypes.c_uint64,
            FFIBasicType.FLOAT32: ctypes.c_float,
            FFIBasicType.FLOAT64: ctypes.c_double,
            FFIBasicType.POINTER: ctypes.c_void_p,
            FFIBasicType.STRING: ctypes.c_char_p,
            FFIBasicType.WSTRING: ctypes.c_wchar_p,
        }

    def load_library(self, path: str, name: str | None = None) -> FFILibrary:
        if name is None:
            name = Path(path).stem

        lib = FFILibrary(name=name, path=path)

        try:
            if platform.system() == "Windows":
                ctypes_lib = ctypes.WinDLL(path)
            else:
                ctypes_lib = ctypes.CDLL(path)
            lib.metadata["ctypes_handle"] = ctypes_lib
        except Exception as e:
            lib.metadata["load_error"] = str(e)

        self.libraries[name] = lib
        return lib

    def register_function(self, library_name: str, func: FFIFunction):
        if library_name in self.libraries:
            self.libraries[library_name].functions.append(func)
            self._bind_function(self.libraries[library_name], func)

    def _bind_function(self, lib: FFILibrary, func: FFIFunction):
        if "ctypes_handle" not in lib.metadata:
            return

        ctypes_lib = lib.metadata["ctypes_handle"]

        try:
            c_func = getattr(ctypes_lib, func.symbol or func.name)

            c_func.restype = self._ffi_type_to_ctypes(func.return_type)
            c_func.argtypes = [self._ffi_type_to_ctypes(p) for p in func.parameters]

            func.metadata["ctypes_func"] = c_func
        except Exception as e:
            func.metadata["bind_error"] = str(e)

    def _ffi_type_to_ctypes(self, ffi_type: FFIType):
        if ffi_type.basic_type and ffi_type.basic_type in self.type_mappings:
            ctype = self.type_mappings[ffi_type.basic_type]
            if ffi_type.is_pointer:
                return ctypes.POINTER(ctype) if ctype else ctypes.c_void_p
            if ffi_type.is_array and ffi_type.array_size:
                return ctype * ffi_type.array_size
            return ctype

        if ffi_type.struct_fields:
            return self._create_struct_type(ffi_type)

        return ctypes.c_void_p

    def _create_struct_type(self, ffi_type: FFIType):
        class DynamicStruct(ctypes.Structure):
            _fields_ = [
                (field.name, self._ffi_type_to_ctypes(field))
                for field in ffi_type.struct_fields
            ]
        DynamicStruct.__name__ = ffi_type.name
        return DynamicStruct

    def call(self, library_name: str, function_name: str, *args) -> Any:
        if library_name not in self.libraries:
            raise ValueError(f"Library not loaded: {library_name}")

        lib = self.libraries[library_name]
        func = next((f for f in lib.functions if f.name == function_name), None)

        if not func:
            raise ValueError(f"Function not found: {function_name}")

        if "ctypes_func" not in func.metadata:
            raise ValueError(f"Function not bound: {function_name}")

        c_func = func.metadata["ctypes_func"]

        converted_args = []
        for i, (arg, param_type) in enumerate(zip(args, func.parameters)):
            converted_args.append(self._convert_arg(arg, param_type))

        result = c_func(*converted_args)
        return self._convert_result(result, func.return_type)

    def _convert_arg(self, value: Any, ffi_type: FFIType) -> Any:
        if ffi_type.basic_type == FFIBasicType.STRING and isinstance(value, str):
            return value.encode('utf-8')
        if ffi_type.basic_type == FFIBasicType.WSTRING and isinstance(value, str):
            return value
        if ffi_type.basic_type == FFIBasicType.POINTER and isinstance(value, (bytes, bytearray)):
            return ctypes.c_char_p(value)
        return value

    def _convert_result(self, value: Any, ffi_type: FFIType) -> Any:
        if ffi_type.basic_type == FFIBasicType.STRING and isinstance(value, bytes):
            return value.decode('utf-8')
        if ffi_type.basic_type == FFIBasicType.WSTRING and isinstance(value, int):
            return ctypes.wstring_at(value)
        return value

    def generate_bindings(self, library_name: str, target: str = "python") -> str:
        if library_name not in self.libraries:
            raise ValueError(f"Library not loaded: {library_name}")

        lib = self.libraries[library_name]

        if target == "python":
            return self._generate_python_bindings(lib)
        if target == "c":
            return self._generate_c_header(lib)
        if target == "rust":
            return self._generate_rust_bindings(lib)
        raise ValueError(f"Unknown target: {target}")

    def _generate_python_bindings(self, lib: FFILibrary) -> str:
        lines = [
            f"# Auto-generated bindings for {lib.name}",
            f"# Library: {lib.path}",
            "",
            "import ctypes",
            "from typing import Any, Optional",
            "",
        ]

        for func in lib.functions:
            params = []
            for param in func.parameters:
                param_name = param.name or f"arg{len(params)}"
                ctype = self._ffi_type_to_ctypes(param).__name__ if hasattr(self._ffi_type_to_ctypes(param), '__name__') else "c_void_p"
                params.append(f"{param_name}: {ctype}")

            return_type = self._ffi_type_to_ctypes(func.return_type)
            return_name = return_type.__name__ if hasattr(return_type, '__name__') else "c_void_p"

            lines.append(f"def {func.name}({', '.join(params)}) -> {return_name}:")
            lines.append(f'    """Call {func.name} from {lib.name}"""')
            lines.append(f"    lib = ctypes.CDLL(r'{lib.path}')")
            lines.append(f"    func = lib.{func.symbol or func.name}")
            lines.append(f"    func.restype = {return_name}")
            if func.parameters:
                argtypes = ", ".join([
                    self._ffi_type_to_ctypes(p).__name__ if hasattr(self._ffi_type_to_ctypes(p), '__name__') else "c_void_p"
                    for p in func.parameters
                ])
                lines.append(f"    func.argtypes = [{argtypes}]")
            lines.append(f"    return func({', '.join([p.split(':')[0].strip() for p in params])})")
            lines.append("")

        return "\n".join(lines)

    def _generate_c_header(self, lib: FFILibrary) -> str:
        lines = [
            f"// Auto-generated header for {lib.name}",
            f"// Library: {lib.path}",
            "",
            "#ifndef __AUTO_GEN_H__",
            "#define __AUTO_GEN_H__",
            "",
        ]

        for func in lib.functions:
            params = []
            for param in func.parameters:
                c_type = self._basic_type_to_c(param.basic_type)
                if param.is_pointer:
                    c_type += "*"
                param_name = param.name or f"arg{len(params)}"
                params.append(f"{c_type} {param_name}")

            return_type = self._basic_type_to_c(func.return_type.basic_type)
            if func.return_type.is_pointer:
                return_type += "*"

            lines.append(f"{return_type} {func.name}({', '.join(params)});")

        lines.extend(["", "#endif // __AUTO_GEN_H__", ""])
        return "\n".join(lines)

    def _basic_type_to_c(self, basic_type: FFIBasicType | None) -> str:
        if not basic_type:
            return "void"
        mapping = {
            FFIBasicType.VOID: "void",
            FFIBasicType.BOOL: "bool",
            FFIBasicType.INT8: "int8_t",
            FFIBasicType.UINT8: "uint8_t",
            FFIBasicType.INT16: "int16_t",
            FFIBasicType.UINT16: "uint16_t",
            FFIBasicType.INT32: "int32_t",
            FFIBasicType.UINT32: "uint32_t",
            FFIBasicType.INT64: "int64_t",
            FFIBasicType.UINT64: "uint64_t",
            FFIBasicType.FLOAT32: "float",
            FFIBasicType.FLOAT64: "double",
            FFIBasicType.POINTER: "void*",
            FFIBasicType.STRING: "const char*",
            FFIBasicType.WSTRING: "const wchar_t*",
        }
        return mapping.get(basic_type, "void")

    def _generate_rust_bindings(self, lib: FFILibrary) -> str:
        lines = [
            f"// Auto-generated Rust bindings for {lib.name}",
            f"// Library: {lib.path}",
            "",
            "use std::os::raw::*;",
            "use std::ffi::*;",
            "",
            f"#[link(name = \"{lib.name}\")]",
            "extern \"C\" {",
        ]

        for func in lib.functions:
            params = []
            for param in func.parameters:
                rust_type = self._basic_type_to_rust(param.basic_type)
                if param.is_pointer:
                    rust_type = f"*const {rust_type}"
                param_name = param.name or f"arg{len(params)}"
                params.append(f"{param_name}: {rust_type}")

            return_type = self._basic_type_to_rust(func.return_type.basic_type)
            if func.return_type.is_pointer:
                return_type = f"*mut {return_type}"

            lines.append(f"    pub fn {func.name}({', '.join(params)}) -> {return_type};")

        lines.extend(["}", ""])
        return "\n".join(lines)

    def _basic_type_to_rust(self, basic_type: FFIBasicType | None) -> str:
        if not basic_type:
            return "c_void"
        mapping = {
            FFIBasicType.VOID: "c_void",
            FFIBasicType.BOOL: "bool",
            FFIBasicType.INT8: "i8",
            FFIBasicType.UINT8: "u8",
            FFIBasicType.INT16: "i16",
            FFIBasicType.UINT16: "u16",
            FFIBasicType.INT32: "i32",
            FFIBasicType.UINT32: "u32",
            FFIBasicType.INT64: "i64",
            FFIBasicType.UINT64: "u64",
            FFIBasicType.FLOAT32: "f32",
            FFIBasicType.FLOAT64: "f64",
            FFIBasicType.POINTER: "c_void",
            FFIBasicType.STRING: "c_char",
            FFIBasicType.WSTRING: "c_wchar",
        }
        return mapping.get(basic_type, "c_void")

    def parse_c_header(self, header_path: str) -> FFILibrary:
        import re

        content = Path(header_path).read_text()
        lib = FFILibrary(name=Path(header_path).stem, path=header_path)

        func_pattern = re.compile(
            r'(\w+(?:\s*\*)?)\s+(\w+)\s*\(([^)]*)\)\s*;'
        )

        for match in func_pattern.finditer(content):
            return_type_str, func_name, params_str = match.groups()

            return_type = self._parse_c_type(return_type_str.strip())

            params = []
            for param_str in params_str.split(','):
                param_str = param_str.strip()
                if not param_str:
                    continue
                param_type = self._parse_c_type(param_str)
                params.append(param_type)

            func = FFIFunction(
                name=func_name,
                return_type=return_type,
                parameters=params,
                library=lib.name,
                symbol=func_name,
            )
            lib.functions.append(func)

        return lib

    def _parse_c_type(self, type_str: str) -> FFIType:
        is_pointer = '*' in type_str
        clean_type = type_str.replace('*', '').replace('const', '').strip()

        basic_mapping = {
            'void': FFIBasicType.VOID,
            'bool': FFIBasicType.BOOL,
            'int8_t': FFIBasicType.INT8,
            'uint8_t': FFIBasicType.UINT8,
            'int16_t': FFIBasicType.INT16,
            'uint16_t': FFIBasicType.UINT16,
            'int32_t': FFIBasicType.INT32,
            'uint32_t': FFIBasicType.UINT32,
            'int64_t': FFIBasicType.INT64,
            'uint64_t': FFIBasicType.UINT64,
            'float': FFIBasicType.FLOAT32,
            'double': FFIBasicType.FLOAT64,
            'char*': FFIBasicType.STRING,
            'const char*': FFIBasicType.STRING,
            'wchar_t*': FFIBasicType.WSTRING,
        }

        basic_type = basic_mapping.get(clean_type)
        if basic_type is None and clean_type.endswith('_t'):
            basic_type = FFIBasicType.INT32

        return FFIType(
            name=clean_type,
            basic_type=basic_type,
            is_pointer=is_pointer,
        )
