"""done node — writes summary and finalizes run state."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from attractor.state import save_run_state

async def done(state: dict[str, Any]) -> dict[str, Any]:
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
        f"# Pipeline Run Summary", "",
        f"**Status:** {status}",
        f"**Cycles used:** {cycles_used} / {max_cycles}",
        f"**Satisfaction score:** {score}",
        f"**Files changed:** {len(diffs)} checkpoint(s)", "",
    ]
    if review:
        summary_lines.extend([f"## Review Report", "", review, ""])
    if not passed:
        failing = validation.get("failing_scenarios", [])
        if failing:
            summary_lines.extend([f"## Failing Scenarios", "", *[f"- {s}" for s in failing], ""])
        diagnosis = validation.get("diagnosis", "")
        if diagnosis:
            summary_lines.extend([f"## Last Diagnosis", "", diagnosis])
    summary_text = "\n".join(summary_lines)
    (ws / "summary.md").write_text(summary_text)
    save_run_state(state, ws / "run_state.json", status=status)
    return {"summary": summary_text}
