"""Watcher morning report — prints + writes a clean summary of recent watcher activity.

Runs daily at 08:30 ET via Gamma_WatcherMorningReport (or on demand via CLI).
Output:
  docs/WATCHER-REPORT.md        — human-readable
  automation/state/watcher-report.json — machine-readable

Sections:
  1. Yesterday's signals (per watcher)
  2. Rolling 7-day P&L per watcher
  3. Rolling 30-day P&L per watcher
  4. Rolling 30-day win rate per watcher
  5. Best signals (top 5 by P&L)
  6. Worst signals (bottom 5 by P&L)
  7. Promotion readiness check (per OP 21: 3+ live wins required)
"""

from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
OBS_LOG = ROOT / "automation" / "state" / "watcher-observations.jsonl"
OUT_MD = ROOT / "docs" / "WATCHER-REPORT.md"
OUT_JSON = ROOT / "automation" / "state" / "watcher-report.json"


def main() -> int:
    if not OBS_LOG.exists():
        print("no observations yet")
        return 0

    rows = []
    for line in OBS_LOG.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except Exception:
                pass

    if not rows:
        return 0

    today = dt.date.today()
    yesterday = today - dt.timedelta(days=1)
    last_7 = today - dt.timedelta(days=7)
    last_30 = today - dt.timedelta(days=30)

    def _date_of(r: dict) -> dt.date:
        return dt.date.fromisoformat(r["bar_timestamp_et"][:10])

    yesterday_rows = [r for r in rows if _date_of(r) == yesterday]
    week_rows = [r for r in rows if _date_of(r) >= last_7]
    month_rows = [r for r in rows if _date_of(r) >= last_30]

    def _pnl_by_watcher(rs):
        d = defaultdict(float)
        for r in rs:
            d[r["watcher_name"]] += r.get("would_be_pnl_dollars") or 0
        return dict(d)

    def _wr_by_watcher(rs):
        wins = defaultdict(int)
        total = defaultdict(int)
        for r in rs:
            w = r["watcher_name"]
            total[w] += 1
            pnl = r.get("would_be_pnl_dollars") or 0
            if pnl > 0:
                wins[w] += 1
        return {w: (wins[w], total[w], wins[w] / total[w] if total[w] else 0) for w in total}

    yesterday_pnl = _pnl_by_watcher(yesterday_rows)
    week_pnl = _pnl_by_watcher(week_rows)
    month_pnl = _pnl_by_watcher(month_rows)
    week_wr = _wr_by_watcher(week_rows)
    month_wr = _wr_by_watcher(month_rows)

    # Promotion readiness: count wins per watcher across all history
    all_wins = defaultdict(int)
    all_total = defaultdict(int)
    for r in rows:
        w = r["watcher_name"]
        all_total[w] += 1
        if (r.get("would_be_pnl_dollars") or 0) > 0:
            all_wins[w] += 1

    sorted_pnl = sorted(rows, key=lambda r: -(r.get("would_be_pnl_dollars") or 0))
    top5 = sorted_pnl[:5]
    bottom5 = sorted_pnl[-5:]

    md = [f"# Watcher Morning Report — {today.isoformat()}\n"]
    md.append("## Yesterday's signals\n")
    if not yesterday_rows:
        md.append("- No signals yesterday.")
    else:
        md.append("| Time | Watcher | Setup | Dir | Conf | Outcome | P&L |")
        md.append("|---|---|---|---|---|---|---|")
        for r in yesterday_rows:
            md.append(
                f"| {r['bar_timestamp_et'][11:16]} | {r['watcher_name'].replace('_watcher','')} "
                f"| {r['setup_name']} | {r['direction']} | {r['confidence']} "
                f"| {r.get('would_be_outcome','open')} | ${r.get('would_be_pnl_dollars',0):+.0f} |"
            )
    md.append("")

    md.append("## Rolling 7-day P&L\n")
    md.append("| Watcher | Net P&L | Win Rate (n) |")
    md.append("|---|---|---|")
    for w in sorted(week_pnl.keys()):
        wins, total, rate = week_wr.get(w, (0, 0, 0))
        md.append(f"| {w} | ${week_pnl[w]:+.0f} | {wins}/{total} ({rate*100:.0f}%) |")
    md.append("")

    md.append("## Rolling 30-day P&L\n")
    md.append("| Watcher | Net P&L | Win Rate (n) |")
    md.append("|---|---|---|")
    for w in sorted(month_pnl.keys()):
        wins, total, rate = month_wr.get(w, (0, 0, 0))
        md.append(f"| {w} | ${month_pnl[w]:+.0f} | {wins}/{total} ({rate*100:.0f}%) |")
    md.append("")

    md.append("## Top 5 signals (all time, by P&L)\n")
    md.append("| Date | Watcher | Setup | Dir | P&L |")
    md.append("|---|---|---|---|---|")
    for r in top5:
        md.append(
            f"| {r['bar_timestamp_et'][:10]} | {r['watcher_name'].replace('_watcher','')} "
            f"| {r['setup_name']} | {r['direction']} | ${r.get('would_be_pnl_dollars',0):+.0f} |"
        )
    md.append("")

    md.append("## Worst 5 signals\n")
    md.append("| Date | Watcher | Setup | Dir | P&L |")
    md.append("|---|---|---|---|---|")
    for r in bottom5:
        md.append(
            f"| {r['bar_timestamp_et'][:10]} | {r['watcher_name'].replace('_watcher','')} "
            f"| {r['setup_name']} | {r['direction']} | ${r.get('would_be_pnl_dollars',0):+.0f} |"
        )
    md.append("")

    md.append("## Promotion readiness (per OP 21)\n")
    md.append("Each watcher needs **3+ historical wins** before promotion to live trading.\n")
    md.append("| Watcher | Total fires | Wins | Status |")
    md.append("|---|---|---|---|")
    for w in sorted(all_total.keys()):
        wins = all_wins[w]
        total = all_total[w]
        status = "✅ ELIGIBLE" if wins >= 3 else f"⏳ need {3 - wins} more wins"
        md.append(f"| {w} | {total} | {wins} | {status} |")
    md.append("")

    md.append("---")
    md.append(f"_Generated {dt.datetime.now().isoformat()}_")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")

    summary = {
        "generated_at": dt.datetime.now().isoformat(),
        "yesterday_signals": len(yesterday_rows),
        "yesterday_pnl_by_watcher": {k: round(v, 2) for k, v in yesterday_pnl.items()},
        "week_pnl_by_watcher": {k: round(v, 2) for k, v in week_pnl.items()},
        "month_pnl_by_watcher": {k: round(v, 2) for k, v in month_pnl.items()},
        "week_wr_by_watcher": {k: {"wins": v[0], "total": v[1], "rate": round(v[2], 3)} for k, v in week_wr.items()},
        "month_wr_by_watcher": {k: {"wins": v[0], "total": v[1], "rate": round(v[2], 3)} for k, v in month_wr.items()},
        "promotion_readiness": {k: {"total": all_total[k], "wins": all_wins[k], "eligible": all_wins[k] >= 3} for k in all_total},
    }
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
