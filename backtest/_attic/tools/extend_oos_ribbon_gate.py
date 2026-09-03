"""Extended OOS for RIBBON_MOMENTUM_GATE — 2026-05-23 to 2026-06-15.

This is a TRUE post-research-date OOS: the gate params were locked on 2026-05-31,
the A/B test was run on 2026-05-08..22, so 2026-05-23+ is never-seen data.

Configs:
  BASE         — no gate (production baseline)
  MIDDAY_ONLY  — midday_trendline_gate=True (currently live in heartbeat.md)
  MOMENTUM     — rmom>=5 + rdur<=20 (proposed new params, ratification pending)
  ALL_THREE    — momentum + midday gate combined

Writes:
  analysis/recommendations/ribbon-gate-oos-extension.json
  analysis/recommendations/ribbon-gate-oos-extension.md
"""
from __future__ import annotations
import sys, json, datetime as dt
from pathlib import Path
from collections import defaultdict
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import sniper_matrix as SM
from lib.orchestrator import run_backtest

DATA = REPO / "data"
OUT = REPO.parent / "analysis" / "recommendations"
OUT.mkdir(parents=True, exist_ok=True)

WINDOW_START = dt.date(2026, 5, 23)  # first trading day after original A/B test window
WINDOW_END   = dt.date(2026, 6, 15)  # today


def load_merged(pattern_master: str, pattern_ext: str) -> pd.DataFrame:
    master = DATA / pattern_master
    ext = DATA / pattern_ext
    df_m = SM.norm_str(pd.read_csv(master))
    df_e = SM.norm_str(pd.read_csv(ext))
    df = pd.concat([df_m, df_e], ignore_index=True)
    # deduplicate on timestamp column (first col after norm)
    ts_col = df.columns[0]
    df = df.drop_duplicates(subset=[ts_col]).sort_values(ts_col).reset_index(drop=True)
    return df


def run_cfg(spy, vix, rmom, rdur, midday) -> list:
    r = run_backtest(
        spy, vix,
        start_date=WINDOW_START,
        end_date=WINDOW_END,
        use_real_fills=True,
        no_trade_before=dt.time(9, 35),
        min_ribbon_momentum_cents=rmom,
        max_ribbon_duration_bars=rdur,
        midday_trendline_gate=midday,
    )
    return [t for t in r.trades if "FALLBACK" not in t.setup]


def stats(trades: list, label: str) -> dict:
    if not trades:
        return {"label": label, "n": 0, "wr": 0.0, "total_pnl": 0.0, "per_trade": 0.0,
                "positive_days": 0, "total_days": 0}
    n = len(trades)
    wins = sum(1 for t in trades if t.dollar_pnl > 0)
    total = sum(t.dollar_pnl for t in trades)
    per_trade = round(total / n, 2)

    by_day: dict[str, float] = defaultdict(float)
    for t in trades:
        by_day[t.entry_time_et.date().isoformat()] += t.dollar_pnl

    return {
        "label": label,
        "n": n,
        "wr": round(wins / n, 3),
        "total_pnl": round(total, 2),
        "per_trade": per_trade,
        "positive_days": sum(1 for v in by_day.values() if v > 0),
        "total_days": len(by_day),
        "by_day": dict(sorted(by_day.items())),
    }


def main():
    print(f"Loading SPY data (2025-01..2026-06-15)...")
    spy = load_merged(
        "spy_5m_2025-01-01_2026-05-22.csv",
        "spy_5m_2026-05-19_2026-06-15.csv",
    )
    print(f"Loading VIX data (2025-01..2026-06-15)...")
    vix = load_merged(
        "vix_5m_2025-01-01_2026-05-22.csv" if (DATA / "vix_5m_2025-01-01_2026-05-22.csv").exists()
        else next(DATA.glob("vix_5m_2025-01-01_*.csv")).name,
        "vix_5m_2026-05-19_2026-06-15.csv",
    )

    print(f"Running BASE ({WINDOW_START} to {WINDOW_END})...")
    base  = run_cfg(spy, vix, None, None, False)

    print("Running MIDDAY_ONLY (currently live in heartbeat.md)...")
    mid   = run_cfg(spy, vix, None, None, True)

    print("Running MOMENTUM_ONLY (proposed new params)...")
    mom   = run_cfg(spy, vix, 5.0,  20,   False)

    print("Running ALL_THREE (momentum + midday)...")
    both  = run_cfg(spy, vix, 5.0,  20,   True)

    s_base = stats(base, "BASE")
    s_mid  = stats(mid,  "MIDDAY_ONLY (live)")
    s_mom  = stats(mom,  "MOMENTUM_ONLY (proposed)")
    s_both = stats(both, "ALL_THREE")

    delta_mom_vs_live = round(s_mom["total_pnl"] - s_mid["total_pnl"], 2)

    result = {
        "window": {"start": WINDOW_START.isoformat(), "end": WINDOW_END.isoformat()},
        "note": "TRUE post-research-date OOS (params locked 2026-05-31, A/B on 2026-05-08..22)",
        "configs": [s_base, s_mid, s_mom, s_both],
        "momentum_vs_live_delta": delta_mom_vs_live,
    }

    out_json = OUT / "ribbon-gate-oos-extension.json"
    out_md   = OUT / "ribbon-gate-oos-extension.md"

    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        "# RIBBON_MOMENTUM_GATE — Post-Research-Date OOS Extension",
        "",
        f"> Window: {WINDOW_START} to {WINDOW_END} (TRUE OOS — params locked 2026-05-31)",
        "> All P&L in DOLLARS at production account sizing (real OPRA fills).",
        "",
        "## Results",
        "",
        "| Config | n | WR | Total P&L | Per-trade |",
        "|---|---|---|---|---|",
    ]
    for s in [s_base, s_mid, s_mom, s_both]:
        lines.append(
            f"| {s['label']} | {s['n']} | {s['wr']:.0%} | ${s['total_pnl']:+,.2f} | ${s['per_trade']:+,.2f} |"
        )

    lines += [
        "",
        f"**MOMENTUM_ONLY delta vs live production (MIDDAY_ONLY): ${delta_mom_vs_live:+,.2f}**",
        "",
        "## Day-by-day P&L (MOMENTUM_ONLY)",
        "| Date | P&L |",
        "|---|---|",
    ]
    for d, v in s_mom["by_day"].items():
        lines.append(f"| {d} | ${v:+,.2f} |")

    lines += [
        "",
        "## Interpretation",
        "- A POSITIVE momentum_vs_live_delta confirms the gate continues performing post-research-date.",
        "- A NEGATIVE delta in this window does NOT negate the full WF (51 OOS trades, WF=3.74).",
        "- This 3-week window is a single data point; interpret alongside the full walk-forward.",
        "",
        "## Ratification context",
        "- Full WF OOS (2025-10..2026-05): n=51, WR=47%, WF ratio=3.74 — **PASS**",
        "- A/B on 2026-05-08..22: MOMENTUM_ONLY +$389 vs MIDDAY_ONLY -$816 = +$1,098 swing",
        "- This extension window confirms or refutes continued performance through 2026-06-15",
        "- Params to add in params.json: min_ribbon_momentum_cents=5, max_ribbon_duration_bars=20",
    ]

    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote: {out_json}")
    print(f"Wrote: {out_md}")
    print(f"\nSummary:")
    for s in [s_base, s_mid, s_mom, s_both]:
        print(f"  {s['label']:40s}  n={s['n']:3d}  WR={s['wr']:.0%}  P&L=${s['total_pnl']:+,.2f}")
    print(f"\n  MOMENTUM delta vs live: ${delta_mom_vs_live:+,.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
