"""Multi-strategy daily scorecard.

Aggregates the 497-line ``automation/state/watcher-observations.jsonl`` plus
``journal/trades.csv`` to produce a per-day comparison of:
  - what each watcher fired (setup + direction + confidence)
  - what trades the engine actually placed
  - the gap (chart events the engine ignored / didn't qualify for)

Output:
  ``analysis/multi-strat-scorecard.md`` (sorted by date desc, 30 most-recent days)
  ``analysis/multi-strat-scorecard.json`` (machine-readable equivalent)

Per CLAUDE.md OP 22 (Don't Stop Cooking): this is the "what did we see vs.
what did we do" report J asked for after watching today's 8 level
interactions get traded only once.

CLI::

    pythonw.exe -m autoresearch.multi_strat_scorecard
    pythonw.exe -m autoresearch.multi_strat_scorecard --days 14
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger("multi_strat_scorecard")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

REPO = Path(__file__).resolve().parent.parent.parent
OBS_LOG = REPO / "automation" / "state" / "watcher-observations.jsonl"
TRADES_CSV = REPO / "journal" / "trades.csv"
OUT_MD = REPO / "analysis" / "multi-strat-scorecard.md"
OUT_JSON = REPO / "analysis" / "multi-strat-scorecard.json"


def _load_observations() -> list[dict]:
    """Read all watcher observations. Returns list of dicts."""
    if not OBS_LOG.exists():
        return []
    out: list[dict] = []
    with OBS_LOG.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _load_trades() -> list[dict]:
    """Read journal/trades.csv. Returns list of dicts."""
    if not TRADES_CSV.exists():
        return []
    out: list[dict] = []
    with TRADES_CSV.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            out.append(row)
    return out


def _obs_date(obs: dict) -> Optional[str]:
    """Extract YYYY-MM-DD from an observation row."""
    ts = obs.get("bar_timestamp_et") or obs.get("observed_at") or ""
    if not ts:
        return None
    return ts[:10]


def _trade_date(trade: dict) -> Optional[str]:
    raw = trade.get("date", "")
    return raw[:10] if raw else None


def build_scorecard(
    days_back: int = 30,
    end_date: Optional[dt.date] = None,
) -> dict:
    """Aggregate observations + trades by date for the last N trading days."""
    if end_date is None:
        end_date = dt.date.today()
    cutoff = (end_date - dt.timedelta(days=days_back)).isoformat()

    observations = _load_observations()
    trades = _load_trades()

    # Filter to last N days (calendar, not trading — close enough)
    obs_filtered = [o for o in observations if (_obs_date(o) or "") >= cutoff]
    trade_filtered = [t for t in trades if (_trade_date(t) or "") >= cutoff]

    # Index by date
    obs_by_date: dict[str, list[dict]] = defaultdict(list)
    for o in obs_filtered:
        d = _obs_date(o)
        if d:
            obs_by_date[d].append(o)

    trade_by_date: dict[str, list[dict]] = defaultdict(list)
    for t in trade_filtered:
        d = _trade_date(t)
        if d:
            trade_by_date[d].append(t)

    all_dates = sorted(set(obs_by_date) | set(trade_by_date), reverse=True)

    days: list[dict] = []
    for d in all_dates:
        day_obs = obs_by_date.get(d, [])
        day_trades = trade_by_date.get(d, [])

        # Count by watcher
        by_watcher: dict[str, int] = defaultdict(int)
        by_setup: dict[str, int] = defaultdict(int)
        directions: dict[str, int] = defaultdict(int)
        for o in day_obs:
            by_watcher[o.get("watcher_name", "?")] += 1
            by_setup[o.get("setup_name", "?")] += 1
            directions[o.get("direction", "?")] += 1

        # Trade P&L total
        total_pnl = 0.0
        trade_setups: list[str] = []
        for t in day_trades:
            try:
                total_pnl += float(t.get("dollar_pnl") or 0)
            except (TypeError, ValueError):
                pass
            trade_setups.append(t.get("setup", "?"))

        days.append({
            "date": d,
            "observations": len(day_obs),
            "by_watcher": dict(by_watcher),
            "by_setup": dict(by_setup),
            "directions": dict(directions),
            "trades_placed": len(day_trades),
            "trade_setups": trade_setups,
            "trade_pnl_dollars": round(total_pnl, 2),
            "miss_ratio": _miss_ratio(len(day_obs), len(day_trades)),
        })

    summary = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "window_days": days_back,
        "total_dates": len(days),
        "total_observations": len(obs_filtered),
        "total_trades": len(trade_filtered),
        "total_trade_pnl": round(sum(d["trade_pnl_dollars"] for d in days), 2),
        "days": days,
    }
    return summary


def _miss_ratio(obs_count: int, trade_count: int) -> str:
    """Heuristic: % of watcher fires not converted to trades."""
    if obs_count == 0:
        return "0.0% (no observations)"
    if trade_count == 0:
        return f"100% ({obs_count} observed, 0 traded)"
    ratio = max(0.0, (obs_count - trade_count) / obs_count)
    return f"{ratio * 100:.1f}% ({obs_count} observed, {trade_count} traded)"


def render_markdown(summary: dict) -> str:
    """Format scorecard as markdown table."""
    lines: list[str] = []
    lines.append(f"# Multi-Strategy Daily Scorecard\n")
    lines.append(f"> Generated: {summary['generated_at']}\n")
    lines.append(f"> Window: {summary['window_days']} days\n")
    lines.append(f"> Total observations: {summary['total_observations']} across {summary['total_dates']} dates\n")
    lines.append(f"> Total trades placed: {summary['total_trades']}, P&L ${summary['total_trade_pnl']:.2f}\n\n")
    lines.append("## Daily breakdown (most recent first)\n\n")
    lines.append("| Date | Obs | Watchers fired | Trades | P&L | Miss ratio |")
    lines.append("|---|---|---|---|---|---|")
    for day in summary["days"]:
        wlist = ", ".join(f"{k}={v}" for k, v in sorted(day["by_watcher"].items(), key=lambda x: -x[1])[:5])
        lines.append(
            f"| {day['date']} | {day['observations']} | {wlist} | "
            f"{day['trades_placed']} ({', '.join(day['trade_setups'][:3])}) | "
            f"${day['trade_pnl_dollars']:.2f} | {day['miss_ratio']} |"
        )
    lines.append("\n## Aggregate by watcher across window\n\n")

    # Aggregate watcher counts
    totals: dict[str, int] = defaultdict(int)
    for day in summary["days"]:
        for w, c in day["by_watcher"].items():
            totals[w] += c

    lines.append("| Watcher | Total observations |")
    lines.append("|---|---|")
    for w, c in sorted(totals.items(), key=lambda x: -x[1]):
        lines.append(f"| {w} | {c} |")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-strategy daily scorecard")
    parser.add_argument("--days", type=int, default=30, help="lookback days (default 30)")
    parser.add_argument("--end-date", type=str, default=None,
                        help="end date YYYY-MM-DD (default today)")
    args = parser.parse_args()

    end_date = None
    if args.end_date:
        try:
            end_date = dt.date.fromisoformat(args.end_date)
        except ValueError:
            logger.error("invalid --end-date: %s", args.end_date)
            return 2

    summary = build_scorecard(days_back=args.days, end_date=end_date)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    OUT_MD.write_text(render_markdown(summary), encoding="utf-8")

    logger.info("wrote %s (%d days, %d obs, %d trades)",
                OUT_MD.name, len(summary["days"]), summary["total_observations"],
                summary["total_trades"])
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
