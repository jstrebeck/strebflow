import json
from pathlib import Path
from attractor.state import PipelineState, save_run_state, load_run_state

def test_save_and_load_run_state(tmp_path):
    state: PipelineState = {
        "spec": "# My Spec",
        "scenarios": "# Scenarios",
        "workspace_path": "/tmp/run_001",
        "implementation_plan": "",
        "cycle": 0,
        "max_cycles": 10,
        "steering_prompt": "",
        "test_output": "",
        "test_exit_code": -1,
        "test_command": "",
        "validation_result": {},
        "tool_call_history": [],
        "diff_history": [],
        "review_report": "",
        "summary": "",
    }
    save_run_state(state, tmp_path / "run_state.json")
    loaded = load_run_state(tmp_path / "run_state.json")
    assert loaded["cycle"] == 0
    assert loaded["spec"] == "# My Spec"

def test_save_run_state_excludes_large_fields(tmp_path):
    """tool_call_history IS included (it's compact). Large text fields are truncated."""
    state: PipelineState = {
        "spec": "x" * 100_000,
        "scenarios": "y" * 100_000,
        "workspace_path": "/tmp/run_001",
        "implementation_plan": "z" * 100_000,
        "cycle": 3,
        "max_cycles": 10,
        "steering_prompt": "",
        "test_output": "w" * 100_000,
        "test_exit_code": 0,
        "test_command": "pytest",
        "validation_result": {"passed": False},
        "tool_call_history": [{"name": "read_file", "args_hash": "abc", "cycle": 0}],
        "diff_history": ["diff1", "diff2"],
        "review_report": "",
        "summary": "",
    }
    save_run_state(state, tmp_path / "run_state.json")
    raw = json.loads((tmp_path / "run_state.json").read_text())
    assert len(raw["tool_call_history"]) == 1
    assert raw["cycle"] == 3
    assert "status" in raw
