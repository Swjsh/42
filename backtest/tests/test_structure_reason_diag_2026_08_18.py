"""Guard: C5's structure input must say WHY it abstained, not just that it did.

SCAR (2026-08-18, alignment review): `structure` degraded on 74% of post-fix conviction
rows and the row could not distinguish a legitimate 'range' abstention from a swallowed
crash -- both returned None. C7: silent success is indistinguishable from silent failure.

The crash path is real and measured. `_classify_sameday_5m` builds `crypto.lib.bar.Bar`,
which rejects a NAIVE timestamp. Replayed over 5 days of cached 5m bars:
    naive  timestamp_iso -> 'unknown' on 714/714 windows  (100% silent failure)
    -04:00 timestamp_iso -> range 299 / uptrend 202 / downtrend 154 / unknown 59 (50.1%)
Live sits at 74%, between the two -- so it is not fully broken, but the row could not tell
us how much of that 74% was the crash path. These tests pin that it can now.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))
sys.path.insert(0, str(REPO))

spec = importlib.util.spec_from_file_location("hc_diag", REPO / "setup" / "scripts" / "heartbeat_core.py")
hc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hc)  # type: ignore[union-attr]

ET = dt.timezone(dt.timedelta(hours=-4))


def _bars(closes: list[float], *, aware: bool) -> list[dict]:
    out = []
    base = dt.datetime(2026, 8, 18, 9, 30, tzinfo=ET if aware else None)
    for i, c in enumerate(closes):
        ts = base + dt.timedelta(minutes=5 * i)
        out.append({"open": c, "high": c + 0.2, "low": c - 0.2, "close": c,
                    "volume": 1000.0, "timestamp_iso": ts.isoformat()})
    return out


UP = [700 + i * 0.5 for i in range(60)]      # a full-session-length clean uptrend
CHOP = [700 + (i % 3) * 0.4 for i in range(60)]  # no directional structure


def test_facade_still_returns_side_only() -> None:
    """The public contract `_sameday_structure_side` -> str|None is unchanged."""
    got = hc._sameday_structure_side({"sameday_5m_bars": _bars(UP, aware=True)})
    assert got in ("C", "P", None)


def test_facade_delegates_to_diag_single_implementation() -> None:
    """L251: one implementation. The façade must return exactly diag's first element."""
    payload = {"sameday_5m_bars": _bars(UP, aware=True)}
    assert hc._sameday_structure_side(payload) == hc._sameday_structure_diag(payload)[0]


def test_diag_reports_a_reason_string_always() -> None:
    for payload in ({}, {"sameday_5m_bars": []}, {"sameday_5m_bars": [{"bad": 1}]},
                    {"sameday_5m_bars": _bars(UP, aware=True)}):
        side, reason = hc._sameday_structure_diag(payload)
        assert isinstance(reason, str) and reason, f"empty reason for {payload!r}"
        assert side in ("C", "P", None)


def test_diag_never_raises_on_hostile_input() -> None:
    """Fail-open is preserved: a shadow input must never break a tick."""
    for bad in (object(), 12345, "not-a-list", [{"open": "x"}], [None] * 9):
        side, reason = hc._sameday_structure_diag({"sameday_5m_bars": bad})
        assert side is None or side in ("C", "P")
        assert isinstance(reason, str)


def test_naive_timestamps_are_distinguishable_from_a_real_abstention() -> None:
    """THE POINT OF THE GUARD.

    Naive and tz-aware inputs must not both silently report the same thing. Whatever the
    naive path yields, it must be visible in `reason` -- so a future 100%-degradation cannot
    masquerade as 'the market was just choppy'.
    """
    naive_side, naive_reason = hc._sameday_structure_diag({"sameday_5m_bars": _bars(UP, aware=False)})
    aware_side, aware_reason = hc._sameday_structure_diag({"sameday_5m_bars": _bars(UP, aware=True)})

    # The naive path is a DEFECT and must be named as one -- never reported as a plain
    # abstention. This is the whole point: a 100%-degradation must be greppable.
    assert naive_reason.startswith("unknown:error:") or naive_reason.startswith("error:"), (
        f"naive timestamps reported as {naive_reason!r} -- a swallowed Bar tz-rejection is "
        "masquerading as a legitimate 'no structural opinion'"
    )
    assert naive_side is None

    # The tz-aware path must NOT be labelled a defect.
    assert not aware_reason.startswith("error:"), f"tz-aware input errored: {aware_reason}"
    assert "error:" not in aware_reason, f"tz-aware input errored: {aware_reason}"

    # And the two must be tellable apart from the logged row alone.
    assert (naive_side, naive_reason) != (aware_side, aware_reason), (
        "naive and tz-aware inputs are indistinguishable from the logged row -- "
        "this is exactly the silent-failure mode the diag exists to end"
    )


def test_error_reason_carries_the_MESSAGE_not_just_the_type() -> None:
    """SCAR (2026-08-19). The first cut recorded only `error:{type}`. Live, that produced
    `error:ModuleNotFoundError` on 12/12 SAFE ticks while BOLD succeeded on all 12 in the
    same process -- a perfectly deterministic asymmetry that could NOT be diagnosed, because
    the one fact needed (which module) was the part thrown away. An instrument that proves
    something is broken but not what is only half an instrument."""
    class Boom:
        def __len__(self): return 9
        def __getitem__(self, i): raise ModuleNotFoundError("No module named 'somepkg'")
        def __iter__(self): raise ModuleNotFoundError("No module named 'somepkg'")
        def __bool__(self): return True
    side, reason = hc._sameday_structure_diag({"sameday_5m_bars": Boom()})
    assert side is None
    assert "error:" in reason
    assert "somepkg" in reason, (
        f"reason {reason!r} names the exception TYPE but not the missing module -- "
        "that is exactly the information the 2026-08-19 safe/bold asymmetry needed"
    )


def test_error_reason_is_prefixed_for_grepability() -> None:
    """An exception must surface as 'error:<Type>' so it can be counted in a ledger sweep."""
    class Exploding:
        def __len__(self): return 9
        def __iter__(self): raise RuntimeError("boom")
        def __getitem__(self, i): raise RuntimeError("boom")
        def __bool__(self): return True
    side, reason = hc._sameday_structure_diag({"sameday_5m_bars": Exploding()})
    assert side is None
    assert "error:" in reason, f"expected an error:* reason, got {reason!r}"


def test_insufficient_bars_is_not_reported_as_an_error() -> None:
    """A short window is a legitimate abstention, not a defect -- don't cry wolf."""
    side, reason = hc._sameday_structure_diag({"sameday_5m_bars": _bars(UP[:3], aware=True)})
    assert side is None
    assert reason == "unknown:insufficient_bars"
    assert "error:" not in reason


def test_reason_vocabulary_is_closed() -> None:
    """Every reason must be classifiable by a ledger sweep -- no free-form strings."""
    ok_exact = {"uptrend", "downtrend", "range", "unknown",
                "unknown:insufficient_bars", "unknown:classifier", "unknown:not_sized"}
    for payload in ({}, {"sameday_5m_bars": []}, {"sameday_5m_bars": [{"bad": 1}]},
                    {"sameday_5m_bars": _bars(UP, aware=True)},
                    {"sameday_5m_bars": _bars(UP, aware=False)},
                    {"sameday_5m_bars": _bars(CHOP, aware=True)}):
        _, reason = hc._sameday_structure_diag(payload)
        assert reason in ok_exact or reason.startswith("error:") or reason.startswith("unknown:error:"), (
            f"unclassifiable reason {reason!r} -- extend the vocabulary deliberately"
        )
