"""
H7 TIME OF DAY -- scratch analysis tool (read-only on all trading-path / state files).
Population: automation/state/pain-ledger-sourced trades (analysis/pain-ledger/mae-mfe.json),
broker-fills-derived, attribution==engine, since 2026-07-01.

Outputs:
  analysis/deep-research/2026-09-03-money/time-of-day.json
  analysis/deep-research/2026-09-03-money/time-of-day.md   (written separately by caller)

No network calls. No writes outside analysis/deep-research/2026-09-03-money/.
"""
import json
import random
import statistics
from collections import defaultdict, Counter
from datetime import datetime
from zoneinfo import ZoneInfo

REPO = "C:/Users/jackw/Desktop/42"
ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

random.seed(42)

WINNING_DAYS = ["2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"]

BUCKETS = [
    ("09:35-09:50", "09:35", "09:50"),
    ("09:50-10:30", "09:50", "10:30"),
    ("10:30-12:00", "10:30", "12:00"),
    ("12:00-14:00", "12:00", "14:00"),
    ("14:00-15:20", "14:00", "15:20"),
]

GATE_CANDIDATES = ["09:45", "09:50", "10:00"]


def hm(ts_et_str):
    # ts_et_str like '2026-08-19T10:41:03' -> 'HH:MM'
    return ts_et_str[11:16]


def bucket_for(hhmm):
    for name, lo, hi in BUCKETS:
        if lo <= hhmm < hi:
            return name
    if hhmm < "09:35":
        return "PRE-09:35(anomaly)"
    if hhmm >= "15:20":
        return "POST-15:20(anomaly)"
    return "UNBUCKETED"


def load_trades():
    with open(f"{REPO}/analysis/pain-ledger/mae-mfe.json", "r", encoding="utf-8") as f:
        d = json.load(f)
    trades = d["trades"]
    out = []
    for t in trades:
        if t["date"] < "2026-07-01":
            continue
        ts_utc = datetime.fromisoformat(t["entry_ts_utc"].replace("Z", "+00:00"))
        ts_et = ts_utc.astimezone(ET)
        t = dict(t)
        t["entry_ts_et"] = ts_et.isoformat()
        t["entry_hm"] = ts_et.strftime("%H:%M")
        t["bucket"] = bucket_for(t["entry_hm"])
        out.append(t)
    return out, d["_meta"]


def load_vix_series():
    """Dense VIX series from core-decisions.jsonl (safe account tick, market-level value)."""
    series = []
    with open(f"{REPO}/automation/state/core-decisions.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("account") != "safe":
                continue
            v = r.get("vix")
            if v is None:
                continue
            series.append((r["ts_et"], v))
    series.sort(key=lambda x: x[0])
    return series


def vix_asof(series, ts_et_iso):
    """Nearest VIX reading AT OR BEFORE ts_et_iso (no look-ahead). series sorted ascending."""
    # ts_et_iso has tz offset (e.g. ...-04:00); core-decisions ts_et strings are naive local ET.
    target = ts_et_iso[:19]  # 'YYYY-MM-DDTHH:MM:SS' naive-comparable prefix
    lo, hi = 0, len(series) - 1
    ans = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if series[mid][0] <= target:
            ans = series[mid][1]
            lo = mid + 1
        else:
            hi = mid - 1
    return ans


def vix_regime(v):
    if v is None:
        return "UNKNOWN"
    if v < 15:
        return "<15"
    if v <= 17:
        return "15-17"
    return ">17"


def bootstrap_mean_ci(values, n_resamples=3000, alpha=0.025):
    if len(values) == 0:
        return (None, None, None)
    if len(values) == 1:
        return (values[0], values[0], values[0])
    means = []
    n = len(values)
    for _ in range(n_resamples):
        sample = [values[random.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo_idx = int(alpha * n_resamples)
    hi_idx = int((1 - alpha) * n_resamples) - 1
    hi_idx = min(hi_idx, n_resamples - 1)
    return (means[lo_idx], statistics.mean(values), means[hi_idx])


def profit_factor(values):
    wins = sum(v for v in values if v > 0)
    losses = sum(-v for v in values if v < 0)
    if losses == 0:
        return float("inf") if wins > 0 else None
    return wins / losses


def bootstrap_pf_ci(values, n_resamples=3000, alpha=0.025):
    if len(values) < 2:
        return (None, None, None)
    n = len(values)
    pfs = []
    for _ in range(n_resamples):
        sample = [values[random.randrange(n)] for _ in range(n)]
        pf = profit_factor(sample)
        if pf is not None and pf != float("inf"):
            pfs.append(pf)
    if not pfs:
        return (None, None, None)
    pfs.sort()
    lo_idx = int(alpha * len(pfs))
    hi_idx = int((1 - alpha) * len(pfs)) - 1
    hi_idx = min(hi_idx, len(pfs) - 1)
    return (pfs[lo_idx], statistics.mean(pfs), pfs[hi_idx])


def concentration_top3(trades_subset):
    pnls = sorted((t["realized_pnl"] for t in trades_subset), reverse=True)
    total = sum(pnls)
    top3 = sum(pnls[:3])
    if total == 0:
        pct = None
    else:
        pct = top3 / total * 100.0
    return {
        "top3_sum": round(top3, 2),
        "total": round(total, 2),
        "top3_pct_of_total": round(pct, 1) if pct is not None else None,
        "top3_trades": pnls[:3],
    }


def day_level_stats(trades_subset, n_resamples=3000, alpha=0.025):
    """Aggregate to one PnL figure per distinct trading day (the true independent unit,
    since the shared-signal architecture fires the SAME setup across up to 6 arms in the
    same 1-2 minutes -- treating each arm-fill as an independent trial pseudo-replicates)."""
    by_day = defaultdict(float)
    by_day_n = defaultdict(int)
    for t in trades_subset:
        by_day[t["date"]] += t["realized_pnl"]
        by_day_n[t["date"]] += 1
    days = sorted(by_day.keys())
    day_pnls = [by_day[d] for d in days]
    n_days = len(days)
    n_pos_days = sum(1 for v in day_pnls if v > 0)
    n_neg_days = sum(1 for v in day_pnls if v < 0)
    total = sum(day_pnls)
    lo, mean_, hi = bootstrap_mean_ci(day_pnls, n_resamples, alpha) if n_days else (None, None, None)
    ranked = sorted(zip(days, day_pnls), key=lambda kv: kv[1])
    worst_day = ranked[0] if ranked else None
    best_day = ranked[-1] if ranked else None
    ex_worst = round(total - worst_day[1], 2) if worst_day else None
    ex_best = round(total - best_day[1], 2) if best_day else None
    top3_days = sorted(day_pnls, key=lambda v: -abs(v))[:3]
    return {
        "n_distinct_days": n_days,
        "n_positive_days": n_pos_days,
        "n_negative_days": n_neg_days,
        "day_win_rate_pct": round(100.0 * n_pos_days / n_days, 1) if n_days else None,
        "total_pnl": round(total, 2),
        "mean_pnl_per_day": round(total / n_days, 2) if n_days else None,
        "mean_pnl_per_day_boot_ci": [round(lo, 2) if lo is not None else None,
                                      round(mean_, 2) if mean_ is not None else None,
                                      round(hi, 2) if hi is not None else None],
        "worst_day": {"date": worst_day[0], "pnl": round(worst_day[1], 2), "n_trades": by_day_n[worst_day[0]]} if worst_day else None,
        "best_day": {"date": best_day[0], "pnl": round(best_day[1], 2), "n_trades": by_day_n[best_day[0]]} if best_day else None,
        "total_ex_worst_day": ex_worst,
        "total_ex_best_day": ex_best,
        "top3_days_by_abs_pnl": [round(v, 2) for v in top3_days],
        "days_detail": [{"date": d, "pnl": round(by_day[d], 2), "n_trades": by_day_n[d]} for d in days],
    }


def bucket_stats(trades_subset):
    n = len(trades_subset)
    pnls = [t["realized_pnl"] for t in trades_subset]
    total = sum(pnls)
    wins = [t for t in trades_subset if t["outcome"] == "winner"]
    losers = [t for t in trades_subset if t["outcome"] == "loser"]
    scratch = [t for t in trades_subset if t["outcome"] == "scratch"]
    wr = (len(wins) / n * 100.0) if n else None
    pf = profit_factor(pnls)
    pf_lo, pf_mean, pf_hi = bootstrap_pf_ci(pnls)
    mean_lo, mean_mean, mean_hi = bootstrap_mean_ci(pnls)
    return {
        "n": n,
        "total_pnl": round(total, 2),
        "mean_pnl": round(total / n, 2) if n else None,
        "mean_pnl_boot_ci": [round(mean_lo, 2) if mean_lo is not None else None,
                              round(mean_mean, 2) if mean_mean is not None else None,
                              round(mean_hi, 2) if mean_hi is not None else None],
        "win_rate_pct": round(wr, 1) if wr is not None else None,
        "n_winners": len(wins),
        "n_losers": len(losers),
        "n_scratch": len(scratch),
        "profit_factor": (round(pf, 3) if isinstance(pf, float) else pf),
        "pf_boot_ci": [round(pf_lo, 3) if pf_lo is not None else None,
                        round(pf_mean, 3) if pf_mean is not None else None,
                        round(pf_hi, 3) if pf_hi is not None else None],
        "concentration": concentration_top3(trades_subset),
        "day_level": day_level_stats(trades_subset),
    }


def main():
    trades, meta = load_trades()
    vix_series = load_vix_series()
    for t in trades:
        v = vix_asof(vix_series, t["entry_ts_et"])
        t["vix_at_entry"] = v
        t["vix_regime"] = vix_regime(v)

    report = {
        "population": {
            "n_trades": len(trades),
            "source": "analysis/pain-ledger/mae-mfe.json trades[], date>=2026-07-01",
            "source_meta_provenance": meta.get("provenance"),
            "date_range": [min(t["date"] for t in trades), max(t["date"] for t in trades)],
            "arms": dict(Counter(t["arm"] for t in trades)),
            "setups": dict(Counter(t["setup"] for t in trades)),
        }
    }

    # anomaly check: any entries outside declared window?
    anomalies = [t for t in trades if "anomaly" in t["bucket"] or t["bucket"] == "UNBUCKETED"]
    report["window_anomalies"] = {
        "n": len(anomalies),
        "rows": [{"date": t["date"], "arm": t["arm"], "hm": t["entry_hm"], "bucket": t["bucket"],
                   "pnl": t["realized_pnl"]} for t in anomalies],
    }

    # --- Overall by bucket ---
    by_bucket = defaultdict(list)
    for t in trades:
        by_bucket[t["bucket"]].append(t)

    bucket_order = [b[0] for b in BUCKETS]
    overall = {}
    for name in bucket_order:
        overall[name] = bucket_stats(by_bucket.get(name, []))
    report["by_bucket_overall"] = overall

    # --- By bucket x setup ---
    by_bucket_setup = {}
    for name in bucket_order:
        subset = by_bucket.get(name, [])
        setups = defaultdict(list)
        for t in subset:
            setups[t["setup"]].append(t)
        by_bucket_setup[name] = {s: bucket_stats(rows) for s, rows in setups.items()}
    report["by_bucket_x_setup"] = by_bucket_setup

    # --- By bucket x arm ---
    by_bucket_arm = {}
    for name in bucket_order:
        subset = by_bucket.get(name, [])
        arms = defaultdict(list)
        for t in subset:
            arms[t["arm"]].append(t)
        by_bucket_arm[name] = {a: bucket_stats(rows) for a, rows in arms.items()}
    report["by_bucket_x_arm"] = by_bucket_arm

    # --- By bucket x regime ---
    by_bucket_regime = {}
    for name in bucket_order:
        subset = by_bucket.get(name, [])
        regimes = defaultdict(list)
        for t in subset:
            regimes[t["vix_regime"]].append(t)
        by_bucket_regime[name] = {r: bucket_stats(rows) for r, rows in regimes.items()}
    report["by_bucket_x_regime"] = by_bucket_regime

    # --- Gate costing ---
    gate_results = {}
    for gate in GATE_CANDIDATES:
        kept = [t for t in trades if t["entry_hm"] >= gate]
        removed = [t for t in trades if t["entry_hm"] < gate]
        kept_stats = bucket_stats(kept)
        removed_stats = bucket_stats(removed)
        book_delta = kept_stats["total_pnl"] - report["by_bucket_overall"][bucket_order[0]]["total_pnl"] \
            if False else (sum(t["realized_pnl"] for t in kept) - sum(t["realized_pnl"] for t in trades))
        # winning-day impact
        wd_impact = {}
        for wd in WINNING_DAYS:
            day_trades = [t for t in trades if t["date"] == wd]
            day_removed = [t for t in day_trades if t["entry_hm"] < gate]
            wd_impact[wd] = {
                "n_day_trades": len(day_trades),
                "n_blocked_by_gate": len(day_removed),
                "day_total_pnl": round(sum(t["realized_pnl"] for t in day_trades), 2),
                "blocked_pnl": round(sum(t["realized_pnl"] for t in day_removed), 2),
                "blocked_trades": [
                    {"arm": t["arm"], "setup": t["setup"], "hm": t["entry_hm"],
                     "pnl": t["realized_pnl"], "outcome": t["outcome"]}
                    for t in day_removed
                ],
            }
        gate_results[gate] = {
            "kept": kept_stats,
            "removed_cohort": removed_stats,
            "book_delta_if_gated": round(book_delta, 2),
            "removed_cohort_is_net_negative": removed_stats["total_pnl"] < 0 if removed else None,
            "winning_day_impact": wd_impact,
        }
    report["gate_costing"] = gate_results

    # --- Structure-reason / range-position diagnosis (core path only: safe/bold, schema from 2026-08-19) ---
    with open(f"{REPO}/automation/state/core-decisions.jsonl", "r", encoding="utf-8") as f:
        core_lines = [json.loads(l) for l in f if l.strip()]
    placed = [r for r in core_lines if r.get("action") == "PLACED"]
    for p in placed:
        p["_hm"] = hm(p["ts_et"])
        conv = p.get("conviction") or {}
        p["_structure_reason"] = conv.get("structure_reason")
        comps = conv.get("components") or {}
        p["_range_position"] = comps.get("range_position")
    schema_present = [p for p in placed if p.get("conviction") is not None]
    early_placed = [p for p in schema_present if "09:35" <= p["_hm"] < "09:50"]
    later_placed = [p for p in schema_present if p["_hm"] >= "09:50"]
    report["structure_reason_diagnosis"] = {
        "caveat": "conviction/structure_reason/range_position schema only exists on the core "
                  "(safe/bold) decision path from 2026-08-19 onward -- NOT present for fleet "
                  "arms (safe-1/safe-3/risky-1/risky-3) at all, and not present for core-path "
                  "PLACED rows before 2026-08-19. This sub-analysis covers a SMALLER, LATER "
                  "population than the main time-of-day population above.",
        "n_placed_total_core_path": len(placed),
        "n_placed_with_conviction_schema": len(schema_present),
        "early_09_35_09_50": {
            "n": len(early_placed),
            "structure_reason_dist": dict(Counter(p["_structure_reason"] for p in early_placed)),
            "n_insufficient_bars": sum(1 for p in early_placed if p["_structure_reason"] == "unknown:insufficient_bars"),
            "pct_insufficient_bars": round(100.0 * sum(1 for p in early_placed if p["_structure_reason"] == "unknown:insufficient_bars") / len(early_placed), 1) if early_placed else None,
            "range_position_values": [p["_range_position"] for p in early_placed],
        },
        "later_09_50_plus": {
            "n": len(later_placed),
            "structure_reason_dist": dict(Counter(p["_structure_reason"] for p in later_placed)),
            "n_insufficient_bars": sum(1 for p in later_placed if p["_structure_reason"] == "unknown:insufficient_bars"),
            "pct_insufficient_bars": round(100.0 * sum(1 for p in later_placed if p["_structure_reason"] == "unknown:insufficient_bars") / len(later_placed), 1) if later_placed else None,
        },
    }

    # --- Winning days full detail (for kills-winners check) ---
    winning_day_detail = {}
    for wd in WINNING_DAYS:
        day_trades = [t for t in trades if t["date"] == wd]
        winning_day_detail[wd] = {
            "n_trades": len(day_trades),
            "total_pnl": round(sum(t["realized_pnl"] for t in day_trades), 2),
            "trades": sorted([
                {"arm": t["arm"], "setup": t["setup"], "hm": t["entry_hm"], "bucket": t["bucket"],
                 "pnl": t["realized_pnl"], "outcome": t["outcome"], "vix": t["vix_at_entry"]}
                for t in day_trades
            ], key=lambda r: r["hm"]),
        }
    report["winning_days_detail"] = winning_day_detail

    with open(f"{REPO}/analysis/deep-research/2026-09-03-money/time-of-day.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print("WROTE analysis/deep-research/2026-09-03-money/time-of-day.json")
    print("n_trades:", len(trades))
    print("bucket totals:")
    for name in bucket_order:
        s = overall[name]
        print(f"  {name}: n={s['n']} total=${s['total_pnl']} mean=${s['mean_pnl']} WR={s['win_rate_pct']}% PF={s['profit_factor']}")


if __name__ == "__main__":
    main()
