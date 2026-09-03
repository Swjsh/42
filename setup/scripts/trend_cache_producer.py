"""trend_cache_producer.py -- daily $0 extender for the trend-classification SPY-daily-bar
cache backtest/tools/regime_classifier.py's classify_trend_asof reads.

WHY (TREND-CLASSIFICATION-CACHE-STALE-SINCE-07-14, automation/overnight/queue.md):
analysis/backtests/cache/trend-alignment-spy-daily-2024-07-01_2026-07-14.json is a FROZEN,
untracked one-off build artifact -- produced 2026-07-14 by
backtest/tools/trend_alignment_correlation_study.py's `--build-cache` step
(`fetch_historical_bars("daily")`, whose FETCH_START/FETCH_END module constants are
deliberately pinned for THAT study's own reproducibility and will never advance; verified
via `git log`/`git status` that the file itself carries no producer commit -- it is
untracked). Nothing has extended it since. Every trend classification for a date past
2026-07-14 either fabricates a plausible-looking answer (the raw, unguarded
`classify_trend_asof` -- its own bar-count check only measures window DENSITY, not
RECENCY) or returns `unknown` (the guarded path in
backtest/tools/regime_conditioned_validation.py) -- 269/403 (67%) real trades and all 6
go-live-gate evidence days, per the queue item.

WHAT THIS SCRIPT DOES -- and does NOT do:
  - Reads whatever cache `regime_classifier.DAILY_SPY_CACHE` currently resolves to for its
    EXISTING bars ("the SPY daily bars already on disk", per the task brief) -- the frozen
    file on a first run, or yesterday's extension after that.
  - Fetches ONLY a small overlapping tail via the SAME paginated Alpaca REST daily-bar
    pull `trend_alignment_correlation_study.fetch_historical_bars` uses: same credential
    loader (`context_bundle_producer._load_alpaca_creds` -- reused, not reimplemented; no
    new vendor), same URL shape (`timeframe=1Day`, `feed=iex`, `adjustment=raw`,
    `sort=asc`, paginated via `page_token`).
  - Merges: fetched bars win on any timestamp overlap (freshest data), every existing bar
    OUTSIDE the fetch window is preserved BYTE-FOR-BYTE. A date's trend label, once
    computable from the frozen file, never changes -- confirmed by
    backtest/tests/test_trend_cache_producer_2026_09_03.py's byte-equality assertion
    against the frozen cache for every overlapping date.
  - Writes a NEW dated file `trend-alignment-spy-daily-2024-07-01_<END>.json` (SAME naming
    convention `_cache_path()` in trend_alignment_correlation_study.py uses, so
    regime_classifier.py's loader needs zero format change) and updates the stable pointer
    `automation/state/trend-alignment-latest.json`. NEVER writes to the frozen
    2026-07-14 filename -- refuses loudly if that would ever happen.
  - NEVER redefines trend. `classify_trend_asof` / `classify_vix_band_asof` /
    `RegimeCalendar` in regime_classifier.py are untouched by this module -- this produces
    DATA (daily OHLC bars), never a label. The regime-conditioned method was validated
    against the frozen classifier's OWN definition; nothing here re-derives that math.

Run: backtest/.venv/Scripts/python.exe setup/scripts/trend_cache_producer.py
  (also runs clean on system pythonw -- pure stdlib, no pandas, matching the hidden-launch
  chain install-first-live-day-review.ps1 / install-prereg-hygiene.ps1 use.)

Per CLAUDE.md OP-3 ($0, pure Python, reuses already-wired Alpaca creds -- no new vendor).
Guard: backtest/tests/test_trend_cache_producer_2026_09_03.py.
REVOKE: delete automation/state/trend-alignment-latest.json (readers fall back to the
frozen file automatically) and Unregister-ScheduledTask -TaskName Gamma_TrendCacheProducer.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time as _time_mod
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # repo root (this file: setup/scripts/)
for _p in (str(ROOT), str(ROOT / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from context_bundle_producer import _load_alpaca_creds  # noqa: E402 -- SAME cred loader, no new vendor
from et_clock import et_now  # noqa: E402

CACHE_DIR = ROOT / "analysis" / "backtests" / "cache"
POINTER_FILE = ROOT / "automation" / "state" / "trend-alignment-latest.json"

FROZEN_CACHE_FILE = CACHE_DIR / "trend-alignment-spy-daily-2024-07-01_2026-07-14.json"
FETCH_START = dt.date(2024, 7, 1)          # SAME start the frozen study cache used
OVERLAP_DAYS = 10                          # re-fetch a small tail overlap -- a prior run's
                                            # last day could have been a not-yet-final bar
FEED = "iex"


def _current_cache_path() -> Path:
    """Whatever regime_classifier.DAILY_SPY_CACHE would resolve to right now: the pointer's
    target if the pointer exists and its file is on disk, else the frozen artifact. Kept as
    a free function (not an import from regime_classifier) so this producer has zero
    dependency on the reader module -- one-way data flow only."""
    try:
        ptr = json.loads(POINTER_FILE.read_text(encoding="utf-8"))
        cand = ROOT / ptr["cache_path"]
        if cand.exists():
            return cand
    except (OSError, json.JSONDecodeError, KeyError):
        pass
    return FROZEN_CACHE_FILE


def _load_existing_bars(cache_path: Path | None = None) -> list[dict]:
    src = cache_path if cache_path is not None else _current_cache_path()
    if not src.exists():
        return []
    data = json.loads(src.read_text(encoding="utf-8"))
    return data.get("bars", [])


def _bar_date(bar: dict) -> dt.date:
    return dt.datetime.fromisoformat(bar["timestamp"].replace("Z", "+00:00")).date()


def fetch_daily_bars(start: dt.date, end: dt.date) -> tuple[list[dict], int]:
    """Paginated Alpaca REST daily-bar pull -- byte-identical request shape to
    trend_alignment_correlation_study.fetch_historical_bars (credential loader, URL
    format, feed/adjustment/sort). Raises on total failure (offline build step, fail
    LOUD -- this is a scheduled producer, not the live fail-open context-bundle path;
    a failed run simply leaves yesterday's cache + pointer in place, never a partial
    write -- see run())."""
    key, sec = _load_alpaca_creds()
    all_bars: list[dict] = []
    page_token = None
    start_s = start.strftime("%Y-%m-%dT00:00:00Z")
    end_s = (end + dt.timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
    n_pages = 0
    while True:
        url = (f"https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=1Day"
               f"&start={start_s}&end={end_s}&limit=10000&feed={FEED}&adjustment=raw&sort=asc")
        if page_token:
            url += f"&page_token={page_token}"
        req = urllib.request.Request(
            url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.loads(r.read())
        all_bars.extend(payload.get("bars", []))
        n_pages += 1
        page_token = payload.get("next_page_token")
        if not page_token:
            break
        _time_mod.sleep(0.2)  # polite pacing across pages, not a rate-limit workaround
    bars = [{"timestamp": b["t"], "open": b["o"], "high": b["h"], "low": b["l"],
             "close": b["c"], "volume": b["v"]} for b in all_bars]
    return bars, n_pages


def merge_bars(existing: list[dict], fetched: list[dict]) -> list[dict]:
    """Fetched bars win on any timestamp overlap (freshest data); every existing bar
    OUTSIDE the fetch window is preserved byte-for-byte -- extension is append-only from
    a reader's point of view. A trend label for a date already computable from `existing`
    never changes as a result of calling this."""
    by_ts = {b["timestamp"]: b for b in existing}
    for b in fetched:
        by_ts[b["timestamp"]] = b
    return sorted(by_ts.values(), key=lambda b: b["timestamp"])


def cache_path_for(end: dt.date) -> Path:
    return CACHE_DIR / f"trend-alignment-spy-daily-{FETCH_START.isoformat()}_{end.isoformat()}.json"


def _rel_or_abs(path: Path) -> str:
    """Path relative to ROOT when possible (the normal case); falls back to the absolute
    path when `path` lives outside ROOT (e.g. tests that monkeypatch CACHE_DIR to a
    tmp_path fixture) -- never raises."""
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def run(*, now_et: dt.datetime | None = None, existing_cache_path: Path | None = None,
        fetch_fn=fetch_daily_bars) -> dict:
    """Full extend-and-publish cycle. `existing_cache_path` / `fetch_fn` are injectable so
    tests can run this against a fixture cache + a stub fetch (no network, no live creds)."""
    now_et = now_et or et_now()
    today = now_et.date()

    existing_bars = _load_existing_bars(existing_cache_path)
    last_existing_date = max((_bar_date(b) for b in existing_bars), default=FETCH_START)
    fetch_from = max(last_existing_date - dt.timedelta(days=OVERLAP_DAYS), FETCH_START)

    fetched_bars, n_pages = fetch_fn(fetch_from, today)
    merged = merge_bars(existing_bars, fetched_bars)
    if not merged:
        raise RuntimeError("trend_cache_producer: merged bar list is empty -- refusing to write")

    end_date = max(_bar_date(b) for b in merged)
    out_path = cache_path_for(end_date)

    if out_path.resolve() == FROZEN_CACHE_FILE.resolve():
        raise RuntimeError(
            f"trend_cache_producer: computed output path {out_path} == the frozen cache file -- "
            "refusing to overwrite it. This should be structurally impossible (today is always "
            "after 2026-07-14) -- if it fires, something upstream is wrong; investigate before "
            "removing this guard.")

    payload = {
        "timeframe": "daily", "start": FETCH_START.isoformat(), "end": end_date.isoformat(),
        "n_bars": len(merged), "n_pages": n_pages,
        "fetched_at_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": ("setup/scripts/trend_cache_producer.py -- daily $0 append-only extension "
                   f"of the frozen {FROZEN_CACHE_FILE.name} build artifact (that file is never "
                   "overwritten by this script)."),
        "bars": merged,
    }
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp_path.replace(out_path)  # atomic on this filesystem -- never a partial cache file

    pointer = {
        "cache_path": _rel_or_abs(out_path),
        "start": FETCH_START.isoformat(), "end": end_date.isoformat(),
        "n_bars": len(merged), "updated_at_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
        "producer": "setup/scripts/trend_cache_producer.py",
        "frozen_source": _rel_or_abs(FROZEN_CACHE_FILE),
    }
    POINTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    ptr_tmp = POINTER_FILE.with_suffix(POINTER_FILE.suffix + ".tmp")
    ptr_tmp.write_text(json.dumps(pointer, indent=2), encoding="utf-8")
    ptr_tmp.replace(POINTER_FILE)

    return {"out_path": str(out_path), "end_date": end_date.isoformat(),
            "n_bars": len(merged), "n_bars_existing": len(existing_bars),
            "n_bars_fetched": len(fetched_bars), "n_pages": n_pages, "pointer": pointer}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--once", action="store_true",
                     help="single run (the only mode this script has)")
    ap.parse_args()
    result = run()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
