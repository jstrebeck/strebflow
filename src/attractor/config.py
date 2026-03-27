"""Configuration loading and validation."""
from __future__ import annotations
import os
import re
from typing import Any
import yaml
from pydantic import BaseModel, Field

ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


def substitute_env_vars(data: Any) -> Any:
    """Recursively substitute ${VAR} patterns with environment variable values."""
    if isinstance(data, str):
        def _replace(match: re.Match) -> str:
            var_name = match.group(1)
            value = os.environ.get(var_name)
            if value is None:
                raise ValueError(f"Environment variable '{var_name}' is not set but is referenced in config")
            return value
        return ENV_VAR_PATTERN.sub(_replace, data)
    if isinstance(data, dict):
        return {k: substitute_env_vars(v) for k, v in data.items()}
    if isinstance(data, list):
        return [substitute_env_vars(item) for item in data]
    return data


class ProviderConfig(BaseModel):
    base_url: str
    api_key: str


class ModelConfig(BaseModel):
    planner: str
    implementer: str
    validator: str
    diagnoser: str
    reviewer: str


class LLMConfig(BaseModel):
    providers: dict[str, ProviderConfig]
    models: ModelConfig


class PipelineSettings(BaseModel):
    max_cycles: int = 10
    loop_detection_window: int = 10
    tool_output_truncation: int = 8000
    context_char_limit: int = 400_000
    context_truncation_strategy: str = "middle"
    test_command: str | None = None
    test_timeout: int = 120


class WorkspaceConfig(BaseModel):
    base_path: str
    target_repo: str


class LoggingConfig(BaseModel):
    level: str = "INFO"
    structured: bool = True
    # events: defined for forward compatibility — event filtering not yet implemented.
    # All events are currently emitted regardless of this list.
    events: list[str] = Field(default_factory=lambda: [
        "CYCLE_START", "TOOL_CALL_START", "TOOL_CALL_END",
        "NODE_ENTER", "NODE_EXIT", "CONVERGENCE", "LOOP_DETECTED",
    ])


class PipelineConfig(BaseModel):
    llm: LLMConfig
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)
    workspace: WorkspaceConfig
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    def model_post_init(self, __context: Any) -> None:
        """Validate that all model strings reference configured providers."""
        provider_names = set(self.llm.providers.keys())
        for field_name in ModelConfig.model_fields:
            model_str = getattr(self.llm.models, field_name)
            provider = model_str.split("/")[0]
            if provider not in provider_names:
                raise ValueError(
                    f"Model '{field_name}' references provider '{provider}' "
                    f"which is not in configured providers: {provider_names}"
                )


def load_config(path: str) -> PipelineConfig:
    """Load and validate pipeline config from a YAML file."""
    with open(path) as f:
        raw = yaml.safe_load(f)
    resolved = substitute_env_vars(raw)
    return PipelineConfig(**resolved)
