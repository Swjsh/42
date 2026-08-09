"""LANE 1 -- LOSS ANATOMY, 2026-08-08 subagent run.

Builds on analysis/deep-research/LOSS-ANATOMY-2026-08-06.md (LANE 0) and
analysis/pain-ledger/mae-mfe.json (MAE/MFE) rather than redoing them.

REAL FILLS ONLY (C1): automation/state/fills-ledger.jsonl, attribution==engine,
options, non-crypto, CORE arms only (safe-2, bold-2 -- the two arms CLAUDE.md's
$100-200/day target refers to). Position grouping reuses
exit_shape_parity_study.reconstruct_positions (repo's ONE definition of "a position").

Analysis-only. Writes nothing outside analysis/deep-research/lane1-loss-anatomy-2026-08-08.json.
"""
from __future__ import annotations

import csv
import json
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "tools"))
from exit_shape_parity_study import reconstruct_positions  # noqa: E402

LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
JOURNAL_CSV = REPO / "journal" / "trades.csv"
OUT = REPO / "analysis" / "deep-research" / "lane1-loss-anatomy-2026-08-08.json"

CORE_ARMS = ("safe-2", "bold-2")

# VIX daily closes, fetched live this session via yfinance (^VIX), 2026-06-20..2026-08-07.
VIX_DAILY = {
 "2026-06-26": 18.41, "2026-06-29": 17.65, "2026-06-30": 16.45, "2026-07-01": 16.59,
 "2026-07-02": 16.15, "2026-07-06": 15.57, "2026-07-07": 16.13, "2026-07-08": 16.90,
 "2026-07-09": 15.84, "2026-07-10": 15.03, "2026-07-13": 17.16, "2026-07-14": 16.50,
 "2026-07-15": 15.67, "2026-07-16": 16.73, "2026-07-17": 18.77, "2026-07-20": 18.65,
 "2026-07-21": 17.05, "2026-07-22": 16.64, "2026-07-23": 18.70, "2026-07-24": 18.58,
 "2026-07-27": 18.67, "2026-07-28": 18.21, "2026-07-29": 20.66, "2026-07-30": 17.09,
 "2026-07-31": 15.99, "2026-08-03": 15.86, "2026-08-04": 16.50, "2026-08-05": 15.81,
 "2026-08-06": 15.15, "2026-08-07": 14.90,
}


def vix_bucket(date_et: str) -> str:
    v = VIX_DAILY.get(date_et)
    if v is None:
        return "unknown"
    if v < 16.0:
        return "low(<16)"
    if v < 18.0:
        return "mid(16-18)"
    return "elevated(>=18)"


OCC_RE = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")


def parse_occ(symbol: str) -> dict:
    m = OCC_RE.match(symbol)
    if not m:
        return {"underlying": symbol, "side": "?", "strike": None}
    root, yymmdd, cp, strike8 = m.groups()
    return {"underlying": root, "side": cp, "strike": int(strike8) / 1000.0}


def load_core_fills() -> list[dict]:
    out = []
    with LEDGER.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if (r.get("arm") in CORE_ARMS and r.get("attribution") == "engine"
                    and not r.get("is_crypto") and r.get("is_option")):
                out.append(r)
    return out


def enrich_positions(fills: list[dict]) -> list[dict]:
    positions = reconstruct_positions(fills)
    for p in positions:
        occ = parse_occ(p["symbol"])
        p["direction"] = "bull" if occ["side"] == "C" else ("bear" if occ["side"] == "P" else "unknown")
        entry_dt = datetime.fromisoformat(p["entry_ts_utc"].replace("Z", "+00:00"))
        p["entry_hour_et"] = (entry_dt.hour - 4) % 24  # EDT = UTC-4, rig trades EDT months only
        p["entry_minute_et"] = p["entry_hour_et"] * 60 + entry_dt.minute
        et_bucket_min = (p["entry_minute_et"] // 30) * 30
        p["tod_bucket"] = f"{et_bucket_min // 60:02d}:{et_bucket_min % 60:02d}"
        dow = datetime.strptime(p["date_et"], "%Y-%m-%d").weekday()
        p["day_of_week"] = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][dow]
        p["vix_bucket"] = vix_bucket(p["date_et"])
        p["outcome"] = "winner" if p["actual_exit_pnl"] > 0.005 else (
            "loser" if p["actual_exit_pnl"] < -0.005 else "scratch")
        if p["exit_fills"]:
            last_exit = max(p["exit_fills"], key=lambda f: f["ts_utc"])
            exit_dt = datetime.fromisoformat(last_exit["ts_utc"].replace("Z", "+00:00"))
            p["hold_minutes"] = round((exit_dt - entry_dt).total_seconds() / 60.0, 1)
            p["last_exit_hhmm_et"] = f"{(exit_dt.hour - 4) % 24:02d}:{exit_dt.minute:02d}"
        else:
            p["hold_minutes"] = None
            p["last_exit_hhmm_et"] = None
        p["n_legs"] = len(p["exit_fills"])
    return positions


# ---- exit-stage enrichment from journal/trades.csv (best-effort join) ---------------------
STAGE_RE = re.compile(r"Exit stage=([a-zA-Z0-9_]+)")


def load_journal_stage_setup_map() -> dict:
    """Map exit_order_id -> (setup, exit_stage) from journal/trades.csv notes_short +
    archetype_match_json. Best-effort; coverage disclosed in the output, not assumed complete."""
    out = {}
    with JOURNAL_CSV.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            aj_raw = row.get("archetype_match_json", "")
            try:
                aj = json.loads(aj_raw)
            except (json.JSONDecodeError, TypeError):
                aj = {}
            exit_oid = aj.get("exit_order_id") if isinstance(aj, dict) else None
            arm = aj.get("arm") if isinstance(aj, dict) else None
            notes = row.get("notes_short", "") or ""
            m = STAGE_RE.search(notes)
            stage = m.group(1) if m else None
            setup = row.get("setup", "") or None
            if exit_oid:
                out[exit_oid] = {"setup": setup, "stage": stage, "arm": arm}
    return out


def classify_stage_heuristic(p: dict) -> str:
    """Fallback stage classifier for positions with no journal join, from raw fill shape only.
    Disclosed as a heuristic, not journal ground truth."""
    if not p["exit_fills"]:
        return "unknown(no_exit)"
    legs = sorted(p["exit_fills"], key=lambda f: f["ts_utc"])
    last = legs[-1]
    last_dt = datetime.fromisoformat(last["ts_utc"].replace("Z", "+00:00"))
    last_hhmm = ((last_dt.hour - 4) % 24) * 100 + last_dt.minute
    if last_hhmm >= 1545:
        return "time_stop(heuristic)"
    entry_px = p["entry_price"]
    if len(legs) == 1:
        px = legs[0]["price"]
        if entry_px and px <= entry_px * 0.55:
            return "stop(heuristic)"
        if entry_px and px >= entry_px * 1.25:
            return "runner_or_tp1_full(heuristic)"
        return "structure_or_flat_exit(heuristic)"
    # multi-leg: first leg partial-profit implies TP1, later leg = runner/stop
    first_frac = legs[0]["qty"] / p["entry_qty"] if p["entry_qty"] else 0
    first_up = entry_px and legs[0]["price"] > entry_px
    if 0.5 <= first_frac <= 0.9 and first_up:
        last_px = legs[-1]["price"]
        if entry_px and last_px < entry_px * 0.9:
            return "tp1_then_runner_stopped(heuristic)"
        return "tp1_then_runner(heuristic)"
    return "multi_leg_other(heuristic)"


def summarize(rows: list[dict], key_fn) -> dict:
    buckets = defaultdict(list)
    for r in rows:
        buckets[key_fn(r)].append(r["actual_exit_pnl"])
    out = {}
    for k, vals in sorted(buckets.items(), key=lambda kv: -sum(kv[1])):
        n = len(vals)
        wins = sum(1 for v in vals if v > 0.005)
        losses = sum(1 for v in vals if v < -0.005)
        out[str(k)] = {
            "n": n,
            "win_rate": round(wins / n, 4) if n else None,
            "n_wins": wins,
            "n_losses": losses,
            "total_net": round(sum(vals), 2),
            "mean_net": round(sum(vals) / n, 2) if n else None,
            "median_net": round(statistics.median(vals), 2) if n else None,
        }
    return out


def main():
    fills = load_core_fills()
    positions = enrich_positions(fills)
    journal_map = load_journal_stage_setup_map()

    matched = 0
    for p in positions:
        stage = None
        setup = None
        for ef in p["exit_fills"]:
            oid = ef.get("order_id")
            if oid in journal_map:
                j = journal_map[oid]
                stage = j["stage"] or stage
                setup = j["setup"] or setup
        if stage or setup:
            matched += 1
        p["exit_stage_journal"] = stage
        p["setup_journal"] = setup
        p["exit_stage_heuristic"] = classify_stage_heuristic(p)
        p["exit_stage_final"] = stage if stage else p["exit_stage_heuristic"]
        p["setup_final"] = setup if setup else "unattributed"

    all_dates = sorted(set(p["date_et"] for p in positions))
    last14_dates = [d for d in all_dates if d >= "2026-07-21"]  # 14-BUSINESS-DAY window per task framing
    last14 = [p for p in positions if p["date_et"] in last14_dates]
    full = positions

    def net(rows):
        return round(sum(r["actual_exit_pnl"] for r in rows), 2)

    report = {
        "_meta": {
            "generated_by": "backtest/tools/lane1_loss_anatomy_2026_08_08.py",
            "authority": "REAL FILLS ONLY -- automation/state/fills-ledger.jsonl, attribution==engine, options, non-crypto",
            "core_arms": list(CORE_ARMS),
            "position_def": "exit_shape_parity_study.reconstruct_positions",
            "n_positions_full_history": len(full),
            "n_positions_last14": len(last14),
            "distinct_dates_full": all_dates,
            "distinct_dates_last14_with_trades": last14_dates,
            "journal_stage_setup_join_coverage": f"{matched}/{len(positions)}",
            "journal_join_key": "exit_order_id (archetype_match_json) -> fills-ledger order_id",
            "vix_source": "yfinance ^VIX daily close, fetched live this session",
            "net_full_history": net(full),
            "net_last14": net(last14),
        },
        "last14": {
            "by_account": summarize(last14, lambda r: r["arm"]),
            "by_direction": summarize(last14, lambda r: r["direction"]),
            "by_setup": summarize(last14, lambda r: r["setup_final"]),
            "by_exit_stage": summarize(last14, lambda r: r["exit_stage_final"]),
            "by_hour_of_day": summarize(last14, lambda r: r["tod_bucket"]),
            "by_day_of_week": summarize(last14, lambda r: r["day_of_week"]),
            "by_vix_bucket": summarize(last14, lambda r: r["vix_bucket"]),
            "by_date": summarize(last14, lambda r: r["date_et"]),
        },
        "full_history": {
            "by_account": summarize(full, lambda r: r["arm"]),
            "by_direction": summarize(full, lambda r: r["direction"]),
            "by_setup": summarize(full, lambda r: r["setup_final"]),
            "by_exit_stage": summarize(full, lambda r: r["exit_stage_final"]),
            "by_hour_of_day": summarize(full, lambda r: r["tod_bucket"]),
            "by_day_of_week": summarize(full, lambda r: r["day_of_week"]),
            "by_vix_bucket": summarize(full, lambda r: r["vix_bucket"]),
            "by_date": summarize(full, lambda r: r["date_et"]),
        },
    }

    # -------- Q1: concentration ----------------------------------------------------------
    def concentration_analysis(rows, label):
        by_date = defaultdict(list)
        for r in rows:
            by_date[r["date_et"]].append(r["actual_exit_pnl"])
        day_totals = {d: round(sum(v), 2) for d, v in by_date.items()}
        worst_date = min(day_totals, key=day_totals.get) if day_totals else None
        worst_val = day_totals.get(worst_date, 0.0)
        total = net(rows)
        ex_worst = round(total - worst_val, 2)
        losing_days = sorted([v for v in day_totals.values() if v < 0])
        loss_total = sum(losing_days)
        worst_share_of_loss = round(worst_val / loss_total, 4) if loss_total else None
        # worst arm
        by_arm = defaultdict(list)
        for r in rows:
            by_arm[r["arm"]].append(r["actual_exit_pnl"])
        arm_totals = {a: round(sum(v), 2) for a, v in by_arm.items()}
        worst_arm = min(arm_totals, key=arm_totals.get) if arm_totals else None
        return {
            "n_dates": len(day_totals),
            "worst_date": worst_date,
            "worst_date_total": worst_val,
            "total_net": total,
            "ex_worst_date_net": ex_worst,
            "worst_date_share_of_all_losing_days_dollars": worst_share_of_loss,
            "arm_totals": arm_totals,
            "worst_arm": worst_arm,
            "worst_arm_total": arm_totals.get(worst_arm) if worst_arm else None,
        }

    report["q1_concentration"] = {
        "last14": concentration_analysis(last14, "last14"),
        "full_history": concentration_analysis(full, "full"),
    }

    # -------- Q2: winner vs loser shape ----------------------------------------------------
    def shape_stats(rows, label):
        winners = [r for r in rows if r["outcome"] == "winner"]
        losers = [r for r in rows if r["outcome"] == "loser"]

        def stat_block(sub):
            if not sub:
                return None
            pnls = [r["actual_exit_pnl"] for r in sub]
            holds = [r["hold_minutes"] for r in sub if r["hold_minutes"] is not None]
            return {
                "n": len(sub),
                "mean_pnl": round(sum(pnls) / len(pnls), 2),
                "median_pnl": round(statistics.median(pnls), 2),
                "max_abs_pnl": round(max(pnls, key=abs), 2),
                "mean_hold_min": round(sum(holds) / len(holds), 1) if holds else None,
                "median_hold_min": round(statistics.median(holds), 1) if holds else None,
            }

        return {"winners": stat_block(winners), "losers": stat_block(losers)}

    report["q2_winner_vs_loser_shape"] = {
        "last14": shape_stats(last14, "last14"),
        "full_history": shape_stats(full, "full"),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"n_positions full={len(full)} last14={len(last14)}")
    print(f"net full={report['_meta']['net_full_history']} last14={report['_meta']['net_last14']}")
    print(f"journal join coverage: {matched}/{len(positions)}")


if __name__ == "__main__":
    main()
