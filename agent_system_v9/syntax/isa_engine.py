"""
Lexical Transformation ISA Engine - Applies language-agnostic text mutations (case, whitespace, line collapses)
"""
import re
import threading
from typing import Dict, List, Optional, Any, Callable, Pattern
from dataclasses import dataclass, field
from enum import Enum


class TransformationType(Enum):
    CASE = "case"
    WHITESPACE = "whitespace"
    LINE = "line"
    QUOTE = "quote"
    COMMENT = "comment"
    BRACKET = "bracket"
    OPERATOR = "operator"
    CUSTOM = "custom"


@dataclass
class TransformationRule:
    rule_id: str
    name: str
    pattern: Pattern
    replacement: str
    transformation_type: TransformationType
    flags: int = 0
    enabled: bool = True
    priority: int = 0
    description: str = ""


class ISAEngine:
    def __init__(self):
        self._rules: List[TransformationRule] = []
        self._lock = threading.RLock()
        self._register_default_rules()
    
    def _register_default_rules(self):
        # Case transformations
        self.add_rule(TransformationRule(
            rule_id="snake_case_functions",
            name="Snake Case Functions",
            pattern=re.compile(r'\b([A-Z][a-zA-Z0-9]*)\(\)'),
            replacement=lambda m: self._to_snake_case(m.group(1)) + "()",
            transformation_type=TransformationType.CASE,
            priority=10
        ))
        
        # Whitespace
        self.add_rule(TransformationRule(
            rule_id="normalize_spaces",
            name="Normalize Spaces",
            pattern=re.compile(r'[ \t]{2,}'),
            replacement=" ",
            transformation_type=TransformationType.WHITESPACE,
            priority=20
        ))
        
        self.add_rule(TransformationRule(
            rule_id="normalize_newlines",
            name="Normalize Newlines",
            pattern=re.compile(r'\n{3,}'),
            replacement="\n\n",
            transformation_type=TransformationType.LINE,
            priority=20
        ))
        
        # Trailing whitespace
        self.add_rule(TransformationRule(
            rule_id="trim_trailing",
            name="Trim Trailing Whitespace",
            pattern=re.compile(r'[ \t]+$', re.MULTILINE),
            replacement="",
            transformation_type=TransformationType.WHITESPACE,
            priority=30
        ))
        
        # Quotes
        self.add_rule(TransformationRule(
            rule_id="double_to_single_quotes",
            name="Double to Single Quotes",
            pattern=re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"'),
            replacement=r"'\1'",
            transformation_type=TransformationType.QUOTE,
            priority=40
        ))
        
        # Brackets
        self.add_rule(TransformationRule(
            rule_id="space_after_comma",
            name="Space After Comma",
            pattern=re.compile(r',([^\s])'),
            replacement=r", \1",
            transformation_type=TransformationType.OPERATOR,
            priority=50
        ))
        
        # Operators
        self.add_rule(TransformationRule(
            rule_id="space_around_operators",
            name="Space Around Operators",
            pattern=re.compile(r'(\w)([+\-*/%=<>!&|^])(\w)'),
            replacement=r"\1 \2 \3",
            transformation_type=TransformationType.OPERATOR,
            priority=50
        ))
    
    def _to_snake_case(self, name: str) -> str:
        import re
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
    
    def add_rule(self, rule: TransformationRule):
        with self._lock:
            self._rules.append(rule)
            self._rules.sort(key=lambda r: -r.priority)
    
    def remove_rule(self, rule_id: str) -> bool:
        with self._lock:
            for i, rule in enumerate(self._rules):
                if rule.rule_id == rule_id:
                    self._rules.pop(i)
                    return True
        return False
    
    def enable_rule(self, rule_id: str) -> bool:
        with self._lock:
            for rule in self._rules:
                if rule.rule_id == rule_id:
                    rule.enabled = True
                    return True
        return False
    
    def disable_rule(self, rule_id: str) -> bool:
        with self._lock:
            for rule in self._rules:
                if rule.rule_id == rule_id:
                    rule.enabled = False
                    return True
        return False
    
    def apply(self, text: str, rule_ids: List[str] = None) -> str:
        with self._lock:
            rules = list(self._rules)
        
        if rule_ids:
            rules = [r for r in rules if r.rule_id in rule_ids]
        
        rules = [r for r in rules if r.enabled]
        
        result = text
        for rule in rules:
            try:
                if callable(rule.replacement):
                    result = rule.pattern.sub(rule.replacement, result)
                else:
                    result = rule.pattern.sub(rule.replacement, result)
            except Exception:
                pass
        
        return result
    
    def apply_batch(self, texts: List[str], rule_ids: List[str] = None) -> List[str]:
        return [self.apply(text, rule_ids) for text in texts]
    
    def get_rules(self) -> List[TransformationRule]:
        with self._lock:
            return list(self._rules)
    
    def create_custom_rule(self, rule_id: str, name: str, pattern: str,
                          replacement: str, trans_type: TransformationType = TransformationType.CUSTOM,
                          flags: int = 0, priority: int = 0) -> TransformationRule:
        rule = TransformationRule(
            rule_id=rule_id,
            name=name,
            pattern=re.compile(pattern, flags),
            replacement=replacement,
            transformation_type=trans_type,
            flags=flags,
            priority=priority
        )
        self.add_rule(rule)
        return rule


_isa_engine: Optional[ISAEngine] = None

def get_isa_engine() -> ISAEngine:
    global _isa_engine
    if _isa_engine is None:
        _isa_engine = ISAEngine()
    return _isa_engine