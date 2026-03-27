# Attractor Pipeline — Design Spec

A LangGraph-based agentic coding pipeline that takes a spec, implements it, validates against scenarios, and converges autonomously. Modeled after StrongDM's Attractor concept.

## 1. Graph Architecture

The pipeline is a LangGraph `StateGraph` with 8 nodes and conditional routing:

```
spec_loader → planner → implementer → test_runner → scenario_validator
                                                          │
                                              ┌───────────┼───────────┐
                                              ▼           ▼           ▼
                                           reviewer    diagnoser     done
                                              │           │        (max_cycles
                                              ▼           ▼         exhausted)
                                            done      implementer
                                                      (re-enter loop)
```

### Edge Conditions

- `spec_loader → planner` — always
- `planner → implementer` — always
- `implementer → test_runner` — always
- `test_runner → scenario_validator` — always
- `scenario_validator → reviewer` — if `passed == True`
- `scenario_validator → diagnoser` — if `passed == False AND cycle < max_cycles`
- `scenario_validator → done` — if `passed == False AND cycle >= max_cycles` (exhausted)
- `diagnoser → implementer` — always (passes focused re-prompt as steering)
- `reviewer → done` — always

### State Schema

```python
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
    steering_prompt: str  # injected by diagnoser, consumed by implementer

    # Test/validation results
    test_output: str
    test_exit_code: int
    test_command: str  # from planner output or config override or auto-detect
    validation_result: dict  # {passed, satisfaction_score, failing_scenarios, diagnosis}

    # History (for loop detection)
    tool_call_history: list[dict]  # {name, args_hash, cycle}

    # Output
    diff_history: list[str]  # git diffs per cycle
    review_report: str
    summary: str
```

Each node receives the full state and returns a partial dict of updates (LangGraph merges them). The `cycle` counter increments each time the `diagnoser → implementer` loop fires.

### Run State Persistence

After every node exit, the current state (minus large fields like full tool call history) is serialized to `run_state.json` in the run directory. This powers the `status` CLI command and provides a foundation for future `resume` support.

## 2. Implementer Inner Loop

The implementer is **not** a LangGraph subgraph. It is a single LangGraph node containing its own `while True` loop (Approach C: internal loop with state snapshots).

```
build messages (system + plan + steering)
       │
       ▼
┌─► call LLM with tools ──┐
│      │                   │
│      ▼                   │
│  has tool calls?         │
│    yes │    no ──────────┼──► return
│        ▼                 │
│  execute tools           │
│        │                 │
│        ▼                 │
│  append results to msgs  │
│        │                 │
│        ▼                 │
│  check loop detection    │
│  check context length    │
│  write state snapshot    │
└────────┘                 │
```

### Message Construction

- **System prompt:** role description + available tools + workspace context
- **First cycle:** the implementation plan from the planner
- **Subsequent cycles:** the `steering_prompt` from the diagnoser (focused fix instructions)
- Conversation builds as assistant (tool calls) + tool (results) pairs

### Context Management

- After each round, estimate token count as `total_chars / 4`
- Configurable threshold (default ~100k tokens = ~400k chars)
- When exceeded: keep system message + first 2 user messages + last N messages that fit. Drop the middle.

### Loop Detection

- Track last 10 tool calls as `(name, hash(args))` tuples
- After each tool call, scan for repeating patterns of length 2 or 3
- If detected: inject a steering message telling the LLM it's looping and to try a different approach

### Tool Output Handling

- Full output stored in state for logging
- Truncated to 8000 chars before appending to LLM messages
- Truncation: first 4000 + last 4000 chars with `\n... [truncated] ...\n` separator

### State Snapshots

After each tool-call round, write current implementer state (tool call count, last tool, estimated tokens used) to `run_state.json`.

## 3. Coding Tools

Six tools, all executed with `workspace_path` as cwd:

| Tool | Signature | Behavior |
|------|-----------|----------|
| `read_file` | `(path: str) -> str` | Read file relative to workspace. Error if not found. |
| `write_file` | `(path: str, content: str) -> str` | Write file, create parent dirs. Return confirmation. |
| `edit_file` | `(path: str, old_str: str, new_str: str) -> str` | Exact string replacement. Error if `old_str` not found or ambiguous (multiple matches). |
| `run_shell` | `(command: str, timeout: int = 30) -> dict` | Run in subprocess, return `{stdout, stderr, exit_code}`. Cwd locked to workspace. |
| `list_files` | `(path: str = ".") -> list[str]` | Recursive listing, respects `.gitignore`. Uses `git ls-files` + untracked. |
| `grep` | `(pattern: str, path: str = ".") -> list[str]` | Search file contents via `grep -rn`. Return matching lines with `file:line` prefix. |

Tools are defined as plain async Python functions. They're converted to OpenAI-format tool schemas for the LLM call and dispatched by name when the LLM returns tool calls.

## 4. Workspace

```python
class Workspace:
    def __init__(self, base_path: str, run_id: str):
        # Creates: {base_path}/{run_id}/
        pass
```

- **Init:** copies target repo contents into workspace dir, runs `git init`, commits everything as "initial state"
- **`get_diff()`** — `git diff` against initial commit (captures all changes this run)
- **`commit_checkpoint(message)`** — `git add -A && git commit`, returns commit hash
- **`run_isolated(command, timeout)`** — subprocess with cwd set to workspace

Run IDs are timestamp-based: `run_YYYYMMDD_HHMMSS` (auto-generated if not provided). Each run is fully isolated.

## 5. OpenRouter Client

Single `OpenRouterClient` class, async with `httpx.AsyncClient`:

```python
class OpenRouterClient:
    def __init__(self, api_key: str, default_model: str = "anthropic/claude-sonnet-4-5"):
        ...

    async def complete(self, messages, system="", model=None, tools=None) -> dict:
        # Standard OpenAI-compatible chat completions
        ...

    async def complete_structured(self, messages, system, response_schema, model=None) -> dict:
        # Forces JSON response matching schema via response_format
        ...
```

- Model selected per-call, defaults from config per node
- Rate limiting with exponential backoff (3 retries)

## 6. Node Details

### spec_loader
No LLM. Reads spec + scenarios files from disk. Initializes state with `cycle: 0`, `max_cycles` from config, empty histories.

### planner
Single LLM call. System prompt describes its role. User message contains the full spec. Returns implementation plan as markdown, including a recommended `test_command`. No tools.

### implementer
Agentic inner loop (see Section 2). On first cycle, receives the plan. On subsequent cycles, receives `steering_prompt` from diagnoser. After exiting, workspace commits a checkpoint.

### test_runner
No LLM. Runs the test command. Priority for test command selection:
1. Config override (`test_command` in `pipeline_config.yaml`)
2. Planner output (`test_command` field)
3. Auto-detect: `pyproject.toml` → `pytest`, `package.json` → `npm test`, `Makefile` → `make test`

Captures stdout/stderr/exit_code. Timeout configurable (default 120s).

### scenario_validator
Single LLM call via `complete_structured()`. Receives: scenarios file, test output, current workspace diff. Returns:
```json
{
  "passed": true/false,
  "satisfaction_score": 0.0-1.0,
  "failing_scenarios": ["scenario names..."],
  "diagnosis": "what went wrong and why"
}
```

### diagnoser
Single LLM call. Receives: validation result, test output, recent diff, original spec. Produces a focused `steering_prompt` for the implementer. Increments `cycle`.

### reviewer
Single LLM call. Only reached on convergence (scenarios pass). Receives: full diff, spec, scenarios. Produces a review report. Informational only.

### done
No LLM. Writes `summary.md` to run directory (cycles taken, satisfaction score, review report, files changed). Final `run_state.json` update with `status: "completed"` or `status: "exhausted"`.

## 7. Configuration

Single `pipeline_config.yaml`:

```yaml
openrouter:
  api_key: ${OPENROUTER_API_KEY}
  models:
    planner: anthropic/claude-sonnet-4-5
    implementer: anthropic/claude-sonnet-4-5
    validator: anthropic/claude-sonnet-4-5
    diagnoser: openai/o3
    reviewer: anthropic/claude-sonnet-4-5

pipeline:
  max_cycles: 10
  loop_detection_window: 10
  tool_output_truncation: 8000
  context_char_limit: 400000  # ~100k tokens at chars/4
  context_truncation_strategy: "middle"
  test_command: null  # override, or let planner/auto-detect decide

workspace:
  base_path: /workspace/runs
  target_repo: /workspace/target

logging:
  level: INFO
  structured: true
  events:
    - CYCLE_START
    - TOOL_CALL_START
    - TOOL_CALL_END
    - NODE_ENTER
    - NODE_EXIT
    - CONVERGENCE
    - LOOP_DETECTED
```

- Loaded via `pyyaml`, validated by Pydantic model at startup
- Env var substitution for `${...}` patterns handled manually
- Immutable after load

## 8. CLI

Entrypoint: `python -m attractor`

```bash
# Run a pipeline
python -m attractor run \
  --spec specs/my-feature.md \
  --scenarios specs/my-feature-scenarios.md \
  --repo /path/to/target/repo \
  --run-id my-feature-001 \
  --config pipeline_config.yaml

# Resume (stubbed — raises NotImplementedError)
python -m attractor resume --run-id my-feature-001

# Show run status
python -m attractor status --run-id my-feature-001
```

- `argparse`-based, no extra dependencies
- `run-id` auto-generated as `run_YYYYMMDD_HHMMSS` if omitted
- `status` reads `run_state.json` and prints formatted summary

## 9. Logging

- `structlog` with JSON output to stdout
- Event types: `CYCLE_START`, `TOOL_CALL_START`, `TOOL_CALL_END`, `NODE_ENTER`, `NODE_EXIT`, `CONVERGENCE`, `LOOP_DETECTED`
- Each entry includes: `run_id`, `cycle`, `node`, `timestamp`
- Also writes to `{run_dir}/run.log`

## 10. Deployment

### Docker

- Python 3.12 slim base
- Non-root user `attractor`
- `git` installed for workspace operations
- Volumes: `/workspace/runs`, `/workspace/specs`, `/workspace/logs`
- `OPENROUTER_API_KEY` required env var
- `docker-compose.yml` mounts local dirs, passes API key from host

### Kubernetes (manifests only)

- `k8s/job-template.yaml` — parameterized Job
- `k8s/configmap.yaml` — pipeline config as ConfigMap
- `k8s/secret-template.yaml` — API key Secret placeholder
- `k8s/pvc.yaml` — workspace PVC
- `k8s/rbac.yaml` — minimal placeholder
- Resource requests: `cpu: 500m, memory: 512Mi`, limits: `cpu: 2, memory: 2Gi`

## 11. Project Structure

```
attractor-py/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── pipeline_config.yaml
├── src/
│   └── attractor/
│       ├── __init__.py
│       ├── __main__.py
│       ├── graph.py
│       ├── state.py
│       ├── nodes/
│       │   ├── __init__.py
│       │   ├── spec_loader.py
│       │   ├── planner.py
│       │   ├── implementer.py
│       │   ├── test_runner.py
│       │   ├── scenario_validator.py
│       │   ├── diagnoser.py
│       │   ├── reviewer.py
│       │   └── done.py
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── file_tools.py
│       │   ├── shell_tools.py
│       │   └── search_tools.py
│       ├── workspace.py
│       ├── openrouter_client.py
│       ├── config.py
│       └── logging.py
├── tests/
│   ├── __init__.py
│   ├── test_tools.py
│   └── test_workspace.py
├── k8s/
│   ├── job-template.yaml
│   ├── configmap.yaml
│   ├── secret-template.yaml
│   ├── pvc.yaml
│   └── rbac.yaml
├── runs/
├── specs/
└── logs/
```

## 12. Dependencies

- `langgraph >= 0.2` — graph execution
- `langchain-core` — message types
- `httpx` — async HTTP for OpenRouter
- `pyyaml` — config loading
- `pydantic` — config/state validation
- `structlog` — structured logging

## 13. What Is NOT Built

- MCP integration
- Web UI or dashboard
- Multi-repo support
- Agent-to-agent communication
- Distributed execution
- `resume` command (stubbed)

## Design Decisions Log

1. **Edge routing:** `scenario_validator → reviewer` on pass, `→ done` only when max_cycles exhausted without passing.
2. **Resume:** Stubbed with `NotImplementedError`. Core loop is priority.
3. **Status:** Lightweight — reads `run_state.json` written after every node transition.
4. **Target repo handling:** Copy + `git init` (not clone). Clean per-run diffs regardless of target's git state.
5. **Context truncation:** Character-based (`chars / 4`), no `tiktoken` dependency. Configurable threshold.
6. **Implementer architecture:** Internal while-loop with state snapshots (Approach C). Same token efficiency as a plain loop, with observability from disk snapshots. No LangGraph subgraph overhead.
