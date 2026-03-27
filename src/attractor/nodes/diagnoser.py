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
    return {"steering_prompt": steering, "cycle": state["cycle"] + 1}
