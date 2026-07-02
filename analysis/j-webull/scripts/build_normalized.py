"""Build analysis/j-webull/trades-normalized.csv — one row per flat->flat round-trip,
with market context at entry joined from SPY 5m/daily (Alpaca IEX, raw).

Causality (C6): every context feature uses only bars whose 5m window CLOSED
strictly at-or-before the entry timestamp minus one bar (i.e. the last completed
bar before entry). Prior-day levels come from the previous trading day's daily
bar. Nothing from the future of the entry tick is used.

SPX/XSP moneyness caveat: spot for SPXW/SPX is approximated as 10 x SPY and XSP
as 1 x SPY (ratio drift ~±0.3%); moneyness_pct for non-SPY family is approximate.
"""
from __future__ import annotations

import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from webull_parse import SPOT_RATIO, build_episodes, load_fills, size_band  # noqa: E402

REPO = SCRIPTS.parents[2]
OUT_DIR = REPO / "analysis" / "j-webull"
CACHE = OUT_DIR / "cache"
ET = ZoneInfo("America/New_York")


def load_bars() -> tuple[pd.DataFrame, pd.DataFrame]:
    m5 = pd.read_csv(CACHE / "spy_5m_2021-06-01_2023-10-31.csv")
    m5["ts"] = pd.to_datetime(m5["t"], utc=True).dt.tz_convert(ET).dt.tz_localize(None)
    m5 = m5.sort_values("ts").reset_index(drop=True)
    m5["date"] = m5["ts"].dt.date
    m5["bar_close_ts"] = m5["ts"] + pd.Timedelta(minutes=5)
    rth = m5[(m5["ts"].dt.time >= pd.Timestamp("09:30").time())
             & (m5["ts"].dt.time < pd.Timestamp("16:00").time())].copy()
    # EMA ribbon over RTH-continuous closes (warm after day 1 of the series)
    rth["ema8"] = rth["c"].ewm(span=8, adjust=False).mean()
    rth["ema21"] = rth["c"].ewm(span=21, adjust=False).mean()
    # session-cumulative VWAP + running HOD/LOD, per date
    tp = (rth["h"] + rth["l"] + rth["c"]) / 3.0
    g = rth.groupby("date")
    rth["cum_pv"] = (tp * rth["v"]).groupby(rth["date"]).cumsum()
    rth["cum_v"] = g["v"].cumsum()
    rth["vwap"] = rth["cum_pv"] / rth["cum_v"].replace(0, np.nan)
    rth["hod"] = g["h"].cummax()
    rth["lod"] = g["l"].cummin()
    rth["open_930"] = g["o"].transform("first")

    daily = pd.read_csv(CACHE / "spy_daily_2021-06-01_2023-10-31.csv")
    daily["date"] = pd.to_datetime(daily["t"], utc=True).dt.tz_convert(ET).dt.date
    daily = daily.sort_values("date").reset_index(drop=True)
    daily[["pdh", "pdl", "pdc"]] = daily[["h", "l", "c"]].shift(1)
    return rth, daily


def context_at(entry_ts: pd.Timestamp, rth: pd.DataFrame, daily_by_date: dict) -> dict:
    d = entry_ts.date()
    day = rth[rth["date"] == d]
    prior = day[day["bar_close_ts"] <= entry_ts]
    out = {"ctx_ok": False}
    if prior.empty:
        return out
    b = prior.iloc[-1]
    spy = float(b["c"])
    out.update(
        ctx_ok=True,
        spy_px=spy,
        vwap=round(float(b["vwap"]), 4) if pd.notna(b["vwap"]) else np.nan,
        vwap_side=("above" if spy > b["vwap"] else "below") if pd.notna(b["vwap"]) else "na",
        vwap_dist_pct=round((spy / b["vwap"] - 1) * 100, 3) if pd.notna(b["vwap"]) else np.nan,
        ribbon_state="bull" if b["ema8"] > b["ema21"] else "bear",
        ribbon_dist_pct=round((b["ema8"] / b["ema21"] - 1) * 100, 3),
        sess_range_pos=round((spy - b["lod"]) / (b["hod"] - b["lod"]), 3) if b["hod"] > b["lod"] else np.nan,
        open_gap_pct=np.nan,
        prior_30m_pct=np.nan,
        mins_since_open=round((entry_ts - pd.Timestamp.combine(d, pd.Timestamp("09:30").time())).total_seconds() / 60, 1),
    )
    if len(prior) >= 7:
        out["prior_30m_pct"] = round((spy / float(prior.iloc[-7]["c"]) - 1) * 100, 3)
    dd = daily_by_date.get(d)
    if dd is not None and pd.notna(dd["pdh"]):
        out["open_gap_pct"] = round((float(day.iloc[0]["o"]) / dd["pdc"] - 1) * 100, 3)
        levels = {"PDH": dd["pdh"], "PDL": dd["pdl"], "PDC": dd["pdc"]}
        dists = {k: (spy / v - 1) * 100 for k, v in levels.items()}
        near = min(dists, key=lambda k: abs(dists[k]))
        out["nearest_level"] = near
        out["nearest_level_dist_pct"] = round(dists[near], 3)
        out["pdh"], out["pdl"], out["pdc"] = dd["pdh"], dd["pdl"], dd["pdc"]
    return out


def main() -> None:
    fills, meta = load_fills()
    ep, anomalies = build_episodes(fills)
    rth, daily = load_bars()
    daily_by_date = {r["date"]: r for _, r in daily.iterrows()}

    ep["size_band"] = ep["qty"].map(size_band)
    ep["tod_bucket"] = pd.to_datetime(ep["entry_ts_et"]).dt.floor("30min").dt.strftime("%H:%M")
    ep["dow"] = pd.to_datetime(ep["entry_ts_et"]).dt.day_name()

    ctx_rows = []
    for _, r in ep.iterrows():
        if r["is_family"]:
            ctx_rows.append(context_at(pd.Timestamp(r["entry_ts_et"]), rth, daily_by_date))
        else:
            ctx_rows.append({"ctx_ok": False})
    ctx = pd.DataFrame(ctx_rows, index=ep.index)
    df = pd.concat([ep, ctx], axis=1)

    ratio = df["underlying"].map(SPOT_RATIO)
    spot_equiv = df["spy_px"] * ratio
    df["moneyness_pct"] = np.where(
        df["ctx_ok"], np.round((df["strike"] / spot_equiv - 1) * 100, 3), np.nan
    )
    # signed for the TRADE: positive = OTM in the direction of the bet
    df["otm_pct"] = np.where(df["right"] == "C", df["moneyness_pct"], -df["moneyness_pct"])

    cols = [
        "episode_id", "entry_ts_et", "exit_ts_et", "underlying", "strike", "right",
        "expiry", "dte", "is_0dte", "is_family", "bias", "qty", "n_adds", "scaled_in",
        "n_buy_fills", "n_sell_fills", "entry_px", "exit_px", "premium_at_risk",
        "pnl", "ret_pct", "hold_min", "closed", "size_band", "tod_bucket", "dow",
        "ctx_ok", "spy_px", "vwap", "vwap_side", "vwap_dist_pct", "ribbon_state",
        "ribbon_dist_pct", "sess_range_pos", "prior_30m_pct", "mins_since_open",
        "open_gap_pct", "nearest_level", "nearest_level_dist_pct", "moneyness_pct", "otm_pct",
    ]
    out = df[cols].copy()
    out_path = OUT_DIR / "trades-normalized.csv"
    out.to_csv(out_path, index=False)

    fam = out[out["is_family"] & out["closed"]]
    cov = fam["ctx_ok"].mean() * 100
    print(f"wrote {out_path}: {len(out)} rows ({len(fam)} closed family)")
    print(f"context-join coverage (closed family): {cov:.1f}%")
    print(f"anomalies: {len(anomalies)}; meta: {meta}")


if __name__ == "__main__":
    main()
