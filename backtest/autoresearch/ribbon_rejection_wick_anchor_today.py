"""RIBBON_REJECTION_WICK — anchor-case sanity check against TODAY's live bars.

Fetches SPY 5m OHLCV via Alpaca market-data REST (key from .mcp.json, same
pattern as setup/scripts/sight_beacon.py), saves a fixture CSV for the guard
test, then runs the detector over today's RTH bars and reports every fire.

J's anchor (2026-07-02): the 10:30 and 10:35 ET bars wicked up into the EMA
ribbon from below and were rejected — the detector MUST fire on at least one
of them, and MUST NOT fire more than ~5 times today (too loose = noise).

Usage:
    backtest/.venv/Scripts/python.exe backtest/autoresearch/ribbon_rejection_wick_anchor_today.py
    ... --date 2026-07-02 --fixture backtest/tests/fixtures/spy_5m_2026-07-02_anchor.csv
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent      # backtest/
PROJECT_ROOT = REPO.parent                          # 42/
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(PROJECT_ROOT))

from lib.ribbon import compute_ribbon  # noqa: E402
from lib.watchers.ribbon_rejection_wick_detector import (  # noqa: E402
    RRWParams,
    SUPERSET_PARAMS,
    detect_both,
)

MCP_JSON = PROJECT_ROOT / ".mcp.json"
DEFAULT_FIXTURE = REPO / "tests" / "fixtures" / "spy_5m_2026-07-02_anchor.csv"

RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)


def _load_alpaca_key() -> tuple[str, str]:
    """Safe-account data key from .mcp.json (never hardcode — CLAUDE.md)."""
    m = json.loads(MCP_JSON.read_text(encoding="utf-8"))
    env = m.get("mcpServers", {}).get("alpaca", {}).get("env", {})
    return env.get("ALPACA_API_KEY", ""), env.get("ALPACA_SECRET_KEY", "")


def fetch_spy_5m(days_back: int = 7) -> pd.DataFrame:
    """Full OHLCV 5m bars (IEX feed, incl. premarket), oldest->newest, ET naive.

    Pages on next_page_token; limit=10000 makes one page the normal case
    (L-scar: sort+limit truncation — we page explicitly, never trust one call).
    """
    key, sec = _load_alpaca_key()
    if not key or not sec:
        raise RuntimeError("no Alpaca key in .mcp.json — cannot fetch today's bars")
    start = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_back)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    rows: list[dict] = []
    token = None
    for _page in range(10):
        url = (
            "https://data.alpaca.markets/v2/stocks/SPY/bars"
            f"?timeframe=5Min&start={start}&limit=10000&feed=iex&adjustment=raw&sort=asc"
        )
        if token:
            url += f"&page_token={token}"
        req = urllib.request.Request(
            url,
            headers={
                "APCA-API-KEY-ID": key,
                "APCA-API-SECRET-KEY": sec,
                "accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
        for b in data.get("bars") or []:
            rows.append(
                {
                    "timestamp_et": b["t"],
                    "open": b["o"],
                    "high": b["h"],
                    "low": b["l"],
                    "close": b["c"],
                    "volume": b["v"],
                }
            )
        token = data.get("next_page_token")
        if not token:
            break
    if not rows:
        raise RuntimeError("Alpaca returned zero bars")
    df = pd.DataFrame(rows)
    df["timestamp_et"] = (
        pd.to_datetime(df["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    df = df.drop_duplicates(subset="timestamp_et").sort_values("timestamp_et")
    return df.reset_index(drop=True)


def run_anchor(
    df: pd.DataFrame,
    session: dt.date,
    params: RRWParams,
    rth_only: bool = True,
) -> dict:
    """Scan `session`'s bars with the detector; return fires + context."""
    frame = df.copy()
    if rth_only:
        t = frame["timestamp_et"].dt.time
        frame = frame[(t >= RTH_OPEN) & (t < RTH_CLOSE)].reset_index(drop=True)

    ribbon = compute_ribbon(frame["close"])
    day_mask = frame["timestamp_et"].dt.date == session
    day_idx = frame.index[day_mask].tolist()

    fires = []
    for i in day_idx:
        ts = frame.iloc[i]["timestamp_et"]
        if ts.time() < dt.time(9, 45) or ts.time() > dt.time(15, 0):
            continue
        for sig in detect_both(frame, i, params, ribbon_df=ribbon):
            fires.append(sig)

    # Context: premarket open + the 10:25 volume claim (needs the full ETH frame).
    pm = df[
        (df["timestamp_et"].dt.date == session)
        & (df["timestamp_et"].dt.time < RTH_OPEN)
    ]
    pm_open = float(pm.iloc[0]["open"]) if len(pm) else None
    pm_low = float(pm["low"].min()) if len(pm) else None
    return {
        "session": session.isoformat(),
        "rth_only": rth_only,
        "n_day_bars": len(day_idx),
        "premarket_open": pm_open,
        "premarket_low": pm_low,
        "n_fires": len(fires),
        "fires": fires,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="session date (default: today ET)")
    ap.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    ap.add_argument("--from-fixture", action="store_true", help="skip fetch; read fixture CSV")
    args = ap.parse_args()

    if args.from_fixture:
        df = pd.read_csv(args.fixture)
        df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    else:
        df = fetch_spy_5m()
        fx = Path(args.fixture)
        fx.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(fx, index=False)
        print(f"fixture saved: {fx} ({len(df)} bars, "
              f"{df['timestamp_et'].iloc[0]} .. {df['timestamp_et'].iloc[-1]})")

    session = (
        dt.date.fromisoformat(args.date)
        if args.date
        else df["timestamp_et"].iloc[-1].date()
    )

    default_params = RRWParams()  # wick 0.35 / lookback 12 / vol off / stack not-flipped
    out = run_anchor(df, session, default_params, rth_only=True)

    print(f"\n=== RIBBON_REJECTION_WICK anchor check — {out['session']} "
          f"(RTH-only ribbon, default params) ===")
    print(f"day bars: {out['n_day_bars']}  premarket_open: {out['premarket_open']}  "
          f"premarket_low: {out['premarket_low']}")
    print(f"fires: {out['n_fires']}")
    for f in out["fires"]:
        print(f"  {f['trigger_bar_time']}  {f['direction']:8s} close={f['bar_close']:.2f} "
              f"high={f['bar_high']:.2f} band=[{f['band_low']:.2f},{f['band_high']:.2f}] "
              f"wick={f['wick_frac']:.2f} since_break={f['bars_since_break']} "
              f"volx={f['vol_break_ratio']:.1f} stack={f['stack_at_signal']}")

    # Superset view (loosest grid corner) for fire-count context.
    sup = run_anchor(df, session, SUPERSET_PARAMS, rth_only=True)
    print(f"\nsuperset (loosest grid corner) fires today: {sup['n_fires']}")
    for f in sup["fires"]:
        print(f"  {f['trigger_bar_time']}  {f['direction']:8s} wick={f['wick_frac']:.2f} "
              f"since_break={f['bars_since_break']} volx={f['vol_break_ratio']:.1f} "
              f"stack={f['stack_at_signal']}")

    anchor_hit = any(
        f["direction"] == "bearish" and f["trigger_bar_time"][11:16] in ("10:30", "10:35")
        for f in out["fires"]
    )
    print(f"\nANCHOR (bearish fire at 10:30/10:35 ET): {'HIT' if anchor_hit else 'MISS'}")
    print(f"fire-count check (<=5): {'PASS' if out['n_fires'] <= 5 else 'TOO LOOSE'}")
    return 0 if anchor_hit else 1


if __name__ == "__main__":
    sys.exit(main())
