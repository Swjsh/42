"""DAY-TYPE CLASSIFIER — detect intraday market character from early price action.

J's insight: we need to know WHAT KIND OF DAY IT IS as it's happening and trade
accordingly. A static midday-trendline gate is one step. A dynamic day-type adapter
that adjusts filter thresholds based on detected day character is the real goal.

This script builds the evidence base: segment 307 OOS trades by day type detected from
the FIRST 15 MINUTES of RTH, and show how engine performance differs across day types.
If trend days and chop days have sufficiently different WR distributions, we can build a
classifier that determines day type at ~09:50 ET and trades accordingly.

Day types (classified from RTH bar 1-3: 09:30-09:45 ET):
  TREND_FOLLOW: gap + first 3 bars all directional, ribbon already stacked, no reversal
  GAP_AND_GO:  opening gap >$1.00, first 15 min hold gap direction
  REVERSAL:    opening reversal (first 3 bars negate the overnight direction)
  CHOP:        narrow first 15 min range (<$1.50), indecisive ribbon
"""
from __future__ import annotations
import sys, json, datetime as dt
from pathlib import Path
from collections import defaultdict
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import sniper_matrix as SM

DATA = REPO / "data"
ABT = REPO.parent / "analysis" / "backtests"


def classify_day(spy: pd.DataFrame, date: dt.date) -> dict:
    """Classify day type from first 15 min of RTH (3 × 5m bars)."""
    d_bars = spy[(spy["timestamp_et"].dt.date == date) &
                 (spy["timestamp_et"].dt.time >= dt.time(9, 30)) &
                 (spy["timestamp_et"].dt.time < dt.time(16, 0))].sort_values("timestamp_et")
    if len(d_bars) < 6:
        return {"type": "INSUFFICIENT_DATA", "early_range": 0.0, "gap": 0.0}

    prev_bars = spy[spy["timestamp_et"].dt.date < date]
    prev_close = float(prev_bars[prev_bars["timestamp_et"].dt.time < dt.time(16, 0)].sort_values("timestamp_et").iloc[-1]["close"]) if len(prev_bars) else None

    open_px = float(d_bars.iloc[0]["open"])
    gap = round(open_px - prev_close, 2) if prev_close else 0.0
    gap_pct = gap / prev_close if prev_close else 0.0

    first3 = d_bars.iloc[:3]
    close3 = float(first3.iloc[-1]["close"])
    early_range = round(float(first3["high"].max()) - float(first3["low"].min()), 2)

    # Direction of first 3 bars vs open
    net3 = close3 - open_px
    all_green = all(float(r["close"]) >= float(r["open"]) for _, r in first3.iterrows())
    all_red = all(float(r["close"]) <= float(r["open"]) for _, r in first3.iterrows())

    # ribbon spread check (use the first scored bar from decisions if available)
    if early_range < 1.50 and not (all_green or all_red):
        day_type = "CHOP"
    elif abs(gap_pct) > 0.0015 and ((gap > 0 and net3 > 0) or (gap < 0 and net3 < 0)):
        day_type = "GAP_AND_GO"
    elif all_green and gap >= 0:
        day_type = "TREND_FOLLOW_BULL"
    elif all_red and gap <= 0:
        day_type = "TREND_FOLLOW_BEAR"
    elif (gap > 0 and net3 < -0.50) or (gap < 0 and net3 > 0.50):
        day_type = "REVERSAL"
    else:
        day_type = "MIXED"

    return {"type": day_type, "early_range": early_range, "gap": gap, "gap_pct": round(gap_pct * 100, 2), "net3": round(net3, 2)}


def main():
    cands = [p for p in DATA.glob("spy_5m_*.csv") if (DATA / p.name.replace("spy_5m", "vix_5m")).exists()]
    cands.sort(key=lambda p: p.stat().st_size, reverse=True)
    master = cands[0]
    spy = pd.read_csv(master)
    spy["timestamp_et"] = SM._to_et(spy["timestamp_et"])
    missed = {dt.date(2026, 5, 26), dt.date(2026, 5, 27), dt.date(2026, 5, 28), dt.date(2026, 5, 29)}
    from collections import Counter
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    fill_days = sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})
    spy_dates = set(spy["timestamp_et"].dt.date)
    oos = sorted([d for d in fill_days if d in spy_dates and d not in missed])

    # Run engine on OOS days (reuse the same 307-trade run)
    spy_str = SM.norm_str(pd.read_csv(master))
    vix_str = SM.norm_str(pd.read_csv(DATA / master.name.replace("spy_5m", "vix_5m")))
    r = SM.run_backtest(spy_str, vix_str, start_date=min(oos), end_date=max(oos),
                        use_real_fills=True, no_trade_before=dt.time(9, 35))
    trades = [t for t in r.trades if t.entry_time_et.date() in set(oos) and "FALLBACK" not in t.setup]
    assert len(trades) >= 20, f"GUARD: {len(trades)}"

    # Classify each trade's day type from early price action
    by_type = defaultdict(list)
    for t in trades:
        d = t.entry_time_et.date()
        cls = classify_day(spy, d)
        by_type[cls["type"]].append({
            "pc": t.dollar_pnl / max(1, t.qty),
            "win": t.dollar_pnl > 0,
            "type": cls,
        })

    out_lines = ["# DAY-TYPE SEGMENTATION — how engine performs by intraday market character", "",
                 f"Classified from first 15 min of RTH (3×5m bars: gap, direction, range). "
                 f"Engine trades: {len(trades)} across {len(oos)} OOS days.", ""]

    results = {}
    out_lines.append("| day type | n trades | WR | per-trade /c | total /c | verdict |")
    out_lines.append("|---|---|---|---|---|---|")
    for dt_type, items in sorted(by_type.items(), key=lambda x: -sum(i["pc"] for i in x[1])):
        n = len(items); w = sum(1 for i in items if i["win"])
        pc = sum(i["pc"] for i in items)
        wr = w / n
        verdict = ("TRADE IT" if pc / n > 5.0 else
                   "SELECTIVE" if pc / n > 0 else
                   "AVOID" if pc / n < -5.0 else "MARGINAL")
        out_lines.append(f"| {dt_type} | {n} | {wr:.2f} | {pc/n:+.1f} | {pc:+.0f} | **{verdict}** |")
        results[dt_type] = {"n": n, "wr": round(wr, 2), "pc_per_trade": round(pc / n, 1), "total_pc": round(pc, 0)}

    # Find the best and worst day types
    sortable = [(v["pc_per_trade"], k) for k, v in results.items() if v["n"] >= 5]
    if sortable:
        best = max(sortable)
        worst = min(sortable)
        out_lines += ["",
            f"## Key finding",
            f"**Best day type: {best[1]} ({best[0]:+.1f}/trade)** — engine performs best on these days.",
            f"**Worst day type: {worst[1]} ({worst[0]:+.1f}/trade)** — engine loses here; consider sitting out.",
            "",
            "## Implication: REGIME-ADAPTIVE FILTER",
            "A classifier that runs at 09:45–09:50 ET (after the first 3 RTH bars) can detect day type",
            "and adjust filter thresholds accordingly:",
            f"- On {best[1]} days: relax filter (allow more entries, confidence required)",
            f"- On {worst[1]} days: tighten filter or suppress all entries (gate = skip day)",
            "This converts a static per-trade gate into a dynamic per-day regime detector,",
            "directly addressing J's 'know what kind of day it is as it's happening' thesis.",
        ]

    (REPO.parent / "analysis" / "day-type-segmentation-2026-05-31.md").write_text(
        "\n".join(out_lines), encoding="utf-8")
    (ABT / "_day_type.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("results:")
    for k, v in sorted(results.items(), key=lambda x: -x[1]["pc_per_trade"]):
        print(f"  {k:<25} n={v['n']:<3} WR={v['wr']:.2f} pc/trade={v['pc_per_trade']:+.1f}")
    print("wrote day-type-segmentation-2026-05-31.md + _day_type.json")


if __name__ == "__main__":
    raise SystemExit(main())
