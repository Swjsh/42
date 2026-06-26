"""structure_edge_study -- does our confluence read actually PREDICT SPY direction?

The elite move is not more patterns; it's MEASURING edge on our own instrument.
This runs the confluence engine CAUSALLY across N months of SPY 5m bars and asks
the only question that matters: as conviction rises, does forward edge rise?

For each evaluation bar i (warmup'd, within an RTH session):
  read   = compute_confluence(trailing LOOKBACK bars up to and INCLUDING i)   # causal
  fwd    = bars i+1 .. i+K (same session only -- 0DTE is flat by EOD)
  win    = directional bracket: did +TARGET print before -STOP, in the read's bias?

Buckets: conviction band, bias, structure-event presence, time-of-day.

DISCLOSURE (C3 / L58): this measures SPY-PRICE direction, which is necessary but
NOT sufficient for an OPTION edge -- delta/theta/stop-misfire corrupt the
translation. Treat the output as a RANKING/screening signal that validates (or
refutes) the confluence weighting. The real-fills simulator remains the option-edge
authority before anything goes live.

Pure Python, $0, no look-ahead. Writes analysis/structure-edge-study-{tag}.json.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from crypto.lib.bar import Bar
from crypto.lib.confluence import compute_confluence
from crypto.lib.market_structure import analyze_structure

LOOKBACK = 60      # bars of context per causal read (~5h on 5m)
WARMUP = 24        # don't evaluate until this many bars into the session
K_FWD = 6          # forward horizon (~30 min)
TARGET_PCT = 0.0015
STOP_PCT = 0.0015


def _rows_by_date(csv_path: Path) -> dict[str, list[dict]]:
    by_date: dict[str, list[dict]] = collections.defaultdict(list)
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            d = row.get("timestamp_et", "")[:10]
            if d:
                by_date[d].append(row)
    return by_date


def _to_bars(rows: list[dict]) -> list[Bar]:
    bars: list[Bar] = []
    for r in rows:
        try:
            ts = r["timestamp_et"]
            dt = datetime.fromisoformat(ts).astimezone(timezone.utc)
            o, h, l, c = float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])
            v = float(r.get("volume", 0) or 0)
        except (KeyError, ValueError, TypeError):
            continue
        if h < l:
            h, l = l, h
        bars.append(Bar(open_time=dt, open=o, high=h, low=l, close=c, volume=v,
                        granularity_seconds=300, source="csv"))
    return bars


def _hour_et(row: dict) -> int:
    try:
        return int(row["timestamp_et"][11:13])
    except (KeyError, ValueError):
        return 0


def _bracket(entry: float, fwd: list[Bar], direction: str) -> str:
    """Conservative (stop-checked-first) directional bracket over the forward bars."""
    tgt_up, stop_up = entry * (1 + TARGET_PCT), entry * (1 + STOP_PCT)
    tgt_dn, stop_dn = entry * (1 - TARGET_PCT), entry * (1 - STOP_PCT)
    for b in fwd:
        if direction == "bullish":
            if b.low <= entry * (1 - STOP_PCT):
                return "loss"
            if b.high >= tgt_up:
                return "win"
        else:
            if b.high >= entry * (1 + STOP_PCT):
                return "loss"
            if b.low <= tgt_dn:
                return "win"
    final = fwd[-1].close
    ret = (final - entry) * (1 if direction == "bullish" else -1)
    return "win" if ret > 0 else "loss"


def _conv_band(c: float) -> str:
    for lo in (80, 60, 40, 20):
        if c >= lo:
            return f"{lo}-{lo + 20}"
    return "0-20"


class _Acc:
    __slots__ = ("n", "wins", "bps")

    def __init__(self):
        self.n = 0
        self.wins = 0
        self.bps = 0.0

    def add(self, win: bool, bps: float):
        self.n += 1
        self.wins += 1 if win else 0
        self.bps += bps

    def report(self) -> dict:
        return {
            "n": self.n,
            "win_rate": round(100 * self.wins / self.n, 1) if self.n else None,
            "mean_fwd_bps": round(self.bps / self.n, 1) if self.n else None,
        }


def run(csv_path: Path, max_days: int | None, step: int) -> dict:
    by_date = _rows_by_date(csv_path)
    dates = sorted(by_date)
    if max_days:
        dates = dates[-max_days:]

    by_conv = collections.defaultdict(_Acc)
    by_bias = collections.defaultdict(_Acc)
    by_event = collections.defaultdict(_Acc)
    by_time = collections.defaultdict(_Acc)
    by_fresh = collections.defaultdict(_Acc)          # break printed THIS bar = decision point
    by_fresh_conv = collections.defaultdict(_Acc)     # fresh-break reads, bucketed by conviction
    overall = _Acc()
    evaluated = 0

    for d in dates:
        rows = by_date[d]
        bars = _to_bars(rows)
        n = len(bars)
        if n < WARMUP + K_FWD + 2:
            continue
        for i in range(WARMUP, n - K_FWD, step):
            trailing = bars[max(0, i - LOOKBACK + 1): i + 1]
            read = compute_confluence(trailing)
            if read.bias == "neutral":
                continue
            entry = bars[i].close
            fwd = bars[i + 1: i + 1 + K_FWD]
            if not fwd:
                continue
            outcome = _bracket(entry, fwd, read.bias)
            win = outcome == "win"
            bps = (fwd[-1].close - entry) / entry * 10000 * (1 if read.bias == "bullish" else -1)
            ms = analyze_structure(trailing)
            fresh = ms.last_event is not None and ms.last_event.break_index == len(trailing) - 1 \
                and ((ms.last_event.direction == "bullish") == (read.bias == "bullish"))
            evaluated += 1
            overall.add(win, bps)
            by_conv[_conv_band(read.conviction)].add(win, bps)
            by_bias[read.bias].add(win, bps)
            has_event = any(f.name == "structure_event" for f in read.factors)
            by_event["with_structure_event" if has_event else "no_structure_event"].add(win, bps)
            by_time["morning" if _hour_et(rows[min(i, len(rows) - 1)]) < 12 else "afternoon"].add(win, bps)
            by_fresh["fresh_break" if fresh else "no_fresh_break"].add(win, bps)
            if fresh:
                by_fresh_conv[_conv_band(read.conviction)].add(win, bps)

    # monotonicity check: does win_rate rise with conviction?
    bands = ["20-40", "40-60", "60-80", "80-100"]
    wr = [by_conv[b].report()["win_rate"] for b in bands if by_conv[b].n >= 30]
    monotone = all(a <= b for a, b in zip(wr, wr[1:])) if len(wr) >= 2 else None

    return {
        "csv": csv_path.name,
        "days": len(dates),
        "evaluated_reads": evaluated,
        "params": {"LOOKBACK": LOOKBACK, "WARMUP": WARMUP, "K_FWD": K_FWD,
                   "TARGET_PCT": TARGET_PCT, "STOP_PCT": STOP_PCT, "step": step},
        "overall": overall.report(),
        "by_conviction": {k: by_conv[k].report() for k in sorted(by_conv)},
        "by_bias": {k: by_bias[k].report() for k in sorted(by_bias)},
        "by_structure_event": {k: by_event[k].report() for k in sorted(by_event)},
        "by_time_of_day": {k: by_time[k].report() for k in sorted(by_time)},
        "by_fresh_break": {k: by_fresh[k].report() for k in sorted(by_fresh)},
        "fresh_break_by_conviction": {k: by_fresh_conv[k].report() for k in sorted(by_fresh_conv)},
        "conviction_monotonic_winrate": monotone,
        "disclaimer": "SPY-direction screening, NOT an option-edge claim (C3/L58). Real-fills sim is the option authority.",
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", type=Path, default=_REPO_ROOT / "backtest/data/spy_5m_2025-01-01_2026-05-15.csv")
    p.add_argument("--max-days", type=int, default=None)
    p.add_argument("--step", type=int, default=1)
    p.add_argument("--tag", default="full")
    args = p.parse_args(argv)
    if not args.csv.exists():
        print(f"RED: csv not found {args.csv}", file=sys.stderr)
        return 2
    rep = run(args.csv, args.max_days, args.step)
    out = _REPO_ROOT / f"analysis/structure-edge-study-{args.tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(json.dumps(rep, indent=2))
    print(f"\n-> {out.relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
