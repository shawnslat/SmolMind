from __future__ import annotations

import shlex
import subprocess
from typing import List, Sequence

from pydantic import BaseModel, Field

from . import ToolContext


SAFE_COMMAND_WHITELIST = {
    "ls",
    "pwd",
    "whoami",
    "uname",
    "date",
    "cat",
    "head",
    "tail",
}


class SafeShellInput(BaseModel):
    command: Sequence[str] | str = Field(
        ..., description="Command to execute. Provide either a string or pre-split list."
    )
    timeout: int = Field(10, ge=1, le=60, description="Maximum execution time in seconds.")


def _normalise_command(command: Sequence[str] | str) -> List[str]:
    if isinstance(command, str):
        parts = shlex.split(command)
    else:
        parts = list(command)
    if not parts:
        raise ValueError("Command cannot be empty.")
    return parts


def safe_shell(params: SafeShellInput, context: ToolContext) -> str:  # noqa: ARG001 (context unused for now)
    parts = _normalise_command(params.command)
    executable = parts[0]
    if executable not in SAFE_COMMAND_WHITELIST:
        raise PermissionError(
            f"Command '{executable}' is not in the safe whitelist: {sorted(SAFE_COMMAND_WHITELIST)}"
        )

    try:
        completed = subprocess.run(
            parts,
            capture_output=True,
            text=True,
            timeout=params.timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"Command '{executable}' timed out after {params.timeout} seconds.")

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if completed.returncode != 0:
        raise RuntimeError(f"Command '{executable}' failed ({completed.returncode}): {stderr}")

    return stdout or "(no output)"


__all__ = ["safe_shell", "SafeShellInput", "SAFE_COMMAND_WHITELIST"]
