"""WHERE is the OOS bleed? Run production v15 (real fills, default exits) over the 60
cached-fill OOS days and segment EVERY trade by side / setup / time-of-day / VIX regime /
trigger-quality / exit-reason. The 82-signal OOS lost overall — this finds WHICH slice loses,
so any fix is a targeted gate (OP-16), not a global curve-fit.

Faithful: uses run_backtest production defaults (the real engine). Sanity-guarded + JSON dump
(L77). One run_backtest over the span (fast). Engine-benefit research; no doctrine/order edits.
"""
from __future__ import annotations
import sys, json, datetime as dt
from collections import defaultdict
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import sniper_matrix as SM  # _to_et, norm_str, run_backtest

DATA = REPO / "data"
ABT = REPO.parent / "analysis" / "backtests"


def cached_fill_days():
    from collections import Counter
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    return sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})


def tod_bucket(t):
    if t < dt.time(10, 15):
        return "OPEN_DRIVE"
    if t < dt.time(11, 30):
        return "MORNING"
    if t < dt.time(14, 0):
        return "MIDDAY"
    if t < dt.time(15, 15):
        return "AFTERNOON"
    return "POWER_HOUR"


def agg(trades, keyfn):
    d = defaultdict(lambda: {"n": 0, "w": 0, "pnl": 0.0, "pc": 0.0})
    for t in trades:
        k = keyfn(t)
        d[k]["n"] += 1
        d[k]["pnl"] += t.dollar_pnl
        d[k]["pc"] += t.dollar_pnl / max(1, t.qty)
        if t.dollar_pnl > 0:
            d[k]["w"] += 1
    return {k: {"n": v["n"], "wr": round(v["w"] / v["n"], 2) if v["n"] else 0,
                "pnl": round(v["pnl"], 0), "pc": round(v["pc"], 1),
                "pc_per_trade": round(v["pc"] / v["n"], 1) if v["n"] else 0}
            for k, v in sorted(d.items())}


def main():
    # widest master with matching vix
    cands = [p for p in DATA.glob("spy_5m_*.csv") if (DATA / p.name.replace("spy_5m", "vix_5m")).exists()]
    cands.sort(key=lambda p: p.stat().st_size, reverse=True)
    master = cands[0]
    spy = SM.norm_str(pd.read_csv(master)); vix = SM.norm_str(pd.read_csv(DATA / master.name.replace("spy_5m", "vix_5m")))
    spy_dates = set(SM._to_et(pd.read_csv(master)["timestamp_et"]).dt.date)
    missed = {dt.date(2026, 5, 26), dt.date(2026, 5, 27), dt.date(2026, 5, 28), dt.date(2026, 5, 29)}
    oos = [d for d in cached_fill_days() if d in spy_dates and d not in missed]
    oos = sorted(oos)[-60:]

    # VIX lookup at entry time (real-fills sim zeroes entry_vix, so join from series)
    vser = SM._to_et(pd.read_csv(master.parent / master.name.replace("spy_5m", "vix_5m"))["timestamp_et"])
    vdf = pd.read_csv(master.parent / master.name.replace("spy_5m", "vix_5m"))
    vdf["ts"] = SM._to_et(vdf["timestamp_et"])
    vdf = vdf.set_index("ts")["close"].sort_index()

    def vix_at(ts):
        ts = pd.Timestamp(ts)
        if ts.tzinfo is None and vdf.index.tz is not None:
            ts = ts.tz_localize(vdf.index.tz)
        try:
            idx = vdf.index.get_indexer([ts], method="ffill")[0]
            return float(vdf.iloc[idx]) if idx >= 0 else None
        except Exception:
            return None

    def vix_regime(v):
        if v is None:
            return "UNK"
        return "LOW(<15)" if v < 15 else "MID(15-22)" if v <= 22 else "HIGH(>22)"

    # ONE production run over the span (default v15 exits, real fills)
    r = SM.run_backtest(spy, vix, start_date=min(oos), end_date=max(oos),
                        use_real_fills=True, no_trade_before=dt.time(9, 35))
    trades = [t for t in r.trades if t.entry_time_et.date() in set(oos)]
    if len(trades) < 20:
        print(f"GUARD FAIL: only {len(trades)} trades, expected >=20. Abort, no write.")
        return 1

    # attach vix regime
    for t in trades:
        t._vix = vix_at(t.entry_time_et)

    total_pnl = sum(t.dollar_pnl for t in trades)
    total_pc = sum(t.dollar_pnl / max(1, t.qty) for t in trades)
    nW = sum(1 for t in trades if t.dollar_pnl > 0)

    out = {
        "oos_days": len(oos), "n_trades": len(trades),
        "overall": {"wr": round(nW / len(trades), 2), "pnl": round(total_pnl, 0),
                    "pc": round(total_pc, 1), "pc_per_trade": round(total_pc / len(trades), 1)},
        "by_side": agg(trades, lambda t: "BULL_call" if "BULLISH" in t.setup else "BEAR_put"),
        "by_setup": agg(trades, lambda t: t.setup),
        "by_tod": agg(trades, lambda t: tod_bucket(t.entry_time_et.time())),
        "by_vix_regime": agg(trades, lambda t: vix_regime(getattr(t, "_vix", None))),
        "by_exit": agg(trades, lambda t: t.exit_reason.value if t.exit_reason else "NONE"),
        "by_ntriggers": agg(trades, lambda t: f"{len(t.triggers_fired)}trig"),
        "by_confluence": agg(trades, lambda t: "has_confluence" if "confluence" in t.triggers_fired else "no_confluence"),
    }
    (ABT / "_segment_oos.json").write_text(json.dumps(out, indent=2, default=str))

    # human-readable
    lines = [f"# OOS SEGMENTATION — where the bleed is (production v15, real fills)", "",
             f"{len(trades)} trades over {len(oos)} OOS days. Overall: WR {out['overall']['wr']}, "
             f"{out['overall']['pc']:+.0f}/c total ({out['overall']['pc_per_trade']:+.1f}/trade).", ""]
    def tbl(title, d):
        lines.append(f"## {title}")
        lines.append("| bucket | n | WR | total/c | per-trade/c |")
        lines.append("|---|---|---|---|---|")
        for k, v in sorted(d.items(), key=lambda kv: kv[1]["pc"], reverse=True):
            lines.append(f"| {k} | {v['n']} | {v['wr']} | {v['pc']:+.0f} | {v['pc_per_trade']:+.1f} |")
        lines.append("")
    tbl("By SIDE (the OP-16 question)", out["by_side"])
    tbl("By setup", out["by_setup"])
    tbl("By time-of-day", out["by_tod"])
    tbl("By VIX regime", out["by_vix_regime"])
    tbl("By trigger count", out["by_ntriggers"])
    tbl("By confluence", out["by_confluence"])
    tbl("By exit reason", out["by_exit"])
    (REPO.parent / "analysis" / "oos-segmentation-2026-05-31.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"trades={len(trades)} overall {out['overall']['pc']:+.0f}/c WR {out['overall']['wr']}")
    print("BY SIDE:", {k: f"{v['pc']:+.0f}/c n{v['n']} WR{v['wr']}" for k, v in out["by_side"].items()})
    print("wrote analysis/oos-segmentation-2026-05-31.md + _segment_oos.json")


if __name__ == "__main__":
    raise SystemExit(main())
