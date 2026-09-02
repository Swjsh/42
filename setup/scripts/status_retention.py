#!/usr/bin/env python3
"""STATUS.md retention / consolidation tool (graduates L181 to a reusable guard).

Problem (L181, re-violated 2026-06-24): `automation/overnight/STATUS.md` is the
conductor's durable cross-fire memory, appended every fire. With no retention cap
it grows past the Read tool's token cap (~25K tokens) so a fire can no longer read
it whole -> it trusts a stale breadcrumb over current STATUS and re-does solved work
(the exact L181 foot-gun). The 2026-06-22 consolidation was a MANUAL one-off; it
regrew to 226KB / 58 entries by 2026-06-24. This module makes consolidation a
repeatable, tested, idempotent operation instead of a bespoke manual effort.

Behaviour:
  * FOLD consecutive byte-identical self-check blocks (see fold_consecutive_selfcheck_
    blocks below) BEFORE the byte-budget pass -- shrinks noise first so fewer real
    entries need to roll off to hit budget.
  * Split STATUS.md on `## [` entry boundaries (entries are newest-first at the top).
  * KEEP the newest entries while cumulative bytes <= --max-keep-bytes (default 45000,
    safely under the ~25K-token Read cap), always keeping at least --min-keep entries.
  * ROLL the older tail (verbatim, nothing deleted) to the monthly archive
    `automation/overnight/STATUS-archive-YYYY-MM.md`, newest roll inserted at the top
    (cold tail, newest-first within each roll) with a dated roll-off comment.
  * Idempotent: if the file already fits the budget, it is a no-op (exit 0).
  * Fail-open (L181/OP-25): any error / missing file -> exit 0 noop, never raises into
    a caller. This is operational state hygiene; it must never block J or a fire.

SELFCHECK-TRENDLINE-DRAW-DUPLICATE-SPAM (queue.md, filed 2026-07-22, closed here
2026-09-01): self_check.py's `_alert()` intentionally writes STATUS.md unthrottled on
EVERY tick (2026-08-17 docstring: Discord throttles, the file never does -- a full
audit trail was the deliberate design). That is correct for detection, but on a quiet
market-hours-closed stretch it means the IDENTICAL problem text (e.g. "FUTURES-HEALTH
RED: ... fills_recency ...") gets appended once per ~30min tick with nothing new to
say -- confirmed 2026-09-01: 10 consecutive byte-identical 967-byte blocks between
04:09 and 08:39 ET, one unbroken RED the whole time. Rather than change self_check.py's
live write behaviour (risks re-opening the exact "STATUS Known broken channel went
dark" failure mode a silent dedup could cause), this module POST-PROCESSES: it folds
runs of literally-adjacent, content-identical self-check blocks into ONE block with a
"(repeated Nx through <last ts>, content unchanged)" note. Nothing is dropped -- the
full problem text is kept once, plus the repeat count and time span, which is MORE
informative than 10 undated copies, not less. Only truly adjacent runs (nothing else
interleaved) are folded, so it never reorders or merges across an unrelated producer's
line sitting between two self-check blocks.

Rail-4 clear: touches ONLY operational state (STATUS.md + its archive). Zero
trading-logic / params / orders / doctrine change.

CLI:
  python setup/scripts/status_retention.py                 # apply consolidation
  python setup/scripts/status_retention.py --check         # report only, exit 2 if over budget
  python setup/scripts/status_retention.py --max-keep-bytes 60000 --min-keep 10
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATUS_PATH = os.path.join(REPO_ROOT, "automation", "overnight", "STATUS.md")

ENTRY_SPLIT = re.compile(r"(?=^## \[)", re.M)
DEFAULT_MAX_KEEP_BYTES = 45_000
DEFAULT_MIN_KEEP = 8

# `### <VERDICT>: self-check <ISO ts>` header, followed by zero or more `- ` body
# lines -- exactly what self_check.py::_alert() appends every ~30min tick.
SELFCHECK_BLOCK = re.compile(
    r"^### (?P<verdict>\w+): self-check (?P<ts>\S+)\n(?P<body>(?:- .*\n)*)", re.M)


def fold_consecutive_selfcheck_blocks(text: str) -> "tuple[str, int, int]":
    """Fold runs of literally-adjacent, content-identical self-check blocks.

    Returns (new_text, n_runs_folded, n_blocks_removed). Pure/testable -- no I/O.

    A "run" is 2+ self-check blocks in a row with (a) identical `body` text and
    (b) nothing but whitespace between one block's end and the next block's start
    (i.e. genuinely adjacent in the file -- an unrelated producer's line sitting
    between two self-check blocks breaks the run, by design, so folding never
    reorders or merges across other content)."""
    matches = list(SELFCHECK_BLOCK.finditer(text))
    if len(matches) < 2:
        return text, 0, 0

    runs: list[list[re.Match]] = []
    current = [matches[0]]
    for prev, cur in zip(matches, matches[1:]):
        between = text[prev.end():cur.start()]
        if cur.group("body") == prev.group("body") and between.strip() == "":
            current.append(cur)
        else:
            runs.append(current)
            current = [cur]
    runs.append(current)

    foldable = [r for r in runs if len(r) >= 2]
    if not foldable:
        return text, 0, 0

    out: list[str] = []
    cursor = 0
    n_runs_folded = 0
    n_blocks_removed = 0
    for run in runs:
        first, last = run[0], run[-1]
        out.append(text[cursor:first.start()])
        if len(run) >= 2:
            note = f" (repeated {len(run)}x through {last.group('ts')}, content unchanged)"
            out.append(f"### {first.group('verdict')}: self-check {first.group('ts')}"
                       f"{note}\n{first.group('body')}")
            n_runs_folded += 1
            n_blocks_removed += len(run) - 1
        else:
            out.append(text[first.start():first.end()])
        cursor = last.end()
    out.append(text[cursor:])
    return "".join(out), n_runs_folded, n_blocks_removed


# Sections that must NEVER roll off, wherever they physically sit in the file.
# `## Known broken` is the standing channel for unresolved failures. It went DEAD for two
# months (memory: status-known-broken-channel-2026-08-20 -- 3 guards sat RED and discarded)
# and was moved into the preamble on 2026-09-02 so the retention roll could not carry it
# away. That fix did not hold for one day: producers PREPEND dated entries at line 1, so by
# the next morning `## Known broken` sat at line 11, BELOW the newest `## [` header.
#
# And it does not start with `## [`, so ENTRY_SPLIT never treats it as an entry of its own --
# it is swallowed INTO whichever dated entry precedes it, and rolls off when that entry does.
# Position-based pinning cannot survive a producer that writes above you; pin by NAME instead.
PINNED_SECTIONS = ("## Known broken",)

_ANY_H2 = re.compile(r"(?=^## )", re.M)


def _extract_pinned(entry: str) -> "tuple[str, str]":
    """Split one entry into (entry_without_pinned_block, pinned_block_or_empty)."""
    blocks = _ANY_H2.split(entry)
    keep, pinned = [], []
    for b in blocks:
        if any(b.lstrip().startswith(name) for name in PINNED_SECTIONS):
            pinned.append(b)
        else:
            keep.append(b)
    return "".join(keep), "".join(pinned)


def split_entries(text: str):
    """Return (preamble, [entries]) splitting on `## [` headers (newest-first order).

    The preamble is any text before the first entry, PLUS any PINNED_SECTIONS lifted out of
    the entries themselves -- see PINNED_SECTIONS above for why hoisting is required rather
    than trusting the section to stay physically at the top.

    Each entry string includes its trailing content up to the next `## [`.
    """
    parts = ENTRY_SPLIT.split(text)
    if not parts:
        return "", []
    # If the file starts with an entry, parts[0] is "" -> preamble empty.
    if parts[0].lstrip().startswith("## ["):
        preamble, entries = "", parts
    else:
        preamble, entries = parts[0], parts[1:]

    if not any(name in text for name in PINNED_SECTIONS):
        return preamble, entries  # cheap bail-out only; every real test below is structural

    # Hoist only the FIRST (newest) occurrence. Older copies are part of the record of the
    # entry that contains them and must roll off with it -- otherwise every archived month's
    # copy accumulates in the live preamble forever. `done` must track what THIS loop has
    # taken, not just what the original preamble held: keying the check on `preamble` alone
    # hoisted every copy (caught by test_a_second_older_copy_is_left_alone_for_the_archive).
    # Structural, not a substring test. The section carries a do-not-move note that QUOTES
    # "## Known broken" in prose, so `name in preamble` is true for a preamble holding only
    # the note -- and the real section would then never be hoisted. Ask whether a BLOCK
    # starts with the name, which is what _extract_pinned already does.
    done = bool(_extract_pinned(preamble)[1])
    hoisted, out = [], []
    for e in entries:
        if not done:
            rest, pinned = _extract_pinned(e)
            if pinned:
                hoisted.append(pinned)
                e = rest
                done = True
        out.append(e)
    if hoisted:
        head = preamble.rstrip("\n") + "\n\n" if preamble.strip() else ""
        preamble = head + "".join(hoisted).rstrip("\n") + "\n\n"
    return preamble, out


def plan_consolidation(text: str, max_keep_bytes: int, min_keep: int):
    """Decide which entries to keep vs roll off. Pure function (testable).

    Returns dict: kept_text, rolled_entries (list, newest-first), n_kept, n_rolled.
    """
    preamble, entries = split_entries(text)
    n = len(entries)
    if n == 0:
        return {"kept_text": text, "rolled_entries": [], "n_kept": 0, "n_rolled": 0}

    cum = len(preamble.encode("utf-8"))
    keep_count = 0
    for i, e in enumerate(entries):
        cum += len(e.encode("utf-8"))
        keep_count = i + 1
        # Always keep at least min_keep; stop once over budget beyond that.
        if keep_count >= min_keep and cum > max_keep_bytes:
            break

    keep_count = min(keep_count, n)
    kept = entries[:keep_count]
    rolled = entries[keep_count:]
    kept_text = preamble + "".join(kept)
    return {
        "kept_text": kept_text,
        "rolled_entries": rolled,
        "n_kept": len(kept),
        "n_rolled": len(rolled),
    }


def _archive_path(status_path: str, today: dt.date) -> str:
    return os.path.join(os.path.dirname(status_path), f"STATUS-archive-{today:%Y-%m}.md")


def _archive_header(today: dt.date) -> str:
    return (
        f"# STATUS archive — {today:%Y-%m} (rolled off from STATUS.md by "
        "status_retention.py, L181)\n\n"
        "> Verbatim older STATUS.md entries, newest-first within each roll. "
        "STATUS.md keeps the newest entries that fit the Read cap; this file is the "
        "cold tail. Nothing deleted.\n\n"
    )


def _insert_roll(existing: str, roll_block: str, today: dt.date) -> str:
    """Insert a new roll at the TOP of the archive body (after the header preamble)."""
    if not existing.strip():
        return _archive_header(today) + roll_block
    marker = existing.find("<!-- rolled off")
    if marker == -1:
        # No prior roll marker; append a header if missing, then the roll.
        if existing.startswith("# STATUS archive"):
            return existing.rstrip() + "\n\n" + roll_block
        return _archive_header(today) + roll_block + existing
    head = existing[:marker]
    tail = existing[marker:]
    return head + roll_block + tail


def apply_consolidation(status_path: str, max_keep_bytes: int, min_keep: int,
                        today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    with open(status_path, "r", encoding="utf-8") as fh:
        text = fh.read()

    text, n_folded_runs, n_folded_blocks = fold_consecutive_selfcheck_blocks(text)

    plan = plan_consolidation(text, max_keep_bytes, min_keep)
    if plan["n_rolled"] == 0:
        if n_folded_blocks:
            _atomic_write(status_path, text)
        return {"changed": bool(n_folded_blocks), "n_kept": plan["n_kept"], "n_rolled": 0,
                "new_bytes": len(text.encode("utf-8")),
                "n_folded_runs": n_folded_runs, "n_folded_blocks": n_folded_blocks}

    rolled = plan["rolled_entries"]
    rolled_lines = sum(e.count("\n") for e in rolled)
    roll_block = (
        f"\n<!-- rolled off {today:%Y-%m-%d} by status_retention.py "
        f"(L181 consolidation): {len(rolled)} entries / {rolled_lines} lines -->\n\n"
        + "".join(rolled).rstrip() + "\n\n"
    )

    archive_path = _archive_path(status_path, today)
    existing = ""
    if os.path.exists(archive_path):
        with open(archive_path, "r", encoding="utf-8") as fh:
            existing = fh.read()
    new_archive = _insert_roll(existing, roll_block, today)

    # Atomic writes (temp + replace) so a crash can't corrupt the live state file.
    _atomic_write(archive_path, new_archive)
    _atomic_write(status_path, plan["kept_text"])

    return {"changed": True, "n_kept": plan["n_kept"], "n_rolled": plan["n_rolled"],
            "new_bytes": len(plan["kept_text"].encode("utf-8")),
            "archive_path": archive_path,
            "n_folded_runs": n_folded_runs, "n_folded_blocks": n_folded_blocks}


def _atomic_write(path: str, content: str) -> None:
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Consolidate STATUS.md (L181 retention guard).")
    ap.add_argument("--status-path", default=STATUS_PATH)
    ap.add_argument("--max-keep-bytes", type=int, default=DEFAULT_MAX_KEEP_BYTES)
    ap.add_argument("--min-keep", type=int, default=DEFAULT_MIN_KEEP)
    ap.add_argument("--check", action="store_true",
                    help="report only; exit 2 if over budget, 0 if fits")
    args = ap.parse_args(argv)

    try:
        if not os.path.exists(args.status_path):
            print(f"status_retention: {args.status_path} missing -> noop")
            return 0
        size = os.path.getsize(args.status_path)
        if args.check:
            over = size > args.max_keep_bytes
            print(f"status_retention --check: {size} bytes "
                  f"({'OVER' if over else 'within'} budget {args.max_keep_bytes})")
            return 2 if over else 0
        res = apply_consolidation(args.status_path, args.max_keep_bytes, args.min_keep)
        fold_note = (f", folded {res['n_folded_runs']} run(s)/{res['n_folded_blocks']} "
                     f"duplicate block(s)" if res.get("n_folded_blocks") else "")
        if res["changed"] and res.get("n_rolled"):
            print(f"status_retention: kept {res['n_kept']} entries "
                  f"({res['new_bytes']} bytes), rolled {res['n_rolled']} to "
                  f"{os.path.basename(res['archive_path'])}{fold_note}")
        elif res["changed"]:
            print(f"status_retention: within roll budget ({res['new_bytes']} bytes, "
                  f"{res['n_kept']} entries){fold_note}")
        else:
            print(f"status_retention: within budget ({res['new_bytes']} bytes, "
                  f"{res['n_kept']} entries) -> noop")
        return 0
    except Exception as exc:  # fail-open (L181/OP-25): never raise into a caller
        print(f"status_retention: FAIL-OPEN noop ({type(exc).__name__}: {exc})",
              file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
