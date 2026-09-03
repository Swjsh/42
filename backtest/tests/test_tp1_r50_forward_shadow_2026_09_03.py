"""Guard suite for setup/scripts/tp1_r50_forward_shadow.py -- the forward counter that
adjudicates prereg-tp1-r50-forward-shadow-2026-09-03.md (queue.md TP1-R50-FORWARD-SHADOW).

This counter's ONLY job is to honestly measure what an f=0.5 TP1 sell would have done
against the LIVE f=0.667 fill, using ONLY the trade's own recorded broker legs. The guards
below pin the four mechanics that would matter if broken:

  1. THE ENGINE'S OWN ROUNDING. qty_moved must be int(qty*0.667) - int(qty*0.5), matching
     exit_manager.ExitState.from_entry's `int(qty * frac)` split exactly -- not a re-derived
     rounding rule that could silently disagree with what actually shipped.
  2. NEVER REACHED TP1 IS A REAL THIRD STATE. A single-leg close contributes exactly $0 and
     is counted separately from a genuine no-op-by-rounding trade that DID reach TP1.
  3. THE LIVE FRACTION IS CONFIRMED, NOT ASSUMED. An arm whose resolved fraction drifts off
     0.667 (a params_patch.exit_patch override) must fall out of scope, not be silently
     scored as if it were 0.667.
  4. IDEMPOTENT + FORWARD-ONLY. Re-running against the same fixtures must never duplicate a
     ledger row, and the CI/summary shape must degrade honestly on thin data (n_days<2).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "automation" / "state" / "fleet", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import tp1_r50_forward_shadow as trfs  # noqa: E402


# ---------------------------------------------------------------------------------
# 1. score_trade -- the delta math, on hand-built leg fixtures
# ---------------------------------------------------------------------------------
def _event(activity_id="buy1", qty=6.0, price=1.00, arm="test-arm",
           setup="BULLISH_RECLAIM_RIDE_THE_RIBBON", date_et="2026-09-03",
           ts_et="2026-09-03T10:00:00", multiplier=100, pnl=200.0, exit_qty=None):
    return {"activity_id": activity_id, "order_id": "o1", "arm": arm,
            "symbol": "SPY260903C00700000", "opt_side": "C", "setup": setup,
            "qty": qty, "price": price, "multiplier": multiplier, "date_et": date_et,
            "ts_et": ts_et, "pnl": pnl, "exit_qty": exit_qty if exit_qty is not None else qty}


def _legs_rec(legs, remaining=0.0, total_qty=6.0):
    return {"legs": legs, "remaining": remaining, "total_qty": total_qty}


def test_reached_tp1_delta_matches_hand_computation():
    """qty=6: tp1_qty_live=int(6*.667)=4, tp1_qty_cf=int(6*.5)=3, qty_moved=1.
    1 contract moves from the $2.00 TP1 fill to the $3.00 runner exit -> +$100.00."""
    ev = _event(qty=6.0, price=1.00)
    legs = _legs_rec([
        {"price": 2.00, "qty": 4.0, "ts_utc": "2026-09-03T14:30:00Z", "ts_et": "10:30"},
        {"price": 3.00, "qty": 2.0, "ts_utc": "2026-09-03T15:00:00Z", "ts_et": "11:00"},
    ], remaining=0.0, total_qty=6.0)
    row = trfs.score_trade(ev, legs, 0.667, "test-source")
    assert row["tp1_reached"] is True
    assert row["tp1_qty_live_rounded"] == 4
    assert row["tp1_qty_cf_rounded"] == 3
    assert row["qty_moved"] == 1
    assert row["no_op_rounding"] is False
    assert row["delta_pnl"] == pytest.approx(100.0)
    assert row["tp1_price"] == 2.00
    assert row["runner_avg_price"] == pytest.approx(3.00)
    assert row["tp1_qty_observed_matches_rounded"] is True


def test_never_reached_tp1_contributes_zero_and_is_flagged():
    """A single sell leg (stop/time-stop closed the whole position at once) is NOT a
    rounding no-op -- it is a genuine 'TP1 never fired' trade, counted separately."""
    ev = _event(qty=6.0, price=1.00)
    legs = _legs_rec([
        {"price": 0.60, "qty": 6.0, "ts_utc": "2026-09-03T14:10:00Z", "ts_et": "10:10"},
    ], remaining=0.0, total_qty=6.0)
    row = trfs.score_trade(ev, legs, 0.667, "test-source")
    assert row["tp1_reached"] is False
    assert row["delta_pnl"] == 0.0
    assert row["no_op_rounding"] is False
    assert row["tp1_price"] is None


def test_rounding_no_op_is_distinguished_from_never_reached():
    """qty=4: tp1_qty_live=int(4*.667)=2, tp1_qty_cf=int(4*.5)=2 -> qty_moved=0. TWO legs
    exist (TP1 WAS reached) but the fractions floor to the identical whole-contract count,
    so the row must be tp1_reached=True, no_op_rounding=True, delta 0.0 -- distinct from the
    single-leg 'never reached' case above even though both post delta=0."""
    ev = _event(qty=4.0, price=1.00)
    legs = _legs_rec([
        {"price": 2.50, "qty": 2.0, "ts_utc": "2026-09-03T14:20:00Z", "ts_et": "10:20"},
        {"price": 3.50, "qty": 2.0, "ts_utc": "2026-09-03T14:50:00Z", "ts_et": "10:50"},
    ], remaining=0.0, total_qty=4.0)
    row = trfs.score_trade(ev, legs, 0.667, "test-source")
    assert row["tp1_reached"] is True
    assert row["qty_moved"] == 0
    assert row["no_op_rounding"] is True
    assert row["delta_pnl"] == 0.0


def test_qty_moved_uses_the_engines_own_int_floor_rounding():
    """Cross-check against exit_manager.ExitState.from_entry's exact formula for a range of
    quantities -- qty_moved must never disagree with int(qty*live)-int(qty*cf)."""
    for qty in range(3, 21):
        expected = int(qty * 0.667) - int(qty * 0.5)
        ev = _event(qty=float(qty), price=1.00)
        # legs irrelevant to qty_moved -- use a trivial 2-leg fully-closed fixture
        legs = _legs_rec([
            {"price": 2.0, "qty": qty - 1.0, "ts_utc": "t1", "ts_et": "t1"},
            {"price": 3.0, "qty": 1.0, "ts_utc": "t2", "ts_et": "t2"},
        ], remaining=0.0, total_qty=float(qty))
        row = trfs.score_trade(ev, legs, 0.667, "src")
        assert row["qty_moved"] == expected, f"qty={qty}"


def test_not_fully_closed_returns_none_never_fabricates():
    ev = _event(qty=6.0)
    legs = _legs_rec([{"price": 2.0, "qty": 3.0, "ts_utc": "t1", "ts_et": "t1"}],
                      remaining=3.0, total_qty=6.0)   # still 3 open
    assert trfs.score_trade(ev, legs, 0.667, "src") is None


def test_missing_legs_record_returns_none():
    assert trfs.score_trade(_event(), None, 0.667, "src") is None


# ---------------------------------------------------------------------------------
# 2. legs_by_activity_id -- FIFO grouping over raw fills
# ---------------------------------------------------------------------------------
def test_legs_by_activity_id_orders_legs_chronologically_and_splits_by_buy():
    fills = [
        {"activity_id": "b1", "arm": "a", "symbol": "S", "date_et": "2026-09-03",
         "side": "buy", "qty": 6.0, "price": 1.0, "ts_utc": "2026-09-03T14:00:00Z"},
        {"activity_id": "s2", "arm": "a", "symbol": "S", "date_et": "2026-09-03",
         "side": "sell", "qty": 2.0, "price": 3.0, "ts_utc": "2026-09-03T15:00:00Z"},
        {"activity_id": "s1", "arm": "a", "symbol": "S", "date_et": "2026-09-03",
         "side": "sell", "qty": 4.0, "price": 2.0, "ts_utc": "2026-09-03T14:30:00Z"},
    ]
    idx = trfs.legs_by_activity_id(fills)
    rec = idx["b1"]
    assert rec["remaining"] == pytest.approx(0.0)
    assert [l["price"] for l in rec["legs"]] == [2.0, 3.0]   # TP1 (earlier ts) first
    assert [l["qty"] for l in rec["legs"]] == [4.0, 2.0]


def test_legs_by_activity_id_two_buys_fifo_matched_separately():
    fills = [
        {"activity_id": "b1", "arm": "a", "symbol": "S", "date_et": "2026-09-03",
         "side": "buy", "qty": 3.0, "price": 1.0, "ts_utc": "2026-09-03T14:00:00Z"},
        {"activity_id": "b2", "arm": "a", "symbol": "S", "date_et": "2026-09-03",
         "side": "buy", "qty": 3.0, "price": 1.1, "ts_utc": "2026-09-03T14:05:00Z"},
        {"activity_id": "s1", "arm": "a", "symbol": "S", "date_et": "2026-09-03",
         "side": "sell", "qty": 3.0, "price": 0.8, "ts_utc": "2026-09-03T14:10:00Z"},
        {"activity_id": "s2", "arm": "a", "symbol": "S", "date_et": "2026-09-03",
         "side": "sell", "qty": 3.0, "price": 0.9, "ts_utc": "2026-09-03T14:20:00Z"},
    ]
    idx = trfs.legs_by_activity_id(fills)
    assert idx["b1"]["legs"][0]["price"] == 0.8      # closed by the FIRST sell (FIFO)
    assert idx["b2"]["legs"][0]["price"] == 0.9


# ---------------------------------------------------------------------------------
# 3. _live_fraction_for_arm -- confirmed, not hardcoded
# ---------------------------------------------------------------------------------
def test_live_fraction_default_is_ribbon_ride_shape():
    frac, src = trfs._live_fraction_for_arm("safe-2", 0.667, {})
    assert frac == 0.667
    assert "strategies.by_name" in src


def test_live_fraction_honors_an_explicit_exit_patch_override():
    frac, src = trfs._live_fraction_for_arm(
        "risky-1", 0.667, {"risky-1": {"tp1_qty_fraction": 0.5}})
    assert frac == 0.5
    assert "OVERRIDES" in src


# ---------------------------------------------------------------------------------
# 4. _summarize / _bootstrap_day_clustered_mean -- CI shape
# ---------------------------------------------------------------------------------
def test_summarize_empty_is_armed_awaiting_fills():
    s = trfs._summarize([])
    assert s["n_trades"] == 0
    assert s["status"] == "ARMED_AWAITING_FILLS"
    assert s["session_clustered_ci"] is None


def test_bootstrap_ci_none_below_two_days():
    rows = [{"date_et": "2026-09-03", "delta_pnl": 10.0}]
    assert trfs._bootstrap_day_clustered_mean(rows) is None


def test_bootstrap_ci_shape_with_two_or_more_days():
    rows = ([{"date_et": "2026-09-03", "delta_pnl": 50.0} for _ in range(5)]
            + [{"date_et": "2026-09-04", "delta_pnl": 40.0} for _ in range(5)])
    ci = trfs._bootstrap_day_clustered_mean(rows, n_boot=200)
    assert ci is not None
    assert set(ci) == {"n_boot", "n_days_clustered", "ci_lower_2.5", "ci_upper_97.5"}
    assert ci["n_days_clustered"] == 2
    assert ci["ci_lower_2.5"] <= ci["ci_upper_97.5"]


def test_top3_concentration_share_all_zero_when_no_delta():
    assert trfs._top3_concentration_share([{"delta_pnl": 0.0}, {"delta_pnl": 0.0}]) == 0.0


def test_summarize_bar_not_met_below_thresholds():
    rows = [{"date_et": "2026-09-03", "delta_pnl": 10.0, "tp1_reached": True,
             "no_op_rounding": False}]
    s = trfs._summarize(rows)
    assert s["bar_met"] is False
    assert s["status"] == "ACCRUING"
    assert s["days_to_bar"] == trfs.BAR_TRADING_DAYS - 1
    assert s["tp1_reached_to_bar"] == trfs.BAR_N_TP1 - 1


# ---------------------------------------------------------------------------------
# 5. run() -- end-to-end idempotent append against fixture artifacts
# ---------------------------------------------------------------------------------
@pytest.fixture
def _wired_fixtures(tmp_path, monkeypatch):
    fills_ledger = tmp_path / "fills-ledger.jsonl"
    accounts_path = tmp_path / "accounts.json"
    eql_path = tmp_path / "entry-quality-ledger.json"
    out_dir = tmp_path / "out"
    ledger = out_dir / "tp1-r50-forward-shadow-ledger.jsonl"
    summary = out_dir / "tp1-r50-forward-shadow-summary.json"

    fills = [
        # in-scope trade: reaches TP1, qty=6 -> qty_moved=1
        {"activity_id": "buy1", "order_id": "o1", "arm": "test-arm", "symbol": "SPY260903C00700000",
         "side": "buy", "qty": 6.0, "price": 1.00, "multiplier": 100, "is_option": True,
         "is_crypto": False, "attribution": "engine", "ts_utc": "2026-09-03T14:00:00.000Z",
         "ts_et": "2026-09-03T10:00:00", "date_et": "2026-09-03"},
        {"activity_id": "sell1a", "order_id": "o1s1", "arm": "test-arm", "symbol": "SPY260903C00700000",
         "side": "sell", "qty": 4.0, "price": 2.00, "multiplier": 100, "is_option": True,
         "is_crypto": False, "attribution": "engine", "ts_utc": "2026-09-03T14:30:00.000Z",
         "ts_et": "2026-09-03T10:30:00", "date_et": "2026-09-03"},
        {"activity_id": "sell1b", "order_id": "o1s2", "arm": "test-arm", "symbol": "SPY260903C00700000",
         "side": "sell", "qty": 2.0, "price": 3.00, "multiplier": 100, "is_option": True,
         "is_crypto": False, "attribution": "engine", "ts_utc": "2026-09-03T15:00:00.000Z",
         "ts_et": "2026-09-03T11:00:00", "date_et": "2026-09-03"},
    ]
    fills_ledger.write_text("".join(json.dumps(f) + "\n" for f in fills), encoding="utf-8")

    accounts = {"arms": [{"id": "test-arm", "params_patch": {"exit_patch": {}}}]}
    accounts_path.write_text(json.dumps(accounts), encoding="utf-8")

    events = [{"activity_id": "buy1", "order_id": "o1", "arm": "test-arm",
               "symbol": "SPY260903C00700000", "opt_side": "C",
               "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON", "qty": 6.0, "price": 1.00,
               "date_et": "2026-09-03", "ts_et": "2026-09-03T10:00:00", "pnl": 200.0,
               "exit_qty": 6.0}]
    eql_path.write_text(json.dumps({"events": events}), encoding="utf-8")

    monkeypatch.setattr(trfs, "FILLS_LEDGER", fills_ledger)
    monkeypatch.setattr(trfs, "ACCOUNTS_PATH", accounts_path)
    monkeypatch.setattr(trfs, "ENTRY_QUALITY_LEDGER", eql_path)
    monkeypatch.setattr(trfs, "OUT_DIR", out_dir)
    monkeypatch.setattr(trfs, "LEDGER", ledger)
    monkeypatch.setattr(trfs, "SUMMARY", summary)
    return {"ledger": ledger, "summary": summary}


def test_run_writes_one_row_for_the_qualifying_trade(_wired_fixtures):
    out = trfs.run()
    assert "error" not in out, out
    assert out["new_this_run"] == 1
    rows = trfs._read_ledger()
    assert len(rows) == 1
    assert rows[0]["activity_id"] == "buy1"
    assert rows[0]["delta_pnl"] == pytest.approx(100.0)
    assert rows[0]["live_tp1_fraction"] == 0.667


def test_run_is_idempotent_on_a_second_fire(_wired_fixtures):
    trfs.run()
    out2 = trfs.run()
    assert out2["new_this_run"] == 0
    rows = trfs._read_ledger()
    assert len(rows) == 1, "re-running must never duplicate a ledger row"


def test_run_summary_has_expected_shape(_wired_fixtures):
    out = trfs.run()
    for key in ("n_trades", "n_tp1_reached", "n_no_op_rounding", "sum_delta", "mean_delta",
                "session_clustered_ci", "top3_concentration_share", "days_accrued"):
        assert key in out, key
    assert out["n_trades"] == 1
    assert out["n_tp1_reached"] == 1
    assert out["n_no_op_rounding"] == 0
    assert out["days_accrued"] == 1


def test_run_skips_an_out_of_scope_arm(tmp_path, monkeypatch):
    fills_ledger = tmp_path / "fills-ledger.jsonl"
    accounts_path = tmp_path / "accounts.json"
    eql_path = tmp_path / "entry-quality-ledger.json"
    out_dir = tmp_path / "out"

    fills_ledger.write_text("", encoding="utf-8")
    accounts = {"arms": [{"id": "override-arm",
                           "params_patch": {"exit_patch": {"tp1_qty_fraction": 0.5}}}]}
    accounts_path.write_text(json.dumps(accounts), encoding="utf-8")
    events = [{"activity_id": "buyX", "order_id": "oX", "arm": "override-arm",
               "symbol": "SPY260903C00700000", "opt_side": "C",
               "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON", "qty": 6.0, "price": 1.00,
               "date_et": "2026-09-03", "ts_et": "2026-09-03T10:00:00", "pnl": 50.0,
               "exit_qty": 6.0}]
    eql_path.write_text(json.dumps({"events": events}), encoding="utf-8")

    monkeypatch.setattr(trfs, "FILLS_LEDGER", fills_ledger)
    monkeypatch.setattr(trfs, "ACCOUNTS_PATH", accounts_path)
    monkeypatch.setattr(trfs, "ENTRY_QUALITY_LEDGER", eql_path)
    monkeypatch.setattr(trfs, "OUT_DIR", out_dir)
    monkeypatch.setattr(trfs, "LEDGER", out_dir / "ledger.jsonl")
    monkeypatch.setattr(trfs, "SUMMARY", out_dir / "summary.json")

    out = trfs.run()
    assert out["new_this_run"] == 0
    assert out["skipped_this_run"], "the override arm must be recorded as skipped, not silently dropped"
    assert "!= 0.667" in out["skipped_this_run"][0]["reason"]
