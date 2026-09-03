"""queue_consolidate.py -- deterministic, $0, stdlib-only consolidation of
automation/overnight/queue.md against its 450,000-byte retention cap
(backtest/tests/test_queue_md_retention_cap.py).

WHY THIS EXISTS: the cap has been enforced by hand four times (2026-08-19,
2026-08-29, and twice on 2026-09-02 -- see automation/overnight/queue-
archive-2026-09-02.md, which has a header + a "## Tranche 2" appended
section). QUEUE-MD-RETENTION-CAP (grep it in queue.md) records the
foot-gun this script is written to never repeat: a plain Python
`open(path, "w")` on this Windows box silently converts LF -> CRLF, which
would corrupt a "byte-for-byte verbatim" archival claim. This script never
opens queue.md or an archive file in text mode -- everything is read/
written as bytes, with line endings tracked and preserved explicitly.

WHAT IT DOES
------------
Parses queue.md from the "## Active backlog" heading onward into top-level
blocks (a block starts at a line beginning "- [", "### ", or "## " and runs
to the next such line; every other line, including blanks and indented
continuation/follow-up notes, belongs to the block above it).

A block is a candidate for archival iff its head line starts with
"- [x] " AND (its LAST `status:` field resolves to one of
done/closed/resolved/cancelled/canceled/decided/shipped, case-insensitive,
OR its head line names CLOSED/DONE/SHIPPED/RESOLVED alongside a
YYYY-MM-DD date). "- [ ]", "- [~]", and bare headings are never candidates.

A candidate is DROPPED from the archive set (and the reason printed) if any
NON-selected block's `depends:` clause references the candidate's id (id =
the text between "- [x] " and the first " (", " --", or " :: ").

Selected blocks are written verbatim (LF-normalised) to
automation/overnight/queue-archive-<YYYY-MM-DD>.md -- appending a new
"## Tranche N" section if today's archive file already exists, else
creating it with the same header shape as the existing 2026-09-02 file.
They are removed from queue.md, and a single pointer line naming the
archive file + item count + byte total is inserted or updated directly
under "## Active backlog". queue.md's own CRLF (and its UTF-8 BOM) are
preserved byte-for-byte on every line this run does not touch.

Every write is preceded (dry-run) or followed (--apply) by a self-
verification pass: every archived block's text must be present verbatim in
the new archive content, and the queue.md line count must reconcile
(kept + removed lines == original, plus exactly the lines the pointer edit
added). Any failure restores the original bytes of both files from an
in-memory copy and exits non-zero -- nothing is left half-written.

USAGE
-----
    python queue_consolidate.py                    # dry run (default)
    python queue_consolidate.py --apply
    python queue_consolidate.py --apply --min-headroom 50000
    python queue_consolidate.py --queue-path X --archive-dir Y   # tests only

$0, stdlib only, no LLM, no network.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from et_clock import et_now  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
QUEUE_MD_DEFAULT = REPO / "automation" / "overnight" / "queue.md"
ARCHIVE_DIR_DEFAULT = REPO / "automation" / "overnight"

# Mirrors backtest/tests/test_queue_md_retention_cap.py::RETENTION_CAP_BYTES.
# Kept as an independent literal (not imported) so this script has zero
# dependency on the test tree at runtime; the two are pinned together by
# convention + this comment, not by import.
CAP_BYTES = 450_000

ACTIVE_BACKLOG_HEADING = "## Active backlog"

TERMINAL_STATUSES = {
    "done", "closed", "resolved", "cancelled", "canceled", "decided", "shipped",
}
HEAD_KEYWORDS = ("CLOSED", "DONE", "SHIPPED", "RESOLVED")

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
STATUS_RE = re.compile(r"status:([A-Za-z][A-Za-z0-9_-]*)")
DEPENDS_RE = re.compile(r"depends:([^\r\n]*?)(?=\s::|\r?\n|$)")
BLOCK_START_RE = re.compile(r"^(- \[|### |## )")
ID_HEAD_RE = re.compile(r"^- \[[ x~]\] (.+)")
POINTER_RE = re.compile(r"^> \d{4}-\d{2}-\d{2} \d{2}:\d{2} ET: \d+ `\[x\]`")


class ConsolidationError(RuntimeError):
    """A post-write self-check failed; caller restores original bytes."""


# --------------------------------------------------------------------------
# Byte/line-ending helpers -- NEVER open queue.md or an archive in text mode.
# --------------------------------------------------------------------------

def _line_ending(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    if line.endswith("\r"):
        return "\r"
    return ""


def _content(line: str) -> str:
    ending = _line_ending(line)
    return line[: len(line) - len(ending)] if ending else line


def normalize_lf(line: str) -> str:
    """Return `line` with its own line ending (if any) forced to a bare '\n'."""
    return _content(line) + ("\n" if _line_ending(line) else "")


def decode_bytes(data: bytes) -> tuple[str, bool]:
    had_bom = data.startswith(b"\xef\xbb\xbf")
    text = data[3:].decode("utf-8") if had_bom else data.decode("utf-8")
    return text, had_bom


def encode_bytes(text: str, had_bom: bool) -> bytes:
    out = text.encode("utf-8")
    return (b"\xef\xbb\xbf" + out) if had_bom else out


# --------------------------------------------------------------------------
# Block parsing + selection
# --------------------------------------------------------------------------

def split_blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if BLOCK_START_RE.match(_content(line)) and current:
            blocks.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append(current)
    return blocks


def extract_id(block_lines: list[str]) -> str:
    head = _content(block_lines[0])
    m = ID_HEAD_RE.match(head)
    if m:
        rest = m.group(1)
    elif head.startswith("### ") or head.startswith("## "):
        rest = head.split(" ", 1)[1] if " " in head else head
    else:
        rest = head
    positions = [p for p in (rest.find(" ("), rest.find(" --"), rest.find(" ::")) if p != -1]
    end = min(positions) if positions else len(rest)
    return rest[:end].strip()


def last_status(block_text: str) -> str | None:
    matches = STATUS_RE.findall(block_text)
    return matches[-1] if matches else None


def is_terminal_status(status_value: str) -> bool:
    tokens = re.split(r"[^a-z0-9]+", status_value.lower())
    return any(t in TERMINAL_STATUSES for t in tokens if t)


def head_closed_with_date(head: str) -> bool:
    # Exact-case match (NOT case-folded): real markers in queue.md are always written
    # ALL-CAPS ("CLOSED 2026-09-01", "**CLOSED 2026-08-30**"). A case-insensitive match
    # here produced a real false positive on the live file -- "fail-closed guard" (a
    # description of a FLATTEN guard's failure mode, lowercase, inside a hyphenated
    # compound) matched \bCLOSED\b once upper-cased, wrongly flagging PHONE-HALT-COMMAND
    # (status:built-not-drilled, genuinely open) as archivable. Exact-case avoids that
    # whole class: none of these keywords legitimately appear lowercase as a status marker.
    has_keyword = any(re.search(rf"\b{kw}\b", head) for kw in HEAD_KEYWORDS)
    return has_keyword and bool(DATE_RE.search(head))


def is_candidate(block_lines: list[str]) -> bool:
    head = _content(block_lines[0])
    if not head.startswith("- [x] "):
        return False
    text = "".join(block_lines)
    status = last_status(text)
    terminal = is_terminal_status(status) if status else False
    return terminal or head_closed_with_date(head)


def depends_tokens(block_text: str) -> set[str]:
    tokens: set[str] = set()
    for val in DEPENDS_RE.findall(block_text):
        val = val.strip()
        if not val or val.lower() == "none":
            continue
        for tok in re.split(r"[,\s]+", val):
            tok = tok.strip()
            if tok:
                tokens.add(tok)
    return tokens


def resolve_selection(blocks: list[list[str]]):
    """Return (selected_indices: list[int], blocked: {idx: [reason,...]}, ids: {idx: id})."""
    candidate_idx = [i for i, b in enumerate(blocks) if is_candidate(b)]
    ids = {i: extract_id(blocks[i]) for i in candidate_idx}
    dep_tokens = ["".join(b) for b in blocks]
    dep_tokens = [depends_tokens(t) for t in dep_tokens]

    blocked: dict[int, list[str]] = {}
    for i in candidate_idx:
        cid = ids[i]
        if not cid:
            continue
        for j, b in enumerate(blocks):
            if j in candidate_idx:
                continue
            if cid in dep_tokens[j]:
                other_id = extract_id(b) or "(heading/section)"
                blocked.setdefault(i, []).append(
                    f"{cid} NOT archived -- open item '{other_id}' has depends:{cid}"
                )

    selected = [i for i in candidate_idx if i not in blocked]
    return selected, blocked, ids


# --------------------------------------------------------------------------
# Archive file rendering
# --------------------------------------------------------------------------

_ARCHIVE_HEADER_TMPL = (
    "# queue.md consolidation archive -- {date}\n"
    "\n"
    "Extracted verbatim from `automation/overnight/queue.md` when it crossed the {cap:,}-byte "
    "retention cap enforced by\n"
    "`backtest/tests/test_queue_md_retention_cap.py` (OP-22: \"every append-only producer has a "
    "retention cap;\n"
    "hitting it triggers CONSOLIDATION\"). Same archival rule as prior consolidations: every "
    "item whose checkbox is\n"
    "`[x]` AND whose terminal status resolves to done/closed/resolved/cancelled/decided/shipped, "
    "or whose head line\n"
    "names CLOSED/DONE/SHIPPED/RESOLVED with a date.\n"
    "\n"
    "Items archived: {count}  ({size:,} bytes)\n"
    "\n"
    "Verified before extraction: no still-open item's `depends:` references any archived id "
    "(checked against the\n"
    "full open set, not a sample). Nothing was deleted -- every item below is byte-identical "
    "(LF-normalised) to\n"
    "what left the live file.\n"
    "\n"
    "---\n"
    "\n"
)

_TRANCHE_HEADER_TMPL = (
    "\n"
    "## Tranche {n} -- {date} {time} ET (queue_consolidate.py)\n"
    "\n"
    "Items archived: {count}  ({size:,} bytes). Rule unchanged: `[x]` AND terminal status, or "
    "head CLOSED/DONE/\n"
    "SHIPPED/RESOLVED with a date. Verified before extraction: no remaining item's `depends:` "
    "references any\n"
    "archived id.\n"
    "\n"
)


def archive_path_for(archive_dir: Path, date_str: str) -> Path:
    return archive_dir / f"queue-archive-{date_str}.md"


def render_archived_body(selected_blocks: list[list[str]]) -> str:
    return "".join(normalize_lf(l) for b in selected_blocks for l in b)


def build_archive_text(
    selected_blocks: list[list[str]],
    existing_text: str | None,
    date_str: str,
    time_str: str,
) -> tuple[str, int]:
    """Return (full new archive file text, tranche number used -- 1 for a new file)."""
    body = render_archived_body(selected_blocks)
    size = len(body.encode("utf-8"))
    count = len(selected_blocks)
    if existing_text is None:
        header = _ARCHIVE_HEADER_TMPL.format(date=date_str, cap=CAP_BYTES, count=count, size=size)
        return header + body, 1
    tranche_n = existing_text.count("## Tranche ") + 2
    section = _TRANCHE_HEADER_TMPL.format(
        n=tranche_n, date=date_str, time=time_str, count=count, size=size
    )
    return existing_text + section + body, tranche_n


# --------------------------------------------------------------------------
# queue.md pointer line + reconstruction
# --------------------------------------------------------------------------

def render_pointer_line(count: int, size: int, archive_filename: str, ending: str) -> str:
    now = et_now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    plural = "s" if count != 1 else ""
    text = (
        f"> {date_str} {time_str} ET: {count} `[x]` done item{plural} ({size:,} bytes) "
        f"moved verbatim to `{archive_filename}` (cap {CAP_BYTES:,} -- "
        f"see test_queue_md_retention_cap.py)."
    )
    return text + ending


def update_heading_block(heading_block: list[str], pointer_line: str) -> list[str]:
    new_block = list(heading_block)
    if len(new_block) > 1 and POINTER_RE.match(_content(new_block[1])):
        new_block[1] = pointer_line
    else:
        new_block.insert(1, pointer_line)
    return new_block


def build_new_queue_lines(
    lines: list[str],
    heading_idx: int,
    blocks: list[list[str]],
    selected_indices: set[int],
    pointer_line: str,
) -> list[str]:
    prefix = lines[:heading_idx]
    heading_block = blocks[0]
    updated_heading_block = update_heading_block(heading_block, pointer_line)
    out = list(prefix) + list(updated_heading_block)
    for i in range(1, len(blocks)):
        if i in selected_indices:
            continue
        out.extend(blocks[i])
    return out


# --------------------------------------------------------------------------
# Self-verification
# --------------------------------------------------------------------------

def self_verify(
    lines: list[str],
    heading_idx: int,
    blocks: list[list[str]],
    selected_indices: list[int],
    new_lines: list[str],
    selected_blocks: list[list[str]],
    new_archive_text: str,
) -> None:
    # 1. Every archived block's LF-normalised text is present verbatim in the archive.
    for i, b in zip(selected_indices, selected_blocks):
        needle = render_archived_body([b])
        if needle not in new_archive_text:
            cid = extract_id(b)
            raise ConsolidationError(
                f"archived block '{cid}' (block index {i}) is NOT present verbatim in the "
                f"new archive text -- refusing to write"
            )

    # 2. Line-count reconciliation: kept + removed (+ pointer delta) == original.
    removed = sum(len(blocks[i]) for i in selected_indices)
    heading_block = blocks[0]
    pointer_delta = 1 if not (
        len(heading_block) > 1 and POINTER_RE.match(_content(heading_block[1]))
    ) else 0
    expected = len(lines) - removed + pointer_delta
    if len(new_lines) != expected:
        raise ConsolidationError(
            f"line-count reconciliation failed: original={len(lines)} removed={removed} "
            f"pointer_delta={pointer_delta} expected={expected} actual={len(new_lines)}"
        )


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def run(
    queue_path: Path,
    archive_dir: Path,
    apply: bool,
    min_headroom: int,
) -> int:
    original_bytes = queue_path.read_bytes()
    text, had_bom = decode_bytes(original_bytes)
    lines = text.splitlines(keepends=True)

    heading_idx = next(
        (i for i, l in enumerate(lines) if _content(l) == ACTIVE_BACKLOG_HEADING), None
    )
    if heading_idx is None:
        print(f"ERROR: '{ACTIVE_BACKLOG_HEADING}' heading not found in {queue_path}", file=sys.stderr)
        return 2

    region = lines[heading_idx:]
    blocks = split_blocks(region)
    selected_indices, blocked, ids = resolve_selection(blocks)

    for idx, reasons in blocked.items():
        for r in reasons:
            print(f"SKIP (depends): {r}")

    print(
        f"Candidates: {len(selected_indices) + len(blocked)}  "
        f"Selected: {len(selected_indices)}  Blocked-by-depends: {len(blocked)}"
    )
    print(f"queue.md (before): {len(original_bytes):,} bytes (cap {CAP_BYTES:,})")

    if not selected_indices:
        print("No archivable blocks -- nothing to do.")
        return 0

    selected_blocks = [blocks[i] for i in selected_indices]
    for i, b in zip(selected_indices, selected_blocks):
        print(f"  archive: {ids[i]}")

    now = et_now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    archive_path = archive_path_for(archive_dir, date_str)
    existing_archive_text = (
        archive_path.read_text(encoding="utf-8") if archive_path.exists() else None
    )
    new_archive_text, tranche_n = build_archive_text(
        selected_blocks, existing_archive_text, date_str, time_str
    )

    body_bytes = len(render_archived_body(selected_blocks).encode("utf-8"))
    archive_filename = archive_path.name
    pointer_line = render_pointer_line(
        len(selected_blocks), body_bytes, archive_filename, _line_ending(lines[heading_idx])
    )

    new_lines = build_new_queue_lines(lines, heading_idx, blocks, set(selected_indices), pointer_line)
    new_text = "".join(new_lines)
    new_bytes = encode_bytes(new_text, had_bom)

    mode = f"append tranche {tranche_n}" if existing_archive_text is not None else "new file"
    print(f"archive: {archive_path} ({mode}), +{body_bytes:,} bytes, {len(selected_blocks)} items")
    print(f"queue.md (projected): {len(new_bytes):,} bytes (cap {CAP_BYTES:,})")

    if not apply:
        print("[dry-run] no files written. Re-run with --apply to write.")
        return 0

    # Self-verify BEFORE writing anything -- if this fails, nothing has moved yet.
    self_verify(lines, heading_idx, blocks, selected_indices, new_lines, selected_blocks, new_archive_text)

    original_archive_bytes = archive_path.read_bytes() if archive_path.exists() else None
    new_archive_bytes = new_archive_text.encode("utf-8")

    try:
        queue_path.write_bytes(new_bytes)
        archive_path.write_bytes(new_archive_bytes)
        # Post-write re-read verification (catches disk-level surprises, not just logic bugs).
        written_queue = queue_path.read_bytes()
        written_archive = archive_path.read_bytes()
        if written_queue != new_bytes or written_archive != new_archive_bytes:
            raise ConsolidationError("post-write byte-for-byte re-read did not match what was written")
    except Exception:
        queue_path.write_bytes(original_bytes)
        if original_archive_bytes is None:
            if archive_path.exists():
                archive_path.unlink()
        else:
            archive_path.write_bytes(original_archive_bytes)
        raise

    print(f"WROTE queue.md ({len(new_bytes):,} bytes) and {archive_path.name}.")

    if len(new_bytes) > CAP_BYTES - min_headroom:
        print(
            f"LOUD: queue.md is still {len(new_bytes):,} bytes, within {min_headroom:,} bytes "
            f"of the {CAP_BYTES:,}-byte cap after this pass -- more terminal-status items must "
            f"land before the next consolidation, or the cap needs a stated-reason raise. "
            f"NOT archiving open items to force this down."
        )

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-path", type=Path, default=QUEUE_MD_DEFAULT)
    parser.add_argument("--archive-dir", type=Path, default=ARCHIVE_DIR_DEFAULT)
    parser.add_argument("--apply", action="store_true", default=False)
    parser.add_argument("--min-headroom", type=int, default=20_000)
    args = parser.parse_args(argv)
    try:
        return run(args.queue_path, args.archive_dir, args.apply, args.min_headroom)
    except ConsolidationError as exc:
        print(f"ABORTED, restored original bytes: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
