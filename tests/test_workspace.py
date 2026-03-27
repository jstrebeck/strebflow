import pytest
from pathlib import Path
from attractor.workspace import Workspace

@pytest.fixture
def target_repo(tmp_path):
    """Create a fake target repo with some files."""
    target = tmp_path / "target"
    target.mkdir()
    (target / "main.py").write_text("print('hello')\n")
    (target / "lib").mkdir()
    (target / "lib" / "utils.py").write_text("def add(a, b): return a + b\n")
    return target

@pytest.fixture
def workspace(tmp_path, target_repo):
    return Workspace(
        base_path=str(tmp_path / "runs"),
        run_id="test_run_001",
        target_repo=str(target_repo),
    )

def test_workspace_init_copies_files(workspace):
    ws_path = Path(workspace.path)
    assert (ws_path / "main.py").exists()
    assert (ws_path / "lib" / "utils.py").exists()

def test_workspace_init_creates_git_repo(workspace):
    ws_path = Path(workspace.path)
    assert (ws_path / ".git").is_dir()

def test_workspace_get_diff_empty_initially(workspace):
    assert workspace.get_diff() == ""

def test_workspace_get_diff_after_modification(workspace):
    ws_path = Path(workspace.path)
    (ws_path / "main.py").write_text("print('modified')\n")
    diff = workspace.get_diff()
    assert "modified" in diff
    assert "hello" in diff

def test_workspace_commit_checkpoint(workspace):
    ws_path = Path(workspace.path)
    (ws_path / "new_file.py").write_text("x = 1\n")
    commit_hash = workspace.commit_checkpoint("add new file")
    assert len(commit_hash) == 40  # full SHA

@pytest.mark.asyncio
async def test_workspace_run_isolated(workspace):
    result = await workspace.run_isolated("echo hello")
    assert result["stdout"].strip() == "hello"
    assert result["exit_code"] == 0

@pytest.mark.asyncio
async def test_workspace_run_isolated_timeout(workspace):
    result = await workspace.run_isolated("sleep 10", timeout=1)
    assert result["exit_code"] != 0
    assert "timeout" in result["stderr"].lower() or result["exit_code"] == -1
