"""ADVERSARIAL validation of the ACTUAL missed-week all-green config found by the
sweep: ATM strike, -50% premium stop, FIXED profit-lock (i.e. PL off), tp1 30%,
qf 0.33, bull-trigger=1. Gate (OP-16): does the wide -50% stop still CAPTURE the
J-edge bear anchors, or does it let losers bleed to -50%? Real run_backtest, real
fills. Writes a verdict file. Robust: each run wrapped in try/except."""
from __future__ import annotations
import sys, datetime as dt, traceback
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from lib.orchestrator import run_backtest  # noqa
DATA = REPO / "data"
OUT = REPO.parent / "analysis" / "green-config-validation.md"


def _norm(df):
    ts = pd.to_datetime(df["timestamp_et"], format="ISO8601", utc=True).dt.tz_convert("America/New_York")
    df = df.copy()
    df["timestamp_et"] = ts.dt.strftime("%Y-%m-%d %H:%M:%S-04:00")
    return df


def perday(trades, dates):
    pd_ = {d: 0.0 for d in dates}
    pc_ = {d: 0.0 for d in dates}
    for t in trades:
        d = t.entry_time_et.date()
        if d in pd_:
            pd_[d] += t.dollar_pnl
            pc_[d] += t.dollar_pnl / max(1, t.qty)
    return pd_, pc_


def captures(trades, date_iso, side):
    for t in trades:
        if t.entry_time_et.date().isoformat() == date_iso and t.dollar_pnl > 0:
            c = "C" if "BULLISH" in t.setup else "P"
            if c == side:
                return round(t.dollar_pnl / max(1, t.qty), 1), t.entry_time_et.strftime("%H:%M"), int(t.strike)
    return None


def worst_loss_per_contract(trades, side):
    worst = 0.0
    for t in trades:
        c = "C" if "BULLISH" in t.setup else "P"
        if c == side:
            pc = t.dollar_pnl / max(1, t.qty)
            worst = min(worst, pc)
    return round(worst, 1)


# The ACTUAL best all-green config (analysis/missed-green-sweep.md row 1).
GREEN = dict(premium_stop_pct=-0.50, tp1_premium_pct=0.30, tp1_qty_fraction=0.33,
             strike_offset=0, min_triggers_bull=1,
             profit_lock_mode="fixed", profit_lock_threshold_pct=0.0,
             profit_lock_trail_pct=0.0, no_trade_before=dt.time(9, 35))
PROD = dict(premium_stop_pct=-0.08, tp1_premium_pct=0.30, tp1_qty_fraction=0.667,
            strike_offset=-2, no_trade_before=dt.time(9, 35))

out = ["# All-green config — adversarial validation (CORRECTED)", "",
       "**ACTUAL best config from the 256-combo sweep:** ATM strike, **-50% premium stop**, "
       "FIXED profit-lock (trailing PL OFF), TP1 +30%, qf 0.33, bull-trigger=1. "
       "Missed week: +521/+676/+393/+788 = 4/4 GREEN (+148.3/contract).", "",
       "**The gate (OP-16):** a -50% stop is very wide (half the premium at risk). Does it still "
       "capture J's bear anchors, or does it let losers bleed to -50%? A config that wins the "
       "bull week but turns the bear book's small losses into -50% disasters is REJECTED.", ""]


def run_safe(name, spy, vix, a0, a1, cfg, disable=None):
    try:
        r = run_backtest(spy, vix, start_date=a0, end_date=a1, use_real_fills=True,
                         disable_filters=disable, **cfg)
        return r
    except Exception:
        out.append(f"- {name}: ERROR\n```\n{traceback.format_exc()[-800:]}\n```")
        return None


# ---- A) J-anchor window ----
aspy = DATA / "spy_5m_2025-01-01_2026-05-07.csv"
out.append("## A) J-edge anchor window 2026-04-27..05-07 (bear puts; filter 8 off)")
if aspy.exists():
    spy = _norm(pd.read_csv(aspy)); vix = _norm(pd.read_csv(DATA / "vix_5m_2025-01-01_2026-05-07.csv"))
    a0, a1 = dt.date(2026, 4, 27), dt.date(2026, 5, 7)
    out.append("| config | trades | total/c | 5/04 capture | 4/29 capture | worst put loss/c |")
    out.append("|---|---|---|---|---|---|")
    for name, cfg in [("PROD (ITM2,-8%)", PROD), ("GREEN (ATM,-50%)", GREEN)]:
        r = run_safe(name, spy, vix, a0, a1, cfg, disable=[8])
        if r is None:
            continue
        totpc = sum(t.dollar_pnl / max(1, t.qty) for t in r.trades)
        out.append(f"| {name} | {len(r.trades)} | {totpc:+.1f} | {captures(r.trades,'2026-05-04','P')} | "
                   f"{captures(r.trades,'2026-04-29','P')} | {worst_loss_per_contract(r.trades,'P')} |")
    out.append("")
    out.append("**Gate A read:** GREEN must still show a 5/04 capture (a winning put). Compare the "
               "WORST put loss/contract: if -50% turns small -8% losses into deep -50% losses, that "
               "is the cost of the wide stop on the bear book — weigh against the bull-week gain.")
else:
    out.append("_anchor master csv not found_")
out.append("")

# ---- B) missed week side-by-side ----
mspy = DATA / "spy_5m_2026-05-19_2026-05-29.csv"
spy = _norm(pd.read_csv(mspy)); vix = _norm(pd.read_csv(DATA / "vix_5m_2026-05-19_2026-05-29.csv"))
m = [dt.date(2026, 5, 26), dt.date(2026, 5, 27), dt.date(2026, 5, 28), dt.date(2026, 5, 29)]
out.append("## B) Missed week 2026-05-26..29 — GREEN vs PROD (per-contract by day)")
out.append("| config | 05-26 | 05-27 | 05-28 | 05-29 | green | total/c | n |")
out.append("|---|---|---|---|---|---|---|---|")
for name, cfg in [("PROD (ITM2,-8%)", PROD), ("GREEN (ATM,-50%)", GREEN)]:
    r = run_safe(name, spy, vix, m[0], m[-1], cfg)
    if r is None:
        continue
    pd_, pc_ = perday(r.trades, m)
    g = sum(1 for d in m if pd_[d] > 0)
    cells = " | ".join(f"{pc_[d]:+.1f}" for d in m)
    out.append(f"| {name} | {cells} | {g}/4 | {sum(pc_.values()):+.1f} | {len(r.trades)} |")
out.append("")
out.append("## Verdict")
out.append("- If GREEN keeps the 5/04 capture AND its worst-put-loss isn't catastrophically deeper "
           "than PROD's, the -50%-stop / no-trailing-PL finding is a real candidate for J + OOS.")
out.append("- KEY SECONDARY FINDING from the sweep: pl-FIXED beat pl-TRAILING on 05-28 (+393 vs "
           "-94). The trailing profit-lock was arming on the chop then stopping out — it was PART "
           "of the chop problem, not just the stop width.")
out.append("- HONEST RISK: a -50% stop means one max loss = half the position. Sizing/kill-switch "
           "interaction must be checked before this is anything but a research hypothesis (Rule 9).")
OUT.write_text("\n".join(out), encoding="utf-8")
print("wrote", OUT)
