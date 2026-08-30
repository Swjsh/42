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
    return subprocess.run(cmd, cwd=str(_HERE.parent.parent)).returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
