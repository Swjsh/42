"""Heartbeat tick audit — generalized re-runnable misalignment detector.

Generalized from `analysis/r4_heartbeat_misalignment_analysis.py` (one-shot for
2026-05-14) into a daily-runnable tool that any wake fire / EOD pipeline / J's
ad-hoc shell can invoke on any date.

Per markdown/audits/HEARTBEAT-CHART-DATA-AUDIT-2026-05-14.md (R3 spec, "diagnostic JSONL
trail"). The R1 closed-bar fix shipped in heartbeat.md v15.1 removes the
in-progress bar at the source; this audit verifies the fix held overnight by
classifying every tick on a given day.

USAGE:
    python -m autoresearch.heartbeat_tick_audit --date 2026-05-14
    python -m autoresearch.heartbeat_tick_audit --date 2026-05-15 --output-dir analysis/

OUTPUTS (per date):
    automation/state/heartbeat-tick-audit-{date}.csv     (per-tick CSV)
    docs/HEARTBEAT-TICK-AUDIT-{date}.md                  (human-readable)
    automation/state/heartbeat-tick-audit-{date}.json    (machine-readable summary)

CLASSIFICATIONS:
    ALIGNED              — heartbeat read correct closed bar
    MISALIGNED-BENIGN    — read in-progress but action unchanged
    MISALIGNED-CRITICAL  — read in-progress AND decision-changing
    STALE_PAUSED         — kill-switch tick with stale cached SPY (can't matter)
    NO_DATA / NO_BAR     — TIMEOUT/ERROR with no chart read
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# Decisions that change behavior if the snapshot is wrong
DECISION_CHANGING_ACTIONS = {
    "ENTER_BULL", "ENTER_BEAR", "EXIT_TP1", "EXIT_TP2",
    "EXIT_RUNNER", "EXIT_STOP", "EXIT_TIME", "ADD",
}
NON_BEHAVIORAL_ACTIONS = {
    "PAUSED", "ERROR_TV", "ERROR_ALPACA", "SKIP_NEWS", "SKIP_STALE",
    "SKIP_THROTTLE",
}

FIRE_RX = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) ET FIRE mode=\S+ idx=(\d+) model=\S+ pos_open=(\S+) htf=\S+ score=\S+")
HB_RX = re.compile(r"^HB#\S*\s+(\d{2}:\d{2})\s+(\S+)\s*\|(.+)$")
SPY_RX = re.compile(r"spy=([0-9.]+)")
RIBBON_RX_ALT = re.compile(r"ribbon=([0-9]+)c\((BULL|BEAR|MIXED|NEUTRAL)\)")
RIBBON_RX = re.compile(r"ribbon=(?:BULL|BEAR|MIXED|NEUTRAL)?\(?([0-9]+)c\)?(?:\(([A-Z]+)\))?")
BEAR_SCORE_RX = re.compile(r"bear=(\d+)/\d+")
BULL_SCORE_RX = re.compile(r"bull=(\d+)/\d+")


@dataclass
class Tick:
    idx: int
    fire_at: datetime
    pos_open: bool
    decision: str | None = None
    decision_bar_label: str | None = None
    spy_claim: float | None = None
    ribbon_claim_cents: int | None = None
    ribbon_stack_claim: str | None = None
    bear_score: int | None = None
    bull_score: int | None = None
    reason: str = ""


def find_spy_csv_for_date(date_str: str) -> Path | None:
    """Locate the spy_5m CSV that contains the given date.

    Search backtest/data/spy_5m_*.csv files in newest-first order; pick the
    first whose filename suggests it covers `date_str`.
    """
    data_dir = ROOT / "backtest" / "data"
    candidates = sorted(data_dir.glob("spy_5m_*.csv"), reverse=True)
    target_dt = datetime.strptime(date_str, "%Y-%m-%d").date()
    for p in candidates:
        # Filenames like spy_5m_2026-05-08_2026-05-14.csv
        m = re.match(r"spy_5m_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.csv", p.name)
        if not m:
            continue
        start = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        end = datetime.strptime(m.group(2), "%Y-%m-%d").date()
        if start <= target_dt <= end:
            return p
    return None


def parse_csv_bars(csv_path: Path, date_str: str) -> list[dict]:
    """Read CSV, return only `date_str` bars sorted by timestamp."""
    bars: list[dict] = []
    with open(csv_path, "r", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            ts = row["timestamp_et"]
            if not ts.startswith(date_str):
                continue
            naive = ts.split("-04:00")[0].split("-05:00")[0].strip()
            dt_obj = datetime.strptime(naive, "%Y-%m-%d %H:%M:%S")
            bars.append({
                "open_dt": dt_obj,
                "close_dt": dt_obj + timedelta(minutes=5),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"] or 0),
            })
    bars.sort(key=lambda b: b["open_dt"])
    return bars


def parse_log(log_path: Path) -> list[Tick]:
    if not log_path.exists():
        return []
    ticks: list[Tick] = []
    pending: Tick | None = None
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")
            m = FIRE_RX.match(line)
            if m:
                if pending is not None:
                    ticks.append(pending)
                fire_dt = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M:%S")
                pending = Tick(
                    idx=int(m.group(3)),
                    fire_at=fire_dt,
                    pos_open=(m.group(4) == "True"),
                )
                continue
            if pending is None:
                continue
            hb = HB_RX.match(line)
            if hb:
                pending.decision_bar_label = hb.group(1)
                pending.decision = hb.group(2)
                tail = hb.group(3)
                pending.reason = tail.strip()
                spy_m = SPY_RX.search(tail)
                if spy_m:
                    pending.spy_claim = float(spy_m.group(1))
                rib = RIBBON_RX_ALT.search(tail) or RIBBON_RX.search(tail)
                if rib:
                    try:
                        pending.ribbon_claim_cents = int(rib.group(1))
                    except (TypeError, ValueError):
                        pass
                    if rib.lastindex and rib.lastindex >= 2:
                        pending.ribbon_stack_claim = rib.group(2)
                bs = BEAR_SCORE_RX.search(tail)
                if bs:
                    pending.bear_score = int(bs.group(1))
                bl = BULL_SCORE_RX.search(tail)
                if bl:
                    pending.bull_score = int(bl.group(1))
        if pending is not None:
            ticks.append(pending)
    return ticks


def find_last_closed_bar(fire_at: datetime, bars: list[dict]) -> dict | None:
    best = None
    for b in bars:
        if b["close_dt"] <= fire_at:
            best = b
        else:
            break
    return best


def find_inprogress_bar(fire_at: datetime, bars: list[dict]) -> dict | None:
    for b in bars:
        if b["open_dt"] <= fire_at < b["close_dt"]:
            return b
    return None


def classify_tick(tick: Tick, rth_bars: list[dict]) -> dict:
    """Return per-tick classification + per-tick row dict."""
    last_closed = find_last_closed_bar(tick.fire_at, rth_bars)
    in_prog = find_inprogress_bar(tick.fire_at, rth_bars)

    # How many minutes has elapsed since the last CSV bar closed?
    # Large lag (>30min) means the CSV itself is stale — the heartbeat read live TV data
    # that simply isn't in the backtest CSV yet (L90/L91 pattern). A $2+ divergence in
    # that scenario reflects a data-source gap, not a heartbeat closed-bar bug.
    csv_lag_minutes: float | None = None
    if last_closed is not None:
        csv_lag_minutes = (tick.fire_at - last_closed["close_dt"]).total_seconds() / 60

    row = {
        "tick_id": tick.idx,
        "fire_at": tick.fire_at.strftime("%H:%M:%S"),
        "decision": tick.decision or "(no_decision)",
        "claimed_spy": tick.spy_claim,
        "claimed_bar_label": tick.decision_bar_label,
        "last_closed_bar_open": last_closed["open_dt"].strftime("%H:%M") if last_closed else None,
        "last_closed_close": last_closed["close"] if last_closed else None,
        "in_progress_bar_open": in_prog["open_dt"].strftime("%H:%M") if in_prog else None,
        "in_progress_close_so_far": in_prog["close"] if in_prog else None,
        "in_progress_high": in_prog["high"] if in_prog else None,
        "in_progress_low": in_prog["low"] if in_prog else None,
        "ribbon_cents": tick.ribbon_claim_cents,
        "bear_score": tick.bear_score,
        "bull_score": tick.bull_score,
        "csv_lag_minutes": round(csv_lag_minutes, 1) if csv_lag_minutes is not None else None,
    }

    if tick.spy_claim is None or last_closed is None:
        row["divergence_dollars"] = None
        row["classification"] = "NO_DATA" if tick.spy_claim is None else "NO_BAR"
        row["notes"] = (tick.reason or "")[:140]
        return row

    div_to_closed = round(tick.spy_claim - last_closed["close"], 4)
    aligned_to_closed = abs(div_to_closed) <= 0.05
    aligned_to_inprog = False
    if in_prog is not None:
        if (in_prog["low"] - 0.05) <= tick.spy_claim <= (in_prog["high"] + 0.05):
            aligned_to_inprog = True

    row["divergence_vs_closed"] = div_to_closed
    action = (tick.decision or "").upper()

    if aligned_to_closed:
        cls = "ALIGNED"
    elif action in NON_BEHAVIORAL_ACTIONS:
        cls = "STALE_PAUSED"
    else:
        if aligned_to_inprog:
            significant_delta = abs(div_to_closed) > 0.30
            bar_drift = (in_prog["high"] - in_prog["low"]) if in_prog else 0
            # Only CRITICAL when a DECISION-CHANGING action was taken on an in-progress bar
            # with meaningful drift.  HOLD ticks that log an in-progress spy= price are a
            # display issue (the output line shows the live quote rather than Latest.close),
            # NOT a decision error — no trade occurred.  Demoting those to BENIGN prevents
            # the audit from inflating CRITICAL counts and masking genuine problems.
            #
            # Requires BOTH significant_delta AND high bar_drift to escalate to CRITICAL;
            # using OR inflates CRITICAL counts when bar was volatile but actual price
            # divergence was tiny (e.g. $0.08 for tick 11 on 2026-05-19 — decision unchanged).
            if action in DECISION_CHANGING_ACTIONS and significant_delta and bar_drift > 0.40:
                cls = "MISALIGNED-CRITICAL"
            elif action in DECISION_CHANGING_ACTIONS and abs(div_to_closed) > 0.50:
                cls = "MISALIGNED-CRITICAL"
            else:
                cls = "MISALIGNED-BENIGN"
        else:
            # spy= not aligned to either closed bar OR in-progress bar → stale-cache territory.
            # CRITICAL for decision-changing actions always; for HOLD/HOLD_DEV only when the
            # divergence is large AND the CSV itself is current (<30min lag).
            # When csv_lag_minutes > 30, the CSV data source is stale (L90/L91 pattern) —
            # the heartbeat correctly read live TV prices that simply weren't in the CSV yet.
            # That's a data-source gap, not a closed-bar-read bug. Don't inflate CRITICAL.
            csv_is_stale = csv_lag_minutes is not None and csv_lag_minutes > 30
            if action in DECISION_CHANGING_ACTIONS:
                cls = "MISALIGNED-CRITICAL"
            elif abs(div_to_closed) > 2.00 and not csv_is_stale:
                cls = "MISALIGNED-CRITICAL"
            else:
                cls = "MISALIGNED-BENIGN"

    row["classification"] = cls
    row["divergence_dollars"] = div_to_closed
    row["notes"] = (tick.reason or "")[:140]
    return row


def run_audit(date_str: str, output_dir: Path | None = None) -> dict:
    """Audit heartbeat ticks for the given date. Returns summary dict."""
    log_path = ROOT / "automation" / "state" / "logs" / f"heartbeat-{date_str}.log"
    csv_path = find_spy_csv_for_date(date_str)
    if csv_path is None:
        return {
            "date": date_str,
            "error": f"No spy_5m_*.csv found covering {date_str}",
            "summary": {},
            "rows": [],
        }

    out_dir = output_dir or (ROOT / "automation" / "state")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / f"heartbeat-tick-audit-{date_str}.csv"
    out_json = out_dir / f"heartbeat-tick-audit-{date_str}.json"
    out_md = ROOT / "markdown" / "audits" / f"HEARTBEAT-TICK-AUDIT-{date_str}.md"

    bars = parse_csv_bars(csv_path, date_str)
    rth_bars = [
        b for b in bars
        if datetime.strptime("09:30", "%H:%M").time() <= b["open_dt"].time() <= datetime.strptime("16:00", "%H:%M").time()
    ]
    ticks = parse_log(log_path)

    rows: list[dict] = []
    counts = {
        "ALIGNED": 0, "MISALIGNED-BENIGN": 0, "MISALIGNED-CRITICAL": 0,
        "STALE_PAUSED": 0, "NO_DATA": 0, "NO_BAR": 0,
    }
    critical_ticks: list[dict] = []

    for t in ticks:
        row = classify_tick(t, rth_bars)
        cls = row.get("classification", "NO_DATA")
        if cls in counts:
            counts[cls] += 1
        if cls == "MISALIGNED-CRITICAL":
            critical_ticks.append({
                "tick_id": t.idx,
                "fire_at": t.fire_at.isoformat(),
                "decision": t.decision,
                "claimed_spy": t.spy_claim,
                "closed_close": row.get("last_closed_close"),
                "divergence": row.get("divergence_dollars"),
                "reason": (t.reason or "")[:200],
            })
        rows.append(row)

    total = sum(counts.values())
    denom_live = counts["ALIGNED"] + counts["MISALIGNED-BENIGN"] + counts["MISALIGNED-CRITICAL"]
    headline_pct = (100.0 * counts["MISALIGNED-CRITICAL"] / denom_live) if denom_live > 0 else 0.0

    summary = {
        "date": date_str,
        "total_ticks": total,
        "live_trading_ticks": denom_live,
        "counts": counts,
        "misaligned_critical_count": counts["MISALIGNED-CRITICAL"],
        "misaligned_critical_pct_of_live": round(headline_pct, 2),
        "headline": (
            f"{counts['MISALIGNED-CRITICAL']} of {denom_live} live-trading ticks "
            f"({headline_pct:.0f}%) were MISALIGNED-CRITICAL on {date_str}"
        ),
        "critical_ticks": critical_ticks,
        "log_path": str(log_path) if log_path.exists() else None,
        "csv_path": str(csv_path),
        "audit_files": {
            "per_tick_csv": str(out_csv),
            "summary_json": str(out_json),
            "human_md": str(out_md),
        },
    }

    # Per-tick CSV
    field_order = [
        "tick_id", "fire_at", "decision", "claimed_spy", "claimed_bar_label",
        "last_closed_bar_open", "last_closed_close",
        "in_progress_bar_open", "in_progress_close_so_far", "in_progress_high", "in_progress_low",
        "divergence_vs_closed", "divergence_dollars", "csv_lag_minutes",
        "ribbon_cents", "bear_score", "bull_score", "classification", "notes",
    ]
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=field_order, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # Summary JSON
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    # Human MD
    out_md.parent.mkdir(parents=True, exist_ok=True)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(f"# Heartbeat Tick Audit — {date_str}\n\n")
        f.write(f"_Auto-generated by `backtest/autoresearch/heartbeat_tick_audit.py`._\n\n")
        f.write(f"## Headline\n\n")
        f.write(f"**{summary['headline']}**\n\n")
        f.write(f"## Counts\n\n")
        f.write(f"| Classification | Ticks | % of total |\n|---|---:|---:|\n")
        for k in ["ALIGNED", "MISALIGNED-BENIGN", "MISALIGNED-CRITICAL", "STALE_PAUSED", "NO_DATA", "NO_BAR"]:
            pct = (100.0 * counts[k] / total) if total else 0
            f.write(f"| {k} | {counts[k]} | {pct:.1f}% |\n")
        f.write(f"| **TOTAL** | **{total}** | 100% |\n\n")
        f.write(f"## Critical ticks ({len(critical_ticks)})\n\n")
        if critical_ticks:
            f.write(f"| tick_id | fire_at | decision | claimed_spy | closed_close | divergence | reason |\n")
            f.write(f"|---:|---|---|---:|---:|---:|---|\n")
            for ct in critical_ticks:
                fire_at_str = ct["fire_at"][-8:] if ct["fire_at"] else "?"
                cc_str = f"{ct['closed_close']:.3f}" if ct['closed_close'] is not None else "?"
                div_str = f"{ct['divergence']:+.4f}" if ct['divergence'] is not None else "?"
                f.write(f"| {ct['tick_id']} | {fire_at_str} | {ct['decision']} | {ct['claimed_spy']} | {cc_str} | {div_str} | {ct['reason'][:80]} |\n")
        else:
            f.write("_None._\n")
        f.write(f"\n## Files\n\n")
        f.write(f"- Per-tick CSV: `{out_csv.relative_to(ROOT)}`\n")
        f.write(f"- Summary JSON: `{out_json.relative_to(ROOT)}`\n")
        f.write(f"- Source log: `{log_path.relative_to(ROOT) if log_path.exists() else '(missing)'}`\n")
        f.write(f"- Source CSV: `{csv_path.relative_to(ROOT)}`\n\n")
        f.write(f"## R1 verification (heartbeat closed-bar fix shipped 2026-05-14 v15.1)\n\n")
        if counts["MISALIGNED-CRITICAL"] == 0:
            f.write(f"✅ **R1 fix held.** Zero MISALIGNED-CRITICAL ticks on {date_str}.\n")
        elif headline_pct < 5:
            f.write(f"🟡 **R1 fix partial.** {counts['MISALIGNED-CRITICAL']} CRITICAL ticks ({headline_pct:.1f}% of live) — investigate via per-tick CSV.\n")
        else:
            f.write(f"🔴 **R1 fix may NOT be working.** {counts['MISALIGNED-CRITICAL']} CRITICAL ticks ({headline_pct:.1f}% of live) — heartbeat may still be reading in-progress bars.\n")

    return summary


def main():
    p = argparse.ArgumentParser(description="Heartbeat tick audit — closed-bar vs in-progress-bar misalignment.")
    p.add_argument("--date", required=True, help="Date in YYYY-MM-DD format")
    p.add_argument("--output-dir", help="Override output directory (default: automation/state/)")
    args = p.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else None
    summary = run_audit(args.date, out_dir)

    print(f"=== Heartbeat Tick Audit — {args.date} ===")
    if "error" in summary:
        print(f"ERROR: {summary['error']}")
        sys.exit(1)
    print(f"Headline: {summary['headline']}")
    print(f"Counts: {summary['counts']}")
    print(f"Files written:")
    for k, v in summary["audit_files"].items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
