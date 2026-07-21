"""RED-proof acceptance tests for setup/scripts/dojo/sim_executor.py (DOJO Phase 1b build,
DOJO-ARCHITECTURE-DECISION.md's sim_executor.py contract).

Proves: `arm_directive` fills a J-directed trade from historical option data and persists
one DojoPosition per targeted arm; `advance_session`, called bar-by-bar exactly as
session.py's cmd_step does, walks each open position via the REAL exit_manager decision
core (backtest/lib/exit_manager_walk.py) and fires the CORRECT exit -- a position built to
double in premium actually TP1s, a position built to crater actually stops out. Option
data is monkeypatched to a small, hand-scripted bar series (deterministic, no dependency
on which historical dates happen to have real OPRA cache coverage); accounts.json /
strategies.py / exit_manager.py are all exercised FOR REAL (only the option-bar and SPY-bar
data sources are faked), so this genuinely proves sim_executor's OWN wiring, not a mock of
the exit mechanism itself.

A third test proves the BS-synthetic fallback path (never OPRA-mocked) fires and is
FLAGGED (price_source="bs_synthetic", is_synthetic=True) when no OPRA cache exists for the
contract -- per Free-Kitchen-Plan-B doctrine, never silent.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_dojo_sim_executor.py -v
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (ROOT / "setup" / "scripts", ROOT):
    _ap = str(_p)
    if _ap not in sys.path:
        sys.path.insert(0, _ap)

from dojo import sim_executor  # noqa: E402

# Captured BEFORE the autouse fixture below ever patches the module attribute -- the one
# test that wants the REAL fallback chain (test_bs_synthetic_fallback_used_and_flagged_...)
# restores this exact original function, not a re-import of an already-monkeypatched module.
_REAL_LOAD_OPTION_SERIES = sim_executor._load_option_series


# =====================================================================================
# fixtures -- hand-scripted option bar series, deterministic, no real-cache dependency
# =====================================================================================
def _bars(rows: list[tuple[str, float]], date_str: str = "2026-07-17") -> pd.DataFrame:
    """rows = [(HH:MM, price), ...] -- flat OHLC=price bars (point-sample convention
    matches exit_manager_walk's own best=worst=bar.open reads, so a flat bar is fully
    deterministic: no ambiguity from intrabar high/low)."""
    out = []
    for hhmm, px in rows:
        ts = datetime.fromisoformat(f"{date_str}T{hhmm}:00")
        out.append({"timestamp_et": ts, "open": px, "high": px, "low": px, "close": px,
                     "volume": 10, "vwap": px, "trade_count": 1})
    return pd.DataFrame(out)


# Entry 1.00 @ 09:30, then 09:40 doubles to 2.10 -- crosses ribbon_ride's tp1 level
# (entry * (1 + tp1_premium_pct=1.0) = 2.00) with room to spare.
CALL_BARS = _bars([("09:30", 1.00), ("09:35", 1.10), ("09:40", 2.10), ("09:45", 2.05)])

# Entry 1.00 @ 09:30, then 09:40 craters to 0.70 -- crosses the premium stop level
# (entry * (1 + premium_stop_pct=-0.20) = 0.80).
PUT_BARS = _bars([("09:30", 1.00), ("09:35", 0.95), ("09:40", 0.70), ("09:45", 0.65)])

SPY_FIXTURE = _bars([("09:30", 550.0), ("09:35", 550.2), ("09:40", 550.1), ("09:45", 550.3)])


def _fake_option_series(symbol, side, strike, trade_date, spy_df):
    bars = CALL_BARS if side == "C" else PUT_BARS
    return bars.copy(), "opra_5m", False


def _fake_spy_loader(trade_date):
    return SPY_FIXTURE.copy()


@pytest.fixture(autouse=True)
def _patch_data_sources(monkeypatch):
    monkeypatch.setattr(sim_executor, "_load_option_series", _fake_option_series)
    monkeypatch.setattr(sim_executor, "_load_spy_5m_for_date", _fake_spy_loader)


def _directive(**overrides) -> dict:
    base = {
        "id": "test-directive", "issued_et": "2026-07-17T09:29:00",
        "cursor_et": "2026-07-17T09:30:00", "arms": ["safe"], "side": "C",
        "trigger": {"type": "level_reclaim_confirmed_close"}, "invalidation": {},
        "exits": {}, "sizing": {}, "note": "test", "dojo": True,
    }
    base.update(overrides)
    return base


def _load_positions(session_id: str, dojo_dir: Path) -> dict:
    return sim_executor._load_positions(session_id, dojo_dir)


# =====================================================================================
# 1. arm_directive fills a position per targeted arm
# =====================================================================================
def test_arm_directive_creates_one_open_position_per_arm(tmp_path):
    d = _directive(id="d-multi", arms=["safe", "bold"], side="C")
    sim_executor.arm_directive("sess-1", d, dojo_dir=tmp_path)
    positions = _load_positions("sess-1", tmp_path)
    assert set(positions) == {"d-multi-safe", "d-multi-bold"}
    for pid in ("d-multi-safe", "d-multi-bold"):
        pos = positions[pid]
        assert pos["status"] == "OPEN"
        assert pos["entry_premium"] == pytest.approx(1.00, abs=1e-6)
        assert pos["price_source"] == "opra_5m"
        assert pos["is_synthetic"] is False
        assert pos["qty"] == 3  # DEFAULT_MIN_CONTRACTS (no sizing override)
    assert positions["d-multi-safe"]["arm"] == "safe"
    assert positions["d-multi-safe"]["accounts_arm_id"] == "safe-2"
    assert positions["d-multi-bold"]["accounts_arm_id"] == "bold-2"


def test_arm_directive_resolves_exit_shape_from_ribbon_ride_registry(tmp_path):
    d = _directive(id="d-shape", arms=["safe"], side="C")
    sim_executor.arm_directive("sess-shape", d, dojo_dir=tmp_path)
    pos = _load_positions("sess-shape", tmp_path)["d-shape-safe"]
    # RIBBON_RIDE.exit.to_dict() verbatim (safe-2's accounts.json params_patch is {} --
    # no exit_patch to merge) -- proves the registry+account merge actually ran.
    assert pos["exit_shape"]["premium_stop_pct"] == -0.20
    assert pos["exit_shape"]["tp1_premium_pct"] == 1.0
    assert pos["exit_shape"]["tp1_qty_fraction"] == 0.667


def test_arm_directive_unknown_arm_records_error_not_crash(tmp_path):
    d = _directive(id="d-bad", arms=["safe", "not-a-real-arm"], side="C")
    sim_executor.arm_directive("sess-bad", d, dojo_dir=tmp_path)  # must not raise
    positions = _load_positions("sess-bad", tmp_path)
    assert positions["d-bad-safe"]["status"] == "OPEN"  # the good arm still filled
    assert positions["d-bad-not-a-real-arm"]["status"] == "ERROR"
    assert "unknown arm id" in positions["d-bad-not-a-real-arm"]["note"]


# =====================================================================================
# 2. RED-PROOF: TP1 fires when it should
# =====================================================================================
def test_advance_session_fires_tp1_when_premium_doubles(tmp_path):
    d = _directive(id="d-tp1", arms=["safe"], side="C")
    sim_executor.arm_directive("sess-tp1", d, dojo_dir=tmp_path)

    events_35 = sim_executor.advance_session(
        "sess-tp1", datetime.fromisoformat("2026-07-17T09:35:00"), SPY_FIXTURE, dojo_dir=tmp_path)
    assert events_35 == []  # 1.10 crosses neither the 0.80 stop nor the 2.00 tp1 level

    events_40 = sim_executor.advance_session(
        "sess-tp1", datetime.fromisoformat("2026-07-17T09:40:00"), SPY_FIXTURE, dojo_dir=tmp_path)
    tp1_events = [e for e in events_40 if e.get("stage") == "tp1"]
    assert tp1_events, f"expected a tp1 event at 09:40, got {events_40}"
    ev = tp1_events[0]
    assert ev["kind"] == "SELL_PARTIAL"
    assert ev["qty"] == 2  # int(3 * tp1_qty_fraction=0.667) == 2
    assert ev["fill_price"] == pytest.approx(2.00, abs=1e-6)  # entry * (1 + tp1_premium_pct)
    assert ev["leg_pnl"] == pytest.approx(200.0, abs=1e-6)

    pos = _load_positions("sess-tp1", tmp_path)["d-tp1-safe"]
    assert pos["status"] == "OPEN"  # runner (1 contract) still open post-TP1
    assert pos["open_qty"] == 1
    assert pos["realized_pnl"] == pytest.approx(200.0, abs=1e-6)


# =====================================================================================
# 3. RED-PROOF: premium stop fires when it should
# =====================================================================================
def test_advance_session_fires_premium_stop_when_premium_craters(tmp_path):
    d = _directive(id="d-stop", arms=["bold"], side="P")
    sim_executor.arm_directive("sess-stop", d, dojo_dir=tmp_path)

    events_35 = sim_executor.advance_session(
        "sess-stop", datetime.fromisoformat("2026-07-17T09:35:00"), SPY_FIXTURE, dojo_dir=tmp_path)
    assert events_35 == []  # 0.95 doesn't cross the 0.80 stop level yet

    events_40 = sim_executor.advance_session(
        "sess-stop", datetime.fromisoformat("2026-07-17T09:40:00"), SPY_FIXTURE, dojo_dir=tmp_path)
    stop_events = [e for e in events_40 if e.get("stage") == "premium_stop"]
    assert stop_events, f"expected a premium_stop event at 09:40, got {events_40}"
    ev = stop_events[0]
    assert ev["kind"] == "SELL_ALL"
    assert ev["qty"] == 3  # entire position -- pre-TP1 hard stop applies to ALL units
    assert ev["fill_price"] == pytest.approx(0.80, abs=1e-6)  # entry * (1 + premium_stop_pct)
    assert ev["leg_pnl"] == pytest.approx(-60.0, abs=1e-6)

    closed = [e for e in events_40 if e.get("kind") == "POSITION_CLOSED"]
    assert closed, f"expected a POSITION_CLOSED event once SELL_ALL empties the position: {events_40}"

    pos = _load_positions("sess-stop", tmp_path)["d-stop-bold"]
    assert pos["status"] == "CLOSED"
    assert pos["open_qty"] == 0
    assert pos["exit_reason"] and "premium_stop" in pos["exit_reason"]
    assert pos["realized_pnl"] == pytest.approx(-60.0, abs=1e-6)


def test_advance_session_never_force_closes_on_a_truncated_incremental_step(tmp_path):
    """The load-bearing anti-regression case for this module's core design decision (see
    its own docstring): walk_exit_manager force-closes at the last bar of whatever opt_df
    it's given ("data_exhausted_force_close") when nothing else resolved -- advance_session
    must ALWAYS strip that phantom leg, or every open position would incorrectly close on
    its very first tick."""
    d = _directive(id="d-noforce", arms=["safe"], side="C")
    sim_executor.arm_directive("sess-noforce", d, dojo_dir=tmp_path)

    events = sim_executor.advance_session(
        "sess-noforce", datetime.fromisoformat("2026-07-17T09:35:00"), SPY_FIXTURE, dojo_dir=tmp_path)
    assert events == []
    pos = _load_positions("sess-noforce", tmp_path)["d-noforce-safe"]
    assert pos["status"] == "OPEN"  # NOT force-closed just because the fed series ended here
    assert pos["realized_pnl"] == 0.0


# =====================================================================================
# 4. BS-synthetic fallback -- flagged, never silent
# =====================================================================================
def test_bs_synthetic_fallback_used_and_flagged_when_no_opra_cache(tmp_path, monkeypatch):
    # Undo the autouse _load_option_series patch for THIS test only -- exercise the real
    # fallback chain (real load_contract_bars miss -> real _synthesize_option_bars ->
    # real backtest/lib/pricing.py Black-Scholes). Only the SPY spot loader stays faked
    # (a real spy_5m cache file for this fictional date doesn't exist either).
    monkeypatch.setattr(sim_executor, "_load_option_series", _REAL_LOAD_OPTION_SERIES)

    fictional_spy = _bars([("09:30", 550.0), ("09:35", 550.1)], date_str="2020-01-01")
    monkeypatch.setattr(sim_executor, "_load_spy_5m_for_date", lambda trade_date: fictional_spy.copy())

    d = _directive(id="d-synth", arms=["safe"], side="C", cursor_et="2020-01-01T09:30:00")
    sim_executor.arm_directive("sess-synth", d, dojo_dir=tmp_path)
    pos = _load_positions("sess-synth", tmp_path)["d-synth-safe"]

    assert pos["price_source"] == "bs_synthetic"
    assert pos["is_synthetic"] is True
    assert pos["status"] == "OPEN"
    assert pos["entry_premium"] > 0.0
    assert "no accounts.json arm" not in (pos.get("note") or "")
