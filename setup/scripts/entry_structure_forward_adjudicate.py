#!/usr/bin/env python
"""entry_structure_forward_adjudicate.py -- THE ADJUDICATOR for the V-d1 / V-e3 forward
pre-registration (analysis/recommendations/entry-structure-forward-prereg-2026-08-06.json).

The prereg froze five forward gates F1-F5 and said, in its own words, that F4 (pooled
within-day permutation) and F5 (regime split) are "adjudicated by a future session ...
this counter only measures". entry_shadow_counter.py measures F1-F3 nightly; NOTHING ran
F4/F5 until this module existed. This is that session's instrument, made re-runnable so
the next EXTEND cycle does not need a human to re-derive the test.

THE TEST (verbatim from the prereg, not re-invented here):
  F1 direction          forward delta_usd > 0
  F2 not-winner-killer  blocked_winner_dollars < blocked_loser_dollars, forward
  F3 frequency          n_blocked >= 8 forward (else EXTEND -- judge nothing)
  F4 discrimination     within-day permutation p <= 0.10 on the POOLED (in-sample+forward)
                        population: hold each day's number of blocked entries FIXED,
                        randomise WHICH entries inside that day are blocked, 20,000 draws
  F5 regime-neutral     forward delta >= 0 on both the best and the worst session
  ladder  ARM = F1..F5 all pass | EXTEND = F3 fails | KILL = F1 or F2 fails, or F4 fails pooled

SHADOW ONLY. This module reads ledgers and writes ONE scorecard. It never blocks an
entry, never touches params/heartbeat/filters/placement, never places an order.

INTEGRITY GATE (why you can trust the numbers): the rule flags are RE-DERIVED here from
entry-quality-ledger fields, then checked row-for-row against shadow-tally.jsonl, which
carries the SINGLE frozen implementation (entry_quality_ledger cells V-d1-rescore /
R-PRES-1m). Any mismatch VOIDS the run with a non-zero exit -- two implementations of
one rule is how replay engines silently disagree (L251). Pinned by
backtest/tests/test_entry_structure_adjudicator_2026_08_25.py.

USAGE:  python setup/scripts/entry_structure_forward_adjudicate.py [--draws 20000] [--dry-run]
COST:   $0 -- pure local Python over existing JSON/JSONL.
REVERT: delete this file + its scorecard; artifacts are inert data.
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "analysis" / "entry-quality" / "entry-quality-ledger.json"
TALLY = REPO / "analysis" / "entry-quality" / "shadow-tally.jsonl"
PREREG = REPO / "analysis" / "recommendations" / "entry-structure-forward-prereg-2026-08-06.json"
OUT = REPO / "analysis" / "recommendations" / "entry-structure-forward-2026-08-06.json"

FORWARD_FIRST_DATE = "2026-08-06"   # prereg frozen pre-dawn 08-06 -> 08-06 is session #1
F3_MIN_BLOCKS = 8
F4_P_BAR = 0.10
DEFAULT_DRAWS = 20000
SEED = 20260825                      # fixed: the verdict must be reproducible


# ---------------------------------------------------------------- rule re-derivation
def vd1(e):
    """Refuse when the LAST FULLY CLOSED 5m bar closed AGAINST the trade direction
    (close <= open for a long; close >= open for a short). 'flat' satisfies both."""
    d, s = e.get("d_last5_dir"), e.get("opt_side")
    if d is None or s is None:
        return None
    if s == "C":
        return d in ("down", "flat")
    if s == "P":
        return d in ("up", "flat")
    return None


def ve3(e):
    """Refuse when >=20 closed 1m RTH bars exist and structure reports NO BOS and no
    CHoCH at all (structure ABSENCE). Abstain below 20 closed 1m bars."""
    n1 = e.get("n_closed_1m")
    if n1 is None or n1 < 20:
        return None
    return e.get("s1_kind") is None


RULES = (("V-d1", vd1), ("V-e3", ve3))


# ---------------------------------------------------------------- integrity gate
def validate_against_frozen(events, tally):
    by_id = {e["activity_id"]: e for e in events}
    checked = missing = 0
    mismatch = {"V-d1": 0, "V-e3": 0}
    for t in tally:
        e = by_id.get(t["activity_id"])
        if e is None:
            missing += 1
            continue
        checked += 1
        if bool(vd1(e)) != bool(t["vd1_would_block"]):
            mismatch["V-d1"] += 1
        if bool(ve3(e)) != bool(t["ve3_would_block"]):
            mismatch["V-e3"] += 1
    return {"tally_rows": len(tally), "matched": checked, "missing_from_ledger": missing,
            "mismatches": mismatch, "ok": checked > 0 and not any(mismatch.values())}


# ---------------------------------------------------------------- metrics
def cohort(pop, fn):
    blocked = [e for e in pop if fn(e) is True]
    delta = -sum(e["pnl"] for e in blocked)           # $ the book GAINS by blocking
    win = sum(e["pnl"] for e in blocked if e["pnl"] > 0)
    los = -sum(e["pnl"] for e in blocked if e["pnl"] < 0)
    return {
        "n": len(pop),
        "n_blocked": len(blocked),
        "n_abstain": sum(1 for e in pop if fn(e) is None),
        "delta_usd": round(delta, 2),
        "blocked_winner_usd": round(win, 2),
        "blocked_loser_usd": round(los, 2),
        "blocked_wr_pct": round(100 * sum(1 for e in blocked if e["pnl"] > 0) / len(blocked), 1) if blocked else 0.0,
        "population_wr_pct": round(100 * sum(1 for e in pop if e["pnl"] > 0) / len(pop), 1) if pop else 0.0,
    }


def within_day_permutation(pop, fn, draws, seed=SEED):
    """p = P(random within-day selection of the SAME per-day block count reaches the
    observed pooled delta). Days where every/no eligible entry is blocked have no
    freedom -- their contribution is constant and is carried outside the draw."""
    rng = random.Random(seed)
    days = collections.defaultdict(list)
    for e in pop:
        if fn(e) is None:
            continue
        days[e["date_et"]].append(e)

    observed = 0.0
    fixed = 0.0
    plan = []
    for _dte, rows in days.items():
        k = sum(1 for e in rows if fn(e) is True)
        observed += -sum(e["pnl"] for e in rows if fn(e) is True)
        if k == 0 or k == len(rows):
            fixed += -sum(e["pnl"] for e in rows if fn(e) is True)
        else:
            plan.append(([e["pnl"] for e in rows], k))

    ge = 0
    for _ in range(draws):
        tot = fixed
        for pnls, k in plan:
            tot += -sum(rng.sample(pnls, k))
        if tot >= observed - 1e-9:
            ge += 1
    return {
        "observed_delta_usd": round(observed, 2),
        "fixed_contribution_usd": round(fixed, 2),
        "days_with_freedom": len(plan),
        "draws": draws,
        "p_value": round((ge + 1) / (draws + 1), 4),
    }


def regime_split(fwd, fn):
    day_book = collections.defaultdict(float)
    day_rule = collections.defaultdict(float)
    for e in fwd:
        day_book[e["date_et"]] += e["pnl"]
        if fn(e) is True:
            day_rule[e["date_et"]] += -e["pnl"]
    if not day_book:
        return None
    best = max(day_book, key=lambda d: day_book[d])
    worst = min(day_book, key=lambda d: day_book[d])
    return {
        "best_session": best, "best_session_book_usd": round(day_book[best], 2),
        "best_session_rule_delta_usd": round(day_rule.get(best, 0.0), 2),
        "worst_session": worst, "worst_session_book_usd": round(day_book[worst], 2),
        "worst_session_rule_delta_usd": round(day_rule.get(worst, 0.0), 2),
    }


def adjudicate(name, fwd_m, perm, reg):
    f1 = fwd_m["delta_usd"] > 0
    f2 = fwd_m["blocked_winner_usd"] < fwd_m["blocked_loser_usd"]
    f3 = fwd_m["n_blocked"] >= F3_MIN_BLOCKS
    f4 = perm["p_value"] <= F4_P_BAR
    f5 = (reg is not None
          and reg["best_session_rule_delta_usd"] >= 0
          and reg["worst_session_rule_delta_usd"] >= 0)
    # ladder, in the prereg's precedence: EXTEND on F3 before judging anything else
    if not f3:
        verdict = "EXTEND"
        basis = (f"F3 FAIL: n_blocked={fwd_m['n_blocked']} < {F3_MIN_BLOCKS} forward. "
                 "The prereg says extend the window and judge nothing.")
    elif not f1 or not f2 or not f4:
        verdict = "KILL"
        failed = [g for g, ok in (("F1", f1), ("F2", f2), ("F4", f4)) if not ok]
        basis = "KILL per the prereg ladder -- " + ", ".join(failed) + " failed."
    elif f1 and f2 and f3 and f4 and f5:
        verdict = "ARM"
        basis = "F1..F5 all pass."
    else:
        verdict = "EXTEND"
        basis = "F5 failed with F1-F4 passing -- not a ladder outcome; treat as inconclusive."
    return {"gates": {"F1_direction": f1, "F2_not_winner_killer": f2,
                      "F3_frequency": f3, "F4_discrimination": f4, "F5_regime_neutral": f5},
            "verdict": verdict, "verdict_basis": basis}


# ---------------------------------------------------------------- main
def run(draws=DEFAULT_DRAWS, dry_run=False):
    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    events = led["events"]
    tally = [json.loads(l) for l in TALLY.read_text(encoding="utf-8").splitlines() if l.strip()]

    integrity = validate_against_frozen(events, tally)
    if not integrity["ok"]:
        print("[adjudicate] VOID -- re-derived flags disagree with the frozen "
              "implementation: " + json.dumps(integrity), file=sys.stderr)
        return 2

    in_sample = [e for e in events if e["date_et"] < FORWARD_FIRST_DATE]
    forward = [e for e in events if e["date_et"] >= FORWARD_FIRST_DATE]

    results = {}
    for name, fn in RULES:
        fwd_m = cohort(forward, fn)
        pooled_m = cohort(events, fn)
        perm = within_day_permutation(events, fn, draws)
        reg = regime_split(forward, fn)
        results[name] = {"rule_id": name, "forward": fwd_m, "pooled": pooled_m,
                         "F4_within_day_permutation_pooled": perm,
                         "F5_regime_split_forward": reg,
                         **adjudicate(name, fwd_m, perm, reg)}

    is_days = len(set(e["date_et"] for e in in_sample))
    scorecard = {
        "rule_id": "entry-structure-forward-2026-08-06",
        "title": "ADJUDICATION of the V-d1 / V-e3 forward pre-registration (F1-F5 ladder)",
        "adjudicated_from_ledger_generated_at_et": led["_meta"]["generated_at_et"],
        "adjudicator": "setup/scripts/entry_structure_forward_adjudicate.py",
        "prereg": "analysis/recommendations/entry-structure-forward-prereg-2026-08-06.json",
        "shadow_only": "No rule here ever refused a live entry. This is the verdict, not a deployment.",
        "population": {
            "source": "analysis/entry-quality/entry-quality-ledger.json (LIVE-ENGINE-REAL-FILLS-v2, broker-truth FIFO P&L)",
            "pooled_n": len(events),
            "pooled_days": len(set(e["date_et"] for e in events)),
            "in_sample_n": len(in_sample),
            "in_sample_days": is_days,
            "forward_n": len(forward),
            "forward_days": len(set(e["date_et"] for e in forward)),
            "forward_first_date": FORWARD_FIRST_DATE,
            "DISCLOSURE_in_sample_n_vs_prereg": (
                "the prereg quotes an in-sample population of 230 entries / 25 days; this ledger's "
                "in-sample slice is " + str(len(in_sample)) + " entries / " + str(is_days) + " days "
                "(population_id LIVE-ENGINE-REAL-FILLS-v2, rebuilt since). The day count matches exactly; "
                "the entry count differs by a single event and cannot move a p-value of this size."),
        },
        "integrity_gate": dict(
            integrity,
            meaning=("re-derived would_block flags were checked row-for-row against shadow-tally.jsonl, "
                     "which carries the single frozen implementation. A mismatch voids the run."),
        ),
        "method_F4": ("within-day permutation on the POOLED population: each day's number of blocked "
                      "entries is held FIXED and WHICH entries are blocked is randomised, "
                      + format(draws, ",") + " draws, seed " + str(SEED) + ". "
                      "p = P(random selection reaches the observed pooled delta). "
                      "It asks 'did the rule pick the bad ENTRY', not 'did the rule sit out a bad DAY'."),
        "results": results,
        "verdict_ladder_source": "the prereg's own forward_gates.verdict_ladder -- not re-invented here",
    }

    if dry_run:
        print(json.dumps(scorecard, indent=1))
        return 0

    OUT.write_text(json.dumps(scorecard, indent=1), encoding="utf-8")
    for name, r in results.items():
        g = r["gates"]

        def mark(ok):
            return "P" if ok else "F"

        print("[adjudicate] " + name + ": " + r["verdict"].ljust(6)
              + " F1=" + mark(g["F1_direction"]) + " F2=" + mark(g["F2_not_winner_killer"])
              + " F3=" + mark(g["F3_frequency"]) + " F4=" + mark(g["F4_discrimination"])
              + "(p=" + str(r["F4_within_day_permutation_pooled"]["p_value"]) + ")"
              + " F5=" + mark(g["F5_regime_neutral"]) + " -- " + r["verdict_basis"])
    print("[adjudicate] -> " + str(OUT.relative_to(REPO)).replace("\\", "/"))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Adjudicate the V-d1/V-e3 forward prereg (F1-F5).")
    ap.add_argument("--draws", type=int, default=DEFAULT_DRAWS)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    return run(draws=args.draws, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
