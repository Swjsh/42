"""f10_volume_reproduce.py -- RESEARCH ONLY, offline reproduction for queue item
SIP-VOLMULT-MISMATCH (automation/overnight/queue.md).

Question: blocker 10 (`buyer_pressure_bar_v11`, backtest/lib/filters.py:1500) is a
green-bar + `volume >= f10_vol_mult * vol_baseline_20` check, f10_vol_mult=0.7,
ratified on SIP volume but running live on IEX (~3.6% of SIP share). On 2026-09-02
blocker 10 was reported as the binding constraint on 144/178 ticks while a crude
approximate-baseline reconstruction did NOT reproduce that block rate. This script
reproduces blocker 10 using the REAL filter functions (imported, never
reimplemented) against:
  (1) real SIP 5-min bars (backtest/data/spy_sip_cache/spy_5m_{date}.json)
  (2) real IEX 5-min bars (fetched live via Alpaca REST, feed=iex, and cached
      locally as scratch JSON by the caller -- this script reads whatever cache
      files are passed via --iex-glob or falls back to fetching live)
under the ENGINE'S OWN vol_baseline_20 definition: a 20-bar SMA over a
continuous, RTH-only, multi-day bar series with NO per-day reset
(`backtest.lib.filters.vol_baseline_20bar`, mirrored at
setup/scripts/heartbeat_core.py:928 `vol20 = win["volume"].iloc[max(0,
trig_idx-20):trig_idx].mean()`), so the baseline for the first ~20 RTH bars of a
trading day (09:35 through ~11:15 ET) draws volume from the TAIL of the prior
trading day's RTH session.

Deterministic, no LLM. Never edits any live-path file. Writes nothing by default
(pass --out to dump a JSON report).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
SPY_SIP_DIR = BACKTEST / "data" / "spy_sip_cache"

for _p in (REPO, BACKTEST, BACKTEST / "lib", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from lib.filters import (  # noqa: E402
    buyer_pressure_bar_v11, vol_baseline_20bar, VOL_BASELINE_BARS,
)

RTH_START = dt.time(9, 30)
RTH_END = dt.time(16, 0)
F10_VOL_MULT = 0.7


def _load_sip_day(date_str: str) -> pd.DataFrame | None:
    """RTH-only 5-min SIP bars for one date, naive ET timestamps (matches
    historical_replay.py's own '_load_spy_1min_day' convention for this cache)."""
    p = SPY_SIP_DIR / f"spy_5m_{date_str}.json"
    if not p.exists():
        return None
    bars = json.loads(p.read_text(encoding="utf-8")).get("bars", [])
    if not bars:
        return None
    df = pd.DataFrame(bars).rename(
        columns={"t": "timestamp_et", "o": "open", "h": "high", "l": "low",
                 "c": "close", "v": "volume"}
    )
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    rth = df[(df["timestamp_et"].dt.time >= RTH_START) & (df["timestamp_et"].dt.time < RTH_END)]
    return rth[["timestamp_et", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def _load_iex_cache(date_str: str, cache_dir: Path) -> pd.DataFrame | None:
    """RTH-only 5-min IEX bars for one date from a local scratch JSON cache written
    by fetching Alpaca REST /v2/stocks/SPY/bars?feed=iex (UTC 't' -> ET wall clock)."""
    p = cache_dir / f"spy_5m_iex_{date_str}.json"
    if not p.exists():
        return None
    bars = json.loads(p.read_text(encoding="utf-8")).get("bars", [])
    if not bars:
        return None
    df = pd.DataFrame(bars).rename(
        columns={"t": "timestamp_et", "o": "open", "h": "high", "l": "low",
                 "c": "close", "v": "volume"}
    )
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert(
        "America/New_York"
    ).dt.tz_localize(None)
    rth = df[(df["timestamp_et"].dt.time >= RTH_START) & (df["timestamp_et"].dt.time < RTH_END)]
    return rth[["timestamp_et", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def _fetch_iex_live(date_str: str) -> pd.DataFrame | None:
    """Fallback: fetch feed=iex bars for one date directly via Alpaca REST using
    the project's own credential helper (never prints/copies the key)."""
    import requests
    from alpaca_keys import keys_for

    key, secret = keys_for("safe")
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    url = "https://data.alpaca.markets/v2/stocks/SPY/bars"
    params = {
        "timeframe": "5Min",
        "start": f"{date_str}T04:00:00-04:00",
        "end": f"{date_str}T20:00:00-04:00",
        "limit": 10000,
        "feed": "iex",
    }
    r = requests.get(url, headers=headers, params=params, timeout=30)
    if r.status_code != 200:
        print(f"IEX fetch FAILED for {date_str}: HTTP {r.status_code} {r.text[:300]}",
              file=sys.stderr)
        return None
    bars = r.json().get("bars", [])
    if not bars:
        return None
    df = pd.DataFrame(bars).rename(
        columns={"t": "timestamp_et", "o": "open", "h": "high", "l": "low",
                 "c": "close", "v": "volume"}
    )
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert(
        "America/New_York"
    ).dt.tz_localize(None)
    rth = df[(df["timestamp_et"].dt.time >= RTH_START) & (df["timestamp_et"].dt.time < RTH_END)]
    return rth[["timestamp_et", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def _build_continuous(day_frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Concatenate RTH-only day frames into ONE continuous series, index reset
    once -- mirrors orchestrator.py:803-824's `spy_df = spy_df_full.loc[rth_mask]
    .reset_index(drop=True)` and heartbeat_core.py's rolling `win` window: NO
    per-day reset, so a 20-bar lookback near the open of one day reaches back
    into the prior day's RTH tail."""
    df = pd.concat(day_frames, ignore_index=True)
    df = df.sort_values("timestamp_et").reset_index(drop=True)
    return df


def _score_day(df: pd.DataFrame, target_date: str, vol_mult: float) -> dict:
    """Run buyer_pressure_bar_v11 via vol_baseline_20bar (the REAL engine functions)
    over every RTH bar of `target_date` within `df` (a continuous multi-day
    series), 09:35 through <16:00 ET (filter 1's own time gate)."""
    rows = []
    for idx in range(len(df)):
        ts = df["timestamp_et"].iloc[idx]
        if ts.strftime("%Y-%m-%d") != target_date:
            continue
        if ts.time() < dt.time(9, 35) or ts.time() >= RTH_END:
            continue
        bar = df.iloc[idx]
        baseline = vol_baseline_20bar(df, idx)
        ratio = (float(bar["volume"]) / baseline) if baseline > 0 else float("inf")
        blocked = not buyer_pressure_bar_v11(bar, baseline, vol_mult=vol_mult)
        rows.append({
            "ts_et": ts.isoformat(),
            "open": float(bar["open"]), "close": float(bar["close"]),
            "volume": float(bar["volume"]),
            "vol_baseline_20": baseline,
            "ratio": ratio,
            "green_bar": bool(bar["close"] > bar["open"]),
            "blocked_f10": blocked,
        })
    n = len(rows)
    n_blocked = sum(1 for r in rows if r["blocked_f10"])
    ratios = sorted(r["ratio"] for r in rows if r["ratio"] != float("inf"))

    def _pctile(p: float) -> float | None:
        if not ratios:
            return None
        i = min(len(ratios) - 1, max(0, int(round(p * (len(ratios) - 1)))))
        return ratios[i]

    return {
        "n_bars": n,
        "n_blocked_f10": n_blocked,
        "pct_blocked": (n_blocked / n) if n else None,
        "ratio_p10": _pctile(0.10),
        "ratio_p50": _pctile(0.50),
        "ratio_p90": _pctile(0.90),
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", default="2026-09-02", help="Target trading date (YYYY-MM-DD).")
    ap.add_argument("--warmup-dates", nargs="*", default=None,
                     help="Prior trading dates (chronological) to prepend for the "
                          "cross-session 20-bar baseline. Default: auto-discover "
                          "available spy_sip_cache days before --date (up to 3).")
    ap.add_argument("--vol-mult", type=float, default=F10_VOL_MULT,
                     help="f10_vol_mult to evaluate (default: ratified 0.7).")
    ap.add_argument("--iex-cache-dir", default=None,
                     help="Directory of spy_5m_iex_{date}.json scratch files "
                          "(fetched via Alpaca REST feed=iex). If a needed date "
                          "is missing, fetches live via alpaca_keys and writes it there.")
    ap.add_argument("--out", default=None, help="Optional path to write the full JSON report.")
    args = ap.parse_args()

    target = args.date
    if args.warmup_dates is not None:
        warmup = args.warmup_dates
    else:
        avail = sorted(p.stem.replace("spy_5m_", "") for p in SPY_SIP_DIR.glob("spy_5m_*.json"))
        avail = [d for d in avail if d < target]
        warmup = avail[-3:]
    all_dates = warmup + [target]
    print(f"[f10-reproduce] target={target} warmup={warmup}")

    # --- SIP branch (real cache, always available) ---
    sip_frames = []
    for d in all_dates:
        day = _load_sip_day(d)
        if day is None:
            print(f"[f10-reproduce] WARNING: no SIP cache for {d}, skipping", file=sys.stderr)
            continue
        sip_frames.append(day)
    if not sip_frames or all(f["timestamp_et"].iloc[0].strftime("%Y-%m-%d") != target
                              for f in sip_frames if len(f)):
        pass  # target may still be present; checked below
    sip_df = _build_continuous(sip_frames)
    sip_result = _score_day(sip_df, target, args.vol_mult)

    # --- IEX branch (fetch/cache) ---
    cache_dir = Path(args.iex_cache_dir) if args.iex_cache_dir else None
    iex_frames = []
    for d in all_dates:
        day = None
        if cache_dir is not None:
            day = _load_iex_cache(d, cache_dir)
        if day is None:
            print(f"[f10-reproduce] fetching IEX bars live for {d}...")
            day = _fetch_iex_live(d)
            if day is not None and cache_dir is not None:
                cache_dir.mkdir(parents=True, exist_ok=True)
                raw = {"bars": [
                    {"t": ts.isoformat() + "Z", "o": o, "h": h, "l": l, "c": c, "v": v}
                    for ts, o, h, l, c, v in zip(
                        day["timestamp_et"], day["open"], day["high"], day["low"],
                        day["close"], day["volume"])
                ]}
                (cache_dir / f"spy_5m_iex_{d}.json").write_text(json.dumps(raw))
        if day is None:
            print(f"[f10-reproduce] WARNING: no IEX data for {d}, skipping", file=sys.stderr)
            continue
        iex_frames.append(day)
    if not iex_frames:
        print("[f10-reproduce] IEX branch: no data available at all -- stopping that branch.")
        iex_result = None
    else:
        iex_df = _build_continuous(iex_frames)
        iex_result = _score_day(iex_df, target, args.vol_mult)

    # --- correlation between SIP and IEX ratio series (aligned by timestamp) ---
    correlation = None
    if iex_result is not None:
        sip_by_ts = {r["ts_et"]: r["ratio"] for r in sip_result["rows"]}
        iex_by_ts = {r["ts_et"]: r["ratio"] for r in iex_result["rows"]}
        common = sorted(set(sip_by_ts) & set(iex_by_ts))
        xs = [sip_by_ts[t] for t in common if sip_by_ts[t] != float("inf")
              and iex_by_ts[t] != float("inf")]
        ys = [iex_by_ts[t] for t in common if sip_by_ts[t] != float("inf")
              and iex_by_ts[t] != float("inf")]
        if len(xs) >= 3:
            sx = pd.Series(xs)
            sy = pd.Series(ys)
            correlation = float(sx.corr(sy))
        n_sip_bars = len({r["ts_et"] for r in sip_result["rows"]})
        n_common = len(common)
        print(f"[f10-reproduce] SIP bars={n_sip_bars} IEX-common-timestamps={n_common} "
              f"(IEX missing {n_sip_bars - n_common} of the SIP 5-min bins that day)")

    report = {
        "target_date": target,
        "warmup_dates": warmup,
        "vol_mult": args.vol_mult,
        "vol_baseline_bars": VOL_BASELINE_BARS,
        "sip": {k: v for k, v in sip_result.items() if k != "rows"},
        "iex": ({k: v for k, v in iex_result.items() if k != "rows"} if iex_result else None),
        "ratio_correlation_sip_vs_iex": correlation,
        "sip_rows": sip_result["rows"],
        "iex_rows": (iex_result["rows"] if iex_result else None),
    }

    print(f"[f10-reproduce] SIP:  n={sip_result['n_bars']} blocked={sip_result['n_blocked_f10']} "
          f"({sip_result['pct_blocked']:.1%}) ratio p10/p50/p90="
          f"{sip_result['ratio_p10']:.3f}/{sip_result['ratio_p50']:.3f}/{sip_result['ratio_p90']:.3f}")
    if iex_result is not None:
        print(f"[f10-reproduce] IEX:  n={iex_result['n_bars']} blocked={iex_result['n_blocked_f10']} "
              f"({iex_result['pct_blocked']:.1%}) ratio p10/p50/p90="
              f"{iex_result['ratio_p10']:.3f}/{iex_result['ratio_p50']:.3f}/{iex_result['ratio_p90']:.3f}")
        print(f"[f10-reproduce] ratio correlation (SIP vs IEX, common bars): {correlation}")

    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"[f10-reproduce] wrote {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
