"""
Core StdLib - Language-agnostic standard library definitions
"""
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class StdLibCategory(Enum):
    CORE = "core"
    COLLECTIONS = "collections"
    IO = "io"
    NETWORK = "network"
    CRYPTO = "crypto"
    CONCURRENCY = "concurrency"
    TEXT = "text"
    MATH = "math"
    TIME = "time"
    OS = "os"
    SERIALIZATION = "serialization"
    TESTING = "testing"
    LOGGING = "logging"
    DEBUGGING = "debugging"


class Language(Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    GO = "go"
    RUST = "rust"
    CPP = "cpp"
    CSHARP = "csharp"
    RUBY = "ruby"
    PHP = "php"
    SWIFT = "swift"
    KOTLIN = "kotlin"


@dataclass
class StdLibFunction:
    name: str
    category: StdLibCategory
    signature: str
    description: str
    parameters: list[dict[str, Any]] = field(default_factory=list)
    return_type: str = "any"
    exceptions: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    since_version: str = ""
    deprecated: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category.value,
            "signature": self.signature,
            "description": self.description,
            "parameters": self.parameters,
            "return_type": self.return_type,
            "exceptions": self.exceptions,
            "examples": self.examples,
            "since_version": self.since_version,
            "deprecated": self.deprecated,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'StdLibFunction':
        return cls(
            name=data["name"],
            category=StdLibCategory(data["category"]),
            signature=data["signature"],
            description=data["description"],
            parameters=data.get("parameters", []),
            return_type=data.get("return_type", "any"),
            exceptions=data.get("exceptions", []),
            examples=data.get("examples", []),
            since_version=data.get("since_version", ""),
            deprecated=data.get("deprecated", False),
            metadata=data.get("metadata", {}),
        )


@dataclass
class StdLibModule:
    name: str
    language: Language
    category: StdLibCategory
    functions: list[StdLibFunction] = field(default_factory=list)
    constants: dict[str, Any] = field(default_factory=dict)
    classes: list[dict[str, Any]] = field(default_factory=list)
    version: str = ""
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "language": self.language.value,
            "category": self.category.value,
            "functions": [f.to_dict() for f in self.functions],
            "constants": self.constants,
            "classes": self.classes,
            "version": self.version,
            "description": self.description,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'StdLibModule':
        return cls(
            name=data["name"],
            language=Language(data["language"]),
            category=StdLibCategory(data["category"]),
            functions=[StdLibFunction.from_dict(f) for f in data.get("functions", [])],
            constants=data.get("constants", {}),
            classes=data.get("classes", []),
            version=data.get("version", ""),
            description=data.get("description", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class StdLibMapping:
    canonical_name: str
    language_mappings: dict[Language, str] = field(default_factory=dict)
    category: StdLibCategory = StdLibCategory.CORE
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "language_mappings": {k.value: v for k, v in self.language_mappings.items()},
            "category": self.category.value,
            "description": self.description,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'StdLibMapping':
        return cls(
            canonical_name=data["canonical_name"],
            language_mappings={Language(k): v for k, v in data.get("language_mappings", {}).items()},
            category=StdLibCategory(data.get("category", "core")),
            description=data.get("description", ""),
            metadata=data.get("metadata", {}),
        )


class CoreStdLib:
    def __init__(self):
        self.modules: dict[str, StdLibModule] = {}
        self.mappings: dict[str, StdLibMapping] = {}
        self._init_core_mappings()
        self._init_python_stdlib()

    def _init_core_mappings(self):
        core_functions = [
            StdLibMapping("print", {
                Language.PYTHON: "print",
                Language.JAVASCRIPT: "console.log",
                Language.TYPESCRIPT: "console.log",
                Language.JAVA: "System.out.println",
                Language.GO: "fmt.Println",
                Language.RUST: "println!",
                Language.CPP: "std::cout <<",
                Language.CSHARP: "Console.WriteLine",
                Language.RUBY: "puts",
                Language.PHP: "echo",
                Language.SWIFT: "print",
                Language.KOTLIN: "println",
            }, StdLibCategory.CORE, "Output to stdout"),

            StdLibMapping("read_file", {
                Language.PYTHON: "open().read()",
                Language.JAVASCRIPT: "fs.readFileSync",
                Language.TYPESCRIPT: "fs.readFileSync",
                Language.JAVA: "Files.readString",
                Language.GO: "os.ReadFile",
                Language.RUST: "std::fs::read_to_string",
                Language.CPP: "std::ifstream",
                Language.CSHARP: "File.ReadAllText",
                Language.RUBY: "File.read",
                Language.PHP: "file_get_contents",
                Language.SWIFT: "String(contentsOfFile:)",
                Language.KOTLIN: "File.readText",
            }, StdLibCategory.IO, "Read entire file as string"),

            StdLibMapping("write_file", {
                Language.PYTHON: "open().write()",
                Language.JAVASCRIPT: "fs.writeFileSync",
                Language.TYPESCRIPT: "fs.writeFileSync",
                Language.JAVA: "Files.writeString",
                Language.GO: "os.WriteFile",
                Language.RUST: "std::fs::write",
                Language.CPP: "std::ofstream",
                Language.CSHARP: "File.WriteAllText",
                Language.RUBY: "File.write",
                Language.PHP: "file_put_contents",
                Language.SWIFT: "write(toFile:)",
                Language.KOTLIN: "File.writeText",
            }, StdLibCategory.IO, "Write string to file"),

            StdLibMapping("http_get", {
                Language.PYTHON: "requests.get",
                Language.JAVASCRIPT: "fetch",
                Language.TYPESCRIPT: "fetch",
                Language.JAVA: "HttpClient.get",
                Language.GO: "http.Get",
                Language.RUST: "reqwest::get",
                Language.CPP: "cpp-httplib",
                Language.CSHARP: "HttpClient.GetAsync",
                Language.RUBY: "Net::HTTP.get",
                Language.PHP: "file_get_contents / curl",
                Language.SWIFT: "URLSession.dataTask",
                Language.KOTLIN: "HttpClient.get",
            }, StdLibCategory.NETWORK, "HTTP GET request"),

            StdLibMapping("json_parse", {
                Language.PYTHON: "json.loads",
                Language.JAVASCRIPT: "JSON.parse",
                Language.TYPESCRIPT: "JSON.parse",
                Language.JAVA: "ObjectMapper.readValue",
                Language.GO: "json.Unmarshal",
                Language.RUST: "serde_json::from_str",
                Language.CPP: "nlohmann::json::parse",
                Language.CSHARP: "JsonSerializer.Deserialize",
                Language.RUBY: "JSON.parse",
                Language.PHP: "json_decode",
                Language.SWIFT: "JSONSerialization.jsonObject",
                Language.KOTLIN: "JSON.parse / kotlinx.serialization",
            }, StdLibCategory.SERIALIZATION, "Parse JSON string"),

            StdLibMapping("json_stringify", {
                Language.PYTHON: "json.dumps",
                Language.JAVASCRIPT: "JSON.stringify",
                Language.TYPESCRIPT: "JSON.stringify",
                Language.JAVA: "ObjectMapper.writeValueAsString",
                Language.GO: "json.Marshal",
                Language.RUST: "serde_json::to_string",
                Language.CPP: "nlohmann::json::dump",
                Language.CSHARP: "JsonSerializer.Serialize",
                Language.RUBY: "JSON.generate",
                Language.PHP: "json_encode",
                Language.SWIFT: "JSONSerialization.data",
                Language.KOTLIN: "JSON.stringify / kotlinx.serialization",
            }, StdLibCategory.SERIALIZATION, "Serialize to JSON string"),

            StdLibMapping("hash_sha256", {
                Language.PYTHON: "hashlib.sha256",
                Language.JAVASCRIPT: "crypto.subtle.digest",
                Language.TYPESCRIPT: "crypto.subtle.digest",
                Language.JAVA: "MessageDigest.getInstance('SHA-256')",
                Language.GO: "sha256.Sum256",
                Language.RUST: "sha2::Sha256",
                Language.CPP: "OpenSSL EVP_Digest",
                Language.CSHARP: "SHA256.Create",
                Language.RUBY: "Digest::SHA256.hexdigest",
                Language.PHP: "hash('sha256', ...)",
                Language.SWIFT: "CryptoKit.SHA256",
                Language.KOTLIN: "MessageDigest.getInstance('SHA-256')",
            }, StdLibCategory.CRYPTO, "SHA-256 hash"),

            StdLibMapping("uuid_generate", {
                Language.PYTHON: "uuid.uuid4",
                Language.JAVASCRIPT: "crypto.randomUUID",
                Language.TYPESCRIPT: "crypto.randomUUID",
                Language.JAVA: "UUID.randomUUID",
                Language.GO: "uuid.NewV4",
                Language.RUST: "uuid::Uuid::new_v4",
                Language.CPP: "boost::uuids::random_generator",
                Language.CSHARP: "Guid.NewGuid",
                Language.RUBY: "SecureRandom.uuid",
                Language.PHP: "random_bytes + bin2hex",
                Language.SWIFT: "UUID().uuidString",
                Language.KOTLIN: "UUID.randomUUID",
            }, StdLibCategory.CORE, "Generate UUID v4"),

            StdLibMapping("sleep", {
                Language.PYTHON: "time.sleep",
                Language.JAVASCRIPT: "setTimeout / await new Promise",
                Language.TYPESCRIPT: "setTimeout / await new Promise",
                Language.JAVA: "Thread.sleep",
                Language.GO: "time.Sleep",
                Language.RUST: "std::thread::sleep",
                Language.CPP: "std::this_thread::sleep_for",
                Language.CSHARP: "Thread.Sleep / Task.Delay",
                Language.RUBY: "sleep",
                Language.PHP: "sleep / usleep",
                Language.SWIFT: "Thread.sleep / Task.sleep",
                Language.KOTLIN: "Thread.sleep / delay",
            }, StdLibCategory.CONCURRENCY, "Sleep current thread"),

            StdLibMapping("now_timestamp", {
                Language.PYTHON: "time.time()",
                Language.JAVASCRIPT: "Date.now()",
                Language.TYPESCRIPT: "Date.now()",
                Language.JAVA: "System.currentTimeMillis()",
                Language.GO: "time.Now().UnixMilli()",
                Language.RUST: "std::time::SystemTime::now",
                Language.CPP: "std::chrono::system_clock::now",
                Language.CSHARP: "DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()",
                Language.RUBY: "Time.now.to_i",
                Language.PHP: "time() / microtime(true)",
                Language.SWIFT: "Date().timeIntervalSince1970",
                Language.KOTLIN: "System.currentTimeMillis()",
            }, StdLibCategory.TIME, "Current timestamp"),
        ]

        for mapping in core_functions:
            self.mappings[mapping.canonical_name] = mapping

    def _init_python_stdlib(self):
        python_modules = {
            "os": StdLibModule("os", Language.PYTHON, StdLibCategory.OS, [
                StdLibFunction("path.join", StdLibCategory.OS, "os.path.join(*paths)", "Join path components"),
                StdLibFunction("path.exists", StdLibCategory.OS, "os.path.exists(path)", "Check if path exists"),
                StdLibFunction("path.isfile", StdLibCategory.OS, "os.path.isfile(path)", "Check if path is file"),
                StdLibFunction("path.isdir", StdLibCategory.OS, "os.path.isdir(path)", "Check if path is directory"),
                StdLibFunction("mkdir", StdLibCategory.OS, "os.makedirs(path, exist_ok=True)", "Create directory"),
                StdLibFunction("listdir", StdLibCategory.OS, "os.listdir(path)", "List directory contents"),
                StdLibFunction("remove", StdLibCategory.OS, "os.remove(path)", "Remove file"),
                StdLibFunction("rename", StdLibCategory.OS, "os.rename(src, dst)", "Rename file"),
                StdLibFunction("environ", StdLibCategory.OS, "os.environ", "Environment variables"),
                StdLibFunction("getpid", StdLibCategory.OS, "os.getpid()", "Get process ID"),
            ]),

            "json": StdLibModule("json", Language.PYTHON, StdLibCategory.SERIALIZATION, [
                StdLibFunction("loads", StdLibCategory.SERIALIZATION, "json.loads(s)", "Parse JSON string"),
                StdLibFunction("dumps", StdLibCategory.SERIALIZATION, "json.dumps(obj)", "Serialize to JSON"),
                StdLibFunction("load", StdLibCategory.SERIALIZATION, "json.load(fp)", "Load JSON from file"),
                StdLibFunction("dump", StdLibCategory.SERIALIZATION, "json.dump(obj, fp)", "Write JSON to file"),
            ]),

            "hashlib": StdLibModule("hashlib", Language.PYTHON, StdLibCategory.CRYPTO, [
                StdLibFunction("sha256", StdLibCategory.CRYPTO, "hashlib.sha256(data).hexdigest()", "SHA-256 hash"),
                StdLibFunction("md5", StdLibCategory.CRYPTO, "hashlib.md5(data).hexdigest()", "MD5 hash (deprecated)"),
                StdLibFunction("sha512", StdLibCategory.CRYPTO, "hashlib.sha512(data).hexdigest()", "SHA-512 hash"),
                StdLibFunction("pbkdf2_hmac", StdLibCategory.CRYPTO, "hashlib.pbkdf2_hmac(...)", "PBKDF2 key derivation"),
            ]),

            "uuid": StdLibModule("uuid", Language.PYTHON, StdLibCategory.CORE, [
                StdLibFunction("uuid4", StdLibCategory.CORE, "uuid.uuid4()", "Random UUID"),
                StdLibFunction("uuid1", StdLibCategory.CORE, "uuid.uuid1()", "Time-based UUID"),
                StdLibFunction("uuid5", StdLibCategory.CORE, "uuid.uuid5(namespace, name)", "Name-based UUID"),
            ]),

            "datetime": StdLibModule("datetime", Language.PYTHON, StdLibCategory.TIME, [
                StdLibFunction("now", StdLibCategory.TIME, "datetime.now()", "Current datetime"),
                StdLibFunction("utcnow", StdLibCategory.TIME, "datetime.utcnow()", "Current UTC datetime"),
                StdLibFunction("fromtimestamp", StdLibCategory.TIME, "datetime.fromtimestamp(ts)", "From timestamp"),
                StdLibFunction("strftime", StdLibCategory.TIME, "dt.strftime(format)", "Format datetime"),
                StdLibFunction("strptime", StdLibCategory.TIME, "datetime.strptime(s, fmt)", "Parse datetime"),
            ]),

            "threading": StdLibModule("threading", Language.PYTHON, StdLibCategory.CONCURRENCY, [
                StdLibFunction("Thread", StdLibCategory.CONCURRENCY, "threading.Thread(target=fn)", "Create thread"),
                StdLibFunction("Lock", StdLibCategory.CONCURRENCY, "threading.Lock()", "Mutex lock"),
                StdLibFunction("RLock", StdLibCategory.CONCURRENCY, "threading.RLock()", "Reentrant lock"),
                StdLibFunction("Event", StdLibCategory.CONCURRENCY, "threading.Event()", "Thread event"),
                StdLibFunction("Condition", StdLibCategory.CONCURRENCY, "threading.Condition()", "Condition variable"),
            ]),

            "subprocess": StdLibModule("subprocess", Language.PYTHON, StdLibCategory.OS, [
                StdLibFunction("run", StdLibCategory.OS, "subprocess.run(cmd, capture_output=True)", "Run command"),
                StdLibFunction("Popen", StdLibCategory.OS, "subprocess.Popen(cmd)", "Spawn process"),
                StdLibFunction("check_output", StdLibCategory.OS, "subprocess.check_output(cmd)", "Get command output"),
            ]),

            "pathlib": StdLibModule("pathlib", Language.PYTHON, StdLibCategory.IO, [
                StdLibFunction("Path", StdLibCategory.IO, "Path(path)", "Path object"),
                StdLibFunction("read_text", StdLibCategory.IO, "Path.read_text()", "Read file as text"),
                StdLibFunction("write_text", StdLibCategory.IO, "Path.write_text(content)", "Write text to file"),
                StdLibFunction("mkdir", StdLibCategory.IO, "Path.mkdir(parents=True, exist_ok=True)", "Create directory"),
                StdLibFunction("glob", StdLibCategory.IO, "Path.glob(pattern)", "Glob pattern match"),
                StdLibFunction("rglob", StdLibCategory.IO, "Path.rglob(pattern)", "Recursive glob"),
            ]),

            "re": StdLibModule("re", Language.PYTHON, StdLibCategory.TEXT, [
                StdLibFunction("search", StdLibCategory.TEXT, "re.search(pattern, string)", "Search pattern"),
                StdLibFunction("match", StdLibCategory.TEXT, "re.match(pattern, string)", "Match at start"),
                StdLibFunction("findall", StdLibCategory.TEXT, "re.findall(pattern, string)", "Find all matches"),
                StdLibFunction("sub", StdLibCategory.TEXT, "re.sub(pattern, repl, string)", "Substitute"),
                StdLibFunction("compile", StdLibCategory.TEXT, "re.compile(pattern)", "Compile pattern"),
            ]),

            "collections": StdLibModule("collections", Language.PYTHON, StdLibCategory.COLLECTIONS, [
                StdLibFunction("defaultdict", StdLibCategory.COLLECTIONS, "defaultdict(factory)", "Dict with default"),
                StdLibFunction("Counter", StdLibCategory.COLLECTIONS, "Counter(iterable)", "Count elements"),
                StdLibFunction("OrderedDict", StdLibCategory.COLLECTIONS, "OrderedDict()", "Ordered dict"),
                StdLibFunction("namedtuple", StdLibCategory.COLLECTIONS, "namedtuple(name, fields)", "Named tuple"),
                StdLibFunction("deque", StdLibCategory.COLLECTIONS, "deque(iterable)", "Double-ended queue"),
            ]),
        }

        for name, module in python_modules.items():
            self.modules[f"python:{name}"] = module

    def register_module(self, module: StdLibModule):
        key = f"{module.language.value}:{module.name}"
        self.modules[key] = module

    def register_mapping(self, mapping: StdLibMapping):
        self.mappings[mapping.canonical_name] = mapping

    def get_module(self, language: Language, name: str) -> StdLibModule | None:
        return self.modules.get(f"{language.value}:{name}")

    def get_mapping(self, canonical_name: str) -> StdLibMapping | None:
        return self.mappings.get(canonical_name)

    def translate(self, canonical_name: str, target_language: Language) -> str | None:
        mapping = self.mappings.get(canonical_name)
        if mapping:
            return mapping.language_mappings.get(target_language)
        return None

    def find_equivalent(self, language: Language, function_name: str) -> list[StdLibMapping]:
        results = []
        for mapping in self.mappings.values():
            if mapping.language_mappings.get(language) == function_name:
                results.append(mapping)
        return results

    def get_all_mappings(self) -> list[StdLibMapping]:
        return list(self.mappings.values())

    def get_modules_by_language(self, language: Language) -> list[StdLibModule]:
        return [m for k, m in self.modules.items() if k.startswith(f"{language.value}:")]

    def get_modules_by_category(self, category: StdLibCategory) -> list[StdLibModule]:
        return [m for m in self.modules.values() if m.category == category]

    def generate_documentation(self, language: Language, output_path: str):
        modules = self.get_modules_by_language(language)

        lines = [
            f"# {language.value.title()} Standard Library Reference",
            "",
            f"Generated on {__import__('datetime').datetime.now().isoformat()}",
            "",
        ]

        for module in modules:
            lines.append(f"## {module.name}")
            lines.append(f"{module.description}")
            lines.append("")

            for func in module.functions:
                lines.append(f"### {func.name}")
                lines.append(f"**Signature:** `{func.signature}`")
                lines.append(f"**Category:** {func.category.value}")
                lines.append(f"**Description:** {func.description}")
                if func.parameters:
                    lines.append("**Parameters:**")
                    for param in func.parameters:
                        lines.append(f"- `{param.get('name', '')}`: {param.get('type', 'any')} - {param.get('description', '')}")
                lines.append(f"**Returns:** {func.return_type}")
                if func.examples:
                    lines.append("**Examples:**")
                    for ex in func.examples:
                        lines.append(f"```python\n{ex}\n```")
                lines.append("")

        Path(output_path).write_text('\n'.join(lines))

    def export_mappings(self, path: str):
        data = {k: v.to_dict() for k, v in self.mappings.items()}
        Path(path).write_text(json.dumps(data, indent=2))

    def import_mappings(self, path: str):
        data = json.loads(Path(path).read_text())
        for k, v in data.items():
            self.mappings[k] = StdLibMapping.from_dict(v)

    def export_modules(self, path: str):
        data = {k: v.to_dict() for k, v in self.modules.items()}
        Path(path).write_text(json.dumps(data, indent=2))

    def import_modules(self, path: str):
        data = json.loads(Path(path).read_text())
        for k, v in data.items():
            self.modules[k] = StdLibModule.from_dict(v)


class CrossLanguageComparator:
    def __init__(self, stdlib: CoreStdLib):
        self.stdlib = stdlib

    def compare_coverage(self, languages: list[Language]) -> dict[str, Any]:
        all_functions = set()
        lang_functions = {}

        for lang in languages:
            funcs = set()
            for module in self.stdlib.get_modules_by_language(lang):
                for func in module.functions:
                    funcs.add(func.name)
            lang_functions[lang] = funcs
            all_functions.update(funcs)

        coverage = {}
        for func in all_functions:
            coverage[func] = {lang: func in lang_functions[lang] for lang in languages}

        return {
            "total_functions": len(all_functions),
            "by_language": {lang.value: len(funcs) for lang, funcs in lang_functions.items()},
            "coverage_matrix": coverage,
        }

    def find_gaps(self, target_language: Language, reference_language: Language) -> list[str]:
        target_funcs = set()
        ref_funcs = set()

        for module in self.stdlib.get_modules_by_language(target_language):
            for func in module.functions:
                target_funcs.add(func.name)

        for module in self.stdlib.get_modules_by_language(reference_language):
            for func in module.functions:
                ref_funcs.add(func.name)

        return list(ref_funcs - target_funcs)

    def suggest_implementations(self, target_language: Language, gaps: list[str]) -> dict[str, str]:
        suggestions = {}
        for gap in gaps:
            equivalents = self.stdlib.find_equivalent(target_language, gap)
            if equivalents:
                suggestions[gap] = equivalents[0].canonical_name
        return suggestions
