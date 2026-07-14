"""futures_shadow_progress.py -- the FUTURES-MIRROR-SHADOW arming-bar tracker (2026-07-14, J
directive "make sure you trade futures today too" -> automation/overnight/queue.md
FUTURES-MIRROR-SHADOW item #5 "the arming bar tracker").

WHY THIS EXISTS: futures_mirror_shadow.py accumulates round-trip evidence into
mirror-would-be.jsonl but deliberately does NOT compute the arming bar itself (its own
ARMING_BAR_DOC says "evaluated by a LATER session, not this one"). This is that later
session's instrument, made a STANDING one instead of a one-off: reads mirror-would-be.jsonl,
counts CLOSED round trips, sums realized P&L, and -- once (and only once) the >=20 round-trip
floor is met -- computes whether the mirror beats a same-horizon ES=F buy-and-hold null.
Writes automation/state/futures/shadow-progress.json. READ-ONLY on the would-be ledger; places
no order, touches no broker, arms nothing (arming is a documented separate J/doctrine step
per queue.md, not automated by this file).

ARMING BAR (verbatim from futures_mirror_shadow.ARMING_BAR_DOC, reproduced here so this file
is self-contained): >=20 CLOSED v2 mirror round-trips (a signal_ref's LAST qty-zeroing
tp1/stopped/time_flat row -- counted per signal_ref, not per row), positive expectancy (sum of
pnl_usd_mes across the CURRENT spec's rows), AND beats a same-horizon ES=F buy-and-hold null.

NULL METHODOLOGY (disclosed limitation, task instruction "compute the null when n>=20, not
before" honored literally -- both the RESULT and the yfinance fetch itself are gated on the
floor, so this script makes zero network calls below 20 round trips): the null re-prices each
closed round trip's OWN entry (same price/timestamp/direction as the real mirror trade) held
UNMANAGED (no stop/target) flat to the SAME 2-session 15:55 ET deadline used by the real trade
-- matches futures_mirror_shadow.ARMING_BAR_DOC's null definition verbatim. The deadline is
NOT stored in mirror-would-be.jsonl rows (schema has no deadline_et field) -- it is instead
RECOMPUTED deterministically from the trade's own entry timestamp via
futures_mirror_shadow.next_trading_day() (reused, not reinvented; a pure function of the entry
date, so it reproduces open_mirror_position()'s original deadline exactly). Because yfinance
1-minute ES=F history only covers a 7-day trailing window (no arbitrary-past-date minute bars
without a paid data source), the null is only computable for round trips whose deadline falls
within that live window; round trips older than that report null_unavailable for that trip
(never a fabricated price) and are excluded from the null aggregate, with coverage disclosed
(e.g. "18/20 round trips" in the written JSON's null_check.coverage).

IDEMPOTENT: pure function of mirror-would-be.jsonl's current content (append-only) plus a
live-quote fetch used ONLY for the null once n>=20 -- calling this once at 16:00 vs. every 5
min all day produces the identical n_round_trips/total_pnl_usd (the null figure can differ
poll-to-poll only in its yfinance-window coverage, which only ever WIDENS forward in time,
never regresses). Called from futures_mirror_shadow.run_once()'s tail (fail-open) so it is
always current without its own scheduled task.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Callable, Optional

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest", "setup/scripts"):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

import futures_mirror_shadow as fms  # noqa: E402

NULL_MIN_ROUND_TRIPS = 20   # task instruction: "compute the null when n>=20, not before"
PROGRESS_DOC = (
    "FUTURES-MIRROR-SHADOW arming-bar progress (setup/scripts/futures_shadow_progress.py). "
    "Bar: >=20 closed round trips (n_round_trips), positive_expectancy (total_pnl_usd > 0), "
    "AND beats_null (same-horizon ES=F buy-and-hold, computed only once n_round_trips>=20 -- "
    "see module docstring NULL METHODOLOGY for the 7-day yfinance-window coverage caveat). "
    "armable=true only when all three hold. Read-only on mirror-would-be.jsonl; places no "
    "order, arms nothing."
)


def _progress_file() -> Path:
    """Resolved at CALL time against fms.STATE_DIR (not a module-level constant) so a test's
    monkeypatch of fms.STATE_DIR is honored -- mirrors futures_mirror_shadow._et_now()'s own
    lazy-resolution rationale."""
    return fms.STATE_DIR / "shadow-progress.json"


def _atomic_write_json(path: Path, data: dict) -> None:
    """Temp file + os.replace -- atomic on both Windows and POSIX (matches the per-file-owned
    copy convention every script in this repo uses; see fill_sim_broker.py /
    futures_mirror_shadow.py, neither of which share this helper as a common import)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


# ── ledger read ──────────────────────────────────────────────────────────────
def load_would_be_rows(path: Optional[Path] = None) -> list[dict]:
    """Fail-open: a missing/corrupt file degrades to []. Skips the `_doc` header line and any
    malformed JSON line (never raises on a partially-written line mid-append)."""
    p = path if path is not None else fms.WOULD_BE_FILE
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows = []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if "_doc" in row:
            continue
        rows.append(row)
    return rows


# ── round-trip aggregation ──────────────────────────────────────────────────
def group_by_signal(rows: list[dict]) -> dict:
    """PURE. Groups lifecycle rows by signal_ref, sorted by ts_et within each group. Rows
    without a signal_ref (shouldn't occur in a well-formed ledger) are silently dropped."""
    groups: dict = {}
    for r in rows:
        ref = r.get("signal_ref")
        if not ref:
            continue
        groups.setdefault(ref, []).append(r)
    for ref in groups:
        groups[ref].sort(key=lambda r: r.get("ts_et", ""))
    return groups


def compute_round_trips(rows: list[dict]) -> list[dict]:
    """PURE. One entry per signal_ref that has FULLY closed -- per
    futures_mirror_shadow.ARMING_BAR_DOC's own counting rule verbatim: 'tp1/stopped/time_flat
    rows that bring a signal_ref's qty_open_after to 0, counted per signal_ref not per row'.
    total_pnl_usd sums pnl_usd_mes across EVERY row for that signal_ref (captures a partial
    TP1 leg plus the final leg). Open/still-pending signal_refs are excluded (not yet a round
    trip) -- this is why n_round_trips can legitimately be 0 while positions_open > 0 in
    futures_mirror_shadow's own summary."""
    trips = []
    for ref, events in group_by_signal(rows).items():
        closing = [e for e in events
                  if e.get("event") in (fms.EV_TP1, fms.EV_STOPPED, fms.EV_TIME_FLAT)
                  and e.get("qty_open_after") == 0]
        if not closing:
            continue
        last_close = closing[-1]
        total_pnl = round(sum(float(e.get("pnl_usd_mes") or 0.0) for e in events), 2)
        entry_row = next((e for e in events if e.get("event") == fms.EV_FILLED), events[0])
        trips.append({
            "signal_ref": ref, "direction": entry_row.get("direction"),
            "entry": entry_row.get("entry"), "entry_ts_et": entry_row.get("ts_et"),
            "total_pnl_usd": total_pnl, "closed_at_et": last_close.get("ts_et"),
            "close_reason": last_close.get("reason"),
            "setup_name": entry_row.get("setup_name"),
            "source_arms": entry_row.get("source_arms"),
        })
    trips.sort(key=lambda t: t.get("closed_at_et") or "")
    return trips


# ── buy-and-hold null (gated on n>=20, see module docstring) ────────────────
def compute_buyhold_null(trip: dict, bar_lookup: Callable[[dt.datetime], Optional[float]], *,
                         entry_qty: int) -> Optional[float]:
    """PURE given `bar_lookup` (a ts -> Optional[price] closure -- production default is a
    cached 7-day 1m ES=F fetch, see `_default_bar_lookup_factory`; tests inject a fixture
    dict-backed closure). Re-prices the SAME entry (price/timestamp/direction) held UNMANAGED
    flat to the SAME 2-session deadline the real mirror trade used (deadline recomputed via
    fms.next_trading_day -- see module docstring). Returns None (never a fabricated number) if
    the deadline price can't be looked up."""
    entry_ts = fms._parse_ts_et(trip.get("entry_ts_et"))
    if entry_ts is None or trip.get("entry") is None or trip.get("direction") is None:
        return None
    deadline = dt.datetime.combine(fms.next_trading_day(entry_ts.date()), fms.DEADLINE_TIME_ET)
    exit_price = bar_lookup(deadline)
    if exit_price is None:
        return None
    from futures.instruments import MES  # noqa: PLC0415 -- lazy, matches futures_mirror_shadow.py
    entry = float(trip["entry"])
    long = trip["direction"] == "long"
    pts = (exit_price - entry) if long else (entry - exit_price)
    return round(pts * MES.point_value * entry_qty - MES.round_turn_usd * entry_qty, 2)


def _default_bar_lookup_factory() -> Callable[[dt.datetime], Optional[float]]:
    """Fetches 7d of 1-min ES=F bars ONCE (fail-open -> a closure that always returns None on
    any failure) and returns a bar_lookup(ts) closure over that snapshot -- avoids re-fetching
    per round trip. yfinance's hard 7-day window for 1m bars is this function's ceiling; a
    deadline older than that (or not yet reached) returns None from every call, never a
    fabricated price -- see module docstring NULL METHODOLOGY."""
    try:
        import yfinance as yf  # noqa: PLC0415
        df = yf.download("ES=F", period="7d", interval="1m", auto_adjust=False,
                         progress=False, prepost=True)
        if df is None or df.empty:
            return lambda ts: None
        if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)
        idx = df.index
        try:
            idx_et = idx.tz_convert("America/New_York").tz_localize(None)
        except (TypeError, AttributeError):
            idx_et = idx
        bars = sorted(zip(idx_et.to_pydatetime(), df["Close"].astype(float).tolist()))
    except Exception:  # noqa: BLE001
        return lambda ts: None

    def _lookup(target: dt.datetime) -> Optional[float]:
        for ts, close in bars:
            if ts >= target:
                return float(close)
        return None  # target is beyond every fetched bar (deadline hasn't happened yet, or the
                     # round trip is older than the 7d window)
    return _lookup


# ── top-level progress computation ──────────────────────────────────────────
def compute_progress(rows: list[dict], *, bar_lookup: Optional[Callable] = None,
                     now_et: Optional[dt.datetime] = None) -> dict:
    """PURE given `rows`/`bar_lookup`/`now_et` (all injectable -- see module docstring
    IDEMPOTENT). Never raises; a missing bar_lookup with n>=20 degrades null_check to
    evaluated=False with an honest reason, never a fabricated beats_null."""
    if now_et is None:
        now_et = fms._et_now()
    trips = compute_round_trips(rows)
    n = len(trips)
    total_pnl = round(sum(t["total_pnl_usd"] for t in trips), 2)
    avg_pnl = round(total_pnl / n, 2) if n else None
    positive_expectancy = bool(n > 0 and total_pnl > 0)

    beats_null: Optional[bool] = None
    if n < NULL_MIN_ROUND_TRIPS:
        null_check = {"evaluated": False,
                     "reason": f"n_round_trips {n} < {NULL_MIN_ROUND_TRIPS} (not computed yet)"}
    elif bar_lookup is None:
        null_check = {"evaluated": False, "reason": "no bar_lookup supplied"}
    else:
        null_pnls, unavailable = [], 0
        for t in trips:
            np_ = compute_buyhold_null(t, bar_lookup, entry_qty=fms.ENTRY_QTY)
            if np_ is None:
                unavailable += 1
            else:
                null_pnls.append(np_)
        if null_pnls:
            null_total = round(sum(null_pnls), 2)
            beats_null = bool(total_pnl > null_total)
            null_check = {"evaluated": True, "null_total_pnl_usd": null_total,
                          "coverage": f"{len(null_pnls)}/{n}", "unavailable": unavailable}
        else:
            null_check = {"evaluated": False,
                         "reason": f"null unavailable for all {n} round trips "
                                   "(every deadline outside the 7d yfinance window)"}

    armable = bool(n >= NULL_MIN_ROUND_TRIPS and positive_expectancy and beats_null is True)
    return {
        "_doc": PROGRESS_DOC,
        "updated_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
        "spec_version": fms.SPEC_VERSION,
        "n_round_trips": n,
        "total_pnl_usd": total_pnl,
        "avg_pnl_usd_per_trip": avg_pnl,
        "positive_expectancy": positive_expectancy,
        "null_check": null_check,
        "arming_bar": {
            "round_trips_needed": NULL_MIN_ROUND_TRIPS, "round_trips_have": n,
            "expectancy_positive": positive_expectancy, "beats_null": beats_null,
            "armable": armable,
        },
    }


def write_progress(progress: dict, path: Optional[Path] = None) -> Path:
    p = path if path is not None else _progress_file()
    _atomic_write_json(p, progress)
    return p


def main() -> int:
    """Fail-open CLI: always returns 0, every exception logged via fms._log (reused) and
    swallowed. Makes a network call ONLY when n_round_trips has already reached the 20-trip
    floor (see module docstring) -- cheap on every other poll."""
    try:
        rows = load_would_be_rows()
        n = len(compute_round_trips(rows))
        bar_lookup = _default_bar_lookup_factory() if n >= NULL_MIN_ROUND_TRIPS else None
        progress = compute_progress(rows, bar_lookup=bar_lookup)
        out_path = write_progress(progress)
        fms._log(f"[shadow_progress] wrote {out_path}: "
                 f"n_round_trips={progress['n_round_trips']} "
                 f"total_pnl_usd={progress['total_pnl_usd']} "
                 f"armable={progress['arming_bar']['armable']}")
        print(f"[futures_shadow_progress] {json.dumps(progress, default=str)}")
        return 0
    except Exception as e:  # noqa: BLE001
        try:
            fms._log(f"[shadow_progress] main() FAILED (fail-open): {type(e).__name__}: {e}")
        except Exception:  # noqa: BLE001
            pass
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
