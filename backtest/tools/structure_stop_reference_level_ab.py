"""structure_stop_reference_level_ab.py -- STOP-REFERENCE-CHOICE sweep for the ALREADY-LIVE
structure stop (item (b) of queue item STRUCTURE-STOP-ZONE-BAND, re-filed standalone as
STRUCTURE-STOP-REFERENCE-LEVEL after item (a)'s buffer-width sweep on the trigger-exact
reference closed REJECT_ALL_CANDIDATES 2026-07-20).

Runs the FROZEN pre-registration (analysis/recommendations/structure-stop-reference-level-
preregistration.json) -- no re-picks after seeing results. Isolates ONE variable: WHICH level
the structure stop's close-vs-level test compares against.

  REF-EXACT (control): trigger_exact -- today's literal live behavior (== item (a)'s BAND-00).
  REF-ZONE:            zone_boundary -- the nearest active level STRICTLY BEYOND the recovered
                        trigger_level, away from spot (puts: next level above; calls: next level
                        below), within max_distance=2.00 (mirrors exit_manager.nearest_active_
                        level's own default). Falls back to REF-EXACT when no further level
                        exists that day.
  REF-NONE:             no structure check at all -- pure SS-B premium-only replay. Isolates
                        whether ANY structure reference beats having none.

Band width is held at 0.00 for every candidate BY RULE (see the pre-reg's band_width_rule):
item (a) already falsified band-width as a lever on the trigger-exact reference; re-opening it
here without first showing the reference itself carries signal would be fishing.

REUSES structure_stop_study.py's already-built, already-tested machinery UNCHANGED:
  * prepare_layer_a / prepare_positions / recover_trigger_level_real_position
  * structure_stop_signal_time (buffer arg held at 0.0) / replay_structure_aware
  * tw8_level_context.frozen_level_set_for_date -- the per-day-frozen multi-level active set
    (LevelSet.active) that ALSO produced the recovered trigger_level, so REF-ZONE is computed
    from the identical level snapshot as REF-EXACT (no new look-ahead risk).

ANALYSIS ONLY: writes only to analysis/recommendations/. Never touches strategies.py,
params.json, exit_manager.py, or any trading-path file.

Run: backtest/.venv/Scripts/python.exe backtest/tools/structure_stop_reference_level_ab.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

import pandas as pd  # noqa: E402

import structure_stop_study as sss              # noqa: E402  (the machinery this reuses)
import tw8_level_context as lc                   # noqa: E402
import exit_shape_parity_study as esp            # noqa: E402
import t4_exit_matrix as t4                      # noqa: E402  (battery, QTY)

PREREG = REPO / "analysis" / "recommendations" / "structure-stop-reference-level-preregistration.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "structure-stop-reference-level-2026-07-20.json"

EXPECTED_FRESH_SHA16 = "d10e1a3a51cbf155"
EXPECTED_ANCHOR_POP_SHA16 = "0c2d963360e57fd7"
EXPECTED_PREREG_VERSION = 1

ANCHOR_END_DATE = "2026-07-17"   # today (2026-07-20, the hypothesis day) is EXCLUDED -- exhibit only
TODAY = dt.date(2026, 7, 20)
LEVEL_HISTORY_START = dt.date(2026, 5, 19)   # matches the cached SPY 5m file window (item (a))
LEVEL_HISTORY_END = dt.date(2026, 7, 17)

MIDPOINT_DATE = "2026-07-08"   # sub-window split: <= this = first half, > this = second half

ZONE_MAX_DISTANCE = 2.00   # mirrors exit_manager.nearest_active_level's own default

FIXED_SHAPE = {"premium_stop_pct": -0.50, "tp1_premium_pct": 1.0, "tp1_qty_fraction": 0.667,
               "profit_lock_mode": "trailing", "trail_pct": 0.15, "runner_target_pct": 9.9}

CANDIDATE_IDS = ("REF-EXACT", "REF-ZONE", "REF-NONE")
CONTROL_ID = "REF-EXACT"


def _content_hash(payload_obj) -> str:
    payload = json.dumps(payload_obj, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def anchor_population_signature(positions: list[dict]) -> list[dict]:
    sig = [{"date_et": p["date_et"], "symbol": p["symbol"], "arm": p["arm"],
            "entry_ts_utc": p["entry_ts_utc"], "entry_qty": p["entry_qty"]} for p in positions]
    return sorted(sig, key=lambda x: (x["date_et"], x["symbol"], x["arm"], x["entry_ts_utc"]))


def preflight() -> dict:
    fresh_raw = json.loads(sss.FRESH_SIGNAL_SET.read_text(encoding="utf-8"))
    fresh_sha16 = _content_hash(fresh_raw["signals"])[:16]

    fills = esp.load_fleet_engine_fills()
    positions = esp.reconstruct_positions(fills)
    anchor_positions = [p for p in positions if p["date_et"] <= ANCHOR_END_DATE]
    anchor_sha16 = _content_hash(anchor_population_signature(anchor_positions))[:16]

    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    ver = preg.get("version")

    return {
        "fresh_slice_sha256_16": fresh_sha16, "fresh_slice_hash_ok": fresh_sha16 == EXPECTED_FRESH_SHA16,
        "anchor_population_sha256_16": anchor_sha16,
        "anchor_population_hash_ok": anchor_sha16 == EXPECTED_ANCHOR_POP_SHA16,
        "preregistration_version": ver, "preregistration_version_ok": ver == EXPECTED_PREREG_VERSION,
    }


# ---------------------------------------------------------------------------------------------
# ZONE-BOUNDARY RESOLUTION -- pure, reuses the SAME frozen LevelSet that produced trigger_level
# ---------------------------------------------------------------------------------------------
def resolve_zone_boundary(level_set, trigger_level: Optional[float], side: str,
                          max_distance: float = ZONE_MAX_DISTANCE) -> Optional[float]:
    """Nearest active level strictly beyond trigger_level, away from spot (puts: next level
    ABOVE trigger; calls: next level BELOW trigger), within max_distance. None if no level_set,
    no trigger_level, or no such level exists -- callers must fall back to trigger_level
    identically (byte-identical degradation, never a guess)."""
    if level_set is None or trigger_level is None or side not in ("P", "C"):
        return None
    active = level_set.active
    if side == "P":
        candidates = [lv for lv in active if lv > trigger_level + 1e-9]
        nxt = min(candidates) if candidates else None
    else:
        candidates = [lv for lv in active if lv < trigger_level - 1e-9]
        nxt = max(candidates) if candidates else None
    if nxt is None or abs(nxt - trigger_level) > max_distance:
        return None
    return round(nxt, 2)


def reference_level_for(cid: str, trigger_level: Optional[float],
                        zone_boundary: Optional[float]) -> Optional[float]:
    """The level structure_stop_signal_time actually compares against for this candidate."""
    if cid == "REF-NONE":
        return None   # no structure check -- ss_time always None regardless of level
    if cid == "REF-ZONE":
        return zone_boundary if zone_boundary is not None else trigger_level
    return trigger_level   # REF-EXACT


# ---------------------------------------------------------------------------------------------
# PREP -- layer(a) fresh-slice + layer(b)/exhibit real positions, both zone-boundary-augmented
# ---------------------------------------------------------------------------------------------
def prep_layer_a_with_zone() -> tuple[list[dict], int, pd.DataFrame]:
    prepared, n_missing_bars, spy_full = sss.prepare_layer_a()
    level_cache: dict = {}
    for p in prepared:
        level_set = lc.frozen_level_set_for_date(spy_full, p["date"], level_cache)
        p["zone_boundary"] = resolve_zone_boundary(level_set, p["trigger_level"], p["side"])
    return prepared, n_missing_bars, spy_full


def prep_positions_with_zone(positions: list[dict], spy_full: pd.DataFrame) -> tuple[list[dict], dict]:
    prepared, stats = sss.prepare_positions(positions, spy_full)
    level_cache: dict = {}
    n_zone_resolved = 0
    for p in prepared:
        date = dt.date.fromisoformat(p["date_et"])
        level_set = lc.frozen_level_set_for_date(spy_full, date, level_cache)
        zb = resolve_zone_boundary(level_set, p["trigger_level"], p["side"])
        p["zone_boundary"] = zb
        if zb is not None:
            n_zone_resolved += 1
    stats["n_zone_resolved"] = n_zone_resolved
    return prepared, stats


# ---------------------------------------------------------------------------------------------
# LAYER (a) -- FRESH-SLICE, reference resolution swept
# ---------------------------------------------------------------------------------------------
def run_layer_a(prepared: list[dict]) -> dict:
    n_recoverable = sum(1 for p in prepared if p["trigger_level"] is not None)
    n_zone_resolved = sum(1 for p in prepared if p.get("zone_boundary") is not None)
    out = {"n_signals": len(prepared), "n_recoverable_trigger_level": n_recoverable,
           "n_zone_resolved": n_zone_resolved, "n_fallback": len(prepared) - n_recoverable,
           "candidates": {}}
    for cid in CANDIDATE_IDS:
        trades = []
        for p in prepared:
            ref_level = reference_level_for(cid, p["trigger_level"], p["zone_boundary"])
            ss_time = sss.structure_stop_signal_time(p["spy_lifetime"], p["side"], ref_level, 0.0)
            r = sss.replay_structure_aware(p["entry_premium"], p["side"], t4.QTY, p["norm_bars"],
                                           ss_time, FIXED_SHAPE, sss.TIME_STOP_LAYER_A)
            trades.append({"date": p["date"], "direction": p["direction"], "band": p["band"],
                          "pnl": r["pnl"], "structure_fired": r["structure_fired"]})
        b = t4.battery(trades)
        n_structure_fired = sum(1 for t in trades if t.get("structure_fired"))
        out["candidates"][cid] = {**b, "n_structure_fired": n_structure_fired}
    return out


# ---------------------------------------------------------------------------------------------
# LAYER (b) -- REAL-FILLS ANCHOR, reference resolution swept, + sub-window split
# ---------------------------------------------------------------------------------------------
def replay_population(prepared: list[dict], cid: str) -> dict:
    tot, n_structure_fired = 0.0, 0
    rows = []
    for p in prepared:
        ref_level = reference_level_for(cid, p["trigger_level"], p["zone_boundary"])
        ss_time = sss.structure_stop_signal_time(p["spy_lifetime"], p["side"], ref_level, 0.0)
        r = sss.replay_structure_aware(p["entry_premium"], p["side"], p["qty"], p["norm_bars"],
                                       ss_time, FIXED_SHAPE, sss.TIME_STOP_LAYER_B)
        tot += r["pnl"]
        if r["structure_fired"]:
            n_structure_fired += 1
        rows.append({"arm": p["arm"], "symbol": p["symbol"], "date_et": p["date_et"],
                     "pnl": r["pnl"], "structure_fired": r["structure_fired"],
                     "trigger_level": p["trigger_level"], "zone_boundary": p.get("zone_boundary"),
                     "reference_used": ref_level, "recovery_status": p["recovery_status"],
                     "actual_exit_pnl": p.get("actual_exit_pnl")})
    return {"anchor_total": round(tot, 2), "n_valid": len(prepared),
           "n_structure_fired": n_structure_fired, "rows": rows}


def run_layer_b(spy_full: pd.DataFrame) -> tuple[dict, dict, dict]:
    fills = esp.load_fleet_engine_fills()
    positions = esp.reconstruct_positions(fills)
    anchor_positions = [p for p in positions if p["date_et"] <= ANCHOR_END_DATE]
    prepared, stats = prep_positions_with_zone(anchor_positions, spy_full)

    first_half = [p for p in prepared if p["date_et"] <= MIDPOINT_DATE]
    second_half = [p for p in prepared if p["date_et"] > MIDPOINT_DATE]

    uniq = sorted(set((p["date_et"], p["symbol"]) for p in prepared))
    dates = sorted(set(p["date_et"] for p in prepared))
    actual_total = round(sum(p.get("actual_exit_pnl") or 0.0 for p in prepared), 2)

    out = {**stats, "n_unique_signals": len(uniq), "n_trading_days": len(dates),
           "date_span": f"{dates[0]}..{dates[-1]}" if dates else None,
           "actual_realized_total": actual_total,
           "n_first_half": len(first_half), "n_second_half": len(second_half),
           "candidates": {}}
    sub_windows = {"first_half": {}, "second_half": {}}
    all_rows = {}
    for cid in CANDIDATE_IDS:
        r = replay_population(prepared, cid)
        out["candidates"][cid] = {k: v for k, v in r.items() if k != "rows"}
        all_rows[cid] = r["rows"]
        rf = replay_population(first_half, cid)
        rs = replay_population(second_half, cid)
        sub_windows["first_half"][cid] = {"anchor_total": rf["anchor_total"], "n_valid": rf["n_valid"]}
        sub_windows["second_half"][cid] = {"anchor_total": rs["anchor_total"], "n_valid": rs["n_valid"]}
    return out, sub_windows, all_rows


# ---------------------------------------------------------------------------------------------
# TODAY EXHIBIT (2026-07-20) -- separate, EXHIBIT ONLY, excluded from all verdicts
# ---------------------------------------------------------------------------------------------
def run_today_exhibit(spy_full: pd.DataFrame) -> dict:
    fills = esp.load_fleet_engine_fills()
    positions = esp.reconstruct_positions(fills)
    today_positions = [p for p in positions if p["date_et"] == TODAY.isoformat()]
    prepared, stats = prep_positions_with_zone(today_positions, spy_full)

    actual_total = round(sum(p.get("actual_exit_pnl") or 0.0 for p in prepared), 2)
    recovered_levels = sorted({p["trigger_level"] for p in prepared if p["trigger_level"] is not None})
    zone_levels = sorted({p["zone_boundary"] for p in prepared if p.get("zone_boundary") is not None})

    out = {**stats, "actual_realized_total": actual_total,
           "recovered_trigger_levels": recovered_levels,
           "resolved_zone_boundaries": zone_levels,
           "task_cited_trigger_level": 744.92,
           "task_cited_zone_top": 745.40,
           "candidates": {}}
    for cid in CANDIDATE_IDS:
        r = replay_population(prepared, cid)
        out["candidates"][cid] = r
    return out


# ---------------------------------------------------------------------------------------------
# VERDICTS
# ---------------------------------------------------------------------------------------------
def build_verdicts(layer_a: dict, layer_b: dict, sub_windows: dict) -> dict:
    verdicts = {}
    ctl_a_exp = layer_a["candidates"][CONTROL_ID]["expectancy"]
    ctl_b_total = layer_b["candidates"][CONTROL_ID]["anchor_total"]
    ctl_first = sub_windows["first_half"][CONTROL_ID]["anchor_total"]
    ctl_second = sub_windows["second_half"][CONTROL_ID]["anchor_total"]
    n_recoverable_b = layer_b["n_recoverable_trigger_level"]
    for cid in CANDIDATE_IDS:
        if cid == CONTROL_ID:
            continue
        a = layer_a["candidates"][cid]
        b = layer_b["candidates"][cid]
        cond1_layer_b = bool(b["anchor_total"] > ctl_b_total)
        cond2_layer_a = bool(a["expectancy"] is not None and ctl_a_exp is not None
                             and a["expectancy"] > ctl_a_exp)
        delta_first = sub_windows["first_half"][cid]["anchor_total"] - ctl_first
        delta_second = sub_windows["second_half"][cid]["anchor_total"] - ctl_second
        sign_flip = (delta_first > 0) != (delta_second > 0) if (delta_first != 0 and delta_second != 0) else False
        underpowered = n_recoverable_b < 15
        overall = "PASS" if (cond1_layer_b and cond2_layer_a) else "FAIL"
        if overall == "PASS" and underpowered:
            overall = "INCONCLUSIVE_UNDERPOWERED"
        if overall == "PASS" and sign_flip:
            overall = "NO_SHIP_SUBWINDOW_UNSTABLE"
        verdicts[cid] = {
            "condition_1_layer_b_beats_control": cond1_layer_b,
            "condition_2_layer_a_beats_control": cond2_layer_a,
            "sub_window_delta_first_half": round(delta_first, 2),
            "sub_window_delta_second_half": round(delta_second, 2),
            "sub_window_sign_flip": sign_flip,
            "n_recoverable_trigger_level_layer_b": n_recoverable_b,
            "underpowered_lt15": underpowered,
            "overall": overall,
            "reason": (f"layer(a) exp ${a['expectancy']} vs control ${ctl_a_exp} "
                      f"({'PASS' if cond2_layer_a else 'FAIL'}); "
                      f"layer(b) anchor ${b['anchor_total']} vs control ${ctl_b_total} "
                      f"({'PASS' if cond1_layer_b else 'FAIL'}); "
                      f"sub-window deltas first=${round(delta_first,2)} second=${round(delta_second,2)} "
                      f"(sign_flip={sign_flip}); n_recoverable(layer b)={n_recoverable_b} "
                      f"({'UNDERPOWERED' if underpowered else 'floor-clearing'})"),
        }
    return verdicts


# ---------------------------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------------------------
def main() -> int:
    pf = preflight()
    print(f"[ssr] preflight: {pf}", flush=True)
    if not (pf["fresh_slice_hash_ok"] and pf["anchor_population_hash_ok"] and pf["preregistration_version_ok"]):
        print("[ssr] PREFLIGHT FAILED -- aborting (no re-picks, no stale-hash runs)", file=sys.stderr)
        return 1

    print("[ssr] loading SPY 5m bars (cached 2026-05-19..2026-07-17)...", flush=True)
    spy_full = lc.load_spy_full(LEVEL_HISTORY_START, LEVEL_HISTORY_END)
    print(f"[ssr] spy_full: {len(spy_full)} rows, {spy_full['date'].min()}..{spy_full['date'].max()}",
          flush=True)

    print("[ssr] layer (a): fresh-slice prep + zone-boundary resolution...", flush=True)
    prepared_a, n_missing_bars_a, _spy_a = prep_layer_a_with_zone()
    print(f"[ssr] layer (a): {len(prepared_a)} prepared "
          f"({sum(1 for p in prepared_a if p['trigger_level'] is not None)} recoverable trigger_level, "
          f"{sum(1 for p in prepared_a if p.get('zone_boundary') is not None)} zone-resolved)", flush=True)
    layer_a = run_layer_a(prepared_a)
    layer_a["n_missing_bars"] = n_missing_bars_a

    print("[ssr] layer (b): real-fills anchor (network calls to Alpaca OPRA, rate-limited)...", flush=True)
    layer_b, sub_windows, layer_b_rows = run_layer_b(spy_full)
    print(f"[ssr] layer (b): {layer_b['n_positions_with_bars']} positions with bars "
          f"({layer_b['n_recoverable_trigger_level']} recoverable trigger_level, "
          f"{layer_b['n_zone_resolved']} zone-resolved)", flush=True)

    print("[ssr] today exhibit (2026-07-20) -- EXHIBIT ONLY...", flush=True)
    today_exhibit = run_today_exhibit(spy_full)
    print(f"[ssr] today exhibit: {today_exhibit['n_positions_with_bars']} positions, "
          f"recovered levels {today_exhibit['recovered_trigger_levels']}, "
          f"zone boundaries {today_exhibit['resolved_zone_boundaries']} "
          f"(task-cited trigger {today_exhibit['task_cited_trigger_level']}, "
          f"task-cited zone-top {today_exhibit['task_cited_zone_top']})", flush=True)

    verdicts = build_verdicts(layer_a, layer_b, sub_windows)
    for cid, v in verdicts.items():
        print(f"[ssr] {cid}: {v['overall']} -- {v['reason']}", flush=True)

    disclosures = [
        "This study isolates ONLY the structure-stop REFERENCE LEVEL choice. Band/buffer width "
        "is held at 0.00 for every candidate by rule -- item (a) (structure-stop-zone-band-"
        "2026-07-20.json) already falsified band-width as a lever on the trigger-exact reference "
        "(REJECT_ALL_CANDIDATES); this study does not re-open that axis.",
        "Fixed exit shape = SS-B (the shape genuinely live today, structure_stop_enabled=true), "
        "held constant across every candidate, identical to item (a)'s fixed shape.",
        "Zone-boundary resolution reuses the SAME frozen per-day LevelSet.active (tw8_level_"
        "context.frozen_level_set_for_date) that produced the recovered trigger_level -- REF-ZONE "
        "and REF-EXACT are computed from the identical level snapshot, so no additional look-"
        "ahead is introduced. max_distance=2.00 mirrors exit_manager.nearest_active_level's own "
        "production default.",
        f"Trigger-level recovery: layer (a) exact entry_spot-matched; layer (b)/exhibit backward-"
        f"scan heuristic (lookback={sss.TRIGGER_RECOVERY_LOOKBACK_BARS} bars). Positions with no "
        f"recoverable trigger_level (or no resolvable zone_boundary, for REF-ZONE) fall back to "
        f"the SAME reference identically across candidates, never dropped.",
        "C6 fill-mark convention: the structure stop fires at the NEXT 5m bar's OPEN premium.",
        "Anchor is CLOSED (date_et<=2026-07-17); 2026-07-20 (today, the hypothesis-generating day) "
        "is EXHIBIT ONLY, excluded from every pass/fail layer -- testing on the day that generated "
        "the hypothesis would be circular.",
        f"Sub-window split at {MIDPOINT_DATE} (~50/50 by position count, identical split to item "
        f"(a)): first_half n={layer_b['n_first_half']}, second_half n={layer_b['n_second_half']}. "
        f"A nominal PASS with a sub-window sign flip is downgraded to NO_SHIP_SUBWINDOW_UNSTABLE "
        f"(the exact C24 single-anchor-trade signature item (a) found).",
        "Small-n: only positions with a recoverable trigger_level are exposed to the reference "
        "choice at all; n_recoverable_trigger_level<15 on layer (b) is disclosed as INCONCLUSIVE_"
        "UNDERPOWERED per the evidence-floor doctrine, not silently passed or failed.",
        "Frictionless fills at trigger/stop/target levels (no spread/queue modelled), matching "
        "every prior study in this codebase (T3/T4/T5/T-W8/structure_stop_study/item (a)).",
    ]

    key_findings = []
    ctl_a = layer_a["candidates"][CONTROL_ID]
    ctl_b = layer_b["candidates"][CONTROL_ID]
    key_findings.append(
        f"REF-EXACT (CONTROL, literal current-live behavior): layer(a) exp ${ctl_a['expectancy']}/tr "
        f"(n={ctl_a['n']}), layer(b) anchor total ${ctl_b['anchor_total']} "
        f"(n={ctl_b['n_valid']} positions, {layer_b['n_recoverable_trigger_level']} recoverable) -- "
        f"the numbers every reference candidate is measured against.")
    for cid in CANDIDATE_IDS:
        if cid == CONTROL_ID:
            continue
        a = layer_a["candidates"][cid]
        b = layer_b["candidates"][cid]
        key_findings.append(
            f"{cid}: layer(a) exp ${a['expectancy']}/tr "
            f"(fired {a['n_structure_fired']}/{layer_a['n_signals']}), layer(b) anchor "
            f"${b['anchor_total']} (fired {b['n_structure_fired']}/{layer_b['n_positions_with_bars']}) "
            f"-> {verdicts[cid]['overall']}.")
    key_findings.append(
        f"TODAY EXHIBIT (2026-07-20, EXCLUDED from pass/fail): {today_exhibit['n_positions_with_bars']} "
        f"positions, actual realized ${today_exhibit['actual_realized_total']}, recovered trigger "
        f"level(s) {today_exhibit['recovered_trigger_levels']} vs. task-cited "
        f"{today_exhibit['task_cited_trigger_level']}, resolved zone boundary(ies) "
        f"{today_exhibit['resolved_zone_boundaries']} vs. task-cited zone-top "
        f"{today_exhibit['task_cited_zone_top']} -- "
        + ", ".join(f"{cid} replayed ${today_exhibit['candidates'][cid]['anchor_total']} "
                    f"(fired {today_exhibit['candidates'][cid]['n_structure_fired']}/"
                    f"{today_exhibit['n_positions_with_bars']})" for cid in CANDIDATE_IDS)
        + ".")

    out = {
        "_doc": "STRUCTURE-STOP reference-level (trigger-exact vs zone-boundary vs none) sweep -- "
                "pre-registered, frozen before any candidate replay. ANALYSIS ONLY: no trading-"
                "path file touched by this run. 2026-07-20 is EXHIBIT ONLY.",
        "generated_at": dt.datetime.now().isoformat(),
        "preregistration_file": str(PREREG.relative_to(REPO)).replace("\\", "/"),
        "preflight": pf,
        "layer_a_fresh_slice": layer_a,
        "layer_b_real_fills_anchor": layer_b,
        "layer_b_sub_windows": sub_windows,
        "layer_b_position_detail": layer_b_rows,
        "today_exhibit_2026_07_20": today_exhibit,
        "verdicts": verdicts,
        "key_findings": key_findings,
        "disclosures": disclosures,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[ssr] wrote {OUT_JSON}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
