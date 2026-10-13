"""
Prometheus Metrics Exporter - Exposes latency, token cost, memory hits, and tool failures for scraping
"""
import threading
import time
import random
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler
import json


class MetricType(Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class Metric:
    name: str
    metric_type: MetricType
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    help_text: str = ""


class PrometheusMetricsExporter:
    def __init__(self, port: int = 9090, path: str = "/metrics"):
        self.port = port
        self.path = path
        self._metrics: Dict[str, Metric] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._summaries: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.RLock()
        self._server: Optional[HTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None
        self._running = False
        self._custom_collectors: List[Callable[[], List[Metric]]] = []
        
        # Register default metrics
        self._register_default_metrics()
    
    def _register_default_metrics(self):
        self.register_metric("agent_v9_uptime_seconds", MetricType.GAUGE, 0, help_text="Uptime in seconds")
        self.register_metric("agent_v9_active_tasks", MetricType.GAUGE, 0, help_text="Number of active tasks")
        self.register_metric("agent_v9_total_tokens", MetricType.COUNTER, 0, help_text="Total tokens used")
        self.register_metric("agent_v9_token_cost_usd", MetricType.COUNTER, 0, help_text="Total token cost in USD")
        self.register_metric("agent_v9_latency_ms", MetricType.HISTOGRAM, 0, help_text="Operation latency in ms")
        self.register_metric("agent_v9_memory_bytes", MetricType.GAUGE, 0, help_text="Memory usage in bytes")
        self.register_metric("agent_v9_tool_calls_total", MetricType.COUNTER, 0, help_text="Total tool calls")
        self.register_metric("agent_v9_tool_failures_total", MetricType.COUNTER, 0, help_text="Total tool failures")
        self.register_metric("agent_v9_errors_total", MetricType.COUNTER, 0, help_text="Total errors")
    
    def start(self):
        if self._running:
            return
        self._running = True
        
        self._server = HTTPServer(('', self.port), self._make_handler())
        self._server_thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._server_thread.start()
    
    def stop(self):
        self._running = False
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._server_thread:
            self._server_thread.join(timeout=5.0)
    
    def _make_handler(self):
        exporter = self
        
        class MetricsHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == exporter.path:
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/plain; version=0.0.4')
                    self.end_headers()
                    self.wfile.write(exporter.generate_metrics().encode())
                else:
                    self.send_response(404)
                    self.end_headers()
            
            def log_message(self, format, *args):
                pass  # Suppress default logging
        
        return MetricsHandler
    
    def register_metric(self, name: str, metric_type: MetricType, value: float = 0,
                        labels: Dict[str, str] = None, help_text: str = "") -> Metric:
        key = self._make_key(name, labels or {})
        with self._lock:
            metric = Metric(
                name=name,
                metric_type=metric_type,
                value=value,
                labels=labels or {},
                help_text=help_text
            )
            self._metrics[key] = metric
        return metric
    
    def _make_key(self, name: str, labels: Dict[str, str]) -> str:
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}" if label_str else name
    
    def increment(self, name: str, value: float = 1, labels: Dict[str, str] = None):
        key = self._make_key(name, labels or {})
        with self._lock:
            if key in self._metrics:
                self._metrics[key].value += value
            else:
                self.register_metric(name, MetricType.COUNTER, value, labels)
    
    def set_gauge(self, name: str, value: float, labels: Dict[str, str] = None):
        key = self._make_key(name, labels or {})
        with self._lock:
            if key in self._metrics:
                self._metrics[key].value = value
                self._metrics[key].timestamp = time.time()
            else:
                self.register_metric(name, MetricType.GAUGE, value, labels)
    
    def observe(self, name: str, value: float, labels: Dict[str, str] = None):
        key = self._make_key(name, labels or {})
        with self._lock:
            self._histograms[key].append(value)
            # Keep last 1000 observations
            if len(self._histograms[key]) > 1000:
                self._histograms[key] = self._histograms[key][-1000:]
            
            if key in self._metrics:
                self._metrics[key].value = value
            else:
                self.register_metric(name, MetricType.HISTOGRAM, value, labels)
    
    def record_latency(self, component: str, operation: str, duration_ms: float):
        self.observe("agent_v9_latency_ms", duration_ms, {"component": component, "operation": operation})
    
    def record_tokens(self, component: str, model: str, input_tokens: int, output_tokens: int, cost_usd: float):
        self.increment("agent_v9_total_tokens", input_tokens + output_tokens, {"component": component, "model": model})
        self.increment("agent_v9_token_cost_usd", cost_usd, {"component": component, "model": model})
    
    def record_tool_call(self, tool: str, success: bool, duration_ms: float):
        self.increment("agent_v9_tool_calls_total", 1, {"tool": tool, "success": str(success).lower()})
        if not success:
            self.increment("agent_v9_tool_failures_total", 1, {"tool": tool})
        self.record_latency("tools", tool, duration_ms)
    
    def record_error(self, component: str, error_type: str):
        self.increment("agent_v9_errors_total", 1, {"component": component, "error_type": error_type})
    
    def add_custom_collector(self, collector: Callable[[], List[Metric]]):
        self._custom_collectors.append(collector)
    
    def generate_metrics(self) -> str:
        lines = []
        with self._lock:
            # Add custom metrics
            for collector in self._custom_collectors:
                try:
                    for metric in collector():
                        self._update_metric(metric)
                except Exception:
                    pass
            
            # Update uptime
            self._metrics["agent_v9_uptime_seconds"].value = time.time() - self._start_time if hasattr(self, '_start_time') else 0
            
            # Generate Prometheus format
            for key, metric in self._metrics.items():
                lines.append(f"# HELP {metric.name} {metric.help_text}")
                lines.append(f"# TYPE {metric.name} {metric.metric_type.value}")
                
                if metric.metric_type == MetricType.HISTOGRAM:
                    values = self._histograms.get(key, [])
                    if values:
                        count = len(values)
                        sum_val = sum(values)
                        lines.append(f'{metric.name}_count {count}')
                        lines.append(f'{metric.name}_sum {sum_val}')
                        
                        # Quantiles
                        sorted_vals = sorted(values)
                        for q in [0.5, 0.9, 0.95, 0.99]:
                            idx = int(len(sorted_vals) * q)
                            lines.append(f'{metric.name}{{quantile="{q}"}} {sorted_vals[idx] if idx < len(sorted_vals) else sorted_vals[-1]}')
                elif metric.metric_type == MetricType.SUMMARY:
                    values = self._summaries.get(key, [])
                    if values:
                        count = len(values)
                        sum_val = sum(values)
                        lines.append(f'{metric.name}_count {count}')
                        lines.append(f'{metric.name}_sum {sum_val}')
                else:
                    label_str = ""
                    if metric.labels:
                        label_str = "{" + ",".join(f'{k}="{v}"' for k, v in metric.labels.items()) + "}"
                    lines.append(f"{metric.name}{label_str} {metric.value}")
        
        return "\n".join(lines) + "\n"
    
    def _update_metric(self, metric: Metric):
        key = self._make_key(metric.name, metric.labels)
        if key in self._metrics:
            self._metrics[key].value = metric.value
            self._metrics[key].timestamp = metric.timestamp
        else:
            self._metrics[key] = metric
    
    def get_metric(self, name: str, labels: Dict[str, str] = None) -> Optional[Metric]:
        key = self._make_key(name, labels or {})
        with self._lock:
            return self._metrics.get(key)
    
    def get_all_metrics(self) -> Dict[str, Metric]:
        with self._lock:
            return dict(self._metrics)
    
    def reset(self):
        with self._lock:
            self._metrics.clear()
            self._histograms.clear()
            self._summaries.clear()
            self._register_default_metrics()


_metrics_exporter: Optional[PrometheusMetricsExporter] = None

def get_metrics_exporter() -> PrometheusMetricsExporter:
    global _metrics_exporter
    if _metrics_exporter is None:
        from ..core.config import config
        port = config.get_param("audit", "metrics_port", 9090)
        _metrics_exporter = PrometheusMetricsExporter(port=port)
        _metrics_exporter.start()
    return _metrics_exporter