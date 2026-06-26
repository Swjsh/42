"""verify_pre_fomc_drift -- MINIMAL real-fills harness + 8 fraud-gates for the SOURCED
strategy ``pre-fomc-announcement-drift`` (arena=0dte, B6-EXTERNAL).

STRATEGY (as sourced)
─────────────────────
ENTRY: only on the ~8 scheduled FOMC announcement days/yr (decision 14:00 ET). Buy a
0DTE SPY CALL at the morning entry gate (09:35-10:00 ET) UNLESS the early session is
already in a sharp risk-off slide (skip if SPY < prior close by > 0.4% AND VIX rising).
EXIT: hard exit at 13:55 ET (5 min BEFORE the 14:00 print -- hold the PRE-announcement
drift, not the coin-flip post-print). Chart-stop only (C2): stop below morning swing
low; NO premium stop (premium_stop_pct = chart-stop-only -0.99). Survivor structure
applied: ATM/ITM-1 strike + morning entry.

This reuses the project's only WR authority (lib.simulator_real real OPRA fills, C1),
the shared random-entry null (autoresearch.null_baseline), and the two graduated fraud
gates (autoresearch.fraud_gates). It mirrors the edge-hunt verify harness's gate set.

THE 8 GATES (a candidate is EDGE only if it clears ALL 8):
  1 GATE_OOS    : OOS (2026 FOMC days) per-trade > 0
  2 GATE_Q      : positive_quarters >= 4/6  (quarters with >=1 trade that are net +)
  3 GATE_CONC   : top5-day concentration < 200%
  4 GATE_N      : n >= 20
  5 GATE_DROP5  : drop-top-5-days per-trade > 0
  6 GATE_TRUNC  : no truncation artifact (sign holds at chart-stop-only) -- L171
  7 GATE_NULL   : beats random-entry null MAX + drop5 beats null mean -- L172
  8 GATE_OOS_N  : OOS n >= 20  (out-of-sample sufficiency)

Pure Python, $0. No live orders. Deterministic.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BACKTEST = ROOT / "backtest"
for _p in (str(BACKTEST), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from autoresearch.null_baseline import null_gate, random_entry_null  # noqa: E402
from autoresearch.runner import load_data  # noqa: E402
from autoresearch.fraud_gates import (  # noqa: E402
    CandidateSignal,
    verify_candidate,
)
from lib.truncation_guard import CHART_STOP_ONLY_PCT  # noqa: E402

# ── Scheduled FOMC announcement DATES (decision 14:00 ET on day-2). Only the days that
# fall inside our OPRA option-cache coverage (2025-01..2026-05) are testable.
FOMC_DAYS = [
    dt.date(2025, 1, 29),
    dt.date(2025, 3, 19),
    dt.date(2025, 5, 7),
    dt.date(2025, 6, 18),
    dt.date(2025, 7, 30),
    dt.date(2025, 9, 17),
    dt.date(2025, 10, 29),
    dt.date(2025, 12, 10),
    dt.date(2026, 1, 28),
    dt.date(2026, 3, 18),
    dt.date(2026, 4, 29),
]

ENTRY_GATE = (dt.time(9, 35), dt.time(10, 0))   # morning entry window
HARD_EXIT = dt.time(13, 55)                       # 5 min before 14:00 print
SWING_LOOKBACK = 12                               # bars for the chart-stop swing low
QTY = 3
STRIKE_OFFSET = -1   # ITM-1 for calls (survivor profile: ITM strike); ATM=0
PREMIUM_STOP = CHART_STOP_ONLY_PCT  # -0.99 = chart-stop-only (C2: NO premium stop)
OOS_START = dt.date(2026, 1, 1)


def _rth(spy: pd.DataFrame) -> pd.DataFrame:
    """RTH-only frame with reset RangeIndex + tz-naive timestamp_et."""
    df = spy.copy()
    ts = pd.to_datetime(df["timestamp_et"], utc=True, errors="coerce")
    df = df.dropna(subset=[df.columns[df.columns.get_loc("timestamp_et")]])
    ts = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
    df["timestamp_et"] = ts
    df = df.dropna(subset=["timestamp_et"])
    t = df["timestamp_et"].dt.time
    df = df[(t >= dt.time(9, 30)) & (t <= dt.time(16, 0))]
    return df.sort_values("timestamp_et").reset_index(drop=True)


def _prior_close(rth: pd.DataFrame, day: dt.date) -> float | None:
    """Prior-session close = last RTH bar before ``day``."""
    before = rth[rth["timestamp_et"].dt.date < day]
    if before.empty:
        return None
    return float(before.iloc[-1]["close"])


def _vix_rising(vix: pd.DataFrame, day: dt.date) -> bool:
    """True if VIX at the morning gate is above the prior-day VIX close (rising stress)."""
    if vix is None or "close" not in vix.columns:
        return False
    vts = pd.to_datetime(vix["timestamp_et"], utc=True, errors="coerce")
    v = vix.copy()
    v["_d"] = vts.dt.tz_convert("America/New_York").dt.tz_localize(None)
    prior = v[v["_d"].dt.date < day]
    today = v[(v["_d"].dt.date == day) & (v["_d"].dt.time <= dt.time(10, 0))]
    if prior.empty or today.empty:
        return False
    return float(today.iloc[-1]["close"]) > float(prior.iloc[-1]["close"])


def _build_signals(rth: pd.DataFrame, vix: pd.DataFrame) -> list[CandidateSignal]:
    """One CALL entry per testable FOMC day: trigger at the first bar inside the morning
    gate; skip the risk-off-slide days (SPY < prior close by >0.4% AND VIX rising).
    rejection_level = trailing 12-bar swing low (the chart-stop, C2)."""
    signals: list[CandidateSignal] = []
    by_day = {d: g for d, g in rth.groupby(rth["timestamp_et"].dt.date)}
    for day in FOMC_DAYS:
        g = by_day.get(day)
        if g is None or g.empty:
            continue
        gate = g[(g["timestamp_et"].dt.time >= ENTRY_GATE[0])
                 & (g["timestamp_et"].dt.time <= ENTRY_GATE[1])]
        if gate.empty:
            continue
        entry_row = gate.iloc[0]
        bar_idx = int(entry_row.name)  # positional index in rth (reset RangeIndex)

        # CONDITIONING skip: sharp risk-off slide already in progress.
        pc = _prior_close(rth, day)
        spot = float(entry_row["close"])
        slide = pc is not None and (spot - pc) / pc < -0.004
        if slide and _vix_rising(vix, day):
            continue

        lo = max(0, bar_idx - SWING_LOOKBACK + 1)
        swing_low = float(rth.iloc[lo:bar_idx + 1]["low"].min())
        rej = swing_low if swing_low < spot else spot - 1.0
        signals.append(CandidateSignal(
            bar_idx=bar_idx, side="C", rejection_level=round(rej, 2),
            note="pre_fomc_drift"))
    return signals


def _simulate(signals, rth, *, strike_offset, premium_stop_pct, setup):
    """Re-run signals through real OPRA fills with the 13:55 hard exit. Returns
    {day: [dollar_pnl,...]} (skips days with no cached OPRA bars)."""
    from lib.simulator_real import simulate_trade_real
    by_day: dict[str, list[float]] = defaultdict(list)
    for sg in signals:
        entry_bar = rth.iloc[sg.bar_idx]
        day = entry_bar["timestamp_et"].date().isoformat()
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=entry_bar, spy_df=rth,
            ribbon_df=None, rejection_level=round(float(sg.rejection_level), 2),
            triggers_fired=[sg.note], side=sg.side, qty=QTY, setup=setup,
            premium_stop_pct=premium_stop_pct, strike_offset=strike_offset,
            time_stop_et=HARD_EXIT)  # hard exit 13:55 ET, BEFORE the 14:00 print
        if fill is None or getattr(fill, "dollar_pnl", None) is None:
            continue
        by_day[day].append(float(fill.dollar_pnl))
    return by_day


def _stats(by_day):
    all_p = [p for v in by_day.values() for p in v]
    n = len(all_p)
    if n == 0:
        return {"n": 0}
    total = sum(all_p)
    per_trade = total / n
    day_tot = {d: sum(v) for d, v in by_day.items()}
    top5 = set(d for d, _ in sorted(day_tot.items(), key=lambda kv: kv[1],
                                    reverse=True)[:5])
    kept = [p for d, v in by_day.items() if d not in top5 for p in v]
    drop5 = (sum(kept) / len(kept)) if kept else None
    top5_sum = sum(day_tot[d] for d in top5)
    # Concentration vs gross positive P&L (robust when net total is <=0).
    gross_pos = sum(s for s in day_tot.values() if s > 0)
    top5_pct = (top5_sum / gross_pos * 100.0) if gross_pos > 0 else None
    return {
        "n": n, "total": round(total, 2), "per_trade": round(per_trade, 2),
        "drop_top5_per_trade": round(drop5, 2) if drop5 is not None else None,
        "top5_day_pct": round(top5_pct, 1) if top5_pct is not None else None,
        "days": {d: round(s, 2) for d, s in sorted(day_tot.items())},
    }


def _quarters(by_day):
    """positive_quarters / n_quarters: quarters (calendar) that traded and are net +."""
    q_tot = defaultdict(float)
    q_traded = set()
    for d, v in by_day.items():
        date = dt.date.fromisoformat(d)
        q = f"{date.year}Q{(date.month - 1) // 3 + 1}"
        q_tot[q] += sum(v)
        q_traded.add(q)
    pos = sum(1 for q in q_traded if q_tot[q] > 0)
    return pos, len(q_traded)


def main():
    spy, vix = load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 29))
    rth = _rth(spy)
    signals = _build_signals(rth, vix)

    setup = "PRE_FOMC_DRIFT"
    by_day = _simulate(signals, rth, strike_offset=STRIKE_OFFSET,
                       premium_stop_pct=PREMIUM_STOP, setup=setup)
    st = _stats(by_day)

    # OOS subset (2026 FOMC days)
    oos_by_day = {d: v for d, v in by_day.items()
                  if dt.date.fromisoformat(d) >= OOS_START}
    oos = _stats(oos_by_day)

    pos_q, n_q = _quarters(by_day)

    # ── GRADUATED FRAUD GATES (truncation + random-null) via the shared module.
    # verify_candidate re-sims chosen cell, chart-stop-only sibling, AND the null.
    # Note: chosen cell IS chart-stop-only here (C2), so truncation is trivially clean;
    # we still run it through the standard gate for disclosure.
    fv = verify_candidate(
        signals, rth, strike_offset=STRIKE_OFFSET, premium_stop_pct=PREMIUM_STOP,
        qty=QTY, setup=setup)

    # Standalone null (matched count + side mix) for the report numbers.
    n_call = sum(1 for s in signals if s.side == "C")
    n_put = sum(1 for s in signals if s.side == "P")
    null = random_entry_null(
        rth, n_signals=st.get("n", 0) or len(signals), n_call=n_call, n_put=n_put,
        strike_offset=STRIKE_OFFSET, premium_stop_pct=PREMIUM_STOP, qty=QTY,
        setup=f"{setup}_NULL", seeds=20,
        entry_gate=(dt.time(9, 35), dt.time(13, 50)))
    ng = null_gate(st.get("per_trade"), st.get("drop_top5_per_trade"), null)

    # ── THE 8 GATES ──────────────────────────────────────────────────────────
    gates = {}
    gates["1_OOS_positive"] = (oos.get("per_trade") is not None
                               and oos.get("per_trade") > 0)
    gates["2_quarters_4of6"] = (n_q > 0 and pos_q / 6.0 >= 4 / 6 - 1e-9)
    gates["3_conc_top5_lt200"] = (st.get("top5_day_pct") is not None
                                  and st.get("top5_day_pct") < 200)
    gates["4_n_ge20"] = st.get("n", 0) >= 20
    gates["5_drop_top5_positive"] = (st.get("drop_top5_per_trade") is not None
                                     and st.get("drop_top5_per_trade") > 0)
    gates["6_no_truncation"] = bool(fv.no_truncation_pass)
    gates["7_beats_null"] = bool(ng.get("null_pass"))
    gates["8_oos_n_ge20"] = oos.get("n", 0) >= 20

    passed = sum(1 for v in gates.values() if v)
    all_pass = all(gates.values())

    # Death cause (first material failure, plainly named).
    death = None
    if not all_pass:
        if st.get("n", 0) < 20:
            death = (f"insufficient-N: only {st.get('n',0)} real-fill trades "
                     f"(~8 FOMC days/yr; OPRA window yields ~11 days max -- a calendar "
                     f"strategy can never reach the n>=20 statistical bar on 0DTE "
                     f"real-fills). Sample too small to claim an edge.")
        elif not gates["1_OOS_positive"]:
            death = f"OOS-negative: 2026 FOMC days per-trade=${oos.get('per_trade')}"
        elif not gates["7_beats_null"]:
            death = ("random-null-fail: a coin-flip morning CALL reproduces the "
                     "per-trade -> the v15 exit bracket, not the FOMC-drift signal, "
                     "is the edge (C3/L58/L172)")
        elif not gates["6_no_truncation"]:
            death = "truncation-artifact (L171)"
        else:
            failed = [k for k, v in gates.items() if not v]
            death = "failed: " + ", ".join(failed)

    verdict = "EDGE" if all_pass else ("LEAD" if passed >= 6 else "DEAD")

    result = {
        "slug": "pre-fomc-announcement-drift",
        "arena": "0dte",
        "section": "B6-EXTERNAL",
        "built": True,
        "ran": True,
        "verdict": verdict,
        "gates_passed": f"{passed}/8",
        "gates": gates,
        "config": {
            "strike_offset": STRIKE_OFFSET, "strike_tier": "ITM-1",
            "premium_stop_pct": PREMIUM_STOP, "stop": "chart-stop-only (C2)",
            "entry_gate": "09:35-10:00 ET", "hard_exit": "13:55 ET (pre-print)",
            "qty": QTY,
        },
        "fomc_days_tested": [d.isoformat() for d in FOMC_DAYS],
        "n_signals_generated": len(signals),
        "overall": st,
        "OOS_2026": oos,
        "positive_quarters": f"{pos_q}/{n_q}",
        "null": null,
        "null_gate": ng,
        "fraud_verdict": fv.as_dict(),
        "death_cause": death,
        "note": ("Sourced external strategy run on REAL OPRA fills (lib.simulator_real, "
                 "C1) with the survivor structure (ITM-1 + morning entry) and the "
                 "strategy's own 13:55 pre-print hard exit + chart-stop-only (C2). "
                 "8 fraud-gates incl OOS-positive + beats-null + no-truncation."),
    }

    # Print the real table.
    print("=" * 78)
    print("B6-EXTERNAL :: pre-fomc-announcement-drift :: REAL-FILLS 8-GATE")
    print("=" * 78)
    print(f"signals generated     : {len(signals)} (testable FOMC days in OPRA window)")
    print(f"real-fill trades (n)  : {st.get('n', 0)}")
    print(f"overall per-trade     : ${st.get('per_trade')}  total ${st.get('total')}")
    print(f"OOS(2026) per-trade   : ${oos.get('per_trade')}  n={oos.get('n',0)}")
    print(f"drop-top5 per-trade   : ${st.get('drop_top5_per_trade')}")
    print(f"top5-day conc         : {st.get('top5_day_pct')}%")
    print(f"positive quarters     : {pos_q}/{n_q}")
    print(f"random-null max/mean  : ${null.get('per_trade_max')}/${null.get('per_trade_mean')}")
    print(f"per-day P&L           : {st.get('days')}")
    print("-" * 78)
    for k, v in gates.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    print("-" * 78)
    print(f"VERDICT: {verdict}   ({passed}/8 gates)")
    if death:
        print(f"DEATH CAUSE: {death}")
    print("=" * 78)

    out = ROOT / "analysis" / "recommendations" / "pre-fomc-announcement-drift.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"-> {out}")
    return result


if __name__ == "__main__":
    main()
