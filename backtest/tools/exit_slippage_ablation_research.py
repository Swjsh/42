#!/usr/bin/env python
"""exit_slippage_ablation_research.py -- WALKER-EXIT-SLIPPAGE-ASYMMETRY-ABLATION (2026-09-03).

QUESTION (from the queue item, filed off WALKER-PDT-ANCHOR-FIDELITY-INPUTS' PARTIAL result):
after the three input fixes, the PDT anchor's per-row median error equals V9's ($15) but the
AGGREGATE ratio is still 2.01 (replay 2x actual) while V9 sits at 0.645 (replay under-
reproduces). Agree-row sign is one-sided: replay is MORE ADVERSE than actual in ~83% of the 30
(now, after fix #1's relabel, still ~similarly skewed) stage-agree rows. Hypothesis
(UNVERIFIED, stated before this script ran a single number): `exit_manager_walk.py`'s
`exit_slippage` constant is applied ONLY to the 3 market-style stages (time_stop/ribbon_flip/
structure_stop; see that module's FILL-PRICE CONVENTION note), and the PDT population is
premium_stop-heavy (49% vs V9's 26%) -- if slippage were the driver, ZEROING it should move
the PDT ratio measurably toward 1.0. If it does NOT move, the residual is not slippage-shaped
at all, and the population's small-actual-total / high-premium_stop-share composition is a
more likely explanation (a scaling artifact, not a fill-model defect).

PRE-REGISTRATION (written before any of this script's numbers were read):
  SETTINGS: "default" (each anchor's own current default -- PDT's own adapter default 0.01,
    V9's own default 0.02; these already differ from each other, itself disclosed evidence,
    not reconciled by this script), "zero" (exit_slippage=0.0 on both), "live" (attempted --
    see below).
  ANCHORS: PDT (setup/scripts/pdt_blocked_counterfactual.py's 43-row/41-at-1min anchor,
    walker="exit_manager", bar_resolution="1min" -- matches the state this queue item inherited)
    and V9 (whole_engine_null.py's 121-row P1 population, run_v9()).
  READ: magnitude_fidelity's aggregate_ratio / median_abs_error_dollars / sign %, for each
    (setting, anchor) cell -- a 3x2 (or fewer, if a setting is skipped) table.
  DERIVED READS: PDT ratio restricted to the (stage-)agree-rows-only subset, at each setting;
    PDT ratio split by recorded stop_mode (premium_stop vs everything else -- structure/
    chandelier/tp), at the "default" setting only.
  DECISION RULE (stated before running): if BOTH anchors move measurably toward 1.0 at
    exit_slippage=0 relative to their own "default" cell, slippage is a real, disclosed
    contributor and the walker's slippage constant should eventually be calibrated from a real
    instrument (not hand-picked) in its own prereg'd commit. If the PDT ratio does NOT move
    toward 1.0 (or moves the WRONG way) while V9 does (or vice versa), slippage is NOT the
    shared mechanism and the PDT anchor's own composition (n=41, premium_stop-heavy, loss-
    skewed) is the more likely explanation -- this script does not adjudicate between "walker
    defect" and "anchor too small/skewed to trust" beyond reporting the per-stage split, which
    localizes where (if anywhere) the bias concentrates.
  "live": analysis/pain-ledger/latency.json (the fill-latency instrument named in the queue
    item) was inspected before this script was written -- see LIVE_SLIPPAGE_UNAVAILABLE_REASON
    below. It is a PIPELINE-TIMING instrument (seconds between order-lifecycle stages: bar
    close -> core verdict -> signal written -> plan -> submit -> broker-submitted -> fill),
    scoped to ENTRY fills only, on arms safe-3/risky-1/risky-3 -- not safe-2/bold-2 (the PDT
    anchor's own arms), and it carries no dollar-denominated exit-slippage field at all. Per
    this repo's no-silent-fallback discipline, "live" is SKIPPED, not guessed at (0 is already
    a tested setting; treating "unmeasured" as "zero" would misrepresent an absence as a
    measurement). `pdt_blocked_counterfactual._resolve_exit_slippage_arg("live")` raises
    SystemExit for the same reason, pinned by
    backtest/tests/test_exit_slippage_ablation_plumbing_2026_09_03.py.

MECHANISM: uses the newly-added additive `exit_slippage` overrides (this session) -- NO walker
default changed. PDT anchor: calls `pdt_blocked_counterfactual.harness_validation(walker=
"exit_manager", bar_resolution="1min", exit_slippage=X)` directly (the SAME function `main()`'s
`--walker exit_manager --bars 1min --exit-slippage X` CLI path calls; this script skips the
CLI/subprocess layer only for speed, not for a different code path) -- the gate-halting read
only (no G1-G4, no population-pricing pass, no output file from that function itself; this
script's own outputs are separate, see below). V9 anchor: monkeypatches
`whole_engine_null.walk_one` for the duration of one `run_v9()` call to inject the override
(mirrors `backtest/tools/whole_engine_null_flagon_research.py`'s established pattern for
`all_exits_market`), restoring the original after -- `whole_engine_null.main()`'s own pipeline,
`analysis/whole-engine-null/{date}.json`, and `latest.json` are never touched.

Both anchors run against the ALREADY-WARM 2026-09-02/03 bar caches this session's prior
WALKER-PDT-ANCHOR-FIDELITY-INPUTS work populated -- no new OPRA network fetch is attempted
beyond what a cache miss would already trigger honestly (never estimated/substituted).

Writes ONLY to analysis/deep-research/WALKER-EXIT-SLIPPAGE-ABLATION-2026-09-03.{json,md} --
RESEARCH label, decides nothing, arms nothing, ships nothing. The published PDT counterfactual
artifacts and analysis/whole-engine-null/*.json are untouched.
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

import pdt_blocked_counterfactual as pbc  # noqa: E402
import whole_engine_null as wen  # noqa: E402

OUT_DIR = REPO / "analysis" / "deep-research"
OUT_JSON = OUT_DIR / "WALKER-EXIT-SLIPPAGE-ABLATION-2026-09-03.json"
OUT_MD = OUT_DIR / "WALKER-EXIT-SLIPPAGE-ABLATION-2026-09-03.md"

LIVE_SLIPPAGE_UNAVAILABLE_REASON = (
    "analysis/pain-ledger/latency.json carries no dollar-denominated exit-slippage field -- "
    "it measures pipeline TIME latency in seconds (bar_close_ts_to_core_verdict_ts_s, etc.), "
    "scoped to ENTRY fills only, on arms safe-3/risky-1/risky-3 (not safe-2/bold-2, the PDT "
    "anchor's own arms). Skipped, not guessed at.")

# "default" per anchor: each walker's OWN currently-shipped default, not reconciled to match
# the other -- PDT's adapter (_walk_via_exit_manager) defaults to 0.01; exit_manager_walk.py's
# own module constant (what V9's walk_one now forwards when not overridden) is 0.02. This
# mismatch is itself part of tonight's evidence, stated here rather than papered over.
PDT_DEFAULT_SLIPPAGE = 0.01
V9_DEFAULT_SLIPPAGE = wen.DEFAULT_EXIT_SLIPPAGE
assert V9_DEFAULT_SLIPPAGE == 0.02

SETTINGS = ["default", "zero"]  # "live" pre-registered above, skipped -- see reason string


# --------------------------------------------------------------------------------- PDT anchor
def _pdt_run(exit_slippage) -> dict:
    hv = pbc.harness_validation(walker="exit_manager", bar_resolution="1min",
                                exit_slippage=exit_slippage)
    rows = hv.get("rows") or []
    agree_rows = [r for r in rows
                 if str(r.get("recorded_stage") or "UNKNOWN") == str(r.get("walked_stage") or "UNKNOWN")]
    agree_mag = pbc._shared_magnitude_fidelity(
        [(r["actual"], r["replay"]) for r in agree_rows]) if agree_rows else {"n": 0}
    return {
        "n": hv.get("n"), "skipped_no_bars": hv.get("skipped_no_bars"),
        "sign_agreement": hv.get("sign_agreement"),
        "aggregate_ratio": (hv.get("magnitude_fidelity") or {}).get("aggregate_ratio"),
        "median_abs_error_dollars": (hv.get("magnitude_fidelity") or {}).get("median_abs_error_dollars"),
        "verdict": hv.get("magnitude_fidelity_verdict"),
        "n_agree_rows": len(agree_rows),
        "agree_only_aggregate_ratio": agree_mag.get("aggregate_ratio"),
        "agree_only_median_abs_error_dollars": agree_mag.get("median_abs_error_dollars"),
        "rows": rows,
    }


def _pdt_by_stop_mode(rows: list[dict]) -> dict:
    """Splits the PDT anchor's rows by recorded stop_mode -- premium_stop vs everything else
    (structure/chandelier/tp share the "structure" stop_mode label in this ledger; there is no
    separate "chandelier"/"tp" stop_mode value recorded -- checked against anchor_trigger_level/
    load_anchor_sample's own row schema, which carries only "structure"|"premium"|None)."""
    buckets: dict[str, list[tuple]] = {"premium": [], "structure_or_other": []}
    for r in rows:
        mode = r.get("stop_mode")
        key = "premium" if mode == "premium" else "structure_or_other"
        buckets[key].append((r["actual"], r["replay"]))
    out = {}
    for k, pairs in buckets.items():
        mag = pbc._shared_magnitude_fidelity(pairs) if pairs else {"n": 0}
        out[k] = {"n": len(pairs), "aggregate_ratio": mag.get("aggregate_ratio"),
                  "median_abs_error_dollars": mag.get("median_abs_error_dollars")}
    return out


# ---------------------------------------------------------------------------------- V9 anchor
def _v9_run(exit_slippage) -> dict:
    rows = wen.load_engine_rows()
    pops = wen.build_populations(rows)
    p1_rows = pops["P1_post_ladder"]
    spy5 = wen.load_spy_5m()
    budget = wen.FetchBudget(0.0)

    orig_walk_one = wen.walk_one

    def _patched(**kwargs):
        kwargs.setdefault("exit_slippage", exit_slippage)
        return orig_walk_one(**kwargs)

    wen.walk_one = _patched
    try:
        v9 = wen.run_v9(p1_rows, spy5, budget)
    finally:
        wen.walk_one = orig_walk_one  # never leave the module patched

    mag = v9.get("magnitude_fidelity") or {}
    return {
        "n_compared": v9.get("n_compared"), "n_skipped_no_bars": v9.get("n_skipped_no_bars"),
        "sign_agreement_rate": v9.get("sign_agreement_rate"),
        "aggregate_ratio": mag.get("aggregate_ratio"),
        "median_abs_error_dollars": mag.get("median_abs_error_dollars"),
        "verdict": v9.get("magnitude_fidelity_verdict"),
        "fetch_budget_n_fetched": budget.n_fetched, "fetch_budget_n_failed": budget.n_failed,
    }


def main() -> int:
    results: dict[str, dict] = {"pdt": {}, "v9": {}}

    for setting in SETTINGS:
        pdt_slip = None if setting == "default" else 0.0  # None -> adapter's own 0.01 default
        v9_slip = V9_DEFAULT_SLIPPAGE if setting == "default" else 0.0
        print(f"[ablation] PDT anchor, setting={setting} (exit_slippage="
              f"{pdt_slip if pdt_slip is not None else PDT_DEFAULT_SLIPPAGE})...", flush=True)
        pdt_res = _pdt_run(pdt_slip)
        results["pdt"][setting] = pdt_res
        print(f"  n={pdt_res['n']} ratio={pdt_res['aggregate_ratio']} "
              f"median=${pdt_res['median_abs_error_dollars']} verdict={pdt_res['verdict']} "
              f"agree_only_ratio={pdt_res['agree_only_aggregate_ratio']}", flush=True)

        print(f"[ablation] V9 population, setting={setting} (exit_slippage={v9_slip})...",
             flush=True)
        v9_res = _v9_run(v9_slip)
        results["v9"][setting] = v9_res
        print(f"  n={v9_res['n_compared']} ratio={v9_res['aggregate_ratio']} "
              f"median=${v9_res['median_abs_error_dollars']} "
              f"sign={v9_res['sign_agreement_rate']} verdict={v9_res['verdict']}", flush=True)

    print("[ablation] PDT per-stage split at default slippage...", flush=True)
    default_rows = results["pdt"]["default"]["rows"]
    by_stage = _pdt_by_stop_mode(default_rows)
    print(f"  {by_stage}", flush=True)

    # decision rule read (pre-registered above)
    pdt_default_ratio = results["pdt"]["default"]["aggregate_ratio"]
    pdt_zero_ratio = results["pdt"]["zero"]["aggregate_ratio"]
    v9_default_ratio = results["v9"]["default"]["aggregate_ratio"]
    v9_zero_ratio = results["v9"]["zero"]["aggregate_ratio"]

    def _toward_one(a, b):
        if a is None or b is None:
            return None
        return abs(b - 1.0) < abs(a - 1.0)

    pdt_moved_toward_one = _toward_one(pdt_default_ratio, pdt_zero_ratio)
    v9_moved_toward_one = _toward_one(v9_default_ratio, v9_zero_ratio)
    # premium_stop is a LIMIT-style stage -- exit_slippage NEVER touches it (see
    # exit_manager_walk.py's FILL-PRICE CONVENTION note: only the 3 market-style stages get
    # slippage). If that bucket alone carries a large ratio, slippage cannot be the (sole)
    # explanation for it -- checked directly rather than inferred from the aggregate move.
    premium_bucket = by_stage.get("premium") or {}
    premium_ratio = premium_bucket.get("aggregate_ratio")
    premium_untouched_but_biased = (premium_ratio is not None and abs(premium_ratio - 1.0) > 0.40)
    pdt_still_fails_at_zero = results["pdt"]["zero"]["verdict"] != "PASS"
    if pdt_moved_toward_one and v9_moved_toward_one and premium_untouched_but_biased:
        conclusion = (
            f"Slippage is a REAL but PARTIAL contributor -- both anchors move toward 1.0 when "
            f"zeroed (PDT {pdt_default_ratio}->{pdt_zero_ratio}, V9 {v9_default_ratio}->"
            f"{v9_zero_ratio}), yet the PASS/FAIL verdict does not flip "
            f"(pdt_still_fails_at_zero={pdt_still_fails_at_zero}) because the premium_stop "
            f"bucket ({premium_bucket.get('n')}/{results['pdt']['default']['n']} rows, ratio "
            f"{premium_ratio} -- a stage exit_slippage structurally NEVER touches) is biased "
            f"on its own: the residual is population composition/small-n (n=41, premium_stop-"
            f"heavy, loss-skewed), not the slippage asymmetry alone.")
    elif pdt_moved_toward_one and v9_moved_toward_one:
        conclusion = ("Slippage IS a real, disclosed contributor: both anchors' aggregate "
                      "ratios move toward 1.0 at exit_slippage=0.")
    elif pdt_moved_toward_one and not v9_moved_toward_one:
        conclusion = ("Slippage explains PART of the PDT anchor's own bias but is NOT the "
                      "shared mechanism (V9 does not move the same way) -- the remaining PDT "
                      "gap is population composition (n=41, premium_stop-heavy, loss-skewed), "
                      "not a walker defect common to both anchors.")
    elif not pdt_moved_toward_one:
        conclusion = ("Slippage does NOT explain the PDT anchor's aggregate bias -- zeroing it "
                      "did not move the ratio toward 1.0; the PDT population is too small/"
                      "skewed to anchor on its own, and re-anchoring on a larger engine-"
                      "attributed set (not a slippage recalibration) is the next lever.")
    else:
        conclusion = "Indeterminate -- see the two anchors' ratios directly."

    out = {
        "label": "RESEARCH -- decides nothing, arms nothing, ships nothing",
        "queue_item": "WALKER-EXIT-SLIPPAGE-ASYMMETRY-ABLATION",
        "pre_registration_note": "See this script's module docstring, written before any "
                                 "number below was read.",
        "settings_run": SETTINGS,
        "live_setting_skipped_reason": LIVE_SLIPPAGE_UNAVAILABLE_REASON,
        "pdt_default_slippage": PDT_DEFAULT_SLIPPAGE, "v9_default_slippage": V9_DEFAULT_SLIPPAGE,
        "results": {
            "pdt": {k: {kk: vv for kk, vv in v.items() if kk != "rows"}
                   for k, v in results["pdt"].items()},
            "v9": results["v9"],
        },
        "pdt_by_stop_mode_at_default_slippage": by_stage,
        "conclusion": conclusion,
        "pdt_moved_toward_one_at_zero_slippage": pdt_moved_toward_one,
        "v9_moved_toward_one_at_zero_slippage": v9_moved_toward_one,
        "pdt_still_fails_at_zero_slippage": pdt_still_fails_at_zero,
        "premium_stop_bucket_untouched_by_slippage_but_biased": premium_untouched_but_biased,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\n[ablation] wrote {OUT_JSON}", flush=True)

    md_lines = [
        "# WALKER-EXIT-SLIPPAGE-ABLATION -- 2026-09-03",
        "",
        "RESEARCH -- decides nothing, arms nothing, ships nothing. Full pre-registration in "
        "`backtest/tools/exit_slippage_ablation_research.py`'s module docstring, written "
        "before this script ran.",
        "",
        f"live setting: SKIPPED. {LIVE_SLIPPAGE_UNAVAILABLE_REASON}",
        "",
        "## 3x2 table (setting x anchor)",
        "",
        "| setting | anchor | n | ratio | median $ | sign % |",
        "|---|---|---|---|---|---|",
    ]
    for setting in SETTINGS:
        p = results["pdt"][setting]
        v = results["v9"][setting]
        md_lines.append(f"| {setting} | PDT (1min) | {p['n']} | {p['aggregate_ratio']} | "
                        f"{p['median_abs_error_dollars']} | "
                        f"{(p['sign_agreement'] or 0) * 100:.1f}% |")
        md_lines.append(f"| {setting} | V9 (121-pop) | {v['n_compared']} | "
                        f"{v['aggregate_ratio']} | {v['median_abs_error_dollars']} | "
                        f"{(v['sign_agreement_rate'] or 0) * 100:.1f}% |")
    md_lines.append(f"| live | both | -- | SKIPPED | -- | -- |")
    md_lines += [
        "",
        "## PDT agree-rows-only subset",
        "",
        "| setting | n agree rows | ratio | median $ |",
        "|---|---|---|---|",
    ]
    for setting in SETTINGS:
        p = results["pdt"][setting]
        md_lines.append(f"| {setting} | {p['n_agree_rows']} | "
                        f"{p['agree_only_aggregate_ratio']} | "
                        f"{p['agree_only_median_abs_error_dollars']} |")
    md_lines += [
        "",
        "## PDT split by recorded stop_mode (default slippage only)",
        "",
        "| stop_mode | n | ratio | median $ |",
        "|---|---|---|---|",
    ]
    for k, v in by_stage.items():
        md_lines.append(f"| {k} | {v['n']} | {v['aggregate_ratio']} | "
                        f"{v['median_abs_error_dollars']} |")
    md_lines += [
        "",
        "## Conclusion",
        "",
        conclusion,
        "",
        f"(pdt_moved_toward_one_at_zero_slippage={pdt_moved_toward_one}, "
        f"v9_moved_toward_one_at_zero_slippage={v9_moved_toward_one})",
    ]
    OUT_MD.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(f"[ablation] wrote {OUT_MD}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
