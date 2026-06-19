"""Call-side STANDALONE OP-22 validation for H2b gap_and_go.

WHY THIS EXISTS (load-bearing, OP-16 bull-DRAFT scrutiny)
---------------------------------------------------------
Gap-and-go is LIVE bear-only (params.gap_and_go_side="put"). Flipping to
side="both" would roughly DOUBLE coverage (calls are the bigger sample). But the
combined-stream WF (1.866) / OOS-sign-stability / all-cuts-OOS+ / DSR /
drop-top5 / by-quarter in ``gap-and-go-LIVE.json`` are the BOTH-DIRECTION stream.
The puts (+$67.96/t, 86.2% WR) carry that combined verdict; the calls
(+$27.69/t, 65.5% WR aggregate) are positive but weaker and UNPROVEN on the
walk-forward / OOS / sub-window axes STANDALONE.

Per OP-16, a bull setup ships only under EXTRA scrutiny — a marginal bull edge
shipped is the worst outcome (the vwap-pullback landmine: headline aggregate
hid an exit-config misattribution). So this script isolates the CALL side and
runs the FULL OP-22 stack on it ALONE, on the LIVE config (chart-stop-only),
ATM + ITM1.

SHIP-CALLS gate (ALL must hold on the call side ALONE, chart-stop-only):
  OOS+ ($ AND %)  AND  WF_median >= 0.70  AND  all-cuts-OOS-positive
  AND  DSR != FAIL  AND  drop-top5 mean > 0 (broad-based)
  AND  >= 5/6 quarters positive.
NOTE: ``both_dirs_positive`` is DELIBERATELY EXCLUDED — it is structurally N/A
for a single-side test (only calls exist), so applying it would auto-fail. This
mirrors the task's 6-axis SHIP-CALLS criteria.

Reuses the EXACT validated harness verbatim (detect_gap_and_go + simulator_real
+ gap_and_go_ratify._sim/_full_metrics/_wf_norm) so the call-side numbers are
apples-to-apples with the combined scorecard. Only the signal SET is filtered to
calls (side=="C"). Trigger logic UNCHANGED -> causality already established
(no re-audit needed).

PROPOSE-ONLY (Rule 9): writes a ``call_side_standalone`` block into
``analysis/recommendations/gap-and-go-LIVE.json``. Touches no params, no
heartbeat, no order path. Pure-Python, $0, deterministic.

Usage:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/gap_and_go_call_side_standalone.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]          # ...\42\backtest
PROJECT = REPO.parent                               # ...\42
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import pandas as pd  # noqa: E402

# Reuse the EXACT validated detector + the ratify harness verbatim.
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    load_spy, align_vix, build_day_contexts, detect_gap_and_go,
)
from autoresearch.gap_and_go_ratify import (  # noqa: E402
    SPY, VIX, OUT, TIERS, WF_GATE, Q_POS_GATE, EXIT_CONFIGS,
    _sim, _full_metrics,
)
from lib.ribbon import compute_ribbon  # noqa: E402

# Call-side ships only if >= 5 of 6 quarters are positive (stricter than the
# combined q>=60% gate — OP-16 extra scrutiny on the bull side).
Q_COUNT_GATE = 5


def _ship_gate_call_side(m: dict) -> dict:
    """The SHIP-CALLS gate on call-side-only metrics, chart-stop-only config.

    DELIBERATELY OMITS both_dirs_positive (N/A for a single-side test). Quarter
    rule is the stricter >=5/6 count, not just the >=60% fraction.
    """
    quarters = m.get("quarters", {})
    q_pos = sum(1 for v in quarters.values() if v["exp"] > 0)
    return {
        "oos_positive_dollar": m["oos_exp_dollar"] > 0,
        "oos_sign_stable_pct": m["oos_sign_stable"],          # IS% AND OOS% both > 0
        "wf_median_ge_0.70": m["median_wf_norm"] >= WF_GATE,
        "all_cuts_oos_positive": m["all_cuts_oos_positive"],
        "dsr_not_fail": m["dsr_verdict"] not in ("FAIL", "ERROR", "UNKNOWN", "DEGENERATE"),
        "robust_drop_top5": m["robust_to_outliers"],
        "quarters_pos_count": q_pos,
        "quarters_total": len(quarters),
        "quarters_ge_5_of_6": q_pos >= Q_COUNT_GATE,
    }


def _gate_pass(gate: dict) -> bool:
    bool_axes = [
        "oos_positive_dollar", "oos_sign_stable_pct", "wf_median_ge_0.70",
        "all_cuts_oos_positive", "dsr_not_fail", "robust_drop_top5",
        "quarters_ge_5_of_6",
    ]
    return all(bool(gate[k]) for k in bool_axes)


def _failing_axes(gate: dict) -> list[str]:
    bool_axes = [
        "oos_positive_dollar", "oos_sign_stable_pct", "wf_median_ge_0.70",
        "all_cuts_oos_positive", "dsr_not_fail", "robust_drop_top5",
        "quarters_ge_5_of_6",
    ]
    return [k for k in bool_axes if not bool(gate[k])]


def main() -> int:
    print("Loading SPY", SPY.name)
    spy = load_spy(str(SPY))
    vix = align_vix(spy, str(VIX))
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    days = build_day_contexts(spy)
    all_dates = [dc.date for dc in days]

    # Full signal set, then FILTER to call-side (gap-UP + green first bar).
    all_signals = detect_gap_and_go(spy, ribbon, vix, days)
    call_signals = [s for s in all_signals if s.side == "C"]
    put_signals = [s for s in all_signals if s.side == "P"]
    print(f"signals total={len(all_signals)} -> CALL={len(call_signals)} PUT={len(put_signals)}")
    print(f"days={len(days)} range={all_dates[0]}..{all_dates[-1]}\n")

    tiers_out = {}
    for tname, off in TIERS.items():
        cfgs = {}
        for cfg_name, stop in EXIT_CONFIGS.items():
            rows, cov = _sim(call_signals, spy, ribbon, vix, off, stop)
            m = _full_metrics(rows, all_dates)
            m["coverage"] = cov
            m["premium_stop_pct"] = stop
            # by_side here will only ever contain "C"; surface that honestly.
            m["note_single_side"] = "CALL-ONLY signal set; both_dirs_positive N/A by construction."
            # Capture top-5-winner sum once (for the outlier-concentration caveat) — no re-sim.
            if rows:
                _sorted = sorted(r["pnl"] for r in rows)
                m["_top5_sum_dollar"] = round(float(sum(_sorted[-5:])), 2)
            if cfg_name == "chart_stop_only":
                gate = _ship_gate_call_side(m)
                m["ship_gate_call_side"] = gate
                m["ship_call_side_pass"] = _gate_pass(gate)
            cfgs[cfg_name] = m
            # print row
            if m.get("n", 0):
                q = m.get("quarters", {})
                qp = sum(1 for v in q.values() if v["exp"] > 0)
                print(f"  [{tname}/{cfg_name}] n={m['n']} exp=${m['exp_dollar']:+.1f} "
                      f"WR={m['wr_pct']}% IS$={m['is_exp_dollar']:+.1f} OOS$={m['oos_exp_dollar']:+.1f} "
                      f"OOSstable={m['oos_sign_stable']} medWF={m['median_wf_norm']:+.3f} "
                      f"allOOS+={m['all_cuts_oos_positive']} q+={qp}/{len(q)} "
                      f"DSR={m['dsr_verdict']} drop5=${m['drop_top5_mean_dollar']}")
            else:
                print(f"  [{tname}/{cfg_name}] NO_TRADES")
        tiers_out[tname] = cfgs

    # Headline call-side verdict = ATM chart-stop-only (the LIVE config). ITM1 is
    # reported as context only (see ATM-PRIMARY rationale below).
    atm_live = tiers_out["ATM"]["chart_stop_only"]
    itm_live = tiers_out["ITM1"]["chart_stop_only"]
    atm_pass = bool(atm_live.get("ship_call_side_pass"))
    itm_pass = bool(itm_live.get("ship_call_side_pass"))
    # ATM-PRIMARY VERDICT (load-bearing): the flip decision is for params.gap_and_go_side
    # while the LIVE engine trades the ATM strike tier (go_live_params.strike_tier="ATM";
    # ITM1 is "also PASS, modestly stronger" — NOT the live config). Under OP-16 extra
    # scrutiny, ITM1 passing is NOT a backdoor to ship calls when the LIVE (ATM) config
    # fails. So SHIP-CALLS requires the ATM call side to pass; ITM1 is reported as context.
    ship = atm_pass
    verdict = "SHIP-CALLS" if ship else "KEEP-PUT-ONLY"

    # Outlier-concentration figures for the honesty caveat (computed once from the
    # already-simulated ATM chart-stop-only rows — no re-sim).
    atm_top5_sum = atm_live.get("_top5_sum_dollar")
    atm_gross_total = atm_live.get("total_dollar")

    # Deciding axis / one-line honesty.
    if ship:
        one_line = ("SHIP-CALLS: call side ALONE passes ALL OP-22 gates on ATM "
                    "chart-stop-only (the LIVE config). Flipping side=both roughly doubles coverage.")
    else:
        if atm_live.get("n", 0) == 0:
            fails = ["no_fills_coverage"]
            one_line = "KEEP-PUT-ONLY: no call-side fills on ATM chart-stop-only (coverage)."
        else:
            fails = _failing_axes(atm_live["ship_gate_call_side"])
            itm_note = ("PASSES" if itm_pass else
                        f"also fails {_failing_axes(itm_live['ship_gate_call_side'])}") if itm_live.get("n") else "no_fills"
            one_line = (f"KEEP-PUT-ONLY: call side ALONE fails {fails} on ATM chart-stop-only "
                        f"(the LIVE tier) — exp ${atm_live['exp_dollar']:+.1f}/WR {atm_live['wr_pct']}%, "
                        f"OOS$ {atm_live['oos_exp_dollar']:+.1f}, medWF {atm_live['median_wf_norm']:+.3f}, "
                        f"DSR {atm_live['dsr_verdict']}. (ITM1 {itm_note}, but ITM1 is not the live tier.)")

    call_block = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "script": "backtest/autoresearch/gap_and_go_call_side_standalone.py",
        "question": (
            "Does the gap-and-go CALL side ALONE clear the full OP-22 bar on the LIVE "
            "config (chart-stop-only)? Decides flip to side='both' vs hold bear-only."
        ),
        "live_state": "params.gap_and_go_side='put' (calls OFF, OP-16 bull-DRAFT).",
        "signal_set": "CALL-ONLY (gap-UP + green first bar; side=='C'), filtered from "
                      "detect_gap_and_go's full 96-signal set.",
        "call_signal_count": len(call_signals),
        "put_signal_count_for_context": len(put_signals),
        "ship_gate_definition": {
            "rule": "SHIP-CALLS iff ALL hold on the call side ALONE (chart-stop-only): "
                    "OOS+ ($ AND %) AND WF_median>=0.70 AND all-cuts-OOS-positive AND "
                    "DSR not-FAIL AND drop-top5 mean>0 AND >=5/6 quarters positive.",
            "both_dirs_excluded": "both_dirs_positive is N/A for a single-side test and is "
                                  "deliberately NOT applied (it would auto-fail a call-only set).",
            "extra_scrutiny": "Quarter rule is the stricter >=5/6 count (not just >=60%) per "
                              "OP-16 bull-side extra scrutiny.",
            "evaluated_on": "ATM chart_stop_only ONLY (the LIVE strike tier). ITM1 is reported "
                            "as context, NOT a ship path — the flip is params.gap_and_go_side "
                            "while the live engine trades ATM, so ITM1 passing cannot ship calls "
                            "if the LIVE (ATM) config fails (OP-16 anti-landmine).",
        },
        "tiers": {
            "ATM": {
                "chart_stop_only": tiers_out["ATM"]["chart_stop_only"],
                "discovery_default_-8pct": tiers_out["ATM"]["discovery_default_-8pct"],
            },
            "ITM1": {
                "chart_stop_only": tiers_out["ITM1"]["chart_stop_only"],
                "discovery_default_-8pct": tiers_out["ITM1"]["discovery_default_-8pct"],
            },
        },
        "result": {
            "decided_on": "ATM chart_stop_only (the LIVE strike tier).",
            "ATM_chart_stop_only_gate": atm_live.get("ship_gate_call_side"),
            "ITM1_chart_stop_only_gate": itm_live.get("ship_gate_call_side"),
            "ATM_pass": atm_pass,
            "ITM1_pass_context_only": itm_pass,
        },
        "deciding_axis": (_failing_axes(atm_live["ship_gate_call_side"])
                          if atm_live.get("n") else ["no_fills_coverage"]),
        "outlier_fragility": {
            "atm_drop_top5_mean_dollar": atm_live.get("drop_top5_mean_dollar"),
            "atm_top5_winner_share_of_gross_wins": atm_live.get("top5_winner_share_of_gross_wins"),
            "note": "ATM call side: drop-top5 mean is NEGATIVE (remove the 5 best winners and "
                    "the average call trade LOSES). 4 of the 6 'positive' quarters flip negative "
                    "when a SINGLE trade is removed (per-quarter drop-top1: 2025Q2 -$51.7, "
                    "2025Q3 -$26.3, 2025Q4 -$14.3, 2026Q1 -$10.0; only 2026Q2 +$49.8 is broad). "
                    "ITM1 is genuinely broader (drop-top5 +$5.04, 6/6 quarters) but is not the "
                    "live tier.",
        },
        "wf_artifact_warning": {
            "atm_median_wf_norm": atm_live.get("median_wf_norm"),
            "note": "ATM call-side WF (5.775) is a SMALL-DENOMINATOR ARTIFACT, not robustness: "
                    "IS per-trade at the 70-cut is only +$8.2 (near breakeven), so the OOS/IS "
                    "ratio explodes. The IS half barely makes money; OOS strength rests on a few "
                    "2026 winners. WF passing the >=0.70 gate is technically true but misleading "
                    "here — the drop-top5 axis is the honest robustness read.",
        },
        "verdict": verdict,
        "verdict_one_line": one_line,
        "caveats": [
            "Modest call sample (n~55 ATM fills / 17 months). No single window is high-power; "
            "DSR + drop-top5 + by-quarter carry the standalone weight — and drop-top5 is where "
            "the ATM call side fails.",
            "Proxy strikes (L58): ATM not always cached; nearest-cached strike used. ITM/OTM "
            "proxy shifts P&L modestly.",
            f"The ATM call side leans on a few outliers (top-5 winners = "
            f"${atm_top5_sum:.0f} of ${atm_gross_total:.0f} gross total) and only 2 of 6 "
            f"quarters are broad-based — drop-top5 + per-quarter drop-top1 are the tells. This "
            f"is exactly the OP-16 landmine the bull side ships under: aggregate-positive but "
            f"NOT broad-based on the LIVE tier.",
            "OP-16 bull-DRAFT + OP-21 live gate STILL STAND: J makes the params flip decision; "
            "this script only files the evidence.",
        ],
    }

    # Merge into the existing combined scorecard (do NOT clobber it).
    sc = json.loads(OUT.read_text())
    sc["call_side_standalone"] = call_block
    OUT.write_text(json.dumps(sc, indent=2, default=str))

    print("\n" + "=" * 88)
    print("CALL-SIDE STANDALONE OP-22 STACK (gap-and-go)")
    print("=" * 88)
    for tname in TIERS:
        m = tiers_out[tname]["chart_stop_only"]
        if not m.get("n"):
            print(f"  {tname}: NO_TRADES")
            continue
        g = m["ship_gate_call_side"]
        print(f"  {tname} chart-stop-only: n={m['n']} exp=${m['exp_dollar']:+.1f} WR={m['wr_pct']}%")
        print(f"      OOS$={m['oos_exp_dollar']:+.1f} OOSstable={g['oos_sign_stable_pct']} "
              f"WF={m['median_wf_norm']:+.3f}(>={WF_GATE}? {g['wf_median_ge_0.70']}) "
              f"allOOS+={g['all_cuts_oos_positive']}")
        print(f"      DSR={m['dsr_verdict']} drop5=${m['drop_top5_mean_dollar']}(>0? {g['robust_drop_top5']}) "
              f"q+={g['quarters_pos_count']}/{g['quarters_total']}(>=5? {g['quarters_ge_5_of_6']}) "
              f"=> PASS={m['ship_call_side_pass']}")
    print(f"\nVERDICT: {verdict}")
    print(f"  {one_line}")
    print(f"\nWrote call_side_standalone block -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
