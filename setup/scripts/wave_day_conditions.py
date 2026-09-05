"""wave_day_conditions.py -- GOAL-WAVE-DAY-CONDITIONS-2026-09-05 W1/W3.

$0 instrument, cached-data-only, fail-open (C7): computes one row of
pre-09:41-ET market conditions for a trading day and joins it to the
right-tail ledger's wave/no-wave label for that day (backtest/lib/
right_tail_waves.py's >=1 genuine wave, i.e. `analysis/right-tail/
CAPTURE-<date>.json`'s `n_waves_meeting_threshold >= 1`).

Conditions computed per DONE-WHEN (W1):
  - overnight gap % (today's RTH open vs prior trading day's RTH close)
  - first-15-min range (09:30-09:45 ET high-low) / 20-trading-day ATR
    (ATR = mean daily RTH high-low range over the 20 trading days strictly
    before this date -- a simple range-ATR, not a Wilder true-range ATR;
    disclosed via `atr20_definition` on every row)
  - opening VIX vs prior VIX close, and VIX 5-trading-day slope
  - prior-day close relative to prior-day VWAP (RTH session VWAP)
  - day of week
  - distance of the 09:30 print to the nearest key-levels zone
    (key-levels-history/<date>/0835.json, the premarket snapshot)
  - whether the premarket bias (journal/<date>.md "Bias:" line) called the
    day's actual direction

Two usage modes, same code path (no mode flag -- availability decides,
per C7 fail-open):
  - HISTORICAL date (spy_sip_cache has a full 1-min day, right-tail ledger
    has a CAPTURE-<date>.json): every field computes.
  - TODAY at premarket (before the day's bars exist and before the 16:20 ET
    right-tail capture has run): day-dependent fields (first_15min_range,
    wave label, bias_called_direction) degrade to null with a `reason`
    string -- never a crash, never a fabricated number. The later 16:20 ET
    Gamma_RightTailCapture fire's ledger join provides the wave label for
    W2's table; this script does not re-join after the fact.

CLI:
  python setup/scripts/wave_day_conditions.py --date 2026-08-04   (one row, print + append)
  python setup/scripts/wave_day_conditions.py                     (today, ET, premarket mode)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (REPO, BACKTEST, BACKTEST / "lib", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from et_clock import et_today_str  # noqa: E402

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None

OUT_PATH = REPO / "analysis" / "right-tail" / "wave-day-conditions.jsonl"
RIGHT_TAIL_DIR = REPO / "analysis" / "right-tail"
SPY_SIP_CACHE = BACKTEST / "data" / "spy_sip_cache"
SPY_5M_FALLBACK = BACKTEST / "data" / "spy_5m_2026-05-19_2026-09-04.csv"
VIX_5M_FILE = BACKTEST / "data" / "vix_5m_2026-05-19_2026-09-04.csv"
KEY_LEVELS_HISTORY = REPO / "automation" / "state" / "key-levels-history"
KEY_LEVELS_LIVE = REPO / "automation" / "state" / "key-levels.json"
JOURNAL_DIR = REPO / "journal"

ATR20_DEFINITION = (
    "mean of daily RTH (09:30-16:00 ET) high-low range over the 20 trading "
    "days strictly before this date (simple range-ATR, not Wilder true-range)"
)

_BIAS_PATTERNS = [
    re.compile(r"^\*\*Bias:\*\*\s*(.+)$"),
    re.compile(r"^-\s*\*\*Bias:\*\*\s*(.+)$"),
    re.compile(r"^-\s*Bias:\s*(.+)$"),
]


# ── SPY / VIX daily-bar loaders (cached, $0, read-only) ─────────────────────

_SPY_DAY_CACHE: dict[str, list[dict[str, Any]] | None] = {}
_VIX_DF_CACHE: "pd.DataFrame | None" = None
_SPY5M_DF_CACHE: "pd.DataFrame | None" = None


def _load_spy_day_bars(date: str) -> list[dict[str, Any]] | None:
    """1-min RTH+extended bars for one trading day from the per-day SIP cache.
    None if the cache file is missing (fail-open, caller degrades that day)."""
    if date in _SPY_DAY_CACHE:
        return _SPY_DAY_CACHE[date]
    path = SPY_SIP_CACHE / f"spy_1m_{date}.json"
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        bars = d.get("bars", [])
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        bars = None
    _SPY_DAY_CACHE[date] = bars
    return bars


def _load_spy5m_fallback_df():
    global _SPY5M_DF_CACHE
    if _SPY5M_DF_CACHE is not None:
        return _SPY5M_DF_CACHE
    if pd is None or not SPY_5M_FALLBACK.exists():
        return None
    df = pd.read_csv(SPY_5M_FALLBACK)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"]).dt.tz_localize(None)
    _SPY5M_DF_CACHE = df
    return df


def _spy_rth_ohlc(date: str) -> dict[str, Any] | None:
    """{'open','high','low','close','bars_1m'} for one trading day's RTH
    (09:30-16:00 ET) session. Tries the per-day 1-min SIP cache first; falls
    back to the aggregate 5-min CSV (covers 2026-08-31, which has no per-day
    cache file). None if neither source has the date."""
    bars = _load_spy_day_bars(date)
    if bars:
        rth = [b for b in bars if "09:30:00" <= b["t"][11:19] <= "16:00:00"]
        if rth:
            return {
                "open": rth[0]["o"], "close": rth[-1]["c"],
                "high": max(b["h"] for b in rth), "low": min(b["l"] for b in rth),
                "source": "spy_1m_sip_cache", "bars_1m": rth,
            }
    df = _load_spy5m_fallback_df()
    if df is not None:
        day_rows = df[df["timestamp_et"].dt.strftime("%Y-%m-%d") == date]
        rth = day_rows[(day_rows["timestamp_et"].dt.time >= dt.time(9, 30))
                        & (day_rows["timestamp_et"].dt.time <= dt.time(16, 0))]
        if not rth.empty:
            return {
                "open": float(rth.iloc[0]["open"]), "close": float(rth.iloc[-1]["close"]),
                "high": float(rth["high"].max()), "low": float(rth["low"].min()),
                "source": "spy_5m_aggregate_fallback", "bars_1m": None,
            }
    return None


def _prior_trading_day(date: str) -> str | None:
    """Previous date with SPY RTH coverage (per-day cache OR the aggregate
    5-min fallback), strictly before `date`. None if none found within 15
    calendar days (fail-open guard against an infinite walk)."""
    d = dt.date.fromisoformat(date)
    for _ in range(15):
        d = d - dt.timedelta(days=1)
        ds = d.isoformat()
        if _spy_rth_ohlc(ds) is not None:
            return ds
    return None


def _prior_n_trading_days(date: str, n: int) -> list[str]:
    """Up to n prior trading days (oldest first) strictly before `date`."""
    out: list[str] = []
    cur = date
    for _ in range(n):
        prev = _prior_trading_day(cur)
        if prev is None:
            break
        out.append(prev)
        cur = prev
    return list(reversed(out))


def _load_vix_df():
    global _VIX_DF_CACHE
    if _VIX_DF_CACHE is not None:
        return _VIX_DF_CACHE
    if pd is None or not VIX_5M_FILE.exists():
        return None
    cols = ["timestamp_et", "open", "high", "low", "close", "volume"]
    df = pd.read_csv(VIX_5M_FILE, header=None, names=cols, skiprows=1)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=False).dt.tz_localize(None)
    _VIX_DF_CACHE = df
    return df


def _vix_close_near(date: str, at_or_before: dt.time) -> float | None:
    df = _load_vix_df()
    if df is None:
        return None
    day = df[df["timestamp_et"].dt.strftime("%Y-%m-%d") == date]
    day = day[day["timestamp_et"].dt.time <= at_or_before]
    if day.empty:
        return None
    return float(day.iloc[-1]["close"])


def _vix_open_near(date: str, at_or_after: dt.time = dt.time(9, 30)) -> float | None:
    df = _load_vix_df()
    if df is None:
        return None
    day = df[df["timestamp_et"].dt.strftime("%Y-%m-%d") == date]
    day = day[day["timestamp_et"].dt.time >= at_or_after]
    if day.empty:
        return None
    return float(day.iloc[0]["open"])


# ── individual condition calculators (each fail-open: None + reason) ───────

def overnight_gap_pct(date: str) -> dict[str, Any]:
    today = _spy_rth_ohlc(date)
    if today is None:
        return {"value": None, "reason": f"no SPY RTH bars cached for {date}"}
    prior_day = _prior_trading_day(date)
    if prior_day is None:
        return {"value": None, "reason": "no prior trading day found in cache"}
    prior = _spy_rth_ohlc(prior_day)
    if prior is None or not prior.get("close"):
        return {"value": None, "reason": f"no SPY RTH close cached for prior day {prior_day}"}
    gap = round((today["open"] - prior["close"]) / prior["close"] * 100.0, 4)
    return {"value": gap, "prior_day": prior_day, "prior_close": prior["close"], "today_open": today["open"]}


def first15_range_over_atr20(date: str) -> dict[str, Any]:
    today = _spy_rth_ohlc(date)
    if today is None:
        return {"first_15min_range": None, "atr20": None, "ratio": None,
                "reason": f"no SPY RTH bars cached for {date}"}
    bars_1m = today.get("bars_1m")
    if not bars_1m:
        return {"first_15min_range": None, "atr20": None, "ratio": None,
                "reason": "no 1-min bars for first-15-min window (aggregate-fallback day has no 1m granularity, or day hasn't opened yet)"}
    first15 = [b for b in bars_1m if "09:30:00" <= b["t"][11:19] < "09:45:00"]
    if not first15:
        return {"first_15min_range": None, "atr20": None, "ratio": None,
                "reason": "no bars in 09:30-09:45 window (day has not opened yet, premarket run)"}
    f15_range = round(max(b["h"] for b in first15) - min(b["l"] for b in first15), 4)

    prior_20 = _prior_n_trading_days(date, 20)
    ranges = []
    for d2 in prior_20:
        o = _spy_rth_ohlc(d2)
        if o is not None:
            ranges.append(o["high"] - o["low"])
    if not ranges:
        return {"first_15min_range": f15_range, "atr20": None, "ratio": None,
                "reason": "no prior-day RTH bars available for ATR20", "n_days_in_atr20": 0}
    atr20 = round(sum(ranges) / len(ranges), 4)
    ratio = round(f15_range / atr20, 4) if atr20 else None
    return {"first_15min_range": f15_range, "atr20": atr20, "ratio": ratio,
            "n_days_in_atr20": len(ranges)}


def vix_conditions(date: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    opening_vix = _vix_open_near(date)
    prior_day = _prior_trading_day(date)
    prior_close_vix = _vix_close_near(prior_day, dt.time(16, 0)) if prior_day else None
    if opening_vix is None or prior_close_vix is None:
        out["opening_vs_prior_close"] = {
            "value": None,
            "reason": f"missing VIX bar(s) (opening={opening_vix}, prior_close={prior_close_vix})",
        }
    else:
        out["opening_vs_prior_close"] = {
            "value": round(opening_vix - prior_close_vix, 4),
            "opening_vix": round(opening_vix, 4), "prior_close_vix": round(prior_close_vix, 4),
        }

    prior_5 = _prior_n_trading_days(date, 5)
    today_close_vix = _vix_close_near(date, dt.time(16, 0))
    if today_close_vix is None:
        today_close_vix = opening_vix  # premarket day: no close yet, use latest reading
    five_ago_close = _vix_close_near(prior_5[0], dt.time(16, 0)) if prior_5 else None
    if today_close_vix is None or five_ago_close is None or len(prior_5) < 5:
        reasons = []
        if today_close_vix is None:
            reasons.append("no VIX reading available for today (no bar yet, premarket before first tick)")
        if len(prior_5) < 5:
            reasons.append(f"insufficient VIX history (n_prior_days={len(prior_5)})")
        elif five_ago_close is None:
            reasons.append(f"no VIX close cached for 5-sessions-ago day {prior_5[0]}")
        out["vix_5day_slope"] = {"value": None, "reason": "; ".join(reasons) or "unknown"}
    else:
        out["vix_5day_slope"] = {
            "value": round((today_close_vix - five_ago_close) / 5.0, 4),
            "today_reading": round(today_close_vix, 4), "five_sessions_ago_close": round(five_ago_close, 4),
        }
    return out


def prior_day_close_vs_vwap(date: str) -> dict[str, Any]:
    prior_day = _prior_trading_day(date)
    if prior_day is None:
        return {"value": None, "reason": "no prior trading day found"}
    bars = _load_spy_day_bars(prior_day)
    if not bars:
        return {"value": None, "reason": f"no 1-min bars cached for prior day {prior_day}", "prior_day": prior_day}
    rth = [b for b in bars if "09:30:00" <= b["t"][11:19] <= "16:00:00"]
    if not rth:
        return {"value": None, "reason": "no RTH bars for prior day", "prior_day": prior_day}
    num = sum(((b["h"] + b["l"] + b["c"]) / 3.0) * b["v"] for b in rth)
    den = sum(b["v"] for b in rth)
    if den == 0:
        return {"value": None, "reason": "zero volume in prior-day RTH bars", "prior_day": prior_day}
    vwap = num / den
    close = rth[-1]["c"]
    pct = round((close - vwap) / vwap * 100.0, 4)
    return {"value": pct, "prior_day": prior_day, "prior_close": close, "prior_vwap": round(vwap, 4)}


def day_of_week(date: str) -> str:
    return dt.date.fromisoformat(date).strftime("%A")


def distance_to_nearest_zone(date: str) -> dict[str, Any]:
    today = _spy_rth_ohlc(date)
    print_price = today["open"] if today else None
    levels_path = KEY_LEVELS_HISTORY / date / "0835.json"
    source = "key-levels-history/<date>/0835.json"
    if not levels_path.exists():
        if date == et_today_str() and KEY_LEVELS_LIVE.exists():
            levels_path = KEY_LEVELS_LIVE
            source = "key-levels.json (live, no dated snapshot yet)"
        else:
            return {"value": None, "reason": f"no key-levels snapshot for {date}"}
    try:
        d = json.loads(levels_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"value": None, "reason": f"unreadable/corrupt {levels_path}"}
    levels = d.get("levels", [])
    if not levels:
        return {"value": None, "reason": "0 levels in snapshot"}
    if print_price is None:
        # premarket mode: no 09:30 print yet -- use the snapshot's own spot_at_compute
        print_price = d.get("spot_at_compute")
    if print_price is None:
        return {"value": None, "reason": "no reference price (09:30 print or spot_at_compute) available"}
    nearest = min(levels, key=lambda l: abs(l.get("price", 1e9) - print_price))
    dist = round(abs(nearest["price"] - print_price), 4)
    return {
        "value": dist, "reference_price": print_price, "reference_price_kind": "09:30_open" if today else "spot_at_compute",
        "nearest_level_price": nearest.get("price"), "nearest_level_type": nearest.get("type"),
        "nearest_level_label": nearest.get("label"), "source": source,
    }


def _bias_raw_for_date(date: str) -> str | None:
    path = JOURNAL_DIR / f"{date}.md"
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        s = line.strip()
        for pat in _BIAS_PATTERNS:
            m = pat.match(s)
            if m:
                return m.group(1).strip()
    return None


def _classify_bias_word(raw: str | None) -> str | None:
    if not raw:
        return None
    low = raw.lower()
    if low.startswith("bullish"):
        return "bullish"
    if low.startswith("bearish"):
        return "bearish"
    if low.startswith("no-trade") or low.startswith("no trade"):
        return "no_trade"
    return None


def bias_direction(date: str) -> dict[str, Any]:
    raw = _bias_raw_for_date(date)
    if raw is None:
        return {"raw": None, "classified": None, "reason": f"no Bias: line found in journal/{date}.md"}
    return {"raw": raw, "classified": _classify_bias_word(raw)}


def wave_label(date: str) -> dict[str, Any]:
    """>=1 genuine right-tail wave that day, from the CAPTURE-<date>.json this
    goal's DONE-WHEN names (right_tail_waves.py's own >=1.3x threshold).
    Prefers the already-computed CAPTURE file (checked into analysis/right-tail/)
    over recomputing find_waves() live -- the daily 16:20 ET
    Gamma_RightTailCapture fire is the source of truth for a closed day."""
    capture_path = RIGHT_TAIL_DIR / f"CAPTURE-{date}.json"
    if not capture_path.exists():
        return {"wave": None, "n_waves_all": None, "n_waves_meeting_threshold": None,
                "sides": None, "peak_multiples": None,
                "reason": f"no {capture_path.name} (Gamma_RightTailCapture has not fired for this date yet)"}
    try:
        d = json.loads(capture_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"wave": None, "n_waves_all": None, "n_waves_meeting_threshold": None,
                "sides": None, "peak_multiples": None, "reason": f"unreadable/corrupt {capture_path}"}
    waves = d.get("waves", [])
    meeting = [w for w in waves if w.get("meets_threshold")]
    return {
        "wave": len(meeting) >= 1,
        "n_waves_all": d.get("n_waves_all"),
        "n_waves_meeting_threshold": d.get("n_waves_meeting_threshold"),
        "sides": [w.get("side") for w in meeting],
        "peak_multiples": [w.get("peak_multiple") for w in meeting],
    }


def bias_called_direction(date: str, wave_info: dict[str, Any], today_ohlc: dict[str, Any] | None) -> dict[str, Any]:
    bias = bias_direction(date)
    classified = bias.get("classified")
    if classified is None:
        return {"value": None, "reason": bias.get("reason") or "premarket bias not bullish/bearish (no_trade or unparsed)"}
    if classified == "no_trade":
        return {"value": None, "reason": "premarket bias was no-trade -- no direction was called"}
    if wave_info.get("wave") is True:
        sides = wave_info.get("sides") or []
        actual = "bullish" if sides and sides[0] == "C" else ("bearish" if sides and sides[0] == "P" else None)
        method = "wave_side (first genuine wave's side)"
    elif wave_info.get("wave") is False:
        if today_ohlc is None:
            return {"value": None, "reason": "no-wave day but no SPY RTH bars to read net direction"}
        actual = "bullish" if today_ohlc["close"] >= today_ohlc["open"] else "bearish"
        method = "net RTH close-vs-open direction (no-wave day, weak proxy)"
    else:
        return {"value": None, "reason": "wave label not yet known (premarket, right-tail capture has not run)"}
    if actual is None:
        return {"value": None, "reason": "could not determine actual direction"}
    return {"value": classified == actual, "bias": classified, "actual": actual, "method": method}


# ── row assembly ─────────────────────────────────────────────────────────

def build_row(date: str) -> dict[str, Any]:
    """Assemble one full conditions row for `date`. Never raises -- every
    field independently degrades to null+reason on missing/unavailable input
    (C7 fail-open); a field's absence never blocks any other field."""
    today_ohlc = _spy_rth_ohlc(date)
    wave_info = wave_label(date)
    row: dict[str, Any] = {
        "date": date,
        "day_of_week": day_of_week(date),
        "wave": wave_info,
        "overnight_gap_pct": overnight_gap_pct(date),
        "first15_range_over_atr20": first15_range_over_atr20(date),
        "vix": vix_conditions(date),
        "prior_day_close_vs_vwap_pct": prior_day_close_vs_vwap(date),
        "distance_to_nearest_zone": distance_to_nearest_zone(date),
        "premarket_bias": bias_direction(date),
        "bias_called_direction": bias_called_direction(date, wave_info, today_ohlc),
        "atr20_definition": ATR20_DEFINITION,
        "generated_at_et": None,  # filled by main() from et_clock, never guessed here
    }
    return row


def append_row(date: str, path: Path = OUT_PATH) -> dict[str, Any]:
    from et_clock import et_now
    row = build_row(date)
    row["generated_at_et"] = et_now().strftime("%Y-%m-%d %H:%M:%S ET")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", default=None, help="ET date YYYY-MM-DD; defaults to today (et_clock).")
    ap.add_argument("--no-append", action="store_true", help="print only, do not write to the jsonl ledger.")
    ap.add_argument("--out-path", default=None, help="override the jsonl output path.")
    args = ap.parse_args()
    date = args.date or et_today_str()
    out_path = Path(args.out_path) if args.out_path else OUT_PATH

    if args.no_append:
        row = build_row(date)
        from et_clock import et_now
        row["generated_at_et"] = et_now().strftime("%Y-%m-%d %H:%M:%S ET")
    else:
        row = append_row(date, path=out_path)

    print(json.dumps(row, indent=2, default=str))
    wave = row["wave"].get("wave")
    print(f"[wave-day-conditions] {date}: wave={wave} "
          f"gap%={row['overnight_gap_pct'].get('value')} "
          f"vix_open_vs_prior={row['vix']['opening_vs_prior_close'].get('value')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
