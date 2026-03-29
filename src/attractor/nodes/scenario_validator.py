"""scenario_validator node — evaluates scenarios against test results."""
from __future__ import annotations
import json
from typing import Any
from attractor.llm_client import LLMClient
from attractor.workspace import Workspace

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

_MAX_DIFF_CHARS = 200_000
_MAX_TEST_OUTPUT_CHARS = 50_000


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + "\n\n[... truncated ...]\n\n" + text[-half:]


async def scenario_validator(state: dict[str, Any], llm: LLMClient, model: str) -> dict[str, Any]:
    try:
        ws = Workspace.reopen(state["workspace_path"])
        current_diff = ws.get_diff() or "No changes from initial state"
    except Exception:
        current_diff = "Unable to compute diff"
    user_content = f"""## Scenarios
{state['scenarios']}

## Test Output (exit code: {state['test_exit_code']})
{_truncate(state['test_output'], _MAX_TEST_OUTPUT_CHARS)}

## Code Diff (cumulative from initial state)
{_truncate(current_diff, _MAX_DIFF_CHARS)}"""
    response = await llm.complete_structured(
        messages=[{"role": "user", "content": user_content}],
        system=VALIDATOR_SYSTEM,
        response_schema=VALIDATOR_SCHEMA,
        model=model,
    )
    content = response["choices"][0]["message"]["content"]
    validation_result = json.loads(content)
    return {"validation_result": validation_result}
