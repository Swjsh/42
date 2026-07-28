"""Guard tests for exit_leak_decompose's pure helpers.

Pins the entry-bar convention (entry+1 STRICT, per markdown/audits/
ENTRY-BAR-CONVENTION-RULING-2026-07-25.md) into the MFE window: a bar AT the entry
timestamp must be EXCLUDED, the exit bar INCLUDED, MFE_open reads OPENs (the point-sample
series the real exit core observes) and MFE_high reads HIGHs. REDs if anyone relaxes the
window to include the entry bar (look-ahead, C6) or silently switches MFE to closes/highs.
"""
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from exit_leak_decompose import exit_family, mfe_window  # noqa: E402


def _bars():
    base = dt.datetime(2026, 7, 17, 13, 0)
    rows = []
    # opens: 1.00 (entry bar), 1.10, 1.50, 1.30, 2.00(after exit)  highs: open+0.25
    for i, o in enumerate([1.00, 1.10, 1.50, 1.30, 2.00]):
        rows.append({"timestamp_et": base + dt.timedelta(minutes=5 * i),
                     "open": o, "high": o + 0.25, "low": o - 0.05, "close": o + 0.10})
    return pd.DataFrame(rows), base


def test_entry_bar_excluded_exit_bar_included():
    df, base = _bars()
    entry_ts = base                                # bar 0 must be EXCLUDED (entry+1 strict)
    exit_ts = base + dt.timedelta(minutes=15)      # bar 3 is the exit bar, INCLUDED
    m = mfe_window(df, entry_ts, exit_ts)
    assert m is not None
    assert m["n_bars"] == 3                        # bars 1,2,3 only
    assert m["mfe_open"] == 1.50                   # bar 2's open; bar 4 (2.00) is after exit
    assert m["mfe_high"] == 1.75                   # bar 2's high (1.50+0.25)
    assert m["mfe_open_ts"] == base + dt.timedelta(minutes=10)


def test_empty_window_returns_none():
    df, base = _bars()
    last_ts = base + dt.timedelta(minutes=20)
    assert mfe_window(df, last_ts, last_ts + dt.timedelta(minutes=5)) is None


def test_mfe_uses_opens_not_closes():
    df, base = _bars()
    # closes are open+0.10 -- if MFE read closes, bar2 would give 1.60 not 1.50
    m = mfe_window(df, base, base + dt.timedelta(minutes=15))
    assert m["mfe_open"] == 1.50


def test_exit_family_mapping():
    # premium_stop reason splits on the trade's RESOLVED stop mode:
    # premium mode -> the -20% floor; structure mode -> the -50% catastrophe cap.
    assert exit_family("premium_stop @ 0.8", "premium") == "PREMIUM_STOP_20"
    assert exit_family("premium_stop @ 0.5", "structure") == "CATASTROPHE_50"
    assert exit_family("runner_stop @ 2.21", "premium") == "RUNNER_TRAIL"
    assert exit_family("structure_stop @ 744.9", "structure") == "STRUCTURE_STOP"
    assert exit_family("ribbon_flip_back", "premium") == "RIBBON_FLIP"
    assert exit_family("time_stop_15:50 (runner)", "structure") == "TIME_STOP"
