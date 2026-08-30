"""commit_msgfile.py -- commit_scoped with the message read from a FILE.

SCAR (2026-08-30, twice in one session): commit_scoped.py takes its message as a
positional argument, so a long message has to survive the shell. A message that
mentions a field name in backticks -- which a good commit message routinely does --
becomes COMMAND SUBSTITUTION inside a double-quoted bash argument. The first time it
silently deleted two words from the message. The second time the substituted word
was `label`, which invoked the volume-label prompt and hung the commit forever
waiting on stdin that a non-interactive shell never provides.

The fix is not "remember to escape": it is to stop handing prose to a shell at all.
This wrapper reads the message as bytes from a file the shell never parses and
execs commit_scoped with a real argv list (shell=False), so no character in the
message can ever be interpreted.

    python setup/scripts/commit_msgfile.py <msgfile> <path> [<path>...]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: commit_msgfile.py <msgfile> <path> [<path>...]", file=sys.stderr)
        return 2
    msg_path = Path(argv[0])
    try:
        message = msg_path.read_text(encoding="utf-8").strip()
    except OSError as e:
        print("cannot read message file: %s" % e, file=sys.stderr)
        return 2
    if not message:
        print("message file is empty -- refusing to commit without one", file=sys.stderr)
        return 2
    cmd = [sys.executable, str(_HERE / "commit_scoped.py"), message, *argv[1:]]
    # shell=False is the entire point; do not "simplify" this to a string.
    #
    # CREATE_NO_WINDOW (2026-08-30, J: "first priority is stopping all popups"): sys.executable
    # is console-subsystem python.exe, so spawning it from a parent that has no console --
    # any pythonw/wscript-launched automation, and every Claude Code hook -- makes Windows
    # allocate a fresh console for the child, which the Win11 default-terminal handler paints
    # as a visible window. The child still inherits this process's stdout/stderr handles, so
    # a run from a real terminal is unchanged; only the "invent a new window" path is removed.
    # Flagged by audit_window_leak_compliance.py check (2) PY_SUBPROCESS_NO_CREATIONFLAGS.
    # CREATE_NO_WINDOW + explicit capture (2026-08-30).
    #
    # sys.executable is console-subsystem python.exe, so spawning it from a parent with no
    # console -- any pythonw/wscript automation, and every Claude Code hook -- makes Windows
    # allocate a console for the child, which the Win11 default-terminal handler paints as a
    # visible window. That is the popup the flag removes.
    #
    # The flag is not free: it gives the child a fresh hidden console, so inherited stdio no
    # longer reaches the parent's pipe. Setting it while letting the child inherit (the first
    # version of this change) silently swallowed commit_scoped.py's ENTIRE pre-commit
    # safety-gate report -- the commit was correctly BLOCKED and printed nothing, which reads
    # exactly like a successful no-op. That is the worst possible failure for this tool.
    #
    # Gating on "does this process have a console" does not work either: GetConsoleWindow()
    # returns 0 under a piped shell that can still perfectly well receive output, so the gate
    # picks the swallowing branch in the common developer case. Both were verified by A/B
    # against a real blocked commit.
    #
    # So: keep the flag and stop relying on inheritance. Capture the child's stream and
    # re-emit it here. Output is no longer streamed live, which for a commit wrapper costs
    # nothing -- and no code path can lose it.
    proc = subprocess.run(
        cmd,
        cwd=str(_HERE.parent.parent),
        creationflags=_CREATE_NO_WINDOW,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.stdout:
        sys.stdout.write(proc.stdout)
        sys.stdout.flush()
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
