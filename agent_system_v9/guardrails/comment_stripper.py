"""
Comment Stripper - Removes comments from code
"""
import ast
import re
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass
from pathlib import Path


@dataclass
class StripResult:
    original: str
    stripped: str
    comments_removed: int
    lines_removed: int


class CommentStripper:
    def __init__(self):
        self.preserve_shebang = True
        self.preserve_encoding = True
        self.preserve_docstrings = False
        self.preserve_todos = False

    def strip_file(self, file_path: str, output_path: str = None) -> StripResult:
        path = Path(file_path)
        content = path.read_text(encoding='utf-8', errors='ignore')
        
        if path.suffix == '.py':
            result = self._strip_python(content)
        else:
            result = self._strip_generic(content)
        
        if output_path:
            Path(output_path).write_text(result.stripped)
        
        return result

    def strip_string(self, content: str, language: str = 'python') -> StripResult:
        if language == 'python':
            return self._strip_python(content)
        else:
            return self._strip_generic(content)

    def _strip_python(self, content: str) -> StripResult:
        lines = content.split('\n')
        output_lines = []
        comments_removed = 0
        lines_removed = 0
        in_multiline_string = False
        multiline_quote = None
        
        for i, line in enumerate(lines):
            if i == 0 and self.preserve_shebang and line.startswith('#!'):
                output_lines.append(line)
                continue
            
            if i < 2 and self.preserve_encoding and re.match(r'#.*coding[:=]\s*[\w-]+', line):
                output_lines.append(line)
                continue
            
            stripped_line = line
            if not in_multiline_string:
                comment_pos = -1
                in_string = False
                string_char = None
                
                for j, char in enumerate(line):
                    if char in ('"', "'") and not in_string:
                        if j + 2 < len(line) and line[j:j+3] == char * 3:
                            in_multiline_string = True
                            multiline_quote = char * 3
                            in_string = True
                            string_char = char
                        else:
                            in_string = True
                            string_char = char
                    elif char == string_char and in_string:
                        if in_multiline_string and j + 2 < len(line) and line[j:j+3] == multiline_quote:
                            in_multiline_string = False
                            multiline_quote = None
                        in_string = False
                        string_char = None
                    elif char == '#' and not in_string:
                        comment_pos = j
                        break
                
                if comment_pos >= 0:
                    if self.preserve_todos and 'TODO' in line[comment_pos:].upper():
                        pass
                    else:
                        stripped_line = line[:comment_pos].rstrip()
                        comments_removed += 1
            
            if stripped_line or (in_multiline_string and self.preserve_docstrings):
                output_lines.append(stripped_line)
            else:
                lines_removed += 1
        
        stripped = '\n'.join(output_lines)
        if content.endswith('\n'):
            stripped += '\n'
        
        return StripResult(
            original=content,
            stripped=stripped,
            comments_removed=comments_removed,
            lines_removed=lines_removed,
        )

    def _strip_generic(self, content: str) -> StripResult:
        lines = content.split('\n')
        output_lines = []
        comments_removed = 0
        lines_removed = 0
        in_block_comment = False
        
        for line in lines:
            stripped_line = line
            
            if in_block_comment:
                end_pos = line.find('*/')
                if end_pos >= 0:
                    stripped_line = line[end_pos + 2:]
                    in_block_comment = False
                else:
                    comments_removed += 1
                    lines_removed += 1
                    continue
            
            while True:
                start_pos = stripped_line.find('/*')
                if start_pos < 0:
                    break
                
                end_pos = stripped_line.find('*/', start_pos + 2)
                if end_pos >= 0:
                    stripped_line = stripped_line[:start_pos] + stripped_line[end_pos + 2:]
                    comments_removed += 1
                else:
                    stripped_line = stripped_line[:start_pos]
                    in_block_comment = True
                    comments_removed += 1
                    break
            
            if not in_block_comment:
                comment_pos = stripped_line.find('//')
                if comment_pos >= 0:
                    if self.preserve_todos and 'TODO' in stripped_line[comment_pos:].upper():
                        pass
                    else:
                        stripped_line = stripped_line[:comment_pos].rstrip()
                        comments_removed += 1
            
            if stripped_line:
                output_lines.append(stripped_line)
            else:
                lines_removed += 1
        
        stripped = '\n'.join(output_lines)
        if content.endswith('\n'):
            stripped += '\n'
        
        return StripResult(
            original=content,
            stripped=stripped,
            comments_removed=comments_removed,
            lines_removed=lines_removed,
        )


class DocstringStripper:
    def __init__(self):
        self.preserve_module_docstring = True
        self.preserve_class_docstring = True
        self.preserve_function_docstring = True

    def strip_file(self, file_path: str, output_path: str = None) -> StripResult:
        path = Path(file_path)
        content = path.read_text(encoding='utf-8', errors='ignore')
        result = self.strip_string(content)
        
        if output_path:
            Path(output_path).write_text(result.stripped)
        
        return result

    def strip_string(self, content: str) -> StripResult:
        try:
            tree = ast.parse(content)
            lines = content.split('\n')
            to_remove = set()
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Module):
                    if not self.preserve_module_docstring:
                        docstring = ast.get_docstring(node)
                        if docstring:
                            self._mark_docstring_lines(lines, node, to_remove)
                elif isinstance(node, ast.ClassDef):
                    if not self.preserve_class_docstring:
                        docstring = ast.get_docstring(node)
                        if docstring:
                            self._mark_docstring_lines(lines, node, to_remove)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not self.preserve_function_docstring:
                        docstring = ast.get_docstring(node)
                        if docstring:
                            self._mark_docstring_lines(lines, node, to_remove)
            
            output_lines = [line for i, line in enumerate(lines) if i not in to_remove]
            stripped = '\n'.join(output_lines)
            if content.endswith('\n'):
                stripped += '\n'
            
            return StripResult(
                original=content,
                stripped=stripped,
                comments_removed=len(to_remove),
                lines_removed=len(to_remove),
            )
        except SyntaxError:
            return StripResult(original=content, stripped=content, comments_removed=0, lines_removed=0)

    def _mark_docstring_lines(self, lines: List[str], node: ast.AST, to_remove: Set[int]):
        if hasattr(node, 'lineno') and hasattr(node, 'end_lineno'):
            for i in range(node.lineno - 1, node.end_lineno):
                if i < len(lines):
                    stripped = lines[i].strip()
                    if stripped.startswith('"""') or stripped.startswith("'''"):
                        to_remove.add(i)
                        if stripped.count('"""') == 2 or stripped.count("'''") == 2:
                            break
                        for j in range(i + 1, min(i + 10, len(lines))):
                            to_remove.add(j)
                            if '"""' in lines[j] or "'''" in lines[j]:
                                break


class LicenseHeaderManager:
    def __init__(self):
        self.headers: Dict[str, str] = {}

    def add_header(self, language: str, header: str):
        self.headers[language] = header

    def apply_header(self, file_path: str, language: str = None) -> bool:
        path = Path(file_path)
        if not path.exists():
            return False
        
        language = language or path.suffix[1:]
        header = self.headers.get(language)
        if not header:
            return False
        
        content = path.read_text(encoding='utf-8', errors='ignore')
        if header.strip() in content[:len(header) + 100]:
            return True
        
        new_content = header + '\n\n' + content
        path.write_text(new_content)
        return True

    def remove_header(self, file_path: str, language: str = None) -> bool:
        path = Path(file_path)
        if not path.exists():
            return False
        
        language = language or path.suffix[1:]
        header = self.headers.get(language)
        if not header:
            return False
        
        content = path.read_text(encoding='utf-8', errors='ignore')
        if header.strip() in content[:len(header) + 100]:
            lines = content.split('\n')
            header_lines = header.strip().split('\n')
            new_lines = lines[len(header_lines) + 1:] if lines[len(header_lines)] == '' else lines[len(header_lines):]
            path.write_text('\n'.join(new_lines))
            return True
        return False