"""
Dynamic Entropy Secret Detector - Detects secrets, keys, and high-entropy strings
"""
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SecretType(Enum):
    API_KEY = "api_key"
    PRIVATE_KEY = "private_key"
    PASSWORD = "password"
    TOKEN = "token"
    CERTIFICATE = "certificate"
    DATABASE_URL = "database_url"
    AWS_KEY = "aws_key"
    GCP_KEY = "gcp_key"
    AZURE_KEY = "azure_key"
    SSH_KEY = "ssh_key"
    JWT = "jwt"
    GENERIC_HIGH_ENTROPY = "generic_high_entropy"


@dataclass
class SecretMatch:
    secret_type: SecretType
    matched_text: str
    file_path: str
    line_number: int
    column: int
    entropy: float
    confidence: float
    pattern_name: str
    context: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "secret_type": self.secret_type.value,
            "matched_text": self.matched_text[:100] + "..." if len(self.matched_text) > 100 else self.matched_text,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "column": self.column,
            "entropy": self.entropy,
            "confidence": self.confidence,
            "pattern_name": self.pattern_name,
            "context": self.context,
            "metadata": self.metadata,
        }


class EntropyDetector:
    def __init__(self, entropy_threshold: float = 4.5, min_length: int = 20):
        self.entropy_threshold = entropy_threshold
        self.min_length = min_length
        self.patterns: dict[SecretType, list[tuple[str, re.Pattern]]] = {}
        self._compile_default_patterns()

    def _compile_default_patterns(self):
        self.patterns[SecretType.API_KEY] = [
            ("generic_api_key", re.compile(r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?')),
            ("stripe", re.compile(r'sk_live_[a-zA-Z0-9]{24,}')),
            ("github", re.compile(r'gh[pousr]_[a-zA-Z0-9]{36,}')),
            ("slack", re.compile(r'xox[baprs]-[a-zA-Z0-9-]{20,}')),
            ("sendgrid", re.compile(r'SG\.[a-zA-Z0-9_-]{22}\.[a-zA-Z0-9_-]{43}')),
        ]

        self.patterns[SecretType.PRIVATE_KEY] = [
            ("rsa_private_key", re.compile(r'-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (RSA |EC |OPENSSH )?PRIVATE KEY-----')),
            ("ssh_private_key", re.compile(r'-----BEGIN OPENSSH PRIVATE KEY-----[\s\S]*?-----END OPENSSH PRIVATE KEY-----')),
            ("pem_private_key", re.compile(r'-----BEGIN PRIVATE KEY-----[\s\S]*?-----END PRIVATE KEY-----')),
        ]

        self.patterns[SecretType.TOKEN] = [
            ("jwt", re.compile(r'eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+')),
            ("bearer_token", re.compile(r'(?i)bearer\s+[a-zA-Z0-9_\-\.]{20,}')),
            ("oauth_token", re.compile(r'(?i)(access_token|refresh_token)\s*[=:]\s*["\']?([a-zA-Z0-9_\-\.]{20,})["\']?')),
        ]

        self.patterns[SecretType.DATABASE_URL] = [
            ("postgres", re.compile(r'postgres(?:ql)?://[^:\s]+:[^@\s]+@[^/\s]+/[^"\'\s]+')),
            ("mysql", re.compile(r'mysql://[^:\s]+:[^@\s]+@[^/\s]+/[^"\'\s]+')),
            ("mongodb", re.compile(r'mongodb(?:\+srv)?://[^:\s]+:[^@\s]+@[^/\s]+')),
            ("redis", re.compile(r'redis://[^:\s]+:[^@\s]+@[^/\s]+')),
        ]

        self.patterns[SecretType.AWS_KEY] = [
            ("aws_access_key", re.compile(r'AKIA[0-9A-Z]{16}')),
            ("aws_secret_key", re.compile(r'(?i)aws[_-]?secret[_-]?access[_-]?key\s*[=:]\s*["\']?([a-zA-Z0-9/+=]{40})["\']?')),
            ("aws_session_token", re.compile(r'(?i)aws[_-]?session[_-]?token\s*[=:]\s*["\']?([a-zA-Z0-9/+=]{100,})["\']?')),
        ]

        self.patterns[SecretType.GCP_KEY] = [
            ("gcp_service_account", re.compile(r'(?i)"type"\s*:\s*"service_account"[\s\S]*?"private_key"\s*:\s*"-----BEGIN PRIVATE KEY-----')),
            ("gcp_api_key", re.compile(r'AIza[0-9A-Za-z_-]{35}')),
        ]

        self.patterns[SecretType.AZURE_KEY] = [
            ("azure_storage_key", re.compile(r'DefaultEndpointsProtocol=https;AccountName=[^;]+;AccountKey=[^;]+')),
            ("azure_client_secret", re.compile(r'(?i)azure[_-]?client[_-]?secret\s*[=:]\s*["\']?([a-zA-Z0-9_\-\.]{20,})["\']?')),
        ]

        self.patterns[SecretType.SSH_KEY] = [
            ("ssh_public_key", re.compile(r'ssh-(rsa|dsa|ecdsa|ed25519)\s+[a-zA-Z0-9+/]+[=]{0,2}')),
            ("ssh_private_key_openssh", re.compile(r'-----BEGIN OPENSSH PRIVATE KEY-----')),
        ]

    def add_pattern(self, secret_type: SecretType, pattern_name: str, pattern: str):
        if secret_type not in self.patterns:
            self.patterns[secret_type] = []
        self.patterns[secret_type].append((pattern_name, re.compile(pattern)))

    def calculate_entropy(self, text: str) -> float:
        if not text:
            return 0.0
        counter = Counter(text)
        length = len(text)
        entropy = 0.0
        for count in counter.values():
            p = count / length
            entropy -= p * math.log2(p)
        return entropy

    def is_high_entropy(self, text: str) -> bool:
        return len(text) >= self.min_length and self.calculate_entropy(text) >= self.entropy_threshold

    def scan_text(self, text: str, file_path: str = "<string>") -> list[SecretMatch]:
        matches = []
        lines = text.split('\n')

        for secret_type, patterns in self.patterns.items():
            for pattern_name, pattern in patterns:
                for match in pattern.finditer(text):
                    matched = match.group(0)
                    line_num = text[:match.start()].count('\n') + 1
                    column = match.start() - text.rfind('\n', 0, match.start())
                    context_start = max(0, match.start() - 50)
                    context_end = min(len(text), match.end() + 50)
                    context = text[context_start:context_end]

                    entropy = self.calculate_entropy(matched)
                    confidence = self._calculate_confidence(secret_type, matched, entropy)

                    matches.append(SecretMatch(
                        secret_type=secret_type,
                        matched_text=matched,
                        file_path=file_path,
                        line_number=line_num,
                        column=column,
                        entropy=entropy,
                        confidence=confidence,
                        pattern_name=pattern_name,
                        context=context,
                    ))

        high_entropy_matches = self._find_high_entropy_strings(text, file_path)
        matches.extend(high_entropy_matches)

        return self._deduplicate_matches(matches)

    def _find_high_entropy_strings(self, text: str, file_path: str) -> list[SecretMatch]:
        matches = []
        words = re.findall(r'[a-zA-Z0-9+/=_-]{20,}', text)

        for word in set(words):
            entropy = self.calculate_entropy(word)
            if entropy >= self.entropy_threshold:
                pos = text.find(word)
                if pos >= 0:
                    line_num = text[:pos].count('\n') + 1
                    column = pos - text.rfind('\n', 0, pos)
                    context_start = max(0, pos - 50)
                    context_end = min(len(text), pos + len(word) + 50)
                    context = text[context_start:context_end]

                    matches.append(SecretMatch(
                        secret_type=SecretType.GENERIC_HIGH_ENTROPY,
                        matched_text=word,
                        file_path=file_path,
                        line_number=line_num,
                        column=column,
                        entropy=entropy,
                        confidence=min(entropy / 8.0, 1.0),
                        pattern_name="high_entropy",
                        context=context,
                        metadata={"detected_by": "entropy_analysis"},
                    ))

        return matches

    def _calculate_confidence(self, secret_type: SecretType, text: str, entropy: float) -> float:
        base_confidence = min(entropy / 8.0, 1.0)

        if secret_type == SecretType.JWT:
            return 0.95 if text.count('.') == 2 else 0.5
        if secret_type == SecretType.AWS_KEY:
            return 0.9 if text.startswith('AKIA') else 0.7
        if secret_type == SecretType.GCP_KEY:
            return 0.85
        if secret_type == SecretType.PRIVATE_KEY:
            return 0.95
        if secret_type == SecretType.DATABASE_URL:
            return 0.9

        return base_confidence

    def _deduplicate_matches(self, matches: list[SecretMatch]) -> list[SecretMatch]:
        seen = set()
        unique = []
        for match in matches:
            key = (match.file_path, match.line_number, match.matched_text[:50])
            if key not in seen:
                seen.add(key)
                unique.append(match)
        return unique

    def scan_file(self, file_path: str) -> list[SecretMatch]:
        try:
            with open(file_path, encoding='utf-8', errors='ignore') as f:
                content = f.read()
            return self.scan_text(content, file_path)
        except Exception:
            return []

    def scan_directory(self, path: str, extensions: list[str] = None) -> list[SecretMatch]:
        if extensions is None:
            extensions = ['.py', '.js', '.ts', '.json', '.yaml', '.yml', '.env', '.config', '.ini', '.txt', '.md']

        all_matches = []
        for ext in extensions:
            for file_path in Path(path).rglob(f'*{ext}'):
                matches = self.scan_file(str(file_path))
                all_matches.extend(matches)

        return all_matches


from pathlib import Path
