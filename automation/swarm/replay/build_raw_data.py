"""
Synthesize raw_data.json for a historical date — replay-mode replacement for
the live data_fetcher.md stage that depends on TradingView + Alpaca MCP.

Reads:
  - backtest/data/spy_5m_*.csv          (16+ months of SPY 5m bars)
  - backtest/data/vix_5m_*.csv          (16+ months of VIX 5m bars)
  - automation/swarm/replay/cache/sector_etf_daily.csv  (yfinance cache, XLK/XLF/XLE/SPY daily)

Writes:
  - automation/swarm/state/raw_data.json  (or --output path)

Schema matches data_fetcher.md exactly so downstream stages (technical, macro,
level_thesis, internals, validator, synthesis) consume it without modification.

Usage:
  python build_raw_data.py --date 2026-05-14 --as-of 06:00
  python build_raw_data.py --date 2026-05-14 --as-of 06:00 --output /tmp/raw_data.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ET = ZoneInfo("America/New_York")
WORK_DIR = Path(__file__).parent.parent.parent.parent.resolve()
SWARM_DIR = WORK_DIR / "automation" / "swarm"
REPLAY_DIR = SWARM_DIR / "replay"
CACHE_DIR = REPLAY_DIR / "cache"

# Saty Pivot Ribbon — periods fingerprinted from J's chart (backtest/lib/ribbon.py uses 13/20/48)
sys.path.insert(0, str(WORK_DIR / "backtest"))
from lib.ribbon import compute_ribbon as _compute_ribbon_canonical, load_periods as _load_ribbon_periods  # noqa: E402

_RIBBON_PERIODS = _load_ribbon_periods()
EMA_FAST = _RIBBON_PERIODS["fast_ema"]
EMA_PIVOT = _RIBBON_PERIODS["pivot_ema"]
EMA_SLOW = _RIBBON_PERIODS["slow_ema"]

SPY_CSV_DEFAULT = WORK_DIR / "backtest" / "data" / "spy_5m_2025-01-01_2026-05-15.csv"
VIX_CSV_DEFAULT = WORK_DIR / "backtest" / "data" / "vix_5m_2025-01-01_2026-05-15.csv"


@dataclass(frozen=True)
class ReplayWindow:
    """The 'as-of' moment we're replaying — everything past this is hidden."""
    date_et: str   # YYYY-MM-DD
    as_of_et: datetime  # tz-aware ET datetime


def _log(msg: str) -> None:
    print(f"[build_raw_data] {msg}", flush=True)


def _load_5m_csv(path: Path, label: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"{label} CSV missing: {path}")
    df = pd.read_csv(path, parse_dates=["timestamp_et"])
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert(ET).dt.tz_localize(None)
    df = df.sort_values("timestamp_et").reset_index(drop=True)
    return df


def _filter_to_as_of(df: pd.DataFrame, as_of: datetime) -> pd.DataFrame:
    """Keep only bars whose timestamp is strictly before the as-of moment."""
    as_of_naive = as_of.replace(tzinfo=None) if as_of.tzinfo else as_of
    return df[df["timestamp_et"] < as_of_naive].copy()


def _compute_ribbon(spy_bars: pd.DataFrame) -> dict:
    if len(spy_bars) < EMA_SLOW:
        return {
            "fast": None, "pivot": None, "slow": None,
            "stack": "UNKNOWN", "spread_cents": 0,
            "note": f"insufficient_bars_for_ribbon ({len(spy_bars)} < {EMA_SLOW})",
        }
    closes = spy_bars["close"].astype(float).reset_index(drop=True)
    ribbon_df = _compute_ribbon_canonical(closes, _RIBBON_PERIODS)
    last = ribbon_df.iloc[-1]
    fast, pivot, slow = float(last["fast"]), float(last["pivot"]), float(last["slow"])
    if fast > pivot > slow:
        stack = "BULL"
    elif fast < pivot < slow:
        stack = "BEAR"
    else:
        stack = "MIXED"
    return {
        "fast": round(fast, 2),
        "pivot": round(pivot, 2),
        "slow": round(slow, 2),
        "stack": stack,
        "spread_cents": int(round(float(last["spread_cents"]))),
        "periods": {"fast_ema": EMA_FAST, "pivot_ema": EMA_PIVOT, "slow_ema": EMA_SLOW},
    }


def _vix_snapshot(vix_df: pd.DataFrame, window: ReplayWindow) -> dict:
    """Compute VIX state at the as-of moment, including direction vs prior session close."""
    if vix_df.empty:
        return {"current": None, "direction": "flat", "iv_regime": "MID",
                "change_pct": 0.0, "note": "vix_data_empty"}

    current_row = vix_df.iloc[-1]
    current = float(current_row["close"])

    target_date = pd.Timestamp(window.date_et)
    prior_session = vix_df[vix_df["timestamp_et"] < target_date]
    if prior_session.empty:
        change_pct = 0.0
    else:
        cutoff = prior_session["timestamp_et"].max().replace(hour=16, minute=0, second=0)
        prior_close_rows = prior_session[prior_session["timestamp_et"] <= cutoff]
        if prior_close_rows.empty:
            change_pct = 0.0
        else:
            prior_close = float(prior_close_rows.iloc[-1]["close"])
            change_pct = (current - prior_close) / prior_close * 100 if prior_close else 0.0

    if change_pct > 0.5:
        direction = "rising"
    elif change_pct < -0.5:
        direction = "falling"
    else:
        direction = "flat"

    if current < 15:
        iv_regime = "LOW"
    elif current <= 22:
        iv_regime = "MID"
    else:
        iv_regime = "HIGH"

    return {
        "current": round(current, 2),
        "direction": direction,
        "change_pct": round(change_pct, 2),
        "iv_regime": iv_regime,
    }


def _spy_context(spy_bars: pd.DataFrame, window: ReplayWindow) -> dict:
    """Premarket H/L, overnight gap, current vs prior session close."""
    target_date = window.date_et
    today_pre_open = spy_bars[
        (spy_bars["timestamp_et"].dt.strftime("%Y-%m-%d") == target_date) &
        (spy_bars["timestamp_et"].dt.time < time(9, 30))
    ]

    prior_session_bars = spy_bars[spy_bars["timestamp_et"].dt.strftime("%Y-%m-%d") < target_date]
    if prior_session_bars.empty:
        return {"current_price": None, "prior_session_close": None,
                "overnight_gap_dollars": 0.0, "overnight_gap_dir": "flat",
                "premarket_high": None, "premarket_low": None,
                "note": "no_prior_session_bars"}

    last_bar = spy_bars.iloc[-1]
    current_price = float(last_bar["close"])

    prior_date = prior_session_bars["timestamp_et"].dt.strftime("%Y-%m-%d").max()
    prior_day_rth = prior_session_bars[
        (prior_session_bars["timestamp_et"].dt.strftime("%Y-%m-%d") == prior_date) &
        (prior_session_bars["timestamp_et"].dt.time < time(16, 0))
    ]
    prior_close = float(prior_day_rth.iloc[-1]["close"]) if not prior_day_rth.empty else None

    if prior_close is not None:
        gap = current_price - prior_close
        if gap > 0.50:
            gap_dir = "up"
        elif gap < -0.50:
            gap_dir = "down"
        else:
            gap_dir = "flat"
    else:
        gap = 0.0
        gap_dir = "flat"

    premarket_high = float(today_pre_open["high"].max()) if not today_pre_open.empty else None
    premarket_low = float(today_pre_open["low"].min()) if not today_pre_open.empty else None

    return {
        "current_price": round(current_price, 2),
        "prior_session_close": round(prior_close, 2) if prior_close is not None else None,
        "overnight_gap_dollars": round(gap, 2),
        "overnight_gap_dir": gap_dir,
        "premarket_high": round(premarket_high, 2) if premarket_high is not None else None,
        "premarket_low": round(premarket_low, 2) if premarket_low is not None else None,
    }


def _load_sector_cache() -> pd.DataFrame | None:
    """Load cached sector ETF daily bars (XLK/XLF/XLE/SPY)."""
    cache_path = CACHE_DIR / "sector_etf_daily.csv"
    if not cache_path.exists():
        return None
    df = pd.read_csv(cache_path, parse_dates=["date"])
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    return df


def _fetch_sector_cache_or_yfinance(window: ReplayWindow) -> pd.DataFrame | None:
    """Try cache first; fall back to yfinance fetch if missing or stale."""
    df = _load_sector_cache()
    target = pd.Timestamp(window.date_et).normalize()
    if df is not None and not df.empty and df["date"].max() >= target:
        return df

    try:
        import yfinance as yf
    except ImportError:
        _log("yfinance not installed — skipping sector data")
        return df

    _log("fetching sector ETF history from yfinance (XLK/XLF/XLE/SPY 2024-01-01 .. today)")
    rows = []
    try:
        for ticker in ["XLK", "XLF", "XLE", "SPY"]:
            t = yf.Ticker(ticker)
            hist = t.history(start="2024-01-01", interval="1d", auto_adjust=False)
            if hist.empty:
                continue
            for idx, row in hist.iterrows():
                rows.append({
                    "ticker": ticker,
                    "date": idx.tz_localize(None) if idx.tzinfo else idx,
                    "open": float(row["Open"]),
                    "close": float(row["Close"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "volume": int(row["Volume"]) if not pd.isna(row["Volume"]) else 0,
                })
    except Exception as exc:
        _log(f"yfinance fetch failed: {exc}")
        return df

    out = pd.DataFrame(rows)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(CACHE_DIR / "sector_etf_daily.csv", index=False)
    _log(f"sector cache written: {len(out)} rows")
    return out


def _sector_snapshot(window: ReplayWindow) -> tuple[dict, str]:
    """For the most recent COMPLETED session before window.date_et, compute per-ticker direction."""
    df = _fetch_sector_cache_or_yfinance(window)
    if df is None or df.empty:
        return ({"XLK": None, "XLF": None, "XLE": None, "SPY": None}, "mixed")

    target = pd.Timestamp(window.date_et).normalize()
    prior_session_rows = df[df["date"] < target]
    if prior_session_rows.empty:
        return ({"XLK": None, "XLF": None, "XLE": None, "SPY": None}, "mixed")

    prior_date = prior_session_rows["date"].max()
    snapshot = {}
    for ticker in ["XLK", "XLF", "XLE", "SPY"]:
        row = prior_session_rows[(prior_session_rows["ticker"] == ticker) & (prior_session_rows["date"] == prior_date)]
        if row.empty:
            snapshot[ticker] = None
            continue
        open_p = float(row.iloc[0]["open"])
        close_p = float(row.iloc[0]["close"])
        change_pct = (close_p - open_p) / open_p * 100 if open_p else 0.0
        if change_pct > 0.3:
            direction = "up"
        elif change_pct < -0.3:
            direction = "down"
        else:
            direction = "flat"
        snapshot[ticker] = {
            "close": round(close_p, 2),
            "change_pct": round(change_pct, 2),
            "direction": direction,
        }

    xlk_dir = snapshot.get("XLK", {}).get("direction") if snapshot.get("XLK") else None
    xlf_dir = snapshot.get("XLF", {}).get("direction") if snapshot.get("XLF") else None
    xle_dir = snapshot.get("XLE", {}).get("direction") if snapshot.get("XLE") else None
    spy_dir = snapshot.get("SPY", {}).get("direction") if snapshot.get("SPY") else None

    if xlk_dir == "up" and spy_dir == "up":
        rotation = "risk_on"
    elif xle_dir == "up" and xlk_dir == "down":
        rotation = "risk_off"
    elif xlk_dir == "down" and xlf_dir == "down":
        rotation = "risk_off"
    else:
        rotation = "mixed"

    return snapshot, rotation


def build_raw_data(date_et: str, as_of_hhmm: str,
                   spy_csv: Path = SPY_CSV_DEFAULT,
                   vix_csv: Path = VIX_CSV_DEFAULT,
                   output_path: Path | None = None) -> dict:
    as_of_dt = datetime.fromisoformat(f"{date_et}T{as_of_hhmm}:00").replace(tzinfo=ET)
    window = ReplayWindow(date_et=date_et, as_of_et=as_of_dt)

    _log(f"replay window: date={date_et} as_of={as_of_hhmm} ET")

    spy_df = _load_5m_csv(spy_csv, "SPY")
    vix_df = _load_5m_csv(vix_csv, "VIX")

    spy_to_now = _filter_to_as_of(spy_df, as_of_dt)
    vix_to_now = _filter_to_as_of(vix_df, as_of_dt)

    if spy_to_now.empty:
        raise RuntimeError(f"No SPY bars available before {date_et} {as_of_hhmm}")

    last_20_bars = spy_to_now.tail(20)
    spy_bars_out = [
        {
            "time": row["timestamp_et"].isoformat(),
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
            "volume": int(row["volume"]),
        }
        for _, row in last_20_bars.iterrows()
    ]

    ribbon_basis = spy_to_now.tail(EMA_SLOW * 3)
    ribbon = _compute_ribbon(ribbon_basis)
    vix = _vix_snapshot(vix_to_now, window)
    spy_context = _spy_context(spy_to_now, window)
    sectors, rotation = _sector_snapshot(window)

    raw_data = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "replay_mode": True,
        "replay_window": {
            "date": date_et,
            "as_of_et": as_of_hhmm,
        },
        "spy_bars": spy_bars_out,
        "ribbon": ribbon,
        "vix": vix,
        "spy_context": spy_context,
        "sectors": sectors,
        "rotation_signal": rotation,
        "tv_data_available": ribbon.get("stack") != "UNKNOWN",
        "alpaca_data_available": all(v is not None for v in sectors.values()),
    }

    if output_path is None:
        output_path = SWARM_DIR / "state" / "raw_data.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, indent=2)
    _log(f"wrote {output_path}")
    return raw_data


def main() -> int:
    parser = argparse.ArgumentParser(description="Build synthetic raw_data.json for a historical date")
    parser.add_argument("--date", required=True, help="Target date YYYY-MM-DD")
    parser.add_argument("--as-of", default="06:00", help="As-of time HH:MM ET (default 06:00)")
    parser.add_argument("--spy-csv", type=Path, default=SPY_CSV_DEFAULT)
    parser.add_argument("--vix-csv", type=Path, default=VIX_CSV_DEFAULT)
    parser.add_argument("--output", type=Path, default=None,
                        help="Output JSON path (default: automation/swarm/state/raw_data.json)")
    args = parser.parse_args()

    try:
        result = build_raw_data(args.date, args.as_of, args.spy_csv, args.vix_csv, args.output)
        bias_summary = (
            f"price={result['spy_context'].get('current_price')} "
            f"ribbon={result['ribbon'].get('stack')} ({result['ribbon'].get('spread_cents')}c) "
            f"vix={result['vix'].get('current')} ({result['vix'].get('direction')}) "
            f"gap={result['spy_context'].get('overnight_gap_dollars')} "
            f"rotation={result['rotation_signal']}"
        )
        _log(f"SUMMARY: {bias_summary}")
        return 0
    except Exception as exc:
        _log(f"ERROR: {exc}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
