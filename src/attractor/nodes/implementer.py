"""implementer node — agentic inner loop with tool use."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from attractor.llm_client import LLMClient
from attractor.tools import (
    TOOL_DEFINITIONS, dispatch_tool, truncate_output, hash_tool_args,
)
from attractor.state import save_run_state
from attractor.workspace import Workspace
from attractor.logging import get_logger

IMPLEMENTER_SYSTEM = """You are an expert software engineer implementing a feature in an existing codebase.

You have access to these tools: read_file, write_file, edit_file, run_shell, list_files, grep.

Guidelines:
- Start by exploring the codebase with list_files and read_file to understand the structure
- Write code incrementally — implement, then test
- Use edit_file for targeted changes to existing files, write_file for new files
- If edit_file fails because old_str matches multiple locations, retry with more surrounding context to make it unique. If the file is small, use write_file to replace the entire file instead.
- If a command times out, try breaking it into smaller steps or increasing the timeout parameter.
- If a tool call fails, read the error message carefully and adjust your approach rather than retrying the same call.
- When you are done implementing, stop calling tools and explain what you did."""


def _estimate_tokens(messages: list[dict]) -> int:
    total_chars = sum(len(json.dumps(m)) for m in messages)
    return total_chars // 4


def _truncate_context(messages: list[dict], char_limit: int) -> list[dict]:
    """Keep system + first 2 user messages + last N messages that fit."""
    if not messages:
        return messages
    total_chars = sum(len(json.dumps(m)) for m in messages)
    if total_chars <= char_limit:
        return messages

    keep_start = []
    user_count = 0
    for msg in messages:
        if msg["role"] == "system" or (msg["role"] == "user" and user_count < 2):
            keep_start.append(msg)
            if msg["role"] == "user":
                user_count += 1
        else:
            break
    remaining = messages[len(keep_start):]

    budget = char_limit - sum(len(json.dumps(m)) for m in keep_start)
    keep_end: list[dict] = []
    for msg in reversed(remaining):
        msg_chars = len(json.dumps(msg))
        if budget - msg_chars < 0:
            break
        keep_end.insert(0, msg)
        budget -= msg_chars

    return keep_start + [{"role": "user", "content": "[... earlier context truncated ...]"}] + keep_end


def _detect_loop(history: list[tuple[str, str]], window: int = 10) -> str | None:
    recent = history[-window:]
    if len(recent) < 4:
        return None
    for pattern_len in (2, 3):
        if len(recent) < pattern_len * 2:
            continue
        tail = recent[-pattern_len:]
        prev = recent[-pattern_len * 2 : -pattern_len]
        if tail == prev:
            calls = [f"{name}({args_hash})" for name, args_hash in tail]
            return f"Repeating pattern detected: {' -> '.join(calls)}"
    return None


async def implementer(
    state: dict[str, Any],
    llm: LLMClient,
    model: str,
    context_char_limit: int = 400_000,
    tool_output_truncation: int = 8000,
    loop_detection_window: int = 10,
) -> dict[str, Any]:
    logger = get_logger("attractor.implementer")
    workspace_path = state["workspace_path"]
    ws = Workspace.reopen(workspace_path)

    messages: list[dict] = []
    if state.get("steering_prompt"):
        messages.append({
            "role": "user",
            "content": f"Fix the following issues with the implementation:\n\n{state['steering_prompt']}",
        })
    else:
        messages.append({
            "role": "user",
            "content": f"Implement the following plan:\n\n{state['implementation_plan']}",
        })

    call_tracker: list[tuple[str, str]] = []
    tool_call_history = list(state.get("tool_call_history", []))
    cycle = state.get("cycle", 0)
    logger.info("cycle starting", event_type="CYCLE_START", cycle=cycle)

    while True:
        messages = _truncate_context(messages, context_char_limit)
        response = await llm.complete(
            messages=messages, system=IMPLEMENTER_SYSTEM, model=model, tools=TOOL_DEFINITIONS,
        )
        assistant_msg = response["choices"][0]["message"]
        messages.append(assistant_msg)

        tool_calls = assistant_msg.get("tool_calls")
        if not tool_calls:
            break

        for tc in tool_calls:
            func_name = tc["function"]["name"]
            try:
                func_args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                func_args = {}
            tool_detail = func_args.get("path") or func_args.get("command", "")[:80] or func_args.get("pattern", "")
            logger.info("tool call", event_type="TOOL_CALL_START", tool=func_name, tool_detail=tool_detail)
            full_result = await dispatch_tool(func_name, func_args, workspace_path)
            logger.info("tool done", event_type="TOOL_CALL_END", tool=func_name)
            args_hash = hash_tool_args(func_args)
            call_tracker.append((func_name, args_hash))
            tool_call_history.append({"name": func_name, "args_hash": args_hash, "cycle": cycle})
            truncated_result = truncate_output(full_result, tool_output_truncation)
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": truncated_result})

        loop_msg = _detect_loop(call_tracker, loop_detection_window)
        if loop_msg:
            logger.warning("loop detected", event_type="LOOP_DETECTED", pattern=loop_msg)
            messages.append({
                "role": "user",
                "content": (
                    f"WARNING: {loop_msg}\n"
                    "You appear to be in a loop. Try a completely different approach. "
                    "Consider: reading the error message more carefully, trying a different "
                    "file or method, or using write_file instead of edit_file."
                ),
            })

        save_run_state(
            state | {"tool_call_history": tool_call_history},
            Path(workspace_path) / "run_state.json",
            status="running", node="implementer",
        )

    try:
        diff = ws.get_diff()
        if diff:
            ws.commit_checkpoint(f"implementer cycle {cycle}")
    except Exception:
        diff = ""

    return {
        "tool_call_history": tool_call_history,
        "latest_diff": diff or state.get("latest_diff", ""),
    }
