# Attractor Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a LangGraph-based agentic coding pipeline that takes a spec, implements it, validates against scenarios, and converges autonomously.

**Architecture:** A LangGraph StateGraph with 8 nodes (spec_loader, planner, implementer, test_runner, scenario_validator, diagnoser, reviewer, done) connected by conditional edges. The implementer node contains its own inner agentic loop with tool use. A multi-provider LLM client routes to OpenRouter, vast.ai, or any OpenAI-compatible endpoint.

**Tech Stack:** Python 3.12, LangGraph, httpx, Pydantic, structlog, PyYAML

**Spec:** `docs/superpowers/specs/2026-03-26-attractor-pipeline-design.md`

---

## File Map

| File | Responsibility |
|------|---------------|
| `pyproject.toml` | Project metadata, dependencies, build config |
| `src/attractor/__init__.py` | Package init, version |
| `src/attractor/__main__.py` | CLI entrypoint (argparse: run, resume, status) |
| `src/attractor/config.py` | Pydantic config models, YAML loading, env var substitution |
| `src/attractor/logging.py` | structlog setup, event types, file + stdout output |
| `src/attractor/state.py` | PipelineState TypedDict, run state serialization helpers |
| `src/attractor/workspace.py` | Workspace class: copy, git init, diff, checkpoint, run_isolated |
| `src/attractor/llm_client.py` | LLMClient: multi-provider routing, complete(), complete_structured() |
| `src/attractor/graph.py` | LangGraph StateGraph definition, edge routing |
| `src/attractor/tools/__init__.py` | Tool registry, schema generation, dispatcher |
| `src/attractor/tools/file_tools.py` | read_file, write_file, edit_file |
| `src/attractor/tools/shell_tools.py` | run_shell |
| `src/attractor/tools/search_tools.py` | list_files, grep |
| `src/attractor/nodes/__init__.py` | Node registry |
| `src/attractor/nodes/spec_loader.py` | Read spec + scenarios from disk |
| `src/attractor/nodes/planner.py` | LLM call to produce implementation plan + test_command |
| `src/attractor/nodes/implementer.py` | Inner agentic loop with tool use, loop detection, context mgmt |
| `src/attractor/nodes/test_runner.py` | Run test suite in subprocess |
| `src/attractor/nodes/scenario_validator.py` | LLM structured evaluation of scenarios |
| `src/attractor/nodes/diagnoser.py` | LLM diagnosis + steering prompt generation |
| `src/attractor/nodes/reviewer.py` | LLM code review (post-convergence) |
| `src/attractor/nodes/done.py` | Write summary, finalize run_state.json |
| `tests/__init__.py` | Test package |
| `tests/test_config.py` | Config loading and validation tests |
| `tests/test_workspace.py` | Workspace operations tests |
| `tests/test_tools.py` | All 6 coding tools tests |
| `tests/test_state.py` | State serialization tests |
| `tests/test_llm_client.py` | LLM client provider routing tests (mocked HTTP) |
| `tests/test_nodes.py` | Node function tests (mocked LLM) |
| `tests/test_graph.py` | Graph wiring and edge condition tests |
| `pipeline_config.yaml` | Default configuration |
| `Dockerfile` | Container image |
| `docker-compose.yml` | Local development compose |
| `k8s/job-template.yaml` | Kubernetes Job template |
| `k8s/configmap.yaml` | Pipeline config as ConfigMap |
| `k8s/secret-template.yaml` | API key Secret placeholder |
| `k8s/pvc.yaml` | Workspace PVC |
| `k8s/rbac.yaml` | RBAC placeholder |

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/attractor/__init__.py`
- Create: `tests/__init__.py`
- Create: `src/attractor/nodes/__init__.py`
- Create: `src/attractor/tools/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "attractor"
version = "0.1.0"
description = "LangGraph-based agentic coding pipeline"
requires-python = ">=3.12"
dependencies = [
    "langgraph>=0.2",
    "langchain-core>=0.3",
    "httpx>=0.27",
    "pyyaml>=6.0",
    "pydantic>=2.0",
    "structlog>=24.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "respx>=0.22",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create package init files**

`src/attractor/__init__.py`:
```python
"""Attractor — LangGraph-based agentic coding pipeline."""

__version__ = "0.1.0"
```

`src/attractor/nodes/__init__.py`:
```python
"""Pipeline graph nodes."""
```

`src/attractor/tools/__init__.py`:
```python
"""Coding tools for the implementer agent."""
```

`tests/__init__.py`:
```python
```

- [ ] **Step 3: Install the project in dev mode**

Run: `pip install -e ".[dev]"`
Expected: Successful install with all dependencies

- [ ] **Step 4: Verify pytest runs**

Run: `python -m pytest --co`
Expected: "no tests ran" (no test files yet), exit 0 or 5 (no tests collected)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/ tests/
git commit -m "feat: project scaffolding with dependencies"
```

---

### Task 2: Configuration Module

**Files:**
- Create: `src/attractor/config.py`
- Create: `tests/test_config.py`
- Create: `pipeline_config.yaml`

- [ ] **Step 1: Write failing test for env var substitution**

`tests/test_config.py`:
```python
from attractor.config import substitute_env_vars


def test_substitute_env_vars(monkeypatch):
    monkeypatch.setenv("MY_KEY", "secret123")
    result = substitute_env_vars({"api_key": "${MY_KEY}", "name": "test"})
    assert result == {"api_key": "secret123", "name": "test"}


def test_substitute_env_vars_missing_raises(monkeypatch):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    import pytest
    with pytest.raises(ValueError, match="MISSING_VAR"):
        substitute_env_vars({"key": "${MISSING_VAR}"})


def test_substitute_env_vars_nested(monkeypatch):
    monkeypatch.setenv("NESTED_KEY", "val")
    result = substitute_env_vars({"outer": {"inner": "${NESTED_KEY}"}})
    assert result == {"outer": {"inner": "val"}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL (ImportError — config module doesn't exist yet)

- [ ] **Step 3: Write the substitute_env_vars function**

`src/attractor/config.py`:
```python
"""Configuration loading and validation."""

from __future__ import annotations

import os
import re
from pathlib import Path
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
                raise ValueError(
                    f"Environment variable '{var_name}' is not set "
                    f"but is referenced in config"
                )
            return value
        return ENV_VAR_PATTERN.sub(_replace, data)
    if isinstance(data, dict):
        return {k: substitute_env_vars(v) for k, v in data.items()}
    if isinstance(data, list):
        return [substitute_env_vars(item) for item in data]
    return data
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Write failing test for Pydantic config models**

Append to `tests/test_config.py`:
```python
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
    import pytest
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
```

- [ ] **Step 6: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py::test_load_config_from_yaml -v`
Expected: FAIL (PipelineConfig not yet defined)

- [ ] **Step 7: Write Pydantic config models and load_config**

Append to `src/attractor/config.py`:
```python
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


class WorkspaceConfig(BaseModel):
    base_path: str
    target_repo: str


class LoggingConfig(BaseModel):
    level: str = "INFO"
    structured: bool = True
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
```

- [ ] **Step 8: Run all config tests**

Run: `python -m pytest tests/test_config.py -v`
Expected: 5 PASSED

- [ ] **Step 9: Create default pipeline_config.yaml**

`pipeline_config.yaml`:
```yaml
llm:
  providers:
    openrouter:
      base_url: https://openrouter.ai/api/v1
      api_key: ${OPENROUTER_API_KEY}
    # vastai:
    #   base_url: ${VASTAI_BASE_URL}
    #   api_key: ${VASTAI_API_KEY}
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
  base_path: ./runs
  target_repo: ./target

logging:
  level: INFO
  structured: true
```

- [ ] **Step 10: Commit**

```bash
git add src/attractor/config.py tests/test_config.py pipeline_config.yaml
git commit -m "feat: config module with Pydantic validation and env var substitution"
```

---

### Task 3: Structured Logging

**Files:**
- Create: `src/attractor/logging.py`

- [ ] **Step 1: Write the logging module**

`src/attractor/logging.py`:
```python
"""Structured logging setup using structlog."""

from __future__ import annotations

import sys
from pathlib import Path

import structlog


def setup_logging(level: str = "INFO", structured: bool = True, log_file: Path | None = None) -> None:
    """Configure structlog for the pipeline."""
    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]
    if structured:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str, **initial_context: str) -> structlog.stdlib.BoundLogger:
    """Get a bound logger with initial context."""
    return structlog.get_logger(name, **initial_context)
```

- [ ] **Step 2: Verify import works**

Run: `python -c "from attractor.logging import setup_logging, get_logger; setup_logging(); log = get_logger('test'); log.info('hello', event_type='NODE_ENTER')"`
Expected: JSON log line printed to stdout

- [ ] **Step 3: Commit**

```bash
git add src/attractor/logging.py
git commit -m "feat: structured logging module with structlog"
```

---

### Task 4: State Module

**Files:**
- Create: `src/attractor/state.py`
- Create: `tests/test_state.py`

- [ ] **Step 1: Write failing test for state serialization**

`tests/test_state.py`:
```python
import json
from pathlib import Path

from attractor.state import PipelineState, save_run_state, load_run_state


def test_save_and_load_run_state(tmp_path):
    state: PipelineState = {
        "spec": "# My Spec",
        "scenarios": "# Scenarios",
        "workspace_path": "/tmp/run_001",
        "implementation_plan": "",
        "cycle": 0,
        "max_cycles": 10,
        "steering_prompt": "",
        "test_output": "",
        "test_exit_code": -1,
        "test_command": "",
        "validation_result": {},
        "tool_call_history": [],
        "diff_history": [],
        "review_report": "",
        "summary": "",
    }
    save_run_state(state, tmp_path / "run_state.json")
    loaded = load_run_state(tmp_path / "run_state.json")
    assert loaded["cycle"] == 0
    assert loaded["spec"] == "# My Spec"


def test_save_run_state_excludes_large_fields(tmp_path):
    """LLM message histories should not be in run_state.json.
    tool_call_history IS included (it's compact)."""
    state: PipelineState = {
        "spec": "x" * 100_000,
        "scenarios": "y" * 100_000,
        "workspace_path": "/tmp/run_001",
        "implementation_plan": "z" * 100_000,
        "cycle": 3,
        "max_cycles": 10,
        "steering_prompt": "",
        "test_output": "w" * 100_000,
        "test_exit_code": 0,
        "test_command": "pytest",
        "validation_result": {"passed": False},
        "tool_call_history": [{"name": "read_file", "args_hash": "abc", "cycle": 0}],
        "diff_history": ["diff1", "diff2"],
        "review_report": "",
        "summary": "",
    }
    save_run_state(state, tmp_path / "run_state.json")
    raw = json.loads((tmp_path / "run_state.json").read_text())
    # tool_call_history is included
    assert len(raw["tool_call_history"]) == 1
    # large text fields are truncated in the saved state
    assert raw["cycle"] == 3
    assert "status" in raw  # save_run_state adds a status field
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_state.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Write the state module**

`src/attractor/state.py`:
```python
"""Pipeline state schema and serialization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict


class PipelineState(TypedDict):
    # Inputs
    spec: str
    scenarios: str
    workspace_path: str

    # Planning
    implementation_plan: str

    # Execution tracking
    cycle: int
    max_cycles: int
    steering_prompt: str

    # Test/validation results
    test_output: str
    test_exit_code: int
    test_command: str
    validation_result: dict

    # History
    tool_call_history: list[dict]

    # Output
    diff_history: list[str]
    review_report: str
    summary: str


# Fields to truncate in run_state.json (keep first 500 chars)
_TRUNCATE_FIELDS = {"spec", "scenarios", "implementation_plan", "test_output", "steering_prompt"}
_TRUNCATE_LENGTH = 500


def save_run_state(
    state: PipelineState,
    path: Path,
    status: str = "running",
    node: str = "",
    error: str = "",
) -> None:
    """Serialize pipeline state to run_state.json."""
    serializable: dict[str, Any] = {}
    for key, value in state.items():
        if key in _TRUNCATE_FIELDS and isinstance(value, str) and len(value) > _TRUNCATE_LENGTH:
            serializable[key] = value[:_TRUNCATE_LENGTH] + "... [truncated]"
        else:
            serializable[key] = value
    serializable["status"] = status
    if node:
        serializable["current_node"] = node
    if error:
        serializable["error"] = error
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(serializable, indent=2, default=str))


def load_run_state(path: Path) -> dict[str, Any]:
    """Load run state from disk."""
    return json.loads(path.read_text())
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_state.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/attractor/state.py tests/test_state.py
git commit -m "feat: state module with PipelineState TypedDict and serialization"
```

---

### Task 5: Workspace Module

**Files:**
- Create: `src/attractor/workspace.py`
- Create: `tests/test_workspace.py`

- [ ] **Step 1: Write failing tests for workspace**

`tests/test_workspace.py`:
```python
import pytest
from pathlib import Path
from attractor.workspace import Workspace


@pytest.fixture
def target_repo(tmp_path):
    """Create a fake target repo with some files."""
    target = tmp_path / "target"
    target.mkdir()
    (target / "main.py").write_text("print('hello')\n")
    (target / "lib").mkdir()
    (target / "lib" / "utils.py").write_text("def add(a, b): return a + b\n")
    return target


@pytest.fixture
def workspace(tmp_path, target_repo):
    return Workspace(
        base_path=str(tmp_path / "runs"),
        run_id="test_run_001",
        target_repo=str(target_repo),
    )


def test_workspace_init_copies_files(workspace):
    ws_path = Path(workspace.path)
    assert (ws_path / "main.py").exists()
    assert (ws_path / "lib" / "utils.py").exists()


def test_workspace_init_creates_git_repo(workspace):
    ws_path = Path(workspace.path)
    assert (ws_path / ".git").is_dir()


def test_workspace_get_diff_empty_initially(workspace):
    assert workspace.get_diff() == ""


def test_workspace_get_diff_after_modification(workspace):
    ws_path = Path(workspace.path)
    (ws_path / "main.py").write_text("print('modified')\n")
    diff = workspace.get_diff()
    assert "modified" in diff
    assert "hello" in diff


def test_workspace_commit_checkpoint(workspace):
    ws_path = Path(workspace.path)
    (ws_path / "new_file.py").write_text("x = 1\n")
    commit_hash = workspace.commit_checkpoint("add new file")
    assert len(commit_hash) == 40  # full SHA


@pytest.mark.asyncio
async def test_workspace_run_isolated(workspace):
    result = await workspace.run_isolated("echo hello")
    assert result["stdout"].strip() == "hello"
    assert result["exit_code"] == 0


@pytest.mark.asyncio
async def test_workspace_run_isolated_timeout(workspace):
    result = await workspace.run_isolated("sleep 10", timeout=1)
    assert result["exit_code"] != 0
    assert "timeout" in result["stderr"].lower() or result["exit_code"] == -1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_workspace.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Write the workspace module**

`src/attractor/workspace.py`:
```python
"""Workspace management for isolated pipeline runs."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path


class Workspace:
    """An isolated workspace for a single pipeline run."""

    def __init__(self, base_path: str, run_id: str, target_repo: str) -> None:
        self.base_path = Path(base_path)
        self.run_id = run_id
        self.path = str(self.base_path / run_id)
        self._ws = Path(self.path)

        # Copy target repo contents into workspace
        if self._ws.exists():
            shutil.rmtree(self._ws)
        shutil.copytree(target_repo, self.path, dirs_exist_ok=False)

        # Initialize git repo with initial commit
        self._git("init")
        self._git("add", "-A")
        self._git("commit", "-m", "initial state", "--allow-empty")

    def _git(self, *args: str) -> str:
        """Run a git command in the workspace."""
        result = subprocess.run(
            ["git", *args],
            cwd=self.path,
            capture_output=True,
            text=True,
            env={
                **subprocess.os.environ,
                "GIT_AUTHOR_NAME": "attractor",
                "GIT_AUTHOR_EMAIL": "attractor@local",
                "GIT_COMMITTER_NAME": "attractor",
                "GIT_COMMITTER_EMAIL": "attractor@local",
            },
        )
        if result.returncode != 0 and "nothing to commit" not in result.stdout:
            if result.returncode != 0 and "nothing to commit" not in result.stderr:
                raise RuntimeError(
                    f"git {' '.join(args)} failed: {result.stderr}"
                )
        return result.stdout.strip()

    def get_diff(self) -> str:
        """Get the diff of all changes since initial state."""
        # Diff working tree against HEAD
        staged = self._git("diff", "--cached")
        unstaged = self._git("diff")
        if staged and unstaged:
            return staged + "\n" + unstaged
        return staged or unstaged

    def commit_checkpoint(self, message: str) -> str:
        """Commit all changes and return the commit hash."""
        self._git("add", "-A")
        self._git("commit", "-m", message, "--allow-empty")
        return self._git("rev-parse", "HEAD")

    async def run_isolated(self, command: str, timeout: int = 120) -> dict:
        """Run a command in the workspace directory."""
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=self.path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            return {
                "stdout": stdout_bytes.decode(errors="replace"),
                "stderr": stderr_bytes.decode(errors="replace"),
                "exit_code": proc.returncode or 0,
            }
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return {
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
                "exit_code": -1,
            }
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_workspace.py -v`
Expected: 7 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/attractor/workspace.py tests/test_workspace.py
git commit -m "feat: workspace module with git isolation and subprocess execution"
```

---

### Task 6: Coding Tools

**Files:**
- Create: `src/attractor/tools/file_tools.py`
- Create: `src/attractor/tools/shell_tools.py`
- Create: `src/attractor/tools/search_tools.py`
- Modify: `src/attractor/tools/__init__.py`
- Create: `tests/test_tools.py`

- [ ] **Step 1: Write failing tests for file tools**

`tests/test_tools.py`:
```python
import pytest
from pathlib import Path
from attractor.tools.file_tools import read_file, write_file, edit_file


@pytest.fixture
def workspace_dir(tmp_path):
    """Create a workspace directory with git init."""
    import subprocess
    ws = tmp_path / "workspace"
    ws.mkdir()
    subprocess.run(["git", "init"], cwd=ws, capture_output=True)
    (ws / "existing.py").write_text("line1\nline2\nline3\n")
    (ws / ".gitignore").write_text("__pycache__/\n*.pyc\n")
    return ws


# --- read_file ---

@pytest.mark.asyncio
async def test_read_file(workspace_dir):
    result = await read_file("existing.py", str(workspace_dir))
    assert "line1" in result
    assert "line2" in result


@pytest.mark.asyncio
async def test_read_file_not_found(workspace_dir):
    result = await read_file("nonexistent.py", str(workspace_dir))
    assert "error" in result.lower()


@pytest.mark.asyncio
async def test_read_file_rejects_path_traversal(workspace_dir):
    result = await read_file("../../etc/passwd", str(workspace_dir))
    assert "error" in result.lower()


# --- write_file ---

@pytest.mark.asyncio
async def test_write_file(workspace_dir):
    result = await write_file("new_file.py", "hello = 1\n", str(workspace_dir))
    assert "wrote" in result.lower() or "created" in result.lower()
    assert (workspace_dir / "new_file.py").read_text() == "hello = 1\n"


@pytest.mark.asyncio
async def test_write_file_creates_dirs(workspace_dir):
    result = await write_file("sub/dir/file.py", "x = 1\n", str(workspace_dir))
    assert (workspace_dir / "sub" / "dir" / "file.py").exists()


# --- edit_file ---

@pytest.mark.asyncio
async def test_edit_file(workspace_dir):
    result = await edit_file("existing.py", "line2", "LINE_TWO", str(workspace_dir))
    content = (workspace_dir / "existing.py").read_text()
    assert "LINE_TWO" in content
    assert "line2" not in content


@pytest.mark.asyncio
async def test_edit_file_not_found(workspace_dir):
    result = await edit_file("existing.py", "nonexistent_string", "replacement", str(workspace_dir))
    assert "error" in result.lower() or "not found" in result.lower()


@pytest.mark.asyncio
async def test_edit_file_ambiguous(workspace_dir):
    (workspace_dir / "dup.py").write_text("foo\nfoo\nbar\n")
    result = await edit_file("dup.py", "foo", "baz", str(workspace_dir))
    assert "ambiguous" in result.lower() or "multiple" in result.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_tools.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Write file_tools.py**

`src/attractor/tools/file_tools.py`:
```python
"""File manipulation tools for the implementer agent."""

from __future__ import annotations

from pathlib import Path


def _validate_path(file_path: str, workspace: str) -> Path | str:
    """Resolve path and validate it's within the workspace. Returns Path or error string."""
    ws = Path(workspace).resolve()
    target = (ws / file_path).resolve()
    if not str(target).startswith(str(ws)):
        return f"Error: path '{file_path}' resolves outside the workspace"
    return target


async def read_file(path: str, workspace: str) -> str:
    """Read a file relative to the workspace."""
    target = _validate_path(path, workspace)
    if isinstance(target, str):
        return target
    if not target.is_file():
        return f"Error: file '{path}' not found"
    try:
        return target.read_text()
    except Exception as e:
        return f"Error reading '{path}': {e}"


async def write_file(path: str, content: str, workspace: str) -> str:
    """Write a file relative to the workspace, creating parent dirs."""
    target = _validate_path(path, workspace)
    if isinstance(target, str):
        return target
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error writing '{path}': {e}"


async def edit_file(path: str, old_str: str, new_str: str, workspace: str) -> str:
    """Replace an exact string in a file. Errors if old_str not found or ambiguous."""
    target = _validate_path(path, workspace)
    if isinstance(target, str):
        return target
    if not target.is_file():
        return f"Error: file '{path}' not found"
    content = target.read_text()
    count = content.count(old_str)
    if count == 0:
        return f"Error: old_str not found in '{path}'"
    if count > 1:
        return f"Error: old_str is ambiguous — found {count} matches in '{path}'. Use more surrounding context to make it unique."
    new_content = content.replace(old_str, new_str, 1)
    target.write_text(new_content)
    return f"Edited {path}: replaced 1 occurrence"
```

- [ ] **Step 4: Run file tool tests**

Run: `python -m pytest tests/test_tools.py -v`
Expected: 8 PASSED

- [ ] **Step 5: Write failing tests for shell and search tools**

Append to `tests/test_tools.py`:
```python
from attractor.tools.shell_tools import run_shell
from attractor.tools.search_tools import list_files, grep


# --- run_shell ---

@pytest.mark.asyncio
async def test_run_shell(workspace_dir):
    result = await run_shell("echo hello", str(workspace_dir))
    assert result["stdout"].strip() == "hello"
    assert result["exit_code"] == 0


@pytest.mark.asyncio
async def test_run_shell_captures_stderr(workspace_dir):
    result = await run_shell("echo err >&2", str(workspace_dir))
    assert "err" in result["stderr"]


@pytest.mark.asyncio
async def test_run_shell_timeout(workspace_dir):
    result = await run_shell("sleep 10", str(workspace_dir), timeout=1)
    assert result["exit_code"] != 0


# --- list_files ---

@pytest.mark.asyncio
async def test_list_files(workspace_dir):
    import subprocess
    subprocess.run(["git", "add", "-A"], cwd=workspace_dir, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init", "--allow-empty"],
        cwd=workspace_dir, capture_output=True,
        env={**subprocess.os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t"},
    )
    files = await list_files(".", str(workspace_dir))
    assert "existing.py" in files
    assert ".gitignore" in files


# --- grep ---

@pytest.mark.asyncio
async def test_grep(workspace_dir):
    results = await grep("line2", ".", str(workspace_dir))
    assert any("existing.py" in r and "line2" in r for r in results)


@pytest.mark.asyncio
async def test_grep_no_match(workspace_dir):
    results = await grep("nonexistent_pattern_xyz", ".", str(workspace_dir))
    assert results == []
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `python -m pytest tests/test_tools.py::test_run_shell -v`
Expected: FAIL (ImportError)

- [ ] **Step 7: Write shell_tools.py**

`src/attractor/tools/shell_tools.py`:
```python
"""Shell execution tool for the implementer agent."""

from __future__ import annotations

import asyncio
from pathlib import Path


async def run_shell(command: str, workspace: str, timeout: int = 30) -> dict:
    """Run a shell command in the workspace directory."""
    ws = Path(workspace).resolve()
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(ws),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        return {
            "stdout": stdout_bytes.decode(errors="replace"),
            "stderr": stderr_bytes.decode(errors="replace"),
            "exit_code": proc.returncode or 0,
        }
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return {
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
            "exit_code": -1,
        }
```

- [ ] **Step 8: Write search_tools.py**

`src/attractor/tools/search_tools.py`:
```python
"""Search tools for the implementer agent."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

MAX_LIST_FILES = 500


async def list_files(path: str, workspace: str) -> list[str]:
    """List files recursively, respecting .gitignore. Capped at 500 entries."""
    ws = Path(workspace).resolve()
    target = (ws / path).resolve()
    if not str(target).startswith(str(ws)):
        return [f"Error: path '{path}' resolves outside the workspace"]

    try:
        # Get tracked files
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=str(target),
            capture_output=True,
            text=True,
        )
        tracked = set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()

        # Get untracked files (not ignored)
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(target),
            capture_output=True,
            text=True,
        )
        untracked = set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()

        all_files = sorted(tracked | untracked - {""})
        if len(all_files) > MAX_LIST_FILES:
            return all_files[:MAX_LIST_FILES] + [
                f"... and {len(all_files) - MAX_LIST_FILES} more files (capped at {MAX_LIST_FILES})"
            ]
        return all_files
    except Exception as e:
        return [f"Error listing files: {e}"]


async def grep(pattern: str, path: str, workspace: str) -> list[str]:
    """Search file contents for a pattern."""
    ws = Path(workspace).resolve()
    target = (ws / path).resolve()
    if not str(target).startswith(str(ws)):
        return [f"Error: path '{path}' resolves outside the workspace"]

    try:
        result = subprocess.run(
            ["grep", "-rn", "--include=*", pattern, str(target)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 1:  # no match
            return []
        lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
        # Make paths relative to workspace
        ws_str = str(ws) + "/"
        return [line.replace(ws_str, "") for line in lines]
    except Exception as e:
        return [f"Error searching: {e}"]
```

- [ ] **Step 9: Run all tool tests**

Run: `python -m pytest tests/test_tools.py -v`
Expected: 14 PASSED

- [ ] **Step 10: Write tool registry and schema generation**

`src/attractor/tools/__init__.py`:
```python
"""Coding tools for the implementer agent.

Provides a registry of tools, their OpenAI-format schemas, and a dispatcher.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from attractor.tools.file_tools import read_file, write_file, edit_file
from attractor.tools.shell_tools import run_shell
from attractor.tools.search_tools import list_files, grep

# Tool definitions: name -> (function, schema)
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file relative to the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to workspace root"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file, creating parent directories as needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to workspace root"},
                    "content": {"type": "string", "description": "File content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace an exact string in a file. Errors if the string is not found or matches multiple locations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to workspace root"},
                    "old_str": {"type": "string", "description": "Exact string to find (must be unique in file)"},
                    "new_str": {"type": "string", "description": "Replacement string"},
                },
                "required": ["path", "old_str", "new_str"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "Run a shell command in the workspace directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)", "default": 30},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files recursively in the workspace, respecting .gitignore. Capped at 500 entries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Subdirectory to list (default: root)", "default": "."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Search file contents for a regex pattern.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Search pattern (regex)"},
                    "path": {"type": "string", "description": "Subdirectory to search (default: root)", "default": "."},
                },
                "required": ["pattern"],
            },
        },
    },
]

# Map tool names to callables
_TOOL_FUNCTIONS: dict[str, Callable] = {
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "run_shell": run_shell,
    "list_files": list_files,
    "grep": grep,
}


async def dispatch_tool(name: str, arguments: dict[str, Any], workspace: str) -> str:
    """Execute a tool call and return the result as a string."""
    func = _TOOL_FUNCTIONS.get(name)
    if func is None:
        return f"Error: unknown tool '{name}'"
    # Inject workspace as the last positional arg
    result = await func(**arguments, workspace=workspace)
    if isinstance(result, dict):
        return json.dumps(result, indent=2)
    if isinstance(result, list):
        return "\n".join(str(item) for item in result)
    return str(result)


def truncate_output(output: str, max_chars: int = 8000) -> str:
    """Truncate tool output, keeping first and last halves."""
    if len(output) <= max_chars:
        return output
    half = max_chars // 2
    return output[:half] + "\n... [truncated] ...\n" + output[-half:]


def hash_tool_args(args: dict[str, Any]) -> str:
    """Hash tool arguments for loop detection."""
    serialized = json.dumps(args, sort_keys=True)
    return hashlib.md5(serialized.encode()).hexdigest()[:12]
```

- [ ] **Step 11: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 12: Commit**

```bash
git add src/attractor/tools/ tests/test_tools.py
git commit -m "feat: coding tools with registry, schema generation, and dispatcher"
```

---

### Task 7: LLM Client

**Files:**
- Create: `src/attractor/llm_client.py`
- Create: `tests/test_llm_client.py`

- [ ] **Step 1: Write failing tests for provider routing**

`tests/test_llm_client.py`:
```python
import pytest
import httpx
import respx
import json
from attractor.llm_client import LLMClient, parse_model_string
from attractor.config import ProviderConfig


def test_parse_model_string():
    provider, model = parse_model_string("openrouter/anthropic/claude-sonnet-4-5")
    assert provider == "openrouter"
    assert model == "anthropic/claude-sonnet-4-5"


def test_parse_model_string_single_segment():
    provider, model = parse_model_string("vastai/llama-3.1-70b")
    assert provider == "vastai"
    assert model == "llama-3.1-70b"


@pytest.mark.asyncio
@respx.mock
async def test_complete_routes_to_correct_provider():
    """Verify the LLM client sends requests to the right provider base URL."""
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "hello"}}],
        })
    )
    client = LLMClient(providers={
        "openrouter": ProviderConfig(base_url="https://openrouter.ai/api/v1", api_key="test-key"),
    })
    result = await client.complete(
        messages=[{"role": "user", "content": "hi"}],
        model="openrouter/anthropic/claude-sonnet-4-5",
    )
    assert route.called
    assert result["choices"][0]["message"]["content"] == "hello"
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_complete_structured():
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": '{"plan": "do stuff", "test_command": "pytest"}'}}],
        })
    )
    client = LLMClient(providers={
        "openrouter": ProviderConfig(base_url="https://openrouter.ai/api/v1", api_key="test-key"),
    })
    result = await client.complete_structured(
        messages=[{"role": "user", "content": "plan this"}],
        system="You are a planner",
        response_schema={"type": "object", "properties": {"plan": {"type": "string"}}},
        model="openrouter/anthropic/claude-sonnet-4-5",
    )
    assert route.called
    # Verify response_format was sent in the request
    request_body = json.loads(route.calls[0].request.content)
    assert "response_format" in request_body
    await client.close()


@pytest.mark.asyncio
async def test_complete_unknown_provider():
    client = LLMClient(providers={
        "openrouter": ProviderConfig(base_url="https://x.com/v1", api_key="k"),
    })
    with pytest.raises(ValueError, match="unknown_provider"):
        await client.complete(
            messages=[{"role": "user", "content": "hi"}],
            model="unknown_provider/some-model",
        )
    await client.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_llm_client.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Write the LLM client**

`src/attractor/llm_client.py`:
```python
"""Multi-provider LLM client for OpenAI-compatible APIs."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from attractor.config import ProviderConfig


def parse_model_string(model: str) -> tuple[str, str]:
    """Parse 'provider/model' into (provider_name, model_id)."""
    parts = model.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid model string '{model}': expected 'provider/model'")
    return parts[0], parts[1]


class LLMClient:
    """Async LLM client that routes to multiple OpenAI-compatible providers."""

    def __init__(self, providers: dict[str, ProviderConfig]) -> None:
        self._providers = providers
        self._clients: dict[str, httpx.AsyncClient] = {}
        for name, config in providers.items():
            self._clients[name] = httpx.AsyncClient(
                base_url=config.base_url,
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(120.0, connect=10.0),
            )

    def _get_client(self, provider: str) -> httpx.AsyncClient:
        client = self._clients.get(provider)
        if client is None:
            raise ValueError(
                f"Provider '{provider}' not configured. "
                f"Available: {list(self._clients.keys())}"
            )
        return client

    async def complete(
        self,
        messages: list[dict],
        system: str = "",
        model: str | None = None,
        tools: list | None = None,
    ) -> dict:
        """Send a chat completion request to the appropriate provider."""
        if model is None:
            raise ValueError("model is required")
        provider, model_id = parse_model_string(model)
        client = self._get_client(provider)

        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        body: dict[str, Any] = {
            "model": model_id,
            "messages": full_messages,
        }
        if tools:
            body["tools"] = tools

        return await self._request_with_retry(client, body)

    async def complete_structured(
        self,
        messages: list[dict],
        system: str,
        response_schema: dict,
        model: str | None = None,
    ) -> dict:
        """Send a chat completion with forced JSON schema response."""
        if model is None:
            raise ValueError("model is required")
        provider, model_id = parse_model_string(model)
        client = self._get_client(provider)

        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        body: dict[str, Any] = {
            "model": model_id,
            "messages": full_messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "schema": response_schema,
                },
            },
        }

        return await self._request_with_retry(client, body)

    async def _request_with_retry(
        self, client: httpx.AsyncClient, body: dict, max_retries: int = 3
    ) -> dict:
        """Send request with exponential backoff retry."""
        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                response = await client.post("/chat/completions", json=body)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPStatusError, httpx.TransportError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = 2 ** attempt
                    await asyncio.sleep(delay)
        raise last_error  # type: ignore[misc]

    async def close(self) -> None:
        """Close all HTTP clients."""
        for client in self._clients.values():
            await client.aclose()
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_llm_client.py -v`
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/attractor/llm_client.py tests/test_llm_client.py
git commit -m "feat: multi-provider LLM client with routing and retry"
```

---

### Task 8: Simple Nodes (spec_loader, test_runner, done)

**Files:**
- Create: `src/attractor/nodes/spec_loader.py`
- Create: `src/attractor/nodes/test_runner.py`
- Create: `src/attractor/nodes/done.py`
- Create: `tests/test_nodes.py`

- [ ] **Step 1: Write failing tests for spec_loader**

`tests/test_nodes.py`:
```python
import pytest
from pathlib import Path
from attractor.nodes.spec_loader import spec_loader


@pytest.mark.asyncio
async def test_spec_loader(tmp_path):
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("# My Feature\nBuild a thing.")
    scenarios_file = tmp_path / "scenarios.md"
    scenarios_file.write_text("## Scenario 1\nGiven: setup\nThen: result")

    state = {
        "spec": str(spec_file),
        "scenarios": str(scenarios_file),
        "workspace_path": "",
        "implementation_plan": "",
        "cycle": 0,
        "max_cycles": 10,
        "steering_prompt": "",
        "test_output": "",
        "test_exit_code": -1,
        "test_command": "",
        "validation_result": {},
        "tool_call_history": [],
        "diff_history": [],
        "review_report": "",
        "summary": "",
    }
    result = await spec_loader(state)
    assert "Build a thing" in result["spec"]
    assert "Scenario 1" in result["scenarios"]
    assert result["cycle"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_nodes.py::test_spec_loader -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Write spec_loader**

`src/attractor/nodes/spec_loader.py`:
```python
"""spec_loader node — reads spec and scenarios from disk."""

from __future__ import annotations

from pathlib import Path
from typing import Any


async def spec_loader(state: dict[str, Any]) -> dict[str, Any]:
    """Read spec and scenarios files, initialize state."""
    spec_path = Path(state["spec"])
    scenarios_path = Path(state["scenarios"])

    if not spec_path.is_file():
        raise FileNotFoundError(f"Spec file not found: {spec_path}")
    if not scenarios_path.is_file():
        raise FileNotFoundError(f"Scenarios file not found: {scenarios_path}")

    return {
        "spec": spec_path.read_text(),
        "scenarios": scenarios_path.read_text(),
        "cycle": 0,
        "tool_call_history": [],
        "diff_history": [],
        "validation_result": {},
        "review_report": "",
        "summary": "",
    }
```

- [ ] **Step 4: Run test**

Run: `python -m pytest tests/test_nodes.py::test_spec_loader -v`
Expected: PASS

- [ ] **Step 5: Write failing test for test_runner**

Append to `tests/test_nodes.py`:
```python
from attractor.nodes.test_runner import test_runner


@pytest.fixture
def workspace_with_pytest(tmp_path):
    """Workspace with a pyproject.toml indicating pytest."""
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "pyproject.toml").write_text('[project]\nname = "test"\n')
    (ws / "test_sample.py").write_text("def test_pass(): assert True\n")
    return ws


@pytest.mark.asyncio
async def test_test_runner_with_explicit_command(workspace_with_pytest):
    state = {
        "test_command": "echo TESTS_PASSED",
        "workspace_path": str(workspace_with_pytest),
        "test_output": "",
        "test_exit_code": -1,
    }
    result = await test_runner(state, test_timeout=30)
    assert result["test_exit_code"] == 0
    assert "TESTS_PASSED" in result["test_output"]


@pytest.mark.asyncio
async def test_test_runner_auto_detects_pytest(workspace_with_pytest):
    state = {
        "test_command": "",
        "workspace_path": str(workspace_with_pytest),
        "test_output": "",
        "test_exit_code": -1,
    }
    result = await test_runner(state, test_timeout=30)
    # Should auto-detect pytest from pyproject.toml
    assert result["test_command"] == "pytest"
```

- [ ] **Step 6: Write test_runner**

`src/attractor/nodes/test_runner.py`:
```python
"""test_runner node — runs the project test suite."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from attractor.workspace import Workspace


def _detect_test_command(workspace_path: str) -> str:
    """Auto-detect the test command based on project files."""
    ws = Path(workspace_path)
    if (ws / "pyproject.toml").exists():
        return "pytest"
    if (ws / "package.json").exists():
        return "npm test"
    if (ws / "Makefile").exists():
        return "make test"
    if (ws / "Cargo.toml").exists():
        return "cargo test"
    return "echo 'No test command detected'"


async def test_runner(
    state: dict[str, Any],
    config_test_command: str | None = None,
    test_timeout: int = 120,
) -> dict[str, Any]:
    """Run the test suite and capture output."""
    # Priority: config override > planner output > auto-detect
    test_cmd = config_test_command or state.get("test_command") or ""
    if not test_cmd:
        test_cmd = _detect_test_command(state["workspace_path"])

    ws = Workspace.__new__(Workspace)
    ws.path = state["workspace_path"]

    result = await ws.run_isolated(test_cmd, timeout=test_timeout)

    return {
        "test_command": test_cmd,
        "test_output": result["stdout"] + "\n" + result["stderr"],
        "test_exit_code": result["exit_code"],
    }
```

- [ ] **Step 7: Run test_runner tests**

Run: `python -m pytest tests/test_nodes.py::test_test_runner_with_explicit_command tests/test_nodes.py::test_test_runner_auto_detects_pytest -v`
Expected: 2 PASSED

- [ ] **Step 8: Write failing test for done node**

Append to `tests/test_nodes.py`:
```python
from attractor.nodes.done import done
import json


@pytest.mark.asyncio
async def test_done_writes_summary(tmp_path):
    state = {
        "workspace_path": str(tmp_path),
        "cycle": 3,
        "max_cycles": 10,
        "validation_result": {"passed": True, "satisfaction_score": 0.95},
        "review_report": "Looks good. Minor style issues.",
        "diff_history": ["diff1", "diff2", "diff3"],
        "spec": "# Spec",
        "scenarios": "# Scenarios",
        "implementation_plan": "",
        "steering_prompt": "",
        "test_output": "",
        "test_exit_code": 0,
        "test_command": "pytest",
        "tool_call_history": [],
        "summary": "",
    }
    result = await done(state)
    assert "summary" in result
    assert "3" in result["summary"]  # cycle count
    # Verify summary.md was written
    assert (tmp_path / "summary.md").exists()
    # Verify run_state.json was updated
    assert (tmp_path / "run_state.json").exists()
    run_state = json.loads((tmp_path / "run_state.json").read_text())
    assert run_state["status"] == "completed"
```

- [ ] **Step 9: Write done node**

`src/attractor/nodes/done.py`:
```python
"""done node — writes summary and finalizes run state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from attractor.state import save_run_state


async def done(state: dict[str, Any]) -> dict[str, Any]:
    """Write summary report and finalize run_state.json."""
    ws = Path(state["workspace_path"])
    validation = state.get("validation_result", {})
    passed = validation.get("passed", False)
    score = validation.get("satisfaction_score", 0.0)
    cycles_used = state.get("cycle", 0)
    max_cycles = state.get("max_cycles", 0)
    review = state.get("review_report", "")
    diffs = state.get("diff_history", [])

    status = "completed" if passed else "exhausted"

    summary_lines = [
        f"# Pipeline Run Summary",
        f"",
        f"**Status:** {status}",
        f"**Cycles used:** {cycles_used} / {max_cycles}",
        f"**Satisfaction score:** {score}",
        f"**Files changed:** {len(diffs)} checkpoint(s)",
        f"",
    ]
    if review:
        summary_lines.extend([
            f"## Review Report",
            f"",
            review,
            f"",
        ])
    if not passed:
        failing = validation.get("failing_scenarios", [])
        if failing:
            summary_lines.extend([
                f"## Failing Scenarios",
                f"",
                *[f"- {s}" for s in failing],
                f"",
            ])
        diagnosis = validation.get("diagnosis", "")
        if diagnosis:
            summary_lines.extend([
                f"## Last Diagnosis",
                f"",
                diagnosis,
            ])

    summary_text = "\n".join(summary_lines)
    (ws / "summary.md").write_text(summary_text)

    save_run_state(state, ws / "run_state.json", status=status)

    return {"summary": summary_text}
```

- [ ] **Step 10: Run all node tests**

Run: `python -m pytest tests/test_nodes.py -v`
Expected: 4 PASSED

- [ ] **Step 11: Commit**

```bash
git add src/attractor/nodes/spec_loader.py src/attractor/nodes/test_runner.py src/attractor/nodes/done.py tests/test_nodes.py
git commit -m "feat: spec_loader, test_runner, and done nodes"
```

---

### Task 9: LLM Nodes (planner, scenario_validator, diagnoser, reviewer)

**Files:**
- Create: `src/attractor/nodes/planner.py`
- Create: `src/attractor/nodes/scenario_validator.py`
- Create: `src/attractor/nodes/diagnoser.py`
- Create: `src/attractor/nodes/reviewer.py`

- [ ] **Step 1: Write the planner node**

`src/attractor/nodes/planner.py`:
```python
"""planner node — produces an implementation plan from the spec."""

from __future__ import annotations

import json
from typing import Any

from attractor.llm_client import LLMClient

PLANNER_SYSTEM = """You are an expert software architect. Given a feature specification, produce a detailed implementation plan.

Return a JSON object with two fields:
- "implementation_plan": A markdown string with the full plan (files to create/modify, approach, step-by-step instructions)
- "test_command": The recommended command to run the project's test suite (e.g., "pytest", "npm test")

Be specific about file paths, function signatures, and test strategies."""

PLANNER_SCHEMA = {
    "type": "object",
    "properties": {
        "implementation_plan": {"type": "string"},
        "test_command": {"type": "string"},
    },
    "required": ["implementation_plan", "test_command"],
}


async def planner(state: dict[str, Any], llm: LLMClient, model: str) -> dict[str, Any]:
    """Generate an implementation plan from the spec."""
    response = await llm.complete_structured(
        messages=[{"role": "user", "content": state["spec"]}],
        system=PLANNER_SYSTEM,
        response_schema=PLANNER_SCHEMA,
        model=model,
    )
    content = response["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    return {
        "implementation_plan": parsed["implementation_plan"],
        "test_command": parsed.get("test_command", ""),
    }
```

- [ ] **Step 2: Write the scenario_validator node**

`src/attractor/nodes/scenario_validator.py`:
```python
"""scenario_validator node — evaluates scenarios against test results."""

from __future__ import annotations

import json
from typing import Any

from attractor.llm_client import LLMClient

VALIDATOR_SYSTEM = """You are evaluating whether a code implementation satisfies a set of scenarios.

You will receive:
1. The scenarios (acceptance criteria)
2. Test output from running the test suite
3. The current code diff

Evaluate each scenario and return a JSON object:
- "passed": true if ALL scenarios are satisfied, false otherwise
- "satisfaction_score": 0.0 to 1.0 indicating overall satisfaction
- "failing_scenarios": list of scenario names that are NOT satisfied (empty if all pass)
- "diagnosis": explanation of what's wrong (empty string if all pass)"""

VALIDATOR_SCHEMA = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean"},
        "satisfaction_score": {"type": "number"},
        "failing_scenarios": {"type": "array", "items": {"type": "string"}},
        "diagnosis": {"type": "string"},
    },
    "required": ["passed", "satisfaction_score", "failing_scenarios", "diagnosis"],
}


async def scenario_validator(state: dict[str, Any], llm: LLMClient, model: str) -> dict[str, Any]:
    """Evaluate scenarios against test output and code diff."""
    user_content = f"""## Scenarios
{state['scenarios']}

## Test Output (exit code: {state['test_exit_code']})
{state['test_output']}

## Code Diff
{state.get('diff_history', [''])[-1] if state.get('diff_history') else 'No diff available'}"""

    response = await llm.complete_structured(
        messages=[{"role": "user", "content": user_content}],
        system=VALIDATOR_SYSTEM,
        response_schema=VALIDATOR_SCHEMA,
        model=model,
    )
    content = response["choices"][0]["message"]["content"]
    validation_result = json.loads(content)
    return {"validation_result": validation_result}
```

- [ ] **Step 3: Write the diagnoser node**

`src/attractor/nodes/diagnoser.py`:
```python
"""diagnoser node — analyzes failures and produces steering for the implementer."""

from __future__ import annotations

from typing import Any

from attractor.llm_client import LLMClient

DIAGNOSER_SYSTEM = """You are a senior debugging engineer. A coding agent attempted to implement a feature but the scenarios are not passing.

Analyze the failure and produce a focused, actionable steering prompt that tells the implementer agent EXACTLY what to fix and why. Be specific:
- Which files need changes
- What the current behavior is vs. expected
- A concrete approach to fix it

Do NOT produce a full implementation plan. Focus on the delta — what specifically needs to change from the current state."""


async def diagnoser(state: dict[str, Any], llm: LLMClient, model: str) -> dict[str, Any]:
    """Diagnose failures and produce a steering prompt for the implementer."""
    validation = state.get("validation_result", {})
    user_content = f"""## Original Spec
{state['spec']}

## Validation Result
Passed: {validation.get('passed', False)}
Score: {validation.get('satisfaction_score', 0)}
Failing scenarios: {validation.get('failing_scenarios', [])}
Diagnosis: {validation.get('diagnosis', 'No diagnosis')}

## Test Output (exit code: {state['test_exit_code']})
{state['test_output']}

## Current Diff
{state.get('diff_history', [''])[-1] if state.get('diff_history') else 'No diff available'}"""

    response = await llm.complete(
        messages=[{"role": "user", "content": user_content}],
        system=DIAGNOSER_SYSTEM,
        model=model,
    )
    steering = response["choices"][0]["message"]["content"]
    return {
        "steering_prompt": steering,
        "cycle": state["cycle"] + 1,
    }
```

- [ ] **Step 4: Write the reviewer node**

`src/attractor/nodes/reviewer.py`:
```python
"""reviewer node — reviews final diff for quality (post-convergence only)."""

from __future__ import annotations

from typing import Any

from attractor.llm_client import LLMClient

REVIEWER_SYSTEM = """You are a senior code reviewer. The implementation has passed all scenarios. Review the final diff for:
- Code style and readability
- Potential bugs or edge cases
- Maintainability concerns
- Security issues

Produce a concise review report. This is informational — it does NOT block the pipeline."""


async def reviewer(state: dict[str, Any], llm: LLMClient, model: str) -> dict[str, Any]:
    """Review the final diff for quality."""
    all_diffs = "\n---\n".join(state.get("diff_history", []))
    user_content = f"""## Spec
{state['spec']}

## Scenarios
{state['scenarios']}

## Full Diff
{all_diffs}"""

    response = await llm.complete(
        messages=[{"role": "user", "content": user_content}],
        system=REVIEWER_SYSTEM,
        model=model,
    )
    review = response["choices"][0]["message"]["content"]
    return {"review_report": review}
```

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All previous tests still PASS (these nodes are tested via integration in task 11)

- [ ] **Step 6: Commit**

```bash
git add src/attractor/nodes/planner.py src/attractor/nodes/scenario_validator.py src/attractor/nodes/diagnoser.py src/attractor/nodes/reviewer.py
git commit -m "feat: LLM nodes — planner, scenario_validator, diagnoser, reviewer"
```

---

### Task 10: Implementer Node

**Files:**
- Create: `src/attractor/nodes/implementer.py`

This is the most complex node — an inner agentic loop with tool use, loop detection, and context management.

- [ ] **Step 1: Write the implementer node**

`src/attractor/nodes/implementer.py`:
```python
"""implementer node — agentic inner loop with tool use."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from attractor.llm_client import LLMClient
from attractor.tools import (
    TOOL_DEFINITIONS,
    dispatch_tool,
    truncate_output,
    hash_tool_args,
)
from attractor.state import save_run_state
from attractor.workspace import Workspace

IMPLEMENTER_SYSTEM = """You are an expert software engineer implementing a feature in an existing codebase.

You have access to these tools: read_file, write_file, edit_file, run_shell, list_files, grep.

Guidelines:
- Start by exploring the codebase with list_files and read_file to understand the structure
- Write code incrementally — implement, then test
- Use edit_file for targeted changes to existing files, write_file for new files
- If edit_file fails because old_str matches multiple locations, retry with more surrounding context to make it unique. If the file is small, use write_file to replace the entire file instead.
- If a command times out, try breaking it into smaller steps or increasing the timeout parameter.
- If a tool call fails, read the error message carefully and adjust your approach rather than retrying the same call.
- When you are done implementing, stop calling tools and explain what you did."""


def _estimate_tokens(messages: list[dict]) -> int:
    """Estimate token count from total characters / 4."""
    total_chars = sum(len(json.dumps(m)) for m in messages)
    return total_chars // 4


def _truncate_context(messages: list[dict], char_limit: int) -> list[dict]:
    """Keep system + first 2 user messages + last N messages that fit."""
    if not messages:
        return messages
    total_chars = sum(len(json.dumps(m)) for m in messages)
    if total_chars <= char_limit:
        return messages

    # Keep system message (index 0) and first user message (index 1)
    keep_start = messages[:2]
    remaining = messages[2:]

    # From the end, keep messages until we hit the budget
    budget = char_limit - sum(len(json.dumps(m)) for m in keep_start)
    keep_end: list[dict] = []
    for msg in reversed(remaining):
        msg_chars = len(json.dumps(msg))
        if budget - msg_chars < 0:
            break
        keep_end.insert(0, msg)
        budget -= msg_chars

    return keep_start + [{"role": "user", "content": "[... earlier context truncated ...]"}] + keep_end


def _detect_loop(history: list[tuple[str, str]], window: int = 10) -> str | None:
    """Detect repeating patterns of length 2 or 3 in recent tool calls."""
    recent = history[-window:]
    if len(recent) < 4:
        return None

    for pattern_len in (2, 3):
        if len(recent) < pattern_len * 2:
            continue
        tail = recent[-pattern_len:]
        prev = recent[-pattern_len * 2 : -pattern_len]
        if tail == prev:
            calls = [f"{name}({args_hash})" for name, args_hash in tail]
            return f"Repeating pattern detected: {' -> '.join(calls)}"
    return None


async def implementer(
    state: dict[str, Any],
    llm: LLMClient,
    model: str,
    context_char_limit: int = 400_000,
    tool_output_truncation: int = 8000,
    loop_detection_window: int = 10,
) -> dict[str, Any]:
    """Run the implementer's inner agentic loop."""
    workspace_path = state["workspace_path"]
    ws = Workspace.__new__(Workspace)
    ws.path = workspace_path

    # Build initial messages
    messages: list[dict] = []

    # First cycle: use implementation plan. Subsequent: use steering prompt.
    if state.get("steering_prompt"):
        messages.append({
            "role": "user",
            "content": f"Fix the following issues with the implementation:\n\n{state['steering_prompt']}",
        })
    else:
        messages.append({
            "role": "user",
            "content": f"Implement the following plan:\n\n{state['implementation_plan']}",
        })

    # Loop detection tracker: list of (name, args_hash)
    call_tracker: list[tuple[str, str]] = []
    tool_call_history = list(state.get("tool_call_history", []))
    cycle = state.get("cycle", 0)

    while True:
        # Check context length and truncate if needed
        messages = _truncate_context(messages, context_char_limit)

        # Call LLM
        response = await llm.complete(
            messages=messages,
            system=IMPLEMENTER_SYSTEM,
            model=model,
            tools=TOOL_DEFINITIONS,
        )

        assistant_msg = response["choices"][0]["message"]
        messages.append(assistant_msg)

        # Check for tool calls
        tool_calls = assistant_msg.get("tool_calls")
        if not tool_calls:
            break  # Implementer is done

        # Execute each tool call
        for tc in tool_calls:
            func_name = tc["function"]["name"]
            try:
                func_args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                func_args = {}

            # Execute tool
            full_result = await dispatch_tool(func_name, func_args, workspace_path)

            # Track for loop detection
            args_hash = hash_tool_args(func_args)
            call_tracker.append((func_name, args_hash))
            tool_call_history.append({
                "name": func_name,
                "args_hash": args_hash,
                "cycle": cycle,
            })

            # Truncate output for LLM context
            truncated_result = truncate_output(full_result, tool_output_truncation)

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": truncated_result,
            })

        # Loop detection
        loop_msg = _detect_loop(call_tracker, loop_detection_window)
        if loop_msg:
            messages.append({
                "role": "user",
                "content": (
                    f"WARNING: {loop_msg}\n"
                    "You appear to be in a loop. Try a completely different approach. "
                    "Consider: reading the error message more carefully, trying a different "
                    "file or method, or using write_file instead of edit_file."
                ),
            })

        # Write state snapshot
        save_run_state(
            state | {"tool_call_history": tool_call_history},
            Path(workspace_path) / "run_state.json",
            status="running",
            node="implementer",
        )

    # Commit checkpoint after implementer finishes
    try:
        diff = ws.get_diff()
        if diff:
            ws.commit_checkpoint(f"implementer cycle {cycle}")
    except Exception:
        diff = ""

    return {
        "tool_call_history": tool_call_history,
        "diff_history": state.get("diff_history", []) + ([diff] if diff else []),
    }
```

- [ ] **Step 2: Run full test suite to verify no regressions**

Run: `python -m pytest tests/ -v`
Expected: All existing tests PASS

- [ ] **Step 3: Commit**

```bash
git add src/attractor/nodes/implementer.py
git commit -m "feat: implementer node with agentic loop, loop detection, context management"
```

---

### Task 11: Graph Assembly

**Files:**
- Create: `src/attractor/graph.py`
- Create: `tests/test_graph.py`

- [ ] **Step 1: Write failing test for graph routing**

`tests/test_graph.py`:
```python
import pytest
from attractor.graph import route_after_validation


def test_route_passes_to_reviewer():
    state = {"validation_result": {"passed": True}, "cycle": 0, "max_cycles": 10}
    assert route_after_validation(state) == "reviewer"


def test_route_fails_to_diagnoser():
    state = {"validation_result": {"passed": False}, "cycle": 0, "max_cycles": 10}
    assert route_after_validation(state) == "diagnoser"


def test_route_exhausted_to_done():
    state = {"validation_result": {"passed": False}, "cycle": 10, "max_cycles": 10}
    assert route_after_validation(state) == "done"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_graph.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Write graph.py**

`src/attractor/graph.py`:
```python
"""LangGraph StateGraph definition for the attractor pipeline."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

from langgraph.graph import StateGraph, END

from attractor.config import PipelineConfig
from attractor.llm_client import LLMClient
from attractor.state import PipelineState, save_run_state
from attractor.logging import get_logger

from attractor.nodes.spec_loader import spec_loader
from attractor.nodes.planner import planner
from attractor.nodes.implementer import implementer
from attractor.nodes.test_runner import test_runner
from attractor.nodes.scenario_validator import scenario_validator
from attractor.nodes.diagnoser import diagnoser
from attractor.nodes.reviewer import reviewer
from attractor.nodes.done import done


def route_after_validation(state: dict[str, Any]) -> str:
    """Conditional routing after scenario_validator."""
    validation = state.get("validation_result", {})
    passed = validation.get("passed", False)
    cycle = state.get("cycle", 0)
    max_cycles = state.get("max_cycles", 10)

    if passed:
        return "reviewer"
    if cycle >= max_cycles:
        return "done"
    return "diagnoser"


def _wrap_node(node_fn, name: str, config: PipelineConfig | None = None, llm: LLMClient | None = None):
    """Wrap a node function to add logging and state persistence."""
    @functools.wraps(node_fn)
    async def wrapper(state: dict[str, Any]) -> dict[str, Any]:
        logger = get_logger("attractor.graph", node=name)
        logger.info("entering node", event_type="NODE_ENTER")

        # Determine if this node needs LLM + model
        if llm and config:
            model_map = {
                "planner": config.llm.models.planner,
                "implementer": config.llm.models.implementer,
                "scenario_validator": config.llm.models.validator,
                "diagnoser": config.llm.models.diagnoser,
                "reviewer": config.llm.models.reviewer,
            }
            if name in model_map:
                if name == "implementer":
                    result = await node_fn(
                        state, llm=llm, model=model_map[name],
                        context_char_limit=config.pipeline.context_char_limit,
                        tool_output_truncation=config.pipeline.tool_output_truncation,
                        loop_detection_window=config.pipeline.loop_detection_window,
                    )
                elif name == "test_runner":
                    result = await node_fn(
                        state,
                        config_test_command=config.pipeline.test_command,
                    )
                else:
                    result = await node_fn(state, llm=llm, model=model_map[name])
            else:
                result = await node_fn(state)
        elif name == "test_runner" and config:
            result = await node_fn(state, config_test_command=config.pipeline.test_command)
        else:
            result = await node_fn(state)

        # Save run state after node exit
        merged = {**state, **result}
        ws_path = merged.get("workspace_path", "")
        if ws_path:
            save_run_state(
                merged,
                Path(ws_path) / "run_state.json",
                status="running",
                node=name,
            )

        logger.info("exiting node", event_type="NODE_EXIT")
        return result

    return wrapper


def build_graph(config: PipelineConfig, llm: LLMClient) -> StateGraph:
    """Build and compile the pipeline graph."""
    graph = StateGraph(dict)

    # Add nodes
    graph.add_node("spec_loader", _wrap_node(spec_loader, "spec_loader", config, llm))
    graph.add_node("planner", _wrap_node(planner, "planner", config, llm))
    graph.add_node("implementer", _wrap_node(implementer, "implementer", config, llm))
    graph.add_node("test_runner", _wrap_node(test_runner, "test_runner", config, llm))
    graph.add_node("scenario_validator", _wrap_node(scenario_validator, "scenario_validator", config, llm))
    graph.add_node("diagnoser", _wrap_node(diagnoser, "diagnoser", config, llm))
    graph.add_node("reviewer", _wrap_node(reviewer, "reviewer", config, llm))
    graph.add_node("done", _wrap_node(done, "done", config, llm))

    # Set entry point
    graph.set_entry_point("spec_loader")

    # Add edges
    graph.add_edge("spec_loader", "planner")
    graph.add_edge("planner", "implementer")
    graph.add_edge("implementer", "test_runner")
    graph.add_edge("test_runner", "scenario_validator")

    # Conditional edge after validation
    graph.add_conditional_edges(
        "scenario_validator",
        route_after_validation,
        {"reviewer": "reviewer", "diagnoser": "diagnoser", "done": "done"},
    )

    graph.add_edge("diagnoser", "implementer")
    graph.add_edge("reviewer", "done")
    graph.add_edge("done", END)

    return graph.compile()
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_graph.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/attractor/graph.py tests/test_graph.py
git commit -m "feat: LangGraph StateGraph with conditional routing"
```

---

### Task 12: CLI Entrypoint

**Files:**
- Create: `src/attractor/__main__.py`

- [ ] **Step 1: Write the CLI**

`src/attractor/__main__.py`:
```python
"""CLI entrypoint for the attractor pipeline."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from attractor.config import load_config
from attractor.llm_client import LLMClient
from attractor.logging import setup_logging, get_logger
from attractor.graph import build_graph
from attractor.workspace import Workspace


def generate_run_id() -> str:
    return f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


async def cmd_run(args: argparse.Namespace) -> None:
    """Execute a pipeline run."""
    config = load_config(args.config)
    setup_logging(level=config.logging.level, structured=config.logging.structured)
    logger = get_logger("attractor.cli")

    run_id = args.run_id or generate_run_id()
    logger.info("starting pipeline run", run_id=run_id)

    # Create workspace
    workspace = Workspace(
        base_path=config.workspace.base_path,
        run_id=run_id,
        target_repo=args.repo,
    )

    # Set up log file
    log_path = Path(workspace.path) / "run.log"
    logger.info("workspace created", path=workspace.path)

    # Build LLM client
    llm = LLMClient(providers=config.llm.providers)

    try:
        # Build and run graph
        graph = build_graph(config, llm)
        initial_state = {
            "spec": str(Path(args.spec).resolve()),
            "scenarios": str(Path(args.scenarios).resolve()),
            "workspace_path": workspace.path,
            "implementation_plan": "",
            "cycle": 0,
            "max_cycles": config.pipeline.max_cycles,
            "steering_prompt": "",
            "test_output": "",
            "test_exit_code": -1,
            "test_command": config.pipeline.test_command or "",
            "validation_result": {},
            "tool_call_history": [],
            "diff_history": [],
            "review_report": "",
            "summary": "",
        }

        result = await graph.ainvoke(initial_state)
        logger.info("pipeline complete", run_id=run_id, status="done")
        print(f"\nRun complete: {run_id}")
        print(f"Workspace: {workspace.path}")
        if result.get("summary"):
            print(f"\n{result['summary']}")
    finally:
        await llm.close()


def cmd_resume(args: argparse.Namespace) -> None:
    """Resume a failed run (not yet implemented)."""
    raise NotImplementedError(
        "Resume is not yet implemented. "
        "See design spec for planned approach."
    )


def cmd_status(args: argparse.Namespace) -> None:
    """Show run status."""
    config = load_config(args.config)
    run_dir = Path(config.workspace.base_path) / args.run_id
    state_file = run_dir / "run_state.json"

    if not state_file.exists():
        print(f"No run state found for '{args.run_id}'")
        print(f"Looked in: {state_file}")
        sys.exit(1)

    state = json.loads(state_file.read_text())
    print(f"Run: {args.run_id}")
    print(f"Status: {state.get('status', 'unknown')}")
    print(f"Cycle: {state.get('cycle', '?')} / {state.get('max_cycles', '?')}")
    if state.get("current_node"):
        print(f"Current node: {state['current_node']}")
    if state.get("validation_result"):
        vr = state["validation_result"]
        print(f"Passed: {vr.get('passed', '?')}")
        print(f"Score: {vr.get('satisfaction_score', '?')}")
    if state.get("error"):
        print(f"Error: {state['error']}")

    summary_file = run_dir / "summary.md"
    if summary_file.exists():
        print(f"\n--- Summary ---\n{summary_file.read_text()}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="attractor",
        description="LangGraph-based agentic coding pipeline",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run
    run_parser = subparsers.add_parser("run", help="Execute a pipeline run")
    run_parser.add_argument("--spec", required=True, help="Path to spec markdown file")
    run_parser.add_argument("--scenarios", required=True, help="Path to scenarios markdown file")
    run_parser.add_argument("--repo", required=True, help="Path to target repository")
    run_parser.add_argument("--run-id", default=None, help="Run ID (auto-generated if omitted)")
    run_parser.add_argument("--config", default="pipeline_config.yaml", help="Config file path")

    # resume
    resume_parser = subparsers.add_parser("resume", help="Resume a failed run")
    resume_parser.add_argument("--run-id", required=True, help="Run ID to resume")
    resume_parser.add_argument("--config", default="pipeline_config.yaml", help="Config file path")

    # status
    status_parser = subparsers.add_parser("status", help="Show run status")
    status_parser.add_argument("--run-id", required=True, help="Run ID to check")
    status_parser.add_argument("--config", default="pipeline_config.yaml", help="Config file path")

    args = parser.parse_args()

    if args.command == "run":
        asyncio.run(cmd_run(args))
    elif args.command == "resume":
        cmd_resume(args)
    elif args.command == "status":
        cmd_status(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify CLI help works**

Run: `python -m attractor --help`
Expected: Shows usage with run/resume/status subcommands

Run: `python -m attractor run --help`
Expected: Shows --spec, --scenarios, --repo, --run-id, --config options

- [ ] **Step 3: Commit**

```bash
git add src/attractor/__main__.py
git commit -m "feat: CLI entrypoint with run, resume (stub), and status commands"
```

---

### Task 13: Node Registry

**Files:**
- Modify: `src/attractor/nodes/__init__.py`

- [ ] **Step 1: Update nodes __init__.py**

`src/attractor/nodes/__init__.py`:
```python
"""Pipeline graph nodes."""

from attractor.nodes.spec_loader import spec_loader
from attractor.nodes.planner import planner
from attractor.nodes.implementer import implementer
from attractor.nodes.test_runner import test_runner
from attractor.nodes.scenario_validator import scenario_validator
from attractor.nodes.diagnoser import diagnoser
from attractor.nodes.reviewer import reviewer
from attractor.nodes.done import done

__all__ = [
    "spec_loader",
    "planner",
    "implementer",
    "test_runner",
    "scenario_validator",
    "diagnoser",
    "reviewer",
    "done",
]
```

- [ ] **Step 2: Commit**

```bash
git add src/attractor/nodes/__init__.py
git commit -m "feat: node registry with all exports"
```

---

### Task 14: Docker Deployment

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

- [ ] **Step 1: Write the Dockerfile**

`Dockerfile`:
```dockerfile
FROM python:3.12-slim

# Install git for workspace operations
RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash attractor
USER attractor
WORKDIR /home/attractor/app

# Install dependencies
COPY --chown=attractor:attractor pyproject.toml .
COPY --chown=attractor:attractor src/ src/
RUN pip install --no-cache-dir --user .

# Configure git for workspace commits
RUN git config --global user.name "attractor" && \
    git config --global user.email "attractor@local"

# Create volume mount points
RUN mkdir -p /home/attractor/workspace/runs /home/attractor/workspace/specs /home/attractor/workspace/logs

COPY --chown=attractor:attractor pipeline_config.yaml .

ENTRYPOINT ["python", "-m", "attractor"]
```

- [ ] **Step 2: Write docker-compose.yml**

`docker-compose.yml`:
```yaml
services:
  attractor:
    build: .
    environment:
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
      - VASTAI_API_KEY=${VASTAI_API_KEY:-}
      - VASTAI_BASE_URL=${VASTAI_BASE_URL:-}
    volumes:
      - ./runs:/home/attractor/workspace/runs
      - ./specs:/home/attractor/workspace/specs
      - ./logs:/home/attractor/workspace/logs
      - ./target:/home/attractor/workspace/target:ro
    command: ["run", "--spec", "/home/attractor/workspace/specs/spec.md", "--scenarios", "/home/attractor/workspace/specs/scenarios.md", "--repo", "/home/attractor/workspace/target"]
```

- [ ] **Step 3: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "feat: Docker deployment with non-root user and volume mounts"
```

---

### Task 15: Kubernetes Manifests

**Files:**
- Create: `k8s/job-template.yaml`
- Create: `k8s/configmap.yaml`
- Create: `k8s/secret-template.yaml`
- Create: `k8s/pvc.yaml`
- Create: `k8s/rbac.yaml`

- [ ] **Step 1: Write k8s manifests**

`k8s/job-template.yaml`:
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: attractor-${RUN_ID}
  labels:
    app: attractor
spec:
  backoffLimit: 0
  template:
    metadata:
      labels:
        app: attractor
    spec:
      restartPolicy: Never
      containers:
        - name: attractor
          image: attractor:latest
          args:
            - run
            - --spec
            - /workspace/specs/${SPEC_FILE}
            - --scenarios
            - /workspace/specs/${SCENARIOS_FILE}
            - --repo
            - /workspace/target
            - --run-id
            - ${RUN_ID}
            - --config
            - /config/pipeline_config.yaml
          env:
            - name: OPENROUTER_API_KEY
              valueFrom:
                secretKeyRef:
                  name: attractor-secrets
                  key: openrouter-api-key
          resources:
            requests:
              cpu: 500m
              memory: 512Mi
            limits:
              cpu: "2"
              memory: 2Gi
          volumeMounts:
            - name: workspace
              mountPath: /workspace
            - name: config
              mountPath: /config
      volumes:
        - name: workspace
          persistentVolumeClaim:
            claimName: attractor-workspace
        - name: config
          configMap:
            name: attractor-config
```

`k8s/configmap.yaml`:
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: attractor-config
data:
  pipeline_config.yaml: |
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
```

`k8s/secret-template.yaml`:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: attractor-secrets
type: Opaque
stringData:
  openrouter-api-key: REPLACE_ME
  # vastai-api-key: REPLACE_ME
```

`k8s/pvc.yaml`:
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: attractor-workspace
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
```

`k8s/rbac.yaml`:
```yaml
# Placeholder — attractor does not require cluster access initially.
# Add ServiceAccount + Role if future features need Kubernetes API access.
apiVersion: v1
kind: ServiceAccount
metadata:
  name: attractor
```

- [ ] **Step 2: Commit**

```bash
git add k8s/
git commit -m "feat: Kubernetes manifests — Job, ConfigMap, Secret, PVC, RBAC"
```

---

### Task 16: Create placeholder directories and .gitkeep

**Files:**
- Create: `runs/.gitkeep`
- Create: `specs/.gitkeep`
- Create: `logs/.gitkeep`

- [ ] **Step 1: Create directories**

```bash
mkdir -p runs specs logs
touch runs/.gitkeep specs/.gitkeep logs/.gitkeep
```

- [ ] **Step 2: Create a sample spec and scenarios for testing**

`specs/sample-spec.md`:
```markdown
# Sample Feature: Add a greeting function

Add a Python function `greet(name: str) -> str` in `greeting.py` that returns `"Hello, {name}!"`.

## Requirements
- Function should be in `greeting.py` at the project root
- Should handle empty string input by returning "Hello, World!"
- Should strip whitespace from the name
```

`specs/sample-scenarios.md`:
```markdown
# Scenarios: Greeting Function

## Scenario 1: Basic greeting
Given: A name "Alice"
When: greet("Alice") is called
Then: Returns "Hello, Alice!"
Validation: Test asserts return value equals "Hello, Alice!"

## Scenario 2: Empty name
Given: An empty string ""
When: greet("") is called
Then: Returns "Hello, World!"
Validation: Test asserts return value equals "Hello, World!"

## Scenario 3: Whitespace handling
Given: A name "  Bob  "
When: greet("  Bob  ") is called
Then: Returns "Hello, Bob!"
Validation: Test asserts return value equals "Hello, Bob!"
```

- [ ] **Step 3: Commit**

```bash
git add runs/ specs/ logs/
git commit -m "feat: placeholder dirs and sample spec/scenarios"
```

---

### Task 17: Final Integration — Run Full Test Suite

- [ ] **Step 1: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Verify CLI entrypoint**

Run: `python -m attractor --help`
Expected: Shows help

- [ ] **Step 3: Verify imports work end-to-end**

Run: `python -c "from attractor.graph import build_graph; print('OK')"`
Expected: Prints "OK"

- [ ] **Step 4: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: integration fixes from final test pass"
```
