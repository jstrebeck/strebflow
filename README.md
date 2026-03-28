# Attractor

A LangGraph-based agentic coding pipeline that takes a spec, implements it, validates against scenarios, and converges autonomously.

Inspired by StrongDM's Attractor concept: a non-interactive coding agent that iterates on implementation until acceptance scenarios pass.

## How it works

Attractor runs a directed graph of phases:

```
spec_loader -> planner -> implementer -> test_runner -> scenario_validator
                                                              |
                                                  +-----------+-----------+
                                                  v           v           v
                                               reviewer    diagnoser     done
                                                  |           |       (exhausted)
                                                  v           v
                                                done      implementer
                                                          (retry loop)
```

1. **spec_loader** reads your spec and scenarios from disk
2. **planner** produces an implementation plan via LLM
3. **implementer** executes the plan using coding tools (read/write/edit files, run shell commands, grep)
4. **test_runner** runs your project's test suite
5. **scenario_validator** checks if the scenarios pass (LLM evaluation)
6. If scenarios fail and cycles remain, **diagnoser** analyzes the failure and steers the implementer to retry
7. On success, **reviewer** produces a code review report
8. **done** writes a summary

The loop continues until scenarios pass or `max_cycles` is exhausted.

## Installation

Requires Python 3.12+ and git.

```bash
pip install -e ".[dev]"
```

## Quick start

### 1. Set your API key

Attractor uses [OpenRouter](https://openrouter.ai) as the default LLM backend. Set your API key:

```bash
export OPENROUTER_API_KEY="your-key-here"
```

### 2. Write a spec

Create a markdown file describing what you want built:

```markdown
# Add a greeting function

Add a Python function `greet(name: str) -> str` in `greeting.py` that returns "Hello, {name}!".

## Requirements
- Function should be in `greeting.py` at the project root
- Should handle empty string input by returning "Hello, World!"
- Should strip whitespace from the name
```

### 3. Write scenarios

Create a scenarios file with acceptance criteria:

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

### 4. Run the pipeline

```bash
python -m attractor run \
  --spec specs/my-feature.md \
  --scenarios specs/my-feature-scenarios.md \
  --repo /path/to/your/project
```

The pipeline creates an isolated workspace (copy of your repo), implements the feature, runs tests, and loops until the scenarios pass.

## CLI reference

### `run` -- Execute a pipeline

```bash
python -m attractor run \
  --spec specs/feature.md \
  --scenarios specs/feature-scenarios.md \
  --repo /path/to/target/repo \
  --run-id my-feature-001 \       # optional, auto-generated if omitted
  --config pipeline_config.yaml    # optional, defaults to pipeline_config.yaml
```

### `status` -- Check a run's progress

```bash
python -m attractor status --run-id my-feature-001
```

Output:
```
Run: my-feature-001
Status: running
Cycle: 3 / 10
Current node: implementer
```

### `resume` -- Resume a failed run

```bash
python -m attractor resume --run-id my-feature-001
```

> Note: `resume` is not yet implemented. It will raise `NotImplementedError`.

## Configuration

All settings are in `pipeline_config.yaml`. The file supports `${ENV_VAR}` substitution.

### LLM providers

Attractor supports any OpenAI-compatible API. Configure one or more providers:

```yaml
llm:
  providers:
    openrouter:
      base_url: https://openrouter.ai/api/v1
      api_key: ${OPENROUTER_API_KEY}
    vastai:
      base_url: ${VASTAI_BASE_URL}
      api_key: ${VASTAI_API_KEY}
```

### Model selection per node

Each pipeline node can use a different model. Model strings are `provider/model-id`:

```yaml
  models:
    planner: openrouter/anthropic/claude-sonnet-4-5
    implementer: openrouter/anthropic/claude-sonnet-4-5
    validator: openrouter/anthropic/claude-sonnet-4-5
    diagnoser: openrouter/openai/o3          # better reasoning for failure analysis
    reviewer: openrouter/anthropic/claude-sonnet-4-5
```

Or mix providers:

```yaml
  models:
    planner: openrouter/anthropic/claude-sonnet-4-5
    implementer: vastai/meta-llama/llama-3.1-70b    # cheaper for coding
    diagnoser: openrouter/openai/o3
```

### Pipeline settings

```yaml
pipeline:
  max_cycles: 10              # max diagnose-implement retry loops
  loop_detection_window: 10   # tool calls to track for loop detection
  tool_output_truncation: 8000 # max chars of tool output sent to LLM
  context_char_limit: 400000  # ~100k tokens; truncate conversation when exceeded
  test_command: null           # override test auto-detection (e.g., "pytest -x")
  test_timeout: 120            # seconds before test run is killed
```

### Workspace

```yaml
workspace:
  base_path: ./runs          # where run workspaces are created
  target_repo: ./target      # default target repo (overridden by --repo)
```

## Docker

### Build and run

```bash
# Build the image
docker compose build

# Place your spec and scenarios in ./specs/
cp my-spec.md specs/spec.md
cp my-scenarios.md specs/scenarios.md

# Place (or symlink) your target repo in ./target/
ln -s /path/to/your/repo target

# Run
OPENROUTER_API_KEY=your-key docker compose up
```

### Custom commands

```bash
docker compose run attractor run \
  --spec /home/attractor/workspace/specs/spec.md \
  --scenarios /home/attractor/workspace/specs/scenarios.md \
  --repo /home/attractor/workspace/target \
  --run-id custom-run-001

docker compose run attractor status --run-id custom-run-001
```

## Kubernetes

Manifests are in `k8s/`. To run the pipeline as a Kubernetes Job:

1. Create the Secret with your API key:
   ```bash
   kubectl create secret generic attractor-secrets \
     --from-literal=openrouter-api-key=your-key
   ```

2. Apply the ConfigMap and PVC:
   ```bash
   kubectl apply -f k8s/configmap.yaml
   kubectl apply -f k8s/pvc.yaml
   ```

3. Create a Job (substitute your values):
   ```bash
   export RUN_ID=my-feature-001
   export SPEC_FILE=spec.md
   export SCENARIOS_FILE=scenarios.md
   envsubst < k8s/job-template.yaml | kubectl apply -f -
   ```

4. Check status:
   ```bash
   kubectl logs job/attractor-my-feature-001 -f
   ```

## Writing specs

Spec files are plain markdown. No special format is required -- the planner LLM reads them as-is. Include:

- What to build (feature description)
- Requirements and constraints
- File paths and function signatures if you have preferences
- Any context the LLM needs about the existing codebase

## Writing scenarios

Scenarios follow a Given/When/Then format with a Validation line:

```markdown
## Scenario N: Descriptive name
Given: [setup conditions]
When: [action taken]
Then: [expected outcome]
Validation: [how to verify -- e.g., "test asserts X equals Y"]
```

The scenario_validator LLM reads these along with test output to determine pass/fail. Be specific in the Validation line -- it helps the validator make accurate judgments.

## Run output

Each run creates a directory under `runs/`:

```
runs/run_20260328_143022/
  run_state.json     # current state (updated after every node)
  run.log            # structured JSON logs
  summary.md         # final summary (cycles, score, review)
  .git/              # git repo with checkpoint commits
```

The workspace is a full copy of your target repo with git history tracking every change the agent made.

## Testing

```bash
# Run the test suite
python -m pytest tests/ -v

# Run a specific test file
python -m pytest tests/test_tools.py -v

# Run tests matching a pattern
python -m pytest tests/ -k "workspace" -v
```

## Architecture

```
src/attractor/
  __init__.py          # package
  __main__.py          # CLI entrypoint
  config.py            # Pydantic config, YAML loading, env var substitution
  logging.py           # structlog setup (JSON to stdout + file)
  state.py             # PipelineState TypedDict, run state serialization
  workspace.py         # git-isolated workspace per run
  llm_client.py        # multi-provider LLM client (OpenRouter, vast.ai, etc.)
  graph.py             # LangGraph StateGraph definition
  nodes/
    spec_loader.py     # read spec + scenarios from disk
    planner.py         # LLM: produce implementation plan
    implementer.py     # LLM + tools: agentic coding loop
    test_runner.py     # run test suite in subprocess
    scenario_validator.py  # LLM: evaluate scenarios
    diagnoser.py       # LLM: analyze failures, steer retry
    reviewer.py        # LLM: code review (post-convergence)
    done.py            # write summary, finalize state
  tools/
    file_tools.py      # read_file, write_file, edit_file
    shell_tools.py     # run_shell
    search_tools.py    # list_files, grep
```
