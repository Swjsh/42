"""Guard: the REAL structure-veto classifier (_classify_sameday_5m) must not
silently fail open.

WHY THIS EXISTS (the gap this closes — same class as G16):
  Gate 16 (the structure veto, engine_cli.py ~line 574) blocks wrong-way entries
  — BEAR/P in an uptrend, BULL/C in a downtrend (the 2026-06-26 −$237 wrong-way-
  short incident). Its trend signal comes from `engine_cli._classify_sameday_5m`,
  which (a) imports `crypto.lib.{bar,market_structure,trendlines}`, (b) builds a
  tz-aware `crypto.lib.bar.Bar` from each sameday 5m bar's `timestamp_iso`, and
  (c) runs swing detection + classify_trend. ALL of (a)/(b)/(c) live inside a
  `try/except Exception: return "unknown"` — and "unknown" => NO veto (fail-open).

  Every EXISTING test in test_structure_veto.py MOCKS `_classify_sameday_5m`
  (see `_with_structure_veto` / `patch.object(..., return_value=stub_trend)`),
  so NONE of them exercise the real import + tz-aware-Bar + classifier path. A
  silent break in any of the three — a crypto.lib rename, a `_REPO`-resolution
  change that drops crypto off sys.path, or a caller that feeds *naive*
  timestamps (crypto.lib.bar.Bar raises ValueError on a naive open_time, which
  the bare except swallows) — would disable Gate 16 in production while every
  test stayed green. This guard exercises the REAL function end-to-end so that
  failure mode goes RED instead of silently fail-open.

DANGEROUS NON-FIX (rejected, documented for posterity — queue G13):
  The G13 breadcrumb proposed adding `_REPO/crypto` and `_REPO/crypto/lib` to
  engine_cli's sys.path "so the import survives a cwd change". That is ACTIVELY
  HARMFUL: engine_cli does `from lib.engine.gates import ...` / `from lib.ribbon
  import RibbonState` expecting `lib` == backtest/lib, but crypto/lib is ALSO a
  package (it has its own ribbon.py and NO engine/). Inserting `_REPO/crypto` at
  sys.path[0] would shadow backtest/lib with crypto/lib and break engine_cli
  entirely. The correct protection is THIS guard, not a path edit. (test_path_*
  below pins the no-shadow invariant.)

Run:  cd backtest && python -m pytest tests/test_structure_veto_classifier_live.py -v
"""

from __future__ import annotations

import datetime as dt
import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib.engine.engine_cli as _cli_mod  # noqa: E402

_ET = dt.timezone(dt.timedelta(hours=-4))  # America/New_York EDT — production tz


def _sawtooth_bars(n: int, slope: float, *, base: float, tz_aware: bool = True) -> list[dict]:
    """A descending (slope<0) or ascending (slope>0) sawtooth, period 6.

    Real SPY 5m bars oscillate enough to produce window=2 swing points; a pure
    monotonic line has NO interior swings and classifies 'unknown'. This sawtooth
    is the minimal synthetic series that yields a clear lower-highs/lower-lows
    (or higher-highs/higher-lows) structure the classifier resolves.
    """
    out: list[dict] = []
    for i in range(n):
        c = round(base + slope * i + 2.5 * math.sin(i * math.pi / 3), 2)
        start = dt.datetime(2026, 6, 26, 10, 0, tzinfo=_ET if tz_aware else None)
        ts = start + dt.timedelta(minutes=5 * i)
        out.append(
            {
                "open": c,
                "high": c + 0.6,
                "low": c - 0.6,
                "close": c,
                "volume": 1000,
                "timestamp_iso": ts.isoformat(),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Happy path — the REAL classifier resolves the import + tz Bar + swings.
# These RED if crypto.lib stops resolving, the tz handling regresses, or the
# classifier is otherwise silently disabled (the fail-open => 'unknown' tell).
# ---------------------------------------------------------------------------

def test_real_classifier_resolves_downtrend():
    """tz-aware descending sawtooth must classify 'downtrend' (NOT 'unknown')."""
    bars = _sawtooth_bars(30, slope=-0.35, base=740.0)
    assert _cli_mod._classify_sameday_5m(bars) == "downtrend"


def test_real_classifier_resolves_uptrend():
    """tz-aware ascending sawtooth must classify 'uptrend' (NOT 'unknown')."""
    bars = _sawtooth_bars(30, slope=+0.35, base=720.0)
    assert _cli_mod._classify_sameday_5m(bars) == "uptrend"


def test_downtrend_classification_drives_a_bull_veto():
    """End-to-end: a real downtrend must make a BULL/C entry veto-eligible.

    This is the property Gate 16 actually depends on — proves the real trend
    signal (not a mock) flows into the veto predicate correctly.
    """
    bars = _sawtooth_bars(30, slope=-0.35, base=740.0)
    trend = _cli_mod._classify_sameday_5m(bars)
    assert trend == "downtrend"
    assert _cli_mod._veto_side("C", trend) is True   # wrong-way long blocked
    assert _cli_mod._veto_side("P", trend) is False  # with-structure short allowed


# ---------------------------------------------------------------------------
# The crypto.lib import — the thing the silent except hides.
# ---------------------------------------------------------------------------

def test_crypto_lib_import_resolves_under_engine_cli_syspath():
    """The exact imports inside _classify_sameday_5m must resolve.

    If a rename/move/_REPO-resolution change breaks these, the bare except in
    _classify_sameday_5m would swallow the ImportError -> 'unknown' -> Gate 16
    silently off. Importing them directly here makes that break loud.
    """
    from crypto.lib.bar import Bar  # noqa: F401
    from crypto.lib.market_structure import classify_trend, label_swings  # noqa: F401
    from crypto.lib.trendlines import find_swing_points  # noqa: F401


# ---------------------------------------------------------------------------
# Characterization: the naive-timestamp fail-open (documents the contract).
# crypto.lib.bar.Bar requires a tz-aware open_time; a naive timestamp_iso
# raises ValueError, swallowed -> 'unknown' -> veto off. heartbeat_core supplies
# tz-aware America/New_York ISO (heartbeat_core.py L147+L428), so production is
# safe TODAY — this test pins that any future naive-feeding caller is a known,
# visible silent-disable, not an invisible one.
# ---------------------------------------------------------------------------

def test_naive_timestamps_silently_fail_open_is_characterized():
    """Naive (tz-less) timestamps => 'unknown' (no veto). Documented fragility.

    If a future hardening localizes naive timestamps, THIS test must be updated
    deliberately — turning a silent regression into an intentional decision.
    """
    naive = _sawtooth_bars(30, slope=-0.35, base=740.0, tz_aware=False)
    assert _cli_mod._classify_sameday_5m(naive) == "unknown"


def test_production_timestamp_shape_classifies():
    """The exact production timestamp_iso shape (tz-aware NY isoformat) works.

    Pins the heartbeat_core -> engine_cli contract: a string like
    '2026-06-26T10:00:00-04:00' must parse + classify, not fall to 'unknown'.
    """
    bars = _sawtooth_bars(30, slope=-0.35, base=740.0)
    assert bars[0]["timestamp_iso"].endswith("-04:00")  # production shape
    assert _cli_mod._classify_sameday_5m(bars) == "downtrend"


# ---------------------------------------------------------------------------
# Fail-open safety — short/empty/garbage input must never raise, only 'unknown'.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad",
    [None, [], _sawtooth_bars(3, slope=-0.35, base=740.0), "not-a-list", [{}, {}, {}, {}, {}]],
)
def test_bad_input_returns_unknown_never_raises(bad):
    """Any malformed / too-short input => 'unknown' (fail-open), never an exception."""
    assert _cli_mod._classify_sameday_5m(bad) == "unknown"


# ---------------------------------------------------------------------------
# The no-shadow invariant (why the G13 path-fix was rejected).
# crypto/lib must NOT carry engine/ or filters/ — if it ever does, putting it on
# sys.path (as G13 proposed) would shadow backtest/lib and break engine_cli.
# This pins the reasoning that rejected that fix.
# ---------------------------------------------------------------------------

def test_crypto_lib_does_not_shadow_backtest_lib_engine():
    """crypto/lib has no engine/ or filters/ -> it must never be put before
    backtest on sys.path (the rejected G13 fix would have shadow-broken
    `from lib.engine.gates import ...`)."""
    crypto_lib = REPO / "crypto" / "lib"
    assert not (crypto_lib / "engine").exists(), "crypto/lib gained engine/ — G13 shadow risk is now real"
    assert not (crypto_lib / "filters.py").exists(), "crypto/lib gained filters.py — G13 shadow risk is now real"


def test_engine_cli_lib_resolves_to_backtest_not_crypto():
    """engine_cli's `lib` must be backtest/lib (proves no crypto/lib shadow)."""
    import lib.ribbon as _r
    assert "backtest" in str(Path(_r.__file__).resolve()).replace("\\", "/").lower()
