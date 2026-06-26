"""Pytest suite for the futures module.

Tests cover: instruments, simulate_futures, risk.py, strategy_config v2b+v3,
data loading, and a smoke test of the end-to-end signal pipeline.
Run: pytest backtest/futures/test_futures.py -v
"""
from __future__ import annotations
import json
import pytest
import datetime as dt
from pathlib import Path
import pandas as pd
import numpy as np

REPO = Path(__file__).resolve().parent.parent.parent
import sys
sys.path.insert(0, str(REPO / "backtest"))

from futures.instruments import MES, MNQ, NQ, ES, get, BY_SYMBOL
from futures.futures_sim import simulate_futures
from lib.watchers.orb_watcher import compute_opening_range, set_futures_range_scale
from futures.risk import PropAccount, TOPSTEP_50K, APEX_50K, size_contracts
from futures.strategy_config        import should_take as should_take_v2b
from futures.strategy_config_v3     import should_take as should_take_v3
from futures.strategy_config_v3_mes import should_take_v3_mes
from futures.data import load_continuous_csv, rth_only, resample_5m


# ─── Instrument specs ──────────────────────────────────────────────────────────

class TestInstruments:
    def test_mes_point_value(self):
        assert MES.point_value == 5.0

    def test_mnq_point_value(self):
        assert MNQ.point_value == 2.0

    def test_mes_tick_value(self):
        assert MES.tick_value == pytest.approx(1.25)

    def test_mnq_tick_value(self):
        assert MNQ.tick_value == pytest.approx(0.50)

    def test_spy_to_index_mes(self):
        assert MES.spy_to_index == 10.0

    def test_spy_to_index_mnq_is_none(self):
        assert MNQ.spy_to_index is None

    def test_get_by_symbol(self):
        assert get("MES") is MES
        assert get("mnq") is MNQ

    def test_round_turn_micros(self):
        # Micros should be cheaper than minis
        assert MES.round_turn_usd < ES.round_turn_usd
        assert MNQ.round_turn_usd < NQ.round_turn_usd


# ─── Futures simulator ─────────────────────────────────────────────────────────

def make_bars(prices: list[float]) -> pd.DataFrame:
    """Create a minimal OHLCV DataFrame for testing."""
    rows = []
    for i, p in enumerate(prices):
        rows.append({"open": p, "high": p + 2, "low": p - 2,
                     "close": p, "volume": 100,
                     "timestamp_et": dt.datetime(2026, 1, 2, 10, i)})
    return pd.DataFrame(rows)


class TestFuturesSim:
    def test_long_runner_hit(self):
        # Long trade, price rallies to runner target
        bars = make_bars([21000, 21010, 21050, 21100, 21200])
        r = simulate_futures("long", entry=21000, stop=20970, tp1=21050, runner=21150,
                              future_bars=bars, instrument=MNQ, qty=3, px_to_points=1.0)
        assert r["outcome"] in ("runner", "tp1_then_be", "tp1_then_timeexit")
        assert r["net"] > 0, "Runner hit should be profitable"

    def test_long_stopped_out(self):
        # Long trade, price drops to stop
        bars = make_bars([20980, 20970, 20960])
        r = simulate_futures("long", entry=21000, stop=20970, tp1=21050, runner=21150,
                              future_bars=bars, instrument=MNQ, qty=3, px_to_points=1.0)
        assert r["outcome"] == "stopped"
        assert r["net"] < 0

    def test_short_runner_hit(self):
        bars = make_bars([21000, 20990, 20950, 20900, 20800])
        r = simulate_futures("short", entry=21000, stop=21030, tp1=20950, runner=20850,
                              future_bars=bars, instrument=MNQ, qty=3, px_to_points=1.0)
        assert r["outcome"] in ("runner", "tp1_then_be", "tp1_then_timeexit")
        assert r["net"] > 0

    def test_pnl_linearity_mnq(self):
        # 10pt win on MNQ with 1 contract = $20 - costs
        bars = make_bars([21010, 21020, 21030])
        r = simulate_futures("long", entry=21000, stop=20990, tp1=21010, runner=None,
                              future_bars=bars, instrument=MNQ, qty=1, px_to_points=1.0)
        # TP1 fills at 21010, gross = 10 pts * $2 = $20, minus slippage + commission
        assert r["gross"] == pytest.approx(10.0 * 2.0, abs=1.0)

    def test_pnl_linearity_mes(self):
        # 10pt win on MES with 1 contract = $50 - costs
        bars = make_bars([5510, 5520, 5530])
        r = simulate_futures("long", entry=5500, stop=5490, tp1=5510, runner=None,
                              future_bars=bars, instrument=MES, qty=1, px_to_points=1.0)
        assert r["gross"] == pytest.approx(10.0 * 5.0, abs=1.0)

    def test_commission_deducted(self):
        # Net should be less than gross
        bars = make_bars([21050, 21100])
        r = simulate_futures("long", entry=21000, stop=20970, tp1=21050, runner=21100,
                              future_bars=bars, instrument=MNQ, qty=3, px_to_points=1.0)
        assert r["net"] < r["gross"]

    def test_proxy_mode_spy_bars(self):
        # Proxy mode: SPY price 530 * 10 ~= 5300 index pts
        bars = make_bars([531, 532, 535])  # SPY prices
        r = simulate_futures("long", entry=530.0, stop=528.0, tp1=533.0, runner=537.0,
                              future_bars=bars, instrument=MES, qty=3, px_to_points=10.0)
        # 3pt SPY move * 10 * $5/pt * 3 contracts - costs
        assert r["net"] != 0

    def test_no_future_bars_time_exit(self):
        bars = make_bars([])
        r = simulate_futures("long", entry=21000, stop=20970, tp1=21050, runner=21150,
                              future_bars=bars, instrument=MNQ, qty=3, px_to_points=1.0)
        assert r["outcome"] == "time_exit"


# ─── Risk module ───────────────────────────────────────────────────────────────

class TestRisk:
    def test_topstep_floor_initial(self):
        # At start, floor = starting_balance - max_drawdown
        acct = PropAccount("Test", 5000, 500, "eod_trailing", 1000, max_contracts=5)
        assert acct.floor() == pytest.approx(4500.0)

    def test_topstep_floor_locks_at_start(self):
        # Once peak > start + dd, floor locks at start
        acct = PropAccount("Test", 5000, 500, "eod_trailing", 1000, max_contracts=5)
        acct.roll_eod(5600)  # gained $600, new peak = 5600
        acct.update(5600)
        floor = acct.floor()
        # floor = min(5600 - 500, 5000) = min(5100, 5000) = 5000
        assert floor == pytest.approx(5000.0)

    def test_apex_intraday_trailing(self):
        # Apex: floor trails peak intraday
        acct = PropAccount("Apex", 5000, 500, "intraday_trailing", 1000, max_contracts=5)
        acct.update(5400)  # unrealized high
        # floor = 5400 - 500 = 4900 (above starting floor of 4500)
        assert acct.floor() == pytest.approx(4900.0)

    def test_would_violate_stops_bad_trade(self):
        acct = TOPSTEP_50K
        # If equity would drop below floor, violates
        floor = acct.floor()
        assert acct.would_violate(floor - 1) is True

    def test_would_violate_ok_trade(self):
        acct = TOPSTEP_50K
        assert acct.would_violate(acct.starting_balance * 0.99) is False

    def test_size_contracts_basic(self):
        # 10pt stop on MNQ ($2/pt) = $20 risk per contract
        # $200 risk budget -> 10 contracts (capped by hard_cap)
        n = size_contracts(50000, 200, 10.0, MNQ, hard_cap=5)
        assert n == 5  # capped at 5

    def test_size_contracts_min_one(self):
        n = size_contracts(100, 1.0, 100.0, MNQ, hard_cap=10)
        assert n >= 1


# ─── Strategy configs ──────────────────────────────────────────────────────────

class TestStrategyConfig:
    def test_v2b_orb_vix16_pass(self):
        assert should_take_v2b("orb_watcher", "long", "medium", 17.0) is True

    def test_v2b_orb_vix_too_low(self):
        assert should_take_v2b("orb_watcher", "long", "medium", 15.0) is False

    def test_v2b_erl_irl_short_band(self):
        # erl_irl short high: VIX 16-22 only
        assert should_take_v2b("erl_irl_watcher", "short", "high", 18.0) is True
        assert should_take_v2b("erl_irl_watcher", "short", "high", 23.0) is False

    def test_v3_erl_irl_long_high_included(self):
        # v3 includes erl_irl long (the #1 MNQ edge)
        assert should_take_v3("erl_irl_watcher", "long", "high", 17.0) is True

    def test_v3_shotgun_short_high_included(self):
        # v3 includes shotgun short/high (new finding from real MNQ data)
        assert should_take_v3("shotgun_scalper_watcher", "short", "high", 17.0) is True

    def test_v3_morning_rejection_removed(self):
        # bearish_rejection_morning was negative on real MNQ — removed from v3
        assert should_take_v3("bearish_rejection_morning_watcher", "short", "medium", 17.0) is False

    def test_v2b_morning_rejection_included(self):
        assert should_take_v2b("bearish_rejection_morning_watcher", "short", "medium", 17.0) is True

    # v3_mes — MES-specific config
    def test_v3_mes_shotgun_long_high_included(self):
        assert should_take_v3_mes("shotgun_scalper_watcher", "long", "high", 17.0) is True

    def test_v3_mes_erl_irl_excluded(self):
        # erl_irl is -$5,788 on real MES data — must NOT be in MES config
        assert should_take_v3_mes("erl_irl_watcher", "long", "high", 17.0) is False
        assert should_take_v3_mes("erl_irl_watcher", "short", "medium", 17.0) is False

    def test_v3_mes_shotgun_short_excluded(self):
        # shotgun short is -$1,174 on real MES — must NOT be in MES config
        assert should_take_v3_mes("shotgun_scalper_watcher", "short", "high", 17.0) is False
        assert should_take_v3_mes("shotgun_scalper_watcher", "short", "medium", 17.0) is False

    def test_v3_mes_v14_enhanced_short_included(self):
        assert should_take_v3_mes("v14_enhanced_watcher", "short", "medium", 18.0) is True
        assert should_take_v3_mes("v14_enhanced_watcher", "short", "high", 18.0) is True

    def test_v3_mes_tbr_short_medium_included(self):
        assert should_take_v3_mes("tbr_high_vol_watcher", "short", "medium", 17.0) is True

    def test_v3_mes_different_from_v3_mnq(self):
        # erl_irl long is in v3 but NOT in v3_mes — configs must diverge
        assert should_take_v3("erl_irl_watcher", "long", "high", 17.0) is True
        assert should_take_v3_mes("erl_irl_watcher", "long", "high", 17.0) is False


class TestORBFuturesScale:
    """ORB dollar thresholds must be scaled for futures (MNQ ~21000, MES ~5500)."""

    def _make_or_bars(self, or_low: float, or_high: float) -> pd.DataFrame:
        times = [dt.time(9, 30), dt.time(9, 35), dt.time(9, 40), dt.time(9, 45),
                 dt.time(9, 50), dt.time(9, 55)]
        rows = []
        for t in times:
            rows.append({
                "timestamp_et": pd.Timestamp(f"2026-01-02 {t}", tz="America/New_York"),
                "open": or_low + (or_high - or_low) * 0.3,
                "high": or_high,
                "low": or_low,
                "close": or_low + (or_high - or_low) * 0.6,
                "volume": 1000,
            })
        return pd.DataFrame(rows)

    def teardown_method(self, _):
        set_futures_range_scale(None)  # always restore SPY mode after each test

    def test_spy_narrow_or_passes(self):
        # SPY-like bars: OR range = 1.50, within [0.50, 2.00)
        bars = self._make_or_bars(or_low=700.0, or_high=701.5)
        assert compute_opening_range(bars) is not None

    def test_spy_wide_or_blocked(self):
        # SPY-like bars: OR range = 3.00, too wide for narrow-OR gate
        bars = self._make_or_bars(or_low=698.0, or_high=701.0)
        assert compute_opening_range(bars) is None

    def test_mnq_without_scale_blocked(self):
        # MNQ range of 45pt looks huge without scale → blocked by 2pt gate
        bars = self._make_or_bars(or_low=21000.0, or_high=21045.0)
        assert compute_opening_range(bars) is None

    def test_mnq_with_scale_passes(self):
        # MNQ scale = 21000/700 = 30. Max OR = 2.0*30 = 60pt. 45pt < 60pt → should pass.
        set_futures_range_scale(21000.0 / 700.0)
        bars = self._make_or_bars(or_low=21000.0, or_high=21045.0)
        assert compute_opening_range(bars) is not None

    def test_mnq_scale_blocks_extreme_range(self):
        # MNQ range of 250pt (tariff-shock morning) should still be blocked. 250 >= 2*30=60.
        set_futures_range_scale(21000.0 / 700.0)
        bars = self._make_or_bars(or_low=20900.0, or_high=21150.0)
        assert compute_opening_range(bars) is None

    def test_mes_with_scale_passes(self):
        # MES scale = 5500/700 ≈ 7.86. Max OR = 2.0*7.86 = 15.7pt. 12pt < 15.7 → pass.
        set_futures_range_scale(5500.0 / 700.0)
        bars = self._make_or_bars(or_low=5500.0, or_high=5512.0)
        assert compute_opening_range(bars) is not None

    def test_scale_resets_properly(self):
        # Setting scale then resetting to None should restore SPY behavior
        set_futures_range_scale(21000.0 / 700.0)
        set_futures_range_scale(None)
        # Wide MNQ should now be blocked again (SPY mode)
        bars = self._make_or_bars(or_low=21000.0, or_high=21045.0)
        assert compute_opening_range(bars) is None


# ─── Data loading ──────────────────────────────────────────────────────────────

class TestDataLoading:
    DATA_DIR = REPO / "backtest" / "data" / "futures"

    def test_mnq_csv_exists(self):
        assert (self.DATA_DIR / "MNQ_5m_continuous.csv").exists(), \
            "MNQ_5m_continuous.csv not found — run fetch_data.py first"

    def test_mes_csv_exists(self):
        assert (self.DATA_DIR / "MES_5m_continuous.csv").exists(), \
            "MES_5m_continuous.csv not found — run fetch_data.py first"

    def test_mnq_bar_schema(self):
        df = pd.read_csv(self.DATA_DIR / "MNQ_5m_continuous.csv")
        for col in ("timestamp_et", "open", "high", "low", "close", "volume"):
            assert col in df.columns, f"Missing column {col}"

    def test_mnq_price_range_reasonable(self):
        df = pd.read_csv(self.DATA_DIR / "MNQ_5m_continuous.csv")
        # MNQ 2025-2026: Nasdaq 100 from ~16K to ~30K+ (tariff rally + bull run)
        assert df["close"].min() > 10000, "MNQ close too low"
        assert df["close"].max() < 40000, "MNQ close too high"

    def test_mes_price_range_reasonable(self):
        df = pd.read_csv(self.DATA_DIR / "MES_5m_continuous.csv")
        # MES in 2025-2026 should be roughly 4800-7500
        assert df["close"].min() > 3000, "MES close too low"
        assert df["close"].max() < 10000, "MES close too high"

    def test_rth_filter(self):
        df = pd.read_csv(self.DATA_DIR / "MNQ_5m_continuous.csv")
        # Build a clean DataFrame with tz-aware timestamp_et
        ts = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
        clean = pd.DataFrame({
            "timestamp_et": ts,
            "open": df["open"], "high": df["high"],
            "low": df["low"], "close": df["close"], "volume": df["volume"],
        })
        rth = rth_only(clean)
        # After RTH filter, no bars before 9:30 or at/after 16:00
        times = rth["timestamp_et"].dt.time
        assert (times >= dt.time(9, 30)).all()
        assert (times < dt.time(16, 0)).all()


# ─── End-to-end signal smoke test ──────────────────────────────────────────────

class TestE2ESmokeTest:
    """Light smoke test: can the backtest engine run on futures bars without crashing?"""

    def test_native_rows_exist_mnq(self):
        rows_file = REPO / "backtest" / "data" / "futures" / "MNQ_native_rows.jsonl"
        if not rows_file.exists():
            pytest.skip("MNQ_native_rows.jsonl not found — run drive_native_backtest.py")
        rows = [json.loads(l) for l in rows_file.open()]
        assert len(rows) > 100, f"Only {len(rows)} rows — expected >100 signals"

    def test_mnq_signals_have_required_fields(self):
        rows_file = REPO / "backtest" / "data" / "futures" / "MNQ_native_rows.jsonl"
        if not rows_file.exists():
            pytest.skip("MNQ rows not yet generated")
        rows = [json.loads(l) for l in rows_file.open()]
        required = {"date", "watcher", "dir", "conf", "net", "outcome"}
        for r in rows[:10]:
            missing = required - set(r.keys())
            assert not missing, f"Row missing fields: {missing}"

    def test_mnq_oos_2026_positive(self):
        """Core gate: OOS 2026 must be net positive with v3 config (uses real VIX if present)."""
        rows_file = REPO / "backtest" / "data" / "futures" / "MNQ_native_rows.jsonl"
        if not rows_file.exists():
            pytest.skip("MNQ rows not yet generated")
        df = pd.DataFrame([json.loads(l) for l in rows_file.open()])
        if "vix" not in df.columns:
            df["vix"] = 17.0
        df["date"] = pd.to_datetime(df["date"])
        oos = df[df["date"] >= "2026-01-01"]
        v3 = oos[oos.apply(lambda r: should_take_v3(r["watcher"], r["dir"], r["conf"], r["vix"]), axis=1)]
        oos_net = v3["net"].sum()
        assert oos_net > 0, f"v3 OOS 2026 net=${oos_net:.0f} — must be positive"
        assert len(v3) >= 30, f"Only {len(v3)} OOS signals — need >=30 for confidence"

    def test_mnq_orb_oos_fails(self):
        """ORB must have ZERO OOS 2026 signals on MNQ — SPY-calibrated gate blocks 94% of days.
        Guard: if someone adds ORB back to v3 config, this test fails and forces re-evaluation."""
        rows_file = REPO / "backtest" / "data" / "futures" / "MNQ_native_rows.jsonl"
        if not rows_file.exists():
            pytest.skip("MNQ rows not yet generated")
        rows = [json.loads(l) for l in rows_file.open()]
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        oos_orb = df[(df["date"] >= "2026-01-01") & (df["watcher"] == "orb_watcher")]
        assert len(oos_orb) == 0, (
            f"ORB fired {len(oos_orb)} OOS signals — ORB is SPY-calibrated and not viable for futures. "
            "Do NOT add ORB to v3/v3_mes configs."
        )

    def test_mnq_v3_no_single_day_over_40pct(self):
        """No single day should contribute >40% of total v3 MNQ P&L (concentration guard)."""
        rows_file = REPO / "backtest" / "data" / "futures" / "MNQ_native_rows.jsonl"
        if not rows_file.exists():
            pytest.skip("MNQ rows not yet generated")
        df = pd.DataFrame([json.loads(l) for l in rows_file.open()])
        if "vix" not in df.columns:
            df["vix"] = 17.0
        df["date"] = pd.to_datetime(df["date"])
        v3 = df[df.apply(lambda r: should_take_v3(r["watcher"], r["dir"], r["conf"], r["vix"]), axis=1)]
        total = v3["net"].sum()
        daily = v3.groupby("date")["net"].sum()
        max_pct = (daily.abs() / abs(total) * 100).max() if total != 0 else 0
        assert max_pct <= 40.0, f"Max single-day P&L = {max_pct:.1f}% > 40% — edge is concentrated"

    def test_mnq_orb_fires_in_v2_rows(self):
        """After v2 backtest (ORB-enabled), ORB signals must exist in MNQ rows."""
        rows_file = REPO / "backtest" / "data" / "futures" / "MNQ_native_rows.jsonl"
        if not rows_file.exists():
            pytest.skip("MNQ rows not yet generated")
        rows = [json.loads(l) for l in rows_file.open()]
        has_vix = all("vix" in r for r in rows[:5])
        if not has_vix:
            pytest.skip("Rows lack vix field — re-run with drive_native_backtest_v2.py")
        orb = [r for r in rows if r.get("watcher") == "orb_watcher"]
        assert len(orb) > 0, "ORB watcher fired zero signals — check set_futures_range_scale"

    def test_mnq_rows_have_vix_field(self):
        """After v2 backtest, every row must have a vix field."""
        rows_file = REPO / "backtest" / "data" / "futures" / "MNQ_native_rows.jsonl"
        if not rows_file.exists():
            pytest.skip("MNQ rows not yet generated")
        rows = [json.loads(l) for l in rows_file.open()]
        if not rows:
            pytest.skip("No rows")
        if "vix" not in rows[0]:
            pytest.skip("Rows from pre-v2 run — re-run with drive_native_backtest_v2.py")
        missing = sum(1 for r in rows if "vix" not in r)
        assert missing == 0, f"{missing} rows missing vix field"

    def test_mes_native_rows_exist(self):
        rows_file = REPO / "backtest" / "data" / "futures" / "MES_native_rows.jsonl"
        if not rows_file.exists():
            pytest.skip("MES_native_rows.jsonl not found — run drive_native_backtest.py")
        rows = [json.loads(l) for l in rows_file.open()]
        assert len(rows) > 100, f"Only {len(rows)} rows"

    def test_mes_oos_2026_positive_v3_mes(self):
        """Core gate: OOS 2026 MES must be positive with MES-specific v3_mes config."""
        rows_file = REPO / "backtest" / "data" / "futures" / "MES_native_rows.jsonl"
        if not rows_file.exists():
            pytest.skip("MES rows not yet generated")
        df = pd.DataFrame([json.loads(l) for l in rows_file.open()])
        if "vix" not in df.columns:
            df["vix"] = 17.0
        df["date"] = pd.to_datetime(df["date"])
        oos = df[df["date"] >= "2026-01-01"]
        v3m = oos[oos.apply(lambda r: should_take_v3_mes(r["watcher"], r["dir"], r["conf"], r["vix"]), axis=1)]
        oos_net = v3m["net"].sum()
        assert oos_net > 0, f"v3_mes OOS 2026 net=${oos_net:.0f} — must be positive"

    def test_mes_v3_mes_beats_v2b_oos(self):
        """v3_mes must outperform v2b on MES OOS — verifies instrument-specific config wins."""
        rows_file = REPO / "backtest" / "data" / "futures" / "MES_native_rows.jsonl"
        if not rows_file.exists():
            pytest.skip("MES rows not yet generated")
        df = pd.DataFrame([json.loads(l) for l in rows_file.open()])
        if "vix" not in df.columns:
            df["vix"] = 17.0
        df["date"] = pd.to_datetime(df["date"])
        oos = df[df["date"] >= "2026-01-01"]
        v3m_net = oos[oos.apply(lambda r: should_take_v3_mes(r["watcher"], r["dir"], r["conf"], r["vix"]), axis=1)]["net"].sum()
        v2b_net = oos[oos.apply(lambda r: should_take_v2b(r["watcher"], r["dir"], r["conf"], r.get("vix", 17.0)), axis=1)]["net"].sum()
        assert v3m_net > v2b_net, f"v3_mes OOS=${v3m_net:.0f} should beat v2b OOS=${v2b_net:.0f}"

    def test_mnq_v3_rolling_2mo_windows_positive(self):
        """All 2-month rolling OOS windows must be positive for MNQ v3 — rolling stability guard."""
        rows_file = REPO / "backtest" / "data" / "futures" / "MNQ_native_rows.jsonl"
        if not rows_file.exists():
            pytest.skip("MNQ rows not yet generated")
        df = pd.DataFrame([json.loads(l) for l in rows_file.open()])
        if "vix" not in df.columns:
            df["vix"] = 17.0
        df["date"] = pd.to_datetime(df["date"])
        oos = df[df["date"] >= "2026-01-01"].copy()
        v3 = oos[oos.apply(lambda r: should_take_v3(r["watcher"], r["dir"], r["conf"], r["vix"]), axis=1)].copy()
        if v3.empty:
            pytest.skip("No OOS v3 signals")
        v3["month"] = v3["date"].dt.to_period("M")
        months = sorted(v3["month"].unique())
        failures = []
        for i in range(len(months) - 1):
            w = months[i:i+2]
            chunk = v3[v3["month"].isin(w)]
            if len(chunk) >= 3:
                net = chunk["net"].sum()
                if net <= 0:
                    failures.append(f"{w[0]}-{w[1]}: N={len(chunk)} net=${net:.0f}")
        assert not failures, f"MNQ v3 negative 2-month windows: {failures}"

    def test_mes_v3_mes_rolling_2mo_windows_positive(self):
        """All 2-month rolling OOS windows must be positive for MES v3_mes — rolling stability guard."""
        rows_file = REPO / "backtest" / "data" / "futures" / "MES_native_rows.jsonl"
        if not rows_file.exists():
            pytest.skip("MES rows not yet generated")
        df = pd.DataFrame([json.loads(l) for l in rows_file.open()])
        if "vix" not in df.columns:
            df["vix"] = 17.0
        df["date"] = pd.to_datetime(df["date"])
        oos = df[df["date"] >= "2026-01-01"].copy()
        v3m = oos[oos.apply(lambda r: should_take_v3_mes(r["watcher"], r["dir"], r["conf"], r["vix"]), axis=1)].copy()
        if v3m.empty:
            pytest.skip("No OOS v3_mes signals")
        v3m["month"] = v3m["date"].dt.to_period("M")
        months = sorted(v3m["month"].unique())
        failures = []
        for i in range(len(months) - 1):
            w = months[i:i+2]
            chunk = v3m[v3m["month"].isin(w)]
            if len(chunk) >= 3:
                net = chunk["net"].sum()
                if net <= 0:
                    failures.append(f"{w[0]}-{w[1]}: N={len(chunk)} net=${net:.0f}")
        assert not failures, f"MES v3_mes negative 2-month windows: {failures}"

    def test_tastytrade_broker_watch_only_does_not_connect(self):
        """Watch-only mode: place_bracket must log to file without any network call."""
        from futures.tastytrade_paper import TastytradeBroker, WOULD_BE_FILE
        import tempfile
        import futures.tastytrade_paper as tt_module

        broker = TastytradeBroker(watch_only=True)
        orig = tt_module.WOULD_BE_FILE
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            tmp = Path(f.name)
        try:
            tt_module.WOULD_BE_FILE = tmp
            result = broker.place_bracket("MNQ", "BUY", 3, 21400.0, 21450.0, 21370.0)
            assert result == [], "Watch-only should return empty order list"
            logged = json.loads(tmp.read_text().strip())
            assert logged["watch_only"] is True
            assert logged["instrument"] == "MNQ"
            assert logged["qty"] == 3
            assert logged["broker"] == "tastytrade"
        finally:
            tt_module.WOULD_BE_FILE = orig
            tmp.unlink(missing_ok=True)

    def test_futures_eod_flatten_prompt_exists(self):
        """Guard: futures-eod-flatten.md must exist — referenced in futures-heartbeat.md."""
        prompt = REPO / "automation" / "prompts" / "futures-eod-flatten.md"
        assert prompt.exists(), "futures-eod-flatten.md missing — referenced in futures-heartbeat.md"
        content = prompt.read_text()
        assert "15:55" in content, "EOD flatten prompt must reference 15:55 ET window"
        assert "cancel_all" in content, "EOD flatten prompt must describe cancel_all step"

    def test_futures_premarket_prompt_exists(self):
        """Guard: futures-premarket.md must exist — needed to populate key-levels.json each morning."""
        prompt = REPO / "automation" / "prompts" / "futures-premarket.md"
        assert prompt.exists(), "futures-premarket.md missing — heartbeat reads key-levels.json which premarket writes"
        content = prompt.read_text()
        assert "key-levels.json" in content, "Premarket prompt must describe writing key-levels.json"
        assert "VIX" in content, "Premarket prompt must document VIX gate check"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
