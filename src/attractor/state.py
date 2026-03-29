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
    latest_diff: str
    review_report: str
    summary: str

# Fields to truncate in run_state.json (keep first 500 chars)
_TRUNCATE_FIELDS = {"spec", "scenarios", "implementation_plan", "test_output", "steering_prompt", "latest_diff"}
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
