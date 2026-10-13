"""
Core System Configuration - Dynamic configuration management with environment variable support
"""
import json
import os
import threading
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class SectionConfig:
    enabled: bool = True
    parameters: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    resource_limits: dict[str, Any] = field(default_factory=dict)


class SystemConfig:
    _instance: Optional['SystemConfig'] = None
    _lock = threading.RLock()

    DEFAULTS = {
        "kernel": SectionConfig(
            enabled=True,
            parameters={
                "max_processes": 100,
                "default_timeout": 30.0,
                "pty_buffer_size": 8192,
                "sandbox_memory_limit": "512m",
                "sandbox_cpu_limit": "1.0",
                "log_tail_lines": 1000
            }
        ),
        "prompt": SectionConfig(
            enabled=True,
            parameters={
                "max_token_budget": 100000,
                "compression_ratio": 0.7,
                "optimization_iterations": 3,
                "cache_ttl": 3600
            }
        ),
        "multimodal": SectionConfig(
            enabled=True,
            parameters={
                "audio_sample_rate": 16000,
                "image_max_dimension": 2048,
                "vision_confidence_threshold": 0.7
            }
        ),
        "audit": SectionConfig(
            enabled=True,
            parameters={
                "telemetry_batch_size": 100,
                "metrics_port": 9090,
                "log_retention_days": 30,
                "pii_redaction_enabled": True
            }
        ),
        "neurocranial": SectionConfig(
            enabled=True,
            parameters={
                "event_bus_capacity": 10000,
                "stream_split_ratio": 0.5,
                "approval_timeout": 5.0
            }
        ),
        "divergent": SectionConfig(
            enabled=True,
            parameters={
                "max_parallel_worktrees": 10,
                "merge_strategy": "ast",
                "failure_trace_model": "sub1b"
            }
        ),
        "hud": SectionConfig(
            enabled=True,
            parameters={
                "visualization_fps": 30,
                "shader_update_interval": 100,
                "nudge_sensitivity": 0.8
            }
        ),
        "restructure": SectionConfig(
            enabled=True,
            parameters={
                "vulnerability_scan_interval": 3600,
                "proxy_rotation_interval": 300,
                "intent_cache_ttl": 600
            }
        ),
        "prometheus9": SectionConfig(
            enabled=True,
            parameters={
                "mcp_max_roundtrips": 5,
                "ast_verification_strict": True,
                "callback_timeout": 1.0
            }
        ),
        "recovery": SectionConfig(
            enabled=True,
            parameters={
                "max_retry_attempts": 3,
                "stderr_patch_timeout": 30.0,
                "merge_core_threshold": 0.85
            }
        ),
        "syntax": SectionConfig(
            enabled=True,
            parameters={
                "isa_optimization_level": 2,
                "sanitization_strict": True,
                "memory_serialization_interval": 60
            }
        ),
        "threat": SectionConfig(
            enabled=True,
            parameters={
                "threat_seeding_rate": 0.1,
                "deep_audit_depth": 5,
                "stress_test_duration": 60
            }
        ),
        "blueprint": SectionConfig(
            enabled=True,
            parameters={
                "supported_languages": ["python", "typescript", "rust", "go", "java", "csharp", "cpp", "php", "ruby"],
                "idl_format": "json_schema",
                "ffi_cache_ttl": 3600
            }
        ),
        "distributed": SectionConfig(
            enabled=True,
            parameters={
                "rpc_timeout": 10.0,
                "dag_partition_strategy": "balanced",
                "consensus_timeout": 5.0,
                "crdt_sync_interval": 1.0
            }
        ),
        "reasoning": SectionConfig(
            enabled=True,
            parameters={
                "vector_dim": 768,
                "episodic_retention_days": 90,
                "ontology_update_interval": 3600
            }
        ),
        "security": SectionConfig(
            enabled=True,
            parameters={
                "zero_trust_enforcement": True,
                "entropy_threshold": 4.5,
                "vuln_scan_on_change": True,
                "egress_whitelist": []
            }
        ),
        "reactive": SectionConfig(
            enabled=True,
            parameters={
                "backpressure_threshold": 0.8,
                "hook_execution_timeout": 5.0,
                "fsm_strict_validation": True
            }
        ),
        "compilation": SectionConfig(
            enabled=True,
            parameters={
                "hot_swap_enabled": True,
                "memory_compilation": True,
                "type_marshalling_strict": True
            }
        ),
        "storage": SectionConfig(
            enabled=True,
            parameters={
                "cas_enabled": True,
                "delta_sync_enabled": True,
                "ephemeral_ttl": 3600,
                "build_ledger_enabled": True
            }
        ),
        "deployment": SectionConfig(
            enabled=True,
            parameters={
                "health_check_timeout": 30.0,
                "degradation_threshold": 0.7,
                "bundle_compression": "zstd"
            }
        ),
        "context": SectionConfig(
            enabled=True,
            parameters={
                "attention_head_count": 8,
                "summary_tiers": 3,
                "cache_invalidation_threshold": 0.3,
                "boundary_monitor_interval": 1.0
            }
        ),
        "benchmark": SectionConfig(
            enabled=True,
            parameters={
                "complexity_threshold": 10,
                "performance_baseline_samples": 10,
                "coverage_target": 0.85
            }
        ),
        "edge": SectionConfig(
            enabled=True,
            parameters={
                "local_model_fallback": True,
                "offline_cache_size": "1GB",
                "sync_batch_size": 100,
                "power_throttle_threshold": 0.2
            }
        ),
        "cicd": SectionConfig(
            enabled=True,
            parameters={
                "self_modification_enabled": True,
                "canary_duration": 300,
                "capability_export_format": "json"
            }
        ),
        "workspace": SectionConfig(
            enabled=True,
            parameters={
                "isolation_mode": "strict",
                "ast_drivers": ["tree-sitter"],
                "mutation_precision": "function"
            }
        ),
        "guardrails": SectionConfig(
            enabled=True,
            parameters={
                "slop_detection_enabled": True,
                "max_comment_ratio": 0.3,
                "complexity_limit": 10,
                "noop_detection": True
            }
        ),
        "tools": SectionConfig(
            enabled=True,
            parameters={
                "synthesis_timeout": 60.0,
                "validation_strict": True,
                "auto_load_generated": True
            }
        ),
        "shadowgit": SectionConfig(
            enabled=True,
            parameters={
                "checkpoint_interval": 1,
                "rollback_on_failure": True,
                "micro_commit_prefix": "μ"
            }
        ),
        "evolution": SectionConfig(
            enabled=True,
            parameters={
                "projection_dimensions": 64,
                "max_shadow_clones": 8,
                "fitness_weights": {
                    "correctness": 0.4,
                    "performance": 0.2,
                    "memory": 0.2,
                    "anti_slop": 0.2
                }
            }
        )
    }

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._config: dict[str, SectionConfig] = deepcopy(self.DEFAULTS)
        self._env_prefix = "AGENT_V9_"
        self._config_files: list[Path] = []
        self._watchers: list[Callable] = []
        self._initialized = True
        self._load_from_env()

    def _load_from_env(self):
        for key, value in os.environ.items():
            if key.startswith(self._env_prefix):
                parts = key[len(self._env_prefix):].lower().split("__")
                if len(parts) >= 2:
                    section, param = parts[0], parts[1]
                    if section in self._config:
                        self._set_nested_param(section, param, self._parse_value(value))

    def _parse_value(self, value: str) -> Any:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            if value.lower() in ("true", "false"):
                return value.lower() == "true"
            try:
                return int(value)
            except ValueError:
                try:
                    return float(value)
                except ValueError:
                    return value

    def _set_nested_param(self, section: str, param: str, value: Any):
        if section in self._config:
            keys = param.split("_")
            target = self._config[section].parameters
            for key in keys[:-1]:
                if key not in target:
                    target[key] = {}
                target = target[key]
            target[keys[-1]] = value

    def load_file(self, path: str | Path) -> bool:
        path = Path(path)
        if not path.exists():
            return False

        try:
            if path.suffix in (".yaml", ".yml"):
                with Path(path).open() as f:
                    data = yaml.safe_load(f)
            elif path.suffix == ".json":
                with Path(path).open() as f:
                    data = json.load(f)
            else:
                return False

            for section, section_data in data.items():
                if section in self._config:
                    if isinstance(section_data, dict):
                        if "enabled" in section_data:
                            self._config[section].enabled = section_data["enabled"]
                        if "parameters" in section_data:
                            self._config[section].parameters.update(section_data["parameters"])
                        if "dependencies" in section_data:
                            self._config[section].dependencies = section_data["dependencies"]
                        if "resource_limits" in section_data:
                            self._config[section].resource_limits = section_data["resource_limits"]

            self._config_files.append(path)
            self._notify_watchers()
            return True
        except Exception:
            return False

    def save_file(self, path: str | Path) -> bool:
        path = Path(path)
        try:
            data = {}
            for section, config in self._config.items():
                data[section] = asdict(config)

            if path.suffix in (".yaml", ".yml"):
                with Path(path).open("w") as f:
                    yaml.dump(data, f, default_flow_style=False)
            elif path.suffix == ".json":
                with Path(path).open("w") as f:
                    json.dump(data, f, indent=2)
            else:
                return False
            return True
        except Exception:
            return False

    def get_section(self, section: str) -> SectionConfig | None:
        return self._config.get(section)

    def get_param(self, section: str, param: str, default: Any = None) -> Any:
        section_config = self._config.get(section)
        if not section_config:
            return default
        keys = param.split(".")
        value = section_config.parameters
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def set_param(self, section: str, param: str, value: Any):
        if section in self._config:
            keys = param.split(".")
            target = self._config[section].parameters
            for key in keys[:-1]:
                if key not in target:
                    target[key] = {}
                target = target[key]
            target[keys[-1]] = value
            self._notify_watchers()

    def is_enabled(self, section: str) -> bool:
        return self._config.get(section, SectionConfig()).enabled

    def enable_section(self, section: str):
        if section in self._config:
            self._config[section].enabled = True
            self._notify_watchers()

    def disable_section(self, section: str):
        if section in self._config:
            self._config[section].enabled = False
            self._notify_watchers()

    def get_all(self) -> dict[str, SectionConfig]:
        return dict(self._config)

    def add_watcher(self, callback: Callable):
        self._watchers.append(callback)

    def remove_watcher(self, callback: Callable):
        if callback in self._watchers:
            self._watchers.remove(callback)

    def _notify_watchers(self):
        for watcher in self._watchers:
            try:
                watcher(self._config)
            except Exception:
                pass


config = SystemConfig()
