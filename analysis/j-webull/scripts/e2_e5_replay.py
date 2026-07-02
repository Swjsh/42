"""E2 + E5 from analysis/j-webull/EXPERIMENTS.md (2026-07-01).

E2 — "J's entries + machine management" counterfactual replay.
  Replays each of J's closed family episodes with his EXACT entry moment and
  direction, replacing everything after entry with v15-style mechanical exits
  (TP1 +30% sell 0.8, runner target 2.5x entry premium with breakeven stop,
  -50% catastrophe cap, 15:50 ET time stop) and HARD-CAPPING qty at his FIRST
  fill size (no adds ever). Option paths are Black-Scholes synthetic
  (backtest/lib/pricing.py conventions: IV = VIX/100, r = 4%, expiry 16:00 ET).

  *** BS-SIM => RANKING-ONLY EVIDENCE PER C1. Never a promotion gate. ***

  Variants:
    (a) his strike            + machine exits + first-fill qty cap
    (b) strike normalized ATM + machine exits + first-fill qty cap
    (c) = (b) restricted to J's best 3-axis cell:
        at-level (<=0.1% from PDH/PDL/PDC) & VWAP-aligned & morning 10:00-11:00
        (the only n>=15 positive cell, per E3-trigger-coverage.md).

E5 — never-average-down guard evidence pack ($0, pure arithmetic on REAL fills):
  (1) scaled-in episodes: actual P&L vs first-fill-size-only counterfactual
      (keep first buy lot only; sell it FIFO at his REAL sell prices);
  (2) the same for the averaged-DOWN subset (any add at a lower premium);
  (3) held-past--50% losers: gross excess loss beyond a -50% premium cap
      (bound: no option path data; assumes exit at exactly -50%).

Data sources:
  - SPY 5m 2021-06-01..2023-10-31: existing cache (Alpaca IEX raw), verified span.
  - VIX daily 2021-06..2023-10: fetched via yfinance (^VIX) -> cache (DISCLOSED;
    intraday IV held constant at the entry day's OPEN — causal at any RTH entry).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parents[2]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(REPO))

from webull_parse import SPOT_RATIO, load_fills  # noqa: E402
from backtest.lib.pricing import black_scholes, vix_to_iv  # noqa: E402

OUT_DIR = REPO / "analysis" / "j-webull"
CACHE = OUT_DIR / "cache"
VIX_CSV = CACHE / "vix_daily_2021-06-01_2023-10-31.csv"
SPY_CSV = CACHE / "spy_5m_2021-06-01_2023-10-31.csv"
ET = ZoneInfo("America/New_York")

# v15-style mechanical exit knobs (Safe-account values, params.json 2026-07-01)
TP1_RET = 0.30          # +30% premium -> partial
TP1_FRAC = 0.80         # tp1_qty_fraction (Safe)
RUNNER_TARGET_RET = 1.5  # runner target 2.5x entry premium
CAT_STOP_RET = -0.50    # -50% catastrophe cap
TIME_STOP = dtime(15, 45)  # last path bar START (closes 15:50 ET)
MIN_PREM = 0.05         # BS entry premium floor; below = unpriceable, drop+count
YEARS_SEC = 365.25 * 24 * 3600.0


# ---------------------------------------------------------------- episodes
def build_episodes_with_fills(fills: pd.DataFrame) -> pd.DataFrame:
    """Same FIFO flat->flat walk as webull_parse.build_episodes, but retains the
    per-episode buy/sell fill lists needed for first-fill counterfactuals."""
    episodes = []
    for sym, g in fills.groupby("Symbol", sort=False):
        g = g.sort_values("ts_et", kind="stable")
        first = g.iloc[0]
        lots: list[list] = []
        cur = None
        for _, row in g.iterrows():
            if row["Side"] == "Buy":
                if cur is None:
                    cur = {
                        "symbol": sym, "underlying": first["underlying"],
                        "right": first["right"], "strike": float(first["strike"]),
                        "expiry": first["expiry"], "is_family": bool(first["is_family"]),
                        "entry_ts_et": row["ts_et"], "exit_ts_et": None,
                        "buys": [], "sells": [], "max_open_qty": 0,
                    }
                cur["buys"].append((row["ts_et"], int(row["qty"]), float(row["px"])))
                lots.append([int(row["qty"]), float(row["px"])])
                cur["max_open_qty"] = max(cur["max_open_qty"], sum(l[0] for l in lots))
            else:
                if cur is None or not lots:
                    continue  # anomaly (matches webull_parse skip)
                need = min(int(row["qty"]), sum(l[0] for l in lots))
                cur["sells"].append((row["ts_et"], need, float(row["px"])))
                while need > 0 and lots:
                    take = min(need, lots[0][0])
                    lots[0][0] -= take
                    need -= take
                    if lots[0][0] == 0:
                        lots.pop(0)
                if not lots:
                    cur["exit_ts_et"] = row["ts_et"]
                    episodes.append(cur)
                    cur = None
        if cur is not None:
            entry_d = cur["entry_ts_et"].date()
            if cur["expiry"] <= entry_d:  # 0DTE leftover -> expired worthless
                cur["exit_ts_et"] = pd.Timestamp.combine(
                    cur["expiry"], dtime(16, 0))
                cur["expired_worthless"] = True
                episodes.append(cur)
            # longer-dated leftovers = unclosed -> excluded (matches parser)

    rows = []
    for e in episodes:
        buy_qty = sum(q for _, q, _ in e["buys"])
        sell_qty = sum(q for _, q, _ in e["sells"])
        buy_cost = sum(q * p for _, q, p in e["buys"])
        sell_proceeds = sum(q * p for _, q, p in e["sells"])
        rows.append({
            "symbol": e["symbol"], "underlying": e["underlying"], "right": e["right"],
            "strike": e["strike"], "expiry": e["expiry"], "is_family": e["is_family"],
            "entry_ts_et": e["entry_ts_et"], "exit_ts_et": e["exit_ts_et"],
            "buys": e["buys"], "sells": e["sells"],
            "n_buy_fills": len(e["buys"]), "qty": e["max_open_qty"],
            "buy_cost": buy_cost, "pnl": (sell_proceeds - buy_cost) * 100.0,
            "premium_at_risk": buy_cost * 100.0,
            "ret_pct": ((sell_proceeds / sell_qty) / (buy_cost / buy_qty) - 1) * 100.0
                       if sell_qty > 0 else -100.0,
            "first_qty": e["buys"][0][1], "first_px": e["buys"][0][2],
        })
    ep = pd.DataFrame(rows)
    ep = ep.sort_values("entry_ts_et").reset_index(drop=True)
    return ep


# ---------------------------------------------------------------- E5
def e5_first_fill_counterfactual(ep_row) -> float:
    """P&L ($) if only the FIRST buy lot existed, sold FIFO at his REAL sell
    prices; any residual (expired worthless) yields 0 proceeds."""
    q0, p0 = ep_row["first_qty"], ep_row["first_px"]
    need = q0
    proceeds = 0.0
    for _, sq, sp in ep_row["sells"]:
        take = min(need, sq)
        proceeds += take * sp
        need -= take
        if need == 0:
            break
    return (proceeds - q0 * p0) * 100.0


def run_e5(fam: pd.DataFrame) -> dict:
    scaled = fam[fam["n_buy_fills"] > 1].copy()
    scaled["cf_pnl"] = scaled.apply(e5_first_fill_counterfactual, axis=1)
    # combined guard: no-adds AND -50% catastrophe cap on the first lot (bound)
    first_lot_risk = scaled["first_qty"] * scaled["first_px"] * 100.0
    scaled["cf_pnl_capped"] = np.maximum(scaled["cf_pnl"], -0.5 * first_lot_risk)
    avg_down = scaled[scaled.apply(
        lambda r: any(p < r["first_px"] for _, _, p in r["buys"][1:]), axis=1)]

    losers = fam[fam["pnl"] < 0]
    past50 = fam[fam["ret_pct"] <= -50.0]
    # excess beyond a -50% cap (bound; assumes exit at exactly -50%)
    excess = (-past50["pnl"]) - 0.5 * past50["premium_at_risk"]
    excess = excess.clip(lower=0.0)

    return {
        "population": {"closed_family_episodes": int(len(fam)),
                       "total_pnl": round(float(fam["pnl"].sum()), 2)},
        "scaled_in": {
            "n": int(len(scaled)),
            "actual_total": round(float(scaled["pnl"].sum()), 2),
            "actual_exp_per_trade": round(float(scaled["pnl"].mean()), 2),
            "cf_first_fill_total": round(float(scaled["cf_pnl"].sum()), 2),
            "cf_first_fill_exp_per_trade": round(float(scaled["cf_pnl"].mean()), 2),
            "delta_saved_by_no_adds": round(
                float(scaled["cf_pnl"].sum() - scaled["pnl"].sum()), 2),
            "cf_no_adds_plus_50cap_total": round(
                float(scaled["cf_pnl_capped"].sum()), 2),
            "delta_saved_by_no_adds_plus_50cap": round(
                float(scaled["cf_pnl_capped"].sum() - scaled["pnl"].sum()), 2),
        },
        "averaged_down_subset": {
            "definition": "any add fill at a LOWER premium than the first fill",
            "n": int(len(avg_down)),
            "share_of_scaled_in_pct": round(100.0 * len(avg_down) / max(1, len(scaled)), 1),
            "actual_total": round(float(avg_down["pnl"].sum()), 2),
            "cf_first_fill_total": round(float(avg_down["cf_pnl"].sum()), 2),
            "delta_saved_by_no_adds": round(
                float(avg_down["cf_pnl"].sum() - avg_down["pnl"].sum()), 2),
            "wr_pct": round(100.0 * float((avg_down["pnl"] > 0).mean()), 1),
        },
        "held_past_minus50": {
            "n_losers": int(len(losers)),
            "n_past_50pct": int(len(past50)),
            "share_of_losers_pct": round(100.0 * len(past50) / max(1, len(losers)), 1),
            "gross_loss_of_past50": round(float(past50["pnl"].sum()), 2),
            "gross_excess_beyond_cap": round(float(excess.sum()), 2),
            "note": ("BOUND, not a sim: assumes exit at exactly -50% of premium at "
                     "risk; gap-through/path effects unknown without option paths."),
        },
        "per_episode_scaled_in": [
            {"symbol": r["symbol"], "entry": str(r["entry_ts_et"]),
             "qty_max": int(r["qty"]), "first_qty": int(r["first_qty"]),
             "actual_pnl": round(float(r["pnl"]), 2),
             "cf_pnl": round(float(r["cf_pnl"]), 2)}
            for _, r in scaled.sort_values("pnl").head(10).iterrows()
        ],
    }


# ---------------------------------------------------------------- data loads
def load_spy_rth() -> pd.DataFrame:
    m5 = pd.read_csv(SPY_CSV)
    m5["ts"] = pd.to_datetime(m5["t"], utc=True).dt.tz_convert(ET).dt.tz_localize(None)
    m5 = m5.sort_values("ts").reset_index(drop=True)
    m5["date"] = m5["ts"].dt.date
    m5["bar_close_ts"] = m5["ts"] + pd.Timedelta(minutes=5)
    rth = m5[(m5["ts"].dt.time >= dtime(9, 30)) & (m5["ts"].dt.time < dtime(16, 0))]
    return rth.copy()


def load_vix() -> pd.DataFrame:
    if not VIX_CSV.exists():
        import yfinance as yf
        df = yf.download("^VIX", start="2021-06-01", end="2023-10-06",
                         interval="1d", auto_adjust=False, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        df = df.reset_index()[["Date", "Open", "Close"]]
        df.columns = ["date", "open", "close"]
        df.to_csv(VIX_CSV, index=False)
    v = pd.read_csv(VIX_CSV)
    v["date"] = pd.to_datetime(v["date"]).dt.date
    v = v.sort_values("date").reset_index(drop=True)
    v["prior_close"] = v["close"].shift(1)
    return v


# ---------------------------------------------------------------- E2 replay
def tte_years(now_et: datetime, expiry_dt: datetime) -> float:
    s = (expiry_dt - now_et).total_seconds()
    return max(60.0 / YEARS_SEC / 1.0, s / YEARS_SEC) if s > 60 else 60.0 / YEARS_SEC


def machine_replay(path_bars, entry_prem, strike, is_call, iv, expiry_dt, ratio):
    """Walk 5m bar closes after entry; return (avg_exit_prem, exit_reason).
    Fractional-contract accounting: TP1 sells TP1_FRAC, runner is the rest."""
    frac_open, tp1_done = 1.0, False
    realized = 0.0
    reason = None
    prem = entry_prem
    for _, b in path_bars.iterrows():
        spot = float(b["c"]) * ratio
        prem, _ = black_scholes(spot, strike, iv,
                                tte_years(b["bar_close_ts"].to_pydatetime(), expiry_dt),
                                is_call)
        ret = prem / entry_prem - 1.0
        if ret <= CAT_STOP_RET:
            realized += frac_open * prem
            frac_open, reason = 0.0, "catastrophe_stop"
            break
        if not tp1_done:
            if ret >= TP1_RET:
                realized += TP1_FRAC * prem
                frac_open, tp1_done = 1.0 - TP1_FRAC, True
                if ret >= RUNNER_TARGET_RET:
                    realized += frac_open * prem
                    frac_open, reason = 0.0, "runner_target"
                    break
        else:
            if ret >= RUNNER_TARGET_RET:
                realized += frac_open * prem
                frac_open, reason = 0.0, "runner_target"
                break
            if ret <= 0.0:
                realized += frac_open * prem
                frac_open, reason = 0.0, "runner_breakeven"
                break
    if frac_open > 0:
        realized += frac_open * prem  # last evaluated bar = 15:45 bar (15:50 close)
        reason = reason or ("time_stop" if tp1_done is False else "time_stop_runner")
    return realized, reason


def atm_strike(spot_equiv: float, underlying: str) -> float:
    if underlying in ("SPX", "SPXW"):
        return round(spot_equiv / 5.0) * 5.0
    return float(round(spot_equiv))


def run_e2(fam: pd.DataFrame, norm: pd.DataFrame, rth: pd.DataFrame,
           vix: pd.DataFrame) -> dict:
    # join ctx from trades-normalized.csv on (symbol identity + entry ts)
    norm = norm.copy()
    norm["key"] = (norm["underlying"] + "|" + norm["strike"].astype(float).astype(str)
                   + "|" + norm["right"] + "|" + norm["expiry"].astype(str)
                   + "|" + norm["entry_ts_et"].astype(str))
    fam = fam.copy()
    fam["key"] = (fam["underlying"] + "|" + fam["strike"].astype(float).astype(str)
                  + "|" + fam["right"] + "|" + fam["expiry"].astype(str)
                  + "|" + fam["entry_ts_et"].astype(str))
    ctx_cols = ["key", "ctx_ok", "spy_px", "vwap_side", "nearest_level_dist_pct",
                "bias", "is_0dte", "entry_px", "qty"]
    j = fam.merge(norm[ctx_cols], on="key", how="left", suffixes=("", "_norm"))
    assert j["ctx_ok"].notna().all(), "context join failed for some episodes"

    vix_by_date = {r["date"]: r for _, r in vix.iterrows()}
    bars_by_date = dict(tuple(rth.groupby("date")))

    spy_span = (str(rth["ts"].min()), str(rth["ts"].max()))
    drops = {"no_ctx": 0, "no_vix": 0, "no_entry_bar": 0, "no_path_bars": 0,
             "unpriceable_low_prem": 0}
    results = {v: [] for v in ("a", "b", "b_null")}
    calib = []

    for _, r in j.iterrows():
        if not bool(r["ctx_ok"]):
            drops["no_ctx"] += 1
            continue
        d = r["entry_ts_et"].date()
        vrow = vix_by_date.get(d)
        vix_val = None
        if vrow is not None:
            vix_val = vrow["open"] if pd.notna(vrow["open"]) else vrow["prior_close"]
        if vrow is None or pd.isna(vix_val):
            drops["no_vix"] += 1
            continue
        day = bars_by_date.get(d)
        if day is None:
            drops["no_entry_bar"] += 1
            continue
        entry_ts = pd.Timestamp(r["entry_ts_et"])
        prior = day[day["bar_close_ts"] <= entry_ts]
        if prior.empty:
            drops["no_entry_bar"] += 1
            continue
        eb = prior.iloc[-1]
        path = day[(day["bar_close_ts"] > entry_ts) & (day["ts"].dt.time <= TIME_STOP)]
        if path.empty:
            drops["no_path_bars"] += 1
            continue

        ratio = SPOT_RATIO[r["underlying"]]
        spot0 = float(eb["c"]) * ratio
        iv = vix_to_iv(float(vix_val))
        is_call = r["right"] == "C"
        expiry_dt = datetime.combine(r["expiry"], dtime(16, 0))
        t0 = eb["bar_close_ts"].to_pydatetime()
        qty = int(r["first_qty"])

        # variant (a): his strike
        prem_a, _ = black_scholes(spot0, float(r["strike"]), iv,
                                  tte_years(t0, expiry_dt), is_call)
        # variant (b): ATM strike
        k_b = atm_strike(spot0, r["underlying"])
        prem_b, _ = black_scholes(spot0, k_b, iv, tte_years(t0, expiry_dt), is_call)

        calib.append({"bs_prem_a": prem_a, "actual_entry_px": float(r["entry_px"])})

        base = {"key": r["key"], "entry_ts": str(r["entry_ts_et"]),
                "j_actual_pnl": float(r["pnl"]), "qty_first_fill": qty,
                "at_level": bool(pd.notna(r["nearest_level_dist_pct"])
                                 and abs(float(r["nearest_level_dist_pct"])) <= 0.1),
                "aligned": bool((r["bias"] == "bull" and r["vwap_side"] == "above")
                                or (r["bias"] == "bear" and r["vwap_side"] == "below")),
                "morning": dtime(10, 0) <= entry_ts.time() < dtime(11, 0)}

        if prem_a < MIN_PREM:
            drops["unpriceable_low_prem"] += 1
        else:
            avg_exit, reason = machine_replay(path, prem_a, float(r["strike"]),
                                              is_call, iv, expiry_dt, ratio)
            results["a"].append({**base, "machine_pnl": qty * 100.0 * (avg_exit - prem_a),
                                 "exit_reason": reason, "entry_prem_bs": prem_a})
        # (b) always priceable (ATM)
        avg_exit, reason = machine_replay(path, prem_b, k_b, is_call, iv, expiry_dt, ratio)
        results["b"].append({**base, "machine_pnl": qty * 100.0 * (avg_exit - prem_b),
                             "exit_reason": reason, "entry_prem_bs": prem_b})
        # NULL CONTROL: same entry moment, ATM strike, OPPOSITE direction.
        # If this also prints positive, the machine-exit ladder is harvesting
        # BS convexity / realized-vs-implied vol, NOT J's directional read.
        prem_n, _ = black_scholes(spot0, k_b, iv, tte_years(t0, expiry_dt),
                                  not is_call)
        avg_exit_n, reason_n = machine_replay(path, prem_n, k_b, not is_call,
                                              iv, expiry_dt, ratio)
        results["b_null"].append(
            {**base, "machine_pnl": qty * 100.0 * (avg_exit_n - prem_n),
             "exit_reason": reason_n, "entry_prem_bs": prem_n})

    def stats(rows, label):
        if not rows:
            return {"label": label, "n": 0}
        df = pd.DataFrame(rows).sort_values("entry_ts")
        m = df["machine_pnl"].to_numpy()
        ja = df["j_actual_pnl"].to_numpy()
        cum = np.cumsum(m)
        maxdd = float(np.max(np.maximum.accumulate(cum) - cum)) if len(cum) else 0.0
        top3 = np.sort(m)[-3:]
        rng = np.random.default_rng(42)
        boot = rng.choice(m, size=(10000, len(m)), replace=True).sum(axis=1)
        reasons = df["exit_reason"].value_counts().to_dict()
        return {
            "label": label, "n": int(len(df)),
            "machine_total": round(float(m.sum()), 2),
            "machine_exp_per_trade": round(float(m.mean()), 2),
            "machine_wr_pct": round(100.0 * float((m > 0).mean()), 1),
            "machine_max_drawdown": round(maxdd, 2),
            "machine_total_drop_top3": round(float(m.sum() - top3[top3 > 0].sum()), 2),
            "bootstrap_p_sum_gt_0": round(float((boot > 0).mean()), 3),
            "j_actual_total_same_population": round(float(ja.sum()), 2),
            "j_actual_exp_same_population": round(float(ja.mean()), 2),
            "j_actual_wr_same_population_pct": round(100.0 * float((ja > 0).mean()), 1),
            "delta_vs_j_actual": round(float(m.sum() - ja.sum()), 2),
            "exit_reasons": reasons,
        }

    df_b = pd.DataFrame(results["b"])
    cell_mask = df_b["at_level"] & df_b["aligned"] & df_b["morning"]
    variant_c_rows = df_b[cell_mask].to_dict("records")

    cal = pd.DataFrame(calib)
    cal_ratio = (cal["bs_prem_a"] / cal["actual_entry_px"]).replace(
        [np.inf, -np.inf], np.nan).dropna()

    return {
        "spy_5m_master_span": {"min_bar_ts": spy_span[0], "max_bar_ts": spy_span[1],
                               "n_rth_bars": int(len(rth))},
        "drops": drops,
        "bs_calibration": {
            "note": ("BS entry premium (his strike, VIX-open IV) vs J's ACTUAL "
                     "entry premium — quantifies how badly the smile-less "
                     "BS+VIX model misprices his (often deep-OTM) contracts."),
            "n": int(len(cal_ratio)),
            "median_bs_over_actual": round(float(cal_ratio.median()), 3),
            "pct_bs_below_half_actual": round(
                100.0 * float((cal_ratio < 0.5).mean()), 1),
            "pct_bs_above_double_actual": round(
                100.0 * float((cal_ratio > 2.0).mean()), 1),
        },
        "variants": {
            "a_his_strike": stats(results["a"], "his entry+strike, machine exits, first-fill qty cap"),
            "b_atm_strike": stats(results["b"], "his entry, ATM strike, machine exits, first-fill qty cap"),
            "c_atm_best_cell": stats(variant_c_rows, "(b) restricted to at-level & aligned & morning 10:00-11:00"),
            "b_null_opposite_direction": stats(
                results["b_null"],
                "NULL CONTROL: same entries, ATM strike, OPPOSITE direction"),
        },
    }


# ---------------------------------------------------------------- main
def main() -> None:
    fills, meta = load_fills()
    ep = build_episodes_with_fills(fills)
    fam = ep[ep["is_family"]].reset_index(drop=True)
    # self-check vs the published parse (C7: audit outputs)
    total = float(fam["pnl"].sum())
    print(f"[check] closed family episodes rebuilt: {len(fam)} (expect 567)")
    print(f"[check] family pnl total: {total:.2f} (expect ~-12885)")
    assert len(fam) == 567, f"episode count mismatch: {len(fam)}"
    assert abs(total - (-12885.0)) < 5.0, f"pnl mismatch: {total}"

    norm = pd.read_csv(OUT_DIR / "trades-normalized.csv",
                       parse_dates=["entry_ts_et"])
    norm = norm[norm["is_family"] & norm["closed"]]
    norm["expiry"] = pd.to_datetime(norm["expiry"]).dt.date

    e5 = run_e5(fam)
    print("[e5] scaled-in:", e5["scaled_in"])
    print("[e5] avg-down:", {k: v for k, v in e5["averaged_down_subset"].items()
                             if k != "definition"})
    print("[e5] past-50:", {k: v for k, v in e5["held_past_minus50"].items()
                            if k != "note"})

    rth = load_spy_rth()
    vix = load_vix()
    print(f"[data] VIX daily rows: {len(vix)} "
          f"({vix['date'].min()} .. {vix['date'].max()})  source=yfinance ^VIX")

    e2 = run_e2(fam, norm, rth, vix)
    for k, v in e2["variants"].items():
        print(f"[e2:{k}]", {kk: vv for kk, vv in v.items() if kk != "exit_reasons"})
    print("[e2] drops:", e2["drops"])
    print("[e2] calibration:", e2["bs_calibration"])

    payload = {
        "generated": "2026-07-01",
        "caveat": ("BS-SYNTHETIC OPTION PRICING — RANKING-ONLY EVIDENCE PER C1. "
                   "No smile, no spread, no fills. Never a promotion gate."),
        "exit_stack": {"tp1_ret": TP1_RET, "tp1_frac": TP1_FRAC,
                       "runner_target_ret": RUNNER_TARGET_RET,
                       "catastrophe_stop_ret": CAT_STOP_RET,
                       "time_stop_et": "15:50 (close of 15:45 bar)",
                       "qty": "hard-capped at J's FIRST fill size (no adds ever)"},
        "e2": e2,
    }
    (OUT_DIR / "E2-machine-management-replay.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8")
    (OUT_DIR / "E5-rule4-evidence.json").write_text(
        json.dumps({"generated": "2026-07-01", "e5": e5}, indent=2, default=str),
        encoding="utf-8")
    print("[out] wrote E2-machine-management-replay.json + E5-rule4-evidence.json")


if __name__ == "__main__":
    main()
