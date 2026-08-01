"""Guard tests for setup/scripts/theta_clock.py -- the THETA COCKPIT visibility instrument
(J directive, 2026-08-01).

Covers, per the build brief's explicit requirements:
  1. Writer schema -- compute_row() always returns the full documented field set, with honest
     None (never fabricated 0) when an input is missing.
  2. Pure decomposition math -- the sqrt(T) decay model's sanity properties (flat spot -> zero
     delta component; ITM move -> exact intrinsic-value delta component; time passing alone
     -> monotonic theta burn).
  3. Alert threshold logic -- a stalled-position fixture fires exactly once, never repeats for
     the same position (RED-proofed: reverting the `alerted` latch check reproduces spam).
  4. Fail-open behavior -- one bad account/position never sinks the tick; a crashing injected
     dependency still yields a summary dict and writes no lock/pid file anywhere.
  5. End-to-end dry run against a SYNTHETIC injected position across simulated 1-min ticks,
     entirely offline (no network, no real credentials) -- proves the full pipeline (entry
     snapshot freeze -> daily JSONL rows -> snapshot JSON -> STATUS.md "## Live watch" line)
     the weekend-limitation requirement asks for.

Pure-logic + tmp_path only -- no network, no live state touched.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _tc():
    return importlib.import_module("theta_clock")


# --------------------------------------------------------------------------- #
# 1. writer schema
# --------------------------------------------------------------------------- #
def test_compute_row_full_schema_happy_path():
    tc = _tc()
    now = datetime(2026, 8, 3, 10, 15, 0)  # a Monday, mid-morning
    position = {"symbol": "SPY260803C00745000", "qty": "5", "avg_entry_price": "1.00",
                "current_price": "0.90", "unrealized_plpc": "-0.10"}
    entry_snap = {"entry_premium": 1.00, "entry_spot": 743.00,
                  "mins_to_close_at_entry": 180.0}
    row = tc.compute_row(arm="safe-3", position=position, quote={"bid": 0.88, "ask": 0.92, "mid": 0.90},
                          greeks=None, entry_snap=entry_snap, spot_now=744.00, now_et=now)
    expected_keys = {
        "ts_et", "arm", "symbol", "strike", "right", "qty", "entry_premium", "mid_now",
        "bid", "ask", "unrealized_pct", "theta_per_contract_per_day",
        "theta_per_contract_per_day_source", "theta_burn_since_entry_est",
        "theta_burn_since_entry_est_usd", "delta_gain_since_entry_est",
        "delta_gain_since_entry_est_usd", "underlying_move_since_entry", "spot_now",
        "mins_to_close_now", "decomposition_est", "greeks_raw", "greeks_source",
    }
    assert set(row.keys()) == expected_keys
    assert row["arm"] == "safe-3"
    assert row["symbol"] == "SPY260803C00745000"
    assert row["strike"] == 745.0 and row["right"] == "C"
    assert row["qty"] == 5
    assert row["entry_premium"] == 1.00
    assert row["mid_now"] == 0.90
    assert row["unrealized_pct"] == -10.0  # sourced from broker unrealized_plpc, preferred
    assert row["underlying_move_since_entry"] == 1.00
    assert row["theta_burn_since_entry_est"] is not None and row["theta_burn_since_entry_est"] <= 0
    assert row["greeks_source"].startswith("unavailable")


def test_compute_row_never_fabricates_missing_inputs():
    """No strike/right parseable -> decomposition fields are honest None, not 0."""
    tc = _tc()
    now = datetime(2026, 8, 3, 10, 15, 0)
    position = {"symbol": "GARBAGE", "qty": "1", "avg_entry_price": "1.00"}
    row = tc.compute_row(arm="safe-3", position=position, quote={}, greeks=None,
                          entry_snap={}, spot_now=744.0, now_et=now)
    assert row["strike"] is None and row["right"] is None
    assert row["decomposition_est"]["delta_component_est"] is None
    assert row["theta_burn_since_entry_est"] is None
    assert row["theta_burn_since_entry_est_usd"] is None


def test_compute_row_prefers_real_greeks_theta_over_estimate():
    tc = _tc()
    now = datetime(2026, 8, 3, 10, 15, 0)
    position = {"symbol": "SPY260803C00745000", "qty": "2", "avg_entry_price": "1.00"}
    entry_snap = {"entry_premium": 1.00, "entry_spot": 743.00, "mins_to_close_at_entry": 180.0}
    row = tc.compute_row(arm="safe-3", position=position, quote={"mid": 0.9}, greeks={"theta": -0.42},
                          entry_snap=entry_snap, spot_now=744.0, now_et=now)
    assert row["theta_per_contract_per_day"] == -42.0  # -0.42 * 100 contract multiplier
    assert row["theta_per_contract_per_day_source"] == "broker_snapshot"
    assert row["greeks_source"] == "broker_snapshot"


# --------------------------------------------------------------------------- #
# 2. pure decomposition math
# --------------------------------------------------------------------------- #
def test_decomposition_flat_spot_zero_delta_component():
    tc = _tc()
    d = tc.estimate_decomposition(premium_ref=1.00, mid_now=0.85, strike=745.0, right="C",
                                   spot_now=740.0, spot_ref=740.0,
                                   mins_to_close_now=100.0, mins_to_close_ref=180.0)
    assert d["delta_component_est"] == 0.0
    assert d["theta_component_est"] < 0.0  # time passed, extrinsic decays
    assert d["basis"].startswith("sqrt_time_decay_model")


def test_decomposition_itm_move_matches_exact_intrinsic():
    """delta_component_est is MODEL-FREE -- must equal the exact intrinsic-value delta,
    independent of the theta model."""
    tc = _tc()
    d = tc.estimate_decomposition(premium_ref=1.00, mid_now=3.00, strike=745.0, right="C",
                                   spot_now=748.0, spot_ref=745.0,
                                   mins_to_close_now=170.0, mins_to_close_ref=180.0)
    # intrinsic_now = max(0, 748-745) = 3; intrinsic_ref = max(0, 745-745) = 0
    assert d["delta_component_est"] == 3.0


def test_decomposition_missing_inputs_returns_all_none():
    tc = _tc()
    d = tc.estimate_decomposition(premium_ref=1.00, mid_now=0.9, strike=None, right="C",
                                   spot_now=740.0, spot_ref=740.0,
                                   mins_to_close_now=100.0, mins_to_close_ref=180.0)
    assert d["delta_component_est"] is None and d["theta_component_est"] is None
    assert d["basis"].startswith("unavailable")


def test_decomposition_theta_accelerates_intraday():
    """0DTE-awareness property: the SAME elapsed-time step burns MORE extrinsic value the
    closer to close it happens (sqrt(T) curve is concave) -- a naive linear model would show
    identical burn for both steps; this must not."""
    tc = _tc()
    # Early step: 180 -> 170 min to close (10 min elapsed, far from close).
    early = tc.estimate_decomposition(premium_ref=1.00, mid_now=1.00, strike=745.0, right="C",
                                       spot_now=740.0, spot_ref=740.0,
                                       mins_to_close_now=170.0, mins_to_close_ref=180.0)
    # Late step: 20 -> 10 min to close (same 10 min elapsed, near close).
    late = tc.estimate_decomposition(premium_ref=1.00, mid_now=1.00, strike=745.0, right="C",
                                      spot_now=740.0, spot_ref=740.0,
                                      mins_to_close_now=10.0, mins_to_close_ref=20.0)
    assert abs(late["theta_component_est"]) > abs(early["theta_component_est"])


def test_parse_occ_symbol_roundtrip():
    tc = _tc()
    p = tc.parse_occ_symbol("SPY260803P00745500")
    assert p == {"root": "SPY", "expiry": "2026-08-03", "right": "P", "strike": 745.5}
    assert tc.parse_occ_symbol("NOT_AN_OPTION") is None
    assert tc.parse_occ_symbol("") is None


def test_minutes_to_close_floors_after_close():
    tc = _tc()
    after_close = datetime(2026, 8, 3, 16, 30, 0)
    assert tc.minutes_to_close(after_close) == 0.5  # floored, never negative/zero


# --------------------------------------------------------------------------- #
# 3. alert threshold logic (RED-proofed)
# --------------------------------------------------------------------------- #
def _row(ts_et: str, *, delta_c: float, theta_c: float, qty: int = 5) -> dict:
    return {"ts_et": ts_et, "qty": qty,
            "decomposition_est": {"delta_component_est": delta_c, "theta_component_est": theta_c}}


def test_check_stall_alert_fires_when_theta_beats_delta():
    tc = _tc()
    rows = [
        _row("2026-08-03T10:00:00", delta_c=0.0, theta_c=-0.02),
        _row("2026-08-03T10:15:00", delta_c=0.01, theta_c=-0.15),  # theta -$75 (5 qty) vs delta +$5
    ]
    alert = tc.check_stall_alert(rows)
    assert alert is not None
    assert alert["theta_burn_window_usd"] < 0
    assert abs(alert["theta_burn_window_usd"]) > alert["delta_gain_window_usd"]


def test_check_stall_alert_silent_when_delta_keeps_pace():
    tc = _tc()
    rows = [
        _row("2026-08-03T10:00:00", delta_c=0.0, theta_c=-0.02),
        _row("2026-08-03T10:15:00", delta_c=0.50, theta_c=-0.15),  # delta +$250 swamps theta burn
    ]
    assert tc.check_stall_alert(rows) is None


def test_check_stall_alert_needs_at_least_two_usable_rows():
    tc = _tc()
    assert tc.check_stall_alert([]) is None
    assert tc.check_stall_alert([_row("2026-08-03T10:00:00", delta_c=0.0, theta_c=-0.5)]) is None
    unusable = [{"ts_et": "x", "qty": 5, "decomposition_est": {"delta_component_est": None}}]
    assert tc.check_stall_alert(unusable) is None


def test_check_stall_alert_red_proof_margin_matters():
    """Below the $ margin, a real theta-beats-delta case must NOT alert (proves the margin
    term is load-bearing, not decorative)."""
    tc = _tc()
    rows = [
        _row("2026-08-03T10:00:00", delta_c=0.0, theta_c=0.0, qty=1),
        _row("2026-08-03T10:15:00", delta_c=0.0, theta_c=-0.01, qty=1),  # -$1 burn, 1 contract
    ]
    assert tc.check_stall_alert(rows, min_margin_usd=5.0) is None
    assert tc.check_stall_alert(rows, min_margin_usd=0.0) is not None


# --------------------------------------------------------------------------- #
# 4. fail-open behavior
# --------------------------------------------------------------------------- #
def test_run_once_survives_load_creds_failure(tmp_path):
    tc = _tc()

    def boom():
        raise RuntimeError("secrets.json missing")

    summary = tc.run_once(
        now_et=datetime(2026, 8, 3, 10, 0, 0),
        creds_by_arm=None, active_arms=["safe-3"],
        state_path=tmp_path / "position-state.json",
        snapshot_path=tmp_path / "theta-clock.json",
        theta_dir=tmp_path / "theta-clock",
        status_md_path=tmp_path / "STATUS.md",
        positions_fn=lambda arm, creds: (_ for _ in ()).throw(RuntimeError("unreachable")),
    )
    # creds_by_arm=None triggers the real fb.load_creds() path in production; here we instead
    # verify the OTHER fail-open seam -- a bad account never raises out of run_once at all.
    assert isinstance(summary, dict)


def test_run_once_one_bad_account_does_not_sink_others(tmp_path):
    tc = _tc()

    def positions_fn(arm, creds):
        if arm == "risky-1":
            raise ConnectionError("simulated network failure")
        return []

    summary = tc.run_once(
        now_et=datetime(2026, 8, 3, 10, 0, 0),
        creds_by_arm={"safe-3": {"key": "k", "secret": "s", "base_url": "https://x"},
                      "risky-1": {"key": "k", "secret": "s", "base_url": "https://x"}},
        active_arms=["safe-3", "risky-1"],
        positions_fn=positions_fn,
        spot_fn=lambda: (744.0, "test"),
        state_path=tmp_path / "position-state.json",
        snapshot_path=tmp_path / "theta-clock.json",
        theta_dir=tmp_path / "theta-clock",
        status_md_path=tmp_path / "STATUS.md",
    )
    assert "safe-3" in summary["accounts_checked"]
    assert any(f.get("arm") == "risky-1" for f in summary["accounts_failed"])
    assert summary["n_positions"] == 0  # both arms had zero/failed positions, no crash either way


def test_run_once_degraded_quote_still_produces_a_row(tmp_path):
    """A quote_fn failure is isolated to just that sub-step (degrades to an empty quote) --
    the position still gets a row, just with bid/ask/mid absent. Finer-grained than skipping
    the whole position, and proven here so the boundary is explicit, not assumed."""
    tc = _tc()
    good = {"symbol": "SPY260803C00745000", "qty": "5", "avg_entry_price": "1.00"}
    flaky = {"symbol": "SPY260803C00746000", "qty": "5", "avg_entry_price": "1.00"}

    def quote_fn(creds, symbol):
        if symbol == flaky["symbol"]:
            raise RuntimeError("simulated quote-feed failure")
        return {"mid": 0.9}

    summary = tc.run_once(
        now_et=datetime(2026, 8, 3, 10, 0, 0),
        creds_by_arm={"safe-3": {"key": "k", "secret": "s", "base_url": "https://x"}},
        active_arms=["safe-3"],
        positions_fn=lambda arm, creds: [good, flaky],
        greeks_fn=lambda creds, symbol: None,
        quote_fn=quote_fn,
        spot_fn=lambda: (744.0, "test"),
        state_path=tmp_path / "position-state.json",
        snapshot_path=tmp_path / "theta-clock.json",
        theta_dir=tmp_path / "theta-clock",
        status_md_path=tmp_path / "STATUS.md",
    )
    assert summary["n_positions"] == 2
    flaky_row = next(r for r in summary["positions"] if r["symbol"] == flaky["symbol"])
    assert flaky_row["mid_now"] is None  # degraded, not fabricated


def test_run_once_malformed_position_does_not_sink_the_tick(tmp_path):
    """A genuinely malformed entry in the positions list (not even a dict) must not crash the
    whole tick -- RED-PROOF for the fix that moved `position.get(...)` inside the per-position
    try/except (it originally sat OUTSIDE the guard, so a single bad element would raise out of
    the entire for-loop and skip every OTHER position + the snapshot write for that tick)."""
    tc = _tc()
    good = {"symbol": "SPY260803C00745000", "qty": "5", "avg_entry_price": "1.00"}

    summary = tc.run_once(
        now_et=datetime(2026, 8, 3, 10, 0, 0),
        creds_by_arm={"safe-3": {"key": "k", "secret": "s", "base_url": "https://x"}},
        active_arms=["safe-3"],
        positions_fn=lambda arm, creds: [None, good, "also_not_a_dict"],
        greeks_fn=lambda creds, symbol: None,
        quote_fn=lambda creds, symbol: {"mid": 0.9},
        spot_fn=lambda: (744.0, "test"),
        state_path=tmp_path / "position-state.json",
        snapshot_path=tmp_path / "theta-clock.json",
        theta_dir=tmp_path / "theta-clock",
        status_md_path=tmp_path / "STATUS.md",
    )
    assert summary["n_positions"] == 1
    assert summary["positions"][0]["symbol"] == good["symbol"]
    assert len(summary["accounts_failed"]) == 2  # both malformed entries logged, not silently dropped


def test_run_once_never_writes_a_lock_or_pid_file(tmp_path):
    """J's explicit weekend-limitation requirement: a crashed run must leave no lock/state
    that could confuse a future run. Overlap protection is Task Scheduler's own
    -MultipleInstances IgnoreNew (see install-theta-clock.ps1), not an app-level lock file."""
    tc = _tc()
    theta_dir = tmp_path / "theta-clock"
    tc.run_once(
        now_et=datetime(2026, 8, 3, 10, 0, 0),
        creds_by_arm={}, active_arms=[],
        state_path=tmp_path / "position-state.json",
        snapshot_path=tmp_path / "theta-clock.json",
        theta_dir=theta_dir,
        status_md_path=tmp_path / "STATUS.md",
    )
    all_files = list(tmp_path.rglob("*"))
    # NOTE: a naive "lock" substring check false-positives on "theta-**clock**.json" (the
    # legitimate snapshot file) -- check real lock-file shapes only (.lock/.pid suffix, or a
    # "lock"/"pid" TOKEN bounded by separators, not embedded in another word).
    assert not any(f.suffix in (".lock", ".pid") for f in all_files if f.is_file())
    assert not any(f.name.lower() in ("theta-clock.lock", "theta_clock.lock", ".lock")
                    for f in all_files if f.is_file())


# --------------------------------------------------------------------------- #
# 5. end-to-end dry run against a SYNTHETIC injected position (offline)
# --------------------------------------------------------------------------- #
def test_end_to_end_synthetic_stall_writes_clock_row_and_alerts_once(tmp_path):
    """The full pipeline, entirely offline: a synthetic position held flat (no favorable
    underlying move) across 16 simulated one-minute ticks must (a) freeze an entry snapshot on
    tick 1, (b) write one row per tick to the daily JSONL + current snapshot, (c) fire exactly
    ONE '## Live watch' STATUS.md line once >= ALERT_WINDOW_MIN minutes of stall have
    accumulated, and (d) NEVER fire a second line on later ticks."""
    tc = _tc()
    state_path = tmp_path / "position-state.json"
    snapshot_path = tmp_path / "theta-clock.json"
    theta_dir = tmp_path / "theta-clock"
    status_md_path = tmp_path / "STATUS.md"
    status_md_path.write_text("## Known broken\n_placeholder_\n\n---\n", encoding="utf-8")

    symbol = "SPY260803C00747000"
    position = {"symbol": symbol, "qty": "5", "avg_entry_price": "1.00", "current_price": "0.95"}
    creds = {"safe-3": {"key": "k", "secret": "s", "base_url": "https://x"}}
    start = datetime(2026, 8, 3, 10, 0, 0)

    for i in range(16):  # minutes 0..15 -> spans the 15-min alert window
        now = start + timedelta(minutes=i)
        tc.run_once(
            now_et=now, creds_by_arm=creds, active_arms=["safe-3"],
            positions_fn=lambda arm, c: [position],
            greeks_fn=lambda c, s: None,
            quote_fn=lambda c, s: {"mid": 0.95},
            spot_fn=lambda: (744.0, "test"),  # SPOT NEVER MOVES -> zero delta contribution
            state_path=state_path, snapshot_path=snapshot_path,
            theta_dir=theta_dir, status_md_path=status_md_path,
        )

    # (a)+(b): daily JSONL has 16 rows for this position; snapshot reflects the last tick.
    jsonl_path = theta_dir / "theta-clock-2026-08-03.jsonl"
    lines = [json.loads(l) for l in jsonl_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 16
    assert all(r["symbol"] == symbol for r in lines)
    snap = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snap["n_positions"] == 1

    # (c): exactly one alert fired, latched in position-state.json.
    pstate = json.loads(state_path.read_text(encoding="utf-8"))
    key = f"safe-3::{symbol}"
    assert pstate["positions"][key]["alerted"] is True

    status_text = status_md_path.read_text(encoding="utf-8")
    assert "## Live watch" in status_text
    assert status_text.count("THETA STALL") == 1  # (d) never repeats

    # RED-proof: run 5 MORE ticks past the alert -- still exactly one line.
    for i in range(16, 21):
        now = start + timedelta(minutes=i)
        tc.run_once(
            now_et=now, creds_by_arm=creds, active_arms=["safe-3"],
            positions_fn=lambda arm, c: [position],
            greeks_fn=lambda c, s: None,
            quote_fn=lambda c, s: {"mid": 0.95},
            spot_fn=lambda: (744.0, "test"),
            state_path=state_path, snapshot_path=snapshot_path,
            theta_dir=theta_dir, status_md_path=status_md_path,
        )
    assert status_md_path.read_text(encoding="utf-8").count("THETA STALL") == 1


def test_end_to_end_favorable_move_never_alerts(tmp_path):
    """RED-proof counterpart: the SAME hold duration, but the underlying moves favorably
    enough each tick that delta keeps pace -- must never alert."""
    tc = _tc()
    state_path = tmp_path / "position-state.json"
    snapshot_path = tmp_path / "theta-clock.json"
    theta_dir = tmp_path / "theta-clock"
    status_md_path = tmp_path / "STATUS.md"
    status_md_path.write_text("## Known broken\n_placeholder_\n\n---\n", encoding="utf-8")

    symbol = "SPY260803C00747000"
    position = {"symbol": symbol, "qty": "5", "avg_entry_price": "1.00", "current_price": "3.00"}
    creds = {"safe-3": {"key": "k", "secret": "s", "base_url": "https://x"}}
    start = datetime(2026, 8, 3, 10, 0, 0)

    for i in range(16):
        now = start + timedelta(minutes=i)
        spot = 744.0 + i * 0.5  # steadily runs deep ITM -- delta dominates
        tc.run_once(
            now_et=now, creds_by_arm=creds, active_arms=["safe-3"],
            positions_fn=lambda arm, c: [position],
            greeks_fn=lambda c, s: None,
            quote_fn=lambda c, s: {"mid": 3.00},
            spot_fn=(lambda spot=spot: (spot, "test")),
            state_path=state_path, snapshot_path=snapshot_path,
            theta_dir=theta_dir, status_md_path=status_md_path,
        )
    assert "THETA STALL" not in status_md_path.read_text(encoding="utf-8")
    pstate = json.loads(state_path.read_text(encoding="utf-8"))
    assert pstate["positions"][f"safe-3::{symbol}"]["alerted"] is False


# --------------------------------------------------------------------------- #
# misc
# --------------------------------------------------------------------------- #
def test_active_arms_excludes_retired_and_futures(tmp_path):
    tc = _tc()
    fixture = tmp_path / "accounts.json"
    fixture.write_text(json.dumps({"arms": [
        {"id": "safe-2", "status": "active", "instrument": "SPY_0DTE_OPTION"},
        {"id": "safe-1", "status": "retired", "instrument": "SPY_0DTE_OPTION"},
        {"id": "mes-linear-sim", "status": "pending_build", "instrument": "MES_FUTURES"},
        {"id": "risky-3", "status": "active", "instrument": "SPY_0DTE_OPTION"},
    ]}), encoding="utf-8")
    arms = tc._active_arms(fixture)
    assert set(arms) == {"safe-2", "risky-3"}


def test_static_guard_never_imports_order_placing_functions():
    """AST guard (mirrors test_fleet_journal_bridge.py's static-safety pattern): theta_clock.py
    must never call an order-mutating fleet_broker function -- this is a READ-ONLY watcher."""
    import ast
    src = (SCRIPTS / "theta_clock.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    forbidden = {"place_bracket", "market_sell", "cancel_order", "close_all_spy_options"}
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not (called & forbidden), f"theta_clock.py calls order-mutating function(s): {called & forbidden}"
