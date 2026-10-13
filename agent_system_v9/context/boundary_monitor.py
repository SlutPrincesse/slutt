from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class BoundaryAlertType(Enum):
    WARNING = "warning"
    CRITICAL = "critical"
    TOKEN_EXCEEDED = "token_exceeded"
    HEAD_EXHAUSTED = "head_exhausted"
    CONTEXT_FRAGMENTATION = "context_fragmentation"


@dataclass
class BoundaryAlert:
    id: str
    alert_type: BoundaryAlertType
    message: str
    current_value: float
    threshold: float
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


class BoundaryMonitor:
    def __init__(
        self,
        max_context_tokens: int = 128000,
        warning_threshold: float = 0.7,
        critical_threshold: float = 0.9,
        max_heads: int = 8,
    ):
        self.max_context_tokens = max_context_tokens
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.max_heads = max_heads

        self.current_tokens = 0
        self.active_heads = 0
        self.alerts: list[BoundaryAlert] = []
        self._alert_handlers: list[Callable[[BoundaryAlert], Any]] = []
        self._monitoring = False

    def add_alert_handler(self, handler: Callable[[BoundaryAlert], Any]):
        self._alert_handlers.append(handler)

    def update_tokens(self, tokens: int):
        old_tokens = self.current_tokens
        self.current_tokens = tokens
        self._check_token_boundary(old_tokens)

    def update_heads(self, count: int):
        old_heads = self.active_heads
        self.active_heads = count
        self._check_head_boundary(old_heads)

    def _check_token_boundary(self, old_tokens: int):
        utilization = self.current_tokens / self.max_context_tokens

        if utilization >= self.critical_threshold and old_tokens / self.max_context_tokens < self.critical_threshold:
            self._emit_alert(BoundaryAlert(
                id=f"critical_{datetime.utcnow().timestamp()}",
                alert_type=BoundaryAlertType.CRITICAL,
                message=f"Context utilization critical: {utilization:.1%}",
                current_value=utilization,
                threshold=self.critical_threshold,
                metadata={"tokens": self.current_tokens, "max": self.max_context_tokens},
            ))
        elif utilization >= self.warning_threshold and old_tokens / self.max_context_tokens < self.warning_threshold:
            self._emit_alert(BoundaryAlert(
                id=f"warning_{datetime.utcnow().timestamp()}",
                alert_type=BoundaryAlertType.WARNING,
                message=f"Context utilization warning: {utilization:.1%}",
                current_value=utilization,
                threshold=self.warning_threshold,
                metadata={"tokens": self.current_tokens, "max": self.max_context_tokens},
            ))
        elif utilization > 1.0:
            self._emit_alert(BoundaryAlert(
                id=f"exceeded_{datetime.utcnow().timestamp()}",
                alert_type=BoundaryAlertType.TOKEN_EXCEEDED,
                message=f"Context tokens exceeded: {self.current_tokens}/{self.max_context_tokens}",
                current_value=utilization,
                threshold=1.0,
                metadata={"tokens": self.current_tokens, "max": self.max_context_tokens},
            ))

    def _check_head_boundary(self, old_heads: int):
        if self.active_heads >= self.max_heads and old_heads < self.max_heads:
            self._emit_alert(BoundaryAlert(
                id=f"head_exhausted_{datetime.utcnow().timestamp()}",
                alert_type=BoundaryAlertType.HEAD_EXHAUSTED,
                message=f"Attention heads exhausted: {self.active_heads}/{self.max_heads}",
                current_value=self.active_heads,
                threshold=self.max_heads,
            ))

    def _emit_alert(self, alert: BoundaryAlert):
        self.alerts.append(alert)
        for handler in self._alert_handlers:
            try:
                handler(alert)
            except Exception:
                pass

    def get_recent_alerts(self, limit: int = 10) -> list[BoundaryAlert]:
        return self.alerts[-limit:]

    def get_status(self) -> dict[str, Any]:
        return {
            "current_tokens": self.current_tokens,
            "max_tokens": self.max_context_tokens,
            "utilization": self.current_tokens / self.max_context_tokens,
            "active_heads": self.active_heads,
            "max_heads": self.max_heads,
            "head_utilization": self.active_heads / self.max_heads,
            "alerts_count": len(self.alerts),
            "recent_alerts": [a.message for a in self.alerts[-5:]],
        }

    def clear_alerts(self):
        self.alerts.clear()
