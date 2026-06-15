"""RIBBON SIGNAL — gate on the two most predictive visual features:
1. Ribbon momentum (spread widening vs compressing) — ★★★★★ discriminator
2. Ribbon duration (fresh flip better than aged trend)

Gate: require ribbon_momentum > -5 cents (spread not compressing) AND
      ribbon_duration < 25 bars (not a stale trend).

Run on 312 OOS real-fills trades. Compare gated vs ungated. If these two
human-readable chart features improve per-trade materially, they become the
next candidate filter — cleaner and more interpretable than the time-of-day
approach because they're visible to J on any chart at any time.
"""
from __future__ import annotations
import sys, json, datetime as dt
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import sniper_matrix as SM
from lib.ribbon import compute_ribbon, ribbon_at

DATA = REPO / "data"
ABT = REPO.parent / "analysis" / "backtests"


def ribbon_momentum(ribbon_df, idx):
    if idx < 3:
        return 0.0
    now = ribbon_at(ribbon_df, idx)
    prev = ribbon_at(ribbon_df, idx - 3)
    if now is None or prev is None:
        return 0.0
    return now.spread_cents - prev.spread_cents


def ribbon_duration(ribbon_df, idx, stack):
    count = 0
    for i in range(idx, -1, -1):
        st = ribbon_at(ribbon_df, i)
        if st is None or st.stack != stack:
            break
        count += 1
    return count


def main():
    cands = [p for p in DATA.glob("spy_5m_*.csv") if (DATA / p.name.replace("spy_5m", "vix_5m")).exists()]
    cands.sort(key=lambda p: p.stat().st_size, reverse=True)
    master = cands[0]

    spy_raw = pd.read_csv(master)
    spy_raw["timestamp_et"] = SM._to_et(spy_raw["timestamp_et"])
    rth_all = spy_raw[(spy_raw["timestamp_et"].dt.time >= dt.time(9, 30)) &
                      (spy_raw["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    ribbon_all = compute_ribbon(rth_all["close"])

    spy_str = SM.norm_str(pd.read_csv(master))
    vix_str = SM.norm_str(pd.read_csv(DATA / master.name.replace("spy_5m", "vix_5m")))
    from collections import Counter
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    fill_days = sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})
    spy_dates = set(SM._to_et(pd.read_csv(master)["timestamp_et"]).dt.date)
    missed = {dt.date(2026, 5, 26), dt.date(2026, 5, 27), dt.date(2026, 5, 28), dt.date(2026, 5, 29)}
    oos = sorted([d for d in fill_days if d in spy_dates and d not in missed])

    r = SM.run_backtest(spy_str, vix_str, start_date=min(oos), end_date=max(oos),
                        use_real_fills=True, no_trade_before=dt.time(9, 35))
    trades = [t for t in r.trades if t.entry_time_et.date() in set(oos) and "FALLBACK" not in t.setup]
    assert len(trades) >= 20

    records = []
    for t in sorted(trades, key=lambda x: x.entry_time_et):
        d = t.entry_time_et.date()
        t_dt = t.entry_time_et
        if hasattr(t_dt, "tzinfo") and t_dt.tzinfo is not None:
            t_dt = t_dt.replace(tzinfo=None)
        cand_idx = None
        for i, row in rth_all.iterrows():
            row_t = row["timestamp_et"]
            if hasattr(row_t, "tzinfo") and row_t.tzinfo is not None:
                row_t = row_t.tz_localize(None) if hasattr(row_t, "tz_localize") else row_t
            if row["timestamp_et"].date() == d and abs((row["timestamp_et"].replace(tzinfo=None) - t_dt).total_seconds()) < 310:
                cand_idx = i
                break
        if cand_idx is None or cand_idx < 5:
            continue
        trigger_idx = max(0, cand_idx - 1)
        st = ribbon_at(ribbon_all, trigger_idx)
        if st is None:
            continue
        rmom = ribbon_momentum(ribbon_all, trigger_idx)
        rdur = ribbon_duration(ribbon_all, trigger_idx, st.stack)
        pc = t.dollar_pnl / max(1, t.qty)
        records.append({"pc": pc, "win": t.dollar_pnl > 0, "rmom": rmom, "rdur": rdur})

    df = pd.DataFrame(records)
    total = sum(r["pc"] for r in records)
    n = len(records)

    # Sweep gate thresholds
    results = {}
    out = ["# RIBBON SIGNAL GATE — momentum + duration thresholds", "",
           f"Base: {n} trades, {total/n:+.1f}/trade total {total:+.0f}/c", ""]

    # Momentum gate sweep
    out.append("## Ribbon momentum gate (require spread widening ≥ threshold)")
    out.append("| momentum threshold | n kept | WR | per-trade /c | total /c |")
    out.append("|---|---|---|---|---|")
    for thr in [-20, -10, -5, 0, 5, 10, 15]:
        kept = df[df["rmom"] >= thr]
        if len(kept) < 10:
            continue
        pc = kept["pc"].sum() / len(kept)
        wr = kept["win"].mean()
        out.append(f"| rmom >= {thr:+d} | {len(kept)} | {wr:.2f} | {pc:+.1f} | {kept['pc'].sum():+.0f} |")
        results[f"rmom>={thr}"] = {"n": len(kept), "pc_per_trade": round(pc, 1), "wr": round(wr, 2)}

    out.append("")
    out.append("## Ribbon duration gate (require fresh ribbon, bars ≤ threshold)")
    out.append("| max duration | n kept | WR | per-trade /c | total /c |")
    out.append("|---|---|---|---|---|")
    for thr in [10, 15, 20, 25, 30, 999]:
        kept = df[df["rdur"] <= thr]
        if len(kept) < 10:
            continue
        pc = kept["pc"].sum() / len(kept)
        wr = kept["win"].mean()
        lbl = "no limit" if thr == 999 else f"≤{thr} bars"
        out.append(f"| rdur {lbl} | {len(kept)} | {wr:.2f} | {pc:+.1f} | {kept['pc'].sum():+.0f} |")
        results[f"rdur<={thr}"] = {"n": len(kept), "pc_per_trade": round(pc, 1), "wr": round(wr, 2)}

    out.append("")
    out.append("## COMBINED: momentum ≥ threshold AND duration ≤ threshold")
    out.append("| combo | n | WR | per-trade /c | total /c | pct signals kept |")
    out.append("|---|---|---|---|---|---|")
    best_combined = (None, -999.0)
    for mthr in [-5, 0, 5, 10]:
        for dthr in [15, 20, 25]:
            kept = df[(df["rmom"] >= mthr) & (df["rdur"] <= dthr)]
            if len(kept) < 15:
                continue
            pc = kept["pc"].sum() / len(kept)
            wr = kept["win"].mean()
            pct = 100 * len(kept) / n
            out.append(f"| rmom≥{mthr:+d} AND rdur≤{dthr} | {len(kept)} | {wr:.2f} | {pc:+.1f} | {kept['pc'].sum():+.0f} | {pct:.0f}% |")
            if pc > best_combined[1]:
                best_combined = (f"rmom≥{mthr} AND rdur≤{dthr}", pc)

    out.append("")
    if best_combined[0]:
        out.append(f"## BEST COMBINED GATE: **{best_combined[0]} — {best_combined[1]:+.1f}/trade**")
        out.append("This is the visual 'conviction check' a human does before entering:")
        out.append("- Ribbon spread is widening (trend accelerating, not topping)")
        out.append("- Ribbon is relatively fresh (not a stale 2-hour trend near exhaustion)")
        out.append("Combined: the setup has momentum AND hasn't been running too long.")

    (REPO.parent / "analysis" / "ribbon-signal-gate-2026-05-31.md").write_text("\n".join(out), encoding="utf-8")
    (ABT / "_ribbon_signal.json").write_text(json.dumps(results, indent=2))

    print("BASE:", n, "trades", round(total / n, 1), "/trade")
    print("Best momentum-only gate:")
    best_m = max((v for k, v in results.items() if "rmom" in k and "rdur" not in k), key=lambda x: x["pc_per_trade"])
    for k, v in results.items():
        if "rmom" in k and "rdur" not in k:
            print(f"  {k}: n={v['n']} WR={v['wr']} pc/trade={v['pc_per_trade']:+.1f}")
    print(f"wrote analysis/ribbon-signal-gate-2026-05-31.md")


if __name__ == "__main__":
    raise SystemExit(main())
