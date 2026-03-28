"""Search tools for the implementer agent."""
from __future__ import annotations
import subprocess
from pathlib import Path

MAX_LIST_FILES = 500

async def list_files(path: str, workspace: str) -> list[str]:
    ws = Path(workspace).resolve()
    target = (ws / path).resolve()
    if not str(target).startswith(str(ws)):
        return [f"Error: path '{path}' resolves outside the workspace"]
    try:
        result = subprocess.run(["git", "ls-files"], cwd=str(target), capture_output=True, text=True)
        tracked = set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()
        result = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=str(target), capture_output=True, text=True)
        untracked = set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()
        all_files = sorted((tracked | untracked) - {""})
        if len(all_files) > MAX_LIST_FILES:
            return all_files[:MAX_LIST_FILES] + [f"... and {len(all_files) - MAX_LIST_FILES} more files (capped at {MAX_LIST_FILES})"]
        return all_files
    except Exception as e:
        return [f"Error listing files: {e}"]

async def grep(pattern: str, path: str, workspace: str) -> list[str]:
    ws = Path(workspace).resolve()
    target = (ws / path).resolve()
    if not str(target).startswith(str(ws)):
        return [f"Error: path '{path}' resolves outside the workspace"]
    try:
        # Use plain grep to find uncommitted/unstaged files too
        result = subprocess.run(
            ["grep", "-rn", "--exclude-dir=.git", pattern, str(target)],
            capture_output=True, text=True,
        )
        if result.returncode == 1: return []
        lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
        # Make paths relative to workspace
        ws_str = str(ws) + "/"
        return [line.replace(ws_str, "") for line in lines]
    except Exception as e:
        return [f"Error searching: {e}"]
