"""guard_test.py -- guard for the engine-view-readout-ws-a package (WS-A, "draw what you
trade" engine-view readout). HELD until 2026-10-30 per Opus's ruling -- this package's
change.patch touches `backtest/lib/filters.py` and `setup/scripts/heartbeat_core.py`, both
on `setup/hooks/doctrine.py::FROZEN_TRADING_PATH`, and is additive instrumentation (not a
pre-registered kill-type risk reduction), so it is NOT eligible for the 2026-09-29
GAMMA_FREEZE_OVERRIDE checkpoint. See README.md.

Packet row: engine-view-readout-ws-a.

HEADLINE GUARD: `detect_trendline_rejection_bearish` gets a new keyword-only `trace`
parameter (backtest/lib/filters.py:758 pre-patch / :791 post-patch, since the new
`_trace_pivot_timestamps_et` helper is inserted above it). The contract is zero-behavior-
change: calling with `trace=None` (the historical call shape, still used by every existing
call site) must be byte-identical to calling with `trace={}` -- same return value on every
bar, for both "fired" and "no-fire" bars. This is verified over the FULL (not RTH-sliced)
real-bar corpus `backtest/data/spy_5m_2026-05-19_2026-09-08.csv` (11,348 rows; the function
needs `TRENDLINE_LOOKBACK_BARS + 2 = 62` bars of history before the first index it will
score, so 11,348 - 62 = 11,286 bars are compared).

WHY-THIS-FILE-CAN'T-RUN-GREEN-YET: the patch is HELD, not applied (OP-0's four
J-first items include none of "ship an additive instrumentation change mid-freeze";
DOCTRINE-HOOKS.md's freeze rationale is that ANY trading-path edit -- even a provably
return-identical one -- silently invalidates go_live_gate.py's 20-day score, because the
window's value is that nothing on the path moved). Importing `lib.filters` from the real
repo (the default below) therefore hits the UNPATCHED file, which has no `trace` kwarg --
calling with `trace={}` raises `TypeError`, and this file reports that failure honestly
rather than lying about coverage. This is the expected/correct RED state while the freeze
holds. `WS_A_FILTERS_LIB_DIR` exists ONLY so an author can re-verify the same assertions
against a scratch (never-committed, never-applied-to-repo) copy of the patched file without
ever writing to a FROZEN_TRADING_PATH file -- see README.md's RED-proof section for exactly
how that was used to produce this package's verified numbers.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]

# Verification escape hatch ONLY (never used by apply.ps1, never points at a FROZEN file
# under this env var's default). Defaults to the real repo's backtest/lib -- the path this
# guard runs against once change.patch is actually applied there.
FILTERS_LIB_DIR = Path(os.environ.get("WS_A_FILTERS_LIB_DIR", str(REPO / "backtest")))

CORPUS_CSV = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-09-08.csv"

# Exit reasons actually measured over the real-bar corpus (see README.md). `slope_not_negative`
# is a documented-but-mathematically-unreachable branch (pivot selection is "max of a
# shrinking subset", so OLS slope can never come out non-negative; a would-be tie is always
# caught earlier by `pivots_not_decreasing`) -- it is a valid value but never observed here.
KNOWN_EXIT_REASONS = {
    "insufficient_bar_idx", "insufficient_prior_bars", "window_too_small",
    "pivots_not_decreasing", "insufficient_pivots", "degenerate_fit",
    "slope_not_negative", "trendline_below_spot", "rejection_criteria_not_met", "fired",
}


def _load_filters():
    sys.path.insert(0, str(FILTERS_LIB_DIR))
    from lib.filters import (  # noqa: PLC0415
        detect_trendline_rejection_bearish,
        TRENDLINE_LOOKBACK_BARS,
        TRENDLINE_MIN_SWINGS,
    )
    return detect_trendline_rejection_bearish, TRENDLINE_LOOKBACK_BARS, TRENDLINE_MIN_SWINGS


def test_byte_identical_returns_corpus() -> dict:
    """The headline guard. Returns the tally dict so main() can print it verbatim."""
    import pandas as pd  # noqa: PLC0415

    detect_trendline_rejection_bearish, lookback_bars, min_swings = _load_filters()

    if not CORPUS_CSV.exists():
        raise AssertionError(f"corpus file missing: {CORPUS_CSV}")
    df = pd.read_csv(CORPUS_CSV)
    ohlcv = df[["open", "high", "low", "close", "volume"]].astype(float)

    start_idx = lookback_bars + 2
    n_compared = 0
    n_fired = 0
    n_none = 0
    mismatches = []
    exit_reason_counts: dict = {}

    for i in range(start_idx, len(ohlcv)):
        bar = ohlcv.iloc[i]
        prior_bars = ohlcv.iloc[: i + 1]
        r_none = detect_trendline_rejection_bearish(
            bar, prior_bars, i, lookback_bars=lookback_bars, min_swings=min_swings,
        )
        trace: dict = {}
        r_trace = detect_trendline_rejection_bearish(
            bar, prior_bars, i, lookback_bars=lookback_bars, min_swings=min_swings,
            trace=trace,
        )
        n_compared += 1
        same = (r_none is None and r_trace is None) or (
            r_none is not None and r_trace is not None and float(r_none) == float(r_trace)
        )
        if not same:
            mismatches.append((i, r_none, r_trace))
        if r_none is None:
            n_none += 1
        else:
            n_fired += 1
        reason = trace.get("exit_reason")
        if reason not in KNOWN_EXIT_REASONS:
            raise AssertionError(f"bar {i}: unrecognized exit_reason {reason!r}")
        exit_reason_counts[reason] = exit_reason_counts.get(reason, 0) + 1

    if mismatches:
        raise AssertionError(
            f"{len(mismatches)}/{n_compared} bars had trace=None vs trace={{}} mismatches "
            f"(first 5: {mismatches[:5]})"
        )
    return {
        "bars_compared": n_compared, "fired": n_fired, "none": n_none,
        "mismatches": len(mismatches), "exit_reason_counts": exit_reason_counts,
    }


def test_trace_none_is_true_noop() -> None:
    """trace=None (the default, and every existing call site's shape) must not require the
    dict machinery at all -- confirms the parameter is additive and optional."""
    detect_trendline_rejection_bearish, lookback_bars, min_swings = _load_filters()
    import pandas as pd  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    rng = np.random.default_rng(7)
    n = lookback_bars + 10
    closes = 700 + np.cumsum(rng.normal(0, 0.3, n))
    bars = pd.DataFrame({
        "open": closes, "high": closes + rng.uniform(0.05, 0.4, n),
        "low": closes - rng.uniform(0.05, 0.4, n), "close": closes,
        "volume": rng.integers(1000, 5000, n),
    })
    i = n - 1
    # Must not raise with the historical call shape (positional-only, no trace kwarg at all).
    detect_trendline_rejection_bearish(
        bars.iloc[i], bars.iloc[: i + 1], i, lookback_bars=lookback_bars, min_swings=min_swings,
    )


def main() -> int:
    results: list[tuple[str, bool, str]] = []
    for name, fn in (
        ("test_trace_none_is_true_noop", test_trace_none_is_true_noop),
        ("test_byte_identical_returns_corpus", test_byte_identical_returns_corpus),
    ):
        try:
            out = fn()
            results.append((name, True, "" if out is None else str(out)))
        except Exception as exc:  # noqa: BLE001 -- guard must report every failure, not raise
            results.append((name, False, f"{type(exc).__name__}: {exc}"))

    ok = True
    for name, passed, detail in results:
        tag = "PASS" if passed else "FAIL"
        print(f"[{tag}] {name}" + (f" -- {detail}" if detail else ""))
        ok = ok and passed
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
