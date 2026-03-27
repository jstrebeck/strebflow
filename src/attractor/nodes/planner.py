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
