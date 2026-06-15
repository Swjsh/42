"""TRENDLINE_BREAK_RETEST scenario backtest.

Tests the playbook hypothesis from 2026-05-08: when an auto-detected trendline
breaks AND price retests a key level within 1-2 bars AND the retest bar rejects,
that's a high-quality entry.

Algorithm per 5m bar in [10:00, 14:00] ET:
  1. Run rolling detect_trendlines over last 2 RTH sessions (~ 156 bars).
  2. For each detected trendline, check break: prior bar close vs current bar
     close on opposite sides of trendline by >= $0.05 (close-through, not wick).
  3. If break detected:
     - Active levels via _detect_from_history (same logic the orchestrator uses).
     - Within next 1-2 bars: did any wick reach within $0.10 of an active level
       (excluding round-number psychological levels)?
     - Did that retest bar close on the trade side of the level?
  4. If yes → enter via simulate_trade_real (with BS fallback for puts).

Sizing & exits: v14 doctrine baseline (premium stop -8%, ITM-2 strike, qty=3).
The setup-tier sizing (ELITE 5c) is NOT applied — keep this an apples-to-apples
test against v14 BASE so the scenario's edge can be measured cleanly.

Usage:
    python tools/sweep_trendline_break_retest.py --start 2026-03-15 --end 2026-05-07
    python tools/sweep_trendline_break_retest.py --start 2026-04-01 --end 2026-05-07 --real-fills
    python tools/sweep_trendline_break_retest.py --quiet  # no per-trade printing

Output:
    analysis/backtests/trendline_break_retest_<label>/trades.csv
    analysis/backtests/trendline_break_retest_<label>/triggers.csv  (per-bar diagnostic)
    analysis/backtests/trendline_break_retest_<label>/summary.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from lib.levels import _detect_from_history  # noqa: E402
from lib.ribbon import compute_ribbon, ribbon_at  # noqa: E402
from lib.simulator import simulate_trade  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from lib.trendlines import Trendline, detect_trendlines  # noqa: E402

ANALYSIS_DIR = REPO.parent / "analysis" / "backtests"
DATA_DIR = REPO / "data"

TRENDLINE_BREAK_THRESHOLD_USD: float = 0.05
RETEST_PROXIMITY_USD: float = 0.10
RETEST_MAX_BARS: int = 2
TRENDLINE_LOOKBACK_SESSIONS: int = 2
SETUP_NAME: str = "TRENDLINE_BREAK_RETEST"


@dataclass
class TrendlineSetup:
    bar_idx: int
    timestamp_et: dt.datetime
    direction: str  # "ascending" or "descending"
    side: str  # "P" (puts on descending break of ascending line) or "C"
    trendline_slope_per_hour: float
    trendline_price_at_break: float
    break_bar_close: float
    retest_bar_idx: int
    retest_level: float
    retest_bar_low: float
    retest_bar_high: float
    retest_bar_close: float


def _latest_data_files(start_date: dt.date) -> tuple[Path, Path]:
    """Pick the SPY + VIX CSVs that span the requested window."""
    spy_candidates = sorted(DATA_DIR.glob("spy_5m_*.csv"))
    vix_candidates = sorted(DATA_DIR.glob("vix_5m_*.csv"))
    if not spy_candidates or not vix_candidates:
        raise FileNotFoundError("No SPY/VIX CSVs in data/. Run tools/fetch_data.py first.")
    return spy_candidates[-1], vix_candidates[-1]


def _load_spy(spy_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(spy_csv)
    # Normalize mixed ISO formats (T separator + space separator)
    df["timestamp_et"] = df["timestamp_et"].astype(str).str.replace("T", " ", regex=False)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp_et"]).reset_index(drop=True)
    df["timestamp_et"] = df["timestamp_et"].dt.tz_convert("America/New_York").dt.tz_localize(None)
    df["date"] = df["timestamp_et"].dt.date
    return df


def _rth_only(df: pd.DataFrame) -> pd.DataFrame:
    mask = (
        (df["timestamp_et"].dt.time >= dt.time(9, 30))
        & (df["timestamp_et"].dt.time < dt.time(16, 0))
    )
    return df.loc[mask].reset_index(drop=True)


def _detect_trendlines_at(
    rth_bars: pd.DataFrame,
    bar_idx: int,
) -> list[Trendline]:
    """Run trendline detection using bars [bar_idx - cap, bar_idx], no look-ahead."""
    if bar_idx < 30:
        return []
    bar_time = rth_bars.iloc[bar_idx]["timestamp_et"]
    cutoff_dates = sorted(rth_bars["date"].unique())
    today = bar_time.date()
    eligible_dates = [d for d in cutoff_dates if d <= today][-TRENDLINE_LOOKBACK_SESSIONS:]
    window = rth_bars.loc[
        (rth_bars["date"].isin(eligible_dates))
        & (rth_bars["timestamp_et"] <= bar_time)
    ].copy()
    if len(window) < 30:
        return []
    window["timestamp_unix"] = window["timestamp_et"].astype("int64") // 1_000_000_000
    return detect_trendlines(window)


def _is_break(
    line: Trendline,
    prior_close: float,
    cur_close: float,
    cur_ts: int,
    threshold: float,
) -> str | None:
    """Return 'down' if line broken downward (price was above, now below by ≥threshold),
    'up' if upward, else None."""
    line_now = line.price_at(cur_ts)
    line_prior = line.price_at(cur_ts - 300)  # one 5-min bar ago
    above_prior = prior_close > line_prior
    above_now = cur_close > line_now
    if above_prior and not above_now and (line_now - cur_close) >= threshold:
        return "down"
    if (not above_prior) and above_now and (cur_close - line_now) >= threshold:
        return "up"
    return None


def _find_level_retest(
    rth_bars: pd.DataFrame,
    break_bar_idx: int,
    direction: str,  # "down" or "up"
    levels_active: list[float],
    proximity: float = RETEST_PROXIMITY_USD,
    max_lookahead: int = RETEST_MAX_BARS,
) -> tuple[int, float] | None:
    """Find the bar where price retests a level after a break, if any.

    For direction='down' (puts entry): look for next bar where bar.high comes within
      `proximity` of an active level from below AND bar.close < level.
    For direction='up' (calls entry): low within proximity from above AND close > level.

    Excludes round-number levels (those that are integer dollars). The playbook spec
    requires Active/Carry tier; we approximate by dropping integers.

    Returns (retest_bar_idx, retest_level) or None.
    """
    nonround_levels = [L for L in levels_active if abs(L - round(L)) > 0.01]
    if not nonround_levels:
        return None
    for k in range(1, max_lookahead + 1):
        if break_bar_idx + k >= len(rth_bars):
            break
        bar = rth_bars.iloc[break_bar_idx + k]
        if direction == "down":
            for L in nonround_levels:
                if bar["high"] >= L - proximity and bar["high"] <= L + proximity:
                    if bar["close"] < L:
                        return break_bar_idx + k, L
        else:  # up
            for L in nonround_levels:
                if bar["low"] >= L - proximity and bar["low"] <= L + proximity:
                    if bar["close"] > L:
                        return break_bar_idx + k, L
    return None


def find_setups(
    spy_df: pd.DataFrame,
    start_date: dt.date,
    end_date: dt.date,
    min_touches: int = 3,
    entry_window: tuple[dt.time, dt.time] = (dt.time(10, 0), dt.time(14, 0)),
) -> list[TrendlineSetup]:
    """Scan bars and yield trendline-break-retest setups."""
    rth = _rth_only(spy_df)
    rth_indexed = rth.copy()
    rth_indexed["ts_unix"] = rth_indexed["timestamp_et"].astype("int64") // 1_000_000_000

    setups: list[TrendlineSetup] = []
    skip_until_idx = -1

    for idx in range(1, len(rth_indexed)):
        if idx <= skip_until_idx:
            continue
        bar = rth_indexed.iloc[idx]
        bar_time: pd.Timestamp = bar["timestamp_et"]
        bar_date = bar_time.date()
        if bar_date < start_date or bar_date > end_date:
            continue
        bar_t = bar_time.time()
        if bar_t < entry_window[0] or bar_t >= entry_window[1]:
            continue

        prior = rth_indexed.iloc[idx - 1]
        if prior["date"] != bar["date"]:
            continue

        trendlines = _detect_trendlines_at(rth_indexed, idx)
        if not trendlines:
            continue

        # Levels active at this bar (uses full SPY history including premarket).
        levels_active = _detect_from_history(
            spy_df.loc[spy_df["timestamp_et"] <= bar_time].copy(),
            bar_date,
        ).active

        prior_close = float(prior["close"])
        cur_close = float(bar["close"])
        cur_ts = int(bar["ts_unix"])

        for line in trendlines:
            if line.touch_count < min_touches:
                continue
            break_dir = _is_break(line, prior_close, cur_close, cur_ts, TRENDLINE_BREAK_THRESHOLD_USD)
            if break_dir is None:
                continue
            retest = _find_level_retest(rth_indexed, idx, break_dir, levels_active)
            if retest is None:
                continue
            retest_idx, retest_level = retest
            retest_bar = rth_indexed.iloc[retest_idx]
            side = "P" if break_dir == "down" else "C"
            setups.append(TrendlineSetup(
                bar_idx=int(retest_idx),
                timestamp_et=retest_bar["timestamp_et"].to_pydatetime(),
                direction=line.direction,
                side=side,
                trendline_slope_per_hour=float(line.slope_per_hour()),
                trendline_price_at_break=float(line.price_at(cur_ts)),
                break_bar_close=cur_close,
                retest_bar_idx=int(retest_idx),
                retest_level=float(retest_level),
                retest_bar_low=float(retest_bar["low"]),
                retest_bar_high=float(retest_bar["high"]),
                retest_bar_close=float(retest_bar["close"]),
            ))
            # Skip past this break to avoid re-firing on the same trendline.
            skip_until_idx = retest_idx + 6
            break

    return setups


def simulate_setups(
    setups: list[TrendlineSetup],
    spy_df: pd.DataFrame,
    vix_df: pd.DataFrame,
    use_real_fills: bool,
    premium_stop_pct: float = -0.08,
    strike_offset: int = -2,
    qty: int = 3,
) -> list[dict]:
    """Run each setup through the existing simulator. Returns trade rows."""
    rth = _rth_only(spy_df)
    rth_indexed = rth.copy()
    ribbon_df = compute_ribbon(rth_indexed["close"])

    # Align VIX to RTH bars
    vix_ts = pd.to_datetime(vix_df["timestamp_et"], utc=True)
    spy_ts = pd.to_datetime(rth_indexed["timestamp_et"], utc=True)
    vix_indexed_series = pd.Series(vix_df["close"].values, index=vix_ts)
    vix_aligned = vix_indexed_series.reindex(spy_ts, method="ffill")
    vix_aligned.index = range(len(vix_aligned))

    rows: list[dict] = []
    for s in setups:
        # Find the bar in the RTH dataframe matching the setup timestamp.
        match = rth_indexed[rth_indexed["timestamp_et"] == s.timestamp_et]
        if match.empty:
            continue
        idx = int(match.index[0])
        bar = rth_indexed.iloc[idx]

        levels_active = _detect_from_history(
            spy_df.loc[spy_df["timestamp_et"] <= bar["timestamp_et"]].copy(),
            bar["timestamp_et"].date(),
        )

        fill = None
        if use_real_fills:
            fill = simulate_trade_real(
                entry_bar_idx=idx,
                entry_bar=bar,
                spy_df=rth_indexed,
                ribbon_df=ribbon_df,
                rejection_level=s.retest_level,
                triggers_fired=["trendline_break", "level_retest", "rejection_close"],
                side=s.side,
                setup=SETUP_NAME,
                levels_active=levels_active.active,
                levels_carry=levels_active.multi_day,
                premium_stop_pct=premium_stop_pct,
                strike_offset=strike_offset,
                qty=qty,
            )
            if fill is None and s.side == "P":
                fill = simulate_trade(
                    entry_bar_idx=idx,
                    entry_bar=bar,
                    spy_df=rth_indexed,
                    vix_aligned=vix_aligned,
                    ribbon_df=ribbon_df,
                    rejection_level=s.retest_level,
                    triggers_fired=["trendline_break", "level_retest", "rejection_close"],
                    setup=SETUP_NAME + "::BS_FALLBACK",
                )
        else:
            if s.side == "P":
                fill = simulate_trade(
                    entry_bar_idx=idx,
                    entry_bar=bar,
                    spy_df=rth_indexed,
                    vix_aligned=vix_aligned,
                    ribbon_df=ribbon_df,
                    rejection_level=s.retest_level,
                    triggers_fired=["trendline_break", "level_retest", "rejection_close"],
                    setup=SETUP_NAME,
                )
            else:
                # BS sim doesn't model bullish — skip in non-real-fill mode.
                continue
        if fill is None:
            continue

        tp1_p = getattr(fill, "tp1_premium", None)
        runner_p = getattr(fill, "runner_exit_premium", None)
        exit_avg = None
        if tp1_p is not None and runner_p is not None:
            exit_avg = (tp1_p * 2 + runner_p) / 3
        elif runner_p is not None:
            exit_avg = runner_p
        elif tp1_p is not None:
            exit_avg = tp1_p

        rows.append({
            "date": s.timestamp_et.date().isoformat(),
            "time_entry": s.timestamp_et.time().isoformat(timespec="minutes"),
            "side": s.side,
            "trendline_direction": s.direction,
            "slope_usd_per_hour": round(s.trendline_slope_per_hour, 4),
            "trendline_price_at_break": round(s.trendline_price_at_break, 2),
            "retest_level": s.retest_level,
            "retest_bar_low": s.retest_bar_low,
            "retest_bar_high": s.retest_bar_high,
            "retest_bar_close": s.retest_bar_close,
            "entry_premium": round(getattr(fill, "entry_premium", 0.0) or 0.0, 2),
            "exit_premium_avg": round(exit_avg, 2) if exit_avg is not None else None,
            "tp1_premium": round(tp1_p, 2) if tp1_p is not None else None,
            "runner_exit_premium": round(runner_p, 2) if runner_p is not None else None,
            "qty": getattr(fill, "qty", qty),
            "dollar_pnl": round(float(getattr(fill, "dollar_pnl", 0.0) or 0.0), 2),
            "exit_reason": str(getattr(fill, "exit_reason", "unknown")),
            "hold_minutes": getattr(fill, "hold_minutes", None),
            "setup": getattr(fill, "setup", SETUP_NAME),
        })
    return rows


def summarize(rows: list[dict]) -> dict:
    if not rows:
        return {"trades": 0, "msg": "no setups fired"}
    df = pd.DataFrame(rows)
    pnl = df["dollar_pnl"].astype(float)
    wins = df[pnl > 0]
    losses = df[pnl < 0]
    total = float(pnl.sum())
    wr = float(len(wins)) / len(df) if len(df) else 0.0
    avg_win = float(wins["dollar_pnl"].mean()) if not wins.empty else 0.0
    avg_loss = float(losses["dollar_pnl"].mean()) if not losses.empty else 0.0
    wl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")
    expectancy = total / len(df) if len(df) else 0.0

    cumulative = pnl.cumsum().to_numpy()
    if len(cumulative) > 0:
        running_max = np.maximum.accumulate(cumulative)
        max_dd = float((cumulative - running_max).min())
    else:
        max_dd = 0.0

    return {
        "trades": int(len(df)),
        "total_pnl": round(total, 2),
        "win_rate": round(wr, 3),
        "avg_winner": round(avg_win, 2),
        "avg_loser": round(avg_loss, 2),
        "wl_ratio": round(wl_ratio, 2),
        "expectancy_per_trade": round(expectancy, 2),
        "max_drawdown": round(max_dd, 2),
        "puts_count": int((df["side"] == "P").sum()),
        "calls_count": int((df["side"] == "C").sum()),
        "by_exit_reason": df["exit_reason"].value_counts().to_dict(),
    }


def gate_check(s: dict) -> dict:
    return {
        "passes_gate_trades": s.get("trades", 0) >= 20,
        "passes_gate_wr": s.get("win_rate", 0.0) >= 0.45,
        "passes_gate_wl": s.get("wl_ratio", 0.0) >= 1.5,
        "passes_gate_expectancy": s.get("expectancy_per_trade", 0.0) > 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=str, required=True)
    parser.add_argument("--end", type=str, required=True)
    parser.add_argument("--real-fills", action="store_true")
    parser.add_argument("--label", type=str, default="default")
    parser.add_argument("--min-touches", type=int, default=3)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    start_d = dt.date.fromisoformat(args.start)
    end_d = dt.date.fromisoformat(args.end)

    spy_csv, vix_csv = _latest_data_files(start_d)
    spy_df = _load_spy(spy_csv)
    vix_df = pd.read_csv(vix_csv, parse_dates=["timestamp_et"])

    if not args.quiet:
        print(f"Loading SPY {spy_csv.name}, VIX {vix_csv.name}")
        print(f"Window: {args.start} -> {args.end}")

    setups = find_setups(spy_df, start_d, end_d, min_touches=args.min_touches)
    if not args.quiet:
        print(f"Found {len(setups)} candidate setups (puts: {sum(1 for s in setups if s.side == 'P')}, "
              f"calls: {sum(1 for s in setups if s.side == 'C')})")

    rows = simulate_setups(setups, spy_df, vix_df, use_real_fills=args.real_fills)
    summary = summarize(rows)
    gates = gate_check(summary)

    out_dir = ANALYSIS_DIR / f"trendline_break_retest_{args.label}"
    out_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(rows).to_csv(out_dir / "trades.csv", index=False)
    pd.DataFrame([asdict(s) for s in setups]).to_csv(out_dir / "triggers.csv", index=False)
    (out_dir / "summary.md").write_text(
        f"# TRENDLINE_BREAK_RETEST — {args.label}\n\n"
        f"**Window:** {args.start} → {args.end}\n"
        f"**Real fills:** {args.real_fills}\n"
        f"**Min touches:** {args.min_touches}\n\n"
        f"## Summary\n\n```json\n{json.dumps(summary, indent=2)}\n```\n\n"
        f"## Gate check\n\n```json\n{json.dumps(gates, indent=2)}\n```\n",
        encoding="utf-8",
    )

    if not args.quiet:
        print(json.dumps({"summary": summary, "gates": gates}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
