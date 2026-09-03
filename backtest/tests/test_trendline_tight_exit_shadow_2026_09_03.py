"""Guard suite for setup/scripts/trendline_tight_exit_shadow.py -- the forward counter that
adjudicates prereg-trendline-tight-exit-shadow-2026-09-03.md (queue.md
TRENDLINE-TIGHT-EXIT-ACCRETE).

This counter's ONLY job is to honestly SHADOW-score kitchen cell A6's tightened TRENDLINE
exit (-20%->-12% stop, 15%->10% trail) against every real trendline-class fill going
forward, comparing a re-simulated shadow exit to the REAL recorded broker P&L. The guards
below pin the four mechanics that would matter if broken:

  1. THE CLASS FILTER. A fill counts as trendline-class only when its canonicalized setup is
     a ribbon_ride entry AND trigger_level is None (the verified causal-at-entry proxy for
     the backtest tier -- see the module docstring). A structure-tier fill (trigger_level
     set) or a non-ribbon setup must never be scored.
  2. THE TIGHTENED-KNOB PASS-THROUGH. The shadow exit shape must differ from the control
     shape in EXACTLY two keys (premium_stop_pct=-0.12, trail_pct=0.10) -- every other knob
     (tp1_premium_pct, tp1_qty_fraction, profit_lock_mode, etc.) must be byte-identical to
     the live control, never silently drifted.
  3. MISSING BARS ARE RECORDED, NEVER SILENTLY DROPPED. A trendline-class fill whose OPRA
     bars are not cached on disk must produce a status="SKIPPED_NO_BARS" ledger row, not a
     vanished trade and not a crashed run.
  4. IDEMPOTENT. Re-running against the same fixtures must never duplicate a ledger row, and
     the CI/summary shape must degrade honestly on thin data (n_days<2).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
# NOTE order: setup/scripts (which has its OWN unrelated "lib" subpackage) must be inserted
# FIRST so later insert(0, ...) calls for backtest/backtest/lib push it behind them --
# otherwise "import lib.xxx" resolves to setup/scripts/lib instead of backtest/lib. A plain
# `pythonw script.py` invocation never hits this (Python auto-inserts the script's own dir
# once, so the module's own dedup'd loop can't reorder it) -- this ordering only matters
# inside a pytest process where no such auto-insertion has happened yet.
for _p in (REPO / "setup" / "scripts", REPO, REPO / "backtest", REPO / "backtest" / "tools",
           REPO / "backtest" / "lib", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import trendline_tight_exit_shadow as ttes  # noqa: E402


# ---------------------------------------------------------------------------------
# 1. class filter -- causal-at-entry proxy (canonicalized setup + trigger_level is None)
# ---------------------------------------------------------------------------------
def _event(setup="BULLISH_RECLAIM_RIDE_THE_RIBBON", trigger_level=None, **kw):
    ev = {"activity_id": "a1", "arm": "safe-2", "symbol": "SPY260903C00700000",
          "opt_side": "C", "setup": setup, "qty": 6.0, "price": 1.00,
          "date_et": "2026-09-03", "ts_et": "2026-09-03T10:00:00", "pnl": 100.0,
          "exit_qty": 6.0, "is_option": True, "attribution": "engine", "side": "buy",
          "trigger_level": trigger_level}
    ev.update(kw)
    return ev


def test_is_trendline_class_true_for_ribbon_setup_with_no_trigger_level():
    assert ttes.is_trendline_class(_event(trigger_level=None)) is True


def test_is_trendline_class_false_when_trigger_level_is_set():
    """A trigger_level means a chart level fired -- SUPER/ELITE/LEVEL tier, not TRENDLINE."""
    assert ttes.is_trendline_class(_event(trigger_level=725.50)) is False


def test_is_trendline_class_false_for_non_ribbon_setup():
    assert ttes.is_trendline_class(
        _event(setup="VWAP_CONTINUATION", trigger_level=None)) is False


def test_is_trendline_class_normalizes_legacy_alias_via_setup_taxonomy():
    """BULLISH_RECLAIM (pre-rename legacy name) must canonicalize to
    BULLISH_RECLAIM_RIDE_THE_RIBBON and still be caught -- this is exactly why the module
    routes through setup_taxonomy.canonical_setup instead of a bare string match."""
    assert ttes.is_trendline_class(_event(setup="BULLISH_RECLAIM", trigger_level=None)) is True


def test_is_trendline_class_case_insensitive():
    assert ttes.is_trendline_class(
        _event(setup="bearish_rejection_ride_the_ribbon", trigger_level=None)) is True


# ---------------------------------------------------------------------------------
# 2. _shapes -- tightened-knob pass-through pinned: ONLY 2 keys differ
# ---------------------------------------------------------------------------------
def test_shapes_tightened_values_are_cell_a6():
    control, tightened = ttes._shapes()
    assert tightened["premium_stop_pct"] == pytest.approx(-0.12)
    assert tightened["trail_pct"] == pytest.approx(0.10)


def test_shapes_only_two_keys_differ_from_control():
    control, tightened = ttes._shapes()
    assert set(control.keys()) == set(tightened.keys()), "no key added/removed"
    diffs = {k for k in control if control[k] != tightened[k]}
    assert diffs == {"premium_stop_pct", "trail_pct"}, (
        f"tightened shape drifted on unexpected keys: {diffs - {'premium_stop_pct', 'trail_pct'}}")


def test_shapes_control_is_read_from_live_ribbon_ride_never_hardcoded():
    import strategies as fleet_strategies
    control, _ = ttes._shapes()
    live = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    assert control == live


# ---------------------------------------------------------------------------------
# 3. _sign helper
# ---------------------------------------------------------------------------------
def test_sign_helper():
    assert ttes._sign(5.0) == 1
    assert ttes._sign(-5.0) == -1
    assert ttes._sign(0.0) == 0
    assert ttes._sign(1e-12) == 0   # dust must not register as a real sign


# ---------------------------------------------------------------------------------
# 4. _summarize / _bootstrap_day_clustered_mean / _top3_concentration_share
# ---------------------------------------------------------------------------------
def test_summarize_empty_is_armed_awaiting_fills():
    s = ttes._summarize([])
    assert s["n"] == 0
    assert s["n_scored"] == 0
    assert s["status"] == "ARMED_AWAITING_FILLS"
    assert s["session_clustered_ci"] is None
    assert "dollar_caveat" in s and "SIGN-ONLY" in s["dollar_caveat"]


def test_summarize_counts_skipped_separately_from_scored():
    rows = [
        {"date_et": "2026-09-03", "delta_pnl": 10.0, "sign_agree": True, "status": "SCORED"},
        {"date_et": "2026-09-03", "status": "SKIPPED_NO_BARS"},
    ]
    s = ttes._summarize(rows)
    assert s["n"] == 2
    assert s["n_scored"] == 1
    assert s["n_skipped"] == 1
    assert s["n_skipped_by_reason"] == {"SKIPPED_NO_BARS": 1}


def test_bootstrap_ci_none_below_two_days():
    rows = [{"date_et": "2026-09-03", "delta_pnl": 10.0}]
    assert ttes._bootstrap_day_clustered_mean(rows) is None


def test_bootstrap_ci_shape_with_two_or_more_days():
    rows = ([{"date_et": "2026-09-03", "delta_pnl": 50.0} for _ in range(5)]
            + [{"date_et": "2026-09-04", "delta_pnl": 40.0} for _ in range(5)])
    ci = ttes._bootstrap_day_clustered_mean(rows, n_boot=200)
    assert ci is not None
    assert set(ci) == {"n_boot", "n_days_clustered", "ci_lower_2.5", "ci_upper_97.5"}
    assert ci["n_days_clustered"] == 2
    assert ci["ci_lower_2.5"] <= ci["ci_upper_97.5"]


def test_top3_concentration_share_all_zero_when_no_delta():
    assert ttes._top3_concentration_share([{"delta_pnl": 0.0}, {"delta_pnl": 0.0}]) == 0.0


def test_summarize_bar_not_met_below_thresholds():
    rows = [{"date_et": "2026-09-03", "delta_pnl": 10.0, "sign_agree": True, "status": "SCORED"}]
    s = ttes._summarize(rows)
    assert s["bar_met"] is False
    assert s["status"] == "ACCRUING"
    assert s["days_to_bar"] == ttes.BAR_TRADING_DAYS - 1
    assert s["trendline_to_bar"] == ttes.BAR_N_TRENDLINE - 1
    assert s["sign_agreement"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------------
# 5. run() -- end-to-end, idempotent, skip-no-bars (fully monkeypatched I/O -- no real
#    OPRA/SIP disk access, no network)
# ---------------------------------------------------------------------------------
def _synthetic_5m_day(date_et: str) -> list[dict]:
    """One synthetic RTH day of 5-min SPY bars, shaped exactly like entry_quality_ledger.
    load_bars' own per-bar dict convention ({t,o,h,l,c,v})."""
    bars = []
    t = dt.datetime.fromisoformat(f"{date_et}T09:30:00")
    end = dt.datetime.fromisoformat(f"{date_et}T16:00:00")
    px = 500.0
    while t < end:
        bars.append({"t": t.isoformat(), "o": px, "h": px + 0.1, "l": px - 0.1,
                     "c": px, "v": 1000})
        t += dt.timedelta(minutes=5)
    return bars


@pytest.fixture
def _wired_fixtures(tmp_path, monkeypatch):
    eql_path = tmp_path / "entry-quality-ledger.json"
    out_dir = tmp_path / "out"
    ledger = out_dir / "trendline-tight-exit-shadow-ledger.jsonl"
    summary = out_dir / "trendline-tight-exit-shadow-summary.json"

    events = [_event(activity_id="buy1", trigger_level=None)]
    eql_path.write_text(json.dumps({"events": events}), encoding="utf-8")

    monkeypatch.setattr(ttes, "ENTRY_QUALITY_LEDGER", eql_path)
    monkeypatch.setattr(ttes, "OUT_DIR", out_dir)
    monkeypatch.setattr(ttes, "LEDGER", ledger)
    monkeypatch.setattr(ttes, "SUMMARY", summary)

    # Synthetic SPY 5m bars for the warmup window -- avoids real disk/network I/O.
    import entry_quality_ledger as eql
    day = events[0]["date_et"]
    monkeypatch.setattr(eql, "load_bars", lambda tf, dates: {day: _synthetic_5m_day(day)})

    # No OPRA option bars cached -- forces the SKIPPED_NO_BARS path deterministically,
    # without needing a real cached contract file.
    # NOTE: import engine_fullhist_replay BEFORE lib.option_pricing_real -- mirrors
    # run()'s own import order exactly. entry_quality_ledger's own import (above) pushes
    # REPO/crypto onto sys.path[0] for its `from crypto.lib.bar import Bar` usage
    # (crypto/lib is ALSO a regular package with __init__.py); engine_fullhist_replay's
    # own sys.path setup re-asserts REPO/backtest at position 0 ahead of it, which is what
    # makes 'lib.xxx' resolve to backtest/lib and not crypto/lib in run() itself. Skipping
    # this import here would make the fixture non-representative of the real call order.
    import engine_fullhist_replay  # noqa: F401
    import lib.option_pricing_real as opr
    monkeypatch.setattr(opr, "load_contract_bars", lambda symbol, **kw: None)

    return {"ledger": ledger, "summary": summary}


def test_run_records_skipped_no_bars_for_a_trendline_fill_with_no_cached_opra(_wired_fixtures):
    out = ttes.run()
    assert "error" not in out, out
    assert out["new_this_run"] == 1
    rows = ttes._read_ledger()
    assert len(rows) == 1
    assert rows[0]["activity_id"] == "buy1"
    assert rows[0]["status"] == "SKIPPED_NO_BARS"
    assert rows[0]["shadow_exit"] is None
    assert rows[0]["delta_pnl"] is None
    assert rows[0]["recorded_exit"]["pnl"] == pytest.approx(100.0)


def test_run_is_idempotent_on_a_second_fire(_wired_fixtures):
    ttes.run()
    out2 = ttes.run()
    assert out2["new_this_run"] == 0
    rows = ttes._read_ledger()
    assert len(rows) == 1, "re-running must never duplicate a ledger row"


def test_run_summary_has_required_shape(_wired_fixtures):
    out = ttes.run()
    for key in ("n", "n_scored", "n_skipped", "sum_delta", "mean_delta",
                "session_clustered_ci", "top3_share", "days_accrued", "dollar_caveat",
                "tightened_knobs"):
        assert key in out, key
    assert out["n"] == 1
    assert out["n_skipped"] == 1
    assert out["n_scored"] == 0


def test_run_never_scores_a_non_trendline_fill(tmp_path, monkeypatch):
    """A structure-tier fill (trigger_level set) must never even enter the ledger -- the
    class filter runs before any bar lookup or write."""
    eql_path = tmp_path / "entry-quality-ledger.json"
    out_dir = tmp_path / "out"
    events = [_event(activity_id="buyLevel", trigger_level=725.50)]
    eql_path.write_text(json.dumps({"events": events}), encoding="utf-8")

    monkeypatch.setattr(ttes, "ENTRY_QUALITY_LEDGER", eql_path)
    monkeypatch.setattr(ttes, "OUT_DIR", out_dir)
    monkeypatch.setattr(ttes, "LEDGER", out_dir / "ledger.jsonl")
    monkeypatch.setattr(ttes, "SUMMARY", out_dir / "summary.json")

    out = ttes.run()
    assert "error" not in out, out
    assert out["new_this_run"] == 0
    assert out["n"] == 0
