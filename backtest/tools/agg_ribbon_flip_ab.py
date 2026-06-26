"""AGG ribbon_just_flipped_bearish A/B sizing bonus analysis.

Task 2207a18a: Split BEARISH_REJECTION entries by ribbon_flip trigger presence.
If flip=True WR >= 0.55 AND avg > non-flip group over IS + OOS:
  -> Propose ELITE sizing when bear_score >= 8 AND ribbon_flip fires.

Method:
  - Proxy for ribbon_just_flipped_bearish: "ribbon_flip" in triggers_fired
  - Proxy for bear_score: use decisions dict (matched via signal bar timestamp)
  - Filter: side=P (bearish) trades only
  - IS (287 days) + OOS (60 days) per standard split

Security: read-only. No Alpaca calls. No production state writes.
"""
from __future__ import annotations
import sys, json, datetime as dt
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from lib.orchestrator import run_backtest  # noqa
from sniper_matrix import norm_str  # noqa: E402

DATA = REPO / "data"
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "agg_ribbon_flip_ab.json"

IS_CUTOFF = dt.date(2026, 2, 27)
MDATES_SET = {dt.date(2026, 5, 26), dt.date(2026, 5, 27),
              dt.date(2026, 5, 28), dt.date(2026, 5, 29)}
ANCHOR_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}

SW_SPLITS = [
    ("SW1_2025H1",  dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("SW2_2025H2",  dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("SW3_early26", dt.date(2026, 1, 2),  dt.date(2026, 2, 26)),
]

AGG_KWARGS = dict(
    use_real_fills=True,
    strike_offset=-2,
    premium_stop_pct_bear=-0.07,
    premium_stop_pct_bull=-0.05,
    tp1_premium_pct=0.75,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=5.0,
    f9_vol_mult=0.7,
    min_triggers_bear=1,
    min_triggers_bull=1,
    no_trade_before=dt.time(9, 35),
    no_trade_window=None,
    block_level_rejection=True,
    block_conf_lvl_rec_afternoon=True,
    block_conf_lvl_rej_midday_afternoon=True,
    midday_trendline_gate=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    require_bearish_fill_bar=True,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.5,
    enable_bullish=True,
    params_overrides={"vix_bear_threshold": 15.0},
)


def get_fill_days():
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    return sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})


def load_spy_vix():
    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"), key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_name = spy_path.name.replace("spy_5m", "vix_5m")
    spy_df = norm_str(pd.read_csv(spy_path))
    vix_df = norm_str(pd.read_csv(vix_path := DATA / vix_name))
    print(f"  SPY: {spy_path.name}  VIX: {vix_path.name}")
    return spy_df, vix_df


def build_decision_map(decisions):
    """Build {timestamp_et_str: decision_dict} for passed=True bear decisions.

    Key is the signal bar timestamp (bar_time). We use str matching since
    pandas timestamps have mixed tz formatting.
    """
    dmap = {}
    for d in decisions:
        if d.get("passed") and d.get("bear_score") is not None:
            ts = str(d["timestamp_et"])
            # Keep highest-score decision if multiple decisions share the same ts
            # (can happen with multi-setup routing; take highest bear_score)
            if ts not in dmap or d["bear_score"] > dmap[ts]["bear_score"]:
                dmap[ts] = d
    return dmap


def match_bear_score(trade, decision_map):
    """Find bear_score for a trade by matching signal bar (fill_time - 5min)."""
    fill_dt = trade.entry_time_et
    if hasattr(fill_dt, "tzinfo") and fill_dt.tzinfo is not None:
        fill_dt = fill_dt.replace(tzinfo=None)
    signal_dt = fill_dt - dt.timedelta(minutes=5)
    # Try exact match first
    for ts_str, decision in decision_map.items():
        # Parse the decision timestamp and compare (strip tz)
        try:
            dts = pd.Timestamp(ts_str)
            if dts.tzinfo is not None:
                dts = dts.tz_localize(None)
            if abs((dts - pd.Timestamp(signal_dt)).total_seconds()) < 61:
                return decision.get("bear_score")
        except Exception:
            continue
    return None  # couldn't match


def annotate_bearish(trades, decision_map):
    """Annotate bearish trades with ribbon_flip and bear_score."""
    out = []
    unmatched = 0
    for t in trades:
        if t.side != "P":
            continue
        has_flip = "ribbon_flip" in t.triggers_fired
        score = match_bear_score(t, decision_map)
        if score is None:
            unmatched += 1
        fill_dt = t.entry_time_et
        if hasattr(fill_dt, "tzinfo") and fill_dt.tzinfo is not None:
            fill_dt = fill_dt.replace(tzinfo=None)
        out.append({
            "date": t.entry_time_et.date(),
            "entry_dt": fill_dt,
            "pnl": round(t.dollar_pnl, 2),
            "exit_reason": str(t.exit_reason),
            "triggers": t.triggers_fired,
            "n_triggers": len(t.triggers_fired),
            "ribbon_flip": has_flip,
            "bear_score": score,
        })
    if unmatched:
        print(f"    Warning: {unmatched}/{len(out)+unmatched} bearish trades had no score match")
    return out


def group_stats(trades, key_fn, label):
    """Return stats dict for two groups split by key_fn (bool)."""
    flip = [t for t in trades if key_fn(t)]
    no_flip = [t for t in trades if not key_fn(t)]
    def s(lst):
        if not lst:
            return {"n": 0, "wr": None, "avg_pnl": None, "total_pnl": None}
        n = len(lst)
        total = round(sum(t["pnl"] for t in lst), 1)
        wins = sum(1 for t in lst if t["pnl"] > 0)
        return {"n": n, "wr": round(wins / n, 3), "avg_pnl": round(total / n, 1), "total_pnl": total}
    print(f"\n  {label}:")
    for grp, lst in [("flip=True", flip), ("flip=False", no_flip)]:
        st = s(lst)
        print(f"    {grp:<14}: n={st['n']:<4} WR={st['wr'] or 0:.1%}  avg={st['avg_pnl'] or 0:>+7.0f}")
    return {"flip_true": s(flip), "flip_false": s(no_flip)}


def score_breakdown(trades, label, min_score=None):
    """Distribution by bear_score bucket."""
    print(f"\n  {label} — by bear_score{' (score>=' + str(min_score) + ')' if min_score else ''}:")
    print(f"  {'score':<8} {'n':>4} {'WR':>6} {'avg':>8} {'total':>8} {'flip%':>6}")
    data = [t for t in trades if min_score is None or (t["bear_score"] or 0) >= min_score]
    for score in sorted(set(t["bear_score"] for t in data if t["bear_score"] is not None)):
        group = [t for t in data if t["bear_score"] == score]
        n = len(group)
        pnls = [t["pnl"] for t in group]
        wins = sum(1 for p in pnls if p > 0)
        total = sum(pnls)
        flip_n = sum(1 for t in group if t["ribbon_flip"])
        print(f"  {str(score):<8} {n:>4} {wins/n:>6.1%} {total/n:>+8.0f} {total:>+8.0f} {flip_n/n:>6.1%}")


def compute_gates(is_bear, oos_bear, hypothesis, filter_fn, sw_splits):
    """OP-22 auto-ratify gates for a filter on bearish trades.

    Baseline = all bearish trades. Candidate = filter applied.
    """
    is_base = sum(t["pnl"] for t in is_bear)
    is_filt = sum(t["pnl"] for t in is_bear if filter_fn(t))
    oos_base = sum(t["pnl"] for t in oos_bear)
    oos_filt = sum(t["pnl"] for t in oos_bear if filter_fn(t))

    is_delta = round(is_filt - is_base, 1)
    oos_delta = round(oos_filt - oos_base, 1)
    n_removed_is  = len(is_bear)  - sum(1 for t in is_bear if filter_fn(t))
    n_removed_oos = len(oos_bear) - sum(1 for t in oos_bear if filter_fn(t))

    wf_norm = None
    if n_removed_is > 0 and is_delta > 0 and n_removed_oos > 0:
        wf_norm = round((oos_delta / n_removed_oos) / (is_delta / n_removed_is), 3)

    sw_hurt = 0
    sw_details = []
    for sw_name, sw_start, sw_end in sw_splits:
        sw_is = [t for t in is_bear if sw_start <= t["date"] <= sw_end]
        sw_base_pnl = sum(t["pnl"] for t in sw_is)
        sw_filt_pnl = sum(t["pnl"] for t in sw_is if filter_fn(t))
        sw_delta = round(sw_filt_pnl - sw_base_pnl, 1)
        hurt = sw_delta < 0
        if hurt:
            sw_hurt += 1
        sw_details.append({"name": sw_name, "delta": sw_delta, "hurt": hurt})

    anchor_blocked = []
    for d in ANCHOR_WINNERS:
        day_trades = [t for t in oos_bear if t["date"] == d]
        for t in day_trades:
            if not filter_fn(t):
                anchor_blocked.append({"date": str(d), "pnl": t["pnl"]})
    anchor_ok = len(anchor_blocked) == 0

    gate_is  = is_delta  > 0
    gate_oos = oos_delta > 0
    gate_wf  = wf_norm is not None and wf_norm >= 0.70
    gate_sw  = sw_hurt <= 1
    all_pass = gate_is and gate_oos and gate_wf and gate_sw and anchor_ok
    verdict  = "AUTO-RATIFY" if all_pass else "REJECT"

    return {
        "hypothesis": hypothesis,
        "verdict": verdict,
        "is_delta": is_delta,
        "oos_delta": oos_delta,
        "n_removed_is": n_removed_is,
        "n_removed_oos": n_removed_oos,
        "wf_norm": wf_norm,
        "sw_hurt": sw_hurt,
        "sw_details": sw_details,
        "anchor_blocked": anchor_blocked,
        "gates": {
            "is_pos": gate_is, "oos_pos": gate_oos,
            "wf": gate_wf, "sw": gate_sw, "anchor": anchor_ok,
        },
    }


def main():
    print("=" * 70)
    print("AGG RIBBON_FLIP A/B SIZING ANALYSIS (BEARISH TRADES)")
    print("=" * 70)

    all_days = get_fill_days()
    is_days  = [d for d in all_days if d < IS_CUTOFF and d not in MDATES_SET]

    print("\n[1] Loading SPY/VIX data...")
    spy_df, vix_df = load_spy_vix()

    spy_dates    = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)
    oos_days_all = [d for d in all_days if d >= IS_CUTOFF and d not in MDATES_SET and d in spy_dates]
    oos_days     = oos_days_all[-60:]

    print(f"\n[2] Date ranges: IS {is_days[0]}..{is_days[-1]} ({len(is_days)} days) | "
          f"OOS {oos_days[0]}..{oos_days[-1]} ({len(oos_days)} days)")

    print("\n[3] Running IS backtest...")
    is_result = run_backtest(spy_df, vix_df, start_date=is_days[0], end_date=is_days[-1], **AGG_KWARGS)
    print(f"    -> {len(is_result.trades)} trades | {len(is_result.decisions)} decisions")

    print("[4] Running OOS backtest...")
    oos_result = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **AGG_KWARGS)
    print(f"    -> {len(oos_result.trades)} trades | {len(oos_result.decisions)} decisions")

    print("\n[5] Annotating bearish trades...")
    is_dmap  = build_decision_map(is_result.decisions)
    oos_dmap = build_decision_map(oos_result.decisions)
    is_bear  = annotate_bearish(is_result.trades, is_dmap)
    oos_bear = annotate_bearish(oos_result.trades, oos_dmap)

    # Overall bearish breakdown
    n_is_bear  = len(is_bear)
    n_oos_bear = len(oos_bear)
    n_is_flip  = sum(1 for t in is_bear if t["ribbon_flip"])
    n_oos_flip = sum(1 for t in oos_bear if t["ribbon_flip"])
    print(f"    IS  bearish: n={n_is_bear}  ribbon_flip={n_is_flip} ({n_is_flip/n_is_bear:.0%})")
    print(f"    OOS bearish: n={n_oos_bear}  ribbon_flip={n_oos_flip} ({n_oos_flip/n_oos_bear:.0%})")

    # ── Primary A/B split: ribbon_flip True vs False ──────────────────────
    print("\n[6a] IS — ribbon_flip A/B split (all bearish):")
    is_ab = group_stats(is_bear, lambda t: t["ribbon_flip"], "IS all bearish")
    print("\n[6b] OOS — ribbon_flip A/B split:")
    oos_ab = group_stats(oos_bear, lambda t: t["ribbon_flip"], "OOS all bearish")

    # ── By score and flip combination ─────────────────────────────────────
    print("\n[6c] IS — bear_score distribution (with ribbon_flip %):")
    score_breakdown(is_bear, "IS all bearish")

    # High-score bearish (score >= 8) flip vs no-flip
    is_hs = [t for t in is_bear if (t["bear_score"] or 0) >= 8]
    oos_hs = [t for t in oos_bear if (t["bear_score"] or 0) >= 8]
    print(f"\n[6d] High-score (score>=8) bearish trades: IS n={len(is_hs)}, OOS n={len(oos_hs)}")
    is_hs_ab = group_stats(is_hs, lambda t: t["ribbon_flip"], "IS score>=8 bearish")
    oos_hs_ab = group_stats(oos_hs, lambda t: t["ribbon_flip"], "OOS score>=8 bearish")

    # ── Exit reason by flip ────────────────────────────────────────────────
    print("\n[6e] IS — exit reason split by ribbon_flip:")
    for flip_val, label in [(True, "flip=True"), (False, "flip=False")]:
        grp = [t for t in is_bear if t["ribbon_flip"] == flip_val]
        if grp:
            print(f"  {label} (n={len(grp)}):")
            exit_ctr = Counter(t["exit_reason"] for t in grp)
            for reason, cnt in sorted(exit_ctr.items(), key=lambda x: -x[1]):
                pnls = [t["pnl"] for t in grp if t["exit_reason"] == reason]
                print(f"    {reason:<42} n={cnt:>3} avg={sum(pnls)/cnt:>+7.0f}")

    # ── Gate hypothesis: BLOCK non-flip bearish entries ───────────────────
    print("\n[7] Testing gate hypotheses (OP-22)...")
    gate_results = []

    # H1: Keep only bearish trades with ribbon_flip
    h1 = compute_gates(is_bear, oos_bear, "H1_flip_only (block bearish without ribbon_flip)",
                       lambda t: t["ribbon_flip"], list(SW_SPLITS))
    gate_results.append(h1)
    print(f"  H1 flip_only: {h1['verdict']}")
    print(f"     IS_delta={h1['is_delta']:+.0f} OOS_delta={h1['oos_delta']:+.0f} "
          f"WF={str(h1['wf_norm'])} SW_hurt={h1['sw_hurt']}")

    # H2: Keep flip=True on high-score (>=8) only
    h2 = compute_gates(is_bear, oos_bear, "H2_hs_flip_only (score>=8 AND ribbon_flip)",
                       lambda t: not ((t["bear_score"] or 0) >= 8 and not t["ribbon_flip"]),
                       list(SW_SPLITS))
    gate_results.append(h2)
    print(f"  H2 hs_flip_only: {h2['verdict']}")
    print(f"     IS_delta={h2['is_delta']:+.0f} OOS_delta={h2['oos_delta']:+.0f} "
          f"WF={str(h2['wf_norm'])} SW_hurt={h2['sw_hurt']}")

    # H3: Block no-flip entries that also have no level_rejection trigger
    h3 = compute_gates(is_bear, oos_bear, "H3_require_lvl_rej_if_no_flip",
                       lambda t: t["ribbon_flip"] or "level_rejection" in t["triggers"],
                       list(SW_SPLITS))
    gate_results.append(h3)
    print(f"  H3 require_lvl_rej_if_no_flip: {h3['verdict']}")
    print(f"     IS_delta={h3['is_delta']:+.0f} OOS_delta={h3['oos_delta']:+.0f} "
          f"WF={str(h3['wf_norm'])} SW_hurt={h3['sw_hurt']}")

    # ── Auto-ratify check ──────────────────────────────────────────────────
    ratified = [g for g in gate_results if g["verdict"] == "AUTO-RATIFY"]

    # Key research question: does ribbon_flip qualify for ELITE sizing bonus?
    # Threshold: IS flip WR >= 0.55 AND IS flip avg > IS no-flip avg
    is_flip_wr  = is_ab["flip_true"]["wr"] or 0.0
    is_flip_avg = is_ab["flip_true"]["avg_pnl"] or 0.0
    is_noflip_avg = is_ab["flip_false"]["avg_pnl"] or 0.0
    oos_flip_wr  = oos_ab["flip_true"]["wr"] or 0.0
    oos_flip_avg = oos_ab["flip_true"]["avg_pnl"] or 0.0

    flip_qualifies = (is_flip_wr >= 0.55 and is_flip_avg > is_noflip_avg)
    oos_confirms   = (oos_flip_wr >= 0.40 and oos_flip_avg > 0)

    print(f"\n{'='*70}")
    print("VERDICT SUMMARY")
    print(f"{'='*70}")
    if ratified:
        best = max(ratified, key=lambda g: g["oos_delta"])
        print(f"  *** AUTO-RATIFY: {best['hypothesis']} ***")
        print(f"  IS_delta={best['is_delta']:+.0f} OOS_delta={best['oos_delta']:+.0f} WF_norm={best['wf_norm']}")
    else:
        print("  No gate hypothesis cleared all OP-22 gates.")

    print(f"\n  ELITE SIZING BONUS ELIGIBILITY:")
    print(f"  IS  flip=True: WR={is_flip_wr:.1%} avg={is_flip_avg:+.0f}")
    print(f"  IS  no-flip:   avg={is_noflip_avg:+.0f}")
    print(f"  OOS flip=True: WR={oos_flip_wr:.1%} avg={oos_flip_avg:+.0f}")
    print(f"  IS WR>=0.55: {'YES' if is_flip_wr >= 0.55 else 'NO'}  "
          f"IS avg>no-flip: {'YES' if is_flip_avg > is_noflip_avg else 'NO'}  "
          f"OOS confirms: {'YES' if oos_confirms else 'NO'}")
    print(f"  -> ELITE BONUS PROPOSAL: {'ELIGIBLE' if flip_qualifies and oos_confirms else 'NOT ELIGIBLE'}")

    # ── Save ─────────────────────────────────────────────────────────────
    scorecard = {
        "task": "2207a18a-ribbon-flip-ab",
        "is_date_range": [str(is_days[0]), str(is_days[-1])],
        "oos_date_range": [str(oos_days[0]), str(oos_days[-1])],
        "is_bearish_total": n_is_bear,
        "oos_bearish_total": n_oos_bear,
        "is_ribbon_flip_pct": round(n_is_flip / n_is_bear, 3) if n_is_bear else 0,
        "oos_ribbon_flip_pct": round(n_oos_flip / n_oos_bear, 3) if n_oos_bear else 0,
        "is_ab": is_ab,
        "oos_ab": oos_ab,
        "is_hs_ab": is_hs_ab,
        "oos_hs_ab": oos_hs_ab,
        "gate_hypotheses": gate_results,
        "auto_ratified": [g["hypothesis"] for g in ratified],
        "elite_bonus_eligible": flip_qualifies and oos_confirms,
        "elite_bonus_criteria": {
            "is_flip_wr": round(is_flip_wr, 3),
            "is_flip_avg": round(is_flip_avg, 1),
            "is_noflip_avg": round(is_noflip_avg, 1),
            "oos_flip_wr": round(oos_flip_wr, 3),
            "oos_flip_avg": round(oos_flip_avg, 1),
            "is_wr_ge_055": is_flip_wr >= 0.55,
            "is_avg_gt_noflip": is_flip_avg > is_noflip_avg,
            "oos_confirms": oos_confirms,
        },
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(scorecard, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")
    print("RIBBON_FLIP A/B COMPLETE.")


if __name__ == "__main__":
    raise SystemExit(main())
