"""Guards for setup/scripts/trade_matrix_build.py -- the canonical trade table.

These pin the two traps the builder exists to survive, plus the honesty rails:

  TRAP 1 (multi-leg exits)  -- a TP1 + runner split exit must produce ONE round trip with a
      REAL qty-weighted exit_premium, never None, never dropped, never zeroed. The upstream
      fills_fifo returns exit_premium=None for exactly this case (its real_pnl is still
      exact), and on 2026-08-19 two of fourteen round trips were split exits -- one of them
      the day's biggest winner. A consumer that drops None rows deletes real money.
  TRAP 2 (broker is truth) -- --verify must NEVER print RECONCILED without an actual broker
      comparison. An unreachable or skipped broker is UNRECONCILED, with a reason.

  Same-day re-entry  -- the same OCC symbol bought, fully sold, and bought again the same day
      is TWO round trips, not one blended average (the 2026-08-02 scar: a replayed +$605
      against a real -$80 while the aggregate still summed correctly).
  No fabrication     -- missing SPY at entry yields moneyness None, not a fabricated "ATM";
      a held window with no OPRA prints yields no MAE/MFE, not an imputed one.
  No look-ahead (C6) -- the filter-release scan and the nearest-core-state fallback must only
      ever read rows STRICTLY BEFORE the entry instant.

Pure/offline: every test builds its own tiny ledger in tmp_path. Nothing here touches the
network, the real ledger, or any live state.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "automation" / "state" / "fleet", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_SPEC = importlib.util.spec_from_file_location(
    "trade_matrix_build", REPO / "setup" / "scripts" / "trade_matrix_build.py")
tmb = importlib.util.module_from_spec(_SPEC)
sys.modules["trade_matrix_build"] = tmb
_SPEC.loader.exec_module(tmb)

import fills_fifo  # noqa: E402


# ------------------------------------------------------------------ fixtures
def _fill(arm, symbol, side, qty, price, ts_et, aid):
    return {"activity_id": aid, "arm": arm, "order_id": f"ord-{aid}", "symbol": symbol,
            "side": side, "qty": float(qty), "price": float(price), "multiplier": 100,
            "is_crypto": False, "is_option": True,
            "ts_utc": f"{ts_et}Z", "ts_et": ts_et, "date_et": ts_et[:10],
            "attribution": "engine"}


def _write_ledger(tmp_path: Path, fills: list[dict]) -> Path:
    p = tmp_path / "fills-ledger.jsonl"
    p.write_text("\n".join(json.dumps(f) for f in fills) + "\n", encoding="utf-8")
    return p


# ============================================================ TRAP 1: multi-leg exits
def test_split_exit_yields_one_trip_with_a_real_weighted_exit_premium(tmp_path):
    """TP1 (2 @ 2.00) + runner (1 @ 0.50) on a 3-lot entry @ 1.00.
    Exit premium must be the qty-weighted average (2*2.00 + 1*0.50)/3 = 1.50 -- a NUMBER."""
    sym = "SPY260819C00771000"
    led = _write_ledger(tmp_path, [
        _fill("safe-2", sym, "buy", 3, 1.00, "2026-08-19T10:00:00", "a1"),
        _fill("safe-2", sym, "sell", 2, 2.00, "2026-08-19T10:10:00", "a2"),
        _fill("safe-2", sym, "sell", 1, 0.50, "2026-08-19T10:20:00", "a3"),
    ])
    trips = tmb.reconstruct_round_trips("safe-2", led)
    assert len(trips) == 1
    t = trips[0]
    assert t["n_exit_legs"] == 2
    assert t["exit_premium"] == pytest.approx(1.50)          # NEVER None
    assert t["exit_premium"] is not None
    assert t["real_pnl"] == pytest.approx((4.5 - 3.0) * 100) # +$150
    assert t["exit_ts_et"] == "2026-08-19T10:20:00"          # last leg closes the trip


def test_upstream_fills_fifo_returns_none_here_and_we_do_not(tmp_path):
    """Pins the exact upstream behaviour this module exists to repair. If fills_fifo ever
    starts returning a real exit_premium for split exits, this test fails LOUD so the
    duplication can be removed rather than silently drifting (C14)."""
    sym = "SPY260819C00771000"
    led = _write_ledger(tmp_path, [
        _fill("safe-2", sym, "buy", 3, 1.00, "2026-08-19T10:00:00", "a1"),
        _fill("safe-2", sym, "sell", 2, 2.00, "2026-08-19T10:10:00", "a2"),
        _fill("safe-2", sym, "sell", 1, 0.50, "2026-08-19T10:20:00", "a3"),
    ])
    ref = fills_fifo.mine_real_arm_fills("safe-2", led)
    assert len(ref) == 1 and ref[0]["exit_premium"] is None
    assert tmb.reconstruct_round_trips("safe-2", led)[0]["exit_premium"] is not None


def test_crosscheck_agrees_with_fills_fifo_on_a_split_exit(tmp_path):
    """Gross P&L, qty and exit timestamp must match the standing reconstructor exactly."""
    sym = "SPY260819P00770000"
    led = _write_ledger(tmp_path, [
        _fill("risky-3", sym, "buy", 8, 1.15, "2026-08-19T11:00:00", "b1"),
        _fill("risky-3", sym, "sell", 5, 1.93, "2026-08-19T11:07:00", "b2"),
        _fill("risky-3", sym, "sell", 3, 0.80, "2026-08-19T11:30:00", "b3"),
    ])
    rows = tmb.reconstruct_round_trips("risky-3", led)
    assert tmb.crosscheck_against_fills_fifo("risky-3", rows, led) == []


def test_partially_exited_position_is_still_open_and_never_flushed(tmp_path):
    """Only one of two sell legs has landed: the trip is OPEN, so it must not appear at all --
    and must NOT appear with a fabricated exit or a zeroed P&L."""
    sym = "SPY260819C00771000"
    led = _write_ledger(tmp_path, [
        _fill("safe-2", sym, "buy", 3, 1.00, "2026-08-19T10:00:00", "a1"),
        _fill("safe-2", sym, "sell", 2, 2.00, "2026-08-19T10:10:00", "a2"),
    ])
    assert tmb.reconstruct_round_trips("safe-2", led) == []


# ============================================================ same-day re-entry
def test_same_symbol_reentry_is_two_round_trips_not_one_blended_average(tmp_path):
    sym = "SPY260819C00771000"
    led = _write_ledger(tmp_path, [
        _fill("safe-3", sym, "buy", 2, 1.00, "2026-08-19T10:00:00", "c1"),
        _fill("safe-3", sym, "sell", 2, 1.50, "2026-08-19T10:05:00", "c2"),
        _fill("safe-3", sym, "buy", 2, 3.00, "2026-08-19T13:00:00", "c3"),
        _fill("safe-3", sym, "sell", 2, 2.00, "2026-08-19T13:05:00", "c4"),
    ])
    trips = tmb.reconstruct_round_trips("safe-3", led)
    assert len(trips) == 2
    assert [t["entry_premium"] for t in trips] == [1.00, 3.00]
    assert [t["real_pnl"] for t in trips] == [pytest.approx(100.0), pytest.approx(-200.0)]


def test_manual_fills_are_excluded_from_the_engine_book(tmp_path):
    sym = "SPY260819C00771000"
    manual = _fill("safe-2", sym, "buy", 3, 1.00, "2026-08-19T10:00:00", "m1")
    manual["attribution"] = "manual"
    led = _write_ledger(tmp_path, [manual,
                                   _fill("safe-2", sym, "sell", 3, 2.00, "2026-08-19T10:05:00", "m2")])
    # the buy is manual -> the sell has nothing open -> no fabricated round trip
    assert tmb.reconstruct_round_trips("safe-2", led) == []


# ============================================================ no fabrication
def test_moneyness_is_none_when_spy_at_entry_is_unknown():
    assert tmb.moneyness_label("C", 771.0, None) == (None, None)
    assert tmb.moneyness_label("C", None, 770.5) == (None, None)


@pytest.mark.parametrize("side,strike,spy,expect", [
    ("C", 771.0, 770.6, "ATM"),      # round(770.6) == 771
    ("C", 773.0, 770.6, "OTM+2"),
    ("C", 769.0, 770.6, "ITM-2"),
    ("P", 769.0, 770.6, "OTM+2"),    # puts invert
    ("P", 773.0, 770.6, "ITM-2"),
])
def test_moneyness_sign_convention(side, strike, spy, expect):
    assert tmb.moneyness_label(side, strike, spy)[0] == expect


def test_float_helper_never_fabricates_a_zero():
    assert tmb._f(None) is None
    assert tmb._f("") is None
    assert tmb._f("not-a-number") is None
    assert tmb._f("1.25") == 1.25


def test_no_bars_in_window_yields_no_mae_mfe_rather_than_an_imputed_one():
    """A sub-2-minute hold inside an OPRA print gap: the contract has bars that day, but none
    while the position was held. MAE/MFE must be ABSENT, not interpolated from adjacent bars."""
    bars = [{"ts": dt.datetime(2026, 8, 10, 9, 30), "o": .7, "h": .8, "l": .6, "c": .7},
            {"ts": dt.datetime(2026, 8, 10, 9, 55), "o": .4, "h": .5, "l": .3, "c": .4}]
    out = tmb.path_metrics(bars, dt.datetime(2026, 8, 10, 9, 52, 10),
                           dt.datetime(2026, 8, 10, 9, 53, 6), 0.55)
    assert out["path_status"] == "NO_BARS_IN_WINDOW"
    assert "mae_pct" not in out and "mfe_pct" not in out


# ============================================================ path metrics
def _bars(seq, day=dt.datetime(2026, 8, 19, 10, 0)):
    return [{"ts": day + dt.timedelta(minutes=i), "o": o, "h": h, "l": lo, "c": c}
            for i, (o, h, lo, c) in enumerate(seq)]


def test_mae_mfe_and_first_touch_grid_are_computed_from_the_held_window_only():
    # entry 1.00 at minute 0; held to minute 3. Minute 4 spikes to 5.00 but is AFTER the exit.
    bars = _bars([(1.0, 1.10, 0.95, 1.05),
                  (1.05, 1.30, 1.00, 1.25),
                  (1.25, 1.40, 0.70, 0.80),
                  (0.80, 0.90, 0.75, 0.85),
                  (0.85, 5.00, 0.85, 5.00)])
    out = tmb.path_metrics(bars, dt.datetime(2026, 8, 19, 10, 0),
                           dt.datetime(2026, 8, 19, 10, 3), 1.00)
    assert out["path_status"] == "OK" and out["path_bars"] == 4
    assert out["mfe_premium"] == pytest.approx(0.40)     # 1.40 high at minute 2, NOT the 5.00
    assert out["mfe_minutes"] == 2.0
    assert out["mae_premium"] == pytest.approx(-0.30)    # 0.70 low at minute 2
    assert out["mae_minutes"] == 2.0
    # first touch: -20% (0.80) first traded at minute 2; -50% (0.50) never
    assert out["stop_first_touch_min_pct"]["-20"] == 2.0
    assert out["stop_first_touch_min_pct"]["-50"] is None
    assert out["target_first_touch_min_pct"]["+30"] == 1.0   # 1.30 high at minute 1
    assert out["target_first_touch_min_pct"]["+100"] is None


def test_entry_bar_inclusive_and_exclusive_mae_both_ship_and_can_differ():
    """A stop cannot fire on a print that printed BEFORE the fill. Both variants must exist so
    a downstream stop study picks one explicitly instead of inheriting an unlabelled default."""
    bars = _bars([(1.0, 1.05, 0.50, 1.00),   # entry bar dipped to 0.50 -- possibly pre-fill
                  (1.0, 1.05, 0.90, 0.95)])
    out = tmb.path_metrics(bars, dt.datetime(2026, 8, 19, 10, 0),
                           dt.datetime(2026, 8, 19, 10, 1), 1.00)
    assert out["mae_premium"] == pytest.approx(-0.50)
    assert out["mae_premium_excl_entry_bar"] == pytest.approx(-0.10)


# ============================================================ no look-ahead (C6)
def test_filter_release_scan_reads_only_rows_strictly_before_the_entry():
    ts = dt.datetime(2026, 8, 19, 12, 36)
    rows = [
        {"_ts": ts - dt.timedelta(minutes=3), "action": "SKIP_STALE_TRIGGER"},
        {"_ts": ts - dt.timedelta(minutes=1), "action": "HOLD"},
        {"_ts": ts, "action": "PLACED"},
        {"_ts": ts + dt.timedelta(minutes=1), "action": "SKIP_LATE_ENTRY"},   # FUTURE
    ]
    got = tmb.filters_released_before({"safe": rows}, "safe", ts)
    assert [g["action"] for g in got] == ["SKIP_STALE_TRIGGER"]
    assert got[0]["last_minutes_before"] == 3.0


def test_nearest_core_state_never_reaches_forward_and_respects_the_tolerance():
    ts = dt.datetime(2026, 8, 19, 12, 36)
    future = {"_ts": ts + dt.timedelta(minutes=1), "spy": 999.0}
    stale = {"_ts": ts - dt.timedelta(minutes=30), "spy": 111.0}
    fresh = {"_ts": ts - dt.timedelta(minutes=2), "spy": 770.5}
    assert tmb.nearest_core_state({"safe": [stale, future]}, "safe", ts) is None  # too stale
    got = tmb.nearest_core_state({"safe": [stale, fresh, future]}, "safe", ts)
    assert got["spy"] == 770.5                                                    # never 999.0


# ============================================================ TRAP 2: broker is truth
def test_verify_without_a_broker_check_is_unreconciled(capsys):
    """--no-broker must print UNRECONCILED. A skipped check can never read as a pass."""
    report = {"totals": {"gross": -1805.0, "fees_ex_cat": 134.9, "cat_allocated": 1.08,
                         "net": -1939.9, "net_incl_cat": -1940.98},
              "row_count": 303, "date_range": ["2026-06-26", "2026-08-19"], "trading_days": 35,
              "per_arm": {}, "path_coverage": {"rows_with_option_bars": 302,
                                               "rows_without_option_bars": 1,
                                               "fetch_failures": []},
              "engine_state_coverage": {"order_id_matched": 303, "unmatched": 0,
                                        "market_state_missing": 0, "exit_reason_matched": 298},
              "crosscheck_vs_fills_fifo": {"status": "AGREE", "problems": []}}
    tmb._print_verify(report, None)
    out = capsys.readouterr().out
    assert "UNRECONCILED" in out and "RECONCILED (" not in out.replace("UNRECONCILED", "")


def test_broker_fifo_helper_matches_the_reconstructor_on_the_same_fills():
    fills = [{"symbol": "S1", "side": "buy", "qty": 3, "price": 1.0, "ts": "t1"},
             {"symbol": "S1", "side": "sell", "qty": 2, "price": 2.0, "ts": "t2"},
             {"symbol": "S1", "side": "sell", "qty": 1, "price": 0.5, "ts": "t3"}]
    pnl, trips = tmb.fifo_pnl_over_fills(fills)
    assert trips == 1 and pnl == pytest.approx(150.0)


def test_broker_reconciliation_is_unreconciled_when_credentials_are_unavailable(monkeypatch):
    """Fail LOUD: an unreachable broker is never a silent pass."""
    import fleet_broker as fb
    monkeypatch.setattr(fb, "load_creds", lambda: (_ for _ in ()).throw(FileNotFoundError("no secrets")))
    res = tmb.reconcile_against_broker()
    assert res["verdict"] == "UNRECONCILED" and "secrets" in res["reason"]


# ------------------------------------------------- broker retention window (measured 2026-08-19)
def _stub_broker(monkeypatch, tmp_path, broker_acts, ledger_fills):
    """Offline reconciliation harness: one arm, one account, fully stubbed broker."""
    import broker_fills as bfl
    import fleet_broker as fb
    monkeypatch.setattr(fb, "load_creds", lambda: {"safe-2": {"key": "k", "secret": "s",
                                                              "base_url": "http://stub"}})
    monkeypatch.setattr(bfl, "fetch_fill_activities", lambda *a, **k: broker_acts)
    monkeypatch.setattr(tmb, "_account_map", lambda: {"safe-2": "ACCT1"})
    monkeypatch.setattr(tmb, "ARMS", ("safe-2",))
    monkeypatch.setattr(tmb, "FILLS_LEDGER", _write_ledger(tmp_path, ledger_fills))


def _act(symbol, side, qty, price, ts_utc, aid):
    return {"id": aid, "activity_type": "FILL", "transaction_time": ts_utc,
            "price": str(price), "qty": str(qty), "side": side, "symbol": symbol}


def test_reconciliation_clips_to_the_broker_retained_window_and_flags_the_rest(monkeypatch, tmp_path):
    """Alpaca paper drops activity history older than ~2.5 weeks (measured live 2026-08-19:
    an explicit July query returns ZERO rows). Older ledger legs must be reported as
    UNVERIFIABLE, never quietly counted as agreeing with a broker that has forgotten them."""
    sym = "SPY260819C00771000"
    broker = [_act(sym, "buy", 1, 1.00, "2026-08-19T14:00:00Z", "n1"),
              _act(sym, "sell", 1, 2.00, "2026-08-19T14:30:00Z", "n2")]
    ledger = [  # two OLD legs the broker no longer retains, plus the two it does
        _fill("safe-2", "SPY260701C00751000", "buy", 1, 5.00, "2026-07-01T10:00:00", "o1"),
        _fill("safe-2", "SPY260701C00751000", "sell", 1, 1.00, "2026-07-01T10:30:00", "o2"),
        _fill("safe-2", sym, "buy", 1, 1.00, "2026-08-19T10:00:00", "n1"),
        _fill("safe-2", sym, "sell", 1, 2.00, "2026-08-19T10:30:00", "n2"),
    ]
    _stub_broker(monkeypatch, tmp_path, broker, ledger)
    res = tmb.reconcile_against_broker()
    acct = res["accounts"]["ACCT1"]
    assert acct["status"] == "RECONCILED_IN_WINDOW"
    assert acct["broker_option_legs_in_window"] == 2 == acct["ledger_option_legs_in_window"]
    assert acct["ledger_legs_broker_no_longer_retains"] == 2   # the July pair
    assert acct["broker_fifo_pnl_in_window"] == acct["ledger_fifo_pnl_in_window"] == 100.0
    # the July -$400 must NOT leak into the in-window comparison
    assert acct["ledger_fifo_pnl_in_window"] != -300.0
    assert res["full_history_verifiable"] is False
    assert res["legs_beyond_broker_retention"] == 2
    assert res["verdict_scope"] == "TRAILING_RETENTION_WINDOW_ONLY"


def test_a_real_in_window_disagreement_is_unreconciled(monkeypatch, tmp_path):
    """If the broker and the ledger genuinely disagree inside the retained window, that is a
    FINDING -- the verdict must flip, not be absorbed by the retention caveat."""
    sym = "SPY260819C00771000"
    broker = [_act(sym, "buy", 1, 1.00, "2026-08-19T14:00:00Z", "n1"),
              _act(sym, "sell", 1, 2.00, "2026-08-19T14:30:00Z", "n2"),
              _act(sym, "buy", 1, 1.00, "2026-08-19T15:00:00Z", "n3")]   # ledger never saw n3
    ledger = [_fill("safe-2", sym, "buy", 1, 1.00, "2026-08-19T10:00:00", "n1"),
              _fill("safe-2", sym, "sell", 1, 2.00, "2026-08-19T10:30:00", "n2")]
    _stub_broker(monkeypatch, tmp_path, broker, ledger)
    res = tmb.reconcile_against_broker()
    assert res["verdict"] == "UNRECONCILED"
    assert res["accounts"]["ACCT1"]["status"] == "MISMATCH"
    assert res["accounts"]["ACCT1"]["in_broker_not_in_ledger"] == 1


def test_et_date_is_derived_in_eastern_not_local_time():
    """The box runs Mountain time -- ET = local + 2. A late-afternoon ET fill is the SAME ET
    day even though its UTC timestamp has already rolled over."""
    assert tmb._et_date_of("2026-08-20T00:30:00Z") == "2026-08-19"   # 20:30 ET on the 19th
    assert tmb._et_date_of("2026-08-19T13:30:00Z") == "2026-08-19"   # 09:30 ET open
    assert tmb._et_date_of("garbage") is None


# ============================================================ scope
def test_retired_safe_1_is_excluded_and_the_reason_is_recorded():
    """safe-1 shares PA3POKNV46VG with safe-2 -- including it double-counts one account."""
    assert "safe-1" not in tmb.ARMS
    assert "safe-1" in tmb.EXCLUDED_ARMS
    assert len(tmb.ARMS) == 5


def test_occ_strike_parsing():
    assert tmb.occ_strike("SPY260819C00771000") == 771.0
    assert tmb.occ_strike("SPY260819P00770500") == 770.5
    assert tmb.occ_strike("garbage") is None
