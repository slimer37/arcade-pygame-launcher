"""Discovering and running the programs the launcher offers."""

import os
import subprocess
import sys
from dataclasses import dataclass

ERROR_TAIL_LINES = 15
ERROR_TAIL_CHARS = 2000  # also cap characters, in case of very long lines


@dataclass(frozen=True)
class ProgramResult:
    """Outcome of running a program."""

    name: str
    exit_code: int | None  # None if the program could not be started
    error: str | None = None  # error output (tail of stderr) if it failed

    @property
    def failed(self) -> bool:
        return self.error is not None

    @property
    def summary(self) -> str:
        if self.exit_code is None:
            return f"'{self.name}' could not be started"
        return f"'{self.name}' exited with code {self.exit_code}"


def find_programs(script_dir):
    """Return a sorted list of (name, script_path).

    A program is either a top-level ``*.py`` file or a sub-directory that
    contains a ``main.py`` (for games that ship with their own assets).
    """
    programs = []
    if not os.path.isdir(script_dir):
        return programs
    for entry in os.listdir(script_dir):
        path = os.path.join(script_dir, entry)
        if os.path.isfile(path) and entry.endswith(".py"):
            programs.append((entry[:-3], path))
        elif os.path.isdir(path) and os.path.isfile(os.path.join(path, "main.py")):
            programs.append((entry, os.path.join(path, "main.py")))
    programs.sort(key=lambda p: p[0].lower())
    return programs


def run_program(name, python, script) -> ProgramResult:
    """Run a script to completion and report how it ended."""
    try:
        proc = subprocess.run([python, script], cwd=os.path.dirname(script),
                              stderr=subprocess.PIPE, check=False)
    except OSError as exc:
        return ProgramResult(name, None, f"Could not start program: {exc}")
    stderr = proc.stderr.decode(errors="replace")
    if stderr:
        sys.stderr.write(stderr)  # keep it visible in the console/journal too
    if proc.returncode == 0:
        return ProgramResult(name, 0)
    lines = stderr.strip().splitlines()[-ERROR_TAIL_LINES:]
    if proc.returncode < 0 and not lines:
        lines = [f"Terminated by signal {-proc.returncode}"]
    error = "\n".join(lines)[-ERROR_TAIL_CHARS:]
    return ProgramResult(name, proc.returncode, error or "(no error output)")
