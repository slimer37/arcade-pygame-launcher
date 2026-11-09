"""Discovering and running the programs the launcher offers."""

import os
import subprocess
import sys
import threading
from dataclasses import dataclass

ERROR_TAIL_LINES = 15
ERROR_TAIL_CHARS = 2000  # also cap characters, in case of very long lines
IDLE_INTERVAL = 0.1  # seconds between idle() calls while a program runs
README_MAX_CHARS = 10000  # more than fits on screen anyway


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


@dataclass(frozen=True)
class Program:
    """A launchable game: a folder with a main.py and optional README.md."""

    name: str
    script: str
    readme: str | None = None  # contents of the folder's README.md, if any

    @property
    def description(self) -> str:
        return self.readme or f"Play {self.name}"


def read_readme(folder):
    """Return the text of folder's README.md (any capitalisation), or None."""
    for entry in os.listdir(folder):
        path = os.path.join(folder, entry)
        if entry.lower() == "readme.md" and os.path.isfile(path):
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    return f.read(README_MAX_CHARS).strip() or None
            except OSError:
                return None
    return None


def find_programs(script_dir) -> list[Program]:
    """Return the programs in script_dir, sorted by name.

    A program is a sub-directory of script_dir that contains a ``main.py``;
    the directory name is the program's name. Anything else is ignored.
    """
    programs = []
    if not os.path.isdir(script_dir):
        return programs
    for entry in os.listdir(script_dir):
        folder = os.path.join(script_dir, entry)
        script = os.path.join(folder, "main.py")
        if os.path.isfile(script):
            programs.append(Program(entry, script, read_readme(folder)))
    programs.sort(key=lambda p: p.name.lower())
    return programs


def run_program(name, python, script, idle=None, env=None) -> ProgramResult:
    """Run a script to completion and report how it ended.

    ``idle`` (if given) is called roughly every IDLE_INTERVAL seconds while
    the program runs, e.g. to keep the launcher's window responsive.
    """
    try:
        proc = subprocess.Popen([python, script], cwd=os.path.dirname(script),
                                stderr=subprocess.PIPE, env=env)
    except OSError as exc:
        return ProgramResult(name, None, f"Could not start program: {exc}")
    # Collect stderr on a thread so a chatty program can't fill the pipe and
    # stall while this thread is busy calling idle().
    output = []
    reader = threading.Thread(target=lambda: output.append(proc.communicate()[1]),
                              daemon=True)
    reader.start()
    while reader.is_alive():
        if idle is not None:
            idle()
        reader.join(IDLE_INTERVAL)
    stderr = output[0].decode(errors="replace")
    if stderr:
        sys.stderr.write(stderr)  # keep it visible in the console/journal too
    if proc.returncode == 0:
        return ProgramResult(name, 0)
    lines = stderr.strip().splitlines()[-ERROR_TAIL_LINES:]
    if proc.returncode < 0 and not lines:
        lines = [f"Terminated by signal {-proc.returncode}"]
    error = "\n".join(lines)[-ERROR_TAIL_CHARS:]
    return ProgramResult(name, proc.returncode, error or "(no error output)")
