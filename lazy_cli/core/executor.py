"""Confirmed, shell-free subprocess execution."""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from lazy_cli.core.guardrail import GuardrailVerdict, L1Guardrail

OutputHandler = Callable[[str], None]
_SHELL_OPERATORS = {"|", "||", "&&", ";", ">", ">>", "<", "<<", "`", "$("}


class ExecutionResult(BaseModel):
    command: str
    exit_code: int
    output: str
    timed_out: bool = False


class ExecutionRefused(RuntimeError):
    """Raised when a command cannot be executed under the safe executor policy."""


class SafeExecutor:
    """Execute a single argv command only after guardrails and confirmation pass."""

    def __init__(self, guardrail: L1Guardrail | None = None, timeout_seconds: float = 60.0) -> None:
        self.guardrail = guardrail or L1Guardrail()
        self.timeout_seconds = timeout_seconds

    def preview(self, command: str) -> GuardrailVerdict:
        """Return the deterministic safety verdict used by the execution gate."""
        return self.guardrail.assess(command)

    def execute(self, command: str, working_directory: Path, on_output: OutputHandler | None = None) -> ExecutionResult:
        """Run one command without a shell, streaming combined stdout and stderr."""
        verdict = self.preview(command)
        if verdict.blocked:
            raise ExecutionRefused(f"Blocked by L1 guardrail: {verdict.reason}")
        argv = _parse_argv(command)
        output: list[str] = []
        try:
            with subprocess.Popen(
                argv,
                cwd=working_directory,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            ) as process:
                if process.stdout is None:
                    raise ExecutionRefused("Unable to capture process output.")
                try:
                    for line in process.stdout:
                        output.append(line)
                        if on_output is not None:
                            on_output(line)
                    exit_code = process.wait(timeout=self.timeout_seconds)
                    return ExecutionResult(command=command, exit_code=exit_code, output="".join(output))
                except subprocess.TimeoutExpired:
                    process.kill()
                    remaining_output, _ = process.communicate()
                    output.append(remaining_output)
                    return ExecutionResult(command=command, exit_code=process.returncode or -1, output="".join(output), timed_out=True)
        except OSError as error:
            raise ExecutionRefused(f"Unable to start command: {error}") from error


def _parse_argv(command: str) -> list[str]:
    if any(operator in command for operator in _SHELL_OPERATORS):
        raise ExecutionRefused("Shell operators are not supported; use a single executable command.")
    try:
        argv = shlex.split(command)
    except ValueError as error:
        raise ExecutionRefused("Command has invalid shell-style quoting.") from error
    if not argv:
        raise ExecutionRefused("Command is empty.")
    return argv
