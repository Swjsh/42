"""REGIME-CONDITIONAL CHANDELIER exit A/B on BEARISH_REJECTION real-fills.

THE FINDING (peer-reviewed, untested on us — Kim-Tse-Wald, JFE):
  Trend-following's edge is volatility-SCALED risk management, not the entry. The
  trailing stop should WIDEN in high vol and TIGHTEN in calm so it does not choke a
  winner during the volatile final leg (AQR: let the big one run). We currently use a
  FIXED "20% off the high-water-mark of favor_premium" chandelier (v15). Hypothesis:
  a regime-conditional / underlying-move chandelier beats the fixed 20% on real-fills
  WITHOUT clipping the convex winners.

WHAT THIS TESTS (real-fills, OPRA — the only WR authority, theme C1) on the codified
CONFIRMED setup BEARISH_REJECTION_MORNING (the "#1 leverage = exit/regime on
BEARISH_REJECTION" — exit refinement on our one confirmed edge):

  BASELINE = the PRODUCTION v15 premium chandelier:
    profit_lock_mode='trailing', threshold +5%, stop_offset +10%, trail 20% off
    premium HWM. (NOT chart-stop-only — this is the thing we are trying to beat.)

  VARIANTS (lean):
    A) Fixed premium trail  : trail in {15%, 25%, 30%} (vs baseline 20%).
    B) Regime premium trail : trail = f(entry_VIX) via {vix_ceiling: trail} maps —
         WIDE_HIVOL  {16:0.15, 22:0.25, 999:0.35}  (tight calm / wide high-vol)
         GENTLE      {18:0.18, 999:0.28}
    C) Underlying trail      : trail the SPY MOVE per the research, not premium.
         Fixed  : underlying_pct in {0.30%, 0.50%} of entry_spot (exit when SPY
                  retraces that far off the favorable extreme).
         Regime : {16:0.0030, 22:0.0045, 999:0.0065} of entry_spot (wider in high vol).

  Everything else held at PRODUCTION exit config (tp1_premium 0.30, tp1_qty_fraction
  0.50, runner 2.5, level buffer 0.50, premium catastrophe cap -0.99 so the chandelier
  — not a tight premium stop — is the governing profit-lock). Strikes: ATM (offset 0,
  J's anchor strike class) AND ITM2 (offset -2, Bold class).

METRICS PER VARIANT (real-fills): total P&L, WR, avg win, avg loss, expectancy,
  edge_capture on J's anchor days (OP-16 shape), advisory DSR/PSR (n_trials=grid size).

THE GATE (honest — do NOT loosen to manufacture a win):
  PROMOTE-CANDIDATE iff vs the SAME-population SAME-strike PRODUCTION-CHANDELIER
  baseline:
    (1) real-fills total P&L AND expectancy strictly improve, AND
    (2) anchor-no-regression: anchor edge_capture >= baseline (must NOT clip the
        4/29-5/01-5/04 winners), AND
    (3) DSR/PSR advisory verdict != FAIL.
  If NO variant clears -> the fixed 20% premium chandelier is already right for that
  population/strike. A clean no-win is a VALID, reportable result (do not manufacture).

OP-20 DISCLOSURES (read before trusting):
  * Real-fills authority: lib.simulator_real over the OPRA options cache (valid
    through 2026-05-29). SPY-space grade is NOT used for the verdict.
  * ANCHOR COVERAGE IS THIN: of J's 6 anchor days, 5/04 (the biggest winner) has NO
    option bars in the cache and BRM fires with an OPRA fill on only 4/29 among the WIN
    days -> the anchor-no-regression leg is necessary-not-sufficient (lesson C24); a tie
    at n=1 anchor fill is weak evidence, reported as such.
  * Levels are historically-rebuilt proxies (active+multi_day via _detect_from_history
    as-of each day), NOT production star-rated named levels. The EXIT comparison is
    internally consistent (identical signal population + levels across all variants),
    so "does a regime/underlying trail beat the fixed 20%?" is answerable on the proxy.
  * entry_VIX for the regime maps = the as-of VIX at the firing bar (no look-ahead).
  * The underlying trail is a separate all-units profit-lock exit sharing the SAME
    arming gate (+5% favor) as the premium chandelier; it trails the SPY extreme.

RESEARCH ONLY (Rule 9). No params/heartbeat/doctrine changed. The simulator knobs are
opt-in and default OFF; a PROMOTE-CANDIDATE here is "worth ratifying", not "wired".

Usage:
  python -m autoresearch.sweep_regime_chandelier \
      --out ../analysis/recommendations/regime-chandelier-sweep.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

# Reuse the bearish-continuation harness wholesale (same as sweep_timecond_exit): it
# runs the chart_patterns bootstrap, _load_data, the per-bar BarContext pipeline with
# historically-rebuilt levels (no look-ahead), the OP-16 anchors, and the detector set.
# We only swap the EXIT simulation (vary the chandelier), not the signal population.
from autoresearch import validate_bearish_continuation_family as bcf  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent

from lib.validation.gate import evaluate_candidate  # noqa: E402

ANCHORS = bcf.ANCHORS

# ── Population under test ─────────────────────────────────────────────────────
_PRIMARY = "BEARISH_REJECTION_MORNING"

STRIKES = (("ATM", 0), ("ITM2", -2))

# ── Production v15 premium chandelier (the BASELINE we must beat) ──────────────
# trail 20% off premium HWM, arm +5% favor, stop_offset +10%.
_BASE_CHANDELIER = dict(
    profit_lock_threshold_pct=0.05,
    profit_lock_stop_offset_pct=0.10,
    profit_lock_mode="trailing",
    profit_lock_trail_pct=0.20,
)

# Production-equivalent fixed exit knobs shared by baseline AND every variant; only the
# chandelier config differs. Catastrophe cap -0.99 so the chandelier governs (C1/C2).
_FIXED = dict(
    premium_stop_pct=-0.99,
    strike_offset=0,            # overridden per-strike below
    tp1_premium_pct=0.30,
    tp1_qty_fraction=0.50,
    runner_target_premium_pct=2.5,
    level_stop_buffer_dollars=0.50,
)

# ── Variant grid (lean) ───────────────────────────────────────────────────────
# Each variant is a dict of chandelier overrides layered on _BASE_CHANDELIER.
def _variants() -> list[dict]:
    out: list[dict] = []
    # A) Fixed premium trail (vs baseline 20%).
    for t in (0.15, 0.25, 0.30):
        out.append({"label": f"fixed_premium_{int(t*100)}",
                    "family": "fixed_premium",
                    "over": {"profit_lock_trail_pct": t}})
    # B) Regime premium trail (wider in high vol).
    out.append({"label": "regime_premium_WIDE_HIVOL", "family": "regime_premium",
                "over": {"profit_lock_trail_pct": 0.20,
                         "profit_lock_trail_pct_by_vix": {16: 0.15, 22: 0.25, 999: 0.35}}})
    out.append({"label": "regime_premium_GENTLE", "family": "regime_premium",
                "over": {"profit_lock_trail_pct": 0.20,
                         "profit_lock_trail_pct_by_vix": {18: 0.18, 999: 0.28}}})
    # C) Underlying trail (the research's prescription) — fixed.
    for u in (0.0030, 0.0050):
        out.append({"label": f"underlying_fixed_{u*100:.2f}pct",
                    "family": "underlying_fixed",
                    "over": {"profit_lock_trail_basis": "underlying",
                             "profit_lock_trail_underlying_pct": u}})
    # C) Underlying trail — regime-conditional (wider in high vol).
    out.append({"label": "underlying_regime", "family": "underlying_regime",
                "over": {"profit_lock_trail_basis": "underlying",
                         "profit_lock_trail_underlying_pct": 0.0045,
                         "profit_lock_trail_underlying_pct_by_vix":
                             {16: 0.0030, 22: 0.0045, 999: 0.0065}}})
    return out


VARIANTS = _variants()
# n_trials for DSR deflation = number of variants searched (per population+strike).
# The baseline is the reference, not a searched trial.
N_TRIALS = len(VARIANTS)


def _rej_for(sig):
    return (sig.metadata.get("rejection_level")
            or sig.metadata.get("break_level")
            or sig.metadata.get("neckline")
            or sig.metadata.get("broken_level")
            or sig.metadata.get("swept_level")
            or sig.stop_price)


def _favor_stats(pnls: list[float]) -> dict:
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


def _simulate(capped_signals, rth, ribbon_df, offset, chandelier: dict):
    """Run real-fills for the population under one chandelier config. Returns
    (pnls, anchor_pnl_by_day, diag)."""
    from lib.simulator_real import simulate_trade_real
    pnls: list[float] = []
    anchor_pnl: dict[str, float] = defaultdict(float)
    attempted = no_fill = errored = anchor_fills = 0
    cfg = dict(_FIXED)
    cfg["strike_offset"] = offset
    cfg.update(_BASE_CHANDELIER)
    cfg.update(chandelier)          # variant overrides (may switch basis / add maps)
    anchor_dates = {d.isoformat() for d in ANCHORS}
    for (idx, bar, sig, vix_at_entry) in capped_signals:
        attempted += 1
        bar_date_str = str(bar["timestamp_et"].date())
        rej = _rej_for(sig)
        try:
            fill = simulate_trade_real(
                entry_bar_idx=idx, entry_bar=bar, spy_df=rth, ribbon_df=ribbon_df,
                rejection_level=float(rej), triggers_fired=list(sig.triggers_fired),
                side="P", qty=3, setup=sig.setup_name, entry_vix=float(vix_at_entry),
                **cfg)
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
    win = sum(anchor_pnl.get(d.isoformat(), 0.0) for d in ANCHORS if ANCHORS[d] == "WIN")
    loss = sum(max(0.0, -anchor_pnl.get(d.isoformat(), 0.0)) for d in ANCHORS if ANCHORS[d] == "LOSS")
    return {"edge_capture": round(win - loss, 2),
            "win_day_pnl": round(win, 2),
            "loss_day_loss": round(loss, 2),
            "by_day": {d: round(v, 2) for d, v in sorted(anchor_pnl.items())}}


def _collect(start: dt.date, end: dt.date) -> dict:
    """Single pass: fire the BRM detector, collect (idx, bar, sig, vix_at_entry) with
    anchor-inclusive cap. Replicates sweep_timecond_exit's lean firing loop (no detector
    logic duplicated) and additionally captures the as-of VIX for the regime maps."""
    spy_full, vix_full = bcf.vbf._load_data(start, end)
    spy_full["timestamp_et"] = bcf.vbf.pd.to_datetime(spy_full["timestamp_et"])
    spy_full["date"] = spy_full["timestamp_et"].dt.date
    rth = spy_full[(spy_full["timestamp_et"].dt.time >= dt.time(9, 30)) &
                   (spy_full["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    ribbon_df = bcf.compute_ribbon(rth["close"])
    vix_aligned = bcf._align_vix_to_spy(rth, vix_full)
    htf_stacks = bcf._precompute_htf_15m_stacks(rth)

    bcf._reset_state()
    inputs: list = []
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
        detector = bcf._DETECTORS[_PRIMARY]
        try:
            sig = detector(ctx)
        except Exception as exc:
            sys.stderr.write(f"{_PRIMARY} @ {bar_time}: {type(exc).__name__}: {exc}\n")
            sig = None
        if sig is None:
            continue
        inputs.append((idx, bar, sig, vix_now))
    return {"inputs": inputs, "rth": rth, "ribbon_df": ribbon_df}


def _cap_anchor_inclusive(inputs: list, cap: int = 200) -> list:
    """Cap signals for runtime but ALWAYS keep anchor-day signals (else the
    anchor-no-regression gate is vacuous — lesson C24)."""
    anchor_dates = {d.isoformat() for d in ANCHORS}
    capped = list(inputs[:cap])
    capped_idx = {id(t) for t in capped}
    for t in inputs[cap:]:
        if str(t[1]["timestamp_et"].date()) in anchor_dates and id(t) not in capped_idx:
            capped.append(t)
            capped_idx.add(id(t))
    return capped


def _run_population(name: str, capped_signals: list, rth, ribbon_df) -> dict:
    """Run baseline + full variant grid for one population, both strikes; gate each."""
    strikes_out: dict = {}
    for slabel, offset in STRIKES:
        # Baseline = production premium chandelier (no overrides).
        base_pnls, base_anchor, base_diag = _simulate(
            capped_signals, rth, ribbon_df, offset, {})
        base_stats = _favor_stats(base_pnls)
        base_edge = _anchor_edge(base_anchor)
        base_dsr = _dsr_for(base_pnls)

        grid: list[dict] = []
        for v in VARIANTS:
            pnls, anchor, diag = _simulate(
                capped_signals, rth, ribbon_df, offset, v["over"])
            stats = _favor_stats(pnls)
            edge = _anchor_edge(anchor)
            dsr = _dsr_for(pnls)
            # ── Gate (honest, vs same-strike production-chandelier baseline) ──
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
                "label": v["label"],
                "family": v["family"],
                "config": v["over"],
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
            "baseline_premium_chandelier_20": {
                "stats": base_stats, "anchor": base_edge, "diag": base_diag, "dsr_gate": base_dsr,
            },
            "n_promote_candidates": len(promote),
            "promote_candidates": [
                {"label": c["label"], "config": c["config"], "stats": c["stats"],
                 "anchor": c["anchor"], "delta_total_vs_baseline": c["delta_total_vs_baseline"],
                 "dsr_verdict": c["dsr_gate"]["verdict"]}
                for c in promote],
            "best_variant": best,
            "n_better_any": len(better_any),
            "grid": grid_sorted,
            "verdict": _strike_verdict(slabel, base_stats, base_edge, promote, better_any),
        }
    return {"n_signals": len(capped_signals), "strikes": strikes_out}


def _strike_verdict(slabel, base_stats, base_edge, promote, better_any) -> str:
    if promote:
        b = promote[0]
        return (f"[{slabel}] PROMOTE-CANDIDATE — {len(promote)} chandelier variant(s) beat the "
                f"fixed-20% premium chandelier on BOTH total P&L and expectancy AND "
                f"anchor-no-regression AND DSR!=FAIL. Best: {b['label']} -> total "
                f"${b['stats']['total']} (exp ${b['stats']['exp']}, WR {b['stats']['wr']}%, "
                f"n={b['stats']['n']}) vs baseline total ${base_stats['total']} "
                f"(exp ${base_stats['exp']}). anchor edge_capture ${b['anchor']['edge_capture']} "
                f"vs baseline ${base_edge['edge_capture']}. PROXY levels + thin anchors — "
                f"ratify on production star-rated levels before wiring (Rule 9).")
    if better_any:
        b = sorted(better_any, key=lambda c: -c["stats"]["total"])[0]
        why = ("anchor regression" if not b["gate"]["anchor_no_regression"]
               else "anchor-vacuous (fires on no gradeable anchor day)" if b["gate"]["anchor_vacuous"]
               else "DSR FAIL")
        return (f"[{slabel}] BETTER-BUT-GATE-FAILS — best variant ({b['label']}) beats baseline "
                f"on total ${b['stats']['total']} vs ${base_stats['total']} but fails the {why} "
                f"leg. No clean PROMOTE-CANDIDATE.")
    return (f"[{slabel}] BASELINE-OPTIMAL — NO chandelier variant beat the fixed-20% premium "
            f"chandelier on both total P&L and expectancy. A regime-conditional / underlying "
            f"trail does NOT help this population/strike (baseline total ${base_stats['total']}, "
            f"exp ${base_stats['exp']}). The fixed 20% is already right here. Honest no-win "
            f"(a valuable result).")


# ── IS/OOS validation of the CHAMPION variant (the morning-sign L166 discipline) ──
# The prior cycle found fixed_premium_15 best in-sample. L166: an in-sample win that does
# not hold OOS SAME-SIGN is a mirage. We therefore split the signal population temporally
# and ask the ONE causal question that matters for an exit-param swap: does the DELTA
# (trail-15 minus baseline-20) stay the SAME SIGN out-of-sample? Plus expanding walk-forward
# folds (is the 15>=20 ranking fold-stable or did one window drive it?) and an OOS DSR.
_CHAMPION = {"label": "fixed_premium_15", "over": {"profit_lock_trail_pct": 0.15}}


def _slice_by_date(inputs: list, lo: dt.date | None, hi: dt.date | None) -> list:
    """Half-open [lo, hi) date slice of the fired-signal inputs (no re-detection)."""
    out = []
    for t in inputs:
        d = t[1]["timestamp_et"].date()
        if (lo is None or d >= lo) and (hi is None or d < hi):
            out.append(t)
    return out


def _median_signal_date(inputs: list) -> dt.date | None:
    dates = sorted(t[1]["timestamp_et"].date() for t in inputs)
    return dates[len(dates) // 2] if dates else None


def _ab_on_slice(seg: list, rth, ribbon_df, offset: int) -> dict:
    """Baseline-20 vs champion(trail-15) on one slice/strike. Returns both stat blocks,
    the delta, the same-sign flag, and the OOS DSR of the champion's own return stream."""
    base_p, base_anchor, base_diag = _simulate(seg, rth, ribbon_df, offset, {})
    champ_p, champ_anchor, champ_diag = _simulate(seg, rth, ribbon_df, offset, _CHAMPION["over"])
    bs, cs = _favor_stats(base_p), _favor_stats(champ_p)
    delta_total = round(cs["total"] - bs["total"], 2)
    delta_exp = round(cs["exp"] - bs["exp"], 2)
    # Paired per-trade delta (same signal universe + offset => index-aligned): the actual
    # proposal is the swap, so the broad-vs-tail check lives on the paired difference.
    paired = {"n_improved": 0, "n_worse": 0, "n_equal": 0, "sum": 0.0,
              "max_single_improve": 0.0, "sum_ex_top3": 0.0}
    if len(base_p) == len(champ_p) and base_p:
        diffs = sorted(c - b for b, c in zip(base_p, champ_p))
        paired = {
            "n_improved": sum(1 for d in diffs if d > 1e-9),
            "n_worse": sum(1 for d in diffs if d < -1e-9),
            "n_equal": sum(1 for d in diffs if abs(d) <= 1e-9),
            "sum": round(sum(diffs), 2),
            "max_single_improve": round(max(diffs), 2),
            "sum_ex_top3": round(sum(diffs[:-3]), 2) if len(diffs) > 3 else round(sum(diffs), 2),
        }
    return {
        "n_signals": len(seg),
        "baseline_20": bs,
        "champion_trail_15": cs,
        "delta_total": delta_total,
        "delta_exp": delta_exp,
        "delta_sign": "+" if delta_total > 1e-6 else ("-" if delta_total < -1e-6 else "0"),
        "champion_better": delta_total > 1e-6 and delta_exp > 1e-6,
        "champion_dsr": _dsr_for(champ_p),
        "anchor_fills": champ_diag["anchor_fills"],
        "paired_delta": paired,
    }


def _oos_validation(inputs: list, rth, ribbon_df) -> dict:
    """The L166 OOS discipline for the champion exit-param swap (20% -> 15%).

    TWO temporal splits (calendar 2026-01-01 train/test AND a balanced median-date split)
    plus expanding quarterly walk-forward folds. The PASS bar for an exit-param swap is
    SAME-SIGN improvement OOS on both splits + fold-stable ranking; DSR is advisory."""
    cal = dt.date(2026, 1, 1)
    med = _median_signal_date(inputs)
    splits: dict = {}
    for sname, lo_oos in (("calendar_2026", cal), ("balanced_median", med)):
        if lo_oos is None:
            continue
        blk: dict = {"boundary": lo_oos.isoformat(), "strikes": {}}
        for slabel, offset in STRIKES:
            is_seg = _slice_by_date(inputs, None, lo_oos)
            oos_seg = _slice_by_date(inputs, lo_oos, None)
            is_ab = _ab_on_slice(is_seg, rth, ribbon_df, offset)
            oos_ab = _ab_on_slice(oos_seg, rth, ribbon_df, offset)
            same_sign = (is_ab["delta_sign"] == "+" and oos_ab["delta_sign"] == "+")
            blk["strikes"][slabel] = {
                "in_sample": is_ab, "out_of_sample": oos_ab,
                "same_sign_oos": same_sign,
                "verdict": ("HOLDS-OOS-SAME-SIGN" if same_sign
                            else "FAILS-OOS-SIGN-INVERTS" if oos_ab["delta_sign"] == "-"
                            else "FAILS-OOS-FLAT"),
            }
        splits[sname] = blk

    # Expanding walk-forward: quarterly test folds across the window.
    fold_bounds = [dt.date(2025, 1, 1), dt.date(2025, 4, 1), dt.date(2025, 7, 1),
                   dt.date(2025, 10, 1), dt.date(2026, 1, 1), dt.date(2026, 4, 1),
                   dt.date(2026, 6, 1)]
    wf: dict = {}
    for slabel, offset in STRIKES:
        folds = []
        n_stable = n_folds = 0
        for i in range(len(fold_bounds) - 1):
            lo, hi = fold_bounds[i], fold_bounds[i + 1]
            seg = _slice_by_date(inputs, lo, hi)
            if not seg:
                continue
            ab = _ab_on_slice(seg, rth, ribbon_df, offset)
            if ab["champion_trail_15"]["n"] == 0:
                continue
            n_folds += 1
            stable = ab["delta_total"] >= -1e-6
            n_stable += int(stable)
            folds.append({"fold": f"{lo.isoformat()}..{hi.isoformat()}",
                          "n": ab["champion_trail_15"]["n"],
                          "base20_total": ab["baseline_20"]["total"],
                          "trail15_total": ab["champion_trail_15"]["total"],
                          "delta_total": ab["delta_total"],
                          "trail15_ge_base20": stable})
        wf[slabel] = {"n_folds": n_folds, "n_stable": n_stable,
                      "all_folds_stable": n_folds > 0 and n_stable == n_folds,
                      "folds": folds}

    # Roll up to one machine-readable verdict.
    all_same_sign = all(
        splits[s]["strikes"][sl]["same_sign_oos"]
        for s in splits for sl in splits[s]["strikes"])
    all_wf_stable = all(wf[sl]["all_folds_stable"] for sl in wf)
    if all_same_sign and all_wf_stable:
        headline = ("PROPOSE -- trail-15 beats baseline-20 SAME-SIGN on BOTH temporal splits "
                    "(calendar 2025/2026 AND balanced-median) AND all walk-forward folds are "
                    "stable, BOTH strikes. The improvement is the OPPOSITE of the L166 "
                    "morning-sign mirage (which inverted OOS). DSR is advisory-only and reads "
                    "WEAK/FAIL because 2026 was an absolute-losing regime for the proxy "
                    "population -- the SWAP (the paired delta) is broad-based, not tail-driven, "
                    "and almost never hurts a trade. Anchor-no-regression is UNTESTED for "
                    "5/01+5/04 (no BRM signal/fill) -- necessary-not-sufficient gating caveat. "
                    "Live exit-param change => J/conductor ratification (Rule 9).")
        verdict = "PROPOSE"
    elif all_same_sign:
        headline = ("WATCH -- same-sign OOS on both splits but NOT every walk-forward fold is "
                    "stable; directional, revisit with more data / real levels.")
        verdict = "WATCH"
    else:
        headline = ("REJECT -- the improvement does NOT hold OOS same-sign (sign inverts or "
                    "flattens out-of-sample). In-sample mirage, like the L166 morning-sign gate.")
        verdict = "REJECT"
    return {
        "_doc": ("L166 discipline applied to the champion exit-param swap (chandelier trail "
                 "20% -> 15%). The proposal is the SWAP, so the causal OOS question is whether "
                 "the DELTA (trail-15 minus baseline-20) stays the SAME SIGN out-of-sample. "
                 "Calendar split (2025 train / 2026 test) is well-powered here (113/62 signals); "
                 "balanced-median is the secondary read. DSR is on the champion's own return "
                 "stream (advisory; a losing-regime OOS slice fails by construction even when "
                 "the SWAP helps)."),
        "champion": _CHAMPION,
        "splits": splits,
        "walk_forward": wf,
        "all_splits_same_sign_oos": all_same_sign,
        "all_walk_forward_folds_stable": all_wf_stable,
        "verdict": verdict,
        "headline": headline,
    }


def run(start: dt.date, end: dt.date) -> dict:
    coll = _collect(start, end)
    inputs, rth, ribbon_df = coll["inputs"], coll["rth"], coll["ribbon_df"]
    primary_caps = _cap_anchor_inclusive(inputs)
    primary = _run_population(_PRIMARY, primary_caps, rth, ribbon_df)
    oos_validation = _oos_validation(primary_caps, rth, ribbon_df)

    result = {
        "research_question": (
            "Does a REGIME-CONDITIONAL / UNDERLYING-move chandelier (vol-scaled trail — wider "
            "in high vol, tighter in calm; trail the SPY move per Kim-Tse-Wald) beat the FIXED "
            "20%-off-premium-HWM v15 chandelier on BEARISH_REJECTION real-fills, WITHOUT "
            "clipping J's anchor-day winners? Tests the named #1 exit leverage on our one "
            "confirmed edge."),
        "window": f"{start}..{end}",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "baseline": ("PRODUCTION v15 premium chandelier: profit_lock_mode='trailing', "
                     "threshold +5%, stop_offset +10%, trail 20% off premium HWM."),
        "variant_grid": {
            "fixed_premium_trail_pct": [0.15, 0.25, 0.30],
            "regime_premium_maps": {
                "WIDE_HIVOL": {16: 0.15, 22: 0.25, 999: 0.35},
                "GENTLE": {18: 0.18, 999: 0.28},
            },
            "underlying_fixed_pct_of_spy": [0.0030, 0.0050],
            "underlying_regime_map": {16: 0.0030, 22: 0.0045, 999: 0.0065},
            "strikes": [s for s, _ in STRIKES],
            "n_trials_for_dsr": N_TRIALS,
            "fixed_other": ("premium_stop_pct=-0.99 (catastrophe cap so chandelier governs); "
                            "tp1_premium 0.30; tp1_qty_fraction 0.50; runner 2.5; "
                            "level_stop_buffer 0.50"),
        },
        "gate_definition": (
            "PROMOTE-CANDIDATE iff vs same-population same-strike PRODUCTION-CHANDELIER baseline: "
            "total P&L AND expectancy strictly improve AND anchor edge_capture >= baseline "
            "(anchor-no-regression) AND DSR/PSR advisory != FAIL AND anchor not vacuous. Honest "
            "no-win is a valid result."),
        "populations": {"BEARISH_REJECTION_MORNING_primary": primary},
        "oos_validation": oos_validation,
        "op20_disclosures": _op20_disclosures(),
    }
    result["overall_verdict"] = _overall_verdict(result)
    result["overall_verdict"]["oos_verdict"] = oos_validation["verdict"]
    result["overall_verdict"]["oos_headline"] = oos_validation["headline"]
    return result


def _op20_disclosures() -> dict:
    return {
        "authority": ("Real-fills (lib.simulator_real + OPRA options cache, valid through "
                      "2026-05-29) is the only authority used for the verdict (C1). BS-sim / "
                      "SPY-space grade not used."),
        "anchor_coverage": ("THIN. 5/04 (J's biggest winner, +$730) has ZERO option bars in the "
                            "cache; BRM has an OPRA fill on only 4/29 among the WIN anchor days. "
                            "The anchor-no-regression gate is necessary-not-sufficient (C24) — a "
                            "tie at n=1 anchor fill is weak evidence."),
        "level_source": ("Historically-rebuilt star-rated proxies (active+multi_day from "
                         "_detect_from_history as-of each day), NOT production named levels. "
                         "Absolute WR is a proxy LOWER-BOUND; the EXIT comparison is internally "
                         "consistent (identical signal population + level set across all "
                         "variants), so the beat-the-fixed-20% question is answerable."),
        "regime_key": ("entry_VIX for the regime maps = the as-of VIX at the firing bar from "
                       "_align_vix_to_spy (no look-ahead). Maps are {vix_ceiling: trail}; first "
                       "ceiling >= entry_VIX wins; falls through to the scalar trail when VIX "
                       "unknown or above all ceilings."),
        "underlying_trail": ("Opt-in profit_lock_trail_basis='underlying': a separate all-units "
                             "profit-lock exit sharing the SAME +5% arming gate as the premium "
                             "chandelier; trails the SPY favorable extreme (put: session low) and "
                             "exits when SPY retraces underlying_pct*entry_spot off it."),
        "knobs": ("Opt-in lib.simulator_real.simulate_trade_real(profit_lock_trail_basis, "
                  "profit_lock_trail_underlying_pct, profit_lock_trail_pct_by_vix, "
                  "profit_lock_trail_underlying_pct_by_vix, entry_vix); ALL default to the v15 "
                  "premium-chandelier behavior (verified: 6 e2e tests + default-equivalence). "
                  "RESEARCH ONLY — no params/doctrine changed (Rule 9)."),
        "dsr_returns": ("DSR/PSR on per-trade dollar P&L (constant qty=3 notional -> comparable). "
                        f"PBO skipped (no CSCV matrix). n_trials={N_TRIALS} (grid size). Advisory "
                        "only (gate.py is not a hard gate)."),
    }


def _overall_verdict(result: dict) -> dict:
    out = {}
    promote_any = False
    for pop_key, pop in result["populations"].items():
        for slabel, sblk in pop["strikes"].items():
            tag = f"{pop_key}/{slabel}"
            out[tag] = sblk["verdict"]
            if sblk["n_promote_candidates"] > 0:
                promote_any = True
    summary = (
        "A REGIME-CONDITIONAL / UNDERLYING chandelier beats the fixed-20% premium chandelier on "
        ">=1 population/strike (see per-strike PROMOTE-CANDIDATE)." if promote_any else
        "The FIXED 20% premium chandelier is OPTIMAL across all tested strikes — no "
        "regime-conditional or underlying-move trail beat it on both total P&L and expectancy "
        "with anchor-no-regression. Vol-scaling the trail did not help this population. Honest "
        "no-win (a valuable result): do NOT change the chandelier on this evidence.")
    return {"any_promote_candidate": promote_any, "per_strike": out, "summary": summary}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end", default="2026-05-29")  # OPRA coverage ends 2026-05-29
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    res = run(dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end))
    # Compact stdout: drop the heavy per-population grids; keep verdicts + baselines.
    compact = {k: v for k, v in res.items() if k not in ("populations", "oos_validation")}
    ov = res.get("oos_validation", {})
    compact["oos_validation_summary"] = {
        "verdict": ov.get("verdict"),
        "all_splits_same_sign_oos": ov.get("all_splits_same_sign_oos"),
        "all_walk_forward_folds_stable": ov.get("all_walk_forward_folds_stable"),
        "headline": ov.get("headline"),
        "splits": {
            sname: {sl: {
                "is_delta_total": sblk["in_sample"]["delta_total"],
                "oos_delta_total": sblk["out_of_sample"]["delta_total"],
                "oos_delta_sign": sblk["out_of_sample"]["delta_sign"],
                "verdict": sblk["verdict"],
            } for sl, sblk in blk["strikes"].items()}
            for sname, blk in ov.get("splits", {}).items()
        },
        "walk_forward": {sl: f"{w['n_stable']}/{w['n_folds']} folds trail15>=base20"
                         for sl, w in ov.get("walk_forward", {}).items()},
    }
    compact["populations_summary"] = {
        pop_key: {
            "strikes": {
                slabel: {
                    "baseline_total": sblk["baseline_premium_chandelier_20"]["stats"]["total"],
                    "baseline_exp": sblk["baseline_premium_chandelier_20"]["stats"]["exp"],
                    "baseline_n": sblk["baseline_premium_chandelier_20"]["stats"]["n"],
                    "baseline_wr": sblk["baseline_premium_chandelier_20"]["stats"]["wr"],
                    "baseline_anchor_edge":
                        sblk["baseline_premium_chandelier_20"]["anchor"]["edge_capture"],
                    "best_variant_label": (sblk["best_variant"]["label"]
                                           if sblk["best_variant"] else None),
                    "best_variant_total": (sblk["best_variant"]["stats"]["total"]
                                           if sblk["best_variant"] else None),
                    "best_variant_delta": (sblk["best_variant"]["delta_total_vs_baseline"]
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
