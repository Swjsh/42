"""Signal-density probe — does the weekly level trigger fire OFTEN ENOUGH to be testable?

HARD BLOCKING PREREQUISITE for the expiry experiment (merged build plan; program doc §9b
phase 6). The frozen pre-registration requires >= 30 paired observations. If the trigger
fires fewer times than that across all available history, the experiment cannot answer J's
which-Friday question with this data, and the honest move is to say so rather than build a
runner that produces an underpowered number.

It also answers the program's single biggest risk directly (L199, "6 arms, 700 signals, 0
trades"): a stack of AND-gates can silently reduce participation to zero. This probe measures
the FIRST gate in that stack -- the signal itself -- in isolation.

NO LOOK-AHEAD, and this is the subtle part:
`trigger.detect_trigger` is written for a live tick (it evaluates only the NEWEST closed 1H
bar). To scan history we replay it bar by bar, and at each step the daily bars used to build
zones are restricted to sessions STRICTLY BEFORE the current hourly bar's own session. Using
the current session's daily bar would leak that day's high/low into an intraday decision --
the classic C6 leak, and the one most likely to make a dead signal look alive.

$0: reuses the already-wired paper market-data key. Places no orders, writes no state.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from zoneinfo import ZoneInfo
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (REPO_ROOT, REPO_ROOT / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from weekly.lib import bars as wbars  # noqa: E402
from weekly.lib import zones as wzones  # noqa: E402
from weekly.lib import trigger as wtrigger  # noqa: E402

OUT_DIR = REPO_ROOT / "analysis" / "weekly-lane"
ET = ZoneInfo("America/New_York")
MIN_PAIRS_REQUIRED = 30  # from the frozen prereg's statistics.min_paired_observations


class ProbeError(RuntimeError):
    """Fail loud: an empty probe result must never look like 'the signal is fine'."""


def probe_symbol(symbol: str, *, daily_limit: int, hourly_limit: int,
                 params: dict) -> dict:
    daily_df = wbars.fetch_daily(symbol, limit=daily_limit, min_bars=60)
    hourly_df = wbars.fetch_hourly(symbol, limit=hourly_limit, min_bars=50)

    daily_bars = wbars.dataframe_to_bars(daily_df, "1Day", source=f"{symbol}_1d")
    hourly_bars = wbars.dataframe_to_bars(hourly_df, "1Hour", source=f"{symbol}_1h")

    daily_dates = [b.open_time.astimezone(ET).date() for b in daily_bars]
    hourly_dates = [b.open_time.astimezone(ET).date() for b in hourly_bars]

    warmup = 60  # enough 1H structure to have swings at all
    signals: list[dict] = []
    zone_cache: dict = {}
    evaluated = 0
    no_prior_daily = 0

    for i in range(warmup, len(hourly_bars)):
        session = hourly_dates[i]
        # STRICTLY BEFORE the current session -- see module docstring.
        n_prior = sum(1 for d in daily_dates if d < session)
        if n_prior < 55:
            no_prior_daily += 1
            continue
        if n_prior not in zone_cache:
            try:
                zone_cache[n_prior] = wzones.compute_zones(
                    daily_bars[:n_prior], params=params
                )
            except wzones.ZoneConsistencyError as e:
                raise ProbeError(f"{symbol}: zone consistency violated at {session}: {e}") from e
        zones = zone_cache[n_prior]
        evaluated += 1
        sig = wtrigger.detect_trigger(symbol, zones, hourly_bars[: i + 1], params=params)
        if sig is not None:
            signals.append({
                "session": session.isoformat(),
                "bar_ts": hourly_bars[i].open_time.astimezone(ET).isoformat(),
                "direction": sig.direction,
                "zone_price": round(sig.zone.price, 4),
                "zone_family": getattr(sig.zone, "family", None),
                "zone_width": round(sig.zone.width, 4),
                "confluence": sig.confluence_count,
                "close": round(hourly_bars[i].close, 4),
            })

    sessions = sorted({s["session"] for s in signals})
    return {
        "symbol": symbol,
        "hourly_bars_available": len(hourly_bars),
        "hourly_bars_evaluated": evaluated,
        "skipped_insufficient_prior_daily": no_prior_daily,
        "daily_bars_available": len(daily_bars),
        "history_start": hourly_dates[0].isoformat() if hourly_dates else None,
        "history_end": hourly_dates[-1].isoformat() if hourly_dates else None,
        "n_signals": len(signals),
        "n_distinct_sessions": len(sessions),
        "signals_per_100_bars": round(100.0 * len(signals) / evaluated, 3) if evaluated else 0.0,
        "direction_split": dict(Counter(s["direction"] for s in signals)),
        "confluence_split": dict(Counter(s["confluence"] for s in signals)),
        "zone_family_split": dict(Counter(s["zone_family"] for s in signals)),
        "signal_sessions": sessions,
        "signals": signals,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--symbols", default=None, help="default: params.json universe.active")
    ap.add_argument("--daily-limit", type=int, default=300)
    ap.add_argument("--hourly-limit", type=int, default=2000)
    args = ap.parse_args(argv)

    params = wzones.load_weekly_params()
    symbols = (
        [s.strip().upper() for s in args.symbols.split(",")]
        if args.symbols else list(params["universe"]["active"])
    )

    results = []
    for sym in symbols:
        r = probe_symbol(sym, daily_limit=args.daily_limit,
                         hourly_limit=args.hourly_limit, params=params)
        results.append(r)
        print(
            f"[{sym}] {r['n_signals']} signals over {r['n_distinct_sessions']} distinct "
            f"sessions from {r['hourly_bars_evaluated']} evaluated 1H bars "
            f"({r['history_start']}..{r['history_end']}) "
            f"= {r['signals_per_100_bars']}/100 bars",
            file=sys.stderr,
        )

    total_signals = sum(r["n_signals"] for r in results)
    total_sessions = len({s for r in results for s in r["signal_sessions"]})
    verdict = (
        "SUFFICIENT" if total_signals >= MIN_PAIRS_REQUIRED
        else "INSUFFICIENT_FOR_PREREG"
    )

    payload = {
        "probe": "weekly_signal_density",
        "params_signal_block": params["signal"],
        "min_pairs_required_by_prereg": MIN_PAIRS_REQUIRED,
        "total_signals": total_signals,
        "total_distinct_sessions": total_sessions,
        "verdict": verdict,
        "_verdict_meaning": (
            "SUFFICIENT = the expiry experiment can reach the prereg's n>=30 paired "
            "observations. INSUFFICIENT = it cannot, and reporting a result anyway would be "
            "an underpowered number dressed as evidence."
        ),
        "per_symbol": results,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "signal-density-probe.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"\nTOTAL: {total_signals} signals / {total_sessions} distinct sessions -> {verdict}",
          file=sys.stderr)
    print(f"wrote {out}", file=sys.stderr)

    if total_signals == 0:
        print(
            "ERROR: zero signals across the entire history. That is a finding, not a run "
            "failure -- but it means the trigger as configured never fires, and the lane "
            "would trade nothing. Exiting non-zero so this cannot be mistaken for success.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
