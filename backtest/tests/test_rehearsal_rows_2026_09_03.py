"""Guard: setup/scripts/rehearsal_rows.py (queue.md DRILLS-WRITE-INTO-PRODUCTION-LEDGERS,
filed 2026-09-02, design decided by Fable: option (b) -- one shared is_rehearsal_row() helper
both eod-flatten-*.jsonl readers import, instead of the private duplicated predicate each
carried before).

Covers exactly what the queue item asked for:
  1. `is_rehearsal_row` / `filter_production_rows` behave correctly on real production rows
     and on every synthetic shape the actual writer produces.
  2. Every synthetic row shape the drills in the repo actually write is pinned. Checked
     2026-09-03 by reading each `*_drill*.py`'s own row-writer: `dms_kill_drill.py`,
     `recovery_drill_observer.py`, `twin_chaos_drill.py` (setup/scripts), plus
     `backtest/futures/futures_drills.py` and `backtest/tools/exit_chaos_drill.py` -- NONE of
     them write into `eod-flatten-*.jsonl`; each writes to its own dedicated ledger. The only
     writer of a synthetic row into THIS shared surface is `eod_flatten.py`'s own
     `GAMMA_EOD_DRY=1` convention (matched by `dead_mans_switch.py`'s dry-run switch, same
     file). Both of `eod_flatten.py::_flatten_account()`'s dry-mode shapes (already-flat NOOP,
     had-positions DRY_RUN) are pinned below, read verbatim from that function.
  3. `preopen_readiness.py` and `first_live_day_review.py` both now import this module (no
     private predicate left in either) -- their own existing test suites
     (test_preopen_readiness.py, test_first_live_day_review_2026_09_02.py) already prove no
     behaviour change; this file does not re-run those, only asserts the import landed.
  4. A grep-guard: every file under setup/scripts that references an `eod-flatten-*.jsonl`
     path must import `rehearsal_rows`, except the allowlisted writers/definition itself.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = REPO / "setup" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import rehearsal_rows  # noqa: E402


# --------------------------------------------------------------------------------------- #
# 1. behaviour on real production rows
# --------------------------------------------------------------------------------------- #
def test_real_production_rows_pass_through():
    """Verbatim rows pulled from automation/state/logs/eod-flatten-2026-09-02.jsonl."""
    real_rows = [
        {"arm": "safe-2", "ts": "2026-09-02 15:52:01 ET", "dry": False, "outcome": "NOOP",
         "closed": [], "errors": [], "remaining": 0},
        {"arm": "risky-1", "ts": "2026-09-02 15:52:01 ET", "dry": False, "outcome": "NOOP",
         "closed": [], "errors": [], "remaining": 0},
        {"arm": "bold-2", "ts": "2026-09-02 15:52:01 ET", "dry": False, "outcome": "NOOP",
         "closed": [], "errors": [], "remaining": 0},
    ]
    for r in real_rows:
        assert rehearsal_rows.is_rehearsal_row(r) is False, r
    assert rehearsal_rows.filter_production_rows(real_rows) == real_rows


def test_real_success_and_read_failed_rows_are_not_rehearsals():
    """A real closed-and-succeeded row and a real READ_FAILED row (both dry: False) must
    never be classified as rehearsals -- READ_FAILED is genuine evidence of a problem, not
    an absence of evidence, and must reach the caller (see first_live_day_review.py's own
    docstring distinction)."""
    success_row = {"arm": "bold-2", "ts": "2026-09-02 15:52:03 ET", "dry": False,
                   "outcome": "SUCCESS", "closed": ["SPY..."], "errors": [], "remaining": 0}
    read_failed_row = {"arm": "safe-2", "ts": "2026-09-02 15:52:01 ET", "dry": False,
                        "outcome": "READ_FAILED", "closed": [], "remaining": None,
                        "errors": ["positions query failed 3x -- flat status UNKNOWN"]}
    assert rehearsal_rows.is_rehearsal_row(success_row) is False
    assert rehearsal_rows.is_rehearsal_row(read_failed_row) is False


# --------------------------------------------------------------------------------------- #
# 2. every synthetic shape the actual writer produces (pinned from eod_flatten.py source)
# --------------------------------------------------------------------------------------- #
def test_dry_already_flat_noop_shape_is_flagged():
    """eod_flatten.py::_flatten_account() under GAMMA_EOD_DRY=1, qty_total == 0 -- the exact
    shape from the 2026-09-02 incident (_lesson-inbox/2026-09-02-a-rehearsal-is-not-
    evidence.md): {"arm":..., "ts":..., "dry": true, "reason": "EARLY_CLOSE", "outcome":
    "NOOP", "closed": [], "errors": [], "remaining": 0}."""
    row = {"arm": "bold-2", "ts": "2026-09-02 12:45:00 ET", "dry": True,
           "reason": "EARLY_CLOSE", "outcome": "NOOP", "closed": [], "errors": [],
           "remaining": 0}
    assert rehearsal_rows.is_rehearsal_row(row) is True


def test_dry_had_positions_dry_run_shape_is_flagged():
    """eod_flatten.py::_flatten_account() under GAMMA_EOD_DRY=1, qty_total > 0 -- the other
    dry-mode shape: {"arm":..., "ts":..., "dry": true, "outcome": "DRY_RUN",
    "would_close": [...], "qty": N}."""
    row = {"arm": "safe-2", "ts": "2026-09-02 12:45:00 ET", "dry": True,
           "outcome": "DRY_RUN", "would_close": ["SPY260902C00650000"], "qty": 3}
    assert rehearsal_rows.is_rehearsal_row(row) is True


def test_outcome_dry_run_without_dry_flag_is_still_flagged():
    """Belt-and-braces clause: if a future writer ever sets outcome=DRY_RUN without also
    setting dry: true, the row must still be caught."""
    row = {"arm": "safe-2", "ts": "2026-09-02 12:45:00 ET", "outcome": "DRY_RUN"}
    assert rehearsal_rows.is_rehearsal_row(row) is True


def test_filter_production_rows_drops_rehearsals_keeps_real_preserves_order():
    rows = [
        {"arm": "safe-2", "dry": False, "outcome": "NOOP"},
        {"arm": "safe-2", "dry": True, "outcome": "NOOP", "reason": "EARLY_CLOSE"},
        {"arm": "safe-2", "dry": False, "outcome": "SUCCESS"},
        {"arm": "safe-2", "outcome": "DRY_RUN"},
    ]
    out = rehearsal_rows.filter_production_rows(rows)
    assert out == [rows[0], rows[2]]
    # never mutates the input
    assert len(rows) == 4


# --------------------------------------------------------------------------------------- #
# 2b. no *_drill*.py writes into eod-flatten-*.jsonl -- checked, not assumed
# --------------------------------------------------------------------------------------- #
def test_no_drill_script_writes_eod_flatten_rows():
    """Checked 2026-09-03: none of the repo's drill scripts construct an eod-flatten-*.jsonl
    path or write a row shaped like one. If this ever becomes false, this test's failure IS
    the signal that a new drill has started writing into the shared production surface and
    rehearsal_rows.py's shape-pins above need a new fixture."""
    drill_files = sorted(REPO.glob("**/*drill*.py"))
    drill_files = [p for p in drill_files
                   if "__pycache__" not in p.parts and "tests" not in p.parts]
    assert drill_files, "expected to find at least the known drill scripts"
    for p in drill_files:
        text = p.read_text(encoding="utf-8", errors="replace")
        assert not re.search(r"eod-flatten-.*\.jsonl", text), (
            f"{p} appears to reference an eod-flatten-*.jsonl path -- if a drill now writes "
            "into the shared ledger, rehearsal_rows.py's pinned shapes must be updated to "
            "cover its row shape."
        )


# --------------------------------------------------------------------------------------- #
# 3. both readers import the shared helper
# --------------------------------------------------------------------------------------- #
def test_preopen_readiness_imports_rehearsal_rows():
    import preopen_readiness as pr
    assert pr.rehearsal_rows is rehearsal_rows
    assert pr.is_rehearsal_row is rehearsal_rows.is_rehearsal_row


def test_first_live_day_review_imports_rehearsal_rows():
    import first_live_day_review as flr
    assert flr.rehearsal_rows is rehearsal_rows


# --------------------------------------------------------------------------------------- #
# 4. grep-guard: every eod-flatten-*.jsonl reader under setup/scripts imports this module
# --------------------------------------------------------------------------------------- #
_ALLOWLIST = {
    "eod_flatten.py",       # the frozen writer -- constructs the paths, does not read/import
    "rehearsal_rows.py",    # this module -- defines the concept, mentions the pattern in prose
}


def test_every_eod_flatten_jsonl_reference_imports_rehearsal_rows():
    pattern = re.compile(r"eod-flatten-[^\"'\s]*\.jsonl|eod-flatten-\[0-9\]")
    offenders = []
    for p in sorted(_SCRIPTS.glob("*.py")):
        if p.name in _ALLOWLIST:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if pattern.search(text) and "import rehearsal_rows" not in text:
            offenders.append(p.name)
    assert offenders == [], (
        f"these setup/scripts files reference eod-flatten-*.jsonl but do not import "
        f"rehearsal_rows: {offenders} -- see rehearsal_rows.py's module docstring: any "
        "future reader of this shared ledger MUST use is_rehearsal_row/"
        "filter_production_rows rather than re-deriving the predicate."
    )
