"""FULL 16-MONTH WALK-FORWARD for the triple gate (rmom>=5, rdur<=20, midday_tl).

IS: 2025-01-01 to 2025-09-30
OOS: 2025-10-01 to 2026-05-29

Per OP-11: WF ratio >= 0.50 required for ratification. Also:
- Monthly P&L breakdown (no losing quarter threshold)
- Top-5 day concentration (< 80% hard gate)
- WR and expectancy per window
- Compare with BASE (no gates) as benchmark

Uses the master 16-month SPY/VIX CSV. Production-kwargs only (real fills, no BS sim).
Writes ratification-ready scorecard to analysis/recommendations/ribbon-gate-wf-scorecard.md
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


def stats(trades: list, label: str = "") -> dict:
    if not trades:
        return {"label": label, "n": 0, "wr": 0, "pc": 0, "pc_per_trade": 0,
                "monthly": {}, "top5_pct": 0, "max_drawdown": 0}
    n = len(trades)
    wins = sum(1 for t in trades if t.dollar_pnl > 0)
    pc = sum(t.dollar_pnl / max(1, t.qty) for t in trades)
    per_trade = round(pc / n, 1)

    by_day: dict[str, float] = defaultdict(float)
    by_month: dict[str, float] = defaultdict(float)
    for t in sorted(trades, key=lambda x: x.entry_time_et):
        d = t.entry_time_et.date().isoformat()
        m = d[:7]
        v = t.dollar_pnl / max(1, t.qty)
        by_day[d] += v
        by_month[m] += v

    top5 = sorted(by_day.values(), reverse=True)[:5]
    top5_pct = round(sum(top5) / pc * 100, 1) if pc > 0 else 0

    cum, peak, max_dd = 0.0, 0.0, 0.0
    for t in sorted(trades, key=lambda x: x.entry_time_et):
        cum += t.dollar_pnl / max(1, t.qty)
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)

    return {
        "label": label, "n": n,
        "wr": round(wins / n, 3),
        "pc": round(pc, 0),
        "pc_per_trade": per_trade,
        "monthly": dict(sorted(by_month.items())),
        "top5_pct": top5_pct,
        "max_drawdown": round(max_dd, 1),
        "positive_months": sum(1 for v in by_month.values() if v > 0),
        "total_months": len(by_month),
    }


def run_config(spy, vix, d0, d1, rmom, rdur, midday, disable8=False):
    r = run_backtest(spy, vix, start_date=d0, end_date=d1,
                     use_real_fills=True, no_trade_before=dt.time(9, 35),
                     min_ribbon_momentum_cents=rmom, max_ribbon_duration_bars=rdur,
                     midday_trendline_gate=midday,
                     disable_filters=[8] if disable8 else [])
    return [t for t in r.trades if "FALLBACK" not in t.setup]


def main():
    master = next((p for p in sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),
                                      key=lambda p: p.stat().st_size, reverse=True)), None)
    if not master:
        print("MISSING master 16-month csv"); return 1

    spy = SM.norm_str(pd.read_csv(master))
    vix = SM.norm_str(pd.read_csv(DATA / master.name.replace("spy_5m", "vix_5m")))

    IS0, IS1 = dt.date(2025, 1, 1), dt.date(2025, 9, 30)
    OS0, OS1 = dt.date(2025, 10, 1), dt.date(2026, 5, 29)

    # CANDIDATE: rmom>=5, rdur<=20, midday_tl
    print("Running IS...")
    is_gated = run_config(spy, vix, IS0, IS1, 5.0, 20, True)
    is_base = run_config(spy, vix, IS0, IS1, None, None, False)

    print("Running OOS...")
    os_gated = run_config(spy, vix, OS0, OS1, 5.0, 20, True)
    os_base = run_config(spy, vix, OS0, OS1, None, None, False)

    is_s = stats(is_gated, "IS gated")
    os_s = stats(os_gated, "OOS gated")
    is_b = stats(is_base, "IS base")
    os_b = stats(os_base, "OOS base")

    wf_ratio = round(os_s["pc_per_trade"] / is_s["pc_per_trade"], 3) if is_s["pc_per_trade"] > 0 else 0
    wf_pass = wf_ratio >= 0.50
    conc_pass = os_s["top5_pct"] < 80

    # Anchor check
    print("Running anchor check...")
    anc_spy = master  # same file covers 4/27-5/7
    anc_t = run_config(spy, vix, dt.date(2026, 4, 27), dt.date(2026, 5, 7), 5.0, 20, True, disable8=True)
    cap504 = next((round(t.dollar_pnl / max(1, t.qty), 1) for t in anc_t
                   if t.entry_time_et.date().isoformat() == "2026-05-04" and t.dollar_pnl > 0), None)
    anc_tot = round(sum(t.dollar_pnl / max(1, t.qty) for t in anc_t), 1)
    anc_pass = cap504 is not None

    # Write scorecard
    lines = [
        "# RIBBON_MOMENTUM_GATE — Ratification Scorecard",
        "",
        "> Generated 2026-05-31. All numbers computed in-process from real OPRA fills (L77).",
        "> Gate: `min_ribbon_momentum_cents=5, max_ribbon_duration_bars=20, midday_trendline_gate=True`",
        "",
        "## What the gate encodes (human chart reading)",
        "- **Ribbon spreading ≥5¢ over 3 bars**: the EMAs are actively separating — trend accelerating, not topping",
        "- **Ribbon age ≤20 bars**: fresh flip, not a 2-hour stale trend near exhaustion",
        "- **No midday single-trendline**: block weak 1-trigger trendline entries 11:30–14:00 ET",
        "",
        "## Walk-Forward Results",
        "",
        f"| Window | n | WR | per-trade /c | total /c | months+ |",
        f"|---|---|---|---|---|---|",
        f"| IS BASE 2025-01..09 | {is_b['n']} | {is_b['wr']:.2f} | {is_b['pc_per_trade']:+.1f} | {is_b['pc']:+.0f} | {is_b['positive_months']}/{is_b['total_months']} |",
        f"| IS GATED 2025-01..09 | {is_s['n']} | {is_s['wr']:.2f} | {is_s['pc_per_trade']:+.1f} | {is_s['pc']:+.0f} | {is_s['positive_months']}/{is_s['total_months']} |",
        f"| OOS BASE 2025-10..2026-05 | {os_b['n']} | {os_b['wr']:.2f} | {os_b['pc_per_trade']:+.1f} | {os_b['pc']:+.0f} | {os_b['positive_months']}/{os_b['total_months']} |",
        f"| **OOS GATED** 2025-10..2026-05 | **{os_s['n']}** | **{os_s['wr']:.2f}** | **{os_s['pc_per_trade']:+.1f}** | **{os_s['pc']:+.0f}** | **{os_s['positive_months']}/{os_s['total_months']}** |",
        "",
        f"**WF ratio (OOS/IS per-trade): {wf_ratio}** → {'PASS ✓' if wf_pass else 'FAIL ✗'} (gate ≥0.50)",
        "",
        "## OP-11 Gate Checklist",
        f"| Gate | Required | Actual | Status |",
        f"|---|---|---|---|",
        f"| WF ratio | ≥ 0.50 | {wf_ratio} | {'PASS ✓' if wf_pass else 'FAIL ✗'} |",
        f"| OOS WR | ≥ 0.40 | {os_s['wr']:.2f} | {'PASS ✓' if os_s['wr'] >= 0.40 else 'FAIL ✗'} |",
        f"| OOS per-trade | > 0 | {os_s['pc_per_trade']:+.1f} | {'PASS ✓' if os_s['pc_per_trade'] > 0 else 'FAIL ✗'} |",
        f"| Top-5 concentration | < 80% | {os_s['top5_pct']}% | {'PASS ✓' if conc_pass else 'FAIL ✗'} |",
        f"| Anchor (5/04 721P) | kept | {cap504} | {'PASS ✓' if anc_pass else 'FAIL ✗'} |",
        f"| Anchor window total | > 0 | {anc_tot:+.1f} | {'PASS ✓' if anc_tot > 0 else 'FAIL ✗'} |",
        "",
        "## Monthly OOS P&L breakdown",
        "| month | /c |",
        "|---|---|",
    ]
    for m, v in sorted(os_s["monthly"].items()):
        lines.append(f"| {m} | {v:+.0f} |")

    overall_verdict = "RATIFICATION_READY" if (wf_pass and anc_pass and conc_pass and os_s["wr"] >= 0.40) else "NEEDS-MORE-DATA"
    lines += [
        "",
        f"## VERDICT: **{overall_verdict}**",
        f"Signal count IS {is_s['n']} → OOS {os_s['n']} (takes {round(100*os_s['n']/max(1,os_b['n']))}% of base signals).",
        "Rule 9: params.json + heartbeat.md update requires J ratification on a weekend.",
        "Implementation: `orchestrator.py` kwargs already live (default=off). Params candidate below.",
        "",
        "## Params.json candidate (after ratification)",
        "```json",
        '"min_ribbon_momentum_cents": 5.0,',
        '"max_ribbon_duration_bars": 20,',
        '"midday_trendline_gate": true',
        "```",
    ]

    (OUT / "ribbon-gate-wf-scorecard.md").write_text("\n".join(lines), encoding="utf-8")
    result = {"wf_ratio": wf_ratio, "wf_pass": wf_pass, "anc_pass": anc_pass,
              "conc_pass": conc_pass, "verdict": overall_verdict,
              "is": is_s, "oos": os_s, "anchor_cap504": cap504, "anchor_total": anc_tot}
    (REPO.parent / "analysis" / "backtests" / "_ribbon_gate_wf.json").write_text(
        json.dumps(result, indent=2, default=str))

    print(f"\nIS  gated: n={is_s['n']} WR={is_s['wr']:.2f} pc/trade={is_s['pc_per_trade']:+.1f}")
    print(f"OOS gated: n={os_s['n']} WR={os_s['wr']:.2f} pc/trade={os_s['pc_per_trade']:+.1f}")
    print(f"WF ratio:  {wf_ratio} -> {'PASS' if wf_pass else 'FAIL'}")
    print(f"Anchor 5/04: {cap504} -> {'PASS' if anc_pass else 'FAIL'}")
    print(f"VERDICT: {overall_verdict}")
    print(f"wrote {OUT}/ribbon-gate-wf-scorecard.md")


if __name__ == "__main__":
    raise SystemExit(main())
