"""futures_live_data.py -- the LIVE futures bar spine + never-blind staleness watchdog.

WHY THIS EXISTS (2026-08-09). The futures engine's only bar source was
`backtest/data/futures/{MES,MNQ}_5m_continuous.csv`, whose newest row is
**2026-06-12** -- two months stale. Every "live" futures tick built on top of it
would have been reading June bars while believing it was reading the tape. That is
the exact shape of the C7 class (silent success: a fetcher that returns SOMETHING is
not a fetcher that returns CURRENT something), so this module ships with the
staleness watchdog wired in from the first commit rather than as a follow-up.

THREE RULES THIS MODULE ENFORCES

1. **The validated master is never mutated.** `*_5m_continuous.csv` is a
   roll-adjusted continuous series that existing scorecards were computed on.
   Appending raw front-month bars to it would splice an unadjusted series onto an
   adjusted one and fabricate P&L across the seam (the #1 futures backtest footgun,
   `data.py` docstring). Live bars land in a SEPARATE `*_{interval}_live.csv`.

2. **Live trading reads the live file only.** Not master+live concatenated. The two
   are separated by a multi-week hole, and any indicator with a lookback that
   straddles that hole is computing across a gap it cannot see. yfinance serves 60
   days of 5-minute history, which is deeper than any warmup this engine needs, so
   the live file is self-sufficient AND contiguous. `mode="spliced"` exists for
   research, discloses the seam, and is never the live default.

3. **Every row carries provenance.** Feed, fetch time, and the delayed-quote caveat
   are stamped per append into `automation/state/futures/data-provenance.jsonl`, per
   markdown/infra/DATA-PROVENANCE.md. Yahoo labels CME futures a DELAYED quote
   (~10-15 min, CME licensing, not a Yahoo choice) -- so this feed is honest for bar
   -close decisions and is NOT a real-time execution feed. Anything that needs true
   real-time reads it from the broker or the TradingView CME add-on instead.

FEED QUIRK, MEASURED NOT ASSUMED (`verify_micro_alias`, run 2026-08-09): the micro
and mini tickers look interchangeable on a spot check -- both `MES=F` and `ES=F`
returned the same last close -- but over 1,028 overlapping 5-minute bars they are
NOT identical: max |close diff| = 0.75 pts (MES vs ES) and 9.00 pts (MNQ vs NQ).
They are separate books that track the same index and occasionally print apart. So
this module always fetches the MICRO ticker we actually trade, never the mini as a
stand-in, and the alias check is re-run and stamped into provenance on demand rather
than trusted once. (Point values differ too, and those live in `instruments.py`.)

TIME DISCIPLINE: `timestamp_et` is tz-aware America/New_York, parsed with the et-v2
convention (`utc=True` then `tz_convert`) that `run_native_backtest.load_futures`
uses -- so a live frame and a backtest frame are join-compatible.

CLI:
    python -m futures.futures_live_data --append MES MNQ     # fetch + extend live cache
    python -m futures.futures_live_data --check MES          # freshness verdict (exit 1 if not GREEN)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest",):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

import pandas as pd  # noqa: E402

from futures.futures_session import (  # noqa: E402
    et_now, is_session_open, session_phase, seconds_since_open,
)

FUTURES_DATA = REPO / "backtest" / "data" / "futures"
STATE_DIR = REPO / "automation" / "state" / "futures"
PROVENANCE_LOG = STATE_DIR / "data-provenance.jsonl"
FRESHNESS_FILE = STATE_DIR / "data-freshness.json"

ET = "America/New_York"
BAR_COLUMNS = ["timestamp_et", "open", "high", "low", "close", "volume"]

# yfinance history limits (Yahoo-imposed): 1m -> last 7d, 5m/15m -> last 60d.
_YF_PERIOD = {"1m": "7d", "5m": "60d", "15m": "60d", "1h": "730d"}

# Staleness thresholds in MULTIPLES of the bar interval, evaluated only while the
# session is open. Generous enough to absorb one missed poll, tight enough that a
# genuinely dead feed is caught within minutes.
STALE_BARS_YELLOW = 3
STALE_BARS_RED = 6

# A session needs to have been open at least this long before absence of a new bar
# means anything -- at the 18:00 ET reopen there is legitimately no bar yet.
WARMUP_SECONDS = 300


def live_path(root: str, interval: str = "5m") -> Path:
    return FUTURES_DATA / f"{root.upper()}_{interval}_live.csv"


def master_path(root: str, interval: str = "5m") -> Path:
    return FUTURES_DATA / f"{root.upper()}_{interval}_continuous.csv"


# ── fetch ─────────────────────────────────────────────────────────────────────

def fetch(root: str, interval: str = "5m", period: Optional[str] = None) -> pd.DataFrame:
    """Pull recent bars for `root` (MES/MNQ/ES/NQ) and normalize to the engine schema.

    Returns an EMPTY DataFrame (never None, never a partial frame) when the feed
    yields nothing, so callers cannot mistake a dead feed for a quiet market -- the
    bare-`except: return None` shape is the L241 foot-gun this avoids.
    """
    import yfinance as yf  # noqa: PLC0415 -- lazy so a missing dep fails at the edge

    symbol = f"{root.upper()}=F"
    period = period or _YF_PERIOD.get(interval, "60d")
    raw = yf.download(symbol, period=period, interval=interval,
                      progress=False, auto_adjust=False)
    if raw is None or len(raw) == 0:
        return pd.DataFrame(columns=BAR_COLUMNS)

    # yfinance returns a MultiIndex column frame for single tickers in recent versions.
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    idx = pd.to_datetime(raw.index, utc=True).tz_convert(ET)
    out = pd.DataFrame({
        "timestamp_et": idx,
        "open": raw["Open"].astype(float).values,
        "high": raw["High"].astype(float).values,
        "low": raw["Low"].astype(float).values,
        "close": raw["Close"].astype(float).values,
        "volume": raw["Volume"].fillna(0).astype("int64").values,
    })
    out = out.dropna(subset=["open", "high", "low", "close"])
    return out.sort_values("timestamp_et").reset_index(drop=True)


def verify_micro_alias(root: str = "MES", interval: str = "5m") -> dict:
    """Measure whether Yahoo serves the micro and the mini as one series.

    Recorded in provenance rather than assumed. Returns the comparison, never raises.
    """
    mini = {"MES": "ES", "MNQ": "NQ"}.get(root.upper())
    if not mini:
        return {"checked": False, "reason": f"{root} has no mini counterpart"}
    try:
        a = fetch(root, interval, period="5d")
        b = fetch(mini, interval, period="5d")
        if a.empty or b.empty:
            return {"checked": False, "reason": "one or both feeds empty"}
        merged = a.merge(b, on="timestamp_et", suffixes=("_micro", "_mini"))
        if merged.empty:
            return {"checked": True, "identical": False, "reason": "no overlapping bars"}
        diff = (merged["close_micro"] - merged["close_mini"]).abs()
        return {
            "checked": True,
            "identical": bool(diff.max() == 0),
            "n_compared": int(len(merged)),
            "max_abs_close_diff": float(diff.max()),
        }
    except Exception as e:  # noqa: BLE001 -- diagnostic only, never breaks an append
        return {"checked": False, "reason": f"{type(e).__name__}: {e}"}


# ── cache ─────────────────────────────────────────────────────────────────────

def _read_csv_et(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=BAR_COLUMNS)
    df = pd.read_csv(path)
    if df.empty:
        return pd.DataFrame(columns=BAR_COLUMNS)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert(ET)
    return df.sort_values("timestamp_et").reset_index(drop=True)


def _atomic_write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=False)
    os.replace(tmp, path)


def _log_provenance(record: dict) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with PROVENANCE_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except Exception:  # noqa: BLE001 -- provenance logging never breaks a fetch
        pass


def append_live(root: str, interval: str = "5m", *, verify_alias: bool = False) -> dict:
    """Extend the live cache with any bars newer than what it already holds.

    Existing rows are never rewritten -- only strictly-new timestamps are appended,
    so a Yahoo revision to an old bar cannot silently mutate history under a
    scorecard that already read it.
    """
    path = live_path(root, interval)
    existing = _read_csv_et(path)
    fresh = fetch(root, interval)

    result = {
        "root": root.upper(),
        "interval": interval,
        "fetched_at_et": et_now().isoformat(timespec="seconds"),
        "feed": f"yfinance:{root.upper()}=F",
        "delayed_quote": True,
        "rows_fetched": int(len(fresh)),
        "rows_before": int(len(existing)),
        "rows_added": 0,
        "new_through": None,
        "path": str(path.relative_to(REPO)),
    }

    if fresh.empty:
        result["error"] = "feed returned zero bars"
        _log_provenance(result)
        return result

    if existing.empty:
        merged = fresh
        result["rows_added"] = int(len(fresh))
    else:
        cutoff = existing["timestamp_et"].max()
        new_rows = fresh[fresh["timestamp_et"] > cutoff]
        result["rows_added"] = int(len(new_rows))
        merged = pd.concat([existing, new_rows], ignore_index=True) if len(new_rows) else existing

    merged = (merged.drop_duplicates(subset=["timestamp_et"], keep="first")
                    .sort_values("timestamp_et")
                    .reset_index(drop=True))
    _atomic_write_csv(merged[BAR_COLUMNS], path)

    result["rows_after"] = int(len(merged))
    result["new_through"] = merged["timestamp_et"].max().isoformat()
    if verify_alias:
        result["micro_alias_check"] = verify_micro_alias(root, interval)
    _log_provenance(result)
    return result


def load_series(root: str, interval: str = "5m", mode: str = "live") -> pd.DataFrame:
    """Return bars for `root`.

    mode="live"     -- the contiguous live cache ONLY. The live default; see rule 2.
    mode="master"   -- the validated roll-adjusted continuous series (backtests).
    mode="spliced"  -- master then live, with the seam DISCLOSED on the frame as
                       `.attrs["seam"]`. Research only; never wire this into a tick.
    """
    if mode == "master":
        return _read_csv_et(master_path(root, interval))
    if mode == "live":
        return _read_csv_et(live_path(root, interval))
    if mode != "spliced":
        raise ValueError(f"unknown mode {mode!r}")

    master = _read_csv_et(master_path(root, interval))
    live = _read_csv_et(live_path(root, interval))
    if master.empty or live.empty:
        out = live if master.empty else master
        out.attrs["seam"] = {"spliced": False, "reason": "one side empty"}
        return out

    cutoff = master["timestamp_et"].max()
    tail = live[live["timestamp_et"] > cutoff]
    out = pd.concat([master, tail], ignore_index=True).reset_index(drop=True)
    gap_minutes = None
    if len(tail):
        gap_minutes = (tail["timestamp_et"].min() - cutoff).total_seconds() / 60.0
    out.attrs["seam"] = {
        "spliced": True,
        "master_ends": cutoff.isoformat(),
        "live_starts": tail["timestamp_et"].min().isoformat() if len(tail) else None,
        "gap_minutes": gap_minutes,
        "warning": ("master is roll-adjusted, live is raw front-month; any indicator "
                    "whose lookback straddles the seam is computing across a gap"),
    }
    return out


# ── never-blind watchdog ──────────────────────────────────────────────────────

def freshness(root: str, interval: str = "5m",
              now_et: Optional[dt.datetime] = None) -> dict:
    """Judge whether the bar feed is currently trustworthy.

    Session-aware by construction: staleness is only meaningful while CME is open
    and has been open long enough to have printed a bar. Outside the session the
    verdict is CLOSED, not STALE -- a watchdog that screams all weekend gets muted,
    and a muted watchdog is not a watchdog.

    Verdicts: GREEN (current) | YELLOW (lagging) | RED (stale during a live session)
              | BLIND (no bars at all) | CLOSED (session not open) | WARMUP (just reopened)
    """
    now_et = now_et or et_now()
    df = _read_csv_et(live_path(root, interval))
    interval_min = int(str(interval).rstrip("mh")) * (60 if interval.endswith("h") else 1)

    out = {
        "root": root.upper(),
        "interval": interval,
        "checked_at_et": now_et.isoformat(timespec="seconds"),
        "session_phase": session_phase(now_et),
        "session_open": is_session_open(now_et),
        "n_bars": int(len(df)),
        "newest_bar_et": None,
        "age_minutes": None,
        "verdict": "BLIND",
        "detail": "",
    }

    if df.empty:
        out["detail"] = f"no live bars cached for {root} -- run --append"
        return out

    newest = df["timestamp_et"].max()
    out["newest_bar_et"] = newest.isoformat()
    age_min = (now_et - newest.tz_localize(None)).total_seconds() / 60.0
    out["age_minutes"] = round(age_min, 1)

    if not out["session_open"]:
        out["verdict"] = "CLOSED"
        out["detail"] = f"session {out['session_phase']}; newest bar {age_min:.0f}m old (expected)"
        return out

    since_open = seconds_since_open(now_et) or 0
    if since_open < WARMUP_SECONDS:
        out["verdict"] = "WARMUP"
        out["detail"] = f"session reopened {since_open}s ago; no bar expected yet"
        return out

    if age_min <= interval_min * STALE_BARS_YELLOW:
        out["verdict"] = "GREEN"
    elif age_min <= interval_min * STALE_BARS_RED:
        out["verdict"] = "YELLOW"
    else:
        out["verdict"] = "RED"
    out["detail"] = (f"newest bar {age_min:.0f}m old vs {interval} bars during an open "
                     f"session (yellow>{interval_min * STALE_BARS_YELLOW}m, "
                     f"red>{interval_min * STALE_BARS_RED}m)")
    return out


def write_freshness_snapshot(roots=("MES", "MNQ"), interval: str = "5m") -> dict:
    """Persist a glanceable freshness snapshot for the dashboard / liveness alarm."""
    snap = {
        "written_at_et": et_now().isoformat(timespec="seconds"),
        "feeds": {r.upper(): freshness(r, interval) for r in roots},
    }
    worst = "GREEN"
    order = ["GREEN", "WARMUP", "CLOSED", "YELLOW", "RED", "BLIND"]
    for f in snap["feeds"].values():
        if order.index(f["verdict"]) > order.index(worst):
            worst = f["verdict"]
    snap["verdict"] = worst
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = FRESHNESS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(snap, indent=2), encoding="utf-8")
        os.replace(tmp, FRESHNESS_FILE)
    except Exception:  # noqa: BLE001 -- snapshot write never breaks the caller
        pass
    return snap


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Futures live bar spine + staleness watchdog")
    ap.add_argument("--append", nargs="*", metavar="ROOT", help="fetch + extend live cache")
    ap.add_argument("--check", nargs="*", metavar="ROOT", help="freshness verdict")
    ap.add_argument("--interval", default="5m")
    ap.add_argument("--verify-alias", action="store_true",
                    help="measure whether Yahoo aliases the micro to the mini series")
    args = ap.parse_args(argv)

    if args.append is not None:
        roots = args.append or ["MES", "MNQ"]
        for r in roots:
            res = append_live(r, args.interval, verify_alias=args.verify_alias)
            print(json.dumps(res, indent=2))
        snap = write_freshness_snapshot(tuple(roots), args.interval)
        print(f"\nFRESHNESS: {snap['verdict']}")
        return 0

    if args.check is not None:
        roots = args.check or ["MES", "MNQ"]
        snap = write_freshness_snapshot(tuple(roots), args.interval)
        print(json.dumps(snap, indent=2))
        return 0 if snap["verdict"] in ("GREEN", "CLOSED", "WARMUP") else 1

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
