"""Guards for the weekly-options lane signal core (weekly/lib/{bars,zones,trigger}.py).

All synthetic, deterministic, no network -- these exercise the pure
filtering/detection logic directly (weekly.lib.bars._bars_to_frame rather
than fetch_bars, which hits the live Alpaca REST endpoint).

Coverage:
  bars.py    - the closed-bar (no-look-ahead) filter excludes an in-progress
               bar; the 1Hour RTH/partial-hour filter; BarFetchError on a
               too-short surviving frame (never a silently short/empty one).
  zones.py   - zone width scales with ATR (C14 vary-and-assert); the
               one-role-per-price consistency check raises on a manufactured
               violation; an unknown zone_families entry raises.
  trigger.py - the trigger fires on a zone return + structure shift
               confirmed on the latest bar; does NOT fire on a zone touch
               with no structure shift at all; does NOT fire on a stale
               (not-latest-bar) structure shift; does NOT fire below
               MIN_ZONE_CONFLUENCE.

Run:  backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_weekly_signal_core.py -q
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

REPO = Path(__file__).resolve().parents[2]  # backtest/tests/this_file.py -> backtest/tests -> backtest -> 42/
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from crypto.lib.bar import Bar  # noqa: E402
from weekly.lib import bars as bars_mod  # noqa: E402
from weekly.lib import trigger as trigger_mod  # noqa: E402
from weekly.lib import zones as zones_mod  # noqa: E402

ET = ZoneInfo("America/New_York")


def _mk_bar(i: int, o: float, h: float, l: float, c: float, *, granularity_seconds: int = 3600) -> Bar:
    base = dt.datetime(2026, 8, 10, 9, 30, tzinfo=dt.timezone.utc)
    return Bar(
        open_time=base + dt.timedelta(seconds=granularity_seconds * i),
        open=o, high=h, low=l, close=c, volume=1000.0,
        granularity_seconds=granularity_seconds, source="test",
    )


def _mk_daily_series(rng: float, *, n: int = 20) -> tuple[Bar, ...]:
    """n daily bars, closing price walking up $1/day, true range ~= rng."""
    base = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
    close = 100.0
    out = []
    for i in range(n):
        close += 1.0
        out.append(Bar(
            open_time=base + dt.timedelta(days=i), open=close,
            high=close + rng / 2, low=close - rng / 2, close=close,
            volume=1000.0, granularity_seconds=86_400, source="test",
        ))
    return tuple(out)


_ZONES_PARAMS = {"signal": {
    "ZONE_WIDTH_ATR_MULT": 0.5,
    "SWING_WINDOW_DAILY": 2,
    "SWING_WINDOW_1H": 1,
    "MIN_ZONE_CONFLUENCE": 1,
    "zone_families": ["round_numbers"],
}}


# ─── bars.py ────────────────────────────────────────────────────────────────

class TestBarsClosedBarFilter:
    def test_drops_in_progress_daily_bar(self):
        """A daily bar dated TODAY, fetched before today's 16:00 ET close, must
        be excluded -- reading it would be look-ahead (lesson C6)."""
        raw = [
            {"t": "2026-08-17T04:00:00Z", "o": 1, "h": 2, "l": 1, "c": 1.5, "v": 100},  # closed session
            {"t": "2026-08-18T04:00:00Z", "o": 2, "h": 3, "l": 2, "c": 2.5, "v": 100},  # still forming
        ]
        now_et = dt.datetime(2026, 8, 18, 14, 0, tzinfo=ET)  # 14:00 ET, before today's 16:00 close
        df = bars_mod._bars_to_frame(raw, "1Day", now_et, min_bars=1, symbol="TEST")
        assert len(df) == 1
        assert df.iloc[0]["close"] == 1.5
        assert str(df.index[0]) == "2026-08-17 00:00:00-04:00"

    def test_includes_todays_daily_bar_after_close(self):
        """Same input, but `now_et` is AFTER today's 16:00 ET close -- today's
        bar is now legitimately closed and must be included."""
        raw = [
            {"t": "2026-08-17T04:00:00Z", "o": 1, "h": 2, "l": 1, "c": 1.5, "v": 100},
            {"t": "2026-08-18T04:00:00Z", "o": 2, "h": 3, "l": 2, "c": 2.5, "v": 100},
        ]
        now_et = dt.datetime(2026, 8, 18, 18, 0, tzinfo=ET)
        df = bars_mod._bars_to_frame(raw, "1Day", now_et, min_bars=2, symbol="TEST")
        assert len(df) == 2

    def test_drops_premarket_and_trailing_partial_hourly_bars(self):
        """Only a bar FULLY inside RTH [09:30, 16:00) ET survives: a 09:00 ET
        open (premarket) and a 15:30 ET open (30-min trailing partial hour,
        closes 16:30 > session close) are both dropped; a clean 09:30-10:30
        bar survives."""
        raw = [
            {"t": "2026-08-18T13:00:00Z", "o": 1, "h": 2, "l": 1, "c": 1.5, "v": 100},  # 09:00 ET
            {"t": "2026-08-18T13:30:00Z", "o": 2, "h": 3, "l": 2, "c": 2.5, "v": 100},  # 09:30 ET
            {"t": "2026-08-18T19:30:00Z", "o": 3, "h": 4, "l": 3, "c": 3.5, "v": 100},  # 15:30 ET
        ]
        now_et = dt.datetime(2026, 8, 18, 20, 0, tzinfo=ET)
        df = bars_mod._bars_to_frame(raw, "1Hour", now_et, min_bars=1, symbol="TEST")
        assert len(df) == 1
        assert df.iloc[0]["close"] == 2.5
        assert str(df.index[0]) == "2026-08-18 09:30:00-04:00"

    def test_raises_on_short_surviving_frame(self):
        """Fewer than min_bars survive filtering -> BarFetchError, never a
        silently short frame (CLAUDE.md 'no silent fallbacks' / lesson C7)."""
        raw = [{"t": "2026-08-17T04:00:00Z", "o": 1, "h": 2, "l": 1, "c": 1.5, "v": 100}]
        now_et = dt.datetime(2026, 8, 18, 14, 0, tzinfo=ET)
        with pytest.raises(bars_mod.BarFetchError):
            bars_mod._bars_to_frame(raw, "1Day", now_et, min_bars=5, symbol="TEST")

    def test_raises_on_empty_raw_response(self):
        """Zero raw bars in -> BarFetchError out (min_bars defaults to >=1,
        so an empty `raw` list can never satisfy it)."""
        with pytest.raises(bars_mod.BarFetchError):
            bars_mod._bars_to_frame([], "1Day", dt.datetime(2026, 8, 18, 14, 0, tzinfo=ET),
                                     min_bars=1, symbol="TEST")

    def test_dataframe_to_bars_roundtrip_is_tz_aware_and_ordered(self):
        raw = [
            {"t": "2026-08-17T04:00:00Z", "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 100},
            {"t": "2026-08-18T04:00:00Z", "o": 2, "h": 3, "l": 1.5, "c": 2.5, "v": 100},
        ]
        now_et = dt.datetime(2026, 8, 18, 18, 0, tzinfo=ET)
        df = bars_mod._bars_to_frame(raw, "1Day", now_et, min_bars=2, symbol="TEST")
        out = bars_mod.dataframe_to_bars(df, "1Day", source="test")
        assert len(out) == 2
        assert all(b.open_time.tzinfo is not None for b in out)
        assert out[0].open_time < out[1].open_time
        assert out[0].granularity_seconds == 86_400


# ─── zones.py ───────────────────────────────────────────────────────────────

class TestZonesAtrScaling:
    def test_width_scales_with_atr(self):
        """C14 vary-and-assert: hold every other knob fixed, vary ONLY the
        input bars' true range, and confirm zone width actually moves --
        proving ZONE_WIDTH_ATR_MULT is a live knob, not a translated-but-
        unapplied one."""
        low_vol = _mk_daily_series(rng=1.0)
        high_vol = _mk_daily_series(rng=6.0)

        low_zones = zones_mod.compute_zones(low_vol, params=_ZONES_PARAMS)
        high_zones = zones_mod.compute_zones(high_vol, params=_ZONES_PARAMS)

        assert low_zones and high_zones
        w_low = low_zones[0].width
        w_high = high_zones[0].width
        assert w_high > w_low * 2, f"width did not scale with ATR: low={w_low} high={w_high}"

    def test_zero_atr_mult_collapses_width(self):
        """Sanity companion to the scaling test: mult=0 must drive width to
        exactly 0 regardless of ATR, proving width really is `atr * mult`
        and not some other formula that merely correlates with it."""
        params = {**_ZONES_PARAMS, "signal": {**_ZONES_PARAMS["signal"], "ZONE_WIDTH_ATR_MULT": 0.0}}
        zs = zones_mod.compute_zones(_mk_daily_series(rng=4.0), params=params)
        assert zs and all(z.width == 0.0 for z in zs)


class TestZonesRoleConsistency:
    def test_conflicting_role_at_same_price_raises(self):
        z_a = zones_mod.Zone(100.0, 1.0, "swing_high_low", "support", 1, (0,))
        z_b = zones_mod.Zone(100.0, 1.0, "ema_20_50", "resistance", 1, (1,))
        with pytest.raises(zones_mod.ZoneConsistencyError):
            zones_mod._check_role_consistency([z_a, z_b])

    def test_agreeing_role_at_same_price_does_not_raise(self):
        z_a = zones_mod.Zone(100.0, 1.0, "swing_high_low", "support", 1, (0,))
        z_b = zones_mod.Zone(100.0, 1.0, "ema_20_50", "support", 1, (1,))
        zones_mod._check_role_consistency([z_a, z_b])  # must not raise

    def test_compute_zones_never_produces_a_real_violation(self):
        """End-to-end: role is derived from the SAME current_price for every
        family, so a real compute_zones run must never trip its own check."""
        bars = _mk_daily_series(rng=3.0, n=40)
        full_params = {"signal": {
            "ZONE_WIDTH_ATR_MULT": 0.25, "SWING_WINDOW_DAILY": 3, "SWING_WINDOW_1H": 3,
            "MIN_ZONE_CONFLUENCE": 1,
            "zone_families": list(zones_mod.ALL_ZONE_FAMILIES),
        }}
        zs = zones_mod.compute_zones(bars, params=full_params)
        assert len(zs) > 0


def test_zones_unknown_family_raises():
    params = {**_ZONES_PARAMS, "signal": {**_ZONES_PARAMS["signal"], "zone_families": ["not_a_real_family"]}}
    with pytest.raises(ValueError):
        zones_mod.compute_zones(_mk_daily_series(rng=2.0), params=params)


def test_zones_insufficient_history_raises():
    """Fewer daily bars than ATR(14) needs -> explicit RuntimeError, never a
    fixed/default width (the exact SPY-engine anti-pattern this lane must
    not inherit)."""
    short = _mk_daily_series(rng=2.0, n=5)
    with pytest.raises(RuntimeError):
        zones_mod.compute_zones(short, params=_ZONES_PARAMS)


# ─── trigger.py ─────────────────────────────────────────────────────────────

_TRIGGER_PARAMS_C1 = {"signal": {"SWING_WINDOW_1H": 1, "MIN_ZONE_CONFLUENCE": 1}}
_TRIGGER_PARAMS_C2 = {"signal": {"SWING_WINDOW_1H": 1, "MIN_ZONE_CONFLUENCE": 2}}


def _structure_shift_bars() -> tuple[Bar, ...]:
    """5 hourly bars, window=1: a swing high forms at index 1 (price 105),
    confirms at index 2, and the LAST bar (index 4) closes at 106 -- a
    confirmed bullish BOS/CHoCH break of 105 on the newest bar. Verified via
    crypto.lib.market_structure.analyze_structure during this build:
    events=(StructureEvent(kind='BOS', direction='bullish',
    broken_price=105, swing_index=1, break_index=4),)."""
    return (
        _mk_bar(0, 99, 99, 98, 99),
        _mk_bar(1, 100, 105, 99, 104),
        _mk_bar(2, 101, 102, 100, 101),
        _mk_bar(3, 102, 103, 101, 103),
        _mk_bar(4, 103, 107, 102, 106),
    )


def _monotonic_no_structure_bars(n: int = 6) -> tuple[Bar, ...]:
    """Strictly increasing highs/lows/closes -> zero swings -> zero structure
    events (find_swing_points requires a LOCAL pivot; a monotonic run has
    none). Verified during this build: analyze_structure(...).events == ()."""
    return tuple(_mk_bar(i, 100 + i, 100 + i + 0.5, 100 + i - 0.5, 100 + i + 0.2) for i in range(n))


class TestTriggerFires:
    def test_fires_on_zone_return_with_structure_shift(self):
        bars = _structure_shift_bars()
        zone = zones_mod.Zone(105.0, 1.0, "swing_high_low", "resistance", 1, (1,))
        sig = trigger_mod.detect_trigger("TEST", [zone], bars, params=_TRIGGER_PARAMS_C1)
        assert sig is not None
        assert sig.symbol == "TEST"
        assert sig.direction == "bullish"
        assert sig.zone == zone
        assert sig.trigger_bar_index == 4
        assert sig.confluence_count == 1
        assert sig.iv_rank is None
        assert sig.sector_heat_rs is None

    def test_does_not_fire_on_zone_touch_without_structure_shift(self):
        """Monotonic bars trade straight through a zone with NO structure
        event at all -- "wait for the return" without a confirmed shift must
        not trigger."""
        bars = _monotonic_no_structure_bars()
        zone = zones_mod.Zone(103.0, 2.0, "swing_high_low", "resistance", 0, ())
        sig = trigger_mod.detect_trigger("TEST", [zone], bars, params=_TRIGGER_PARAMS_C1)
        assert sig is None

    def test_does_not_fire_when_structure_shift_is_not_at_a_zone(self):
        """The same confirmed shift as the firing test, but no zone sits near
        its broken price -- "never chase candles" without a level."""
        bars = _structure_shift_bars()
        far_zone = zones_mod.Zone(500.0, 1.0, "swing_high_low", "resistance", 0, ())
        sig = trigger_mod.detect_trigger("TEST", [far_zone], bars, params=_TRIGGER_PARAMS_C1)
        assert sig is None

    def test_does_not_fire_on_stale_structure_shift(self):
        """Append two flat bars after the break -- the BOS is still the last
        EVENT, but no longer on the LAST BAR, so it must read as stale."""
        bars = _structure_shift_bars() + (
            _mk_bar(5, 106, 107, 105, 106),
            _mk_bar(6, 106, 107, 105, 106),
        )
        zone = zones_mod.Zone(105.0, 1.0, "swing_high_low", "resistance", 1, (1,))
        sig = trigger_mod.detect_trigger("TEST", [zone], bars, params=_TRIGGER_PARAMS_C1)
        assert sig is None

    def test_does_not_fire_below_min_zone_confluence(self):
        bars = _structure_shift_bars()
        zone = zones_mod.Zone(105.0, 1.0, "swing_high_low", "resistance", 1, (1,))
        sig = trigger_mod.detect_trigger("TEST", [zone], bars, params=_TRIGGER_PARAMS_C2)
        assert sig is None

    def test_fires_when_min_zone_confluence_met_by_a_second_family(self):
        bars = _structure_shift_bars()
        zone_a = zones_mod.Zone(105.0, 1.0, "swing_high_low", "resistance", 1, (1,))
        zone_b = zones_mod.Zone(105.0, 1.0, "ema_20_50", "resistance", 1, ())
        sig = trigger_mod.detect_trigger("TEST", [zone_a, zone_b], bars, params=_TRIGGER_PARAMS_C2)
        assert sig is not None
        assert sig.confluence_count == 2

    def test_no_order_placement_surface_exists(self):
        """Static guard: this module must never import anything order-shaped.
        Stage A is shadow-only -- no order-placement call exists anywhere in
        the weekly signal core."""
        src = (REPO / "weekly" / "lib" / "trigger.py").read_text(encoding="utf-8")
        for forbidden in ("place_order", "place_option_order", "submit_order", "alpaca_creds", "fleet_broker"):
            assert forbidden not in src, f"trigger.py must not reference {forbidden!r}"
