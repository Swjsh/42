"""T48 — Diagnose why SNIPER did NOT fire on 5/13/2026 12:20 ET ATH break.

Per queue.md T48: SPY 12:20 bar O=740.70, H=740.96, C=740.95, V=31,185.
740.79 (5/11 ATH) within proximity ($0.16 away). Body $0.25 > 0.02. require_break_above_open OK (C>O).
Most likely cause: 20-bar vol avg includes early-morning bars (78K-145K) biasing high so 31K bar < 1.1x avg.

Output:
- Volume avg comparison
- ALL SNIPER condition evaluations for the 12:20 bar
- Counterfactual: what knob change would make it fire?
- Surface to docs/T48-SNIPER-5-13-MISSFIRE-2026-05-14.md
"""
from __future__ import annotations

import sys
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backtest"))

import pandas as pd

MASTER_5M_FULL = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-05-12.csv"
MASTER_5M_TODAY = ROOT / "backtest" / "data" / "spy_5m_2026-05-08_2026-05-13.csv"
MASTER_5M = MASTER_5M_TODAY  # for today's bars; full master used separately for prior-day levels
TARGET_DATE = "2026-05-13"
TARGET_TIME = "12:20"  # ET


def load_5m_for_day(date: str) -> pd.DataFrame:
    df = pd.read_csv(MASTER_5M)
    if "timestamp_et" in df.columns:
        df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
        # Already ET if no tz
        if df["timestamp_et"].dt.tz is not None:
            df["timestamp_et"] = df["timestamp_et"].dt.tz_localize(None)
        df["date"] = df["timestamp_et"].dt.date.astype(str)
        df["time"] = df["timestamp_et"].dt.strftime("%H:%M")
    else:
        # try alternate column names
        ts_col = next((c for c in df.columns if "time" in c.lower() or "date" in c.lower()), None)
        if ts_col is None:
            raise RuntimeError(f"can't find timestamp col in {df.columns.tolist()}")
        df["timestamp_et"] = pd.to_datetime(df[ts_col])
        df["date"] = df["timestamp_et"].dt.date.astype(str)
        df["time"] = df["timestamp_et"].dt.strftime("%H:%M")

    return df[df["date"] == date].reset_index(drop=True)


def main():
    print("=== T48 SNIPER 5/13 12:20 ET ATH BREAK DIAGNOSTIC ===\n")

    df = load_5m_for_day(TARGET_DATE)
    if df.empty:
        print(f"!! No 5m bars found for {TARGET_DATE} in {MASTER_5M}")
        return

    print(f"Loaded {len(df)} bars for {TARGET_DATE}")
    print(f"First bar: {df.iloc[0]['time']}, last bar: {df.iloc[-1]['time']}")
    print(f"Columns: {df.columns.tolist()}\n")

    # Find target bar
    target_idx = df[df["time"] == TARGET_TIME].index
    if len(target_idx) == 0:
        print(f"!! No bar at {TARGET_TIME} on {TARGET_DATE}")
        return
    target_idx = int(target_idx[0])
    bar = df.iloc[target_idx]

    print(f"--- TARGET BAR (idx {target_idx}, time {bar['time']}) ---")
    # Try multiple column casings
    o = bar.get("open", bar.get("Open"))
    h = bar.get("high", bar.get("High"))
    l = bar.get("low", bar.get("Low"))
    c = bar.get("close", bar.get("Close"))
    v = bar.get("volume", bar.get("Volume"))
    print(f"O={o}, H={h}, L={l}, C={c}, V={int(v) if v else 'NA'}")
    body = abs(c - o)
    print(f"body=|C-O|={body:.4f}")
    print(f"break_above_open: {c > o} (C > O)")
    print()

    # 20-bar volume average from 19 prior bars + this bar
    # SNIPER actually uses prior 20 bars, not including current
    if target_idx < 20:
        print(f"!! Only {target_idx} prior bars available — need 20")
        prior = df.iloc[:target_idx]
    else:
        prior = df.iloc[target_idx - 20:target_idx]
    vol_col = "volume" if "volume" in df.columns else "Volume"
    prior_vol_avg = prior[vol_col].mean()
    bar_vol = bar[vol_col]
    vol_mult_actual = bar_vol / prior_vol_avg if prior_vol_avg > 0 else 0
    print(f"--- VOLUME ANALYSIS ---")
    print(f"prior_20_bar_vol_avg: {prior_vol_avg:,.0f}")
    print(f"this_bar_volume:       {bar_vol:,.0f}")
    print(f"vol_mult (bar/avg):    {vol_mult_actual:.3f}")
    print(f"sniper threshold:      1.1x")
    print(f"FIRES on volume? {vol_mult_actual >= 1.1}")
    print()

    # Show prior 20 bars for context
    print("--- PRIOR 20 BARS (for vol context) ---")
    print(prior[["time", vol_col]].to_string())
    print()
    print(f"prior_vol_min: {prior[vol_col].min():,.0f}")
    print(f"prior_vol_max: {prior[vol_col].max():,.0f}")
    print(f"prior_vol_median: {prior[vol_col].median():,.0f}")
    print()

    # Counterfactual analyses
    print("--- COUNTERFACTUAL ANALYSES ---")

    # CF1: what if we use rolling-20 from 9:30 onward (RTH only) — the 09:30+ bars
    rth = df[df["time"] >= "09:30"].reset_index(drop=True)
    rth_target_idx = rth[rth["time"] == TARGET_TIME].index
    if len(rth_target_idx) > 0:
        rth_target_idx = int(rth_target_idx[0])
        rth_prior = rth.iloc[max(0, rth_target_idx - 20):rth_target_idx]
        rth_avg = rth_prior[vol_col].mean()
        rth_mult = bar_vol / rth_avg if rth_avg > 0 else 0
        print(f"CF1 (RTH-only 20-bar avg): avg={rth_avg:,.0f}, mult={rth_mult:.3f}, fires? {rth_mult >= 1.1}")

    # CF2: median instead of mean (robust to outliers)
    median_mult = bar_vol / prior[vol_col].median() if prior[vol_col].median() > 0 else 0
    print(f"CF2 (median 20-bar):       median_mult={median_mult:.3f}, fires? {median_mult >= 1.1}")

    # CF3: Time-decay weighted (recent bars 2x weight)
    n = len(prior)
    weights = list(range(1, n + 1))  # 1, 2, ..., n
    weighted_avg = (prior[vol_col] * weights).sum() / sum(weights)
    weighted_mult = bar_vol / weighted_avg if weighted_avg > 0 else 0
    print(f"CF3 (time-decay weighted): avg={weighted_avg:,.0f}, mult={weighted_mult:.3f}, fires? {weighted_mult >= 1.1}")

    # CF4: Drop top 25% bars before averaging
    trimmed = prior[vol_col].sort_values()
    n_keep = int(0.75 * len(trimmed))
    trimmed_avg = trimmed.iloc[:n_keep].mean()
    trimmed_mult = bar_vol / trimmed_avg if trimmed_avg > 0 else 0
    print(f"CF4 (drop-top-25% avg):    avg={trimmed_avg:,.0f}, mult={trimmed_mult:.3f}, fires? {trimmed_mult >= 1.1}")

    # CF5: Absolute-volume-fallback rule
    print(f"CF5 (abs-vol >= 10K AND body >= 0.30): vol={bar_vol >= 10000}, body={body >= 0.30}, fires? {(bar_vol >= 10000) and (body >= 0.30)}")

    # CF6: Lower vol_mult threshold
    print(f"CF6 (lower threshold 1.0): mult={vol_mult_actual:.3f}, fires? {vol_mult_actual >= 1.0}")

    print()
    print("--- BIAS CHECK: VWAP / 5/11 ATH proximity ---")
    # ATH from 5/11 was 740.79
    ATH = 740.79
    proximity = abs(bar.get("high", bar.get("High")) - ATH)
    print(f"5/11 ATH: {ATH}")
    print(f"bar_high: {h}, distance to ATH: {proximity:.4f}")
    print(f"within $0.20 proximity? {proximity <= 0.20}")
    print()

    # WHEN was the ATH first broken?
    print("--- ATH BREAK CHRONOLOGY ---")
    rth_bars = df[df["time"] >= "09:30"].reset_index(drop=True)
    above_ath = rth_bars[rth_bars["high"] > ATH]
    if not above_ath.empty:
        first_break = above_ath.iloc[0]
        print(f"First bar with high > ATH ({ATH}): time={first_break['time']}, O={first_break['open']:.2f}, H={first_break['high']:.2f}, C={first_break['close']:.2f}, V={int(first_break['volume']):,}")
        first_break_idx = rth_bars[rth_bars["time"] == first_break["time"]].index[0]
        # 20-bar prior avg for that bar
        if first_break_idx >= 20:
            fb_prior = rth_bars.iloc[first_break_idx - 20:first_break_idx]
        else:
            fb_prior = rth_bars.iloc[:first_break_idx]
        fb_prior_avg = fb_prior["volume"].mean()
        fb_mult = first_break["volume"] / fb_prior_avg if fb_prior_avg > 0 else 0
        fb_body = abs(first_break["close"] - first_break["open"])
        print(f"  body={fb_body:.4f}, vol_mult={fb_mult:.3f}, break_above_open? {first_break['close'] > first_break['open']}")
    print()

    # SNIPER level set as of 12:20 ET on 5/13
    print("--- SNIPER LEVEL SET as of 5/13 12:20 ET ---")
    # Use FULL master CSV for proper 5-day window (today's CSV only has 5/08-5/13)
    master = pd.read_csv(MASTER_5M_FULL)
    master["timestamp_et"] = pd.to_datetime(master["timestamp_et"])
    if master["timestamp_et"].dt.tz is not None:
        master["timestamp_et"] = master["timestamp_et"].dt.tz_localize(None)
    master["date"] = master["timestamp_et"].dt.date.astype(str)
    master["time"] = master["timestamp_et"].dt.strftime("%H:%M")

    prior_rth = master[
        (master["date"] < TARGET_DATE)
        & (master["time"] >= "09:30")
        & (master["time"] < "16:00")
    ]
    prior_dates = sorted(prior_rth["date"].unique())
    print(f"Prior RTH date count: {len(prior_dates)}, last 6: {prior_dates[-6:]}")

    if prior_dates:
        last_prior = prior_dates[-1]
        last_day = prior_rth[prior_rth["date"] == last_prior]
        pdh = last_day["high"].max()
        pdl = last_day["low"].min()
        print(f"prior_day_high (PDH on {last_prior}): {pdh:.2f}  [stars=2 Active]")
        print(f"prior_day_low  (PDL on {last_prior}): {pdl:.2f}  [stars=2 Active]")

        five_d = prior_dates[-5:]
        five_d_data = prior_rth[prior_rth["date"].isin(five_d)]
        h5 = five_d_data["high"].max()
        l5 = five_d_data["low"].min()
        print(f"5d_high (over {five_d}): {h5:.2f}  [stars=3 Carry]")
        print(f"5d_low  (over {five_d}): {l5:.2f}  [stars=3 Carry]")

        # Show 5/11 high specifically
        if "2026-05-11" in prior_dates:
            d511 = prior_rth[prior_rth["date"] == "2026-05-11"]
            print(f"5/11 RTH high (queue.md ATH claim): {d511['high'].max():.2f}")
        if "2026-05-12" in prior_dates:
            d512 = prior_rth[prior_rth["date"] == "2026-05-12"]
            print(f"5/12 RTH high: {d512['high'].max():.2f}")
    print()

    # Where was 5/13 RTH high BEFORE 12:20?
    print("--- 5/13 RTH HIGH BEFORE 12:20 ---")
    pre_target = df[(df["time"] >= "09:30") & (df["time"] < TARGET_TIME)]
    if not pre_target.empty:
        pre_high = pre_target["high"].max()
        pre_high_bar = pre_target.loc[pre_target["high"].idxmax()]
        print(f"5/13 high before 12:20: {pre_high:.2f} at {pre_high_bar['time']}")
        if prior_dates:
            print(f"  vs PDH ({pdh:.2f}): {'BROKEN' if pre_high > pdh else 'INTACT'}")
            print(f"  vs 5d_high ({h5:.2f}): {'BROKEN' if pre_high > h5 else 'INTACT'}")
    print()

    # SIMULATE SNIPER on 5/13 with v15 default params
    print("--- SNIPER FULL DAY TRACE on 5/13 ---")
    sys.path.insert(0, str(ROOT / "backtest"))
    import datetime as dt
    from lib.sniper_detector import SniperParams, SniperLevel, detect_sniper_break, vol_baseline_20

    # Build level set as of 5/13 09:30
    levels = []
    if prior_dates:
        # PDH/PDL
        last_day = prior_rth[prior_rth["date"] == last_prior]
        levels.append(SniperLevel(price=float(last_day["high"].max()), stars=2, label="prior_day_high", tier="Active"))
        levels.append(SniperLevel(price=float(last_day["low"].min()), stars=2, label="prior_day_low", tier="Active"))
        five_d_data = prior_rth[prior_rth["date"].isin(prior_dates[-5:])]
        levels.append(SniperLevel(price=float(five_d_data["high"].max()), stars=3, label="5d_high", tier="Carry"))
        levels.append(SniperLevel(price=float(five_d_data["low"].min()), stars=3, label="5d_low", tier="Carry"))

    print(f"Levels: {[(l.label, l.price, l.stars) for l in levels]}")

    # Production sniper-v1.json combo
    params = SniperParams(
        vol_mult=1.1,
        body_min_cents=0.02,
        no_trade_before=dt.time(9, 30),
        no_trade_after=dt.time(15, 50),
        require_break_above_open=True,
        min_stars=2,
        use_prior_day_levels=True,
        use_5d_levels=True,
    )

    # Simulate over 5/13 RTH
    rth_513 = df[(df["time"] >= "09:30") & (df["time"] <= "15:50")].reset_index(drop=True)
    print()
    print(f"RTH bars on 5/13: {len(rth_513)}")
    print()

    fires = []
    for idx in range(len(rth_513)):
        bar = rth_513.iloc[idx]
        signal = detect_sniper_break(bar, idx, rth_513, levels, params)
        if signal:
            fires.append((bar["time"], signal))
            print(f"  FIRE at {bar['time']}: {signal.direction} {signal.reason}")

    print(f"\nTotal SNIPER fires on 5/13: {len(fires)}")

    # Specifically check the 12:20 bar for why it didn't fire
    print()
    print("--- 12:20 BAR DETAILED CHECK ---")
    bar_1220_idx = rth_513[rth_513["time"] == "12:20"].index[0]
    bar_1220 = rth_513.iloc[bar_1220_idx]
    prior_1215 = rth_513.iloc[bar_1220_idx - 1]
    print(f"prior bar 12:15 close: {prior_1215['close']:.4f}")
    print(f"12:20: O={bar_1220['open']:.4f}, C={bar_1220['close']:.4f}, V={int(bar_1220['volume']):,}")
    for level in levels:
        if level.stars < params.min_stars:
            continue
        # UP-reclaim check
        cond_a = prior_1215['close'] < level.price - 0.001
        cond_b = bar_1220['close'] > level.price + params.body_min_cents
        cond_c = bar_1220['close'] > bar_1220['open']
        print(f"  {level.label}({level.price:.2f}): prior_below={cond_a}, this_above_by_body={cond_b}, break_above_open={cond_c} -> fires? {cond_a and cond_b and cond_c}")
    print()

    # Conclusion
    print("=== VERDICT ===")
    if vol_mult_actual < 1.1:
        print(f"PRIMARY MISS REASON: vol_mult={vol_mult_actual:.2f} < 1.1 threshold (volume avg biased high by AM bars)")
        if median_mult >= 1.1:
            print(f"FIX: Use MEDIAN instead of MEAN: would fire ({median_mult:.2f} >= 1.1)")
        elif weighted_mult >= 1.1:
            print(f"FIX: Time-decay weighted avg: would fire ({weighted_mult:.2f} >= 1.1)")
        elif trimmed_mult >= 1.1:
            print(f"FIX: Drop top-25% bars: would fire ({trimmed_mult:.2f} >= 1.1)")
        elif (bar_vol >= 10000 and body >= 0.30):
            print(f"FIX: Absolute-vol fallback (vol>=10K AND body>=0.30): would fire")
        else:
            print(f"FIX: Lower threshold OR multiple changes needed")
    else:
        print(f"vol_mult={vol_mult_actual:.2f} PASSES — miss must be elsewhere")


if __name__ == "__main__":
    main()
