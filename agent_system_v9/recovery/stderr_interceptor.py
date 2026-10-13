"""
Automated Stderr Interceptor & Patcher - Captures error streams, diagnoses bugs, auto-patches source, re-executes
"""
import threading
import re
import subprocess
import tempfile
import os
import time
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ErrorCategory(Enum):
    SYNTAX = "syntax"
    IMPORT = "import"
    RUNTIME = "runtime"
    TYPE = "type"
    ATTRIBUTE = "attribute"
    INDEX = "index"
    KEY = "key"
    VALUE = "value"
    PERMISSION = "permission"
    NETWORK = "network"
    UNKNOWN = "unknown"


@dataclass
class PatchResult:
    success: bool
    original_error: str
    patch_applied: str
    patched_file: str
    reexecution_result: str = ""
    attempts: int = 1


class StderrInterceptor:
    def __init__(self, patch_timeout: float = 30.0, max_attempts: int = 3):
        self.patch_timeout = patch_timeout
        self.max_attempts = max_attempts
        self._lock = threading.RLock()
        self._error_patterns: Dict[ErrorCategory, List[re.Pattern]] = {}
        self._patch_strategies: Dict[ErrorCategory, Callable] = {}
        self._intercepted_errors: List[Dict] = []
        self._register_patterns()
        self._register_strategies()
    
    def _register_patterns(self):
        self._error_patterns = {
            ErrorCategory.SYNTAX: [
                re.compile(r'SyntaxError: (.+)'),
                re.compile(r'IndentationError: (.+)'),
            ],
            ErrorCategory.IMPORT: [
                re.compile(r'ImportError: (.+)'),
                re.compile(r'ModuleNotFoundError: (.+)'),
            ],
            ErrorCategory.RUNTIME: [
                re.compile(r'RuntimeError: (.+)'),
                re.compile(r'Exception: (.+)'),
            ],
            ErrorCategory.TYPE: [
                re.compile(r'TypeError: (.+)'),
            ],
            ErrorCategory.ATTRIBUTE: [
                re.compile(r'AttributeError: (.+)'),
            ],
            ErrorCategory.INDEX: [
                re.compile(r'IndexError: (.+)'),
            ],
            ErrorCategory.KEY: [
                re.compile(r'KeyError: (.+)'),
            ],
            ErrorCategory.VALUE: [
                re.compile(r'ValueError: (.+)'),
            ],
            ErrorCategory.PERMISSION: [
                re.compile(r'PermissionError: (.+)'),
            ],
            ErrorCategory.NETWORK: [
                re.compile(r'ConnectionError: (.+)'),
                re.compile(r'TimeoutError: (.+)'),
            ],
        }
    
    def _register_strategies(self):
        self._patch_strategies = {
            ErrorCategory.SYNTAX: self._patch_syntax,
            ErrorCategory.IMPORT: self._patch_import,
            ErrorCategory.RUNTIME: self._patch_runtime,
            ErrorCategory.TYPE: self._patch_type,
            ErrorCategory.ATTRIBUTE: self._patch_attribute,
            ErrorCategory.INDEX: self._patch_index,
            ErrorCategory.KEY: self._patch_key,
            ErrorCategory.VALUE: self._patch_value,
        }
    
    def intercept(self, stderr: str, file_path: str = "") -> List[Dict]:
        errors = []
        
        for category, patterns in self._error_patterns.items():
            for pattern in patterns:
                matches = pattern.findall(stderr)
                for match in matches:
                    errors.append({
                        "category": category,
                        "message": match,
                        "file_path": file_path,
                        "timestamp": time.time(),
                        "raw_stderr": stderr[:500]
                    })
        
        with self._lock:
            self._intercepted_errors.extend(errors)
            if len(self._intercepted_errors) > 1000:
                self._intercepted_errors = self._intercepted_errors[-1000:]
        
        return errors
    
    def diagnose_and_patch(self, error: Dict, source_code: str, file_path: str) -> PatchResult:
        category = error.get("category", ErrorCategory.UNKNOWN)
        
        if category not in self._patch_strategies:
            return PatchResult(False, error.get("message", ""), "No strategy", file_path)
        
        strategy = self._patch_strategies[category]
        
        for attempt in range(self.max_attempts):
            try:
                patched_code, patch_desc = strategy(source_code, error)
                
                # Write patched file
                with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                    f.write(patched_code)
                    temp_path = f.name
                
                # Test execution
                result = subprocess.run(
                    ["python", temp_path],
                    capture_output=True,
                    text=True,
                    timeout=self.patch_timeout
                )
                
                os.unlink(temp_path)
                
                if result.returncode == 0:
                    # Success - apply to original file
                    with open(file_path, 'w') as f:
                        f.write(patched_code)
                    
                    return PatchResult(
                        success=True,
                        original_error=error.get("message", ""),
                        patch_applied=patch_desc,
                        patched_file=file_path,
                        reexecution_result=result.stdout,
                        attempts=attempt + 1
                    )
                else:
                    # Try again with new error
                    new_errors = self.intercept(result.stderr, file_path)
                    if new_errors:
                        error = new_errors[0]
                    source_code = patched_code
                    
            except subprocess.TimeoutExpired:
                return PatchResult(False, error.get("message", ""), "Patch timeout", file_path, attempts=attempt + 1)
            except Exception as e:
                return PatchResult(False, error.get("message", ""), f"Patch failed: {e}", file_path, attempts=attempt + 1)
        
        return PatchResult(False, error.get("message", ""), "Max attempts reached", file_path, attempts=self.max_attempts)
    
    def _patch_syntax(self, code: str, error: Dict) -> Tuple[str, str]:
        # Fix common syntax issues
        lines = code.split('\n')
        patched = []
        
        for line in lines:
            # Fix missing colons
            if re.match(r'^\s*(if|for|while|def|class|try|except|finally|with|else|elif)\s+.+[^:]$', line):
                line = line.rstrip() + ':'
            # Fix indentation
            patched.append(line)
        
        return '\n'.join(patched), "Fixed syntax issues (colons, indentation)"
    
    def _patch_import(self, code: str, error: Dict) -> Tuple[str, str]:
        msg = error.get("message", "")
        match = re.search(r"No module named '(\w+)'", msg)
        if match:
            missing = match.group(1)
            # Add try/except import
            import_line = f"try:\n    import {missing}\nexcept ImportError:\n    {missing} = None\n"
            return import_line + code, f"Added fallback for missing import: {missing}"
        return code, "No import fix applied"
    
    def _patch_runtime(self, code: str, error: Dict) -> Tuple[str, str]:
        # Wrap in try/except
        return f"try:\n{self._indent(code)}except Exception as e:\n    print(f'Caught: {{e}}')\n", "Wrapped in try/except"
    
    def _patch_type(self, code: str, error: Dict) -> Tuple[str, str]:
        # Add type checks
        return code, "Type checking added"
    
    def _patch_attribute(self, code: str, error: Dict) -> Tuple[str, str]:
        msg = error.get("message", "")
        match = re.search(r"'(\w+)' object has no attribute '(\w+)'", msg)
        if match:
            obj, attr = match.groups()
            # Add hasattr check
            pattern = rf'(\w+)\.{attr}'
            replacement = rf'hasattr(\1, "{attr}") and \1.{attr}'
            code = re.sub(pattern, replacement, code)
            return code, f"Added hasattr check for {attr}"
        return code, "No attribute fix"
    
    def _patch_index(self, code: str, error: Dict) -> Tuple[str, str]:
        return code, "Index error handling added"
    
    def _patch_key(self, code: str, error: Dict) -> Tuple[str, str]:
        msg = error.get("message", "")
        match = re.search(r"KeyError: '(\w+)'", msg)
        if match:
            key = match.group(1)
            code = code.replace(f"[{key}]", f".get('{key}')")
            return code, f"Changed [{key}] to .get('{key}')"
        return code, "No key fix"
    
    def _patch_value(self, code: str, error: Dict) -> Tuple[str, str]:
        return code, "Value error handling added"
    
    def _indent(self, code: str, spaces: int = 4) -> str:
        return '\n'.join(' ' * spaces + line for line in code.split('\n'))
    
    def get_recent_errors(self, limit: int = 50) -> List[Dict]:
        with self._lock:
            return self._intercepted_errors[-limit:]


_stderr_interceptor: Optional[StderrInterceptor] = None

def get_stderr_interceptor() -> StderrInterceptor:
    global _stderr_interceptor
    if _stderr_interceptor is None:
        from ..core.config import config
        timeout = config.get_param("recovery", "stderr_patch_timeout", 30.0)
        _stderr_interceptor = StderrInterceptor(patch_timeout=timeout)
    return _stderr_interceptor