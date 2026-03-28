"""Coding tools for the implementer agent.
Provides a registry of tools, their OpenAI-format schemas, and a dispatcher.
"""
from __future__ import annotations
import hashlib
import json
from typing import Any, Callable

from attractor.tools.file_tools import read_file, write_file, edit_file
from attractor.tools.shell_tools import run_shell
from attractor.tools.search_tools import list_files, grep

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {"type": "function", "function": {"name": "read_file", "description": "Read a file relative to the workspace.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "File path relative to workspace root"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "Write content to a file, creating parent directories as needed.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "File path relative to workspace root"}, "content": {"type": "string", "description": "File content to write"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "edit_file", "description": "Replace an exact string in a file. Errors if the string is not found or matches multiple locations.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "File path relative to workspace root"}, "old_str": {"type": "string", "description": "Exact string to find (must be unique in file)"}, "new_str": {"type": "string", "description": "Replacement string"}}, "required": ["path", "old_str", "new_str"]}}},
    {"type": "function", "function": {"name": "run_shell", "description": "Run a shell command in the workspace directory.", "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "Shell command to execute"}, "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)", "default": 30}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "list_files", "description": "List files recursively in the workspace, respecting .gitignore. Capped at 500 entries.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Subdirectory to list (default: root)", "default": "."}}, "required": []}}},
    {"type": "function", "function": {"name": "grep", "description": "Search file contents for a regex pattern.", "parameters": {"type": "object", "properties": {"pattern": {"type": "string", "description": "Search pattern (regex)"}, "path": {"type": "string", "description": "Subdirectory to search (default: root)", "default": "."}}, "required": ["pattern"]}}},
]

_TOOL_FUNCTIONS: dict[str, Callable] = {
    "read_file": read_file, "write_file": write_file, "edit_file": edit_file,
    "run_shell": run_shell, "list_files": list_files, "grep": grep,
}

async def dispatch_tool(name: str, arguments: dict[str, Any], workspace: str) -> str:
    func = _TOOL_FUNCTIONS.get(name)
    if func is None: return f"Error: unknown tool '{name}'"
    result = await func(**arguments, workspace=workspace)
    if isinstance(result, dict): return json.dumps(result, indent=2)
    if isinstance(result, list): return "\n".join(str(item) for item in result)
    return str(result)

def truncate_output(output: str, max_chars: int = 8000) -> str:
    if len(output) <= max_chars: return output
    half = max_chars // 2
    return output[:half] + "\n... [truncated] ...\n" + output[-half:]

def hash_tool_args(args: dict[str, Any]) -> str:
    serialized = json.dumps(args, sort_keys=True)
    return hashlib.md5(serialized.encode()).hexdigest()[:12]
