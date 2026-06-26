"""_vwap_pullback_edge_verify — is vwap_pullback (H4) a genuine 4th 0DTE edge, or a
RE-SKIN of #1 vwap_continuation (the anchored-VWAP trap, L174)?

SAFE research (Sunday, $0, READ-ONLY). Reuses BYTE-FOR-BYTE:
  * detector: infinite_ammo_discovery.detect_vwap_pullback (H4)
  * #1/#2/#4 detectors: the EXACT calls recency_check.detect_all uses
  * overlap method: _b8_anchored_vwap (day-overlap = shared_days / candidate_days; OVERLAP_MAX=0.80)
  * 0DTE real-fills metrics + the full structural/L171/L172/L173 gate machinery: _dte_expansion_sim
    (run_cell with dte=0 + metrics + clears_bar) and lib.truncation_guard + the survey's dte_null
  * recency window: recency_check (merged master+recent frame, last ~25 trading days)

ANSWERS:
  1. INDEPENDENCE (decisive, L174): day-overlap (Jaccard) + same-side day-overlap of vwap_pullback's
     signal days vs #1 (and #2, #4). >=0.80 same-side -> RESKIN_OF_1; <0.80 -> independent.
  2. FULL 11-gate bar at its best 0DTE tier (ITM-2/-0.08), re-run from scratch (don't trust prose).
  3. RECENCY: score the freshest ~25 trading days (real OPRA fills) — RED / holding?
  4. INCREMENTAL value over the #1+#2+#4 book (daily-P&L correlation + does adding it improve the book).

No edits to detectors/params/risk_gate/orchestrator/heartbeat. No orders. Writes a JSON scorecard.
Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_vwap_pullback_edge_verify.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402

# ── byte-for-byte detector + the 0DTE gate machinery ───────────────────────────
import _dte_expansion_sim as sim  # noqa: E402  (run_cell/metrics/clears_bar/simulate_dte_trade/_load_spy_vix)
from autoresearch.infinite_ammo_discovery import detect_vwap_pullback, build_day_contexts  # noqa: E402
from lib.truncation_guard import is_truncation_artifact  # noqa: E402
from _dte_library_survey import dte_null  # noqa: E402  (the survey's DTE-aware random-entry null)

# ── #1/#2/#4 detectors via the SAME calls recency_check uses (no drift) ─────────
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy, _align_vix, detect_signals as detect_vwap_continuation,
)
from autoresearch._sub_struct_vwap_reclaim_failed_break import (  # noqa: E402
    detect_signals as detect_reclaim_failed_break,
)
from autoresearch._b5_vix_regime_dayside import (  # noqa: E402
    causal_vix_median, vix_slope, detect_opt_signals as detect_vix_regime_dayside,
    _swing_stop, VIX_MEDIAN_BARS, VIX_SLOPE_BARS,
)
from autoresearch.infinite_ammo_discovery import Signal  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

DATA = REPO / "data"
DATA_COVERAGE = ROOT / "automation" / "state" / "data-coverage.json"
B5_SCORECARD = ROOT / "analysis" / "recommendations" / "b5-vix-regime-dayside.json"
OUT = ROOT / "analysis" / "recommendations" / "VWAP-PULLBACK-EDGE-VERIFY.json"

OVERLAP_MAX = 0.80          # _b8_anchored_vwap canonical independence threshold (L174)
BEST_TIER_OFFSET = -2       # ITM-2 (survey best 0DTE cell)
BEST_TIER_STOP = -0.08      # survey best 0DTE stop
RECENCY_LOOKBACK = 25       # recency_check canonical window
RECENCY_FLOOR = 10          # recency_check CONFIRM n-floor
PREMIUM_STOP_PCT = -0.08
MAX_STRIKE_STEPS = 4
QTY = 3
OOS_YEAR = sim.OOS_YEAR


# ════════════════════════════════════════════════════════════════════════════════
# helpers — signal-day extraction (the overlap currency)
# ════════════════════════════════════════════════════════════════════════════════
def signal_day_sides(signals, spy) -> dict[dt.date, set]:
    """date -> {sides fired that day}. (One signal/day for these detectors, but be safe.)"""
    out: dict[dt.date, set] = defaultdict(set)
    for s in signals:
        d = spy.iloc[s.bar_idx]["timestamp_et"].date()
        out[d].add(s.side)
    return out


def overlap_metrics(cand: dict, other: dict) -> dict:
    """Day-overlap (b8 convention: shared/candidate) + Jaccard + SAME-SIDE day-overlap."""
    cd, od = set(cand), set(other)
    shared = cd & od
    union = cd | od
    same_side = {d for d in shared if cand[d] & other[d]}
    day_overlap = round(len(shared) / len(cd), 3) if cd else 0.0       # b8 directional (shared/cand)
    jaccard = round(len(shared) / len(union), 3) if union else 0.0
    same_side_overlap = round(len(same_side) / len(cd), 3) if cd else 0.0  # same-side fraction of cand days
    return {
        "candidate_days": len(cd), "other_days": len(od),
        "shared_days": len(shared), "same_side_shared_days": len(same_side),
        "day_overlap_shared_over_candidate": day_overlap,
        "jaccard_shared_over_union": jaccard,
        "same_side_day_overlap": same_side_overlap,
        "reskin_by_same_side": bool(same_side_overlap >= OVERLAP_MAX),
        "reskin_by_day_overlap": bool(day_overlap >= OVERLAP_MAX),
    }


# ════════════════════════════════════════════════════════════════════════════════
# #1/#2/#4 detect (the recency_check.detect_all calls, verbatim) on a given frame
# ════════════════════════════════════════════════════════════════════════════════
def load_vix_regime_config() -> dict:
    try:
        b5 = json.loads(B5_SCORECARD.read_text(encoding="utf-8"))
        rb = b5.get("headline", {}).get("robust_clearing_cell")
        if rb and rb.get("slope_rule") is not None and rb.get("low_margin") is not None:
            return {"slope_rule": rb["slope_rule"], "low_margin": rb["low_margin"],
                    "source": "b5 robust_clearing_cell"}
    except Exception as e:  # noqa: BLE001
        print(f"[verify] WARN b5 scorecard unreadable ({e}); default vix-regime cfg", flush=True)
    return {"slope_rule": "not_rising", "low_margin": 0.0, "source": "default"}


def detect_book_edges(days, spy, vix) -> dict:
    """#1 / #2 / #4 signal sets — same calls as recency_check.detect_all."""
    out = {}
    out["vwap_continuation"] = detect_vwap_continuation(
        days, vix, breakout_only=False, put_needs_rising_vix=False)
    out["vwap_reclaim_failed_break"] = detect_reclaim_failed_break(days)
    vix_g = vix.to_numpy()
    vix_med_g = causal_vix_median(vix_g, VIX_MEDIAN_BARS)
    vix_slp_g = vix_slope(vix_g, VIX_SLOPE_BARS)
    cfg = load_vix_regime_config()
    raw4 = detect_vix_regime_dayside(days, spy, vix_g, vix_med_g, vix_slp_g,
                                     cfg["low_margin"], cfg["slope_rule"])
    out["vix_regime_dayside"] = [Signal(bar_idx=s.gidx, side=s.side,
                                        stop_level=round(_swing_stop(spy, s.gidx, s.side), 2),
                                        note="vix_regime_dayside") for s in raw4]
    return out


# ════════════════════════════════════════════════════════════════════════════════
# real-OPRA 0DTE rows for a signal set (lib.simulator_real — the WR authority)
# Used for the recency window + incremental-book correlation (0DTE, ITM-2/-0.08).
# ════════════════════════════════════════════════════════════════════════════════
def simulate_realfills(signals, spy, ribbon, vix, *, strike_offset, setup) -> list[dict]:
    from autoresearch.infinite_ammo_discovery import _nearest_cached_strike, _strike_from_spot
    rows = []
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - strike_offset if sg.side == "P" else atm + strike_offset
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
        if strike is None:
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side=sg.side,
            qty=QTY, setup=setup, strike_override=strike, entry_vix=entry_vix,
            premium_stop_pct=PREMIUM_STOP_PCT)
        if fill is None or fill.dollar_pnl is None:
            continue
        rows.append({"date": str(d), "side": sg.side, "pnl": round(float(fill.dollar_pnl), 2)})
    return rows


def window_metrics(rows, start: dt.date, end: dt.date) -> dict:
    sub = [r for r in rows if start <= dt.date.fromisoformat(r["date"]) <= end]
    if not sub:
        return {"n": 0, "window": f"{start}..{end}"}
    pnl = np.array([r["pnl"] for r in sub], float)
    by_day = defaultdict(float)
    for r in sub:
        by_day[r["date"]] += r["pnl"]
    daily = np.array([by_day[d] for d in sorted(by_day)], float)
    return {"window": f"{start}..{end}", "n": len(sub), "n_days": len(by_day),
            "wr_pct": round(100 * float((pnl > 0).mean()), 1),
            "exp_per_trade": round(float(pnl.mean()), 2),
            "total_dollar": round(float(pnl.sum()), 2),
            "sign": "POSITIVE" if pnl.mean() > 0 else ("FLAT" if pnl.mean() == 0 else "NEGATIVE"),
            "win_days": int((daily > 0).sum()), "loss_days": int((daily < 0).sum())}


def daily_pnl_series(rows) -> dict[dt.date, float]:
    by = defaultdict(float)
    for r in rows:
        by[dt.date.fromisoformat(r["date"])] += r["pnl"]
    return dict(by)


# ════════════════════════════════════════════════════════════════════════════════
def main() -> int:
    print("[verify] ===== STEP 0: load master frame for INDEPENDENCE + 0DTE gate run =====", flush=True)
    spy, vix = sim._load_spy_vix()            # master 2025-01-02..2026-06-16 (the gate-run frame)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(__import__("pandas").Series(spy["close"].values))
    n_days = len(days)
    print(f"[verify] master frame days={n_days} "
          f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}", flush=True)

    # ── vwap_pullback (H4) signals + #1/#2/#4 signals (byte-for-byte) ──────────
    vp_signals = detect_vwap_pullback(spy, None, vix, days)
    book = detect_book_edges(days, spy, vix)
    vp_days = signal_day_sides(vp_signals, spy)
    book_days = {k: signal_day_sides(v, spy) for k, v in book.items()}
    print(f"[verify] vwap_pullback signals={len(vp_signals)} on {len(vp_days)} days", flush=True)
    for k, v in book.items():
        print(f"[verify]   {k}: {len(v)} signals on {len(book_days[k])} days", flush=True)

    # ════ STEP 1: INDEPENDENCE (decisive, L174) ════════════════════════════════
    print("\n[verify] ===== STEP 1: INDEPENDENCE (day-overlap + same-side, L174) =====", flush=True)
    independence = {}
    for k in ("vwap_continuation", "vwap_reclaim_failed_break", "vix_regime_dayside"):
        om = overlap_metrics(vp_days, book_days[k])
        independence[k] = om
        print(f"[verify]   vs {k:28s}: day_overlap={om['day_overlap_shared_over_candidate']} "
              f"jaccard={om['jaccard_shared_over_union']} same_side={om['same_side_day_overlap']} "
              f"({om['same_side_shared_days']}/{om['candidate_days']}) "
              f"RESKIN={om['reskin_by_same_side']}", flush=True)
    reskin_of_1 = independence["vwap_continuation"]["reskin_by_same_side"] or \
        independence["vwap_continuation"]["reskin_by_day_overlap"]

    # ════ STEP 2: FULL 11-gate bar at ITM-2/-0.08 (re-run from scratch) ════════
    print("\n[verify] ===== STEP 2: FULL 11-gate bar at ITM-2/-0.08 (0DTE, re-run) =====", flush=True)
    day_open_close = sim._spy_day_open_close(spy)
    rows0, cov0 = sim.run_cell(vp_signals, spy, day_open_close, 0,
                               strike_offset=BEST_TIER_OFFSET, premium_stop_pct=BEST_TIER_STOP)
    m0 = sim.metrics(rows0)
    struct_pass, struct_fails = sim.clears_bar(m0)
    # gate8 no-truncation: same-strike chart-stop-only (-0.99) per-trade
    rowsCS, _ = sim.run_cell(vp_signals, spy, day_open_close, 0,
                             strike_offset=BEST_TIER_OFFSET, premium_stop_pct=-0.99)
    mCS = sim.metrics(rowsCS)
    trunc_artifact = is_truncation_artifact(
        best_per_trade=m0.get("exp_dollar"),
        chart_stop_only_per_trade=mCS.get("exp_dollar"),
        best_premium_stop_pct=BEST_TIER_STOP)
    # gate7 random-entry null (L172) — survey's dte_null, dte=0, matched cell
    cell_rows = [{"date": r.date, "side": r.side} for r in rows0]
    null = dte_null(cell_rows, spy, day_open_close, 0, BEST_TIER_OFFSET, BEST_TIER_STOP)
    beats_max = m0.get("exp_dollar") is not None and m0["exp_dollar"] > null["per_trade_max"]
    drop5_full = m0.get("drop_top5_full")
    drop_beats_mean = drop5_full is not None and drop5_full > null["per_trade_mean"]
    null_pass = bool(beats_max and drop_beats_mean)
    l173_pass = bool(m0.get("oos_drop_top5_evaluable") and (m0.get("oos_drop_top5") or -1) > 0)
    all_11_pass = bool(struct_pass and null_pass and (not trunc_artifact))
    gate_block = {
        "tier": "ITM-2", "strike_offset": BEST_TIER_OFFSET, "premium_stop_pct": BEST_TIER_STOP,
        "coverage": cov0, "n": m0.get("n"), "oos_n": m0.get("oos_n"),
        "oos_per_trade": m0.get("oos_exp"), "exp_per_trade": m0.get("exp_dollar"),
        "is_first_half": m0.get("is_first_half_exp"),
        "positive_quarters": m0.get("positive_quarters"),
        "top5_day_pct": m0.get("top5_day_pct"),
        "drop_top5_full": drop5_full,
        "oos_drop_top5_L173": m0.get("oos_drop_top5"),
        "oos_drop_top5_evaluable": m0.get("oos_drop_top5_evaluable"),
        "risk_adj_exp_over_std": m0.get("risk_adj_exp"),
        "structural_gates_pass": struct_pass, "structural_fails": struct_fails,
        "L173_pass": l173_pass,
        "gate7_null": null, "gate7_null_pass": null_pass,
        "chart_stop_only_per_trade": mCS.get("exp_dollar"),
        "gate8_truncation_artifact": trunc_artifact,
        "ALL_11_GATES_PASS": all_11_pass,
    }
    print(f"[verify]   n={m0.get('n')} oos/tr=${m0.get('oos_exp')} exp/tr=${m0.get('exp_dollar')} "
          f"struct={'P' if struct_pass else 'F'} L173={'P' if l173_pass else 'F'} "
          f"null_pass={null_pass} trunc={'BAD' if trunc_artifact else 'ok'} -> ALL={all_11_pass}",
          flush=True)
    if struct_fails:
        print(f"[verify]   structural fails: {struct_fails}", flush=True)

    # ════ STEP 3: RECENCY (freshest ~25 trading days, real OPRA fills) ═════════
    print("\n[verify] ===== STEP 3: RECENCY (last ~25 trading days, merged frame) =====", flush=True)
    # merged frame = master + recent daily (recency_check.load_merged_spy_vix logic)
    import pandas as pd
    mspy = pd.read_csv(DATA / "spy_5m_2025-01-01_2026-06-16.csv")
    mvix = pd.read_csv(DATA / "vix_5m_2025-01-01_2026-06-16.csv")
    rspy = pd.read_csv(DATA / "spy_5m_2026-05-19_2026-06-18.csv")
    rvix = pd.read_csv(DATA / "vix_5m_2026-05-19_2026-06-18.csv")
    spy_m = _normalize_spy(pd.concat([mspy, rspy], ignore_index=True))
    vix_m = _align_vix(spy_m, pd.concat([mvix, rvix], ignore_index=True))
    days_m = build_day_contexts(spy_m)
    ribbon_m = compute_ribbon(pd.Series(spy_m["close"].values))
    cov = json.loads(DATA_COVERAGE.read_text(encoding="utf-8"))
    cache_last = dt.date.fromisoformat(cov["classes"]["option_chain_realfills"]["last"])
    tdays = sorted({dc.date for dc in days_m})
    in_range = [d for d in tdays if d <= cache_last]
    recent_start = in_range[-RECENCY_LOOKBACK] if len(in_range) >= RECENCY_LOOKBACK else in_range[0]
    recent_end = cache_last
    print(f"[verify]   OPRA cache last={cache_last} recent window {recent_start}..{recent_end} "
          f"({len([d for d in tdays if recent_start <= d <= recent_end])} trading days)", flush=True)

    vp_signals_m = detect_vwap_pullback(spy_m, None, vix_m, days_m)
    vp_rows_real = simulate_realfills(vp_signals_m, spy_m, ribbon_m, vix_m,
                                      strike_offset=BEST_TIER_OFFSET, setup="VP_RECENCY")
    recent = window_metrics(vp_rows_real, recent_start, recent_end)
    full_oos = window_metrics(vp_rows_real, dt.date(2026, 1, 1), recent_end)
    # recency_check verdict logic
    rn, rexp, foexp = recent.get("n", 0), recent.get("exp_per_trade"), full_oos.get("exp_per_trade")
    if rn == 0:
        rec_verdict, rec_reason = "NO_FILLS", "no fills in recent window"
    elif rexp is not None and rexp > 0:
        rec_verdict = "CONFIRM" if rn >= RECENCY_FLOOR else "YELLOW"
        rec_reason = f"recent +${rexp}/tr n={rn} ({'>=' if rn>=RECENCY_FLOOR else '<'}floor {RECENCY_FLOOR})"
    elif rn >= RECENCY_FLOOR:
        rec_verdict, rec_reason = "RED", f"recent ${rexp}/tr NEGATIVE n={rn}>=floor"
    else:
        rec_verdict = "YELLOW"
        rec_reason = f"recent ${rexp}/tr <=0 but n={rn}<floor; full-OOS ${foexp}/tr"
    recency_block = {"recent_window": recent, "full_oos_2026": full_oos,
                     "verdict": rec_verdict, "reason": rec_reason,
                     "opra_cache_last": str(cache_last)}
    print(f"[verify]   recency: n={recent.get('n')} exp=${recent.get('exp_per_trade')} "
          f"{recent.get('sign')} -> {rec_verdict} | full-OOS-2026 exp=${full_oos.get('exp_per_trade')} "
          f"(n={full_oos.get('n')})", flush=True)

    # ════ STEP 4: INCREMENTAL value over the #1+#2+#4 book ═════════════════════
    print("\n[verify] ===== STEP 4: INCREMENTAL value over the #1+#2+#4 book =====", flush=True)
    # All on the master frame, real OPRA fills, ITM-2/-0.08 (apples-to-apples directional read).
    vp_book = simulate_realfills(detect_vwap_pullback(spy, None, vix, days), spy, ribbon, vix,
                                 strike_offset=BEST_TIER_OFFSET, setup="VP_BOOK")
    book_rows = {}
    for k, sigset in book.items():
        book_rows[k] = simulate_realfills(sigset, spy, ribbon, vix,
                                          strike_offset=BEST_TIER_OFFSET, setup=f"{k}_BOOK")
    vp_daily = daily_pnl_series(vp_book)
    c1_daily = daily_pnl_series(book_rows["vwap_continuation"])
    # combined existing book daily
    book_daily = defaultdict(float)
    for k in book_rows:
        for d, p in daily_pnl_series(book_rows[k]).items():
            book_daily[d] += p
    book_daily = dict(book_daily)

    def corr(a: dict, b: dict) -> dict:
        common = sorted(set(a) & set(b))
        if len(common) < 3:
            return {"n_common_days": len(common), "pearson": None}
        av = np.array([a[d] for d in common]); bv = np.array([b[d] for d in common])
        if av.std() == 0 or bv.std() == 0:
            return {"n_common_days": len(common), "pearson": None}
        return {"n_common_days": len(common), "pearson": round(float(np.corrcoef(av, bv)[0, 1]), 3)}

    def sharpe_daily(series: dict) -> dict:
        vals = np.array([series[d] for d in sorted(series)], float)
        if len(vals) < 2 or vals.std(ddof=1) == 0:
            return {"n_days": len(vals), "total": round(float(vals.sum()), 2), "daily_sharpe": None}
        return {"n_days": len(vals), "total": round(float(vals.sum()), 2),
                "daily_mean": round(float(vals.mean()), 2),
                "daily_sharpe": round(float(vals.mean() / vals.std(ddof=1)), 4)}

    combined = defaultdict(float)
    for d, p in book_daily.items():
        combined[d] += p
    for d, p in vp_daily.items():
        combined[d] += p
    incremental = {
        "note": "all on master frame, real OPRA fills, ITM-2/-0.08 (directional apples-to-apples)",
        "vwap_pullback_daily": sharpe_daily(vp_daily),
        "existing_book_1+2+4_daily": sharpe_daily(book_daily),
        "book_plus_vp_daily": sharpe_daily(dict(combined)),
        "corr_vp_vs_#1": corr(vp_daily, c1_daily),
        "corr_vp_vs_existing_book": corr(vp_daily, book_daily),
        "shared_trading_days_vp_book": len(set(vp_daily) & set(book_daily)),
    }
    print(f"[verify]   vp daily_sharpe={incremental['vwap_pullback_daily'].get('daily_sharpe')} "
          f"book daily_sharpe={incremental['existing_book_1+2+4_daily'].get('daily_sharpe')} "
          f"book+vp daily_sharpe={incremental['book_plus_vp_daily'].get('daily_sharpe')}", flush=True)
    print(f"[verify]   corr(vp,#1)={incremental['corr_vp_vs_#1']['pearson']} "
          f"corr(vp,book)={incremental['corr_vp_vs_existing_book']['pearson']}", flush=True)

    # ════ VERDICT ══════════════════════════════════════════════════════════════
    if reskin_of_1:
        verdict = "RESKIN_OF_1"
    elif not all_11_pass:
        verdict = "FAILS_GATES"
    else:
        verdict = "NEW_4TH_EDGE"

    summary = {
        "study": "vwap_pullback (H4) — genuine 4th 0DTE edge, or re-skin of #1 (L174)?",
        "run_date": dt.date.today().isoformat(),
        "mode": "SAFE research — READ-ONLY, $0, no live edit, no orders",
        "frame_independence_and_gates": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()} (master)",
        "fills_authority": "real OPRA via lib.simulator_real / _dte_expansion_sim (C1)",
        "detector": "BYTE-FOR-BYTE infinite_ammo_discovery.detect_vwap_pullback (H4)",
        "overlap_method": f"_b8_anchored_vwap convention (shared/candidate) + jaccard + same-side; OVERLAP_MAX={OVERLAP_MAX} (L174)",
        "best_tier": {"tier": "ITM-2", "strike_offset": BEST_TIER_OFFSET, "premium_stop_pct": BEST_TIER_STOP},
        "vwap_pullback_signal_days": len(vp_days),
        "independence_vs_book": independence,
        "reskin_of_1": reskin_of_1,
        "gate_bar_11": gate_block,
        "recency": recency_block,
        "incremental_value": incremental,
        "VERDICT": verdict,
        "DISCLOSURE": {
            "L174": "decisive test is same-side day-overlap vs LIVE #1; anchored-VWAP A3 was blocked at 0.973",
            "chart_stop_caveat": ("the headline +$64.77/tr uses premium_stop=-0.08; the LIVE first-strike "
                                  "rule (L51/L55/C2) trades chart-stop-only, where prior ratify "
                                  "(vwap_pullback_ratify.py) found only +$14/t and WF median 0.239 FAIL. "
                                  "This study evaluates the SURVEY's -0.08 cell as posed."),
            "proxy_strikes": "nearest-cached strike (L58); directionally valid, $ modestly off",
            "real_fills": "real OPRA fills only — WR authority (C1); SPY-direction != option edge (C3/L58)",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[verify] wrote {OUT}", flush=True)
    print("\n=== VWAP_PULLBACK EDGE-VERIFY VERDICT ===")
    print(f"  same-side overlap vs #1 = {independence['vwap_continuation']['same_side_day_overlap']} "
          f"(day_overlap {independence['vwap_continuation']['day_overlap_shared_over_candidate']}, "
          f"jaccard {independence['vwap_continuation']['jaccard_shared_over_union']})")
    print(f"  11-gate bar ITM-2/-0.08: ALL_PASS={all_11_pass} "
          f"(n={m0.get('n')} oos/tr=${m0.get('oos_exp')})")
    print(f"  recency ({recent.get('window')}): {rec_verdict} (n={recent.get('n')} exp=${recent.get('exp_per_trade')})")
    print(f"  VERDICT = {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
