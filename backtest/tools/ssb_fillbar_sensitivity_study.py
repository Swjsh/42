"""ssb_fillbar_sensitivity_study.py -- SS-A/SS-B/SS-C fill-bar-convention sensitivity
(2026-07-14, ultracode-review Job 2).

structure_stop_study.py's Layer (a) fresh-slice replay (via t4_exit_matrix._load_bars,
mask ``ts >= entry_ts``) and Layer (b) real-fills anchor (via norm_bars_from_esp, filter
``b["t"] >= entry_ts_utc``) both INCLUDE the fill bar itself in the option-bar walk that
decides TP1/stop/trail/time-stop -- the SAME same-bar-inclusion convention the 2026-07-11
fillbar audit flagged for t4/t5 (analysis/recommendations/entry-exit-matrix-fillbar-
audit-2026-07-11.{json,md}, guard: backtest/tests/test_fill_bar_convention.py). That audit
found ZERO T4/T5 verdict flips under the fill-bar-excluded convention (one evidence-revoked
upgrade, not a KILL/SHIP flip) -- but it explicitly did NOT test structure_stop_study.py,
which reuses t4's/esp's loaders unchanged and was never re-run under the alternate
convention. This module closes that gap for SS-A/SS-B/SS-C specifically, exactly like
t4_exit_matrix.py's own disclosure pattern: run the SAME frozen candidates under BOTH
conventions and report the delta as a disclosed sensitivity column, not a silent number.

CONVENTION TOGGLE (identical technique to the guard test's own
``t4.replay(1.00, bars[1:], ...)`` fill-bar-excluded probe -- see
backtest/tests/test_fill_bar_convention.py::test_t4_replay_bar0_stop_semantics_vs_fill_bar_excluded):
  * AS-RUN (current, in structure_stop_study.py, unchanged): norm_bars = the full list
    returned by t4._load_bars / norm_bars_from_esp, bars[0] IS the fill bar (matches the
    live 1-min-actuator: the real exit manager can act inside the first 5 minutes).
  * EXCLUDED (sensitivity probe, matching simulator_real's entry_idx+1 "one full bar min
    hold" convention -- the P5/mass-grind/ship-gate fills authority): the SAME norm_bars
    list with element 0 dropped. entry_premium is UNCHANGED in both variants (matches the
    2026-07-11 audit's own method: "re-ran fill-bar-excluded (entry price unchanged)") --
    only which bars the replay WALKS for stop/TP1/trail/time-stop changes.
  * The SPY-close-based structure-stop trigger (structure_stop_signal_time, over
    spy_lifetime) is UNTOUCHED by this toggle in both variants -- it is a separate data
    stream (SPY 5m closes, not option premium bars) and was not in the audit's flagged
    scope (t4._load_bars / norm_bars_from_esp are both OPTION-bar loaders).

REUSES, does not reinvent: imports structure_stop_study.py wholesale and calls its own
preflight/prepare_layer_a/prepare_positions/run_layer_a/replay_population/battery
functions unchanged for the AS-RUN convention; the EXCLUDED variant is built by slicing
each already-prepared position's own norm_bars list (bars[1:]) and re-running the SAME
replay functions on that slice -- zero duplicated replay logic, zero re-fetch of option
bars (Layer (b) makes exactly the same number of live Alpaca OPRA calls as a single
structure_stop_study.py run, not double).

VERDICT RULE: for each of SS-A/SS-B/SS-C, at each layer, PASS = beats CONTROL (mirrors
structure_stop_study.build_verdicts' own per-layer conditions). "Toggle-stable" = the
PASS/FAIL call for a candidate at a layer is IDENTICAL in both conventions. A sign-flip
(candidate beats CONTROL in one convention, loses in the other) is CRITICAL -- SS-B is
already shipped/certified (backtest/tools/ssb_certification_study.py), so a flip there
means the certification does not hold under the alternate fill-bar convention and must be
escalated loudly, not silently absorbed.

ANALYSIS ONLY: writes only to analysis/recommendations/. Never touches strategies.py,
params.json, exit_manager.py, structure_stop_study.py, or any trading-path file.

Run: backtest/.venv/Scripts/python.exe backtest/tools/ssb_fillbar_sensitivity_study.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

import structure_stop_study as sss  # noqa: E402

OUT_JSON = REPO / "analysis" / "recommendations" / "ssb-fillbar-sensitivity-2026-07-14.json"
OUT_MD = REPO / "analysis" / "recommendations" / "ssb-fillbar-sensitivity-2026-07-14.md"

CERTIFIED_CANDIDATE = "SS-B"   # the one that's actually shipped (ssb_certification_study.py)


# ---------------------------------------------------------------------------------------------
# CONVENTION TOGGLE -- exclude each position's own fill bar from the walked norm_bars
# ---------------------------------------------------------------------------------------------
def exclude_fill_bar(prepared: list[dict]) -> tuple[list[dict], int]:
    """Sensitivity variant of an already-prepared position list: drop element 0 of each
    position's own norm_bars (the fill bar), matching simulator_real's entry_idx+1
    convention. entry_premium untouched. Positions left with zero bars after the drop are
    excluded (mirrors t4._load_bars/esp returning empty -> skipped upstream) and counted."""
    out, n_dropped_empty = [], 0
    for p in prepared:
        nb = p["norm_bars"][1:]
        if not nb:
            n_dropped_empty += 1
            continue
        out.append({**p, "norm_bars": nb})
    return out, n_dropped_empty


# ---------------------------------------------------------------------------------------------
# LAYER (a) -- both conventions off the SAME prepared fresh-slice population
# ---------------------------------------------------------------------------------------------
def run_layer_a_both_conventions() -> dict:
    prepared_asrun, n_missing_bars, _spy = sss.prepare_layer_a()
    prepared_excl, n_dropped_empty = exclude_fill_bar(prepared_asrun)

    asrun = sss.run_layer_a(prepared_asrun)
    asrun["n_missing_bars"] = n_missing_bars
    excl = sss.run_layer_a(prepared_excl)
    excl["n_missing_bars"] = n_missing_bars + n_dropped_empty
    excl["n_positions_lost_to_empty_walk"] = n_dropped_empty
    return {"as_run_fill_bar_included": asrun, "excluded_fill_bar": excl}


# ---------------------------------------------------------------------------------------------
# LAYER (b) -- both conventions off the SAME prepared real-fills anchor population
# (fetches option bars ONCE -- the excluded variant reuses the same fetched bars)
# ---------------------------------------------------------------------------------------------
def run_layer_b_both_conventions(spy_full) -> dict:
    fills = sss.esp.load_fleet_engine_fills()
    positions = sss.esp.reconstruct_positions(fills)
    anchor_positions = [p for p in positions if p["date_et"] <= sss.ANCHOR_END_DATE]
    prepared_asrun, stats = sss.prepare_positions(anchor_positions, spy_full)
    prepared_excl, n_dropped_empty = exclude_fill_bar(prepared_asrun)

    def _run(prepared: list[dict], extra_stats: dict) -> dict:
        uniq = sorted(set((p["date_et"], p["symbol"]) for p in prepared))
        dates = sorted(set(p["date_et"] for p in prepared))
        actual_total = round(sum(p.get("actual_exit_pnl") or 0.0 for p in prepared), 2)
        out = {**stats, **extra_stats, "n_positions_with_bars": len(prepared),
               "n_unique_signals": len(uniq), "n_trading_days": len(dates),
               "date_span": f"{dates[0]}..{dates[-1]}" if dates else None,
               "actual_realized_total": actual_total, "candidates": {}}
        for cid in sss.ALL_CANDIDATE_IDS:
            r = sss.replay_population(prepared, cid)
            out["candidates"][cid] = {k: v for k, v in r.items() if k != "rows"}
        return out

    asrun = _run(prepared_asrun, {})
    excl = _run(prepared_excl, {"n_positions_lost_to_empty_walk": n_dropped_empty})
    return {"as_run_fill_bar_included": asrun, "excluded_fill_bar": excl}


# ---------------------------------------------------------------------------------------------
# STABILITY VERDICTS
# ---------------------------------------------------------------------------------------------
def _beats_control(layer: dict, cid: str, key: str, ctl_key: str) -> Optional[bool]:
    cand = layer["candidates"][cid].get(key)
    ctl = layer["candidates"]["CONTROL"].get(ctl_key)
    if cand is None or ctl is None:
        return None
    return bool(cand > ctl)


def build_stability(layer_a_both: dict, layer_b_both: dict) -> dict:
    stability = {}
    for cid in sss.STRUCTURE_CANDIDATE_IDS:
        a_asrun = _beats_control(layer_a_both["as_run_fill_bar_included"], cid,
                                  "expectancy", "expectancy")
        a_excl = _beats_control(layer_a_both["excluded_fill_bar"], cid,
                                 "expectancy", "expectancy")
        b_asrun = _beats_control(layer_b_both["as_run_fill_bar_included"], cid,
                                  "anchor_total", "anchor_total")
        b_excl = _beats_control(layer_b_both["excluded_fill_bar"], cid,
                                 "anchor_total", "anchor_total")
        layer_a_stable = (a_asrun == a_excl)
        layer_b_stable = (b_asrun == b_excl)
        toggle_stable = bool(layer_a_stable and layer_b_stable)

        a_exp_asrun = layer_a_both["as_run_fill_bar_included"]["candidates"][cid]["expectancy"]
        a_exp_excl = layer_a_both["excluded_fill_bar"]["candidates"][cid]["expectancy"]
        b_tot_asrun = layer_b_both["as_run_fill_bar_included"]["candidates"][cid]["anchor_total"]
        b_tot_excl = layer_b_both["excluded_fill_bar"]["candidates"][cid]["anchor_total"]

        stability[cid] = {
            "layer_a_beats_control": {"as_run": a_asrun, "excluded_fill_bar": a_excl,
                                       "stable": layer_a_stable},
            "layer_b_beats_control": {"as_run": b_asrun, "excluded_fill_bar": b_excl,
                                       "stable": layer_b_stable},
            "layer_a_expectancy": {"as_run": a_exp_asrun, "excluded_fill_bar": a_exp_excl},
            "layer_b_anchor_total": {"as_run": b_tot_asrun, "excluded_fill_bar": b_tot_excl},
            "toggle_stable": toggle_stable,
            "is_certified_shipped_candidate": cid == CERTIFIED_CANDIDATE,
            "severity": ("OK" if toggle_stable else
                         ("CRITICAL_CERTIFICATION_AT_RISK" if cid == CERTIFIED_CANDIDATE
                          else "FLAG_NOT_SHIPPED")),
        }
    return stability


# ---------------------------------------------------------------------------------------------
# MARKDOWN
# ---------------------------------------------------------------------------------------------
def render_md(out: dict) -> str:
    lines = [
        "# SS-B fill-bar-convention sensitivity (2026-07-14)",
        "",
        f"Generated: {out['generated_at']}",
        "",
        "Runs structure_stop_study.py's SS-A/SS-B/SS-C (+ CONTROL) under BOTH the as-run "
        "same-bar-inclusion convention (t4._load_bars / norm_bars_from_esp, `>= entry_ts`) "
        "AND the fill-bar-excluded convention (simulator_real's entry_idx+1, the P5/mass-"
        "grind/ship-gate authority) -- exactly the sensitivity check the 2026-07-11 fillbar "
        "audit ran for t4/t5, extended here to structure_stop_study.py which that audit did "
        "not cover.",
        "",
        "## Verdict",
        "",
    ]
    ssb = out["stability"]["SS-B"]
    if ssb["toggle_stable"]:
        lines.append("**SS-B: TOGGLE-STABLE. The certification (ssb_certification_study.py) "
                      "STANDS.** Beats-CONTROL calls at both layers are identical under both "
                      "fill-bar conventions.")
    else:
        lines.append("**SS-B: SIGN-FLIP DETECTED -- CRITICAL.** The beats-CONTROL call "
                      "changes between fill-bar conventions. The shipped certification "
                      "(ssb_certification_study.py) does NOT hold under the alternate "
                      "convention. No config change made; escalating per JOB 2 instructions.")
    lines.append("")
    lines.append("| Candidate | Layer (a) exp as-run | Layer (a) exp excl. | Layer (a) stable | "
                  "Layer (b) total as-run | Layer (b) total excl. | Layer (b) stable | "
                  "Toggle-stable | Severity |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for cid in sss.STRUCTURE_CANDIDATE_IDS:
        s = out["stability"][cid]
        lines.append(
            f"| {cid} | ${s['layer_a_expectancy']['as_run']} | "
            f"${s['layer_a_expectancy']['excluded_fill_bar']} | "
            f"{'YES' if s['layer_a_beats_control']['stable'] else 'NO'} | "
            f"${s['layer_b_anchor_total']['as_run']} | "
            f"${s['layer_b_anchor_total']['excluded_fill_bar']} | "
            f"{'YES' if s['layer_b_beats_control']['stable'] else 'NO'} | "
            f"{'YES' if s['toggle_stable'] else '**NO**'} | {s['severity']} |")
    lines.append("")
    lines.append("## CONTROL reference (both conventions)")
    lines.append("")
    ctl_a = out["layer_a"]
    ctl_b = out["layer_b"]
    lines.append(f"- Layer (a) CONTROL expectancy: as-run ${ctl_a['as_run_fill_bar_included']['candidates']['CONTROL']['expectancy']}/tr "
                 f"-> excluded ${ctl_a['excluded_fill_bar']['candidates']['CONTROL']['expectancy']}/tr")
    lines.append(f"- Layer (b) CONTROL anchor total: as-run ${ctl_b['as_run_fill_bar_included']['candidates']['CONTROL']['anchor_total']} "
                 f"-> excluded ${ctl_b['excluded_fill_bar']['candidates']['CONTROL']['anchor_total']}")
    lines.append("")
    lines.append("## Disclosures")
    lines.append("")
    for d in out["disclosures"]:
        lines.append(f"- {d}")
    lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------------------------
def main() -> int:
    pf = sss.preflight()
    print(f"[ssb-sens] preflight: {pf}", flush=True)
    if not (pf["fresh_slice_hash_ok"] and pf["anchor_population_hash_ok"] and pf["preregistration_version_ok"]):
        print("[ssb-sens] PREFLIGHT FAILED -- aborting (same frozen pre-registration as structure_stop_study.py)",
              file=sys.stderr)
        return 1

    print("[ssb-sens] loading SPY 5m bars...", flush=True)
    spy_full = sss.load_spy_full_with_today()

    print("[ssb-sens] layer (a): both conventions off the same fresh-slice prep...", flush=True)
    layer_a_both = run_layer_a_both_conventions()
    for conv, layer in layer_a_both.items():
        for cid in sss.STRUCTURE_CANDIDATE_IDS:
            c = layer["candidates"][cid]
            print(f"[ssb-sens]   layer(a) {conv:24s} {cid}: exp=${c['expectancy']} n={c['n']}",
                  flush=True)

    print("[ssb-sens] layer (b): real-fills anchor, both conventions (single fetch pass)...",
          flush=True)
    layer_b_both = run_layer_b_both_conventions(spy_full)
    for conv, layer in layer_b_both.items():
        for cid in sss.STRUCTURE_CANDIDATE_IDS:
            c = layer["candidates"][cid]
            print(f"[ssb-sens]   layer(b) {conv:24s} {cid}: total=${c['anchor_total']} "
                  f"n={c['n_valid']}", flush=True)

    stability = build_stability(layer_a_both, layer_b_both)
    for cid, s in stability.items():
        print(f"[ssb-sens] {cid}: toggle_stable={s['toggle_stable']} severity={s['severity']}",
              flush=True)

    disclosures = [
        "Scope: extends the 2026-07-11 fillbar audit (entry-exit-matrix-fillbar-audit-"
        "2026-07-11.md, T4/T5 only) to structure_stop_study.py's SS-A/SS-B/SS-C, which "
        "reuses t4._load_bars (layer a) and norm_bars_from_esp (layer b) unchanged and was "
        "never covered by that audit.",
        "Convention toggle: EXCLUDED = drop element 0 (the fill bar) from each position's "
        "already-prepared norm_bars list, identical technique to "
        "test_fill_bar_convention.py::test_t4_replay_bar0_stop_semantics_vs_fill_bar_excluded's "
        "bars[1:] probe. entry_premium is unchanged in both conventions (matches the "
        "2026-07-11 audit's own method).",
        "The SPY-close-based structure-stop trigger (structure_stop_signal_time / "
        "spy_lifetime) is NOT toggled -- it is a separate SPY-bar data stream, not an "
        "option-bar walk, and was outside the audit's flagged scope.",
        "structure_stop_study.py itself is UNCHANGED -- this module imports it and calls "
        "its existing prepare/run/replay functions unchanged; the excluded-convention "
        "variant is built by post-processing already-prepared positions, not by editing "
        "the frozen pre-registration or its replay engine.",
        "Layer (b) makes exactly ONE pass of live Alpaca OPRA option-bar fetches (shared by "
        "both conventions via the already-prepared position list) -- not doubled.",
        "No trading-path file touched (strategies.py / params.json / exit_manager.py / "
        "structure_stop_study.py all read-only). No orders placed. No config changed "
        "regardless of verdict, per JOB 2 instructions.",
    ]

    out = {
        "_doc": "SS-A/SS-B/SS-C fill-bar-convention sensitivity -- extends the 2026-07-11 "
                "fillbar audit (T4/T5-scoped) to structure_stop_study.py. ANALYSIS ONLY.",
        "generated_at": dt.datetime.now().isoformat(),
        "source_study": "backtest/tools/structure_stop_study.py",
        "related_audit": "analysis/recommendations/entry-exit-matrix-fillbar-audit-2026-07-11.json",
        "certified_shipped_candidate": CERTIFIED_CANDIDATE,
        "certification_reference": "backtest/tools/ssb_certification_study.py",
        "preflight": pf,
        "layer_a": layer_a_both,
        "layer_b": layer_b_both,
        "stability": stability,
        "disclosures": disclosures,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    OUT_MD.write_text(render_md(out), encoding="utf-8")
    print(f"[ssb-sens] wrote {OUT_JSON}", flush=True)
    print(f"[ssb-sens] wrote {OUT_MD}", flush=True)

    ssb = stability["SS-B"]
    if not ssb["toggle_stable"]:
        print("[ssb-sens] *** CRITICAL: SS-B sign-flips under the alternate fill-bar "
              "convention -- certification does NOT hold. See severity=CRITICAL_CERTIFICATION_AT_RISK. ***",
              file=sys.stderr, flush=True)
        return 2
    print("[ssb-sens] SS-B toggle-stable -- certification stands.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
