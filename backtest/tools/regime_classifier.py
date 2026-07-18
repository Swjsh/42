"""regime_classifier.py -- VIX band + trend-character regime classifier.

Built for `analysis/recommendations/prereg-regime-conditioned-validation-2026-07-17.json`
(the 2025-vs-2026 reference-class adjudication). Reuses the SAME primitives the LIVE
engine reads for context, cited precisely so nothing here is invented:

- **VIX band** -- `automation/state/params.json#vix_iv_regime_bands`, the live
  premarket context-tagging ladder (params.json `_vix_section`: "iv_regime bands
  (LOW/MID/HIGH) used by premarket for context tagging"): LOW <15, MID [15,22],
  HIGH >22. This is NOT the same as `vix_entry_thresholds` (disclosed VESTIGIAL in
  params.json, not read by the live order-placing path) -- we use the iv_regime
  ladder because it is the one live consumer actually reads.
- **Trend character** -- `crypto/lib/market_structure.py#analyze_structure` /
  `classify_trend` (Trend = uptrend/downtrend/range/unknown), called with
  `window=DEFAULT_WINDOW` (=2) and `min_bars=10` -- BYTE-IDENTICAL to
  `setup/scripts/context_bundle_producer.py#_tf_state()`'s live daily-timeframe
  call (the function that feeds the live context bundle's
  `trend_alignment.per_tf.daily` field, itself consumed by `compute_trend_alignment`,
  Phase-1-reused per that module's own docstring: "AS-OF-BOUNDED and pure ...
  zero look-ahead (C6) and zero re-derivation of the math"). Same
  `days_back=190` / `limit=200` daily-bar lookback window
  (`context_bundle_producer.py` line ~635: `_fetch_bars("1Day", days_back=190, limit=200)`).

CAUSAL BY CONSTRUCTION (C6, zero lookahead): every date's regime label is computed
from data STRICTLY BEFORE that date -- the prior TRADING day's VIX close for the VIX
band, and daily SPY bars up to (and excluding) the date itself for the trend read.
Nothing at or after the target date's own session is ever touched.

Data sources (both already-cached, no new fetch):
- Daily SPY OHLC: `analysis/backtests/cache/trend-alignment-spy-daily-2024-07-01_2026-07-14.json`
  (the SAME cache `context_bundle_producer.py`'s live daily fetch populates/reads).
- VIX 5m -> daily close: `backtest/data/vix_5m_2025-01-01_2026-07-08.csv`, day's close =
  the LAST bar of that calendar date in the file (file is chronologically ordered).

Run standalone for a smoke check: backtest/.venv/Scripts/python.exe backtest/tools/regime_classifier.py
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]          # backtest/
ROOT = REPO.parent                                   # repo root
for p in (str(ROOT), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.market_structure import analyze_structure, DEFAULT_WINDOW  # noqa: E402

DAILY_SPY_CACHE = ROOT / "analysis" / "backtests" / "cache" / "trend-alignment-spy-daily-2024-07-01_2026-07-14.json"
VIX_5M_CSV = REPO / "data" / "vix_5m_2025-01-01_2026-07-08.csv"

# ---- VIX band ladder, mirrored verbatim from automation/state/params.json#vix_iv_regime_bands ----
VIX_LOW_MAX_EXCLUSIVE = 15.0
VIX_MID_MAX_INCLUSIVE = 22.0
# HIGH = anything > 22.0 (min_exclusive)

# ---- trend character params, mirrored verbatim from context_bundle_producer.py ----
MIN_BARS = 10          # context_bundle_producer.py MIN_BARS
DAILY_DAYS_BACK = 190   # context_bundle_producer.py _fetch_bars("1Day", days_back=190, limit=200)
DAILY_LIMIT = 200


def vix_band(vix_close: float) -> str:
    if vix_close < VIX_LOW_MAX_EXCLUSIVE:
        return "LOW"
    if vix_close <= VIX_MID_MAX_INCLUSIVE:
        return "MID"
    return "HIGH"


def load_daily_spy_bars() -> list[Bar]:
    data = json.loads(DAILY_SPY_CACHE.read_text(encoding="utf-8"))
    bars: list[Bar] = []
    for row in data["bars"]:
        ts_raw = row["timestamp"].replace("Z", "+00:00")
        ts = dt.datetime.fromisoformat(ts_raw)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=dt.timezone.utc)
        vol = row.get("volume", 0) or 0
        bars.append(Bar(open_time=ts, open=float(row["open"]), high=float(row["high"]),
                         low=float(row["low"]), close=float(row["close"]), volume=float(vol),
                         granularity_seconds=86400, source="spy_daily_cache"))
    bars.sort(key=lambda b: b.open_time)
    return bars


def load_vix_daily_closes() -> dict[dt.date, float]:
    """Last 5m bar's close per calendar (ET) date -> end-of-coverage VIX read for that date."""
    closes: dict[dt.date, float] = {}
    with open(VIX_5M_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = row["timestamp_et"]
            d = dt.date.fromisoformat(ts[:10])
            closes[d] = float(row["close"])  # file is chronological -> last write per date wins
    return closes


def classify_trend_asof(daily_bars: list[Bar], target_date: dt.date) -> tuple[str, dict]:
    """Trend as-of target_date using ONLY bars strictly before it (causal)."""
    cutoff = dt.datetime.combine(target_date, dt.time(0, 0), tzinfo=dt.timezone.utc)
    lookback_start = cutoff - dt.timedelta(days=DAILY_DAYS_BACK)
    window_bars = [b for b in daily_bars if lookback_start <= b.open_time < cutoff]
    window_bars = window_bars[-DAILY_LIMIT:]
    if len(window_bars) < MIN_BARS:
        return "unknown", {"available": False, "n_bars": len(window_bars), "reason": "insufficient_bars"}
    try:
        read = analyze_structure(window_bars, window=DEFAULT_WINDOW)
    except Exception as e:  # noqa: BLE001 -- degrade, never crash the classifier
        return "unknown", {"available": False, "n_bars": len(window_bars),
                            "reason": f"analyze_structure_error: {type(e).__name__}"}
    return read.trend, {"available": True, "n_bars": len(window_bars),
                         "trend_basis": read.trend_basis, "confidence": round(float(read.confidence), 4)}


def classify_vix_band_asof(vix_daily: dict[dt.date, float], target_date: dt.date) -> tuple[str | None, float | None]:
    prior_dates = [d for d in vix_daily if d < target_date]
    if not prior_dates:
        return None, None
    d = max(prior_dates)
    v = vix_daily[d]
    return vix_band(v), v


def regime_label(target_date: dt.date, daily_bars: list[Bar], vix_daily: dict[dt.date, float]) -> dict:
    trend, trend_meta = classify_trend_asof(daily_bars, target_date)
    band, vix_val = classify_vix_band_asof(vix_daily, target_date)
    band_label = band or "UNKNOWN"
    label = f"{band_label}_{trend}"
    return {
        "date": target_date.isoformat(),
        "regime": label,
        "vix_band": band_label,
        "vix_close_prior_trading_day": vix_val,
        "trend": trend,
        "trend_meta": trend_meta,
    }


class RegimeCalendar:
    """Cached classifier: build once, label many dates cheaply."""

    def __init__(self) -> None:
        self.daily_bars = load_daily_spy_bars()
        self.vix_daily = load_vix_daily_closes()
        self._cache: dict[str, dict] = {}

    def label(self, target_date: dt.date | str) -> dict:
        if isinstance(target_date, str):
            target_date = dt.date.fromisoformat(target_date)
        key = target_date.isoformat()
        if key not in self._cache:
            self._cache[key] = regime_label(target_date, self.daily_bars, self.vix_daily)
        return self._cache[key]

    def label_many(self, dates) -> dict[str, dict]:
        out = {}
        for d in dates:
            key = d.isoformat() if hasattr(d, "isoformat") else d
            out[key] = self.label(key)
        return out

    def all_trading_days(self, start: dt.date, end: dt.date) -> list[dt.date]:
        """Every VIX-data-covered date in [start, end] -- our trading-day universe."""
        return sorted(d for d in self.vix_daily if start <= d <= end)


def tautology_stats(calendar: RegimeCalendar, start: dt.date, end: dt.date) -> dict:
    """Regime-vs-calendar-year contingency + Cramer's V over the FULL trading-day universe
    (not just a candidate's cohort) -- the global check that the regime classifier is not
    simply reproducing the calendar."""
    days = calendar.all_trading_days(start, end)
    labels = [calendar.label(d) for d in days]
    years = [d.year for d in days]
    regimes = sorted({l["regime"] for l in labels})
    year_vals = sorted(set(years))
    # contingency table: regime x year
    table = {r: {y: 0 for y in year_vals} for r in regimes}
    for lab, y in zip(labels, years):
        table[lab["regime"]][y] += 1
    n = len(days)
    # chi-square + Cramer's V (manual, no scipy dependency assumed)
    row_totals = {r: sum(table[r].values()) for r in regimes}
    col_totals = {y: sum(table[r][y] for r in regimes) for y in year_vals}
    chi2 = 0.0
    for r in regimes:
        for y in year_vals:
            expected = row_totals[r] * col_totals[y] / n if n else 0
            observed = table[r][y]
            if expected > 0:
                chi2 += (observed - expected) ** 2 / expected
    k = min(len(regimes), len(year_vals))
    cramers_v = (chi2 / (n * (k - 1))) ** 0.5 if n and k > 1 else None
    pct_2026_by_regime = {
        r: round(100.0 * table[r].get(2026, 0) / row_totals[r], 1) if row_totals[r] else None
        for r in regimes
    }
    return {
        "n_days": n,
        "regimes_seen": regimes,
        "contingency_table": table,
        "chi2": round(chi2, 3),
        "cramers_v": round(cramers_v, 4) if cramers_v is not None else None,
        "pct_2026_by_regime": pct_2026_by_regime,
        "note": "Cramer's V close to 0 = regime label is roughly independent of calendar year "
                "(good -- not a calendar proxy). Close to 1 = regime label IS essentially a "
                "calendar-year proxy (tautology risk) -- any candidate that PASSES only because "
                "its target regime happens to concentrate in one year should be treated with the "
                "same suspicion as passing on calendar-year alone.",
    }


if __name__ == "__main__":
    cal = RegimeCalendar()
    smoke_dates = ["2025-01-08", "2025-05-04", "2026-04-29", "2026-05-04", "2026-07-08"]
    for ds in smoke_dates:
        print(cal.label(ds))
    stats = tautology_stats(cal, dt.date(2025, 1, 2), dt.date(2026, 7, 8))
    print(json.dumps({k: v for k, v in stats.items() if k != "contingency_table"}, indent=2))
