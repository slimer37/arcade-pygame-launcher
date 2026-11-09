"""Discovering and running the programs the launcher offers."""

import os
import subprocess
import sys

ERROR_TAIL_LINES = 15


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


def run_program(python, script):
    """Run a script to completion. Returns (exit_code, error_text or None)."""
    try:
        proc = subprocess.run([python, script], cwd=os.path.dirname(script),
                              stderr=subprocess.PIPE, check=False)
    except OSError as exc:
        return None, f"Could not start program: {exc}"
    stderr = proc.stderr.decode(errors="replace")
    if stderr:
        sys.stderr.write(stderr)  # keep it visible in the console/journal too
    if proc.returncode == 0:
        return 0, None
    lines = stderr.strip().splitlines()[-ERROR_TAIL_LINES:]
    if proc.returncode < 0 and not lines:
        lines = [f"Terminated by signal {-proc.returncode}"]
    return proc.returncode, "\n".join(lines) or "(no error output)"
