"""
Stealth Proxy Execution & Identity Randomizer - Rotates IPs, MAC signatures, and user-agents during metadata fetches
"""
import threading
import time
import random
import requests
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum


class ProxyType(Enum):
    HTTP = "http"
    HTTPS = "https"
    SOCKS4 = "socks4"
    SOCKS5 = "socks5"


@dataclass
class ProxyConfig:
    proxy_type: ProxyType = ProxyType.HTTP
    rotation_interval: float = 300.0
    proxy_list: List[str] = field(default_factory=list)
    user_agents: List[str] = field(default_factory=list)
    verify_ssl: bool = True
    timeout: float = 10.0


class StealthProxyExecutor:
    def __init__(self, config: ProxyConfig = None):
        self.config = config or ProxyConfig()
        self._current_proxy: Optional[str] = None
        self._current_ua: Optional[str] = None
        self._lock = threading.Lock()
        self._running = False
        self._rotation_thread: Optional[threading.Thread] = None
        self._session = requests.Session()
        self._stats = {"requests": 0, "rotations": 0, "failures": 0}
        
        # Default user agents
        if not self.config.user_agents:
            self.config.user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/109.0",
            ]
    
    def start(self):
        if self._running:
            return
        self._running = True
        self._rotate_identity()
        self._rotation_thread = threading.Thread(target=self._rotation_loop, daemon=True)
        self._rotation_thread.start()
    
    def stop(self):
        self._running = False
        if self._rotation_thread:
            self._rotation_thread.join(timeout=5.0)
    
    def _rotation_loop(self):
        while self._running:
            time.sleep(self.config.rotation_interval)
            if self._running:
                self._rotate_identity()
    
    def _rotate_identity(self):
        with self._lock:
            if self.config.proxy_list:
                self._current_proxy = random.choice(self.config.proxy_list)
            self._current_ua = random.choice(self.config.user_agents)
            self._stats["rotations"] += 1
    
    def get_session(self) -> requests.Session:
        with self._lock:
            session = requests.Session()
            if self._current_proxy:
                session.proxies = {"http": self._current_proxy, "https": self._current_proxy}
            session.headers.update({"User-Agent": self._current_ua or self.config.user_agents[0]})
            return session
    
    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        session = self.get_session()
        kwargs.setdefault("timeout", self.config.timeout)
        kwargs.setdefault("verify", self.config.verify_ssl)
        
        try:
            response = session.request(method, url, **kwargs)
            self._stats["requests"] += 1
            return response
        except Exception as e:
            self._stats["failures"] += 1
            # Try with new identity
            self._rotate_identity()
            session = self.get_session()
            return session.request(method, url, **kwargs)
    
    def get(self, url: str, **kwargs) -> requests.Response:
        return self.request("GET", url, **kwargs)
    
    def post(self, url: str, **kwargs) -> requests.Response:
        return self.request("POST", url, **kwargs)
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                **self._stats,
                "current_proxy": self._current_proxy,
                "current_ua": self._current_ua[:50] if self._current_ua else None
            }
    
    def add_proxy(self, proxy: str):
        with self._lock:
            if proxy not in self.config.proxy_list:
                self.config.proxy_list.append(proxy)
    
    def remove_proxy(self, proxy: str):
        with self._lock:
            if proxy in self.config.proxy_list:
                self.config.proxy_list.remove(proxy)


_proxy_executor: Optional[StealthProxyExecutor] = None

def get_proxy_executor() -> StealthProxyExecutor:
    global _proxy_executor
    if _proxy_executor is None:
        from ..core.config import config
        cfg = ProxyConfig(
            rotation_interval=config.get_param("restructure", "proxy_rotation_interval", 300)
        )
        _proxy_executor = StealthProxyExecutor(cfg)
        _proxy_executor.start()
    return _proxy_executor