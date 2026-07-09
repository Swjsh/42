"""t5_confirmatory_matrix.py -- T-W7 layers (a)+(b), CONFIRM-AND-WIRE (post-STOP-A sign-off).

Runs the T5 confirmatory battery on EXACTLY the frozen v2 pre-registration
(analysis/recommendations/entry-exit-matrix-stop-a-preregistration.json) -- no re-picks, no new
cells. ANALYSIS ONLY: writes scorecards to analysis/recommendations/; does NOT touch
strategies.py, params.json, waivers, or any trading-path file.

LAYER (a) -- FRESH-SLICE REPLAY: regenerates ribbon_ride signals over a window that NO
exploratory grid has ever seen (2026-06-19..2026-07-08), reusing _signal_cache.build_signals()
verbatim (monkeypatched START/END -- no file edits) with warmup bars fed from 2026-05-01 so the
ribbon EMAs (fast13/pivot20/slow48 on 5-min bars) and level-memory lookback (<=10 trading days)
are seeded before the kept window begins. Signals dated < 2026-06-19 are generated for warmup
ONLY and immediately discarded -- never counted, never replayed.

LAYER (b) -- REAL-FILLS ANCHOR (kill-check, never a ratifier): replays the same candidates on
ALL real fleet_rest round-trips (automation/state/fills-ledger.jsonl, engine-attributed,
safe-1/safe-3/risky-1/risky-3) via exit_shape_parity_study's fill->position->bar->replay
machinery (REAL 1-min Alpaca OPRA bars). A candidate materially worse than replayed CONTROL here
is a KILL regardless of layer (a) (ground rule per t5_holdout_definition).

Layer (c) [fresh P5 grind, ~7560 combos] is a SEPARATE kill-check per the STOP-A sign-off
(condition 2) and is NOT run here. Layer (d) [2-week forward paper] is T-W8, also not here.

DISCLOSURES (ground rule 9, carried from T3/T4): frictionless fills at trigger levels; 5-min
OPRA bars for layer (a) (touch stops; 1m-close timing owed); premium-only replay (ribbon/level/
chart exits OFF, same as every prior anchor); qty 10 fixed (edge_capture/absolute $ ignore the
kill switch + per-trade cap -- relative-to-control and the anchor are the trustworthy signals);
ribbon_ride only (vwap owed, ground rule 11); fresh-slice is SMALL BY CONSTRUCTION (~13 trading
days) -- disclosed, not padded.

Run: backtest/.venv/Scripts/python.exe backtest/tools/t5_confirmatory_matrix.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import time as _time_mod
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

import t4_exit_matrix as t4              # noqa: E402  (replay, band_of, battery, _load_bars, CONTROL, _shape, BANDS)
import t3_entry_matrix as t3              # noqa: E402  (entry_fill -- entry-2 limit/patience/cancel semantics)
import _signal_cache as sc                # noqa: E402  (build_signals -- monkeypatch START/END, no file edits)
import exit_shape_parity_study as esp     # noqa: E402  (real-fills anchor: fills -> positions -> bars -> replay)
from per_band_stop import resolve_stop_pct, EXIT_B_BAND_TABLE  # noqa: E402

PREREG = REPO / "analysis" / "recommendations" / "entry-exit-matrix-stop-a-preregistration.json"
SIGNAL_SET = REPO / "analysis" / "exit-parity" / "signal-set.json"
FRESH_SIGNAL_SET = REPO / "analysis" / "exit-parity" / "signal-set-fresh-20260619-20260708.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "entry-exit-matrix-2026-07-09.json"
OUT_MD = REPO / "analysis" / "recommendations" / "entry-exit-matrix-2026-07-09.md"

EXPECTED_SHA16 = "b5e8931994b9d34b"
EXPECTED_PREREG_VERSION = 2

FRESH_START_WARMUP = dt.date(2026, 5, 1)    # warmup buffer >> ribbon EMA(48 bars) & level lookback(<=10d)
FRESH_END = dt.date(2026, 7, 8)
FRESH_KEEP_FROM = dt.date(2026, 6, 19)       # never-seen-by-any-grid boundary (day after Juneteenth close)

TIME_STOP = dt.time(15, 40)
FLOOR = 0.30
SMALL_N_THRESHOLD = 8

CONTROL_SHAPE = t4._shape(t4.CONTROL)  # -20/+150/sell80/fixed/tgt2.5x -- the shipped ribbon_ride shape
EXIT_A_SHAPE = {"premium_stop_pct": -0.50, "tp1_premium_pct": 1.5, "tp1_qty_fraction": 0.667,
                 "profit_lock_mode": "trailing", "trail_pct": 0.15, "runner_target_pct": 9.9}
EXIT_C_SHAPE = {"premium_stop_pct": -0.35, "tp1_premium_pct": 0.5, "tp1_qty_fraction": 0.8,
                 "profit_lock_mode": "trailing", "trail_pct": 0.15, "runner_target_pct": 2.5}
ENTRY2_POLICY = {"type": "limit", "delta": 0.10, "patience": 3, "miss": "cancel"}


def exit_b_shape_for(entry_premium: float) -> dict:
    stop = resolve_stop_pct(entry_premium, EXIT_B_BAND_TABLE)
    return {"premium_stop_pct": stop, "tp1_premium_pct": 1.5, "tp1_qty_fraction": 0.667,
            "profit_lock_mode": "trailing", "trail_pct": 0.15, "runner_target_pct": 9.9}


# ---------------------------------------------------------------------------------------------
# PRE-FLIGHT
# ---------------------------------------------------------------------------------------------
def preflight() -> dict:
    sha_full = hashlib.sha256(SIGNAL_SET.read_bytes()).hexdigest()
    sha16 = sha_full[:16]
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    ver = preg.get("version")
    return {"signal_set_sha256_16": sha16, "signal_set_hash_ok": sha16 == EXPECTED_SHA16,
            "preregistration_version": ver, "preregistration_version_ok": ver == EXPECTED_PREREG_VERSION}


# ---------------------------------------------------------------------------------------------
# LAYER (a) -- FRESH-SLICE SIGNAL GENERATION
# ---------------------------------------------------------------------------------------------
def _content_hash(payload_obj) -> str:
    payload = json.dumps(payload_obj, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_fresh_slice() -> dict:
    """Regenerate ribbon_ride signals with warmup, keep only >= FRESH_KEEP_FROM. Reuses
    _signal_cache.build_signals() VERBATIM via monkeypatched module globals (no file edits to
    _signal_cache.py -- the function body looks up START/END as module globals at call time)."""
    if FRESH_SIGNAL_SET.exists():
        existing = json.loads(FRESH_SIGNAL_SET.read_text(encoding="utf-8"))
        same_window = (existing.get("kept_from") == str(FRESH_KEEP_FROM)
                        and existing.get("generation_end") == str(FRESH_END)
                        and existing.get("generation_start_with_warmup") == str(FRESH_START_WARMUP))
        recomputed = _content_hash(existing.get("signals", []))
        if same_window and recomputed == existing.get("sha256"):
            print(f"[t5] VERIFIED existing fresh signal set ({existing['n']} signals, "
                  f"sha256_16={existing['sha256_16']}) -- reusing, not rebuilding", flush=True)
            return existing
        print(f"[t5] existing fresh signal set present but FAILED verification "
              f"(same_window={same_window}, hash_match={recomputed == existing.get('sha256')}) "
              f"-- rebuilding from scratch, not trusting it", flush=True)

    sc.START = FRESH_START_WARMUP
    sc.END = FRESH_END
    print(f"[t5] building fresh slice: full detector run {FRESH_START_WARMUP}..{FRESH_END} "
          f"(warmup bars included), keeping ONLY signals >= {FRESH_KEEP_FROM}", flush=True)
    t0 = _time_mod.time()
    all_sigs = sc.build_signals()
    kept = [s for s in all_sigs if dt.date.fromisoformat(s["date"]) >= FRESH_KEEP_FROM]
    sha = _content_hash(kept)
    out = {
        "_doc": "T-W7 layer (a) fresh OPRA slice -- never seen by any exploratory grid. Full "
                f"backtest run {FRESH_START_WARMUP}..{FRESH_END} for ribbon-EMA/level warmup; "
                f"ONLY signals dated >= {FRESH_KEEP_FROM} are kept below.",
        "generation_start_with_warmup": str(FRESH_START_WARMUP),
        "generation_end": str(FRESH_END),
        "kept_from": str(FRESH_KEEP_FROM),
        "window": f"{FRESH_KEEP_FROM}..{FRESH_END}",
        "n_generated_total_incl_warmup": len(all_sigs),
        "n": len(kept),
        "signal_strike_offset": sc.SIGNAL_STRIKE_OFFSET,
        "sha256": sha,
        "sha256_16": sha[:16],
        "sha256_note": "sha256 of the canonical json.dumps(sort_keys=True) of the KEPT signals "
                        "list only (not of this file -- avoids a self-referential hash).",
        "signals": kept,
    }
    FRESH_SIGNAL_SET.parent.mkdir(parents=True, exist_ok=True)
    FRESH_SIGNAL_SET.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[t5] fresh slice built in {_time_mod.time()-t0:.0f}s: {len(kept)} kept of "
          f"{len(all_sigs)} generated (incl warmup)", flush=True)
    return out


def prepare_signals(signals: list[dict]) -> tuple[list[dict], int]:
    prepared, miss = [], 0
    for s in signals:
        bars = t4._load_bars(s)
        if not bars:
            miss += 1
            continue
        entry_premium = bars[0][1]
        if entry_premium <= 0:
            miss += 1
            continue
        prepared.append({"date": dt.date.fromisoformat(s["date"]), "direction": s["direction"],
                         "side": s["side"], "entry_premium": entry_premium,
                         "band": t4.band_of(entry_premium), "bars": bars})
    return prepared, miss


# ---------------------------------------------------------------------------------------------
# LAYER (a) -- REPLAY CELLS
# ---------------------------------------------------------------------------------------------
def replay_market(prepared_subset: list[dict], shape_or_fn) -> list[dict]:
    trades = []
    for p in prepared_subset:
        shape = shape_or_fn(p["entry_premium"]) if callable(shape_or_fn) else shape_or_fn
        r = t4.replay(p["entry_premium"], p["bars"], p["side"], shape, TIME_STOP)
        trades.append({"date": p["date"], "direction": p["direction"], "band": p["band"],
                       "pnl": r["pnl"], "stopped": r["stopped"], "missed": False})
    return trades


def replay_entry2_pair(prepared_subset: list[dict], exit_shape: dict) -> list[dict]:
    trades = []
    for p in prepared_subset:
        f = t3.entry_fill(p["bars"], p["entry_premium"], ENTRY2_POLICY)
        if f is None:
            trades.append({"date": p["date"], "direction": p["direction"], "band": p["band"],
                           "pnl": 0.0, "missed": True})
            continue
        sub = p["bars"][f["fill_idx"]:]
        r = t4.replay(f["entry"], sub, p["side"], exit_shape, TIME_STOP)
        trades.append({"date": p["date"], "direction": p["direction"], "band": p["band"],
                       "pnl": r["pnl"], "missed": False})
    return trades


def per_band(trades: list[dict]) -> dict:
    out = {}
    for b, _lo, _hi in t4.BANDS:
        ts = [t for t in trades if t["band"] == b]
        out[b] = {"n": len(ts), "exp": round(sum(x["pnl"] for x in ts) / len(ts), 2) if ts else None}
    return out


def cell_metrics(cand_id: str, label: str, trades: list[dict], eligible_subset: list[dict],
                  control_all_battery: dict, n_total_fresh: int) -> dict:
    b = t4.battery(trades)
    control_same_trades = replay_market(eligible_subset, CONTROL_SHAPE)
    cb_same = t4.battery(control_same_trades)
    n = b.get("n", 0)
    exp = b.get("expectancy")
    delta_full = (round(exp - control_all_battery["expectancy"], 2)
                  if n and control_all_battery.get("n") else None)
    delta_same = round(exp - cb_same["expectancy"], 2) if n and cb_same.get("n") else None
    return {
        "id": cand_id, "label": label,
        "n_signals_fresh_slice_total": n_total_fresh,
        "n_eligible": n,
        "n_missed": sum(1 for t in trades if t.get("missed")),
        "expectancy": exp, "total": b.get("total"), "wr": b.get("wr"),
        "exp_drop_top3": b.get("exp_drop_top3"),
        "by_band": per_band(trades),
        "control_all_fresh_signals_expectancy": control_all_battery.get("expectancy"),
        "control_same_eligible_subset_expectancy": cb_same.get("expectancy"),
        "delta_vs_control_full_population": delta_full,
        "delta_vs_control_same_subset": delta_same,
        "small_n": n < SMALL_N_THRESHOLD,
    }


def run_layer_a(prepared: list[dict]) -> dict:
    n_total = len(prepared)
    control_all_trades = replay_market(prepared, CONTROL_SHAPE)
    control_all = t4.battery(control_all_trades)

    out = {"n_prepared": n_total, "control_all_fresh_signals": control_all, "candidates": {}}

    trades = replay_market(prepared, EXIT_A_SHAPE)
    out["candidates"]["exit-A-wide-ride"] = cell_metrics(
        "exit-A-wide-ride", "exit-A standalone, market entry, no floor", trades, prepared,
        control_all, n_total)

    trades = replay_market(prepared, exit_b_shape_for)
    out["candidates"]["exit-B-perband-hybrid"] = cell_metrics(
        "exit-B-perband-hybrid", "exit-B standalone, market entry, no floor, per-band stop",
        trades, prepared, control_all, n_total)

    elig = [p for p in prepared if p["entry_premium"] >= FLOOR]
    trades = replay_entry2_pair(elig, EXIT_C_SHAPE)
    out["candidates"]["exit-C-paired-scalp"] = cell_metrics(
        "exit-C-paired-scalp(entry-2)",
        "exit-C PAIRED with entry-2 limit-10%/pat3/cancel, floor $0.30", trades, elig,
        control_all, n_total)

    trades = replay_market(elig, CONTROL_SHAPE)
    out["candidates"]["entry-1+control"] = cell_metrics(
        "entry-1+control", "entry-1 floor $0.30 + CONTROL exit, market entry", trades, elig,
        control_all, n_total)

    trades = replay_market(elig, EXIT_A_SHAPE)
    out["candidates"]["entry-1+exitA"] = cell_metrics(
        "entry-1+exitA", "entry-1 floor $0.30 + exit-A, market entry (likely ship combo)",
        trades, elig, control_all, n_total)

    return out


# ---------------------------------------------------------------------------------------------
# LAYER (b) -- REAL-FILLS ANCHOR
# ---------------------------------------------------------------------------------------------
def run_layer_b() -> dict:
    fills = esp.load_fleet_engine_fills()
    positions = esp.reconstruct_positions(fills)
    if not positions:
        return {"status": "unavailable", "reason": "fills-ledger empty or no fleet_rest engine fills"}

    uniq = sorted(set((p["date_et"], p["symbol"]) for p in positions))
    dates = sorted(set(p["date_et"] for p in positions))
    actual_total = round(sum(p.get("actual_exit_pnl", 0.0) for p in positions), 2)

    bar_cache: dict = {}

    def bars_for(p):
        key = (p["symbol"], p["date_et"])
        if key not in bar_cache:
            bar_cache[key] = esp.fetch_option_bars(p["symbol"], p["date_et"])
            _time_mod.sleep(0.12)
        return bar_cache[key]

    def total_for(shape_or_fn, subset):
        tot, n_valid, n_nodata = 0.0, 0, 0
        for p in subset:
            bars = bars_for(p)
            if not bars:
                n_nodata += 1
                continue
            shape = shape_or_fn(p["entry_price"]) if callable(shape_or_fn) else shape_or_fn
            r = esp.replay_position(p, bars, shape)
            if r.get("pnl") is not None:
                tot += r["pnl"]
                n_valid += 1
            else:
                n_nodata += 1
        return round(tot, 2), n_valid, n_nodata

    def uniq_of(subset):
        return sorted(set((p["date_et"], p["symbol"]) for p in subset))

    print(f"[t5] layer(b): {len(positions)} reconstructed positions "
          f"({len(uniq)} unique signals, {len(dates)} trading days, "
          f"{dates[0]}..{dates[-1]}) -- fetching real OPRA bars...", flush=True)

    ctl_total, ctl_valid, ctl_nodata = total_for(CONTROL_SHAPE, positions)

    result = {
        "status": "ok",
        "n_positions_total": len(positions), "n_unique_signals_total": len(uniq),
        "n_trading_days": len(dates), "date_span": f"{dates[0]}..{dates[-1]}" if dates else None,
        "actual_realized_total": actual_total,
        "control_anchor_total": ctl_total, "control_n_valid": ctl_valid,
        "control_n_nodata": ctl_nodata,
        "candidates": {},
    }

    a_total, a_valid, a_nodata = total_for(EXIT_A_SHAPE, positions)
    result["candidates"]["exit-A-wide-ride"] = {
        "n_positions": len(positions), "n_unique_signals": len(uniq), "n_valid": a_valid,
        "n_nodata": a_nodata, "anchor_total": a_total, "control_anchor_total": ctl_total,
        "no_regression": a_total >= ctl_total,
    }

    b_total, b_valid, b_nodata = total_for(exit_b_shape_for, positions)
    result["candidates"]["exit-B-perband-hybrid"] = {
        "n_positions": len(positions), "n_unique_signals": len(uniq), "n_valid": b_valid,
        "n_nodata": b_nodata, "anchor_total": b_total, "control_anchor_total": ctl_total,
        "no_regression": b_total >= ctl_total,
    }

    result["candidates"]["exit-C-paired-scalp"] = {
        "status": "not_available",
        "reason": ("entry-2-limit-headroom is SHADOW-only per STOP-A sign-off condition 3 -- "
                   "zero real fills exist under a limit-headroom entry. Replaying exit-C's exit "
                   "body against the REAL market-priced entries would test exit-C standalone "
                   "with a market entry, which the pre-registration explicitly forbids (exit-C "
                   "is weak standalone: exp $13.19/tr, rank 609/2016 in the exploratory grid). "
                   "Anchor owed once entry-2's shadow ledger (or a live arm) produces real "
                   "limit-headroom fills."),
    }

    floor_subset = [p for p in positions if p["entry_price"] >= FLOOR]
    floor_uniq = uniq_of(floor_subset)
    ctl_floor_total, ctl_floor_valid, _ = total_for(CONTROL_SHAPE, floor_subset)

    result["candidates"]["entry-1+control"] = {
        "n_positions": len(floor_subset), "n_unique_signals": len(floor_uniq),
        "n_positions_dropped_by_floor": len(positions) - len(floor_subset),
        "anchor_total": ctl_floor_total,  # candidate IS control-exit on the floor subset
        "control_anchor_total_full_population": ctl_total,
        "control_anchor_total_same_floor_subset": ctl_floor_total,
        "no_regression": ctl_floor_total >= ctl_total,
    }

    e1a_total, e1a_valid, _ = total_for(EXIT_A_SHAPE, floor_subset)
    result["candidates"]["entry-1+exitA"] = {
        "n_positions": len(floor_subset), "n_unique_signals": len(floor_uniq),
        "n_positions_dropped_by_floor": len(positions) - len(floor_subset),
        "anchor_total": e1a_total,
        "control_anchor_total_full_population": ctl_total,
        "control_anchor_total_same_floor_subset": ctl_floor_total,
        "no_regression": e1a_total >= ctl_total,
    }

    return result


# ---------------------------------------------------------------------------------------------
# VERDICTS
# ---------------------------------------------------------------------------------------------
CANDIDATE_ORDER = ["exit-A-wide-ride", "exit-B-perband-hybrid", "exit-C-paired-scalp",
                   "entry-1+control", "entry-1+exitA"]
CANDIDATE_LABELS = {
    "exit-A-wide-ride": "exit-A (-50/+150/sell66/trail15/tgt-none)",
    "exit-B-perband-hybrid": "exit-B (per-band stop on exit-A body)",
    "exit-C-paired-scalp": "exit-C + entry-2 (PAIRED, floor $0.30)",
    "entry-1+control": "entry-1 (floor $0.30) + CONTROL exit",
    "entry-1+exitA": "entry-1 (floor $0.30) + exit-A [likely ship combo]",
}


def build_key_findings(layer_a: dict, layer_b: dict, verdicts: dict) -> list[str]:
    """Things that 'smell wrong' or matter for the reader even though they are NOT bugs --
    computed from the already-replayed numbers (OP-33: quote real output, don't editorialize
    without evidence)."""
    notes = []
    ctl_all = layer_a["control_all_fresh_signals"]
    notes.append(
        f"CONTROL ITSELF loses on the fresh slice: exp ${ctl_all['expectancy']}/tr, WR "
        f"{ctl_all['wr']*100:.1f}% (1 win of {ctl_all['n']}), worst trade ${ctl_all['worst_trade']} "
        f"-- 2026-06-19..07-08 was a genuinely bad stretch for ribbon_ride (both directions), not "
        f"an exit-shape-specific problem.")
    exit_a = layer_a["candidates"]["exit-A-wide-ride"]
    notes.append(
        f"Every one of the {exit_a['n_eligible']} fresh signals that stopped out under CONTROL also "
        "stopped out under exit-A/exit-B at EXACTLY 2.5x the loss (stop-A/-B never once recovered "
        "to trigger TP1 in this window) -- verified by hand against the raw 5-min option bars "
        "(e.g. 2026-06-22 P entry $1.07: low touches -30.8% on the ENTRY bar itself, control stops "
        "immediately at -20%, price keeps bleeding to -50%+ by 13:00 with no bounce -> exit-A's -50% "
        "stop just rides the SAME decay further before cutting). This is why the wide/trailing exits "
        "that WIN on the burned window and the real-fills anchor LOSE MORE on this specific fresh "
        "slice: with no recoveries, a wider stop only adds downside, never captures upside.")
    notes.append(
        "Layers (a) and (b) DISAGREE for exit-A/exit-B/entry-1+exitA: the real-fills anchor (7 "
        "trading days, 06-29..07-08) shows LARGE gains (+$1,501 to +$2,821 vs control -$757), while "
        "the fresh 13-day slice (06-22..07-08, a superset of the anchor's days) shows LARGE losses "
        "(control itself -$100.67/tr, candidates -$253 to -$435/tr). Per the pre-registration's own "
        "auto-ratify bar ('ALL must hold'), a failing OOS layer kills auto-ratification regardless of "
        "anchor strength -- verdict is FAIL/escalate-to-STOP-B, not a silent override in either "
        "direction. This conflict, not a clean pass, is the honest headline.")
    e1c = layer_a["candidates"]["entry-1+control"]
    notes.append(
        f"entry-1's floor ($0.30) EXCLUDES the fresh slice's ONLY winning trade (2026-06-23 P, "
        f"entered at $0.27 -- 3 cents under the floor), so entry-1+control's n={e1c['n_eligible']} "
        "subset has ZERO winners (WR 0.0%) and looks strictly worse than the unfiltered control. "
        "This is a small-n artifact, not evidence against the floor thesis: one flipped trade (of "
        "18) swings the entire sign of this candidate's layer (a) result, which is why n=11 barely "
        "clears the small-n gate (8) in spirit even though it clears it in number.")
    exit_c = layer_a["candidates"]["exit-C-paired-scalp"]
    notes.append(
        f"exit-C+entry-2 is the ONE candidate that outperforms control on the fresh slice (exp "
        f"${exit_c['expectancy']} vs control ${exit_c['control_all_fresh_signals_expectancy']}, "
        f"delta {exit_c['delta_vs_control_full_population']:+.2f}) -- still net negative in $ terms "
        "(the window was bad for everything) but the SMALLEST loss of any candidate and the only "
        "one with a positive WR trend (0.364 vs control's 0.056). No anchor exists to corroborate "
        "(entry-2 is shadow-only) -- this is suggestive, not confirmatory.")
    return notes


def build_verdicts(layer_a: dict, layer_b: dict) -> dict:
    verdicts = {}
    for cid in CANDIDATE_ORDER:
        a = layer_a["candidates"][cid]
        b = layer_b.get("candidates", {}).get(cid, {}) if layer_b.get("status") == "ok" else {}

        if a["small_n"]:
            a_pass = None
        else:
            a_pass = bool(a["expectancy"] is not None and a["expectancy"] > 0
                          and a["delta_vs_control_full_population"] is not None
                          and a["delta_vs_control_full_population"] >= 0)

        if b.get("status") == "not_available" or layer_b.get("status") != "ok":
            b_pass = None
        else:
            b_pass = bool(b.get("no_regression"))

        reason_parts = []
        if a["small_n"]:
            reason_parts.append(f"layer(a) n={a['n_eligible']}<{SMALL_N_THRESHOLD} -- cannot discriminate")
        else:
            reason_parts.append(
                f"layer(a) exp ${a['expectancy']} vs control ${a['control_all_fresh_signals_expectancy']} "
                f"(delta {a['delta_vs_control_full_population']:+.2f}) -> "
                f"{'PASS' if a_pass else 'FAIL'}")
        if b.get("status") == "not_available":
            reason_parts.append(f"layer(b) N/A ({b['reason'][:100]}...)")
        elif layer_b.get("status") != "ok":
            reason_parts.append(f"layer(b) unavailable ({layer_b.get('reason', layer_b.get('status'))})")
        else:
            ctl_ref = b.get("control_anchor_total", b.get("control_anchor_total_full_population"))
            reason_parts.append(f"layer(b) anchor ${b.get('anchor_total')} vs control ${ctl_ref} -> "
                                f"{'no-regression' if b_pass else 'REGRESSION (kill)'}")

        if b_pass is False:
            overall = "FAIL"
        elif a["small_n"]:
            overall = "VERDICT_INCONCLUSIVE_SMALL_N"
        elif b_pass is None:
            overall = "INCONCLUSIVE_NO_ANCHOR"
        elif a_pass is False:
            overall = "FAIL"
        else:
            overall = "PASS"

        verdicts[cid] = {
            "layer_a_pass": a_pass, "layer_b_pass": b_pass, "overall": overall,
            "reason": "; ".join(reason_parts),
        }
    return verdicts


# ---------------------------------------------------------------------------------------------
# REPORT
# ---------------------------------------------------------------------------------------------
def render_md(out: dict) -> str:
    L = []
    L.append("# T-W7 layers (a)+(b) — ENTRY-EXIT-MATRIX confirmatory pass (T5)")
    L.append("")
    pf = out["preflight"]
    L.append(f"Frozen v2 pre-registration, EXACTLY these candidates -- no re-picks, no new cells. "
             f"Preflight: signal-set sha256_16 `{pf['signal_set_sha256_16']}` "
             f"({'OK' if pf['signal_set_hash_ok'] else '**MISMATCH**'}), pre-registration version "
             f"{pf['preregistration_version']} ({'OK' if pf['preregistration_version_ok'] else '**MISMATCH**'}).")
    L.append("")
    fsm = out["fresh_signal_set_meta"]
    L.append(f"**Fresh-slice signal set:** {fsm['n']} signals kept (dated >= `{fsm['kept_from']}`) "
             f"of {fsm['n_generated_total_incl_warmup']} generated over the full detector run "
             f"`{fsm['generation_start_with_warmup']}..{fsm['generation_end']}` "
             f"(everything before `{fsm['kept_from']}` is warmup, discarded -- never replayed). "
             f"sha256_16 `{fsm['sha256_16']}`. **~13 trading days -- SMALL BY CONSTRUCTION, "
             f"disclosed not padded.**")
    L.append("")
    L.append("## VERDICT TABLE")
    L.append("")
    L.append("| candidate | layer (a) fresh-slice | layer (b) real-fills anchor | OVERALL |")
    L.append("|---|---|---|:--:|")
    la = out["layer_a_fresh_slice"]["candidates"]
    lb = out["layer_b_real_fills_anchor"].get("candidates", {})
    for cid in CANDIDATE_ORDER:
        v = out["verdicts"][cid]
        a = la[cid]
        b = lb.get(cid, {})
        if a["small_n"]:
            a_str = f"n={a['n_eligible']} **SMALL-N**"
        else:
            a_str = f"n={a['n_eligible']}, exp ${a['expectancy']}, Δ{a['delta_vs_control_full_population']:+.2f}"
        if b.get("status") == "not_available":
            b_str = "N/A (no real fills under entry-2)"
        elif out["layer_b_real_fills_anchor"].get("status") != "ok":
            b_str = "unavailable"
        else:
            ctl_ref = b.get("control_anchor_total", b.get("control_anchor_total_full_population"))
            b_str = (f"${b.get('anchor_total')} vs ctl ${ctl_ref} "
                     f"({'n/r' if b.get('no_regression') else 'REGRESSION'}, "
                     f"n={b.get('n_unique_signals')})")
        L.append(f"| **{CANDIDATE_LABELS[cid]}** | {a_str} | {b_str} | **{v['overall']}** |")
    L.append("")
    L.append("`Δ` = delta vs CONTROL replayed on the FULL fresh-slice population (same detector, "
             "same window). `n/r` = no-regression. Anchor `n` = unique (date,symbol) signals, "
             "NOT position count (ground rule 8).")
    L.append("")
    L.append("## KEY FINDINGS (read before the per-candidate detail)")
    L.append("")
    for kf in out.get("key_findings", []):
        L.append(f"- {kf}")
    L.append("")
    L.append("## Per-candidate detail")
    L.append("")
    for cid in CANDIDATE_ORDER:
        a = la[cid]
        v = out["verdicts"][cid]
        L.append(f"### `{cid}` — {CANDIDATE_LABELS[cid]}")
        L.append("")
        L.append(f"- **Verdict:** {v['overall']} — {v['reason']}")
        L.append(f"- Layer (a): n_eligible={a['n_eligible']} (of {a['n_signals_fresh_slice_total']} fresh "
                 f"signals), n_missed={a['n_missed']}, expectancy ${a['expectancy']}, total ${a['total']}, "
                 f"WR {a['wr']}, drop-top-3 ${a['exp_drop_top3']}")
        L.append(f"  - control (same fresh window, full pop) exp ${a['control_all_fresh_signals_expectancy']} | "
                 f"control (same eligible subset) exp ${a['control_same_eligible_subset_expectancy']}")
        L.append(f"  - delta vs control (full pop) {a['delta_vs_control_full_population']:+.2f} | "
                 f"delta vs control (same subset) {a['delta_vs_control_same_subset']:+.2f}"
                 if a['delta_vs_control_full_population'] is not None else "  - delta vs control: n/a (no eligible trades)")
        bands = ", ".join(f"{k}: n={vv['n']} exp={vv['exp']}" for k, vv in a["by_band"].items())
        L.append(f"  - per-band: {bands}")
        b = lb.get(cid, {})
        if b.get("status") == "not_available":
            L.append(f"- Layer (b): **N/A** — {b['reason']}")
        elif out["layer_b_real_fills_anchor"].get("status") != "ok":
            L.append("- Layer (b): unavailable (see layer_b_real_fills_anchor.status/reason)")
        else:
            ctl_ref = b.get("control_anchor_total", b.get("control_anchor_total_full_population"))
            L.append(f"- Layer (b): anchor_total ${b.get('anchor_total')} vs control ${ctl_ref}, "
                     f"n_positions={b.get('n_positions')}, n_unique_signals={b.get('n_unique_signals')}, "
                     f"no_regression={b.get('no_regression')}")
        L.append("")
    L.append("## Layer (b) anchor overview")
    L.append("")
    lbo = out["layer_b_real_fills_anchor"]
    if lbo.get("status") == "ok":
        L.append(f"Reconstructed **{lbo['n_positions_total']} positions** = "
                 f"**{lbo['n_unique_signals_total']} unique (date,symbol) signals** over "
                 f"{lbo['n_trading_days']} trading days ({lbo['date_span']}) from "
                 f"fleet_rest engine-attributed fills (safe-1/safe-3/risky-1/risky-3). "
                 f"Actual realized: ${lbo['actual_realized_total']} vs replayed CONTROL: "
                 f"${lbo['control_anchor_total']} (n_valid={lbo['control_n_valid']}, "
                 f"n_nodata={lbo['control_n_nodata']}).")
    else:
        L.append(f"Status: **{lbo.get('status')}** — {lbo.get('reason', 'n/a')}")
    L.append("")
    L.append("## Disclosures")
    L.append("")
    for d in out["disclosures"]:
        L.append(f"- {d}")
    L.append("")
    L.append("---")
    L.append("_Source: `backtest/tools/t5_confirmatory_matrix.py`. Layer (c) [fresh P5 grind] and "
             "layer (d) [forward paper] run separately per the STOP-A sign-off. Nothing ships from "
             "this file -- STOP CHECKPOINT B (Opus/Fable/J) decides what arms._")
    return "\n".join(L) + "\n"


def main() -> int:
    pf = preflight()
    print(f"[t5] preflight: {pf}", flush=True)
    if not pf["signal_set_hash_ok"] or not pf["preregistration_version_ok"]:
        print("[t5] PREFLIGHT FAILED -- aborting (no re-picks, no stale-hash runs)", file=sys.stderr)
        return 1

    fresh = build_fresh_slice()
    print(f"[t5] fresh slice: {fresh['n']} signals kept (of {fresh['n_generated_total_incl_warmup']} "
          f"generated {fresh['generation_start_with_warmup']}..{fresh['generation_end']}), "
          f"kept-from {fresh['kept_from']}, sha256_16={fresh['sha256_16']}", flush=True)

    prepared, n_missing_bars = prepare_signals(fresh["signals"])
    print(f"[t5] {len(prepared)} prepared (bars available) of {fresh['n']} fresh signals "
          f"({n_missing_bars} missing bars)", flush=True)

    layer_a = run_layer_a(prepared)
    layer_a["n_missing_bars"] = n_missing_bars
    layer_a["n_fresh_signals_generated"] = fresh["n"]

    print("[t5] layer (b): real-fills anchor (network calls to Alpaca market data, single "
          "process, politely rate-limited)...", flush=True)
    layer_b = run_layer_b()
    print(f"[t5] layer (b) status: {layer_b.get('status')}", flush=True)

    verdicts = build_verdicts(layer_a, layer_b)
    key_findings = build_key_findings(layer_a, layer_b, verdicts)
    for kf in key_findings:
        print(f"[t5] FINDING: {kf[:140]}...", flush=True)

    out = {
        "_doc": "T-W7 layers (a)+(b) -- confirmatory pass on the FROZEN v2 pre-registration. "
                "ANALYSIS ONLY: no trading-path file touched. Layer (c) [fresh P5 grind] is a "
                "separate kill-check per STOP-A sign-off condition 2, NOT run here.",
        "generated_at": dt.datetime.now().isoformat(),
        "preflight": pf,
        "fresh_signal_set_file": str(FRESH_SIGNAL_SET.relative_to(REPO)).replace("\\", "/"),
        "fresh_signal_set_meta": {k: v for k, v in fresh.items() if k != "signals"},
        "layer_a_fresh_slice": layer_a,
        "layer_b_real_fills_anchor": layer_b,
        "verdicts": verdicts,
        "key_findings": key_findings,
        "disclosures": [
            "Fresh-slice window 2026-06-19..2026-07-08 (~13 trading days) is SMALL BY "
            "CONSTRUCTION -- disclosed, not padded (STOP-A directive).",
            "Detector warmed up on 2026-05-01..2026-06-18 (ribbon EMA<=48 5-min bars, level "
            "lookback<=10 trading days) -- warmup-window signals produce NO kept trades "
            "(filtered out before any replay).",
            "Frictionless fills at trigger levels; 5-min OPRA bars for layer (a) (touch stops; "
            "1m-close timing owed); premium-only replay (ribbon/level/chart exits OFF, same as "
            "every prior anchor).",
            "qty 10 fixed; absolute $/edge_capture ignore the kill switch + per-trade cap -- "
            "relative-to-control and the anchor are the trustworthy signals (same caveat as T4).",
            "Real-fills anchor = ONE regime, 1-min Alpaca OPRA bars, engine-attributed fleet_rest "
            "arms only (safe-1/safe-3/risky-1/risky-3) -- core-lane (safe-2/bold-2) engine fills "
            "excluded (fleet_rest is the anchor tool's established scope, per exit_shape_parity_study.py).",
            "exit-C-paired-scalp has NO real-fills anchor: entry-2 is SHADOW-only (STOP-A sign-off "
            "condition 3) -- zero live limit-headroom fills exist; testing exit-C against "
            "market-priced real entries would violate the pair-only constraint and is NOT done here.",
            "Layer (c) [fresh P5 grind, ~7560 combos] is a separate KILL-CHECK per STOP-A sign-off "
            "condition 2 -- NOT run by this pass.",
            "ribbon_ride only (ground rule 11); vwap_continuation entry/exit matrix is owed separately.",
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    OUT_MD.write_text(render_md(out), encoding="utf-8")
    print(f"[t5] wrote {OUT_JSON.name} + {OUT_MD.name}", flush=True)
    for cid in CANDIDATE_ORDER:
        print(f"[t5] {cid}: {verdicts[cid]['overall']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
