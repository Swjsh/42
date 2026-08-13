#!/usr/bin/env python3
"""parity_check.py -- does the BACKTEST model what LIVE actually does?

WHY THIS EXISTS (J directive, 2026-08-12: "we've surfaced things that should have been found").

On 2026-08-12 we discovered that the free-model veto had killed 132 of 656 live ENTER verdicts
(20.1%) over 38 days -- and that NO backtest, replay or simulator in the repo modelled it. Every
backtest number ever produced described an engine that took trades production silently refused.
Nothing flagged this. It was found by a human asking a question at midnight.

It was not an isolated case. The same audit found the same shape repeatedly:
  * SKIP_STRUCTURE_VETO   -- enforced live inside engine_cli.decide_payload, which
                             orchestrator.run_backtest never calls. No backtest kwarg can enable it.
  * RISK_DENY_PDT / _SETTLEMENT / _RISK_CAP -- orchestrator's risk_gate call explicitly neutralises
                             kill-switch, PDT and prior-stops.
  * NOT_FLAT              -- broker position state; structurally absent from a single-threaded sim.
  * SKIP_NO_LEVELS        -- deliberately kept OUT of shared code, so no replay tool can model a
                             stale-key-levels refusal.

Every one of these makes backtests OPTIMISTIC IN THE SAME DIRECTION: the harness takes trades that
production would have refused. That is the mechanism behind "armed on an 8/8-gate backtest at
+$32-79/trade, then 0-for-12 live" -- which the repo's own queue calls a falsification of the
VALIDATION PIPELINE rather than two unlucky setups.

WHAT THIS DOES

Ground truth is the LIVE LEDGER, not the source. Reading source only finds refusals someone wrote
as a literal; the live engine also emits actions dynamically (`rec["action"] = v` from the engine
verdict, and `rec["exec"].get("status")` from the executor), so a source-only scan is blind to most
of the vocabulary -- 7 literals versus 20+ actually observed. So:

  1. Harvest every DISTINCT action the live engine has actually emitted, with frequency.
  2. Look each up in automation/state/parity-registry.json.
  3. Anything the live engine emits that the registry does not classify is UNCLASSIFIED -> RED.

An UNCLASSIFIED action is the alarm. It means the live engine grew a new behaviour and nobody
decided whether the backtest can reproduce it. That is exactly the state the free-model veto sat in
for 38 days.

Severity is DATA-DRIVEN, never asserted: a divergence's weight is its share of ACTIONABLE ticks
(non-HOLD), because ~91% of ticks are HOLD and including them makes every divergence look
negligible.

Reads only. Writes nothing. No network. $0. Fails open -- never raises into a caller.

Usage:
    python setup/scripts/parity_check.py           # human table
    python setup/scripts/parity_check.py --json    # machine-readable
    python setup/scripts/parity_check.py --strict  # exit 1 if anything is UNCLASSIFIED
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "automation" / "state" / "core-decisions.jsonl"
REGISTRY = REPO / "automation" / "state" / "parity-registry.json"

# Actions that are OUTCOMES, not refusals. A backtest is not expected to "model" HOLD -- it is the
# absence of a signal, which every harness reproduces by construction.
NON_REFUSAL = {"HOLD", "PLACED", "PERCEPTION_ONLY"}

# Registry status vocabulary.
MODELED = "MODELED"                                # backtest reproduces it
LIVE_ONLY_INTENTIONAL = "LIVE_ONLY_INTENTIONAL"    # live-only BY DESIGN, no backtest equivalent needed
LIVE_ONLY_DIVERGENCE = "LIVE_ONLY_DIVERGENCE"      # live refuses, backtest cannot -> backtest optimistic
VALID_STATUS = {MODELED, LIVE_ONLY_INTENTIONAL, LIVE_ONLY_DIVERGENCE}


ENTER_VERDICTS = {"ENTER_BULL", "ENTER_BEAR"}


def _harvest_live_actions(path: Path = LEDGER) -> tuple[Counter, int, Counter]:
    """Distinct actions the live engine has ACTUALLY emitted, with counts.

    The ledger rather than the source, deliberately: heartbeat_core assigns `rec["action"]` from a
    literal in only 7 places, but also from the engine verdict and from the executor's status, so
    a source scan sees a small minority of the real vocabulary.

    THIRD RETURN VALUE, added 2026-08-12 after this tool's own first run misled me. A ledger row
    carries BOTH `verdict` (what the shared engine decided) and `action` (the final outcome), and
    they are DIFFERENT LAYERS. Counting rows alone conflates them:

        SKIP_STALE_TRIGGER  400 rows, but only  10 sat on an ENTER verdict (2.5%)

    The other 390 stamped ticks that were already HOLD or already SKIP_* -- the action changed the
    LABEL, not the OUTCOME. Weighting it by row count made it the single largest apparent
    divergence at 18.16% of decisions when its true blocking impact is 10 trades. A 40x overstate.

    So `blocked_enter` counts only rows where the engine said ENTER and the action was something
    else -- refusals that demonstrably stopped a trade. Note this is the right denominator for
    POST-VERDICT refusals (heartbeat/executor layer, which run 100% on ENTER rows) and is
    structurally 0 for ENGINE-SIDE gates, where the verdict IS the refusal and no ENTER ever
    appears. Both are real refusals; they are simply measured at different layers, and the report
    must not pretend one number covers both.
    """
    counts: Counter = Counter()
    blocked: Counter = Counter()
    total = 0
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except (ValueError, TypeError):
                    continue
                total += 1
                action = str(rec.get("action") or "(none)")
                counts[action] += 1
                if str(rec.get("verdict") or "") in ENTER_VERDICTS and action != "PLACED":
                    blocked[action] += 1
    except OSError:
        return Counter(), 0, Counter()
    return counts, total, blocked


def _load_registry(path: Path = REGISTRY) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("actions", {})
    except (OSError, ValueError, TypeError):
        return {}


def evaluate(counts: Counter, total: int, registry: dict,
             blocked: Counter | None = None) -> dict:
    """Classify every observed action. Pure -- no I/O, so it is trivially testable."""
    actionable = total - counts.get("HOLD", 0)
    blocked = blocked or Counter()
    n_enter_blocked = sum(blocked.values())
    rows = []
    for action, n in counts.most_common():
        if action in NON_REFUSAL:
            continue
        entry = registry.get(action)
        status = (entry or {}).get("status", "UNCLASSIFIED")
        if status not in VALID_STATUS:
            status = "UNCLASSIFIED"
        rows.append({
            "action": action,
            "count": n,
            "pct_actionable": round(100.0 * n / actionable, 2) if actionable else 0.0,
            "status": status,
            "reason": (entry or {}).get("reason", ""),
            # Rows where the ENGINE said ENTER and this action stopped it. The honest measure of
            # a POST-VERDICT refusal's blocking impact; structurally 0 for engine-side gates.
            "blocked_enter": blocked.get(action, 0),
        })

    unclassified = [r for r in rows if r["status"] == "UNCLASSIFIED"]
    divergences = [r for r in rows if r["status"] == LIVE_ONLY_DIVERGENCE]

    # REPORT THESE SEPARATELY, NEVER AS ONE BLENDED NUMBER.
    # The first version of this tool summed divergence + unclassified into a single
    # "97.97% unmodelled" headline. That is technically defensible ("unknown is not safe") and
    # badly misleading: most UNCLASSIFIED rows are probably gates.py verdicts, which IS shared
    # code and therefore genuinely modelled. Blending a MEASURED 16% with an UNMEASURED 82% into
    # one scary number is precisely the overclaim this repo keeps having to retract. Confirmed
    # and unknown are different epistemic states and get different fields.
    confirmed_pct = round(sum(r["pct_actionable"] for r in divergences), 2)
    unknown_pct = round(sum(r["pct_actionable"] for r in unclassified), 2)
    # Trades actually stopped by a refusal no backtest can reproduce -- the number that survives
    # the row-count/outcome conflation described in _harvest_live_actions.
    confirmed_blocked = sum(r["blocked_enter"] for r in divergences)
    unknown_blocked = sum(r["blocked_enter"] for r in unclassified)

    if unclassified:
        verdict = "RED"
    elif divergences:
        verdict = "AMBER"
    else:
        verdict = "GREEN"

    return {
        "verdict": verdict,
        "total_ticks": total,
        "actionable_ticks": actionable,
        "confirmed_unmodelled_pct": confirmed_pct,
        "unknown_pct": unknown_pct,
        "n_unclassified": len(unclassified),
        "n_divergences": len(divergences),
        "enter_verdicts_blocked_total": n_enter_blocked,
        "confirmed_blocked_enters": confirmed_blocked,
        "unknown_blocked_enters": unknown_blocked,
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Live-vs-backtest decision parity.")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when any live action is UNCLASSIFIED")
    args = ap.parse_args(argv)

    counts, total, blocked = _harvest_live_actions()
    if total == 0:
        print("parity_check: live ledger unreadable or empty -- cannot assess. "
              f"(looked in {LEDGER})")
        return 0

    result = evaluate(counts, total, _load_registry(), blocked)

    if args.json:
        print(json.dumps(result, indent=2))
        return 1 if (args.strict and result["n_unclassified"]) else 0

    print(f"LIVE/BACKTEST DECISION PARITY -- {result['verdict']}")
    print(f"  {result['actionable_ticks']:,} actionable live decisions "
          f"(of {result['total_ticks']:,} ticks; HOLD excluded)")
    print(f"  {result['confirmed_unmodelled_pct']}% CONFIRMED unmodellable by any backtest "
          f"(measured, {result['n_divergences']} actions)")
    print(f"  {result['unknown_pct']}% UNKNOWN -- not yet classified either way "
          f"({result['n_unclassified']} actions). Unknown is not the same as broken.")
    print()
    print(f"  {result['confirmed_blocked_enters']} ENTER verdicts were actually STOPPED by a "
          f"confirmed divergence (of {result['enter_verdicts_blocked_total']} blocked overall) -- "
          f"row counts overstate blocking impact, see BLOCK column")
    print()
    print(f"{'STATUS':<24} {'ACTION':<32} {'N':>6} {'%ACT':>7} {'BLOCK':>6}")
    print("-" * 82)
    for r in result["rows"]:
        print(f"{r['status']:<24} {r['action'][:32]:<32} {r['count']:>6} "
              f"{r['pct_actionable']:>6.2f}% {r['blocked_enter']:>6}")

    if result["n_unclassified"]:
        print(f"\n!! {result['n_unclassified']} UNCLASSIFIED action(s). Each is a live behaviour "
              f"nobody has decided the backtest can reproduce.")
        print(f"   Classify in {REGISTRY.relative_to(REPO)} as one of: "
              f"{MODELED} / {LIVE_ONLY_INTENTIONAL} / {LIVE_ONLY_DIVERGENCE}.")
        print("   This is exactly the state VETOED_BY_MODELS sat in, unnoticed, for 38 days.")
    return 1 if (args.strict and result["n_unclassified"]) else 0


if __name__ == "__main__":  # pragma: no cover
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 -- fail open, never raise into a caller
        print(f"parity_check: non-fatal error: {exc}")
        sys.exit(0)
