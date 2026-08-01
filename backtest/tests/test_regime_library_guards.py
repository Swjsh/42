"""Guards for the WS6 day-archetype regime library (2026-08-01).

Pins three surfaces:
  1. CLASSIFIER SEMANTICS -- synthetic OHLC vectors must map to every one of the
     8 archetypes + data-incomplete, and the documented precedence must hold
     (gap mechanism outranks shape; V outranks trend; pin outranks chop).
  2. DETERMINISM -- serialize(build) of a fixed synthetic session set is
     byte-identical across two calls (the artifact's core promise).
  3. ARTIFACT INTEGRITY -- the committed day-archetypes.json self-reconciles:
     population counts match the day records, every archetype is legal, the
     distribution sums to the assignable count, verified-window day count is
     pinned, and known landmark days carry the labels verified at build time
     (2025-04-03 tariff crash = gap-go, 2026-06-15 broken feed day =
     data-incomplete).
  4. SLICER CONTRACT -- unknown dates land in UNTAGGED loudly, rows include ALL.

RED-proof: each block was mutated during WS6 (threshold flip / artifact edit /
bucket rename) and observed to fail before shipping.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO / "backtest"), str(REPO / "backtest" / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import build_day_archetypes as bda  # noqa: E402
from lib import regime_slice as rs  # noqa: E402

ART = REPO / "analysis" / "regime-library" / "day-archetypes.json"


# ---------------------------------------------------------------------------
# helpers -- synthetic 5m sessions (78 bars unless stated)
# ---------------------------------------------------------------------------

def _session(path_points: list[float], n_bars: int = 78) -> pd.DataFrame:
    """Build a 5m session whose closes linearly interpolate path_points.

    open[0] = path_points[0]; each bar is a small candle around the path so
    high/low track the path envelope tightly.
    """
    import numpy as np
    xs = np.linspace(0.0, 1.0, n_bars)
    seg = np.linspace(0.0, 1.0, len(path_points))
    closes = np.interp(xs, seg, path_points)
    opens = np.concatenate([[path_points[0]], closes[:-1]])
    highs = np.maximum(opens, closes) + 0.02
    lows = np.minimum(opens, closes) - 0.02
    ts = [dt.datetime(2026, 1, 2, 9, 30) + dt.timedelta(minutes=5 * i)
          for i in range(n_bars)]
    return pd.DataFrame({"ts": ts, "open": opens, "high": highs,
                         "low": lows, "close": closes})


def _label(path_points, prior_close=None, n_bars=78):
    f = bda.day_features(_session(path_points, n_bars), prior_close)
    return bda.classify(f), f


# ---------------------------------------------------------------------------
# 1. classifier semantics -- one synthetic day per archetype
# ---------------------------------------------------------------------------

def test_trend_up():
    arch, f = _label([600.0, 602.0, 604.0, 606.0])
    assert arch == "trend-up", f
    assert f["body_pct"] >= bda.TREND_BODY_PCT


def test_trend_down():
    arch, f = _label([600.0, 598.0, 596.0, 594.0])
    assert arch == "trend-down", f


def test_v_reversal():
    # opens 600, dumps to 594 in the first third, recovers to close 599.8
    arch, f = _label([600.0, 594.0, 597.0, 599.8])
    assert arch == "V-reversal", f
    assert f["t_low"] <= bda.V_TIME_FRAC


def test_inverted_v():
    arch, f = _label([600.0, 606.0, 603.0, 600.2])
    assert arch == "inverted-V", f


def test_range_chop():
    # wide two-way swings, mid-range close, small body: no mechanism resolves
    arch, f = _label([600.0, 602.5, 598.5, 601.5, 599.0, 600.9])
    assert arch == "range-chop", f


def test_pin_day():
    # 0.3%-range drift that closes at the open
    arch, f = _label([600.0, 601.0, 599.5, 600.1])
    assert arch == "pin-day", f
    assert abs(f["body_pct"]) <= bda.PIN_BODY_PCT


def test_gap_go_up():
    # prior close 600, opens +0.5% at 603, never trades back to 600, closes higher
    arch, f = _label([603.0, 604.0, 605.5], prior_close=600.0)
    assert arch == "gap-go", f


def test_gap_fade_up():
    # opens +0.5% at 603, fills to 599.5, closes below open
    arch, f = _label([603.0, 599.4, 600.5], prior_close=600.0)
    assert arch == "gap-fade", f


def test_gap_fade_down_recovers():
    # gap DOWN that fills upward and closes above open
    arch, f = _label([597.0, 601.0, 600.5], prior_close=600.0)
    assert arch == "gap-fade", f


def test_data_incomplete_short_session():
    arch, _ = _label([600.0, 601.0], n_bars=bda.MIN_BARS_ASSIGNABLE - 1)
    assert arch == "data-incomplete"


# ---------------------------------------------------------------------------
# precedence pins
# ---------------------------------------------------------------------------

def test_precedence_gap_outranks_v_shape():
    """A gap-down day that V-recovers through prior close = gap-fade, not V-reversal
    (the documented 2025-04-09 semantics)."""
    arch, f = _label([597.0, 594.0, 601.0, 600.8], prior_close=600.0)
    assert arch == "gap-fade", f
    # shape-wise it WOULD have been a V: prove the shape conditions held
    assert f["t_low"] <= bda.V_TIME_FRAC and f["close_loc"] >= bda.V_CLOSE_LOC


def test_precedence_unresolved_gap_falls_through_to_shape():
    """Significant gap that neither fills nor continues cleanly -> shape rules."""
    # gap up 0.5%, never fills (low 601 > 600), but closes BELOW open -> not go/fade
    arch, f = _label([603.0, 606.5, 601.2, 601.4], prior_close=600.0)
    assert f["gap_pct"] >= bda.GAP_SIG_PCT
    assert arch not in ("gap-go", "gap-fade"), f


def test_first_population_day_has_no_gap_rules():
    # same shape as a gap-go day, but with no prior close it must fall through
    # to the shape rules (here: a clean trend-up)
    arch, f = _label([603.0, 605.0, 607.0, 609.0], prior_close=None)
    assert f["gap_pct"] is None
    assert arch == "trend-up", f


# ---------------------------------------------------------------------------
# 2. determinism
# ---------------------------------------------------------------------------

def test_synthetic_build_days_deterministic():
    days = {dt.date(2026, 1, 2): _session([600.0, 602.0, 604.0, 606.0]),
            dt.date(2026, 1, 5): _session([606.0, 600.5, 604.0, 605.8])}
    vix = {dt.date(2026, 1, 2): (15.0, 14.5), dt.date(2026, 1, 5): (14.5, 16.0)}
    a = json.dumps(bda.build_days(days, vix), sort_keys=True)
    b = json.dumps(bda.build_days(days, vix), sort_keys=True)
    assert a == b


# ---------------------------------------------------------------------------
# 3. committed-artifact integrity
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def artifact():
    assert ART.exists(), f"regime library artifact missing: {ART}"
    return json.loads(ART.read_text(encoding="ascii"))


def test_artifact_population_reconciles(artifact):
    days = artifact["days"]
    pop = artifact["population"]
    assert pop["data_days"] == len(days)
    n_incomplete = sum(1 for r in days.values()
                       if r["archetype"] == "data-incomplete")
    assert pop["assignable_days"] == len(days) - n_incomplete
    sess = {"full": 0, "half-day": 0, "truncated-tail": 0, "incomplete": 0}
    for r in days.values():
        sess[r["session"]] += 1
    assert pop["sessions"] == sess


def test_artifact_verified_window_day_count_pinned(artifact):
    """The verified window 2025-01-02..2026-07-31 yields exactly 394 data-days
    (386 full + 3 half + 4 truncated-tail + 1 incomplete) from the pinned
    lineage. If this moves, the input files changed -- investigate, then re-pin."""
    days = artifact["days"]
    vw = artifact["population"]["verified_window"]
    in_window = [d for d in days if vw["start"] <= d <= vw["end"]]
    assert len(in_window) == 394
    assert artifact["population"]["incomplete_dates"] == ["2026-06-15"]


def test_artifact_archetypes_legal_and_distribution_sums(artifact):
    legal = set(artifact["archetypes"]) | {"data-incomplete"}
    for d, r in artifact["days"].items():
        assert r["archetype"] in legal, (d, r["archetype"])
    dist = artifact["distribution"]
    assert sum(dist["full_counts"].values()) == dist["n_assignable"]
    assert sum(dist["last_25_counts"].values()) == min(25, dist["n_assignable"])


def test_artifact_landmark_days(artifact):
    days = artifact["days"]
    assert days["2025-04-03"]["archetype"] == "gap-go"        # tariff crash, never filled
    assert days["2026-06-15"]["archetype"] == "data-incomplete"
    assert days["2026-07-31"]["archetype"] == "V-reversal"    # Friday dip-and-recover
    assert days["2025-12-24"]["session"] == "half-day"


def test_artifact_spec_and_thresholds_frozen(artifact):
    assert artifact["spec_version"] == "1.0.0"
    th = artifact["thresholds"]
    assert th["GAP_SIG_PCT"] == bda.GAP_SIG_PCT
    assert th["TREND_BODY_PCT"] == bda.TREND_BODY_PCT
    assert list(artifact["precedence"]) == list(bda.PRECEDENCE)


# ---------------------------------------------------------------------------
# 4. slicer contract
# ---------------------------------------------------------------------------

def test_slicer_untagged_is_loud(artifact):
    rows = rs.per_archetype_rows({"2026-07-31": 100.0, "1999-01-04": -50.0},
                                 path=ART)
    by = {r["archetype"]: r for r in rows}
    assert by["V-reversal"]["n"] == 1
    assert by["UNTAGGED"]["n"] == 1          # never silently dropped
    assert by["ALL"]["n"] == 2
    assert by["ALL"]["total"] == 50.0


def test_slicer_accepts_date_objects(artifact):
    assert rs.archetype_of(dt.date(2026, 7, 31), path=ART) == "V-reversal"


def test_slicer_recent_mix_counts(artifact):
    mix = rs.recent_mix(25, path=ART)
    assert sum(mix.values()) == 25
    assert mix == artifact["distribution"]["last_25_counts"] or all(
        mix.get(k, 0) == v for k, v in artifact["distribution"]["last_25_counts"].items() if v
    )
