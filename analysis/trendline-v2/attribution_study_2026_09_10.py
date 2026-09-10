"""ATTRIBUTION STUDY -- does trendline_rejection carry its own weight? (2026-09-10)

Work order: markdown/0dte/KEY-LEVELS-CHART-READING-HANDOFF.md (task text, this session).
Closes the gap flagged in RESULTS-2026-09-10-trade-outcome-ab.md's caveat (a): that file's
n=45 population is "entries whose triggers list INCLUDES trendline_rejection" -- it cannot
say whether trendline_rejection was load-bearing for the fill or just along for the ride.

READ-ONLY. Imports setup/scripts/go_live_gate.py and REUSES its statistical_criterion()
verbatim (L251 -- never reimplement the bootstrap-PF-CI machinery). Writes nothing outside
analysis/trendline-v2/. Does not call go_live_gate.refresh_trades_enriched() or
build_report() (the latter fetches live broker REST for the reconciliation criterion --
out of scope and an unwanted network call for a read-only decomposition). Reads
analysis/trades-enriched.jsonl AS-IS off disk, same practice as the prior
ab_replay_2026_09_10.py study in this same directory.

POPULATION: every row in trades-enriched.jsonl with attribution=="engine" and
arm in go_live_gate.ACTIVE_ARMS (the 4 real-fills arms: safe-2, bold-2, safe-3, risky-1 --
derived live from accounts.json, matches the work order's named roster). Real fills only
(L50/L71); pnl_dollars is option P&L (L74/C3), never SPY-price P&L.

DECOMPOSITION (exactly as specified, no second slicing -- p-hacking guard):
  SOLE        triggers == ["trendline_rejection"]  (exactly this one trigger, nothing else)
  CO_FIRING   "trendline_rejection" in triggers AND len(triggers) > 1
  NONE        "trendline_rejection" not in triggers  (comparison baseline / rest of book)
  ALL_TL      SOLE union CO_FIRING (every entry carrying the trigger at all -- this IS the
              n=45 population from RESULTS-2026-09-10-trade-outcome-ab.md, reproduced here
              as a consistency check on the SAME data source used there)

Each bucket scored with go_live_gate.statistical_criterion(rows, arm_id=None) -- pools all
arms in that bucket into one CI (arm_id=None means "scoped = rows", per that function's own
top line). Per-trade P&L reported alongside (mean, net, n) since that is the unit the
2026-09-08 STATUS.md trendline_tier_rail read used, and this file's job is to reconcile with
that read explicitly (see reconcile_with_status_2026_09_08 below).

BLOCK COUNTERFACTUALS (naive -- see module docstring section in the results .md for the
explicit "assumes nothing replaces the blocked trade" caveat):
  book_as_traded                  = statistical_criterion(ALL engine rows)
  book_with_SOLE_blocked          = statistical_criterion(ALL engine rows MINUS SOLE)
  book_with_ALL_TL_blocked        = statistical_criterion(ALL engine rows MINUS ALL_TL)
  + drop-best-ARM variant of each (distinct from statistical_criterion's own drop-best-DAY):
    removes the single arm contributing the most net pnl to that scenario's rows entirely,
    then rescopes. A result that only survives on one arm is not a result (C4/C24).

RECONCILIATION: setup/scripts/trendline_tier_rail.py is the source of the STATUS.md
2026-09-08 "n=41, -2.17/tr" line (LOSS-MECHANISMS-READ-2026-09-08 entry). It uses the SAME
strict triggers==["trendline_rejection"] shape as this file's SOLE bucket, but a DIFFERENT
population: ARMS=("safe-2","bold-2") only (2 arms, not 4), sourced from
automation/state/core-decisions.jsonl + fills-ledger.jsonl via
exit_shape_parity_study.reconstruct_positions (position-level P&L), not trades-enriched.jsonl
round trips. This script re-derives a 2-arm-restricted cut of SOLE (safe-2+bold-2 only) from
trades-enriched.jsonl and reports whether it matches n=41/-$2.17 -- if it does not, the
residual is attributable to the join/position-reconstruction method, not the population
definition, and this file says so rather than hiding the mismatch.

Usage: backtest/.venv/Scripts/python.exe analysis/trendline-v2/attribution_study_2026_09_10.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO / "setup" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import go_live_gate as glg  # noqa: E402 -- statistical_criterion() REUSED VERBATIM, per L251

OUT_JSON = REPO / "analysis" / "trendline-v2" / "attribution_study_2026_09_10.json"

TRIGGER = "trendline_rejection"
UNDERPOWERED_N = 15  # work order's own bar: n<15 reported AND labelled, never dropped/hidden


# --------------------------------------------------------------------------------------- #
# Population + partition
# --------------------------------------------------------------------------------------- #
def load_engine_rows() -> list[dict]:
    """go_live_gate.load_ledger_rows() already filters arm in ACTIVE_ARMS (the 4 real-fills
    arms) and excludes the _meta row / retired safe-1. We additionally restrict to
    attribution=="engine" here, matching build_report()'s own line
    `engine_rows = [r for r in all_rows if r["attribution"] == "engine"]` verbatim."""
    all_rows = glg.load_ledger_rows()
    return [r for r in all_rows if r.get("attribution") == "engine"]


def partition(rows: list[dict]) -> dict[str, list[dict]]:
    sole, co_firing, none_bucket = [], [], []
    for r in rows:
        trigs = r.get("triggers")
        has_tl = isinstance(trigs, list) and TRIGGER in trigs
        if not has_tl:
            none_bucket.append(r)
        elif len(trigs) == 1:
            sole.append(r)
        else:
            co_firing.append(r)
    return {
        "SOLE": sole,
        "CO_FIRING": co_firing,
        "NONE": none_bucket,
        "ALL_TL": sole + co_firing,
    }


def co_firing_partners(co_firing_rows: list[dict], min_n: int = 5) -> dict:
    """Break out CO_FIRING by partner-trigger combo where N allows (work order instruction).
    A combo is the OTHER triggers present alongside trendline_rejection, order-independent."""
    combo_counter: Counter = Counter()
    combo_rows: dict[tuple, list[dict]] = defaultdict(list)
    for r in co_firing_rows:
        others = tuple(sorted(t for t in r["triggers"] if t != TRIGGER))
        combo_counter[others] += 1
        combo_rows[others].append(r)
    out = {}
    for combo, n in combo_counter.most_common():
        label = "+".join(combo) if combo else "(none -- malformed, len>1 but no other trigger)"
        bucket_rows = combo_rows[combo]
        stat = glg.statistical_criterion(bucket_rows, None)
        pnl = [float(x["pnl_dollars"]) for x in bucket_rows]
        out[label] = {
            "n": n,
            "underpowered": n < min_n,
            "net_pnl": round(sum(pnl), 2),
            "mean_pnl_per_trade": round(sum(pnl) / n, 2) if n else None,
            "statistical_criterion": stat,
        }
    return out


# --------------------------------------------------------------------------------------- #
# Per-bucket scoring
# --------------------------------------------------------------------------------------- #
def score_bucket(name: str, rows: list[dict]) -> dict:
    n = len(rows)
    pnl = [float(r["pnl_dollars"]) for r in rows]
    days = sorted({r["date"] for r in rows})
    per_arm_net = defaultdict(float)
    for r in rows:
        per_arm_net[r["arm"]] += float(r["pnl_dollars"])
    stat = glg.statistical_criterion(rows, None)
    return {
        "bucket": name,
        "n": n,
        "underpowered_n_lt_15": n < UNDERPOWERED_N,
        "n_trading_days": len(days),
        "date_range": [days[0], days[-1]] if days else None,
        "net_pnl": round(sum(pnl), 2) if pnl else None,
        "mean_pnl_per_trade": round(sum(pnl) / n, 2) if n else None,
        "win_rate": round(sum(1 for v in pnl if v > 0) / n, 4) if n else None,
        "per_arm_net_pnl": {k: round(v, 2) for k, v in per_arm_net.items()},
        "statistical_criterion": stat,
    }


# --------------------------------------------------------------------------------------- #
# Block counterfactuals (naive -- see docstring)
# --------------------------------------------------------------------------------------- #
def drop_best_arm(rows: list[dict]) -> tuple[str | None, list[dict]]:
    if not rows:
        return None, rows
    per_arm_net = defaultdict(float)
    for r in rows:
        per_arm_net[r["arm"]] += float(r["pnl_dollars"])
    if not per_arm_net:
        return None, rows
    best_arm = max(per_arm_net, key=per_arm_net.get)
    return best_arm, [r for r in rows if r["arm"] != best_arm]


def block_counterfactual(all_rows: list[dict], blocked_rows: list[dict], label: str) -> dict:
    blocked_ids = {id(r) for r in blocked_rows}
    remaining = [r for r in all_rows if id(r) not in blocked_ids]
    base_stat = glg.statistical_criterion(remaining, None)
    best_arm, remaining_ex_best_arm = drop_best_arm(remaining)
    ex_best_arm_stat = glg.statistical_criterion(remaining_ex_best_arm, None)
    pnl_remaining = [float(r["pnl_dollars"]) for r in remaining]
    pnl_ex_best_arm = [float(r["pnl_dollars"]) for r in remaining_ex_best_arm]
    return {
        "label": label,
        "n_blocked": len(blocked_rows),
        "n_remaining": len(remaining),
        "book_net_pnl_after_block": round(sum(pnl_remaining), 2) if pnl_remaining else None,
        "book_mean_pnl_per_trade_after_block": (
            round(sum(pnl_remaining) / len(pnl_remaining), 2) if pnl_remaining else None
        ),
        "statistical_criterion_after_block": base_stat,
        "drop_best_arm": {
            "arm_dropped": best_arm,
            "n_remaining_after_arm_drop": len(remaining_ex_best_arm),
            "net_pnl": round(sum(pnl_ex_best_arm), 2) if pnl_ex_best_arm else None,
            "mean_pnl_per_trade": (
                round(sum(pnl_ex_best_arm) / len(pnl_ex_best_arm), 2) if pnl_ex_best_arm else None
            ),
            "statistical_criterion": ex_best_arm_stat,
        },
    }


# --------------------------------------------------------------------------------------- #
# Reconciliation with the 09-08 STATUS.md trendline_tier_rail read (n=41, -$2.17/tr)
# --------------------------------------------------------------------------------------- #
def reconcile_with_status_2026_09_08(sole_rows: list[dict]) -> dict:
    """Restrict THIS study's SOLE bucket (4 arms, trades-enriched.jsonl round trips) to the
    same 2 arms trendline_tier_rail.py scores (safe-2 + bold-2 only), and compare against a
    FRESH dry-run of that rail (not a stale quote -- rerun this session)."""
    sole_2arm = [r for r in sole_rows if r["arm"] in ("safe-2", "bold-2")]
    pnl = [float(r["pnl_dollars"]) for r in sole_2arm]
    n = len(sole_2arm)
    days = sorted({r["date"] for r in sole_2arm})

    import trendline_tier_rail as ttr  # local import: only needed for this reconciliation
    rail_report = ttr.run(dry_run=True)  # dry_run=True -- reads state, writes NOTHING

    this_study_2arm_sole = {
        "n": n,
        "n_trading_days": len(days),
        "net_pnl": round(sum(pnl), 2) if pnl else None,
        "mean_pnl_per_trade": round(sum(pnl) / n, 2) if n else None,
        "win_rate": round(sum(1 for v in pnl if v > 0) / n, 4) if n else None,
    }
    rail_tl = rail_report["trendline_only"]
    matches_exactly = (
        n == rail_tl["n"]
        and this_study_2arm_sole["net_pnl"] is not None
        and abs(this_study_2arm_sole["net_pnl"] - rail_tl["net_usd"]) < 0.01
    )
    return {
        "status_md_quote_2026_09_08": (
            "Trendline-only rail HOLDING (n=41, -2.17/tr; rest-of-book -4.73/tr, WR 25 pct)."
        ),
        "fresh_rerun_this_session_trendline_tier_rail_dry_run": rail_tl,
        "fresh_rerun_matches_the_status_quote": (
            rail_tl["n"] == 41 and abs(rail_tl["mean_usd"] - (-2.17)) < 0.005
        ),
        "this_study_SOLE_restricted_to_safe2_bold2_only": this_study_2arm_sole,
        "exact_match_to_rail": matches_exactly,
        "scope_differences_if_any": [
            "trendline_tier_rail.py scores 2 arms only (safe-2, bold-2) -- this study's "
            "headline SOLE bucket scores all 4 real-fills arms (adds safe-3, risky-1). "
            "This reconciliation cut restricts to the same 2 arms to isolate that variable.",
            "trendline_tier_rail.py sources automation/state/core-decisions.jsonl "
            "(action==PLACED rows) joined to fills-ledger.jsonl via "
            "exit_shape_parity_study.reconstruct_positions (position-level P&L, FIFO-free "
            "flat-to-flat reconstruction from raw fills). This study sources "
            "analysis/trades-enriched.jsonl (a separately-built round-trip ledger via "
            "trades_enriched.py, basis='flat_to_flat' per the sample row, fifo_trip-based). "
            "Both target the same real fills; a residual after arm-matching indicates the "
            "two pipelines' join/reconstruction logic disagree on trip boundaries for some "
            "subset, not a population-definition disagreement (both use the identical STRICT "
            "triggers==['trendline_rejection'] shape).",
            "trendline_tier_rail has no explicit date floor; trades-enriched.jsonl's earliest "
            "row is 2026-06-26 -- if core-decisions.jsonl/fills-ledger.jsonl retain rows "
            "trades-enriched.jsonl's producer dropped (or vice versa) that is a further "
            "source of residual n.",
        ],
    }


# --------------------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------------------- #
def main() -> dict:
    engine_rows = load_engine_rows()
    buckets = partition(engine_rows)

    bucket_scores = {name: score_bucket(name, rows) for name, rows in buckets.items()}
    co_firing_breakout = co_firing_partners(buckets["CO_FIRING"])

    book_as_traded = score_bucket("BOOK_AS_TRADED", engine_rows)

    counterfactuals = {
        "SOLE_blocked": block_counterfactual(engine_rows, buckets["SOLE"], "block SOLE only"),
        "ALL_TL_blocked": block_counterfactual(
            engine_rows, buckets["ALL_TL"], "block every trendline_rejection-carrying entry"
        ),
    }

    reconciliation = reconcile_with_status_2026_09_08(buckets["SOLE"])

    report = {
        "_doc": __doc__,
        "generated_by": "analysis/trendline-v2/attribution_study_2026_09_10.py",
        "population_source": "analysis/trades-enriched.jsonl (as-is on disk, NOT refreshed "
                              "this run -- read-only per task boundary)",
        "active_arms_used": glg.ACTIVE_ARMS,
        "n_engine_rows_all_arms_all_triggers": len(engine_rows),
        "trigger_studied": TRIGGER,
        "underpowered_threshold_n": UNDERPOWERED_N,
        "book_as_traded": book_as_traded,
        "buckets": bucket_scores,
        "co_firing_partner_breakout": co_firing_breakout,
        "block_counterfactuals_NAIVE": counterfactuals,
        "reconciliation_with_status_2026_09_08": reconciliation,
        "limitations": [
            "Naive block counterfactual: assumes a blocked entry simply does not happen and "
            "nothing replaces it (capital/PDT slot freed goes unused in this model). If the "
            "engine would plausibly have taken a different trade in that slot, this model "
            "does not capture it -- no replacement trade is evidenced or simulated here.",
            "SOLE vs CO_FIRING is a STRUCTURAL partition of the trigger LIST on the fill, not "
            "a causal claim about which trigger was load-bearing for the entry decision -- "
            "for CO_FIRING entries specifically, the engine's actual gating logic (not "
            "measured here) may have required ALL listed triggers jointly, or any one of "
            "them may have been sufficient alone; this study cannot distinguish those cases "
            "from the ledger.",
            "Real fills only, per L50/L71 -- no sim/BS-priced rows are used anywhere in this "
            "file. That also means no ranking-only counterfactual exists for trades the "
            "engine never took.",
            "IS-only: 100% of rows are on/before today (2026-09-10); there is no forward/OOS "
            "window to check this decomposition against yet.",
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    rep = main()
    print(f"[attribution_study] wrote {OUT_JSON}")
    print(f"[attribution_study] SOLE n={rep['buckets']['SOLE']['n']} "
          f"mean=${rep['buckets']['SOLE']['mean_pnl_per_trade']}/tr "
          f"ex_best_day_ci_lower="
          f"{rep['buckets']['SOLE']['statistical_criterion'].get('ex_best_day', {}).get('ci_lower_2.5')}")
    print(f"[attribution_study] CO_FIRING n={rep['buckets']['CO_FIRING']['n']} "
          f"mean=${rep['buckets']['CO_FIRING']['mean_pnl_per_trade']}/tr")
    print(f"[attribution_study] NONE (rest of book) n={rep['buckets']['NONE']['n']} "
          f"mean=${rep['buckets']['NONE']['mean_pnl_per_trade']}/tr")
    print(f"[attribution_study] reconciliation match to rail: "
          f"{rep['reconciliation_with_status_2026_09_08']['exact_match_to_rail']}")
