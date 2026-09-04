"""Tests for the PRODUCTION-scorer adapter (multi/lib/scorer_production.py) and the
multi/core.py scorer dispatch + four new tick()/manage_open_positions() kwargs
(state_path, level_state_dir, realized_pnl_today, kill_switch_tripped).

Covers:
  * SHAPE PARITY -- multi.lib.signal.build_signal (the fork) and scorer_production.build_signal
    (production) return dicts with the SAME key set, top level and inside bear/bull, on
    identical synthetic bars.
  * PRODUCTION IS GENUINELY CALLED, not just import-compatible -- monkeypatching
    backtest.lib.filters.evaluate_bullish_setup changes scorer_production's result and leaves
    the fork's untouched (vary-and-assert RED-proof that the dispatch is real).
  * KWARG THREADING -- state_path -> mps.load_state(path=...), level_state_dir ->
    mctx.update_level_states(state_dir=...), realized_pnl_today/kill_switch_tripped ->
    mr.evaluate_admission(...), each proven via a monkeypatched recorder on the exact callee,
    both when the kwarg is supplied and when it is omitted (byte-identical to prior behavior).
  * TICK DISPATCH -- params["scorer"]="fork"/"production" rows carry the matching
    row["scorer"] and call the matching build_signal implementation (never both); any other
    value raises TickError immediately, before any account/network call.

NOTE on `dry_bars`: multi/core.py's own SCORING bars come from `fetch_bars_batch` (a
module-level function), not from the `dry_bars` parameter (that only feeds exit-management and
the attention fallback) -- verified by reading tick()'s body. So the tick-dispatch tests below
inject bars by monkeypatching `core.fetch_bars_batch` directly, which is the mechanism that
actually reaches the scorer, and pass `attention_override` to skip the (also dry_bars-fed)
attention-from-bars path deterministically.

FROZEN_TRADING_PATH (setup/hooks/doctrine.py): backtest/lib/filters.py is imported here and by
scorer_production.py, and monkeypatched-and-restored (pytest's `monkeypatch` fixture) in the
RED-proof test below -- never edited on disk by either.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from multi import core                     # noqa: E402
from multi.lib import creds as mc          # noqa: E402
from multi.lib import position_state as mps  # noqa: E402
from multi.lib import scorer_production as msp  # noqa: E402
from multi.lib import signal as ms         # noqa: E402
from backtest.lib import filters as bf     # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Shared fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

def _synthetic_bars(n: int = 300, seed: int = 7, start: float = 120.0) -> pd.DataFrame:
    """Deterministic random walk, seed fixed -- well past every warmup requirement
    (ribbon slow EMA=48, ATR=14, vol/range baselines=20, MIN_BARS_REQUIRED=50) at n=300."""
    rng = random.Random(seed)
    closes = [start]
    for _ in range(n - 1):
        nxt = closes[-1] + rng.gauss(0, 0.15)
        closes.append(nxt if nxt > 1.0 else 1.0)
    rows = []
    prev_close = closes[0]
    for c in closes:
        o = prev_close
        h = max(o, c) + abs(rng.gauss(0, 0.05))
        l = min(o, c) - abs(rng.gauss(0, 0.05))
        v = 500_000.0 + rng.random() * 500_000.0
        rows.append({"open": o, "high": h, "low": l, "close": c, "volume": v})
        prev_close = c
    idx = pd.date_range("2026-08-03 09:30", periods=n, freq="5min", tz="America/New_York")
    return pd.DataFrame(rows, index=idx)


_FAKE_VIX_KWARGS = dict(vix_now=15.0, vix_prior=15.0, vix_5d_ma=15.0, vix_20d_ma=15.0)

FAKE_CREDS = mc.MultiCreds(key="k", secret="s", base_url="https://paper-api.alpaca.markets",
                           account_number="TESTACCT", source="test")

_ATT = {"ZTEST": {"rel_volume": 5.0, "pct_change": 1.0, "dollar_volume": 1e7, "scanner_hits": 1}}


def _apply_tick_env(monkeypatch, bars_map: dict) -> None:
    """Patch the account/network boundary so core.tick() runs hermetically: fake equity,
    empty broker positions, bars served from `bars_map` instead of a live HTTP call, and a
    fixed non-degraded VIX read. Leaves mlv.compute_levels / mctx.update_level_states /
    mr.evaluate_admission / the scorer dispatch itself REAL unless a test patches them too."""
    monkeypatch.setattr(core.mb, "get_account", lambda creds: {"equity": 10_000.0})
    monkeypatch.setattr(core.mb, "get_positions", lambda creds: [])

    def _fake_fetch_bars_batch(creds, symbols, timeframe="5Min", limit=400):
        return {s: bars_map[s] for s in symbols if s in bars_map}

    monkeypatch.setattr(core, "fetch_bars_batch", _fake_fetch_bars_batch)

    fake_vix = core.mctx.VixContext(now=15.0, prior=15.0, ma_5d=15.0, ma_20d=15.0,
                                    as_of_et="2026-08-03T09:30:00-04:00", degraded=False)
    monkeypatch.setattr(core.mctx, "fetch_vix", lambda: fake_vix)


def _fake_build_signal_factory(action: str, calls: list, tag: str):
    """A canned build_signal stand-in: shape-complete (every key core.tick() reads), records
    (tag, symbol) into `calls` so a test can assert exactly which scorer was invoked."""
    def _fake(symbol, bars, **kwargs):
        calls.append((tag, symbol))
        return {
            "_doc": "test stub", "symbol": symbol, "arm": None, "shadow_only": True,
            "date": "2026-08-03", "time_et": "09:30", "spot": float(bars["close"].iloc[-1]),
            "atr_14": 1.0, "vix": 15.0, "vix_dir": "flat", "vix_regime": None,
            "ribbon_stack": None, "ribbon_spread_pct": None, "htf_15m_stack": None,
            "levels_active": [], "multi_day_levels": [], "action": action,
            "bear": {"passed": action == "ENTER_BEAR", "score": 10, "blockers": [],
                     "triggers_fired": [], "rejection_level": None, "confluence": False,
                     "candlestick_pattern": None},
            "bull": {"passed": action == "ENTER_BULL", "score": 11, "blockers": [],
                     "triggers_fired": [], "reclaim_level": None, "confluence": False,
                     "shadow_triggers_fired": []},
            "written_at": "2026-08-03T09:30:00+0000", "source": tag,
        }
    return _fake


def _seed_empty_state(tmp_path: Path) -> Path:
    p = tmp_path / "exit-state.json"
    mps.save_state({}, path=p)
    return p


# ─────────────────────────────────────────────────────────────────────────────
# 1. SHAPE PARITY -- fork vs production, same bars, same key set
# ─────────────────────────────────────────────────────────────────────────────

def test_shape_parity_top_level_and_bear_bull_keys():
    bars = _synthetic_bars()
    spot = float(bars["close"].iloc[-1])
    kwargs = dict(candidate_levels=[spot + 1.0], candidate_multi_day_levels=[spot - 1.0],
                 level_states={}, params={"arm": "test", "shadow_only": True},
                 **_FAKE_VIX_KWARGS)

    fork_sig = ms.build_signal("ZFAKE", bars, **kwargs)
    prod_sig = msp.build_signal("ZFAKE", bars, **kwargs)

    assert set(fork_sig.keys()) == set(prod_sig.keys()), (
        f"top-level key mismatch: fork-only={set(fork_sig) - set(prod_sig)} "
        f"prod-only={set(prod_sig) - set(fork_sig)}"
    )
    assert set(fork_sig["bear"].keys()) == set(prod_sig["bear"].keys())
    assert set(fork_sig["bull"].keys()) == set(prod_sig["bull"].keys())

    # both are genuinely scored dicts, not stubs -- and provenance is distinguishable
    assert fork_sig["source"] == "multi-lib-signal-v1"
    assert prod_sig["source"] == "production-filters-v1"
    assert prod_sig["symbol"] == "ZFAKE"
    # documented divergence, not an invented value (see scorer_production.py module docstring)
    assert prod_sig["vix_regime"] is None
    assert isinstance(fork_sig["vix_regime"], dict)


def test_shape_parity_holds_with_no_candidate_levels_too():
    """Same key-set proof on the HOLD path (no levels supplied -> both scorers HOLD)."""
    bars = _synthetic_bars()
    kwargs = dict(candidate_levels=None, candidate_multi_day_levels=None, level_states={},
                 params={"arm": "test", "shadow_only": True}, **_FAKE_VIX_KWARGS)
    fork_sig = ms.build_signal("ZFAKE", bars, **kwargs)
    prod_sig = msp.build_signal("ZFAKE", bars, **kwargs)
    assert set(fork_sig.keys()) == set(prod_sig.keys())
    assert fork_sig["action"] == "HOLD"
    assert prod_sig["action"] == "HOLD"


# ─────────────────────────────────────────────────────────────────────────────
# 2. PRODUCTION IS GENUINELY CALLED -- RED-proof via monkeypatched backtest.lib.filters
# ─────────────────────────────────────────────────────────────────────────────

def test_production_scorer_actually_calls_production_filters(monkeypatch):
    """Monkeypatch backtest.lib.filters.evaluate_bullish_setup to a sentinel. If
    scorer_production.py calls it module-qualified (bf.evaluate_bullish_setup(...)), the
    patched sentinel is what runs and prod_sig reflects it. The fork's OWN
    evaluate_bullish_setup (multi/lib/filters.py, untouched) must NOT be affected --
    proving the two are genuinely independent code paths, not one aliasing the other."""
    bars = _synthetic_bars()
    spot = float(bars["close"].iloc[-1])
    kwargs = dict(candidate_levels=[spot + 1.0], candidate_multi_day_levels=[],
                 level_states={}, params={"arm": "test", "shadow_only": True},
                 **_FAKE_VIX_KWARGS)

    sentinel = bf.BullishSetupResult(passed=True, bull_score=999)
    monkeypatch.setattr(bf, "evaluate_bullish_setup", lambda ctx, **kw: sentinel)

    prod_sig = msp.build_signal("ZFAKE", bars, **kwargs)
    assert prod_sig["bull"]["score"] == 999
    assert prod_sig["bull"]["passed"] is True
    assert prod_sig["action"] == "ENTER_BULL"  # bull_score=999 wins any bear/bull tie-break

    fork_sig = ms.build_signal("ZFAKE", bars, **kwargs)
    assert fork_sig["bull"]["score"] != 999  # the fork's own (unpatched) evaluator ran instead


# ─────────────────────────────────────────────────────────────────────────────
# 3. KWARG THREADING -- manage_open_positions(state_path=...)
# ─────────────────────────────────────────────────────────────────────────────

def test_manage_open_positions_default_state_path_matches_prior_behavior(monkeypatch):
    calls = []

    def fake_load_state(**kw):
        calls.append(kw)
        return {}

    monkeypatch.setattr(core.mps, "load_state", fake_load_state)
    out = core.manage_open_positions({}, FAKE_CREDS, [], {})
    assert out == []
    assert calls == [{}]  # no `path` kwarg at all -> mps.load_state's own default STATE_PATH


def test_manage_open_positions_threads_state_path(monkeypatch, tmp_path):
    calls = []

    def fake_load_state(**kw):
        calls.append(kw)
        return {}

    monkeypatch.setattr(core.mps, "load_state", fake_load_state)
    p = tmp_path / "exit-state.json"
    out = core.manage_open_positions({}, FAKE_CREDS, [], {}, state_path=p)
    assert out == []
    assert calls == [{"path": p}]


# ─────────────────────────────────────────────────────────────────────────────
# 4. KWARG THREADING -- tick(level_state_dir=...) -> mctx.update_level_states(state_dir=...)
# ─────────────────────────────────────────────────────────────────────────────

def test_level_state_dir_threads_to_update_level_states(monkeypatch, tmp_path):
    calls = []

    def _fake_update_level_states(symbol, levels, bars, **kw):
        calls.append(kw)
        return {}

    monkeypatch.setattr(core.mctx, "update_level_states", _fake_update_level_states)
    monkeypatch.setattr(core.ms, "build_signal", _fake_build_signal_factory("HOLD", [], "fork"))
    _apply_tick_env(monkeypatch, {"ZTEST": _synthetic_bars()})
    state_path = _seed_empty_state(tmp_path)
    level_dir = tmp_path / "levels"

    core.tick({"scorer": "fork"}, FAKE_CREDS, ["ZTEST"], attention_override=_ATT,
             state_path=state_path, level_state_dir=level_dir)

    assert calls == [{"state_dir": level_dir}]


def test_level_state_dir_omitted_uses_update_level_states_own_default(monkeypatch, tmp_path):
    calls = []

    def _fake_update_level_states(symbol, levels, bars, **kw):
        calls.append(kw)
        return {}

    monkeypatch.setattr(core.mctx, "update_level_states", _fake_update_level_states)
    monkeypatch.setattr(core.ms, "build_signal", _fake_build_signal_factory("HOLD", [], "fork"))
    _apply_tick_env(monkeypatch, {"ZTEST": _synthetic_bars()})
    state_path = _seed_empty_state(tmp_path)

    core.tick({"scorer": "fork"}, FAKE_CREDS, ["ZTEST"], attention_override=_ATT,
             state_path=state_path)  # level_state_dir omitted

    assert calls == [{}]  # no state_dir kwarg passed -> byte-identical to pre-change behavior


def test_level_state_dir_actually_isolates_the_real_state_directory(monkeypatch, tmp_path):
    """End-to-end (mctx.update_level_states runs FOR REAL, not mocked): proves level_state_dir
    is not just a kwarg that gets passed, but one that actually redirects the write.

    RED-PROOF for a real bug found while building this: multi/lib/context.py's
    update_level_states(state_dir=...) used to be a DEAD knob for the actual read/write path
    -- `_states_path(symbol)` ignored `state_dir` entirely and always pointed at the real
    automation/state/multi/ directory (state_dir only drove an incidental mkdir). Fixed
    alongside this task (2026-09-04) since it directly undermines this kwarg's whole purpose.
    This test would have caught the dead knob; it fails RED against the pre-fix code.
    """
    real_state_dir = REPO_ROOT / "automation" / "state" / "multi"
    real_ztest_file = real_state_dir / "level-states-ZTEST.json"
    assert not real_ztest_file.exists(), (
        "precondition violated -- a real level-states-ZTEST.json already exists; "
        "this test cannot tell its own write apart from a pre-existing one"
    )

    monkeypatch.setattr(core.ms, "build_signal", _fake_build_signal_factory("HOLD", [], "fork"))
    _apply_tick_env(monkeypatch, {"ZTEST": _synthetic_bars()})
    state_path = _seed_empty_state(tmp_path)
    level_dir = tmp_path / "levels"

    try:
        core.tick({"scorer": "fork"}, FAKE_CREDS, ["ZTEST"], attention_override=_ATT,
                 state_path=state_path, level_state_dir=level_dir)

        assert (level_dir / "level-states-ZTEST.json").is_file(), (
            "level_state_dir was accepted but the file did not land there"
        )
        assert not real_ztest_file.exists(), (
            "level_state_dir was accepted but update_level_states ALSO (or instead) wrote "
            "into the real automation/state/multi/ directory -- the dead-knob bug is back"
        )
    finally:
        # Never leave a real trading-state file behind even if the assertions above fail.
        if real_ztest_file.exists():
            real_ztest_file.unlink()


# ─────────────────────────────────────────────────────────────────────────────
# 5. KWARG THREADING -- tick(realized_pnl_today=, kill_switch_tripped=) -> mr.evaluate_admission
# ─────────────────────────────────────────────────────────────────────────────

def _fake_admission_recorder(calls: list):
    """Records the kwargs mr.evaluate_admission was called with, then DENIES -- so tick()
    stops right at the risk_admitted gate and never reaches the chain/quote network calls
    further down the pipeline. Only the wiring is under test here, not the gate's own logic
    (multi/lib/risk.py has its own dedicated tests) or anything past it."""
    def _fake(**kw):
        calls.append(kw)
        return core.mr.Deny("TEST_STOP", "test stub -- halting before any network call")
    return _fake


def test_realized_pnl_and_kill_switch_thread_to_evaluate_admission(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(core.mr, "evaluate_admission", _fake_admission_recorder(calls))
    monkeypatch.setattr(core.ms, "build_signal",
                        _fake_build_signal_factory("ENTER_BEAR", [], "fork"))
    _apply_tick_env(monkeypatch, {"ZTEST": _synthetic_bars()})
    state_path = _seed_empty_state(tmp_path)

    rows, _ = core.tick({"scorer": "fork"}, FAKE_CREDS, ["ZTEST"], attention_override=_ATT,
                        state_path=state_path, level_state_dir=tmp_path / "levels",
                        realized_pnl_today=-123.45, kill_switch_tripped=True)

    assert len(calls) == 1
    assert calls[0]["realized_pnl_today"] == -123.45
    assert calls[0]["kill_switch_tripped"] is True
    row = next(r for r in rows if r.get("symbol") == "ZTEST")
    assert row["decision"] == "BLOCKED" and row["gate"] == "risk_admitted"


def test_realized_pnl_and_kill_switch_default_to_prior_hardcoded_values(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(core.mr, "evaluate_admission", _fake_admission_recorder(calls))
    monkeypatch.setattr(core.ms, "build_signal",
                        _fake_build_signal_factory("ENTER_BEAR", [], "fork"))
    _apply_tick_env(monkeypatch, {"ZTEST": _synthetic_bars()})
    state_path = _seed_empty_state(tmp_path)

    core.tick({"scorer": "fork"}, FAKE_CREDS, ["ZTEST"], attention_override=_ATT,
             state_path=state_path, level_state_dir=tmp_path / "levels")
    # realized_pnl_today / kill_switch_tripped both omitted

    assert len(calls) == 1
    assert calls[0]["realized_pnl_today"] == 0.0       # prior hardcoded literal
    assert calls[0]["kill_switch_tripped"] is False     # prior hardcoded literal


# ─────────────────────────────────────────────────────────────────────────────
# 6. TICK DISPATCH -- params["scorer"] selects fork vs production; bogus raises
# ─────────────────────────────────────────────────────────────────────────────

def test_tick_dispatch_scorer_fork(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(core.ms, "build_signal", _fake_build_signal_factory("HOLD", calls, "fork"))
    monkeypatch.setattr(core.msp, "build_signal", _fake_build_signal_factory("HOLD", calls, "production"))
    _apply_tick_env(monkeypatch, {"ZTEST": _synthetic_bars()})
    state_path = _seed_empty_state(tmp_path)

    rows, _ = core.tick({"scorer": "fork"}, FAKE_CREDS, ["ZTEST"], attention_override=_ATT,
                        state_path=state_path, level_state_dir=tmp_path / "levels")

    scored = [r for r in rows if r.get("symbol") == "ZTEST"]
    assert scored, f"no ZTEST row in {rows}"
    assert all(r["scorer"] == "fork" for r in scored)
    assert {c[0] for c in calls} == {"fork"}  # production's build_signal was NEVER called


def test_tick_dispatch_scorer_production(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(core.ms, "build_signal", _fake_build_signal_factory("HOLD", calls, "fork"))
    monkeypatch.setattr(core.msp, "build_signal", _fake_build_signal_factory("HOLD", calls, "production"))
    _apply_tick_env(monkeypatch, {"ZTEST": _synthetic_bars()})
    state_path = _seed_empty_state(tmp_path)

    rows, _ = core.tick({"scorer": "production"}, FAKE_CREDS, ["ZTEST"], attention_override=_ATT,
                        state_path=state_path, level_state_dir=tmp_path / "levels")

    scored = [r for r in rows if r.get("symbol") == "ZTEST"]
    assert scored, f"no ZTEST row in {rows}"
    assert all(r["scorer"] == "production" for r in scored)
    assert {c[0] for c in calls} == {"production"}  # the fork's build_signal was NEVER called


def test_tick_scorer_omitted_defaults_to_fork(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(core.ms, "build_signal", _fake_build_signal_factory("HOLD", calls, "fork"))
    monkeypatch.setattr(core.msp, "build_signal", _fake_build_signal_factory("HOLD", calls, "production"))
    _apply_tick_env(monkeypatch, {"ZTEST": _synthetic_bars()})
    state_path = _seed_empty_state(tmp_path)

    rows, _ = core.tick({}, FAKE_CREDS, ["ZTEST"], attention_override=_ATT,
                        state_path=state_path, level_state_dir=tmp_path / "levels")

    scored = [r for r in rows if r.get("symbol") == "ZTEST"]
    assert scored and all(r["scorer"] == "fork" for r in scored)


def test_tick_dispatch_scorer_bogus_raises_tick_error_before_any_network_call():
    """No monkeypatching at all -- if the scorer validation didn't run FIRST (before any
    account/broker read), this would attempt a real network call instead of raising fast."""
    with pytest.raises(core.TickError, match="bogus"):
        core.tick({"scorer": "bogus"}, FAKE_CREDS, ["ZTEST"])
