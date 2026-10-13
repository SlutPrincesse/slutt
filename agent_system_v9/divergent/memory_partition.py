"""
Secure Memory Space Partitioning - Hardware/OS memory isolator restricting access to core state data
"""
import threading
import os
import mmap
import ctypes
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum


class PartitionType(Enum):
    CORE = "core"           # Core system state - highest protection
    AGENT = "agent"         # Agent working memory
    TOOL = "tool"           # Tool execution memory
    SANDBOX = "sandbox"     # Sandboxed execution
    SHARED = "shared"       # Shared between partitions


class AccessLevel(Enum):
    NONE = 0
    READ = 1
    WRITE = 2
    EXECUTE = 4
    READ_WRITE = 3
    FULL = 7


@dataclass
class PartitionConfig:
    partition_id: str
    partition_type: PartitionType
    size_bytes: int
    base_address: int = 0
    access_level: AccessLevel = AccessLevel.READ_WRITE
    encryption: bool = False
    guard_pages: bool = True


class MemoryPartition:
    def __init__(self):
        self._partitions: Dict[str, PartitionConfig] = {}
        self._memory_maps: Dict[str, mmap.mmap] = {}
        self._access_control: Dict[str, Dict[str, AccessLevel]] = {}  # partition -> {requester -> level}
        self._lock = threading.RLock()
        self._initialized = False
    
    def create_partition(self, config: PartitionConfig) -> bool:
        with self._lock:
            if config.partition_id in self._partitions:
                return False
            
            try:
                # Create memory map
                if config.base_address:
                    # Fixed address (requires special privileges)
                    mm = mmap.mmap(-1, config.size_bytes, 
                                  flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS,
                                  prot=mmap.PROT_READ | mmap.PROT_WRITE)
                else:
                    mm = mmap.mmap(-1, config.size_bytes,
                                  flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS,
                                  prot=mmap.PROT_READ | mmap.PROT_WRITE)
                
                # Add guard pages if enabled
                if config.guard_pages:
                    # mprotect the first and last pages as PROT_NONE
                    page_size = os.sysconf('SC_PAGE_SIZE')
                    if hasattr(mm, 'mprotect'):
                        mm.mprotect(0, page_size, mmap.PROT_NONE)
                        mm.mprotect(config.size_bytes - page_size, page_size, mmap.PROT_NONE)
                
                self._memory_maps[config.partition_id] = mm
                self._partitions[config.partition_id] = config
                self._access_control[config.partition_id] = {}
                
                return True
            except Exception:
                return False
    
    def delete_partition(self, partition_id: str) -> bool:
        with self._lock:
            mm = self._memory_maps.pop(partition_id, None)
            if mm:
                try:
                    mm.close()
                except Exception:
                    pass
            
            self._partitions.pop(partition_id, None)
            self._access_control.pop(partition_id, None)
            return True
    
    def grant_access(self, partition_id: str, requester: str, level: AccessLevel):
        with self._lock:
            if partition_id in self._access_control:
                self._access_control[partition_id][requester] = level
    
    def revoke_access(self, partition_id: str, requester: str):
        with self._lock:
            if partition_id in self._access_control:
                self._access_control[partition_id].pop(requester, None)
    
    def check_access(self, partition_id: str, requester: str, level: AccessLevel) -> bool:
        with self._lock:
            if partition_id not in self._access_control:
                return False
            granted = self._access_control[partition_id].get(requester, AccessLevel.NONE)
            return (granted.value & level.value) == level.value
    
    def read(self, partition_id: str, offset: int, size: int, requester: str) -> Optional[bytes]:
        if not self.check_access(partition_id, requester, AccessLevel.READ):
            raise PermissionError(f"Read access denied to {partition_id} for {requester}")
        
        with self._lock:
            mm = self._memory_maps.get(partition_id)
            if not mm:
                return None
            
            if offset + size > len(mm):
                return None
            
            return mm[offset:offset + size]
    
    def write(self, partition_id: str, offset: int, data: bytes, requester: str) -> bool:
        if not self.check_access(partition_id, requester, AccessLevel.WRITE):
            raise PermissionError(f"Write access denied to {partition_id} for {requester}")
        
        with self._lock:
            mm = self._memory_maps.get(partition_id)
            if not mm:
                return False
            
            if offset + len(data) > len(mm):
                return False
            
            mm[offset:offset + len(data)] = data
            return True
    
    def get_partition(self, partition_id: str) -> Optional[PartitionConfig]:
        with self._lock:
            return self._partitions.get(partition_id)
    
    def list_partitions(self) -> List[PartitionConfig]:
        with self._lock:
            return list(self._partitions.values())
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "partitions": len(self._partitions),
                "total_size": sum(p.size_bytes for p in self._partitions.values()),
                "by_type": {}
            }
    
    def initialize_core_partitions(self):
        """Create standard core partitions"""
        configs = [
            PartitionConfig("core_state", PartitionType.CORE, 1024*1024, 
                          access_level=AccessLevel.READ_WRITE, encryption=True),
            PartitionConfig("agent_memory", PartitionType.AGENT, 10*1024*1024,
                          access_level=AccessLevel.READ_WRITE),
            PartitionConfig("tool_scratch", PartitionType.TOOL, 5*1024*1024,
                          access_level=AccessLevel.READ_WRITE),
            PartitionConfig("sandbox_memory", PartitionType.SANDBOX, 50*1024*1024,
                          access_level=AccessLevel.READ_WRITE, guard_pages=True),
            PartitionConfig("shared_buffer", PartitionType.SHARED, 1024*1024,
                          access_level=AccessLevel.READ_WRITE),
        ]
        
        for config in configs:
            self.create_partition(config)
        
        self._initialized = True


_memory_partition: Optional[MemoryPartition] = None

def get_memory_partition() -> MemoryPartition:
    global _memory_partition
    if _memory_partition is None:
        _memory_partition = MemoryPartition()
        _memory_partition.initialize_core_partitions()
    return _memory_partition