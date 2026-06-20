"""Guard: never `tz_localize("UTC")` a naive `entry_time_et` (the L161 foot-gun).

Graduates L161 (markdown/doctrine/LESSONS-LEARNED.md, 2026-06-18; OP-25 C7). TradeFill
`.entry_time_et` is a NAIVE ET timestamp (option-CSV convention). To look it up
against UTC-indexed bar data (ribbon / VIX / SPY 5m) you must FIRST declare the
real zone then convert:

    entry_ts = pd.Timestamp(t.entry_time_et)
    if entry_ts.tzinfo is None:
        entry_ts = entry_ts.tz_localize("America/New_York").tz_convert("UTC")

`tz_localize("UTC")` on the naive value mislabels "15:40 ET" as "15:40 UTC"
(= 10:40 ET), a ~5h shift that silently hits a PREMARKET bar instead of the real
RTH entry bar. In the original incident this flipped an A/B verdict to a false
RATIFY (the gate looked like it blocked 11 bad trades; with correct TZ it removed
2 IS winners and was REJECTED). A wrong-TZ lookup ships a gate that destroys edge.

Two layers of teeth:

  test_no_entry_time_et_localized_as_utc -- STATIC scan of backtest research
      scripts. Any function that localizes a `pd.Timestamp(... entry_time_et ...)`
      as "UTC" in the naive branch FAILS. This is the exact bug pattern; it caught
      a live recurrence in safe_trendline_spread_gate.py (fixed alongside this
      guard). Note: bare `tz_localize("UTC")` on VIX/SPY *data* columns is
      LEGITIMATE (that data is genuinely naive-UTC) -- this guard fires ONLY on the
      entry_time_et combination, so it won't false-positive on data localization.

  test_localize_math_matches_rth_bar -- BEHAVIORAL proof of why it matters: the
      broken form lands on a premarket-hour clock; the correct form preserves the
      RTH wall-clock. Pins the timezone arithmetic itself, independent of any file.

Regression caught: a new (or reverted) A/B / gate-sweep script that converts
entry_time_et to UTC via tz_localize("UTC") -> static test fails, naming file+line.

Run:  cd backtest && python -m pytest tests/test_tz_localize_entry_time.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"

# Directories of research / A-B / analysis scripts that consume entry_time_et.
SCAN_DIRS = [BACKTEST, BACKTEST / "autoresearch"]

# A line that takes a Timestamp from entry_time_et, OR a recent `entry_ts`/`ts`
# derived from it, and localizes it to UTC. We approximate "derived from
# entry_time_et" by scanning each .py file that mentions entry_time_et and, within
# it, flagging any tz_localize("UTC") / tz_localize('UTC') that is applied to a
# bare Timestamp variable (NOT a DataFrame column access like vix[...].dt or
# .dt.tz_localize, which are data-localization and legitimate).
_LOCALIZE_UTC = re.compile(r"""\.tz_localize\(\s*["']UTC["']\s*\)""")
# A ".dt.tz_localize(" prefix means it's a pandas Series/column (data), not a
# scalar entry-time Timestamp -> legitimate, skip.
_IS_SERIES_DT = re.compile(r"""\.dt\.tz_localize\(\s*["']UTC["']\s*\)""")


def _iter_py_files():
    seen = set()
    for d in SCAN_DIRS:
        if not d.exists():
            continue
        for p in sorted(d.glob("*.py")):
            if p in seen:
                continue
            seen.add(p)
            yield p


def test_no_entry_time_et_localized_as_utc() -> None:
    """No scalar entry_time_et timestamp may be localized to UTC (must be ET->UTC)."""
    offenders: list[str] = []
    for path in _iter_py_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if "entry_time_et" not in text:
            continue  # file doesn't deal with entry times at all
        for i, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not _LOCALIZE_UTC.search(stripped):
                continue
            if _IS_SERIES_DT.search(stripped):
                continue  # ".dt.tz_localize('UTC')" == data column, legitimate
            if stripped.startswith("#"):
                continue  # a comment / docstring warning ABOUT the bug is fine
            # A bare `<scalar>.tz_localize("UTC")` inside a file that handles
            # entry_time_et is the L161 signature.
            offenders.append(f"{path.relative_to(REPO)}:{i}: {stripped}")

    assert not offenders, (
        "L161 GUARD: a naive entry_time_et timestamp is being localized to UTC. "
        "That mislabels ET as UTC (~5h shift -> premarket bar) and silently "
        "corrupts ribbon/VIX/SPY lookups. Use "
        '`.tz_localize("America/New_York").tz_convert("UTC")` instead.\n  '
        + "\n  ".join(offenders)
    )


def test_localize_math_matches_rth_bar() -> None:
    """Behavioral proof: the correct conversion preserves the RTH wall-clock; the
    broken one shifts a 15:40 ET entry to a 10:40 ET (premarket-adjacent) clock."""
    naive = pd.Timestamp("2025-02-18 15:40:00")  # 3:40pm ET entry (RTH)
    assert naive.tzinfo is None

    correct = naive.tz_localize("America/New_York").tz_convert("UTC")
    broken = naive.tz_localize("UTC")

    # Round-tripped back to ET, the CORRECT path still reads 15:40 ET.
    assert correct.tz_convert("America/New_York").strftime("%H:%M") == "15:40"
    # The BROKEN path, interpreted as ET, reads 10:40 -- a different (earlier) bar.
    assert broken.tz_convert("America/New_York").strftime("%H:%M") == "10:40"
    # And the two UTC instants differ by the EST offset (5h) -- never equal.
    assert correct != broken
    assert abs((correct - broken).total_seconds()) == 5 * 3600


def test_clock_time_path_uses_localize_none() -> None:
    """Sanity: for time-of-day (.time()) comparisons, tz_localize(None) is the
    correct idiom on a naive entry_time_et (no UTC conversion needed). This pins
    the *other* half of L161 so a future 'fix' doesn't wrongly UTC-convert the
    clock-time path too."""
    naive = pd.Timestamp("2025-02-18 15:40:00")
    # tz_localize(None) on an already-naive ts is a no-op clock; .time() is 15:40.
    assert naive.tz_localize(None).time() == pd.Timestamp("2025-02-18 15:40").time()
