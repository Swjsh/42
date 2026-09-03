"""rehearsal_rows.py -- the ONE place `eod-flatten-*.jsonl` rehearsal-detection logic lives.

WHY THIS EXISTS (queue.md DRILLS-WRITE-INTO-PRODUCTION-LEDGERS, filed 2026-09-02, design
decided by Fable: option (b) -- keep co-location, add a shared `is_rehearsal_row()` helper
both readers import, rather than moving drills to a separate file glob).

BACKGROUND: `automation/state/logs/eod-flatten-*.jsonl` is written by `eod_flatten.py` (the
production EOD-flatten writer -- frozen, never edited by this module) on every real fire AND
on every dry-run rehearsal (`GAMMA_EOD_DRY=1`, e.g. an early-close-path rehearsal run with an
injected clock -- see `automation/overnight/_lesson-inbox/2026-09-02-a-rehearsal-is-not-
evidence.md` for the incident this closes). A rehearsal row lands in the SAME file, same
shape, with a synthetic timestamp. Two independent readers --
`preopen_readiness.py::is_rehearsal_row()` and `first_live_day_review.py::_is_rehearsal()`
-- each carried their own copy of the classification predicate (deliberately duplicated at
the time, since neither module imports the other). Both predicates were IDENTICAL:

    row.get("dry") is True or row.get("outcome") == "DRY_RUN"

This module is the union of both (trivial here, since they already agreed) collapsed into one
place, so the two seams cannot silently drift apart again.

WHAT ACTUALLY WRITES A REHEARSAL ROW (checked 2026-09-03, so this module's test can pin real
shapes rather than invented ones): `eod_flatten.py::_flatten_account()` under
`GAMMA_EOD_DRY=1` writes ONE of two shapes into `eod-flatten-*.jsonl` depending on whether the
arm had open positions at rehearsal time:

  - already flat:  {"arm": ..., "ts": ..., "dry": true, "reason": <optional>,
                     "outcome": "NOOP", "closed": [], "errors": [], "remaining": 0}
  - had positions:  {"arm": ..., "ts": ..., "dry": true, "reason": <optional>,
                     "outcome": "DRY_RUN", "would_close": [...], "qty": N}

Both are covered by the single predicate above (the "NOOP" shape via `dry is True`, the
"DRY_RUN" shape via either clause). Checked 2026-09-03: NONE of the repo's other `*_drill*.py`
scripts (`setup/scripts/dms_kill_drill.py`, `setup/scripts/recovery_drill_observer.py`,
`setup/scripts/twin_chaos_drill.py`, `backtest/futures/futures_drills.py`,
`backtest/tools/exit_chaos_drill.py`) write into `eod-flatten-*.jsonl` at all -- they each
write to their own dedicated ledger (`analysis/drills/dms-kill-drill-*.jsonl`,
`analysis/drills/recovery-drill-*.jsonl`, `resilience-ledger.jsonl`, etc). The ONLY path a
synthetic row reaches this specific shared surface is `eod_flatten.py`'s own `GAMMA_EOD_DRY`
convention (matched by `dead_mans_switch.py`'s dry-run switch, same convention, same file).
This is disclosed here rather than silently assumed, per C7 (audit outputs, not exit codes).

ANY FUTURE READER of `eod-flatten-*.jsonl` MUST import this module and use `is_rehearsal_row`
/ `filter_production_rows` rather than re-deriving the predicate. A grep-guard test
(`backtest/tests/test_rehearsal_rows_2026_09_03.py`) enforces this: every file under
`setup/scripts/` that opens an `eod-flatten-` path must import `rehearsal_rows`, except the
writers themselves (`eod_flatten.py`, `dead_mans_switch.py`) and this module.
"""
from __future__ import annotations


def is_rehearsal_row(row: dict) -> bool:
    """A dry-run/rehearsal row written into `eod-flatten-*.jsonl`: flattens nothing, proves
    nothing about whether the real EOD sweep ran. Union of both prior per-file predicates
    (`preopen_readiness.py::is_rehearsal_row`, `first_live_day_review.py::_is_rehearsal`,
    both identical at the time this module was extracted, 2026-09-03):

        row.get("dry") is True or row.get("outcome") == "DRY_RUN"

    `dry is True` catches every rehearsal row eod_flatten.py writes (both the "already flat"
    NOOP shape and the "had positions" DRY_RUN shape -- see module docstring). The
    `outcome == "DRY_RUN"` clause is kept as a second, independent signal in case a future
    writer ever sets `outcome` to `DRY_RUN` without also setting `dry: true` -- belt and
    braces, exactly as both original readers intended it defensively, not merely redundantly.
    """
    return row.get("dry") is True or row.get("outcome") == "DRY_RUN"


def filter_production_rows(rows: list[dict]) -> list[dict]:
    """Drops every rehearsal row, preserving order. Never mutates the input list or its
    row dicts (immutability per coding-style doctrine) -- returns a new list."""
    return [r for r in rows if not is_rehearsal_row(r)]
