"""
H6: BEAR ENTRIES WITHOUT A LEVEL
Scratch analysis script for analysis/deep-research/2026-09-03-money/bear-no-level.{md,json}

READ-ONLY on automation/state/** and journal/**. No network calls. Cached data only.

Population: every BEARISH_REJECTION_RIDE_THE_RIBBON real engine fill since 2026-07-01
across all arms (safe-2, bold-2, safe-1, safe-3, risky-1, risky-3), sourced from the
pain-ledger (analysis/pain-ledger/mae-mfe.json), which is itself built from broker fills
(fills-ledger.jsonl, attribution==engine) + real OPRA 1-min bars. That ledger is the only
source of REALIZED PnL per trade, so it is the population anchor.

Each trade is joined to its originating automation/state/core-decisions.jsonl tick (same
date + side + nearest timestamp + matching setup name) to recover trigger_level_exact,
conviction.components.range_position, htf_15m, ribbon, vix and time-of-day. This join is
valid for fleet arms too: automation/state/fleet/build_shared_signal.py confirms every arm
(safe-1/3, risky-1/3) inherits its side/setup/trigger_level_exact from the SAME core-decisions
tick (whichever of safe/bold produced the ENTER_* verdict that minute) -- it is a broadcast
signal, not a per-arm computation. safe-2/bold-2 ARE core-decisions rows directly.
"""
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
PAIN_LEDGER = REPO / "analysis" / "pain-ledger" / "mae-mfe.json"

OUT_DIR = REPO / "analysis" / "deep-research" / "2026-09-03-money"
OUT_MD = OUT_DIR / "bear-no-level.md"
OUT_JSON = OUT_DIR / "bear-no-level.json"

CUTOFF_DATE = "2026-07-01"
BEAR_SETUP = "BEARISH_REJECTION_RIDE_THE_RIBBON"
BULL_SETUP = "BULLISH_RECLAIM_RIDE_THE_RIBBON"
RNG_SEED = 42
N_BOOT = 5000

BIG_WIN_DAYS = ["2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"]
NAMED_BEAR_DAYS = ["2026-08-07", "2026-08-14"]


def load_core_decisions():
    """Load every core-decisions row with a non-null side (entry-eligible ticks only)."""
    rows = []
    with open(CORE_DECISIONS, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("side") not in ("C", "P"):
                continue
            ts = d.get("ts_et")
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts)
            except ValueError:
                continue
            conv = d.get("conviction") or {}
            comps = conv.get("components") or {}
            rows.append({
                "dt": dt,
                "date": dt.strftime("%Y-%m-%d"),
                "account": d.get("account"),
                "side": d.get("side"),
                "setup": d.get("setup"),
                "verdict": d.get("verdict"),
                "action": d.get("action"),
                "trigger_level_exact": d.get("trigger_level_exact"),
                "conviction_total": conv.get("total"),
                "conviction_would_block": conv.get("would_block"),
                "range_position": comps.get("range_position"),
                "range_extreme_score": comps.get("range_extreme"),
                "structure_agreement": comps.get("structure_agreement"),
                "htf_15m": d.get("htf_15m"),
                "ribbon": d.get("ribbon"),
                "vix": d.get("vix"),
                "spy": d.get("spy"),
                "triggers": d.get("triggers") or [],
            })
    return rows


def load_pain_ledger_trades():
    d = json.loads(PAIN_LEDGER.read_text(encoding="utf-8"))
    return d["trades"], d.get("_meta", {})


def et_from_utc_iso(ts_utc: str) -> datetime:
    """Convert an entry_ts_utc ISO string to naive ET (UTC-4, EDT -- entire dataset
    06-26..09-02 falls inside EDT, verified: no DST boundary crossed)."""
    s = ts_utc.replace("Z", "+00:00")
    dt_utc = datetime.fromisoformat(s)
    dt_et = dt_utc.astimezone(timezone(timedelta(hours=-4)))
    return dt_et.replace(tzinfo=None)


def bucket_range_position(rp):
    if rp is None:
        return "missing"
    if rp <= 0.15:
        return "extreme_low_0.00-0.15"
    if rp <= 0.35:
        return "low_0.15-0.35"
    if rp <= 0.65:
        return "mid_0.35-0.65"
    if rp <= 0.85:
        return "high_0.65-0.85"
    return "extreme_high_0.85-1.00"


def bucket_time(dt: datetime):
    hm = dt.hour * 60 + dt.minute
    if hm < 9 * 60 + 30:
        return "pre_930"
    if hm < 10 * 60:
        return "0930-1000_open"
    if hm < 11 * 60 + 30:
        return "1000-1130_morning"
    if hm < 13 * 60 + 30:
        return "1130-1330_midday"
    if hm < 15 * 60:
        return "1330-1500_afternoon"
    return "1500-1555_close"


def htf_agrees(htf_15m, side):
    if not htf_15m:
        return "unknown"
    htf_u = str(htf_15m).upper()
    if side == "P":
        return "agrees" if htf_u == "BEAR" else ("disagrees" if htf_u == "BULL" else "neutral")
    else:
        return "agrees" if htf_u == "BULL" else ("disagrees" if htf_u == "BEAR" else "neutral")


def match_trade_to_core_row(trade, core_by_date_side, tol_minutes=6):
    date = trade["date"]
    side = "P" if trade["setup"] == BEAR_SETUP else "C"
    entry_et = et_from_utc_iso(trade["entry_ts_utc"])
    candidates = core_by_date_side.get((date, side), [])
    best = None
    best_dt_diff = None
    for row in candidates:
        if row["setup"] != trade["setup"]:
            continue
        diff = abs((row["dt"] - entry_et).total_seconds()) / 60.0
        if diff > tol_minutes:
            continue
        if best is None or diff < best_dt_diff:
            best = row
            best_dt_diff = diff
    return best, best_dt_diff, entry_et


def bootstrap_mean_ci(values, n_boot=N_BOOT, seed=RNG_SEED):
    values = np.asarray(values, dtype=float)
    n = len(values)
    if n == 0:
        return {"n": 0, "mean": None, "ci_lo": None, "ci_hi": None}
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot)
    for i in range(n_boot):
        sample = rng.choice(values, size=n, replace=True)
        means[i] = sample.mean()
    return {
        "n": int(n),
        "mean": float(values.mean()),
        "ci_lo": float(np.percentile(means, 2.5)),
        "ci_hi": float(np.percentile(means, 97.5)),
    }


def win_rate(trades):
    n = len(trades)
    if n == 0:
        return None
    w = sum(1 for t in trades if t["realized_pnl"] > 0)
    return w / n


def profit_factor(trades):
    gains = sum(t["realized_pnl"] for t in trades if t["realized_pnl"] > 0)
    losses = -sum(t["realized_pnl"] for t in trades if t["realized_pnl"] < 0)
    if losses == 0:
        return None if gains == 0 else float("inf")
    return gains / losses


def group_summary(trades):
    pnls = [t["realized_pnl"] for t in trades]
    boot = bootstrap_mean_ci(pnls)
    return {
        "n": len(trades),
        "sum_pnl": round(sum(pnls), 2) if pnls else 0.0,
        "mean_pnl": round(boot["mean"], 2) if boot["mean"] is not None else None,
        "mean_pnl_ci95": [round(boot["ci_lo"], 2), round(boot["ci_hi"], 2)] if boot["mean"] is not None else None,
        "win_rate": round(win_rate(trades), 3) if win_rate(trades) is not None else None,
        "profit_factor": (round(profit_factor(trades), 3)
                           if profit_factor(trades) not in (None, float("inf")) else profit_factor(trades)),
    }


def main():
    core_rows = load_core_decisions()
    core_by_date_side = defaultdict(list)
    for r in core_rows:
        core_by_date_side[(r["date"], r["side"])].append(r)

    all_trades, pain_meta = load_pain_ledger_trades()

    report = {
        "generated_at_et": None,
        "cutoff_date": CUTOFF_DATE,
        "pain_ledger_meta": pain_meta,
    }

    for setup_name, side_letter, tag in [(BEAR_SETUP, "P", "bear"), (BULL_SETUP, "C", "bull")]:
        pop = [t for t in all_trades if t["setup"] == setup_name and t["date"] >= CUTOFF_DATE]
        matched = []
        unmatched = []
        for t in pop:
            row, diff, entry_et = match_trade_to_core_row(t, core_by_date_side)
            rec = dict(t)
            rec["entry_et"] = entry_et.isoformat()
            if row is None:
                unmatched.append(rec)
                continue
            rec["match_diff_min"] = round(diff, 2)
            rec["match_account"] = row["account"]
            rec["trigger_level_exact"] = row["trigger_level_exact"]
            rec["has_level"] = row["trigger_level_exact"] is not None
            rec["conviction_total"] = row["conviction_total"]
            rec["range_position"] = row["range_position"]
            rec["range_position_bucket"] = bucket_range_position(row["range_position"])
            rec["htf_15m"] = row["htf_15m"]
            rec["htf_agreement"] = htf_agrees(row["htf_15m"], side_letter)
            rec["ribbon"] = row["ribbon"]
            rec["vix"] = row["vix"]
            rec["time_bucket"] = bucket_time(entry_et)
            rec["tod_hhmm"] = entry_et.strftime("%H:%M")
            rec["triggers"] = row["triggers"]
            matched.append(rec)

        # VIX regime split
        def vix_regime(v):
            if v is None:
                return "unknown"
            if v < 15:
                return "vix<15"
            if v <= 17:
                return "vix15-17"
            return "vix>17"

        for rec in matched:
            rec["vix_regime"] = vix_regime(rec["vix"])

        has_level_group = [r for r in matched if r["has_level"]]
        no_level_group = [r for r in matched if not r["has_level"]]

        by_range_bucket = defaultdict(list)
        for r in matched:
            by_range_bucket[r["range_position_bucket"]].append(r)

        by_level_x_range = defaultdict(list)
        for r in matched:
            key = f"{'level' if r['has_level'] else 'no_level'}__{r['range_position_bucket']}"
            by_level_x_range[key].append(r)

        by_time = defaultdict(list)
        for r in matched:
            by_time[r["time_bucket"]].append(r)

        by_htf = defaultdict(list)
        for r in matched:
            by_htf[r["htf_agreement"]].append(r)

        by_vix_regime = defaultdict(list)
        for r in matched:
            by_vix_regime[r["vix_regime"]].append(r)

        by_arm = defaultdict(list)
        for r in matched:
            by_arm[r["arm"]].append(r)

        # concentration check: top-3 trade share of |sum pnl|
        sorted_by_abs = sorted(matched, key=lambda r: abs(r["realized_pnl"]), reverse=True)
        top3 = sorted_by_abs[:3]
        total_abs = sum(abs(r["realized_pnl"]) for r in matched) or 1.0
        top3_share = sum(abs(r["realized_pnl"]) for r in top3) / total_abs

        section = {
            "setup": setup_name,
            "n_population_pain_ledger": len(pop),
            "n_matched_to_core_decisions": len(matched),
            "n_unmatched": len(unmatched),
            "unmatched_trades": [
                {"date": u["date"], "arm": u["arm"], "symbol": u["symbol"],
                 "realized_pnl": u["realized_pnl"], "entry_et": u["entry_et"]}
                for u in unmatched
            ],
            "has_level_vs_no_level": {
                "has_level": group_summary(has_level_group),
                "no_level": group_summary(no_level_group),
            },
            "by_range_position_bucket": {k: group_summary(v) for k, v in sorted(by_range_bucket.items())},
            "by_level_x_range_bucket": {k: group_summary(v) for k, v in sorted(by_level_x_range.items())},
            "by_time_of_day": {k: group_summary(v) for k, v in sorted(by_time.items())},
            "by_htf_agreement": {k: group_summary(v) for k, v in sorted(by_htf.items())},
            "by_vix_regime": {k: group_summary(v) for k, v in sorted(by_vix_regime.items())},
            "by_arm": {k: group_summary(v) for k, v in sorted(by_arm.items())},
            "top3_concentration": {
                "top3_share_of_total_abs_pnl": round(top3_share, 3),
                "top3_trades": [
                    {"date": r["date"], "arm": r["arm"], "symbol": r["symbol"], "pnl": r["realized_pnl"],
                     "has_level": r["has_level"], "range_position": r["range_position"]}
                    for r in top3
                ],
            },
            "range_position_coverage_note": (
                "conviction.components.range_position is populated ONLY from the tick where the "
                "producer's session_high/session_low bug was fixed (2026-08-14 per heartbeat_core.py "
                "comment at _score_conviction_shadow) -- see coverage_by_month below."
            ),
        }
        # coverage by month for range_position
        cov = defaultdict(lambda: [0, 0])
        for r in matched:
            month = r["date"][:7]
            cov[month][1] += 1
            if r["range_position"] is not None:
                cov[month][0] += 1
        section["range_position_coverage_by_month"] = {
            k: {"n_with_range_position": v[0], "n_total": v[1]} for k, v in sorted(cov.items())
        }

        report[tag] = section
        report[f"_{tag}_matched_raw"] = matched  # kept for rule-costing pass below

    # ---------------------------------------------------------------
    # PROPOSED RULE COSTING (bear only): require trigger_level_exact is not None
    # AND (range_position is None OR range_position >= 0.25)
    # range_position None (pre-2026-08-14 / degraded) is treated as PASS (not blocked) --
    # the instrument was not live then, so a live rule cannot condition on it; only cases
    # where the instrument actually SAW range_position and it was < 0.25 get blocked.
    # ---------------------------------------------------------------
    bear_matched = report["_bear_matched_raw"]

    def rule_allows(r, use_range_gate=True):
        if not r["has_level"]:
            return False
        if use_range_gate and r["range_position"] is not None and r["range_position"] < 0.25:
            return False
        return True

    variants = {
        "A_level_only": lambda r: r["has_level"],
        "B_level_and_range>=0.25": lambda r: rule_allows(r, use_range_gate=True),
    }
    rule_costing = {}
    for vname, fn in variants.items():
        allowed = [r for r in bear_matched if fn(r)]
        blocked = [r for r in bear_matched if not fn(r)]
        rule_costing[vname] = {
            "allowed": group_summary(allowed),
            "blocked": group_summary(blocked),
            "baseline_all": group_summary(bear_matched),
            "delta_vs_baseline_mean_pnl": (
                round(group_summary(allowed)["mean_pnl"] - group_summary(bear_matched)["mean_pnl"], 2)
                if allowed and group_summary(allowed)["mean_pnl"] is not None
                and group_summary(bear_matched)["mean_pnl"] is not None else None
            ),
        }

    # Named-day checks
    named_day_checks = {}
    for day in BIG_WIN_DAYS + NAMED_BEAR_DAYS:
        day_bear = [r for r in bear_matched if r["date"] == day]
        day_bull = report["_bull_matched_raw"]
        day_bull_trades = [r for r in day_bull if r["date"] == day]
        rows = []
        for r in day_bear:
            would_block_B = not rule_allows(r, use_range_gate=True)
            rows.append({
                "arm": r["arm"], "symbol": r["symbol"], "realized_pnl": r["realized_pnl"],
                "outcome": r["outcome"], "has_level": r["has_level"],
                "range_position": r["range_position"], "tod": r["tod_hhmm"],
                "would_block_under_rule_B": would_block_B,
            })
        named_day_checks[day] = {
            "bear_trades": rows,
            "bear_pnl_sum": round(sum(r["realized_pnl"] for r in day_bear), 2),
            "bull_pnl_sum": round(sum(r["realized_pnl"] for r in day_bull_trades), 2),
            "rule_B_would_block_any_bear_winner": any(
                r["would_block_under_rule_B"] and r["realized_pnl"] > 0 for r in rows
            ),
        }

    report["bear_rule_costing"] = rule_costing
    report["named_day_checks"] = named_day_checks

    # drop the raw matched dumps from the compact JSON (keep separately for inspection if wanted)
    bear_raw = report.pop("_bear_matched_raw")
    bull_raw = report.pop("_bull_matched_raw")

    report["generated_at_et"] = datetime.now().isoformat()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    # also dump raw matched trade tables for auditability
    (OUT_DIR / "bear-no-level-raw-bear-trades.json").write_text(
        json.dumps(bear_raw, indent=2, default=str), encoding="utf-8")
    (OUT_DIR / "bear-no-level-raw-bull-trades.json").write_text(
        json.dumps(bull_raw, indent=2, default=str), encoding="utf-8")

    print("WROTE", OUT_JSON)
    print("bear n_matched:", report["bear"]["n_matched_to_core_decisions"],
          "of pop", report["bear"]["n_population_pain_ledger"])
    print("bull n_matched:", report["bull"]["n_matched_to_core_decisions"],
          "of pop", report["bull"]["n_population_pain_ledger"])


if __name__ == "__main__":
    main()
