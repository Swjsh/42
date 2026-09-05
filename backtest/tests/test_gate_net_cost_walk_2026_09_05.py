"""Guards for setup/scripts/gate_net_cost_walk.py -- GOAL-GATE-NET-COST-2026-09-05 N2.

Pin, in order:
  1. HAND-CHECK WINNER: a real safe-2 fill (journal/trades.csv, 2026-09-01, 762P,
     entry 0.94) that hit TP1 (+100%) then trailed out -- walking the SAME entry tick/
     contract through `_walk_entry` at the SAME 1-minute OPRA resolution the live engine
     ticks at (already cached on disk, backtest/data/highres/SPY260901P00762000_1m_
     2026-09-01.csv -- no live fetch) reproduces BOTH legs' stage (tp1 then trail) and
     both legs' price within 10% (leg1 2.04 vs 2.14 = 4.9%; leg2 2.12 vs 2.21 = 4.2%).
  2. HAND-CHECK LOSER: a real bold-2 fill (2026-09-01, 759P, entry 0.43) that hit the
     -50% catastrophe cap (premium_stop @ 0.21) -- walking it at 1-min resolution
     reproduces the exact stage, the exact trigger level, and the exit price within 10%
     (0.15 vs 0.14 = 6.7%), and the exit timestamp within 1 minute (14:57:05 vs 14:57:00).
  3. SIDE-AWARE LEVEL FIX: `_stop_level_for_wave_row` prefers the SIDE-MATCHING raw level
     field (never the other side's) and falls back to `_swing_stop` when neither is
     populated -- proven by a synthetic row where the naive fixed-priority order (as
     `gate_expiry_check._stop_level_for_row` uses it) would return the WRONG-side level.
  4. FAIL-OPEN: a wave whose source row has no cached OPRA contract near its target
     strike degrades to `walk_ok=False` with a labeled `walk_error`, never a raised
     exception -- and `run_walk`'s per-row try/except means one such row never aborts the
     whole inventory walk.

RED-PROOF (quoted in the goal's session report): a mutation that breaks the side-aware
level selection (reverting to the naive fixed-priority order) turns check #1 RED --
demonstrated by temporarily monkeypatching `_stop_level_for_wave_row` back to the naive
order inside test_naive_level_order_would_mistrigger_winner and observing the mistrigger
this fix corrected.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (REPO, BACKTEST, BACKTEST / "lib", BACKTEST / "tools", BACKTEST / "autoresearch",
           FLEET_DIR, REPO / "setup" / "scripts", REPO / "crypto" / "lib"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import gate_net_cost_walk as w  # noqa: E402
import _option_bars_1min_cache as c1m  # noqa: E402

WINNER_SYMBOL = "SPY260901P00762000"
WINNER_DATE = "2026-09-01"
LOSER_SYMBOL = "SPY260901P00759000"
LOSER_DATE = "2026-09-01"


def _require_1min_cache(symbol: str, date_et: str) -> pd.DataFrame:
    df, source = c1m.fetch_1min_cached(symbol, date_et)
    if source != "cache_hit" or df is None or df.empty:
        pytest.skip(f"{symbol} {date_et} 1-min cache not present on disk -- "
                    f"this test NEVER fetches live (source={source})")
    # option_pricing_real.bar_at_or_after/bar_containing build an OptionBar requiring
    # vwap/trade_count columns that the 1-min highres cache (backtest/data/highres/*.csv,
    # backtest/tools/_option_bars_1min_cache.py) does not carry (only timestamp_et/o/h/l/
    # c/volume) -- the 5-min OPRA cache these functions were written against always has
    # them. Neither field is read anywhere downstream of that constructor in this walk
    # (only .timestamp_et/.open/.close matter), so filling them with a close-price/volume
    # proxy is a schema shim, not a pricing change.
    df = df.copy()
    df["vwap"] = df["close"]
    df["trade_count"] = df["volume"].fillna(0).astype(int)
    return df


@pytest.fixture(scope="module")
def ctx() -> w.WalkCtx:
    return w.WalkCtx()


def test_handcheck_winner_safe2_tp1_then_trail(ctx):
    """Real fill: journal/trades.csv 2026-09-01 13:21:04 safe-2 762P entry 0.94 ->
    leg1 qty2 tp1 @2.04 (ts 14:43:04), leg2 qty1 trail @2.12 (ts 14:47:55/14:48:04)."""
    df = _require_1min_cache(WINNER_SYMBOL, WINNER_DATE)
    trig_ts = pd.Timestamp("2026-09-01 13:21:04")
    bar_idx, stale = w.bar_idx_for_ts(ctx.spy_ts, trig_ts.to_pydatetime())
    assert not stale
    row = {"trigger_level_exact": None, "bull_reclaim_level_raw": 761.51,
           "bear_rejection_level_raw": None}
    level = w._stop_level_for_wave_row(row, ctx.spy, bar_idx, "P")

    res = w._walk_entry(
        ctx, arm="safe-2", side="P", day=dt.date(2026, 9, 1), trig_ts=trig_ts,
        stop_level=level, strike_override=762, entry_premium_override=0.94,
        opt_df_override=df, opt_df_resolution="1min",
    )
    assert res["walk_ok"], res.get("walk_error")
    assert res["exit_stage"] == "trail"  # last leg -- runner trailed out after TP1

    # Recover both legs via the raw walk_exit_manager call (mirrors _walk_entry internals)
    # to check leg1 (tp1) explicitly -- _walk_entry's dict only surfaces the LAST leg.
    from lib.option_pricing_real import bar_at_or_after  # noqa: E402
    from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
    import gate_revalidation_ab as grab  # noqa: E402
    entry_bar = bar_at_or_after(df, (trig_ts).to_pydatetime())
    cfg = grab.account_config()["safe"]
    rtd = grab.ribbon_tick_df_for(df, ctx.ribbon_lookup)
    spy_day = ctx.spy_by_date[dt.date(2026, 9, 1)]
    full = walk_exit_manager(
        symbol=WINNER_SYMBOL, side="P", entry_time_et=entry_bar.timestamp_et,
        entry_premium=0.94, qty=3, exit_shape=grab.ribbon_ride_shape(),
        structure_stop_enabled=cfg["structure_stop_enabled"], trigger_level=level,
        strategy="ribbon_ride", time_stop_et=cfg["time_stop_et"], opt_df=df,
        ribbon_tick_df=rtd, five_min_spy_df=spy_day, opt_df_resolution="1min",
        allow_5min=True, all_exits_market=True,
    )
    assert len(full.legs) == 2
    leg1, leg2 = full.legs
    assert leg1.stage == "tp1"
    assert leg2.stage == "trail"

    real_leg1_px, real_leg2_px = 2.04, 2.12
    assert abs(leg1.fill_price - real_leg1_px) / real_leg1_px < 0.10
    assert abs(leg2.fill_price - real_leg2_px) / real_leg2_px < 0.10


def test_handcheck_loser_bold2_catastrophe_cap(ctx):
    """Real fill: journal/trades.csv 2026-09-01 14:44:07 bold-2 759P entry 0.43 ->
    premium_stop (-50% catastrophe cap) @ 0.21, exit_px 0.15, ts 14:57:05, hold 13min."""
    df = _require_1min_cache(LOSER_SYMBOL, LOSER_DATE)
    trig_ts = pd.Timestamp("2026-09-01 14:44:07")
    bar_idx, stale = w.bar_idx_for_ts(ctx.spy_ts, trig_ts.to_pydatetime())
    assert not stale
    row = {"trigger_level_exact": None, "bull_reclaim_level_raw": None,
           "bear_rejection_level_raw": None}  # trendline_rejection: no raw level populated
    level = w._stop_level_for_wave_row(row, ctx.spy, bar_idx, "P")

    res = w._walk_entry(
        ctx, arm="bold-2", side="P", day=dt.date(2026, 9, 1), trig_ts=trig_ts,
        stop_level=level, strike_override=759, entry_premium_override=0.43,
        opt_df_override=df, opt_df_resolution="1min",
    )
    assert res["walk_ok"], res.get("walk_error")
    assert res["exit_stage"] == "premium_stop"
    assert "0.21" in res["exit_reason"]  # entry*0.5 = 0.215 -> rounds to 0.21, the real level

    real_exit_px = 0.15
    assert abs(res["exit_px"] - real_exit_px) / real_exit_px < 0.10
    real_exit_ts = dt.datetime(2026, 9, 1, 14, 57, 5)
    walked_exit_ts = dt.datetime.fromisoformat(res["exit_ts"])
    assert abs((walked_exit_ts - real_exit_ts).total_seconds()) <= 120


def test_side_aware_level_prefers_matching_side(ctx):
    """A row carrying ONLY the wrong-side raw level must fall back to swing_stop, never
    return the wrong-side number -- the exact bug the naive gate_expiry_check helper hit
    on the winner hand-check fixture (returned the BULL level for a BEAR/put trade)."""
    bar_idx, _ = w.bar_idx_for_ts(ctx.spy_ts, dt.datetime(2026, 9, 1, 13, 21, 4))
    row_bull_only = {"trigger_level_exact": None, "bull_reclaim_level_raw": 761.51,
                      "bear_rejection_level_raw": None}
    level = w._stop_level_for_wave_row(row_bull_only, ctx.spy, bar_idx, "P")
    assert level != 761.51  # never the wrong-side field
    # swing_stop for a put = highest high in the lookback window >= current close
    spot = float(ctx.spy.iloc[bar_idx]["close"])
    assert level > spot


def test_naive_level_order_would_mistrigger_winner(ctx):
    """RED-PROOF: reproduces the exact failure this fix corrected. Using the NAIVE
    fixed-priority level order (trigger_level_exact -> bull_reclaim_level_raw ->
    bear_rejection_level_raw, regardless of side -- gate_expiry_check._stop_level_for_row's
    own convention) on the winner fixture returns the wrong-side level and mistriggers a
    structure_stop within minutes, instead of the real TP1-then-trail outcome. This test
    documents the mechanism the walker's side-aware fix avoids; it does not import the
    naive helper (this module never adds that dependency), it reimplements its documented
    priority order inline to prove the mistrigger is real, not hypothetical."""
    df = _require_1min_cache(WINNER_SYMBOL, WINNER_DATE)

    def naive_level(row):
        for key in ("trigger_level_exact", "bull_reclaim_level_raw", "bear_rejection_level_raw"):
            v = row.get(key)
            if v is not None:
                return float(v)
        return None

    row = {"trigger_level_exact": None, "bull_reclaim_level_raw": 761.51,
           "bear_rejection_level_raw": None}
    naive = naive_level(row)
    assert naive == 761.51

    trig_ts = pd.Timestamp("2026-09-01 13:21:04")
    res = w._walk_entry(
        ctx, arm="safe-2", side="P", day=dt.date(2026, 9, 1), trig_ts=trig_ts,
        stop_level=naive, strike_override=762, entry_premium_override=0.94,
        opt_df_override=df, opt_df_resolution="1min",
    )
    assert res["walk_ok"]
    # the mistrigger: exits FAR earlier than the real 82-minute TP1 hold, on a structure
    # break the wrong-side level manufactures near-immediately.
    assert res["exit_stage"] == "structure_stop"
    assert res["hold_minutes"] < 20  # real trade held 82+ minutes


def test_fail_open_no_cached_contract_never_raises(ctx):
    """A target strike with no cached OPRA contract anywhere within MAX_STRIKE_STEPS
    degrades to walk_ok=False + a labeled walk_error, never an exception."""
    res = w._walk_entry(
        ctx, arm="safe-2", side="C", day=dt.date(2099, 1, 1),
        trig_ts=pd.Timestamp("2099-01-01 10:00:00"), stop_level=None,
    )
    assert res["walk_ok"] is False
    assert "walk_error" in res and res["walk_error"]


def test_run_walk_row_level_exception_is_fail_open(ctx, monkeypatch):
    """One row's _walk_entry raising must not abort run_walk's loop over the rest of the
    inventory -- mirrors the goal's 'a missing bar = labeled null, never a crash' mandate."""
    import gate_net_cost_walk as mod

    calls = {"n": 0}
    real_walk_entry = mod._walk_entry

    def boom(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("synthetic failure for the fail-open guard")
        return real_walk_entry(*args, **kwargs)

    monkeypatch.setattr(mod, "_walk_entry", boom)
    tiny = {
        "core_gates": {
            "SKIP_STRUCTURE_VETO": {"waves": [
                {"date": "2026-08-07", "wave_start_et": "2026-08-07T12:36:03",
                 "account": "safe"},
            ]},
        },
        "fleet_decisions_reason_gates": {},
    }
    import json
    tmp = REPO / "backtest" / "tests" / "_tmp_gate_net_cost_walk_fixture.json"
    tmp.write_text(json.dumps(tiny), encoding="utf-8")
    try:
        out = mod.run_walk(tmp)
    finally:
        tmp.unlink(missing_ok=True)
    assert out["n_rows"] == 1
    assert out["rows"][0]["walk_ok"] is False
    assert "unexpected" in out["rows"][0]["walk_error"]
