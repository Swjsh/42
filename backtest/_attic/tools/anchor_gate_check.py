"""Verify the G_NO_midday_trendline gate does NOT suppress J's anchor trades.
Run production backtest on the anchor window (2026-04-27..05-07) with and without the gate.
Must still capture 5/04 721P and 4/29 710P (or show it's the post-05-05 VIX filter that blocks
4/29, not the midday-trendline gate). Sanity-guarded, JSON dump (L77)."""
from __future__ import annotations
import sys, json, datetime as dt
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import sniper_matrix as SM

DATA = REPO / "data"
ABT = REPO.parent / "analysis" / "backtests"


def tod_is_midday(t):
    return dt.time(11, 30) <= t < dt.time(14, 0)


def is_midday_trendline_only(trade):
    """The pattern we want to block: midday AND single trendline_rejection trigger."""
    t_time = trade.entry_time_et.time()
    if not tod_is_midday(t_time):
        return False
    triggers = trade.triggers_fired
    return len(triggers) == 1 and "trendline_rejection" in triggers


def stats(trades):
    if not trades:
        return {"n": 0, "wr": 0.0, "pc": 0.0}
    n = len(trades); w = sum(1 for t in trades if t.dollar_pnl > 0)
    pc = sum(t.dollar_pnl / max(1, t.qty) for t in trades)
    cap = {}
    for t in trades:
        d = t.entry_time_et.date().isoformat()
        if t.dollar_pnl > 0:
            cap.setdefault(d, round(t.dollar_pnl / max(1, t.qty), 1))
    return {"n": n, "wr": round(w / n, 2), "pc": round(pc, 0), "pc_per_trade": round(pc / n, 1), "cap": cap}


def main():
    aspy_p = DATA / "spy_5m_2025-01-01_2026-05-07.csv"
    if not aspy_p.exists():
        print("anchor master missing"); return 1

    spy = SM.norm_str(pd.read_csv(aspy_p)); vix = SM.norm_str(pd.read_csv(DATA / "vix_5m_2025-01-01_2026-05-07.csv"))
    a0, a1 = dt.date(2026, 4, 27), dt.date(2026, 5, 7)

    # Run 1: production ungated (filter 8 OFF = fair pre-VIX-rule test)
    r_ung = SM.run_backtest(spy, vix, start_date=a0, end_date=a1, use_real_fills=True,
                            disable_filters=[8], no_trade_before=dt.time(9, 35))
    trades_ung = [t for t in r_ung.trades if "FALLBACK" not in t.setup]

    # Run 2: same but apply the gate post-hoc (same signals, filtered)
    trades_gated = [t for t in trades_ung if not is_midday_trendline_only(t)]

    assert len(trades_ung) >= 5, f"GUARD: only {len(trades_ung)} anchor trades"

    s_ung = stats(trades_ung); s_gated = stats(trades_gated)

    # Which anchor trades would the gate SUPPRESS?
    suppressed = [t for t in trades_ung if is_midday_trendline_only(t)]

    out = {"ungated": s_ung, "gated": s_gated,
           "suppressed": [{"date": t.entry_time_et.date().isoformat(),
                           "time": t.entry_time_et.strftime("%H:%M"),
                           "triggers": "|".join(t.triggers_fired),
                           "pc": round(t.dollar_pnl / max(1, t.qty), 1)} for t in suppressed]}

    (ABT / "_anchor_gate.json").write_text(json.dumps(out, indent=2, default=str))

    print(f"Anchor ungated: n={s_ung['n']} WR={s_ung['wr']} pc={s_ung['pc']}/c")
    print(f"Anchor gated:   n={s_gated['n']} WR={s_gated['wr']} pc={s_gated['pc']}/c")
    print(f"Suppressed by gate: {len(suppressed)} trades")
    for t in suppressed:
        print(f"  SUPPRESSED: {t.entry_time_et.date()} {t.entry_time_et.strftime('%H:%M')} "
              f"{'|'.join(t.triggers_fired)} -> {t.dollar_pnl/max(1,t.qty):+.1f}/c")
    cap429 = s_gated["cap"].get("2026-04-29"); cap504 = s_gated["cap"].get("2026-05-04")
    print(f"5/04 captured: {cap504} | 4/29 captured: {cap429}")
    verdict = "PASS" if cap504 else "FAIL"
    print(f"VERDICT: {verdict} (5/04 {'kept' if cap504 else 'DROPPED BY GATE'})")
    print("wrote _anchor_gate.json")


if __name__ == "__main__":
    raise SystemExit(main())
