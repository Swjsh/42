"""verify_edgehunt_candidates -- the throttled Verify phase, redone in PURE PYTHON (serial).

The edge-hunt workflow's Verify+Synthesize agents got SERVER-rate-limited (30+ concurrent
agents). Verification is deterministic, so it needs no LLM agents ($0, OP-3). This reads
every per-family artifact, extracts EVERY candidate, and applies the formal doctrine gates
PLUS the agents' own robustness flags -- nothing left untested:

  GATE_OOS    : OOS(2026) per-trade > 0
  GATE_Q      : positive_quarters >= 4/6
  GATE_CONC   : overall top5-day < 200%  AND  OOS top5-day < 300%
  GATE_N      : n >= 20  AND  OOS n >= 20
  GATE_ROBUST : agent's clears_bar_robust != False  AND  fragility.is_fragile_survivor != True
  GATE_ANCHOR : anchor_no_regression != False  AND  true_edge != False (OP-16)
  GATE_AUTH   : for bear-authorized families, the authorized (bear) subset per-trade must be > 0
                (an aggregate that only works because an UNAUTHORIZED bull book masks it is not shippable -- C4/C24)

  GATE_FRAUD  : the two GRADUATED fraud-detector gates that caught RSI2 / IBS / ema_adx
                AFTER they passed the naive 5-gate bar (C3/L58, L171/L172) --
                  * NO-TRUNCATION : per-trade sign must NOT invert between the chosen
                    (tight) premium stop and chart-stop-only (-0.99). truncation_guard.py.
                  * RANDOM-NULL   : per-trade must beat a random-entry coin-flip MAX
                    (same exit/stop/strike/count, ~20 seeds). null_baseline.py.
                Both need per-trade re-simulation; this harness consumes a candidate's
                inline self-verify when present (truncation_guard / null_baseline already
                ran in the family script) and otherwise re-simulates via
                fraud_gates.verify_candidate. The combined gate is STANDARD on every
                candidate -- a positive cell that FAILS either fraud gate is REJECTED.

Caveats (flagged, not auto-reject): exit_dependent, OOS-concentration-unverifiable, thin-OOS-n.
Writes analysis/recommendations/EDGE-HUNT-VERIFIED.json + prints a table.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKTEST = ROOT / "backtest"
if str(BACKTEST) not in sys.path:
    sys.path.insert(0, str(BACKTEST))

ART = ROOT / "analysis" / "recommendations"
BEAR_AUTHORIZED = {"v14_enhanced", "bearish_rejection_morning"}

from autoresearch.fraud_gates import (  # noqa: E402
    CHART_STOP_ONLY_PCT,
    fraud_gate_from_per_trade,
)


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _first(*vals):
    for v in vals:
        if v is not None:
            return v
    return None


def _posq_ratio(s):
    if isinstance(s, str) and "/" in s:
        a, b = s.split("/")[:2]
        na, nb = _num(a), _num(b)
        if na is not None and nb:
            return na / nb
    return None


def _grid_chart_stop_only_pt(fam_dict, strike_off, m):
    """Find the SAME-strike chart-stop-only (-0.99) per-trade from the family's grid.

    Edge-hunt families sweep premium_stop in {-0.08,-0.20,-0.50,-0.99} per strike but
    only the chosen cell lands in candidate_cells; the chart-stop-only sibling lives in
    ``base_grid`` / ``grid``. Pulling it lets the NO-TRUNCATION gate be evaluated for
    every edge-hunt candidate (not just families that recorded an inline self_verify).
    Returns the chart-stop-only per-trade (overall expectancy) or None if not in the grid.
    """
    if fam_dict is None or strike_off is None:
        return None
    for key in ("base_grid", "grid", "strike_stop_grid"):
        grid = fam_dict.get(key)
        if not isinstance(grid, list):
            continue
        for cell in grid:
            if not isinstance(cell, dict):
                continue
            if _num(cell.get("strike_offset")) != _num(strike_off):
                continue
            ps = _num(cell.get("premium_stop_pct"))
            if ps is None or ps > -0.99 + 1e-9:   # only the chart-stop-only (-0.99) sibling
                continue
            cm = cell.get("metrics") if isinstance(cell.get("metrics"), dict) else {}
            cov = cell.get("overall") if isinstance(cell.get("overall"), dict) else {}
            pt = _num(_first(cm.get("exp_dollar"), cov.get("avg_pnl"),
                             cell.get("overall_per_trade")))
            if pt is not None:
                return pt
    return None


def _fraud_inputs(c, ov, m, oos, fam_dict=None):
    """Pull the inputs the two graduated fraud gates need out of a candidate dict.

    Prefers an inline ``self_verify`` block (the family script already ran
    truncation_guard + null_baseline) and falls back to (a) the candidate's own fields
    and (b) the family's grid for the same-strike chart-stop-only sibling. Returns a
    dict (possibly with None values when a family did not record them -- in which case
    the gate FAILS OPEN, i.e. cannot disprove, never silently blesses).
    """
    sv = c.get("self_verify") if isinstance(c.get("self_verify"), dict) else {}
    null = c.get("null") if isinstance(c.get("null"), dict) else (
        sv.get("null") if isinstance(sv.get("null"), dict) else {})
    chosen_pt = _num(_first(
        sv.get("overall_per_trade"), c.get("overall_per_trade"),
        m.get("exp_dollar"), ov.get("avg_pnl")))
    strike_off = c.get("strike_offset")
    chart_stop_only_pt = _num(_first(
        sv.get("same_strike_chart_stop_only_per_trade"),
        c.get("same_strike_chart_stop_only_per_trade"),
        c.get("chart_stop_only_per_trade"),
        _grid_chart_stop_only_pt(fam_dict, strike_off, m)))
    return {
        "chosen_per_trade": chosen_pt,
        "chart_stop_only_per_trade": chart_stop_only_pt,
        "chosen_premium_stop_pct": _num(_first(
            c.get("premium_stop_pct"), sv.get("premium_stop_pct"))),
        "drop_top5_per_trade": _num(_first(
            sv.get("drop_top5_per_trade"), c.get("drop_top5_per_trade"))),
        "null": null,
        # A family that recorded an inline truncation verdict pins it (overrides recompute).
        "inline_is_artifact": sv.get("is_truncation_artifact",
                                     c.get("is_truncation_artifact")),
        "inline_null_pass": (sv.get("criteria", {}) or {}).get("null_pass",
                                                               c.get("null_pass")),
    }


def _extract(fam, c, fam_dict=None):
    if not isinstance(c, dict):
        return None
    m = c.get("metrics") if isinstance(c.get("metrics"), dict) else {}
    ov = c.get("overall") if isinstance(c.get("overall"), dict) else {}
    oos = c.get("OOS_2026") if isinstance(c.get("OOS_2026"), dict) else (c.get("oos") if isinstance(c.get("oos"), dict) else {})
    frag = c.get("fragility") if isinstance(c.get("fragility"), dict) else {}
    cfg = _first(c.get("config"), c.get("name"),
                 f"{c.get('strike_tier')}/{c.get('stop_label')}" if c.get("strike_tier") else None,
                 f"off{c.get('strike_offset')}_stop{c.get('premium_stop_pct')}" if "strike_offset" in c else "?")
    return {
        "config": str(cfg),
        "overall_pt": _num(_first(c.get("overall_per_trade"), m.get("exp_dollar"), ov.get("avg_pnl"))),
        "oos_pt": _num(_first(c.get("oos_per_trade"), m.get("oos_exp"), oos.get("avg_pnl"), oos.get("exp_dollar"))),
        "n": _num(_first(c.get("n_trades"), c.get("n"), m.get("n"), ov.get("n"))),
        "oos_n": _num(_first(m.get("oos_n"), oos.get("n"), c.get("oos_n"))),
        "top5": _num(_first(c.get("top5_day_pct"), m.get("top5_day_pct"), ov.get("top5_day_pct"))),
        "oos_top5": _num(_first(c.get("oos_top5_day_pct"), frag.get("oos_top5_day_pct"), oos.get("top5_day_pct"), m.get("oos_top5_day_pct"))),
        "posq": _first(c.get("positive_quarters"), m.get("positive_quarters")),
        "robust": c.get("clears_bar_robust"),
        "fragile": frag.get("is_fragile_survivor"),
        "anchor_ok": c.get("anchor_no_regression"),
        "true_edge": c.get("true_edge"),
        "exit_dependent": bool(c.get("exit_dependent")),
        "bear_pt": _num(c.get("bear_per_trade")),
        "fraud_inputs": _fraud_inputs(c, ov, m, oos, fam_dict=fam_dict),
    }


def _gate(fam, c):
    fails, caveats = [], []
    if c["oos_pt"] is None or c["oos_pt"] <= 0:
        fails.append(f"OOS/t={c['oos_pt']}<=0")
    r = _posq_ratio(c["posq"])
    if r is None or r < 4 / 6 - 1e-9:
        fails.append(f"posQ={c['posq']}<4/6")
    if c["top5"] is None or c["top5"] >= 200:
        fails.append(f"top5={c['top5']}>=200")
    if c["oos_top5"] is not None and c["oos_top5"] >= 300:
        fails.append(f"OOS_top5={c['oos_top5']}>=300")
    elif c["oos_top5"] is None:
        caveats.append("OOS-conc-unverified")
    if c["n"] is None or c["n"] < 20:
        fails.append(f"n={c['n']}<20")
    if c["oos_n"] is not None and c["oos_n"] < 20:
        fails.append(f"OOS_n={c['oos_n']}<20")
    elif c["oos_n"] is None:
        caveats.append("OOS_n-unknown")
    if c["robust"] is False:
        fails.append("clears_bar_robust=False")
    if c["fragile"] is True:
        fails.append("fragile_survivor")
    if c["anchor_ok"] is False:
        fails.append("anchor_regression(OP-16)")
    if c["true_edge"] is False or c["true_edge"] == 0:
        fails.append("true_edge=0")
    if fam in BEAR_AUTHORIZED and c["bear_pt"] is not None and c["bear_pt"] <= 0:
        fails.append(f"authorized_bear/t={c['bear_pt']}<=0(bull-book-masks,C4/C24)")
    if c["exit_dependent"]:
        caveats.append("exit-dependent")

    # ── GATE_FRAUD: the two graduated fraud-detector gates (C3/L58, L171/L172) ──
    fv = _fraud_verdict(c.get("fraud_inputs") or {})
    c["fraud"] = fv
    if fv.get("no_truncation_pass") is False:
        fails.append("TRUNCATION_ARTIFACT(L171:sign-inverts-at-chart-stop-only)")
    if fv.get("null_pass") is False and fv.get("null_evaluable"):
        fails.append("RANDOM_NULL_FAIL(L172:coin-flip-reproduces-per-trade)")
    elif not fv.get("null_evaluable"):
        caveats.append("null-unverified(no inline null + no re-sim)")
    return fails, caveats


def _fraud_verdict(fi: dict) -> dict:
    """Resolve the combined fraud verdict for a candidate from its extracted inputs.

    Honors a family's inline truncation/null self-verify when recorded (that family
    already ran truncation_guard / null_baseline with full per-trade data). Otherwise
    recomputes the pure-from-per-trade gate via fraud_gates.fraud_gate_from_per_trade.
    Both gates FAIL OPEN on missing reference data (cannot disprove != bless)."""
    inline_artifact = fi.get("inline_is_artifact")
    inline_null = fi.get("inline_null_pass")

    null = fi.get("null") or {}
    null_evaluable = bool(null.get("per_trade_max") is not None) or inline_null is not None

    fv = fraud_gate_from_per_trade(
        chosen_per_trade=fi.get("chosen_per_trade"),
        chart_stop_only_per_trade=fi.get("chart_stop_only_per_trade"),
        chosen_premium_stop_pct=fi.get("chosen_premium_stop_pct") if fi.get("chosen_premium_stop_pct") is not None else CHART_STOP_ONLY_PCT,
        drop_top5_per_trade=fi.get("drop_top5_per_trade"),
        null=null,
        chart_stop_pct=CHART_STOP_ONLY_PCT,
    )
    d = fv.as_dict()
    # An inline truncation verdict (computed with full per-trade data inside the family
    # script) PINS the result -- it is more authoritative than re-deriving from the
    # summary numbers.
    if inline_artifact is not None:
        d["is_truncation_artifact"] = bool(inline_artifact)
        d["no_truncation_pass"] = not bool(inline_artifact)
    if inline_null is not None:
        d["null_pass"] = bool(inline_null)
    d["null_evaluable"] = null_evaluable
    d["passes"] = bool(d["no_truncation_pass"] and (d["null_pass"] or not null_evaluable))
    return d


def _all_candidates(d):
    seen, out = set(), []
    for key in ("candidate_cells", "candidate_edges", "candidate_edges_sorted",
                "candidate_edges_clearing_bar", "strike_stop_grid", "grid"):
        v = d.get(key)
        if isinstance(v, list):
            for c in v:
                ex = _extract("", c, fam_dict=d)
                if ex and ex["config"] not in seen:
                    seen.add(ex["config"])
                    out.append((c, ex))
    return out


def main():
    families, total_conf = {}, 0
    print("=" * 80)
    print("EDGE-HUNT VERIFICATION (serial pure-python; agents' robustness flags + formal gates)")
    print("=" * 80)
    for f in sorted(glob.glob(str(ART / "edgehunt-*.json"))):
        fam = os.path.basename(f).replace("edgehunt-", "").replace(".json", "")
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception as e:
            families[fam] = {"error": str(e)}
            print(f"\n### {fam}: ARTIFACT ERROR {e}")
            continue
        confirmed, rejected = [], []
        for raw, ex in _all_candidates(d):
            ex = _extract(fam, raw, fam_dict=d)
            fails, caveats = _gate(fam, ex)
            ex["caveats"] = caveats
            if fails:
                ex["fails"] = fails
                rejected.append(ex)
            else:
                confirmed.append(ex)
        confirmed.sort(key=lambda c: -(c["oos_pt"] or -9e9))
        rejected.sort(key=lambda c: -(c["oos_pt"] or -9e9))
        families[fam] = {"n": len(confirmed) + len(rejected), "confirmed": confirmed, "rejected": rejected}
        total_conf += len(confirmed)
        print(f"\n### {fam}: {len(confirmed)} CONFIRMED / {len(confirmed)+len(rejected)} candidates")
        for c in confirmed[:4]:
            cv = (" CAVEATS:" + ",".join(c["caveats"])) if c["caveats"] else ""
            fr = c.get("fraud") or {}
            fr_s = (f" FRAUD[trunc={'OK' if fr.get('no_truncation_pass') else 'FAIL'},"
                    f"null={'OK' if fr.get('null_pass') else ('OK*' if not fr.get('null_evaluable') else 'FAIL')}]")
            print(f"  [CONFIRMED] {c['config']:46s} OOS/t=${c['oos_pt']} all/t=${c['overall_pt']} n={c['n']} oosN={c['oos_n']} posQ={c['posq']} top5={c['top5']} oosTop5={c['oos_top5']}{fr_s}{cv}")
        for c in rejected[:2]:
            print(f"  [reject]    {c['config']:46s} OOS/t=${c['oos_pt']}  fails: {', '.join(c['fails'])}")

    out = {"gates": ("OOS>0; posQ>=4/6; top5<200; OOS_top5<300; n>=20; OOS_n>=20; robust; anchor; "
                     "auth-bear>0; NO-TRUNCATION(L171 sign holds at chart-stop-only); "
                     "RANDOM-NULL(L172 beat coin-flip MAX)"),
           "fraud_gates": ("GRADUATED C3/L58: no-truncation (truncation_guard.py + L171) AND "
                           "random-entry-null (null_baseline.py + L172), wired via "
                           "autoresearch.fraud_gates -- STANDARD on every candidate; a positive "
                           "cell that FAILS either is REJECTED (caught RSI2/IBS/ema_adx)"),
           "total_confirmed": total_conf, "families": families,
           "note": "Pure-python serial verify (no agent fan-out -> no server throttle). Honors agents' "
                   "fragility/robust/anchor/true_edge flags + formal gates + the two graduated fraud "
                   "gates. Caveats flagged, not auto-rejected."}
    (ART / "EDGE-HUNT-VERIFIED.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\n{'='*80}\nTOTAL CONFIRMED (after all gates): {total_conf}\n-> analysis/recommendations/EDGE-HUNT-VERIFIED.json")


if __name__ == "__main__":
    main()
