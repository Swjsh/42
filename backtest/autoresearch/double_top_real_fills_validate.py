"""Real-fills validation of double_top_watcher (PUT side) — OPRA, 16mo, OOS-split.

Mirror of db_base_quiet_real_fills_validate.py for the bearish double-top (M-pattern).
The double_top_watcher is deliberately UN-gated (no conf/VIX/proximity) — it gathers an
unbiased SPY 5m sample — so this tests the FULL double-top population as puts.

Per C1 (real-fills authority) + C3/L58 (SPY-shape != option edge). Entry on neckline-break
(close below the min-low-between the two tops); side=P; ATM; qty 3; chart-stop-only
(premium_stop=-0.99) with rejection_level = neckline + $0.30 (put chart stop above neckline);
v15 exits. OP-20 disclosure: per-trade expectancy, IS/OOS, by-quarter, top5-day concentration.

Output: analysis/recommendations/double-top-real-fills.json  +  STATUS verdict line.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from autoresearch import runner as ar_runner  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from crypto.lib.chart_patterns import Bar, double_top_detector as _detect_dt  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger(__name__)

OUT = ROOT / "analysis" / "recommendations" / "double-top-real-fills.json"
QTY = 3
PREMIUM_STOP_PCT = -0.99      # chart-stop only
STRIKE_OFFSET = 0             # ATM (the watcher is un-gated; sweep strikes later only if +EV)
RTH_START, RTH_END = dt.time(9, 35), dt.time(15, 55)
COOLDOWN_MIN = 30
_CHART_STOP_ABOVE_NECKLINE = 0.30
START, END = dt.date(2025, 1, 1), dt.date(2026, 5, 15)


def _quarter(d):  # 2025Q1..
    return f"{d.year}Q{(d.month - 1)//3 + 1}"


def _make_bars(rth, idx, window=30):
    sub = rth.iloc[max(0, idx - window + 1): idx + 1]
    out = []
    for _, row in sub.iterrows():
        ts = pd.Timestamp(row["timestamp_et"])
        if ts.tzinfo is not None:
            ts = ts.tz_localize(None)
        out.append(Bar(open_time=ts.to_pydatetime().replace(tzinfo=dt.timezone.utc),
                       open=float(row["open"]), high=float(row["high"]), low=float(row["low"]),
                       close=float(row["close"]), volume=int(row.get("volume", 50000) or 50000),
                       granularity_seconds=300, source="spy_5m"))
    return out


def run():
    log.info("Loading %s..%s", START, END)
    spy, _ = ar_runner.load_data(START, END)
    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"])
    rth = spy[(spy["timestamp_et"].dt.time >= dt.time(9, 30)) & (spy["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    log.info("RTH bars: %d", len(rth))

    signals, last_t = [], None
    for idx in range(30, len(rth)):
        bar = rth.iloc[idx]
        t = pd.Timestamp(bar["timestamp_et"])
        tn = t.tz_localize(None).to_pydatetime() if t.tz is not None else t.to_pydatetime()
        if not (RTH_START <= tn.time() <= RTH_END):
            continue
        if last_t and (tn - last_t).total_seconds() / 60.0 < COOLDOWN_MIN:
            continue
        bars = _make_bars(rth, idx)
        if len(bars) < 10:
            continue
        hit = _detect_dt(bars)
        if hit is None or hit.bias != "bearish":
            continue
        last_t = tn
        neckline = float(hit.notes.get("neckline", hit.key_price))
        signals.append({"idx": idx, "date": tn.date(), "bar": bar,
                        "rejection_level": neckline + _CHART_STOP_ABOVE_NECKLINE,
                        "conf": round(hit.confidence, 3)})

    log.info("Signals: %d. Real-fills...", len(signals))
    by_day = defaultdict(float)
    by_q = defaultdict(lambda: {"n": 0, "pnl": 0.0})
    is_pnl = is_n = oos_pnl = oos_n = 0.0
    wins = n = nodata = 0
    total = 0.0
    rows = []
    for s in signals:
        fill = simulate_trade_real(entry_bar_idx=s["idx"], entry_bar=s["bar"], spy_df=rth, ribbon_df=None,
                                   rejection_level=s["rejection_level"],
                                   triggers_fired=["double_top_detector", "neckline_break"],
                                   side="P", qty=QTY, setup="DOUBLE_TOP", premium_stop_pct=PREMIUM_STOP_PCT,
                                   strike_offset=STRIKE_OFFSET)
        if fill is None:
            nodata += 1
            continue
        pnl = fill.dollar_pnl
        n += 1
        total += pnl
        wins += 1 if pnl > 0 else 0
        d = s["date"].isoformat()
        by_day[d] += pnl
        q = _quarter(s["date"])
        by_q[q]["n"] += 1
        by_q[q]["pnl"] += pnl
        if s["date"].year == 2025:
            is_pnl += pnl; is_n += 1
        else:
            oos_pnl += pnl; oos_n += 1
        rows.append({"date": d, "conf": s["conf"], "strike": fill.strike,
                     "pnl": round(pnl, 2),
                     "exit": fill.exit_reason.value if hasattr(fill.exit_reason, "value") else str(fill.exit_reason)})

    days_sorted = sorted(by_day.values(), reverse=True)
    top5_pct = round(100 * sum(days_sorted[:5]) / total, 0) if total > 0 else None
    pos_q = sum(1 for q in by_q.values() if q["pnl"] > 0)
    q_report = {k: {"n": v["n"], "pnl": round(v["pnl"], 0)} for k, v in sorted(by_q.items())}
    summary = {
        "run_date": dt.date.today().isoformat(), "family": "double_top", "side": "P",
        "window": f"{START}..{END}", "authority": "real OPRA fills (C1)",
        "n_signals": len(signals), "n_completed": n, "n_no_opra": nodata,
        "wr_pct": round(100 * wins / n, 1) if n else None,
        "total_pnl": round(total, 0), "per_trade": round(total / n, 1) if n else None,
        "is_2025": {"n": int(is_n), "per_trade": round(is_pnl / is_n, 1) if is_n else None, "total": round(is_pnl, 0)},
        "oos_2026": {"n": int(oos_n), "per_trade": round(oos_pnl / oos_n, 1) if oos_n else None, "total": round(oos_pnl, 0)},
        "positive_quarters": f"{pos_q}/{len(by_q)}", "by_quarter": q_report, "top5_day_pct": top5_pct,
        "DISCLOSURE": {
            "per_trade": "expectancy reported, not WR alone (OP-14)",
            "spy_vs_option": "SPY-shape != option edge; this is the option test (C3/L58)",
            "un_gated": "double_top_watcher has NO conf/VIX/proximity gate -> full unbiased population (ATM, chart-stop-only)",
            "sample": "single honest read, NOT a grid survivor (anti-pattern 2.10)",
        },
        "results": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    verdict = ("TRADEABLE?" if (n and total > 0 and pos_q >= 4) else "NOT TRADEABLE (negative or regime-fragile)")
    print("\n=== DOUBLE_TOP REAL-FILLS ===")
    print(f"signals={len(signals)} completed={n} no_opra={nodata}")
    print(f"WR={summary['wr_pct']}% per_trade=${summary['per_trade']} total=${summary['total_pnl']} posQ={summary['positive_quarters']} top5%={top5_pct}")
    print(f"IS={summary['is_2025']}  OOS={summary['oos_2026']}")
    print(f"VERDICT: {verdict}")
    return summary


if __name__ == "__main__":
    run()
