"""v13_tv_mcp_parity — verify TradingView MCP behaves identically to Coinbase REST.

The SPY heartbeat uses `mcp__tradingview__data_get_ohlcv` for its bar reads.
On 2026-05-14 the foot-gun was specifically that TV returns the IN-PROGRESS
bar at index [-1] (same as Coinbase REST). This validator closes the loop:
- Compare TV's closed bars vs Coinbase's closed bars (should match)
- Confirm TV's last bar is in-progress when fetched mid-bar-window
- Run the same closed-bar filter against TV data, prove it works

The TV MCP is interactive-session only (not Python-callable). This validator
operates in two modes:
  --mode fixture  : compare against a captured TV+Coinbase snapshot fixture
  --mode live     : compare live Coinbase REST vs a SUPPLIED tv-bars JSON file
                    (capture from Claude session: `mcp__tradingview__data_get_ohlcv(count=5)`)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.lib.bar import Bar, BarSeries
from crypto.lib.bar_reader import last_closed_bar


def _coinbase_to_series(rows, granularity_seconds, symbol="BTC-USD") -> BarSeries:
    rows = sorted(rows, key=lambda r: r[0])
    bars = tuple(
        Bar(
            open_time=datetime.fromtimestamp(int(r[0]), tz=timezone.utc),
            low=float(r[1]), high=float(r[2]), open=float(r[3]),
            close=float(r[4]), volume=float(r[5]),
            granularity_seconds=granularity_seconds, source="coinbase",
        )
        for r in rows
    )
    return BarSeries(symbol=symbol, granularity_seconds=granularity_seconds, source="coinbase", bars=bars)


def _tv_to_series(tv_bars, granularity_seconds, symbol="COINBASE:BTCUSD") -> BarSeries:
    bars = tuple(
        Bar(
            open_time=datetime.fromtimestamp(int(b["time"]), tz=timezone.utc),
            open=float(b["open"]), high=float(b["high"]), low=float(b["low"]),
            close=float(b["close"]), volume=float(b["volume"]),
            granularity_seconds=granularity_seconds, source="tradingview",
        )
        for b in sorted(tv_bars, key=lambda x: x["time"])
    )
    return BarSeries(symbol=symbol, granularity_seconds=granularity_seconds, source="tradingview", bars=bars)


def compare_series(tv: BarSeries, cb: BarSeries, captured_at_unix: int, tolerance_pct: float = 0.05) -> dict:
    now = datetime.fromtimestamp(captured_at_unix, tz=timezone.utc)
    tv_closed = last_closed_bar(tv, now)
    cb_closed = last_closed_bar(cb, now)

    tv_map = {b.open_time: b for b in tv.bars}
    cb_map = {b.open_time: b for b in cb.bars}
    shared = sorted(set(tv_map) & set(cb_map))

    closed_disagreements = []
    in_progress_drift = None

    for t in shared:
        tv_bar, cb_bar = tv_map[t], cb_map[t]
        is_closed = tv_bar.is_closed_at(now) and cb_bar.is_closed_at(now)
        ohlc_close_delta = tv_bar.close - cb_bar.close
        ohlc_high_delta = tv_bar.high - cb_bar.high
        ohlc_low_delta = tv_bar.low - cb_bar.low
        ohlc_vol_ratio = (tv_bar.volume / cb_bar.volume) if cb_bar.volume > 0 else None

        worst = max(abs(d) for d in (ohlc_close_delta, ohlc_high_delta, ohlc_low_delta))
        worst_pct = (worst / cb_bar.close * 100) if cb_bar.close else 0

        if is_closed and worst_pct > tolerance_pct:
            closed_disagreements.append({
                "open_time": t.isoformat(),
                "close_delta": ohlc_close_delta,
                "worst_pct": worst_pct,
            })
        if not is_closed and in_progress_drift is None:
            in_progress_drift = {
                "open_time": t.isoformat(),
                "close_drift_usd": ohlc_close_delta,
                "high_drift_usd": ohlc_high_delta,
                "low_drift_usd": ohlc_low_delta,
                "vol_ratio": ohlc_vol_ratio,
            }

    return {
        "captured_at_unix": captured_at_unix,
        "tv_total_bars": len(tv),
        "cb_total_bars": len(cb),
        "shared_bars": len(shared),
        "tv_last_closed_open": tv_closed.last_closed.open_time.isoformat() if tv_closed.last_closed else None,
        "cb_last_closed_open": cb_closed.last_closed.open_time.isoformat() if cb_closed.last_closed else None,
        "tv_in_progress_open": tv_closed.in_progress.open_time.isoformat() if tv_closed.in_progress else None,
        "cb_in_progress_open": cb_closed.in_progress.open_time.isoformat() if cb_closed.in_progress else None,
        "closed_disagreements_count": len(closed_disagreements),
        "closed_disagreements_above_tolerance_pct": tolerance_pct,
        "closed_disagreements": closed_disagreements,
        "in_progress_drift": in_progress_drift,
        "foot_gun_signature": (
            tv_closed.in_progress is not None
            and cb_closed.in_progress is not None
            and tv_closed.in_progress.open_time == cb_closed.in_progress.open_time
        ),
        "pass": len(closed_disagreements) == 0,
    }


def run_fixture(fixture_path: Path, tolerance_pct: float) -> dict:
    fixture = json.loads(fixture_path.read_text())
    tv = _tv_to_series(fixture["tv_mcp_bars"], granularity_seconds=fixture["resolution"] * 60)
    cb = _coinbase_to_series(
        [(b["time"], b["low"], b["high"], b["open"], b["close"], b["volume"]) for b in fixture["coinbase_rest_bars"]],
        granularity_seconds=fixture["resolution"] * 60,
    )
    out = compare_series(tv, cb, fixture["captured_at_unix"], tolerance_pct)
    out["fixture"] = str(fixture_path)
    return out


def run_live(tv_bars_path: Path, tolerance_pct: float) -> dict:
    """Compare a fresh TV bars dump (from interactive session) against live Coinbase REST."""
    tv_data = json.loads(tv_bars_path.read_text())
    tv_bars = tv_data.get("bars", tv_data) if isinstance(tv_data, dict) else tv_data
    captured_at = int(tv_data.get("captured_at_unix", time.time())) if isinstance(tv_data, dict) else int(time.time())
    granularity_seconds = int(tv_data.get("granularity_seconds", 300)) if isinstance(tv_data, dict) else 300

    r = requests.get(
        "https://api.exchange.coinbase.com/products/BTC-USD/candles",
        params={"granularity": granularity_seconds},
        headers={"User-Agent": "gamma-crypto-validator/0.1"},
        timeout=15,
    )
    r.raise_for_status()
    cb_rows = r.json()
    tv = _tv_to_series(tv_bars, granularity_seconds)
    cb = _coinbase_to_series(cb_rows, granularity_seconds)
    return compare_series(tv, cb, captured_at, tolerance_pct)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["fixture", "live"], default="fixture")
    p.add_argument("--fixture", type=Path, default=Path("crypto/data/fixtures/tv_mcp_snapshot_2026-05-16T14-24Z.json"))
    p.add_argument("--tv-bars", type=Path, default=Path("crypto/data/fixtures/tv_bars_latest.json"))
    p.add_argument("--tolerance-pct", type=float, default=0.05)
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args(argv)

    if args.mode == "fixture":
        sc = run_fixture(args.fixture, args.tolerance_pct)
    else:
        sc = run_live(args.tv_bars, args.tolerance_pct)

    print(f"=== TV MCP vs COINBASE PARITY (mode={args.mode}) ===")
    print(f"  tv_total_bars:                  {sc['tv_total_bars']}")
    print(f"  cb_total_bars:                  {sc['cb_total_bars']}")
    print(f"  shared_bars:                    {sc['shared_bars']}")
    print(f"  tv_last_closed_open:            {sc['tv_last_closed_open']}")
    print(f"  cb_last_closed_open:            {sc['cb_last_closed_open']}")
    print(f"  tv_in_progress_open:            {sc['tv_in_progress_open']}")
    print(f"  cb_in_progress_open:            {sc['cb_in_progress_open']}")
    print(f"  closed_disagreements_count:     {sc['closed_disagreements_count']}")
    if sc["in_progress_drift"]:
        d = sc["in_progress_drift"]
        print(f"  in-progress drift @ {d['open_time']}:")
        print(f"    close_drift: ${d['close_drift_usd']:+.2f}")
        print(f"    high_drift:  ${d['high_drift_usd']:+.2f}")
        print(f"    low_drift:   ${d['low_drift_usd']:+.2f}")
        if d["vol_ratio"] is not None:
            print(f"    vol_ratio:   {d['vol_ratio']:.2f}x")
    print(f"  foot_gun_signature_present:     {sc['foot_gun_signature']}")
    print(f"  PASS:                            {sc['pass']}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(sc, indent=2, default=str))

    return 0 if sc["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
