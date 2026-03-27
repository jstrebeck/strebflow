"""File manipulation tools for the implementer agent."""
from __future__ import annotations
from pathlib import Path

def _validate_path(file_path: str, workspace: str) -> Path | str:
    """Resolve path and validate it's within the workspace."""
    ws = Path(workspace).resolve()
    target = (ws / file_path).resolve()
    if not str(target).startswith(str(ws)):
        return f"Error: path '{file_path}' resolves outside the workspace"
    return target

async def read_file(path: str, workspace: str) -> str:
    target = _validate_path(path, workspace)
    if isinstance(target, str): return target
    if not target.is_file(): return f"Error: file '{path}' not found"
    try: return target.read_text()
    except Exception as e: return f"Error reading '{path}': {e}"

async def write_file(path: str, content: str, workspace: str) -> str:
    target = _validate_path(path, workspace)
    if isinstance(target, str): return target
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e: return f"Error writing '{path}': {e}"

async def edit_file(path: str, old_str: str, new_str: str, workspace: str) -> str:
    target = _validate_path(path, workspace)
    if isinstance(target, str): return target
    if not target.is_file(): return f"Error: file '{path}' not found"
    content = target.read_text()
    count = content.count(old_str)
    if count == 0: return f"Error: old_str not found in '{path}'"
    if count > 1: return f"Error: old_str is ambiguous — found {count} matches in '{path}'. Use more surrounding context to make it unique."
    new_content = content.replace(old_str, new_str, 1)
    target.write_text(new_content)
    return f"Edited {path}: replaced 1 occurrence"
