"""VARIANT signal probe: zones from WEEKLY bars, trigger on DAILY bars.

Tests the #1 ranked hypothesis for why the v1 signal failed
(analysis/deep-research/WEEKLY-EXPIRY-EXPERIMENT-2026-08-18.md addendum): the production
trigger requires a structure shift on the newest **1-hour** bar to justify a **multi-day**
hold. That is a timeframe mismatch — an hourly CHoCH is a intraday event being asked to
predict a multi-day move.

The fix under test is a clean one-step scale-up that PRESERVES the design's slow-zone /
fast-trigger separation:

    production : zones from DAILY  , trigger on 1-HOUR
    variant    : zones from WEEKLY , trigger on DAILY

WHY NOT "zones from daily, trigger on daily": that would be circular. Zones are built from
daily swing highs/lows, so a daily break-of-structure IS, by construction, a break at one of
those very swings — the trigger would fire trivially and mean nothing. Keeping a genuine
timeframe gap between the zone series and the trigger series is what makes the signal a signal.

Weekly bars are aggregated from the daily series (Alpaca has no native weekly bar we need);
aggregation is calendar-week, and an INCOMPLETE trailing week is dropped so no partial week
can act as a closed bar (lesson C6).

Emits the SAME schema as weekly_signal_density_probe.py so the existing expiry-experiment
machinery can consume it unchanged. Reads only; places no orders.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (REPO_ROOT, REPO_ROOT / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from crypto.lib.bar import Bar  # noqa: E402
from weekly.lib import bars as wbars  # noqa: E402
from weekly.lib import trigger as wtrigger  # noqa: E402
from weekly.lib import zones as wzones  # noqa: E402

ET = ZoneInfo("America/New_York")
OUT = REPO_ROOT / "analysis" / "weekly-lane" / "signal-density-probe-DAILY-VARIANT.json"
_WEEK_SECONDS = 7 * 86_400


class VariantProbeError(RuntimeError):
    """Fail loud — an empty variant probe must not read as 'the variant is fine'."""


def to_weekly(daily: list[Bar]) -> list[Bar]:
    """Aggregate daily Bars into calendar-week Bars, dropping any incomplete trailing week."""
    buckets: dict[date, list[Bar]] = {}
    for b in daily:
        d = b.open_time.astimezone(ET).date()
        monday = d - timedelta(days=d.weekday())
        buckets.setdefault(monday, []).append(b)

    weeks = []
    for monday in sorted(buckets):
        grp = sorted(buckets[monday], key=lambda x: x.open_time)
        # A week is only CLOSED once we have its Friday, or the next week has started.
        weeks.append((monday, grp))
    if not weeks:
        return []
    # Drop the final week if it is still in progress (fewer than 5 sessions AND it is the
    # newest week present). Conservative: it can only withhold a bar, never admit an open one.
    last_monday, last_grp = weeks[-1]
    if len(last_grp) < 5:
        weeks = weeks[:-1]

    out = []
    for monday, grp in weeks:
        out.append(Bar(
            open_time=grp[0].open_time,
            open=grp[0].open,
            high=max(x.high for x in grp),
            low=min(x.low for x in grp),
            close=grp[-1].close,
            volume=sum(x.volume for x in grp),
            granularity_seconds=_WEEK_SECONDS,
            source=f"{grp[0].source}_weekly_agg",
        ))
    return out


def probe_symbol(symbol: str, params: dict, daily_limit: int) -> dict:
    daily_df = wbars.fetch_daily(symbol, limit=daily_limit, min_bars=120)
    daily_bars = list(wbars.dataframe_to_bars(daily_df, "1Day", source=f"{symbol}_1d"))
    daily_dates = [b.open_time.astimezone(ET).date() for b in daily_bars]

    signals: list[dict] = []
    evaluated = 0
    # ATR(14) on the WEEKLY series needs >=15 weekly bars, so the daily warmup must be
    # long enough to aggregate that many complete weeks (~5 sessions each) plus margin.
    warmup = 120

    for i in range(warmup, len(daily_bars)):
        session = daily_dates[i]
        # Weekly zones from STRICTLY-EARLIER daily data (no same-session leak, and to_weekly
        # additionally drops an in-progress week).
        prior_daily = daily_bars[:i]
        weekly = to_weekly(prior_daily)
        if len(weekly) < 20:  # ATR(14) + margin; zones.py refuses below this, by design
            continue
        try:
            zones = wzones.compute_zones(weekly, params=params)
        except wzones.ZoneConsistencyError as e:
            raise VariantProbeError(f"{symbol}: zone consistency violated at {session}: {e}") from e
        evaluated += 1
        sig = wtrigger.detect_trigger(symbol, zones, daily_bars[: i + 1], params=params)
        if sig is not None:
            signals.append({
                "session": session.isoformat(),
                "bar_ts": daily_bars[i].open_time.astimezone(ET).isoformat(),
                "direction": sig.direction,
                "zone_price": round(sig.zone.price, 4),
                "zone_family": getattr(sig.zone, "family", None),
                "zone_width": round(sig.zone.width, 4),
                "confluence": sig.confluence_count,
                "close": round(daily_bars[i].close, 4),
            })

    sessions = sorted({s["session"] for s in signals})
    return {
        "symbol": symbol,
        "variant": "zones=WEEKLY, trigger=DAILY",
        "daily_bars_available": len(daily_bars),
        "sessions_evaluated": evaluated,
        "history_start": daily_dates[0].isoformat() if daily_dates else None,
        "history_end": daily_dates[-1].isoformat() if daily_dates else None,
        "n_signals": len(signals),
        "n_distinct_sessions": len(sessions),
        "signals_per_100_sessions": round(100.0 * len(signals) / evaluated, 2) if evaluated else 0.0,
        "direction_split": dict(Counter(s["direction"] for s in signals)),
        "zone_family_split": dict(Counter(s["zone_family"] for s in signals)),
        "confluence_split": dict(Counter(s["confluence"] for s in signals)),
        "signal_sessions": sessions,
        "signals": signals,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--symbols", default=None)
    ap.add_argument("--daily-limit", type=int, default=400)
    args = ap.parse_args(argv)

    params = wzones.load_weekly_params()
    symbols = ([s.strip().upper() for s in args.symbols.split(",")]
               if args.symbols else list(params["universe"]["active"]))

    results = [probe_symbol(s, params, args.daily_limit) for s in symbols]
    for r in results:
        print(f"[{r['symbol']}] {r['n_signals']} signals / {r['n_distinct_sessions']} sessions "
              f"from {r['sessions_evaluated']} evaluated daily bars "
              f"({r['history_start']}..{r['history_end']}) "
              f"= {r['signals_per_100_sessions']}/100 sessions", file=sys.stderr)

    total = sum(r["n_signals"] for r in results)
    payload = {
        "probe": "weekly_signal_density_DAILY_VARIANT",
        "variant": "zones=WEEKLY, trigger=DAILY (production is zones=DAILY, trigger=1H)",
        "hypothesis": "the 1H trigger is too fast a timeframe to justify a multi-day hold",
        "params_signal_block": params["signal"],
        "min_pairs_required_by_prereg": 30,
        "total_signals": total,
        "total_distinct_sessions": len({s for r in results for s in r["signal_sessions"]}),
        "verdict": "SUFFICIENT" if total >= 30 else "INSUFFICIENT_FOR_PREREG",
        "per_symbol": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nTOTAL: {total} signals -> {payload['verdict']}\nwrote {OUT}", file=sys.stderr)

    if total == 0:
        print("ERROR: zero variant signals. A finding, not a clean run.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
