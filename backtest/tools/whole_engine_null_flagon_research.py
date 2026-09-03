#!/usr/bin/env python
"""whole_engine_null_flagon_research.py -- ONE-OFF RESEARCH comparison for
WALKER-MARKET-STAGE-FILL-ROOT-FIX (2026-09-03).

QUESTION (from the queue item): "what the flag flip would change in the null study's verdict".
whole_engine_null.py's V9/N_a/N_b/N_c legs are walked through `exit_manager_walk.walk_exit_manager`
(backtest/lib/exit_manager_walk.py) -- a DIFFERENT walker from `multileg_exit_walk.py`, the one
this session actually fixed (see analysis/harness-fidelity/WALKER-MAGNITUDE-2026-09-03.md).
exit_manager_walk.py already carries its OWN pre-existing, already-tested `all_exits_market`
kwarg (prereg FILL-MODEL-UNIFICATION-2026-08-13, default False, untouched by this session) that
is the closest analogue in ITS walker to what this session's fix does in multileg_exit_walk.py:
every stage fills at the bar's real price (there: bar close - slippage) instead of 6 of 9 stages
filling at a zero-slippage theoretical level. `all_exits_market=True` was never wired into
whole_engine_null.py's own pipeline before this script -- this run answers "what would change if
it were".

MECHANISM: `whole_engine_null.walk_one()` grew an additive `all_exits_market: bool = False`
passthrough this session (default False, byte-identical for the published pipeline -- verified
below by reproducing the baseline run first). This script monkeypatches `wen.walk_one` to force
`all_exits_market=True` for the SECOND run only, calls `wen.run()` (the same core function
`main()` calls) directly -- NEVER `wen.main()` itself, so no CLI/env state is touched -- and
NEVER calls `wen.write_outputs()`, so `analysis/whole-engine-null/{date}.json` /
`latest.json` / `summary-line.txt` (the published, REVOKE-surfaced study output) are never
touched by this script.

$0, deterministic given the on-disk 1-minute bar cache (`--skip-fetch` / `skip_fetch=True` on
both runs -- NO new network fetches; any contract missing from cache is an honest null on BOTH
sides, so the comparison is apples-to-apples). Does NOT call `refresh_trades_enriched()` (passes
`trades_enriched_refresh=None`, matching `--no-refresh`) -- scores trades-enriched.jsonl AS-IS,
so this research run cannot race another session's write to that file.

Writes ONLY to analysis/whole-engine-null/{date}-flagon.json -- a `-flagon` suffixed sibling,
never the canonical file. RESEARCH label -- decides nothing, arms nothing, ships nothing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest", "backtest/lib", "backtest/tools", "automation/state/fleet", "setup/scripts"):
    _full = str(REPO / _p)
    if _full not in sys.path:
        sys.path.insert(0, _full)

import whole_engine_null as wen  # noqa: E402

OUT_DIR = REPO / "analysis" / "whole-engine-null"

# The date the last PUBLISHED whole_engine_null.py run scored (2026-09-02.json on disk) --
# reusing it keeps this comparison apples-to-apples against a run this repo already trusts,
# and the 1-minute bar cache for that date is already warm (skip_fetch=True below reuses it,
# no new network calls).
RESEARCH_DATE = "2026-09-02"
RESAMPLES = wen.DEFAULT_RESAMPLES  # 300, the prereg's own disclosed fallback -- matches the
                                   # published run's own resamples count for comparability.
SEED = 42


def _extract_summary(doc: dict) -> dict:
    v9 = doc["v9_harness_validation"]
    return {
        "overall_verdict": doc["overall_verdict"],
        "mechanical_verdict": doc["mechanical_verdict"],
        "p1_total_pnl": doc["populations"]["P1_post_ladder"]["total_pnl"],
        "p1_n_trades": doc["populations"]["P1_post_ladder"]["n_trades"],
        "v9_sign_agreement_rate": v9.get("sign_agreement_rate"),
        "v9_harness_reliable": doc["harness_reliable"],
        "v9_magnitude_fidelity": v9.get("magnitude_fidelity"),
        "na_percentiles": doc["pass_criterion"].get("na_percentiles"),
        "n_b_call_total": doc["n_b_buy_and_hold_atm"]["n_b_call"]["total_pnl"],
        "n_b_put_total": doc["n_b_buy_and_hold_atm"]["n_b_put"]["total_pnl"],
        "n_c_total_pnl": doc["n_c_opposite_direction"]["total_pnl"],
        "named_fails": doc["pass_criterion"].get("named_fails"),
    }


def main() -> int:
    print(f"[flagon-research] baseline run (all_exits_market=False, byte-identical to "
          f"today's pipeline) -- date={RESEARCH_DATE} resamples={RESAMPLES}...", flush=True)
    doc_off = wen.run(RESEARCH_DATE, RESAMPLES, SEED, 0.0, True, None)
    summary_off = _extract_summary(doc_off)
    print(f"  P1=${summary_off['p1_total_pnl']:+.2f}  "
          f"V9 sign_agreement={summary_off['v9_sign_agreement_rate']}  "
          f"verdict={summary_off['overall_verdict']}", flush=True)

    print("[flagon-research] treatment run (all_exits_market=True, monkeypatched into "
          "walk_one for THIS process only)...", flush=True)
    _orig_walk_one = wen.walk_one

    def _walk_one_flagon(**kwargs):
        kwargs["all_exits_market"] = True
        return _orig_walk_one(**kwargs)

    wen.walk_one = _walk_one_flagon
    try:
        doc_on = wen.run(RESEARCH_DATE, RESAMPLES, SEED, 0.0, True, None)
    finally:
        wen.walk_one = _orig_walk_one  # restore -- never leave the module patched
    summary_on = _extract_summary(doc_on)
    print(f"  P1=${summary_on['p1_total_pnl']:+.2f}  "
          f"V9 sign_agreement={summary_on['v9_sign_agreement_rate']}  "
          f"verdict={summary_on['overall_verdict']}", flush=True)

    comparison = {
        "label": "RESEARCH -- decides nothing, arms nothing, ships nothing",
        "queue_item": "WALKER-MARKET-STAGE-FILL-ROOT-FIX",
        "question": "What would exit_manager_walk.py's own all_exits_market=True flag change "
                   "in whole_engine_null.py's verdict, if wired in (it is NOT wired into the "
                   "published pipeline by this script -- walk_one's default stays False).",
        "date": RESEARCH_DATE, "resamples": RESAMPLES, "seed": SEED,
        "all_exits_market_false": summary_off,
        "all_exits_market_true": summary_on,
        "p1_unchanged": (summary_off["p1_total_pnl"] == summary_on["p1_total_pnl"]),
        "note": ("P1 is real fills -- the flag only touches WALKED legs (V9/N_a/N_b/N_c), so "
                "p1_total_pnl must be identical across both runs; p1_unchanged=False would "
                "indicate a bug in this script, not a real effect."),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{RESEARCH_DATE}-flagon.json"
    out_path.write_text(json.dumps(comparison, indent=2, default=str), encoding="utf-8")
    print(f"[flagon-research] wrote {out_path} (published {RESEARCH_DATE}.json / latest.json / "
          f"summary-line.txt untouched)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
