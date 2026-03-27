"""Tests for attractor.config module."""
import pytest
from attractor.config import substitute_env_vars


def test_substitute_env_vars(monkeypatch):
    monkeypatch.setenv("MY_KEY", "secret123")
    result = substitute_env_vars({"api_key": "${MY_KEY}", "name": "test"})
    assert result == {"api_key": "secret123", "name": "test"}


def test_substitute_env_vars_missing_raises(monkeypatch):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    with pytest.raises(ValueError, match="MISSING_VAR"):
        substitute_env_vars({"key": "${MISSING_VAR}"})


def test_substitute_env_vars_nested(monkeypatch):
    monkeypatch.setenv("NESTED_KEY", "val")
    result = substitute_env_vars({"outer": {"inner": "${NESTED_KEY}"}})
    assert result == {"outer": {"inner": "val"}}


from attractor.config import PipelineConfig, load_config


def test_load_config_from_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
llm:
  providers:
    openrouter:
      base_url: https://openrouter.ai/api/v1
      api_key: ${OPENROUTER_API_KEY}
  models:
    planner: openrouter/anthropic/claude-sonnet-4-5
    implementer: openrouter/anthropic/claude-sonnet-4-5
    validator: openrouter/anthropic/claude-sonnet-4-5
    diagnoser: openrouter/openai/o3
    reviewer: openrouter/anthropic/claude-sonnet-4-5
pipeline:
  max_cycles: 10
  loop_detection_window: 10
  tool_output_truncation: 8000
  context_char_limit: 400000
  context_truncation_strategy: middle
workspace:
  base_path: /workspace/runs
  target_repo: /workspace/target
logging:
  level: INFO
  structured: true
""")
    config = load_config(str(config_file))
    assert isinstance(config, PipelineConfig)
    assert config.llm.providers["openrouter"].api_key == "test-key"
    assert config.pipeline.max_cycles == 10
    assert config.llm.models.planner == "openrouter/anthropic/claude-sonnet-4-5"


def test_load_config_validates_provider_in_model():
    """Model string must reference a configured provider."""
    from attractor.config import PipelineConfig, LLMConfig, PipelineSettings, WorkspaceConfig, LoggingConfig, ProviderConfig, ModelConfig
    with pytest.raises(ValueError):
        PipelineConfig(
            llm=LLMConfig(
                providers={"openrouter": ProviderConfig(base_url="https://x.com/v1", api_key="k")},
                models=ModelConfig(
                    planner="unknown_provider/model",
                    implementer="openrouter/model",
                    validator="openrouter/model",
                    diagnoser="openrouter/model",
                    reviewer="openrouter/model",
                ),
            ),
            pipeline=PipelineSettings(),
            workspace=WorkspaceConfig(base_path="/tmp", target_repo="/tmp"),
            logging=LoggingConfig(),
        )
