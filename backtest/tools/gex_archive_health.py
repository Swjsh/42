"""GEX OI-archive continuity checker — fail-LOUD guard on the months-long accrual.

WHY THIS EXISTS (C7 silent-failure class; the 'class'-rung needle-mover)
------------------------------------------------------------------------
The dealer-GEX regime signal (``backtest/lib/engine/gex_regime.py``) is the standing
direction's 'class' rung — the one genuinely-unblocked path past the dead 0DTE-SPY
premium/range axes. Per ``gex_regime.assess_backtest_feasibility`` it can only become
BACKTESTABLE once a *historical full-chain OI+gamma snapshot archive* accrues (~60-90
trading days). Two daily bankers feed that archive into ``journal/gex-archive/``:

  * ``backtest/tools/cboe_oi_bank.py``  -> ``{date}-cboe.json``  (free CBOE CDN, native gamma)
  * ``automation/scripts/gex_capture.py`` -> ``{date}.json``      (Alpaca, BS gamma)

The whole investment is *calendar-time-gated*: it only pays off if a snapshot lands EVERY
trading day for months. If the ``Gamma_CboeOiBank`` task silently stalls (un-scheduled,
reaped, CBOE format change), we would not discover the gap-riddled, backtest-worthless
archive until months later — the exact silent-failure class (C7) the project bans.

This module turns "is the accrual still alive?" into a PURE, testable, fail-open verdict.
It is a REPORTER: it reads the archive directory listing and returns a structured
GREEN/YELLOW/RED dict. It performs NO network, NO clock read (caller passes ``as_of``),
NO mutation, and NEVER blocks anything live (rail-2 fail-open). It touches no params,
orders, doctrine, or heartbeat.

VERDICT RULES (holiday-robust by tolerance, not a holiday calendar)
-------------------------------------------------------------------
A "trading day" is modelled as a weekday (Mon-Fri). US market holidays are NOT enumerated
— a holiday simply shows up as a benign 1-day staleness or single interior gap, which the
tolerances below absorb as YELLOW (never a false RED on a holiday).

  * RED    : archive empty, OR staleness > ``max_stale_trading_days`` (default 2),
             OR more than one interior gap (a real multi-day stall).
  * YELLOW : staleness 1-2 trading days, OR exactly one interior gap (mild / holiday-ish).
  * GREEN  : latest snapshot == the most-recent expected trading day, no interior gaps.

``expect_today`` defaults False (the capture fires at 15:55 ET; before then today's
session is not yet "owed", so we never flag a missing today pre-close).
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Iterable, Optional

# Repo-anchored default archive dir (L21/L60); overridable for tests.
_REPO = Path(__file__).resolve().parents[2]
DEFAULT_ARCHIVE_DIR = _REPO / "journal" / "gex-archive"

# Matches both banker schemas: "2026-06-26.json" (Alpaca) and "2026-06-26-cboe.json" (CBOE).
_DATE_FILE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:-[a-z0-9]+)?\.json$", re.IGNORECASE)

# Default tolerances.
MAX_STALE_TRADING_DAYS = 2          # latest may lag the owed day by this many before RED.
MAX_INTERIOR_GAPS_FOR_YELLOW = 1    # one interior gap = YELLOW; more = RED (real stall).


def _is_weekday(d: dt.date) -> bool:
    return d.weekday() < 5  # Mon=0 .. Fri=4


def _prev_weekday(d: dt.date) -> dt.date:
    """The latest weekday strictly before ``d``."""
    cur = d - dt.timedelta(days=1)
    while not _is_weekday(cur):
        cur -= dt.timedelta(days=1)
    return cur


def _weekdays_between(lo: dt.date, hi: dt.date) -> list[dt.date]:
    """All weekdays in the half-open interval ``(lo, hi]`` (lo excluded, hi included)."""
    out: list[dt.date] = []
    cur = lo + dt.timedelta(days=1)
    while cur <= hi:
        if _is_weekday(cur):
            out.append(cur)
        cur += dt.timedelta(days=1)
    return out


def parse_archive_dates(archive_dir: Path) -> list[dt.date]:
    """Sorted, de-duplicated session dates present in the archive dir (both schemas).

    Returns ``[]`` if the directory is missing or holds no dated snapshots. A given
    session date counts once even if both the ``{date}.json`` and ``{date}-cboe.json``
    snapshots are present (we care about *coverage*, not which banker filled it).
    """
    if not archive_dir.exists() or not archive_dir.is_dir():
        return []
    dates: set[dt.date] = set()
    for f in archive_dir.iterdir():
        if not f.is_file():
            continue
        m = _DATE_FILE_RE.match(f.name)
        if not m:
            continue
        try:
            dates.add(dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            continue
    return sorted(dates)


def assess_archive_continuity(
    archive_dir: Optional[Path] = None,
    as_of: Optional[dt.date] = None,
    *,
    expect_today: bool = False,
    max_stale_trading_days: int = MAX_STALE_TRADING_DAYS,
    present_dates: Optional[Iterable[dt.date]] = None,
) -> dict:
    """Pure continuity verdict for the GEX OI archive. Never raises, never mutates.

    Parameters
    ----------
    archive_dir:
        Directory of ``{date}[-source].json`` snapshots. Defaults to the repo archive.
        Ignored when ``present_dates`` is supplied (the testable injection seam).
    as_of:
        The date to evaluate freshness against. Defaults to ``dt.date.today()``.
    expect_today:
        If True and ``as_of`` is a weekday, today's snapshot is considered owed (use
        only after the 15:55 ET capture window). Default False — never flag a missing
        today before its capture has had a chance to fire.
    max_stale_trading_days:
        How many trading days the latest snapshot may lag the most-recent owed day
        before the verdict is RED. 1-2 is YELLOW.
    present_dates:
        Explicit set of session dates (test seam). When given, ``archive_dir`` is not read.

    Returns
    -------
    dict with: ``status`` (GREEN/YELLOW/RED), ``reason``, ``latest_session``,
    ``days_accrued``, ``most_recent_expected``, ``staleness_trading_days``,
    ``interior_gaps`` (list of ISO dates), ``expect_today``.
    """
    as_of = as_of or dt.date.today()
    archive_dir = archive_dir or DEFAULT_ARCHIVE_DIR

    dates = (sorted(set(present_dates)) if present_dates is not None
             else parse_archive_dates(archive_dir))

    def _result(status: str, reason: str, **extra) -> dict:
        base = {
            "status": status,
            "reason": reason,
            "latest_session": dates[-1].isoformat() if dates else None,
            "days_accrued": len(dates),
            "as_of": as_of.isoformat(),
            "expect_today": expect_today,
        }
        base.update(extra)
        return base

    if not dates:
        return _result("RED", "no GEX OI snapshots in archive — accrual not running",
                       most_recent_expected=None, staleness_trading_days=None,
                       interior_gaps=[])

    latest = dates[-1]
    earliest = dates[0]

    # The most-recent trading day a snapshot is owed for:
    #   * today, if it is a weekday AND expect_today (after the 15:55 ET capture);
    #   * else the last weekday strictly before today (weekday as_of);
    #   * else (weekend as_of) the most recent weekday <= as_of (i.e. Friday).
    if expect_today and _is_weekday(as_of):
        most_recent_expected = as_of
    elif _is_weekday(as_of):
        most_recent_expected = _prev_weekday(as_of)
    else:
        # weekend: owed day is the most recent weekday <= as_of (i.e. Friday)
        cur = as_of
        while not _is_weekday(cur):
            cur -= dt.timedelta(days=1)
        most_recent_expected = cur

    # Staleness: trading days the latest snapshot lags the owed day (0 if caught up/ahead).
    if latest >= most_recent_expected:
        staleness = 0
    else:
        staleness = len(_weekdays_between(latest, most_recent_expected))

    # Interior gaps: weekdays inside [earliest, latest] with no snapshot (the stall signal).
    present_set = set(dates)
    interior_expected = [earliest] + _weekdays_between(earliest, latest)
    interior_gaps = [d for d in interior_expected
                     if d not in present_set and _is_weekday(d)]
    interior_gaps_iso = [d.isoformat() for d in interior_gaps]

    common = dict(
        most_recent_expected=most_recent_expected.isoformat(),
        staleness_trading_days=staleness,
        interior_gaps=interior_gaps_iso,
    )

    if staleness > max_stale_trading_days:
        return _result("RED",
                       f"archive stale: latest {latest.isoformat()} lags owed "
                       f"{most_recent_expected.isoformat()} by {staleness} trading days "
                       f"(> {max_stale_trading_days}) — accrual likely stalled", **common)
    if len(interior_gaps) > MAX_INTERIOR_GAPS_FOR_YELLOW:
        return _result("RED",
                       f"{len(interior_gaps)} interior trading-day gaps "
                       f"{interior_gaps_iso} — accrual dropped multiple days", **common)
    if staleness >= 1 or len(interior_gaps) == 1:
        bits = []
        if staleness >= 1:
            bits.append(f"{staleness} trading day(s) stale")
        if len(interior_gaps) == 1:
            bits.append(f"1 interior gap {interior_gaps_iso}")
        return _result("YELLOW", "; ".join(bits) + " — watch the accrual", **common)
    return _result("GREEN",
                   f"accrual healthy: {len(dates)} sessions, latest {latest.isoformat()} "
                   f"== owed {most_recent_expected.isoformat()}, no gaps", **common)


def main() -> int:
    """CLI: print the live verdict for the repo archive (fail-open, always exits 0)."""
    import json
    verdict = assess_archive_continuity()
    print(json.dumps(verdict, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
