"""Workspace management for isolated pipeline runs."""
from __future__ import annotations
import asyncio
import shutil
import subprocess
from pathlib import Path

class Workspace:
    """An isolated workspace for a single pipeline run."""

    def __init__(self, base_path: str, run_id: str, target_repo: str) -> None:
        self.base_path = Path(base_path)
        self.run_id = run_id
        self.path = str(self.base_path / run_id)
        self._ws = Path(self.path)

        # Copy target repo contents into workspace
        if self._ws.exists():
            shutil.rmtree(self._ws)
        shutil.copytree(target_repo, self.path, dirs_exist_ok=False)

        # Initialize git repo with initial commit
        self._git("init")
        self._git("add", "-A")
        self._git("commit", "-m", "initial state", "--allow-empty")
        self._initial_commit = self._git("rev-parse", "HEAD")

    def _git(self, *args: str) -> str:
        """Run a git command in the workspace."""
        result = subprocess.run(
            ["git", *args],
            cwd=self.path,
            capture_output=True,
            text=True,
            env={
                **subprocess.os.environ,
                "GIT_AUTHOR_NAME": "attractor",
                "GIT_AUTHOR_EMAIL": "attractor@local",
                "GIT_COMMITTER_NAME": "attractor",
                "GIT_COMMITTER_EMAIL": "attractor@local",
            },
        )
        if result.returncode != 0 and "nothing to commit" not in result.stdout:
            if result.returncode != 0 and "nothing to commit" not in result.stderr:
                raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
        return result.stdout.strip()

    def get_diff(self) -> str:
        """Get the diff of all changes since initial commit."""
        return self._git("diff", self._initial_commit)

    def commit_checkpoint(self, message: str) -> str:
        """Commit all changes and return the commit hash."""
        self._git("add", "-A")
        self._git("commit", "-m", message, "--allow-empty")
        return self._git("rev-parse", "HEAD")

    @classmethod
    def reopen(cls, workspace_path: str) -> "Workspace":
        """Reopen an existing workspace without copying/reinitializing."""
        ws = cls.__new__(cls)
        ws.path = workspace_path
        ws._ws = Path(workspace_path)
        ws._initial_commit = ws._git("rev-list", "--max-parents=0", "HEAD")
        return ws

    async def run_isolated(self, command: str, timeout: int = 120) -> dict:
        """Run a command in the workspace directory."""
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=self.path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            return {
                "stdout": stdout_bytes.decode(errors="replace"),
                "stderr": stderr_bytes.decode(errors="replace"),
                "exit_code": proc.returncode or 0,
            }
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return {
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
                "exit_code": -1,
            }
