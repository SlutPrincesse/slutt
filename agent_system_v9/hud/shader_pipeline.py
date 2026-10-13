"""
Reactive Ambient Shader Pipeline - Updates visual background themes based on CPU load, latency, and status
"""
import threading
import time
import math
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum


class ShaderTheme(Enum):
    IDLE = "idle"
    ACTIVE = "active"
    HIGH_LOAD = "high_load"
    ERROR = "error"
    WARNING = "warning"
    SUCCESS = "success"


@dataclass
class ShaderConfig:
    theme: ShaderTheme = ShaderTheme.IDLE
    color_primary: str = "#00ff88"
    color_secondary: str = "#0088ff"
    color_accent: str = "#ff8800"
    intensity: float = 0.5
    animation_speed: float = 1.0
    particle_count: int = 100
    blur_radius: float = 0.0
    pulse_enabled: bool = True


class AmbientShaderPipeline:
    def __init__(self, update_interval: float = 0.1):
        self.update_interval = update_interval
        self._config = ShaderConfig()
        self._lock = threading.RLock()
        self._running = False
        self._update_thread: Optional[threading.Thread] = None
        self._metrics: Dict[str, float] = {}
        self._theme_rules: Dict[ShaderTheme, Callable[[Dict[str, float]], bool]] = {}
        self._callbacks: Dict[str, List[Callable]] = {
            "theme_changed": [],
            "config_updated": [],
            "metrics_updated": []
        }
        
        self._register_default_rules()
    
    def _register_default_rules(self):
        self._theme_rules[ShaderTheme.ERROR] = lambda m: m.get("error_rate", 0) > 0.1
        self._theme_rules[ShaderTheme.HIGH_LOAD] = lambda m: m.get("cpu_percent", 0) > 80
        self._theme_rules[ShaderTheme.WARNING] = lambda m: m.get("cpu_percent", 0) > 60 or m.get("memory_percent", 0) > 80
        self._theme_rules[ShaderTheme.SUCCESS] = lambda m: m.get("success_rate", 0) > 0.9 and m.get("cpu_percent", 0) < 30
        self._theme_rules[ShaderTheme.ACTIVE] = lambda m: m.get("active_tasks", 0) > 0
        self._theme_rules[ShaderTheme.IDLE] = lambda m: m.get("active_tasks", 0) == 0
    
    def start(self):
        if self._running:
            return
        self._running = True
        self._update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self._update_thread.start()
    
    def stop(self):
        self._running = False
        if self._update_thread:
            self._update_thread.join(timeout=2.0)
    
    def update_metrics(self, metrics: Dict[str, float]):
        with self._lock:
            self._metrics.update(metrics)
        
        self._notify_metrics_updated(metrics)
        self._evaluate_theme()
    
    def _update_loop(self):
        while self._running:
            time.sleep(self.update_interval)
            self._evaluate_theme()
            self._animate()
    
    def _evaluate_theme(self):
        new_theme = self._config.theme
        
        # Check rules in priority order
        priority = [
            ShaderTheme.ERROR,
            ShaderTheme.HIGH_LOAD,
            ShaderTheme.WARNING,
            ShaderTheme.SUCCESS,
            ShaderTheme.ACTIVE,
            ShaderTheme.IDLE
        ]
        
        with self._lock:
            metrics = self._metrics.copy()
        
        for theme in priority:
            if theme in self._theme_rules:
                try:
                    if self._theme_rules[theme](metrics):
                        new_theme = theme
                        break
                except Exception:
                    pass
        
        if new_theme != self._config.theme:
            self.set_theme(new_theme)
    
    def _animate(self):
        with self._lock:
            if self._config.pulse_enabled:
                # Animate intensity
                t = time.time() * self._config.animation_speed
                pulse = (math.sin(t) + 1) / 2  # 0 to 1
                self._config.intensity = 0.3 + 0.4 * pulse
    
    def set_theme(self, theme: ShaderTheme):
        with self._lock:
            old_theme = self._config.theme
            self._config.theme = theme
            
            # Apply theme-specific config
            theme_configs = {
                ShaderTheme.IDLE: {"color_primary": "#004422", "intensity": 0.2, "animation_speed": 0.5},
                ShaderTheme.ACTIVE: {"color_primary": "#00ff88", "intensity": 0.6, "animation_speed": 1.0},
                ShaderTheme.HIGH_LOAD: {"color_primary": "#ff4400", "intensity": 0.9, "animation_speed": 2.0},
                ShaderTheme.ERROR: {"color_primary": "#ff0000", "intensity": 1.0, "animation_speed": 3.0},
                ShaderTheme.WARNING: {"color_primary": "#ffaa00", "intensity": 0.7, "animation_speed": 1.5},
                ShaderTheme.SUCCESS: {"color_primary": "#00ff44", "intensity": 0.5, "animation_speed": 0.8},
            }
            
            if theme in theme_configs:
                for key, value in theme_configs[theme].items():
                    setattr(self._config, key, value)
        
        self._notify_theme_changed(old_theme, theme)
        self._notify_config_updated()
    
    def set_config(self, **kwargs):
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self._config, key):
                    setattr(self._config, key, value)
        self._notify_config_updated()
    
    def get_config(self) -> ShaderConfig:
        with self._lock:
            return ShaderConfig(
                theme=self._config.theme,
                color_primary=self._config.color_primary,
                color_secondary=self._config.color_secondary,
                color_accent=self._config.color_accent,
                intensity=self._config.intensity,
                animation_speed=self._config.animation_speed,
                particle_count=self._config.particle_count,
                blur_radius=self._config.blur_radius,
                pulse_enabled=self._config.pulse_enabled
            )
    
    def get_shader_uniforms(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "u_time": time.time(),
                "u_intensity": self._config.intensity,
                "u_color_primary": self._hex_to_rgb(self._config.color_primary),
                "u_color_secondary": self._hex_to_rgb(self._config.color_secondary),
                "u_color_accent": self._hex_to_rgb(self._config.color_accent),
                "u_particle_count": self._config.particle_count,
                "u_blur_radius": self._config.blur_radius,
                "u_theme": self._config.theme.value
            }
    
    def _hex_to_rgb(self, hex_color: str) -> List[float]:
        hex_color = hex_color.lstrip('#')
        return [int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4)]
    
    def register_callback(self, event: str, callback: Callable):
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    def _notify_theme_changed(self, old: ShaderTheme, new: ShaderTheme):
        for cb in self._callbacks["theme_changed"]:
            try:
                cb(old, new)
            except Exception:
                pass
    
    def _notify_config_updated(self):
        for cb in self._callbacks["config_updated"]:
            try:
                cb(self.get_config())
            except Exception:
                pass
    
    def _notify_metrics_updated(self, metrics: Dict):
        for cb in self._callbacks["metrics_updated"]:
            try:
                cb(metrics)
            except Exception:
                pass
    
    def add_theme_rule(self, theme: ShaderTheme, rule: Callable[[Dict[str, float]], bool]):
        self._theme_rules[theme] = rule


_shader_pipeline: Optional[AmbientShaderPipeline] = None

def get_shader_pipeline() -> AmbientShaderPipeline:
    global _shader_pipeline
    if _shader_pipeline is None:
        from ..core.config import config
        interval = config.get_param("hud", "shader_update_interval", 100) / 1000.0
        _shader_pipeline = AmbientShaderPipeline(update_interval=interval)
        _shader_pipeline.start()
    return _shader_pipeline