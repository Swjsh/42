"""Guard for HISTORICAL-REPLAY-TRIGGER-LEVEL-SUPERSEDED (2026-09-03, queue item).

backtest/tools/historical_replay.py#load_core_trigger_lookup used to reconstruct every
walked trade's trigger_level via a nearest-in-time match against core-decisions.jsonl's
trigger_level_exact -- but every placed row now carries the EXACT level exit_manager.py
actually armed (exec.trigger_level / placement.trigger_level, joinable by broker order id),
and trades_enriched.py has stamped that order-id-joined value onto trades-enriched.jsonl's
own `trigger_level` field for every row since the 2026-09-01 fix (see
test_trades_enriched_trigger_level_2026_09_01.py). This fix re-points the lookup to that
exact field FIRST, falling back to the old reconstruction only when it is absent, and labels
each resolution `trigger_level_source` = 'exact' | 'reconstructed' instead of the old
blanket "trigger_level is RECONSTRUCTED" disclosure.

Pin, in order:
  1. A trade whose trades-enriched.jsonl row carries a non-null `trigger_level` resolves
     'exact' with that exact value -- the core-decisions reconstruction lookup is never
     even consulted for gap-matching in this case.
  2. A trade with `trigger_level` absent/None falls back to the reconstruction (nearest-in-
     time core-decisions.jsonl trigger_level_exact within TRIGGER_LEVEL_MATCH_TOL_S) and is
     labeled 'reconstructed'.
  3. A trade with `trigger_level` absent AND no reconstruction match resolves (None,
     'reconstructed') -- never silently mislabeled 'exact'.
  4. exact == 0.0 (falsy but a real level) must still resolve as 'exact', not fall through
     to the reconstruction (the check is `is not None`, never a truthiness check).
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "backtest", REPO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import historical_replay as hr  # noqa: E402


def _lookup_with(date_str: str, side: str, ts: str, level: float) -> dict:
    return {(date_str, side): [(dt.datetime.fromisoformat(ts), level)]}


def test_exact_field_present_wins_and_reconstruction_never_needed():
    t = {"trigger_level": 765.41, "date": "2026-09-02", "right": "C",
         "entry_ts_et": "2026-09-02T10:00:00"}
    # lookup deliberately holds a DIFFERENT level -- if the fallback path were taken by
    # mistake, this assertion would catch it.
    lookup = _lookup_with("2026-09-02", "C", "2026-09-02T10:00:05", 999.99)
    level, source = hr.resolve_trigger_level_for_trade(t, lookup)
    assert level == 765.41
    assert source == "exact"


def test_missing_exact_field_falls_back_to_reconstruction():
    t = {"trigger_level": None, "date": "2026-09-02", "right": "P",
         "entry_ts_et": "2026-09-02T10:00:00"}
    lookup = _lookup_with("2026-09-02", "P", "2026-09-02T10:00:05", 760.12)
    level, source = hr.resolve_trigger_level_for_trade(t, lookup)
    assert level == 760.12
    assert source == "reconstructed"


def test_missing_exact_field_and_no_reconstruction_match_stays_reconstructed_none():
    t = {"trigger_level": None, "date": "2026-09-02", "right": "P",
         "entry_ts_et": "2026-09-02T10:00:00"}
    level, source = hr.resolve_trigger_level_for_trade(t, {})
    assert level is None
    assert source == "reconstructed"


def test_exact_zero_still_counts_as_exact_not_falsy_fallthrough():
    t = {"trigger_level": 0.0, "date": "2026-09-02", "right": "C",
         "entry_ts_et": "2026-09-02T10:00:00"}
    lookup = _lookup_with("2026-09-02", "C", "2026-09-02T10:00:05", 500.0)
    level, source = hr.resolve_trigger_level_for_trade(t, lookup)
    assert level == 0.0
    assert source == "exact"


def test_key_absent_entirely_falls_back_same_as_none():
    """A trades-enriched.jsonl row shape that never had the key at all (pre-09-01 rows)
    must behave identically to an explicit None -- .get() default, not a KeyError."""
    t = {"date": "2026-09-02", "right": "C", "entry_ts_et": "2026-09-02T10:00:00"}
    lookup = _lookup_with("2026-09-02", "C", "2026-09-02T10:00:05", 700.5)
    level, source = hr.resolve_trigger_level_for_trade(t, lookup)
    assert level == 700.5
    assert source == "reconstructed"
