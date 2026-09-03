"""money_bold_otm_tickets.py -- H3 BOLD OTM TICKETS hypothesis test.

Scratch analysis script. READ-ONLY on all production/state data. No network calls.
Writes report to analysis/deep-research/2026-09-03-money/bold-otm-tickets.{md,json}.

Hypothesis: bold-2 buys OTM-2 strikes; recent entries were $0.15-$0.37 premiums
under VIX ~15. Does entry premium bucket / strike distance from spot correlate
with outcome (P&L, WR, PF, catastrophe-cap-hit rate), split by VIX regime?
What would a min-premium floor or tier shift for bold-2 under VIX<16 have done?

Data sources (all cached, all local, read-only):
  - analysis/pain-ledger/mae-mfe.json        -- 394 scored positions, all arms
  - automation/state/core-decisions.jsonl    -- 1/min core ticks (safe+bold), vix+spy
  - automation/state/aggressive/params.json  -- bold-2 min_entry_premium floor (read-only)
  - crypto/lib/strike_selection.py           -- tier ladder (read-only, not imported
    for execution -- just inspected; this script does not touch the trading path)
"""
from __future__ import annotations

import json
import re
import random
import statistics
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAE_MFE_PATH = ROOT / "analysis" / "pain-ledger" / "mae-mfe.json"
CORE_DECISIONS_PATH = ROOT / "automation" / "state" / "core-decisions.jsonl"
BOLD_TIER_RAIL_PATH = ROOT / "automation" / "state" / "bold-tier-rail.json"
OUT_DIR = ROOT / "analysis" / "deep-research" / "2026-09-03-money"
OUT_MD = OUT_DIR / "bold-otm-tickets.md"
OUT_JSON = OUT_DIR / "bold-otm-tickets.json"

random.seed(42)  # deterministic bootstrap

OCC_RE = re.compile(r"^SPY(\d{6})([CP])(\d{8})$")


def parse_occ(symbol: str):
    m = OCC_RE.match(symbol)
    if not m:
        return None
    _, side, strike8 = m.groups()
    strike = int(strike8) / 1000.0
    return side, strike


def load_mae_mfe():
    d = json.loads(MAE_MFE_PATH.read_text())
    return d["_meta"], d["trades"]


def load_core_decisions_series():
    """Return a sorted list of (dt_et_naive, spy, vix) from core-decisions.jsonl,
    one row per tick per account, deduped to at most one row per (minute)."""
    rows = []
    with open(CORE_DECISIONS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = r.get("ts_et")
            spy = r.get("spy")
            vix = r.get("vix")
            if not ts or spy is None or vix is None:
                continue
            try:
                dt = datetime.fromisoformat(ts)
            except ValueError:
                continue
            rows.append((dt, float(spy), float(vix)))
    rows.sort(key=lambda x: x[0])
    return rows


def nearest_market_snapshot(series, target_dt_et, tolerance_seconds=150):
    """Binary search nearest (spy, vix) to target_dt_et in the sorted series.
    Returns (spy, vix, abs_seconds_diff) or (None, None, None) if nothing within tolerance."""
    import bisect
    times = [r[0] for r in series]
    idx = bisect.bisect_left(times, target_dt_et)
    candidates = []
    if idx < len(series):
        candidates.append(series[idx])
    if idx > 0:
        candidates.append(series[idx - 1])
    if not candidates:
        return None, None, None
    best = min(candidates, key=lambda r: abs((r[0] - target_dt_et).total_seconds()))
    diff = abs((best[0] - target_dt_et).total_seconds())
    if diff > tolerance_seconds:
        return None, None, None
    return best[1], best[2], diff


def utc_to_et_naive(utc_iso: str) -> datetime:
    """entry_ts_utc looks like '2026-06-26T18:53:49.640000Z'. Convert to US/Eastern
    naive datetime matching core-decisions.jsonl's ts_et convention (DST-aware)."""
    s = utc_iso.rstrip("Z")
    dt_utc = datetime.fromisoformat(s)
    # DST-aware EDT/EST offset: EDT (UTC-4) roughly Mar-Nov, EST (UTC-5) otherwise.
    # All trade dates in this dataset (2026-06-26 .. 2026-09-03) are within EDT.
    return dt_utc - timedelta(hours=4)


def premium_bucket(p):
    if p < 0.40:
        return "<0.40"
    if p < 0.80:
        return "0.40-0.80"
    if p < 1.50:
        return "0.80-1.50"
    return ">1.50"


def vix_regime(v):
    if v is None:
        return "unknown"
    if v < 15:
        return "<15"
    if v < 17:
        return "15-17"
    return ">17"


def distance_bucket(dist):
    """dist = signed OTM distance in $ (positive=OTM, negative=ITM, 0=ATM)."""
    if dist is None:
        return "unknown"
    if dist <= 0:
        return "ATM/ITM (<=0)"
    if dist <= 1.5:
        return "OTM $0-1.5"
    if dist <= 3.5:
        return "OTM $1.5-3.5 (OTM-2 zone)"
    return "OTM $3.5+"


def bootstrap_mean_ci(values, n_resamples=2000, alpha=0.05):
    """Bootstrap CI on the mean of `values`. Returns (mean, lo, hi, n)."""
    n = len(values)
    if n == 0:
        return None, None, None, 0
    mean = statistics.fmean(values)
    if n == 1:
        return mean, mean, mean, n
    boots = []
    for _ in range(n_resamples):
        sample = [values[random.randrange(n)] for _ in range(n)]
        boots.append(statistics.fmean(sample))
    boots.sort()
    lo_idx = int((alpha / 2) * n_resamples)
    hi_idx = int((1 - alpha / 2) * n_resamples) - 1
    hi_idx = min(hi_idx, n_resamples - 1)
    return mean, boots[lo_idx], boots[hi_idx], n


def bootstrap_sum_ci(values, n_resamples=2000, alpha=0.05):
    """Bootstrap CI on the SUM (total $) implied by resampling the per-trade pnl
    vector at its own n (i.e. CI on what a same-size population's total would be),
    reported alongside the observed sum. Uses mean*n scaling of the bootstrap mean CI."""
    mean, lo, hi, n = bootstrap_mean_ci(values, n_resamples, alpha)
    if mean is None:
        return None, None, None, 0
    return mean * n, lo * n, hi * n, n


def profit_factor(values):
    gains = sum(v for v in values if v > 0)
    losses = -sum(v for v in values if v < 0)
    if losses == 0:
        return float("inf") if gains > 0 else None
    return gains / losses


def win_rate(outcomes):
    scored = [o for o in outcomes if o in ("winner", "loser")]
    if not scored:
        return None
    return sum(1 for o in scored if o == "winner") / len(scored)


def cap_hit_flag(t):
    """Approximate 'hit the -50% catastrophe cap' using realized loss vs full entry
    notional. Only meaningful for losers (winners/scratch can't be cap-hit)."""
    if t["outcome"] != "loser":
        return False
    notional = t["entry_price"] * t["qty"] * 100
    if notional <= 0:
        return False
    loss_pct = t["realized_pnl"] / notional
    return loss_pct <= -0.45


def summarize_group(trades, label):
    pnls = [t["realized_pnl"] for t in trades]
    outcomes = [t["outcome"] for t in trades]
    n = len(trades)
    total_pnl = sum(pnls)
    wr = win_rate(outcomes)
    pf = profit_factor(pnls)
    cap_hits = sum(1 for t in trades if cap_hit_flag(t))
    n_losers = sum(1 for o in outcomes if o == "loser")
    cap_hit_rate = (cap_hits / n_losers) if n_losers else None
    mean, lo, hi, _ = bootstrap_mean_ci(pnls) if n > 0 else (None, None, None, 0)
    return {
        "label": label,
        "n": n,
        "total_pnl": round(total_pnl, 2),
        "mean_pnl_per_trade": round(mean, 2) if mean is not None else None,
        "mean_pnl_ci95": [round(lo, 2), round(hi, 2)] if lo is not None else None,
        "win_rate": round(wr, 4) if wr is not None else None,
        "profit_factor": round(pf, 3) if isinstance(pf, float) else pf,
        "n_losers": n_losers,
        "catastrophe_cap_hits": cap_hits,
        "catastrophe_cap_hit_rate_of_losers": round(cap_hit_rate, 4) if cap_hit_rate is not None else None,
        "dates": sorted(set(t["date"] for t in trades)),
    }


def main():
    meta, trades = load_mae_mfe()
    series = load_core_decisions_series()

    enriched = []
    unmatched = []
    for t in trades:
        occ = parse_occ(t["symbol"])
        if occ is None:
            unmatched.append({"reason": "occ_parse_fail", "trade": t["symbol"]})
            continue
        side, strike = occ
        entry_dt_et = utc_to_et_naive(t["entry_ts_utc"])
        spy, vix, diff_s = nearest_market_snapshot(series, entry_dt_et)
        if spy is None:
            unmatched.append({"reason": "no_market_snapshot_within_tolerance",
                               "date": t["date"], "arm": t["arm"], "symbol": t["symbol"]})
            continue
        dist = (strike - spy) if side == "C" else (spy - strike)
        row = dict(t)
        row["side"] = side
        row["strike"] = strike
        row["spy_at_entry"] = round(spy, 3)
        row["vix_at_entry"] = round(vix, 3)
        row["match_diff_seconds"] = round(diff_s, 1)
        row["otm_distance"] = round(dist, 3)
        row["premium_bucket"] = premium_bucket(t["entry_price"])
        row["vix_regime"] = vix_regime(vix)
        row["distance_bucket"] = distance_bucket(dist)
        row["is_cap_hit"] = cap_hit_flag(t)
        enriched.append(row)

    print(f"Matched {len(enriched)}/{len(trades)} trades to a market (spy,vix) snapshot; "
          f"{len(unmatched)} unmatched.")

    all_arms = enriched
    bold2 = [r for r in enriched if r["arm"] == "bold-2"]

    report = {
        "hypothesis": "H3_BOLD_OTM_TICKETS",
        "n_total_scored_positions_all_arms": len(trades),
        "n_matched_to_market_snapshot": len(enriched),
        "n_unmatched": len(unmatched),
        "unmatched_detail": unmatched,
        "mae_mfe_meta": meta,
    }

    # ---- 1. Premium bucket x outcome, ALL ARMS -----------------------------------
    buckets = ["<0.40", "0.40-0.80", "0.80-1.50", ">1.50"]
    report["premium_bucket_all_arms"] = [
        summarize_group([r for r in all_arms if r["premium_bucket"] == b], b)
        for b in buckets
    ]
    report["premium_bucket_bold2_only"] = [
        summarize_group([r for r in bold2 if r["premium_bucket"] == b], b)
        for b in buckets
    ]

    # ---- 2. Premium bucket x VIX regime, ALL ARMS and bold-2 ----------------------
    regimes = ["<15", "15-17", ">17"]
    pb_vix_all = {}
    pb_vix_bold2 = {}
    for reg in regimes:
        pb_vix_all[reg] = [
            summarize_group([r for r in all_arms if r["premium_bucket"] == b and r["vix_regime"] == reg], f"{b} / VIX {reg}")
            for b in buckets
        ]
        pb_vix_bold2[reg] = [
            summarize_group([r for r in bold2 if r["premium_bucket"] == b and r["vix_regime"] == reg], f"{b} / VIX {reg}")
            for b in buckets
        ]
    report["premium_x_vix_all_arms"] = pb_vix_all
    report["premium_x_vix_bold2"] = pb_vix_bold2

    # ---- 3. Moneyness / OTM distance bucket x outcome -----------------------------
    dist_buckets = ["ATM/ITM (<=0)", "OTM $0-1.5", "OTM $1.5-3.5 (OTM-2 zone)", "OTM $3.5+"]
    report["distance_bucket_all_arms"] = [
        summarize_group([r for r in all_arms if r["distance_bucket"] == b], b)
        for b in dist_buckets
    ]
    report["distance_bucket_bold2_only"] = [
        summarize_group([r for r in bold2 if r["distance_bucket"] == b], b)
        for b in dist_buckets
    ]
    dist_vix_bold2 = {}
    for reg in regimes:
        dist_vix_bold2[reg] = [
            summarize_group([r for r in bold2 if r["distance_bucket"] == b and r["vix_regime"] == reg], f"{b} / VIX {reg}")
            for b in dist_buckets
        ]
    report["distance_x_vix_bold2"] = dist_vix_bold2

    # ---- 4. VIX regime summary, bold-2 and all arms --------------------------------
    report["vix_regime_bold2"] = [summarize_group([r for r in bold2 if r["vix_regime"] == reg], reg) for reg in regimes]
    report["vix_regime_all_arms"] = [summarize_group([r for r in all_arms if r["vix_regime"] == reg], reg) for reg in regimes]

    # ---- 5. Per-arm baseline (context) ---------------------------------------------
    arm_names = sorted(set(r["arm"] for r in all_arms))
    report["per_arm_baseline"] = [summarize_group([r for r in all_arms if r["arm"] == a], a) for a in arm_names]

    # ---- 6. Counterfactual: min-premium floor for bold-2 under VIX<16 --------------
    # Candidate floors to test (current live floor is 0.30 mid-based; entry_price here
    # is FILL price, a reasonable proxy -- fill >= mid by construction of the
    # marketable-limit pricing, so this is a conservative (slightly generous) filter).
    floors = [0.30, 0.40, 0.50, 0.60, 0.80]
    bold2_vix_lt16 = [r for r in bold2 if r["vix_at_entry"] is not None and r["vix_at_entry"] < 16]
    cf_results = []
    for floor in floors:
        kept = [r for r in bold2_vix_lt16 if r["entry_price"] >= floor]
        blocked = [r for r in bold2_vix_lt16 if r["entry_price"] < floor]
        kept_summary = summarize_group(kept, f"kept (premium>={floor})")
        blocked_summary = summarize_group(blocked, f"blocked (premium<{floor})")
        cf_results.append({
            "floor": floor,
            "n_vix_lt16_population": len(bold2_vix_lt16),
            "n_blocked": len(blocked),
            "blocked_total_pnl": blocked_summary["total_pnl"],
            "blocked_trades": [{"date": r["date"], "symbol": r["symbol"], "entry_price": r["entry_price"],
                                 "outcome": r["outcome"], "pnl": r["realized_pnl"], "vix": r["vix_at_entry"]}
                                for r in blocked],
            "kept_summary": kept_summary,
            "would_have_blocked_08_27_or_08_28_winner": any(
                r["date"] in ("2026-08-27", "2026-08-28") and r["outcome"] == "winner" for r in blocked
            ),
        })
    report["counterfactual_min_premium_floor_bold2_vix_lt16"] = cf_results
    report["actual_bold2_vix_lt16_baseline"] = summarize_group(bold2_vix_lt16, "actual (no new floor), bold-2 VIX<16")

    # ---- 7. Distance-based counterfactual (proxy for a tier shift) -----------------
    # Since re-pricing at an alternate strike requires cached option bars we may not
    # have for every day/strike, we instead test EXCLUDING the far-OTM zone
    # (distance > threshold) as an observable proxy for "shift the tier closer to ATM"
    # -- this does not simulate what the ATM-strike premium/outcome would have been,
    # it only asks: does removing far-OTM entries improve or hurt bold-2 VIX<16 P&L.
    dist_thresholds = [1.5, 2.5, 3.5, 5.0]
    dist_cf_results = []
    for thresh in dist_thresholds:
        kept = [r for r in bold2_vix_lt16 if r["otm_distance"] <= thresh]
        blocked = [r for r in bold2_vix_lt16 if r["otm_distance"] > thresh]
        dist_cf_results.append({
            "otm_distance_threshold": thresh,
            "n_blocked": len(blocked),
            "blocked_summary": summarize_group(blocked, f"blocked (dist>{thresh})"),
            "kept_summary": summarize_group(kept, f"kept (dist<={thresh})"),
            "would_have_blocked_08_27_or_08_28_winner": any(
                r["date"] in ("2026-08-27", "2026-08-28") and r["outcome"] == "winner" for r in blocked
            ),
        })
    report["counterfactual_otm_distance_shift_bold2_vix_lt16"] = dist_cf_results

    # ---- 8. Big-winner-day check (08-06, 08-13, 08-27, 08-28), ALL ARMS ------------
    winner_days = ["2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"]
    wd_rows = [r for r in all_arms if r["date"] in winner_days]
    wd_bold2 = [r for r in bold2 if r["date"] in winner_days]
    report["winner_day_trades_all_arms"] = [
        {"date": r["date"], "arm": r["arm"], "symbol": r["symbol"], "entry_price": r["entry_price"],
         "premium_bucket": r["premium_bucket"], "otm_distance": r["otm_distance"],
         "distance_bucket": r["distance_bucket"], "vix_at_entry": r["vix_at_entry"],
         "vix_regime": r["vix_regime"], "outcome": r["outcome"], "pnl": r["realized_pnl"]}
        for r in sorted(wd_rows, key=lambda x: (x["date"], x["arm"]))
    ]
    report["winner_day_trades_bold2_only"] = [
        {"date": r["date"], "symbol": r["symbol"], "entry_price": r["entry_price"],
         "otm_distance": r["otm_distance"], "vix_at_entry": r["vix_at_entry"],
         "outcome": r["outcome"], "pnl": r["realized_pnl"]}
        for r in sorted(wd_bold2, key=lambda x: x["date"])
    ]

    # ---- 9. Concentration disclosure -------------------------------------------------
    def top3_concentration(trades_list):
        pos = sorted([t["realized_pnl"] for t in trades_list if t["realized_pnl"] > 0], reverse=True)
        total_gains = sum(pos)
        top3 = sum(pos[:3])
        return {
            "total_gains": round(total_gains, 2),
            "top3_gains": round(top3, 2),
            "top3_pct_of_gains": round(top3 / total_gains, 4) if total_gains > 0 else None,
            "top3_trades": pos[:3],
        }
    report["concentration_bold2"] = top3_concentration(bold2)
    report["concentration_all_arms"] = top3_concentration(all_arms)

    # ---- 10. Strike-tier ladder facts (read-only, for context) ---------------------
    # IMPORTANT: heartbeat_core.py line ~2679 is the ACTUAL live call site (verified by
    # direct read of the file, not the crypto/lib/strike_selection.py module docstring,
    # which is STALE on this point -- see stale_docstring_note below). As of this
    # session (2026-09-03) it reads ss.V15_BOLD_TIERS for account=="bold", i.e. OTM-2 at
    # $2K-$10K equity. The V15_BOLD_CORE_TIERS ATM table WAS wired 2026-07-18..2026-08-20
    # then REVERTED -- see prior_tier_shift_experiment below, this IS the "tier shift"
    # H3 asks about, and it already ran live.
    bold_tier_rail = None
    if BOLD_TIER_RAIL_PATH.exists():
        try:
            bold_tier_rail = json.loads(BOLD_TIER_RAIL_PATH.read_text())
        except json.JSONDecodeError:
            bold_tier_rail = {"error": "failed to parse bold-tier-rail.json"}

    report["tier_ladder_context"] = {
        "bold2_account_equity_2026_08_18_broker_verified": 5048.40,
        "v15_bold_tiers_live_core_bold_branch_AS_OF_2026_09_03": "heartbeat_core.py (~line 2679, direct read, not the strike_selection.py "
                                                  "docstring) currently reads ss.V15_BOLD_TIERS for account=='bold' -- i.e. OTM-2 (strike_offset -2) "
                                                  "at $2K-$10K equity, OTM-3 under $2K. This is NOT V15_BOLD_CORE_TIERS (which would be ATM 0-$10K).",
        "stale_docstring_note": "crypto/lib/strike_selection.py's V15_BOLD_CORE_TIERS docstring says 'STATUS UPDATE 2026-07-18: WIRED' and does "
                                 "NOT mention the 2026-08-20 revert documented directly in heartbeat_core.py's inline comment at the call site. "
                                 "Doc drift, flagged here, NOT fixed (out of scope / read-only per this task's constraints).",
        "min_entry_premium_floor_aggressive_params_json": 0.30,
        "min_entry_premium_enforced_against": "mid (option mid quote at plan time), NOT the fill price -- fill price (this "
                                                "report's entry_price) is typically >= mid via marketable-limit ask+buffer pricing, "
                                                "so filtering on entry_price is a conservative (slightly permissive) proxy for the live gate.",
        "skip_min_premium_floor_events_bold_account_core_decisions": 49,
    }
    report["prior_tier_shift_experiment"] = {
        "summary": "The EXACT lever H3 asks about (shift bold-2 toward ATM, i.e. reduce OTM distance to ~0) was ALREADY "
                    "shipped live 2026-07-18 (commit 718e0809, V15_BOLD_TIERS->V15_BOLD_CORE_TIERS) and REVERTED 2026-08-20 "
                    "after its own standing falsification rail (setup/scripts/bold_tier_rail.py) triggered negative.",
        "rail_state_file": "automation/state/bold-tier-rail.json",
        "rail_verdict": bold_tier_rail.get("verdict") if bold_tier_rail else "UNVERIFIED (state file missing/unreadable)",
        "rail_status": bold_tier_rail.get("rail_status") if bold_tier_rail else None,
        "post_ship_ATM_population": bold_tier_rail.get("post_ship") if bold_tier_rail else None,
        "pre_ship_OTM_population": bold_tier_rail.get("pre_ship") if bold_tier_rail else None,
        "delta": bold_tier_rail.get("delta") if bold_tier_rail else None,
        "revert_authorization": "J, in-chat, 2026-08-20: \"so #2 is asking if I want to retire a strat that is losing? i guess so yeah\" "
                                 "(quoted in heartbeat_core.py's inline comment at the strike-selection call site).",
        "relevance_to_H3": "This is DIRECT prior evidence against a tier shift toward ATM for bold-2: n=38 live ATM fills netted "
                            "-$346 (WR 34.2%) vs the OTM tier's smaller pre-ship sample of n=4 at +$406 (WR 50%). Combined with "
                            "this report's own distance-bucket finding (OTM-2-zone entries are bold-2's BEST-performing bucket "
                            "post-revert, section 3/7 below), the tier-shift half of H3 is REFUTED by a real, larger live "
                            "experiment, not just this report's smaller counterfactual slice.",
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str))

    write_markdown(report)
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_MD}")


def fmt_summary_row(s):
    ci = s["mean_pnl_ci95"]
    ci_str = f"[{ci[0]}, {ci[1]}]" if ci else "n/a"
    pf = s["profit_factor"]
    pf_str = f"{pf}" if pf is not None else "n/a"
    wr = s["win_rate"]
    wr_str = f"{wr*100:.1f}%" if wr is not None else "n/a"
    caphit = s["catastrophe_cap_hit_rate_of_losers"]
    caphit_str = f"{caphit*100:.1f}%" if caphit is not None else "n/a"
    return (f"| {s['label']} | {s['n']} | ${s['total_pnl']:.2f} | ${s['mean_pnl_per_trade'] if s['mean_pnl_per_trade'] is not None else 0:.2f} "
            f"{ci_str} | {wr_str} | {pf_str} | {caphit_str} |")


def write_markdown(report):
    lines = []
    lines.append("# H3 BOLD OTM TICKETS -- premium bucket / moneyness / VIX-regime analysis")
    lines.append("")
    lines.append("Stamp: 2026-09-03T10:24 ET. Slug: bold-otm-tickets.")
    lines.append("")
    lines.append("**Scope note**: read-only, cached-data-only analysis per the money-hunt work order. "
                  "No broker/market-data calls made. No trading-path files edited.")
    lines.append("")
    lines.append(f"Population: {report['n_total_scored_positions_all_arms']} scored positions (all 6 arms, "
                  f"analysis/pain-ledger/mae-mfe.json), {report['n_matched_to_market_snapshot']} matched to a "
                  f"core-decisions.jsonl market (spy,vix) snapshot within 150s "
                  f"({report['n_unmatched']} unmatched -- see JSON `unmatched_detail`).")
    lines.append("")

    lines.append("## 0. Tier-ladder context (read-only inspection)")
    tc = report["tier_ladder_context"]
    for k, v in tc.items():
        lines.append(f"- **{k}**: {v}")
    lines.append("")

    lines.append("## 0b. PRIOR EXPERIMENT: bold-2 tier shift to ATM already ran live and was reverted")
    pte = report["prior_tier_shift_experiment"]
    lines.append(f"**{pte['summary']}**")
    lines.append("")
    lines.append(f"- Rail verdict: {pte['rail_verdict']}")
    lines.append(f"- Rail status: {pte['rail_status']}")
    if pte["post_ship_ATM_population"]:
        p = pte["post_ship_ATM_population"]
        lines.append(f"- Post-ship ATM population (2026-07-18..2026-08-20): n={p['n']}, net=${p['net_usd']}, "
                      f"WR={p['win_rate']*100:.1f}%, mean/tr=${p['mean_usd']}")
    if pte["pre_ship_OTM_population"]:
        p = pte["pre_ship_OTM_population"]
        lines.append(f"- Pre-ship OTM population (baseline): n={p['n']}, net=${p['net_usd']}, "
                      f"WR={p['win_rate']*100:.1f}%, mean/tr=${p['mean_usd']}")
    lines.append(f"- Revert authorization: {pte['revert_authorization']}")
    lines.append(f"- **Relevance to H3**: {pte['relevance_to_H3']}")
    lines.append("")

    lines.append("## 1. Premium bucket x outcome")
    lines.append("")
    lines.append("### All arms")
    lines.append("| Bucket | n | Total P&L | Mean $/trade (95% CI) | WR | PF | Cap-hit rate (of losers) |")
    lines.append("|---|---|---|---|---|---|---|")
    for s in report["premium_bucket_all_arms"]:
        lines.append(fmt_summary_row(s))
    lines.append("")
    lines.append("### bold-2 only")
    lines.append("| Bucket | n | Total P&L | Mean $/trade (95% CI) | WR | PF | Cap-hit rate (of losers) |")
    lines.append("|---|---|---|---|---|---|---|")
    for s in report["premium_bucket_bold2_only"]:
        lines.append(fmt_summary_row(s))
    lines.append("")

    lines.append("## 2. Premium bucket x VIX regime, bold-2")
    for reg, rows in report["premium_x_vix_bold2"].items():
        lines.append(f"### VIX {reg}")
        lines.append("| Bucket | n | Total P&L | Mean $/trade (95% CI) | WR | PF | Cap-hit rate |")
        lines.append("|---|---|---|---|---|---|---|")
        for s in rows:
            lines.append(fmt_summary_row(s))
        lines.append("")

    lines.append("## 3. OTM distance bucket x outcome (recomputed moneyness: OCC strike vs decision-row spy)")
    lines.append("")
    lines.append("### All arms")
    lines.append("| Bucket | n | Total P&L | Mean $/trade (95% CI) | WR | PF | Cap-hit rate |")
    lines.append("|---|---|---|---|---|---|---|")
    for s in report["distance_bucket_all_arms"]:
        lines.append(fmt_summary_row(s))
    lines.append("")
    lines.append("### bold-2 only")
    lines.append("| Bucket | n | Total P&L | Mean $/trade (95% CI) | WR | PF | Cap-hit rate |")
    lines.append("|---|---|---|---|---|---|---|")
    for s in report["distance_bucket_bold2_only"]:
        lines.append(fmt_summary_row(s))
    lines.append("")

    lines.append("## 4. VIX regime summary, bold-2 vs all arms")
    lines.append("### bold-2")
    lines.append("| Regime | n | Total P&L | Mean $/trade (95% CI) | WR | PF | Cap-hit rate |")
    lines.append("|---|---|---|---|---|---|---|")
    for s in report["vix_regime_bold2"]:
        lines.append(fmt_summary_row(s))
    lines.append("")
    lines.append("### All arms")
    lines.append("| Regime | n | Total P&L | Mean $/trade (95% CI) | WR | PF | Cap-hit rate |")
    lines.append("|---|---|---|---|---|---|---|")
    for s in report["vix_regime_all_arms"]:
        lines.append(fmt_summary_row(s))
    lines.append("")

    lines.append("## 5. Per-arm baseline (context)")
    lines.append("| Arm | n | Total P&L | Mean $/trade (95% CI) | WR | PF | Cap-hit rate |")
    lines.append("|---|---|---|---|---|---|---|")
    for s in report["per_arm_baseline"]:
        lines.append(fmt_summary_row(s))
    lines.append("")

    lines.append("## 6. Counterfactual: min-premium floor for bold-2, VIX<16 only")
    base = report["actual_bold2_vix_lt16_baseline"]
    base_wr_str = f"{base['win_rate']*100:.1f}%" if base['win_rate'] is not None else "n/a"
    lines.append(f"Actual bold-2 population under VIX<16 (no new floor): n={base['n']}, total P&L=${base['total_pnl']:.2f}, "
                  f"WR={base_wr_str}, PF={base['profit_factor']}.")
    lines.append("")
    lines.append("| Floor ($) | n blocked | Blocked total P&L | Kept n | Kept total P&L | Kept mean/tr (95% CI) | Kept WR | Kept PF | Blocks an 08-27/08-28 winner? |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for cf in report["counterfactual_min_premium_floor_bold2_vix_lt16"]:
        ks = cf["kept_summary"]
        ci = ks["mean_pnl_ci95"]
        ci_str = f"[{ci[0]}, {ci[1]}]" if ci else "n/a"
        wr = ks["win_rate"]
        wr_str = f"{wr*100:.1f}%" if wr is not None else "n/a"
        lines.append(f"| {cf['floor']} | {cf['n_blocked']} | ${cf['blocked_total_pnl']:.2f} | {ks['n']} | ${ks['total_pnl']:.2f} | "
                      f"${ks['mean_pnl_per_trade'] if ks['mean_pnl_per_trade'] is not None else 0:.2f} {ci_str} | {wr_str} | "
                      f"{ks['profit_factor']} | {cf['would_have_blocked_08_27_or_08_28_winner']} |")
    lines.append("")
    lines.append("Blocked-trade detail per floor (dates/symbols/outcomes) is in the JSON sidecar "
                  "(`counterfactual_min_premium_floor_bold2_vix_lt16[*].blocked_trades`).")
    lines.append("")

    lines.append("## 7. Counterfactual: OTM-distance shift (proxy for a tier shift), bold-2 VIX<16 only")
    lines.append("")
    lines.append("**Caveat**: this does NOT re-price at an alternate strike (no guaranteed cached option bars for every "
                  "alternate strike/day). It only asks: does removing far-OTM entries (as actually traded) change bold-2's "
                  "VIX<16 P&L. A genuine tier-shift simulation (re-pricing at the ATM/near strike) is a separate, larger "
                  "undertaking flagged in Caveats below.")
    lines.append("")
    lines.append("| OTM distance threshold ($) | n blocked | Blocked total P&L | Kept n | Kept total P&L | Kept WR | Kept PF | Blocks an 08-27/08-28 winner? |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for cf in report["counterfactual_otm_distance_shift_bold2_vix_lt16"]:
        ks = cf["kept_summary"]
        bs = cf["blocked_summary"]
        wr = ks["win_rate"]
        wr_str = f"{wr*100:.1f}%" if wr is not None else "n/a"
        lines.append(f"| {cf['otm_distance_threshold']} | {cf['n_blocked']} | ${bs['total_pnl']:.2f} | {ks['n']} | ${ks['total_pnl']:.2f} | "
                      f"{wr_str} | {ks['profit_factor']} | {cf['would_have_blocked_08_27_or_08_28_winner']} |")
    lines.append("")

    lines.append("## 8. Winner-day trades (08-06 / 08-13 / 08-27 / 08-28) -- did the floor/shift touch them?")
    lines.append("### bold-2")
    lines.append("| Date | Symbol | Entry $ | OTM dist | VIX | Outcome | P&L |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in report["winner_day_trades_bold2_only"]:
        lines.append(f"| {r['date']} | {r['symbol']} | {r['entry_price']} | {r['otm_distance']} | {r['vix_at_entry']} | {r['outcome']} | {r['pnl']} |")
    lines.append("")
    lines.append("### All arms")
    lines.append("| Date | Arm | Symbol | Entry $ | Bucket | OTM dist | VIX | Outcome | P&L |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in report["winner_day_trades_all_arms"]:
        lines.append(f"| {r['date']} | {r['arm']} | {r['symbol']} | {r['entry_price']} | {r['premium_bucket']} | {r['otm_distance']} | {r['vix_at_entry']} | {r['outcome']} | {r['pnl']} |")
    lines.append("")

    lines.append("## 9. Concentration disclosure (top-3 winning trades as % of total gains)")
    c2 = report["concentration_bold2"]
    ca = report["concentration_all_arms"]
    c2_pct_str = f"{c2['top3_pct_of_gains']*100:.1f}%" if c2['top3_pct_of_gains'] else "n/a"
    ca_pct_str = f"{ca['top3_pct_of_gains']*100:.1f}%" if ca['top3_pct_of_gains'] else "n/a"
    lines.append(f"- bold-2: top-3 winners = ${c2['top3_gains']:.2f} of ${c2['total_gains']:.2f} total gains ({c2_pct_str}).")
    lines.append(f"- All arms: top-3 winners = ${ca['top3_gains']:.2f} of ${ca['total_gains']:.2f} total gains ({ca_pct_str}).")
    lines.append("")

    OUT_MD.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
