"""
Dynamic CLI Schema Generator - Introspects CLI help outputs (--help) to auto-generate JSON tool schemas
"""
import re
import subprocess
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ParamType(Enum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    FILE = "file"
    DIRECTORY = "directory"
    ENUM = "enum"


@dataclass
class CLISchema:
    tool_name: str
    command: str
    description: str
    version: str = ""
    parameters: list[dict[str, Any]] = field(default_factory=list)
    subcommands: dict[str, 'CLISchema'] = field(default_factory=dict)
    examples: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class CLISchemaGenerator:
    def __init__(self):
        self._schemas: dict[str, CLISchema] = {}
        self._lock = threading.RLock()
        self._cache: dict[str, CLISchema] = {}

    def generate_schema(self, command: str, tool_name: str = None) -> CLISchema:
        if tool_name is None:
            tool_name = command.split(maxsplit=1)[0]

        cache_key = f"{tool_name}:{command}"
        with self._lock:
            if cache_key in self._cache:
                return self._cache[cache_key]

        # Get help output
        help_text = self._get_help(command)
        if not help_text:
            return CLISchema(tool_name=tool_name, command=command, description="")

        # Parse help text
        schema = self._parse_help(tool_name, command, help_text)

        with self._lock:
            self._cache[cache_key] = schema
            self._schemas[tool_name] = schema

        return schema

    def _get_help(self, command: str) -> str | None:
        try:
            # Try --help first
            result = subprocess.run(
                f"{command} --help",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout

            # Try -h
            result = subprocess.run(
                f"{command} -h",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except Exception:
            pass
        return None

    def _parse_help(self, tool_name: str, command: str, help_text: str) -> CLISchema:
        lines = help_text.split('\n')

        schema = CLISchema(
            tool_name=tool_name,
            command=command,
            description=""
        )

        # Extract description (first paragraph)
        desc_lines = []
        for line in lines:
            if line.strip() and not line.startswith(' ') and not line.startswith('-'):
                desc_lines.append(line.strip())
            elif desc_lines:
                break
        schema.description = ' '.join(desc_lines[:3])

        # Extract version
        version_match = re.search(r'version\s+(\S+)', help_text, re.IGNORECASE)
        if version_match:
            schema.version = version_match.group(1)

        # Parse parameters
        in_options = False
        current_param = None

        for line in lines:
            stripped = line.strip()

            # Detect options section
            if re.match(r'(options?|flags?|arguments?):', stripped, re.IGNORECASE):
                in_options = True
                continue

            if in_options and not stripped:
                continue

            if in_options and stripped and not stripped.startswith('-'):
                # End of options
                in_options = False
                continue

            if in_options:
                param = self._parse_option_line(stripped)
                if param:
                    schema.parameters.append(param)

        # Extract subcommands
        schema.subcommands = self._extract_subcommands(help_text, command)

        # Extract examples
        schema.examples = self._extract_examples(help_text)

        return schema

    def _parse_option_line(self, line: str) -> dict[str, Any] | None:
        # Match patterns like: -o, --output FILE    Output file path
        # or: --verbose                 Enable verbose output
        # or: -p PORT, --port=PORT      Port number (default: 8080)

        # Split into option part and description
        parts = re.split(r'\s{2,}', line)
        if len(parts) < 2:
            return None

        opt_part = parts[0].strip()
        desc = ' '.join(parts[1:]).strip()

        # Parse option names
        opt_names = []
        for part in opt_part.split(','):
            part = part.strip()
            if part.startswith('--') or part.startswith('-'):
                opt_names.append(part.lstrip('-'))

        if not opt_names:
            return None

        # Determine if it takes a value
        has_value = False
        value_name = ""
        param_type = ParamType.STRING

        # Check for value patterns
        value_match = re.search(r'[<=\s]([A-Z_][A-Z0-9_]*)[>\s]', opt_part)
        if value_match:
            has_value = True
            value_name = value_match.group(1).lower()

            # Infer type from value name
            if value_name in ('port', 'number', 'count', 'size', 'timeout', 'limit'):
                param_type = ParamType.INTEGER
            elif value_name in ('rate', 'ratio', 'threshold'):
                param_type = ParamType.NUMBER
            elif value_name in ('file', 'path', 'dir', 'directory'):
                param_type = ParamType.FILE if value_name == 'file' else ParamType.DIRECTORY
            elif value_name in ('true', 'false', 'yes', 'no', 'on', 'off'):
                param_type = ParamType.BOOLEAN
                has_value = False

        # Check for default value
        default_match = re.search(r'\(default:\s*([^)]+)\)', desc, re.IGNORECASE)
        default = default_match.group(1) if default_match else None

        # Check for enum/choices
        choices = []
        choice_match = re.search(r'\[([^\]]+)\]', desc)
        if choice_match:
            choices = [c.strip() for c in choice_match.group(1).split('|')]
            param_type = ParamType.ENUM

        # Determine required
        required = '(required)' in desc.lower() or 'required' in desc.lower()

        return {
            "names": opt_names,
            "primary_name": opt_names[0].replace('-', '_'),
            "description": desc,
            "type": param_type.value,
            "has_value": has_value,
            "value_name": value_name,
            "required": required,
            "default": default,
            "choices": choices
        }

    def _extract_subcommands(self, help_text: str, parent_command: str) -> dict[str, CLISchema]:
        subcommands = {}

        # Look for subcommands section
        subcmd_section = re.search(r'(?:commands?|subcommands?):\s*\n(.*?)(?:\n\n|\n\w+:|$)',
                                   help_text, re.IGNORECASE | re.DOTALL)

        if subcmd_section:
            subcmd_text = subcmd_section.group(1)
            for line in subcmd_text.split('\n'):
                line = line.strip()
                if not line:
                    continue

                # Match: "  subcmd    Description"
                match = re.match(r'^(\w+)\s+(.+)$', line)
                if match:
                    subcmd_name = match.group(1)
                    subcmd_desc = match.group(2)
                    full_cmd = f"{parent_command} {subcmd_name}"

                    try:
                        sub_schema = self.generate_schema(full_cmd, f"{parent_command}_{subcmd_name}")
                        subcommands[subcmd_name] = sub_schema
                    except Exception:
                        subcommands[subcmd_name] = CLISchema(
                            tool_name=f"{parent_command}_{subcmd_name}",
                            command=full_cmd,
                            description=subcmd_desc
                        )

        return subcommands

    def _extract_examples(self, help_text: str) -> list[str]:
        examples = []

        # Look for examples section
        example_section = re.search(r'(?:examples?|usage):\s*\n(.*?)(?:\n\n|\n\w+:|$)',
                                    help_text, re.IGNORECASE | re.DOTALL)

        if example_section:
            example_text = example_section.group(1)
            for line in example_text.split('\n'):
                line = line.strip()
                if line and (line.startswith('$') or line.startswith('#') or
                           re.match(r'^\w+', line)):
                    examples.append(line)

        return examples

    def to_json_schema(self, schema: CLISchema) -> dict[str, Any]:
        """Convert CLI schema to JSON Schema format"""
        properties = {}
        required = []

        for param in schema.parameters:
            name = param["primary_name"]

            prop = {
                "type": param["type"],
                "description": param["description"]
            }

            if param["choices"]:
                prop["enum"] = param["choices"]

            if param["default"] is not None:
                prop["default"] = param["default"]

            properties[name] = prop

            if param["required"]:
                required.append(name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "title": schema.tool_name,
            "description": schema.description
        }

    def get_schema(self, tool_name: str) -> CLISchema | None:
        with self._lock:
            return self._schemas.get(tool_name)

    def list_schemas(self) -> list[str]:
        with self._lock:
            return list(self._schemas.keys())

    def clear_cache(self):
        with self._lock:
            self._cache.clear()


_cli_schema_generator: CLISchemaGenerator | None = None


def get_cli_schema_generator() -> CLISchemaGenerator:
    global _cli_schema_generator
    if _cli_schema_generator is None:
        _cli_schema_generator = CLISchemaGenerator()
    return _cli_schema_generator
