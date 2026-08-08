"""Guards for backtest/tools/postfix_gate_costing.py -- POSTFIX-GATE-COSTING-UNSOUND-REPLAY
fix (2026-08-08 night, filed the same session gate_expiry_check.py was rewired off
lib.simulator_real.simulate_trade_real, commit 97a2e2ac).

Pin, in order:
  1. THE SOUNDNESS PROOF: replay_event routes through the sound replay module
     (walk_exit_manager, via the lazy gate_revalidation_ab import) and NEVER touches
     lib.simulator_real.simulate_trade_real -- proven by monkeypatching that function (on the
     real module -- postfix_gate_costing.py no longer imports the name into its own namespace
     at all post-fix, the strongest possible form of this proof) to raise if called.
  2. STRUCTURAL PROOF: the module carries no reference to simulate_event / simulate_trade_real
     at all anymore (the retired gate_expiry_check.simulate_event import is gone, not just
     unused) -- so a future edit can't quietly re-wire a call site back onto it without an
     import showing up in a diff.
  3. SCHEMA: every EV-bearing section mine() writes (part_a/part_b/oracle/part_c) carries
     replay_engine="walk_exit_manager" + replay_soundness="sound", matching the schema
     gate_expiry_check.py's evaluate_gate_pnl emits.
  4. END-TO-END: a full mine() run against synthetic core-decisions.jsonl rows (SKIP action +
     HOLD sole-blocker + bear[5,8] both-lifted), with the real replay module swapped for a
     fake, never touches simulate_trade_real and produces the expected per-part shape.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "tools"))
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO))

import postfix_gate_costing as pgc  # noqa: E402
import lib.simulator_real as simulator_real_module  # noqa: E402


class _FakeSoundReplayModule:
    """Stands in for the lazily-imported backtest/tools/gate_revalidation_ab.py -- byte-for-byte
    the same shape test_gate_expiry_check.py's fixture uses, so both fix sites are proven with
    the identical technique."""

    def __init__(self, pnl_by_ts: dict[str, float] | None = None):
        self.replay_calls: list[dict] = []
        self._pnl_by_ts = pnl_by_ts or {}

    def account_config(self):
        return {
            "safe": {"qty": 3, "structure_stop_enabled": True, "time_stop_et": dt.time(15, 40)},
            "bold": {"qty": 5, "structure_stop_enabled": True, "time_stop_et": dt.time(15, 40)},
        }

    def build_ribbon_lookup(self, spy):
        return "FAKE_RIBBON_LOOKUP"

    def replay_row(self, row, *, spy, spy_ts, spy_by_date, ribbon_lookup, cfg):
        self.replay_calls.append({"row": row, "cfg": cfg, "ribbon_lookup": ribbon_lookup})
        ts = row["ts_et"]
        pnl = self._pnl_by_ts.get(ts, 10.0)
        return {"status": "ok", "date": ts[:10], "pnl": pnl, "ts_et": ts}


def _tiny_spy_raw() -> pd.DataFrame:
    ts = pd.date_range("2026-07-31 09:30:00", periods=3, freq="5min", tz="UTC")
    return pd.DataFrame({
        "timestamp_et": ts, "open": [450.0, 450.5, 451.0], "high": [451.0, 451.5, 452.0],
        "low": [449.5, 450.0, 450.5], "close": [450.5, 451.0, 451.5], "volume": [1000, 1100, 1200],
    })


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


@pytest.fixture(autouse=True)
def _clear_replay_cache():
    pgc._REPLAY_CTX_CACHE.clear()
    pgc._SOUND_REPLAY_MODULE = None
    yield
    pgc._REPLAY_CTX_CACHE.clear()
    pgc._SOUND_REPLAY_MODULE = None


# ─────────────────────────────────────────────────────────────────────────── (1) core proof
def test_replay_event_uses_sound_replay_never_simulate_trade_real(monkeypatch):
    fake_grab = _FakeSoundReplayModule(pnl_by_ts={"2026-07-31T11:00:00": 42.0})
    monkeypatch.setattr(pgc, "_sound_replay_module", lambda: fake_grab)

    def _boom(*args, **kwargs):
        raise AssertionError("simulate_trade_real must NEVER be called by postfix_gate_costing.py "
                              "post-2026-08-08 POSTFIX-GATE-COSTING-UNSOUND-REPLAY fix")
    monkeypatch.setattr(simulator_real_module, "simulate_trade_real", _boom)

    spy = _tiny_spy_raw()
    row = {"ts_et": "2026-07-31T11:00:00", "side": "C", "account": "safe"}
    cfg = {"qty": 3, "structure_stop_enabled": True, "time_stop_et": dt.time(15, 40)}
    result = pgc.replay_event(row, spy, spy["timestamp_et"], {}, None, cfg)

    assert len(fake_grab.replay_calls) == 1, "sound replay must run exactly once"
    assert fake_grab.replay_calls[0]["cfg"]["qty"] == 3
    assert result["status"] == "ok"
    assert result["pnl"] == 42.0


# ─────────────────────────────────────────────────────────────────────── (2) structural proof
def test_module_carries_no_simulate_trade_real_reference():
    """The retired gate_expiry_check.simulate_event import is GONE (not just unused) -- this
    module cannot reach lib.simulator_real.simulate_trade_real even by accident, because the
    name is not bound anywhere in its namespace. (The module DOCSTRING is allowed to mention
    'simulate_trade_real' in prose describing the fix -- this checks for an actual import or
    call site, not the word appearing anywhere in the file.)"""
    import re
    assert not hasattr(pgc, "simulate_event")
    assert not hasattr(pgc, "simulate_trade_real")
    src = Path(pgc.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(from|import).*simulate_trade_real", src, re.M), (
        "no import statement may bind simulate_trade_real into this module's namespace")
    assert not re.search(r"\bsimulate_trade_real\s*\(", src), "no call site may invoke it directly"
    assert not re.search(r"\bsimulate_event\s*\(", src), "the retired simulate_event wrapper must not be called"
    assert not re.search(r"^\s*(from|import).*simulate_event", src, re.M), (
        "no import statement may bind simulate_event into this module's namespace (prose "
        "mentions of the retired name in docstrings are fine -- only import/call sites matter)")
    assert "compute_ribbon" not in src, "old direct compute_ribbon() call should be gone too -- build_ribbon_lookup owns it now"


# ─────────────────────────────────────────────────────────────────────────────── (3) schema
def test_replay_event_return_is_compatible_with_window_metrics(monkeypatch):
    """window_metrics only needs 'date'/'pnl' on each ok row -- confirm the sound replay_row
    shape (which differs from the retired simulate_event's shape: adds side/strike/
    entry_time_et/exit_reason/hold_minutes, drops nothing window_metrics reads) still feeds it
    cleanly."""
    fake_grab = _FakeSoundReplayModule(pnl_by_ts={"2026-07-31T11:00:00": 15.0})
    monkeypatch.setattr(pgc, "_sound_replay_module", lambda: fake_grab)
    spy = _tiny_spy_raw()
    cfg = {"qty": 3, "structure_stop_enabled": True, "time_stop_et": dt.time(15, 40)}
    row = {"ts_et": "2026-07-31T11:00:00", "side": "C"}
    out = pgc.replay_event(row, spy, spy["timestamp_et"], {}, None, cfg)
    m = pgc.window_metrics([out], dt.date(2026, 7, 1), dt.date(2026, 8, 31))
    assert m["n"] == 1
    assert m["exp_per_trade"] == 15.0


# ────────────────────────────────────────────────────────────────────── (4) end-to-end mine()
def test_mine_end_to_end_stamps_provenance_and_never_touches_simulate_trade_real(monkeypatch, tmp_path):
    fake_grab = _FakeSoundReplayModule()
    monkeypatch.setattr(pgc, "_sound_replay_module", lambda: fake_grab)

    def _boom(*a, **k):
        raise AssertionError("simulate_trade_real must NEVER be called during mine()")
    monkeypatch.setattr(simulator_real_module, "simulate_trade_real", _boom)

    spy_raw = _tiny_spy_raw()
    vix_raw = pd.DataFrame({"timestamp_et": spy_raw["timestamp_et"], "close": [15.0, 15.1, 15.2]})
    monkeypatch.setattr(pgc, "load_merged_spy_vix", lambda: (spy_raw, vix_raw))

    core_decisions = tmp_path / "core-decisions.jsonl"
    _write_jsonl(core_decisions, [
        {"ts_et": "2026-07-31T11:00:00", "side": "C", "account": "safe",
         "verdict": "SKIP_STRUCTURE_VETO", "armed": True},
        {"ts_et": "2026-07-31T11:05:00", "side": "P", "account": "safe", "verdict": "HOLD",
         "armed": True, "bear_blockers": [8], "bear_rejection_level_raw": 449.0},
        {"ts_et": "2026-07-31T11:10:00", "side": "P", "account": "safe", "verdict": "HOLD",
         "armed": True, "bear_blockers": [5, 8], "bear_rejection_level_raw": 449.0},
    ])
    monkeypatch.setattr(pgc, "CORE_DECISIONS", core_decisions)
    # point fleet arm reads at an empty tmp dir so Part C naturally finds n=0 (no real
    # automation/state/fleet dependency needed for this fixture)
    monkeypatch.setattr(pgc, "ROOT", tmp_path)

    out = pgc.mine(dt.date(2026, 7, 31), dt.date(2026, 8, 3))

    assert out["replay_engine"] == "walk_exit_manager"
    assert out["replay_soundness"] == "sound"
    assert "SKIP_STRUCTURE_VETO" in out["part_a_skip_gates"]
    a = out["part_a_skip_gates"]["SKIP_STRUCTURE_VETO"]
    assert a["replay_engine"] == "walk_exit_manager" and a["replay_soundness"] == "sound"

    assert "bear_filter8_safe" in out["part_b_filter_sole_blockers"]
    b = out["part_b_filter_sole_blockers"]["bear_filter8_safe"]
    assert b["replay_engine"] == "walk_exit_manager" and b["replay_soundness"] == "sound"

    oracle = out["oracle_bear_5_8_both_lifted"]["safe"]
    assert oracle["replay_engine"] == "walk_exit_manager" and oracle["replay_soundness"] == "sound"

    for arm, part in out["part_c_fleet_floor_atm_counterfactual"].items():
        assert part["replay_engine"] == "walk_exit_manager" and part["replay_soundness"] == "sound"
        assert part["n_raw_floor_rows"] == 0  # empty tmp fleet dir -> nothing to mine

    assert len(fake_grab.replay_calls) >= 3, "sound replay must have run for the SKIP + both HOLD cohorts"
