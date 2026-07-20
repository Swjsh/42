"""decision_row_spy_staleness_study.py -- DECISION-ROW-SPY-STALENESS quantification
(automation/overnight/queue.md, filed 2026-07-20 ~18:30 ET, Lever-2 discovery).

For every core-decisions.jsonl row in 2026-07-14..2026-07-20 (RTH only), computes
|row.spy - SIP 1-min close at that minute| against the real 1-minute SIP tape
(backtest/data/highres/SPY_1m_<date>.csv, same fetch pattern as
fetch_premium_stop_counterfactual_1min.py / fetch_spy_1min_sight_staleness.py).

Reports the full distribution + every row >$0.25 divergence, grouped by session and by
time-of-day bucket (open 09:30-10:00, morning 10:00-11:30, midday 11:30-14:00, afternoon
14:00-15:55). Report-only -- no trading-path file touched.

Output: analysis/recommendations/decision-row-spy-staleness-2026-07-20.json
"""
from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from datetime import datetime, time as dt_time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "automation" / "state" / "core-decisions.jsonl"
HIRES_DIR = ROOT / "backtest" / "data" / "highres"
OUT_F = ROOT / "analysis" / "recommendations" / "decision-row-spy-staleness-2026-07-20.json"

DATE_LO, DATE_HI = "2026-07-14", "2026-07-20"
DIVERGENCE_FLAG = 0.25


def _load_sip_minutes(date_str: str) -> dict[str, float]:
    """minute-of-day 'HH:MM' -> SIP 1-min close, for one date's cached CSV. Empty if missing."""
    path = HIRES_DIR / f"SPY_1m_{date_str}.csv"
    out: dict[str, float] = {}
    if not path.exists():
        return out
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = row["timestamp_et"]  # e.g. 2026-07-14T09:30:00-04:00
            hhmm = ts[11:16]
            try:
                out[hhmm] = float(row["close"])
            except (TypeError, ValueError):
                continue
    return out


def _nearest_sip_close(minutes: dict[str, float], hhmm: str) -> tuple[float | None, str | None, int]:
    """Exact-minute SIP close if present; else the most recent PRIOR minute within 5 back
    (covers thin/pre-open ticks). Returns (close, matched_hhmm, lag_minutes_used)."""
    if hhmm in minutes:
        return minutes[hhmm], hhmm, 0
    try:
        h, m = int(hhmm[:2]), int(hhmm[3:5])
    except ValueError:
        return None, None, -1
    total = h * 60 + m
    for back in range(1, 6):
        cand_total = total - back
        cand_hhmm = f"{cand_total // 60:02d}:{cand_total % 60:02d}"
        if cand_hhmm in minutes:
            return minutes[cand_hhmm], cand_hhmm, back
    return None, None, -1


def _tod_bucket(t: dt_time) -> str:
    if t < dt_time(10, 0):
        return "open_0930_1000"
    if t < dt_time(11, 30):
        return "morning_1000_1130"
    if t < dt_time(14, 0):
        return "midday_1130_1400"
    return "afternoon_1400_1555"


def main() -> int:
    sip_by_date: dict[str, dict[str, float]] = {}
    rows_out = []
    n_total = 0
    n_scored = 0
    n_no_sip = 0
    n_no_spy_field = 0

    with open(LEDGER, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = rec.get("ts_et") or ""
            date_str = ts[:10]
            if not (DATE_LO <= date_str <= DATE_HI):
                continue
            try:
                dt_obj = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                continue
            t = dt_obj.time()
            if t < dt_time(9, 30) or t >= dt_time(16, 0):
                continue  # RTH only
            n_total += 1

            spy = rec.get("spy")
            if spy is None:
                n_no_spy_field += 1
                continue

            if date_str not in sip_by_date:
                sip_by_date[date_str] = _load_sip_minutes(date_str)
            minutes = sip_by_date[date_str]
            if not minutes:
                n_no_sip += 1
                continue

            hhmm = ts[11:16]
            sip_close, matched_hhmm, lag = _nearest_sip_close(minutes, hhmm)
            if sip_close is None:
                n_no_sip += 1
                continue

            diff = round(float(spy) - sip_close, 4)
            n_scored += 1
            rows_out.append({
                "ts_et": ts,
                "date": date_str,
                "account": rec.get("account"),
                "row_spy": spy,
                "sip_1min_close": sip_close,
                "sip_minute_matched": matched_hhmm,
                "sip_match_lag_min": lag,
                "abs_diff": round(abs(diff), 4),
                "signed_diff": diff,
                "tod_bucket": _tod_bucket(t),
                "action": rec.get("action"),
                "verdict": rec.get("verdict"),
                "trigger_bar_et": rec.get("trigger_bar_et"),
            })

    abs_diffs = [r["abs_diff"] for r in rows_out]
    flagged = sorted((r for r in rows_out if r["abs_diff"] > DIVERGENCE_FLAG),
                      key=lambda r: -r["abs_diff"])

    by_session: dict[str, list[float]] = defaultdict(list)
    by_tod: dict[str, list[float]] = defaultdict(list)
    for r in rows_out:
        by_session[r["date"]].append(r["abs_diff"])
        by_tod[r["tod_bucket"]].append(r["abs_diff"])

    def _dist(vals: list[float]) -> dict:
        if not vals:
            return {"n": 0}
        sv = sorted(vals)
        return {
            "n": len(vals),
            "mean": round(statistics.mean(vals), 4),
            "median": round(statistics.median(vals), 4),
            "p90": round(sv[int(0.90 * (len(sv) - 1))], 4),
            "p99": round(sv[int(0.99 * (len(sv) - 1))], 4),
            "max": round(max(vals), 4),
            "n_gt_025": sum(1 for v in vals if v > 0.25),
            "n_gt_050": sum(1 for v in vals if v > 0.50),
            "n_gt_100": sum(1 for v in vals if v > 1.00),
        }

    out = {
        "_doc": "DECISION-ROW-SPY-STALENESS quantification (queue.md item filed 2026-07-20 "
                "~18:30 ET). |row.spy - SIP 1-min close at that minute| over every RTH "
                "core-decisions.jsonl row 2026-07-14..2026-07-20, both accounts. row.spy is "
                "bc['bar']['close'] -- the SAME value the score/trigger path evaluates (see "
                "heartbeat_core._build_payload: spy = float(trig['close']), trig = win.iloc[n-2] "
                "-- the trigger bar is ALWAYS the 2nd-to-last fetched 5m bar, reserving the "
                "newest bar as the forward-confirmation bar the require_bearish_fill_bar gate "
                "reads; matches backtest fidelity). This means row.spy is STRUCTURALLY ~5-10 "
                "minutes behind real-time by design (bar-close cadence), not a caching defect "
                "on top of a fresher read -- the divergence this script measures is EXPECTED "
                "to correlate with the last 5m bar's staleness, not with a distinct bug.",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "date_range": [DATE_LO, DATE_HI],
        "n_ledger_rows_in_range_rth": n_total,
        "n_scored": n_scored,
        "n_skipped_no_spy_field": n_no_spy_field,
        "n_skipped_no_sip_data": n_no_sip,
        "divergence_flag_threshold": DIVERGENCE_FLAG,
        "overall_distribution": _dist(abs_diffs),
        "by_session": {d: _dist(v) for d, v in sorted(by_session.items())},
        "by_time_of_day": {k: _dist(v) for k, v in sorted(by_tod.items())},
        "n_flagged_gt_threshold": len(flagged),
        "flagged_rows": flagged,
    }
    OUT_F.parent.mkdir(parents=True, exist_ok=True)
    OUT_F.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"n_total(RTH)={n_total} n_scored={n_scored} n_no_spy={n_no_spy_field} "
          f"n_no_sip={n_no_sip}")
    print(f"overall: {out['overall_distribution']}")
    print(f"n_flagged(>${DIVERGENCE_FLAG}): {len(flagged)}")
    print(f"wrote {OUT_F}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
