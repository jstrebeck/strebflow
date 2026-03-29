# Claude Code Provider Design

**Date:** 2026-03-29
**Status:** Draft

## Overview

Add Claude Code (the CLI tool) as a provider in the attractor pipeline, enabling nodes to use a fixed-price Claude Code subscription instead of per-token API costs. Claude Code runs as a headless subprocess that can operate agentically — using its own built-in tools, MCP servers (including memory), skills, and CLAUDE.md context.

## Motivation

- **Cost:** Claude Code subscription is fixed-price, eliminating per-token API costs for Claude models.
- **Capabilities:** Claude Code's agentic mode provides built-in file editing, shell execution, MCP integrations (memory, context7), and project context that raw API calls lack.
- **Flexibility:** Per-node provider assignment means Claude Code can be used where its agentic capabilities add value, while cheaper/faster models handle simpler tasks.

## Architecture: Provider Protocol with Separate Implementations

### Provider Protocol

A Python `Protocol` class that both provider types implement:

```python
from typing import Protocol

class Provider(Protocol):
    async def complete(
        self,
        messages: list[dict],
        system: str = "",
        model: str | None = None,
        tools: list | None = None,
        workspace_path: str | None = None,
        max_turns: int | None = None,
    ) -> dict: ...

    async def complete_structured(
        self,
        messages: list[dict],
        system: str,
        response_schema: dict,
        model: str | None = None,
        workspace_path: str | None = None,
        max_turns: int | None = None,
    ) -> dict: ...

    async def close(self) -> None: ...
```

The `workspace_path` and `max_turns` parameters are new. `ClaudeCodeProvider` uses `workspace_path` as the subprocess working directory and `max_turns` to override the provider-level default. `HttpProvider` ignores both. Both providers return OpenAI-format response dicts so nodes remain unchanged.

### HttpProvider

Extracted from the current `LLMClient`. Handles a single provider (one `httpx.AsyncClient`). Contains the existing retry logic, bearer token auth, and `/chat/completions` request format. No behavior changes from current code.

### ClaudeCodeProvider

Spawns `claude` as a subprocess using `asyncio.create_subprocess_exec`. Key implementation details:

**CLI invocation:**
```
claude --print - --output-format stream-json --verbose \
  --model <model_id> \
  --max-turns <n> \
  --allowedTools <tool1> --allowedTools <tool2> ...
```

- `--print -`: Non-interactive mode, prompt read from stdin.
- `--output-format stream-json`: NDJSON output on stdout for structured parsing.
- `--model`: Model variant (e.g., `claude-sonnet-4-5-20250514`).
- `--max-turns`: Limits agentic iterations.
- `--allowedTools`: Permissions allowlist, one flag per tool.

**Prompt construction (`_build_prompt`):** Flattens the messages list and system prompt into a single text prompt for Claude Code's stdin. Since Claude Code isn't an OpenAI-compatible API, the conversation is rendered into natural language.

**Subprocess execution (`_run_claude`):**
- Spawns `claude` with `stdin=PIPE, stdout=PIPE, stderr=PIPE`.
- Sets `cwd` to `workspace_path` when provided.
- Writes the prompt to stdin, then closes the stream.
- Strips Claude Code nesting environment variables (`CLAUDE_CODE_SESSION`, `CLAUDE_CODE_ENTRYPOINT`, etc.) from the subprocess environment to prevent nested session detection.

**Stream-JSON parsing (`_parse_stream_json`):** Processes NDJSON output line by line, extracting:
- Assistant text blocks (the response content).
- Tool use events (for populating `tool_call_history`).
- Token usage and cost information (for logging/observability).

**Response normalization (`_to_openai_format`):** Wraps the parsed result in an OpenAI-compatible dict:
```python
{"choices": [{"message": {"role": "assistant", "content": result_text}}]}
```

No `tool_calls` in the response — Claude Code executes tools internally, so the implementer's tool loop sees a final message and exits naturally.

### LLMClient as Router

`LLMClient` becomes a thin routing layer. It holds a `dict[str, Provider]`, instantiates the correct provider type based on config, and delegates calls using `parse_model_string()` to resolve the provider name.

```python
class LLMClient:
    def __init__(self, providers: dict[str, ProviderConfig]) -> None:
        self._providers: dict[str, Provider] = {}
        for name, config in providers.items():
            if isinstance(config, ClaudeCodeProviderConfig):
                self._providers[name] = ClaudeCodeProvider(config)
            else:
                self._providers[name] = HttpProvider(config)
```

The public interface (`complete`, `complete_structured`, `close`) is unchanged. Nodes call it exactly as before.

## Configuration

### Provider Config Models

```python
class HttpProviderConfig(BaseModel):
    type: Literal["http"] = "http"
    base_url: str
    api_key: str

class ClaudeCodeProviderConfig(BaseModel):
    type: Literal["claude_code"]
    max_turns: int = 30
    allowed_tools: list[str] = []

ProviderConfig = HttpProviderConfig | ClaudeCodeProviderConfig
```

Existing configs without `type` default to `"http"` for backward compatibility.

### YAML Configuration

```yaml
llm:
  providers:
    openrouter:
      type: http
      base_url: https://openrouter.ai/api/v1
      api_key: ${OPENROUTER_API_KEY}
    claude_code:
      type: claude_code
      max_turns: 30
      allowed_tools:
        - Read
        - Edit
        - Write
        - Glob
        - Grep
        - "Bash(python *)"
        - "Bash(pytest *)"
        - "Bash(pip *)"
  models:
    planner: openrouter/deepseek/deepseek-chat-v3-0324
    implementer: claude_code/claude-sonnet-4-5-20250514
    validator: openrouter/google/gemini-2.0-flash-001
    diagnoser: openrouter/deepseek/deepseek-chat-v3-0324
    reviewer: claude_code/claude-sonnet-4-5-20250514
  max_turns_override:
    implementer: 50
    reviewer: 10
```

### Max Turns Override

`max_turns_override` is an optional dict at the `llm` level mapping node names to turn limits. Applied in `_wrap_node` in `graph.py` — the graph layer passes the override to the provider when constructing the call. The provider's `complete()` method accepts an optional `max_turns` parameter that takes precedence over the provider-level default.

## Implementer Integration

The implementer node's tool loop works unchanged:

1. Calls `llm.complete(messages, system, model, tools, workspace_path)`.
2. Checks response for `tool_calls`.
3. With `HttpProvider`: tool calls present, loop continues (existing behavior).
4. With `ClaudeCodeProvider`: no tool calls in response (Claude Code executed them internally), loop exits immediately.

**`latest_diff`:** Computed via `Workspace.get_diff()` after the implementer finishes. Works regardless of provider since it's just `git diff` on the workspace.

**`tool_call_history`:** Extracted from the stream-json output when using `ClaudeCodeProvider`. The NDJSON stream includes tool use events that can be parsed into the same `{name, args_hash, cycle}` format used for cross-cycle loop detection by the diagnoser. The `ClaudeCodeProvider` includes extracted tool calls in a `_tool_calls` key on the response dict (alongside the standard `choices` key). The implementer checks for this key and appends to its history. `HttpProvider` does not set this key — the implementer populates the history from the standard `tool_calls` response field as it does today.

**Minimal implementer code change:** Pass `workspace_path` to `llm.complete()`:

```python
response = await llm.complete(
    messages=messages,
    system=IMPLEMENTER_SYSTEM,
    model=model,
    tools=TOOL_DEFINITIONS,
    workspace_path=state["workspace_path"],  # new
)
```

## Sessions

Fresh session per call. No `--resume` flag. Each node invocation starts a new Claude Code session. The pipeline already passes full context (spec, diffs, test results) in messages, so session memory is redundant. Session resumption can be added later if needed.

## Permissions

Controlled via `--allowedTools` CLI flags, sourced from the `allowed_tools` list in the provider config. Claude Code tools not in the list are blocked — Claude Code adapts or reports what it couldn't do. No `--dangerously-skip-permissions` flag.

Recommended starting allowlist:
- `Read`, `Edit`, `Write`, `Glob`, `Grep` — file operations
- `Bash(python *)`, `Bash(pytest *)`, `Bash(pip *)` — Python-specific shell commands
- Git commands and destructive operations (`rm`, etc.) excluded by default

## Error Handling

- **Non-zero exit code:** `ClaudeCodeProvider` raises an error with stderr content.
- **Timeout:** Use `asyncio.wait_for()` with a configurable timeout (default: 300s for agentic calls, longer than the 120s HTTP timeout since Claude Code may run multi-turn tool loops).
- **Claude Code not installed:** Detect at provider initialization by checking if `claude` binary is on PATH. Raise a clear error.
- **Permission denied tool use:** Claude Code reports what it couldn't do in its response text. The pipeline treats this as a normal (possibly insufficient) response; the scenario validator and diagnoser handle it in subsequent cycles.

## Testing Strategy

- **Unit tests for `ClaudeCodeProvider`:** Mock `asyncio.create_subprocess_exec` to test prompt construction, CLI argument building, stream-json parsing, and response normalization without spawning real processes.
- **Unit tests for `HttpProvider`:** Existing `test_llm_client.py` tests, adapted to the new class structure.
- **Unit tests for `LLMClient` router:** Test provider resolution and delegation with mock providers.
- **Integration test:** Optional end-to-end test that spawns real Claude Code (gated behind an env var like `CLAUDE_CODE_INTEGRATION=1`) to verify the full flow.
- **Config tests:** Discriminated union parsing, backward compatibility (configs without `type` default to `http`), validation of `max_turns_override` node names.

## Files Changed

| File | Change |
|------|--------|
| `src/attractor/config.py` | Add `HttpProviderConfig`, `ClaudeCodeProviderConfig`, discriminated union `ProviderConfig`, `max_turns_override` field |
| `src/attractor/llm_client.py` | Extract `HttpProvider`, add `Provider` protocol, refactor `LLMClient` to router |
| `src/attractor/claude_code_provider.py` | New file: `ClaudeCodeProvider` class with subprocess management, prompt building, stream-json parsing |
| `src/attractor/graph.py` | Pass `workspace_path` and `max_turns` override through `_wrap_node` |
| `src/attractor/nodes/implementer.py` | Pass `workspace_path` to `llm.complete()` |
| `pipeline_config.yaml` | Add `claude_code` provider example (commented out) |
| `tests/test_llm_client.py` | Update for refactored classes, add router tests |
| `tests/test_claude_code_provider.py` | New file: unit tests for `ClaudeCodeProvider` |
| `tests/test_config.py` | Add discriminated union and backward compatibility tests |
