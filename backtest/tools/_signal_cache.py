"""_signal_cache.py -- shared signal set for T3/T4 (HANDOFF-2026-07-10-ENTRY-EXIT-MATRIX).

Runs ONE full-window run_backtest (L2 gate, both directions, cap OFF) to get the ribbon_ride
SIGNAL SET (strike-independent entry events), caches it to JSON so T3 (entry matrix) and T4 (exit
matrix) reuse it without re-running the backtest. BS_FALLBACK fills excluded (C1: real OPRA only).

Both T3 and T4 then load each signal's real cached OPRA bars per strike and replay entries/exits
-- fast (ms/cell), the same method exit_shape_parity_study uses for the 17-signal anchor.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("GAMMA_RISK_GATE_ASSERT", "0")
os.environ.setdefault("GAMMA_ENGINE_SCORE_ASSERT", "0")

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))

CACHE = REPO / "analysis" / "exit-parity" / "signal-set.json"
START = dt.date(2025, 1, 1)
END = dt.date(2026, 6, 18)
SIGNAL_STRIKE_OFFSET = 2   # OTM-2 signal-generating strike (band split is post-hoc)


def build_signals() -> list[dict]:
    import json as _json
    from lib.orchestrator import run_backtest
    from autoresearch.runner import load_data
    import autoresearch.strategy_space_grind as g
    params = _json.loads((REPO / "automation" / "state" / "params.json").read_text(encoding="utf-8-sig"))
    p = g._strip_strike_keys(params)
    p.update(g.L2_PATCH)
    p["use_real_fills"] = True
    p["enable_bullish"] = True
    spy, vix = load_data(START, END)
    res = run_backtest(spy, vix, start_date=START, end_date=END, use_real_fills=True,
                       params_overrides=p, initial_equity=2000.0, strike_offset=SIGNAL_STRIKE_OFFSET,
                       premium_stop_pct=-0.50, premium_stop_pct_bear=-0.50, premium_stop_pct_bull=-0.50)
    signals = []
    for t in res.trades:
        setup = str(t.setup)
        if "BS_FALLBACK" in setup:
            continue
        et = t.entry_time_et
        if hasattr(et, "to_pydatetime"):
            et = et.to_pydatetime()
        if getattr(et, "tzinfo", None) is not None:
            et = et.replace(tzinfo=None)
        signals.append({"date": str(et.date()), "entry_ts": et.isoformat(), "side": t.side,
                        "entry_spot": float(t.entry_spot), "setup": setup,
                        "direction": "bull" if "BULLISH" in setup else "bear"})
    return signals


def load_or_build_signals(force: bool = False) -> list[dict]:
    if CACHE.exists() and not force:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    sigs = build_signals()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({"window": f"{START}..{END}", "n": len(sigs),
                                 "signal_strike_offset": SIGNAL_STRIKE_OFFSET,
                                 "signals": sigs}, indent=2), encoding="utf-8")
    return json.loads(CACHE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    data = load_or_build_signals(force="--force" in sys.argv)
    sigs = data["signals"] if isinstance(data, dict) else data
    from collections import Counter
    print(f"[signal_cache] {len(sigs)} signals cached -> {CACHE}")
    print("  by direction:", dict(Counter(s["direction"] for s in sigs)))
    print("  date span:", min(s["date"] for s in sigs), "..", max(s["date"] for s in sigs))
