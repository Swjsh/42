#!/usr/bin/env python
"""money_verify_range_extreme_dead_2.py -- REPRODUCTION-lens independent verification of
H2 DEAD COMPONENT (range-extreme-dead.md / .json, 2026-09-03).

Does NOT import conviction.py, conviction_shadow_report.py, or fills_fifo.py. Re-parses
the 5 raw decision ledgers and the raw fills-ledger.jsonl directly, and reimplements:
  - the post-fix partition (own copy of the FIX_BOUNDARY_ET timestamp, independently
    re-verified against `git log/show 974ca235` in this same session)
  - the range_position / range_extreme empirical distribution by side
  - a FIFO round-trip miner over fills-ledger.jsonl (own implementation, not fills_fifo.py)
  - the +/-120s greedy one-to-one join of conviction rows to real round trips
  - the counterfactual polarity-flip re-score and its bootstrap CI

READ-ONLY. No writes outside analysis/deep-research/2026-09-03-money/ and this file's own
directory. No network, no broker.

Run:
    python backtest/tools/money_verify_range_extreme_dead_2.py
"""
from __future__ import annotations

import glob
import json
import random
import statistics
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
FILLS_LEDGER = STATE / "fills-ledger.jsonl"

# Independently re-derived from `git log --format='%h %ad %s' --date=iso-strict -1 974ca235`
# run in this session: "2026-08-14T17:15:22-06:00" (box is Mountain, UTC-6 in Aug, no DST
# switch mid-August) -> ET (UTC-4 in Aug) = -06:00 + 2h = 17:15:22 + 2:00 = 19:15:22 ET.
FIX_BOUNDARY_ET = "2026-08-14T19:15:22"
REPORT_MAX_DATE = "2026-09-02"  # the date the shadow report (generated 09-02T16:33:44) covers

RANGE_EXTREME_PCT = 0.30  # copied as a LITERAL from conviction.py:97 for independence --
                          # cross-checked against the source file's own constant below.


def _sanity_check_constant() -> None:
    """Confirm the literal above still matches conviction.py's own constant (don't silently
    drift if someone retunes it) -- read as TEXT, not imported, to stay independent."""
    src = (REPO / "setup" / "scripts" / "conviction.py").read_text(encoding="utf-8")
    assert "RANGE_EXTREME_PCT = 0.30" in src, \
        "conviction.py's RANGE_EXTREME_PCT no longer matches this script's hardcoded 0.30"


def ledger_paths() -> list[Path]:
    paths = [STATE / "core-decisions.jsonl"]
    paths += [Path(p) for p in sorted(glob.glob(str(STATE / "fleet" / "*" / "decisions.jsonl")))]
    return [p for p in paths if p.exists()]


def load_conviction_rows() -> list[dict]:
    """Every row on disk carrying a top-level `conviction` dict (v0, NOT variant_tl)."""
    out = []
    for path in ledger_paths():
        arm = "core" if path.name == "core-decisions.jsonl" else path.parent.name
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"conviction"' not in line:
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                cv = row.get("conviction")
                if not isinstance(cv, dict):
                    continue
                ts = row.get("ts_et")
                if not isinstance(ts, str) or len(ts) < 10:
                    continue
                out.append({
                    "arm": arm, "ts_et": ts, "date": ts[:10],
                    "account": row.get("account"), "side": row.get("side"),
                    "setup": row.get("setup"), "conviction": cv,
                })
    out.sort(key=lambda r: r["ts_et"])
    return out


def is_post_fix(row: dict) -> bool:
    return row["ts_et"] >= FIX_BOUNDARY_ET


# ---------------------------------------------------------------------------------------
# Independent FIFO round-trip miner (own implementation, not fills_fifo.mine_real_arm_fills)
# ---------------------------------------------------------------------------------------
_CORE_ACCOUNT_TO_ARM = {"safe": "safe-2", "bold": "bold-2"}


def mine_round_trips(arm_id: str) -> list[dict]:
    if not FILLS_LEDGER.exists():
        return []
    by_symbol: dict[str, list[dict]] = {}
    with FILLS_LEDGER.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("arm") != arm_id or row.get("attribution") != "engine":
                continue
            if not row.get("is_option"):
                continue
            by_symbol.setdefault(row["symbol"], []).append(row)

    trips = []
    for symbol, legs in by_symbol.items():
        legs = sorted(legs, key=lambda r: r["ts_et"])
        open_qty = 0.0
        buy_notional = 0.0
        buy_qty = 0.0
        sell_notional = 0.0
        sell_qty = 0.0
        entry_ts = None
        last_sell_ts = None
        for leg in legs:
            q = float(leg.get("qty") or 0.0)
            px = float(leg.get("price") or 0.0)
            mult = float(leg.get("multiplier") or 100)
            if leg.get("side") == "buy":
                if open_qty <= 1e-9:
                    entry_ts = leg["ts_et"]
                    buy_notional, buy_qty = 0.0, 0.0
                    sell_notional, sell_qty = 0.0, 0.0
                open_qty += q
                buy_notional += q * px * mult
                buy_qty += q
            elif leg.get("side") == "sell":
                if open_qty <= 1e-9:
                    continue
                open_qty -= q
                sell_notional += q * px * mult
                sell_qty += q
                last_sell_ts = leg["ts_et"]
                if abs(open_qty) > 1e-6:
                    continue
                real_pnl = round(sell_notional - buy_notional, 2)
                trips.append({
                    "date": legs[0]["date_et"], "symbol": symbol,
                    "entry_ts_et": entry_ts, "exit_ts_et": last_sell_ts,
                    "real_pnl": real_pnl,
                })
    return sorted(trips, key=lambda r: r["entry_ts_et"])


def join_to_fills(rows: list[dict]) -> int:
    """+/-120s greedy one-to-one join, own implementation. Attaches real_pnl in place."""
    by_arm: dict[str, list[dict]] = {}
    for arm in set(_CORE_ACCOUNT_TO_ARM.values()):
        by_arm[arm] = mine_round_trips(arm)

    def parse(ts):
        try:
            return datetime.fromisoformat(ts[:19])
        except (ValueError, TypeError):
            return None

    candidates = []
    for idx, row in enumerate(rows):
        arm = _CORE_ACCOUNT_TO_ARM.get(str(row.get("account")))
        t = parse(row["ts_et"])
        if not arm or t is None:
            continue
        for rid, rt in enumerate(by_arm.get(arm, [])):
            if rt["date"] != row["date"]:
                continue
            et = parse(rt["entry_ts_et"])
            if et is None:
                continue
            gap = abs((et - t).total_seconds())
            if gap <= 120:
                candidates.append((gap, idx, arm, rid, rt["real_pnl"]))
    candidates.sort(key=lambda c: c[0])
    used_rows, used_rts, joined = set(), set(), 0
    for gap, idx, arm, rid, pnl in candidates:
        if idx in used_rows or (arm, rid) in used_rts:
            continue
        rows[idx]["real_pnl"] = pnl
        used_rows.add(idx)
        used_rts.add((arm, rid))
        joined += 1
    return joined


def bootstrap_ci(vals: list[float], n_resamples: int = 5000, seed: int = 42) -> tuple[float, float]:
    if not vals:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    means = []
    n = len(vals)
    for _ in range(n_resamples):
        sample = [vals[rng.randrange(n)] for _ in range(n)]
        means.append(statistics.mean(sample))
    means.sort()
    lo_idx = int(0.025 * n_resamples)
    hi_idx = int(0.975 * n_resamples) - 1
    return (round(means[lo_idx], 2), round(means[hi_idx], 2))


def main() -> None:
    _sanity_check_constant()

    all_rows = load_conviction_rows()
    post_all = [r for r in all_rows if is_post_fix(r)]
    post_482 = [r for r in post_all if r["date"] <= REPORT_MAX_DATE]

    result: dict = {"_meta": {
        "script": "backtest/tools/money_verify_range_extreme_dead_2.py",
        "independent_of": ["conviction.py", "conviction_shadow_report.py", "fills_fifo.py"],
        "fix_boundary_et_used": FIX_BOUNDARY_ET,
        "n_all_ledger_rows_with_conviction": len(all_rows),
        "n_post_fix_all_dates": len(post_all),
        "n_post_fix_through_2026_09_02": len(post_482),
    }}

    # --- 1. n reproduction ---------------------------------------------------------------
    result["n_check"] = {
        "claimed_n": 482,
        "reproduced_n_report_matched": len(post_482),
        "match": len(post_482) == 482,
    }

    # --- 2. fleet ledger check -------------------------------------------------------------
    by_arm_counts = {}
    for r in all_rows:
        by_arm_counts[r["arm"]] = by_arm_counts.get(r["arm"], 0) + 1
    result["fleet_conviction_row_counts"] = by_arm_counts
    result["fleet_check"] = {
        "claim": "0 conviction rows in all 4 fleet ledgers",
        "reproduced": {a: by_arm_counts.get(a, 0) for a in ("risky-1", "risky-3", "safe-1", "safe-3")},
        "match": all(by_arm_counts.get(a, 0) == 0 for a in ("risky-1", "risky-3", "safe-1", "safe-3")),
    }

    # --- 3. range_extreme hit rate + degraded count (report-matched population, top-level v0) --
    n_re_true = sum(1 for r in post_482 if r["conviction"].get("components", {}).get("range_extreme"))
    n_re_degraded = sum(1 for r in post_482 if "range_extreme" in (r["conviction"].get("degraded_components") or []))
    result["range_extreme_hit_rate"] = {
        "claimed_hit_rate_pct": 0.0,
        "n": len(post_482),
        "n_range_extreme_true": n_re_true,
        "n_range_extreme_degraded": n_re_degraded,
        "reproduced_hit_rate_pct": round(100.0 * n_re_true / len(post_482), 2) if post_482 else None,
        "match": n_re_true == 0,
    }

    # --- 4. by-side pos distribution + setup homogeneity ------------------------------------
    by_side_pos = {"C": [], "P": []}
    by_side_setup = {"C": set(), "P": set()}
    for r in post_482:
        cv = r["conviction"]
        comp = cv.get("components", {})
        side = r.get("side")
        if side not in ("C", "P"):
            continue
        if "range_extreme" in (cv.get("degraded_components") or []):
            continue
        pos = comp.get("range_position")
        if pos is None:
            continue
        by_side_pos[side].append(pos)
        by_side_setup[side].add(r.get("setup"))

    side_stats = {}
    for side, vals in by_side_pos.items():
        if not vals:
            side_stats[side] = {"n": 0}
            continue
        if side == "P":
            hits_current = sum(1 for x in vals if x >= (1.0 - RANGE_EXTREME_PCT))
            hits_flipped = sum(1 for x in vals if x <= RANGE_EXTREME_PCT)
        else:
            hits_current = sum(1 for x in vals if x <= RANGE_EXTREME_PCT)
            hits_flipped = sum(1 for x in vals if x >= (1.0 - RANGE_EXTREME_PCT))
        side_stats[side] = {
            "n": len(vals), "min": round(min(vals), 3), "max": round(max(vals), 3),
            "mean": round(statistics.mean(vals), 3),
            "hits_under_current_rule": hits_current,
            "hits_under_flipped_rule": hits_flipped,
            "setups_seen": sorted(x for x in by_side_setup[side] if x is not None),
            "setup_homogeneous": len(by_side_setup[side]) == 1,
        }
    result["by_side_distribution"] = side_stats
    result["by_side_claim_check"] = {
        "claimed_call_n": 270, "claimed_call_mean": 0.812,
        "claimed_put_n": 242, "claimed_put_mean": 0.138,
        "reproduced_call_n": side_stats.get("C", {}).get("n"),
        "reproduced_call_mean": side_stats.get("C", {}).get("mean"),
        "reproduced_put_n": side_stats.get("P", {}).get("n"),
        "reproduced_put_mean": side_stats.get("P", {}).get("mean"),
    }

    # --- 5. counterfactual polarity flip + would_block flips --------------------------------
    joined = join_to_fills(post_482)
    flips_block_to_allow = 0
    flips_other = 0
    newly_allowed = []  # (ts_et, account, side, pnl, pos, orig_total, floor)
    for r in post_482:
        cv = r["conviction"]
        comp = cv.get("components", {})
        side = r.get("side")
        total = cv.get("total")
        floor_eff = cv.get("floor_effective")
        if total is None or floor_eff is None or side not in ("C", "P"):
            continue
        if "range_extreme" in (cv.get("degraded_components") or []):
            continue
        pos = comp.get("range_position")
        if pos is None:
            continue
        orig_re = int(comp.get("range_extreme") or 0)
        if side == "P":
            fixed_re = 1 if pos <= RANGE_EXTREME_PCT else 0
        else:
            fixed_re = 1 if pos >= (1.0 - RANGE_EXTREME_PCT) else 0
        new_total = total - orig_re + fixed_re
        orig_block = bool(cv.get("would_block"))
        new_block = bool(new_total < floor_eff)
        if orig_block and not new_block:
            flips_block_to_allow += 1
            pnl = r.get("real_pnl")
            if pnl is not None:
                newly_allowed.append({
                    "ts_et": r["ts_et"], "account": r.get("account"), "side": side,
                    "pnl": pnl, "pos": pos, "orig_total": total, "floor": floor_eff,
                })
        elif (not orig_block) and new_block:
            flips_other += 1

    pnls = [x["pnl"] for x in newly_allowed]
    ci_lo, ci_hi = bootstrap_ci(pnls, n_resamples=5000, seed=42)
    result["counterfactual_flip"] = {
        "n_joined_to_real_fill_total_population": joined,
        "would_block_flips_to_allow": flips_block_to_allow,
        "would_allow_flips_to_block": flips_other,
        "claimed_flips_block_to_allow": 47,
        "claimed_flips_other": 0,
        "match_flip_count": flips_block_to_allow == 47 and flips_other == 0,
        "newly_allowed_joined_to_fills": newly_allowed,
        "n_newly_allowed_joined": len(newly_allowed),
        "sum_pnl": round(sum(pnls), 2) if pnls else 0.0,
        "mean_pnl": round(statistics.mean(pnls), 2) if pnls else None,
        "win_rate_pct": round(100.0 * sum(1 for p in pnls if p > 0) / len(pnls), 1) if pnls else None,
        "bootstrap_ci_95_mean": [ci_lo, ci_hi],
        "claimed": {"n": 5, "sum": -148, "mean": -29.60, "wr_pct": 20,
                    "ci": [-93.00, 66.40]},
    }

    print(json.dumps(result, indent=2, default=str))

    out_path = REPO / "analysis" / "deep-research" / "2026-09-03-money" / "verify-range-extreme-dead-2.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
