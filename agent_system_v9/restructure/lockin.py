"""
Autonomous Lock-In Handshake - Freezes base prompts and locks execution into self-evolution mode
"""
import threading
import time
import hashlib
import json
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class LockInState(Enum):
    UNLOCKED = "unlocked"
    PREPARING = "preparing"
    LOCKED = "locked"
    EVOLVING = "evolving"
    ROLLED_BACK = "rolled_back"


@dataclass
class LockInConfig:
    freeze_prompts: bool = True
    freeze_tools: bool = True
    freeze_config: bool = True
    evolution_mode: bool = True
    checkpoint_interval: float = 60.0
    max_evolution_cycles: int = 1000


class AutonomousLockIn:
    def __init__(self, config: LockInConfig = None):
        self.config = config or LockInConfig()
        self._state = LockInState.UNLOCKED
        self._lock = threading.RLock()
        self._frozen_state: Dict[str, Any] = {}
        self._evolution_cycles = 0
        self._running = False
        self._checkpoint_thread: Optional[threading.Thread] = None
        self._callbacks: Dict[str, List[Callable]] = {
            "lock_initiated": [],
            "lock_completed": [],
            "evolution_cycle": [],
            "rollback_triggered": [],
            "unlock_completed": []
        }
        self._checkpoint_dir = Path("./lockin_checkpoints")
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)
    
    def initiate_lock(self) -> bool:
        with self._lock:
            if self._state != LockInState.UNLOCKED:
                return False
            
            self._state = LockInState.PREPARING
        
        self._notify_lock_initiated()
        
        # Freeze current state
        self._freeze_state()
        
        with self._lock:
            self._state = LockInState.LOCKED
            self._evolution_cycles = 0
        
        if self.config.evolution_mode:
            self._state = LockInState.EVOLVING
            self._running = True
            self._checkpoint_thread = threading.Thread(target=self._checkpoint_loop, daemon=True)
            self._checkpoint_thread.start()
        
        self._notify_lock_completed()
        return True
    
    def _freeze_state(self):
        # Capture current system state
        self._frozen_state = {
            "timestamp": time.time(),
            "prompts_hash": self._hash_prompts(),
            "tools_hash": self._hash_tools(),
            "config_hash": self._hash_config(),
            "checkpoint_id": hashlib.sha256(str(time.time()).encode()).hexdigest()[:12]
        }
        
        # Save checkpoint
        self._save_checkpoint()
    
    def _hash_prompts(self) -> str:
        # Would hash all prompt files
        return hashlib.sha256(b"prompts").hexdigest()[:16]
    
    def _hash_tools(self) -> str:
        # Would hash all tool definitions
        return hashlib.sha256(b"tools").hexdigest()[:16]
    
    def _hash_config(self) -> str:
        # Would hash configuration
        return hashlib.sha256(str(self.config).encode()).hexdigest()[:16]
    
    def _save_checkpoint(self):
        checkpoint_file = self._checkpoint_dir / f"checkpoint_{self._frozen_state['checkpoint_id']}.json"
        with open(checkpoint_file, 'w') as f:
            json.dump(self._frozen_state, f, indent=2)
    
    def _checkpoint_loop(self):
        while self._running and self._state == LockInState.EVOLVING:
            time.sleep(self.config.checkpoint_interval)
            if self._running:
                self._evolution_cycles += 1
                self._save_checkpoint()
                self._notify_evolution_cycle()
                
                if self._evolution_cycles >= self.config.max_evolution_cycles:
                    self._running = False
    
    def unlock(self) -> bool:
        with self._lock:
            if self._state == LockInState.UNLOCKED:
                return False
            
            self._running = False
            old_state = self._state
            self._state = LockInState.UNLOCKED
        
        if self._checkpoint_thread:
            self._checkpoint_thread.join(timeout=5.0)
        
        self._notify_unlock_completed()
        return True
    
    def rollback(self, checkpoint_id: str = None) -> bool:
        with self._lock:
            if self._state not in (LockInState.LOCKED, LockInState.EVOLVING):
                return False
        
        # Find checkpoint
        if checkpoint_id is None:
            checkpoints = sorted(self._checkpoint_dir.glob("checkpoint_*.json"),
                               key=lambda p: p.stat().st_mtime, reverse=True)
            if not checkpoints:
                return False
            checkpoint_file = checkpoints[0]
        else:
            checkpoint_file = self._checkpoint_dir / f"checkpoint_{checkpoint_id}.json"
            if not checkpoint_file.exists():
                return False
        
        # Load checkpoint
        with open(checkpoint_file, 'r') as f:
            frozen = json.load(f)
        
        # Restore state
        self._restore_state(frozen)
        
        with self._lock:
            self._state = LockInState.ROLLED_BACK
        
        self._notify_rollback_triggered(checkpoint_file.name)
        return True
    
    def _restore_state(self, frozen: Dict):
        # Would restore prompts, tools, config
        pass
    
    def get_state(self) -> LockInState:
        with self._lock:
            return self._state
    
    def get_evolution_cycles(self) -> int:
        with self._lock:
            return self._evolution_cycles
    
    def register_callback(self, event: str, callback: Callable):
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    def _notify_lock_initiated(self):
        for cb in self._callbacks["lock_initiated"]:
            try:
                cb()
            except Exception:
                pass
    
    def _notify_lock_completed(self):
        for cb in self._callbacks["lock_completed"]:
            try:
                cb()
            except Exception:
                pass
    
    def _notify_evolution_cycle(self):
        for cb in self._callbacks["evolution_cycle"]:
            try:
                cb(self._evolution_cycles)
            except Exception:
                pass
    
    def _notify_rollback_triggered(self, checkpoint: str):
        for cb in self._callbacks["rollback_triggered"]:
            try:
                cb(checkpoint)
            except Exception:
                pass
    
    def _notify_unlock_completed(self):
        for cb in self._callbacks["unlock_completed"]:
            try:
                cb()
            except Exception:
                pass


_lockin: Optional[AutonomousLockIn] = None

def get_lockin() -> AutonomousLockIn:
    global _lockin
    if _lockin is None:
        _lockin = AutonomousLockIn()
    return _lockin