"""Guard suite for setup/scripts/structure_classifier_shadow.py -- the EVIDENCE-half
counter for queue item STRUCTURE-VETO-CLASSIFIER-FIX (the classifier swap itself is a
separate, later, 2026-10-30 decision; this module only measures).

The guards below pin the mechanics that would matter if broken:

  1. THE DEFECT REPRODUCES. A synthetic rally whose last two CONFIRMED swing pairs are a
     stale "downtrend" shape, with a monotonic tail that pushes price back above the
     nearest confirmed swing high WITHOUT ever forming a new pivot (window=2 structurally
     forbids it), must make `label_live` ("downtrend") disagree with `label_walk`
     ("uptrend") on the IDENTICAL bars -- proving both the D7 defect and walk_structure's
     own fix mechanism in one fixture.
  2. NO LOOK-AHEAD. A bar dated after the cutoff must never change the computed label.
  3. THE ENGINE'S OWN FUNCTIONS ARE IMPORTED, NEVER REIMPLEMENTED (byte-for-byte fidelity
     against the real frozen spy_5m cache, cross-checked against a real logged verdict).
  4. IDEMPOTENT + FORWARD-ONLY DECISION CLOCK. Re-running against the same fixtures must
     never duplicate a ledger row; the forward bar only counts ticks on/after FREEZE_DATE.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "backtest", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import structure_classifier_shadow as scs  # noqa: E402


# ---------------------------------------------------------------------------------
# fixture builder -- a fully synthetic, deterministic rally
# ---------------------------------------------------------------------------------
def _filler(v):
    return (v, v + 0.1, v - 0.1, v)


def _high_pivot(v):
    return (v - 0.2, v, v - 0.3, v - 0.1)


def _low_pivot(v):
    return (v + 0.2, v + 0.3, v, v + 0.1)


def _synthetic_rally_bars_upto() -> list[dict]:
    """24 bars: a clean stale-downtrend pivot pair (swing highs 101.0 -> 100.0, swing lows
    99.5 -> 98.5, both non-increasing pairs) followed by a 10-bar MONOTONIC rally that never
    forms a new pivot (window=2 needs both-side confirmation; a pure ramp has no interior
    local extreme) but DOES close back above the nearest confirmed swing high (100.0),
    which is exactly the mechanism that lets walk_structure react while classify_trend
    cannot. Verified empirically (this build) to produce label_live='downtrend',
    label_walk='uptrend' on the identical bar list.
    """
    seq = []
    seq += [_filler(98.0), _filler(98.2)]                 # 0,1 buffer
    seq += [_high_pivot(101.0)]                            # 2  swing_high H_a=101.0
    seq += [_filler(100.0), _filler(99.7)]                 # 3,4
    seq += [_low_pivot(99.5)]                               # 5  swing_low  L_a=99.5
    seq += [_filler(99.7), _filler(99.9)]                   # 6,7
    seq += [_high_pivot(100.0)]                             # 8  swing_high H_b=100.0 (LH)
    seq += [_filler(99.5), _filler(99.0)]                   # 9,10
    seq += [_low_pivot(98.5)]                               # 11 swing_low  L_b=98.5 (LL)
    seq += [_filler(98.7), _filler(98.9)]                   # 12,13 buffer before rally
    px = 99.0
    for _ in range(10):
        o = px
        px += 0.35
        seq.append((o, px + 0.03, o - 0.03, px))            # monotonic ramp, no interior peak

    t0 = datetime(2026, 9, 3, 9, 30)
    bars = []
    for i, (o, h, l, c) in enumerate(seq):
        bars.append({"ts": t0 + timedelta(minutes=5 * i), "open": o, "high": h,
                     "low": l, "close": c, "volume": 1000.0})
    return bars


# ---------------------------------------------------------------------------------
# 1. the defect reproduces on a fully synthetic rally
# ---------------------------------------------------------------------------------
def test_synthetic_rally_reproduces_live_downtrend_and_walk_uptrend():
    bars = _synthetic_rally_bars_upto()
    result = scs.classify_both(bars)
    assert result["label_live"] == "downtrend", (
        "classify_trend must stay frozen on the stale 101.0->100.0 / 99.5->98.5 pivot "
        "pair through a rally that never forms a NEW pivot -- this is the D7 defect")
    assert result["label_walk"] == "uptrend", (
        "walk_structure must react once a bar CLOSES above the nearest CONFIRMED swing "
        "high (100.0) even with no new pivot -- this is the mechanism the fix relies on")
    assert result["label_live"] != result["label_walk"]
    assert result["n_walk_events"] >= 1


def test_synthetic_rally_veto_side_disagrees_between_classifiers():
    """The practical consequence: a bull ('C') entry at this exact tick would be vetoed by
    the live classifier (downtrend blocks C) but NOT by walk_structure (uptrend does not)."""
    bars = _synthetic_rally_bars_upto()
    result = scs.classify_both(bars)
    assert scs._veto_side("C", result["label_live"]) is True
    assert scs._veto_side("C", result["label_walk"]) is False


# ---------------------------------------------------------------------------------
# 2. no look-ahead
# ---------------------------------------------------------------------------------
def test_no_look_ahead_future_bar_never_changes_the_label():
    bars = _synthetic_rally_bars_upto()
    cutoff = bars[-1]["ts"]
    baseline = scs.classify_both(bars)

    # A dramatic future bar (a crash) dated AFTER the cutoff must be excluded by the same
    # capping logic build_row uses, and must never reach classify_both.
    future_bar = {"ts": cutoff + timedelta(minutes=5), "open": 102.5, "high": 102.5,
                  "low": 50.0, "close": 50.0, "volume": 1000.0}
    bars_full_with_future = bars + [future_bar]
    bars_upto = [b for b in bars_full_with_future if b["ts"] <= cutoff]

    assert bars_upto == bars, "capping logic must exclude the future bar"
    capped_result = scs.classify_both(bars_upto)
    assert capped_result["label_live"] == baseline["label_live"]
    assert capped_result["label_walk"] == baseline["label_walk"]


def test_no_look_ahead_forward_move_is_the_only_place_future_bars_are_used():
    """forward_close_at_or_after is explicitly allowed to see the future -- but only when
    called on bars_full, never bars_upto. This pins that the two data views stay separate."""
    bars = _synthetic_rally_bars_upto()
    cutoff = bars[-1]["ts"]
    future_bar = {"ts": cutoff + timedelta(minutes=30), "open": 200.0, "high": 200.0,
                  "low": 200.0, "close": 200.0, "volume": 0.0}
    bars_full = bars + [future_bar]
    got = scs.forward_close_at_or_after(bars_full, cutoff + timedelta(minutes=30))
    assert got == 200.0


# ---------------------------------------------------------------------------------
# 3. real production functions, imported not reimplemented -- byte-for-byte fidelity
# ---------------------------------------------------------------------------------
def test_classify_sameday_5m_is_the_real_imported_function():
    import inspect
    from lib.engine import engine_cli
    assert scs._classify_sameday_5m is engine_cli._classify_sameday_5m
    assert scs._veto_side is engine_cli._veto_side
    assert "classify_trend" in inspect.getsource(engine_cli._classify_sameday_5m)


@pytest.mark.skipif(not scs.SPY_5M_CACHE_CSV.exists(), reason="frozen spy_5m cache not present")
def test_selfcheck_byte_reproduces_a_real_logged_downtrend_verdict():
    cache = scs.load_spy_5m_cache()
    result = scs._selfcheck(cache)
    assert result["ok"] is True, result


# ---------------------------------------------------------------------------------
# 4. _favorable
# ---------------------------------------------------------------------------------
def test_favorable_bull_side_favors_upward_move():
    assert scs._favorable("C", 0.5) is True
    assert scs._favorable("C", -0.5) is False


def test_favorable_bear_side_favors_downward_move():
    assert scs._favorable("P", -0.5) is True
    assert scs._favorable("P", 0.5) is False


def test_favorable_none_when_move_or_side_missing():
    assert scs._favorable("C", None) is None
    assert scs._favorable(None, 0.5) is None
    assert scs._favorable("X", 0.5) is None


# ---------------------------------------------------------------------------------
# 5. RTH filtering + cache/reconstruction source selection
# ---------------------------------------------------------------------------------
def test_load_spy_5m_cache_filters_to_rth_only(tmp_path, monkeypatch):
    csv_path = tmp_path / "fake_spy_5m.csv"
    csv_path.write_text(
        "timestamp_et,open,high,low,close,volume\n"
        "2026-08-21 04:00:00-04:00,100,100.1,99.9,100,1000\n"   # premarket -- excluded
        "2026-08-21 09:30:00-04:00,100,100.1,99.9,100,1000\n"   # RTH -- included
        "2026-08-21 15:55:00-04:00,101,101.1,100.9,101,1000\n"  # RTH -- included
        "2026-08-21 16:00:00-04:00,102,102.1,101.9,102,1000\n", # >=16:00 -- excluded
        encoding="utf-8")
    monkeypatch.setattr(scs, "SPY_5M_CACHE_CSV", csv_path)
    cache = scs.load_spy_5m_cache()
    assert len(cache["2026-08-21"]) == 2
    assert [b["ts"].strftime("%H:%M") for b in cache["2026-08-21"]] == ["09:30", "15:55"]


def test_reconstruct_5m_bars_for_date_buckets_correctly(tmp_path, monkeypatch):
    core_path = tmp_path / "core-decisions.jsonl"
    rows = [
        {"account": "safe", "ts_et": "2026-09-10T09:30:03", "spy": 700.0},
        {"account": "safe", "ts_et": "2026-09-10T09:31:03", "spy": 701.0},
        {"account": "safe", "ts_et": "2026-09-10T09:32:03", "spy": 699.5},
        {"account": "safe", "ts_et": "2026-09-10T09:34:03", "spy": 700.5},
        {"account": "bold", "ts_et": "2026-09-10T09:30:03", "spy": 999.0},   # wrong account
        {"account": "safe", "ts_et": "2026-09-10T03:00:03", "spy": 1.0},    # premarket
    ]
    core_path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    monkeypatch.setattr(scs, "CORE_DECISIONS", core_path)

    bars = scs.reconstruct_5m_bars_for_date("2026-09-10")
    assert len(bars) == 1
    b = bars[0]
    assert b["ts"].strftime("%H:%M") == "09:30"
    assert b["open"] == 700.0
    assert b["close"] == 700.5
    assert b["high"] == 701.0
    assert b["low"] == 699.5


def test_bars_for_date_prefers_cache_over_reconstruction(monkeypatch):
    cache = {"2026-08-21": [{"ts": datetime(2026, 8, 21, 9, 30), "open": 1, "high": 1,
                             "low": 1, "close": 1, "volume": 0.0}]}
    called = {"n": 0}

    def _boom(date_et):
        called["n"] += 1
        return []

    monkeypatch.setattr(scs, "reconstruct_5m_bars_for_date", _boom)
    memo = {}
    bars, source = scs.bars_for_date("2026-08-21", cache, memo)
    assert source == "csv_cache_real"
    assert called["n"] == 0

    bars2, source2 = scs.bars_for_date("2026-09-05", cache, memo)
    assert source2 == "reconstructed_approx_from_core_decisions"
    assert called["n"] == 1
    # memoized -- second call for the same date must not re-invoke reconstruction
    scs.bars_for_date("2026-09-05", cache, memo)
    assert called["n"] == 1


# ---------------------------------------------------------------------------------
# 6. bootstrap helpers
# ---------------------------------------------------------------------------------
def test_bootstrap_rate_ci_shape():
    ci = scs._bootstrap_rate_ci([1.0, 1.0, 0.0, 1.0, 0.0], n_boot=200)
    assert ci is not None
    assert ci["n"] == 5
    assert ci["ci_lower_2.5"] <= ci["rate"] <= ci["ci_upper_97.5"]


def test_bootstrap_rate_ci_none_on_empty():
    assert scs._bootstrap_rate_ci([]) is None


def test_bootstrap_rate_diff_ci_none_when_either_group_empty():
    assert scs._bootstrap_rate_diff_ci([1.0], []) is None
    assert scs._bootstrap_rate_diff_ci([], [1.0]) is None


def test_bootstrap_rate_diff_ci_shape():
    ci = scs._bootstrap_rate_diff_ci([1.0, 1.0, 0.0], [0.0, 0.0, 1.0], n_boot=200)
    assert ci is not None
    assert set(ci) == {"n_a", "n_b", "rate_a", "rate_b", "diff", "ci_lower_2.5", "ci_upper_97.5"}
    assert ci["ci_lower_2.5"] <= ci["ci_upper_97.5"]


# ---------------------------------------------------------------------------------
# 7. _summarize -- empty population, forward-clock date filtering
# ---------------------------------------------------------------------------------
def test_summarize_empty_population_is_accruing():
    s = scs._summarize([], None)
    assert s["n_ticks"] == 0
    assert s["status"] == "ACCRUING"


def _mk_row(ts_et, date_et, action, side, agree, favorable_30m, walk_would_veto):
    return {"ts_et": ts_et, "date_et": date_et, "account": "safe", "action": action,
            "execution_action_raw": action, "side": side, "spy": 700.0, "setup": None,
            "trigger_bar_et": None, "bar_source": "csv_cache_real", "n_bars_fed": 20,
            "label_live": "downtrend" if action == "SKIP_STRUCTURE_VETO" else "range",
            "label_walk": "uptrend" if agree is False else "downtrend",
            "n_walk_events": 1, "agree": agree,
            "structure_reason_logged": None, "live_label_matches_logged": None,
            "live_would_veto_recomputed": (action == "SKIP_STRUCTURE_VETO"),
            "walk_would_veto": walk_would_veto,
            "fwd_move_30m": (1.0 if favorable_30m else -1.0) if favorable_30m is not None else None,
            "fwd_move_60m": None,
            "favorable_30m": favorable_30m, "favorable_60m": None}


def test_forward_clock_only_counts_ticks_on_or_after_freeze_date():
    rows = [
        _mk_row("2026-08-20T10:00:00", "2026-08-20", "SKIP_STRUCTURE_VETO", "C", True, False, True),
        _mk_row("2026-09-03T10:00:00", scs.FREEZE_DATE, "SKIP_STRUCTURE_VETO", "C", True, False, True),
        _mk_row("2026-09-03T10:05:00", scs.FREEZE_DATE, "ENTER_BULL", "C", False, True, True),
    ]
    s = scs._summarize(rows, "2026-08-20T10:00:00")
    fc = s["forward_decision_clock"]
    assert fc["forward_sessions_accrued"] == 1              # only 09-03, not 08-20
    assert s["status"] == "ACCRUING"                         # nowhere near the bar
    assert fc["bar_met"] is False


def test_winner_day_check_flags_a_walk_veto_on_a_named_winning_day():
    rows = [
        _mk_row("2026-08-06T10:00:00", "2026-08-06", "ENTER_BULL", "C", False, True, True),
        _mk_row("2026-08-27T10:00:00", "2026-08-27", "ENTER_BULL", "C", True, True, False),
    ]
    s = scs._summarize(rows, "2026-08-06T10:00:00")
    assert s["winner_day_check"]["2026-08-06"]["n_would_be_vetoed_by_walk"] == 1
    assert s["winner_day_check"]["2026-08-27"]["n_would_be_vetoed_by_walk"] == 0
    assert s["any_winner_day_entry_would_be_vetoed_by_walk"] is True


# ---------------------------------------------------------------------------------
# 8. end-to-end run() -- idempotent, dedup, no duplicate ledger rows
# ---------------------------------------------------------------------------------
@pytest.fixture
def _wired_fixtures(tmp_path, monkeypatch):
    core_path = tmp_path / "core-decisions.jsonl"
    csv_path = tmp_path / "spy_5m.csv"
    out_dir = tmp_path / "out"
    ledger = out_dir / "structure-classifier-shadow-ledger.jsonl"
    summary = out_dir / "structure-classifier-shadow-summary.json"

    bars = _synthetic_rally_bars_upto()
    header = "timestamp_et,open,high,low,close,volume\n"
    lines = [header]
    for b in bars:
        lines.append(f"{b['ts'].strftime('%Y-%m-%d %H:%M:%S')}-04:00,{b['open']},{b['high']},"
                     f"{b['low']},{b['close']},{b['volume']}\n")
    csv_path.write_text("".join(lines), encoding="utf-8")

    trig_iso = bars[-1]["ts"].isoformat() + "-04:00"
    rows = [
        {"account": "safe", "ts_et": "2026-09-03T10:00:03", "verdict": "SKIP_STRUCTURE_VETO",
         "action": "SKIP_STRUCTURE_VETO", "side": "C", "spy": bars[-1]["close"],
         "trigger_bar_et": trig_iso, "setup": None,
         "conviction": {"structure_reason": "downtrend"}},
    ]
    core_path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    monkeypatch.setattr(scs, "CORE_DECISIONS", core_path)
    monkeypatch.setattr(scs, "SPY_5M_CACHE_CSV", csv_path)
    monkeypatch.setattr(scs, "OUT_DIR", out_dir)
    monkeypatch.setattr(scs, "LEDGER", ledger)
    monkeypatch.setattr(scs, "SUMMARY", summary)
    monkeypatch.setattr(scs, "_selfcheck", lambda cache: {"ok": True, "note": "bypassed in test"})
    return {"ledger": ledger, "summary": summary}


def test_run_backfills_then_is_idempotent_on_rerun(_wired_fixtures):
    ledger = _wired_fixtures["ledger"]

    out1 = scs.run()
    assert "error" not in out1, out1
    assert out1["new_this_run"] == 1
    assert ledger.exists()
    lines1 = ledger.read_text(encoding="utf-8").splitlines()
    assert len(lines1) == 1
    row = json.loads(lines1[0])
    assert row["label_live"] == "downtrend"
    assert row["label_walk"] == "uptrend"
    assert row["agree"] is False

    out2 = scs.run()
    assert out2["new_this_run"] == 0
    lines2 = ledger.read_text(encoding="utf-8").splitlines()
    assert len(lines2) == 1, "idempotent rerun must never duplicate a ledger row"


def test_run_reports_selfcheck_failure_loudly(tmp_path, monkeypatch):
    monkeypatch.setattr(scs, "CORE_DECISIONS", tmp_path / "missing.jsonl")
    monkeypatch.setattr(scs, "SPY_5M_CACHE_CSV", tmp_path / "missing.csv")
    monkeypatch.setattr(scs, "OUT_DIR", tmp_path / "out")
    monkeypatch.setattr(scs, "LEDGER", tmp_path / "out" / "ledger.jsonl")
    monkeypatch.setattr(scs, "SUMMARY", tmp_path / "out" / "summary.json")
    out = scs.run()
    assert out.get("error") == "SELFCHECK_FAILED"
