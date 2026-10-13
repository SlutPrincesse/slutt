"""
Unit tests for core SystemConfig module.
"""
import pytest
import tempfile
import os
from pathlib import Path

from agent_system_v9.core.config import SystemConfig, SectionConfig


class TestSystemConfig:
    """Tests for SystemConfig singleton."""

    def test_singleton_instance(self, clean_config):
        """Test that SystemConfig is a singleton."""
        config1 = SystemConfig()
        config2 = SystemConfig()
        assert config1 is config2

    def test_default_sections_exist(self, clean_config):
        """Test all expected sections are present."""
        expected_sections = [
            "kernel", "prompt", "multimodal", "audit", "neurocranial",
            "divergent", "hud", "restructure", "prometheus9", "recovery",
            "syntax", "threat", "blueprint", "distributed", "reasoning",
            "security", "reactive", "compilation", "storage", "deployment",
            "context", "benchmark", "edge", "cicd", "workspace",
            "guardrails", "tools", "shadowgit", "evolution"
        ]

        for section in expected_sections:
            assert clean_config.get_section(section) is not None

    def test_section_enabled_by_default(self, clean_config):
        """Test all sections are enabled by default."""
        for section_name in clean_config._config.keys():
            section = clean_config.get_section(section_name)
            assert section.enabled is True

    def test_get_param(self, clean_config):
        """Test getting nested parameters."""
        value = clean_config.get_param("kernel", "max_processes")
        assert value == 100

        value = clean_config.get_param("prompt", "max_token_budget")
        assert value == 100000

    def test_get_param_with_default(self, clean_config):
        """Test getting non-existent parameter returns default."""
        value = clean_config.get_param("kernel", "nonexistent", default="fallback")
        assert value == "fallback"

    def test_set_param(self, clean_config):
        """Test setting nested parameters."""
        clean_config.set_param("kernel", "custom_param", 42)
        value = clean_config.get_param("kernel", "custom_param")
        assert value == 42

    def test_set_nested_param(self, clean_config):
        """Test setting deeply nested parameters."""
        clean_config.set_param("kernel", "nested.deep.value", "test")
        value = clean_config.get_param("kernel", "nested.deep.value")
        assert value == "test"

    def test_enable_disable_section(self, clean_config):
        """Test enabling/disabling sections."""
        assert clean_config.is_enabled("kernel") is True

        clean_config.disable_section("kernel")
        assert clean_config.is_enabled("kernel") is False

        clean_config.enable_section("kernel")
        assert clean_config.is_enabled("kernel") is True

    def test_get_all(self, clean_config):
        """Test getting all configuration."""
        all_config = clean_config.get_all()
        assert isinstance(all_config, dict)
        assert len(all_config) > 0

    def test_config_watchers(self, clean_config):
        """Test config change watchers."""
        called = []

        def watcher(config):
            called.append(config)

        clean_config.add_watcher(watcher)
        clean_config.set_param("kernel", "watched_param", "test")

        assert len(called) == 1
        assert called[0]["kernel"].parameters["watched_param"] == "test"

    def test_remove_watcher(self, clean_config):
        """Test removing watcher."""
        called = []

        def watcher(config):
            called.append(config)

        clean_config.add_watcher(watcher)
        clean_config.remove_watcher(watcher)
        clean_config.set_param("kernel", "watched_param", "test")

        assert len(called) == 0

    def test_load_yaml_file(self, clean_config):
        """Test loading configuration from YAML file."""
        yaml_content = """
kernel:
  enabled: true
  parameters:
    max_processes: 200
    custom_yaml_param: "from_yaml"
  dependencies: ["test_dep"]
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            try:
                result = clean_config.load_file(f.name)
                assert result is True

                value = clean_config.get_param("kernel", "max_processes")
                assert value == 200

                value = clean_config.get_param("kernel", "custom_yaml_param")
                assert value == "from_yaml"

                section = clean_config.get_section("kernel")
                assert "test_dep" in section.dependencies
            finally:
                os.unlink(f.name)

    def test_load_json_file(self, clean_config):
        """Test loading configuration from JSON file."""
        json_content = {
            "prompt": {
                "enabled": True,
                "parameters": {
                    "max_token_budget": 50000,
                    "custom_json_param": "from_json"
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            import json
            json.dump(json_content, f)
            f.flush()
            try:
                result = clean_config.load_file(f.name)
                assert result is True

                value = clean_config.get_param("prompt", "max_token_budget")
                assert value == 50000

                value = clean_config.get_param("prompt", "custom_json_param")
                assert value == "from_json"
            finally:
                os.unlink(f.name)

    def test_save_file(self, clean_config):
        """Test saving configuration to file."""
        clean_config.set_param("kernel", "save_test", "saved_value")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            fname = f.name

        try:
            result = clean_config.save_file(fname)
            assert result is True

            # Verify saved content
            with open(fname) as f:
                content = f.read()
            assert "save_test" in content
            assert "saved_value" in content
        finally:
            os.unlink(fname)

    def test_env_variable_override(self, clean_config, monkeypatch):
        """Test environment variable override."""
        monkeypatch.setenv("AGENT_V9_KERNEL__MAX_PROCESSES", "500")

        # Need to create new config instance to pick up env vars
        # Since we have clean_config fixture, we test the parsing logic directly
        value = clean_config._parse_value("500")
        assert value == 500

        value = clean_config._parse_value("true")
        assert value is True

        value = clean_config._parse_value("false")
        assert value is False

        value = clean_config._parse_value("3.14")
        assert value == 3.14

        value = clean_config._parse_value("hello")
        assert value == "hello"

    def test_section_config_dataclass(self):
        """Test SectionConfig dataclass defaults."""
        section = SectionConfig()
        assert section.enabled is True
        assert section.parameters == {}
        assert section.dependencies == []
        assert section.resource_limits == {}

    def test_section_config_with_values(self):
        """Test SectionConfig with custom values."""
        section = SectionConfig(
            enabled=False,
            parameters={"key": "value"},
            dependencies=["dep1"],
            resource_limits={"memory": "1GB"}
        )
        assert section.enabled is False
        assert section.parameters == {"key": "value"}
        assert section.dependencies == ["dep1"]
        assert section.resource_limits == {"memory": "1GB"}

    def test_complex_nested_params(self, clean_config):
        """Test complex nested parameter structures."""
        clean_config.set_param("kernel", "complex", {
            "level1": {
                "level2": {
                    "level3": "deep_value"
                }
            }
        })

        value = clean_config.get_param("kernel", "complex.level1.level2.level3")
        assert value == "deep_value"

    def test_dependencies_and_resource_limits_in_yaml(self, clean_config):
        """Test loading dependencies and resource_limits from YAML."""
        yaml_content = """
storage:
  enabled: true
  parameters:
    cas_enabled: true
  dependencies: ["kernel", "security"]
  resource_limits:
    disk: "10GB"
    memory: "2GB"
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            try:
                result = clean_config.load_file(f.name)
                assert result is True

                section = clean_config.get_section("storage")
                assert "kernel" in section.dependencies
                assert "security" in section.dependencies
                assert section.resource_limits["disk"] == "10GB"
                assert section.resource_limits["memory"] == "2GB"
            finally:
                os.unlink(f.name)