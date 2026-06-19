"""EXIT-REDESIGN sweep for the highest-edge WATCH_ONLY watcher patterns.

THE QUESTION (highest-value research item — the watcher-fleet "unlock"):
  Three level-keyed watchers have STRONG SPY-price edge but NEGATIVE real-fills
  expectancy under the current exit config (the R:R/theta-mismatch class, themes
  C1/C3). They already use chart-stop-only (premium_stop disabled). So the fix is
  NOT "add chart stops" — it is whether SWEEPING THE EXIT KNOBS finds a config
  that flips real-fills POSITIVE while staying anchor-clean.

PATTERNS UNDER TEST (the strong-SPY-edge subset of the level family):
  1. FLOOR_HOLD_BOUNCE          (floor_hold_bounce_watcher)        disk-read
  2. CLOSE_CEILING_FADE         (close_ceiling_fade_watcher)       disk-read
  3. NAMED_LEVEL_SECOND_TEST    (named_level_second_test_watcher)  disk-read

EXIT KNOBS SWEPT (high-leverage only — lean grid, not a 1000-combo blowout):
  - strike_offset:            ATM(0) / ITM-1(-1) / ITM-2(-2)   (theta/gamma on loser leg)
  - tp1_premium_pct:          +0.30 / +0.50 / +0.70 / +1.00    (premium take-profit)
  - level_stop_buffer_dollars: 0.30 / 0.50 / 0.80              (chart-stop distance below/above level)

  tp1_qty_fraction + runner kept at production (0.50 / 2.5) — they don't change
  the win/loss SIGN of the loser leg, which is the binding constraint here.

REAL-FILLS IS THE ONLY AUTHORITY (theme C1 — BS-sim is ranking-only). Every
number below is OPRA (lib.simulator_real + the options cache, valid through
2026-05-29). chart-stop only (premium_stop_pct=-0.99) for ALL configs — this
sweep is about chart-exit geometry, not premium stops.

THE GATE (honest — do NOT loosen to manufacture a win):
  PROMOTE-CANDIDATE  iff  real-fills exp > 0
                     AND  anchor-no-regression (per-pattern real-fills edge_capture
                          on J-anchor days not worse than the production-config baseline)
                     AND  DSR/PBO advisory (lib.validation.gate) != FAIL.
  If NO config clears for a pattern → that pattern is confirmed DEAD-UNDER-ALL-
  TESTED-EXITS. A clean no-win is a valid, reportable result (the watchers are
  WATCH_ONLY by doctrine; this is research, not a promotion).

LEVEL-SOURCE CAVEAT (inherited from validate_level_family — read before trusting):
  All 3 watchers read key-levels.json from DISK and ignore ctx.levels_active. In a
  naive backtest that is look-ahead. This script reuses validate_level_family's
  monkeypatch that forces each disk-reader's per-day cache to SYNTHETIC PDH/PDL/
  PDC/PDO proxies (★★/★), so the backtest is VALID — but the proxies are NOT the
  production ★★★ named levels (no historical archive). Numbers are a proxy
  LOWER-BOUND. The EXIT-knob comparison is internally consistent regardless
  (same level set across all configs), so "does any exit config flip the sign?"
  is answerable even though the absolute WR is a proxy.

Usage:
  python -m autoresearch.sweep_watcher_exits \
      --start 2025-01-01 --end 2026-05-29 \
      --out analysis/recommendations/watcher-exit-sweep.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

# Reuse the proven level-family machinery verbatim (no duplication, no drift).
from autoresearch.validate_level_family import (  # noqa: E402
    ANCHORS,
    _REJ_LEVEL_KEY,
    _load_data,
    _patch_disk_readers_for_day,
    _reset_watcher_state,
    _stats,
    _synthetic_levels_for_day,
)

from lib.filters import vol_baseline_20bar, range_baseline_20bar, BarContext  # noqa: E402
from lib.ribbon import compute_ribbon, RibbonState  # noqa: E402
from lib.orchestrator import (  # noqa: E402
    _align_vix_to_spy,
    _precompute_htf_15m_stacks,
    _update_level_states,
)
from lib.simulator_real import simulate_trade_real  # noqa: E402
from lib.validation.gate import evaluate_candidate  # noqa: E402

# The 3 strong-SPY-edge detectors under exit-sweep.
from lib.watchers.floor_hold_bounce_watcher import detect_floor_hold_bounce_setup  # noqa: E402
from lib.watchers.named_level_second_test_watcher import detect_named_level_second_test_setup  # noqa: E402
from lib.watchers.close_ceiling_fade_watcher import detect_close_ceiling_fade_setup  # noqa: E402

DETECTORS = [
    ("FLOOR_HOLD_BOUNCE", detect_floor_hold_bounce_setup),
    ("CLOSE_CEILING_FADE", detect_close_ceiling_fade_setup),
    ("NAMED_LEVEL_SECOND_TEST", detect_named_level_second_test_setup),
]

# ── Exit-knob grid (high-leverage, lean) ─────────────────────────────────────
STRIKE_OFFSETS = [0, -1, -2]               # ATM / ITM-1 / ITM-2
TP1_PCTS = [0.30, 0.50, 0.70, 1.00]        # premium take-profit fallback
STOP_BUFFERS = [0.30, 0.50, 0.80]          # chart-stop distance past the level

# The PRODUCTION-config baseline for each pattern's real-fills anchor comparison.
# This is the config the prior level-family validation used (chart-stop only,
# tp1 default 0.30, prod stop buffer 0.50). ITM-2 + ATM were both reported; we
# anchor against ATM @ tp1=0.30 @ buf=0.50 as the canonical "current" exit.
BASELINE = {"strike_offset": 0, "tp1_premium_pct": 0.30, "level_stop_buffer_dollars": 0.50}

# Per-stream signal cap (runtime control). Anchor-day signals are ALWAYS included
# on top of the cap (see _select_signals) so the anchor-no-regression gate is never
# vacuous — the level-family 120-cap silently truncated NAMED_LEVEL_SECOND_TEST
# (1828 signals) before its May-2026 anchor days, making that gate uninformative.
# This is the small-n mirage guard for the anchor leg (lesson C24).
MAX_SIGNALS_PER_STREAM = 400

# n_trials for the DSR deflation = size of the searched exit grid.
N_TRIALS = len(STRIKE_OFFSETS) * len(TP1_PCTS) * len(STOP_BUFFERS)


def _collect_signals(start: dt.date, end: dt.date) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """Single pass over the window: fire the 3 detectors, collect (idx, bar, sig)
    inputs per stream. Mirrors validate_level_family.run's firing loop exactly so
    the signal population is identical — only the EXIT simulation differs."""
    spy_full, vix_full = _load_data(start, end)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    spy_full["date"] = spy_full["timestamp_et"].dt.date
    rth = spy_full[
        (spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)
    ribbon_df = compute_ribbon(rth["close"])
    vix_aligned = _align_vix_to_spy(rth, vix_full)
    htf_stacks = _precompute_htf_15m_stacks(rth)

    inputs: dict[str, list] = {k: [] for k, _ in DETECTORS}

    _reset_watcher_state()
    level_states: dict = {}
    ribbon_history: list = []
    last_date = None
    _day_levels_cache: dict[dt.date, tuple[list[float], list[float], list[float]]] = {}

    for idx in range(len(rth)):
        bar = rth.iloc[idx]
        bar_time = bar["timestamp_et"]
        bar_date = bar_time.date()
        if start and bar_date < start:
            continue
        if end and bar_date > end:
            continue
        if last_date is not None and bar_date != last_date:
            ribbon_history = []
            level_states = {}
        last_date = bar_date
        if idx < 60:
            continue

        try:
            r = ribbon_df.iloc[idx]
            ribbon_state = RibbonState(
                fast=float(r["fast"]), pivot=float(r["pivot"]), slow=float(r["slow"]),
                stack=str(r["stack"]), spread_cents=float(r["spread_cents"]),
            )
        except Exception:
            continue
        ribbon_history.append(ribbon_state)
        ribbon_history = ribbon_history[-10:]

        vol_baseline = vol_baseline_20bar(rth, idx)
        range_baseline = range_baseline_20bar(rth, idx)
        vix_now = float(vix_aligned.iloc[idx]) if idx < len(vix_aligned) else 17.0
        vix_prior = float(vix_aligned.iloc[max(0, idx - 3)]) if max(0, idx - 3) < len(vix_aligned) else vix_now

        if bar_date not in _day_levels_cache:
            _day_levels_cache[bar_date] = _synthetic_levels_for_day(spy_full, bar_date)
        all_levels, supports, resistances = _day_levels_cache[bar_date]
        today_str = bar_date.isoformat()
        _patch_disk_readers_for_day(supports, resistances, today_str)

        htf = htf_stacks[idx] if idx < len(htf_stacks) else None
        ctx = BarContext(
            bar_idx=idx,
            timestamp_et=bar_time.to_pydatetime(),
            bar=bar,
            prior_bars=rth.iloc[: idx + 1],
            ribbon_now=ribbon_state,
            ribbon_history=ribbon_history,
            vix_now=vix_now,
            vix_prior=vix_prior,
            vol_baseline_20=vol_baseline,
            range_baseline_20=range_baseline,
            levels_active=all_levels,
            multi_day_levels=all_levels,
            htf_15m_stack=htf,
            level_states=level_states,
        )
        _update_level_states(level_states, all_levels, bar, idx)

        for stream, fn in DETECTORS:
            try:
                sig = fn(ctx)
            except Exception as exc:  # surface, never swallow (C7)
                sys.stderr.write(f"{stream} exc @ {bar_time}: {type(exc).__name__}: {exc}\n")
                continue
            if sig is None:
                continue
            inputs[stream].append((idx, bar, sig, bar_date))

    return inputs, rth, ribbon_df


def _select_signals(inputs: list) -> list:
    """Cap the signal population for runtime, but ALWAYS keep every anchor-day
    signal so the anchor-no-regression gate is informative (never vacuous)."""
    anchor_sigs = [t for t in inputs if t[3] in ANCHORS]
    nonanchor = [t for t in inputs if t[3] not in ANCHORS]
    capped_nonanchor = nonanchor[:MAX_SIGNALS_PER_STREAM]
    # Preserve original chronological order for the combined set.
    keep_ids = {id(t) for t in (anchor_sigs + capped_nonanchor)}
    return [t for t in inputs if id(t) in keep_ids]


def _simulate_config(
    stream: str,
    inputs: list,
    rth: pd.DataFrame,
    ribbon_df: pd.DataFrame,
    strike_offset: int,
    tp1_premium_pct: float,
    level_stop_buffer_dollars: float,
) -> dict:
    """Run real-fills for one stream under one exit config. Returns stats + the
    per-trade pnl list + per-anchor-day pnl (for the edge_capture anchor gate)."""
    rej_key = _REJ_LEVEL_KEY[stream]
    pnls: list[float] = []
    anchor_pnl: dict[dt.date, float] = defaultdict(float)
    filled = 0
    attempted = 0
    anchor_attempted = 0
    anchor_filled = 0
    for (idx, bar, sig, bar_date) in _select_signals(inputs):
        attempted += 1
        is_anchor = bar_date in ANCHORS
        if is_anchor:
            anchor_attempted += 1
        side = "C" if sig.direction == "long" else "P"
        rej = sig.metadata.get(rej_key)
        if rej is None:
            rej = sig.stop_price
        try:
            fill = simulate_trade_real(
                entry_bar_idx=idx, entry_bar=bar, spy_df=rth, ribbon_df=ribbon_df,
                rejection_level=float(rej), triggers_fired=list(sig.triggers_fired),
                side=side, qty=3, setup=sig.setup_name,
                premium_stop_pct=-0.99,            # chart-stop only (C1/C2 — premium stop disabled)
                strike_offset=strike_offset,
                tp1_premium_pct=tp1_premium_pct,
                level_stop_buffer_dollars=level_stop_buffer_dollars,
            )
        except Exception as exc:
            sys.stderr.write(f"realfills {stream} exc @ {bar['timestamp_et']}: "
                             f"{type(exc).__name__}: {exc}\n")
            fill = None
        if fill is not None and getattr(fill, "dollar_pnl", None) is not None:
            filled += 1
            p = float(fill.dollar_pnl)
            pnls.append(p)
            if is_anchor:
                anchor_filled += 1
                anchor_pnl[bar_date] += p

    stats = _stats([{"pnl": p} for p in pnls])
    # Per-pattern edge_capture on J-anchor days (OP-16 shape, real-fills):
    #   winners_capture = sum(pnl on WIN-anchor days)
    #   losers_added    = sum(max(0, -pnl) on LOSS-anchor days)   [engine loss is bad]
    win_cap = sum(anchor_pnl[d] for d in anchor_pnl if ANCHORS[d] == "WIN")
    loss_add = sum(max(0.0, -anchor_pnl[d]) for d in anchor_pnl if ANCHORS[d] == "LOSS")
    edge_capture = win_cap - loss_add
    return {
        "config": {
            "strike_offset": strike_offset,
            "tp1_premium_pct": tp1_premium_pct,
            "level_stop_buffer_dollars": level_stop_buffer_dollars,
        },
        "stats": stats,
        "attempted": attempted,
        "filled": filled,
        "anchor_attempted": anchor_attempted,
        "anchor_filled": anchor_filled,
        "anchor_edge_capture": round(edge_capture, 2),
        "anchor_win_capture": round(win_cap, 2),
        "anchor_loss_added": round(loss_add, 2),
        "anchor_by_day": {str(d): round(anchor_pnl[d], 2) for d in sorted(anchor_pnl)},
        "_pnls": pnls,  # internal — stripped before JSON
    }


def _dsr_for(pnls: list[float]) -> dict:
    """Run the advisory DSR/PSR/PBO gate on a config's per-trade real-fills returns.

    Returns to the gate are per-trade dollar P&L (a constant-notional return proxy:
    qty=3 contracts, so the series is directly comparable across configs). PBO is
    skipped (no per-slice CSCV matrix) — verdict rests on DSR + PSR, capped at WEAK
    on low power (n < 20), which is honest for these small per-config samples."""
    if len(pnls) < 2:
        return {"verdict": "FAIL", "reason": f"n={len(pnls)} < 2 — cannot compute", "dsr": None, "psr": None}
    res = evaluate_candidate(pnls, n_trials=N_TRIALS)
    return {
        "verdict": res.verdict,
        "dsr": round(res.dsr, 4),
        "psr": round(res.psr, 4),
        "pbo": res.pbo,
        "n_obs": res.n_obs,
        "low_power": res.low_power,
    }


def run(start: dt.date, end: dt.date) -> dict:
    inputs, rth, ribbon_df = _collect_signals(start, end)

    streams_out: dict = {}
    for stream, _ in DETECTORS:
        sig_inputs = inputs[stream]
        # Baseline (current production exit) for the anchor-no-regression reference.
        base = _simulate_config(
            stream, sig_inputs, rth, ribbon_df,
            BASELINE["strike_offset"], BASELINE["tp1_premium_pct"],
            BASELINE["level_stop_buffer_dollars"],
        )
        base_edge = base["anchor_edge_capture"]
        base_dsr = _dsr_for(base["_pnls"])
        base.pop("_pnls", None)

        # Full exit-knob sweep.
        grid: list[dict] = []
        for so in STRIKE_OFFSETS:
            for tp in TP1_PCTS:
                for buf in STOP_BUFFERS:
                    cfg = _simulate_config(stream, sig_inputs, rth, ribbon_df, so, tp, buf)
                    pnls = cfg.pop("_pnls")
                    cfg["dsr_gate"] = _dsr_for(pnls)
                    # Gate evaluation (honest):
                    exp = cfg["stats"]["exp"]
                    n = cfg["stats"]["n"]
                    anchor_ok = cfg["anchor_edge_capture"] >= base_edge - 1e-6
                    # Vacuous anchor: pattern fires on NO anchor days → the anchor
                    # gate is uninformative (passes only as 0>=0). Per C24 this must
                    # NOT count as a clean PROMOTE-CANDIDATE.
                    anchor_vacuous = cfg["anchor_filled"] == 0
                    dsr_ok = cfg["dsr_gate"]["verdict"] != "FAIL"
                    rf_positive = exp > 0 and n >= 1
                    if rf_positive and anchor_ok and not anchor_vacuous and dsr_ok:
                        verdict = "PROMOTE-CANDIDATE"
                    elif rf_positive and anchor_vacuous and dsr_ok:
                        verdict = "POSITIVE-BUT-ANCHOR-VACUOUS"
                    elif rf_positive and not anchor_ok:
                        verdict = "POSITIVE-BUT-ANCHOR-REGRESSION"
                    elif rf_positive and not dsr_ok:
                        verdict = "POSITIVE-BUT-DSR-FAIL"
                    else:
                        verdict = "NEGATIVE"
                    cfg["gate"] = {
                        "real_fills_positive": rf_positive,
                        "anchor_no_regression": anchor_ok,
                        "anchor_vacuous": anchor_vacuous,
                        "dsr_not_fail": dsr_ok,
                        "verdict": verdict,
                    }
                    grid.append(cfg)

        # Rank: PROMOTE-CANDIDATEs first, then anchor-vacuous-positive, then by exp.
        _ORDER = {"PROMOTE-CANDIDATE": 0, "POSITIVE-BUT-ANCHOR-VACUOUS": 1}

        def _rank_key(c):
            return (_ORDER.get(c["gate"]["verdict"], 2), -c["stats"]["exp"])
        grid.sort(key=_rank_key)

        best = grid[0] if grid else None
        promote_candidates = [c for c in grid if c["gate"]["verdict"] == "PROMOTE-CANDIDATE"]
        anchor_vacuous_positive = [c for c in grid if c["gate"]["verdict"] == "POSITIVE-BUT-ANCHOR-VACUOUS"]
        best_positive = next((c for c in grid if c["stats"]["exp"] > 0), None)

        streams_out[stream] = {
            "n_signals_collected": len(sig_inputs),
            "baseline_current_exit": {
                "config": base["config"],
                "stats": base["stats"],
                "anchor_edge_capture": base_edge,
                "anchor_attempted": base["anchor_attempted"],
                "anchor_filled": base["anchor_filled"],
                "anchor_by_day": base["anchor_by_day"],
                "dsr_gate": base_dsr,
            },
            "best_config": {
                "config": best["config"],
                "stats": best["stats"],
                "anchor_edge_capture": best["anchor_edge_capture"],
                "anchor_attempted": best["anchor_attempted"],
                "anchor_filled": best["anchor_filled"],
                "anchor_by_day": best["anchor_by_day"],
                "dsr_gate": best["dsr_gate"],
                "gate": best["gate"],
            } if best else None,
            "n_promote_candidates": len(promote_candidates),
            "promote_candidates": [
                {"config": c["config"], "exp": c["stats"]["exp"], "wr": c["stats"]["wr"],
                 "n": c["stats"]["n"], "anchor_edge_capture": c["anchor_edge_capture"],
                 "anchor_filled": c["anchor_filled"], "dsr_verdict": c["dsr_gate"]["verdict"]}
                for c in promote_candidates
            ],
            "n_anchor_vacuous_positive": len(anchor_vacuous_positive),
            "anchor_vacuous_positive": [
                {"config": c["config"], "exp": c["stats"]["exp"], "wr": c["stats"]["wr"],
                 "n": c["stats"]["n"], "anchor_filled": c["anchor_filled"],
                 "dsr_verdict": c["dsr_gate"]["verdict"]}
                for c in anchor_vacuous_positive
            ],
            "best_positive_exp_config": (
                {"config": best_positive["config"], "exp": best_positive["stats"]["exp"],
                 "wr": best_positive["stats"]["wr"], "n": best_positive["stats"]["n"],
                 "anchor_edge_capture": best_positive["anchor_edge_capture"],
                 "anchor_filled": best_positive["anchor_filled"],
                 "anchor_ok": best_positive["anchor_edge_capture"] >= base_edge - 1e-6,
                 "dsr_verdict": best_positive["dsr_gate"]["verdict"]}
                if best_positive else None
            ),
            "full_grid": grid,
            "pattern_verdict": _pattern_verdict(
                stream, promote_candidates, anchor_vacuous_positive, best_positive, base_edge),
        }

    result = {
        "window": f"{start}..{end}",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "research_question": (
            "Can an EXIT REDESIGN (sweep strike_offset x tp1_premium_pct x chart-stop-buffer) "
            "flip the strong-SPY-edge WATCH_ONLY watchers to real-fills-POSITIVE while staying "
            "anchor-clean? Real-fills (OPRA) is the only authority (C1)."
        ),
        "exit_grid": {
            "strike_offsets": STRIKE_OFFSETS,
            "tp1_premium_pcts": TP1_PCTS,
            "level_stop_buffer_dollars": STOP_BUFFERS,
            "n_trials": N_TRIALS,
            "fixed": "premium_stop_pct=-0.99 (chart-stop only); tp1_qty_fraction=0.50; runner=2.5",
        },
        "gate_definition": (
            "PROMOTE-CANDIDATE iff real-fills exp>0 AND anchor_edge_capture >= baseline "
            "AND DSR/PBO advisory verdict != FAIL. Baseline = current production exit "
            "(ATM, tp1=0.30, stop_buffer=0.50). Honest no-win is a valid result."
        ),
        "streams": streams_out,
        "op20_disclosures": _op20_disclosures(),
        "overall_verdict": _overall_verdict(streams_out),
    }
    return result


def _pattern_verdict(stream, promote_candidates, anchor_vacuous_positive, best_positive, base_edge) -> str:
    if promote_candidates:
        b = promote_candidates[0]  # raw grid cfg (best by rank)
        return (f"PROMOTE-CANDIDATE — {len(promote_candidates)} exit config(s) flip real-fills "
                f"positive AND anchor-clean (anchor_filled={b['anchor_filled']}) AND DSR!=FAIL. "
                f"Best: {b['config']} exp=${b['stats']['exp']} (WR {b['stats']['wr']}%, "
                f"n={b['stats']['n']}, anchor_edge_capture=${b['anchor_edge_capture']} vs baseline "
                f"${base_edge}). PROXY levels — confirm on production ★★★ before wiring.")
    if anchor_vacuous_positive:
        b = anchor_vacuous_positive[0]
        return (f"POSITIVE-BUT-ANCHOR-UNTESTABLE — {len(anchor_vacuous_positive)} exit config(s) reach "
                f"positive real-fills exp (best {b['config']} exp=${b['stats']['exp']}, WR "
                f"{b['stats']['wr']}%, n={b['stats']['n']}) but the pattern fires on ZERO J-anchor "
                f"days (anchor_filled=0) so the anchor-no-regression gate is UNINFORMATIVE (passes "
                f"only vacuously as 0>=0). NOT a clean PROMOTE-CANDIDATE — anchor alignment is unproven "
                f"(C24). Worth a focused real-fills re-test on production ★★★ levels + a J-anchor-day "
                f"firing check before any promotion.")
    if best_positive is not None:
        anchor_ok = best_positive["anchor_edge_capture"] >= base_edge - 1e-6
        reason = "anchor regression" if not anchor_ok else "DSR FAIL"
        return (f"DEAD-UNDER-TESTED-EXITS — best exit ({best_positive['config']}) reaches positive "
                f"real-fills exp=${best_positive['stats']['exp']} but fails the {reason} leg of the "
                f"gate. No PROMOTE-CANDIDATE config.")
    return ("DEAD-UNDER-ALL-TESTED-EXITS — NO exit config in the swept grid produced positive "
            "real-fills expectancy. Confirmed real-fills-unprofitable across strike_offset x "
            "tp1 x stop-buffer. Honest no-win.")


def _overall_verdict(streams_out: dict) -> dict:
    promote = [s for s, v in streams_out.items() if v["n_promote_candidates"] > 0]
    vacuous = [s for s, v in streams_out.items()
               if v["n_promote_candidates"] == 0 and v.get("n_anchor_vacuous_positive", 0) > 0]
    dead = [s for s, v in streams_out.items()
            if v["n_promote_candidates"] == 0 and v.get("n_anchor_vacuous_positive", 0) == 0]
    return {
        "promote_candidates": promote,
        "positive_but_anchor_untestable": vacuous,
        "dead_under_tested_exits": dead,
        "summary": (
            f"{len(promote)}/{len(streams_out)} patterns have >=1 clean PROMOTE-CANDIDATE exit config. "
            + ("Tradeable exit-redesign path (anchor-clean): " + ", ".join(promote) + ". " if promote else "")
            + ("Real-fills-positive but anchor-untestable (fires on no J-anchor days — NOT a clean "
               "promote, re-test needed): " + ", ".join(vacuous) + ". " if vacuous else "")
            + ("Confirmed dead under all tested exits: " + ", ".join(dead) + "." if dead else "")
        ),
    }


def _op20_disclosures() -> dict:
    return {
        "authority": "Real-fills (lib.simulator_real + OPRA options cache, valid through 2026-05-29). "
                     "BS-sim is ranking-only and is NOT used here (C1). SPY-price grade omitted — the "
                     "prior level-family-validation.json already established SPY-space edge; this run "
                     "tests ONLY whether real-fills can be flipped by exit geometry.",
        "level_source_caveat": (
            "All 3 watchers read key-levels.json from disk; this run monkeypatches each per-day cache "
            "to SYNTHETIC PDH/PDL/PDC/PDO proxies (★★/★), NOT production ★★★ named levels (no historical "
            "archive). Absolute WR is a proxy LOWER-BOUND (PDL-class proxies understate ★★★ WR up to "
            "~20pp per L58). The EXIT comparison is internally consistent (identical level set across all "
            "configs), so 'does any exit flip the sign?' is answerable on the proxy."
        ),
        "concentration": "Per-config n is the real-fills fill count (OPRA-available, capped at "
                         f"{MAX_SIGNALS_PER_STREAM}/stream). Small per-config n → DSR capped at WEAK on "
                         "low_power (n<20). Treat single-config wins with the per-quarter concentration "
                         "caveat from the parent level-family-validation.json.",
        "anchor_gate": "OP-16 shape on real-fills: anchor_edge_capture = sum(pnl on WIN-anchor days) - "
                       "sum(max(0,-pnl) on LOSS-anchor days). 'no regression' = config's edge_capture >= "
                       "the current-production-exit baseline's. NOTE: anchor n is tiny (J has 3 WIN + 3 LOSS "
                       "days, and these watchers fire on only a subset) — a clean anchor here is necessary, "
                       "not sufficient (lesson C24: absence of regression at small-n is weak evidence).",
        "premium_stop": "premium_stop_pct=-0.99 (disabled) for ALL configs — chart/ribbon/time exits only "
                        "(C1/C2). This sweep isolates chart-exit geometry; it does NOT re-test premium stops.",
        "dsr_returns": "DSR/PSR computed on per-trade dollar P&L (constant qty=3 notional → comparable). "
                       "PBO skipped (no CSCV per-slice matrix). Advisory only (gate.py is not a hard gate).",
        "not_a_promotion": "RESEARCH ONLY. No watcher code, params, or doctrine changed. Watchers remain "
                           "WATCH_ONLY. A PROMOTE-CANDIDATE here means 'worth a real-fills re-test on "
                           "production ★★★ levels', not 'wire it live'.",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end", default="2026-05-29")  # OPRA coverage ends 2026-05-29
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    res = run(dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end))
    # Strip the heavy full_grid from stdout (keep it in the file).
    summary = {k: v for k, v in res.items() if k != "streams"}
    summary["streams_summary"] = {
        s: {
            "pattern_verdict": v["pattern_verdict"],
            "baseline_exp": v["baseline_current_exit"]["stats"]["exp"],
            "best_exp": v["best_config"]["stats"]["exp"] if v["best_config"] else None,
            "n_promote_candidates": v["n_promote_candidates"],
        }
        for s, v in res["streams"].items()
    }
    print(json.dumps(summary, indent=2, default=str))
    if a.out:
        out_path = Path(a.out)
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
        print("wrote", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
