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
             OR more than one UNEXPLAINED interior gap (a real multi-day stall).
  * YELLOW : staleness 1-2 trading days, OR exactly one UNEXPLAINED interior gap.
  * GREEN  : latest snapshot == the most-recent expected trading day, no UNEXPLAINED gaps
             (a KNOWN, explained gap does not block GREEN -- see below).

``expect_today`` defaults False (the capture fires at 15:55 ET; before then today's
session is not yet "owed", so we never flag a missing today pre-close).

KNOWN_GAP vs SILENT_LOSS (2026-08-01)
--------------------------------------
An interior gap can be EXPLAINED: ``{archive_dir}/known-gaps.json`` (read by
``parse_known_gaps``, or injected via the ``known_gaps`` test seam) is a registry of
dates the accrual is known to have missed and WHY (e.g. a documented whole-machine
outage, or a producer blackout where the day's window has closed and both bankers'
current-day-only CDN sources make it permanently unfetchable). A date in that registry
is subtracted from ``interior_gaps`` (so it stops degrading the verdict) but is NEVER
added to ``days_accrued`` -- an explained absence is still an absence, not data. This is
what lets a RED caused by two long-explained historical gaps resolve back to GREEN/YELLOW
without silently pretending the missing days were captured, and keeps a genuinely NEW,
unexplained gap RED exactly as before (a known-gaps entry only suppresses the SPECIFIC
dates it names).
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Iterable, Optional

# Repo-anchored default archive dir (L21/L60); overridable for tests.
_REPO = Path(__file__).resolve().parents[2]
DEFAULT_ARCHIVE_DIR = _REPO / "journal" / "gex-archive"

# Matches both banker schemas: "2026-06-26.json" (Alpaca) and "2026-06-26-cboe.json" (CBOE).
_DATE_FILE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:-[a-z0-9]+)?\.json$", re.IGNORECASE)

# Explicit KNOWN_GAP registry (2026-08-01, C7 fix): {archive_dir}/known-gaps.json.
# Filename deliberately does NOT match _DATE_FILE_RE (no leading YYYY-MM-DD), so it is
# never mistaken for a captured snapshot / never counted toward days_accrued.
KNOWN_GAPS_FILENAME = "known-gaps.json"

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


def parse_known_gaps(archive_dir: Path) -> dict[dt.date, dict]:
    """Read ``{archive_dir}/known-gaps.json`` -- an explicit registry of trading days the
    accrual is KNOWN to have missed, and WHY, so the continuity verdict can distinguish an
    EXPLAINED absence (machine outage, producer blackout -- genuinely unfetchable after the
    fact because both bankers are current-day-only sources) from an unexplained SILENT_LOSS
    that still needs chasing (2026-08-01, C7 silent-failure class).

    Schema: ``{"YYYY-MM-DD": {"reason": str, ...}, ...}``. Fail-open, matching every other
    reader in this module: a missing file, garbled JSON, or a non-dict payload all return
    ``{}`` (never raises, never blocks the reporter). Malformed individual keys/values are
    skipped rather than failing the whole read.
    """
    path = archive_dir / KNOWN_GAPS_FILENAME
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- fail-open reporter, never raise
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[dt.date, dict] = {}
    for k, v in raw.items():
        try:
            d = dt.date.fromisoformat(str(k))
        except ValueError:
            continue
        out[d] = v if isinstance(v, dict) else {"reason": str(v)}
    return out


def assess_archive_continuity(
    archive_dir: Optional[Path] = None,
    as_of: Optional[dt.date] = None,
    *,
    expect_today: bool = False,
    max_stale_trading_days: int = MAX_STALE_TRADING_DAYS,
    present_dates: Optional[Iterable[dt.date]] = None,
    known_gaps: Optional[Iterable[dt.date]] = None,
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
    known_gaps:
        Explicit set of EXPLAINED-absence dates (test seam), e.g. a documented whole-machine
        outage or producer blackout where both bankers' current-day-only sources make the
        day permanently unfetchable. When given, ``archive_dir``'s ``known-gaps.json`` is not
        read. When omitted, read via ``parse_known_gaps(archive_dir)``. A known gap is
        EXCLUDED from ``interior_gaps`` (so it no longer degrades the verdict) but is NEVER
        counted toward ``days_accrued`` (an explained absence is still an absence, not data)
        -- this is what lets the checker distinguish KNOWN_GAP from SILENT_LOSS instead of
        just laundering the hole.

    Returns
    -------
    dict with: ``status`` (GREEN/YELLOW/RED), ``reason``, ``latest_session``,
    ``days_accrued``, ``most_recent_expected``, ``staleness_trading_days``,
    ``interior_gaps`` (list of ISO dates, UNEXPLAINED only), ``known_gaps`` (list of ISO
    dates excluded from ``interior_gaps`` because ``known-gaps.json`` explains them),
    ``expect_today``.
    """
    as_of = as_of or dt.date.today()
    archive_dir = archive_dir or DEFAULT_ARCHIVE_DIR

    dates = (sorted(set(present_dates)) if present_dates is not None
             else parse_archive_dates(archive_dir))
    known_gap_set = (set(known_gaps) if known_gaps is not None
                      else set(parse_known_gaps(archive_dir)))

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
                       interior_gaps=[], known_gaps=[])

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
    # Split into UNEXPLAINED (still degrade the verdict) vs KNOWN (explained by
    # known-gaps.json -- e.g. a documented outage on a current-day-only source that can
    # never be backfilled) -- a known gap is excluded from the severity math below but
    # reported separately so KNOWN_GAP stays visibly distinct from SILENT_LOSS.
    present_set = set(dates)
    interior_expected = [earliest] + _weekdays_between(earliest, latest)
    all_interior_gaps = [d for d in interior_expected
                         if d not in present_set and _is_weekday(d)]
    known_interior_gaps = [d for d in all_interior_gaps if d in known_gap_set]
    interior_gaps = [d for d in all_interior_gaps if d not in known_gap_set]
    interior_gaps_iso = [d.isoformat() for d in interior_gaps]
    known_gaps_iso = [d.isoformat() for d in known_interior_gaps]

    common = dict(
        most_recent_expected=most_recent_expected.isoformat(),
        staleness_trading_days=staleness,
        interior_gaps=interior_gaps_iso,
        known_gaps=known_gaps_iso,
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
    known_suffix = (f" ({len(known_interior_gaps)} known gap(s) {known_gaps_iso}, explained)"
                    if known_interior_gaps else "")
    return _result("GREEN",
                   f"accrual healthy: {len(dates)} sessions, latest {latest.isoformat()} "
                   f"== owed {most_recent_expected.isoformat()}, no unexplained gaps"
                   f"{known_suffix}", **common)


def main() -> int:
    """CLI: print the live verdict for the repo archive (fail-open, always exits 0)."""
    import json
    verdict = assess_archive_continuity()
    print(json.dumps(verdict, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
