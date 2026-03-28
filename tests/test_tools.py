import pytest
from pathlib import Path
from attractor.tools.file_tools import read_file, write_file, edit_file

@pytest.fixture
def workspace_dir(tmp_path):
    """Create a workspace directory with git init."""
    import subprocess
    ws = tmp_path / "workspace"
    ws.mkdir()
    subprocess.run(["git", "init"], cwd=ws, capture_output=True)
    (ws / "existing.py").write_text("line1\nline2\nline3\n")
    (ws / ".gitignore").write_text("__pycache__/\n*.pyc\n")
    return ws

# --- read_file ---
@pytest.mark.asyncio
async def test_read_file(workspace_dir):
    result = await read_file("existing.py", str(workspace_dir))
    assert "line1" in result
    assert "line2" in result

@pytest.mark.asyncio
async def test_read_file_not_found(workspace_dir):
    result = await read_file("nonexistent.py", str(workspace_dir))
    assert "error" in result.lower()

@pytest.mark.asyncio
async def test_read_file_rejects_path_traversal(workspace_dir):
    result = await read_file("../../etc/passwd", str(workspace_dir))
    assert "error" in result.lower()

# --- write_file ---
@pytest.mark.asyncio
async def test_write_file(workspace_dir):
    result = await write_file("new_file.py", "hello = 1\n", str(workspace_dir))
    assert "wrote" in result.lower() or "created" in result.lower()
    assert (workspace_dir / "new_file.py").read_text() == "hello = 1\n"

@pytest.mark.asyncio
async def test_write_file_creates_dirs(workspace_dir):
    result = await write_file("sub/dir/file.py", "x = 1\n", str(workspace_dir))
    assert (workspace_dir / "sub" / "dir" / "file.py").exists()

# --- edit_file ---
@pytest.mark.asyncio
async def test_edit_file(workspace_dir):
    result = await edit_file("existing.py", "line2", "LINE_TWO", str(workspace_dir))
    content = (workspace_dir / "existing.py").read_text()
    assert "LINE_TWO" in content
    assert "line2" not in content

@pytest.mark.asyncio
async def test_edit_file_not_found(workspace_dir):
    result = await edit_file("existing.py", "nonexistent_string", "replacement", str(workspace_dir))
    assert "error" in result.lower() or "not found" in result.lower()

@pytest.mark.asyncio
async def test_edit_file_ambiguous(workspace_dir):
    (workspace_dir / "dup.py").write_text("foo\nfoo\nbar\n")
    result = await edit_file("dup.py", "foo", "baz", str(workspace_dir))
    assert "ambiguous" in result.lower() or "multiple" in result.lower()

# --- run_shell ---
from attractor.tools.shell_tools import run_shell

@pytest.mark.asyncio
async def test_run_shell(workspace_dir):
    result = await run_shell("echo hello", str(workspace_dir))
    assert result["stdout"].strip() == "hello"
    assert result["exit_code"] == 0

@pytest.mark.asyncio
async def test_run_shell_captures_stderr(workspace_dir):
    result = await run_shell("echo err >&2", str(workspace_dir))
    assert "err" in result["stderr"]

@pytest.mark.asyncio
async def test_run_shell_timeout(workspace_dir):
    result = await run_shell("sleep 10", str(workspace_dir), timeout=1)
    assert result["exit_code"] != 0

# --- list_files ---
from attractor.tools.search_tools import list_files, grep

@pytest.mark.asyncio
async def test_list_files(workspace_dir):
    import subprocess
    subprocess.run(["git", "add", "-A"], cwd=workspace_dir, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init", "--allow-empty"],
        cwd=workspace_dir, capture_output=True,
        env={**subprocess.os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t"},
    )
    files = await list_files(".", str(workspace_dir))
    assert "existing.py" in files
    assert ".gitignore" in files

# --- grep ---
@pytest.mark.asyncio
async def test_grep(workspace_dir):
    # grep uses plain grep, no git commit needed
    results = await grep("line2", ".", str(workspace_dir))
    assert any("existing.py" in r and "line2" in r for r in results)

@pytest.mark.asyncio
async def test_grep_no_match(workspace_dir):
    results = await grep("nonexistent_pattern_xyz", ".", str(workspace_dir))
    assert results == []
