"""status_known_broken.py -- one shared, de-duplicating writer for STATUS.md's
'## Known broken' section.

THE BUG (found live 2026-09-03T00:55 ET): several producers each APPEND one line
per fire to '## Known broken' and never clear or de-duplicate. Live evidence at the
time this module was written: the section carried 8 `ROSTER-LIVENESS: ...` lines
(2026-09-02T05:37Z through 16:40Z, all for the same recurring dead-lane condition)
and 5 `MCP_AUDIT_*` lines (4 YELLOW 06:23-23:50 ET plus a newer RED at
2026-09-03T00:03:45 ET) -- one even reading "All MCP servers healthy" sitting in
the SAME broken list as three other stale reads of the identical condition. A
section that grows one line per fire is unreadable within a day and trains every
reader (human or automated) to skip it -- the same C7/2026-08-20 scar class this
project has hit before (see status_retention.py's PINNED_SECTIONS docstring and
guard_runner_full.py's FULL-SUITE-RED-LINE-OUTLIVES-GREEN fix, which this module
generalizes from one caller to any caller).

WHAT THIS PROVIDES
  upsert(marker, line, *, status_path=STATUS_PATH) -- bounded to the '## Known
  broken' section BODY only (never a copy of a marker-prefixed line that has
  already rolled into an older dated '## [' entry elsewhere in the file -- that is
  history, not the live channel). Removes every existing bullet line in the
  section whose text after its '- [timestamp] ' prefix starts with `marker`
  (e.g. 'ROSTER-LIVENESS:' or 'MCP_AUDIT_' -- the latter deliberately matches
  MCP_AUDIT_RED/_YELLOW/_GREEN as ONE dedup key, since they are all readings of
  the same underlying probe). If `line` is given, the caller's fully-formed
  bullet (its own '- [ts] ...' prefix included) is inserted at the TOP of the
  section, replacing whatever was there for that marker. If `line` is None (a
  green/recovered reading), nothing is inserted -- the marker is simply cleared.

  Recreates the section at the top of the file if missing, for the same reason
  guard_runner_full.py does: a report that goes nowhere manufactures the false
  belief that something is watching (the June 2026 outage this project already
  paid for once).

  Preserves the file's line-ending convention (CRLF or LF) exactly as found, and
  leaves every byte outside the section untouched. Never raises to the caller --
  any failure is logged to stderr and treated as a no-op (fail-open, OP-25).

CLI (for non-Python callers -- e.g. a PowerShell script, or an LLM-driven prompt
that only knows how to shell out):
    python setup/scripts/status_known_broken.py --marker "MCP_AUDIT_" --line "- [2026-09-03T01:00:00 ET] MCP_AUDIT_RED: reason text"
    python setup/scripts/status_known_broken.py --marker "MCP_AUDIT_" --clear
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
STATUS_PATH = REPO_ROOT / "automation" / "overnight" / "STATUS.md"
MARKER_HEADING = "## Known broken"

# A section-body bullet line: '- [<anything but ]/newline>] <rest of line>'.
# Matches the shape every current producer writes (roster_liveness.py,
# guard_runner_full.py's FULL-SUITE line, twin_gauntlet_conductor_hook.py, etc).
_BULLET_LINE_RE = re.compile(r"^- \[[^\]\n]*\][ \t]*(.*)$")


def _known_broken_body_bounds(text: str, heading: str = MARKER_HEADING) -> "tuple[int, int]":
    """(body_start, body_end): body_start sits right after the heading line's own
    newline; body_end is the offset of the next top-level '## ' heading, or EOF.

    Mirrors guard_runner_full.py::_known_broken_body_bounds exactly -- bounds every
    clear/replace to ONLY the pinned '## Known broken' section, so a marker-prefixed
    line that has already rolled into an older dated '## [' entry elsewhere in the
    file (history) is never touched (FULL-SUITE-RED-LINE-OUTLIVES-GREEN, queue.md
    2026-09-02)."""
    idx = text.index(heading)
    nl = text.find("\n", idx)
    body_start = nl + 1 if nl != -1 else len(text)
    m = re.search(r"^## ", text[body_start:], re.MULTILINE)
    body_end = body_start + m.start() if m else len(text)
    return body_start, body_end


def _strip_marker_lines(body: str, marker: str) -> str:
    """Remove every bullet line in `body` whose text-after-'] ' starts with `marker`.

    Operates on `body` normalized to '\\n' line endings (see _upsert_impl) so this
    function never has to reason about CRLF itself."""
    out = []
    for raw_line in body.splitlines(keepends=True):
        stripped = raw_line[:-1] if raw_line.endswith("\n") else raw_line
        m = _BULLET_LINE_RE.match(stripped)
        if m and m.group(1).startswith(marker):
            continue
        out.append(raw_line)
    return "".join(out)


def _detect_newline(raw: bytes) -> str:
    return "\r\n" if b"\r\n" in raw else "\n"


def _upsert_impl(marker: str, line: Optional[str], status_path: Path) -> bool:
    try:
        raw = status_path.read_bytes()
    except OSError:
        return False
    newline = _detect_newline(raw)
    text = raw.decode("utf-8")
    # Normalize to '\n' internally so every regex/split below is newline-convention
    # -agnostic; the file's ORIGINAL convention is restored byte-for-byte on write.
    norm = text.replace("\r\n", "\n")

    if MARKER_HEADING not in norm:
        # DO NOT return here -- see module docstring / guard_runner_full.py's own
        # rationale. Position cannot be trusted either (a session can prepend a
        # dated '## [' entry above this at any time), so recreate at the top.
        norm = MARKER_HEADING + "\n\n" + norm

    body_start, body_end = _known_broken_body_bounds(norm)
    body = norm[body_start:body_end]
    stripped_body = _strip_marker_lines(body, marker)

    if line is not None:
        clean_line = line if line.endswith("\n") else line + "\n"
        new_body = "\n" + clean_line + stripped_body.lstrip("\n")
    else:
        new_body = stripped_body

    new_norm = norm[:body_start] + new_body + norm[body_end:]

    out_text = new_norm if newline == "\n" else new_norm.replace("\n", newline)
    out_bytes = out_text.encode("utf-8")
    if out_bytes == raw:
        return False  # true no-op (e.g. clearing a marker that had no prior line)

    tmp = status_path.with_name(status_path.name + ".tmp")
    tmp.write_bytes(out_bytes)
    tmp.replace(status_path)
    return True


def upsert(marker: str, line: Optional[str], *, status_path: Path = STATUS_PATH) -> bool:
    """De-duplicating writer for STATUS.md's '## Known broken' section.

    See module docstring for full behaviour. Returns True if the file was
    written, False on a true no-op or any failure (fail-open -- never raises).
    """
    try:
        return _upsert_impl(marker, line, status_path)
    except Exception as exc:  # noqa: BLE001 -- fail-open (OP-25): never raise into a caller
        print(f"status_known_broken: FAIL-OPEN noop ({type(exc).__name__}: {exc})",
              file=sys.stderr)
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="De-duplicating writer for STATUS.md '## Known broken' (see module docstring).")
    ap.add_argument("--marker", required=True,
                    help="prefix to match/replace, e.g. 'MCP_AUDIT_' or 'ROSTER-LIVENESS:'")
    ap.add_argument("--line", default=None,
                    help="full bullet line to insert, e.g. '- [2026-09-03T01:00 ET] MCP_AUDIT_RED: ...'")
    ap.add_argument("--clear", action="store_true",
                    help="clear the marker's line(s) instead of writing a new one (a green/healthy reading)")
    ap.add_argument("--status-path", default=str(STATUS_PATH))
    args = ap.parse_args(argv)

    if args.clear and args.line:
        print("status_known_broken: --clear and --line are mutually exclusive", file=sys.stderr)
        return 2
    if not args.clear and not args.line:
        print("status_known_broken: one of --line or --clear is required", file=sys.stderr)
        return 2

    line = None if args.clear else args.line
    changed = upsert(args.marker, line, status_path=Path(args.status_path))
    print(f"status_known_broken: marker={args.marker!r} "
          f"{'cleared' if line is None else 'written'} changed={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
