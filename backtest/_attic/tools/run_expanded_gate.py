"""Re-run gate_test with the newly-fetched OPRA grids (more OOS days).
Identical logic to gate_test.py but discovers ALL now-cached days instead of the prior 60.
Sanity-guarded, JSON-dump, single combined runner (cascade-proof).
Also adds a TRENDLINE-MIDDAY gate specifically targeting the pattern the autopsy exposed."""
from __future__ import annotations
import sys, json, datetime as dt
from pathlib import Path
from collections import Counter
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import sniper_matrix as SM

DATA = REPO / "data"
ABT = REPO.parent / "analysis" / "backtests"


def cached_fill_days():
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    return sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})


def tod(t):
    if t < dt.time(10, 15): return "OPEN_DRIVE"
    if t < dt.time(11, 30): return "MORNING"
    if t < dt.time(14, 0): return "MIDDAY"
    if t < dt.time(15, 15): return "AFTERNOON"
    return "POWER_HOUR"


def stats(trades):
    if not trades:
        return {"n": 0, "wr": 0.0, "pc": 0.0, "pc_per_trade": 0.0}
    n = len(trades)
    w = sum(1 for t in trades if t.dollar_pnl > 0)
    pc = sum(t.dollar_pnl / max(1, t.qty) for t in trades)
    return {"n": n, "wr": round(w / n, 2), "pc": round(pc, 0), "pc_per_trade": round(pc / n, 1)}


def main():
    cands = [p for p in DATA.glob("spy_5m_*.csv") if (DATA / p.name.replace("spy_5m", "vix_5m")).exists()]
    cands.sort(key=lambda p: p.stat().st_size, reverse=True)
    master = cands[0]
    spy = SM.norm_str(pd.read_csv(master)); vix = SM.norm_str(pd.read_csv(DATA / master.name.replace("spy_5m", "vix_5m")))
    missed = {dt.date(2026, 5, 26), dt.date(2026, 5, 27), dt.date(2026, 5, 28), dt.date(2026, 5, 29)}
    spy_dates = set(SM._to_et(pd.read_csv(master)["timestamp_et"]).dt.date)
    # Use ALL cached days (not capped at 60) now that we have more
    all_cached = [d for d in cached_fill_days() if d in spy_dates and d not in missed]
    oos = sorted(all_cached)

    print(f"Running on {len(oos)} OOS cached-fill days ({oos[0] if oos else '-'}..{oos[-1] if oos else '-'})")
    r = SM.run_backtest(spy, vix, start_date=min(oos), end_date=max(oos),
                        use_real_fills=True, no_trade_before=dt.time(9, 35))
    trades = [t for t in r.trades if t.entry_time_et.date() in set(oos)
              and "FALLBACK" not in t.setup]  # exclude BS_FALLBACK (not real fills)
    assert len(trades) >= 20, f"GUARD: {len(trades)} trades, expected >=20"
    print(f"Real-fills trades: {len(trades)}, WR {sum(1 for t in trades if t.dollar_pnl>0)/len(trades):.2f}")

    def has_conf(t): return "confluence" in t.triggers_fired
    def ntrig(t): return len(t.triggers_fired)
    def is_mid(t): return tod(t.entry_time_et.time()) == "MIDDAY"
    def is_trendline_only(t): return ntrig(t) == 1 and "trendline_rejection" in t.triggers_fired

    gates = {
        "ALL production (real fills only)": lambda t: True,
        "G_conf_required": has_conf,
        "G_ge2trig": lambda t: ntrig(t) >= 2,
        "G_not_midday": lambda t: not is_mid(t),
        "G_conf_OR_ge2trig": lambda t: has_conf(t) or ntrig(t) >= 2,
        "G_conf_AND_not_midday": lambda t: has_conf(t) and not is_mid(t),
        "G_ge2trig_AND_not_midday": lambda t: ntrig(t) >= 2 and not is_mid(t),
        "G_NO_midday_trendline": lambda t: not (is_mid(t) and is_trendline_only(t)),  # new: block the 24-loser pattern
        "G_BEAR_only": lambda t: "BULLISH" not in t.setup,
        "G_BULL_only": lambda t: "BULLISH" in t.setup,
        "G_BEAR_conf": lambda t: "BULLISH" not in t.setup and has_conf(t),
        "G_BEAR_ge2trig": lambda t: "BULLISH" not in t.setup and ntrig(t) >= 2,
    }
    res = {name: stats([t for t in trades if fn(t)]) for name, fn in gates.items()}

    out = ["# EXPANDED GATE TEST (all cached OOS days, real fills only, no BS_FALLBACK)", "",
           f"{len(trades)} real-fills trades / {len(oos)} OOS days. "
           f"G_NO_midday_trendline is new: blocks the 24-loser pattern the autopsy exposed.", "",
           "| gate | n | WR | total/c | per-trade/c |",
           "|---|---|---|---|---|"]
    for name, s in res.items():
        mark = " **← new**" if "NO_midday_trendline" in name else ""
        out.append(f"| {name}{mark} | {s['n']} | {s['wr']} | {s['pc']:+.0f} | {s['pc_per_trade']:+.1f} |")

    out += ["", "## Key comparisons"]
    base = res["ALL production (real fills only)"]
    for k in ["G_conf_AND_not_midday", "G_ge2trig_AND_not_midday", "G_NO_midday_trendline",
              "G_BEAR_conf", "G_BEAR_ge2trig"]:
        s = res[k]
        if s["n"] < 10:
            out.append(f"- {k}: n={s['n']} (too small to conclude)")
        else:
            lift = s["pc_per_trade"] - base["pc_per_trade"]
            out.append(f"- {k}: {s['pc_per_trade']:+.1f}/trade vs base {base['pc_per_trade']:+.1f} "
                       f"(lift {lift:+.1f}/c), n={s['n']}, WR {s['wr']}, total {s['pc']:+.0f}/c")
    out.append("")
    out.append("## Verdict: which is the strongest LARGE-SAMPLE (n>=30) gate?")
    viable = {k: v for k, v in res.items() if v["n"] >= 30 and k != "ALL production (real fills only)"}
    ranked = sorted(viable.items(), key=lambda kv: kv[1]["pc_per_trade"], reverse=True)
    for i, (k, v) in enumerate(ranked[:5], 1):
        out.append(f"  {i}. {k}: {v['pc_per_trade']:+.1f}/trade, WR {v['wr']}, n={v['n']}, total {v['pc']:+.0f}")

    (REPO.parent / "analysis" / "expanded-gate-2026-05-31.md").write_text("\n".join(out), encoding="utf-8")
    (ABT / "_expanded_gate.json").write_text(json.dumps({"base": base, "gates": res, "oos_days": len(oos)}, indent=2, default=str))
    print("wrote analysis/expanded-gate-2026-05-31.md + _expanded_gate.json")
    print("TOP (n>=30):")
    for k, v in ranked[:5]:
        print(f"  {k}: {v['pc_per_trade']:+.1f}/trade n={v['n']}")


if __name__ == "__main__":
    raise SystemExit(main())
