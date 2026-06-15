"""
v15.3 live-price first-bar level-break trigger — smoke test.

PROPOSAL: heartbeat-v15.3-draft.md adds a NEW conditional trigger path that fires on a live-bid
cross of a named ★★+ level inside the 09:35-09:45 ET window. Fixes the 1-bar lag at fast-V
reversals (foot-gun behind 2026-05-15's −$770 loss).

This smoke test:
  1. Reads the 2026-05-15 5m bars from any data/spy_5m_*.csv covering that date.
  2. Simulates the live-price trigger during the 09:40 bar (in-flight wall-clock ~09:41 ET):
     verifies it WOULD fire on the live bid (~$738.95) below PML 739.04 with the proposed margin.
  3. Re-simulates the closed-bar trigger at the SAME wall-clock 09:41 ET: verifies it would NOT
     fire (because the 09:40 bar has not yet closed — last closed = 09:35 with close 739.16
     ABOVE PML).
  4. Asserts both branches behave as expected. Fails loudly on either mismatch.

Run standalone:
    python backtest/autoresearch/v15_3_live_price_trigger_smoke.py

OP-20 disclosures live in the candidate spec at
strategy/candidates/2026-05-17-live-price-first-bar-trigger.md.

CLAUDE.md OP-22 verify-now-not-later: this script reproduces the foot-gun synthetically
BEFORE any production change. If the assertions fail, the v15.3 design is wrong; if they pass,
v15.3 catches the 5/15 09:40 fast-V class that v15.1 misses by one bar.
"""

from __future__ import annotations

import csv
import io
import sys
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Optional

# Windows console default is cp1252 which can't render em-dashes or stars — force UTF-8 stdout.
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Python 3.7+
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


# ---- Constants (from heartbeat-v15.3-draft.md Change B) -----------------------------------------

PML_PRICE = 739.04          # 2026-05-15 premarket low — named ★★ Active support (key-levels.json)
PML_STARS = 2               # ★★ qualifies (proposal requires stars ≥ 2)
PML_TIER = "Active"         # qualifies (proposal requires tier ∈ {Carry, Active})
PML_SOURCE = "2026-05-15 premarket low — 08:20 ET bar, fresh intraday floor"
                            # matches /PMH|PML|premarket high|premarket low|Carry/i

LEVEL_CROSS_ABS_MARGIN = 0.05         # $0.05 absolute floor
LEVEL_CROSS_REL_MARGIN_PCT = 0.00007  # 0.7 basis-points relative

FIRST_BAR_WINDOW_START = time(9, 35)
FIRST_BAR_WINDOW_END = time(9, 45)   # exclusive

QUOTE_FRESHNESS_SECONDS_MAX = 60

DATA_DIR_CANDIDATES = [
    Path(__file__).resolve().parents[2] / "backtest" / "data",
    Path(__file__).resolve().parents[2] / "data",
]


# ---- Data model ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Bar:
    """One 5m SPY bar. timestamp_et is naive ET (no tz)."""

    timestamp_et: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class Level:
    """Named key level from key-levels.json (simplified subset)."""

    price: float
    type: str               # support / resistance / etc.
    tier: str               # Active / Carry / Reference
    stars: int
    source: str


@dataclass(frozen=True)
class LiveQuote:
    """Live quote_get response (simplified)."""

    bid: float
    last: float
    fetched_at_et: datetime  # naive ET


# ---- Helpers ------------------------------------------------------------------------------------


def find_spy_5m_csv_for_date(target_date: str) -> Optional[Path]:
    """
    Locate the most-recent spy_5m_*.csv that covers target_date (YYYY-MM-DD).
    Returns the longest-coverage match if multiple exist.
    """
    candidates: list[Path] = []
    for data_dir in DATA_DIR_CANDIDATES:
        if not data_dir.exists():
            continue
        for path in data_dir.glob("spy_5m_*.csv"):
            # filename: spy_5m_<start>_<end>.csv
            try:
                stem_parts = path.stem.split("_")
                if len(stem_parts) >= 4:
                    end_date_str = stem_parts[-1]
                    start_date_str = stem_parts[-2]
                    if start_date_str <= target_date <= end_date_str:
                        candidates.append(path)
            except (IndexError, ValueError):
                continue
    if not candidates:
        return None
    # Prefer the longest-coverage file
    return max(candidates, key=lambda p: p.stat().st_size)


def load_bars_for_date(csv_path: Path, target_date: str) -> list[Bar]:
    """Load only bars whose timestamp's date matches target_date (YYYY-MM-DD)."""
    bars: list[Bar] = []
    with csv_path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ts_raw = row["timestamp_et"]
            if not ts_raw.startswith(target_date):
                continue
            # timestamp_et format: "2026-05-15 09:40:00-04:00"
            # Strip tz suffix and parse as naive ET.
            ts_no_tz = ts_raw.split("-04:00")[0].split("-05:00")[0].rstrip()
            ts = datetime.strptime(ts_no_tz, "%Y-%m-%d %H:%M:%S")
            bars.append(
                Bar(
                    timestamp_et=ts,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(float(row["volume"])),
                )
            )
    return bars


def find_bar(bars: list[Bar], hh: int, mm: int) -> Bar:
    target = time(hh, mm)
    for b in bars:
        if b.timestamp_et.time() == target:
            return b
    raise LookupError(f"No bar found at {hh:02d}:{mm:02d}")


def last_closed_bar(bars: list[Bar], now_et: datetime) -> Optional[Bar]:
    """
    Mirrors heartbeat v15.1 R1 closed-bar rule: a bar is closed iff bar.timestamp + 5min <= now_et.
    Returns the LAST such bar, or None if no bar has closed yet.
    """
    closed = [b for b in bars if (b.timestamp_et + timedelta(minutes=5)) <= now_et]
    return closed[-1] if closed else None


def level_cross_margin(level_price: float) -> float:
    """max(abs_floor, relative_pct × level_price)"""
    return max(LEVEL_CROSS_ABS_MARGIN, LEVEL_CROSS_REL_MARGIN_PCT * level_price)


def level_qualifies_for_v15_3(level: Level) -> bool:
    """Apply v15.3 Change B qualifier: tier ∈ {Carry, Active} AND stars ≥ 2 AND source regex match."""
    if level.tier not in {"Carry", "Active"}:
        return False
    if level.stars < 2:
        return False
    source_lower = level.source.lower()
    needles = ("pmh", "pml", "premarket high", "premarket low", "carry")
    return any(n in source_lower for n in needles)


# ---- v15.3 live-price branch (BEAR — level break) -----------------------------------------------


def live_price_level_break_fires(
    *,
    level: Level,
    live_quote: LiveQuote,
    prior_closed_bar: Optional[Bar],
    now_et: datetime,
) -> tuple[bool, str]:
    """
    Returns (fires, reason). Mirrors heartbeat-v15.3-draft.md Change B BEAR trigger.

    Conditions (BEAR — break support):
      0. level_qualifies_for_v15_3(level) == True
      1. now_et in [09:35:00, 09:45:00)
      2. live_quote.bid < level.price - margin
      3. prior_closed_bar.close >= level.price - $0.05
      4. live_quote.fetched_at_et within 60s of now_et
      5. level.type in {support, psychological, transition}  (BEAR side breaks support-class)
    """
    if not level_qualifies_for_v15_3(level):
        return False, "level does not qualify (tier/stars/source)"

    if level.type not in {"support", "psychological", "transition"}:
        return False, f"level.type={level.type!r} is not support-class for BEAR break"

    if not (FIRST_BAR_WINDOW_START <= now_et.time() < FIRST_BAR_WINDOW_END):
        return False, f"now_et.time()={now_et.time()} outside [09:35, 09:45)"

    margin = level_cross_margin(level.price)
    if live_quote.bid >= (level.price - margin):
        return False, (
            f"live_bid {live_quote.bid:.2f} not below level {level.price:.2f} - margin {margin:.3f} "
            f"(={level.price - margin:.3f})"
        )

    if prior_closed_bar is None:
        return False, "no prior closed bar (cannot verify level was not previously broken)"
    if prior_closed_bar.close < (level.price - LEVEL_CROSS_ABS_MARGIN):
        return False, (
            f"prior closed bar close {prior_closed_bar.close:.2f} already below level "
            f"{level.price:.2f} - $0.05 — closed-bar trigger should handle this, not live-price"
        )

    age_seconds = (now_et - live_quote.fetched_at_et).total_seconds()
    if age_seconds > QUOTE_FRESHNESS_SECONDS_MAX or age_seconds < 0:
        return False, f"quote age {age_seconds:.0f}s outside [0, {QUOTE_FRESHNESS_SECONDS_MAX}]"

    return True, (
        f"FIRES: live_bid {live_quote.bid:.2f} < level {level.price:.2f} - margin {margin:.3f}; "
        f"prior_close {prior_closed_bar.close:.2f} >= level - $0.05; "
        f"quote_age {age_seconds:.0f}s ok; window ok"
    )


# ---- v15.1 closed-bar branch (BEAR — level_reject) ----------------------------------------------


def closed_bar_level_reject_fires(
    *,
    level: Level,
    bars: list[Bar],
    now_et: datetime,
) -> tuple[bool, str]:
    """
    Mirrors heartbeat.md line 346 level_reject trigger:
      bar.high > level AND bar.close < level  on LAST CLOSED 5m bar.
    """
    lcb = last_closed_bar(bars, now_et)
    if lcb is None:
        return False, "no bar has closed yet"
    if lcb.high > level.price and lcb.close < level.price:
        return True, (
            f"FIRES: last_closed_bar {lcb.timestamp_et.time()} high {lcb.high:.2f} > level "
            f"{level.price:.2f} AND close {lcb.close:.2f} < level — level_reject"
        )
    return False, (
        f"NO FIRE: last_closed_bar {lcb.timestamp_et.time()} high {lcb.high:.2f} / close "
        f"{lcb.close:.2f} vs level {level.price:.2f}"
    )


# ---- Test cases ---------------------------------------------------------------------------------


def case_1_live_price_fires_during_0940_bar(bars: list[Bar], pml: Level) -> bool:
    """
    Case 1: wall-clock 09:41:30 ET, INSIDE the 09:40 5m bar (in-flight).
    The live bid is somewhere between the 09:40 open (739.16) and low (738.62).
    Use 738.95 (consistent with the in-flight cross of PML 739.04).

    Expected:
      - live-price branch FIRES (bid below level minus margin, prior closed bar = 09:35 with
        close 739.16 ≥ level − $0.05, window OK)
      - closed-bar branch does NOT fire (last closed bar = 09:35 with high 740.21 > level but
        close 739.16 > level → no level_reject)
    """
    print("\n=== CASE 1: live-price trigger DURING 09:40 in-flight bar ===")
    now_et = datetime(2026, 5, 15, 9, 41, 30)
    live_quote = LiveQuote(
        bid=738.95,
        last=738.96,
        fetched_at_et=datetime(2026, 5, 15, 9, 41, 25),
    )
    bar_0935 = find_bar(bars, 9, 35)

    live_fires, live_reason = live_price_level_break_fires(
        level=pml,
        live_quote=live_quote,
        prior_closed_bar=bar_0935,
        now_et=now_et,
    )
    print(f"  live-price branch: {'FIRES' if live_fires else 'no fire'} — {live_reason}")

    closed_fires, closed_reason = closed_bar_level_reject_fires(
        level=pml,
        bars=bars,
        now_et=now_et,
    )
    print(f"  closed-bar branch: {'FIRES' if closed_fires else 'no fire'} — {closed_reason}")

    if not live_fires:
        print("  FAIL: live-price branch should have FIRED on the in-flight cross at 09:41 ET")
        return False
    if closed_fires:
        print("  FAIL: closed-bar branch should NOT fire at 09:41 ET (09:40 bar not yet closed)")
        return False
    print("  PASS")
    return True


def case_2_closed_bar_fires_at_0946_into_bounce(bars: list[Bar], pml: Level) -> bool:
    """
    Case 2: wall-clock 09:46:38 ET (the real journal fill time).
    The 09:40 bar has closed (close_time 09:45 ≤ now_et). v15.1 closed-bar branch fires.

    Expected:
      - closed-bar branch FIRES (last closed = 09:40 with high 740.10 > level AND close
        738.66 < level — level_reject)
      - live-price branch is OUTSIDE the [09:35, 09:45) window so it does NOT fire even with a
        below-level bid

    This case proves the v15.3 branch is correctly time-scoped: AFTER the 09:40 bar closes,
    the live-price branch suppresses itself and v15.1's closed-bar logic takes over (as
    happened in the real 5/15 trade — entry at 09:46, into the bounce).
    """
    print("\n=== CASE 2: at 09:46:38 ET — closed-bar fires, live-price out of window ===")
    now_et = datetime(2026, 5, 15, 9, 46, 38)
    live_quote = LiveQuote(
        bid=738.95,
        last=739.00,
        fetched_at_et=datetime(2026, 5, 15, 9, 46, 35),
    )
    bar_0940 = find_bar(bars, 9, 40)

    live_fires, live_reason = live_price_level_break_fires(
        level=pml,
        live_quote=live_quote,
        prior_closed_bar=bar_0940,
        now_et=now_et,
    )
    print(f"  live-price branch: {'FIRES' if live_fires else 'no fire'} — {live_reason}")

    closed_fires, closed_reason = closed_bar_level_reject_fires(
        level=pml,
        bars=bars,
        now_et=now_et,
    )
    print(f"  closed-bar branch: {'FIRES' if closed_fires else 'no fire'} — {closed_reason}")

    if live_fires:
        print("  FAIL: live-price branch is OUT of [09:35, 09:45) window — must not fire")
        return False
    if not closed_fires:
        print("  FAIL: closed-bar branch should fire on the 09:40 bar's confirmed close")
        return False
    print("  PASS")
    return True


def case_3_v_reversal_bar_closes_above_level(bars: list[Bar], pml: Level) -> bool:
    """
    Case 3: wall-clock 09:50:30 ET (just after 09:45 bar closed).
    The 09:45 bar WICKED to 737.96 (well below PML) but CLOSED at 739.65 — V-reversal.

    Expected:
      - closed-bar branch on the 09:45 bar reading: high 739.67 > level 739.04 AND close
        739.65 > level → NOT a level_reject (close did not cross below). NO FIRE on 09:45
        BUT the 09:40 bar is now 2 bars back, and 09:40's level_reject would have already
        fired at 09:46 ET (case 2). So this case is about whether the NEW closed-bar (09:45)
        re-fires — which it should NOT.
      - live-price branch is OUT of window.

    This case proves the closed-bar branch correctly does NOT re-fire on the V-reversal bar
    even though SPY is again above the level — illustrating why the V-reversal pattern is so
    treacherous: the entry already fired on the 09:40 break, and the 09:45 bar's reversal is
    too late to inform the entry decision.
    """
    print("\n=== CASE 3: at 09:50:30 ET — V-reversal bar (09:45) closes ABOVE level ===")
    now_et = datetime(2026, 5, 15, 9, 50, 30)
    bar_0945 = find_bar(bars, 9, 45)

    # Verify the data matches journal narrative
    assert bar_0945.low <= 738.0, f"09:45 bar low should be ~737.96, got {bar_0945.low}"
    assert bar_0945.close > pml.price, (
        f"09:45 bar close {bar_0945.close} should be ABOVE PML {pml.price} (V-reversal)"
    )

    # On the 09:45 closed bar: high > level (yes, 739.67 > 739.04) AND close < level (NO,
    # 739.65 > 739.04) — so level_reject does NOT fire on the V-reversal bar.
    # But last_closed_bar at 09:50:30 is 09:45 (not 09:40). So the level_reject check is on
    # 09:45's OHLC.
    lcb = last_closed_bar(bars, now_et)
    assert lcb is not None and lcb.timestamp_et.time() == time(9, 45), (
        f"last_closed_bar at 09:50:30 should be 09:45 bar, got "
        f"{lcb.timestamp_et.time() if lcb else None}"
    )

    closed_fires, closed_reason = closed_bar_level_reject_fires(
        level=pml,
        bars=bars,
        now_et=now_et,
    )
    print(f"  closed-bar branch on 09:45 V-reversal bar: "
          f"{'FIRES' if closed_fires else 'no fire'} — {closed_reason}")

    if closed_fires:
        print("  FAIL: closed-bar branch should NOT fire on V-reversal (close above level)")
        return False
    print("  PASS — V-reversal correctly does not trigger fresh level_reject")
    return True


def case_4_level_qualifies(pml: Level) -> bool:
    """Case 4: the PML 739.04 named level qualifies under v15.3 Change B filter."""
    print("\n=== CASE 4: PML 739.04 qualifies under v15.3 named-level filter ===")
    qualifies = level_qualifies_for_v15_3(pml)
    print(f"  level_qualifies_for_v15_3(PML 739.04): {qualifies}")
    if not qualifies:
        print("  FAIL: PML should qualify (tier=Active, stars=2, source matches /premarket low/)")
        return False
    print("  PASS")
    return True


def case_5_reference_level_does_not_qualify() -> bool:
    """Case 5: a 1-star Reference-tier psychological level does NOT qualify."""
    print("\n=== CASE 5: Reference-tier 1-star psychological level does NOT qualify ===")
    psych_740 = Level(
        price=740.00,
        type="psychological",
        tier="Reference",
        stars=1,
        source="Round number -- immediate overhead",
    )
    qualifies = level_qualifies_for_v15_3(psych_740)
    print(f"  level_qualifies_for_v15_3(740.00 psychological 1-star Reference): {qualifies}")
    if qualifies:
        print("  FAIL: Reference-tier 1-star psychological should NOT qualify")
        return False
    print("  PASS")
    return True


def case_6_window_boundary_at_0935(bars: list[Bar], pml: Level) -> bool:
    """
    Case 6: live-price branch is active starting at 09:35:00 exactly (inclusive) and inactive
    at 09:45:00 exactly (exclusive). Test both boundaries.
    """
    print("\n=== CASE 6: window boundaries [09:35, 09:45) ===")
    # 09:35:00 ET — window OPENS exactly here
    now_at_open = datetime(2026, 5, 15, 9, 35, 0)
    bar_0930 = find_bar(bars, 9, 30)
    live_quote = LiveQuote(
        bid=738.95,
        last=738.96,
        fetched_at_et=datetime(2026, 5, 15, 9, 34, 55),
    )
    fires_at_open, reason_at_open = live_price_level_break_fires(
        level=pml,
        live_quote=live_quote,
        prior_closed_bar=bar_0930,
        now_et=now_at_open,
    )
    print(f"  at 09:35:00 ET (window OPEN): "
          f"{'FIRES' if fires_at_open else 'no fire'} — {reason_at_open}")
    if not fires_at_open:
        print("  FAIL: window should be inclusive at 09:35:00")
        return False

    # 09:45:00 ET — window CLOSES exactly here (exclusive)
    now_at_close = datetime(2026, 5, 15, 9, 45, 0)
    bar_0940 = find_bar(bars, 9, 40)
    live_quote_2 = LiveQuote(
        bid=738.95,
        last=738.96,
        fetched_at_et=datetime(2026, 5, 15, 9, 44, 55),
    )
    fires_at_close, reason_at_close = live_price_level_break_fires(
        level=pml,
        live_quote=live_quote_2,
        prior_closed_bar=bar_0940,
        now_et=now_at_close,
    )
    print(f"  at 09:45:00 ET (window CLOSE): "
          f"{'FIRES' if fires_at_close else 'no fire'} — {reason_at_close}")
    if fires_at_close:
        print("  FAIL: window should be exclusive at 09:45:00")
        return False
    print("  PASS")
    return True


def case_7_stale_quote_aborts(bars: list[Bar], pml: Level) -> bool:
    """Case 7: a quote with fetched_at_et > 60s old should abort the trigger."""
    print("\n=== CASE 7: stale quote (>60s) aborts the trigger ===")
    now_et = datetime(2026, 5, 15, 9, 41, 30)
    stale_quote = LiveQuote(
        bid=738.95,
        last=738.96,
        fetched_at_et=datetime(2026, 5, 15, 9, 40, 0),  # 90s old
    )
    bar_0935 = find_bar(bars, 9, 35)
    fires, reason = live_price_level_break_fires(
        level=pml,
        live_quote=stale_quote,
        prior_closed_bar=bar_0935,
        now_et=now_et,
    )
    print(f"  with 90s-old quote: {'FIRES' if fires else 'no fire'} — {reason}")
    if fires:
        print("  FAIL: stale quote should abort the trigger")
        return False
    print("  PASS")
    return True


# ---- Entry point --------------------------------------------------------------------------------


def main() -> int:
    print("v15.3 live-price first-bar level-break — smoke test")
    print("=" * 72)

    target_date = "2026-05-15"
    csv_path = find_spy_5m_csv_for_date(target_date)
    if csv_path is None:
        print(f"ERROR: no spy_5m_*.csv found covering {target_date}")
        print(f"  Looked in: {[str(p) for p in DATA_DIR_CANDIDATES]}")
        return 2
    print(f"Using CSV: {csv_path}")

    bars = load_bars_for_date(csv_path, target_date)
    if not bars:
        print(f"ERROR: no bars loaded for {target_date} from {csv_path}")
        return 2
    print(f"Loaded {len(bars)} bars for {target_date}")

    # Sanity: print the key RTH bars
    print("\nKey RTH bars on 2026-05-15:")
    for hh, mm in [(9, 30), (9, 35), (9, 40), (9, 45), (9, 50)]:
        try:
            b = find_bar(bars, hh, mm)
            print(f"  {b.timestamp_et.time()}  O={b.open:.2f}  H={b.high:.2f}  "
                  f"L={b.low:.2f}  C={b.close:.2f}  V={b.volume}")
        except LookupError:
            print(f"  {hh:02d}:{mm:02d}  MISSING")

    # Construct the PML 739.04 named level
    pml = Level(
        price=PML_PRICE,
        type="support",
        tier=PML_TIER,
        stars=PML_STARS,
        source=PML_SOURCE,
    )

    # Run cases
    results = {
        "case_1_live_fires_in_window": case_1_live_price_fires_during_0940_bar(bars, pml),
        "case_2_closed_fires_at_0946": case_2_closed_bar_fires_at_0946_into_bounce(bars, pml),
        "case_3_v_reversal_no_refire": case_3_v_reversal_bar_closes_above_level(bars, pml),
        "case_4_level_qualifies": case_4_level_qualifies(pml),
        "case_5_reference_does_not_qualify": case_5_reference_level_does_not_qualify(),
        "case_6_window_boundaries": case_6_window_boundary_at_0935(bars, pml),
        "case_7_stale_quote_aborts": case_7_stale_quote_aborts(bars, pml),
    }

    print("\n" + "=" * 72)
    print("Results:")
    for name, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")

    if all(results.values()):
        print("\nOVERALL: PASS  ({}/{})".format(sum(results.values()), len(results)))
        return 0

    print("\nOVERALL: FAIL  ({}/{})".format(sum(results.values()), len(results)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
