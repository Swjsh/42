"""zones.py -- automatic supply/demand zone detection for the weekly-options lane.

WHY "AUTOMATIC" MATTERS: the core SPY 0DTE engine's key-levels system is
hand-curated per session (J draws/confirms levels via TradingView). That does
NOT generalize -- this lane trades a multi-symbol basket (program doc
markdown/planning/WEEKLY-OPTIONS-PROGRAM.md §2/§5) and nobody is hand-drawing
levels on GLD, QQQ, NVDA, TSLA, AAPL every session. Every zone here is
computed purely from OHLCV bars for ANY symbol, five independent families
(automation/state/weekly/params.json#signal.zone_families):

  swing_high_low          raw fractal pivots (crypto.lib.trendlines) at
                           SWING_WINDOW_DAILY -- every local high/low.
  structure_hh_hl_lh_ll    only the levels that were actually BROKEN into a
                           confirmed BOS/CHoCH (crypto.lib.market_structure) --
                           a curated subset of the raw pivots above: the ones
                           the market itself proved were structurally
                           significant. Deliberately narrower than
                           swing_high_low so the two families are NOT
                           duplicates of each other; where they DO agree on a
                           price, that agreement is exactly the "confluence"
                           trigger.py counts.
  prior_week_month_hlc     previous COMPLETE week's and month's high/low/
                           close -- never the still-forming current period
                           (that would be same-bar look-ahead: using today's
                           own price action as if it were a pre-existing
                           level).
  round_numbers            psychological levels at an increment derived from
                           THIS symbol's own price scale (see
                           `_round_increment`) -- never a fixed dollar step.
  ema_20_50                the 20- and 50-day EMA read as dynamic support/
                           resistance (crypto.lib.indicators.ema).

ZONE WIDTH IS ALWAYS ATR-SCALED (ZONE_WIDTH_ATR_MULT from params.json),
computed ONCE per snapshot from Wilder ATR(14) on the input daily bars and
shared by every zone/family in that snapshot. This is the load-bearing
anti-pattern-avoidance of this module: the core SPY engine hardcodes a $12
band / $0.15 zone floor, which is a SPY-price-scale coupling that silently
breaks on a $2.70 name (GLD) or a $480 name (QQQ) alike. A fixed dollar band
here would be the exact mistake program doc §5 calls out by name.

ROLE (support/resistance) is never guessed independently per family -- it is
always `_role_for_price(price, current_price)`, a pure function of the
zone's price relative to the daily close used to build the snapshot. That is
what makes `_check_role_consistency` meaningful: two families landing on the
same price will ALWAYS agree on its role, because both derive it from the
SAME current_price. A disagreement can only mean a bug in a family builder
(e.g. one path computing role from a stale/None current_price), so the
check raises rather than silently keeping one arbitrary label.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[2]  # weekly/lib/zones.py -> weekly/lib -> weekly -> 42/
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.indicators import atr as _atr_series  # noqa: E402
from crypto.lib.indicators import ema as _ema_series  # noqa: E402
from crypto.lib.market_structure import analyze_structure  # noqa: E402
from crypto.lib.trendlines import find_swing_points  # noqa: E402

PARAMS_PATH = _REPO_ROOT / "automation" / "state" / "weekly" / "params.json"

Role = Literal["support", "resistance"]

ALL_ZONE_FAMILIES = (
    "swing_high_low",
    "structure_hh_hl_lh_ll",
    "prior_week_month_hlc",
    "round_numbers",
    "ema_20_50",
)

_ATR_LENGTH = 14  # Wilder ATR period -- a structural constant, not one of the 4 tunables
_EMA_LENGTHS = (20, 50)


@dataclass(frozen=True, slots=True)
class Zone:
    price: float
    width: float
    family: str
    role: Role
    touch_count: int
    source_bar_indices: tuple[int, ...]


class ZoneConsistencyError(RuntimeError):
    """The same price was emitted as both support and resistance in one
    snapshot -- a bug in a family builder, not a market condition (role is a
    deterministic function of price vs current close; see `_role_for_price`).
    """


def load_weekly_params(path: Path = PARAMS_PATH) -> dict:
    """Read automation/state/weekly/params.json fresh off disk every call.

    OWNED by another workstream -- this module only ever reads it, never
    writes it, never caches a copy across calls (a stale cached copy would
    silently ignore a live param change -- the exact failure class OP-25's
    "dead knob" lessons (C14) exist to prevent).
    """
    if not path.exists():
        raise FileNotFoundError(f"weekly params not found at {path} -- cannot compute zones without it")
    return json.loads(path.read_text(encoding="utf-8"))


def _role_for_price(price: float, current_price: float) -> Role:
    """Resistance sits ABOVE current price, support BELOW. A price that was a
    swing high yesterday but has since been reclaimed (current_price above
    it) correctly reads as SUPPORT here -- the standard supply/demand
    role-flip-on-break behavior, for free, because role is re-derived from
    the live current_price every snapshot rather than frozen at detection
    time."""
    return "resistance" if price > current_price else "support"


def _round_increment(current_price: float) -> float:
    """Choose the round-number step from THIS symbol's own price scale --
    never a constant (program doc §5: the core engine's hardcoded $12 band /
    $0.15 zone floor is exactly the SPY-price-scale coupling this lane must
    not inherit). Heuristic: ~1% of price, snapped to a clean 1/2/5 * 10^n
    step (e.g. ~$0.03 at a $2.70 GLD-scale price -> step 0.05; ~$4.80 at a
    $480 QQQ-scale price -> step 5)."""
    if current_price <= 0:
        raise ValueError(f"_round_increment: non-positive price {current_price}")
    raw = current_price * 0.01
    exp = math.floor(math.log10(raw))
    base = raw / (10 ** exp)
    if base < 1.5:
        step = 1
    elif base < 3.5:
        step = 2
    elif base < 7.5:
        step = 5
    else:
        step = 10
    return step * (10.0 ** exp)


def _touch_count(bars: Sequence[Bar], price: float, width: float) -> int:
    lo, hi = price - width, price + width
    return sum(1 for b in bars if b.low <= hi and b.high >= lo)


def _last_valid(values: Sequence[float]) -> float | None:
    for v in reversed(values):
        if v == v:  # NaN != NaN
            return v
    return None


def _swing_high_low_zones(bars: Sequence[Bar], window: int, width: float, current_price: float) -> list[Zone]:
    swings = find_swing_points(bars, window=window, inclusive_right=True)
    out = []
    for s in swings:
        role = _role_for_price(s.price, current_price)
        out.append(Zone(s.price, width, "swing_high_low", role,
                         _touch_count(bars, s.price, width), (s.bar_index,)))
    return out


def _structure_zones(bars: Sequence[Bar], window: int, width: float, current_price: float) -> list[Zone]:
    """Only the swing prices that were actually BROKEN into a confirmed
    BOS/CHoCH -- see module docstring for why this differs from
    `_swing_high_low_zones`."""
    read = analyze_structure(bars, window=window)
    out = []
    for ev in read.events:
        role = _role_for_price(ev.broken_price, current_price)
        out.append(Zone(ev.broken_price, width, "structure_hh_hl_lh_ll", role,
                         _touch_count(bars, ev.broken_price, width), (ev.swing_index,)))
    return out


def _prior_week_month_zones(bars: Sequence[Bar], width: float, current_price: float) -> list[Zone]:
    out: list[Zone] = []
    key_fns = (
        lambda b: (b.open_time.isocalendar()[0], b.open_time.isocalendar()[1]),  # (iso_year, iso_week)
        lambda b: (b.open_time.year, b.open_time.month),
    )
    for key_fn in key_fns:
        groups: dict[tuple, list[int]] = {}
        for i, b in enumerate(bars):
            groups.setdefault(key_fn(b), []).append(i)
        keys = sorted(groups)
        if len(keys) < 2:
            continue  # no PRIOR complete period in the window -- skip, never fabricate one
        prior_idx = groups[keys[-2]]  # period immediately before the latest (possibly still-forming) one
        prior_bars = [bars[i] for i in prior_idx]
        hi = max(b.high for b in prior_bars)
        lo = min(b.low for b in prior_bars)
        close = prior_bars[-1].close
        for price in (hi, lo, close):
            role = _role_for_price(price, current_price)
            out.append(Zone(price, width, "prior_week_month_hlc", role,
                             _touch_count(bars, price, width), tuple(prior_idx)))
    return out


def _round_number_zones(bars: Sequence[Bar], current_price: float, width: float) -> list[Zone]:
    step = _round_increment(current_price)
    base = math.floor(current_price / step) * step
    levels = sorted({base - step, base, base + step, base + 2 * step})
    out = []
    for lvl in levels:
        if lvl <= 0:
            continue
        role = _role_for_price(lvl, current_price)
        # Synthetic from the price scale alone -- no single originating bar,
        # so source_bar_indices is empty; touch_count is still measured
        # against real history.
        out.append(Zone(lvl, width, "round_numbers", role, _touch_count(bars, lvl, width), ()))
    return out


def _ema_zones(bars: Sequence[Bar], width: float, current_price: float) -> list[Zone]:
    out = []
    for length in _EMA_LENGTHS:
        values = _ema_series(bars, length)
        last = _last_valid(values)
        if last is None:
            continue  # insufficient history for this EMA length -- documented skip, not a crash
        start = max(0, len(bars) - length)
        role = _role_for_price(last, current_price)
        out.append(Zone(last, width, "ema_20_50", role,
                         _touch_count(bars, last, width), tuple(range(start, len(bars)))))
    return out


def _check_role_consistency(zones: Sequence[Zone]) -> None:
    seen: dict[float, Role] = {}
    for z in zones:
        key = round(z.price, 2)
        prior = seen.get(key)
        if prior is not None and prior != z.role:
            raise ZoneConsistencyError(
                f"price {key} emitted as both {prior!r} and {z.role!r} in one snapshot "
                f"(zone family {z.family!r}) -- role must be a pure function of price vs current close"
            )
        seen[key] = z.role


_FAMILY_BUILDERS = {
    "swing_high_low": lambda bars, sig, width, cur: _swing_high_low_zones(
        bars, int(sig["SWING_WINDOW_DAILY"]), width, cur),
    "structure_hh_hl_lh_ll": lambda bars, sig, width, cur: _structure_zones(
        bars, int(sig["SWING_WINDOW_DAILY"]), width, cur),
    "prior_week_month_hlc": lambda bars, sig, width, cur: _prior_week_month_zones(bars, width, cur),
    "round_numbers": lambda bars, sig, width, cur: _round_number_zones(bars, cur, width),
    "ema_20_50": lambda bars, sig, width, cur: _ema_zones(bars, width, cur),
}


def compute_zones(daily_bars: Sequence[Bar], *, params: dict | None = None) -> tuple[Zone, ...]:
    """Compute all configured zone families from CLOSED daily bars (oldest-
    first, as produced by weekly.lib.bars.fetch_daily + dataframe_to_bars).

    `params` defaults to a fresh read of automation/state/weekly/params.json.
    This module's only tunables: ZONE_WIDTH_ATR_MULT, SWING_WINDOW_DAILY
    (the other two of the lane's 4-tunable cap belong to trigger.py).

    Raises RuntimeError if ATR(14) cannot be computed (insufficient daily
    history -- never falls back to a fixed-dollar width). Raises
    ZoneConsistencyError if any two zones disagree on the role of the same
    price (see `_check_role_consistency` -- should be structurally
    impossible; this is a bug-catching assertion, not a market-condition
    path). Raises ValueError on an unknown zone_families entry.
    """
    if not daily_bars:
        raise ValueError("compute_zones: daily_bars is empty")
    if params is None:
        params = load_weekly_params()
    sig = params["signal"]
    families = tuple(sig["zone_families"])
    unknown = set(families) - set(ALL_ZONE_FAMILIES)
    if unknown:
        raise ValueError(f"compute_zones: unknown zone_families entr(ies) {sorted(unknown)}")

    current_price = daily_bars[-1].close
    atr_values = _atr_series(daily_bars, length=_ATR_LENGTH)
    latest_atr = _last_valid(atr_values)
    if latest_atr is None or latest_atr <= 0:
        raise RuntimeError(
            f"compute_zones: ATR({_ATR_LENGTH}) unavailable ({len(daily_bars)} daily bars given) -- "
            "refusing to emit zones with an undefined/fixed width"
        )
    width = latest_atr * float(sig["ZONE_WIDTH_ATR_MULT"])

    zones: list[Zone] = []
    for family in families:
        zones.extend(_FAMILY_BUILDERS[family](daily_bars, sig, width, current_price))

    _check_role_consistency(zones)
    return tuple(zones)
