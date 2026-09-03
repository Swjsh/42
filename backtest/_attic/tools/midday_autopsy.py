"""MIDDAY AUTOPSY — the 33 midday trades (WR 0.24, −8.6/trade) are killing the OOS P&L.
What specifically distinguishes the 8 midday winners from the 25 losers?
Also: cross-validate the selectivity gate on the BEAR-only anchor window (do the
confluence/>=2-trig gates help BEARISH_REJECTION specifically?).
Sanity-guarded, JSON-dump, no doctrine edits."""
from __future__ import annotations
import sys, json, datetime as dt
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import sniper_matrix as SM

DATA = REPO / "data"
ABT = REPO.parent / "analysis" / "backtests"


def cached_fill_days():
    from collections import Counter
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    return sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})


def tod(t):
    if t < dt.time(10, 15): return "OPEN_DRIVE"
    if t < dt.time(11, 30): return "MORNING"
    if t < dt.time(14, 0): return "MIDDAY"
    if t < dt.time(15, 15): return "AFTERNOON"
    return "POWER_HOUR"


def agg_rows(trades):
    return [{"time": t.entry_time_et.strftime("%H:%M"),
             "setup": t.setup[:30],
             "side": "C" if "BULLISH" in t.setup else "P",
             "triggers": "|".join(t.triggers_fired),
             "ntrig": len(t.triggers_fired),
             "has_conf": "confluence" in t.triggers_fired,
             "level": round(t.rejection_level, 2) if t.rejection_level else None,
             "entry_px": round(t.entry_premium, 2),
             "pc": round(t.dollar_pnl / max(1, t.qty), 1),
             "exit": t.exit_reason.value if t.exit_reason else "?",
             "win": t.dollar_pnl > 0}
            for t in trades]


def main():
    cands = [p for p in DATA.glob("spy_5m_*.csv") if (DATA / p.name.replace("spy_5m", "vix_5m")).exists()]
    cands.sort(key=lambda p: p.stat().st_size, reverse=True)
    master = cands[0]
    spy = SM.norm_str(pd.read_csv(master)); vix = SM.norm_str(pd.read_csv(DATA / master.name.replace("spy_5m", "vix_5m")))
    missed = {dt.date(2026, 5, 26), dt.date(2026, 5, 27), dt.date(2026, 5, 28), dt.date(2026, 5, 29)}
    spy_dates = set(SM._to_et(pd.read_csv(master)["timestamp_et"]).dt.date)
    oos = sorted([d for d in cached_fill_days() if d in spy_dates and d not in missed])[-60:]

    r = SM.run_backtest(spy, vix, start_date=min(oos), end_date=max(oos),
                        use_real_fills=True, no_trade_before=dt.time(9, 35))
    trades = [t for t in r.trades if t.entry_time_et.date() in set(oos)
              and "FALLBACK" not in t.setup]  # exclude BS_FALLBACK (not real fills)
    assert len(trades) >= 20, f"GUARD: {len(trades)} trades"

    midday = [t for t in trades if tod(t.entry_time_et.time()) == "MIDDAY"]
    mid_w = [t for t in midday if t.dollar_pnl > 0]
    mid_l = [t for t in midday if t.dollar_pnl <= 0]

    out = {
        "n_real_fills_trades": len(trades),
        "midday_n": len(midday),
        "midday_wr": round(len(mid_w) / len(midday), 2) if midday else 0,
        "midday_pc": round(sum(t.dollar_pnl / max(1, t.qty) for t in midday), 0),
        "midday_pc_per_trade": round(sum(t.dollar_pnl / max(1, t.qty) for t in midday) / len(midday), 1) if midday else 0,
        "midday_winners": agg_rows(mid_w),
        "midday_losers": agg_rows(mid_l),
        # trigger profile of midday losers vs winners
        "midday_losers_avg_ntrig": round(sum(len(t.triggers_fired) for t in mid_l) / len(mid_l), 2) if mid_l else 0,
        "midday_winners_avg_ntrig": round(sum(len(t.triggers_fired) for t in mid_w) / len(mid_w), 2) if mid_w else 0,
        "midday_losers_conf_pct": round(sum(1 for t in mid_l if "confluence" in t.triggers_fired) / len(mid_l), 2) if mid_l else 0,
        "midday_winners_conf_pct": round(sum(1 for t in mid_w if "confluence" in t.triggers_fired) / len(mid_w), 2) if mid_w else 0,
        # gate applied to midday only
        "midday_with_conf": len([t for t in midday if "confluence" in t.triggers_fired]),
        "midday_with_conf_pc": round(sum(t.dollar_pnl / max(1, t.qty) for t in midday if "confluence" in t.triggers_fired), 1),
        "midday_no_conf_pc": round(sum(t.dollar_pnl / max(1, t.qty) for t in midday if "confluence" not in t.triggers_fired), 1),
        "midday_ge2trig_n": len([t for t in midday if len(t.triggers_fired) >= 2]),
        "midday_ge2trig_pc": round(sum(t.dollar_pnl / max(1, t.qty) for t in midday if len(t.triggers_fired) >= 2), 1),
        "midday_1trig_pc": round(sum(t.dollar_pnl / max(1, t.qty) for t in midday if len(t.triggers_fired) < 2), 1),
    }

    (ABT / "_midday_autopsy.json").write_text(json.dumps(out, indent=2, default=str))

    lines = ["# MIDDAY AUTOPSY — why the 33 midday trades bleed (real fills only, no BS_FALLBACK)", "",
             f"**{len(midday)} midday real-fills trades**, WR {out['midday_wr']}, "
             f"{out['midday_pc_per_trade']:+.1f}/trade (total {out['midday_pc']:+.0f}/c)", "",
             "## Trigger profile: winners vs losers",
             f"| metric | winners (n={len(mid_w)}) | losers (n={len(mid_l)}) |",
             "|---|---|---|",
             f"| avg triggers | {out['midday_winners_avg_ntrig']} | {out['midday_losers_avg_ntrig']} |",
             f"| % with confluence | {out['midday_winners_conf_pct']:.0%} | {out['midday_losers_conf_pct']:.0%} |",
             "",
             "## Selectivity gate applied to midday ONLY",
             f"- midday with confluence: n={out['midday_with_conf']}, total {out['midday_with_conf_pc']:+.0f}/c",
             f"- midday without confluence: n={len(midday)-out['midday_with_conf']}, total {out['midday_no_conf_pc']:+.0f}/c",
             f"- midday >=2 triggers: n={out['midday_ge2trig_n']}, total {out['midday_ge2trig_pc']:+.0f}/c",
             f"- midday 1-trigger: n={len(midday)-out['midday_ge2trig_n']}, total {out['midday_1trig_pc']:+.0f}/c",
             "",
             "## Midday WINNERS (all real fills)",
             "| time | setup | triggers | px | pc | exit |",
             "|---|---|---|---|---|---|"]
    for r2 in sorted(out["midday_winners"], key=lambda x: x["pc"], reverse=True):
        lines.append(f"| {r2['time']} | {r2['setup'][:25]} | {r2['triggers'][:20]} | {r2['entry_px']} | {r2['pc']:+.1f} | {r2['exit']} |")
    lines += ["", "## Midday LOSERS (all real fills)",
              "| time | setup | triggers | px | pc | exit |",
              "|---|---|---|---|---|---|"]
    for r2 in sorted(out["midday_losers"], key=lambda x: x["pc"]):
        lines.append(f"| {r2['time']} | {r2['setup'][:25]} | {r2['triggers'][:20]} | {r2['entry_px']} | {r2['pc']:+.1f} | {r2['exit']} |")

    (REPO.parent / "analysis" / "midday-autopsy-2026-05-31.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"midday n={len(midday)} WR={out['midday_wr']} pc/trade={out['midday_pc_per_trade']}")
    print(f"  midday with conf: n={out['midday_with_conf']} pc={out['midday_with_conf_pc']:+.0f}")
    print(f"  midday no conf: n={len(midday)-out['midday_with_conf']} pc={out['midday_no_conf_pc']:+.0f}")
    print(f"  midday >=2 trig: n={out['midday_ge2trig_n']} pc={out['midday_ge2trig_pc']:+.0f}")
    print(f"  midday 1-trig: n={len(midday)-out['midday_ge2trig_n']} pc={out['midday_1trig_pc']:+.0f}")
    print("wrote analysis/midday-autopsy-2026-05-31.md + _midday_autopsy.json")


if __name__ == "__main__":
    raise SystemExit(main())
