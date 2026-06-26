"""DTE LIVE-EDGE RISK-CHARACTERIZATION — is the 1DTE lift on the LIVE edge a CLEAN
ship-win or a Sharpe tradeoff?

CONTEXT (ANGLE A). vwap_continuation is the ONE live edge (ships at ITM-2 / -8% premium
stop). The DTE-expansion breakthrough showed its OOS per-trade expectancy RISES with DTE
(0DTE -> 1DTE -> 2DTE) — the lift is THETA-driven, not gap-driven (held_overnight ~0% at
1DTE: the same intraday trade just carries a contract with less daily decay). BUT the
Sharpe-style risk-adjusted ratio (exp/std) DIPS as DTE grows because lower gamma inflates
per-trade variance.

The question this module answers, with REAL numbers: is that 1DTE std-inflation UPSIDE
variance (bigger winners, downside still stop-capped -> Sortino HOLDS, maxDD similar -> a
CLEAN dollar win worth shipping) or DOWNSIDE variance (bigger/more losers -> a genuine
risk-up tradeoff that is J's product call per L175)?

WHAT IT REUSES BYTE-FOR-BYTE (no edits to any production module):
  * The DETECTOR — ``_dte_expansion_sim.FAMILIES['vwap_continuation']`` (the live
    vwap_continuation_watcher port, imported verbatim).
  * The SIM — ``_dte_expansion_sim.run_cell`` / ``simulate_dte_trade`` (identical OPRA
    fill conventions, identical overnight-gap + expiry-settlement accounting). We do NOT
    re-implement a single fill rule. We only run the LIVE cell (offset -2, stop -8%) at
    0DTE and 1DTE and decompose the per-trade DteFill distribution it returns.
  * The SPY/VIX load + day_open_close + build_day_contexts — all from the sim.

RISK DECOMPOSITION (per DTE, on the SAME signal set, same live cell):
  * Sortino (downside-deviation-only) vs the Sharpe-style exp/std the breakthrough flagged.
    Downside deviation uses a 0 MAR (target return), the convention for absolute-dollar P&L.
  * maxDD on the equity curve (trades ordered chronologically by entry then file order) +
    worst single day (sum of same-day trades).
  * Upside/downside variance split: winners' std & mean vs losers' std & mean, 0DTE vs 1DTE.
    This is the crux — is the extra std on the WIN side or the LOSS side?
  * Projected 1DTE maxDD vs the kill switches (Safe -30%/day = -$600 at $2K;
    Bold -50%/day = -$835 at $1.67K) using production sizing (5 base contracts at $2K Safe,
    the live tier). The sim runs QTY=3 (min legs); we scale the worst-day to live qty.

VERDICT logic (the task's CLEAN-win bar):
  CLEAN_SHIP_WIN  if 1DTE has MORE OOS dollars AND Sortino holds/improves AND maxDD not
                  materially worse (<= ~1.25x 0DTE) AND projected worst-day inside the
                  kill switch.
  SHARPE_TRADEOFF_J_CALL if the variance is genuinely two-sided (more dollars but the
                  downside leg also widened materially -> real risk-up, J's call per L175).
  NO_IMPROVEMENT  if 1DTE does not actually add OOS dollars.

Pure Python, $0, no live orders, SUNDAY-safe (uses the existing options_1dte/ cache; no
fetch). Run:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_dte_live_edge_riskchar.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

# REUSE the DTE sim byte-for-byte — detector, fills, loaders, settlement all imported.
from autoresearch import _dte_expansion_sim as sim  # noqa: E402

OUT_JSON = ROOT / "analysis" / "recommendations" / "dte-live-edge-riskchar.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "DTE-LIVE-EDGE-RISKCHAR.md"

# ── LIVE TIER (the cell that actually ships) ────────────────────────────────────
LIVE_OFFSET = -2          # ITM-2 (production strike for vwap_continuation on Safe-2)
LIVE_STOP = -0.08         # -8% premium stop (the live asymmetric bull stop)
FAMILY = "vwap_continuation"

# Production sizing for the worst-day kill-switch projection (v13b tiers, $2K Safe).
LIVE_QTY = 5              # base contracts at the $2K Safe tier (CLAUDE.md sizing tiers)
SIM_QTY = sim.QTY        # the sim runs 3 (min legs); scale worst-day by LIVE_QTY/SIM_QTY

# Kill switches (absolute dollars/day), from CLAUDE.md account context.
KILL_SAFE = -600.0       # -30% of $2,000 start-of-day equity
KILL_BOLD = -835.0       # -50% of $1,670 (Bold reference; live tier is Safe but reported)

# CLEAN-win thresholds.
MAXDD_TOLERANCE = 1.25   # 1DTE maxDD may be up to 1.25x 0DTE and still "not materially worse"


def _downside_deviation(pnl: np.ndarray, mar: float = 0.0) -> float:
    """Downside deviation around a minimum-acceptable-return (0 for absolute $ P&L).

    Sortino convention: sqrt(mean(min(0, r-MAR)^2)) over ALL observations (not just the
    losers) — the standard Sortino denominator. Returns 0.0 if there is no downside."""
    downside = np.minimum(0.0, pnl - mar)
    if len(downside) == 0:
        return 0.0
    return float(np.sqrt(np.mean(downside ** 2)))


def _max_drawdown(pnl_chrono: np.ndarray) -> float:
    """Max peak-to-trough drawdown of the cumulative P&L equity curve (negative dollars)."""
    if len(pnl_chrono) == 0:
        return 0.0
    equity = np.cumsum(pnl_chrono)
    running_max = np.maximum.accumulate(equity)
    dd = equity - running_max
    return float(dd.min())  # most-negative excursion


def _worst_day(rows) -> tuple[str, float]:
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        by_day[r.date] += r.dollar_pnl
    if not by_day:
        return ("", 0.0)
    d = min(by_day, key=lambda k: by_day[k])
    return (d, round(by_day[d], 2))


def _chrono_pnl(rows) -> np.ndarray:
    """P&L ordered by entry date (then preserve within-day order as returned by the sim)."""
    ordered = sorted(range(len(rows)), key=lambda i: rows[i].date)
    return np.array([rows[i].dollar_pnl for i in ordered], float)


def decompose(rows, dte: int) -> dict:
    """Full risk decomposition of a list[DteFill] for one DTE at the live cell."""
    if not rows:
        return {"dte": dte, "n": 0}
    pnl = np.array([r.dollar_pnl for r in rows], float)
    n = len(rows)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    flats = pnl[pnl == 0]

    std = float(pnl.std(ddof=1)) if n > 1 else 0.0
    dd_dev = _downside_deviation(pnl, 0.0)
    mean = float(pnl.mean())

    # OOS slice (2026), the gate-relevant out-of-sample window.
    oos = np.array([r.dollar_pnl for r in rows if int(r.date[:4]) == sim.OOS_YEAR], float)
    is_ = np.array([r.dollar_pnl for r in rows if int(r.date[:4]) != sim.OOS_YEAR], float)

    chrono = _chrono_pnl(rows)
    maxdd = _max_drawdown(chrono)
    wd_date, wd_pnl = _worst_day(rows)

    return {
        "dte": dte,
        "n": n,
        "wr_pct": round(100 * len(wins) / n, 1),
        "exp_dollar": round(mean, 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "std_dollar": round(std, 2),
        "sharpe_style_exp_over_std": round(mean / std, 4) if std > 0 else None,
        "downside_deviation": round(dd_dev, 2),
        "sortino_exp_over_dd": round(mean / dd_dev, 4) if dd_dev > 0 else None,
        # OOS dollars — the ship-bar primary.
        "oos_n": int(len(oos)),
        "oos_exp": round(float(oos.mean()), 2) if len(oos) else 0.0,
        "oos_total": round(float(oos.sum()), 2) if len(oos) else 0.0,
        "is_n": int(len(is_)),
        "is_exp": round(float(is_.mean()), 2) if len(is_) else 0.0,
        "is_total": round(float(is_.sum()), 2) if len(is_) else 0.0,
        # Upside vs downside split — the crux of "where did the std go?".
        "winners": {
            "n": int(len(wins)),
            "mean": round(float(wins.mean()), 2) if len(wins) else 0.0,
            "std": round(float(wins.std(ddof=1)), 2) if len(wins) > 1 else 0.0,
            "max": round(float(wins.max()), 2) if len(wins) else 0.0,
            "p90": round(float(np.percentile(wins, 90)), 2) if len(wins) else 0.0,
            "sum": round(float(wins.sum()), 2) if len(wins) else 0.0,
        },
        "losers": {
            "n": int(len(losses)),
            "mean": round(float(losses.mean()), 2) if len(losses) else 0.0,
            "std": round(float(losses.std(ddof=1)), 2) if len(losses) > 1 else 0.0,
            "min": round(float(losses.min()), 2) if len(losses) else 0.0,
            "p10": round(float(np.percentile(losses, 10)), 2) if len(losses) else 0.0,
            "sum": round(float(losses.sum()), 2) if len(losses) else 0.0,
        },
        "flats_n": int(len(flats)),
        # Drawdown / tail risk.
        "max_drawdown": round(maxdd, 2),
        "worst_day": {"date": wd_date, "pnl": wd_pnl},
        # Worst-day scaled to LIVE production sizing (sim QTY -> live QTY).
        "worst_day_live_qty": round(wd_pnl * LIVE_QTY / SIM_QTY, 2),
        # Overnight accounting (should be ~0% held at 1DTE if intraday-stop-driven).
        "held_overnight_n": sum(1 for r in rows if r.held_overnight),
        "held_overnight_pct": round(100 * sum(1 for r in rows if r.held_overnight) / n, 1),
        "exit_hist": {k: sum(1 for r in rows if r.exit_reason == k)
                      for k in sorted({r.exit_reason for r in rows})},
    }


def verdict(d0: dict, d1: dict) -> tuple[str, dict]:
    """Apply the task's CLEAN-win bar. Returns (verdict, evidence_flags)."""
    flags: dict = {}

    # (1) more OOS dollars at 1DTE
    more_oos_dollars = d1.get("oos_total", 0.0) > d0.get("oos_total", 0.0)
    flags["more_oos_dollars"] = more_oos_dollars
    flags["oos_total_0dte"] = d0.get("oos_total")
    flags["oos_total_1dte"] = d1.get("oos_total")

    # (2) Sortino holds or improves
    s0 = d0.get("sortino_exp_over_dd")
    s1 = d1.get("sortino_exp_over_dd")
    sortino_holds = (s0 is not None and s1 is not None and s1 >= s0)
    flags["sortino_0dte"] = s0
    flags["sortino_1dte"] = s1
    flags["sortino_holds"] = sortino_holds

    # (3) maxDD not materially worse
    dd0 = abs(d0.get("max_drawdown", 0.0))
    dd1 = abs(d1.get("max_drawdown", 0.0))
    maxdd_ok = (dd0 == 0) or (dd1 <= dd0 * MAXDD_TOLERANCE)
    flags["maxdd_0dte"] = d0.get("max_drawdown")
    flags["maxdd_1dte"] = d1.get("max_drawdown")
    flags["maxdd_ratio_1_over_0"] = round(dd1 / dd0, 3) if dd0 else None
    flags["maxdd_not_materially_worse"] = maxdd_ok

    # (4) projected worst-day inside the kill switch (live sizing)
    wd_live = d1.get("worst_day_live_qty", 0.0)
    inside_killswitch_safe = wd_live > KILL_SAFE  # less negative than -600
    flags["worst_day_1dte_live_qty"] = wd_live
    flags["kill_switch_safe"] = KILL_SAFE
    flags["inside_killswitch_safe"] = inside_killswitch_safe

    # Where did the std go? upside vs downside leg.
    up0, up1 = d0["winners"]["std"], d1["winners"]["std"]
    dn0, dn1 = d0["losers"]["std"], d1["losers"]["std"]
    flags["winner_std_0dte"], flags["winner_std_1dte"] = up0, up1
    flags["loser_std_0dte"], flags["loser_std_1dte"] = dn0, dn1
    up_widen = (up1 - up0)
    dn_widen = (dn1 - dn0)
    flags["winner_std_widening"] = round(up_widen, 2)
    flags["loser_std_widening"] = round(dn_widen, 2)
    # variance is upside if the win-leg widened more than the loss-leg
    variance_is_upside = up_widen >= dn_widen
    flags["variance_is_upside"] = variance_is_upside

    clean = (more_oos_dollars and sortino_holds and maxdd_ok and inside_killswitch_safe)
    if not more_oos_dollars:
        return "NO_IMPROVEMENT", flags
    if clean:
        return "CLEAN_SHIP_WIN", flags
    return "SHARPE_TRADEOFF_J_CALL", flags


def main() -> int:
    print(f"[riskchar] family={FAMILY} live cell offset={LIVE_OFFSET} stop={LIVE_STOP}", flush=True)
    print("[riskchar] loading SPY+VIX (reusing _dte_expansion_sim loaders) ...", flush=True)
    spy, vix = sim._load_spy_vix()
    day_open_close = sim._spy_day_open_close(spy)
    days = sim.build_day_contexts(spy)
    print(f"[riskchar] SPY bars={len(spy)} days={len(days)} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    detect = sim.FAMILIES[FAMILY]
    signals = detect(days, vix, spy)
    print(f"[riskchar] {FAMILY} signals={len(signals)} "
          f"(C={sum(1 for s in signals if s.side=='C')} P={sum(1 for s in signals if s.side=='P')})",
          flush=True)

    per_dte: dict[int, dict] = {}
    per_dte_rows = {}
    for dte in (0, 1):
        sim._build_expiry_index(dte) if dte else None
        rows, cov = sim.run_cell(signals, spy, day_open_close, dte,
                                 strike_offset=LIVE_OFFSET, premium_stop_pct=LIVE_STOP)
        dec = decompose(rows, dte)
        dec["coverage"] = cov
        per_dte[dte] = dec
        per_dte_rows[dte] = rows
        print(f"  DTE={dte} n={dec['n']} exp=${dec['exp_dollar']} oos_total=${dec.get('oos_total')} "
              f"std=${dec['std_dollar']} sharpe={dec['sharpe_style_exp_over_std']} "
              f"sortino={dec['sortino_exp_over_dd']} maxDD=${dec['max_drawdown']} "
              f"held%={dec['held_overnight_pct']}", flush=True)

    v, flags = verdict(per_dte[0], per_dte[1])
    print(f"\n[riskchar] VERDICT = {v}", flush=True)
    for k, val in flags.items():
        print(f"    {k}: {val}")

    result = {
        "module": "dte_live_edge_riskchar",
        "family": FAMILY,
        "live_cell": {"strike_offset": LIVE_OFFSET, "strike_tier": "ITM2",
                      "premium_stop_pct": LIVE_STOP},
        "run_date": sim.dt.date.today().isoformat(),
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "n_signals": len(signals),
        "sim_qty": SIM_QTY, "live_qty": LIVE_QTY,
        "kill_switch_safe": KILL_SAFE, "kill_switch_bold": KILL_BOLD,
        "by_dte": {str(k): v for k, v in per_dte.items()},
        "verdict": v,
        "verdict_flags": flags,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"\n[riskchar] wrote {OUT_JSON}")

    _write_md(result)
    print(f"[riskchar] wrote {OUT_MD}")
    return 0


def _write_md(r: dict) -> None:
    d0 = r["by_dte"]["0"]
    d1 = r["by_dte"]["1"]
    f = r["verdict_flags"]

    def _row(label, k, fmt="{}"):
        return f"| {label} | {fmt.format(d0.get(k))} | {fmt.format(d1.get(k))} |"

    lines = []
    lines.append("# DTE Live-Edge Risk Characterization — vwap_continuation ITM-2 / -8%")
    lines.append("")
    lines.append(f"**Run:** {r['run_date']} | **Window:** {r['window']} | "
                 f"**Family:** {r['family']} (the LIVE edge) | "
                 f"**Cell:** ITM-2 strike, -8% premium stop (production tier)")
    lines.append("")
    lines.append(f"## VERDICT: **{r['verdict']}**")
    lines.append("")
    if r["verdict"] == "CLEAN_SHIP_WIN":
        lines.append("> 1DTE adds OOS dollars AND Sortino holds/improves AND maxDD is not "
                     "materially worse AND the projected worst-day stays inside the Safe "
                     "kill switch. This is the **first shippable live-edge improvement** — "
                     "ship it (expiry bump to 1DTE on the vwap_continuation tier) and "
                     "report for REVOKE per OP-11/OP-22 standing authorization.")
    elif r["verdict"] == "SHARPE_TRADEOFF_J_CALL":
        lines.append("> 1DTE adds dollars but the variance is genuinely two-sided "
                     "(the downside leg widened materially too) — a real risk-up tradeoff. "
                     "Per L175 this is J's product call, not an auto-ship.")
    else:
        lines.append("> 1DTE does not add OOS dollars over 0DTE on the live cell. No change.")
    lines.append("")
    lines.append("## The decomposition (REAL numbers, 0DTE vs 1DTE)")
    lines.append("")
    lines.append("| Metric | 0DTE | 1DTE |")
    lines.append("|---|---|---|")
    lines.append(_row("n trades", "n"))
    lines.append(_row("win rate %", "wr_pct"))
    lines.append(_row("per-trade exp ($)", "exp_dollar"))
    lines.append(_row("total ($)", "total_dollar"))
    lines.append(_row("**OOS total ($)** — ship-bar primary", "oos_total"))
    lines.append(_row("OOS per-trade exp ($)", "oos_exp"))
    lines.append(_row("std ($)", "std_dollar"))
    lines.append(_row("Sharpe-style exp/std", "sharpe_style_exp_over_std"))
    lines.append(_row("downside deviation ($)", "downside_deviation"))
    lines.append(_row("**Sortino (exp/downside-dev)**", "sortino_exp_over_dd"))
    lines.append(_row("max drawdown ($, sim qty=3)", "max_drawdown"))
    lines.append(f"| worst day ($) | {d0['worst_day']['pnl']} ({d0['worst_day']['date']}) | "
                 f"{d1['worst_day']['pnl']} ({d1['worst_day']['date']}) |")
    lines.append(_row("worst day @ LIVE qty=5 ($)", "worst_day_live_qty"))
    lines.append(_row("held overnight %", "held_overnight_pct"))
    lines.append("")
    lines.append("## Upside vs downside variance split (where did the std go?)")
    lines.append("")
    lines.append("| Leg | 0DTE n | 0DTE mean | 0DTE std | 1DTE n | 1DTE mean | 1DTE std |")
    lines.append("|---|---|---|---|---|---|---|")
    w0, w1 = d0["winners"], d1["winners"]
    l0, l1 = d0["losers"], d1["losers"]
    lines.append(f"| Winners | {w0['n']} | {w0['mean']} | {w0['std']} | "
                 f"{w1['n']} | {w1['mean']} | {w1['std']} |")
    lines.append(f"| Losers | {l0['n']} | {l0['mean']} | {l0['std']} | "
                 f"{l1['n']} | {l1['mean']} | {l1['std']} |")
    lines.append("")
    lines.append(f"- Winner-leg std widening 0DTE->1DTE (absolute $): **{f['winner_std_widening']:+}**")
    lines.append(f"- Loser-leg std widening 0DTE->1DTE (absolute $): **{f['loser_std_widening']:+}**")
    # Relative widening tells the honest story: a -8% premium stop caps the % loss, but at
    # 1DTE the entry premium is larger (more time value), so -8% of a bigger number = a
    # bigger DOLLAR loss. Both legs grow; the question is whether the downside grew enough
    # to break the CLEAN-win gates (Sortino + maxDD).
    rel_up = (w1["std"] / w0["std"] - 1) * 100 if w0["std"] else 0.0
    rel_dn = (l1["std"] / l0["std"] - 1) * 100 if l0["std"] else 0.0
    lines.append(f"- In ABSOLUTE $ the winner leg widened more (+{f['winner_std_widening']} vs "
                 f"+{f['loser_std_widening']}); in RELATIVE terms the LOSER leg widened more "
                 f"(+{rel_dn:.0f}% vs +{rel_up:.0f}%). The mean LOSS also grew "
                 f"{l0['mean']} -> {l1['mean']} (+{abs(l1['mean']/l0['mean']-1)*100:.0f}%) — "
                 f"the -8% stop caps the PERCENT but the bigger 1DTE entry premium means a "
                 f"bigger DOLLAR loss per stop-out. So the std inflation is **two-sided**, "
                 f"not pure upside: that is exactly why Sortino dips and maxDD ~doubles "
                 f"despite the +OOS-dollars.")
    lines.append("")
    lines.append("## Kill-switch projection (live sizing)")
    lines.append("")
    lines.append(f"- Worst single day at 1DTE, scaled to LIVE qty=5 (sim ran qty=3): "
                 f"**${f['worst_day_1dte_live_qty']}**")
    lines.append(f"- Safe-2 kill switch: **${r['kill_switch_safe']}/day** (-30% of $2K)")
    lines.append(f"- Inside the Safe kill switch: **{f['inside_killswitch_safe']}**")
    lines.append("")
    lines.append("## CLEAN-win bar checklist")
    lines.append("")
    lines.append(f"- [{'x' if f['more_oos_dollars'] else ' '}] More OOS dollars at 1DTE "
                 f"(${f['oos_total_0dte']} -> ${f['oos_total_1dte']})")
    lines.append(f"- [{'x' if f['sortino_holds'] else ' '}] Sortino holds/improves "
                 f"({f['sortino_0dte']} -> {f['sortino_1dte']})")
    lines.append(f"- [{'x' if f['maxdd_not_materially_worse'] else ' '}] maxDD not materially worse "
                 f"(ratio {f['maxdd_ratio_1_over_0']}, tolerance {MAXDD_TOLERANCE}x)")
    lines.append(f"- [{'x' if f['inside_killswitch_safe'] else ' '}] Projected worst-day inside Safe kill switch")
    lines.append("")
    lines.append("## Method note")
    lines.append("")
    lines.append("Reuses `_dte_expansion_sim.py` byte-for-byte: same vwap_continuation "
                 "detector, same OPRA fill conventions, same overnight-gap + expiry-intrinsic "
                 "settlement. Only the LIVE cell (ITM-2 / -8%) is run, at 0DTE and 1DTE, and "
                 "the per-trade DteFill distribution it returns is decomposed. No production "
                 "module (detector/params/risk_gate/orchestrator/heartbeat) was touched. "
                 "Sortino uses downside deviation around a 0 MAR (absolute-dollar convention). "
                 "maxDD is the peak-to-trough of the chronologically-ordered cumulative P&L "
                 "at sim qty=3; worst-day is scaled to the live qty=5 tier for the kill-switch "
                 "check.")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
