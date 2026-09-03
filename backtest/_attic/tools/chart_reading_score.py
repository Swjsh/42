"""CHART READING SCORE — encode what a human sees before entering a trade.

J's insight: the engine sees filter checks. A human sees a picture. This builds
a composite 'chart reading' score at the moment of each entry bar and correlates
it with the resulting P&L on real fills. If the chart picture predicts winners,
we have a trainable pre-entry signal.

At the trigger bar (the bar where all filters pass), a human would see:

1. RIBBON DURATION: how many consecutive bars has the ribbon been stacked in this
   direction? Fresh flip (1-2 bars) is riskier than established trend (10+ bars).

2. RIBBON MOMENTUM: is the spread widening (gaining conviction) or compressing
   (losing conviction)? Widening spread = the trend is accelerating.

3. REJECTION CANDLE: body-to-range ratio, wick direction, close position relative
   to range. A full-body shooting star is a better rejection signal than a doji.

4. VOLUME CONVICTION: volume on the trigger bar vs. 20-bar average. High volume
   rejection = institutional participation.

5. LEVEL FRESHNESS: first touch of this level today (high edge) vs. 4th retest
   (level being absorbed/broken). From bounce_history in filters.py.

6. FAILED PRIOR ATTEMPT: did this exact setup already stop out today?
   Second attempt after a stop = lower WR historically.

7. DISTANCE FROM RIBBON: how far is entry price from the fast EMA? Close = you're
   entering at the ribbon (good), far = you're chasing (bad).

All 7 visual features are available at the trigger bar. We can compute them from
spy_df + ribbon_df without any look-ahead.
"""
from __future__ import annotations
import sys, json, datetime as dt
from pathlib import Path
from collections import defaultdict
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import sniper_matrix as SM
from lib.ribbon import compute_ribbon, ribbon_at

DATA = REPO / "data"
ABT = REPO.parent / "analysis" / "backtests"


def ribbon_duration(ribbon_df: pd.DataFrame, idx: int, stack: str) -> int:
    """How many consecutive bars has ribbon been stacked in `stack` direction ending at idx?"""
    count = 0
    for i in range(idx, -1, -1):
        st = ribbon_at(ribbon_df, i)
        if st is None or st.stack != stack:
            break
        count += 1
    return count


def ribbon_momentum(ribbon_df: pd.DataFrame, idx: int) -> float:
    """Spread delta: spread now minus spread 3 bars ago. + = widening, - = compressing."""
    if idx < 3:
        return 0.0
    now = ribbon_at(ribbon_df, idx)
    prev = ribbon_at(ribbon_df, idx - 3)
    if now is None or prev is None:
        return 0.0
    return round(now.spread_cents - prev.spread_cents, 1)


def candle_score(bar: pd.Series, side: str) -> dict:
    """Body-to-range, wick direction, close position. Range 0-1, higher = better rejection."""
    o, h, l, c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
    rng = h - l
    if rng < 0.01:
        return {"body_pct": 0.0, "close_pos": 0.5, "wick_favor": 0.0}
    body = abs(c - o) / rng
    close_pos = (c - l) / rng  # 0=bottom, 1=top
    # For BEAR entry: close should be low (shooting star shape)
    # For BULL entry: close should be high (hammer shape)
    wick_favor = (1.0 - close_pos) if side == "P" else close_pos
    return {"body_pct": round(body, 2), "close_pos": round(close_pos, 2), "wick_favor": round(wick_favor, 2)}


def volume_conv(rth: pd.DataFrame, idx: int) -> float:
    """Volume on trigger bar vs. 20-bar average. >1.5 = institutional."""
    if idx < 5:
        return 1.0
    vol = float(rth.iloc[idx]["volume"])
    avg = float(rth.iloc[max(0, idx - 20):idx]["volume"].mean())
    return round(vol / avg, 2) if avg > 0 else 1.0


def ema_distance(rth: pd.DataFrame, ribbon_df: pd.DataFrame, idx: int) -> float:
    """Distance of close from fast EMA in cents. Closer = better entry."""
    st = ribbon_at(ribbon_df, idx)
    if st is None or pd.isna(st.fast):
        return 999.0
    close = float(rth.iloc[idx]["close"])
    return round(abs(close - st.fast) * 100, 1)  # in cents


def compute_chart_score(
    rth: pd.DataFrame,
    ribbon_df: pd.DataFrame,
    trigger_idx: int,
    side: str,
    failed_today: bool,
) -> dict:
    """Composite chart reading at the trigger bar."""
    bar = rth.iloc[trigger_idx]
    st = ribbon_at(ribbon_df, trigger_idx)
    if st is None:
        return {}

    rdur = ribbon_duration(ribbon_df, trigger_idx, st.stack)
    rmom = ribbon_momentum(ribbon_df, trigger_idx)
    cand = candle_score(bar, side)
    vcov = volume_conv(rth, trigger_idx)
    edist = ema_distance(rth, ribbon_df, trigger_idx)

    # Composite 0-10 score (human's gestalt)
    score = 0.0
    # Ribbon duration (capped at 20 bars = 2 points)
    score += min(rdur / 10, 2.0)
    # Ribbon momentum widening = good (1 point)
    score += min(max(rmom / 30, -1.0), 1.0)
    # Candle wick direction (2 points)
    score += cand["wick_favor"] * 2.0
    # Candle body size (1 point)
    score += cand["body_pct"]
    # Volume conviction (2 points, capped at 3x)
    score += min(vcov / 1.5, 2.0)
    # EMA distance: <30 cents = 2 points, scaled down
    score += max(2.0 - edist / 30, 0.0)
    # Prior failure penalty (-2 points)
    if failed_today:
        score -= 2.0

    return {
        "ribbon_duration": rdur,
        "ribbon_momentum": rmom,
        "wick_favor": cand["wick_favor"],
        "body_pct": cand["body_pct"],
        "close_pos": cand["close_pos"],
        "volume_conv": vcov,
        "ema_dist_cents": edist,
        "failed_today": failed_today,
        "chart_score": round(score, 2),
    }


def main():
    cands = [p for p in DATA.glob("spy_5m_*.csv") if (DATA / p.name.replace("spy_5m", "vix_5m")).exists()]
    cands.sort(key=lambda p: p.stat().st_size, reverse=True)
    master = cands[0]

    spy_raw = pd.read_csv(master)
    spy_raw["timestamp_et"] = SM._to_et(spy_raw["timestamp_et"])
    rth_all = spy_raw[(spy_raw["timestamp_et"].dt.time >= dt.time(9, 30)) &
                      (spy_raw["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    rth_all["vol_avg20"] = rth_all["volume"].rolling(20, min_periods=5).mean()
    ribbon_all = compute_ribbon(rth_all["close"])

    spy_str = SM.norm_str(pd.read_csv(master))
    vix_str = SM.norm_str(pd.read_csv(DATA / master.name.replace("spy_5m", "vix_5m")))

    from collections import Counter
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    fill_days = sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})
    spy_dates = set(SM._to_et(pd.read_csv(master)["timestamp_et"]).dt.date)
    missed = {dt.date(2026, 5, 26), dt.date(2026, 5, 27), dt.date(2026, 5, 28), dt.date(2026, 5, 29)}
    oos = sorted([d for d in fill_days if d in spy_dates and d not in missed])

    r = SM.run_backtest(spy_str, vix_str, start_date=min(oos), end_date=max(oos),
                        use_real_fills=True, no_trade_before=dt.time(9, 35))
    trades = [t for t in r.trades if t.entry_time_et.date() in set(oos) and "FALLBACK" not in t.setup]
    assert len(trades) >= 20, f"GUARD: {len(trades)}"

    # For each trade, find its trigger bar in rth_all and compute chart score
    records = []
    failed_by_day: dict[dt.date, bool] = defaultdict(bool)
    for t in sorted(trades, key=lambda x: x.entry_time_et):
        d = t.entry_time_et.date()
        side = "P" if "BEARISH" in t.setup else "C"
        t_dt = t.entry_time_et
        if hasattr(t_dt, "tzinfo") and t_dt.tzinfo is not None:
            import pytz
            t_dt_naive = t_dt.astimezone(pytz.utc).replace(tzinfo=None)
        else:
            t_dt_naive = t_dt
        # Find the trigger bar (fill bar - 1)
        cand_idx = None
        for i, row in rth_all.iterrows():
            row_t = row["timestamp_et"]
            if hasattr(row_t, "tzinfo") and row_t.tzinfo is not None:
                row_t = row_t.tz_localize(None) if hasattr(row_t, "tz_localize") else row_t
            # Within 5 minutes of entry
            if row["timestamp_et"].date() == d and abs((row["timestamp_et"].replace(tzinfo=None) - t_dt_naive).total_seconds()) < 310:
                cand_idx = i
                break
        if cand_idx is None or cand_idx < 5:
            continue
        trigger_idx = max(0, cand_idx - 1)
        cs = compute_chart_score(rth_all, ribbon_all, trigger_idx, side, failed_by_day[d])
        if not cs:
            continue
        pc = t.dollar_pnl / max(1, t.qty)
        win = t.dollar_pnl > 0
        if not win and t.exit_reason and "STOP" in t.exit_reason.value:
            failed_by_day[d] = True
        records.append({**cs, "pc": round(pc, 1), "win": win, "date": d.isoformat(),
                        "side": side, "exit": t.exit_reason.value if t.exit_reason else "?"})

    if not records:
        print("No records computed — check timestamp matching"); return

    # Bucket by chart_score quartile and show WR + per-trade
    df = pd.DataFrame(records)
    df["score_bucket"] = pd.qcut(df["chart_score"], 4, labels=["Q1(low)", "Q2", "Q3", "Q4(high)"])

    out = ["# CHART READING SCORE — does the visual quality of the setup predict winners?", "",
           f"Built from {len(records)} OOS real-fills trades. Each trade scored 0-10 on:", "",
           "- **Ribbon duration** (how long established)", "- **Ribbon momentum** (spreading vs compressing)",
           "- **Rejection candle** (wick direction, body size)", "- **Volume conviction** (vs 20-bar avg)",
           "- **EMA distance** (how close to the ribbon at entry)", "- **Failed today penalty** (-2 if prior stop)", "",
           "## Score by quartile", "",
           "| quartile | n | WR | per-trade /c | verdict |",
           "|---|---|---|---|---|"]

    for bucket, grp in df.groupby("score_bucket", observed=True):
        n = len(grp); w = grp["win"].sum()
        pc = grp["pc"].sum() / n
        verdict = "ENTER" if pc > 5 else "SELECTIVE" if pc > 0 else "SKIP"
        out.append(f"| {bucket} | {n} | {w/n:.2f} | {pc:+.1f} | **{verdict}** |")

    out += ["", "## By individual feature (top correlation with winning)",
            "| feature | winners mean | losers mean | signal strength |"]
    out.append("|---|---|---|---|")
    wins = df[df["win"]]
    losers = df[~df["win"]]
    for feat in ["chart_score", "ribbon_duration", "ribbon_momentum", "wick_favor",
                 "volume_conv", "ema_dist_cents", "failed_today"]:
        wm = wins[feat].mean() if len(wins) else 0
        lm = losers[feat].mean() if len(losers) else 0
        strength = round(abs(wm - lm) / (max(abs(wm), abs(lm), 0.01)) * 10, 1)
        out.append(f"| {feat} | {wm:.2f} | {lm:.2f} | {'★'*min(int(strength),5)} |")

    (REPO.parent / "analysis" / "chart-reading-score-2026-05-31.md").write_text(
        "\n".join(out), encoding="utf-8")
    (ABT / "_chart_score.json").write_text(
        json.dumps({"records": records, "n": len(records)}, indent=2, default=str))

    print(f"Chart score built on {len(records)} trades:")
    for bucket, grp in df.groupby("score_bucket", observed=True):
        print(f"  {bucket}: n={len(grp)} WR={grp['win'].mean():.2f} pc/trade={grp['pc'].mean():+.1f}")
    print("wrote analysis/chart-reading-score-2026-05-31.md + _chart_score.json")


if __name__ == "__main__":
    raise SystemExit(main())
