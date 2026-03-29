"""spec_loader node — reads spec and scenarios from disk."""
from __future__ import annotations
from pathlib import Path
from typing import Any

async def spec_loader(state: dict[str, Any]) -> dict[str, Any]:
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
        "latest_diff": "",
        "validation_result": {},
        "review_report": "",
        "summary": "",
    }
