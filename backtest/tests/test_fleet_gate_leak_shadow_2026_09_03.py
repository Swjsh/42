"""Guard suite for setup/scripts/fleet_gate_leak_shadow.py -- the nightly instrument that
joins core safe/bold verdicts x REAL fills per core_tick_id (queue.md
FLEET-GATE-LEAK-SHADOW), feeding the frozen decision rule in
analysis/recommendations/prereg-fleet-gate-inheritance-2026-09-03.md.

The guards below pin the two mechanics that would silently corrupt the audit if broken:

  1. ONE REAL FILL COUNTS ONCE. `fleet_live.py` re-logs the SAME persisting decision every
     ~1-3 min while a signal condition holds (the exact bug
     verify-fleet-gates-ledger-binding-check-2.md caught in the ORIGINAL, now-superseded
     decision-row-count methodology). A single real round trip must never be attributed to
     more than one qualifying tick.
  2. NO LOOK-AHEAD. A round trip can only be claimed by a tick whose own timestamp is <=
     the round trip's entry_ts_et -- the gate label a claimed row carries must always come
     from the SAME tick that precedes (never follows) its real fill.

Plus: the classify/finalize pure functions, the summary statistics' honest degradation on
thin data, and an end-to-end idempotent run() against fixture artifacts.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "automation" / "state" / "fleet", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import fleet_gate_leak_shadow as fgls  # noqa: E402


# ---------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------
def _core_row(account, ts_et, action, verdict, vix=15.0, core_tick_id=None):
    return {"ts_et": ts_et, "account": account, "action": action, "verdict": verdict,
            "vix": vix, "core_tick_id": core_tick_id or ts_et}


def _rt(entry_ts_et, side, exit_ts_et=None, qty=3, real_pnl=100.0):
    return {"entry_ts_et": entry_ts_et, "exit_ts_et": exit_ts_et or entry_ts_et,
            "side": side, "qty": qty, "real_pnl": real_pnl}


def _ev(tick_iso, direction="BULL", core_tick_id=None, gate="SKIP_TEST"):
    return {"core_tick_id": core_tick_id or tick_iso, "tick_dt": datetime.fromisoformat(tick_iso),
            "date_et": tick_iso[:10], "vix": 15.0, "cohort": "bypass",
            "refused_account": "safe", "gate": gate, "gate_param_key": None,
            "is_symmetric_gate": False, "direction": direction}


# ---------------------------------------------------------------------------------
# 1. classify_tick -- bypass / mirror / control / symmetric-gate detection
# ---------------------------------------------------------------------------------
def test_classify_tick_bypass_safe_gated_bold_entered():
    safe = _core_row("safe", "2026-08-12T14:16:02", "SKIP_STRUCTURE_VETO", "SKIP_STRUCTURE_VETO")
    bold = _core_row("bold", "2026-08-12T14:16:02", "PLACED", "ENTER_BULL")
    events = fgls.classify_tick("2026-08-12T14:16:02.973209", safe, bold)
    bypass = [e for e in events if e["cohort"] == "bypass"]
    assert len(bypass) == 1
    assert bypass[0]["refused_account"] == "safe"
    assert bypass[0]["gate"] == "SKIP_STRUCTURE_VETO"
    assert bypass[0]["gate_param_key"] == "structure_veto_enabled"
    assert bypass[0]["direction"] == "BULL"


def test_classify_tick_mirror_bold_gated_safe_entered():
    safe = _core_row("safe", "2026-08-13T15:11:02", "PLACED", "ENTER_BULL")
    bold = _core_row("bold", "2026-08-13T15:11:02", "SKIP_CONF_LVL_REC_AFTERNOON",
                      "SKIP_CONF_LVL_REC_AFTERNOON")
    events = fgls.classify_tick("2026-08-13T15:11:02.929340", safe, bold)
    bypass = [e for e in events if e["cohort"] == "bypass"]
    assert len(bypass) == 1
    assert bypass[0]["refused_account"] == "bold"
    assert bypass[0]["gate"] == "SKIP_CONF_LVL_REC_AFTERNOON"
    assert bypass[0]["direction"] == "BULL"


def test_classify_tick_control_both_passed():
    safe = _core_row("safe", "2026-08-27T10:00:00", "PLACED", "ENTER_BEAR")
    bold = _core_row("bold", "2026-08-27T10:00:00", "PLACED", "ENTER_BEAR")
    events = fgls.classify_tick("2026-08-27T10:00:00.000000", safe, bold)
    control = [e for e in events if e["cohort"] == "control"]
    assert len(control) == 1
    assert control[0]["direction"] == "BEAR"
    assert control[0]["refused_account"] is None
    assert control[0]["gate"] is None


def test_classify_tick_no_events_when_both_hold():
    safe = _core_row("safe", "2026-09-03T14:53:04", "HOLD", "HOLD")
    bold = _core_row("bold", "2026-09-03T14:53:04", "HOLD", "HOLD")
    assert fgls.classify_tick("2026-09-03T14:53:04.000000", safe, bold) == []


def test_classify_tick_symmetric_gate_flagged_true():
    """SKIP_LATE_ENTRY firing on BOTH accounts at the same tick is a shared session-clock
    gate, not a safe/bold cohort divergence -- must be flagged, never silently mixed in."""
    safe = _core_row("safe", "2026-08-17T15:02:02", "SKIP_LATE_ENTRY", "ENTER_BEAR")
    bold = _core_row("bold", "2026-08-17T15:02:02", "SKIP_LATE_ENTRY", "ENTER_BEAR")
    events = fgls.classify_tick("2026-08-17T15:02:02.438566", safe, bold)
    bypass = [e for e in events if e["cohort"] == "bypass" and e["refused_account"] == "safe"]
    assert len(bypass) == 1
    assert bypass[0]["is_symmetric_gate"] is True


# ---------------------------------------------------------------------------------
# 2. assign_real_fills -- dedup ("one real fill counts once") + no-look-ahead
# ---------------------------------------------------------------------------------
def test_one_real_fill_counts_once_against_repeated_enter_ticks():
    """The exact bug the skeptic pass caught: decisions.jsonl repeats the SAME ENTER
    signal every ~1min while a condition holds. 3 qualifying ticks, 1 minute apart, ALL
    within reach of the SAME single real fill -- exactly one of them may claim it."""
    events = [
        _ev("2026-08-12T14:16:00", core_tick_id="t1"),
        _ev("2026-08-12T14:17:00", core_tick_id="t2"),
        _ev("2026-08-12T14:18:00", core_tick_id="t3"),
    ]
    round_trips = [_rt("2026-08-12T14:17:10", "C", real_pnl=507.0)]
    out = fgls.assign_real_fills(events, round_trips, window_sec=300)
    filled = [r for r in out if r["real_fill"]]
    assert len(filled) == 1, "exactly one tick may claim the one real fill, not three"
    assert filled[0]["core_tick_id"] == "t1", "the EARLIEST qualifying tick claims it"
    assert filled[0]["real_pnl"] == 507.0
    # the other two ticks must NOT show a phantom entry
    unfilled = [r for r in out if not r["real_fill"]]
    assert len(unfilled) == 2
    assert all(r["real_pnl"] is None for r in unfilled)


def test_no_look_ahead_gate_label_matches_the_claiming_ticks_own_gate():
    """Two DIFFERENT gates fire at two different ticks; a real fill lands only inside the
    SECOND tick's window. The claimed row's gate must be the SECOND tick's gate (the one
    whose window causally contains the fill), never the first tick's -- and the fill's
    entry_ts_et must be >= the claiming tick's own timestamp (no look-ahead in reverse)."""
    t1 = _ev("2026-08-07T12:36:00", core_tick_id="early-tick", gate="SKIP_STRUCTURE_VETO")
    t2 = _ev("2026-08-07T12:45:00", core_tick_id="late-tick", gate="SKIP_BULL_1100_1200")
    # entry lands 5s after t2, and 9 minutes after t1 -- OUTSIDE t1's 300s window entirely
    round_trips = [_rt("2026-08-07T12:45:05", "C", real_pnl=433.0)]
    out = fgls.assign_real_fills([t1, t2], round_trips, window_sec=300)
    by_tick = {r["core_tick_id"]: r for r in out}
    assert by_tick["early-tick"]["real_fill"] is False
    assert by_tick["late-tick"]["real_fill"] is True
    assert by_tick["late-tick"]["gate"] == "SKIP_BULL_1100_1200"
    claim_dt = datetime.fromisoformat("2026-08-07T12:45:00")
    entry_dt = datetime.fromisoformat(by_tick["late-tick"]["entry_ts_et"])
    assert entry_dt >= claim_dt, "a claimed fill's entry must never precede its own tick"


def test_fill_before_the_tick_is_never_claimed():
    """A round trip whose entry predates a tick entirely (e.g. logged clock skew) must
    never be attributed to that tick, even though nothing else exists to claim it."""
    ev = _ev("2026-08-07T12:45:00", core_tick_id="t1")
    round_trips = [_rt("2026-08-07T12:44:59", "C", real_pnl=999.0)]  # 1s BEFORE the tick
    out = fgls.assign_real_fills([ev], round_trips, window_sec=300)
    assert out[0]["real_fill"] is False
    assert out[0]["real_pnl"] is None


def test_side_mismatch_is_never_claimed():
    """A BULL event only claims a CALL fill; a PUT fill inside the same window must not
    be misattributed to a BULL gate refusal."""
    ev = _ev("2026-08-07T12:45:00", direction="BULL", core_tick_id="t1")
    round_trips = [_rt("2026-08-07T12:46:00", "P", real_pnl=200.0)]
    out = fgls.assign_real_fills([ev], round_trips, window_sec=300)
    assert out[0]["real_fill"] is False


def test_outside_window_is_never_claimed():
    ev = _ev("2026-08-07T12:45:00", core_tick_id="t1")
    round_trips = [_rt("2026-08-07T12:50:01", "C", real_pnl=200.0)]  # 301s later
    out = fgls.assign_real_fills([ev], round_trips, window_sec=300)
    assert out[0]["real_fill"] is False


# ---------------------------------------------------------------------------------
# 3. finalize_row -- in_sample flag, JSON-safety
# ---------------------------------------------------------------------------------
def test_finalize_row_in_sample_true_on_or_before_cutoff():
    ev = _ev("2026-09-03T10:00:00", core_tick_id="t1")
    matched = fgls.assign_real_fills([ev], [], window_sec=300)[0]
    row = fgls.finalize_row("safe-3", matched, in_sample_cutoff="2026-09-03")
    assert row["in_sample"] is True
    assert "tick_dt" not in row, "raw datetime must never leak into the JSON-safe row"


def test_finalize_row_in_sample_false_after_cutoff():
    ev = _ev("2026-09-04T10:00:00", core_tick_id="t1")
    matched = fgls.assign_real_fills([ev], [], window_sec=300)[0]
    row = fgls.finalize_row("safe-3", matched, in_sample_cutoff="2026-09-03")
    assert row["in_sample"] is False


# ---------------------------------------------------------------------------------
# 4. summary statistics -- honest degradation on thin data
# ---------------------------------------------------------------------------------
def test_pnl_stats_empty_when_no_real_fills():
    rows = [{"real_fill": False, "real_pnl": None, "date_et": "2026-08-06"}]
    stats = fgls._pnl_stats(rows)
    assert stats == {"n": 0, "sum": 0.0, "mean": None, "ci": None, "top3_concentration_share": None}


def test_pnl_stats_ci_none_below_two_days():
    rows = [{"real_fill": True, "real_pnl": 50.0, "date_et": "2026-08-06"}]
    stats = fgls._pnl_stats(rows)
    assert stats["n"] == 1
    assert stats["ci"] is None


def test_pnl_stats_ci_shape_with_two_or_more_days():
    rows = ([{"real_fill": True, "real_pnl": 50.0, "date_et": "2026-08-06"} for _ in range(5)]
            + [{"real_fill": True, "real_pnl": -20.0, "date_et": "2026-08-07"} for _ in range(5)])
    stats = fgls._pnl_stats(rows)
    assert stats["ci"] is not None
    assert set(stats["ci"]) == {"n_boot", "n_days_clustered", "ci_lower_2.5", "ci_upper_97.5"}
    assert stats["ci"]["ci_lower_2.5"] <= stats["ci"]["ci_upper_97.5"]


def test_cell_stats_share_computation():
    rows = [{"real_fill": True, "real_pnl": 10.0, "date_et": "2026-08-06"},
            {"real_fill": False, "real_pnl": None, "date_et": "2026-08-06"},
            {"real_fill": False, "real_pnl": None, "date_et": "2026-08-07"},
            {"real_fill": False, "real_pnl": None, "date_et": "2026-08-07"}]
    cell = fgls._cell_stats(rows)
    assert cell["n_ticks"] == 4
    assert cell["n_real_entries"] == 1
    assert cell["share"] == pytest.approx(0.25)


# ---------------------------------------------------------------------------------
# 5. run() -- end-to-end idempotent backfill against fixture artifacts
# ---------------------------------------------------------------------------------
@pytest.fixture
def _wired_fixtures(tmp_path, monkeypatch):
    core_path = tmp_path / "core-decisions.jsonl"
    fills_path = tmp_path / "fills-ledger.jsonl"
    out_dir = tmp_path / "out"
    ledger = out_dir / "fleet-gate-leak-ledger.jsonl"
    summary = out_dir / "fleet-gate-leak-summary.json"

    core_rows = [
        _core_row("safe", "2026-08-06T11:21:02", "SKIP_STRUCTURE_VETO", "SKIP_STRUCTURE_VETO",
                  core_tick_id="2026-08-06T11:21:02.000000"),
        _core_row("bold", "2026-08-06T11:21:02", "PLACED", "ENTER_BULL",
                  core_tick_id="2026-08-06T11:21:02.000000"),
        _core_row("safe", "2026-08-06T13:00:00", "PLACED", "ENTER_BEAR",
                  core_tick_id="2026-08-06T13:00:00.000000"),
        _core_row("bold", "2026-08-06T13:00:00", "PLACED", "ENTER_BEAR",
                  core_tick_id="2026-08-06T13:00:00.000000"),
    ]
    core_path.write_text("".join(json.dumps(r) + "\n" for r in core_rows), encoding="utf-8")

    fills = [
        {"activity_id": "a1", "arm": "safe-3", "symbol": "SPY260806C00700000", "side": "buy",
         "qty": 5.0, "price": 1.17, "date_et": "2026-08-06", "ts_et": "2026-08-06T11:22:07.262113",
         "attribution": "engine"},
        {"activity_id": "a2", "arm": "safe-3", "symbol": "SPY260806C00700000", "side": "sell",
         "qty": 5.0, "price": 2.15, "date_et": "2026-08-06", "ts_et": "2026-08-06T11:40:00.000000",
         "attribution": "engine"},
    ]
    fills_path.write_text("".join(json.dumps(f) + "\n" for f in fills), encoding="utf-8")

    monkeypatch.setattr(fgls, "CORE_DECISIONS", core_path)
    monkeypatch.setattr(fgls, "OUT_DIR", out_dir)
    monkeypatch.setattr(fgls, "LEDGER", ledger)
    monkeypatch.setattr(fgls, "SUMMARY", summary)
    monkeypatch.setattr(fgls, "FILLS_LEDGER", fills_path)
    monkeypatch.setattr(fgls, "ARMS", ("safe-3",))
    monkeypatch.setattr(fgls, "DECISION_FOCUS_ARMS", ("safe-3",))
    return {"ledger": ledger, "summary": summary}


def test_run_backfills_and_writes_rows(_wired_fixtures):
    out = fgls.run()
    assert "error" not in out, out
    rows = fgls._read_jsonl(_wired_fixtures["ledger"])
    assert len(rows) >= 2, "at least the bypass row and the control row must be written"
    bypass_rows = [r for r in rows if r["cohort"] == "bypass"]
    assert len(bypass_rows) == 1
    assert bypass_rows[0]["real_fill"] is True
    assert bypass_rows[0]["real_pnl"] == pytest.approx(490.0)  # (2.15-1.17)*100*5 = 490
    assert bypass_rows[0]["in_sample"] is True


def test_run_is_idempotent_on_a_second_fire(_wired_fixtures):
    fgls.run()
    out2 = fgls.run()
    assert out2["new_this_run"] == 0
    rows = fgls._read_jsonl(_wired_fixtures["ledger"])
    n_after_second = len(rows)
    fgls.run()
    rows_after_third = fgls._read_jsonl(_wired_fixtures["ledger"])
    assert len(rows_after_third) == n_after_second, "re-running must never duplicate a row"


def test_run_summary_stats_do_not_inflate_across_repeated_runs(_wired_fixtures):
    """Regression guard for a caught bug: `all_finalized` must be the freshly recomputed,
    already-deduplicated row set every run -- never `existing-on-disk PLUS
    freshly-recomputed`, which would silently double n_rows_total/n_real_entries/pnl sums
    on every subsequent fire without ever showing up in new_this_run (which only tracks
    disk writes)."""
    out1 = fgls.run()
    out2 = fgls.run()
    out3 = fgls.run()
    assert out1["n_rows_total"] == out2["n_rows_total"] == out3["n_rows_total"]
    bypass1 = [c for c in out1["gate_arm_cells"] if c["arm"] == "safe-3"]
    bypass3 = [c for c in out3["gate_arm_cells"] if c["arm"] == "safe-3"]
    assert bypass1 == bypass3, "gate x arm cells must be byte-identical across repeated runs"
    ctrl1 = out1["control_cohort_by_arm"]
    ctrl3 = out3["control_cohort_by_arm"]
    assert ctrl1 == ctrl3, "control cohort stats must be byte-identical across repeated runs"


def test_run_summary_has_expected_shape(_wired_fixtures):
    out = fgls.run()
    for key in ("window", "n_ticks_joined_since_start", "gate_arm_cells",
                "control_cohort_by_arm", "vix_bands_bypass_only", "named_winning_days",
                "september_window", "forward_bar", "status", "decision_rule"):
        assert key in out, key
    assert out["window"]["entry_window_sec"] == 300
    assert out["status"] in ("ACCRUING", "BAR_MET_AWAITING_VERDICT")
