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
        "tool_call_history": [], "latest_diff": "", "review_report": "",
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
        "latest_diff": "diff3",
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


from unittest.mock import AsyncMock
from attractor.nodes.planner import planner
from attractor.nodes.scenario_validator import scenario_validator
from attractor.nodes.diagnoser import diagnoser
from attractor.nodes.reviewer import reviewer

def _make_mock_llm(content: str) -> AsyncMock:
    """Create a mock LLMClient that returns the given content."""
    mock = AsyncMock()
    mock.complete.return_value = {
        "choices": [{"message": {"role": "assistant", "content": content}}],
    }
    mock.complete_structured.return_value = {
        "choices": [{"message": {"role": "assistant", "content": content}}],
    }
    return mock

@pytest.mark.asyncio
async def test_planner_extracts_plan_and_test_command():
    mock_llm = _make_mock_llm('{"implementation_plan": "Step 1: do stuff", "test_command": "pytest"}')
    state = {"spec": "# Build a thing", "scenarios": "", "workspace_path": "", "implementation_plan": "", "cycle": 0, "max_cycles": 10, "steering_prompt": "", "test_output": "", "test_exit_code": -1, "test_command": "", "validation_result": {}, "tool_call_history": [], "diff_history": [], "review_report": "", "summary": ""}
    result = await planner(state, llm=mock_llm, model="openrouter/test-model")
    assert result["implementation_plan"] == "Step 1: do stuff"
    assert result["test_command"] == "pytest"
    mock_llm.complete_structured.assert_called_once()

@pytest.mark.asyncio
async def test_scenario_validator_returns_structured_result(tmp_path):
    # Need a real git workspace for Workspace.reopen()
    import subprocess
    ws = tmp_path / "validator_ws"
    ws.mkdir()
    (ws / "file.py").write_text("x = 1\n")
    subprocess.run(["git", "init"], cwd=ws, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=ws, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=ws, capture_output=True,
        env={**subprocess.os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})

    mock_llm = _make_mock_llm('{"passed": true, "satisfaction_score": 0.95, "failing_scenarios": [], "diagnosis": ""}')
    state = {"spec": "", "scenarios": "## Scenario 1", "workspace_path": str(ws), "implementation_plan": "", "cycle": 0, "max_cycles": 10, "steering_prompt": "", "test_output": "all passed", "test_exit_code": 0, "test_command": "pytest", "validation_result": {}, "tool_call_history": [], "diff_history": ["some diff"], "review_report": "", "summary": ""}
    result = await scenario_validator(state, llm=mock_llm, model="openrouter/test-model")
    assert result["validation_result"]["passed"] is True
    assert result["validation_result"]["satisfaction_score"] == 0.95

@pytest.mark.asyncio
async def test_diagnoser_increments_cycle():
    mock_llm = _make_mock_llm("Fix the bug in main.py line 10")
    state = {"spec": "# Spec", "scenarios": "", "workspace_path": "", "implementation_plan": "", "cycle": 2, "max_cycles": 10, "steering_prompt": "", "test_output": "FAILED", "test_exit_code": 1, "test_command": "pytest", "validation_result": {"passed": False, "diagnosis": "test failed"}, "tool_call_history": [], "latest_diff": "diff", "review_report": "", "summary": ""}
    result = await diagnoser(state, llm=mock_llm, model="openrouter/test-model")
    assert result["cycle"] == 3
    assert "Fix the bug" in result["steering_prompt"]

@pytest.mark.asyncio
async def test_reviewer_returns_report():
    mock_llm = _make_mock_llm("Code looks good. Minor: add docstrings.")
    state = {"spec": "# Spec", "scenarios": "## Scenario 1", "workspace_path": "", "implementation_plan": "", "cycle": 1, "max_cycles": 10, "steering_prompt": "", "test_output": "", "test_exit_code": 0, "test_command": "pytest", "validation_result": {"passed": True}, "tool_call_history": [], "latest_diff": "diff content", "review_report": "", "summary": ""}
    result = await reviewer(state, llm=mock_llm, model="openrouter/test-model")
    assert "docstrings" in result["review_report"]


from attractor.nodes.implementer import implementer, _detect_loop, _truncate_context

def test_detect_loop_no_pattern():
    history = [("read_file", "a"), ("write_file", "b"), ("run_shell", "c")]
    assert _detect_loop(history) is None

def test_detect_loop_pattern_len_2():
    history = [("read_file", "a"), ("write_file", "b"), ("read_file", "a"), ("write_file", "b")]
    assert _detect_loop(history) is not None

def test_detect_loop_pattern_len_3():
    history = [("a", "1"), ("b", "2"), ("c", "3"), ("a", "1"), ("b", "2"), ("c", "3")]
    assert _detect_loop(history) is not None

def test_truncate_context_under_limit():
    msgs = [{"role": "system", "content": "hi"}, {"role": "user", "content": "hello"}]
    result = _truncate_context(msgs, 100_000)
    assert len(result) == 2

def test_truncate_context_over_limit():
    msgs = [{"role": "system", "content": "sys"}]
    msgs += [{"role": "user", "content": "x" * 1000}]
    msgs += [{"role": "assistant", "content": f"msg{i}"} for i in range(50)]
    result = _truncate_context(msgs, 2000)
    assert result[0]["role"] == "system"
    assert result[1]["role"] == "user"
    assert "[... earlier context truncated ...]" in result[2]["content"]
    assert len(result) < len(msgs)

@pytest.mark.asyncio
async def test_implementer_single_round_no_tools(tmp_path):
    """LLM returns no tool calls — implementer exits immediately."""
    import subprocess
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    (ws_dir / "file.py").write_text("x = 1\n")
    subprocess.run(["git", "init"], cwd=ws_dir, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=ws_dir, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=ws_dir, capture_output=True,
        env={**subprocess.os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
    )
    mock_llm = _make_mock_llm("I have reviewed the code and no changes are needed.")
    state = {
        "spec": "# Spec", "scenarios": "", "workspace_path": str(ws_dir),
        "implementation_plan": "Step 1: review code", "cycle": 0, "max_cycles": 10,
        "steering_prompt": "", "test_output": "", "test_exit_code": -1,
        "test_command": "", "validation_result": {}, "tool_call_history": [],
        "diff_history": [], "review_report": "", "summary": "",
    }
    result = await implementer(state, llm=mock_llm, model="openrouter/test-model")
    assert isinstance(result["tool_call_history"], list)
    assert isinstance(result["diff_history"], list)
