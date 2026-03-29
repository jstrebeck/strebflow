# Claude Code Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Claude Code as an agentic provider in the attractor pipeline using the Claude Agent SDK.

**Architecture:** Introduce a `Provider` protocol with `HttpProvider` (extracted from current `LLMClient`) and `ClaudeCodeProvider` (Agent SDK-based). `LLMClient` becomes a thin router. Config uses a Pydantic discriminated union for provider types.

**Tech Stack:** Python 3.12, Pydantic v2, claude-agent-sdk, pytest, respx

**Deviation from spec:** The design spec described raw subprocess spawning (Paperclip approach). This plan uses the `claude-agent-sdk` Python package instead, which wraps the subprocess management and provides typed message handling. All architectural decisions from the spec are unchanged.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `pyproject.toml` | Modify | Add `claude-agent-sdk` optional dependency |
| `src/attractor/config.py` | Modify | Discriminated union provider configs, `max_turns_override` |
| `src/attractor/llm_client.py` | Modify | `Provider` protocol, `HttpProvider`, `LLMClient` router |
| `src/attractor/claude_code_provider.py` | Create | `ClaudeCodeProvider` using Agent SDK |
| `src/attractor/graph.py` | Modify | Pass `workspace_path` and `max_turns` override |
| `src/attractor/nodes/implementer.py` | Modify | Forward `workspace_path` and `max_turns` to `llm.complete()` |
| `src/attractor/nodes/planner.py` | Modify | Forward `max_turns` to `llm.complete_structured()` |
| `src/attractor/nodes/diagnoser.py` | Modify | Forward `max_turns` to `llm.complete()` |
| `src/attractor/nodes/reviewer.py` | Modify | Forward `max_turns` to `llm.complete()` |
| `src/attractor/nodes/scenario_validator.py` | Modify | Forward `max_turns` to `llm.complete_structured()` |
| `pipeline_config.yaml` | Modify | Add commented `claude_code` provider example |
| `tests/test_config.py` | Modify | Discriminated union + backward compat tests |
| `tests/test_llm_client.py` | Modify | Adapt for `HttpProvider` + router |
| `tests/test_claude_code_provider.py` | Create | Unit tests for `ClaudeCodeProvider` |
| `tests/test_nodes.py` | Modify | Update mock LLM to accept new kwargs |

---

### Task 1: Config — Discriminated Union Provider Types

**Files:**
- Modify: `src/attractor/config.py:29-44`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for new config types**

Add to `tests/test_config.py`:

```python
from attractor.config import HttpProviderConfig, ClaudeCodeProviderConfig


def test_http_provider_config_defaults_type():
    config = HttpProviderConfig(base_url="https://x.com/v1", api_key="k")
    assert config.type == "http"


def test_claude_code_provider_config():
    config = ClaudeCodeProviderConfig(
        type="claude_code", max_turns=50,
        allowed_tools=["Read", "Edit"],
    )
    assert config.type == "claude_code"
    assert config.max_turns == 50
    assert config.allowed_tools == ["Read", "Edit"]


def test_claude_code_provider_config_defaults():
    config = ClaudeCodeProviderConfig(type="claude_code")
    assert config.max_turns == 30
    assert config.allowed_tools == []


def test_load_config_without_type_defaults_to_http(tmp_path, monkeypatch):
    """Backward compat: configs without 'type' parse as HttpProviderConfig."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
llm:
  providers:
    openrouter:
      base_url: https://openrouter.ai/api/v1
      api_key: ${OPENROUTER_API_KEY}
  models:
    planner: openrouter/model
    implementer: openrouter/model
    validator: openrouter/model
    diagnoser: openrouter/model
    reviewer: openrouter/model
workspace:
  base_path: /tmp
  target_repo: /tmp
""")
    config = load_config(str(config_file))
    provider = config.llm.providers["openrouter"]
    assert isinstance(provider, HttpProviderConfig)
    assert provider.api_key == "test-key"


def test_load_config_with_claude_code_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
llm:
  providers:
    openrouter:
      type: http
      base_url: https://openrouter.ai/api/v1
      api_key: ${OPENROUTER_API_KEY}
    claude_code:
      type: claude_code
      max_turns: 50
      allowed_tools:
        - Read
        - Edit
  models:
    planner: openrouter/model
    implementer: claude_code/sonnet
    validator: openrouter/model
    diagnoser: openrouter/model
    reviewer: openrouter/model
  max_turns_override:
    implementer: 80
workspace:
  base_path: /tmp
  target_repo: /tmp
""")
    config = load_config(str(config_file))
    cc = config.llm.providers["claude_code"]
    assert isinstance(cc, ClaudeCodeProviderConfig)
    assert cc.max_turns == 50
    assert cc.allowed_tools == ["Read", "Edit"]
    assert config.llm.max_turns_override == {"implementer": 80}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `HttpProviderConfig`, `ClaudeCodeProviderConfig` not defined

- [ ] **Step 3: Implement discriminated union config**

Replace the `ProviderConfig` class and update `LLMConfig` in `src/attractor/config.py`:

```python
from typing import Annotated, Any, Literal, Union
from pydantic import BaseModel, Discriminator, Field, Tag


class HttpProviderConfig(BaseModel):
    type: Literal["http"] = "http"
    base_url: str
    api_key: str


class ClaudeCodeProviderConfig(BaseModel):
    type: Literal["claude_code"]
    max_turns: int = 30
    allowed_tools: list[str] = Field(default_factory=list)


def _provider_discriminator(data: Any) -> str:
    if isinstance(data, dict):
        return data.get("type", "http")
    return getattr(data, "type", "http")


ProviderConfig = Annotated[
    Union[
        Annotated[HttpProviderConfig, Tag("http")],
        Annotated[ClaudeCodeProviderConfig, Tag("claude_code")],
    ],
    Discriminator(_provider_discriminator),
]


class LLMConfig(BaseModel):
    providers: dict[str, ProviderConfig]
    models: ModelConfig
    max_turns_override: dict[str, int] = Field(default_factory=dict)
```

Keep `ModelConfig` unchanged. Update the existing `test_load_config_validates_provider_in_model` test to use `HttpProviderConfig` instead of `ProviderConfig`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/attractor/config.py tests/test_config.py
git commit -m "feat(config): add discriminated union provider types for Claude Code support"
```

---

### Task 2: Provider Protocol + HttpProvider Extraction

**Files:**
- Modify: `src/attractor/llm_client.py`
- Modify: `tests/test_llm_client.py`

- [ ] **Step 1: Write failing test for HttpProvider**

Add to `tests/test_llm_client.py`:

```python
from attractor.llm_client import HttpProvider
from attractor.config import HttpProviderConfig


@pytest.mark.asyncio
@respx.mock
async def test_http_provider_complete():
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "hello"}}],
        })
    )
    provider = HttpProvider(HttpProviderConfig(
        base_url="https://openrouter.ai/api/v1", api_key="test-key",
    ))
    result = await provider.complete(
        messages=[{"role": "user", "content": "hi"}],
        model="anthropic/claude-sonnet-4-5",
    )
    assert route.called
    assert result["choices"][0]["message"]["content"] == "hello"
    await provider.close()


@pytest.mark.asyncio
@respx.mock
async def test_http_provider_complete_structured():
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": '{"plan": "do stuff"}'}}],
        })
    )
    provider = HttpProvider(HttpProviderConfig(
        base_url="https://openrouter.ai/api/v1", api_key="test-key",
    ))
    result = await provider.complete_structured(
        messages=[{"role": "user", "content": "plan this"}],
        system="You are a planner",
        response_schema={"type": "object", "properties": {"plan": {"type": "string"}}},
        model="anthropic/claude-sonnet-4-5",
    )
    assert route.called
    request_body = json.loads(route.calls[0].request.content)
    assert "response_format" in request_body
    await provider.close()


@pytest.mark.asyncio
async def test_http_provider_ignores_workspace_and_max_turns():
    """HttpProvider accepts but ignores workspace_path and max_turns."""
    provider = HttpProvider(HttpProviderConfig(
        base_url="https://x.com/v1", api_key="k",
    ))
    # Should not raise even with extra kwargs
    # (will fail on network, but that proves kwargs are accepted)
    with pytest.raises(Exception):  # network error expected
        await provider.complete(
            messages=[{"role": "user", "content": "hi"}],
            model="test-model",
            workspace_path="/tmp",
            max_turns=10,
        )
    await provider.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_llm_client.py::test_http_provider_complete -v`
Expected: FAIL — `HttpProvider` not defined

- [ ] **Step 3: Implement Provider protocol and HttpProvider**

In `src/attractor/llm_client.py`, add above the `LLMClient` class:

```python
from typing import Any, Protocol, runtime_checkable
from attractor.config import HttpProviderConfig, ClaudeCodeProviderConfig


@runtime_checkable
class Provider(Protocol):
    async def complete(
        self, messages: list[dict], system: str = "",
        model: str | None = None, tools: list | None = None,
        workspace_path: str | None = None, max_turns: int | None = None,
    ) -> dict: ...

    async def complete_structured(
        self, messages: list[dict], system: str,
        response_schema: dict, model: str | None = None,
        workspace_path: str | None = None, max_turns: int | None = None,
    ) -> dict: ...

    async def close(self) -> None: ...


class HttpProvider:
    """Provider that talks to OpenAI-compatible HTTP APIs."""

    def __init__(self, config: HttpProviderConfig) -> None:
        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(120.0, connect=10.0),
        )

    async def complete(
        self, messages: list[dict], system: str = "",
        model: str | None = None, tools: list | None = None,
        workspace_path: str | None = None, max_turns: int | None = None,
    ) -> dict:
        if model is None:
            raise ValueError("model is required")
        full_messages: list[dict[str, Any]] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)
        body: dict[str, Any] = {"model": model, "messages": full_messages}
        if tools:
            body["tools"] = tools
        return await self._request_with_retry(body)

    async def complete_structured(
        self, messages: list[dict], system: str,
        response_schema: dict, model: str | None = None,
        workspace_path: str | None = None, max_turns: int | None = None,
    ) -> dict:
        if model is None:
            raise ValueError("model is required")
        schema_instruction = (
            f"{system}\n\n"
            f"You MUST respond with a JSON object matching this schema:\n"
            f"{json.dumps(response_schema, indent=2)}"
        )
        full_messages: list[dict[str, Any]] = [
            {"role": "system", "content": schema_instruction},
        ]
        full_messages.extend(messages)
        body: dict[str, Any] = {
            "model": model,
            "messages": full_messages,
            "response_format": {"type": "json_object"},
        }
        return await self._request_with_retry(body)

    async def _request_with_retry(
        self, body: dict, max_retries: int = 3,
    ) -> dict:
        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                response = await self._client.post(
                    "/chat/completions", json=body,
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                error_body = e.response.text
                last_error = LLMRequestError(
                    f"{e.response.status_code} from {e.request.url}: {error_body}",
                )
                last_error.__cause__ = e
                status = e.response.status_code
                if 400 <= status < 500 and status != 429:
                    raise last_error from e
                if attempt < max_retries - 1:
                    delay = 2 ** attempt
                    await asyncio.sleep(delay)
            except httpx.TransportError as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = 2 ** attempt
                    await asyncio.sleep(delay)
        raise last_error  # type: ignore[misc]

    async def close(self) -> None:
        await self._client.aclose()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_llm_client.py -v`
Expected: New HttpProvider tests PASS, existing LLMClient tests still PASS

- [ ] **Step 5: Commit**

```bash
git add src/attractor/llm_client.py tests/test_llm_client.py
git commit -m "feat(llm): add Provider protocol and HttpProvider class"
```

---

### Task 3: LLMClient Router Refactoring

**Files:**
- Modify: `src/attractor/llm_client.py:20-111` (replace `LLMClient` class)
- Modify: `tests/test_llm_client.py`

- [ ] **Step 1: Update existing tests to use `HttpProviderConfig`**

In `tests/test_llm_client.py`, change all `ProviderConfig(...)` to `HttpProviderConfig(...)` and update the import:

```python
from attractor.config import HttpProviderConfig

# In test_complete_routes_to_correct_provider:
client = LLMClient(providers={
    "openrouter": HttpProviderConfig(base_url="https://openrouter.ai/api/v1", api_key="test-key"),
})

# In test_complete_structured:
client = LLMClient(providers={
    "openrouter": HttpProviderConfig(base_url="https://openrouter.ai/api/v1", api_key="test-key"),
})

# In test_complete_unknown_provider:
client = LLMClient(providers={
    "openrouter": HttpProviderConfig(base_url="https://x.com/v1", api_key="k"),
})
```

- [ ] **Step 2: Refactor LLMClient to router**

Replace the `LLMClient` class in `src/attractor/llm_client.py`:

```python
class LLMClient:
    """Routes LLM requests to the correct provider based on model string."""

    def __init__(self, providers: dict[str, ProviderConfig]) -> None:
        self._providers: dict[str, Provider] = {}
        for name, config in providers.items():
            if isinstance(config, ClaudeCodeProviderConfig):
                from attractor.claude_code_provider import ClaudeCodeProvider
                self._providers[name] = ClaudeCodeProvider(config)
            else:
                self._providers[name] = HttpProvider(config)

    def _get_provider(self, provider_name: str) -> Provider:
        provider = self._providers.get(provider_name)
        if provider is None:
            raise ValueError(
                f"Provider '{provider_name}' not configured. "
                f"Available: {list(self._providers.keys())}"
            )
        return provider

    async def complete(
        self, messages: list[dict], system: str = "",
        model: str | None = None, tools: list | None = None,
        workspace_path: str | None = None, max_turns: int | None = None,
    ) -> dict:
        if model is None:
            raise ValueError("model is required")
        provider_name, model_id = parse_model_string(model)
        provider = self._get_provider(provider_name)
        return await provider.complete(
            messages, system, model=model_id, tools=tools,
            workspace_path=workspace_path, max_turns=max_turns,
        )

    async def complete_structured(
        self, messages: list[dict], system: str,
        response_schema: dict, model: str | None = None,
        workspace_path: str | None = None, max_turns: int | None = None,
    ) -> dict:
        if model is None:
            raise ValueError("model is required")
        provider_name, model_id = parse_model_string(model)
        provider = self._get_provider(provider_name)
        return await provider.complete_structured(
            messages, system, response_schema, model=model_id,
            workspace_path=workspace_path, max_turns=max_turns,
        )

    async def close(self) -> None:
        for provider in self._providers.values():
            await provider.close()
```

Remove the old import of `ProviderConfig` and add:

```python
from attractor.config import ProviderConfig, HttpProviderConfig, ClaudeCodeProviderConfig
```

- [ ] **Step 3: Run all tests to verify nothing broke**

Run: `pytest tests/ -v`
Expected: All existing tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/attractor/llm_client.py tests/test_llm_client.py
git commit -m "refactor(llm): convert LLMClient to provider router"
```

---

### Task 4: ClaudeCodeProvider Implementation

**Files:**
- Create: `src/attractor/claude_code_provider.py`
- Create: `tests/test_claude_code_provider.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_claude_code_provider.py`:

```python
"""Tests for ClaudeCodeProvider using mocked Agent SDK."""
import sys
from unittest.mock import MagicMock

import pytest

from attractor.config import ClaudeCodeProviderConfig

# Mock the Agent SDK module before importing the provider.
# This allows tests to run without claude-agent-sdk installed.
_mock_sdk = MagicMock()


class _FakeResultMessage:
    def __init__(self, result: str):
        self.result = result


class _FakeAssistantMessage:
    def __init__(self, content: list | None = None, usage: dict | None = None):
        self.content = content or []
        self.usage = usage


_mock_sdk.ResultMessage = _FakeResultMessage
_mock_sdk.AssistantMessage = _FakeAssistantMessage
_mock_sdk.ClaudeAgentOptions = MagicMock
sys.modules.setdefault("claude_agent_sdk", _mock_sdk)

from attractor.claude_code_provider import ClaudeCodeProvider  # noqa: E402


def _make_config(**overrides) -> ClaudeCodeProviderConfig:
    defaults = {"type": "claude_code", "max_turns": 10}
    defaults.update(overrides)
    return ClaudeCodeProviderConfig(**defaults)


@pytest.mark.asyncio
async def test_complete_returns_openai_format():
    config = _make_config()
    provider = ClaudeCodeProvider(config)

    async def fake_query(prompt, options):
        yield _FakeResultMessage("Implementation complete.")

    _mock_sdk.query = fake_query

    result = await provider.complete(
        messages=[{"role": "user", "content": "Implement the plan"}],
        system="You are an engineer",
        model="sonnet",
        workspace_path="/tmp/ws",
    )

    assert result["choices"][0]["message"]["role"] == "assistant"
    assert result["choices"][0]["message"]["content"] == "Implementation complete."


@pytest.mark.asyncio
async def test_complete_structured_returns_openai_format():
    config = _make_config()
    provider = ClaudeCodeProvider(config)

    async def fake_query(prompt, options):
        yield _FakeResultMessage('{"plan": "step 1", "test_command": "pytest"}')

    _mock_sdk.query = fake_query

    result = await provider.complete_structured(
        messages=[{"role": "user", "content": "Plan this"}],
        system="You are a planner",
        response_schema={"type": "object", "properties": {"plan": {"type": "string"}}},
        model="sonnet",
    )

    content = result["choices"][0]["message"]["content"]
    assert '"plan"' in content


@pytest.mark.asyncio
async def test_complete_passes_workspace_as_cwd():
    config = _make_config(allowed_tools=["Read", "Edit"])
    provider = ClaudeCodeProvider(config)
    captured_options = {}

    async def fake_query(prompt, options):
        captured_options.update(vars(options) if hasattr(options, "__dict__") else {})
        yield _FakeResultMessage("done")

    _mock_sdk.query = fake_query
    # Capture the ClaudeAgentOptions constructor args
    options_calls = []
    original_options = _mock_sdk.ClaudeAgentOptions

    def capture_options(**kwargs):
        options_calls.append(kwargs)
        return original_options(**kwargs)

    _mock_sdk.ClaudeAgentOptions = capture_options

    await provider.complete(
        messages=[{"role": "user", "content": "test"}],
        model="sonnet",
        workspace_path="/workspace/target",
    )

    assert len(options_calls) == 1
    assert options_calls[0]["cwd"] == "/workspace/target"
    assert options_calls[0]["allowed_tools"] == ["Read", "Edit"]


@pytest.mark.asyncio
async def test_complete_uses_max_turns_override():
    config = _make_config(max_turns=30)
    provider = ClaudeCodeProvider(config)
    options_calls = []

    async def fake_query(prompt, options):
        yield _FakeResultMessage("done")

    _mock_sdk.query = fake_query
    original_options = _mock_sdk.ClaudeAgentOptions

    def capture_options(**kwargs):
        options_calls.append(kwargs)
        return original_options(**kwargs)

    _mock_sdk.ClaudeAgentOptions = capture_options

    # Call with override
    await provider.complete(
        messages=[{"role": "user", "content": "test"}],
        model="sonnet",
        max_turns=50,
    )

    assert options_calls[0]["max_turns"] == 50


@pytest.mark.asyncio
async def test_complete_uses_default_max_turns():
    config = _make_config(max_turns=25)
    provider = ClaudeCodeProvider(config)
    options_calls = []

    async def fake_query(prompt, options):
        yield _FakeResultMessage("done")

    _mock_sdk.query = fake_query
    original_options = _mock_sdk.ClaudeAgentOptions

    def capture_options(**kwargs):
        options_calls.append(kwargs)
        return original_options(**kwargs)

    _mock_sdk.ClaudeAgentOptions = capture_options

    # Call without override — should use config default
    await provider.complete(
        messages=[{"role": "user", "content": "test"}],
        model="sonnet",
    )

    assert options_calls[0]["max_turns"] == 25


@pytest.mark.asyncio
async def test_build_prompt_flattens_messages():
    config = _make_config()
    provider = ClaudeCodeProvider(config)
    captured_prompts = []

    async def fake_query(prompt, options):
        captured_prompts.append(prompt)
        yield _FakeResultMessage("done")

    _mock_sdk.query = fake_query
    _mock_sdk.ClaudeAgentOptions = MagicMock

    await provider.complete(
        messages=[
            {"role": "user", "content": "First message"},
            {"role": "assistant", "content": "Response"},
            {"role": "user", "content": "Second message"},
        ],
        model="sonnet",
    )

    prompt = captured_prompts[0]
    assert "First message" in prompt
    assert "Second message" in prompt


@pytest.mark.asyncio
async def test_close_is_noop():
    config = _make_config()
    provider = ClaudeCodeProvider(config)
    await provider.close()  # Should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_claude_code_provider.py -v`
Expected: FAIL — `attractor.claude_code_provider` module not found

- [ ] **Step 3: Implement ClaudeCodeProvider**

Create `src/attractor/claude_code_provider.py`:

```python
"""Claude Code provider using the Agent SDK."""
from __future__ import annotations

import json
from typing import Any

from attractor.config import ClaudeCodeProviderConfig

try:
    from claude_agent_sdk import (
        ClaudeAgentOptions,
        ResultMessage,
        query,
    )

    _HAS_SDK = True
except ImportError:
    _HAS_SDK = False


class ClaudeCodeProvider:
    """Provider that runs Claude Code agentically via the Agent SDK."""

    def __init__(self, config: ClaudeCodeProviderConfig) -> None:
        if not _HAS_SDK:
            raise ImportError(
                "claude-agent-sdk is required for the claude_code provider. "
                "Install it with: pip install claude-agent-sdk"
            )
        self._max_turns = config.max_turns
        self._allowed_tools = config.allowed_tools

    def _build_prompt(self, messages: list[dict]) -> str:
        """Flatten non-system messages into a single prompt for Claude Code."""
        parts: list[str] = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str) and msg.get("role") != "system":
                parts.append(content)
        return "\n\n".join(parts)

    async def complete(
        self,
        messages: list[dict],
        system: str = "",
        model: str | None = None,
        tools: list | None = None,
        workspace_path: str | None = None,
        max_turns: int | None = None,
    ) -> dict:
        from claude_agent_sdk import (
            AssistantMessage, ClaudeAgentOptions, ResultMessage, query,
        )

        prompt = self._build_prompt(messages)
        options_kwargs: dict[str, Any] = {
            "max_turns": max_turns or self._max_turns,
            "allowed_tools": self._allowed_tools or [
                "Read", "Edit", "Write", "Glob", "Grep", "Bash",
            ],
            "permission_mode": "acceptEdits",
            "setting_sources": ["user", "project"],
        }
        if system:
            options_kwargs["system_prompt"] = system
        if model:
            options_kwargs["model"] = model
        if workspace_path:
            options_kwargs["cwd"] = workspace_path

        options = ClaudeAgentOptions(**options_kwargs)

        result_text = ""
        tool_calls_extracted: list[dict] = []

        try:
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, ResultMessage) and message.result:
                    result_text = message.result
                elif isinstance(message, AssistantMessage):
                    for block in message.content:
                        if getattr(block, "type", None) == "tool_use":
                            tool_calls_extracted.append({
                                "name": getattr(block, "name", "unknown"),
                                "input": getattr(block, "input", {}),
                            })
        except Exception as e:
            from attractor.llm_client import LLMRequestError

            raise LLMRequestError(
                f"Claude Code provider error: {e}"
            ) from e

        response: dict[str, Any] = {
            "choices": [
                {"message": {"role": "assistant", "content": result_text}},
            ],
        }
        if tool_calls_extracted:
            response["_tool_calls"] = tool_calls_extracted
        return response

    async def complete_structured(
        self,
        messages: list[dict],
        system: str,
        response_schema: dict,
        model: str | None = None,
        workspace_path: str | None = None,
        max_turns: int | None = None,
    ) -> dict:
        schema_instruction = (
            f"{system}\n\n"
            f"You MUST respond with a JSON object matching this schema:\n"
            f"{json.dumps(response_schema, indent=2)}"
        )
        return await self.complete(
            messages=messages,
            system=schema_instruction,
            model=model,
            workspace_path=workspace_path,
            max_turns=max_turns or min(self._max_turns, 5),
        )

    async def close(self) -> None:
        pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_claude_code_provider.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/attractor/claude_code_provider.py tests/test_claude_code_provider.py
git commit -m "feat(provider): add ClaudeCodeProvider using Agent SDK"
```

---

### Task 5: Graph + Node Integration

**Files:**
- Modify: `src/attractor/graph.py:38-95`
- Modify: `src/attractor/nodes/implementer.py:80-113`
- Modify: `src/attractor/nodes/planner.py:24-36`
- Modify: `src/attractor/nodes/diagnoser.py:25-47`
- Modify: `src/attractor/nodes/reviewer.py:24-40`
- Modify: `src/attractor/nodes/scenario_validator.py:43-65`
- Modify: `tests/test_nodes.py`

- [ ] **Step 1: Update mock LLM helper in tests to accept new kwargs**

In `tests/test_nodes.py`, update `_make_mock_llm`:

```python
def _make_mock_llm(content: str) -> AsyncMock:
    """Create a mock LLMClient that returns the given content."""
    mock = AsyncMock()
    mock.complete.return_value = {
        "choices": [{"message": {"role": "assistant", "content": content}}],
    }
    mock.complete_structured.return_value = {
        "choices": [{"message": {"role": "assistant", "content": content}}],
    }
    return mock
```

This already works because `AsyncMock` accepts any kwargs. But we should verify the new kwargs are passed through. Add a test:

```python
@pytest.mark.asyncio
async def test_implementer_passes_workspace_path_to_llm(tmp_path):
    """Implementer forwards workspace_path to llm.complete()."""
    import subprocess
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    (ws_dir / "file.py").write_text("x = 1\n")
    subprocess.run(["git", "init"], cwd=ws_dir, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=ws_dir, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=ws_dir, capture_output=True,
        env={**subprocess.os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
    )
    mock_llm = _make_mock_llm("No changes needed.")
    state = {
        "spec": "# Spec", "scenarios": "", "workspace_path": str(ws_dir),
        "implementation_plan": "Step 1: review", "cycle": 0, "max_cycles": 10,
        "steering_prompt": "", "test_output": "", "test_exit_code": -1,
        "test_command": "", "validation_result": {}, "tool_call_history": [],
        "latest_diff": "", "review_report": "", "summary": "",
    }
    await implementer(state, llm=mock_llm, model="openrouter/test-model")

    call_kwargs = mock_llm.complete.call_args
    assert call_kwargs.kwargs.get("workspace_path") == str(ws_dir)


@pytest.mark.asyncio
async def test_planner_forwards_max_turns():
    mock_llm = _make_mock_llm('{"implementation_plan": "plan", "test_command": "pytest"}')
    state = {"spec": "# Spec", "scenarios": "", "workspace_path": "", "implementation_plan": "", "cycle": 0, "max_cycles": 10, "steering_prompt": "", "test_output": "", "test_exit_code": -1, "test_command": "", "validation_result": {}, "tool_call_history": [], "latest_diff": "", "review_report": "", "summary": ""}
    await planner(state, llm=mock_llm, model="openrouter/test", max_turns=15)
    call_kwargs = mock_llm.complete_structured.call_args
    assert call_kwargs.kwargs.get("max_turns") == 15
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_nodes.py::test_implementer_passes_workspace_path_to_llm -v`
Expected: FAIL — `workspace_path` not passed

- [ ] **Step 3: Update node signatures to forward workspace_path and max_turns**

In `src/attractor/nodes/implementer.py`, update the function signature and the `llm.complete()` call:

```python
async def implementer(
    state: dict[str, Any],
    llm: LLMClient,
    model: str,
    context_char_limit: int = 400_000,
    tool_output_truncation: int = 8000,
    loop_detection_window: int = 10,
    max_turns: int | None = None,
) -> dict[str, Any]:
```

And inside the while loop, change the `llm.complete()` call:

```python
        response = await llm.complete(
            messages=messages, system=IMPLEMENTER_SYSTEM, model=model,
            tools=TOOL_DEFINITIONS,
            workspace_path=workspace_path,
            max_turns=max_turns,
        )
```

After the existing tool_calls loop (after `if not tool_calls: break`), add handling for `_tool_calls` from Claude Code provider:

```python
        tool_calls = assistant_msg.get("tool_calls")
        if not tool_calls:
            # Check for tool calls extracted by ClaudeCodeProvider
            for tc in response.get("_tool_calls", []):
                args_hash = hash_tool_args(tc.get("input", {}))
                tool_call_history.append({
                    "name": tc["name"], "args_hash": args_hash, "cycle": cycle,
                })
            break
```

In `src/attractor/nodes/planner.py`:

```python
async def planner(state: dict[str, Any], llm: LLMClient, model: str, max_turns: int | None = None) -> dict[str, Any]:
    response = await llm.complete_structured(
        messages=[{"role": "user", "content": state["spec"]}],
        system=PLANNER_SYSTEM,
        response_schema=PLANNER_SCHEMA,
        model=model,
        max_turns=max_turns,
    )
```

In `src/attractor/nodes/diagnoser.py`:

```python
async def diagnoser(state: dict[str, Any], llm: LLMClient, model: str, max_turns: int | None = None) -> dict[str, Any]:
```

And at the end:

```python
    response = await llm.complete(
        messages=[{"role": "user", "content": user_content}],
        system=DIAGNOSER_SYSTEM,
        model=model,
        max_turns=max_turns,
    )
```

In `src/attractor/nodes/reviewer.py`:

```python
async def reviewer(state: dict[str, Any], llm: LLMClient, model: str, max_turns: int | None = None) -> dict[str, Any]:
```

And:

```python
    response = await llm.complete(
        messages=[{"role": "user", "content": user_content}],
        system=REVIEWER_SYSTEM,
        model=model,
        max_turns=max_turns,
    )
```

In `src/attractor/nodes/scenario_validator.py`:

```python
async def scenario_validator(state: dict[str, Any], llm: LLMClient, model: str, max_turns: int | None = None) -> dict[str, Any]:
```

And:

```python
    response = await llm.complete_structured(
        messages=[{"role": "user", "content": user_content}],
        system=VALIDATOR_SYSTEM,
        response_schema=VALIDATOR_SCHEMA,
        model=model,
        max_turns=max_turns,
    )
```

- [ ] **Step 4: Update `_wrap_node` in graph.py to pass max_turns**

In `src/attractor/graph.py`, update the `_wrap_node` function. Change the two LLM branches:

```python
        try:
            model_map = {
                "planner": config.llm.models.planner if config else None,
                "implementer": config.llm.models.implementer if config else None,
                "scenario_validator": config.llm.models.validator if config else None,
                "diagnoser": config.llm.models.diagnoser if config else None,
                "reviewer": config.llm.models.reviewer if config else None,
            }
            max_turns = (
                config.llm.max_turns_override.get(name)
                if config else None
            )
            if name == "test_runner" and config:
                result = await node_fn(
                    state,
                    config_test_command=config.pipeline.test_command,
                    test_timeout=config.pipeline.test_timeout,
                )
            elif name == "implementer" and llm and config:
                result = await node_fn(
                    state, llm=llm, model=model_map[name],
                    context_char_limit=config.pipeline.context_char_limit,
                    tool_output_truncation=config.pipeline.tool_output_truncation,
                    loop_detection_window=config.pipeline.loop_detection_window,
                    max_turns=max_turns,
                )
            elif name in model_map and model_map[name] and llm:
                result = await node_fn(
                    state, llm=llm, model=model_map[name],
                    max_turns=max_turns,
                )
            else:
                result = await node_fn(state)
```

- [ ] **Step 5: Run all tests**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/attractor/nodes/ src/attractor/graph.py tests/test_nodes.py
git commit -m "feat(nodes): forward workspace_path and max_turns through pipeline"
```

---

### Task 6: Dependencies + Pipeline Config

**Files:**
- Modify: `pyproject.toml`
- Modify: `pipeline_config.yaml`

- [ ] **Step 1: Add claude-agent-sdk as optional dependency**

In `pyproject.toml`, add:

```toml
[project.optional-dependencies]
claude-code = [
    "claude-agent-sdk",
]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "respx>=0.22",
]
```

- [ ] **Step 2: Add commented claude_code provider example to pipeline_config.yaml**

Add after the existing `openrouter` provider:

```yaml
    # claude_code:
    #   type: claude_code
    #   max_turns: 30
    #   allowed_tools:
    #     - Read
    #     - Edit
    #     - Write
    #     - Glob
    #     - Grep
    #     - "Bash(python *)"
    #     - "Bash(pytest *)"
    #     - "Bash(pip *)"
```

And add after the `models` block:

```yaml
  # max_turns_override:
  #   implementer: 50
  #   reviewer: 10
```

- [ ] **Step 3: Run all tests to verify nothing broke**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml pipeline_config.yaml
git commit -m "feat: add claude-agent-sdk dependency and config example"
```
