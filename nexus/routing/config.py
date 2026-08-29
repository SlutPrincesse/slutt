from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pydantic_settings
import yaml
from pydantic import AliasChoices, Field

from nexus.routing.types import ClassifierConfig, Registry, RoutePolicies, TaskConfig


def default_registry_path() -> Path:
    bundled = Path(__file__).resolve().parent / "models.yaml"
    if bundled.exists():
        return bundled
    try:
        from importlib import resources
        return Path(str(resources.files("nexus.routing").joinpath("models.yaml")))
    except Exception:
        return bundled


DEFAULT_REGISTRY_PATH = default_registry_path()


class Settings(pydantic_settings.BaseSettings):
    model_config = pydantic_settings.SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    nvidia_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "NEXUS_API_KEY",
            "NVIDIA_API_KEY",
            "NIM_API_KEY",
            "NVIDIA_NIM_API_KEY",
            "nvidia_api_key",
        ),
    )
    nim_base_url: str = Field(
        default="https://integrate.api.nvidia.com/v1",
        validation_alias=AliasChoices(
            "NEXUS_BASE_URL",
            "NIM_BASE_URL",
            "nim_base_url",
        ),
    )
    router_host: str = Field(
        default="127.0.0.1",
        validation_alias=AliasChoices(
            "NEXUS_ROUTER_HOST",
            "ROUTER_HOST",
            "router_host",
        ),
    )
    router_port: int = Field(
        default=8080,
        validation_alias=AliasChoices(
            "NEXUS_ROUTER_PORT",
            "ROUTER_PORT",
            "router_port",
        ),
    )
    router_config: Path = Field(
        default=DEFAULT_REGISTRY_PATH,
        validation_alias=AliasChoices(
            "NEXUS_ROUTER_CONFIG",
            "ROUTER_CONFIG",
            "router_config",
        ),
    )
    router_log_path: Path | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "NEXUS_ROUTER_LOG_PATH",
            "ROUTER_LOG_PATH",
            "router_log_path",
        ),
    )
    router_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "NEXUS_ROUTER_API_KEY",
            "ROUTER_API_KEY",
            "router_api_key",
        ),
    )
    nvcf_poll_seconds: str = Field(
        default="300",
        validation_alias=AliasChoices(
            "NEXUS_NVCF_POLL_SECONDS",
            "NVCF_POLL_SECONDS",
            "nvcf_poll_seconds",
        ),
    )
    upstream_max_retries: int = Field(
        default=3,
        validation_alias=AliasChoices(
            "NEXUS_UPSTREAM_MAX_RETRIES",
            "UPSTREAM_MAX_RETRIES",
            "upstream_max_retries",
        ),
    )
    upstream_retry_backoff_seconds: float = Field(
        default=0.5,
        validation_alias=AliasChoices(
            "NEXUS_UPSTREAM_RETRY_BACKOFF_SECONDS",
            "UPSTREAM_RETRY_BACKOFF_SECONDS",
            "upstream_retry_backoff_seconds",
        ),
    )
    enable_prometheus: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "NEXUS_ENABLE_PROMETHEUS",
            "ENABLE_PROMETHEUS",
            "enable_prometheus",
        ),
    )
    max_request_body_bytes: int = Field(
        default=10_485_760,
        validation_alias=AliasChoices(
            "NEXUS_MAX_REQUEST_BODY_BYTES",
            "MAX_REQUEST_BODY_BYTES",
            "max_request_body_bytes",
        ),
    )
    health_check_upstream: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "NEXUS_HEALTH_CHECK_UPSTREAM",
            "HEALTH_CHECK_UPSTREAM",
            "health_check_upstream",
        ),
    )
    router_cors_origins: str = Field(
        default="",
        validation_alias=AliasChoices(
            "NEXUS_ROUTER_CORS_ORIGINS",
            "ROUTER_CORS_ORIGINS",
            "router_cors_origins",
        ),
    )


def load_registry(path: Path | None = None) -> Registry:
    config_path = path or DEFAULT_REGISTRY_PATH
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    tasks = {name: TaskConfig(**cfg) for name, cfg in raw.get("tasks", {}).items()}
    aliases = {k: v for k, v in raw.get("aliases", {}).items()}
    classifier = ClassifierConfig(**raw.get("classifier", {}))
    policies = RoutePolicies(**raw.get("policies", {}))
    latency_routing = bool(raw.get("latency_routing", True))
    return Registry(
        tasks=tasks,
        aliases=aliases,
        classifier=classifier,
        policies=policies,
        latency_routing=latency_routing,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
