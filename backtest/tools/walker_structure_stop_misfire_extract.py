#!/usr/bin/env python
"""walker_structure_stop_misfire_extract.py -- WALKER-STRUCTURE-STOP-MISFIRE-MECHANISM
(2026-09-03), read-only diagnostic.

QUESTION: `walker_full_population_anchor.py` (WALKER-REANCHOR-FULL-ENGINE-POPULATION) reported
a 42-row stage-disagree bucket (n matches `stage_decomposition.stage_disagree.n` in the
published JSON exactly) carrying 56% of the pooled full-population dollar error, but that
tool's persisted JSON companion does NOT round-trip per-row detail -- `main()` only ever
stores `_bucket_stats(...)` aggregates into the output dict, never `hv["rows"]` itself (verified
by reading the published JSON: no "rows" key anywhere under "full_population"). The per-stage
docstring's claim that row detail "round-trips through the JSON companion's rows list" does not
match what `main()` actually writes.

REUSE, NOT REIMPLEMENTATION: calls `walker_full_population_anchor.run_via_harness_validation`
UNMODIFIED (same monkeypatch-load_anchor_sample / ARM2ACCOUNT-extension pattern), at
`exit_slippage=None` (the "default" setting the queue item's histogram is keyed off), and reads
`hv["rows"]` directly -- byte-identical resolution to the published run, just not thrown away
this time. Zero new network calls: same 96 (symbol,date) contracts, already disk-cached.

Writes ONLY a local JSON in the scratchpad for this session's own analysis; the queue item's
findings are reported in prose, not shipped as a new artifact (no analysis/deep-research file
requested for this row-level dump -- the WALKER-STRUCTURE-STOP-MISFIRE-MECHANISM.md/.json pair
covers the classification&mechanism instead).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest", "backtest/lib", "backtest/tools", "automation/state/fleet",
          "setup/scripts"):
    _full = str(REPO / _p)
    if _full not in sys.path:
        sys.path.insert(0, _full)

import walker_full_population_anchor as wfpa  # noqa: E402
import pdt_blocked_counterfactual as pbc  # noqa: E402


def main() -> int:
    latest = wfpa.latest_session_date()
    full_rows = wfpa.load_population_rows(wfpa.POPULATION_ARMS, wfpa.WINDOW_START, latest)
    print(f"[extract] population n_input_rows={len(full_rows)}", flush=True)

    hv = wfpa.run_via_harness_validation(full_rows, None)  # default slippage, same as histogram
    rows = hv.get("rows", [])
    print(f"[extract] hv rows priced: {len(rows)}", flush=True)

    disagree = [r for r in rows if str(r.get("recorded_stage") or "UNKNOWN")
               != str(r.get("walked_stage") or "UNKNOWN")]
    print(f"[extract] disagree n={len(disagree)} (expect 42, matches published "
         f"stage_decomposition.stage_disagree.n)", flush=True)

    struct_misfire = [r for r in disagree if r.get("walked_stage") == "structure_stop"]
    print(f"[extract] walked_stage==structure_stop AND disagree: n={len(struct_misfire)}",
         flush=True)

    out = {
        "n_disagree_total": len(disagree),
        "n_walked_structure_stop_disagree": len(struct_misfire),
        "disagree_rows": disagree,
        "recorded_stage_hist_of_disagree": {},
        "stop_mode_hist_of_disagree": {},
    }
    from collections import Counter
    out["recorded_stage_hist_of_disagree"] = dict(
        Counter(str(r.get("recorded_stage")) for r in disagree))
    out["stop_mode_hist_of_disagree"] = dict(
        Counter(str(r.get("stop_mode")) for r in disagree))
    out["arm_hist_of_disagree"] = dict(Counter(r.get("arm") for r in disagree))

    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        REPO / "backtest" / "tools" / "_scratch_misfire_rows.json")
    dest.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[extract] wrote {dest}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
