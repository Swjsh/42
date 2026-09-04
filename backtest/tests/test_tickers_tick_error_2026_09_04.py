"""RED-proof for the 2026-09-04 TICKERS-LANE TICK_ERROR outage.

SYMPTOM: on 2026-09-04, all three tickers arms logged
`{"decision": "TICK_ERROR", "reason": "TypeError: 'float' object is not subscriptable"}`
in automation/state/tickers/tickers-{1,2,3}/ledger.jsonl (tickers-1 x32, tickers-2 x102,
tickers-3 x10). The catch at multi/execute.py's `run_arm()` (around the `core.tick(...)`
call) logged only `str(e)`, no traceback, so the exact failing line was unknowable from the
ledger alone.

ROOT CAUSE (one sentence): `multi/core.py`'s per-symbol entry-scoring loop caught only
`(ms.SignalBuildError, ValueError)` around the `build_signal_fn(...)` call -- narrower than
every OTHER per-symbol gate in the same loop (chain/expiry/strike/quote/sizing all catch
bare `Exception`) -- so any other exception type raised inside the scorer (the "production"
scorer in particular calls `backtest/lib/filters.py`'s FROZEN, SPY-only-validated setup
evaluators against this lane's symbol-generic level/LevelState shapes for the first time in
production) escaped `core.tick()` entirely and was caught only by `execute.py`'s OUTER
per-arm try/except as an undiagnosed TICK_ERROR -- which blocks EVERY symbol in that arm for
that WHOLE tick, not just the one that actually failed. `mr.evaluate_admission(...)` a few
lines below was completely unguarded for the same reason.

THE FIX: widen `except (ms.SignalBuildError, ValueError)` to `except Exception` around the
`build_signal_fn` call (`multi/core.py`, "signal_scored" gate), and wrap the previously-bare
`mr.evaluate_admission(...)` call in the same "one bad symbol must not kill the tick"
try/except (`multi/core.py`, "risk_admitted" gate) -- both now degrade to a per-symbol
BLOCKED row instead of aborting the whole tick. Also: `multi/execute.py`'s TICK_ERROR ledger
row now carries `traceback.format_exc()[-1500:]` so any FUTURE TICK_ERROR is diagnosable
straight from the ledger, never blind again.

RED RUN (pre-fix code, `except (ms.SignalBuildError, ValueError)` restored, reproduced by
temporarily reverting the widened except and re-running this file):

    FAILED backtest/tests/test_tickers_tick_error_2026_09_04.py::test_scorer_typeerror_no_longer_kills_the_whole_tick
    TypeError: 'float' object is not subscriptable
    ... (raised out of core.tick(), uncaught by the test's own pytest.raises(TypeError) check
        failing instead on the SECOND symbol never being scored at all -- old code aborts the
        loop entirely on the first symbol's exception)

GREEN RUN (post-fix, this file against the fixed multi/core.py):

    2 passed in <1s>  (see test run quoted in the commit / GOAL log for the exact count)
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

from multi import core                        # noqa: E402
from multi.lib import creds as mc              # noqa: E402
from multi.lib import position_state as mps    # noqa: E402


def _synthetic_bars(n: int = 300, seed: int = 7, start: float = 120.0) -> pd.DataFrame:
    """Deterministic random walk, well past every warmup requirement at n=300 (mirrors the
    identical helper in test_tickers_scorer_2026_09_04.py)."""
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


FAKE_CREDS = mc.MultiCreds(key="k", secret="s", base_url="https://paper-api.alpaca.markets",
                           account_number="TESTACCT", source="test")

_ATT = {
    "ZBOOM": {"rel_volume": 5.0, "pct_change": 1.0, "dollar_volume": 1e7, "scanner_hits": 1},
    "ZOK": {"rel_volume": 5.0, "pct_change": 1.0, "dollar_volume": 1e7, "scanner_hits": 1},
}


def _apply_tick_env(monkeypatch, bars_map: dict) -> None:
    """Same hermetic account/network boundary as test_tickers_scorer_2026_09_04.py's helper."""
    monkeypatch.setattr(core.mb, "get_account", lambda creds: {"equity": 10_000.0})
    monkeypatch.setattr(core.mb, "get_positions", lambda creds: [])

    def _fake_fetch_bars_batch(creds, symbols, timeframe="5Min", limit=400):
        return {s: bars_map[s] for s in symbols if s in bars_map}

    monkeypatch.setattr(core, "fetch_bars_batch", _fake_fetch_bars_batch)

    fake_vix = core.mctx.VixContext(now=15.0, prior=15.0, ma_5d=15.0, ma_20d=15.0,
                                    as_of_et="2026-08-03T09:30:00-04:00", degraded=False)
    monkeypatch.setattr(core.mctx, "fetch_vix", lambda: fake_vix)


def _ok_signal(symbol, bars, **kwargs):
    """A HOLD-shaped stub -- shape-complete, never fires an entry, never raises."""
    return {
        "_doc": "test stub", "symbol": symbol, "arm": None, "shadow_only": True,
        "date": "2026-08-03", "time_et": "09:30", "spot": float(bars["close"].iloc[-1]),
        "atr_14": 1.0, "vix": 15.0, "vix_dir": "flat", "vix_regime": None,
        "ribbon_stack": None, "ribbon_spread_pct": None, "htf_15m_stack": None,
        "levels_active": [], "multi_day_levels": [], "action": "HOLD",
        "bear": {"passed": False, "score": 0, "blockers": [], "triggers_fired": [],
                 "rejection_level": None, "confluence": False, "candlestick_pattern": None},
        "bull": {"passed": False, "score": 0, "blockers": [], "triggers_fired": [],
                 "reclaim_level": None, "confluence": False, "shadow_triggers_fired": []},
        "written_at": "2026-08-03T09:30:00+0000", "source": "test-ok",
    }


def _seed_empty_state(tmp_path: Path) -> Path:
    p = tmp_path / "exit-state.json"
    mps.save_state({}, path=p)
    return p


def test_scorer_typeerror_no_longer_kills_the_whole_tick(monkeypatch, tmp_path):
    """The exact production symptom: build_signal_fn raises a bare TypeError (the same
    exception TYPE and MESSAGE observed live: "'float' object is not subscriptable") for
    ZBOOM. Pre-fix, this exception type is NOT in `except (ms.SignalBuildError, ValueError)`
    -- it escapes core.tick() entirely and this call raises TypeError instead of returning.
    Post-fix, ZBOOM degrades to a per-symbol BLOCKED/signal_scored row and ZOK (scored right
    after it, in the same universe, same tick) still gets evaluated -- proving one bad
    symbol's scorer failure no longer blocks its neighbors, matching every other per-symbol
    gate in this same loop (chain/expiry/strike/quote/sizing)."""
    def _boom_or_ok(symbol, bars, **kwargs):
        if symbol == "ZBOOM":
            raise TypeError("'float' object is not subscriptable")
        return _ok_signal(symbol, bars, **kwargs)

    monkeypatch.setattr(core.ms, "build_signal", _boom_or_ok)
    _apply_tick_env(monkeypatch, {"ZBOOM": _synthetic_bars(seed=1), "ZOK": _synthetic_bars(seed=2)})
    state_path = _seed_empty_state(tmp_path)

    # PRE-FIX this line raises TypeError, killing the whole tick for every symbol -- exactly
    # the outage: `execute.py`'s outer try/except then logs a bare, traceback-less TICK_ERROR
    # and NEITHER ZBOOM nor ZOK (nor any other arm symbol) is scored that tick.
    rows, cascade = core.tick({"scorer": "fork"}, FAKE_CREDS, ["ZBOOM", "ZOK"],
                              attention_override=_ATT, state_path=state_path)

    by_symbol = {r.get("symbol"): r for r in rows if r.get("kind") != "exit_eval"}
    assert "ZBOOM" in by_symbol, "ZBOOM's row must exist -- degrade, never silently drop it"
    boom_row = by_symbol["ZBOOM"]
    assert boom_row["decision"] == "BLOCKED"
    assert boom_row["gate"] == "signal_scored"
    assert "TypeError" in boom_row["reason"]
    assert "not subscriptable" in boom_row["reason"]

    # THE ACTUAL REGRESSION THIS TEST GUARDS: ZOK is scored normally in the SAME tick, right
    # after the symbol that blew up.
    assert "ZOK" in by_symbol, "a neighbor symbol must still be evaluated in the same tick"
    assert by_symbol["ZOK"]["decision"] == "HOLD"


def test_admission_exception_no_longer_kills_the_whole_tick(monkeypatch, tmp_path):
    """`mr.evaluate_admission(...)` was completely unguarded in the entries loop (the only
    such call in the loop with no try/except at all). A raise there -- of ANY type, not just
    a TypeError -- must degrade to a per-symbol BLOCKED/risk_admitted row instead of aborting
    the tick, exactly like every other gate a few lines around it."""
    def _always_enter(symbol, bars, **kwargs):
        sig = _ok_signal(symbol, bars, **kwargs)
        sig["action"] = "ENTER_BULL"
        sig["bull"] = {"passed": True, "score": 10, "blockers": [], "triggers_fired": ["x"],
                       "reclaim_level": None, "confluence": False, "shadow_triggers_fired": []}
        return sig

    monkeypatch.setattr(core.ms, "build_signal", _always_enter)
    monkeypatch.setattr(
        core.mr, "evaluate_admission",
        lambda **kw: (_ for _ in ()).throw(RuntimeError("admission boom")),
    )
    _apply_tick_env(monkeypatch, {"ZBOOM": _synthetic_bars(seed=3)})
    state_path = _seed_empty_state(tmp_path)

    # PRE-FIX this line raises RuntimeError, killing the whole tick.
    rows, cascade = core.tick({"scorer": "fork"}, FAKE_CREDS, ["ZBOOM"],
                              attention_override=_ATT, state_path=state_path)

    by_symbol = {r.get("symbol"): r for r in rows if r.get("kind") != "exit_eval"}
    assert "ZBOOM" in by_symbol
    row = by_symbol["ZBOOM"]
    assert row["decision"] == "BLOCKED"
    assert row["gate"] == "risk_admitted"
    assert "admission boom" in row["reason"]


def test_tick_error_ledger_row_carries_a_traceback(monkeypatch, tmp_path):
    """execute.py's TICK_ERROR row (the outer, last-resort safety net around core.tick()
    itself) must carry a traceback -- the 2026-09-04 outage's actual diagnosability gap: the
    ledger showed the exception message but never the failing line, so the root cause was
    unknowable without a live repro session."""
    import multi.execute as execute

    captured: list[dict] = []
    monkeypatch.setattr(execute, "append_jsonl", lambda path, row: captured.append(row))
    monkeypatch.setattr(execute, "check_static_invariants", lambda *a, **k: None)
    monkeypatch.setattr(execute, "effective_key_source", lambda cfg: "tickers-x")
    monkeypatch.setattr(execute, "precheck_creds", lambda key_source, arm: None)
    monkeypatch.setattr(execute, "load_pinned_account", lambda arm: "ACCT123")
    monkeypatch.setattr(execute.mc, "resolve", lambda params: FAKE_CREDS)
    monkeypatch.setattr(execute.mc, "verify_account",
                        lambda creds: {"account_number": "ACCT123", "equity": 5000.0})

    def _boom_tick(*a, **k):
        raise TypeError("'float' object is not subscriptable")

    monkeypatch.setattr(execute.core, "tick", _boom_tick)
    monkeypatch.setattr(execute.mps, "ensure_initialized", lambda **k: None)
    monkeypatch.setattr(execute.mb, "equity_option_positions", lambda creds, allowed_roots=None: [])
    monkeypatch.setattr(execute.mb, "get_orders", lambda creds, status=None: [])

    lane_params = {
        "scorer": "fork",
        "arms": {"tickers-x": {"universe": ["ZBOOM"], "key_source": "tickers-x"}},
        "risk": {"daily_loss_kill_switch_pct": 0.30},
    }

    summary = execute.run_arm("tickers-x", lane_params, {}, {}, shadow=True,
                              deadline=__import__("time").monotonic() + 30)

    tick_error_rows = [r for r in captured if r.get("decision") == "TICK_ERROR"]
    assert len(tick_error_rows) == 1, f"expected exactly one TICK_ERROR row, got {captured!r}"
    row = tick_error_rows[0]
    assert "TypeError" in row["reason"]
    assert "traceback" in row, "TICK_ERROR row must carry a traceback field"
    assert "_boom_tick" in row["traceback"] or "TypeError" in row["traceback"]
