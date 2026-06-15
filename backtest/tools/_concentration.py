"""Equity-curve concentration check for G_NO_midday_trendline gate.
Top-5-day %, monthly P&L, positive-month rate. Writes result to _concentration.json."""
from __future__ import annotations
import sys, json, datetime as dt
from pathlib import Path
from collections import defaultdict, Counter
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import sniper_matrix as SM

DATA = REPO / "data"
ABT = REPO.parent / "analysis" / "backtests"


def main():
    cands = [p for p in DATA.glob("spy_5m_*.csv") if (DATA / p.name.replace("spy_5m", "vix_5m")).exists()]
    cands.sort(key=lambda p: p.stat().st_size, reverse=True)
    master = cands[0]
    spy = SM.norm_str(pd.read_csv(master)); vix = SM.norm_str(pd.read_csv(DATA / master.name.replace("spy_5m", "vix_5m")))
    missed = {dt.date(2026, 5, 26), dt.date(2026, 5, 27), dt.date(2026, 5, 28), dt.date(2026, 5, 29)}
    spy_dates = set(SM._to_et(pd.read_csv(master)["timestamp_et"]).dt.date)
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    fill_days = sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})
    oos = sorted([d for d in fill_days if d in spy_dates and d not in missed])

    r = SM.run_backtest(spy, vix, start_date=min(oos), end_date=max(oos),
                        use_real_fills=True, no_trade_before=dt.time(9, 35))
    trades = [t for t in r.trades if t.entry_time_et.date() in set(oos) and "FALLBACK" not in t.setup]
    assert len(trades) >= 20, f"GUARD: {len(trades)} trades"

    def is_mt(t):
        return (dt.time(11, 30) <= t.entry_time_et.time() < dt.time(14, 0) and
                len(t.triggers_fired) == 1 and "trendline_rejection" in t.triggers_fired)

    gated = [t for t in trades if not is_mt(t)]

    day_pnl: dict[str, float] = defaultdict(float)
    for t in gated:
        day_pnl[t.entry_time_et.date().isoformat()] += t.dollar_pnl / max(1, t.qty)

    total = sum(day_pnl.values())
    top5 = sorted(day_pnl.values(), reverse=True)[:5]
    top5_pct = sum(top5) / total * 100 if total > 0 else 0

    monthly: dict[str, float] = defaultdict(float)
    for d, v in day_pnl.items():
        monthly[d[:7]] += v
    pos_months = sum(1 for v in monthly.values() if v > 0)

    out = {
        "n_gated": len(gated), "total_pc": round(total, 0),
        "top5_days": [round(v, 1) for v in top5],
        "top5_pct": round(top5_pct, 1),
        "monthly": dict(sorted(monthly.items())),
        "positive_months": pos_months, "total_months": len(monthly),
        "verdict": ("LOW (<50%)" if top5_pct < 50 else
                    "MODERATE (50-80%)" if top5_pct < 80 else "HIGH-CONCENTRATION (>80%)"),
    }
    (ABT / "_concentration.json").write_text(json.dumps(out, indent=2))
    print(f"n={len(gated)} total={total:+.0f}/c top5={top5_pct:.1f}% verdict={out['verdict']}")
    print(f"positive months: {pos_months}/{len(monthly)}")
    for m, v in sorted(monthly.items()):
        print(f"  {m}: {v:+.0f}")
    print("wrote _concentration.json")


if __name__ == "__main__":
    raise SystemExit(main())
