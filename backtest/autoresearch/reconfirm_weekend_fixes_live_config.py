"""RE-CONFIRM the 3 weekend BEARISH_REJECTION fixes on the CURRENT LIVE config.

WHY THIS EXISTS (the vwap-pullback / landmine lesson): a validation is only valid on
the exit config it was run on. The 3 weekend scorecards were each run on a
research-ISOLATED exit config that does NOT match what params.json runs live today:

  * regime-chandelier-sweep.json  -> baseline used tp1_premium 0.30, tp1_qty_fraction
        0.50, premium_stop -0.99, chandelier ON. LIVE is tp1 0.50 @ 0.667, bear stop
        -0.50, chandelier ON (trail 20%). The 20%->15% A/B is the DELTA; must re-run on
        live exits to confirm the delta survives.
  * bearish-rejection-quality-validation.json (VIX-falling skip) and
    bearish-rejection-tier-recalibration.json (confidence-tier cap) -> the BRM real-fills
        were simulated with premium_stop=-0.99 and CHANDELIER OFF (no profit_lock_* args)
        + default tp1 0.30 @ 0.667-from-simulator. LIVE is chandelier ON + tp1 0.50 @
        0.667 + bear stop -0.50. Must re-check the bucket sign-stability under live exits.

This script does NOT change any production knob (Rule 9 / propose-only). It re-runs the
three candidates on the LIVE config and reports re-confirmed IS/OOS/WF/sub-window/anchor
numbers so the conductor can ship the ones that still meet OP-22.

LIVE CONFIG (read from automation/state/params.json at runtime; pinned defaults below for
the record):
  premium_stop_pct_bear = -0.50 (catastrophe cap; chart-stop primary)
  premium_stop_pct (bull/generic) = -0.50
  tp1_premium_pct = 0.50 ; tp1_qty_fraction = 0.667 ; runner_target = 2.5
  chandelier: profit_lock_mode='trailing', threshold +5%, stop_offset +10%, trail 20%
  level_stop_buffer = 0.50 ; time_stop 20 min before close ; per_trade_risk_cap 0.30 (Safe)
  live gates: midday_trendline_gate, block_level_rejection, block_elite_bull[0,25),
              entry_bar_body_pct_min 0.20, block_bull_1100_1200, vix thresholds.

PART A (candidate #1, chandelier 20->15) — FULL-ENGINE via lib.orchestrator.run_backtest.
  The chandelier (v15_profit_lock_trail_pct) is a GLOBAL live exit knob applied to EVERY
  production trade, so the authoritative re-confirm runs the WHOLE live engine (all gates,
  chandelier ON, real fills) with trail=0.20 (current live baseline) vs trail=0.15
  (candidate) over IS/OOS + walk-forward + sub-windows, BOTH the Safe per-tier strike and
  the Bold ITM2 strike. OP-22 gate: OOS+ AND WF>=0.70 AND SW_hurt<=1 AND anchor-no-regress.

PART B (candidates #2 VIX-falling-skip + #3 confidence-tier) — BRM watcher real-fills with
  LIVE exits. These two are refinements to the bearish_rejection_morning_watcher (still
  WATCH_ONLY, op21 0/3 — NOT yet in the live gate-based trading path), so they are
  validated on the isolated BRM real-fills path. The ONLY change vs the weekend scorecard
  is the exit config: we now layer the LIVE exits (chandelier ON + tp1 0.50@0.667 + bear
  stop -0.50) instead of chart-stop-only/no-chandelier. We then re-check:
    #3 tier: is HIGH still <= LOW on real-fills exp (the inversion), and does capping HIGH
        (no size-up) still help vs the inverted 1.5x? (ATM = Safe-anchor strike, ITM2 = Bold)
    #2 VIX-skip: is vix_character=='falling' still sign-stable NEGATIVE across both OOS
        splits under live exits? (do-no-harm tail trim)

Usage (run from backtest/ with the venv interpreter):
  python -m autoresearch.reconfirm_weekend_fixes_live_config \
      --out ../analysis/recommendations/weekend-fixes-live-reconfirm-2026-06-19.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))

import pandas as pd  # noqa: E402

# Reuse the BRM firing pipeline + VIX-character tagger from the weekend script (single
# source of truth — no detector logic duplicated).
from autoresearch import stratify_bearish_rejection_quality as sbrq  # noqa: E402
from autoresearch import validate_breakout_family as vbf  # noqa: E402
from lib.orchestrator import run_backtest  # noqa: E402

ANCHORS = vbf.ANCHORS  # {date: "WIN"|"LOSS"}

MASTER_SPY = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
MASTER_VIX = ROOT / "backtest" / "data" / "vix_5m_2025-01-01_2026-06-16.csv"
PARAMS_PATH = ROOT / "automation" / "state" / "params.json"

# Real-fills window cap (OPRA cache ends 2026-05-29).
RF_END = dt.date(2026, 5, 29)

# IS/OOS split used by the live exit-param sweep (exit_param_chandelier_on_sweep.py) —
# keep the SAME boundary so this is comparable to prior live-config sweeps.
IS_START = dt.date(2025, 1, 2)
IS_END = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END = RF_END  # cap OOS at OPRA coverage for real-fills authority

SUBWINDOWS = [
    ("W1_2025H1", dt.date(2025, 1, 2), dt.date(2025, 6, 30)),
    ("W2_2025Q3", dt.date(2025, 7, 1), dt.date(2025, 9, 30)),
    ("W3_2025Q4", dt.date(2025, 10, 1), dt.date(2025, 12, 31)),
    ("W4_2026H1", dt.date(2026, 1, 2), OOS_END),
]

# Walk-forward folds (same quarterly grid the weekend chandelier scorecard used).
WF_FOLDS = [
    ("2025Q1", dt.date(2025, 1, 1), dt.date(2025, 4, 1)),
    ("2025Q2", dt.date(2025, 4, 1), dt.date(2025, 7, 1)),
    ("2025Q3", dt.date(2025, 7, 1), dt.date(2025, 10, 1)),
    ("2025Q4", dt.date(2025, 10, 1), dt.date(2026, 1, 1)),
    ("2026Q1", dt.date(2026, 1, 1), dt.date(2026, 4, 1)),
    ("2026Q2", dt.date(2026, 4, 1), OOS_END),
]


def _load_live_params() -> dict:
    return json.loads(PARAMS_PATH.read_text(encoding="utf-8"))


def _live_engine_config(p: dict, strike_offset: int) -> dict:
    """Build the run_backtest kwargs that mirror the CURRENT live Safe config from
    params.json. strike_offset selects the strike class (ATM=0 for the anchor read /
    Safe-mid-tier proxy, -2 = ITM2/Bold class). All gate flags read from params."""
    return dict(
        use_real_fills=True,
        setup="BEARISH_REJECTION_RIDE_THE_RIBBON",
        # entry window [09:35, 15:00), no mid-day blackout (v15.1 live)
        no_trade_before=dt.time(9, 35),
        no_trade_window=None,
        # asymmetric exits — LIVE values
        premium_stop_pct_bear=p["premium_stop_pct_bear"],          # -0.50 catastrophe cap
        premium_stop_pct_bull=p.get("premium_stop_pct", -0.50),
        premium_stop_pct=p.get("premium_stop_pct", -0.50),
        tp1_premium_pct=p["tp1_premium_pct"],                      # 0.50
        tp1_qty_fraction=p["tp1_qty_fraction"],                    # 0.667
        runner_target_premium_pct=p["runner_max_premium_pct"],    # 2.5
        level_stop_buffer_dollars=p["chart_stop_buffer_dollars"], # 0.50
        time_stop_minutes_before_close=p["time_stop_minutes_before_close"],  # 20
        per_trade_risk_cap_pct=p["per_trade_risk_cap_pct"],       # 0.30 Safe
        strike_offset=strike_offset,
        strike_offset_bear=strike_offset,
        # chandelier ON — LIVE
        profit_lock_threshold_pct=p["v15_profit_lock_threshold_pct"],   # 0.05
        profit_lock_stop_offset_pct=0.10,
        profit_lock_mode=p["v15_profit_lock_mode"],                     # 'trailing'
        profit_lock_trail_pct=p["v15_profit_lock_trail_pct"],          # 0.20 (baseline)
        # live gate flags
        midday_trendline_gate=p.get("midday_trendline_gate", True),
        midday_trendline_gate_start_minutes=690,
        block_level_rejection=p.get("block_level_rejection", True),
        block_elite_bull=p.get("block_elite_bull", True),
        block_elite_bull_vix_low=p.get("block_elite_bull_vix_low", 0.0),
        block_elite_bull_vix_high=p.get("block_elite_bull_vix_high", 25.0),
        min_triggers_bear=p["filter_10_min_triggers_bear"],
        min_triggers_bull=p["filter_10_min_triggers_bull"],
        f9_vol_mult=p["filter_9_vol_multiplier"],
    )


def _bt_pnl(spy_df, vix_df, cfg, start, end) -> tuple[int, float, dict]:
    """run_backtest -> (n_trades, total_pnl, anchor_pnl_by_day)."""
    res = run_backtest(spy_df, vix_df, start_date=start, end_date=end, **cfg)
    trades = res.trades
    pnl = sum(t.dollar_pnl for t in trades)
    anchor = defaultdict(float)
    anchor_dates = {d.isoformat() for d in ANCHORS}
    for t in trades:
        # TradeFill carries entry time; derive its date string.
        et = getattr(t, "entry_time_et", None) or getattr(t, "entry_time", None)
        try:
            ds = pd.Timestamp(et).date().isoformat()
        except Exception:
            ds = None
        if ds in anchor_dates:
            anchor[ds] += t.dollar_pnl
    return len(trades), round(pnl, 2), dict(anchor)


def _anchor_edge(anchor_pnl: dict) -> float:
    win = sum(anchor_pnl.get(d.isoformat(), 0.0) for d in ANCHORS if ANCHORS[d] == "WIN")
    loss = sum(max(0.0, -anchor_pnl.get(d.isoformat(), 0.0))
               for d in ANCHORS if ANCHORS[d] == "LOSS")
    return round(win - loss, 2)


# ══════════════════════════════════════════════════════════════════════════════
# PART A — chandelier 20% -> 15% on the FULL LIVE engine (candidate #1)
# ══════════════════════════════════════════════════════════════════════════════
def part_a_chandelier(spy_df, vix_df, p: dict) -> dict:
    out = {"candidate": "chandelier_trail_20_to_15",
           "method": "full-engine run_backtest on LIVE config (all gates, chandelier ON, real fills)",
           "baseline_trail": p["v15_profit_lock_trail_pct"], "candidate_trail": 0.15,
           "strikes": {}}
    for slabel, offset in (("ATM_safe_anchor", 0), ("ITM2_bold", -2)):
        base_cfg = _live_engine_config(p, offset)            # trail 0.20 (live baseline)
        cand_cfg = {**base_cfg, "profit_lock_trail_pct": 0.15}

        b_is_n, b_is, b_is_anc = _bt_pnl(spy_df, vix_df, base_cfg, IS_START, IS_END)
        c_is_n, c_is, c_is_anc = _bt_pnl(spy_df, vix_df, cand_cfg, IS_START, IS_END)
        b_oos_n, b_oos, b_oos_anc = _bt_pnl(spy_df, vix_df, base_cfg, OOS_START, OOS_END)
        c_oos_n, c_oos, c_oos_anc = _bt_pnl(spy_df, vix_df, cand_cfg, OOS_START, OOS_END)

        is_d = round(c_is - b_is, 2)
        oos_d = round(c_oos - b_oos, 2)
        n_is = b_is_n or 1
        n_oos = b_oos_n or 1
        wf = round((oos_d / n_oos) / (is_d / n_is), 3) if abs(is_d) > 1e-9 else None

        # sub-windows
        sw_rows = []
        sw_hurt = 0
        for wname, ws, we in SUBWINDOWS:
            _, b_sw, _ = _bt_pnl(spy_df, vix_df, base_cfg, ws, we)
            _, c_sw, _ = _bt_pnl(spy_df, vix_df, cand_cfg, ws, we)
            d = round(c_sw - b_sw, 2)
            tag = "HELP" if d > 50 else ("HURT" if d < -50 else "FLAT")
            if tag == "HURT":
                sw_hurt += 1
            sw_rows.append({"window": wname, "base": b_sw, "cand": c_sw, "delta": d, "tag": tag})

        # walk-forward folds (delta sign-stability)
        wf_rows = []
        n_stable = n_folds = 0
        for fname, fs, fe in WF_FOLDS:
            bn, b_f, _ = _bt_pnl(spy_df, vix_df, base_cfg, fs, fe)
            cn, c_f, _ = _bt_pnl(spy_df, vix_df, cand_cfg, fs, fe)
            if cn == 0 and bn == 0:
                continue
            n_folds += 1
            d = round(c_f - b_f, 2)
            stable = d >= -1e-6
            n_stable += int(stable)
            wf_rows.append({"fold": fname, "n": cn, "base": b_f, "cand": c_f,
                            "delta": d, "cand_ge_base": stable})

        anchor_ok = _anchor_edge(c_is_anc) >= _anchor_edge(b_is_anc) - 1e-6 and \
            _anchor_edge(c_oos_anc) >= _anchor_edge(b_oos_anc) - 1e-6
        oos_pos = oos_d > 0
        wf_ok = wf is not None and wf >= 0.70
        sw_ok = sw_hurt <= 1
        gate = {"oos_positive": oos_pos, "wf_ge_0.70": wf_ok, "wf": wf,
                "sw_hurt_le_1": sw_ok, "sw_hurt": sw_hurt,
                "anchor_no_regression": anchor_ok,
                "all_wf_folds_stable": n_folds > 0 and n_stable == n_folds}
        gate["SHIP"] = bool(oos_pos and wf_ok and sw_ok and anchor_ok)

        out["strikes"][slabel] = {
            "baseline_IS": {"n": b_is_n, "pnl": b_is, "anchor_edge": _anchor_edge(b_is_anc)},
            "candidate_IS": {"n": c_is_n, "pnl": c_is, "anchor_edge": _anchor_edge(c_is_anc)},
            "IS_delta": is_d,
            "baseline_OOS": {"n": b_oos_n, "pnl": b_oos, "anchor_edge": _anchor_edge(b_oos_anc)},
            "candidate_OOS": {"n": c_oos_n, "pnl": c_oos, "anchor_edge": _anchor_edge(c_oos_anc)},
            "OOS_delta": oos_d,
            "sub_windows": sw_rows,
            "walk_forward": {"n_folds": n_folds, "n_stable": n_stable, "folds": wf_rows},
            "gate": gate,
        }
    return out


# ══════════════════════════════════════════════════════════════════════════════
# PART B — VIX-skip (#2) + confidence-tier (#3) on BRM real-fills with LIVE exits
# ══════════════════════════════════════════════════════════════════════════════
# LIVE exit kwargs threaded into simulate_trade_real for the BRM isolated path.
def _live_exit_kwargs(p: dict) -> dict:
    return dict(
        premium_stop_pct=p["premium_stop_pct_bear"],            # -0.50 (was -0.99 in scorecard)
        tp1_premium_pct=p["tp1_premium_pct"],                   # 0.50  (was 0.30 default)
        tp1_qty_fraction=p["tp1_qty_fraction"],                 # 0.667
        runner_target_premium_pct=p["runner_max_premium_pct"], # 2.5
        level_stop_buffer_dollars=p["chart_stop_buffer_dollars"],  # 0.50
        # chandelier ON — LIVE (was OFF in the scorecard)
        profit_lock_threshold_pct=p["v15_profit_lock_threshold_pct"],
        profit_lock_stop_offset_pct=0.10,
        profit_lock_mode=p["v15_profit_lock_mode"],
        profit_lock_trail_pct=p["v15_profit_lock_trail_pct"],
    )


def _collect_brm_fires_live(exit_kwargs: dict) -> list[dict]:
    """Fire the BRM watcher across the RF window and real-fill each fire ATM + ITM2 with
    the LIVE exit config, by calling the (now exit-config-parameterized) sbrq._collect.
    Single firing pipeline — no detector logic duplicated, no rejection-level re-derivation.
    sbrq._collect with exit_kwargs threads the live chandelier/tp1/stop into
    simulate_trade_real and passes entry_vix per fire (so a regime map would bind)."""
    coll = sbrq._collect(IS_START, RF_END, do_realfills=True, exit_kwargs=exit_kwargs)
    return coll["fires"]


def _stats(rows: list[dict], pnl_key: str) -> dict:
    vals = [r for r in rows if r.get(pnl_key) is not None]
    n = len(vals)
    if n == 0:
        return {"n": 0, "wr": 0.0, "total": 0.0, "exp": 0.0, "edge_capture": 0.0,
                "n_anchor_fills": 0, "low_power": True}
    wins = sum(1 for r in vals if r[pnl_key] > 0)
    tot = sum(r[pnl_key] for r in vals)
    win_pnl = sum(r[pnl_key] for r in vals if r.get("anchor_label") == "WIN")
    loss_loss = sum(max(0.0, -r[pnl_key]) for r in vals if r.get("anchor_label") == "LOSS")
    return {"n": n, "wr": round(100 * wins / n, 1), "total": round(tot, 2),
            "exp": round(tot / n, 2), "edge_capture": round(win_pnl - loss_loss, 2),
            "n_anchor_fills": sum(1 for r in vals if r.get("is_anchor")),
            "low_power": n < 8}


def _tier_block(fires: list[dict], pnl_key: str) -> dict:
    """Re-confirm the confidence-tier inversion + the min-fix (cap HIGH, no size-up) on
    LIVE exits. The watcher confidence tiers: high/medium/low. The min fix caps HIGH at
    1.0x (vs the inverted 1.5x). We report each tier's live-exit exp + the policy A/B."""
    tiers = {c: _stats([f for f in fires if f.get("conf") == c], pnl_key)
             for c in ("high", "medium", "low")}
    # Inversion check: HIGH exp <= LOW exp (the bug).
    hi, lo = tiers["high"]["exp"], tiers["low"]["exp"]
    inversion = hi <= lo
    # Policy A/B on the same fills:
    #   OLD inverted: HIGH=1.5x MED=1.0x LOW=0.5x
    #   MIN FIX     : HIGH=1.0x MED=1.0x LOW=1.0x (cap HIGH; flat otherwise)
    mult_old = {"high": 1.5, "medium": 1.0, "low": 0.5}
    sized_old = sum((f[pnl_key] * mult_old.get(f.get("conf"), 1.0))
                    for f in fires if f.get(pnl_key) is not None)
    units_old = sum(mult_old.get(f.get("conf"), 1.0)
                    for f in fires if f.get(pnl_key) is not None)
    sized_flat = sum(f[pnl_key] for f in fires if f.get(pnl_key) is not None)
    units_flat = sum(1 for f in fires if f.get(pnl_key) is not None)
    return {
        "tiers_live_exits": tiers,
        "inversion_confirmed_on_live": inversion,
        "high_exp": hi, "low_exp": lo, "medium_exp": tiers["medium"]["exp"],
        "policy_backtest_live_exits": {
            "OLD_inverted_1.5x_HIGH": {"total_sized_pnl": round(sized_old, 2),
                                       "units": round(units_old, 1),
                                       "exp_per_unit": round(sized_old / units_old, 2) if units_old else None},
            "MIN_FIX_cap_HIGH_flat": {"total_sized_pnl": round(sized_flat, 2),
                                      "units": round(units_flat, 1),
                                      "exp_per_unit": round(sized_flat / units_flat, 2) if units_flat else None},
            "min_fix_better_than_inverted": round(sized_flat, 2) > round(sized_old, 2),
        },
    }


def _vix_skip_block(fires: list[dict], pnl_key: str) -> dict:
    """Re-confirm vix_character=='falling' sign-stable NEGATIVE across both OOS splits on
    LIVE exits, plus the skip-falling book delta."""
    filled = sorted([f for f in fires if f.get(pnl_key) is not None],
                    key=lambda f: (f["date"], f["time"]))
    if not filled:
        return {"note": "no live-exit fills under " + pnl_key}
    dates = [f["date"] for f in filled]
    median_date = dates[len(dates) // 2]
    splits = {
        "calendar_2025_vs_2026": (lambda f: f["date"] < "2026-01-01",
                                  lambda f: f["date"] >= "2026-01-01", "2026-01-01"),
        "balanced_median_date": (lambda f: f["date"] < median_date,
                                 lambda f: f["date"] >= median_date, median_date),
    }
    out = {"splits": {}}
    for sp_name, (is_pred, oos_pred, boundary) in splits.items():
        is_falling = _stats([f for f in filled if is_pred(f) and f["vix_character"] == "falling"], pnl_key)
        oos_falling = _stats([f for f in filled if oos_pred(f) and f["vix_character"] == "falling"], pnl_key)
        si, so = is_falling["exp"], oos_falling["exp"]
        if is_falling["n"] == 0 or oos_falling["n"] == 0:
            stab = "no_data_one_half"
        elif (si < 0 and so < 0):
            stab = "SAME_SIGN_NEGATIVE"
        elif (si > 0 and so > 0):
            stab = "SAME_SIGN_POSITIVE"
        else:
            stab = "SIGN_FLIP"
        out["splits"][sp_name] = {"boundary": boundary, "IS_falling": is_falling,
                                  "OOS_falling": oos_falling, "sign_stability": stab}
    # book delta
    base = _stats(filled, pnl_key)
    skip = _stats([f for f in filled if f["vix_character"] != "falling"], pnl_key)
    out["book"] = {"baseline_all": base, "skip_vix_falling": skip,
                   "exp_delta": round(skip["exp"] - base["exp"], 2),
                   "removes_anchor_win": skip["n_anchor_fills"] < base["n_anchor_fills"]}
    out["sign_stable_negative_both_splits"] = all(
        out["splits"][s]["sign_stability"] == "SAME_SIGN_NEGATIVE" for s in out["splits"])
    return out


def part_b_watcher(p: dict) -> dict:
    exit_kwargs = _live_exit_kwargs(p)
    fires = _collect_brm_fires_live(exit_kwargs)
    n_atm = sum(1 for f in fires if f.get("rf_ATM_pnl") is not None)
    n_itm2 = sum(1 for f in fires if f.get("rf_ITM2_pnl") is not None)
    out = {"candidates": ["confidence_tier_cap_HIGH (#3)", "vix_falling_skip (#2)"],
           "method": ("BRM watcher (WATCH_ONLY) real-fills re-simulated with LIVE exits "
                      "(chandelier ON trail 0.20, tp1 0.50@0.667, bear stop -0.50) instead "
                      "of the scorecard's chart-stop-only/no-chandelier config."),
           "exit_config_applied": exit_kwargs,
           "n_fires": len(fires), "n_filled_ATM": n_atm, "n_filled_ITM2": n_itm2,
           "confidence_tier": {}, "vix_falling_skip": {}}
    for label, key in (("ATM", "rf_ATM_pnl"), ("ITM2", "rf_ITM2_pnl")):
        out["confidence_tier"][label] = _tier_block(fires, key)
        out["vix_falling_skip"][label] = _vix_skip_block(fires, key)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--part", choices=["a", "b", "both"], default="both")
    a = ap.parse_args()

    p = _load_live_params()
    spy_df = pd.read_csv(MASTER_SPY)
    vix_df = pd.read_csv(MASTER_VIX)

    result = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "purpose": ("Re-confirm the 3 weekend BEARISH_REJECTION fixes on the CURRENT LIVE "
                    "params.json exit config (config-check mandatory per the vwap-pullback "
                    "landmine). Propose-only (Rule 9)."),
        "live_config_snapshot": {
            "premium_stop_pct_bear": p["premium_stop_pct_bear"],
            "tp1_premium_pct": p["tp1_premium_pct"],
            "tp1_qty_fraction": p["tp1_qty_fraction"],
            "runner_max_premium_pct": p["runner_max_premium_pct"],
            "v15_profit_lock_mode": p["v15_profit_lock_mode"],
            "v15_profit_lock_trail_pct": p["v15_profit_lock_trail_pct"],
            "v15_profit_lock_threshold_pct": p["v15_profit_lock_threshold_pct"],
            "chart_stop_buffer_dollars": p["chart_stop_buffer_dollars"],
            "per_trade_risk_cap_pct": p["per_trade_risk_cap_pct"],
        },
        "rf_window": f"{IS_START}..{RF_END} (OPRA coverage cap)",
        "is_oos_split": {"IS": f"{IS_START}..{IS_END}", "OOS": f"{OOS_START}..{OOS_END}"},
    }
    if a.part in ("a", "both"):
        result["part_a_chandelier_full_engine"] = part_a_chandelier(spy_df, vix_df, p)
    if a.part in ("b", "both"):
        result["part_b_watcher_realfills"] = part_b_watcher(p)

    print(json.dumps(result, indent=2, default=str))
    if a.out:
        outp = Path(a.out)
        if not outp.is_absolute():
            outp = (Path.cwd() / outp).resolve()
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print("wrote", outp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
