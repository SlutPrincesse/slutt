"""
PII & Key Redactor - Regex filter auto-redacting secrets, API keys, and sensitive PII from logs
"""
import re
import threading
from typing import Dict, List, Optional, Any, Callable, Pattern, Set
from dataclasses import dataclass, field
from enum import Enum


class RedactionType(Enum):
    API_KEY = "api_key"
    SECRET = "secret"
    PASSWORD = "password"
    TOKEN = "token"
    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    IP_ADDRESS = "ip_address"
    JWT = "jwt"
    PRIVATE_KEY = "private_key"
    DATABASE_URL = "database_url"
    CUSTOM = "custom"


@dataclass
class RedactionRule:
    rule_id: str
    name: str
    pattern: Pattern
    redaction_type: RedactionType
    replacement: str = "[REDACTED]"
    groups: List[int] = field(default_factory=lambda: [0])
    enabled: bool = True
    description: str = ""


class PIIKeyRedactor:
    def __init__(self):
        self._rules: Dict[str, RedactionRule] = {}
        self._lock = threading.RLock()
        self._register_default_rules()
    
    def _register_default_rules(self):
        # API Keys
        self.add_rule(RedactionRule(
            rule_id="api_key_generic",
            name="Generic API Key",
            pattern=re.compile(r'(?i)(api[_-]?key|apikey)\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?', re.IGNORECASE),
            redaction_type=RedactionType.API_KEY,
            replacement="[API_KEY]",
            groups=[2]
        ))
        
        self.add_rule(RedactionRule(
            rule_id="api_key_bearer",
            name="Bearer Token",
            pattern=re.compile(r'(?i)bearer\s+([a-zA-Z0-9_\-]{20,})'),
            redaction_type=RedactionType.TOKEN,
            replacement="[BEARER_TOKEN]",
            groups=[1]
        ))
        
        # OpenAI
        self.add_rule(RedactionRule(
            rule_id="openai_key",
            name="OpenAI API Key",
            pattern=re.compile(r'sk-[a-zA-Z0-9]{48,}'),
            redaction_type=RedactionType.API_KEY,
            replacement="[OPENAI_KEY]",
            groups=[0]
        ))
        
        # Anthropic
        self.add_rule(RedactionRule(
            rule_id="anthropic_key",
            name="Anthropic API Key",
            pattern=re.compile(r'sk-ant-[a-zA-Z0-9_\-]{95,}'),
            redaction_type=RedactionType.API_KEY,
            replacement="[ANTHROPIC_KEY]",
            groups=[0]
        ))
        
        # AWS
        self.add_rule(RedactionRule(
            rule_id="aws_access_key",
            name="AWS Access Key",
            pattern=re.compile(r'AKIA[0-9A-Z]{16}'),
            redaction_type=RedactionType.API_KEY,
            replacement="[AWS_ACCESS_KEY]",
            groups=[0]
        ))
        
        self.add_rule(RedactionRule(
            rule_id="aws_secret_key",
            name="AWS Secret Key",
            pattern=re.compile(r'(?i)aws[_-]?secret[_-]?access[_-]?key\s*[:=]\s*["\']?([a-zA-Z0-9/+=]{40})["\']?'),
            redaction_type=RedactionType.SECRET,
            replacement="[AWS_SECRET_KEY]",
            groups=[1]
        ))
        
        # GitHub
        self.add_rule(RedactionRule(
            rule_id="github_token",
            name="GitHub Token",
            pattern=re.compile(r'gh[ps]_[a-zA-Z0-9]{36,}'),
            redaction_type=RedactionType.TOKEN,
            replacement="[GITHUB_TOKEN]",
            groups=[0]
        ))
        
        # Generic secrets
        self.add_rule(RedactionRule(
            rule_id="generic_secret",
            name="Generic Secret",
            pattern=re.compile(r'(?i)(secret|password|passwd|pwd)\s*[:=]\s*["\']?([^\s"\']{8,})["\']?'),
            redaction_type=RedactionType.SECRET,
            replacement="[SECRET]",
            groups=[2]
        ))
        
        # Private keys
        self.add_rule(RedactionRule(
            rule_id="private_key",
            name="Private Key",
            pattern=re.compile(r'-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----[\s\S]*?-----END (RSA |EC |DSA )?PRIVATE KEY-----'),
            redaction_type=RedactionType.PRIVATE_KEY,
            replacement="[PRIVATE_KEY]",
            groups=[0]
        ))
        
        # JWT
        self.add_rule(RedactionRule(
            rule_id="jwt",
            name="JWT Token",
            pattern=re.compile(r'eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+'),
            redaction_type=RedactionType.JWT,
            replacement="[JWT]",
            groups=[0]
        ))
        
        # Database URLs
        self.add_rule(RedactionRule(
            rule_id="database_url",
            name="Database URL",
            pattern=re.compile(r'(?i)(postgres|mysql|mongodb|redis)://[^:\s]+:[^@\s]+@[^/\s]+/\w+'),
            redaction_type=RedactionType.DATABASE_URL,
            replacement="[DATABASE_URL]",
            groups=[0]
        ))
        
        # Email
        self.add_rule(RedactionRule(
            rule_id="email",
            name="Email Address",
            pattern=re.compile(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b'),
            redaction_type=RedactionType.EMAIL,
            replacement="[EMAIL]",
            groups=[0]
        ))
        
        # Phone numbers
        self.add_rule(RedactionRule(
            rule_id="phone_us",
            name="US Phone Number",
            pattern=re.compile(r'(\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})'),
            redaction_type=RedactionType.PHONE,
            replacement="[PHONE]",
            groups=[0]
        ))
        
        # SSN
        self.add_rule(RedactionRule(
            rule_id="ssn",
            name="Social Security Number",
            pattern=re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
            redaction_type=RedactionType.SSN,
            replacement="[SSN]",
            groups=[0]
        ))
        
        # Credit Card
        self.add_rule(RedactionRule(
            rule_id="credit_card",
            name="Credit Card Number",
            pattern=re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b'),
            redaction_type=RedactionType.CREDIT_CARD,
            replacement="[CREDIT_CARD]",
            groups=[0]
        ))
        
        # IP Address
        self.add_rule(RedactionRule(
            rule_id="ipv4",
            name="IPv4 Address",
            pattern=re.compile(r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'),
            redaction_type=RedactionType.IP_ADDRESS,
            replacement="[IP_ADDRESS]",
            groups=[0]
        ))
        
        # IPv6
        self.add_rule(RedactionRule(
            rule_id="ipv6",
            name="IPv6 Address",
            pattern=re.compile(r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b'),
            redaction_type=RedactionType.IP_ADDRESS,
            replacement="[IP_ADDRESS]",
            groups=[0]
        ))
    
    def add_rule(self, rule: RedactionRule):
        with self._lock:
            self._rules[rule.rule_id] = rule
    
    def remove_rule(self, rule_id: str) -> bool:
        with self._lock:
            if rule_id in self._rules:
                del self._rules[rule_id]
                return True
        return False
    
    def enable_rule(self, rule_id: str) -> bool:
        with self._lock:
            if rule_id in self._rules:
                self._rules[rule_id].enabled = True
                return True
        return False
    
    def disable_rule(self, rule_id: str) -> bool:
        with self._lock:
            if rule_id in self._rules:
                self._rules[rule_id].enabled = False
                return True
        return False
    
    def redact(self, text: str, rule_ids: List[str] = None) -> str:
        if not text:
            return text
        
        with self._lock:
            rules = list(self._rules.values())
        
        if rule_ids:
            rules = [r for r in rules if r.rule_id in rule_ids]
        
        rules = [r for r in rules if r.enabled]
        
        result = text
        for rule in rules:
            result = rule.pattern.sub(rule.replacement, result)
        
        return result
    
    def redact_lines(self, lines: List[str], rule_ids: List[str] = None) -> List[str]:
        return [self.redact(line, rule_ids) for line in lines]
    
    def redact_dict(self, data: Dict[str, Any], rule_ids: List[str] = None,
                    redact_keys: bool = True, redact_values: bool = True) -> Dict[str, Any]:
        result = {}
        for key, value in data.items():
            new_key = self.redact(key, rule_ids) if redact_keys else key
            if isinstance(value, str):
                new_value = self.redact(value, rule_ids) if redact_values else value
            elif isinstance(value, dict):
                new_value = self.redact_dict(value, rule_ids, redact_keys, redact_values)
            elif isinstance(value, list):
                new_value = [self.redact(v, rule_ids) if isinstance(v, str) and redact_values else v for v in value]
            else:
                new_value = value
            result[new_key] = new_value
        return result
    
    def find_matches(self, text: str, rule_ids: List[str] = None) -> List[Dict[str, Any]]:
        matches = []
        
        with self._lock:
            rules = list(self._rules.values())
        
        if rule_ids:
            rules = [r for r in rules if r.rule_id in rule_ids]
        
        rules = [r for r in rules if r.enabled]
        
        for rule in rules:
            for match in rule.pattern.finditer(text):
                for group_idx in rule.groups:
                    if group_idx < len(match.groups()) + 1:
                        matched_text = match.group(group_idx)
                        matches.append({
                            "rule_id": rule.rule_id,
                            "rule_name": rule.name,
                            "redaction_type": rule.redaction_type.value,
                            "matched_text": matched_text,
                            "start": match.start(group_idx),
                            "end": match.end(group_idx),
                            "full_match": match.group(0)
                        })
        
        return matches
    
    def get_rules(self) -> List[RedactionRule]:
        with self._lock:
            return list(self._rules.values())
    
    def get_enabled_rules(self) -> List[RedactionRule]:
        with self._lock:
            return [r for r in self._rules.values() if r.enabled]
    
    def create_custom_rule(self, rule_id: str, name: str, pattern: str,
                          redaction_type: RedactionType = RedactionType.CUSTOM,
                          replacement: str = "[REDACTED]",
                          groups: List[int] = None,
                          flags: int = 0) -> RedactionRule:
        rule = RedactionRule(
            rule_id=rule_id,
            name=name,
            pattern=re.compile(pattern, flags),
            redaction_type=redaction_type,
            replacement=replacement,
            groups=groups or [0]
        )
        self.add_rule(rule)
        return rule


_redactor: Optional[PIIKeyRedactor] = None

def get_redactor() -> PIIKeyRedactor:
    global _redactor
    if _redactor is None:
        _redactor = PIIKeyRedactor()
    return _redactor