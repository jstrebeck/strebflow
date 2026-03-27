import pytest
import json
from pathlib import Path
from attractor.nodes.spec_loader import spec_loader

@pytest.mark.asyncio
async def test_spec_loader(tmp_path):
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("# My Feature\nBuild a thing.")
    scenarios_file = tmp_path / "scenarios.md"
    scenarios_file.write_text("## Scenario 1\nGiven: setup\nThen: result")
    state = {
        "spec": str(spec_file), "scenarios": str(scenarios_file),
        "workspace_path": "", "implementation_plan": "", "cycle": 0,
        "max_cycles": 10, "steering_prompt": "", "test_output": "",
        "test_exit_code": -1, "test_command": "", "validation_result": {},
        "tool_call_history": [], "diff_history": [], "review_report": "",
        "summary": "",
    }
    result = await spec_loader(state)
    assert "Build a thing" in result["spec"]
    assert "Scenario 1" in result["scenarios"]
    assert result["cycle"] == 0


from attractor.nodes.test_runner import test_runner as run_tests

@pytest.fixture
def workspace_with_pytest(tmp_path):
    import subprocess
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "pyproject.toml").write_text('[project]\nname = "test"\n')
    (ws / "test_sample.py").write_text("def test_pass(): assert True\n")
    subprocess.run(["git", "init"], cwd=ws, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=ws, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=ws, capture_output=True,
        env={**subprocess.os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
    )
    return ws

@pytest.mark.asyncio
async def test_test_runner_with_explicit_command(workspace_with_pytest):
    state = {"test_command": "echo TESTS_PASSED", "workspace_path": str(workspace_with_pytest), "test_output": "", "test_exit_code": -1}
    result = await run_tests(state, test_timeout=30)
    assert result["test_exit_code"] == 0
    assert "TESTS_PASSED" in result["test_output"]

@pytest.mark.asyncio
async def test_test_runner_auto_detects_pytest(workspace_with_pytest):
    state = {"test_command": "", "workspace_path": str(workspace_with_pytest), "test_output": "", "test_exit_code": -1}
    result = await run_tests(state, test_timeout=30)
    assert result["test_command"] == "pytest"


from attractor.nodes.done import done

@pytest.mark.asyncio
async def test_done_writes_summary(tmp_path):
    state = {
        "workspace_path": str(tmp_path), "cycle": 3, "max_cycles": 10,
        "validation_result": {"passed": True, "satisfaction_score": 0.95},
        "review_report": "Looks good. Minor style issues.",
        "diff_history": ["diff1", "diff2", "diff3"],
        "spec": "# Spec", "scenarios": "# Scenarios",
        "implementation_plan": "", "steering_prompt": "",
        "test_output": "", "test_exit_code": 0, "test_command": "pytest",
        "tool_call_history": [], "summary": "",
    }
    result = await done(state)
    assert "summary" in result
    assert "3" in result["summary"]
    assert (tmp_path / "summary.md").exists()
    assert (tmp_path / "run_state.json").exists()
    run_state = json.loads((tmp_path / "run_state.json").read_text())
    assert run_state["status"] == "completed"
