"""Guard: L3 lane (2026-08-25) -- core-decisions.jsonl schema + retention coverage.

DEFECT A (schema, fixed here): _log() -- the ledger's ONLY writer (heartbeat_core.py) --
emitted "ts_et" but no "date" key, while its sibling writer for core-decisions-tick.json
(_write_tick_marker) has emitted "date" since inception. Verified consequence: any future
consumer that filters the 78MB ledger on a "date" key returns ZERO rows and exits clean --
a silent-zero trap (C7: silent success is failure). Repo-wide grep at investigation time
found no current consumer keying on "date" in this specific file, so this closed a LATENT
trap, not a live outage. Fix: _log() now derives "date" (YYYY-MM-DD) from the row's own
"ts_et" and injects it additively -- no existing field is removed, renamed, or
reinterpreted; no decision/score/gate/threshold/strike/placement behavior changes.

DEFECT B (retention): investigated, NOT implemented as a live-file bound tonight.
core-decisions.jsonl has ~180 repo-wide references. Two confirmed PRODUCTION consumers
do unrestricted full-history scans of the LIVE file with no date/glob filtering and no
archive-awareness:
  * setup/scripts/broker_fills.py:126 engine_order_ids() -- scans every row, every date,
    to build the set of engine-placed broker order ids used for fill attribution.
  * setup/scripts/backfill_fills_enriched.py:~150 _index_core() (via build_decision_index)
    -- same full-file scan, building an order_id -> derivation index used to enrich
    historical fills at reconciliation time, which by construction can run against
    fills from ANY past date.
setup/scripts/trade_matrix_build.py (the canonical trade-ledger builder wired into
CLAUDE.md doctrine and exercised by archive_ledgers.py's own restore-drill) also reads
core-decisions.jsonl account-grouped across full history, not a bounded window.
Rotating/truncating rows out of the LIVE file would silently degrade all three -- not a
crash, a WRONG (incomplete) answer with no error, which is the worse failure mode this
lane exists to prevent. Per the lane's own instructions, that is grounds to implement
Defect A only and report the finding rather than force a truncating rotation against
consumers this lane does not own.
What already exists and is NOT being duplicated: two daily archival scripts already give
core-decisions.jsonl real retention/custody coverage WITHOUT touching the live file's
row set --
  * setup/scripts/ledger_archive.py -- daily flat-copy into
    automation/archive/ledgers/<date>/, 30-day local retention (belt-and-suspenders vs.
    accidental deletion).
  * setup/scripts/archive_ledgers.py -- permanent, checksummed, off-volume
    (D:\\GammaArchive) content-addressed custody; every capture is read back and
    re-hashed to prove it landed intact.
These two guards below lock in that core-decisions.jsonl stays wired into BOTH, so a
future edit cannot silently drop this specific producer from either archive's source
list without going RED here.

RED-PROOF (run by hand, not part of this file -- see agent report for the transcript):
  1. temporarily revert _log() to the pre-fix body (write rec verbatim, no date
     injection) -> test_log_injects_date_from_ts_et FAILS (KeyError / assertion on
     "date" missing).
  2. restore the fix -> same test PASSES.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import heartbeat_core as hc  # noqa: E402


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _read_rows(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


@pytest.fixture
def scratch_ledger(tmp_path, monkeypatch):
    """Point hc.LEDGER at a scratch file for this test only -- never the real ledger."""
    fake = tmp_path / "core-decisions.jsonl"
    monkeypatch.setattr(hc, "LEDGER", fake)
    return fake


# --------------------------------------------------------------------------- #
# DEFECT A -- _log() injects "date" derived from "ts_et"
# --------------------------------------------------------------------------- #

def test_log_injects_date_from_ts_et(scratch_ledger):
    rec = {"ts_et": "2026-08-25T09:41:03", "account": "safe", "verdict": "HOLD"}
    hc._log(rec)
    rows = _read_rows(scratch_ledger)
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-08-25"
    assert rows[0]["date"] == rows[0]["ts_et"][:10]


def test_log_date_matches_ts_et_across_all_three_real_call_shapes(scratch_ledger):
    """Mirrors the three rec-construction shapes in heartbeat_core.py (SKIP_NO_DATA,
    the normal scored row, and the main() exception path) -- all three build ts_et the
    same way (et.strftime("%Y-%m-%dT%H:%M:%S")), so all three must get a matching date."""
    shapes = [
        {"ts_et": "2026-08-25T09:35:00", "account": "safe", "verdict": "SKIP_NO_DATA",
         "armed": False, "core_tick_id": None},
        {"ts_et": "2026-08-25T09:36:00", "account": "bold", "armed": False,
         "core_tick_id": "x", "spy": 645.1, "verdict": "HOLD", "side": None},
        {"ts_et": "2026-08-25T09:37:00", "account": "safe", "verdict": "ERROR",
         "error": "boom", "core_tick_id": "x"},
    ]
    for rec in shapes:
        hc._log(rec)
    rows = _read_rows(scratch_ledger)
    assert len(rows) == 3
    for row in rows:
        assert row["date"] == row["ts_et"][:10] == "2026-08-25"


def test_log_never_overwrites_a_caller_supplied_date(scratch_ledger):
    """Belt-and-suspenders: no current caller sets "date" itself, but if one ever did,
    _log() must not clobber it with its own derivation."""
    rec = {"ts_et": "2026-08-25T09:41:03", "date": "2099-01-01", "account": "safe"}
    hc._log(rec)
    rows = _read_rows(scratch_ledger)
    assert rows[0]["date"] == "2099-01-01"


def test_log_missing_ts_et_does_not_crash_and_omits_date(scratch_ledger):
    """A malformed/absent ts_et must never crash the live write path -- the row is
    logged without a "date", exactly as it behaved before this fix."""
    rec = {"account": "safe", "verdict": "HOLD"}
    hc._log(rec)  # must not raise
    rows = _read_rows(scratch_ledger)
    assert "date" not in rows[0]
    assert rows[0]["account"] == "safe"


def test_log_short_malformed_ts_et_does_not_crash_and_omits_date(scratch_ledger):
    rec = {"ts_et": "20", "account": "safe"}
    hc._log(rec)
    rows = _read_rows(scratch_ledger)
    assert "date" not in rows[0]


def test_log_preserves_every_existing_field_unchanged(scratch_ledger):
    """Hard constraint check: the fix is additive-only -- no existing field is removed,
    renamed, or given a different value."""
    rec = {
        "ts_et": "2026-08-25T09:41:03", "account": "safe", "armed": True,
        "core_tick_id": "2026-08-25T09:41:03.123456", "spy": 645.12, "ribbon": "BULL",
        "spread_cents": 12.5, "vix": 15.3, "htf_15m": "BULL", "verdict": "ENTER_BULL",
        "side": "C", "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON", "bear_score": 2,
        "bull_score": 9, "triggers": ["trendline_reclaim"], "reason": "passed scoring",
        "conviction": None,
    }
    original = dict(rec)
    hc._log(rec)
    # the caller's own dict object must not have been mutated in place
    assert rec == original
    rows = _read_rows(scratch_ledger)
    row = rows[0]
    for k, v in original.items():
        assert row[k] == v, f"field {k!r} changed: {v!r} -> {row[k]!r}"
    assert row["date"] == "2026-08-25"


def test_log_does_not_mutate_caller_dict_in_place(scratch_ledger):
    """Immutable-update pattern check (coding-style.md): _log() must build a NEW dict
    for the write rather than mutating the caller's rec object."""
    rec = {"ts_et": "2026-08-25T09:41:03", "account": "safe"}
    hc._log(rec)
    assert "date" not in rec  # caller's own object is untouched


# --------------------------------------------------------------------------- #
# DEFECT B -- retention coverage stays wired for core-decisions.jsonl
# (no live-file truncation shipped; these lock in the EXISTING archival coverage
# this lane relies on instead of a new bounded-rotation mechanism -- see module
# docstring for why a truncating rotation was rejected as unsafe tonight.)
# --------------------------------------------------------------------------- #

def test_daily_local_archive_still_covers_core_decisions():
    sys.path.insert(0, str(SCRIPTS))
    import ledger_archive as la  # noqa: E402 (imported here, not at module scope, to
    # keep this file's failure isolated to the retention-coverage claim it's making)
    assert "automation/state/core-decisions.jsonl" in la.SOURCES


def test_durable_offvolume_archive_still_covers_core_decisions():
    sys.path.insert(0, str(SCRIPTS))
    import archive_ledgers as al  # noqa: E402
    assert "automation/state/core-decisions.jsonl" in al.SOURCE_SPECS
