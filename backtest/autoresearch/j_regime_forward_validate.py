"""C-angle PART 2 — forward-validate the J-data regime hypotheses on OUR fills.

J's Webull data (j_regime_split.py) said his edge is:
  C1  concentrated in the MID VIX band (16-19) — both tails (low AND high) bleed,
      and VIX *level* alone barely discriminates winners from losers (24.65 vs 25.01).
  C2  concentrated on TREND days, dead on CHOP/range days (range bull +$13/PF1.30 vs
      chop bear -$78/PF0.35) — the single most robust, decent-N cell.

The prior harness (vwap_pullback_regime_gate.py + vwap_pullback_gate_own_oos.py)
already swept ONE-SIDED VIX gates (vix_lt_X), vix_falling, ADX, range_ratio,
realized-vol on the VWAP-continuation real fills and found **0 winners** (no gate
makes ALL sub-windows OOS-positive — the bimodality killer). It also found the bad
months were LOW-VIX / low-realized-vol / low-morning-move (the OPPOSITE of a naive
low-VIX gate).

THIS adds the gate families J's combined C1+C2 point to that were NOT isolated:
  G1  TWO-SIDED mid-VIX band  (VIX_floor <= vix < VIX_ceil)  — J's mid-band finding.
  G2  realized-vol FLOOR  (rvol_bps >= X) — skip the dead quiet-tape summer (the
      bad-month signature), the inverse of the failed `vix_lt_X`.
  G3  morning-move FLOOR  (|open->trigger| >= X) — trend-day participation floor.
  G4  combined: vol-floor AND trend-day — the C1∩C2 intersection.

Each gate is evaluated on BOTH exit configs (chart_stop_only=live, -8pct=scorecard),
with: n_kept, IS/OOS exp, 4 contiguous sub-windows (all-positive = bimodality killed),
OOS sign stability, both-sides-positive, DSR, drop-top5 robustness, AND — for any gate
that passes the winner bar — its OWN OOS (threshold derived IS-only, applied unseen
OOS). A gate curve-fit to the bad window fails that.

CAUSAL: reuses build_gated_trades verbatim (every feature read from bars[0..trigger];
VIX aligned at trigger). PROPOSE-ONLY (Rule 9): writes a scorecard JSON, no params /
heartbeat / order path. Pure-Python, $0, deterministic.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]          # ...\42\backtest
PROJECT = REPO.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from autoresearch.infinite_ammo_discovery import load_spy, align_vix, build_day_contexts  # noqa: E402
from autoresearch.vwap_pullback_regime_gate import (  # noqa: E402 — reuse verbatim
    build_gated_trades, EXIT_CONFIGS, LIVE_EXIT_KEY, KNOWN_BAD_MONTHS,
    SPY_CSV, VIX_CSV, OOS_SPLIT_FRAC, N_TRIALS_DSR,
)
from lib.ribbon import compute_ribbon                 # noqa: E402
from lib.validation.gate import evaluate_candidate    # noqa: E402

OUT = PROJECT / "analysis" / "recommendations" / "j-regime-vwap-vix-gate.json"

# Doctrine bands (regime_book). The mid band is [LOW_CEIL, HIGH_VOL_FLOOR).
VIX_LOW_CEIL = 16.0
VIX_HIGH_VOL_FLOOR = 19.0

MIN_KEPT = 35          # same as the prior winner bar
MIN_RETENTION = 0.40
N_SUBWINDOWS = 4


# ─────────────────────────────────────────────────────────────────────────────
def _exp(pnls):
    return float(np.mean(pnls)) if pnls else 0.0


def _subwindows(trades):
    """4 contiguous time-ordered sub-windows; return per-window mean pnl + all-positive."""
    ts = sorted(trades, key=lambda t: (t.date, t.bar_idx))
    if len(ts) < N_SUBWINDOWS:
        return [], False, len(ts)
    means = []
    n = len(ts)
    for k in range(N_SUBWINDOWS):
        a = k * n // N_SUBWINDOWS
        b = (k + 1) * n // N_SUBWINDOWS
        chunk = ts[a:b]
        means.append(round(_exp([t.pnl for t in chunk]), 2) if chunk else 0.0)
    n_hurt = sum(1 for m in means if m <= 0)
    return means, (n_hurt == 0), n_hurt


def _metrics(trades, all_trades, oos_cut_idx):
    """Full metric block for a gated subset. oos_cut_idx is index into the
    time-ordered ALL-trades list defining the IS/OOS boundary (shared across gates,
    chronological — never per-gate)."""
    if not trades:
        return {"n": 0}
    pnls = [t.pnl for t in trades]
    ts = sorted(trades, key=lambda t: (t.date, t.bar_idx))
    # chronological IS/OOS using the GLOBAL cut date (so gates are comparable)
    all_sorted = sorted(all_trades, key=lambda t: (t.date, t.bar_idx))
    cut_date = all_sorted[oos_cut_idx].date
    is_t = [t for t in ts if t.date < cut_date]
    oos_t = [t for t in ts if t.date >= cut_date]
    is_exp = round(_exp([t.pnl for t in is_t]), 2)
    oos_exp = round(_exp([t.pnl for t in oos_t]), 2)
    means, all_pos, n_hurt = _subwindows(trades)
    # both sides positive
    c = [t.pnl for t in trades if t.side == "C"]
    p = [t.pnl for t in trades if t.side == "P"]
    both_pos = (_exp(c) > 0 if c else False) and (_exp(p) > 0 if p else False)
    # drop-top5 robustness
    srt = sorted(pnls, reverse=True)
    drop5 = round(_exp(srt[5:]), 2) if len(srt) > 5 else None
    # DSR via existing harness (returns as pct-of-premium series)
    rets = [t.pct for t in trades]
    try:
        gr = evaluate_candidate(rets, n_trials=N_TRIALS_DSR)
        dsr_verdict = gr.verdict
    except Exception as e:  # pragma: no cover - defensive
        dsr_verdict = f"ERR:{e}"
    wins = sum(1 for x in pnls if x > 0)
    # per-month positivity over OOS
    oos_months = {}
    for t in oos_t:
        oos_months.setdefault(t.month, []).append(t.pnl)
    oos_month_detail = {m: {"n": len(v), "exp": round(_exp(v), 2),
                            "positive": _exp(v) > 0} for m, v in sorted(oos_months.items())}
    return {
        "n": len(trades),
        "wins": wins,
        "wr_pct": round(100.0 * wins / len(trades), 1),
        "exp_dollar": round(_exp(pnls), 2),
        "total_dollar": round(sum(pnls), 1),
        "is_n": len(is_t), "oos_n": len(oos_t),
        "is_exp_dollar": is_exp, "oos_exp_dollar": oos_exp,
        "oos_sign_stable": (is_exp > 0 and oos_exp > 0) or (is_exp <= 0 and oos_exp <= 0)
                           if is_t and oos_t else False,
        "oos_positive": oos_exp > 0,
        "sub_window_means": means,
        "all_sub_windows_positive": all_pos,
        "n_sub_hurt": n_hurt,
        "both_dirs_positive": both_pos,
        "drop_top5_mean_dollar": drop5,
        "robust_to_outliers": (drop5 is not None and drop5 > 0),
        "dsr_verdict": dsr_verdict,
        "n_bad_month_trades_kept": sum(1 for t in trades if t.month in KNOWN_BAD_MONTHS),
        "oos_months": oos_month_detail,
    }


def _is_winner(m, n_total):
    """The bimodality-killer winner bar (same spirit as prior harness)."""
    if m.get("n", 0) < MIN_KEPT:
        return False, "n_kept<35"
    if m["n"] / n_total < MIN_RETENTION:
        return False, "retention<0.40"
    if not m["all_sub_windows_positive"]:
        return False, "bimodal(sub-window<=0)"
    if not m["oos_sign_stable"]:
        return False, "oos_sign_unstable"
    if not m["both_dirs_positive"]:
        return False, "one_side_negative"
    if not m["robust_to_outliers"]:
        return False, "fails_drop_top5"
    if m["dsr_verdict"] == "FAIL":
        return False, "dsr_fail"
    return True, "WINNER"


def _own_oos(all_trades, oos_cut_idx, feature, grid, direction):
    """Anti-overfit: derive best threshold on IS-only, apply UNSEEN to OOS.

    feature: attr name on GatedTrade (e.g. 'realized_vol_bps').
    direction: '>=' (floor) or '<' (ceiling).
    grid: candidate thresholds.
    """
    all_sorted = sorted(all_trades, key=lambda t: (t.date, t.bar_idx))
    cut_date = all_sorted[oos_cut_idx].date
    is_all = [t for t in all_trades if t.date < cut_date]
    oos_all = [t for t in all_trades if t.date >= cut_date]

    def keep(t, thr):
        v = getattr(t, feature)
        if v is None:
            return False
        return v >= thr if direction == ">=" else v < thr

    is_grid = []
    best = None
    for thr in grid:
        kept = [t for t in is_all if keep(t, thr)]
        if len(kept) < 15:
            is_grid.append({"thr": thr, "is_n": len(kept), "is_exp": None, "skipped": "n<15"})
            continue
        e = round(_exp([t.pnl for t in kept]), 2)
        is_grid.append({"thr": thr, "is_n": len(kept), "is_exp": e})
        if best is None or e > best[1]:
            best = (thr, e, len(kept))
    if best is None:
        return {"is_grid": is_grid, "verdict": "NO_VIABLE_IS_THRESHOLD"}
    thr_pick = best[0]
    oos_kept = [t for t in oos_all if keep(t, thr_pick)]
    oos_exp = round(_exp([t.pnl for t in oos_kept]), 2) if oos_kept else None
    full = [t for t in all_trades if keep(t, thr_pick)]
    means, all_pos, n_hurt = _subwindows(full)
    return {
        "feature": feature, "direction": direction,
        "is_grid": is_grid,
        "is_picked_threshold": thr_pick, "is_n": best[2], "is_exp_dollar": best[1],
        "oos_n_at_is_threshold": len(oos_kept),
        "oos_exp_dollar_at_is_threshold": oos_exp,
        "oos_generalizes": (oos_exp is not None and oos_exp > 0),
        "full_series_at_is_threshold": {
            "n": len(full), "exp_dollar": round(_exp([t.pnl for t in full]), 2),
            "sub_window_means": means, "all_sub_windows_positive": all_pos,
            "n_sub_hurt": n_hurt,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
def gate_families():
    """J-data-motivated gates NOT isolated by the prior sweep. Each: (name, pred, desc)."""
    fams = {}
    # G1 two-sided mid-VIX band (J's mid-band finding) — floor AND ceiling
    for lo, hi in [(16, 19), (15, 20), (16, 22), (14, 19)]:
        fams[f"vix_band_{lo}_{hi}"] = (
            lambda t, lo=lo, hi=hi: (t.vix is not None and lo <= t.vix < hi),
            f"two-sided VIX band [{lo}, {hi}) — J mid-band; live: vix_cache at trigger",
        )
    # G2 realized-vol floor (inverse of failed low-VIX; skip dead quiet tape)
    for thr in (5, 6, 7, 8, 9, 10):
        fams[f"rvol_ge_{thr}"] = (
            lambda t, thr=thr: (t.realized_vol_bps is not None and t.realized_vol_bps >= thr),
            f"realized-vol floor >= {thr}bps — skip quiet-tape (bad-month signature); "
            f"live: stdev of session 5m log-rets to date",
        )
    # G3 morning-move floor (trend-day participation)
    for thr in (0.002, 0.003, 0.004, 0.005):
        fams[f"mmove_ge_{thr}"] = (
            lambda t, thr=thr: (t.morning_move_pct is not None and t.morning_move_pct >= thr),
            f"morning-move floor >= {thr} (|open->trigger|) — trend-day floor; "
            f"live: |session open -> current close|",
        )
    # G4 combined C1∩C2: vol-floor AND not-high-VIX (calm-but-not-dead)
    for rv, hi in [(6, 22), (7, 22), (6, 19)]:
        fams[f"rvol_ge_{rv}_and_vix_lt_{hi}"] = (
            lambda t, rv=rv, hi=hi: (t.realized_vol_bps is not None and t.realized_vol_bps >= rv
                                     and t.vix is not None and t.vix < hi),
            f"rvol>={rv}bps AND vix<{hi} (calm-but-participating); live: both computable",
        )
    return fams


def run():
    spy_df = load_spy(str(SPY_CSV))
    vix = align_vix(spy_df, str(VIX_CSV))
    days = build_day_contexts(spy_df)
    ribbon_df = compute_ribbon(pd.Series(spy_df["close"].values))

    result = {
        "_generated": dt.datetime.now(dt.timezone.utc).isoformat(),
        "_script": "backtest/autoresearch/j_regime_forward_validate.py",
        "_purpose": "Forward-validate J's C1(mid-VIX)+C2(trend/vol) regime hypotheses on OUR "
                    "VWAP-continuation real OPRA fills. Test the gate families NOT isolated by "
                    "vwap_pullback_regime_gate.py: two-sided mid-VIX band, realized-vol floor, "
                    "morning-move floor, and the C1∩C2 combo. Bimodality-killer winner bar + "
                    "each winner's OWN OOS.",
        "_prior_result": "vwap_pullback_regime_gate.json found 0 winners across one-sided VIX / "
                         "vix_falling / ADX / range_ratio / rvol gates (none make all 4 sub-windows "
                         "OOS-positive). Bad months were LOW-vix/low-rvol (opposite of low-VIX gate).",
        "_causality": "reuses build_gated_trades verbatim (features from bars[0..trigger]; VIX at "
                      "trigger). chronological shared IS/OOS cut. PROPOSE-ONLY (Rule 9).",
        "data": {"spy": SPY_CSV.name, "vix": VIX_CSV.name, "days": len(days)},
        "by_exit_config": {},
    }

    fams = gate_families()
    for cfg_name, prem in EXIT_CONFIGS.items():
        trades = build_gated_trades(spy_df, ribbon_df, vix, days, premium_stop_pct=prem)
        n_total = len(trades)
        all_sorted = sorted(trades, key=lambda t: (t.date, t.bar_idx))
        oos_cut_idx = int(n_total * OOS_SPLIT_FRAC)
        baseline = _metrics(trades, trades, oos_cut_idx)

        gate_results = []
        winners = []
        for name, (pred, desc) in fams.items():
            kept = [t for t in trades if pred(t)]
            m = _metrics(kept, trades, oos_cut_idx)
            m["gate"] = name
            m["desc"] = desc
            m["retention"] = round(len(kept) / n_total, 3) if n_total else 0.0
            won, why = _is_winner(m, n_total)
            m["IS_WINNER"] = won
            m["winner_fail_reason"] = None if won else why
            gate_results.append(m)
            if won:
                winners.append(name)
        gate_results.sort(key=lambda r: (r.get("oos_exp_dollar") or -1e9), reverse=True)

        # own-OOS for the volatility-floor + morning-move families (the live-computable
        # continuous knobs) regardless of winner status — the anti-overfit evidence.
        own_oos = {
            "rvol_floor": _own_oos(trades, oos_cut_idx, "realized_vol_bps", [5, 6, 7, 8, 9, 10], ">="),
            "mmove_floor": _own_oos(trades, oos_cut_idx, "morning_move_pct",
                                    [0.002, 0.003, 0.004, 0.005], ">="),
        }

        result["by_exit_config"][cfg_name] = {
            "premium_stop_pct": prem,
            "n_trades": n_total,
            "oos_cut_date": all_sorted[oos_cut_idx].date if n_total else None,
            "baseline_no_gate": baseline,
            "gate_sweep": gate_results,
            "winners": winners,
            "winner_count": len(winners),
            "own_oos": own_oos,
        }

    OUT.write_text(json.dumps(result, indent=2))
    print("WROTE", OUT)

    # digest
    for cfg, blk in result["by_exit_config"].items():
        b = blk["baseline_no_gate"]
        print(f"\n=== {cfg} (prem={blk['premium_stop_pct']}) baseline n={b['n']} "
              f"exp=${b['exp_dollar']} subwins={b['sub_window_means']} "
              f"allpos={b['all_sub_windows_positive']} ===")
        print(f"  WINNERS: {blk['winners'] or 'NONE'}")
        print(f"  {'gate':26s} nkeep ret  exp    oos    allsub oossign drop5 dsr   winner")
        for g in blk["gate_sweep"][:14]:
            print(f"  {g['gate']:26s} {g.get('n',0):3d}  {g.get('retention',0):.2f} "
                  f"{str(g.get('exp_dollar'))[:6]:>6s} {str(g.get('oos_exp_dollar'))[:6]:>6s} "
                  f"{str(g.get('all_sub_windows_positive'))[0]}      "
                  f"{str(g.get('oos_sign_stable'))[0]}       "
                  f"{str(g.get('robust_to_outliers'))[0]}     {str(g.get('dsr_verdict'))[:4]:4s}  "
                  f"{g.get('winner_fail_reason') or 'WIN'}")
        oo = blk["own_oos"]["rvol_floor"]
        print(f"  own-OOS rvol_floor: IS pick={oo.get('is_picked_threshold')} "
              f"IS exp=${oo.get('is_exp_dollar')} -> OOS exp=${oo.get('oos_exp_dollar_at_is_threshold')} "
              f"generalizes={oo.get('oos_generalizes')} "
              f"full_allsubpos={oo.get('full_series_at_is_threshold',{}).get('all_sub_windows_positive')}")


if __name__ == "__main__":
    run()
