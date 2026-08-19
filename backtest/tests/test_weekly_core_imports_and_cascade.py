"""Guards for setup/scripts/weekly_core.py (the weekly-1 SEE/DECIDE skeleton) and
automation/state/weekly/participation_cascade.py (the joint gate-cascade funnel -- THE
load-bearing guard for the weekly-options program). Built by the INTEGRATOR workstream,
2026-08-18.

Both modules are loaded via importlib.util.spec_from_file_location (mirroring
backtest/tests/test_participation_cascade.py's own `_load` helper) rather than a package
import -- neither setup/scripts/ nor automation/state/weekly/ has an __init__.py, matching
every other script directory in this repo.

Run:  backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_weekly_core_imports_and_cascade.py -q
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = Path(os.path.dirname(os.path.dirname(HERE)))  # backtest/tests -> backtest -> 42/
ET = ZoneInfo("America/New_York")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


wc = _load("weekly_core", REPO / "setup" / "scripts" / "weekly_core.py")
pc = _load("weekly_participation_cascade", REPO / "automation" / "state" / "weekly" / "participation_cascade.py")


# =============================================================================================
# 1. REAL-RUNTIME-ENVIRONMENT import guard (REQUIRED)
# =============================================================================================

class TestRealRuntimeImports:
    def test_weekly_core_self_check_resolves_under_backtest_venv_python(self):
        """Mirrors this repo's real scheduled-task wiring (see
        setup/scripts/install-participation-daily.ps1's own WIRING PATTERN comment:
        wscript -> run_exe_hidden.vbs -> backtest\\.venv\\Scripts\\pythonw.exe -> <script>.py
        -- the backtest-venv interpreter invoked DIRECTLY on the script file). Launches the
        REAL file (not a bare `import weekly_core` inside pytest's own already-configured
        sys.path) as a fresh subprocess via the backtest venv's own python.exe, with a
        MINIMAL explicit env (no inherited PYTHONPATH or sys.path state from the pytest
        process) -- proving the module's own __file__-anchored sys.path bootstrap is
        self-sufficient, exactly as a real scheduled-task launch would be. `--self-check`
        does zero network I/O and zero state writes (see weekly_core.main)."""
        python_exe = REPO / "backtest" / ".venv" / "Scripts" / "python.exe"
        if not python_exe.exists():
            pytest.skip(f"backtest venv python not found at {python_exe}")
        script = REPO / "setup" / "scripts" / "weekly_core.py"
        env = {"SYSTEMROOT": os.environ.get("SYSTEMROOT", ""), "PATH": os.environ.get("PATH", "")}
        result = subprocess.run(
            [str(python_exe), str(script), "--self-check"],
            cwd=str(REPO), env=env, capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, (
            "weekly_core.py --self-check failed under the real backtest-venv interpreter "
            f"with a minimal env (mirrors the real scheduled-task launch shape):\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
        assert "self-check OK" in result.stdout, result.stdout


# =============================================================================================
# 2. NO-ORDER-PLACEMENT structural guard (REQUIRED, RED-PROOFED -- see build report)
# =============================================================================================

class TestNoOrderPlacement:
    """SOURCE-LEVEL structural assertion (intentional -- this is a source-text scan, not a
    runtime/behavioral test). Mirrors weekly/lib/conflict.py's own guard
    (test_weekly_conflict_gates.py::test_conflict_module_never_places_cancels_or_modifies_orders)
    and weekly/lib/kill_switch.py's `_assert_never_force_closes_positions` pattern. Stage A
    is shadow-only by CONSTRUCTION: this scans weekly_core.py's own source text for any of
    the real broker order-placement/cancel/modify function names used elsewhere in this repo
    (fleet_broker.py, the alpaca MCP tool names) and fails if the string appears ANYWHERE in
    the file -- the guarantee pinned here is stronger than "not called at runtime", it is
    "the string does not even exist in this file"."""

    _FORBIDDEN = [
        "place_option_order", "place_stock_order", "place_crypto_order", "place_order(",
        "place_bracket", "cancel_order", "cancel_all_orders", "close_position(",
        "close_all_positions", "close_all_spy_options", "replace_order_by_id",
        "exercise_options_position", "do_not_exercise_options_position", "mcp__alpaca",
    ]

    def test_weekly_core_never_places_cancels_or_modifies_orders(self):
        src = (REPO / "setup" / "scripts" / "weekly_core.py").read_text(encoding="utf-8")
        hits = [f for f in self._FORBIDDEN if f in src]
        assert not hits, f"weekly_core.py must never place/cancel/modify orders -- found: {hits}"


# =============================================================================================
# 3. weekly_core.py pure gate functions
# =============================================================================================

class TestCheckLiquidity:
    def _params(self, max_spread=5.0, min_oi=500):
        return {"entry": {"liquidity_gate": {"max_spread_pct_of_premium": max_spread,
                                              "min_open_interest": min_oi}}}

    def test_none_quote_fails_closed(self):
        r = wc.check_liquidity(None, self._params())
        assert r["allowed"] is False
        assert "no representative option contract" in r["reason"]

    def test_missing_bid_ask_fails_closed(self):
        q = {"occ_symbol": "GLD260821C00270000", "bid": None, "ask": 1.05, "open_interest": 1000}
        r = wc.check_liquidity(q, self._params())
        assert r["allowed"] is False
        assert "bid/ask unavailable" in r["reason"]

    def test_missing_open_interest_fails_closed(self):
        q = {"occ_symbol": "X", "bid": 1.0, "ask": 1.02, "open_interest": None}
        r = wc.check_liquidity(q, self._params())
        assert r["allowed"] is False
        assert "open_interest unavailable" in r["reason"]

    def test_wide_spread_denied(self):
        q = {"occ_symbol": "X", "bid": 1.0, "ask": 1.20, "open_interest": 1000}  # ~18% spread
        r = wc.check_liquidity(q, self._params(max_spread=5.0))
        assert r["allowed"] is False
        assert "spread" in r["reason"]

    def test_low_open_interest_denied(self):
        q = {"occ_symbol": "X", "bid": 1.00, "ask": 1.02, "open_interest": 10}
        r = wc.check_liquidity(q, self._params(min_oi=500))
        assert r["allowed"] is False
        assert "open_interest 10" in r["reason"]

    def test_tight_spread_sufficient_oi_allowed(self):
        q = {"occ_symbol": "X", "bid": 1.00, "ask": 1.02, "open_interest": 1000}
        r = wc.check_liquidity(q, self._params(max_spread=5.0, min_oi=500))
        assert r["allowed"] is True
        assert r["spread_pct"] == pytest.approx(1.98, abs=0.01)

    def test_missing_params_config_fails_closed(self):
        r = wc.check_liquidity({"occ_symbol": "X", "bid": 1.0, "ask": 1.01, "open_interest": 1000}, {})
        assert r["allowed"] is False


class TestCheckMinDteCalendar:
    def test_same_week_friday_clears_min_dte(self):
        # Monday, 4 DTE to that week's Friday, min_dte=3 -> passes without advancing.
        monday = date(2026, 8, 17)
        r = wc.check_min_dte_calendar(monday, min_dte=3)
        assert r["allowed"] is True
        assert r["advanced_past_same_week"] is False

    def test_thursday_same_week_under_min_dte_advances_and_still_passes(self):
        # Thursday: same-week Friday is 1 DTE, under min_dte=3 -> RULE_SAME_WEEK's own
        # self-heal advances a week (8 DTE), which clears 3 -- never denies.
        thursday = date(2026, 8, 20)
        r = wc.check_min_dte_calendar(thursday, min_dte=3)
        assert r["allowed"] is True
        assert r["advanced_past_same_week"] is True
        assert r["target_dte"] == 8

    def test_min_dte_exceeding_one_week_of_headroom_genuinely_denies(self):
        """The real bite this check has (module docstring judgment call 1): min_dte=10
        exceeds what a single self-heal advance (+7 days) can always satisfy from a
        Thursday (1 DTE same-week -> 8 DTE after advancing, still < 10)."""
        thursday = date(2026, 8, 20)
        r = wc.check_min_dte_calendar(thursday, min_dte=10)
        assert r["allowed"] is False
        assert r["target_dte"] == 8


class TestCheckEarningsBlackout:
    def _params(self, stale_h=48):
        return {"entry": {"earnings_feed_stale_hours_fail_closed": stale_h}}

    def _doc(self, generated_at, symbols):
        return {"generated_at_et": generated_at, "symbols": symbols}

    def test_missing_doc_fails_closed_data_error(self):
        r = wc.check_earnings_blackout("NVDA", None, self._params(), date(2026, 8, 18),
                                        datetime(2026, 8, 18, 10, 0, 0))
        assert r["allowed"] is False and r["data_error"] is True

    def test_stale_doc_fails_closed_data_error(self):
        doc = self._doc("2026-08-01T00:00:00", {"NVDA": {"exempt": False, "status": "ok",
                                                           "blackout_start_date": "2026-08-01",
                                                           "blackout_end_date": "2026-08-02"}})
        now = datetime(2026, 8, 18, 10, 0, 0)  # ~17 days old > 48h floor
        r = wc.check_earnings_blackout("NVDA", doc, self._params(stale_h=48), date(2026, 8, 18), now)
        assert r["allowed"] is False and r["data_error"] is True

    def test_exempt_etf_always_allowed(self):
        doc = self._doc("2026-08-18T20:00:00", {"GLD": {"exempt": True, "reason": "known ETF"}})
        now = datetime(2026, 8, 18, 20, 30, 0)
        r = wc.check_earnings_blackout("GLD", doc, self._params(), date(2026, 8, 18), now)
        assert r["allowed"] is True and r["data_error"] is False

    def test_status_not_ok_fails_closed_data_error(self):
        doc = self._doc("2026-08-18T20:00:00", {"NVDA": {"exempt": False, "status": "unavailable"}})
        now = datetime(2026, 8, 18, 20, 30, 0)
        r = wc.check_earnings_blackout("NVDA", doc, self._params(), date(2026, 8, 18), now)
        assert r["allowed"] is False and r["data_error"] is True

    def test_inside_blackout_window_denies_not_a_data_error(self):
        doc = self._doc("2026-08-22T08:00:00", {"NVDA": {
            "exempt": False, "status": "ok", "next_earnings_date": "2026-08-26",
            "blackout_start_date": "2026-08-21", "blackout_end_date": "2026-08-27"}})
        now = datetime(2026, 8, 22, 10, 0, 0)  # 2h after generated_at_et -- well inside the 48h floor
        r = wc.check_earnings_blackout("NVDA", doc, self._params(), date(2026, 8, 22), now)
        assert r["allowed"] is False and r["data_error"] is False
        assert "inside the earnings blackout window" in r["reason"]

    def test_clear_of_blackout_window_allowed(self):
        doc = self._doc("2026-08-18T20:00:00", {"NVDA": {
            "exempt": False, "status": "ok", "next_earnings_date": "2026-08-26",
            "blackout_start_date": "2026-08-21", "blackout_end_date": "2026-08-27"}})
        now = datetime(2026, 8, 18, 20, 30, 0)
        r = wc.check_earnings_blackout("NVDA", doc, self._params(), date(2026, 8, 18), now)
        assert r["allowed"] is True


class TestExpiryAvailabilityHelpers:
    def test_available_expiries_from_contracts_dedupes_and_sorts(self):
        contracts = [
            {"expiration_date": "2026-08-28"}, {"expiration_date": "2026-08-21"},
            {"expiration_date": "2026-08-21"}, {"expiration_date": "bad-date"}, {},
        ]
        out = wc.available_expiries_from_contracts(contracts)
        assert out == (date(2026, 8, 21), date(2026, 8, 28))

    def test_pick_atm_contract_nearest_strike(self):
        contracts = [
            {"expiration_date": "2026-08-21", "type": "call", "strike_price": "95", "tradable": True, "symbol": "A"},
            {"expiration_date": "2026-08-21", "type": "call", "strike_price": "100", "tradable": True, "symbol": "B"},
            {"expiration_date": "2026-08-21", "type": "call", "strike_price": "105", "tradable": True, "symbol": "C"},
            {"expiration_date": "2026-08-21", "type": "put", "strike_price": "100", "tradable": True, "symbol": "D"},
        ]
        c = wc._pick_atm_contract(contracts, date(2026, 8, 21), "call", spot=101.4)
        assert c["symbol"] == "B"

    def test_pick_atm_contract_none_when_no_match(self):
        contracts = [{"expiration_date": "2026-08-21", "type": "put", "strike_price": "100",
                      "tradable": True, "symbol": "D"}]
        assert wc._pick_atm_contract(contracts, date(2026, 8, 21), "call", spot=100.0) is None

    def test_resolve_expiry_availability_empty_chain_blocks(self):
        params = {"entry": {"expiry_rule": "this_friday_if_dte_ge_3_else_next_friday"}}
        sel, res = wc.resolve_expiry_availability("GLD", (), params, date(2026, 8, 18), 3)
        assert sel is None and res["allowed"] is False

    def test_resolve_expiry_availability_unrecognized_rule_raises(self):
        params = {"entry": {"expiry_rule": "some_unmapped_rule"}}
        with pytest.raises(ValueError):
            wc.resolve_expiry_availability("GLD", (date(2026, 8, 21),), params, date(2026, 8, 18), 3)

    def test_resolve_expiry_availability_succeeds_on_a_real_chain(self):
        params = {"entry": {"expiry_rule": "this_friday_if_dte_ge_3_else_next_friday"}}
        as_of = date(2026, 8, 17)  # Monday
        chain = tuple(sorted({as_of + timedelta(days=d) for d in range(1, 22)}))
        sel, res = wc.resolve_expiry_availability("GLD", chain, params, as_of, 3)
        assert res["allowed"] is True
        assert sel is not None and sel.dte >= 3


class TestBuildLiquidityQuote:
    def _contracts(self):
        return [
            {"expiration_date": "2026-08-21", "type": "call", "strike_price": "100",
             "tradable": True, "symbol": "GLD260821C00100000", "open_interest": 1500},
            {"expiration_date": "2026-08-21", "type": "put", "strike_price": "100",
             "tradable": True, "symbol": "GLD260821P00100000", "open_interest": 900},
            {"expiration_date": "2026-08-28", "type": "call", "strike_price": "100",
             "tradable": True, "symbol": "GLD260828C00100000", "open_interest": 300},
        ]

    def test_bullish_picks_call_at_nearest_expiry_with_quote(self):
        def fake_snaps(symbol):
            return {"GLD260821C00100000": {"latestQuote": {"bp": 1.10, "ap": 1.15},
                                            "open_interest": 1500}}
        q = wc.build_liquidity_quote("GLD", spot=100.2, direction="bullish",
                                      contracts=self._contracts(), snapshots_fetcher=fake_snaps)
        assert q["occ_symbol"] == "GLD260821C00100000"
        assert q["bid"] == 1.10 and q["ask"] == 1.15
        assert q["open_interest"] == 1500
        assert q["right"] == "call"

    def test_bearish_picks_put(self):
        def fake_snaps(symbol):
            return {"GLD260821P00100000": {"latestQuote": {"bp": 0.90, "ap": 0.95}}}
        q = wc.build_liquidity_quote("GLD", spot=99.8, direction="bearish",
                                      contracts=self._contracts(), snapshots_fetcher=fake_snaps)
        assert q["right"] == "put" and q["occ_symbol"] == "GLD260821P00100000"

    def test_empty_chain_returns_none(self):
        assert wc.build_liquidity_quote("GLD", 100.0, "bullish", (), snapshots_fetcher=lambda s: {}) is None

    def test_missing_snapshot_entry_yields_none_bid_ask(self):
        q = wc.build_liquidity_quote("GLD", 100.2, "bullish", self._contracts(),
                                      snapshots_fetcher=lambda s: {})
        assert q["occ_symbol"] == "GLD260821C00100000"
        assert q["bid"] is None and q["ask"] is None
        assert q["open_interest"] == 1500  # sourced from the contracts payload, not the snapshot


# =============================================================================================
# 4. evaluate_symbol -- full pipeline, fully injected/monkeypatched (no network)
# =============================================================================================

def _daily_df(n=70, close=100.0):
    idx = pd.date_range("2026-05-01", periods=n, freq="B", tz=ET)
    return pd.DataFrame(
        {"open": close, "high": close + 1.0, "low": close - 1.0, "close": close, "volume": 1000.0},
        index=idx,
    ).rename_axis("timestamp_et")


def _hourly_df(n=40, close=100.0):
    idx = pd.date_range("2026-08-01 09:30", periods=n, freq="1h", tz=ET)
    return pd.DataFrame(
        {"open": close, "high": close + 0.5, "low": close - 0.5, "close": close, "volume": 500.0},
        index=idx,
    ).rename_axis("timestamp_et")


def _fake_zone(price=100.0):
    return wc.weekly_zones.Zone(price=price, width=1.0, family="swing_high_low", role="support",
                                 touch_count=2, source_bar_indices=(0,))


def _fake_signal(symbol, zone, direction="bullish"):
    return wc.weekly_trigger.WeeklySignal(symbol=symbol, direction=direction, zone=zone,
                                           trigger_bar_index=0, confluence_count=1,
                                           iv_rank=None, sector_heat_rs=None)


def _real_params():
    return json.loads(wc.PARAMS_PATH.read_text(encoding="utf-8"))


def _fridays_chain(as_of: date, weeks: int = 4) -> tuple:
    out = set()
    d = as_of
    for _ in range(weeks * 7 + 7):
        if d.weekday() == 4:
            out.add(d)
        d += timedelta(days=1)
    return tuple(sorted(out))


def _contracts_for(as_of: date, right_both=True):
    contracts = []
    for fri in _fridays_chain(as_of):
        for right, occ in (("call", "SYM_C"), ("put", "SYM_P")):
            contracts.append({
                "expiration_date": fri.isoformat(), "type": right, "strike_price": "100",
                "tradable": True, "symbol": f"{occ}_{fri.isoformat()}", "open_interest": 1000,
            })
    return tuple(contracts)


def _tight_snapshots(symbol):
    def _fn(sym):
        out = {}
        for c in _contracts_for(date(2026, 8, 17)):
            out[c["symbol"]] = {"latestQuote": {"bp": 1.00, "ap": 1.02}, "open_interest": 1000}
        return out
    return _fn(symbol)


class TestEvaluateSymbolPipeline:
    def _base_kwargs(self, monkeypatch, *, quote_bid=1.00, quote_ask=1.02, direction="bullish"):
        as_of = date(2026, 8, 17)  # Monday -- same-week Friday is 4 DTE, clears min_dte=3
        now_et = datetime(2026, 8, 17, 10, 0, 0, tzinfo=ET)
        zone = _fake_zone()
        signal = _fake_signal("GLD", zone, direction=direction)

        monkeypatch.setattr(wc.weekly_zones, "compute_zones", lambda bars, params=None: (zone,))
        monkeypatch.setattr(wc.weekly_trigger, "detect_trigger",
                             lambda sym, zones, bars, params=None: signal)

        contracts = _contracts_for(as_of)

        def snapshots_fetcher(symbol):
            return {c["symbol"]: {"latestQuote": {"bp": quote_bid, "ap": quote_ask},
                                   "open_interest": 1000} for c in contracts}

        blackout_doc = {
            "generated_at_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
            "symbols": {"GLD": {"exempt": True, "reason": "known ETF"}},
        }
        return dict(
            symbol="GLD", params=_real_params(), now_et=now_et, earnings_blackout_doc=blackout_doc,
            open_positions={},
            daily_bars_fetcher=lambda sym, **kw: _daily_df(),
            hourly_bars_fetcher=lambda sym, **kw: _hourly_df(),
            contracts_fetcher=lambda sym, **kw: contracts,
            snapshots_fetcher=snapshots_fetcher,
        )

    def test_full_clear_would_place(self, monkeypatch):
        kwargs = self._base_kwargs(monkeypatch)
        row = wc.evaluate_symbol(**kwargs)
        assert row["stage"] == wc.STAGE_WOULD_PLACE, row["reason"]
        assert row["decision"] == "WOULD_PLACE"
        assert row["gate"] is None
        assert row["direction"] == "bullish"
        assert row["chosen_expiry"] is not None
        assert row["feed"] == "indicative"

    def test_wide_spread_blocks_at_liquidity(self, monkeypatch):
        kwargs = self._base_kwargs(monkeypatch, quote_bid=1.00, quote_ask=1.40)  # ~33% spread
        row = wc.evaluate_symbol(**kwargs)
        assert row["stage"] == wc.STAGE_LIQUIDITY_BLOCK
        assert row["gate"] == "liquidity"
        assert row["decision"] == "BLOCKED"

    def test_bars_fetch_error_is_data_error(self, monkeypatch):
        kwargs = self._base_kwargs(monkeypatch)

        def raise_bar_error(sym, **kw):
            raise wc.weekly_bars.BarFetchError(f"{sym}: simulated fetch failure")

        kwargs["daily_bars_fetcher"] = raise_bar_error
        row = wc.evaluate_symbol(**kwargs)
        assert row["stage"] == wc.STAGE_NO_DATA
        assert row["decision"] == "DATA_ERROR"
        assert row["gate"] == "bars_daily"

    def test_no_trigger_is_no_signal(self, monkeypatch):
        kwargs = self._base_kwargs(monkeypatch)
        monkeypatch.setattr(wc.weekly_trigger, "detect_trigger",
                             lambda sym, zones, bars, params=None: None)
        row = wc.evaluate_symbol(**kwargs)
        assert row["stage"] == wc.STAGE_NO_TRIGGER
        assert row["decision"] == "NO_SIGNAL"

    def test_earnings_blackout_window_blocks_single_name(self, monkeypatch):
        kwargs = self._base_kwargs(monkeypatch)
        kwargs["symbol"] = "NVDA"
        as_of = kwargs["now_et"].date()
        kwargs["earnings_blackout_doc"] = {
            "generated_at_et": kwargs["now_et"].strftime("%Y-%m-%dT%H:%M:%S"),
            "symbols": {"NVDA": {"exempt": False, "status": "ok", "next_earnings_date": "2026-08-20",
                                  "blackout_start_date": "2026-08-14", "blackout_end_date": "2026-08-21"}},
        }
        monkeypatch.setattr(wc.weekly_trigger, "detect_trigger",
                             lambda sym, zones, bars, params=None: _fake_signal("NVDA", _fake_zone()))
        row = wc.evaluate_symbol(**kwargs)
        assert row["stage"] == wc.STAGE_EARNINGS_BLACKOUT_BLOCK
        assert row["gate"] == "earnings_blackout"

    def test_concurrency_block_when_basket_full(self, monkeypatch):
        kwargs = self._base_kwargs(monkeypatch)
        kwargs["open_positions"] = {"QQQ": {"qty": 3, "premium": 1.5}, "NVDA": {"qty": 3, "premium": 2.0}}
        row = wc.evaluate_symbol(**kwargs)
        assert row["stage"] == wc.STAGE_CONCURRENCY_BLOCK
        assert row["gate"] == "concurrency"

    def test_correlation_block_denies_via_injected_price_fetcher(self, monkeypatch):
        kwargs = self._base_kwargs(monkeypatch)
        kwargs["open_positions"] = {"QQQ": {"qty": 3, "premium": 1.5}}

        # 25 aligned, perfectly-correlated synthetic daily closes for both symbols.
        base = [100.0 + i for i in range(25)]
        kwargs["correlation_price_fetcher"] = lambda symbol, lookback_days, now_et=None: list(base)

        row = wc.evaluate_symbol(**kwargs)
        assert row["stage"] == wc.STAGE_CORRELATION_BLOCK
        assert row["gate"] == "correlation"


# =============================================================================================
# 5. weekly_core.run() -- orchestration (universe/exit-code), evaluate_symbol monkeypatched
# =============================================================================================

class TestRun:
    def _params_file(self, tmp_path, universe):
        p = tmp_path / "params.json"
        p.write_text(json.dumps({"universe": {"active": universe}}), encoding="utf-8")
        return p

    def test_empty_universe_raises(self, tmp_path):
        p = self._params_file(tmp_path, [])
        with pytest.raises(RuntimeError, match="universe.active is EMPTY"):
            wc.run(params_path=p, ledger_path=tmp_path / "ledger.jsonl",
                   earnings_blackout_path=tmp_path / "eb.json", positions_path=tmp_path / "pos.json")

    def test_writes_ledger_rows_and_exit_code_zero_when_clean(self, tmp_path, monkeypatch):
        p = self._params_file(tmp_path, ["GLD", "QQQ"])
        monkeypatch.setattr(wc, "evaluate_symbol",
                             lambda symbol, **kw: {"symbol": symbol, "stage": wc.STAGE_WOULD_PLACE,
                                                    "decision": "WOULD_PLACE", "gate": None, "reason": "ok"})
        ledger = tmp_path / "ledger.jsonl"
        result = wc.run(params_path=p, ledger_path=ledger, earnings_blackout_path=tmp_path / "eb.json",
                         positions_path=tmp_path / "pos.json")
        assert result["exit_code"] == 0
        assert len(result["rows"]) == 2
        lines = ledger.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

    def test_exit_code_one_when_any_data_error(self, tmp_path, monkeypatch):
        p = self._params_file(tmp_path, ["GLD", "QQQ"])

        def fake_eval(symbol, **kw):
            if symbol == "QQQ":
                return {"symbol": symbol, "stage": wc.STAGE_NO_DATA, "decision": "DATA_ERROR",
                        "gate": "bars_daily", "reason": "simulated"}
            return {"symbol": symbol, "stage": wc.STAGE_WOULD_PLACE, "decision": "WOULD_PLACE",
                    "gate": None, "reason": "ok"}

        monkeypatch.setattr(wc, "evaluate_symbol", fake_eval)
        result = wc.run(params_path=p, ledger_path=tmp_path / "ledger.jsonl",
                         earnings_blackout_path=tmp_path / "eb.json", positions_path=tmp_path / "pos.json")
        assert result["exit_code"] == 1


# =============================================================================================
# 6. participation_cascade.py -- funnel counting on synthetic ledgers
# =============================================================================================

def _cascade_row(day: str, symbol: str, stage: str, *, gate=None, hh="10", mm="00") -> dict:
    return {"ts_et": f"{day}T{hh}:{mm}:00", "arm": "weekly-1", "symbol": symbol,
            "stage": stage, "gate": gate}


class TestCascadeFunnel:
    def test_full_funnel_all_would_place(self, tmp_path):
        ledger = tmp_path / "shadow-ledger.jsonl"
        rows = [_cascade_row("2026-08-18", "GLD", pc.STAGE_WOULD_PLACE),
                _cascade_row("2026-08-18", "QQQ", pc.STAGE_WOULD_PLACE)]
        ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        f = pc.compute_cascade_day("2026-08-18", ledger_path=ledger)
        assert f["symbols_evaluated"] == 2
        assert f["n_data_errors_excluded_from_funnel"] == 0
        for label in pc.CHECKPOINT_LABELS:
            assert f["funnel"][label] == 2, f"{label} expected 2, got {f['funnel'][label]}"
        assert f["joint_pass_rate_pct_of_triggered"] == 100.0
        assert f["verdict"] == "WOULD_PLACE_OCCURRED"
        assert f["top_blockers"] == []

    def test_no_rows_for_day_is_fully_visible_not_a_crash(self, tmp_path):
        ledger = tmp_path / "shadow-ledger.jsonl"
        ledger.write_text("", encoding="utf-8")
        f = pc.compute_cascade_day("2026-08-18", ledger_path=ledger)
        assert f["symbols_evaluated"] == 0
        assert f["verdict"] == "NO_DATA_FOR_DAY"
        assert f["joint_pass_rate_pct_of_triggered"] is None

    def test_missing_ledger_file_fails_open(self, tmp_path):
        f = pc.compute_cascade_day("2026-08-18", ledger_path=tmp_path / "does-not-exist.jsonl")
        assert f["symbols_evaluated"] == 0
        assert f["verdict"] == "NO_DATA_FOR_DAY"

    def test_middle_gate_kills_everything_joint_pass_rate_zero_and_correctly_attributed(self, tmp_path):
        """THE required zero-participation attribution test: 3 symbols reach the trigger and
        all die at the SAME middle gate (earnings-blackout, checkpoint index 4 of 9), plus a
        NO_ZONE and a NO_TRIGGER and a NO_DATA row for a realistic mixed day. Pins the exact
        funnel counts by hand-computed rank arithmetic -- see participation_cascade.py's
        `_RANK`/`ORDERED_STAGES` docstring for the formula this exercises."""
        ledger = tmp_path / "shadow-ledger.jsonl"
        rows = [
            _cascade_row("2026-08-19", "AAA", pc.STAGE_NO_DATA, gate="bars_daily"),
            _cascade_row("2026-08-19", "BBB", pc.STAGE_NO_ZONE),
            _cascade_row("2026-08-19", "CCC", pc.STAGE_NO_TRIGGER),
            _cascade_row("2026-08-19", "DDD", pc.STAGE_EARNINGS_BLACKOUT_BLOCK, gate="earnings_blackout"),
            _cascade_row("2026-08-19", "EEE", pc.STAGE_EARNINGS_BLACKOUT_BLOCK, gate="earnings_blackout"),
            _cascade_row("2026-08-19", "FFF", pc.STAGE_EARNINGS_BLACKOUT_BLOCK, gate="earnings_blackout"),
        ]
        ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        f = pc.compute_cascade_day("2026-08-19", ledger_path=ledger)

        assert f["symbols_evaluated"] == 6
        assert f["n_data_errors_excluded_from_funnel"] == 1
        assert f["funnel"]["zone_present"] == 4          # everyone except AAA(excluded) and BBB(NO_ZONE)
        assert f["funnel"]["trigger_fired"] == 3          # DDD/EEE/FFF only (CCC stopped at NO_TRIGGER)
        assert f["funnel"]["liquidity_pass"] == 3
        assert f["funnel"]["min_dte_pass"] == 3
        assert f["funnel"]["earnings_blackout_pass"] == 0  # THE kill point -- all 3 triggered symbols die here
        assert f["funnel"]["expiry_available_pass"] == 0
        assert f["funnel"]["concurrency_pass"] == 0
        assert f["funnel"]["correlation_pass"] == 0
        assert f["funnel"]["would_place"] == 0

        assert f["joint_pass_rate_pct_of_triggered"] == 0.0
        assert f["verdict"] == "GATED_OUT"

        assert f["top_blockers"] == [
            {"stage": pc.STAGE_EARNINGS_BLACKOUT_BLOCK, "gate": "earnings_blackout", "count": 3}
        ], f["top_blockers"]

    def test_arm_field_filters_out_non_weekly_rows(self, tmp_path):
        ledger = tmp_path / "shadow-ledger.jsonl"
        rows = [
            {"ts_et": "2026-08-18T10:00:00", "arm": "safe-2", "symbol": "SPY", "stage": "PLACED"},
            _cascade_row("2026-08-18", "GLD", pc.STAGE_WOULD_PLACE),
        ]
        ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        f = pc.compute_cascade_day("2026-08-18", ledger_path=ledger)
        assert f["symbols_evaluated"] == 1

    def test_discover_sessions_and_compute_cascade_sessions(self, tmp_path):
        ledger = tmp_path / "shadow-ledger.jsonl"
        rows = [_cascade_row("2026-08-17", "GLD", pc.STAGE_WOULD_PLACE),
                _cascade_row("2026-08-18", "QQQ", pc.STAGE_NO_TRIGGER)]
        ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        days = pc.discover_sessions(10, ledger_path=ledger)
        assert days == ["2026-08-17", "2026-08-18"]
        sessions = pc.compute_cascade_sessions(10, ledger_path=ledger)
        assert [s["date"] for s in sessions] == ["2026-08-17", "2026-08-18"]

    def test_summarize_range_aggregates_and_returns_joint_pass_rate(self, tmp_path):
        ledger = tmp_path / "shadow-ledger.jsonl"
        rows = [
            _cascade_row("2026-08-17", "GLD", pc.STAGE_WOULD_PLACE),
            _cascade_row("2026-08-17", "QQQ", pc.STAGE_CORRELATION_BLOCK, gate="correlation"),
            _cascade_row("2026-08-18", "GLD", pc.STAGE_NO_TRIGGER),
        ]
        ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        summary = pc.summarize_range("2026-08-17", "2026-08-18", ledger_path=ledger)
        assert summary["n_days"] == 2
        assert summary["symbols_evaluated"] == 3
        assert summary["trigger_fired"] == 2  # GLD(WOULD_PLACE) + QQQ(CORRELATION_BLOCK); NO_TRIGGER excluded
        assert summary["would_place"] == 1
        assert summary["joint_pass_rate_pct_of_triggered"] == 50.0
        assert any(b["stage"] == pc.STAGE_CORRELATION_BLOCK for b in summary["top_blockers"])

    def test_summarize_range_rejects_inverted_range(self, tmp_path):
        with pytest.raises(ValueError):
            pc.summarize_range("2026-08-20", "2026-08-18", ledger_path=tmp_path / "x.jsonl")


class TestCascadeArtifactWriter:
    def test_append_cascade_row_appends_not_overwrites(self, tmp_path):
        out = tmp_path / "participation-cascade.jsonl"
        f1 = {"date": "2026-08-17", "symbols_evaluated": 2, "funnel": {}, "top_blockers": [],
              "rows": [{"x": 1}]}
        f2 = {"date": "2026-08-18", "symbols_evaluated": 1, "funnel": {}, "top_blockers": [],
              "rows": []}
        pc.append_cascade_row(f1, path=out, now_et=datetime(2026, 8, 17, 16, 0, 0))
        pc.append_cascade_row(f2, path=out, now_et=datetime(2026, 8, 18, 16, 0, 0))
        lines = out.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        row1 = json.loads(lines[0])
        assert row1["date"] == "2026-08-17"
        assert "rows" not in row1, "full per-row detail must be dropped before persisting"
        assert row1["generated_at_et"] == "2026-08-17T16:00:00"


# =============================================================================================
# 7. weekly_core.py loaded module sanity (module-level constants stay in lockstep)
# =============================================================================================

def test_stage_vocabulary_matches_between_weekly_core_and_participation_cascade():
    """If either file's STAGE_* constants ever drift, the funnel silently miscounts. This
    pins them equal -- a genuine cross-module contract, not a coincidence."""
    wc_stages = {wc.STAGE_NO_DATA, wc.STAGE_NO_ZONE, wc.STAGE_NO_TRIGGER, wc.STAGE_LIQUIDITY_BLOCK,
                 wc.STAGE_MIN_DTE_BLOCK, wc.STAGE_EARNINGS_BLACKOUT_BLOCK,
                 wc.STAGE_EXPIRY_UNAVAILABLE_BLOCK, wc.STAGE_CONCURRENCY_BLOCK,
                 wc.STAGE_CORRELATION_BLOCK, wc.STAGE_WOULD_PLACE}
    pc_stages = {pc.STAGE_NO_DATA, pc.STAGE_NO_ZONE, pc.STAGE_NO_TRIGGER, pc.STAGE_LIQUIDITY_BLOCK,
                 pc.STAGE_MIN_DTE_BLOCK, pc.STAGE_EARNINGS_BLACKOUT_BLOCK,
                 pc.STAGE_EXPIRY_UNAVAILABLE_BLOCK, pc.STAGE_CONCURRENCY_BLOCK,
                 pc.STAGE_CORRELATION_BLOCK, pc.STAGE_WOULD_PLACE}
    assert wc_stages == pc_stages
