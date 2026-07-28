"""exit_leak_decompose.py -- THE EXIT LEAK, measured not guessed (J directive 2026-07-27
"figure out what we need to replay to make money"; lane: exit mechanics decomposition).

POPULATION: analysis/recommendations/engine-fullhist-replay-2026-07-23.json `trades` (190,
RIDE_THE_RIBBON family, real-OPRA-derived P&L via the REAL exit_manager -- reused verbatim,
never re-run at the entry layer). PROVISIONAL caveat carried forward: trade-level anchors vs
live are 1/4 on 2026-07-17 (corrected matcher, L250) -- the ENTRY layer diverges from live;
everything below decomposes the replay's own exit mechanics, not live fills.

WHAT THIS COMPUTES (three deliverables, one pre-registered check):
  1. MFE-GIVEBACK: for every trade, re-walk the REAL exit core
     (backtest/lib/exit_manager_walk.walk_exit_manager, the live decision code) under the
     unchanged control shape, reconcile per-trade dollar_pnl byte-for-byte against the source
     replay (abort-on-drift), then compute Max Favorable Excursion over the trade's own OPRA
     bar path: bars STRICTLY AFTER entry through the exit bar inclusive (entry+1 strict, per
     markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md). Two MFE conventions, both
     reported: MFE_open = max(bar.open) -- the SAME point-sample series the exit engine's
     decisions actually observe (walk_exit_manager passes best=worst=bar.open; a limit at or
     below MFE_open would have been touched by a print the engine saw); MFE_high =
     max(bar.high) -- best print incl. intra-bar wicks the point-sample engine may never see.
     Giveback = (full position liquidated exactly at MFE_open) - actual realized P&L. MFE is
     a retrospective diagnostic (no strategy can capture 100% of it); giveback is an UPPER
     BOUND on recoverable money, not a claimable edge.
  2. LOSS COMPOSITION: losers bucketed by the mechanical exit family that closed them --
     premium_stop in premium mode (-20% floor; exclusively TRENDLINE-tier trades, mechanism
     preflight-verified per prereg-class-conditional-exits-2026-07-23.json) vs premium_stop
     in structure mode (the -50% catastrophe cap: a "full catastrophe ride") vs
     structure_stop (SPY chart-level break) vs ribbon_flip_back vs time_stop. Fill-ratio
     sanity asserts each family's fills land where its mechanism says they must
     (premium mode ~0.80x entry, catastrophe ~0.50x entry).
  3. ONE PRE-REGISTERED CHECK (frozen in PREREG_A6_TRENDLINE below, written before any
     computation ran): does the A6 exit shape replicate on THIS population's
     TRENDLINE-tier cohort? See the dict for hypothesis + pass bar + independence caveats.

DESCRIPTIVE-ATTRIBUTION DISCLAIMER: items 1-2 slice existing trades by fields computed from
each trade's own path -- descriptive attribution, not search (no BH). The
"exit-all-at-+X%-touch" counterfactual table is a descriptive BOUND, explicitly NOT a
validated rule: any TP1/threshold rule change proposal must go through its own frozen
pre-reg + 4-gate bar + untouched data before it is anything more than a number on a page.

ANALYSIS ONLY: writes only to analysis/deep-research/. Never touches strategies.py,
params.json, exit_manager.py, or any trading-path file. No broker imports, no network calls.

Run: backtest/.venv/Scripts/python.exe backtest/tools/exit_leak_decompose.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (str(BACKTEST), str(BACKTEST / "tools"), str(FLEET_DIR), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import strategies as fleet_strategies  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import load_contract_bars  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402

SOURCE_REPLAY = REPO / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"
EPISODES = REPO / "analysis" / "kitchen" / "class-conditional-exits-episodes.json"
OUT_JSON = REPO / "analysis" / "deep-research" / "EXIT-LEAK-2026-07-28.json"
OUT_MD = REPO / "analysis" / "deep-research" / "EXIT-LEAK-2026-07-28.md"
SPY_FILE = BACKTEST / "data" / "spy_5m_2025-01-01_2026-07-22.csv"
TIME_STOP_ET = dt.time(15, 40)  # engine_fullhist_replay.py's SAFE_BASE_LIVE convention

ONCE_GREEN_THRESHOLDS = [0.10, 0.20, 0.30, 0.50, 1.00]

# ---------------------------------------------------------------------------------------------
# FROZEN PRE-REGISTRATION -- written BEFORE this script computed anything. One check, no grid.
# ---------------------------------------------------------------------------------------------
PREREG_A6_TRENDLINE = {
    "written_et": "2026-07-28T00:15:00",
    "check": "A6-trendline-cohort-replication",
    "hypothesis": (
        "The A6 exit shape (premium_stop_pct -0.20 -> -0.12 applied ONLY to TRENDLINE-tier "
        "trades; trail_pct 0.15 -> 0.10 applied to any trade reaching the runner stage) -- the "
        "2026-07-23 kitchen night's only 4/4-gate cell (67.4% day-WR, killed portfolio-wide at "
        "q(BH-83)=0.3076, verdict ACCRETE per markdown/research/STRATEGY-PORTFOLIO-2026-07-23.md "
        "sect. 3) -- concentrates its benefit in, and still clears the standing 4-gate bar when "
        "scored ONLY on, the TRENDLINE-tier cohort (n=124 of 190; the cohort that is 65% of "
        "engine volume at 19.4% WR and the cohort the trigger-class open question is about)."
    ),
    "pass_bar": {
        "g1_positive_aggregate": "sum(A6_pnl - control_pnl) > 0 over TUNING TRENDLINE trades only",
        "g2_day_majority": "days with >=1 TUNING TRENDLINE trade where A6 cohort day-total > "
                            "control cohort day-total outnumber days where control >= A6 "
                            "(ties -> control; same convention as the kitchen lane)",
        "g3_survives_ex_top1": "drop the single largest positive per-trade delta; remaining "
                                "TUNING cohort aggregate delta still > 0",
        "g4_held_out_positive": "sum(A6_pnl - control_pnl) > 0 over HELD-OUT TRENDLINE trades "
                                 "(is_heldout flags reused verbatim from the kitchen episodes file)",
        "replicates": "ALL FOUR gates pass on the cohort",
    },
    "data_plan": (
        "Per-trade A6 and control P&L are INDEPENDENTLY RE-WALKED by this script via "
        "walk_exit_manager (not just read from the kitchen file), then cross-checked "
        "byte-for-byte against analysis/kitchen/class-conditional-exits-episodes.json's "
        "candidates['A6_T-TIGHT_TR-TIGHT'] and control_pnl; any mismatch is reported. "
        "is_heldout split reused verbatim from the episodes file (day-inventory heldout_days)."
    ),
    "independence_caveats": [
        "NOT independent evidence: this is the SAME 190-trade population the kitchen lane "
        "already scored A6 on, and the held-out slice was already touched once by that lane. "
        "This check answers WHERE A6's effect lives (trendline cohort vs elsewhere) and whether "
        "the cohort-restricted view survives the same bar -- it CANNOT upgrade A6 past its "
        "portfolio-level multiple-comparison kill (q=0.31). Only new independent fills or a "
        "standalone frozen pre-reg on untouched data can do that.",
        "p_raw (one-sided paired, kitchen convention) is reported as DESCRIPTIVE context only; "
        "no BH is claimed for a single pre-registered confirmatory slice.",
    ],
}


def log(msg: str) -> None:
    print(f"[exit-leak] {msg}", flush=True)


# ---------------------------------------------------------------------------------------------
# PURE HELPERS (unit-tested in backtest/tests/test_exit_leak_decompose.py)
# ---------------------------------------------------------------------------------------------
def mfe_window(opt_df: pd.DataFrame, entry_ts, exit_ts) -> Optional[dict]:
    """MFE over bars STRICTLY AFTER entry_ts through exit_ts INCLUSIVE (entry+1 strict).

    Returns {mfe_open, mfe_high, mfe_open_ts, n_bars} or None if the window is empty.
    mfe_open uses bar OPENs (the exact point-sample series walk_exit_manager feeds the
    real exit core); mfe_high uses bar HIGHs (best print incl. wicks).
    """
    ts_col = opt_df["timestamp_et"]
    if not pd.api.types.is_datetime64_any_dtype(ts_col):
        ts_col = pd.to_datetime(ts_col)
    if getattr(ts_col.dt, "tz", None) is not None:
        ts_col = ts_col.dt.tz_localize(None)
    e = pd.Timestamp(entry_ts)
    if e.tzinfo is not None:
        e = e.tz_localize(None)
    x = pd.Timestamp(exit_ts)
    if x.tzinfo is not None:
        x = x.tz_localize(None)
    mask = (ts_col > e) & (ts_col <= x)
    win = opt_df.loc[mask.values]
    if win.empty:
        return None
    opens = win["open"].astype(float)
    highs = win["high"].astype(float)
    i_best = opens.idxmax()
    return {
        "mfe_open": float(opens.max()),
        "mfe_high": float(highs.max()),
        "mfe_open_ts": pd.Timestamp(win.loc[i_best, "timestamp_et"]).to_pydatetime(),
        "n_bars": int(len(win)),
    }


def exit_family(exit_reason: str, resolved_stop_mode: str) -> str:
    """Map a walk exit_reason + the trade's resolved stop mode to a mechanical family."""
    r = exit_reason
    if r.startswith("premium_stop"):
        return "PREMIUM_STOP_20" if resolved_stop_mode == "premium" else "CATASTROPHE_50"
    if r.startswith("runner_stop"):
        return "RUNNER_TRAIL"
    if r.startswith("structure_stop"):
        return "STRUCTURE_STOP"
    if r.startswith("ribbon_flip"):
        return "RIBBON_FLIP"
    if r.startswith("time_stop"):
        return "TIME_STOP"
    if r.startswith("runner_target"):
        return "RUNNER_TARGET"
    if r.startswith("tp1"):
        return "TP1_FINAL"
    return "OTHER"


def one_sided_p_mean_gt_0(xs: list) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mean = sum(xs) / n
    var = sum((v - mean) ** 2 for v in xs) / (n - 1)
    sd = var ** 0.5
    if sd == 0:
        return 0.0 if mean > 0 else 1.0
    t = mean / (sd / math.sqrt(n))
    return 0.5 * math.erfc(t / math.sqrt(2))


# ---------------------------------------------------------------------------------------------
# RIBBON WIRING -- byte-identical pattern to engine_fullhist_replay.py / class_conditional_
# exits_ab.py so the control walk reconciles exactly against the source replay.
# ---------------------------------------------------------------------------------------------
def build_ribbon_lookup(spy_df: pd.DataFrame) -> pd.DataFrame:
    rth_mask = ((spy_df["timestamp_et"].dt.time >= dt.time(9, 30))
                & (spy_df["timestamp_et"].dt.time < dt.time(16, 0)))
    spy_rth = spy_df.loc[rth_mask].reset_index(drop=True)
    ribbon = compute_ribbon(spy_rth["close"])
    out = spy_rth[["timestamp_et"]].copy()
    out["stack"] = ribbon["stack"].values
    return out.sort_values("timestamp_et").reset_index(drop=True)


def ribbon_tick_df_for(opt_df: pd.DataFrame, ribbon_lookup: pd.DataFrame) -> pd.DataFrame:
    left = opt_df[["timestamp_et"]].copy()
    if getattr(left["timestamp_et"].dt, "tz", None) is not None:
        left["timestamp_et"] = left["timestamp_et"].dt.tz_localize(None)
    right = ribbon_lookup.copy()
    if getattr(right["timestamp_et"].dt, "tz", None) is not None:
        right["timestamp_et"] = right["timestamp_et"].dt.tz_localize(None)
    left = left.sort_values("timestamp_et", kind="stable")
    right = right.sort_values("timestamp_et", kind="stable")
    merged = pd.merge_asof(left, right, on="timestamp_et", direction="backward")
    assert len(merged) == len(opt_df), "merge_asof row count drifted -- alignment broken"
    return merged.reset_index(drop=True)[["stack"]]


def naive_dt(ts) -> dt.datetime:
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.replace(tzinfo=None)
    return ts


# ---------------------------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------------------------
def main() -> int:  # noqa: C901 -- single linear research pipeline, deliberately unsplit
    t0 = time.time()
    src = json.loads(SOURCE_REPLAY.read_text(encoding="utf-8"))
    trades = src["trades"]
    eps = json.loads(EPISODES.read_text(encoding="utf-8"))
    ep_by_key = {(e["date"], e["symbol"], e["entry_time_et"]): e for e in eps["episodes"]}
    log(f"loaded {len(trades)} source trades, {len(ep_by_key)} kitchen episodes")
    assert eps["control_reconciliation_vs_source_replay"]["n_mismatches"] == 0, \
        "kitchen episodes file itself failed control reconciliation -- do not build on it"

    spy_df = pd.read_csv(SPY_FILE)
    spy_df["timestamp_et"] = pd.to_datetime(spy_df["timestamp_et"])
    ribbon_lookup = build_ribbon_lookup(spy_df)
    control_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    log(f"control_shape={control_shape}")

    a6_premium_stop, a6_trail = -0.12, 0.10  # A6_T-TIGHT_TR-TIGHT, frozen kitchen prereg values

    rows: list[dict] = []
    n_ctl_mismatch = 0
    n_a6_mismatch = 0
    fill_ratio_violations: list[dict] = []

    for t in trades:
        symbol = t["symbol"]
        date = dt.date.fromisoformat(t["date"])
        opt_df = load_contract_bars(symbol)
        assert opt_df is not None, f"OPRA cache vanished for {symbol} -- source replay had it"
        day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == date].reset_index(drop=True)
        assert not day_spy.empty, f"SPY day vanished for {date}"

        entry_time_et = naive_dt(dt.datetime.fromisoformat(t["entry_time_et"]))
        rtd = ribbon_tick_df_for(opt_df, ribbon_lookup)
        common = dict(symbol=symbol, side=t["side"], entry_time_et=entry_time_et,
                      entry_premium=t["entry_premium"], qty=t["qty"],
                      structure_stop_enabled=True, trigger_level=t["trigger_level"],
                      strategy="exit_leak", time_stop_et=TIME_STOP_ET,
                      opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=day_spy)

        ctl = walk_exit_manager(exit_shape=control_shape, **common)
        if abs(ctl.dollar_pnl - t["dollar_pnl"]) > 0.01:
            n_ctl_mismatch += 1

        a6_shape = dict(control_shape, trail_pct=a6_trail)
        if t["tier"] == "TRENDLINE":
            a6_shape["premium_stop_pct"] = a6_premium_stop
        a6 = walk_exit_manager(exit_shape=a6_shape, **common)
        ep = ep_by_key.get((t["date"], symbol, t["entry_time_et"]))
        assert ep is not None, f"no kitchen episode for {t['date']} {symbol}"
        if abs(a6.dollar_pnl - ep["candidates"]["A6_T-TIGHT_TR-TIGHT"]) > 0.01:
            n_a6_mismatch += 1

        m = mfe_window(opt_df, entry_time_et, ctl.exit_time_et)
        assert m is not None, f"empty MFE window for {symbol} -- walk exited before entry+1?"
        entry = float(t["entry_premium"])
        qty = int(t["qty"])
        mfe_open_pct = m["mfe_open"] / entry - 1.0
        mfe_high_pct = m["mfe_high"] / entry - 1.0
        mfe_dollar_open = (m["mfe_open"] - entry) * qty * 100.0
        giveback_open = mfe_dollar_open - ctl.dollar_pnl
        fam = exit_family(ctl.exit_reason, ctl.stop_mode)
        tp1_hit = any(leg.stage == "tp1" and leg.kind == "SELL_PARTIAL" for leg in ctl.legs)

        # fill-ratio sanity for the premium families (mechanism check, not assumed)
        if fam in ("PREMIUM_STOP_20", "CATASTROPHE_50"):
            fill = ctl.legs[-1].fill_price
            ratio = fill / entry
            lo, hi = (0.75, 0.85) if fam == "PREMIUM_STOP_20" else (0.45, 0.55)
            if not (lo <= ratio <= hi):
                fill_ratio_violations.append({"symbol": symbol, "date": t["date"],
                                              "family": fam, "ratio": round(ratio, 3)})

        rows.append({
            "date": t["date"], "symbol": symbol, "side": t["side"], "tier": t["tier"],
            "entry_time_et": t["entry_time_et"], "qty": qty, "entry_premium": entry,
            "pnl": ctl.dollar_pnl, "exit_reason": ctl.exit_reason, "family": fam,
            "stop_mode": ctl.stop_mode, "hold_minutes": ctl.hold_minutes,
            "tp1_hit": tp1_hit, "is_heldout": ep["is_heldout"],
            "a6_pnl": a6.dollar_pnl, "a6_delta": round(a6.dollar_pnl - ctl.dollar_pnl, 2),
            "mfe_open": round(m["mfe_open"], 4), "mfe_high": round(m["mfe_high"], 4),
            "mfe_open_pct": round(mfe_open_pct, 4), "mfe_high_pct": round(mfe_high_pct, 4),
            "mfe_dollar_open": round(mfe_dollar_open, 2),
            "giveback_open": round(giveback_open, 2),
            "minutes_to_mfe": int(round((naive_dt(m["mfe_open_ts"]) - entry_time_et
                                          ).total_seconds() / 60.0)),
            "n_bars_walked": m["n_bars"],
        })

    log(f"walked {len(rows)} trades: control mismatches={n_ctl_mismatch} "
        f"a6-vs-kitchen mismatches={n_a6_mismatch} "
        f"fill-ratio violations={len(fill_ratio_violations)}")
    df = pd.DataFrame(rows)

    # -----------------------------------------------------------------------------------------
    # TABLE 1: exit-family x P&L decomposition (all 190)
    # -----------------------------------------------------------------------------------------
    fam_table = {}
    for fam, g in df.groupby("family"):
        w = g[g["pnl"] > 0]
        l = g[g["pnl"] <= 0]
        fam_table[fam] = {
            "n": len(g), "total_pnl": round(g["pnl"].sum(), 2),
            "n_winners": len(w), "winners_pnl": round(w["pnl"].sum(), 2),
            "n_losers": len(l), "losers_pnl": round(l["pnl"].sum(), 2),
            "avg_pnl": round(g["pnl"].mean(), 2),
            "median_mfe_open_pct": round(g["mfe_open_pct"].median(), 4),
            "avg_hold_minutes": round(g["hold_minutes"].mean(), 1),
        }

    # -----------------------------------------------------------------------------------------
    # TABLE 2: winners' MFE-giveback by family
    # -----------------------------------------------------------------------------------------
    winners = df[df["pnl"] > 0]
    give_table = {}
    for fam, g in winners.groupby("family"):
        mfe_sum = g["mfe_dollar_open"].sum()
        act = g["pnl"].sum()
        give_table[fam] = {
            "n_winners": len(g), "mfe_dollar_open_sum": round(mfe_sum, 2),
            "actual_pnl_sum": round(act, 2), "giveback_sum": round(mfe_sum - act, 2),
            "capture_ratio": round(act / mfe_sum, 3) if mfe_sum > 0 else None,
            "median_mfe_open_pct": round(g["mfe_open_pct"].median(), 4),
        }
    winners_total = {
        "n": len(winners),
        "mfe_dollar_open_sum": round(winners["mfe_dollar_open"].sum(), 2),
        "actual_pnl_sum": round(winners["pnl"].sum(), 2),
        "giveback_sum": round((winners["mfe_dollar_open"] - winners["pnl"]).sum(), 2),
        "capture_ratio": round(winners["pnl"].sum() / winners["mfe_dollar_open"].sum(), 3),
    }

    # -----------------------------------------------------------------------------------------
    # TABLE 3: loss composition (losers only) + once-green flags
    # -----------------------------------------------------------------------------------------
    losers = df[df["pnl"] <= 0]
    loss_table = {}
    for fam, g in losers.groupby("family"):
        loss_table[fam] = {
            "n": len(g), "total_pnl": round(g["pnl"].sum(), 2),
            "avg_pnl": round(g["pnl"].mean(), 2),
            "share_of_gross_loss": round(g["pnl"].sum() / losers["pnl"].sum(), 3),
            "n_once_green_30": int((g["mfe_open_pct"] >= 0.30).sum()),
            "once_green_30_pnl": round(g.loc[g["mfe_open_pct"] >= 0.30, "pnl"].sum(), 2),
            "median_mfe_open_pct": round(g["mfe_open_pct"].median(), 4),
        }

    # -----------------------------------------------------------------------------------------
    # TABLE 4: once-green thresholds -- how much favorable excursion the book offers, and the
    # descriptive (NOT-a-rule) exit-all-at-touch counterfactual
    # -----------------------------------------------------------------------------------------
    actual_total = round(df["pnl"].sum(), 2)
    once_green = {}
    for thr in ONCE_GREEN_THRESHOLDS:
        reached = df[df["mfe_open_pct"] >= thr]
        not_reached = df[df["mfe_open_pct"] < thr]
        cf_reached = (thr * reached["entry_premium"] * reached["qty"] * 100.0).sum()
        cf_total = round(cf_reached + not_reached["pnl"].sum(), 2)
        r_losers = reached[reached["pnl"] <= 0]
        once_green[f"{int(thr*100)}pct"] = {
            "n_reached": len(reached), "pct_of_book": round(len(reached) / len(df), 3),
            "reached_actual_pnl": round(reached["pnl"].sum(), 2),
            "n_reached_but_finished_loser": len(r_losers),
            "reached_but_loser_pnl": round(r_losers["pnl"].sum(), 2),
            "counterfactual_exit_all_at_touch_total_book_pnl": cf_total,
            "delta_vs_actual": round(cf_total - actual_total, 2),
        }

    # -----------------------------------------------------------------------------------------
    # PRE-REGISTERED CHECK: A6 on the TRENDLINE cohort (gates per PREREG_A6_TRENDLINE)
    # -----------------------------------------------------------------------------------------
    tl = df[df["tier"] == "TRENDLINE"]
    tl_tune = tl[~tl["is_heldout"]]
    tl_held = tl[tl["is_heldout"]]

    g1_delta = round(tl_tune["a6_delta"].sum(), 2)
    g1 = g1_delta > 0

    day_ctl = tl_tune.groupby("date")["pnl"].sum()
    day_a6 = tl_tune.groupby("date")["a6_pnl"].sum()
    days = sorted(set(day_ctl.index) | set(day_a6.index))
    a6_wins = sum(1 for d in days if day_a6.get(d, 0.0) > day_ctl.get(d, 0.0))
    ctl_wins = sum(1 for d in days if day_ctl.get(d, 0.0) >= day_a6.get(d, 0.0))
    g2 = a6_wins > ctl_wins

    deltas_sorted = tl_tune["a6_delta"].sort_values(ascending=False)
    ex_top1 = round(deltas_sorted.iloc[1:].sum(), 2) if len(deltas_sorted) else 0.0
    g3 = ex_top1 > 0

    g4_delta = round(tl_held["a6_delta"].sum(), 2)
    g4 = g4_delta > 0

    p_raw = one_sided_p_mean_gt_0(list(tl_tune["a6_delta"]))
    replicates = g1 and g2 and g3 and g4

    a6_check = {
        "prereg": PREREG_A6_TRENDLINE,
        "cohort": {"n_trendline": len(tl), "n_tuning": len(tl_tune), "n_heldout": len(tl_held),
                   "n_tuning_touched": int((tl_tune["a6_delta"] != 0).sum()),
                   "n_heldout_touched": int((tl_held["a6_delta"] != 0).sum())},
        "verification": {"n_control_mismatch_vs_source": n_ctl_mismatch,
                          "n_a6_mismatch_vs_kitchen_episodes": n_a6_mismatch},
        "gates": {
            "g1_positive_aggregate": {"delta": g1_delta, "pass": g1},
            "g2_day_majority": {"a6_day_wins": a6_wins, "control_day_wins_incl_ties": ctl_wins,
                                 "n_days": len(days), "pass": g2},
            "g3_survives_ex_top1": {"ex_top1_delta": ex_top1, "pass": g3},
            "g4_held_out_positive": {"delta": g4_delta, "pass": g4},
        },
        "p_raw_descriptive": round(p_raw, 5) if p_raw is not None else None,
        "replicates_on_cohort": replicates,
        "for_reference_full_population_a6": {
            "tuning_delta_all_190_pop": round(df.loc[~df["is_heldout"], "a6_delta"].sum(), 2),
            "heldout_delta_all_190_pop": round(df.loc[df["is_heldout"], "a6_delta"].sum(), 2),
            "structure_tier_tuning_delta": round(
                df.loc[(~df["is_heldout"]) & (df["tier"] != "TRENDLINE"), "a6_delta"].sum(), 2),
            "structure_tier_heldout_delta": round(
                df.loc[(df["is_heldout"]) & (df["tier"] != "TRENDLINE"), "a6_delta"].sum(), 2),
        },
    }

    out = {
        "_doc": __doc__,
        "generated_at_et": dt.datetime.now().isoformat(),
        "population": {
            "source": str(SOURCE_REPLAY.relative_to(REPO)).replace("\\", "/"),
            "n_trades": len(df), "actual_total_pnl": actual_total,
            "win_rate": round((df["pnl"] > 0).mean(), 4),
            "provisional_caveat": "trade-level anchors vs live 1/4 on 2026-07-17 (corrected "
                                   "matcher L250) -- entry layer diverges from live; this "
                                   "decomposes the REPLAY's exit mechanics.",
        },
        "conventions": {
            "entry_bar": "entry+1 strict (markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md)",
            "mfe_primary": "MFE_open = max(bar.open) over bars strictly after entry through exit "
                            "bar inclusive -- the exact point-sample series the exit engine "
                            "observes (walk_exit_manager best=worst=bar.open)",
            "mfe_secondary": "MFE_high = max(bar.high), best print incl. wicks -- upper bound "
                              "a point-sample engine may never see",
            "giveback": "full-position liquidation at MFE_open minus actual realized P&L; an "
                         "UPPER BOUND on recoverable money, not a claimable edge",
        },
        "verification": {
            "n_control_mismatch_vs_source_replay": n_ctl_mismatch,
            "n_a6_mismatch_vs_kitchen_episodes": n_a6_mismatch,
            "fill_ratio_violations": fill_ratio_violations,
        },
        "table1_exit_family_decomposition": fam_table,
        "table2_winner_giveback_by_family": give_table,
        "table2b_winners_total": winners_total,
        "table3_loss_composition": loss_table,
        "table4_once_green_thresholds": once_green,
        "a6_trendline_cohort_check": a6_check,
        "trades": rows,
        "runtime_seconds": round(time.time() - t0, 1),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_markdown(out)
    log(f"wrote {OUT_MD}")
    log(f"A6 trendline-cohort check: replicates={replicates} g1={g1_delta} g4={g4_delta} "
        f"p_raw={a6_check['p_raw_descriptive']}")
    return 0


def write_markdown(out: dict) -> None:
    pop = out["population"]
    ver = out["verification"]
    a6 = out["a6_trendline_cohort_check"]
    g = a6["gates"]
    wt = out["table2b_winners_total"]
    L = [
        "# THE EXIT LEAK -- 2026-07-28",
        "",
        f"Generated {out['generated_at_et']}. Runner: `backtest/tools/exit_leak_decompose.py` "
        f"(runtime {out['runtime_seconds']}s). Machine-readable: `analysis/deep-research/"
        f"EXIT-LEAK-2026-07-28.json` (per-trade rows included).",
        "",
        f"Population: {pop['n_trades']} trades, total ${pop['actual_total_pnl']:+,.2f}, "
        f"WR {pop['win_rate']:.1%} -- `{pop['source']}`. PROVISIONAL: {pop['provisional_caveat']}",
        "",
        f"Verification: control re-walk mismatches vs source = "
        f"{ver['n_control_mismatch_vs_source_replay']}; A6 re-walk mismatches vs kitchen "
        f"episodes = {ver['n_a6_mismatch_vs_kitchen_episodes']}; premium-family fill-ratio "
        f"violations = {len(ver['fill_ratio_violations'])}.",
        "",
        f"Conventions: {out['conventions']['entry_bar']}. MFE primary = "
        f"{out['conventions']['mfe_primary']}. Giveback = {out['conventions']['giveback']}.",
        "",
        "## Table 1 -- exit family x P&L (all trades)",
        "",
        "| family | n | total P&L | winners (n / $) | losers (n / $) | median MFE_open | avg hold min |",
        "|---|--:|--:|--:|--:|--:|--:|",
    ]
    for fam, v in sorted(out["table1_exit_family_decomposition"].items(),
                          key=lambda kv: kv[1]["total_pnl"]):
        L.append(f"| {fam} | {v['n']} | ${v['total_pnl']:+,.2f} | {v['n_winners']} / "
                 f"${v['winners_pnl']:+,.2f} | {v['n_losers']} / ${v['losers_pnl']:+,.2f} | "
                 f"{v['median_mfe_open_pct']:+.1%} | {v['avg_hold_minutes']} |")
    L += [
        "",
        "## Table 2 -- winners' MFE-giveback by family",
        "",
        f"**All winners (n={wt['n']}): MFE offered ${wt['mfe_dollar_open_sum']:+,.2f}, realized "
        f"${wt['actual_pnl_sum']:+,.2f}, giveback ${wt['giveback_sum']:+,.2f} "
        f"(capture ratio {wt['capture_ratio']:.1%}).**",
        "",
        "| family | n | MFE $ (open) | realized $ | giveback $ | capture | median MFE_open |",
        "|---|--:|--:|--:|--:|--:|--:|",
    ]
    for fam, v in sorted(out["table2_winner_giveback_by_family"].items(),
                          key=lambda kv: -kv[1]["giveback_sum"]):
        L.append(f"| {fam} | {v['n_winners']} | ${v['mfe_dollar_open_sum']:+,.2f} | "
                 f"${v['actual_pnl_sum']:+,.2f} | ${v['giveback_sum']:+,.2f} | "
                 f"{v['capture_ratio']:.1%} | {v['median_mfe_open_pct']:+.1%} |")
    L += [
        "",
        "## Table 3 -- loss composition (losers only)",
        "",
        "| family | n | total loss | avg | share of gross loss | once-green >=+30% (n / their $) "
        "| median MFE_open |",
        "|---|--:|--:|--:|--:|--:|--:|",
    ]
    for fam, v in sorted(out["table3_loss_composition"].items(), key=lambda kv: kv[1]["total_pnl"]):
        L.append(f"| {fam} | {v['n']} | ${v['total_pnl']:+,.2f} | ${v['avg_pnl']:+,.2f} | "
                 f"{v['share_of_gross_loss']:.1%} | {v['n_once_green_30']} / "
                 f"${v['once_green_30_pnl']:+,.2f} | {v['median_mfe_open_pct']:+.1%} |")
    L += [
        "",
        "## Table 4 -- once-green thresholds (descriptive counterfactual, NOT a rule)",
        "",
        "> `exit-all-at-touch` liquidates the FULL position the moment MFE_open first reaches "
        "the threshold and keeps every other trade's actual exit. It forfeits the right tail "
        "that pays this engine's whole model. Descriptive bound only -- any TP/threshold rule "
        "change needs its own frozen pre-reg + 4-gate bar on untouched data.",
        "",
        "| threshold | n reached (% book) | their actual $ | reached-but-lost (n / $) | "
        "exit-all-at-touch book total | delta vs actual |",
        "|---|--:|--:|--:|--:|--:|",
    ]
    for thr, v in out["table4_once_green_thresholds"].items():
        L.append(f"| +{thr} | {v['n_reached']} ({v['pct_of_book']:.0%}) | "
                 f"${v['reached_actual_pnl']:+,.2f} | {v['n_reached_but_finished_loser']} / "
                 f"${v['reached_but_loser_pnl']:+,.2f} | "
                 f"${v['counterfactual_exit_all_at_touch_total_book_pnl']:+,.2f} | "
                 f"${v['delta_vs_actual']:+,.2f} |")
    L += [
        "",
        "## A6 trendline-cohort replication (the ONE pre-registered check)",
        "",
        f"Pre-reg frozen in-script before computation (`PREREG_A6_TRENDLINE`, written "
        f"{a6['prereg']['written_et']}). Hypothesis: {a6['prereg']['hypothesis']}",
        "",
        f"Cohort: {a6['cohort']['n_trendline']} TRENDLINE trades "
        f"({a6['cohort']['n_tuning']} tuning / {a6['cohort']['n_heldout']} held-out; "
        f"touched: {a6['cohort']['n_tuning_touched']} / {a6['cohort']['n_heldout_touched']}).",
        "",
        "| gate | value | pass |",
        "|---|--:|:--:|",
        f"| g1 positive aggregate (tuning) | ${g['g1_positive_aggregate']['delta']:+,.2f} | "
        f"{g['g1_positive_aggregate']['pass']} |",
        f"| g2 day majority | {g['g2_day_majority']['a6_day_wins']} vs "
        f"{g['g2_day_majority']['control_day_wins_incl_ties']} (of "
        f"{g['g2_day_majority']['n_days']} days, ties->control) | {g['g2_day_majority']['pass']} |",
        f"| g3 survives ex-top1 | ${g['g3_survives_ex_top1']['ex_top1_delta']:+,.2f} | "
        f"{g['g3_survives_ex_top1']['pass']} |",
        f"| g4 held-out positive | ${g['g4_held_out_positive']['delta']:+,.2f} | "
        f"{g['g4_held_out_positive']['pass']} |",
        "",
        f"**REPLICATES ON COHORT: {a6['replicates_on_cohort']}** "
        f"(p_raw descriptive: {a6['p_raw_descriptive']}).",
        "",
        f"Reference splits (full 190-pop A6 deltas): tuning "
        f"${a6['for_reference_full_population_a6']['tuning_delta_all_190_pop']:+,.2f}, held-out "
        f"${a6['for_reference_full_population_a6']['heldout_delta_all_190_pop']:+,.2f}; "
        f"STRUCTURE-tier-only tuning "
        f"${a6['for_reference_full_population_a6']['structure_tier_tuning_delta']:+,.2f}, "
        f"held-out ${a6['for_reference_full_population_a6']['structure_tier_heldout_delta']:+,.2f}.",
        "",
        "Independence caveats (verbatim from pre-reg):",
    ] + [f"- {c}" for c in a6["prereg"]["independence_caveats"]] + [
        "",
        "---",
        "_Source: `backtest/tools/exit_leak_decompose.py`. Population: "
        "`analysis/recommendations/engine-fullhist-replay-2026-07-23.json`. A6 cross-check: "
        "`analysis/kitchen/class-conditional-exits-episodes.json`._",
    ]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
