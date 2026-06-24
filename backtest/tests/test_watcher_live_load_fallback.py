"""Guard for the watcher_live load-data fallback (C7 silent-failure, 2026-06-23).

ROOT CAUSE: `watcher_live.main()` wrapped `ar_runner.load_data` in a NARROW
`except FileNotFoundError`. FileNotFoundError is only raised when no CSV covers
the window (the routine morning case). But `load_data` also calls `pd.read_csv`
+ `_dedupe_by_timestamp` on a MATCHING file -- a corrupt / truncated / empty
rolling CSV (a half-finished daily-append) raises `pd.errors.ParserError` /
`EmptyDataError` / `KeyError` instead. Those escaped the narrow except,
propagated out of main(), and crashed the producer with ZERO diag rows -- an
invisible TOTAL-DARKNESS day (matches 2026-06-23: NumberOfMissedRuns=0, no obs,
no diag). Every other early-return in main() writes a diag; this path defeated
that observability.

These tests pin `_load_with_fallback` so that ANY load failure degrades to the
history-only path AND writes a diag (never crashes silently). A revert to a
narrow `except FileNotFoundError` fails loud here.
"""
import datetime as dt

import pandas as pd
import pytest

from autoresearch.watcher_live import _load_with_fallback

_LOOKBACK = dt.date(2026, 6, 16)
_TODAY = dt.date(2026, 6, 23)
_NOW = dt.datetime(2026, 6, 23, 9, 35)


def _fallback_df():
    """A non-empty history-only frame, as _load_history_only_fallback would return."""
    spy = pd.DataFrame({
        "timestamp_et": ["2026-06-20 15:55:00"],
        "open": [743.0], "high": [743.5], "low": [742.8], "close": [743.2],
        "volume": [100000],
    })
    vix = pd.DataFrame(columns=["timestamp_et", "open", "high", "low", "close", "volume"])
    return spy, vix


class _DiagCollector:
    def __init__(self):
        self.rows = []

    def __call__(self, reason, bar_ts="", now=None, extra=None):
        self.rows.append({"reason": reason, "extra": extra or {}})


def test_success_path_no_fallback_no_diag():
    spy_in, vix_in = _fallback_df()

    def load_ok(_s, _e):
        return spy_in, vix_in

    diag = _DiagCollector()
    spy, vix, used = _load_with_fallback(load_ok, _fallback_df, _LOOKBACK, _TODAY, _NOW, diag)
    assert used is False
    assert diag.rows == []  # success writes NO diag
    assert len(spy) == 1


def test_file_not_found_is_routine_fallback():
    def load_missing(_s, _e):
        raise FileNotFoundError("no SPY/VIX csv found covering ...")

    diag = _DiagCollector()
    spy, vix, used = _load_with_fallback(load_missing, _fallback_df, _LOOKBACK, _TODAY, _NOW, diag)
    assert used is True
    assert len(diag.rows) == 1
    assert diag.rows[0]["reason"] == "load_data_fallback_history_only"
    assert not spy.empty  # fallback frame returned, producer keeps going


@pytest.mark.parametrize("exc", [
    pd.errors.ParserError("bad CSV token"),
    pd.errors.EmptyDataError("No columns to parse from file"),
    KeyError("timestamp_et"),
    ValueError("could not convert string to float"),
    UnicodeDecodeError("utf-8", b"", 0, 1, "invalid start byte"),
])
def test_corrupt_csv_does_not_crash_and_writes_loud_diag(exc):
    """The 2026-06-23 total-darkness class: a non-FileNotFoundError from load_data
    must degrade to the fallback AND write an alarming diag -- never crash."""
    def load_corrupt(_s, _e):
        raise exc

    diag = _DiagCollector()
    # Must NOT raise.
    spy, vix, used = _load_with_fallback(load_corrupt, _fallback_df, _LOOKBACK, _TODAY, _NOW, diag)
    assert used is True
    assert len(diag.rows) == 1
    reason = diag.rows[0]["reason"]
    assert reason.startswith("load_data_unexpected_error:")
    assert type(exc).__name__ in reason  # exc type surfaced for triage
    assert not spy.empty  # producer continues on the history-only frame


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
