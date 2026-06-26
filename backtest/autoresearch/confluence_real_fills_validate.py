"""Real-fills validation of the CONFLUENCE / STRUCTURE / BULL-TILT claims (OPRA sim).

J's challenge: "I don't believe a word until I see you've backtested it to infinity."
Correct -- the forward-return study (structure_edge_study.py) was a SPY-DIRECTION proxy,
explicitly NOT an option edge (C3/L58). This script replaces the proxy with ACTUAL 0DTE
option P&L via simulator_real.simulate_trade_real, the only WR authority (C1).

The test: at every FRESH structure break (BOS/CHoCH printing on the current bar) where the
confluence bias agrees and conviction >= threshold, simulate a 0DTE option (CALL for
bullish, PUT for bearish), chart-stop-only (premium_stop=-0.99), ATM, qty 3, v15 exits.
Then stratify by bias / IS(2025) vs OOS(2026) / quarter / VIX -- per OP-11, OP-16, OP-20.

Honest possible verdicts (all fine):
  - bull-side real-fills expectancy > 0 OOS, bear-side <= 0  -> bull-tilt SURVIVES on options
  - both <= 0                                                -> confluence is NOT a trigger (awareness only)
  - neither stable OOS                                       -> KILL the trigger idea

Disclosure (OP-20): per-trade expectancy (not WR alone), top-5-day concentration, positive
quarters, IS/OOS per-month-normalized, account-scaling note. SPY-direction != option edge.

Pure Python, $0. Writes analysis/recommendations/confluence-real-fills-{tag}.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from autoresearch import runner as ar_runner  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.confluence import compute_confluence  # noqa: E402
from crypto.lib.market_structure import analyze_structure  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger(__name__)

QTY = 3
STRIKE_OFFSET = 0
PREMIUM_STOP_PCT = -0.99      # chart-stop only (C2/L55)
TRAIL = 60                    # trailing bars for structure/confluence
WARMUP = 12                   # bars into the day before evaluating
COOLDOWN_MIN = 45            # anti-pattern 2.7 (no back-to-back same-setup churn)
START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)


def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


class _Acc:
    __slots__ = ("n", "wins", "pnl", "by_day")

    def __init__(self):
        self.n = 0
        self.wins = 0
        self.pnl = 0.0
        self.by_day: dict[str, float] = defaultdict(float)

    def add(self, pnl: float, day: str):
        self.n += 1
        self.wins += 1 if pnl > 0 else 0
        self.pnl += pnl
        self.by_day[day] += pnl

    def report(self) -> dict:
        if not self.n:
            return {"n": 0}
        days_sorted = sorted(self.by_day.values(), reverse=True)
        top5 = sum(days_sorted[:5])
        return {
            "n": self.n,
            "wr": round(100 * self.wins / self.n, 1),
            "total_pnl": round(self.pnl, 0),
            "avg_pnl": round(self.pnl / self.n, 1),
            "top5_day_pct": round(100 * top5 / self.pnl, 0) if self.pnl > 0 else None,
        }


def run(conviction_min: float, fresh_only: bool, tag: str) -> dict:
    log.info("Loading %s..%s SPY+VIX", START, END)
    spy_full, vix_full = ar_runner.load_data(START, END)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    rth = spy_full[(spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
                   & (spy_full["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    rth["date"] = rth["timestamp_et"].dt.date
    log.info("RTH bars: %d", len(rth))

    # VIX aligned (ffill)
    vix_full["timestamp_et"] = pd.to_datetime(
        vix_full["timestamp_et"] if "timestamp_et" in vix_full.columns else vix_full.index)
    vix_ser = vix_full.set_index("timestamp_et")["close"] if "close" in vix_full.columns else vix_full.iloc[:, 0]
    rth_naive = rth["timestamp_et"].dt.tz_localize(None) if rth["timestamp_et"].dt.tz is not None else rth["timestamp_et"]
    vix_arr = []
    for ts in rth_naive:
        try:
            j = vix_ser.index.get_indexer([ts], method="ffill")[0]
            vix_arr.append(float(vix_ser.iloc[j]) if j >= 0 else 17.0)
        except Exception:
            vix_arr.append(17.0)

    # precompute crypto Bars per row (once)
    log.info("Building bars + scanning for fresh-break confluence signals...")
    all_bars: list[Bar] = []
    for _, r in rth.iterrows():
        ts = pd.Timestamp(r["timestamp_et"])
        if ts.tzinfo is not None:
            ts = ts.tz_localize(None)
        all_bars.append(Bar(open_time=ts.to_pydatetime().replace(tzinfo=dt.timezone.utc),
                            open=float(r["open"]), high=float(r["high"]), low=float(r["low"]),
                            close=float(r["close"]), volume=int(r.get("volume", 50000) or 50000),
                            granularity_seconds=300, source="spy"))

    # day boundaries (start index of each date)
    day_start: dict[dt.date, int] = {}
    for i, d in enumerate(rth["date"]):
        if d not in day_start:
            day_start[d] = i

    signals: list[dict] = []
    last_sig_time: dt.datetime | None = None
    for idx in range(len(rth)):
        d = rth["date"].iloc[idx]
        i0 = day_start[d]
        local = idx - i0
        if local < WARMUP:
            continue
        trailing = all_bars[max(i0, idx - TRAIL + 1): idx + 1]
        if len(trailing) < 10:
            continue
        ms = analyze_structure(trailing)
        fresh = ms.last_event is not None and ms.last_event.break_index == len(trailing) - 1
        if fresh_only and not fresh:
            continue
        read = compute_confluence(trailing)
        if read.bias == "neutral" or read.conviction < conviction_min:
            continue
        if fresh and ((ms.last_event.direction == "bullish") != (read.bias == "bullish")):
            continue  # require break direction to agree with confluence bias
        bar_time = all_bars[idx].open_time.replace(tzinfo=None)
        if last_sig_time is not None and (bar_time - last_sig_time).total_seconds() / 60.0 < COOLDOWN_MIN:
            continue
        last_sig_time = bar_time
        side = "C" if read.bias == "bullish" else "P"
        rej = read.invalidation
        if rej is None:
            continue
        signals.append({"idx": idx, "date": d, "side": side, "bias": read.bias,
                        "conviction": read.conviction, "vix": round(vix_arr[idx], 1),
                        "rejection_level": float(rej), "fresh": fresh,
                        "time": bar_time.strftime("%H:%M")})

    log.info("Signals: %d. Running OPRA real-fills...", len(signals))

    overall = _Acc()
    by_bias = {"bullish": _Acc(), "bearish": _Acc()}
    by_sample = {"IS_2025": _Acc(), "OOS_2026": _Acc()}
    by_q: dict[str, _Acc] = defaultdict(_Acc)
    by_vix = {"lt17": _Acc(), "17to22": _Acc(), "gte22": _Acc()}
    no_data = 0
    rows: list[dict] = []

    for s in signals:
        fill = simulate_trade_real(
            entry_bar_idx=s["idx"], entry_bar=rth.iloc[s["idx"]], spy_df=rth, ribbon_df=None,
            rejection_level=s["rejection_level"],
            triggers_fired=["confluence", "structure_break" if s["fresh"] else "structure", s["bias"]],
            side=s["side"], qty=QTY, setup="CONFLUENCE", premium_stop_pct=PREMIUM_STOP_PCT,
            strike_offset=STRIKE_OFFSET)
        if fill is None:
            no_data += 1
            continue
        pnl = fill.dollar_pnl
        day = s["date"].isoformat()
        overall.add(pnl, day)
        by_bias[s["bias"]].add(pnl, day)
        by_sample["IS_2025" if s["date"].year == 2025 else "OOS_2026"].add(pnl, day)
        by_q[_quarter(s["date"])].add(pnl, day)
        vb = "lt17" if s["vix"] < 17 else ("17to22" if s["vix"] < 22 else "gte22")
        by_vix[vb].add(pnl, day)
        rows.append({"date": day, "time": s["time"], "bias": s["bias"], "side": s["side"],
                     "conviction": s["conviction"], "vix": s["vix"], "fresh": s["fresh"],
                     "strike": fill.strike, "entry_premium": round(fill.entry_premium, 3),
                     "pnl": round(pnl, 2),
                     "exit": fill.exit_reason.value if hasattr(fill.exit_reason, "value") else str(fill.exit_reason)})

    q_reports = {k: by_q[k].report() for k in sorted(by_q)}
    pos_q = sum(1 for r in q_reports.values() if r.get("total_pnl", 0) and r["total_pnl"] > 0)
    is_r, oos_r = by_sample["IS_2025"].report(), by_sample["OOS_2026"].report()
    # per-month normalized OOS/IS (IS ~12mo, OOS ~4.5mo)
    is_pm = (is_r.get("total_pnl", 0) / 12.0) if is_r.get("n") else 0
    oos_pm = (oos_r.get("total_pnl", 0) / 4.5) if oos_r.get("n") else 0
    wf_ratio = round(oos_pm / is_pm, 2) if is_pm > 0 else None

    summary = {
        "run_date": dt.date.today().isoformat(),
        "tag": tag,
        "params": {"conviction_min": conviction_min, "fresh_only": fresh_only, "qty": QTY,
                   "strike_offset": STRIKE_OFFSET, "premium_stop_pct": PREMIUM_STOP_PCT,
                   "cooldown_min": COOLDOWN_MIN, "trailing": TRAIL},
        "window": f"{START}..{END}",
        "n_signals": len(signals), "n_no_opra_data": no_data,
        "overall": overall.report(),
        "by_bias": {k: v.report() for k, v in by_bias.items()},
        "by_sample": {k: v.report() for k, v in by_sample.items()},
        "walk_forward_oos_per_month_ratio": wf_ratio,
        "by_quarter": q_reports,
        "positive_quarters": f"{pos_q}/{len(q_reports)}",
        "by_vix": {k: v.report() for k, v in by_vix.items()},
        "DISCLOSURE": {
            "authority": "real OPRA fills (C1) -- supersedes the SPY-direction proxy study",
            "spy_vs_option": "SPY-direction != option edge; this is the option-edge test (C3/L58)",
            "per_trade": "expectancy (avg_pnl) reported, not WR alone (OP-14)",
            "concentration": "top5_day_pct shown per cut (OP-20 #5)",
            "account_scaling": "qty=3 ATM ~ $300-600 capital/trade; fits the $2K Safe per-trade cap",
            "sample_caveat": "no parameter grid was searched here -- this is a single honest read, not a survivor",
        },
        "results": rows,
    }
    out = ROOT / "analysis" / "recommendations" / f"confluence-real-fills-{tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", out)

    print("\n=== CONFLUENCE REAL-FILLS VERDICT ===")
    print(f"signals={len(signals)} completed={overall.n} no_opra={no_data}")
    print(f"OVERALL  : {overall.report()}")
    print(f"BULL(C)  : {by_bias['bullish'].report()}")
    print(f"BEAR(P)  : {by_bias['bearish'].report()}")
    print(f"IS 2025  : {is_r}")
    print(f"OOS 2026 : {oos_r}   wf_per_month_ratio={wf_ratio}")
    print(f"pos_quarters={pos_q}/{len(q_reports)}  by_quarter={q_reports}")
    print(f"by_vix={ {k: v.report() for k, v in by_vix.items()} }")
    return summary


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--conviction-min", type=float, default=50.0)
    p.add_argument("--fresh-only", action="store_true", default=False)
    p.add_argument("--tag", default="base")
    args = p.parse_args(argv)
    run(args.conviction_min, args.fresh_only, args.tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
