"""entry_exit_diagnostics.py -- T2, HANDOFF-2026-07-10-ENTRY-EXIT-MATRIX.

Extends the 17-live-signal entry-runback to the FULL OPRA backtest signal population: every
ribbon_ride signal the engine fires over the cached OPRA window (both directions), priced across
the strike ladder so all four premium bands are richly populated. Produces the per-band tables
that PARAMETERIZE the T3 (entry) and T4 (exit) grids -- "at premium <$0.20 no stop tighter than X
survives the noise floor," etc. NUMBERS BEFORE SEARCH.

DESIGN (efficient + faithful):
  1. ONE full-window run_backtest (L2 gate, both directions, cap OFF) yields the SIGNAL SET --
     the entry (date, time, side, entry_spot, setup) events. Strike-independent by construction
     (the trigger is a SPY/ribbon event); BS_FALLBACK fills (uncached -> Black-Scholes) are
     EXCLUDED (C1: real OPRA only).
  2. Each signal is then priced across the strike ladder {OTM-3..ITM-2} by loading each strike's
     REAL cached OPRA bars and walking the premium path from the entry bar. One signal priced at
     k strikes = k positions but ONE unique signal (ground rule 8: effective-n honesty).

DISCLOSURES (ground rule 9 -- frictionless, and stated everywhere):
  * FRICTIONLESS entry: entry premium = the entry bar's OPEN, no spread/slippage/queue. Absolute
    levels are optimistic; the comparison across bands/variants is fair (same rule for all).
  * 5-MIN granularity: the backtest OPRA cache is 5-min bars (the 17-live-signal runback used
    1-min). "MAE at 5/10/30 min" = the deepest low over the first 1/2/6 bars. A -S touch and a +T
    touch inside the SAME 5-min bar are ordered STOP-FIRST (matches simulator_real's conservative
    same-bar convention) -- so intrabar sub-5-min ordering is not resolved; disclosed.
  * ribbon_ride ONLY: the generic backtest path emits BEARISH_REJECTION / BULLISH_RECLAIM
    (ribbon_ride). vwap_continuation is a separate setup path not generated here (ground rule 11:
    per-strategy scope) -- its diagnostic is owed separately.

Writes analysis/exit-parity/entry-exit-diagnostics.json + .md. Pure local OPRA cache, $0, no network.

Run: backtest/.venv/Scripts/python.exe backtest/tools/entry_exit_diagnostics.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import statistics as st
import sys
from pathlib import Path

# Turn off the per-bar parity oracles for speed (same opt-out mass_grind uses; ranking-neutral).
os.environ.setdefault("GAMMA_RISK_GATE_ASSERT", "0")
os.environ.setdefault("GAMMA_ENGINE_SCORE_ASSERT", "0")

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))

from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
from lib.orchestrator import run_backtest  # noqa: E402
from autoresearch.runner import load_data  # noqa: E402
import autoresearch.strategy_space_grind as g  # noqa: E402

OUT_JSON = REPO / "analysis" / "exit-parity" / "entry-exit-diagnostics.json"
OUT_MD = REPO / "analysis" / "exit-parity" / "entry-exit-diagnostics.md"

START = dt.date(2025, 1, 1)
END = dt.date(2026, 6, 18)          # OPRA real-fill coverage cap (matches strategy_space_grind)
SIGNAL_STRIKE_OFFSET = 2            # OTM-2: the strike we generate the signal set at
STRIKE_LADDER = [3, 2, 1, 0, -1, -2]  # OTM-3..ITM-2 (simulator convention: +=OTM, -=ITM)

# Grid axes for the stop-harvest matrix (defect #3): does -S% get touched before +T%?
STOP_LEVELS = [10, 15, 20, 25, 30, 35, 40, 50]
TP_LEVELS = [15, 25, 30, 50, 75, 100, 150]
BANDS = [("<0.20", 0.0, 0.20), ("0.20-0.50", 0.20, 0.50),
         ("0.50-1.00", 0.50, 1.00), (">1.00", 1.00, 1e9)]


def band_of(premium: float) -> str:
    for name, lo, hi in BANDS:
        if lo <= premium < hi:
            return name
    return ">1.00"


def build_signal_set() -> list[dict]:
    """ONE full-window backtest -> the strike-independent signal events (BS_FALLBACK excluded)."""
    params = json.loads((REPO / "automation" / "state" / "params.json").read_text(encoding="utf-8-sig"))
    p = g._strip_strike_keys(params)
    p.update(g.L2_PATCH)
    p["use_real_fills"] = True
    p["enable_bullish"] = True
    spy, vix = load_data(START, END)
    print(f"[diag] data spy={len(spy)} vix={len(vix)}; window {START}..{END}", flush=True)
    res = run_backtest(spy, vix, start_date=START, end_date=END, use_real_fills=True,
                       params_overrides=p, initial_equity=2000.0,
                       strike_offset=SIGNAL_STRIKE_OFFSET,
                       premium_stop_pct=-0.50, premium_stop_pct_bear=-0.50, premium_stop_pct_bull=-0.50)
    signals = []
    for t in res.trades:
        setup = str(t.setup)
        if "BS_FALLBACK" in setup:
            continue  # not real OPRA -> exclude (C1)
        et = t.entry_time_et
        if hasattr(et, "to_pydatetime"):
            et = et.to_pydatetime()
        if getattr(et, "tzinfo", None) is not None:
            et = et.replace(tzinfo=None)
        signals.append({"date": et.date(), "entry_ts": et, "side": t.side,
                        "entry_spot": float(t.entry_spot), "setup": setup})
    print(f"[diag] signal set: {len(signals)} real-OPRA ribbon_ride signals", flush=True)
    return signals


def _strike_for(entry_spot: float, side: str, offset: int) -> int:
    atm = int(round(entry_spot))
    return atm - offset if side == "P" else atm + offset


def walk_premium_path(entry_spot: float, side: str, offset: int, date: dt.date,
                      entry_ts: dt.datetime) -> dict | None:
    """Frictionless walk of ONE (signal, strike) premium path over real 5-min OPRA bars.

    Returns per-bar-derived metrics, or None if the contract isn't cached / no entry bar."""
    strike = _strike_for(entry_spot, side, offset)
    symbol = option_symbol(date, strike, side)
    df = load_contract_bars(symbol)
    if df is None or df.empty:
        return None
    dfx = df.copy()
    if dfx["timestamp_et"].dt.tz is not None:
        dfx["timestamp_et"] = dfx["timestamp_et"].dt.tz_localize(None)
    after = dfx[dfx["timestamp_et"] >= entry_ts]
    if after.empty:
        return None
    entry_row = after.iloc[0]
    entry_premium = float(entry_row["open"])
    if entry_premium <= 0:
        return None
    # Bars from entry to EOD (same calendar date; 0DTE).
    path = after[after["timestamp_et"].dt.date == date]
    highs = path["high"].astype(float).tolist()
    lows = path["low"].astype(float).tolist()
    n = len(highs)
    if n == 0:
        return None

    def mae_over(k: int) -> float:
        kk = min(k, n)
        return min(lows[:kk]) / entry_premium - 1.0

    mfe_eod = max(highs) / entry_premium - 1.0
    # First-touch bar index for each stop / tp level (percent thresholds).
    first_stop_bar = {}
    first_tp_bar = {}
    for i in range(n):
        lo_pct = lows[i] / entry_premium - 1.0
        hi_pct = highs[i] / entry_premium - 1.0
        for s in STOP_LEVELS:
            if s not in first_stop_bar and lo_pct <= -s / 100.0:
                first_stop_bar[s] = i
        for tp in TP_LEVELS:
            if tp not in first_tp_bar and hi_pct >= tp / 100.0:
                first_tp_bar[tp] = i
    spread_proxy = (float(entry_row["high"]) - float(entry_row["low"]))
    return {
        "offset": offset, "strike": strike, "symbol": symbol,
        "entry_premium": round(entry_premium, 4),
        "band": band_of(entry_premium),
        "mae_5min": round(mae_over(1), 4), "mae_10min": round(mae_over(2), 4),
        "mae_30min": round(mae_over(6), 4), "mfe_eod": round(mfe_eod, 4),
        "first_stop_bar": first_stop_bar, "first_tp_bar": first_tp_bar,
        "spread_proxy": round(spread_proxy, 4),
        "spread_pct": round(spread_proxy / entry_premium, 4) if entry_premium else None,
        "n_bars": n,
    }


def _pctile(xs: list[float], q: float) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    idx = min(len(s) - 1, int(q * len(s)))
    return s[idx]


def _fmt_pct(x: float) -> str:
    return "n/a" if x != x else f"{x*100:.0f}%"


def aggregate(rows: list[dict], n_signals: int) -> dict:
    by_band = {b[0]: [r for r in rows if r["band"] == b[0]] for b in BANDS}
    out = {"n_positions": len(rows), "n_unique_signals": n_signals, "bands": {}}
    for band, rs in by_band.items():
        if not rs:
            out["bands"][band] = {"n": 0}
            continue
        prems = [r["entry_premium"] for r in rs]
        # stop-harvest matrix P(touch -S before +T | reached +T)
        harvest = {}
        for tp in TP_LEVELS:
            reached = [r for r in rs if tp in r["first_tp_bar"]]
            row = {"reach_rate": round(len(reached) / len(rs), 3), "n_reached": len(reached)}
            for s in STOP_LEVELS:
                if not reached:
                    row[f"stop{s}_before"] = None
                    continue
                # -S touched at or before +T bar (same-bar => stop first, conservative).
                cnt = sum(1 for r in reached
                          if s in r["first_stop_bar"] and r["first_stop_bar"][s] <= r["first_tp_bar"][tp])
                row[f"stop{s}_before"] = round(cnt / len(reached), 3)
            harvest[f"tp{tp}"] = row
        # median stop-distance in $0.01 ticks for a -20% stop (defect #1)
        ticks_20 = [r["entry_premium"] * 0.20 / 0.01 for r in rs]
        out["bands"][band] = {
            "n": len(rs),
            "median_entry_premium": round(st.median(prems), 3),
            "mae_5min": {"median": round(st.median(r["mae_5min"] for r in rs), 3),
                         "p25": round(_pctile([r["mae_5min"] for r in rs], 0.25), 3),
                         "p75": round(_pctile([r["mae_5min"] for r in rs], 0.75), 3)},
            "mae_10min": {"median": round(st.median(r["mae_10min"] for r in rs), 3),
                          "p25": round(_pctile([r["mae_10min"] for r in rs], 0.25), 3),
                          "p75": round(_pctile([r["mae_10min"] for r in rs], 0.75), 3)},
            "mae_30min": {"median": round(st.median(r["mae_30min"] for r in rs), 3),
                          "p75": round(_pctile([r["mae_30min"] for r in rs], 0.75), 3)},
            "mfe_eod": {"median": round(st.median(r["mfe_eod"] for r in rs), 3),
                        "p75": round(_pctile([r["mfe_eod"] for r in rs], 0.75), 3)},
            "median_20pct_stop_in_ticks": round(st.median(ticks_20), 1),
            "median_spread_proxy_pct": round(st.median(r["spread_pct"] for r in rs if r["spread_pct"] is not None), 3),
            "stop_harvest": harvest,
        }
    return out


def render_md(agg: dict) -> str:
    L = []
    L.append("# T2 — Entry/Exit Diagnostics (full OPRA ribbon_ride signal population)")
    L.append("")
    L.append(f"**{agg['n_unique_signals']} unique signals** priced across the OTM-3..ITM-2 ladder "
             f"= **{agg['n_positions']} positions** (ground rule 8: effective-n honesty). "
             f"Window {START}..{END}. FRICTIONLESS entry (bar open, no spread); 5-min OPRA bars; "
             f"ribbon_ride only (ground rule 11). Same-5min-bar -S/+T ties ordered STOP-FIRST.")
    L.append("")
    L.append("## Per-band noise floor (the priors that parameterize T3/T4)")
    L.append("")
    L.append("| band | n | med entry | MAE 5m (med/p75) | MAE 10m (med/p75) | MFE EOD (med/p75) | −20% stop = ticks | spread proxy |")
    L.append("|---|--:|--:|--:|--:|--:|--:|--:|")
    for band, _lo, _hi in BANDS:
        b = agg["bands"].get(band, {})
        if not b.get("n"):
            L.append(f"| {band} | 0 | — | — | — | — | — | — |")
            continue
        L.append(f"| {band} | {b['n']} | ${b['median_entry_premium']:.2f} "
                 f"| {_fmt_pct(b['mae_5min']['median'])} / {_fmt_pct(b['mae_5min']['p75'])} "
                 f"| {_fmt_pct(b['mae_10min']['median'])} / {_fmt_pct(b['mae_10min']['p75'])} "
                 f"| {_fmt_pct(b['mfe_eod']['median'])} / {_fmt_pct(b['mfe_eod']['p75'])} "
                 f"| {b['median_20pct_stop_in_ticks']:.1f} | {_fmt_pct(b['median_spread_proxy_pct'])} |")
    L.append("")
    L.append("**Reading:** where `−20% stop = ticks` is ≲3 and the spread proxy is a large % of "
             "premium, a −20% stop sits INSIDE the spread/noise (defect #1). Where MAE 10m median "
             "is deeper than a candidate stop, that stop is inside the median noise floor (defect #3).")
    L.append("")
    L.append("## Stop-harvest matrix — P(touch −S before +T | reached +T)")
    L.append("")
    L.append("For each band: among signals that EVER reach +T, the fraction that first touch −S "
             "at/before the +T bar (i.e. a −S stop would harvest them out of an eventual +T winner). "
             "A high number = the stop is too tight for that target in that band.")
    L.append("")
    for band, _lo, _hi in BANDS:
        b = agg["bands"].get(band, {})
        if not b.get("n"):
            continue
        L.append(f"### band {band}  (n={b['n']}, med premium ${b['median_entry_premium']:.2f})")
        L.append("")
        hv = b["stop_harvest"]
        header = "| target | reach% | " + " | ".join(f"−{s}%" for s in STOP_LEVELS) + " |"
        L.append(header)
        L.append("|---|--:|" + "--:|" * len(STOP_LEVELS))
        for tp in TP_LEVELS:
            r = hv[f"tp{tp}"]
            cells = []
            for s in STOP_LEVELS:
                v = r.get(f"stop{s}_before")
                cells.append("—" if v is None else f"{v*100:.0f}%")
            L.append(f"| +{tp}% | {r['reach_rate']*100:.0f}% ({r['n_reached']}) | " + " | ".join(cells) + " |")
        L.append("")
    L.append("---")
    L.append("_Source: `backtest/tools/entry_exit_diagnostics.py` over real cached OPRA. "
             "Exploratory — priors for T3/T4, not a ratification. Regenerate to refresh._")
    return "\n".join(L) + "\n"


def main() -> int:
    signals = build_signal_set()
    rows = []
    miss = 0
    for sig in signals:
        for offset in STRIKE_LADDER:
            r = walk_premium_path(sig["entry_spot"], sig["side"], offset, sig["date"], sig["entry_ts"])
            if r is None:
                miss += 1
                continue
            r["date"] = str(sig["date"])
            r["side"] = sig["side"]
            rows.append(r)
    print(f"[diag] priced {len(rows)} positions ({miss} uncached/no-bar skips)", flush=True)
    agg = aggregate(rows, n_signals=len(signals))

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({
        "window": f"{START}..{END}", "n_unique_signals": len(signals),
        "n_positions": len(rows), "strike_ladder": STRIKE_LADDER,
        "disclosures": ["frictionless entry (bar open, no spread)", "5-min OPRA bars",
                        "ribbon_ride only (vwap owed)", "same-bar -S/+T ties = stop-first"],
        "aggregate": agg,
        "positions": rows,
    }, indent=2, default=str), encoding="utf-8")
    OUT_MD.write_text(render_md(agg), encoding="utf-8")
    print(f"[diag] wrote {OUT_JSON.name} + {OUT_MD.name}", flush=True)
    # quick console read
    for band, _lo, _hi in BANDS:
        b = agg["bands"].get(band, {})
        if b.get("n"):
            print(f"  {band:10s} n={b['n']:4d} medPrem=${b['median_entry_premium']:.2f} "
                  f"MAE10m_med={_fmt_pct(b['mae_10min']['median'])} "
                  f"-20%stop={b['median_20pct_stop_in_ticks']:.1f}ticks", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
