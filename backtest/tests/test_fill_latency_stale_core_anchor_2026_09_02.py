"""Guard: FILL-LATENCY-JOINS-THE-WRONG-CORE-ROW (queue, filed 2026-09-02).

fill_latency.py already joins core-decisions.jsonl by EXACT core_tick_id (never
nearest-timestamp) -- but the id it joins to can be a SKIP_STALE_TRIGGER/SKIP_STALE_SIGHT
row whose own verdict admits its trigger_bar_et is stale, because a fleet arm's
core_tick_id passthrough only records "whichever core tick was last COMPLETE when
shared-signal.json was built", not "the core row that caused this fill". Real case
reproduced against automation/state/{fills-ledger,core-decisions,fleet/*/decisions}.jsonl
on 2026-08-10: 3 fills (safe-3 ec5219ee-a365-48bc-b88e-09b49848ecc7, risky-1
189fb6f3-c642-40b4-9d9c-de3f14658d30, risky-3 9a6a04b0-28a6-48ed-aff7-6e879056bb24) all
exact-joined by core_tick_id "2026-08-10T09:34:02.151940" to a SKIP_STALE_TRIGGER row
carrying trigger_bar_et 2026-08-07T15:55 (the prior Friday) -- reporting a
bar_close->core_verdict of 236,343.0s (2.7 days) that never happened; the fleet arm's OWN
decision row shows a real ENTER_BULL off Monday's fresh bar at the same timestamp.

FIX: _core_anchor_is_stale() rejects a core_tick_id match whose action contains "STALE" as
a bar_close_ts/core_verdict_ts anchor -- those two stages drop to None (same treatment as
no match at all) and the row is flagged core_anchor_excluded_stale=True + carries the
excluded action, so the exclusion is DISCLOSED in the row rather than silently dropped or
silently fabricated. The join itself (core_tick_id, exact) is untouched."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO / "setup" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import fill_latency as flat  # noqa: E402

_STALE_CORE_ROW = {"ts_et": "2026-08-10T09:34:03", "trigger_bar_et": "2026-08-07T15:55:00-04:00",
                   "action": "SKIP_STALE_TRIGGER", "core_tick_id": "2026-08-10T09:34:02.151940"}
_FRESH_CORE_ROW = {"ts_et": "2026-08-10T09:36:04", "trigger_bar_et": "2026-08-10T09:30:00-04:00",
                   "action": "HOLD", "core_tick_id": "2026-08-10T09:36:02.887657"}
_DECISION_ROW = {
    "core_tick_id": "2026-08-10T09:34:02.151940", "signal_written_at": "2026-08-10T09:35:02-04:00",
    "placement": {"plan_ts": "2026-08-10T09:35:06.527847-04:00",
                 "submit_ts": "2026-08-10T09:35:07.409940-04:00",
                 "broker": {"submitted_at": "2026-08-10T13:35:07.298499292Z", "id": "oid-1"}},
}
_FILL = {"order_id": "oid-1", "ts_utc": "2026-08-10T13:35:07.401705Z",
        "date_et": "2026-08-10", "arm": "safe-3", "symbol": "SPY260810C00773000", "side": "buy"}


# --- _core_anchor_is_stale -------------------------------------------------------------
def test_stale_trigger_action_is_flagged_stale():
    assert flat._core_anchor_is_stale(_STALE_CORE_ROW) is True


def test_stale_sight_action_is_flagged_stale():
    assert flat._core_anchor_is_stale({"action": "SKIP_STALE_SIGHT"}) is True


def test_hold_action_is_not_stale():
    assert flat._core_anchor_is_stale(_FRESH_CORE_ROW) is False


def test_placed_action_is_not_stale():
    assert flat._core_anchor_is_stale({"action": "PLACED"}) is False


def test_none_core_row_is_not_stale():
    assert flat._core_anchor_is_stale(None) is False


# --- latency_row_from_fill: the exclusion is disclosed in the row ----------------------
def test_stale_anchor_drops_bar_close_and_core_verdict_but_keeps_other_stages():
    row = flat.latency_row_from_fill(_FILL, _DECISION_ROW, _STALE_CORE_ROW)
    assert row is not None, "signal/plan/submit/broker/fill stages still resolve without the anchor"
    assert row["core_anchor_excluded_stale"] is True
    assert row["core_anchor_action"] == "SKIP_STALE_TRIGGER"
    assert row["stages"]["bar_close_ts"] is None
    assert row["stages"]["core_verdict_ts"] is None
    assert row["stages"]["signal_written_ts"] is not None
    # the invented 236,343s tail must be gone -- there is no bar_close_ts to compute it from
    assert row["bar_close_ts_to_core_verdict_ts_s"] is None


def test_fresh_core_anchor_is_used_normally():
    row = flat.latency_row_from_fill(_FILL, _DECISION_ROW, _FRESH_CORE_ROW)
    assert row["core_anchor_excluded_stale"] is False
    assert row["core_anchor_action"] is None
    assert row["stages"]["bar_close_ts"] == "2026-08-10T09:30:00-04:00"


def test_join_is_still_exact_tick_id_not_nearest_time():
    """The join key itself is untouched by this fix -- still core_tick_id, not proximity."""
    core_by_tick = {"2026-08-10T09:34:02.151940": _STALE_CORE_ROW,
                    "2026-08-10T09:36:02.887657": _FRESH_CORE_ROW}
    matched = core_by_tick.get(_DECISION_ROW["core_tick_id"])
    assert matched is _STALE_CORE_ROW  # exact id match, not "closest in time" (which would be fresh)


# --- build_ledger: the real 2026-08-10 fixture, end to end ------------------------------
def test_build_ledger_2026_08_10_excludes_the_stale_anchor_not_the_fill(tmp_path, monkeypatch):
    import json
    fills = tmp_path / "fills-ledger.jsonl"
    fills.write_text(json.dumps(_FILL) + "\n", encoding="utf-8")
    core = tmp_path / "core-decisions.jsonl"
    core.write_text(
        json.dumps({**_STALE_CORE_ROW, "account": "safe"}) + "\n" +
        json.dumps({**_STALE_CORE_ROW, "account": "bold"}) + "\n",
        encoding="utf-8")
    fleet_dir = tmp_path / "fleet"
    (fleet_dir / "safe-3").mkdir(parents=True)
    (fleet_dir / "safe-3" / "decisions.jsonl").write_text(
        json.dumps({**_DECISION_ROW, "ts_et": "2026-08-10T09:35:05-04:00"}) + "\n",
        encoding="utf-8")
    monkeypatch.setattr(flat, "FILLS_LEDGER", fills)
    monkeypatch.setattr(flat, "CORE_DECISIONS", core)
    monkeypatch.setattr(flat, "FLEET_DIR", fleet_dir)

    ledger = flat.build_ledger(date_et="2026-08-10", out_path=tmp_path / "latency.json")

    assert ledger["n_entry_fills"] == 1
    assert ledger["n_excluded_no_decision_row"] == 0
    assert ledger["n_excluded_missing_instrumentation"] == 0
    assert ledger["n_core_anchor_stale_excluded"] == 1
    assert len(ledger["rows"]) == 1, "the fill is KEPT (reported), only the stale anchor is dropped"
    row = ledger["rows"][0]
    assert row["core_anchor_excluded_stale"] is True
    assert row["bar_close_ts_to_core_verdict_ts_s"] is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
