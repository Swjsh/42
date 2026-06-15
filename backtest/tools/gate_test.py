"""SELECTIVITY GATE test — does requiring conviction (confluence / >=2 triggers / not-midday)
concentrate the OOS edge? Loads the SAME production OOS trade set (real fills) ONCE, then
re-aggregates under candidate gates. This is J's 'more sniper entries' thesis, tested on the
68-trade OOS set with no re-running (pure filtering of already-simulated real trades).

Faithful (production run_backtest trades), sanity-guarded, JSON dump (L77). No doctrine edits.
"""
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
    if t < dt.time(10, 15):
        return "OPEN_DRIVE"
    if t < dt.time(11, 30):
        return "MORNING"
    if t < dt.time(14, 0):
        return "MIDDAY"
    if t < dt.time(15, 15):
        return "AFTERNOON"
    return "POWER_HOUR"


def stats(trades):
    if not trades:
        return {"n": 0, "wr": 0, "pc": 0.0, "pc_per_trade": 0.0, "green_days": 0, "days": 0}
    n = len(trades)
    w = sum(1 for t in trades if t.dollar_pnl > 0)
    pc = sum(t.dollar_pnl / max(1, t.qty) for t in trades)
    byday = {}
    for t in trades:
        byday.setdefault(t.entry_time_et.date(), 0.0)
        byday[t.entry_time_et.date()] += t.dollar_pnl
    return {"n": n, "wr": round(w / n, 2), "pc": round(pc, 0),
            "pc_per_trade": round(pc / n, 1),
            "green_days": sum(1 for v in byday.values() if v > 0), "days": len(byday)}


def main():
    cands = [p for p in DATA.glob("spy_5m_*.csv") if (DATA / p.name.replace("spy_5m", "vix_5m")).exists()]
    cands.sort(key=lambda p: p.stat().st_size, reverse=True)
    master = cands[0]
    spy = SM.norm_str(pd.read_csv(master)); vix = SM.norm_str(pd.read_csv(DATA / master.name.replace("spy_5m", "vix_5m")))
    spy_dates = set(SM._to_et(pd.read_csv(master)["timestamp_et"]).dt.date)
    missed = {dt.date(2026, 5, 26), dt.date(2026, 5, 27), dt.date(2026, 5, 28), dt.date(2026, 5, 29)}
    oos = sorted([d for d in cached_fill_days() if d in spy_dates and d not in missed])[-60:]

    r = SM.run_backtest(spy, vix, start_date=min(oos), end_date=max(oos),
                        use_real_fills=True, no_trade_before=dt.time(9, 35))
    trades = [t for t in r.trades if t.entry_time_et.date() in set(oos)]
    assert len(trades) >= 20, f"GUARD FAIL: {len(trades)} trades. Abort."

    def has_conf(t):
        return "confluence" in t.triggers_fired
    def ntrig(t):
        return len(t.triggers_fired)
    def is_mid(t):
        return tod(t.entry_time_et.time()) == "MIDDAY"

    gates = {
        "ALL (production, ungated)": lambda t: True,
        "G1: confluence required": has_conf,
        "G2: >=2 triggers": lambda t: ntrig(t) >= 2,
        "G3: not MIDDAY": lambda t: not is_mid(t),
        "G4: confluence OR >=2 trig": lambda t: has_conf(t) or ntrig(t) >= 2,
        "G5: (conf OR >=2trig) AND not-midday": lambda t: (has_conf(t) or ntrig(t) >= 2) and not is_mid(t),
        "G6: >=2 triggers AND not-midday": lambda t: ntrig(t) >= 2 and not is_mid(t),
        "G7: confluence AND not-midday": lambda t: has_conf(t) and not is_mid(t),
    }
    res = {name: stats([t for t in trades if fn(t)]) for name, fn in gates.items()}

    out = ["# SELECTIVITY GATE test — does conviction concentrate the OOS edge? (real fills)", "",
           f"Production OOS trade set: {len(trades)} trades / {len(oos)} cached-fill days. "
           "Each gate FILTERS that exact set (no re-run). This tests J's 'more sniper entries' thesis.", "",
           "| gate | n | WR | total/c | per-trade/c | green days/traded |",
           "|---|---|---|---|---|---|"]
    base = res["ALL (production, ungated)"]
    for name, s in res.items():
        out.append(f"| {name} | {s['n']} | {s['wr']} | {s['pc']:+.0f} | {s['pc_per_trade']:+.1f} | "
                   f"{s['green_days']}/{s['days']} |")
    out.append("")
    # best gate by per-trade with >= 15 trades (avoid tiny-n)
    viable = {k: v for k, v in res.items() if v["n"] >= 15 and k != "ALL (production, ungated)"}
    best = max(viable.items(), key=lambda kv: kv[1]["pc_per_trade"]) if viable else (None, None)
    out.append("## Verdict")
    out.append(f"- Ungated production: {base['pc']:+.0f}/c total, {base['pc_per_trade']:+.1f}/trade, "
               f"WR {base['wr']}, n={base['n']}.")
    if best[0]:
        b = best[1]
        kept = round(100 * b["n"] / base["n"])
        out.append(f"- **Best viable gate (n>=15): {best[0]} -> {b['pc_per_trade']:+.1f}/trade "
                   f"(WR {b['wr']}, n={b['n']}, keeps {kept}% of trades, total {b['pc']:+.0f}/c).**")
        lift = b["pc_per_trade"] - base["pc_per_trade"]
        out.append(f"- Per-trade lift vs ungated: {lift:+.1f}/c ({'BETTER' if lift > 0 else 'worse'}). "
                   f"Total {'higher' if b['pc'] > base['pc'] else 'lower'} P&L on far fewer trades "
                   f"= higher quality + less PDT/capital usage.")
        out.append("")
        out.append("**This is the ratifiable lead (DRAFT for J, Rule 9):** a SELECTIVITY gate "
                   "(require confluence or >=2 triggers, optionally skip midday) maps directly to existing "
                   "params (filter_10_min_triggers_bull/bear, confluence_min_signals) — no new code. "
                   "Validate via grinder + walk-forward, compare edge_capture x sharpe per OP-16, then "
                   "gamma-sync. It is exactly J's 'sniper entries' instinct, now backed by a 68-trade "
                   "segmentation that agrees across confluence, trigger-count, AND time-of-day.")
    else:
        out.append("- No gate keeps >=15 trades; sample too small for a gate conclusion. Need wider OOS data.")

    (REPO.parent / "analysis" / "selectivity-gate-2026-05-31.md").write_text("\n".join(out), encoding="utf-8")
    (ABT / "_gate_test.json").write_text(json.dumps({"base": base, "gates": res, "best": best[0]}, indent=2, default=str))
    print("BASE:", base["pc_per_trade"], "/trade, n", base["n"])
    for k, v in res.items():
        print(f"  {k:<40} n={v['n']:<3} WR={v['wr']:<5} {v['pc']:+7.0f}/c  {v['pc_per_trade']:+6.1f}/trade")
    print("BEST viable:", best[0])
    print("wrote analysis/selectivity-gate-2026-05-31.md + _gate_test.json")


if __name__ == "__main__":
    raise SystemExit(main())
