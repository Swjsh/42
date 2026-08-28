"""OP-11 A/B battery for the per-arm DAILY PREMIUM BUDGET rule.

QUESTION
--------
Does capping the total option premium an arm may DEPLOY in one session improve
the book, and does it clear the OP-11 auto-ratify bar?

TWO VARIANTS ARE TESTED
-----------------------
A  FLAT       -- the cap applies from the session's first entry.
C  LOSS-ARMED -- the arm is UNCONSTRAINED until it books a losing exit today;
                 the cap engages only after the market has already said no.

C is the candidate. A is kept as the comparison arm because it is the obvious
rule and it FAILS the anchor gate: a flat cap trims size on winning trend days,
which is exactly where the right-tail edge lives. C targets the actual failure
mode -- re-deploying into a session that is already red -- and leaves winning
days alone. 48% of all historical entries were placed while that arm was ALREADY
red on the day; that is the population C acts on.

WHY THIS IS A SUBTRACTIVE OVERLAY (and why that matters for validity)
---------------------------------------------------------------------
The policy only ever REMOVES entries from the realized tape -- it never adds an
entry, never resizes one, never moves a fill price. So no counterfactual price
path is required: each surviving entry keeps its own broker-truth realized P&L.
That is a much weaker assumption than a re-simulation, and it is the reason this
battery runs on `automation/state/pnl-statement.json` (T1 broker-truth round
trips) rather than on the simulator.

DISCLOSED LIMITS (C4)
---------------------
* Removing an entry would in reality free settled cash / change equity, which
  could change a LATER entry's qty. Not modelled -- sizing is held as-traded.
* Paper fills. n = 42 trading days, 5 active arms. Small; do not over-read.
* Fees modelled per `analysis/recommendations/A1-cost-rebuild-2026-08-28.json`
  rates (OCC/ORF/TAF/SEC). Every number below is net of them.
* Walk-forward on 42 days is weak by construction. Folds are held to a 5-day
  minimum so a fold is at least a trading week, but n_folds stays small --
  treat WF here as corroborating, not decisive.

PRIOR COVERAGE (Obsidian-brain check, done BEFORE this file existed)
--------------------------------------------------------------------
* B3-loss-anatomy-2026-08-28   -- observed deployed premium per trade, worst
                                  days, bounded-config table (max_entries_per_day).
* B3-bounded-config-2026-08-28 -- 20k Monte Carlo over ticket x max_entries_day.
* A1-cost-rebuild-2026-08-28   -- the fee model reused here.
This battery is the piece those three imply but none of them ran: a policy
overlay on the REALIZED tape with the OP-11 gate applied.

OUTPUT
------
analysis/recommendations/daily-premium-budget.json
"""

from __future__ import annotations

import json
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from backtest.lib.anchor_check import anchor_no_regression  # noqa: E402

PNL_STATEMENT = REPO / "automation" / "state" / "pnl-statement.json"
OUT = REPO / "analysis" / "recommendations" / "daily-premium-budget.json"

# Fee rates -- verbatim from A1-cost-rebuild-2026-08-28.json `rates_used`.
OCC_PER_CONTRACT = 0.025
ORF_PER_CONTRACT = 0.015
TAF_PER_CONTRACT_SELL = 0.00329
SEC_RATE_PER_DOLLAR_SELL = 2.06e-05

CAP_GRID = [400, 500, 600, 700, 800, 1000, 1200, 1500, 2000, 3000]
IS_FRACTION = 0.60
WF_MAX_FOLDS = 4
MIN_WF_FOLD_DAYS = 5
ANCHOR_TOLERANCE_PCT = 0.10

ExitIndex = dict  # {(arm, date): [(exit_ts_et, net_pnl), ...]}


# --------------------------------------------------------------------------
# load
# --------------------------------------------------------------------------
def _round_trip_fee(rt: dict) -> float:
    """Regulatory fees for one round trip (both legs), per the A1 model."""
    qty = float(rt["qty"])
    proceeds = float(rt["exit_price"]) * qty * 100.0
    return (
        qty * (OCC_PER_CONTRACT + ORF_PER_CONTRACT) * 2.0
        + qty * TAF_PER_CONTRACT_SELL
        + proceeds * SEC_RATE_PER_DOLLAR_SELL
    )


def _spy_round_trips() -> list[dict]:
    statement = json.loads(PNL_STATEMENT.read_text(encoding="utf-8"))
    return [
        rt
        for rt in statement["round_trips"]
        # crypto-twin rows share this tape; they are not this rule's scope
        if rt["symbol"].startswith("SPY") and float(rt["qty"]) > 0
    ]


def load_exits() -> ExitIndex:
    """Realized exits indexed by (arm, date), each (exit_ts_et, net_pnl).

    Answers "was this arm already red when it placed this entry?" using ONLY
    exits that closed strictly BEFORE the entry timestamp -- causal, and
    knowable live from the fills ledger.
    """
    out: ExitIndex = defaultdict(list)
    for rt in _spy_round_trips():
        out[(rt["arm"], rt["date_et"])].append(
            (rt["exit_ts_et"], float(rt["pnl"]) - _round_trip_fee(rt))
        )
    for v in out.values():
        v.sort()
    return out


def load_entries() -> list[dict]:
    """Collapse broker round trips into ENTRIES (one buy -> N partial exits).

    The budget is spent at ENTRY time, so the entry -- not the round trip -- is
    the unit the policy acts on.
    """
    by_entry: dict[str, dict] = {}
    for rt in _spy_round_trips():
        e = by_entry.setdefault(
            rt["entry_activity_id"],
            {
                "arm": rt["arm"],
                "date": rt["date_et"],
                "ts": rt["entry_ts_et"],
                "entry_price": float(rt["entry_price"]),
                "qty": 0.0,
                "gross_pnl": 0.0,
                "fees": 0.0,
            },
        )
        e["qty"] += float(rt["qty"])
        e["gross_pnl"] += float(rt["pnl"])
        e["fees"] += _round_trip_fee(rt)

    entries = sorted(by_entry.values(), key=lambda e: e["ts"])
    for e in entries:
        e["cost"] = e["entry_price"] * e["qty"] * 100.0
        e["net"] = e["gross_pnl"] - e["fees"]
    return entries


def realized_before(exits: ExitIndex, arm: str, date: str, ts: str) -> float:
    """Net realized P&L for `arm` on `date` from exits strictly before `ts`."""
    return sum(p for (x_ts, p) in exits.get((arm, date), []) if x_ts < ts)


# --------------------------------------------------------------------------
# the policy
# --------------------------------------------------------------------------
def apply_budget(
    entries: list[dict],
    cap: float | None,
    days: set[str] | None = None,
    *,
    loss_armed: bool = False,
    exits: ExitIndex | None = None,
) -> dict:
    """Chronological and causal.

    An entry is skipped when the arm's premium already deployed this session,
    plus this entry's premium, exceeds `cap`. Under `loss_armed` the cap only
    binds once the arm is already red on the day. Both quantities are knowable
    at decision time, which is what makes the rule implementable live.
    """
    spent: dict[tuple[str, str], float] = defaultdict(float)
    taken, deployed, net = 0, 0.0, 0.0
    per_day: dict[str, float] = defaultdict(float)
    per_arm_day: dict[tuple[str, str], float] = defaultdict(float)

    for e in entries:
        if days is not None and e["date"] not in days:
            continue
        key = (e["date"], e["arm"])
        armed = True
        if loss_armed:
            armed = realized_before(exits or {}, e["arm"], e["date"], e["ts"]) < 0
        if armed and cap is not None and spent[key] + e["cost"] > cap:
            continue
        spent[key] += e["cost"]
        taken += 1
        deployed += e["cost"]
        net += e["net"]
        per_day[e["date"]] += e["net"]
        per_arm_day[key] += e["net"]

    day_keys = sorted(days) if days is not None else sorted({e["date"] for e in entries})
    day_series = [per_day.get(d, 0.0) for d in day_keys]
    equity = peak = max_dd = 0.0
    for v in day_series:
        equity += v
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    wins = sum(v for v in per_arm_day.values() if v > 0)
    losses = -sum(v for v in per_arm_day.values() if v < 0)

    return {
        "entries_taken": taken,
        "deployed": round(deployed, 2),
        "net_pnl": round(net, 2),
        "roi_pct": round(100.0 * net / deployed, 4) if deployed else 0.0,
        "max_drawdown": round(max_dd, 2),
        "profit_factor": round(wins / losses, 4) if losses else None,
        "worst_day": round(min(day_series), 2) if day_series else 0.0,
        "best_day": round(max(day_series), 2) if day_series else 0.0,
        "green_day_pct": round(100.0 * sum(1 for v in day_series if v > 0) / len(day_series), 1)
        if day_series
        else 0.0,
        "arm_days": len(per_arm_day),
        "arm_days_ge_100": sum(1 for v in per_arm_day.values() if v >= 100),
    }


def _best_cap(
    entries: list[dict], days: set[str], *, loss_armed: bool, exits: ExitIndex
) -> tuple[float, float]:
    """Pick the cap maximising net P&L on the given (in-sample) days."""
    base = apply_budget(entries, None, days)["net_pnl"]
    best_cap, best_benefit = CAP_GRID[0], float("-inf")
    for cap in CAP_GRID:
        benefit = (
            apply_budget(entries, cap, days, loss_armed=loss_armed, exits=exits)["net_pnl"] - base
        )
        if benefit > best_benefit:
            best_cap, best_benefit = cap, benefit
    return best_cap, best_benefit


# --------------------------------------------------------------------------
# battery
# --------------------------------------------------------------------------
def evaluate_variant(
    name: str,
    label: str,
    entries: list[dict],
    exits: ExitIndex,
    days: list[str],
    *,
    loss_armed: bool,
) -> dict[str, Any]:
    """Run the full OP-11 battery for one policy variant."""
    n_days = len(days)
    baseline = apply_budget(entries, None)

    def run(cap: float | None, sub: set[str] | None = None) -> dict:
        return apply_budget(entries, cap, sub, loss_armed=loss_armed, exits=exits)

    def benefit(cap: float | None, sub: set[str] | None = None) -> float:
        return run(cap, sub)["net_pnl"] - apply_budget(entries, None, sub)["net_pnl"]

    grid = {
        str(cap): run(cap) | {"benefit_vs_baseline": round(benefit(cap), 2)} for cap in CAP_GRID
    }

    # -- 1. in-sample / out-of-sample --------------------------------------
    cut = int(n_days * IS_FRACTION)
    is_days, oos_days = set(days[:cut]), set(days[cut:])
    cap, is_benefit = _best_cap(entries, is_days, loss_armed=loss_armed, exits=exits)
    oos_benefit = benefit(cap, oos_days)

    # -- 2. walk-forward (expanding origin; folds >= MIN_WF_FOLD_DAYS) -----
    n_oos = n_days - cut
    n_folds = max(1, min(WF_MAX_FOLDS, n_oos // MIN_WF_FOLD_DAYS))
    fold_size = max(MIN_WF_FOLD_DAYS, n_oos // n_folds)
    folds = []
    for i in range(n_folds):
        tr_end = cut + i * fold_size
        te_start, te_end = tr_end, min(tr_end + fold_size, n_days)
        if te_start >= te_end:
            break
        tr, te = set(days[:tr_end]), set(days[te_start:te_end])
        fold_cap, tr_ben = _best_cap(entries, tr, loss_armed=loss_armed, exits=exits)
        te_ben = benefit(fold_cap, te)
        tr_rate, te_rate = tr_ben / max(len(tr), 1), te_ben / max(len(te), 1)
        # Over-delivery clipped to 1.0: a lucky fold is not extra robustness.
        eff = min(te_rate / tr_rate, 1.0) if tr_rate > 0 else (1.0 if te_rate > 0 else 0.0)
        folds.append(
            {
                "fold": i + 1,
                "train_days": len(tr),
                "test_days": len(te),
                "chosen_cap": fold_cap,
                "train_benefit": round(tr_ben, 2),
                "test_benefit": round(te_ben, 2),
                "wf_efficiency": round(eff, 4),
            }
        )
    wf_median = st.median([f["wf_efficiency"] for f in folds]) if folds else 0.0

    # -- 3. sub-window stability -------------------------------------------
    w = n_days // 3
    windows = [set(days[:w]), set(days[w : 2 * w]), set(days[2 * w :])]
    sub = [
        {
            "window": i,
            "days": len(win),
            "baseline_net": apply_budget(entries, None, win)["net_pnl"],
            "capped_net": run(cap, win)["net_pnl"],
            "benefit": round(benefit(cap, win), 2),
        }
        for i, win in enumerate(windows, 1)
    ]
    sub_window_stable = all(s["benefit"] > 0 for s in sub)

    # -- 4. anchor no-regression: the 5 best realised days ------------------
    per_day_net: dict[str, float] = defaultdict(float)
    for e in entries:
        per_day_net[e["date"]] += e["net"]
    anchor_days = {d for d, _ in sorted(per_day_net.items(), key=lambda kv: -kv[1])[:5]}
    base_anchor = apply_budget(entries, None, anchor_days)["net_pnl"]
    curr_anchor = run(cap, anchor_days)["net_pnl"]
    anchor_pass = anchor_no_regression(base_anchor, curr_anchor, ANCHOR_TOLERANCE_PCT)

    # -- 5. artifact hunts ---------------------------------------------------
    best_day = max(days, key=lambda d: per_day_net.get(d, 0.0))
    jack = [benefit(cap, set(days) - {d}) for d in days]
    per_day_delta = sorted(
        ({"date": d, "delta": round(benefit(cap, {d}), 2)} for d in days),
        key=lambda x: x["delta"],
    )

    gate = {
        "oos_positive": bool(oos_benefit > 0),
        "wf_median_ge_0.70": bool(wf_median >= 0.70),
        "sub_window_stable": bool(sub_window_stable),
        "anchor_no_regression": bool(anchor_pass),
    }
    headline = run(cap)

    return {
        "variant": name,
        "label": label,
        "loss_armed": loss_armed,
        "candidate_cap_dollars": cap,
        "candidate_chosen_by": f"max net P&L over the in-sample first {cut} of {n_days} days",
        "headline": headline,
        "benefit_vs_baseline": round(headline["net_pnl"] - baseline["net_pnl"], 2),
        "cap_grid": grid,
        "battery": {
            "in_sample_out_of_sample": {
                "is_days": len(is_days),
                "oos_days": len(oos_days),
                "is_chosen_cap": cap,
                "is_benefit": round(is_benefit, 2),
                "oos_baseline_net": apply_budget(entries, None, oos_days)["net_pnl"],
                "oos_capped_net": run(cap, oos_days)["net_pnl"],
                "oos_benefit": round(oos_benefit, 2),
            },
            "walk_forward": {
                "min_fold_days": MIN_WF_FOLD_DAYS,
                "folds": folds,
                "wf_median_efficiency": round(wf_median, 4),
            },
            "sub_windows": sub,
            "anchor": {
                "anchor_days": sorted(anchor_days),
                "baseline_anchor_net": base_anchor,
                "capped_anchor_net": curr_anchor,
                "regression_pct": round(
                    100.0 * (curr_anchor - base_anchor) / abs(base_anchor), 2
                )
                if base_anchor
                else 0.0,
                "tolerance_pct": ANCHOR_TOLERANCE_PCT,
                "passes": anchor_pass,
            },
        },
        "artifact_hunts": {
            "drop_best_day": {
                "dropped": best_day,
                "benefit": round(benefit(cap, set(days) - {best_day}), 2),
                "note": "Benefit must survive removing the single best day.",
            },
            "leave_one_day_out": {
                "full_sample_benefit": round(benefit(cap), 2),
                "min": round(min(jack), 2),
                "median": round(st.median(jack), 2),
                "max": round(max(jack), 2),
                "folds_with_non_positive_benefit": sum(1 for b in jack if b <= 0),
                "n_folds": len(jack),
            },
            "per_day_delta_worst5": per_day_delta[:5],
            "per_day_delta_best5": per_day_delta[-5:],
            "days_helped": sum(1 for x in per_day_delta if x["delta"] > 1),
            "days_hurt": sum(1 for x in per_day_delta if x["delta"] < -1),
        },
        "op11_gate": gate,
        "auto_ratify": all(gate.values()),
    }


def _per_arm_attribution(
    entries: list[dict], exits: ExitIndex, variant: dict[str, Any]
) -> dict[str, dict[str, float]]:
    """Baseline vs candidate net P&L per arm, using the variant's own policy."""
    base_arm: dict[str, float] = defaultdict(float)
    cand_arm: dict[str, float] = defaultdict(float)
    spent: dict[tuple[str, str], float] = defaultdict(float)
    cap = variant["candidate_cap_dollars"]
    for e in entries:
        base_arm[e["arm"]] += e["net"]
        armed = True
        if variant["loss_armed"]:
            armed = realized_before(exits, e["arm"], e["date"], e["ts"]) < 0
        key = (e["date"], e["arm"])
        if armed and spent[key] + e["cost"] > cap:
            continue
        spent[key] += e["cost"]
        cand_arm[e["arm"]] += e["net"]
    return {
        arm: {
            "baseline_net": round(base_arm[arm], 2),
            "candidate_net": round(cand_arm.get(arm, 0.0), 2),
            "delta": round(cand_arm.get(arm, 0.0) - base_arm[arm], 2),
        }
        for arm in sorted(base_arm)
    }


def main() -> int:
    entries = load_entries()
    exits = load_exits()
    days = sorted({e["date"] for e in entries})
    baseline = apply_budget(entries, None)

    armed_population = sum(
        1 for e in entries if realized_before(exits, e["arm"], e["date"], e["ts"]) < 0
    )

    variants = [
        evaluate_variant(
            "A_flat",
            "Flat per-arm daily premium cap (engages from the first entry)",
            entries,
            exits,
            days,
            loss_armed=False,
        ),
        evaluate_variant(
            "C_loss_armed",
            "Loss-armed per-arm daily premium cap (engages only after the arm "
            "books a losing exit that session)",
            entries,
            exits,
            days,
            loss_armed=True,
        ),
    ]
    passing = [v for v in variants if v["auto_ratify"]]
    winner = max(passing, key=lambda v: v["benefit_vs_baseline"]) if passing else None
    show = winner or max(variants, key=lambda v: v["benefit_vs_baseline"])

    payload: dict[str, Any] = {
        "rule_id": "daily-premium-budget",
        "title": "Per-arm daily option-premium deployment budget (loss-armed)",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "backtest/autoresearch/daily_premium_budget_battery.py",
        "source_ledger": "automation/state/pnl-statement.json (T1 broker-truth round_trips)",
        "source_generated_at_utc": json.loads(PNL_STATEMENT.read_text(encoding="utf-8"))[
            "generated_at_utc"
        ],
        "method": (
            "Subtractive policy overlay on REALIZED broker fills: an entry is skipped "
            "when the arm's premium already deployed that session plus this entry's "
            "premium exceeds the cap. Variant C additionally requires the arm to be "
            "ALREADY RED on the day (from exits closed strictly before this entry's "
            "timestamp) before the cap engages. Causal -- both spend-so-far and "
            "realized-so-far are knowable live. No resizing, no counterfactual price "
            "paths. Net of OCC/ORF/TAF/SEC fees (A1-cost-rebuild-2026-08-28 rates)."
        ),
        "disclosed_limits": [
            "Freed settled cash is NOT recycled into later sizing (held as-traded).",
            f"n={len(days)} trading days, paper fills, 5 active arms -- small sample (C4).",
            "Slippage not swept here; A1 puts August breakeven at 146c/contract.",
            f"Walk-forward on {len(days)} days is weak by construction; folds are held "
            f"to {MIN_WF_FOLD_DAYS}+ trading days but n_folds is small. Corroborating, "
            "not decisive.",
            "Anchor set is the 5 best realised days. A flat cap is EXPECTED to stress "
            "it -- that is the tradeoff variant C exists to avoid.",
        ],
        "prior_coverage": [
            "analysis/recommendations/B3-loss-anatomy-2026-08-28.json",
            "analysis/recommendations/B3-bounded-config-2026-08-28.json",
            "analysis/recommendations/A1-cost-rebuild-2026-08-28.json",
        ],
        "window": {"start": days[0], "end": days[-1], "trading_days": len(days)},
        "baseline_no_rule": baseline,
        "armed_population": {
            "entries_placed_while_arm_already_red": armed_population,
            "total_entries": len(entries),
            "pct": round(100.0 * armed_population / len(entries), 1),
            "note": "The population variant C acts on.",
        },
        "variants": variants,
        "per_arm_attribution_for_candidate": _per_arm_attribution(entries, exits, show),
        "winner": winner["variant"] if winner else None,
        "auto_ratify": winner is not None,
        "verdict": (
            f"AUTO-RATIFY {winner['variant']} (cap ${winner['candidate_cap_dollars']}): "
            f"clears every OP-11 gate; net {baseline['net_pnl']:+.0f} -> "
            f"{winner['headline']['net_pnl']:+.0f} on "
            f"{100 * winner['headline']['deployed'] / baseline['deployed']:.0f}% of the capital."
            if winner
            else "NO VARIANT AUTO-RATIFIES -- escalate to J with the tradeoff quantified."
        ),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    for v in variants:
        print(
            f"{v['variant']:14} cap ${v['candidate_cap_dollars']:<5} "
            f"net {v['headline']['net_pnl']:>+8.0f}  "
            f"deployed ${v['headline']['deployed']:>8.0f}  "
            f"DD {v['headline']['max_drawdown']:>7.0f}  "
            f"PF {v['headline']['profit_factor']}"
        )
        print(f"{'':14} gate {v['op11_gate']}")
    print("\n" + payload["verdict"])
    print(f"wrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
