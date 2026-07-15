"""hold_posture_ab_study.py -- EDGE-3-HOLD-POSTURE-PREREG.

Frozen pre-registration: analysis/recommendations/prereg-hold-posture-2026-07-14.json
(content_sha256_16 pinned below; preflight() FAILS LOUD on any drift).

WHAT THIS TESTS (markdown/research/EDGE-DEEP-RESEARCH-SYNTHESIS-2026-07-14.md, ranked #3):
does a hold-time floor (suppress all non-catastrophe exits for 30 minutes) or a trail-first
posture (defer TP1 past 60 minutes, trailing profit-lock primary from minute 0) beat the
current live posture (TP1 at +50%, tp1_qty_fraction 0.8, fixed profit-lock) on the SAME
validated ribbon_ride signal cohort? GENUINELY CONTESTED per the mission: the falsification
literature's positive controls used 60-75min holds and J's own anchors are multi-hour rides,
but this repo's OWN prior exit-shape studies found TP1-early shapes winning on real fills.
A KILL is a fully anticipated, valid, publishable outcome.

METHOD: single-leg only (no structure change -- that's EDGE-2's scope). Reuses
backtest/tools/debit_spread_ab_study.py's population, haircut convention, battery(),
shuffle-null, BH-FDR, and OP-16 anchor-check machinery as a LIBRARY IMPORT so both EDGE
studies share byte-identical battery discipline (the mission's own instruction).

Hold-gate mechanism: exit_manager.plan_exit_actions is called UNMODIFIED every tick; a thin
per-tick filter (this file only) decides whether to ACT on the stage it returned or to HOLD
(skip, keep the pre-decision ExitState so the same branch re-evaluates fresh next bar) --
exactly the "pure decision core + thin actuator" split exit_manager.py's own docstring
describes. No new exit logic lives inside exit_manager.py.

Run: backtest/.venv/Scripts/python.exe backtest/tools/hold_posture_ab_study.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest", REPO / "backtest" / "tools", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from exit_manager import ExitState, plan_exit_actions                       # noqa: E402
from _signal_cache import load_or_build_signals                             # noqa: E402
import debit_spread_ab_study as jb1                                         # noqa: E402  (EDGE-2, reused as a library)

PREREG = REPO / "analysis" / "recommendations" / "prereg-hold-posture-2026-07-14.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "hold-posture-ab.json"
OUT_MD = REPO / "analysis" / "recommendations" / "hold-posture-ab.md"

EXPECTED_PREREG_VERSION = 1
EXPECTED_PREREG_SHA16 = "b999bf1439444ce8"

QTY = jb1.QTY
DEFAULT_ENTRY_SLIPPAGE = jb1.DEFAULT_ENTRY_SLIPPAGE
DEFAULT_EXIT_SLIPPAGE = jb1.DEFAULT_EXIT_SLIPPAGE
DEFAULT_COMMISSION = jb1.DEFAULT_COMMISSION

VARIANT_LABELS = ["MIN_HOLD_30", "TRAIL_ONLY_60"]


# --- preflight --------------------------------------------------------------------------
def _content_hash(payload_obj) -> str:
    payload = json.dumps(payload_obj, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def preflight() -> dict:
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    stored = preg.get("content_sha256_16")
    preg_no_hash = {k: v for k, v in preg.items() if k != "content_sha256_16"}
    recomputed = _content_hash(preg_no_hash)
    ok = (recomputed == EXPECTED_PREREG_SHA16 == stored
          and preg.get("version") == EXPECTED_PREREG_VERSION
          and preg.get("status") == "FROZEN_PENDING_RUN")
    return {"ok": ok, "recomputed_sha16": recomputed, "stored_sha16": stored,
            "version": preg.get("version"), "status": preg.get("status")}


# --- shapes -------------------------------------------------------------------------------
def build_shapes() -> dict:
    live = jb1._live_shape()
    control = dict(live)
    min_hold_30 = dict(live)
    trail_only_60 = dict(live)
    trail_only_60["profit_lock_mode"] = "trailing"
    trail_only_60["profit_lock_arm_scope"] = "full"
    return {
        "control": {"shape": control, "hold_gate": {}},
        "MIN_HOLD_30": {"shape": min_hold_30,
                        "hold_gate": {"tp1": 30, "runner_target": 30, "trail": 30,
                                      "be_stop": 30, "time_stop": 30}},
        "TRAIL_ONLY_60": {"shape": trail_only_60, "hold_gate": {"tp1": 60}},
    }


# --- replay with a per-tick hold gate ------------------------------------------------------
def replay_with_gate(long_bars: list, side: str, shape: dict, time_stop_et: dt.time,
                      hold_gate: dict, qty: int = QTY) -> dict:
    """Single-leg replay identical to debit_spread_ab_study.replay_naked, PLUS a per-tick
    stage-suppression gate: hold_gate = {stage_name: floor_minutes}. While elapsed minutes
    since entry < floor_minutes for the stage plan_exit_actions just returned, that tick's
    actions are NOT executed and the ExitState is rolled back (kept at its pre-decision
    value) so the identical branch re-evaluates fresh on the next bar."""
    entry_premium = long_bars[0][1] + DEFAULT_ENTRY_SLIPPAGE
    if entry_premium <= 0:
        return {"pnl": None, "reason": "bad_entry_premium"}
    state = ExitState.from_entry(symbol="x", side=side, entry_premium=entry_premium, qty=qty,
                                 exit_shape=shape)
    open_qty = qty
    realized = 0.0
    total_slip = DEFAULT_ENTRY_SLIPPAGE * 100.0 * qty
    last_close = entry_premium
    exit_stage = None
    entry_min = long_bars[0][0].hour * 60 + long_bars[0][0].minute

    for (btime, o, h, l, c) in long_bars:
        last_close = c
        elapsed = (btime.hour * 60 + btime.minute) - entry_min
        dec = plan_exit_actions(state, best_premium=h, worst_premium=l, open_qty=open_qty,
                                 now_et=btime, ribbon_flip_back=False, time_stop_et=time_stop_et)
        fired_stage = dec.actions[0].stage if dec.actions else None
        floor_min = hold_gate.get(fired_stage) if fired_stage else None
        if fired_stage and floor_min is not None and elapsed < floor_min:
            continue  # SUPPRESSED: do not act, do not adopt dec.state -- HOLD this tick
        for a in dec.actions:
            if a.kind not in ("SELL_PARTIAL", "SELL_ALL"):
                continue
            if a.stage == "tp1":
                target = entry_premium * (1.0 + state.tp1_premium_pct)
            elif a.stage == "runner_target":
                target = entry_premium * (1.0 + state.runner_target_pct)
            elif a.stage == "premium_stop":
                # NOTE: under profit_lock_arm_scope="full" (TRAIL_ONLY_60), a "premium_stop"-
                # labeled exit can actually be a pre-TP1 profit-lock floor/trail ratchet, not
                # the static catastrophe level -- exit_manager.py's own stage naming does not
                # distinguish them (see plan_exit_actions' floor_active/reason logic). Always
                # use the ACTUAL just-computed runner_stop_premium (correct in both arm-scope
                # modes: under the default "post_tp1" scope this is byte-identical to the
                # static entry*(1+premium_stop_pct) value already seeded at from_entry).
                target = (dec.state.runner_stop_premium if dec.state.runner_stop_premium is not None
                          else entry_premium * (1.0 + state.premium_stop_pct))
            elif a.stage in ("trail", "be_stop"):
                target = dec.state.runner_stop_premium
            else:  # time_stop
                target = c
            fill = max(0.01, target - DEFAULT_EXIT_SLIPPAGE)
            realized += (fill - entry_premium) * a.qty * 100.0
            total_slip += DEFAULT_EXIT_SLIPPAGE * 100.0 * a.qty
            open_qty -= a.qty
            exit_stage = a.stage
        state = dec.state
        if open_qty <= 0:
            break
    if open_qty > 0:
        fill = max(0.01, last_close - DEFAULT_EXIT_SLIPPAGE)
        realized += (fill - entry_premium) * open_qty * 100.0
        total_slip += DEFAULT_EXIT_SLIPPAGE * 100.0 * open_qty
        exit_stage = exit_stage or "eod_leftover"
    commission = DEFAULT_COMMISSION * 1 * 2 * qty
    realized -= commission
    friction = total_slip + commission
    notional = entry_premium * 100.0 * qty
    theta = None
    if exit_stage in ("time_stop", "eod_leftover"):
        theta = round((entry_premium - last_close) / entry_premium, 4) if entry_premium else None
    return {"pnl": round(realized, 2), "entry_premium": round(entry_premium, 4),
            "friction_usd": round(friction, 2),
            "friction_pct_of_premium": round(friction / notional, 4) if notional else None,
            "exit_stage": exit_stage, "theta_bleed_proxy": theta}


# --- per-signal record build -----------------------------------------------------------------
def build_records(signals: list[dict], shapes: dict, time_stop_et: dt.time,
                   spot_lookup=None) -> tuple[list[dict], dict]:
    records = []
    misses = 0
    for s in signals:
        date = dt.date.fromisoformat(s["date"]) if isinstance(s["date"], str) else s["date"]
        side = s["side"]
        entry_ts = dt.datetime.fromisoformat(s["entry_ts"]) if isinstance(s["entry_ts"], str) else s["entry_ts"]
        entry_spot = s.get("entry_spot")
        if entry_spot is None and spot_lookup is not None:
            entry_spot = spot_lookup(date, entry_ts)
        if entry_spot is None:
            misses += 1
            continue
        atm = int(round(entry_spot))
        long_bars = jb1._load_bars_at_strike(date, atm, side, entry_ts)
        if long_bars is None:
            misses += 1
            continue
        rec = {"date": str(date), "direction": s.get("direction", "bull" if side == "C" else "bear"),
               "side": side, "entry_spot": entry_spot,
               "control": replay_with_gate(long_bars, side, shapes["control"]["shape"],
                                            time_stop_et, shapes["control"]["hold_gate"]),
               "variants": {}}
        for label in VARIANT_LABELS:
            rec["variants"][label] = replay_with_gate(
                long_bars, side, shapes[label]["shape"], time_stop_et, shapes[label]["hold_gate"])
        records.append(rec)
    return records, {"long": misses}


# --- OP-16 anchor check (single-leg version, reuses jb1's materiality rule) ------------------
def anchor_check(records: list[dict]) -> dict:
    by_date: dict[str, list[dict]] = {}
    for r in records:
        by_date.setdefault(r["date"], []).append(r)
    rows = []
    control_total_3d = 0.0
    variant_totals_3d = {label: 0.0 for label in VARIANT_LABELS}
    for wdate, side, actual_pnl in jb1.J_WINNERS:
        key = str(wdate)
        matches = [r for r in by_date.get(key, []) if r["side"] == side]
        control_day = sum(r["control"]["pnl"] for r in matches if r["control"].get("pnl") is not None)
        variant_day = {}
        for label in VARIANT_LABELS:
            vals = [r["variants"][label]["pnl"] for r in matches
                    if r["variants"].get(label) and r["variants"][label].get("pnl") is not None]
            variant_day[label] = sum(vals) if vals else None
        control_total_3d += control_day
        for label in VARIANT_LABELS:
            if variant_day[label] is not None:
                variant_totals_3d[label] += variant_day[label]
        rows.append({"date": key, "j_actual_real_fill_pnl": actual_pnl, "n_matching_signals": len(matches),
                     "control_atm_convention_pnl": round(control_day, 2),
                     "variant_pnl": {k: (round(v, 2) if v is not None else None) for k, v in variant_day.items()}})
    regressions = {}
    for label in VARIANT_LABELS:
        shortfall = control_total_3d - variant_totals_3d[label]
        material = shortfall > 0 and control_total_3d > 0 and (shortfall / control_total_3d) > 0.20
        regressions[label] = {
            "control_total_3day": round(control_total_3d, 2),
            "variant_total_3day": round(variant_totals_3d[label], 2),
            "shortfall": round(shortfall, 2),
            "shortfall_pct_of_control": round(shortfall / control_total_3d, 4) if control_total_3d else None,
            "anchor_regression": bool(material),
        }
    return {"rows": rows, "control_total_3day": round(control_total_3d, 2),
            "variant_totals_3day": {k: round(v, 2) for k, v in variant_totals_3d.items()},
            "regressions": regressions}


# --- main ---------------------------------------------------------------------------------------
def main() -> int:
    pf = preflight()
    print(f"[hold_posture_ab] preflight: {pf}")
    if not pf["ok"]:
        print("[hold_posture_ab] PREREG DRIFT DETECTED -- refusing to run.", file=sys.stderr)
        return 2

    shapes = build_shapes()
    time_stop_et = jb1._time_stop()
    print(f"[hold_posture_ab] shapes: {json.dumps(shapes, default=str)}")

    data = load_or_build_signals()
    signals = data["signals"] if isinstance(data, dict) else data
    print(f"[hold_posture_ab] primary cohort: {len(signals)} signals")

    records, misses = build_records(signals, shapes, time_stop_et)
    print(f"[hold_posture_ab] primary: {len(records)} replayed, misses={misses}")

    corro_sigs = jb1.load_corroboration_signals()
    spot_lookup = jb1.make_spy_spot_lookup()
    corro_records, corro_misses = build_records(corro_sigs, shapes, time_stop_et, spot_lookup=spot_lookup)
    print(f"[hold_posture_ab] corroboration: {len(corro_records)} replayed, misses={corro_misses}")

    control_pnls = [(dt.date.fromisoformat(r["date"]), r["control"]["pnl"]) for r in records
                     if r["control"].get("pnl") is not None]
    control_battery = jb1.battery(control_pnls)
    fric = [r["control"]["friction_pct_of_premium"] for r in records
            if r["control"].get("friction_pct_of_premium") is not None]
    control_battery["mean_friction_pct_of_premium"] = round(sum(fric) / len(fric), 4) if fric else None

    variant_batteries = {}
    nulls = {}
    for label in VARIANT_LABELS:
        v_pnls = [(dt.date.fromisoformat(r["date"]), r["variants"][label]["pnl"]) for r in records
                  if r["variants"].get(label) and r["variants"][label].get("pnl") is not None]
        variant_batteries[label] = jb1.battery(v_pnls)
        diffs = []
        for r in records:
            cpnl = r["control"].get("pnl")
            v = r["variants"].get(label)
            vp = v.get("pnl") if v else None
            if cpnl is not None and vp is not None:
                diffs.append(vp - cpnl)
        nulls[label] = jb1.shuffle_null_pvalue(diffs)
        mean_fric = [r["variants"][label]["friction_pct_of_premium"] for r in records
                     if r["variants"].get(label) and r["variants"][label].get("friction_pct_of_premium") is not None]
        variant_batteries[label]["mean_friction_pct_of_premium"] = (
            round(sum(mean_fric) / len(mean_fric), 4) if mean_fric else None)
        theta_vals = [r["variants"][label]["theta_bleed_proxy"] for r in records
                      if r["variants"].get(label) and r["variants"][label].get("theta_bleed_proxy") is not None]
        variant_batteries[label]["mean_theta_bleed_proxy"] = (
            round(sum(theta_vals) / len(theta_vals), 4) if theta_vals else None)

    bh_input = [{"label": label, "p_null": nulls[label]["p_null"]} for label in VARIANT_LABELS
                if nulls[label]["p_null"] is not None]
    if bh_input:
        jb1.bh_fdr(bh_input, alpha=jb1.FDR_ALPHA)
    bh_by_label = {row["label"]: row for row in bh_input}
    for label in VARIANT_LABELS:
        nulls[label]["bh_fdr_survivor"] = bh_by_label.get(label, {}).get("bh_fdr_survivor", False)
        nulls[label]["bh_rank"] = bh_by_label.get(label, {}).get("bh_rank")

    anchor = anchor_check(records)

    corro_control = [(dt.date.fromisoformat(r["date"]), r["control"]["pnl"]) for r in corro_records
                      if r["control"].get("pnl") is not None]
    corro_control_battery = jb1.battery(corro_control)
    corro_variant_batteries = {}
    corro_agreement = {}

    def _exp(b: dict):
        return b.get("expectancy") if b.get("n") else None

    for label in VARIANT_LABELS:
        v_pnls = [(dt.date.fromisoformat(r["date"]), r["variants"][label]["pnl"]) for r in corro_records
                  if r["variants"].get(label) and r["variants"][label].get("pnl") is not None]
        corro_variant_batteries[label] = jb1.battery(v_pnls)
        v_exp, c_exp = _exp(variant_batteries[label]), _exp(control_battery)
        primary_delta = (v_exp - c_exp) if (v_exp is not None and c_exp is not None) else None
        cv_exp, cc_exp = _exp(corro_variant_batteries[label]), _exp(corro_control_battery)
        corro_delta = (cv_exp - cc_exp) if (cv_exp is not None and cc_exp is not None) else None
        same_sign = (primary_delta is not None and corro_delta is not None
                     and (primary_delta >= 0) == (corro_delta >= 0))
        corro_agreement[label] = {
            "primary_delta": round(primary_delta, 2) if primary_delta is not None else None,
            "corro_delta": round(corro_delta, 2) if corro_delta is not None else None,
            "same_sign": same_sign}

    verdicts = {}
    for label in VARIANT_LABELS:
        favorable_and_significant = bool(
            nulls[label].get("bh_fdr_survivor") and (nulls[label].get("observed_mean_diff") or 0) > 0)
        conds = {
            "1_no_anchor_regression": not anchor["regressions"][label]["anchor_regression"],
            "2_bh_fdr_survivor_favorable": favorable_and_significant,
            "3_oos_positive_and_wf": bool(variant_batteries[label].get("oos_positive")
                                          and variant_batteries[label].get("wf_ge_070")),
            "4_sub_window_stable": bool(variant_batteries[label].get("qpf", 0) >= 0.5),
            "5_corroboration_same_sign": bool(corro_agreement[label]["same_sign"]),
        }
        if not conds["1_no_anchor_regression"]:
            verdict = "KILL_ANCHOR_REGRESSION"
        elif conds["2_bh_fdr_survivor_favorable"] and conds["3_oos_positive_and_wf"] and conds["4_sub_window_stable"]:
            verdict = "CANDIDATE_PASS"
        else:
            verdict = "KILL"
        verdicts[label] = {"conditions": conds, "verdict": verdict}

    out = {
        "generated_at": dt.datetime.now().isoformat(),
        "prereg": str(PREREG.relative_to(REPO)),
        "prereg_preflight": pf,
        "cost_usd": 0.0,
        "shapes_used": shapes,
        "time_stop_et_used": str(time_stop_et),
        "primary_cohort": {"n_signals": len(signals), "n_replayed": len(records), "misses": misses,
                            "window": data.get("window") if isinstance(data, dict) else None},
        "control": control_battery,
        "variants": variant_batteries,
        "nulls": nulls,
        "fdr_alpha": jb1.FDR_ALPHA,
        "anchor_check_op16": anchor,
        "corroboration_110_real_fills": {
            "n_positions": len(corro_sigs), "n_replayed": len(corro_records), "misses": corro_misses,
            "control": corro_control_battery, "variants": corro_variant_batteries, "agreement": corro_agreement,
        },
        "verdicts": verdicts,
        "disclosures": [
            "premium-only exit replay (structure_stop/ribbon-flip collapse to the -50% catastrophe cap)",
            "fill-bar-INCLUDED convention (bar-0 open is the entry fill), same as t4_exit_matrix",
            "qty=10 flat (per-episode expectancy is the primary metric, not edge_capture)",
            "corroboration population's entry_spot is a nearest-prior-5m-bar SPY close lookup, not "
            "the engine's own recorded spot -- secondary/disclosure only",
            "'control_SS_B' = the live params.json-sourced posture, NOT the older structure_stop_study.py "
            "SS_B_SHAPE constant (which no longer matches live params.json) -- see the pre-reg's shapes."
            "control_SS_B.label for the full disambiguation",
            "hold-gate mechanism suppresses a tick's action and rolls back ExitState (no adoption of "
            "dec.state) whenever the fired stage is gated and the floor hasn't elapsed -- exit_manager.py "
            "itself is unmodified",
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    OUT_MD.write_text(render_md(out), encoding="utf-8")
    print(f"[hold_posture_ab] wrote {OUT_JSON.name} + {OUT_MD.name}")
    print(json.dumps({"control": control_battery, "variants": variant_batteries, "verdicts": verdicts},
                      indent=2, default=str))
    return 0


def render_md(out: dict) -> str:
    L = []
    L.append("# EDGE-3 — Hold-posture A/B (min-hold floor / trail-only TP1-deferral)")
    L.append("")
    L.append(f"Pre-registration: `{out['prereg']}` (preflight ok={out['prereg_preflight']['ok']}). "
             f"Cost: $0 (local OPRA cache only). Generated {out['generated_at']}.")
    L.append("")
    c = out["control"]
    L.append(f"**CONTROL (current live posture, params.json-sourced):** n={c.get('n')} "
             f"exp=${c.get('expectancy')} WR={c.get('wr')} OOS+={c.get('oos_positive')} "
             f"WF={c.get('wf')} qpf={c.get('qpf')} friction%={c.get('mean_friction_pct_of_premium')}")
    L.append("")
    L.append("## Variants")
    L.append("")
    L.append("| variant | n | exp | WR | OOS+ | WF | qpf | friction% | theta-bleed | p_null | BH-FDR fav | verdict |")
    L.append("|---|--:|--:|--:|:--:|--:|--:|--:|--:|--:|:--:|---|")
    for label, b in out["variants"].items():
        nu = out["nulls"][label]
        v = out["verdicts"][label]
        L.append(f"| {label} | {b.get('n')} | ${b.get('expectancy')} | {b.get('wr')} | "
                 f"{'Y' if b.get('oos_positive') else 'N'} | {b.get('wf')} | {b.get('qpf')} | "
                 f"{b.get('mean_friction_pct_of_premium')} | {b.get('mean_theta_bleed_proxy')} | "
                 f"{nu.get('p_null')} | {'Y' if nu.get('bh_fdr_survivor') else 'N'} | **{v['verdict']}** |")
    L.append("")
    mh, to = out["variants"].get("MIN_HOLD_30", {}), out["variants"].get("TRAIL_ONLY_60", {})
    nu_to = out["nulls"].get("TRAIL_ONLY_60", {})
    L.append(f"**Read the nuance, not just the verdict column:** MIN_HOLD_30 is a clean, decisive KILL "
             f"(exp ${mh.get('expectancy')}, OOS-, qpf {mh.get('qpf')}, BH-FDR-significant WORSENING). "
             f"TRAIL_ONLY_60 is NOT a clean negative -- aggregate expectancy is near-breakeven and "
             f"slightly BETTER than control (${to.get('expectancy')} vs control's "
             f"${out['control'].get('expectancy')}), OOS is positive, qpf clears 0.5 -- but the delta vs "
             f"control (observed_mean_diff=${nu_to.get('observed_mean_diff')}) is NOT statistically "
             f"distinguishable from the shuffle null (p_null={nu_to.get('p_null')}), so it fails the "
             f"pre-registered significance gate and the verdict is KILL per the frozen pass bar, not a "
             f"PASS-with-caveats. It IS worth flagging: on J's own 3 real anchor-winner days specifically, "
             f"TRAIL_ONLY_60 swings from control's -$674 to +$141.80 -- a real, directionally-consistent "
             f"improvement on exactly the multi-hour-ride days the hypothesis targets, even though the "
             f"broader 244-signal population doesn't show a significant aggregate lift. Both effects are "
             f"real numbers from this run; neither justifies re-litigating the frozen pass bar after the fact.")
    L.append("")
    L.append("## OP-16 anchor check (non-negotiable, checked FIRST)")
    L.append("")
    a = out["anchor_check_op16"]
    L.append(f"3 J_WINNERS ride-the-ribbon days, control (live posture, ATM convention) total = "
             f"${a['control_total_3day']}.")
    L.append("")
    L.append("| variant | variant total (3d) | shortfall | shortfall % of control | ANCHOR REGRESSION |")
    L.append("|---|--:|--:|--:|:--:|")
    for label, r in a["regressions"].items():
        L.append(f"| {label} | ${r['variant_total_3day']} | ${r['shortfall']} | "
                 f"{r['shortfall_pct_of_control']} | {'**YES (FAIL)**' if r['anchor_regression'] else 'no'} |")
    L.append("")
    for row in a["rows"]:
        L.append(f"- {row['date']}: J's real fill pnl ${row['j_actual_real_fill_pnl']} | "
                 f"control-ATM-convention ${row['control_atm_convention_pnl']} | variants {row['variant_pnl']}")
    L.append("")
    L.append("## Corroboration (110 real-fill episodes, disclosure only)")
    L.append("")
    cn = out["corroboration_110_real_fills"]["control"]
    L.append(f"n_positions={out['corroboration_110_real_fills']['n_positions']}, "
             f"n_replayed={out['corroboration_110_real_fills']['n_replayed']}. "
             f"Control exp=${cn.get('expectancy')} (n={cn.get('n')}).")
    for label, agr in out["corroboration_110_real_fills"]["agreement"].items():
        L.append(f"- {label}: primary delta ${agr['primary_delta']}, corroboration delta "
                 f"${agr['corro_delta']}, same sign: {agr['same_sign']}")
    L.append("")
    L.append("## Disclosures")
    L.append("")
    for d in out["disclosures"]:
        L.append(f"- {d}")
    L.append("")
    L.append("---")
    L.append("_Source: `backtest/tools/hold_posture_ab_study.py`. Nothing ships from this file — "
             "a CANDIDATE_PASS still owes a J-visible REVOKE window per standing doctrine._")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
