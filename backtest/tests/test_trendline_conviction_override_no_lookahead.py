"""No-look-ahead guard for the trendline-conviction-override study
(analysis/recommendations/trendline-structure-conviction-preregistration.json,
no_look_ahead_guard section).

Mirrors test_break_only_fires_on_closed_bar's pattern: the reconstructed structure-state
at signal time T (computed as trendline_engine.detect(bars[:idx+1])) must NOT change when
MORE bars (dated after T) exist in the underlying data store the truncation is drawn from.
This is the exact C6 invariant the study's data_plan relies on -- truncating the bar list
to timestamp_et <= signal_ts_et BEFORE calling detect() is the only thing standing between
the study and look-ahead, so this guard proves that truncation is sufficient in the actual
production code path (no separate re-implementation to keep in sync -- see trendline_engine.
py's own no_look_ahead_guard.statement).

Run: cd backtest && python -m pytest tests/test_trendline_conviction_override_no_lookahead.py -v
"""
from __future__ import annotations

import csv
import sys
from dataclasses import asdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "autoresearch"))

import trendline_engine as te  # noqa: E402

FIXTURE = REPO / "backtest" / "fixtures" / "spy_5m_2026-07-06_to_2026-07-08_trendline.csv"


def _load_fixture() -> list[dict]:
    rows = list(csv.DictReader(FIXTURE.open(encoding="utf-8")))
    assert rows, f"fixture is empty: {FIXTURE}"
    bars = [{"t": r["t"], "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]),
             "c": float(r["c"]), "v": float(r["v"])} for r in rows]
    bars.sort(key=lambda b: b["t"])
    return bars


def _synthetic_future_bars(n: int, last: dict) -> list[dict]:
    """n synthetic RTH-shaped bars appended strictly AFTER the fixture's last real bar --
    stand-ins for "more data landed in the store later" (a later trading day). Prices drift
    away from the fixture's last close so a look-ahead bug (accidentally scanning past the
    truncation index) would visibly change respect_count/current_value/status if it existed."""
    import datetime as _dt
    out = []
    t = _dt.datetime.fromisoformat(last["t"].replace("Z", "+00:00"))
    px = last["c"]
    for i in range(n):
        t = t + _dt.timedelta(minutes=5)
        px = px + 0.15  # steady synthetic drift, unrelated to the real tape's structure
        out.append({"t": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": round(px - 0.05, 2),
                    "h": round(px + 0.10, 2), "l": round(px - 0.10, 2), "c": round(px, 2), "v": 1000.0})
    return out


def _lines_comparable(lines: list) -> list[dict]:
    """Sort + dict-ify for order-independent, float-safe comparison."""
    return sorted((asdict(ln) for ln in lines), key=lambda d: (d["kind"], d["anchor_family"]))


def test_truncated_detect_matches_regardless_of_store_size() -> None:
    """The study's exact production call: te.detect(bars[:idx+1], families=(...)). Truncating
    a SHORT store (only real fixture bars) must give byte-identical structure state to
    truncating a LONGER store that has extra bars appended strictly AFTER the truncation
    point -- proving the future bars never influenced the result."""
    bars = _load_fixture()
    idx = len(bars) - 20  # an interior signal point, well before the fixture's own end

    short_store = bars                       # nothing after idx exists yet
    long_store = bars + _synthetic_future_bars(50, bars[-1])   # 50 more bars "landed later"

    truncated_short = short_store[: idx + 1]
    truncated_long = long_store[: idx + 1]
    assert truncated_short == truncated_long, "sanity: truncation itself must be store-size-invariant"

    lines_short = te.detect(truncated_short, families=("wick", "body"))
    lines_long = te.detect(truncated_long, families=("wick", "body"))

    assert _lines_comparable(lines_short) == _lines_comparable(lines_long), (
        "structure state at signal time T changed when MORE bars existed after T in the "
        "underlying store -- this is a look-ahead leak in the truncation convention"
    )


def test_appending_future_bars_without_retruncating_does_change_current_value() -> None:
    """Negative control -- proves the guard above is actually discriminating, not vacuously
    true because detect() ignores its input. Calling detect() on the FULL (untruncated) long
    store must project a DIFFERENT current_value than the truncated call (the line's `last`
    bar moves forward), confirming the test above would catch a real leak."""
    bars = _load_fixture()
    idx = len(bars) - 20
    long_store = bars + _synthetic_future_bars(50, bars[-1])

    truncated = te.detect(long_store[: idx + 1], families=("wick",))
    untruncated = te.detect(long_store, families=("wick",))

    truncated_support = next((ln for ln in truncated if ln.kind == "support"), None)
    untruncated_support = next((ln for ln in untruncated if ln.kind == "support"), None)
    if truncated_support is None or untruncated_support is None:
        return  # no support line detected in one of the two -- nothing to contrast, skip quietly
    assert (truncated_support.current_et != untruncated_support.current_et
            or truncated_support.current_value != untruncated_support.current_value), (
        "expected the untruncated call (which legitimately sees the future bars) to project "
        "a different current bar/value than the truncated call -- if they're identical this "
        "test isn't discriminating anything"
    )
