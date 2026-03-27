"""test_runner node — runs the project test suite."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from attractor.workspace import Workspace

def _detect_test_command(workspace_path: str) -> str:
    ws = Path(workspace_path)
    if (ws / "pyproject.toml").exists(): return "pytest"
    if (ws / "package.json").exists(): return "npm test"
    if (ws / "Makefile").exists(): return "make test"
    if (ws / "Cargo.toml").exists(): return "cargo test"
    return "echo 'No test command detected'"

async def test_runner(
    state: dict[str, Any],
    config_test_command: str | None = None,
    test_timeout: int = 120,
) -> dict[str, Any]:
    test_cmd = config_test_command or state.get("test_command") or ""
    if not test_cmd:
        test_cmd = _detect_test_command(state["workspace_path"])
    ws = Workspace.reopen(state["workspace_path"])
    result = await ws.run_isolated(test_cmd, timeout=test_timeout)
    return {
        "test_command": test_cmd,
        "test_output": result["stdout"] + "\n" + result["stderr"],
        "test_exit_code": result["exit_code"],
    }
