"""Shell execution tool for the implementer agent."""
from __future__ import annotations
import asyncio
from pathlib import Path

async def run_shell(command: str, workspace: str, timeout: int = 30) -> dict:
    ws = Path(workspace).resolve()
    try:
        proc = await asyncio.create_subprocess_shell(
            command, cwd=str(ws),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {"stdout": stdout_bytes.decode(errors="replace"), "stderr": stderr_bytes.decode(errors="replace"), "exit_code": proc.returncode or 0}
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return {"stdout": "", "stderr": f"Command timed out after {timeout}s", "exit_code": -1}
