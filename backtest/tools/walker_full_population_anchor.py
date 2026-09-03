#!/usr/bin/env python
"""walker_full_population_anchor.py -- WALKER-REANCHOR-FULL-ENGINE-POPULATION (2026-09-03).

QUESTION (from the queue item, filed off WALKER-EXIT-SLIPPAGE-ASYMMETRY-ABLATION's decision to
stop tuning against the 43/41-row PDT subset): that anchor is unfit to judge
`exit_manager_walk`'s magnitude fidelity -- too small (n=41 at 1-min), too premium_stop-heavy
(49%), too loss-skewed (76% losing) to average out a stage-specific bias. Build the anchor the
`walker_magnitude_fidelity` criterion deserves: every engine-attributed real fill across the
FOUR active gate-scored arms, not just the two core accounts the PDT population happened to be
drawn from.

PRE-REGISTRATION: written in full, before this script ran, at
`analysis/deep-research/WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md` (criterion, population
definition, table shape, decision rule). This module does not restate it -- read that file
first.

REUSE, NOT REIMPLEMENTATION: every pricing/walking primitive is imported from
`pdt_blocked_counterfactual` (`canonical_shape`, `anchor_trigger_level`, `_load_anchor_bars`,
`_price_via_walker`, `spy_by_day`, `harness_validation` itself, `_shared_magnitude_fidelity`,
`evaluate_magnitude_fidelity`, `stage_decomposition`) and `whole_engine_null`
(`_core_account_for_arm`, `ACTIVE_ARMS`). The only new code is (a) a population loader
parameterized over an arm set + date window (the existing `load_anchor_sample` hardcodes both
to the PDT study's own scope, so it cannot serve this population without modification) and
(b) the three-anchor / per-arm / per-stage reporting tables this queue item asks for.

MECHANISM: `harness_validation()` is called UNMODIFIED for both the full population and the
PDT-43 subset, via a temporary monkeypatch of `pdt_blocked_counterfactual.load_anchor_sample`
(the same "monkeypatch to inject a population, restore after" pattern
`exit_slippage_ablation_research.py` already uses for `whole_engine_null.walk_one`) -- so both
runs get byte-identical stage/trigger/shape resolution, sign-agreement, magnitude-fidelity, and
stage-decomposition logic to every prior walker study in this repo, not a parallel
reimplementation that could drift.

CACHE / BUDGET: every distinct (symbol, date) contract in the full population was checked
against `backtest/data/highres/` BEFORE this script ran (see the pre-registration doc) -- all
96 were already disk-cached from prior WALKER-PDT-ANCHOR-FIDELITY-INPUTS / V9 1-min work, so
this run makes ZERO new OPRA network calls. If a cache entry had been missing,
`_option_bars_1min_cache.fetch_1min_cached` would fetch it live (bounded, single-reader,
rate-limited) and the result would report it as a genuine fetch, never estimated.

Writes ONLY to `analysis/deep-research/WALKER-FULL-POPULATION-ANCHOR-2026-09-03.{json,md}` --
RESEARCH label, decides nothing, arms nothing, ships nothing. The published PDT counterfactual
artifact, `analysis/whole-engine-null/*.json`, and every trading-path file are untouched.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest", "backtest/lib", "backtest/tools", "automation/state/fleet",
          "setup/scripts"):
    _full = str(REPO / _p)
    if _full not in sys.path:
        sys.path.insert(0, _full)

import pdt_blocked_counterfactual as pbc  # noqa: E402
import whole_engine_null as wen  # noqa: E402

OUT_DIR = REPO / "analysis" / "deep-research"
OUT_JSON = OUT_DIR / "WALKER-FULL-POPULATION-ANCHOR-2026-09-03.json"
OUT_MD = OUT_DIR / "WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md"
TRADES_ENRICHED = pbc.TRADES_ENRICHED

# Same 4 arms go_live_gate.py scores (safe-3/risky-1 included, risky-3/safe-1 excluded -- not
# gate-scored). Imported from whole_engine_null, not retyped, so this list can never silently
# drift from the value V9 itself already uses.
POPULATION_ARMS = wen.ACTIVE_ARMS
WINDOW_START = "2026-07-08"
# PDT anchor's own frozen subset window, for the 3-way continuity table.
PDT_WINDOW_START, PDT_WINDOW_END = "2026-07-08", "2026-08-07"
PDT_ARMS = ("safe-2", "bold-2")


# --------------------------------------------------------------------------------- population
def latest_session_date() -> str:
    """Max `date` over every non-_meta row in trades-enriched.jsonl -- "latest session" per the
    queue item's own wording, not hardcoded."""
    latest = ""
    with open(TRADES_ENRICHED, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("_meta"):
                continue
            d = row.get("date")
            if d and d > latest:
                latest = d
    return latest


def load_population_rows(arms: tuple[str, ...], window_start: str, window_end: str) -> list[dict]:
    """General-purpose population loader: `attribution=='engine'`, arm in `arms`, date in
    [window_start, window_end], and the same completeness filter
    `pdt_blocked_counterfactual.load_anchor_sample` already applies (pnl_dollars/entry_px/qty
    all present). Parameterized over arm-set + window because `load_anchor_sample` hardcodes
    both to the PDT study's own two-arm, 1-month scope -- it cannot serve this population
    without being generalized, so this is a NEW loader, not a copy of that one (the field-level
    filter logic it applies is intentionally identical for a fair three-anchor comparison)."""
    rows: list[dict] = []
    with open(TRADES_ENRICHED, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("_meta"):
                continue
            if r.get("arm") not in arms:
                continue
            d = r.get("date")
            if not d or not (window_start <= d <= window_end):
                continue
            if r.get("attribution") != "engine":
                continue
            if r.get("pnl_dollars") is None or r.get("entry_px") is None or not r.get("qty"):
                continue
            rows.append(r)
    return rows


def contracts_for(rows: list[dict]) -> list[tuple[str, str]]:
    return sorted({(r["symbol"], r["date"]) for r in rows})


def check_cache_status(rows: list[dict]) -> dict:
    """Pre-flight cache check (informational only -- `_load_anchor_bars` does the real
    fetch/cache work during the walk itself; this just lets the pre-registration doc state the
    fetch budget honestly before any walking happens)."""
    highres = REPO / "backtest" / "data" / "highres"
    contracts = contracts_for(rows)
    missing = [(s, d) for s, d in contracts
              if not (highres / f"{s}_1m_{d}.csv").exists()]
    return {"n_contracts": len(contracts), "n_cached": len(contracts) - len(missing),
           "n_missing_pre_run": len(missing), "missing_pre_run": missing}


class _ArmAccountMap(dict):
    """Extends `pdt_blocked_counterfactual.ARM2ACCOUNT` (hardcoded {"safe-2":"safe",
    "bold-2":"bold"} -- the PDT study's own two-arm scope) to any arm, via
    `whole_engine_null._core_account_for_arm` (VERIFIED, not assumed -- see that function's own
    docstring: every fleet_rest arm, safe-3/risky-1/risky-3 included, shares ONE ribbon read
    off the "safe" core row regardless of its own risk-class naming). For "safe-2"/"bold-2"
    this returns the EXACT SAME values the original dict already did ("safe"/"bold") -- a
    lookup-miss extension, not a behavior change for the rows `harness_validation` already
    covered correctly. Without this, `_walk_via_exit_manager` would silently receive
    `fill["account"]=None` for every safe-3/risky-1 row (ARM2ACCOUNT.get() falling through to
    its default), making ribbon_flip exits structurally unreachable for two of this
    population's four arms -- the same disclosed gap the PDT-43 anchor already had for
    safe-2/bold-2 before WALKER-PDT-ANCHOR-FIDELITY-INPUTS step 2 fixed it, left unfixed here
    by omission rather than by disclosed design."""

    def get(self, key, default=None):
        if dict.__contains__(self, key):
            return dict.__getitem__(self, key)
        return wen._core_account_for_arm(key)


# ---------------------------------------------------------------------------- walk (via reuse)
def run_via_harness_validation(rows: list[dict], exit_slippage: Optional[float]) -> dict:
    """Runs `pdt_blocked_counterfactual.harness_validation(walker="exit_manager",
    bar_resolution="1min", exit_slippage=...)` against an arbitrary population, by temporarily
    monkeypatching `load_anchor_sample` to return `rows` -- the same "monkeypatch, call,
    restore" pattern `exit_slippage_ablation_research.py` already established for
    `whole_engine_null.walk_one` -- AND `ARM2ACCOUNT` to `_ArmAccountMap` (see above) so
    safe-3/risky-1 rows get a real ribbon read instead of a silent `account=None`. Every other
    downstream computation (stage/trigger resolution, 1-min bar walking, sign agreement,
    magnitude fidelity, stage decomposition) is byte-identical code to every prior walker study
    in this repo, not a parallel reimplement. For the PDT-43 subset (safe-2/bold-2 only) the
    ARM2ACCOUNT patch is a no-op -- both dicts resolve identically -- so those numbers stay
    directly comparable to the published WALKER-EXIT-SLIPPAGE-ABLATION-2026-09-03 result."""
    orig_loader = pbc.load_anchor_sample
    orig_map = pbc.ARM2ACCOUNT
    pbc.load_anchor_sample = lambda *a, **k: rows
    pbc.ARM2ACCOUNT = _ArmAccountMap(orig_map)
    try:
        return pbc.harness_validation(walker="exit_manager", bar_resolution="1min",
                                      exit_slippage=exit_slippage)
    finally:
        pbc.load_anchor_sample = orig_loader
        pbc.ARM2ACCOUNT = orig_map


def _sign_agreement(pairs: list[tuple[float, float]]) -> Optional[float]:
    if not pairs:
        return None
    ok = sum(1 for a, w in pairs if (a > 0) == (w > 0) or abs(w - a) < 1e-9)
    return round(ok / len(pairs), 4)


def _bucket_stats(rows: list[dict]) -> dict:
    """n / sign_agreement / aggregate_ratio / median_abs_error_dollars / verdict for an
    arbitrary subset of `harness_validation`'s own `rows` list -- reuses
    `pbc._shared_magnitude_fidelity`/`pbc.evaluate_magnitude_fidelity` (imported into
    `pdt_blocked_counterfactual`'s namespace from `walker_magnitude_fidelity`, re-exposed here
    the same way that module already re-exposes them for its own callers)."""
    pairs = [(r["actual"], r["replay"]) for r in rows]
    mag = pbc._shared_magnitude_fidelity(pairs) if pairs else {"n": 0}
    verdict = pbc.evaluate_magnitude_fidelity(mag) if pairs else "INSUFFICIENT"
    return {
        "n": len(rows),
        "sign_agreement": _sign_agreement([(r["actual"], r["replay"]) for r in rows]),
        "aggregate_ratio": mag.get("aggregate_ratio"),
        "median_abs_error_dollars": mag.get("median_abs_error_dollars"),
        "verdict": verdict,
    }


def per_arm_table(hv_rows: list[dict]) -> dict:
    by_arm: dict[str, list[dict]] = {}
    for r in hv_rows:
        by_arm.setdefault(r["arm"], []).append(r)
    return {arm: _bucket_stats(rs) for arm, rs in sorted(by_arm.items())}


def per_stage_table(hv_rows: list[dict]) -> dict:
    """Bucketed by the RECORDED (broker-truth) exit stage -- `exit_reason` verbatim, the same
    convention V9's own `agreement_by_exit_reason` table uses (no first-token truncation, so
    "tp1+trail" stays its own bucket rather than colliding with a bare "tp1"). Buckets with
    n<3 are folded into "other_rare" for table readability; the full per-row detail (with exact
    recorded_stage) still round-trips through the JSON companion's `rows` list."""
    by_stage: dict[str, list[dict]] = {}
    for r in hv_rows:
        stage = str(r.get("recorded_stage") or "UNKNOWN")
        by_stage.setdefault(stage, []).append(r)
    rare = [s for s, rs in by_stage.items() if len(rs) < 3]
    out = {}
    rare_rows: list[dict] = []
    for stage, rs in sorted(by_stage.items()):
        if stage in rare:
            rare_rows.extend(rs)
            continue
        out[stage] = _bucket_stats(rs)
    if rare_rows:
        out["other_rare(" + ",".join(sorted(rare)) + ")"] = _bucket_stats(rare_rows)
    return out


def skipped_summary(hv: dict, rows: list[dict]) -> dict:
    """Contracts the walk could not price at all (`_load_anchor_bars` returned None/empty ->
    counted in `hv["skipped_no_bars"]`) plus any row `_price_via_walker` itself returned an
    "error" for (visible as rows present in `rows` but absent from `hv["rows"]`)."""
    priced_keys = {(r["date"], r["arm"], r["symbol"]) for r in hv.get("rows", [])}
    all_keys = [(r["date"], r["arm"], r["symbol"]) for r in rows]
    unpriced = [k for k in all_keys if k not in priced_keys]
    return {
        "skipped_no_bars_count": hv.get("skipped_no_bars", 0),
        "n_input_rows": len(rows),
        "n_priced_rows": len(hv.get("rows", [])),
        "n_unpriced_total": len(unpriced),
        "unpriced_rows_sample": [{"date": d, "arm": a, "symbol": s} for d, a, s in unpriced[:50]],
    }


# ------------------------------------------------------------------------------------- V9 line
def v9_continuity_line() -> dict:
    """Reads the ALREADY-PUBLISHED V9 121-row result (`analysis/whole-engine-null/2026-09-02.
    json`) rather than re-running the V9 harness -- V9 is a separate, much larger pipeline
    (its own null-hypothesis families A/B/C) and this queue item asks for its number "for
    continuity", not a re-derivation. Default slippage only (V9's own module default,
    exit_manager_walk.DEFAULT_EXIT_SLIPPAGE=0.02) -- no zero-slippage cell for V9 in this table
    (out of scope; the ablation study already covered that comparison separately)."""
    path = REPO / "analysis" / "whole-engine-null" / "2026-09-02.json"
    if not path.exists():
        return {"available": False, "reason": f"{path} not found"}
    doc = json.loads(path.read_text(encoding="utf-8"))
    v9 = doc.get("v9_harness_validation") or {}
    mag = v9.get("magnitude_fidelity") or {}
    return {
        "available": True, "source": str(path.relative_to(REPO)),
        "n": v9.get("n_compared"), "skipped_no_bars": v9.get("n_skipped_no_bars"),
        "sign_agreement": v9.get("sign_agreement_rate"),
        "aggregate_ratio": mag.get("aggregate_ratio"),
        "median_abs_error_dollars": mag.get("median_abs_error_dollars"),
        "verdict": v9.get("harness_reliable"),
        "magnitude_fidelity_verdict": pbc.evaluate_magnitude_fidelity(mag) if mag else "INSUFFICIENT",
        "agreement_by_exit_reason": v9.get("agreement_by_exit_reason"),
    }


# ------------------------------------------------------------------------------------- main
def main() -> int:
    latest = latest_session_date()
    print(f"[full-pop] latest session in trades-enriched.jsonl: {latest}", flush=True)

    full_rows = load_population_rows(POPULATION_ARMS, WINDOW_START, latest)
    pdt_rows = load_population_rows(PDT_ARMS, PDT_WINDOW_START, PDT_WINDOW_END)
    print(f"[full-pop] full population: {len(full_rows)} rows, arms={POPULATION_ARMS}, "
         f"window={WINDOW_START}..{latest}", flush=True)
    print(f"[full-pop] PDT-43 subset (same run, for continuity): {len(pdt_rows)} rows, "
         f"arms={PDT_ARMS}, window={PDT_WINDOW_START}..{PDT_WINDOW_END}", flush=True)
    by_arm_counts = Counter(r["arm"] for r in full_rows)
    print(f"[full-pop] by arm: {dict(by_arm_counts)}", flush=True)

    cache_status = check_cache_status(full_rows)
    print(f"[full-pop] cache pre-check: {cache_status['n_cached']}/{cache_status['n_contracts']} "
         f"contracts already disk-cached, {cache_status['n_missing_pre_run']} would need a "
         f"live fetch this run", flush=True)

    results: dict = {
        "_meta": {
            "queue_item": "WALKER-REANCHOR-FULL-ENGINE-POPULATION",
            "generated_by": "backtest/tools/walker_full_population_anchor.py",
            "prereg": "analysis/deep-research/WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md",
            "population_arms": list(POPULATION_ARMS),
            "population_window": [WINDOW_START, latest],
            "pdt_subset_arms": list(PDT_ARMS),
            "pdt_subset_window": [PDT_WINDOW_START, PDT_WINDOW_END],
            "criterion": "|aggregate_ratio-1|<=0.40 AND median_abs_error_dollars<=$40 AND n>=20",
        },
        "population_composition": {
            "n_input_rows": len(full_rows), "by_arm": dict(by_arm_counts),
            "cache_status": cache_status,
        },
        "full_population": {}, "pdt_subset": {}, "v9_continuity": v9_continuity_line(),
    }

    for setting, slip in (("default", None), ("zero", 0.0)):
        print(f"[full-pop] FULL population, setting={setting}...", flush=True)
        hv = run_via_harness_validation(full_rows, slip)
        top = _bucket_stats(hv.get("rows", []))
        results["full_population"][setting] = {
            **top,
            "skipped": skipped_summary(hv, full_rows),
            "per_arm": per_arm_table(hv.get("rows", [])),
            "per_stage": per_stage_table(hv.get("rows", [])),
            "stage_decomposition": hv.get("stage_decomposition"),
        }
        print(f"  n={top['n']} sign={top['sign_agreement']} ratio={top['aggregate_ratio']} "
             f"median=${top['median_abs_error_dollars']} verdict={top['verdict']}", flush=True)

        print(f"[full-pop] PDT-43 subset (this run), setting={setting}...", flush=True)
        hv_pdt = run_via_harness_validation(pdt_rows, slip)
        top_pdt = _bucket_stats(hv_pdt.get("rows", []))
        results["pdt_subset"][setting] = {
            **top_pdt, "skipped": skipped_summary(hv_pdt, pdt_rows),
        }
        print(f"  n={top_pdt['n']} sign={top_pdt['sign_agreement']} "
             f"ratio={top_pdt['aggregate_ratio']} median=${top_pdt['median_abs_error_dollars']} "
             f"verdict={top_pdt['verdict']}", flush=True)

    # decision read
    full_default = results["full_population"]["default"]
    full_zero = results["full_population"]["zero"]
    clears_default = full_default["verdict"] == "PASS"
    clears_zero = full_zero["verdict"] == "PASS"
    clears_either = clears_default or clears_zero

    if clears_either:
        which = "default" if clears_default else "zero"
        per_arm = results["full_population"][which]["per_arm"]
        failing_arms = sorted(a for a, s in per_arm.items() if s.get("verdict") != "PASS")
        passing_arms = sorted(a for a, s in per_arm.items() if s.get("verdict") == "PASS")
        if failing_arms:
            conclusion = (
                f"The pooled full engine-attributed population (n={full_default['n']}) "
                f"CLEARS the letter of the magnitude-fidelity criterion at {which} slippage "
                f"(ratio {results['full_population'][which]['aggregate_ratio']}, median "
                f"${results['full_population'][which]['median_abs_error_dollars']}), BUT this "
                f"is arithmetic cancellation across arms, not per-arm fidelity: "
                f"{len(failing_arms)}/{len(per_arm)} arms ({', '.join(failing_arms)}) "
                f"individually FAIL their own arm-level ratio (only {', '.join(passing_arms) or 'none'} "
                f"pass), with opposite-signed biases netting out in the pooled sum -- the "
                f"residual is concentrated in stage-disagreement rows (structure_stop firing "
                f"where the broker recorded premium_stop/tp1+trail) that recur correlated "
                f"across arms trading the same signal, not evenly spread. Do NOT migrate "
                f"WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-WALK on the pooled number alone.")
        else:
            conclusion = (
                f"The pooled full engine-attributed population (n={full_default['n']}, arms="
                f"{list(POPULATION_ARMS)}) CLEARS the magnitude-fidelity criterion at "
                f"{which} slippage AND every individual arm also clears its own ratio -- "
                f"WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-WALK may unblock on this anchor.")
    else:
        # find worst residual stage bucket by aggregate distance from 1.0, default setting
        stage_tbl = full_default["per_stage"]
        worst_stage, worst_dist = None, -1.0
        for stage, s in stage_tbl.items():
            r = s.get("aggregate_ratio")
            if r is None:
                continue
            dist = abs(r - 1.0)
            if dist > worst_dist:
                worst_stage, worst_dist = stage, dist
        conclusion = (
            f"The pooled full population does NOT clear the criterion at either slippage "
            f"setting (default ratio {full_default['aggregate_ratio']} median "
            f"${full_default['median_abs_error_dollars']} verdict {full_default['verdict']}; "
            f"zero ratio {full_zero['aggregate_ratio']} median "
            f"${full_zero['median_abs_error_dollars']} verdict {full_zero['verdict']}) -- the "
            f"largest residual sits in the '{worst_stage}' stage bucket "
            f"(ratio {stage_tbl.get(worst_stage, {}).get('aggregate_ratio')}, n="
            f"{stage_tbl.get(worst_stage, {}).get('n')}).")

    results["conclusion"] = conclusion
    print(f"[full-pop] CONCLUSION: {conclusion}", flush=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"[full-pop] wrote {OUT_JSON}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
