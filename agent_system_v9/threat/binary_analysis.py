"""
Binary Analysis & Disassembly Integration - Debugger and disassembler hooks
"""
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import Dict, List, Optional, Any, Callable, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from collections import defaultdict


class BinaryFormat(Enum):
    ELF = "elf"
    PE = "pe"
    MACHO = "macho"
    UNKNOWN = "unknown"


class Architecture(Enum):
    X86 = "x86"
    X86_64 = "x86_64"
    ARM = "arm"
    ARM64 = "arm64"
    MIPS = "mips"
    RISCV = "riscv"
    UNKNOWN = "unknown"


class AnalysisTool(Enum):
    GHIDRA = "ghidra"
    RADARE2 = "radare2"
    GDB = "gdb"
    OBJDUMP = "objdump"
    NM = "nm"
    STRINGS = "strings"
    READER = "readelf"


@dataclass
class BinaryInfo:
    file_path: str
    format: BinaryFormat
    architecture: Architecture
    bits: int
    endian: str
    entry_point: int
    sections: List[Dict] = field(default_factory=list)
    symbols: List[Dict] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)
    strings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FunctionInfo:
    address: int
    name: str
    size: int
    blocks: List[int] = field(default_factory=list)
    calls: List[int] = field(default_factory=list)
    called_by: List[int] = field(default_factory=list)
    instructions: List[Dict] = field(default_factory=list)
    stack_frame_size: int = 0
    calling_convention: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CFGNode:
    address: int
    instructions: List[Dict] = field(default_factory=list)
    successors: List[int] = field(default_factory=list)
    predecessors: List[int] = field(default_factory=list)
    is_entry: bool = False
    is_exit: bool = False


@dataclass
class ControlFlowGraph:
    function_address: int
    nodes: Dict[int, CFGNode] = field(default_factory=dict)
    edges: List[Tuple[int, int]] = field(default_factory=list)


class BinaryAnalyzer:
    def __init__(self):
        self.tools: Dict[AnalysisTool, str] = {}
        self._detect_tools()
        self.cache: Dict[str, BinaryInfo] = {}

    def _detect_tools(self):
        tool_paths = {
            AnalysisTool.GHIDRA: ["ghidra", "/opt/ghidra/ghidraRun"],
            AnalysisTool.RADARE2: ["r2", "radare2"],
            AnalysisTool.GDB: ["gdb"],
            AnalysisTool.OBJDUMP: ["objdump"],
            AnalysisTool.NM: ["nm"],
            AnalysisTool.STRINGS: ["strings"],
            AnalysisTool.READER: ["readelf"],
        }
        
        for tool, paths in tool_paths.items():
            for path in paths:
                if shutil.which(path):
                    self.tools[tool] = path
                    break

    def is_tool_available(self, tool: AnalysisTool) -> bool:
        return tool in self.tools

    async def analyze_binary(self, file_path: str, tools: List[AnalysisTool] = None) -> BinaryInfo:
        if file_path in self.cache:
            return self.cache[file_path]
        
        tools = tools or [AnalysisTool.OBJDUMP, AnalysisTool.READER, AnalysisTool.STRINGS, AnalysisTool.NM]
        
        info = BinaryInfo(file_path=file_path, format=BinaryFormat.UNKNOWN, architecture=Architecture.UNKNOWN, bits=0, endian="", entry_point=0)
        
        if AnalysisTool.OBJDUMP in tools and self.is_tool_available(AnalysisTool.OBJDUMP):
            await self._analyze_with_objdump(file_path, info)
        
        if AnalysisTool.READER in tools and self.is_tool_available(AnalysisTool.READER):
            await self._analyze_with_readelf(file_path, info)
        
        if AnalysisTool.STRINGS in tools and self.is_tool_available(AnalysisTool.STRINGS):
            await self._extract_strings(file_path, info)
        
        if AnalysisTool.NM in tools and self.is_tool_available(AnalysisTool.NM):
            await self._extract_symbols(file_path, info)
        
        self._detect_format_and_arch(info)
        self.cache[file_path] = info
        return info

    async def _analyze_with_objdump(self, file_path: str, info: BinaryInfo):
        try:
            result = await self._run_command([self.tools[AnalysisTool.OBJDUMP], "-f", file_path])
            self._parse_objdump_file_info(result.stdout, info)
            
            result = await self._run_command([self.tools[AnalysisTool.OBJDUMP], "-h", file_path])
            self._parse_objdump_sections(result.stdout, info)
            
            result = await self._run_command([self.tools[AnalysisTool.OBJDUMP], "-d", file_path])
            self._parse_objdump_disassembly(result.stdout, info)
        except Exception as e:
            info.metadata["objdump_error"] = str(e)

    async def _analyze_with_readelf(self, file_path: str, info: BinaryInfo):
        try:
            result = await self._run_command([self.tools[AnalysisTool.READER], "-h", file_path])
            self._parse_readelf_header(result.stdout, info)
            
            result = await self._run_command([self.tools[AnalysisTool.READER], "-s", file_path])
            self._parse_readelf_symbols(result.stdout, info)
            
            result = await self._run_command([self.tools[AnalysisTool.READER], "-d", file_path])
            self._parse_readelf_dynamic(result.stdout, info)
        except Exception as e:
            info.metadata["readelf_error"] = str(e)

    async def _extract_strings(self, file_path: str, info: BinaryInfo):
        try:
            result = await self._run_command([self.tools[AnalysisTool.STRINGS], "-n", "4", file_path])
            info.strings = [s for s in result.stdout.split('\n') if s.strip()]
        except Exception as e:
            info.metadata["strings_error"] = str(e)

    async def _extract_symbols(self, file_path: str, info: BinaryInfo):
        try:
            result = await self._run_command([self.tools[AnalysisTool.NM], "-C", file_path])
            for line in result.stdout.split('\n'):
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 3:
                        info.symbols.append({
                            "address": parts[0],
                            "type": parts[1],
                            "name": " ".join(parts[2:]),
                        })
        except Exception as e:
            info.metadata["nm_error"] = str(e)

    async def _run_command(self, cmd: List[str]) -> subprocess.CompletedProcess:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return subprocess.CompletedProcess(cmd, proc.returncode, stdout.decode(), stderr.decode())

    def _parse_objdump_file_info(self, output: str, info: BinaryInfo):
        for line in output.split('\n'):
            if 'file format' in line:
                fmt = line.split('file format')[-1].strip()
                if 'elf' in fmt.lower():
                    info.format = BinaryFormat.ELF
                elif 'pe' in fmt.lower():
                    info.format = BinaryFormat.PE
                elif 'mach' in fmt.lower():
                    info.format = BinaryFormat.MACHO
            elif 'architecture:' in line:
                arch = line.split('architecture:')[-1].strip()
                if 'x86-64' in arch or 'amd64' in arch:
                    info.architecture = Architecture.X86_64
                    info.bits = 64
                elif 'i386' in arch or 'i686' in arch:
                    info.architecture = Architecture.X86
                    info.bits = 32
                elif 'arm64' in arch or 'aarch64' in arch:
                    info.architecture = Architecture.ARM64
                    info.bits = 64
                elif 'arm' in arch:
                    info.architecture = Architecture.ARM
                    info.bits = 32
            elif 'start address' in line:
                addr = line.split('start address')[-1].strip()
                info.entry_point = int(addr, 16) if addr.startswith('0x') else int(addr)

    def _parse_objdump_sections(self, output: str, info: BinaryInfo):
        for line in output.split('\n'):
            if re.match(r'\s+\d+\s+\.\w+', line):
                parts = line.split()
                if len(parts) >= 5:
                    info.sections.append({
                        "name": parts[1],
                        "size": parts[2],
                        "vma": parts[3],
                        "lma": parts[4],
                        "flags": " ".join(parts[5:]) if len(parts) > 5 else "",
                    })

    def _parse_objdump_disassembly(self, output: str, info: BinaryInfo):
        current_func = None
        for line in output.split('\n'):
            match = re.match(r'^([0-9a-f]+)\s+<(.+)>:', line)
            if match:
                addr = int(match.group(1), 16)
                name = match.group(2)
                current_func = FunctionInfo(address=addr, name=name)
                continue
            
            if current_func:
                inst_match = re.match(r'\s+([0-9a-f]+):\s+([0-9a-f\s]+)\s+(\w+)', line)
                if inst_match:
                    current_func.instructions.append({
                        "address": int(inst_match.group(1), 16),
                        "bytes": inst_match.group(2).strip(),
                        "mnemonic": inst_match.group(3),
                    })

    def _parse_readelf_header(self, output: str, info: BinaryInfo):
        for line in output.split('\n'):
            if 'Class:' in line:
                if 'ELF64' in line:
                    info.bits = 64
                elif 'ELF32' in line:
                    info.bits = 32
            elif 'Data:' in line:
                if 'little' in line.lower():
                    info.endian = "little"
                elif 'big' in line.lower():
                    info.endian = "big"
            elif 'Machine:' in line:
                if 'x86-64' in line or 'AMD x86-64' in line:
                    info.architecture = Architecture.X86_64
                elif 'Intel 80386' in line:
                    info.architecture = Architecture.X86
                elif 'ARM' in line:
                    info.architecture = Architecture.ARM
                elif 'AArch64' in line:
                    info.architecture = Architecture.ARM64
            elif 'Entry point address:' in line:
                addr = line.split('Entry point address:')[-1].strip()
                info.entry_point = int(addr, 16) if addr.startswith('0x') else int(addr)

    def _parse_readelf_symbols(self, output: str, info: BinaryInfo):
        for line in output.split('\n'):
            if '@@' in line or re.match(r'\s+\d+:', line):
                parts = line.split()
                if len(parts) >= 8:
                    info.symbols.append({
                        "index": parts[0].rstrip(':'),
                        "value": parts[1],
                        "size": parts[2],
                        "type": parts[3],
                        "bind": parts[4],
                        "vis": parts[5],
                        "ndx": parts[6],
                        "name": " ".join(parts[7:]),
                    })

    def _parse_readelf_dynamic(self, output: str, info: BinaryInfo):
        for line in output.split('\n'):
            if 'NEEDED' in line:
                match = re.search(r'\[(.+)\]', line)
                if match:
                    info.imports.append(match.group(1))

    def _detect_format_and_arch(self, info: BinaryInfo):
        if info.format == BinaryFormat.UNKNOWN:
            with open(info.file_path, 'rb') as f:
                magic = f.read(16)
            if magic.startswith(b'\x7fELF'):
                info.format = BinaryFormat.ELF
            elif magic.startswith(b'MZ'):
                info.format = BinaryFormat.PE
            elif magic.startswith(b'\xcf\xfa\xed\xfe') or magic.startswith(b'\xfe\xed\xfa\xcf'):
                info.format = BinaryFormat.MACHO


class GhidraAnalyzer:
    def __init__(self, ghidra_path: str = None, project_dir: str = None):
        self.ghidra_path = ghidra_path or shutil.which("ghidra") or "/opt/ghidra/ghidraRun"
        self.project_dir = project_dir or tempfile.mkdtemp(prefix="ghidra_")
        self.project_name = "analysis"

    async def analyze(self, binary_path: str, script_path: str = None) -> Dict[str, Any]:
        if script_path is None:
            script_path = self._generate_default_script()
        
        cmd = [
            self.ghidra_path,
            self.project_dir,
            self.project_name,
            "-import", binary_path,
            "-postScript", script_path,
            "-deleteProject",
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        
        output_file = Path(self.project_dir) / f"{Path(binary_path).stem}_analysis.json"
        if output_file.exists():
            with open(output_file) as f:
                return json.load(f)
        
        return {"stdout": stdout.decode(), "stderr": stderr.decode()}

    def _generate_default_script(self) -> str:
        script = """
import json
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor

program = currentProgram
decompiler = DecompInterface()
decompiler.openProgram(program)

functions = program.getFunctionManager().getFunctions(True)
results = {"functions": []}

for func in functions:
    func_data = {
        "name": func.getName(),
        "address": str(func.getEntryPoint()),
        "signature": str(func.getSignature()),
        "calling_convention": str(func.getCallingConvention()),
        "stack_frame_size": func.getStackFrame().getSize() if func.getStackFrame() else 0,
    }
    
    results["functions"].append(func_data)

with open(f"{program.getName()}_analysis.json", "w") as f:
    json.dump(results, f, indent=2)
"""
        script_file = Path(self.project_dir) / "analyze.java"
        script_file.write_text(script)
        return str(script_file)


class Radare2Analyzer:
    def __init__(self, r2_path: str = None):
        self.r2_path = r2_path or shutil.which("r2") or shutil.which("radare2")

    async def analyze(self, binary_path: str, commands: List[str] = None) -> Dict[str, Any]:
        commands = commands or [
            "aaa",  # analyze all
            "aflj",  # list functions as JSON
            "pdfj",  # disassemble function as JSON
            "agj",   # CFG as JSON
            "ij",    # binary info as JSON
        ]
        
        cmd_str = ";".join(commands)
        cmd = [self.r2_path, "-q", "-c", cmd_str, binary_path]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        
        output = stdout.decode()
        results = {}
        
        for line in output.split('\n'):
            if line.startswith('{') or line.startswith('['):
                try:
                    data = json.loads(line)
                    if "functions" not in results:
                        results["functions"] = []
                    if isinstance(data, list):
                        results["functions"].extend(data)
                    else:
                        results["info"] = data
                except json.JSONDecodeError:
                    pass
        
        return results

    async def get_function_cfg(self, binary_path: str, func_address: int) -> ControlFlowGraph:
        cmd = [self.r2_path, "-q", "-c", f"s {func_address}; agj", binary_path]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE)
        stdout, _ = await proc.communicate()
        
        try:
            data = json.loads(stdout.decode())
            return self._parse_r2_cfg(data, func_address)
        except Exception:
            return ControlFlowGraph(function_address=func_address)

    def _parse_r2_cfg(self, data: List, func_address: int) -> ControlFlowGraph:
        cfg = ControlFlowGraph(function_address=func_address)
        for block in data:
            if isinstance(block, dict):
                addr = block.get("offset", 0)
                node = CFGNode(address=addr)
                node.instructions = block.get("ops", [])
                node.successors = [e.get("addr", 0) for e in block.get("edges", []) if e.get("type") in ("t", "f", "u")]
                cfg.nodes[addr] = node
                for succ in node.successors:
                    cfg.edges.append((addr, succ))
        return cfg


class GDBController:
    def __init__(self, gdb_path: str = None):
        self.gdb_path = gdb_path or shutil.which("gdb")
        self.process: Optional[asyncio.subprocess.Process] = None

    async def start(self, binary_path: str, args: List[str] = None):
        self.process = await asyncio.create_subprocess_exec(
            self.gdb_path, "-q", "-ex", "set confirm off", "-ex", f"file {binary_path}",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def send_command(self, command: str) -> str:
        if not self.process:
            return ""
        self.process.stdin.write(f"{command}\n".encode())
        await self.process.stdin.drain()
        stdout, _ = await asyncio.wait_for(self.process.stdout.read(4096), timeout=5.0)
        return stdout.decode()

    async def set_breakpoint(self, address: int) -> str:
        return await self.send_command(f"break *{hex(address)}")

    async def run(self, args: List[str] = None) -> str:
        arg_str = " ".join(args) if args else ""
        return await self.send_command(f"run {arg_str}")

    async def continue_execution(self) -> str:
        return await self.send_command("continue")

    async def step_instruction(self) -> str:
        return await self.send_command("stepi")

    async def read_register(self, register: str) -> str:
        return await self.send_command(f"info registers {register}")

    async def read_memory(self, address: int, size: int) -> bytes:
        output = await self.send_command(f"x/{size}xb {hex(address)}")
        return self._parse_memory_output(output)

    def _parse_memory_output(self, output: str) -> bytes:
        result = bytearray()
        for line in output.split('\n'):
            match = re.match(r'0x[0-9a-f]+:\s+((?:[0-9a-f]{2}\s+)+)', line)
            if match:
                hex_bytes = match.group(1).split()
                result.extend(int(b, 16) for b in hex_bytes)
        return bytes(result)

    async def close(self):
        if self.process:
            await self.send_command("quit")
            await self.process.wait()


class BinaryASTMapper:
    def __init__(self, analyzer: BinaryAnalyzer):
        self.analyzer = analyzer

    async def map_to_ast(self, binary_path: str) -> List[Dict]:
        info = await self.analyzer.analyze_binary(binary_path)
        
        ast_nodes = []
        
        for func in info.metadata.get("functions", []):
            node = {
                "type": "FUNCTION",
                "name": func.get("name", ""),
                "address": func.get("address", 0),
                "size": func.get("size", 0),
                "blocks": func.get("blocks", []),
                "calls": func.get("calls", []),
                "metadata": {
                    "calling_convention": func.get("calling_convention", ""),
                    "stack_frame_size": func.get("stack_frame_size", 0),
                }
            }
            ast_nodes.append(node)
        
        for section in info.sections:
            node = {
                "type": "SECTION",
                "name": section.get("name", ""),
                "address": int(section.get("vma", 0), 16) if section.get("vma", "").startswith("0x") else 0,
                "size": int(section.get("size", 0), 16) if section.get("size", "").startswith("0x") else 0,
                "flags": section.get("flags", ""),
            }
            ast_nodes.append(node)
        
        return ast_nodes

    def find_vulnerabilities(self, binary_path: str) -> List[Dict]:
        info = self.analyzer.cache.get(binary_path)
        if not info:
            return []
        
        vulns = []
        
        dangerous_functions = {
            "strcpy", "strcat", "sprintf", "gets", "scanf", "printf",
            "memcpy", "memmove", "strncpy", "strncat", "snprintf",
        }
        
        for sym in info.symbols:
            name = sym.get("name", "")
            if any(danger in name.lower() for danger in dangerous_functions):
                vulns.append({
                    "type": "DANGEROUS_FUNCTION",
                    "function": name,
                    "address": sym.get("address", ""),
                    "severity": "MEDIUM",
                    "description": f"Potentially dangerous function: {name}",
                })
        
        for string in info.strings:
            if any(pattern in string.lower() for pattern in ["password", "secret", "key", "token", "api"]):
                vulns.append({
                    "type": "HARDCODED_SECRET",
                    "string": string[:100],
                    "severity": "HIGH",
                    "description": "Potential hardcoded secret in binary",
                })
        
        return vulns


class PackerDetector:
    def __init__(self, analyzer: BinaryAnalyzer):
        self.analyzer = analyzer
        self.signatures = {
            "UPX": [b"UPX!", b"UPX0", b"UPX1"],
            "PECompact": [b"PEC2", b"PEC1"],
            "ASPack": [b"ASPack", b"ASPACK"],
            "FSG": [b"FSG!", b"FSG "],
            "MEW": [b"MEW"],
            "MPRESS": [b"MPRESS1", b"MPRESS2"],
        }

    async def detect(self, binary_path: str) -> List[str]:
        detected = []
        
        with open(binary_path, 'rb') as f:
            content = f.read()
        
        for packer, sigs in self.signatures.items():
            for sig in sigs:
                if sig in content:
                    detected.append(packer)
                    break
        
        info = await self.analyzer.analyze_binary(binary_path)
        
        for section in info.sections:
            name = section.get("name", "").lower()
            if "upx" in name or "packed" in name:
                if "UPX" not in detected:
                    detected.append("UPX")
        
        entropy = self._calculate_entropy(content)
        if entropy > 7.5:
            detected.append("HIGH_ENTROPY_PACKED")
        
        return detected

    def _calculate_entropy(self, data: bytes) -> float:
        if not data:
            return 0.0
        
        freq = defaultdict(int)
        for byte in data:
            freq[byte] += 1
        
        entropy = 0.0
        for count in freq.values():
            p = count / len(data)
            entropy -= p * (p.bit_length() - 1)
        
        return entropy


class AntiDebugDetector:
    def __init__(self, analyzer: BinaryAnalyzer):
        self.analyzer = analyzer
        self.techniques = {
            "ptrace": ["ptrace", "PTRACE_TRACEME"],
            "timing": ["rdtsc", "RDTSC", "GetTickCount", "timeGetTime"],
            "debugger_check": ["IsDebuggerPresent", "CheckRemoteDebuggerPresent", "NtGlobalFlag"],
            "hardware_breakpoint": ["DR0", "DR1", "DR2", "DR3", "DR7"],
            "software_breakpoint": ["INT 3", "0xCC", "CC"],
            "memory_check": ["VirtualQuery", "NtQueryVirtualMemory"],
            "process_check": ["FindWindow", "EnumWindows", "GetWindowThreadProcessId"],
        }

    async def detect(self, binary_path: str) -> List[Dict]:
        detected = []
        
        info = await self.analyzer.analyze_binary(binary_path)
        
        for string in info.strings:
            for technique, patterns in self.techniques.items():
                for pattern in patterns:
                    if pattern.lower() in string.lower():
                        detected.append({
                            "technique": technique,
                            "indicator": pattern,
                            "context": string[:200],
                        })
        
        for func in info.metadata.get("functions", []):
            for inst in func.get("instructions", []):
                mnemonic = inst.get("mnemonic", "").upper()
                if mnemonic in ("INT3", "INT 3") or inst.get("bytes", "").startswith("CC"):
                    detected.append({
                        "technique": "SOFTWARE_BREAKPOINT",
                        "indicator": "0xCC / INT 3",
                        "address": inst.get("address", 0),
                    })
        
        return detected


class BinaryAnalysisOrchestrator:
    def __init__(self):
        self.analyzer = BinaryAnalyzer()
        self.ghidra = GhidraAnalyzer()
        self.radare2 = Radare2Analyzer()
        self.gdb = GDBController()
        self.mapper = BinaryASTMapper(self.analyzer)
        self.packer_detector = PackerDetector(self.analyzer)
        self.anti_debug = AntiDebugDetector(self.analyzer)

    async def full_analysis(self, binary_path: str) -> Dict[str, Any]:
        info = await self.analyzer.analyze_binary(binary_path)
        
        results = {
            "binary_info": {
                "file": info.file_path,
                "format": info.format.value,
                "architecture": info.architecture.value,
                "bits": info.bits,
                "endian": info.endian,
                "entry_point": hex(info.entry_point),
                "sections_count": len(info.sections),
                "symbols_count": len(info.symbols),
                "imports": info.imports,
                "exports": info.exports,
                "strings_count": len(info.strings),
            },
            "packers": await self.packer_detector.detect(binary_path),
            "anti_debug": await self.anti_debug.detect(binary_path),
            "vulnerabilities": self.mapper.find_vulnerabilities(binary_path),
            "ast_mapping": await self.mapper.map_to_ast(binary_path),
        }
        
        if self.analyzer.is_tool_available(AnalysisTool.RADARE2):
            try:
                r2_results = await self.radare2.analyze(binary_path)
                results["radare2"] = r2_results
            except Exception as e:
                results["radare2_error"] = str(e)
        
        return results

    async def dynamic_analysis(self, binary_path: str, args: List[str] = None) -> Dict[str, Any]:
        await self.gdb.start(binary_path, args)
        
        results = {"registers": {}, "memory": {}, "trace": []}
        
        try:
            await self.gdb.run(args)
            await asyncio.sleep(1)
            
            for reg in ["rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "rsp", "rip", "eflags"]:
                results["registers"][reg] = await self.gdb.read_register(reg)
            
            await self.gdb.close()
        except Exception as e:
            results["error"] = str(e)
        
        return results