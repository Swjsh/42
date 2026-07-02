"""E6 — J structure-read study. Implements REGISTRATION.md EXACTLY (frozen 2026-07-02).

Pipeline: population filter -> causal feature computation (completed 5m bars only)
-> train-fit linear score (z * point-biserial weights) -> ONE test-year evaluation
-> permutation p (seed 42, 1000 draws) -> results.json.

Run: backtest/.venv/Scripts/python.exe analysis/j-webull/E6-structure-read/scripts/e6_structure_read.py
"""
from __future__ import annotations

import json
import math
import sys
from datetime import timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
E6 = HERE.parent
JW = E6.parent
REPO = JW.parents[1]
sys.path.insert(0, str(REPO))

from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.market_structure import analyze_structure  # noqa: E402

ET = ZoneInfo("America/New_York")
FEATURES = [
    "wick_favor", "level_sweep_favor", "hold_bars", "structure_align", "event_recency",
    "body_favor", "vwap_streak", "touch_count", "ribbon_slope_favor", "abs_level_dist",
]
MIN_BARS = 3          # registered early-entry gate
SWEEP_LOOKBACK = 3    # F2: last 3 bars
SWEEP_PIERCE = 0.05   # F2: $0.05 pierce
HOLD_CAP = 6          # F3
VWAP_CAP = 12         # F7
TOUCH_TOL = 0.15      # F8: $0.15
TOUCH_CAP = 10        # F8
SEED = 42
N_PERM = 1000


def load_rth() -> pd.DataFrame:
    m5 = pd.read_csv(JW / "cache" / "spy_5m_2021-06-01_2023-10-31.csv")
    m5["ts"] = pd.to_datetime(m5["t"], utc=True).dt.tz_convert(ET).dt.tz_localize(None)
    m5 = m5.sort_values("ts").reset_index(drop=True)
    m5["date"] = m5["ts"].dt.date
    m5["bar_close_ts"] = m5["ts"] + pd.Timedelta(minutes=5)
    rth = m5[(m5["ts"].dt.time >= pd.Timestamp("09:30").time())
             & (m5["ts"].dt.time < pd.Timestamp("16:00").time())].copy()
    rth = rth.reset_index(drop=True)
    # RTH-continuous EMA ribbon (identical convention to build_normalized.py)
    rth["ema8"] = rth["c"].ewm(span=8, adjust=False).mean()
    rth["ema21"] = rth["c"].ewm(span=21, adjust=False).mean()
    rth["spread_pct"] = (rth["ema8"] / rth["ema21"] - 1.0) * 100.0
    # running session VWAP per date
    tp = (rth["h"] + rth["l"] + rth["c"]) / 3.0
    g = rth.groupby("date")
    rth["cum_pv"] = (tp * rth["v"]).groupby(rth["date"]).cumsum()
    rth["cum_v"] = g["v"].cumsum()
    rth["vwap"] = rth["cum_pv"] / rth["cum_v"].replace(0, np.nan)
    return rth


def load_daily() -> dict:
    daily = pd.read_csv(JW / "cache" / "spy_daily_2021-06-01_2023-10-31.csv")
    daily["date"] = pd.to_datetime(daily["t"], utc=True).dt.tz_convert(ET).dt.date
    daily = daily.sort_values("date").reset_index(drop=True)
    daily[["pdh", "pdl", "pdc"]] = daily[["h", "l", "c"]].shift(1)
    return {r["date"]: r for _, r in daily.iterrows()}


def to_bars(day: pd.DataFrame) -> list[Bar]:
    out = []
    for _, r in day.iterrows():
        ot = pd.Timestamp(r["ts"]).tz_localize(ET).tz_convert(timezone.utc).to_pydatetime()
        out.append(Bar(open_time=ot, open=float(r["o"]), high=float(max(r["h"], r["l"]))
                       , low=float(min(r["h"], r["l"])), close=float(r["c"]),
                       volume=float(r["v"]), granularity_seconds=300, source="alpaca_iex"))
    return out


def features_for(day: pd.DataFrame, rth: pd.DataFrame, bias: str, dd) -> dict | None:
    """day = today's completed RTH bars (bar_close_ts <= entry_ts), oldest first."""
    b0 = day.iloc[-1]
    if dd is None or pd.isna(dd["pdh"]):
        return None
    c0 = float(b0["c"])
    levels = {"PDH": float(dd["pdh"]), "PDL": float(dd["pdl"]), "PDC": float(dd["pdc"])}
    near = min(levels, key=lambda k: abs(c0 / levels[k] - 1))
    L = levels[near]
    bull = bias == "bull"
    rng0 = float(b0["h"]) - float(b0["l"])
    o0, h0, l0 = float(b0["o"]), float(b0["h"]), float(b0["l"])

    f: dict[str, float] = {"nearest_level": near}
    # F1 wick_favor
    if rng0 <= 0:
        f["wick_favor"] = 0.0
    elif bull:
        f["wick_favor"] = (min(o0, c0) - l0) / rng0
    else:
        f["wick_favor"] = (h0 - max(o0, c0)) / rng0
    # F2 level_sweep_favor (last 3 bars)
    tail = day.iloc[-SWEEP_LOOKBACK:]
    swept = 0
    for _, r in tail.iterrows():
        if bull and (float(r["l"]) < L - SWEEP_PIERCE) and (float(r["c"]) >= L):
            swept = 1
        if (not bull) and (float(r["h"]) > L + SWEEP_PIERCE) and (float(r["c"]) <= L):
            swept = 1
    f["level_sweep_favor"] = float(swept)
    # F3 hold_bars
    hold = 0
    for _, r in day.iloc[::-1].iterrows():
        fav = (float(r["c"]) > L) if bull else (float(r["c"]) < L)
        if not fav:
            break
        hold += 1
        if hold >= HOLD_CAP:
            break
    f["hold_bars"] = float(hold)
    # F4/F5 structure via crypto.lib.market_structure
    read = analyze_structure(to_bars(day), window=2)
    want = "uptrend" if bull else "downtrend"
    anti = "downtrend" if bull else "uptrend"
    f["structure_align"] = 1.0 if read.trend == want else (-1.0 if read.trend == anti else 0.0)
    if read.last_event is not None:
        bars_ago = (len(day) - 1) - read.last_event.break_index
        s = 1.0 if ((read.last_event.direction == "bullish") == bull) else -1.0
        f["event_recency"] = s / (1.0 + bars_ago)
    else:
        f["event_recency"] = 0.0
    # F6 body_favor
    if rng0 <= 0:
        f["body_favor"] = 0.0
    else:
        f["body_favor"] = ((c0 - o0) if bull else (o0 - c0)) / rng0
    # F7 vwap_streak (signed)
    streak = 0
    first_side = None
    for _, r in day.iloc[::-1].iterrows():
        if pd.isna(r["vwap"]):
            break
        side = float(r["c"]) > float(r["vwap"])  # True = above
        trade_side = side if bull else (not side)
        if first_side is None:
            first_side = trade_side
        if trade_side != first_side:
            break
        streak += 1
        if streak >= VWAP_CAP:
            break
    if first_side is None:
        f["vwap_streak"] = np.nan
    else:
        f["vwap_streak"] = float(streak if first_side else -streak)
    # F8 touch_count (exclude b0)
    prior = day.iloc[:-1]
    touches = int(((prior["l"] - TOUCH_TOL <= L) & (prior["h"] + TOUCH_TOL >= L)).sum())
    f["touch_count"] = float(min(touches, TOUCH_CAP))
    # F9 ribbon_slope_favor (series-wise on full RTH frame)
    p = int(b0.name)  # positional index in rth (reset_index'd)
    if p >= 3:
        slope = float(rth["spread_pct"].iloc[p] - rth["spread_pct"].iloc[p - 3])
    else:
        slope = 0.0
    f["ribbon_slope_favor"] = slope if bull else -slope
    # F10 abs_level_dist
    f["abs_level_dist"] = abs((c0 / L - 1.0) * 100.0)
    return f


def quartile_stats(sub: pd.DataFrame) -> dict:
    """sub must have score, dir_ok, pnl, episode_id. Registered quartile split."""
    s = sub.sort_values(["score", "episode_id"], ascending=[True, True]).reset_index(drop=True)
    k = math.ceil(len(s) / 4)
    bot, top = s.iloc[:k], s.iloc[-k:]
    def cell(c):
        return {"n": int(len(c)), "hit_rate": round(float(c["dir_ok"].mean()), 4),
                "pnl_per_trade": round(float(c["pnl"].mean()), 2),
                "pnl_total": round(float(c["pnl"].sum()), 2)}
    return {"k": k, "top": cell(top), "bottom": cell(bot),
            "delta_hit": round(float(top["dir_ok"].mean() - bot["dir_ok"].mean()), 4),
            "delta_pnl": round(float(top["pnl"].mean() - bot["pnl"].mean()), 2)}


def permutation_p(sub: pd.DataFrame) -> dict:
    s = sub.sort_values(["score", "episode_id"], ascending=[True, True]).reset_index(drop=True)
    k = math.ceil(len(s) / 4)
    dir_ok = s["dir_ok"].to_numpy(float)
    pnl = s["pnl"].to_numpy(float)
    top_idx = np.arange(len(s) - k, len(s))
    bot_idx = np.arange(0, k)
    obs_hit = dir_ok[top_idx].mean() - dir_ok[bot_idx].mean()
    obs_pnl = pnl[top_idx].mean() - pnl[bot_idx].mean()
    rng = np.random.default_rng(SEED)
    ge_hit = ge_pnl = 0
    for _ in range(N_PERM):
        perm = rng.permutation(len(s))
        d, p_ = dir_ok[perm], pnl[perm]
        if d[top_idx].mean() - d[bot_idx].mean() >= obs_hit:
            ge_hit += 1
        if p_[top_idx].mean() - p_[bot_idx].mean() >= obs_pnl:
            ge_pnl += 1
    return {"p_hit": round((1 + ge_hit) / (N_PERM + 1), 4),
            "p_pnl": round((1 + ge_pnl) / (N_PERM + 1), 4),
            "obs_delta_hit": round(float(obs_hit), 4), "obs_delta_pnl": round(float(obs_pnl), 2)}


def main() -> None:
    ep = pd.read_csv(JW / "trades-normalized.csv")
    rth = load_rth()
    daily_by_date = load_daily()
    by_date = {d: g for d, g in rth.groupby("date")}

    pop = ep[(ep["is_family"]) & (ep["closed"]) & (ep["ctx_ok"])
             & (ep["bias"].isin(["bull", "bear"])) & ep["pnl"].notna()].copy()
    pop["entry_ts"] = pd.to_datetime(pop["entry_ts_et"])
    pop["exit_ts"] = pd.to_datetime(pop["exit_ts_et"])
    drops = {"start_closed_family_ctx": int(len(pop)), "no_entry_bar": 0,
             "early_entry_lt3_bars": 0, "no_exit_bar_after_entry": 0, "no_prior_daily": 0}

    rows = []
    close_ts_all = rth["bar_close_ts"].to_numpy()
    for _, r in pop.iterrows():
        day = by_date.get(r["entry_ts"].date())
        if day is None:
            drops["no_entry_bar"] += 1
            continue
        done = day[day["bar_close_ts"] <= r["entry_ts"]]
        if done.empty:
            drops["no_entry_bar"] += 1
            continue
        if len(done) < MIN_BARS:
            drops["early_entry_lt3_bars"] += 1
            continue
        # C6 assertion: no feature bar closes after entry
        assert (done["bar_close_ts"] <= r["entry_ts"]).all()
        b0 = done.iloc[-1]
        # exit join: last RTH bar closed <= exit_ts, strictly after the entry bar
        j = int(np.searchsorted(close_ts_all, np.datetime64(r["exit_ts"]), side="right")) - 1
        if j < 0 or int(rth.iloc[j].name) <= int(b0.name):
            drops["no_exit_bar_after_entry"] += 1
            continue
        spy_entry, spy_exit = float(b0["c"]), float(rth.iloc[j]["c"])
        dd = daily_by_date.get(r["entry_ts"].date())
        f = features_for(done, rth, r["bias"], dd)
        if f is None:
            drops["no_prior_daily"] += 1
            continue
        bull = r["bias"] == "bull"
        f.update(episode_id=int(r["episode_id"]), entry_ts=str(r["entry_ts"]),
                 bias=r["bias"], pnl=float(r["pnl"]), qty=int(r["qty"]),
                 spy_entry=spy_entry, spy_exit=spy_exit,
                 dir_ok=int((spy_exit > spy_entry) if bull else (spy_exit < spy_entry)),
                 year=int(r["entry_ts"].year), csv_nearest_level=r["nearest_level"])
        rows.append(f)

    df = pd.DataFrame(rows)
    df["is_test"] = df["year"] >= 2023

    # sanity 1: nearest-level agreement with CSV
    agree = float((df["nearest_level"] == df["csv_nearest_level"]).mean())
    # sanity 2: overall hit rate vs TRAITS 59.2%
    overall_hit = float(df["dir_ok"].mean())

    train, test = df[~df["is_test"]].copy(), df[df["is_test"]].copy()

    # frozen score: train z + point-biserial weights
    weights, mus, sds = {}, {}, {}
    for c in FEATURES:
        col = train[c].astype(float)
        mu, sd = float(col.mean()), float(col.std(ddof=0))
        if not np.isfinite(sd) or sd == 0:
            continue
        z = (col - mu) / sd
        z = z.fillna(0.0)
        y = train["dir_ok"].astype(float)
        w = float(np.corrcoef(z, y)[0, 1]) if z.std(ddof=0) > 0 else 0.0
        if not np.isfinite(w):
            w = 0.0
        weights[c], mus[c], sds[c] = w, mu, sd

    def score(frame: pd.DataFrame) -> pd.Series:
        s = pd.Series(0.0, index=frame.index)
        for c, w in weights.items():
            z = ((frame[c].astype(float) - mus[c]) / sds[c]).fillna(0.0)
            s = s + w * z
        return s

    train["score"] = score(train)
    test["score"] = score(test)

    train_stats = quartile_stats(train)
    test_stats = quartile_stats(test)          # THE single test evaluation
    perm = permutation_p(test)

    n_test = int(len(test))
    d_hit, d_pnl, p_hit = test_stats["delta_hit"], test_stats["delta_pnl"], perm["p_hit"]
    if d_hit <= 0:
        verdict = "NO_SEPARATION"
    elif n_test >= 40 and p_hit < 0.05 and d_pnl > 0:
        verdict = "SEPARATES"
    else:
        verdict = "WEAK"

    out = {
        "study": "E6-structure-read", "registered": "REGISTRATION.md (commit precedes compute)",
        "population": {"joined_n": int(len(df)), "train_n": int(len(train)), "test_n": n_test,
                       "drops": drops},
        "sanity": {"nearest_level_agreement": round(agree, 4),
                   "overall_dir_hit_rate": round(overall_hit, 4),
                   "traits_reference_hit_rate": 0.592,
                   "hit_rate_within_2pp": abs(overall_hit - 0.592) <= 0.02},
        "train_weights_point_biserial": {k: round(v, 4) for k, v in weights.items()},
        "train_quartiles_descriptive": train_stats,
        "test_quartiles_EVALUATED_ONCE": test_stats,
        "permutation": {**perm, "n_perm": N_PERM, "seed": SEED},
        "verdict": verdict,
    }
    (E6 / "results.json").write_text(json.dumps(out, indent=2))
    df.drop(columns=["csv_nearest_level"]).to_csv(E6 / "episodes-scored.csv", index=False)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
