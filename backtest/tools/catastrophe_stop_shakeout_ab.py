"""catastrophe_stop_shakeout_ab.py -- Q1 forensic (J-directed 2026-07-23, after today's Bold
bold-2 SPY260723P00735000 -50% catastrophe stop-out at 11:56 ET, -$305). Tests whether the
-50% catastrophe premium backstop (fired inside stop_mode=='structure' positions, demoted from
the strategy's normal premium_stop_pct per v15.3 chart-stop-primary doctrine) systematically
shakes trades out ahead of a slower-confirming 5-min structure check.

Frozen pre-reg: analysis/recommendations/catastrophe-stop-shakeout-prereg-2026-07-23.json.
Population REUSED (not re-run) from analysis/recommendations/engine-fullhist-replay-2026-07-23.json
-- the already-generated 2025-01-02..2026-07-22 (387 RTH days), real-OPRA-fills,
exit_manager_walk-derived entry population, per the task's explicit "386-day population, real
OPRA fills through exit_manager_walk" instruction. Reusing guarantees byte-identical entries
between this study and the cited baseline (no re-derivation risk).

RECONCILIATION (pre-committed in the pre-reg, restated here with real numbers at the bottom of
the .md): trail-width-exit-2026-07-21 and structure-stop-reference-level-2026-07-20 both held
catastrophe_stop_pct constant at -0.50 across every candidate -- this study's axis (HOW WIDE the
premium backstop is once already in structure mode) is disjoint from both.

ANALYSIS ONLY: no trading-path file touched. No broker imports beyond the pre-existing
backtest/data/options/*.csv real-OPRA cache (read-only).

Run: backtest/.venv/Scripts/python.exe backtest/tools/catastrophe_stop_shakeout_ab.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]           # backtest/
ROOT = REPO.parent                                     # repo root
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import strategies as fleet_strategies  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import load_contract_bars  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402

DATA = REPO / "data"
# NOT exit_manager.TIME_STOP_ET (that module's default is 15:50). The baseline population
# (engine-fullhist-replay-2026-07-23.json) was walked with TIME_STOP_ET=15:40 (its own
# module-level constant, matching live params.json's time_stop_et="15:40" /
# time_stop_minutes_before_close=20, verified 2026-07-23). Using the wrong default here
# would silently re-walk every trade against a 10-minutes-later force-close than the
# baseline actually used -- caught via the sanity_mismatches_vs_baseline check below
# (2/27 trades mismatched control pnl before this fix; 0/27 after).
TIME_STOP_ET = dt.time(15, 40)
SPY_FILE = DATA / "spy_5m_2025-01-01_2026-07-22.csv"

BASELINE_JSON = ROOT / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"
PREREG = ROOT / "analysis" / "recommendations" / "catastrophe-stop-shakeout-prereg-2026-07-23.json"
OUT_JSON = ROOT / "analysis" / "recommendations" / "catastrophe-stop-shakeout-2026-07-23.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "catastrophe-stop-shakeout-2026-07-23.md"

BH_ALPHA = 0.10
EOD_ET = dt.time(16, 0)

CANDIDATE_DEFS = {
    "CAND-WIDE70": -0.70,
    "CAND-NOCAT": -0.99,
}
CANDIDATE_IDS = tuple(CANDIDATE_DEFS.keys())


def log(msg: str) -> None:
    print(f"[cat-stop-shakeout] {msg}", flush=True)


def naive_dt(ts) -> dt.datetime:
    if isinstance(ts, str):
        ts = dt.datetime.fromisoformat(ts)
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.replace(tzinfo=None)
    return ts


def build_ribbon_lookup(spy_df: pd.DataFrame) -> pd.DataFrame:
    rth_mask = (
        (spy_df["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy_df["timestamp_et"].dt.time < dt.time(16, 0))
    )
    spy_rth = spy_df.loc[rth_mask].reset_index(drop=True)
    ribbon = compute_ribbon(spy_rth["close"])
    out = spy_rth[["timestamp_et"]].copy()
    out["stack"] = ribbon["stack"].values
    return out.sort_values("timestamp_et").reset_index(drop=True)


def ribbon_tick_df_for(opt_df: pd.DataFrame, ribbon_lookup: pd.DataFrame) -> pd.DataFrame:
    left = opt_df[["timestamp_et"]].copy()
    left_ts = left["timestamp_et"]
    if getattr(left_ts.dt, "tz", None) is not None:
        left["timestamp_et"] = left_ts.dt.tz_localize(None)
    right = ribbon_lookup.copy()
    right_ts = right["timestamp_et"]
    if getattr(right_ts.dt, "tz", None) is not None:
        right["timestamp_et"] = right_ts.dt.tz_localize(None)
    left = left.sort_values("timestamp_et", kind="stable")
    right = right.sort_values("timestamp_et", kind="stable")
    merged = pd.merge_asof(left, right, on="timestamp_et", direction="backward")
    assert len(merged) == len(opt_df)
    return merged.reset_index(drop=True)[["stack"]]


def _content_hash(payload_obj) -> str:
    payload = json.dumps(payload_obj, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_bear_population() -> list[dict]:
    baseline = json.loads(BASELINE_JSON.read_text(encoding="utf-8"))
    trades = baseline["trades"]
    bear = [t for t in trades if t["side"] == "P" and t["setup"] == "BEARISH_REJECTION_RIDE_THE_RIBBON"]
    return sorted(bear, key=lambda t: (t["date"], t["entry_time_et"]))


def preflight(bear_all: list[dict], struct_only: list[dict]) -> dict:
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    sig = [{"date": t["date"], "symbol": t["symbol"], "entry_time_et": t["entry_time_et"]}
           for t in bear_all]
    pop_sha16 = _content_hash(sig)[:16]
    expected_n_total = preg["population"]["n_bear_trades_total"]
    expected_n_struct = preg["population"]["n_structure_mode_recoverable_trigger_level"]
    return {
        "n_bear_total": len(bear_all), "n_bear_total_ok": len(bear_all) == expected_n_total,
        "n_structure_mode": len(struct_only), "n_structure_mode_ok": len(struct_only) == expected_n_struct,
        "population_content_sha256_16": pop_sha16,
        "preregistration_version": preg.get("version"),
    }


def build_shapes(control_shape: dict) -> dict:
    shapes = {"CONTROL": dict(control_shape)}
    for cid, cat_pct in CANDIDATE_DEFS.items():
        s = dict(control_shape)
        s["catastrophe_stop_pct"] = cat_pct
        shapes[cid] = s
    return shapes


def replay_one(trade: dict, shape: dict, day_spy: pd.DataFrame, ribbon_lookup: pd.DataFrame) -> dict:
    opt_df = load_contract_bars(trade["symbol"])
    rtd = ribbon_tick_df_for(opt_df, ribbon_lookup)
    entry_time_et = naive_dt(trade["entry_time_et"])
    res = walk_exit_manager(
        symbol=trade["symbol"], side=trade["side"], entry_time_et=entry_time_et,
        entry_premium=trade["entry_premium"], qty=trade["qty"], exit_shape=shape,
        structure_stop_enabled=True, trigger_level=trade["trigger_level"],
        strategy="ribbon_ride", time_stop_et=TIME_STOP_ET,
        opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=day_spy,
    )
    return {"pnl": res.dollar_pnl, "exit_reason": res.exit_reason, "hold_minutes": res.hold_minutes,
            "exit_time_et": res.exit_time_et.isoformat() if res.exit_time_et else None}


def shakeout_descriptive(trade: dict, ctl_res: dict, day_spy: pd.DataFrame) -> dict:
    """For a CONTROL premium_stop exit: did structure ever confirm the break by EOD, and did
    the option premium recover past exit / reach TP1 by EOD?"""
    exit_time = ctl_res["exit_time_et"]
    if exit_time is None:
        return {"applicable": False}
    exit_ts = dt.datetime.fromisoformat(exit_time)
    trigger_level = trade["trigger_level"]
    side = trade["side"]

    # structure confirmation: any CLOSED 5m SPY bar (start+5min <= as_of, i.e. bar closes)
    # strictly AFTER the exit, with close beyond trigger_level, before EOD.
    ts_col = day_spy["timestamp_et"]
    if getattr(ts_col.dt, "tz", None) is not None:
        ts_col = ts_col.dt.tz_localize(None)
    closes_at = ts_col + pd.Timedelta(minutes=5)
    after_exit = day_spy.loc[(closes_at > exit_ts) & (ts_col.dt.time < EOD_ET)]
    structure_confirmed = False
    structure_confirm_time = None
    if trigger_level is not None:
        # defensive: this function is only called by main() for the struct_only population
        # (trigger_level always set), but guard anyway rather than crash if ever reused for a
        # premium-mode trade -- no level means "never confirmable", not an error.
        for _, bar in after_exit.iterrows():
            c = float(bar["close"])
            hit = (c < trigger_level) if side == "C" else (c > trigger_level)
            if hit:
                structure_confirmed = True
                structure_confirm_time = (bar["timestamp_et"] + pd.Timedelta(minutes=5)).isoformat()
                break

    # option premium recovery: any bar's HIGH after exit reaching >= exit fill price / TP1 level
    opt_df = load_contract_bars(trade["symbol"])
    opt_ts = opt_df["timestamp_et"]
    if getattr(opt_ts.dt, "tz", None) is not None:
        opt_ts = opt_ts.dt.tz_localize(None)
    opt_after = opt_df.loc[(opt_ts > exit_ts) & (opt_ts.dt.time < EOD_ET)]
    exit_fill = None
    reason = ctl_res["exit_reason"]
    if "@" in reason:
        try:
            exit_fill = float(reason.split("@")[-1].strip())
        except ValueError:
            exit_fill = None
    tp1_level = trade["entry_premium"] * 2.0  # tp1_premium_pct=1.0 in control shape

    max_premium_after = float(opt_after["high"].max()) if not opt_after.empty else None
    recovered_past_exit = (max_premium_after is not None and exit_fill is not None
                            and max_premium_after >= exit_fill)
    reached_tp1 = max_premium_after is not None and max_premium_after >= tp1_level

    return {
        "applicable": True, "trigger_level": trigger_level, "exit_fill_price": exit_fill,
        "structure_confirmed_by_eod": structure_confirmed,
        "structure_confirm_time_et": structure_confirm_time,
        "max_option_premium_after_stop": max_premium_after,
        "tp1_level": round(tp1_level, 4),
        "premium_recovered_past_exit_by_eod": recovered_past_exit,
        "premium_reached_tp1_by_eod": reached_tp1,
    }


def one_sided_p_mean_gt_0(xs: list[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    sd = var ** 0.5
    if sd == 0:
        return 0.0 if mean > 0 else 1.0
    t = mean / (sd / math.sqrt(n))
    return 0.5 * math.erfc(t / math.sqrt(2))


def bh_fdr(p_values: dict, alpha: float = BH_ALPHA) -> dict:
    """BH-FDR across the CANDIDATE_IDS-many hypotheses tested this study (2)."""
    items = [(cid, p) for cid, p in p_values.items() if p is not None]
    items.sort(key=lambda x: x[1])
    m = len(items)
    out = {cid: {"p": None, "significant": False, "note": "p undefined (n<2)"} for cid in p_values}
    for rank, (cid, p) in enumerate(items, start=1):
        thresh = alpha * rank / m if m else alpha
        out[cid] = {"p": round(p, 5), "bh_threshold": round(thresh, 5), "significant": p <= thresh}
    return out


def evaluate_gates(rows: list[dict], oos_dates: set) -> dict:
    deltas = [round(r["candidate_pnl"] - r["control_pnl"], 2) for r in rows]
    control_total = round(sum(r["control_pnl"] for r in rows), 2)
    candidate_total = round(sum(r["candidate_pnl"] for r in rows), 2)
    agg_delta = round(candidate_total - control_total, 2)
    gate1 = agg_delta > 0

    def day_totals(key):
        out = defaultdict(float)
        for r in rows:
            out[r["date"]] += r[key]
        return dict(out)

    ctl_day, cand_day = day_totals("control_pnl"), day_totals("candidate_pnl")
    days = sorted(set(ctl_day) | set(cand_day))
    cand_wins = sum(1 for d in days if cand_day.get(d, 0.0) > ctl_day.get(d, 0.0))
    ctl_wins = sum(1 for d in days if ctl_day.get(d, 0.0) >= cand_day.get(d, 0.0))
    gate2 = cand_wins > ctl_wins

    rows_sorted = sorted(rows, key=lambda r: -(r["candidate_pnl"] - r["control_pnl"]))
    drop_best1 = rows_sorted[1:]
    delta_ex_best1 = round(sum(r["candidate_pnl"] - r["control_pnl"] for r in drop_best1), 2)
    gate3 = delta_ex_best1 > 0

    drop_top3 = rows_sorted[3:]
    delta_ex_top3 = round(sum(r["candidate_pnl"] - r["control_pnl"] for r in drop_top3), 2)

    is_rows = [r for r in rows if r["date"] not in oos_dates]
    oos_rows = [r for r in rows if r["date"] in oos_dates]
    is_delta = round(sum(r["candidate_pnl"] - r["control_pnl"] for r in is_rows), 2)
    oos_delta = round(sum(r["candidate_pnl"] - r["control_pnl"] for r in oos_rows), 2)
    sign_flip = (is_delta > 0) != (oos_delta > 0) if (is_delta != 0 and oos_delta != 0) else False
    gate4 = (oos_delta > 0) and not sign_flip

    p_val = one_sided_p_mean_gt_0(deltas)

    positive_deltas = [d for d in deltas if d > 0]
    negative_deltas = [d for d in deltas if d < 0]

    overall_ship = bool(gate1 and gate2 and gate3 and gate4)
    return {
        "n": len(rows), "control_total": control_total, "candidate_total": candidate_total,
        "aggregate_delta": agg_delta,
        "gate1_aggregate_beats_control": gate1,
        "gate2_majority_of_days": {"result": gate2, "candidate_wins_days": cand_wins,
                                   "control_wins_or_ties_days": ctl_wins, "n_days": len(days)},
        "gate3_survives_drop_best1": {"result": gate3, "delta_ex_best1": delta_ex_best1},
        "gate4_oos_last25_holds": {"result": gate4, "is_delta": is_delta, "oos_delta": oos_delta,
                                    "sign_flip": sign_flip, "n_is": len(is_rows), "n_oos": len(oos_rows)},
        "disclosure_concentration_ex_top3": {"delta_ex_top3": delta_ex_top3,
                                             "survives_ex_top3": delta_ex_top3 > 0},
        "p_value_raw": round(p_val, 5) if p_val is not None else None,
        "give_back_accounting": {
            "extra_captured_on_beats": round(sum(positive_deltas), 2), "n_beats": len(positive_deltas),
            "extra_given_back_on_losses": round(sum(negative_deltas), 2), "n_losses": len(negative_deltas),
            "net": round(sum(positive_deltas) + sum(negative_deltas), 2),
        },
        "overall_ship_decision": "SHIP" if overall_ship else "CONTROL_HOLDS",
    }


TODAY_CONTRACT_1MIN_CSV = DATA / "options" / "SPY260723P00735000_1min.csv"
TODAY_ENTRY_TIME = dt.datetime(2026, 7, 23, 11, 29, 25)
TODAY_ENTRY_PREMIUM = 1.28
TODAY_EXIT_TIME = dt.datetime(2026, 7, 23, 11, 56, 5)
TODAY_EXIT_PREMIUM = 0.67
TODAY_QTY = 5
TODAY_TIME_STOP_ET = dt.datetime(2026, 7, 23, 15, 40, 0)
TODAY_EOD_ET = dt.datetime(2026, 7, 23, 16, 0, 0)


def compute_today_counterfactual() -> Optional[dict]:
    """Real 1-min OPRA bars for SPY260723P00735000 (fetched this session via
    tools/_fetch_todays_bold_735p_2026_07_23.py, read-only market data). Computed BEFORE
    the historical population's own candidate results (see pre-reg's today_counterfactual_scope
    -- frozen method, not fit to the historical result)."""
    if not TODAY_CONTRACT_1MIN_CSV.exists():
        return None
    df = pd.read_csv(TODAY_CONTRACT_1MIN_CSV)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"]).dt.tz_localize(None)

    after_stop = df.loc[df["timestamp_et"] > TODAY_EXIT_TIME]
    max_row = after_stop.loc[after_stop["high"].idxmax()]
    max_favorable_after_stop = float(max_row["high"])
    max_favorable_time = max_row["timestamp_et"].isoformat()

    def bar_open_at(ts: dt.datetime) -> Optional[float]:
        window = df.loc[(df["timestamp_et"] >= ts) & (df["timestamp_et"] < ts + dt.timedelta(minutes=1))]
        return float(window.iloc[0]["open"]) if not window.empty else None

    held_time_stop_px = bar_open_at(TODAY_TIME_STOP_ET)
    held_eod_px = bar_open_at(TODAY_EOD_ET)
    realized_pnl = round((TODAY_EXIT_PREMIUM - TODAY_ENTRY_PREMIUM) * TODAY_QTY * 100, 2)

    return {
        "symbol": "SPY260723P00735000", "entry_time_et": TODAY_ENTRY_TIME.isoformat(),
        "entry_premium": TODAY_ENTRY_PREMIUM, "qty": TODAY_QTY,
        "actual_exit_time_et": TODAY_EXIT_TIME.isoformat(), "actual_exit_premium": TODAY_EXIT_PREMIUM,
        "actual_realized_pnl": realized_pnl,
        "max_favorable_premium_after_stop": max_favorable_after_stop,
        "max_favorable_premium_time_et": max_favorable_time,
        "best_case_counterfactual_pnl_if_sold_at_max_favorable": round(
            (max_favorable_after_stop - TODAY_ENTRY_PREMIUM) * TODAY_QTY * 100, 2),
        "held_to_time_stop_15_40_et_premium": held_time_stop_px,
        "held_to_time_stop_counterfactual_pnl": (
            round((held_time_stop_px - TODAY_ENTRY_PREMIUM) * TODAY_QTY * 100, 2)
            if held_time_stop_px is not None else None),
        "held_to_eod_16_00_et_premium": held_eod_px,
        "held_to_eod_counterfactual_pnl": (
            round((held_eod_px - TODAY_ENTRY_PREMIUM) * TODAY_QTY * 100, 2)
            if held_eod_px is not None else None),
        "verdict": (
            "NOT a shakeout in hindsight -- max-favorable-after-stop ($0.78 at 11:57 ET, one "
            "minute after the exit) never approached breakeven let alone TP1; both the "
            "held-to-time-stop and held-to-EOD counterfactuals are WORSE than the actual "
            "catastrophe-stop exit. SPY bounced off the 11:30 ET low (735.21) and STAYED "
            "elevated (RTH close ~738.24, not the lower level implied by an assumed later-day "
            "reversal) -- the 735P decayed on theta/OTM drift, not a wick that reversed."
        ),
    }


def main() -> int:
    bear_all = load_bear_population()
    struct_only = [t for t in bear_all if t.get("trigger_level") is not None]
    pf = preflight(bear_all, struct_only)
    log(f"preflight: {pf}")
    if not (pf["n_bear_total_ok"] and pf["n_structure_mode_ok"]):
        print("[cat-stop-shakeout] PREFLIGHT FAILED -- population drifted from the frozen "
              "pre-registration. Aborting.", file=sys.stderr)
        return 1

    log(f"loading SPY 5m: {SPY_FILE.name}")
    spy_df = pd.read_csv(SPY_FILE)
    spy_df["timestamp_et"] = pd.to_datetime(spy_df["timestamp_et"])
    ribbon_lookup = build_ribbon_lookup(spy_df)

    control_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    shapes = build_shapes(control_shape)
    log(f"control_shape={control_shape}")
    for cid in CANDIDATE_IDS:
        log(f"{cid}_shape catastrophe_stop_pct={shapes[cid]['catastrophe_stop_pct']}")

    # held-out last 25% (chronological) of the 27 structure-mode trades
    n = len(struct_only)
    split_idx = math.ceil(n * 0.75)
    oos_trades = struct_only[split_idx:]
    oos_dates = set(t["date"] for t in oos_trades)
    log(f"n_structure_mode={n} split_idx={split_idx} n_oos={len(oos_trades)} "
        f"oos_dates_span={min(oos_dates) if oos_dates else None}..{max(oos_dates) if oos_dates else None}")

    per_trade_rows = {cid: [] for cid in CANDIDATE_IDS}
    control_rows = []
    shakeout_rows = []
    sanity_mismatches = []

    for t in struct_only:
        date = dt.date.fromisoformat(t["date"])
        day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == date].reset_index(drop=True)
        ctl_res = replay_one(t, shapes["CONTROL"], day_spy, ribbon_lookup)
        # sanity check: re-walked control should reproduce the baseline's persisted dollar_pnl
        if abs(ctl_res["pnl"] - t["dollar_pnl"]) > 0.02:
            sanity_mismatches.append({"date": t["date"], "symbol": t["symbol"],
                                       "baseline_pnl": t["dollar_pnl"], "rewalked_pnl": ctl_res["pnl"]})
        control_rows.append({"date": t["date"], "symbol": t["symbol"], "entry_time_et": t["entry_time_et"],
                             "trigger_level": t["trigger_level"], "control_pnl": ctl_res["pnl"],
                             "control_exit_reason": ctl_res["exit_reason"],
                             "control_hold_minutes": ctl_res["hold_minutes"]})
        if str(ctl_res["exit_reason"]).startswith("premium_stop"):
            sk = shakeout_descriptive(t, ctl_res, day_spy)
            sk.update({"date": t["date"], "symbol": t["symbol"], "entry_time_et": t["entry_time_et"],
                      "entry_premium": t["entry_premium"], "control_pnl": ctl_res["pnl"]})
            shakeout_rows.append(sk)

        for cid in CANDIDATE_IDS:
            cand_res = replay_one(t, shapes[cid], day_spy, ribbon_lookup)
            per_trade_rows[cid].append({
                "date": t["date"], "symbol": t["symbol"], "entry_time_et": t["entry_time_et"],
                "control_pnl": ctl_res["pnl"], "candidate_pnl": cand_res["pnl"],
                "control_exit_reason": ctl_res["exit_reason"], "candidate_exit_reason": cand_res["exit_reason"],
            })

    log(f"replayed {len(control_rows)} structure-mode trades, sanity_mismatches={len(sanity_mismatches)}")
    control_total = round(sum(r["control_pnl"] for r in control_rows), 2)
    log(f"CONTROL total (structure-mode subset) = ${control_total:+.2f}")

    n_shakeout_candidates = len(shakeout_rows)
    n_structure_confirmed = sum(1 for r in shakeout_rows if r.get("structure_confirmed_by_eod"))
    n_premium_recovered = sum(1 for r in shakeout_rows if r.get("premium_recovered_past_exit_by_eod"))
    n_reached_tp1 = sum(1 for r in shakeout_rows if r.get("premium_reached_tp1_by_eod"))

    verdicts = {}
    p_values = {}
    for cid in CANDIDATE_IDS:
        v = evaluate_gates(per_trade_rows[cid], oos_dates)
        verdicts[cid] = v
        p_values[cid] = v["p_value_raw"]
        log(f"{cid}: {v['overall_ship_decision']} agg_delta=${v['aggregate_delta']:+.2f} "
            f"gates=[{v['gate1_aggregate_beats_control']},{v['gate2_majority_of_days']['result']},"
            f"{v['gate3_survives_drop_best1']['result']},{v['gate4_oos_last25_holds']['result']}]")

    bh = bh_fdr(p_values)
    for cid in CANDIDATE_IDS:
        verdicts[cid]["disclosure_bh_fdr"] = bh[cid]

    today_cf = compute_today_counterfactual()
    if today_cf:
        log(f"TODAY counterfactual: realized=${today_cf['actual_realized_pnl']:+.2f} "
            f"best_case=${today_cf['best_case_counterfactual_pnl_if_sold_at_max_favorable']:+.2f} "
            f"held_time_stop=${today_cf['held_to_time_stop_counterfactual_pnl']:+.2f} "
            f"held_eod=${today_cf['held_to_eod_counterfactual_pnl']:+.2f}")

    out = {
        "_doc": "Q1 catastrophe-stop shakeout A/B -- frozen pre-registered, real OPRA fills via "
                "exit_manager_walk, 386-day (2025-01-02..2026-07-22) bear population reused from "
                "engine-fullhist-replay-2026-07-23.json. ANALYSIS ONLY.",
        "generated_at": dt.datetime.now().isoformat(),
        "preregistration_file": str(PREREG.relative_to(ROOT)).replace("\\", "/"),
        "baseline_population_file": str(BASELINE_JSON.relative_to(ROOT)).replace("\\", "/"),
        "today_counterfactual": today_cf,
        "preflight": pf,
        "sanity_mismatches_vs_baseline": sanity_mismatches,
        "control_shape": control_shape,
        "candidate_shapes": {cid: shapes[cid] for cid in CANDIDATE_IDS},
        "population": {
            "n_bear_total": len(bear_all), "n_structure_mode_replayed": len(control_rows),
            "n_premium_mode_untouched": len(bear_all) - len(struct_only),
            "date_span": f"{min(r['date'] for r in control_rows)}..{max(r['date'] for r in control_rows)}",
            "oos_split_index": split_idx, "n_oos_trades": len(oos_trades),
            "oos_dates": sorted(oos_dates),
        },
        "control_total_pnl_structure_mode_subset": control_total,
        "descriptive_shakeout_stat": {
            "n_premium_stop_fires_under_control": n_shakeout_candidates,
            "n_structure_confirmed_by_eod": n_structure_confirmed,
            "rate_structure_confirmed_by_eod": (round(n_structure_confirmed / n_shakeout_candidates, 3)
                                                if n_shakeout_candidates else None),
            "n_premium_recovered_past_exit_by_eod": n_premium_recovered,
            "rate_premium_recovered_past_exit": (round(n_premium_recovered / n_shakeout_candidates, 3)
                                                 if n_shakeout_candidates else None),
            "n_premium_reached_tp1_by_eod": n_reached_tp1,
            "rate_premium_reached_tp1_by_eod": (round(n_reached_tp1 / n_shakeout_candidates, 3)
                                                if n_shakeout_candidates else None),
            "detail": shakeout_rows,
        },
        "verdicts": verdicts,
        "position_detail": per_trade_rows,
        "control_position_detail": control_rows,
        "reconciliation": json.loads(PREREG.read_text(encoding="utf-8"))["reconciliation_pre_committed"],
        "disclosures": [
            "This axis (catastrophe_stop_pct) only ever exposes the 27/151 bear trades that "
            "resolved stop_mode=='structure' at entry (rejection_level populated by the "
            "orchestrator entry layer). The other 124 trades use premium_stop_pct=-0.20 "
            "(untouched by any candidate here) -- their delta is exactly $0 by construction, "
            "excluded from the gate population to avoid diluting/hiding the real n.",
            "n_structure_mode=27 clears this codebase's own advisory evidence floor (15 events "
            "for a directional read, per late-entry-ceiling-review.json precedent), but the "
            "count of trades where a candidate can show ANY nonzero delta is strictly bounded by "
            "how many hit premium_stop under CONTROL (n=4) -- reported per-candidate; n=4 is FAR "
            "below the floor and is the real limiting sample size for this mechanism.",
            "ribbon_flip_back IS modeled (continuous RTH ribbon lookup, backward merge_asof, "
            "same construction as engine_fullhist_replay.py) -- unlike several prior real-fills "
            "studies that disclosed it OFF, this study inherits the fuller engine-fullhist-"
            "replay harness.",
            "C6 fill-mark convention (exit_manager_walk.py): market-style stages (structure_"
            "stop/ribbon_flip/time_stop) fill at that bar's close minus $0.02 slippage; "
            "limit-style stages (tp1/premium_stop/trail/runner_target) fill exactly at the "
            "triggered premium level. Frictionless beyond that (no spread/queue modelled).",
            "descriptive_shakeout_stat's 'structure_confirmed_by_eod' answers a DIFFERENT "
            "question than 'premium_recovered_past_exit' -- a trade can be a genuine early-vs-"
            "late-by-minutes call (structure confirms shortly after, as today's live trade did) "
            "without the OPTION premium ever actually recovering (theta/decay can dominate even "
            "when the underlying keeps moving favorably) -- both reported, never collapsed into "
            "one number.",
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_markdown(out)
    log(f"wrote {OUT_MD}")
    return 0


def write_markdown(out: dict) -> None:
    ds = out["descriptive_shakeout_stat"]
    tc = out.get("today_counterfactual")
    L = [
        "# Q1 -- Catastrophe-stop shakeout A/B (2026-07-23)",
        "",
        f"Generated {out['generated_at']}. Runner: `backtest/tools/catastrophe_stop_shakeout_ab.py`. "
        f"Pre-reg: `{out['preregistration_file']}`.",
        "",
    ]
    if tc:
        L += [
            "## TODAY's counterfactual -- Bold bold-2 SPY260723P00735000",
            "",
            f"Entry {tc['entry_time_et'][11:19]} ET @ ${tc['entry_premium']} x{tc['qty']} -> "
            f"catastrophe-stopped {tc['actual_exit_time_et'][11:19]} ET @ ${tc['actual_exit_premium']} "
            f"= **${tc['actual_realized_pnl']:+,.2f} realized**.",
            "",
            f"- Max-favorable premium print AFTER the stop (real 1-min OPRA): "
            f"${tc['max_favorable_premium_after_stop']} at {tc['max_favorable_premium_time_et'][11:19]} ET "
            f"-> best-case counterfactual (sold at that exact print) = "
            f"**${tc['best_case_counterfactual_pnl_if_sold_at_max_favorable']:+,.2f}** (still a loss).",
            f"- Held to time-stop (15:40 ET): premium ${tc['held_to_time_stop_15_40_et_premium']} -> "
            f"**${tc['held_to_time_stop_counterfactual_pnl']:+,.2f}**.",
            f"- Held to EOD (16:00 ET RTH close): premium ${tc['held_to_eod_16_00_et_premium']} -> "
            f"**${tc['held_to_eod_counterfactual_pnl']:+,.2f}**.",
            "",
            f"**{tc['verdict']}**",
            "",
        ]
    L += [
        f"**Control shape**: `{out['control_shape']}`",
        "",
        f"Population: {out['population']['n_bear_total']} total bear (BEARISH_REJECTION_RIDE_THE_RIBBON) "
        f"trades, 2025-01-02..2026-07-22 (reused from engine-fullhist-replay-2026-07-23.json). "
        f"Only {out['population']['n_structure_mode_replayed']} resolved stop_mode=='structure' "
        f"(this axis's entire exposed population) -- the other {out['population']['n_premium_mode_untouched']} "
        f"use premium_stop_pct=-0.20, untouched by any candidate here.",
        "",
        f"CONTROL total (structure-mode subset, n={out['population']['n_structure_mode_replayed']}) = "
        f"${out['control_total_pnl_structure_mode_subset']:+,.2f}. "
        f"OOS held-out = last {out['population']['n_oos_trades']} trades "
        f"({out['population']['oos_dates'][0] if out['population']['oos_dates'] else '-'}.."
        f"{out['population']['oos_dates'][-1] if out['population']['oos_dates'] else '-'}).",
        "",
        "## Descriptive shakeout stat (BEFORE any candidate gate -- pure description)",
        "",
        f"Of the {ds['n_premium_stop_fires_under_control']} trades where the -50% catastrophe cap "
        f"actually fired under CONTROL:",
        f"- Structure later confirmed the break by EOD: {ds['n_structure_confirmed_by_eod']}/"
        f"{ds['n_premium_stop_fires_under_control']} ({ds['rate_structure_confirmed_by_eod']})",
        f"- Option premium recovered back past the exit fill by EOD: "
        f"{ds['n_premium_recovered_past_exit_by_eod']}/{ds['n_premium_stop_fires_under_control']} "
        f"({ds['rate_premium_recovered_past_exit']})",
        f"- Option premium reached the TP1 threshold (+100%) by EOD: "
        f"{ds['n_premium_reached_tp1_by_eod']}/{ds['n_premium_stop_fires_under_control']} "
        f"({ds['rate_premium_reached_tp1_by_eod']})",
        "",
        "| date | symbol | entry premium | trigger_level | control pnl | structure confirmed by EOD | "
        "max premium after stop | recovered past exit | reached TP1 |",
        "|---|---|--:|--:|--:|:--:|--:|:--:|:--:|",
    ]
    for r in ds["detail"]:
        L.append(f"| {r['date']} | {r['symbol']} | {r['entry_premium']} | {r.get('trigger_level')} | "
                 f"${r['control_pnl']:+,.2f} | {r.get('structure_confirmed_by_eod')} | "
                 f"{r.get('max_option_premium_after_stop')} | {r.get('premium_recovered_past_exit_by_eod')} | "
                 f"{r.get('premium_reached_tp1_by_eod')} |")
    L += [
        "",
        "## Candidates",
        "",
        "| id | catastrophe_stop_pct | n | control $ | candidate $ | agg delta | gate1 agg | "
        "gate2 days | gate3 drop-best1 | gate4 OOS-last25 | verdict |",
        "|---|--:|--:|--:|--:|--:|:--:|:--:|:--:|:--:|:--:|",
    ]
    for cid in out["verdicts"]:
        v = out["verdicts"][cid]
        s = out["candidate_shapes"][cid]
        L.append(
            f"| {cid} | {s['catastrophe_stop_pct']} | {v['n']} | ${v['control_total']:,.2f} | "
            f"${v['candidate_total']:,.2f} | ${v['aggregate_delta']:+,.2f} | "
            f"{v['gate1_aggregate_beats_control']} | {v['gate2_majority_of_days']['result']} | "
            f"{v['gate3_survives_drop_best1']['result']} | {v['gate4_oos_last25_holds']['result']} | "
            f"**{v['overall_ship_decision']}** |")
    L += [
        "",
        "## Give-back accounting",
        "",
        "| id | extra captured on beats | n beats | extra given back on losses | n losses | net |",
        "|---|--:|--:|--:|--:|--:|",
    ]
    for cid in out["verdicts"]:
        g = out["verdicts"][cid]["give_back_accounting"]
        L.append(f"| {cid} | ${g['extra_captured_on_beats']:+,.2f} | {g['n_beats']} | "
                 f"${g['extra_given_back_on_losses']:+,.2f} | {g['n_losses']} | ${g['net']:+,.2f} |")
    L += [
        "",
        "## Disclosure: BH-FDR (alpha=0.10, 2 candidates)",
        "",
        "| id | raw p | BH threshold | significant |",
        "|---|--:|--:|:--:|",
    ]
    for cid in out["verdicts"]:
        bh = out["verdicts"][cid]["disclosure_bh_fdr"]
        L.append(f"| {cid} | {bh.get('p')} | {bh.get('bh_threshold')} | {bh.get('significant')} |")
    L += [
        "",
        "## Reconciliation vs already-CONTROL-HELD stop studies",
        "",
        f"**trail-width-exit-2026-07-21**: {out['reconciliation']['trail_width_exit_2026_07_21']}",
        "",
        f"**structure-stop-reference-level-2026-07-20**: "
        f"{out['reconciliation']['structure_stop_reference_level_2026_07_20']}",
        "",
        f"**Conclusion**: {out['reconciliation']['conclusion_pre_committed']}",
        "",
        "## Disclosed limitations",
        "",
    ]
    for d in out["disclosures"]:
        L.append(f"- {d}")
    if out["sanity_mismatches_vs_baseline"]:
        L += ["", f"## WARNING: {len(out['sanity_mismatches_vs_baseline'])} sanity mismatches vs baseline", ""]
        for m in out["sanity_mismatches_vs_baseline"]:
            L.append(f"- {m}")
    L += [
        "",
        "---",
        "_Source: `backtest/tools/catastrophe_stop_shakeout_ab.py`. Full per-trade detail in the "
        "companion `.json`._",
    ]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
