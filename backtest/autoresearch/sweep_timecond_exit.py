"""GAME PLAN 2 — Time-conditional exit A/B around the 0DTE theta cliff (real-fills).

THE FINDING (triple-corroborated, markdown/planning/WEEKEND-RESEARCH-GAMEPLANS-2026-06-19.md GP2):
  0DTE theta decay is BACK-LOADED — ~2%/hr at the open climbing past ~15%/hr after
  14:00, with a sharp cliff ~15:30 ET. Our hard time stop is 15:50 — slightly LATE
  for a long-premium holder. Hypothesis: a TIME-CONDITIONAL exit (let positions in
  strong favor ride the existing exits, but pull NON-favored/stagnant positions out
  earlier ~15:00-15:30) improves real-fills expectancy by stepping off the steepest
  decay WITHOUT clipping the convex winners (AQR: let winners run).

WHAT THIS TESTS (real-fills, OPRA — the ONLY authority, theme C1):
  A/B the new opt-in `early_cutoff_et` + `early_cutoff_min_favor_pct` knob in
  lib.simulator_real.simulate_trade_real against the current 15:50 baseline, on:
    * PRIMARY population: BEARISH_REJECTION_MORNING — the codified, CONFIRMED
      BEARISH_REJECTION_RIDE_THE_RIBBON setup (the prior bearish-continuation-family
      scorecard's clean result: it IS the bearish edge; "the leverage is in
      EXIT/REGIME work").
    * BROAD population: the pooled bearish-continuation real-fills set
      (BRM + LEVEL_BREAK_FIRST_STRIKE + HEAD_AND_SHOULDERS_BEAR) — the same entries
      that scorecard graded on real fills, pooled, to see the exit effect across the
      whole bearish-continuation book rather than one detector.

  EXIT VARIANTS (lean: 3 cutoffs x 3 favor thresholds + baseline = 10 per strike):
    - Baseline:        early_cutoff_et=None  (current 15:50-only behavior).
    - Time-conditional: early_cutoff_et in {15:00, 15:15, 15:30}
                        x early_cutoff_min_favor_pct in {0.00, +0.10, +0.25}.
      "Not in favor" = TP1 not filled AND current premium < entry*(1+thr) at the
      cutoff -> force-close at market. In-favor (TP1 banked or premium past thr)
      rides to the existing chandelier/level/ribbon/15:50 exits.

  Everything else held at PRODUCTION (chart-stop only premium_stop_pct=-0.99 per
  L51/L55; tp1_premium 0.30; tp1_qty_fraction 0.50; runner 2.5; level buffer 0.50).
  Strikes: ATM (offset 0, J's anchor strike class) AND ITM2 (offset -2, Bold class).

METRICS PER VARIANT (real-fills): total P&L, WR, avg win, avg loss, expectancy,
  edge_capture on J's anchor days (OP-16 shape: sum WIN-day pnl - sum max(0,-LOSS-day
  pnl)), and the advisory DSR/PSR gate (n_trials = grid size).

THE GATE (honest — do NOT loosen to manufacture a win):
  PROMOTE-CANDIDATE iff vs the SAME-population SAME-strike baseline:
    (1) real-fills total P&L AND expectancy strictly improve, AND
    (2) anchor-no-regression: anchor edge_capture >= baseline (must NOT hurt the
        4/29-5/01-5/04 winners), AND
    (3) DSR/PSR advisory verdict != FAIL.
  If NO variant clears -> 15:50 is already right for that population/strike (cutting
  earlier clips late winners). A clean no-win is a VALID, reportable result.

OP-20 DISCLOSURES (read before trusting):
  * Real-fills authority: lib.simulator_real over the OPRA options cache (valid
    through 2026-05-29). SPY-space grade is NOT used for the verdict here.
  * ANCHOR COVERAGE IS THIN: of J's 6 anchor days, 5/04 has NO option bars in the
    cache (0 contracts) so the biggest winner cannot be graded; BRM fires with an
    OPRA fill on only 4/29 among the WIN days. The anchor-no-regression leg is
    therefore necessary-not-sufficient (lesson C24) — a tie at n=1 anchor fill is
    weak evidence, reported as such.
  * Levels are historically-rebuilt proxies (active+multi_day via _detect_from_history
    as-of each day), NOT production ★★★ named levels (no archive). The EXIT comparison
    is internally consistent (identical signal population + levels across all variants),
    so "does an earlier cutoff flip the sign?" is answerable on the proxy.
  * The early-cutoff favor test reads the CURRENT bar high as the favorable reference
    (generous: only genuinely stagnant positions get cut). It evaluates strictly
    BEFORE the 15:50 stop, so a 15:00/15:15/15:30 cutoff binds first.

RESEARCH ONLY (Rule 9). No params/heartbeat/doctrine changed. The simulator knob is
opt-in and defaults OFF; a PROMOTE-CANDIDATE here is "worth ratifying", not "wired".

Usage:
  python -m autoresearch.sweep_timecond_exit --realfills \
      --out ../analysis/recommendations/timecond-exit-sweep.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

# Reuse the bearish-continuation harness wholesale: it runs the chart_patterns
# bootstrap, _load_data, the per-bar BarContext pipeline with historically-rebuilt
# levels (no look-ahead), the OP-16 anchors, and the detector set. We only swap the
# EXIT simulation (vary early_cutoff_*), not the signal population.
from autoresearch import validate_bearish_continuation_family as bcf  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent

from lib.validation.gate import evaluate_candidate  # noqa: E402

ANCHORS = bcf.ANCHORS

# ── Populations under test ───────────────────────────────────────────────────
# PRIMARY: the confirmed setup. BROAD: pooled bearish-continuation real-fills book.
_PRIMARY = "BEARISH_REJECTION_MORNING"
_BROAD_MEMBERS = [
    "BEARISH_REJECTION_MORNING",
    "LEVEL_BREAK_FIRST_STRIKE",
    "HEAD_AND_SHOULDERS_BEAR",
]

# ── Exit-knob grid (lean) ────────────────────────────────────────────────────
CUTOFFS = [dt.time(15, 0), dt.time(15, 15), dt.time(15, 30)]
FAVOR_THRESHOLDS = [0.00, 0.10, 0.25]
STRIKES = (("ATM", 0), ("ITM2", -2))

# n_trials for DSR deflation = number of time-conditional configs searched (per
# population+strike). Baseline is the reference, not a searched trial.
N_TRIALS = len(CUTOFFS) * len(FAVOR_THRESHOLDS)

# Production-equivalent fixed exit knobs (the baseline config + every variant share
# these; only early_cutoff_* differs). Chart-stop only per C1/C2.
_FIXED = dict(
    premium_stop_pct=-0.99,
    strike_offset=0,            # overridden per-strike below
    tp1_premium_pct=0.30,
    tp1_qty_fraction=0.50,
    runner_target_premium_pct=2.5,
    level_stop_buffer_dollars=0.50,
)


def _rej_for(sig):
    """The chart level a bearish-continuation signal keys its level-stop on (mirrors
    validate_bearish_continuation_family's real-fills rej selection)."""
    return (sig.metadata.get("rejection_level")
            or sig.metadata.get("break_level")
            or sig.metadata.get("neckline")
            or sig.metadata.get("broken_level")
            or sig.metadata.get("swept_level")
            or sig.stop_price)


def _favor_stats(pnls: list[float]) -> dict:
    """real-fills stats incl. avg win / avg loss (the convex-payoff diagnostics)."""
    n = len(pnls)
    if n == 0:
        return {"n": 0, "wr": 0.0, "total": 0.0, "exp": 0.0, "avg_win": 0.0,
                "avg_loss": 0.0, "n_win": 0, "n_loss": 0}
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    tot = sum(pnls)
    return {
        "n": n,
        "wr": round(100 * len(wins) / n, 1),
        "total": round(tot, 2),
        "exp": round(tot / n, 2),
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0.0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
        "n_win": len(wins),
        "n_loss": len(losses),
    }


def _dsr_for(pnls: list[float]) -> dict:
    """Advisory DSR/PSR on per-trade dollar P&L (constant qty=3 notional -> comparable).
    PBO skipped (no CSCV per-slice matrix); capped at WEAK on low power (honest)."""
    if len(pnls) < 2:
        return {"verdict": "FAIL", "reason": f"n={len(pnls)} < 2", "dsr": None, "psr": None,
                "low_power": True, "n_obs": len(pnls)}
    res = evaluate_candidate(pnls, n_trials=N_TRIALS)
    return {"verdict": res.verdict, "dsr": round(res.dsr, 4), "psr": round(res.psr, 4),
            "pbo": res.pbo, "n_obs": res.n_obs, "low_power": res.low_power}


def _simulate(capped_signals, rth, ribbon_df, offset, early_cutoff_et, favor_pct):
    """Run real-fills for one (population subset already in capped_signals) under one
    exit config. Returns (pnls, anchor_pnl_by_day, diag)."""
    from lib.simulator_real import simulate_trade_real
    pnls: list[float] = []
    anchor_pnl: dict[str, float] = defaultdict(float)
    attempted = no_fill = errored = anchor_fills = 0
    cfg = dict(_FIXED)
    cfg["strike_offset"] = offset
    cfg["early_cutoff_et"] = early_cutoff_et       # None for baseline
    cfg["early_cutoff_min_favor_pct"] = favor_pct
    anchor_dates = {d.isoformat() for d in ANCHORS}
    for (idx, bar, sig) in capped_signals:
        attempted += 1
        bar_date_str = str(bar["timestamp_et"].date())
        rej = _rej_for(sig)
        try:
            fill = simulate_trade_real(
                entry_bar_idx=idx, entry_bar=bar, spy_df=rth, ribbon_df=ribbon_df,
                rejection_level=float(rej), triggers_fired=list(sig.triggers_fired),
                side="P", qty=3, setup=sig.setup_name, **cfg)
        except Exception as exc:
            errored += 1
            if errored <= 3:
                sys.stderr.write(f"realfills exc @ {bar['timestamp_et']}: "
                                 f"{type(exc).__name__}: {exc}\n")
            fill = None
        if fill is not None and getattr(fill, "dollar_pnl", None) is not None:
            p = float(fill.dollar_pnl)
            pnls.append(p)
            if bar_date_str in anchor_dates:
                anchor_pnl[bar_date_str] += p
                anchor_fills += 1
        else:
            no_fill += 1
    diag = {"attempted": attempted, "filled": len(pnls),
            "no_fill_or_no_data": no_fill, "errored": errored,
            "anchor_fills": anchor_fills}
    return pnls, dict(anchor_pnl), diag


def _anchor_edge(anchor_pnl: dict[str, float]) -> dict:
    """OP-16 edge_capture on real-fills anchor days for this config."""
    win = sum(anchor_pnl.get(d.isoformat(), 0.0) for d in ANCHORS if ANCHORS[d] == "WIN")
    loss = sum(max(0.0, -anchor_pnl.get(d.isoformat(), 0.0)) for d in ANCHORS if ANCHORS[d] == "LOSS")
    return {"edge_capture": round(win - loss, 2),
            "win_day_pnl": round(win, 2),
            "loss_day_loss": round(loss, 2),
            "by_day": {d: round(v, 2) for d, v in sorted(anchor_pnl.items())}}


def _collect(start: dt.date, end: dt.date) -> dict:
    """Single pass: fire the bearish-continuation detectors, collect (idx,bar,sig)
    per stream with anchor-inclusive cap. Reuses bcf.run's firing loop by calling it
    and re-deriving from realfills_inputs is not exposed, so we replicate the lean
    firing loop here using bcf's pipeline helpers (no detector logic duplicated)."""
    spy_full, vix_full = bcf.vbf._load_data(start, end)
    spy_full["timestamp_et"] = bcf.vbf.pd.to_datetime(spy_full["timestamp_et"])
    spy_full["date"] = spy_full["timestamp_et"].dt.date
    rth = spy_full[(spy_full["timestamp_et"].dt.time >= dt.time(9, 30)) &
                   (spy_full["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    ribbon_df = bcf.compute_ribbon(rth["close"])
    vix_aligned = bcf._align_vix_to_spy(rth, vix_full)
    htf_stacks = bcf._precompute_htf_15m_stacks(rth)

    bcf._reset_state()
    inputs: dict[str, list] = {k: [] for k in _BROAD_MEMBERS}
    level_states: dict = {}
    ribbon_history: list = []
    last_date = None
    _lvl_cache = [None]
    _lvl_date = [None]

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
            rr = ribbon_df.iloc[idx]
            ribbon_state = bcf.RibbonState(fast=float(rr["fast"]), pivot=float(rr["pivot"]),
                                           slow=float(rr["slow"]), stack=str(rr["stack"]),
                                           spread_cents=float(rr["spread_cents"]))
        except Exception:
            continue
        ribbon_history.append(ribbon_state)
        ribbon_history = ribbon_history[-10:]
        vol_baseline = bcf.vol_baseline_20bar(rth, idx)
        range_baseline = bcf.range_baseline_20bar(rth, idx)
        vix_now = float(vix_aligned.iloc[idx]) if idx < len(vix_aligned) else 17.0
        vix_prior = float(vix_aligned.iloc[max(0, idx - 3)]) if max(0, idx - 3) < len(vix_aligned) else vix_now

        if bar_date != _lvl_date[0]:
            full_history = spy_full[spy_full["timestamp_et"] <= bar_time]
            _lvl_cache[0] = bcf._detect_from_history(full_history, bar_date)
            _lvl_date[0] = bar_date
        level_set = _lvl_cache[0]
        bcf._update_level_states(level_states, level_set.active, bar, idx)
        htf = htf_stacks[idx] if idx < len(htf_stacks) else None

        ctx = bcf.BarContext(
            bar_idx=idx, timestamp_et=bar_time.to_pydatetime(), bar=bar,
            prior_bars=rth.iloc[:idx + 1], ribbon_now=ribbon_state, ribbon_history=ribbon_history,
            vix_now=vix_now, vix_prior=vix_prior, vol_baseline_20=vol_baseline,
            range_baseline_20=range_baseline, levels_active=level_set.active,
            multi_day_levels=level_set.multi_day, htf_15m_stack=htf, level_states=level_states,
        )
        for stream in _BROAD_MEMBERS:
            detector = bcf._DETECTORS[stream]
            try:
                sig = detector(ctx)
            except Exception as exc:
                sys.stderr.write(f"{stream} @ {bar_time}: {type(exc).__name__}: {exc}\n")
                sig = None
            if sig is None:
                continue
            inputs[stream].append((idx, bar, sig))
    return {"inputs": inputs, "rth": rth, "ribbon_df": ribbon_df}


def _cap_anchor_inclusive(inputs: list, cap: int = 200) -> list:
    """Cap signals for runtime but ALWAYS keep anchor-day signals (else the
    anchor-no-regression gate is vacuous — lesson C24 / mirrors sweep_watcher_exits)."""
    anchor_dates = {d.isoformat() for d in ANCHORS}
    capped = list(inputs[:cap])
    capped_idx = {id(t) for t in capped}
    for t in inputs[cap:]:
        if str(t[1]["timestamp_et"].date()) in anchor_dates and id(t) not in capped_idx:
            capped.append(t)
            capped_idx.add(id(t))
    return capped


def _run_population(name: str, capped_signals: list, rth, ribbon_df) -> dict:
    """Run baseline + full grid for one population, both strikes; gate each variant."""
    strikes_out: dict = {}
    for slabel, offset in STRIKES:
        # Baseline (cutoff OFF).
        base_pnls, base_anchor, base_diag = _simulate(
            capped_signals, rth, ribbon_df, offset, None, 0.0)
        base_stats = _favor_stats(base_pnls)
        base_edge = _anchor_edge(base_anchor)
        base_dsr = _dsr_for(base_pnls)

        grid: list[dict] = []
        for cutoff in CUTOFFS:
            for thr in FAVOR_THRESHOLDS:
                pnls, anchor, diag = _simulate(
                    capped_signals, rth, ribbon_df, offset, cutoff, thr)
                stats = _favor_stats(pnls)
                edge = _anchor_edge(anchor)
                dsr = _dsr_for(pnls)
                # ── Gate (honest, vs same-strike baseline) ──
                pnl_better = stats["total"] > base_stats["total"] + 1e-6
                exp_better = stats["exp"] > base_stats["exp"] + 1e-6
                anchor_ok = edge["edge_capture"] >= base_edge["edge_capture"] - 1e-6
                anchor_vacuous = diag["anchor_fills"] == 0
                dsr_ok = dsr["verdict"] != "FAIL"
                if pnl_better and exp_better and anchor_ok and not anchor_vacuous and dsr_ok:
                    verdict = "PROMOTE-CANDIDATE"
                elif pnl_better and exp_better and anchor_vacuous and dsr_ok:
                    verdict = "BETTER-BUT-ANCHOR-VACUOUS"
                elif pnl_better and exp_better and not anchor_ok:
                    verdict = "BETTER-BUT-ANCHOR-REGRESSION"
                elif pnl_better and exp_better and not dsr_ok:
                    verdict = "BETTER-BUT-DSR-FAIL"
                else:
                    verdict = "NOT-BETTER"
                grid.append({
                    "config": {"cutoff_et": cutoff.strftime("%H:%M"), "min_favor_pct": thr},
                    "stats": stats,
                    "anchor": edge,
                    "diag": diag,
                    "dsr_gate": dsr,
                    "delta_total_vs_baseline": round(stats["total"] - base_stats["total"], 2),
                    "delta_exp_vs_baseline": round(stats["exp"] - base_stats["exp"], 2),
                    "gate": {
                        "pnl_better": pnl_better, "exp_better": exp_better,
                        "anchor_no_regression": anchor_ok, "anchor_vacuous": anchor_vacuous,
                        "dsr_not_fail": dsr_ok, "verdict": verdict,
                    },
                })

        promote = [c for c in grid if c["gate"]["verdict"] == "PROMOTE-CANDIDATE"]
        better_any = [c for c in grid if c["gate"]["pnl_better"] and c["gate"]["exp_better"]]

        def _rank_key(c):
            order = {"PROMOTE-CANDIDATE": 0, "BETTER-BUT-ANCHOR-VACUOUS": 1}
            return (order.get(c["gate"]["verdict"], 2), -c["stats"]["total"])
        grid_sorted = sorted(grid, key=_rank_key)
        best = grid_sorted[0] if grid_sorted else None

        strikes_out[slabel] = {
            "baseline_15_50": {
                "stats": base_stats, "anchor": base_edge, "diag": base_diag, "dsr_gate": base_dsr,
            },
            "n_promote_candidates": len(promote),
            "promote_candidates": [
                {"config": c["config"], "stats": c["stats"], "anchor": c["anchor"],
                 "delta_total_vs_baseline": c["delta_total_vs_baseline"],
                 "dsr_verdict": c["dsr_gate"]["verdict"]}
                for c in promote],
            "best_variant": best,
            "n_better_any": len(better_any),
            "grid": grid_sorted,
            "verdict": _strike_verdict(slabel, base_stats, base_edge, promote, better_any),
        }
    return {
        "n_signals": len(capped_signals),
        "strikes": strikes_out,
    }


def _strike_verdict(slabel, base_stats, base_edge, promote, better_any) -> str:
    if promote:
        b = promote[0]
        return (f"[{slabel}] PROMOTE-CANDIDATE — {len(promote)} time-conditional config(s) beat the "
                f"15:50 baseline on BOTH total P&L and expectancy AND anchor-no-regression AND "
                f"DSR!=FAIL. Best: cutoff {b['config']['cutoff_et']} / favor +{int(b['config']['min_favor_pct']*100)}% "
                f"-> total ${b['stats']['total']} (exp ${b['stats']['exp']}, WR {b['stats']['wr']}%, "
                f"n={b['stats']['n']}) vs baseline total ${base_stats['total']} (exp ${base_stats['exp']}). "
                f"anchor edge_capture ${b['anchor']['edge_capture']} vs baseline ${base_edge['edge_capture']}. "
                f"PROXY levels + thin anchors — ratify on production ★★★ before wiring (Rule 9).")
    if better_any:
        b = sorted(better_any, key=lambda c: -c["stats"]["total"])[0]
        why = ("anchor regression" if not b["gate"]["anchor_no_regression"]
               else "anchor-vacuous (fires on no gradeable anchor day)" if b["gate"]["anchor_vacuous"]
               else "DSR FAIL")
        return (f"[{slabel}] BETTER-BUT-GATE-FAILS — best time-conditional config "
                f"(cutoff {b['config']['cutoff_et']} / favor +{int(b['config']['min_favor_pct']*100)}%) beats "
                f"baseline on total ${b['stats']['total']} vs ${base_stats['total']} but fails the {why} leg. "
                f"No clean PROMOTE-CANDIDATE.")
    return (f"[{slabel}] BASELINE-OPTIMAL — NO time-conditional cutoff beat the 15:50 baseline on both "
            f"total P&L and expectancy. Cutting non-favored positions earlier does NOT help this "
            f"population/strike (baseline total ${base_stats['total']}, exp ${base_stats['exp']}). "
            f"15:50 is already right here — earlier exits clip late winners / give up theta-rebound. "
            f"Honest no-win (a valuable result).")


def run(start: dt.date, end: dt.date) -> dict:
    coll = _collect(start, end)
    inputs, rth, ribbon_df = coll["inputs"], coll["rth"], coll["ribbon_df"]

    # PRIMARY population: BRM alone.
    primary_caps = _cap_anchor_inclusive(inputs[_PRIMARY])
    primary = _run_population(_PRIMARY, primary_caps, rth, ribbon_df)

    # BROAD population: pooled bearish-continuation real-fills book (chronological).
    pooled = []
    for stream in _BROAD_MEMBERS:
        pooled.extend(inputs[stream])
    pooled.sort(key=lambda t: t[0])  # by bar idx
    broad_caps = _cap_anchor_inclusive(pooled)
    broad = _run_population("BEARISH_CONTINUATION_POOLED", broad_caps, rth, ribbon_df)

    result = {
        "research_question": (
            "Does a TIME-CONDITIONAL early exit (cut stagnant/non-favored 0DTE positions at "
            "15:00/15:15/15:30, let in-favor positions ride to existing exits) beat the 15:50 "
            "hard time stop on real-fills, WITHOUT hurting J's anchor-day winners? "
            "Game Plan 2 — exit refinement around the theta cliff."),
        "window": f"{start}..{end}",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "exit_grid": {
            "cutoffs_et": [c.strftime("%H:%M") for c in CUTOFFS],
            "favor_thresholds_pct": FAVOR_THRESHOLDS,
            "strikes": [s for s, _ in STRIKES],
            "n_trials_for_dsr": N_TRIALS,
            "fixed": ("premium_stop_pct=-0.99 (chart-stop only); tp1_premium 0.30; "
                      "tp1_qty_fraction 0.50; runner 2.5; level_stop_buffer 0.50"),
        },
        "gate_definition": (
            "PROMOTE-CANDIDATE iff vs same-population same-strike 15:50 baseline: total P&L AND "
            "expectancy strictly improve AND anchor edge_capture >= baseline (anchor-no-regression) "
            "AND DSR/PSR advisory != FAIL AND anchor not vacuous. Honest no-win is a valid result."),
        "populations": {
            "BEARISH_REJECTION_MORNING_primary": primary,
            "BEARISH_CONTINUATION_POOLED_broad": broad,
        },
        "op20_disclosures": _op20_disclosures(),
    }
    result["overall_verdict"] = _overall_verdict(result)
    return result


def _op20_disclosures() -> dict:
    return {
        "authority": ("Real-fills (lib.simulator_real + OPRA options cache, valid through 2026-05-29) "
                      "is the only authority used for the verdict (C1). BS-sim / SPY-space grade not used."),
        "anchor_coverage": ("THIN. 5/04 (J's biggest winner, +$730) has ZERO option bars in the cache, "
                            "so it cannot be graded on real fills; BRM has an OPRA fill on only 4/29 among "
                            "the WIN anchor days. The anchor-no-regression gate is necessary-not-sufficient "
                            "(C24) — a tie at n=1 anchor fill is weak evidence."),
        "level_source": ("Historically-rebuilt ★★ proxies (active+multi_day from _detect_from_history "
                         "as-of each day), NOT production ★★★ named levels (no archive). Absolute WR is a "
                         "proxy LOWER-BOUND; the EXIT comparison is internally consistent (identical signal "
                         "population + level set across all variants), so the sign-flip question is answerable."),
        "favor_test": ("'In favor' at the cutoff = TP1 filled OR current-bar premium >= entry*(1+thr). "
                       "Uses the current bar HIGH as the favorable reference (generous — only genuinely "
                       "stagnant positions are cut). Evaluated strictly BEFORE the 15:50 stop."),
        "knob": ("Opt-in lib.simulator_real.simulate_trade_real(early_cutoff_et, early_cutoff_min_favor_pct); "
                 "defaults early_cutoff_et=None => OFF => byte-for-byte prior behavior (verified: 18 e2e tests + "
                 "anchor reproduction unchanged). RESEARCH ONLY — no params/doctrine changed (Rule 9)."),
        "populations": ("PRIMARY = BEARISH_REJECTION_MORNING (the codified CONFIRMED setup, the prior "
                        "bearish-continuation scorecard's clean edge). BROAD = pooled BRM + LEVEL_BREAK_FIRST_STRIKE "
                        "+ HEAD_AND_SHOULDERS_BEAR real-fills (same set that scorecard graded), to see the "
                        "exit effect across the whole bearish-continuation book."),
        "dsr_returns": ("DSR/PSR on per-trade dollar P&L (constant qty=3 notional -> comparable). PBO skipped "
                        f"(no CSCV matrix). n_trials={N_TRIALS} (grid size). Advisory only (gate.py is not a hard gate)."),
    }


def _overall_verdict(result: dict) -> dict:
    out = {}
    promote_any = False
    lines = []
    for pop_key, pop in result["populations"].items():
        for slabel, sblk in pop["strikes"].items():
            tag = f"{pop_key}/{slabel}"
            out[tag] = sblk["verdict"]
            if sblk["n_promote_candidates"] > 0:
                promote_any = True
            lines.append(sblk["verdict"])
    result_summary = (
        "TIME-CONDITIONAL EXIT beats 15:50 on >=1 population/strike (see per-strike PROMOTE-CANDIDATE)."
        if promote_any else
        "15:50 BASELINE IS OPTIMAL across all tested populations/strikes — no earlier time-conditional "
        "cutoff beat it on both total P&L and expectancy with anchor-no-regression. Cutting non-favored "
        "positions earlier clips late winners / gives up theta-rebound. Honest no-win (a valuable result): "
        "do NOT move the time stop earlier on this evidence.")
    return {"any_promote_candidate": promote_any, "per_strike": out, "summary": result_summary}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end", default="2026-05-29")  # OPRA coverage ends 2026-05-29
    ap.add_argument("--realfills", action="store_true", help="(always real-fills; flag kept for parity)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    res = run(dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end))
    # Compact stdout: drop the heavy per-population grids; keep verdicts + baselines.
    compact = {k: v for k, v in res.items() if k != "populations"}
    compact["populations_summary"] = {
        pop_key: {
            "n_signals": pop["strikes"][list(pop["strikes"])[0]].get("n_signals") if False else None,
            "strikes": {
                slabel: {
                    "baseline_total": sblk["baseline_15_50"]["stats"]["total"],
                    "baseline_exp": sblk["baseline_15_50"]["stats"]["exp"],
                    "baseline_n": sblk["baseline_15_50"]["stats"]["n"],
                    "baseline_anchor_edge": sblk["baseline_15_50"]["anchor"]["edge_capture"],
                    "best_variant_total": (sblk["best_variant"]["stats"]["total"]
                                           if sblk["best_variant"] else None),
                    "best_variant_config": (sblk["best_variant"]["config"]
                                            if sblk["best_variant"] else None),
                    "n_promote_candidates": sblk["n_promote_candidates"],
                    "verdict": sblk["verdict"],
                }
                for slabel, sblk in pop["strikes"].items()
            },
        }
        for pop_key, pop in res["populations"].items()
    }
    print(json.dumps(compact, indent=2, default=str))
    if a.out:
        out_path = Path(a.out)
        if not out_path.is_absolute():
            out_path = (Path.cwd() / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
        print("wrote", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
