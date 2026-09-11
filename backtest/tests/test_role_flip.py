"""T7 role-flip: support-broken-becomes-resistance (2026-07-09, SHADOW-ONLY).

J's entire 2026-07-08 edge: the ~745.4 shelf was SUPPORT on 07-07 (respected all session --
multiple touches/wicks, closes above), broke overnight, and was THEREFORE RESISTANCE on 07-08 --
confirmed live by the 13:30 ET tag-746.09 / close-744.39 rejection off it. No producer held this
concept: key-levels.json (the LIVE file) tagged 745.21 "support" ALL DAY on 07-08 even while
price was rejecting it from ABOVE (setup/scripts/refresh_levels_intraday.py's SEMANTIC_SOURCE_ROLE
keeps live roles STATIC on purpose -- the 2026-06-30 "flip-flop bug" fix -- so this concept is
implemented SHADOW-ONLY here and must never touch that file or key-levels.json).

`backtest/lib/watchers/level_memory.py`'s `_score_and_role` already flips a level's causal
`role` on the FIRST decisive close through it (BREAK_MARGIN) -- correct for scoring memory
(`role_flips`) but too eager to REPORT as a confirmed regime change (a single 15c close that
reverts next bar is noise). `detect_role_flip` adds a stricter, opt-in SUSTAINED + memory-scored
confirmation gate (module comment there explains the ROLE_FLIP_SUSTAIN_BARS=3 /
ROLE_FLIP_MEMORY_THRESHOLD=50.0 defaults) and tags `flipped_at` (ISO ET) + `provenance`.
`setup/scripts/level_memory_producer.py::apply_role_flip` wires it into the shadow file
(automation/state/key-levels-memory.json) ONLY.

This file has three layers, cheapest-to-most-expensive:
  1. TestDetectRoleFlipUnit    -- the pure gate function, hand-built Level + synthetic bars.
  2. TestApplyRoleFlipWiring   -- the producer's dict-merging wrapper, synthetic Levels.
  3. TestGolden745RoleFlip     -- the REAL 2026-07-07->07-08 SPY tape (not a hand-built fixture
                                  -- backtest/data/spy_5m_2026-05-19_2026-07-08.csv), proving the
                                  whole story end to end, including the noise-suppression design
                                  surviving the real 13:20-13:30 whipsaw.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

_BT = Path(__file__).resolve().parents[1]
if str(_BT) not in sys.path:
    sys.path.insert(0, str(_BT))

from lib.watchers.level_memory import (  # noqa: E402
    Level,
    LevelMemory,
    ROLE_FLIP_MEMORY_THRESHOLD,
    ROLE_FLIP_SUSTAIN_BARS,
    detect_role_flip,
)


def _prod():
    """Load setup/scripts/level_memory_producer.py as a module (it's a script, not a package)."""
    repo = _BT.parent
    spec = importlib.util.spec_from_file_location(
        "level_memory_producer", repo / "setup" / "scripts" / "level_memory_producer.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["level_memory_producer"] = m
    spec.loader.exec_module(m)
    return m


def _bars(n: int, start: str = "2026-07-08 09:30") -> pd.DataFrame:
    """Minimal ET-timestamped frame. detect_role_flip only reads df['timestamp_et'] (the Level
    object already carries every price/score/index fact it needs) -- OHLC content is irrelevant
    to the pure gate, so it's omitted here to keep the unit tests obviously minimal."""
    ts = pd.date_range(start=start, periods=n, freq="5min", tz="America/New_York")
    return pd.DataFrame({"timestamp_et": ts})


def _lvl(price=745.40, role="resistance", mem=111.0, role_flips=14, last_flip_idx=3,
         last_touch_idx=9) -> Level:
    return Level(price=price, role=role, memory_score=mem, touches=int(mem // 2), wicks=1,
                 bars_consolidated=10, role_flips=role_flips, first_seen_idx=0,
                 last_touch_idx=last_touch_idx, last_flip_idx=last_flip_idx)


def _load_full_tape() -> pd.DataFrame:
    """Full real SPY 5m tape through 2026-07-08 close (premarket + RTH) -- the real 07-07->07-08
    745.40 flip J traded live. Real equity data, not a hand-built fixture: the strongest
    available proof this behavior isn't curve-fit."""
    csv = _BT / "data" / "spy_5m_2026-05-19_2026-07-08.csv"
    df = pd.read_csv(csv)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    return df


def _idx_at(df: pd.DataFrame, date: str, time: str) -> int:
    mask = (df["timestamp_et"].dt.date == pd.Timestamp(date).date()) & (
        df["timestamp_et"].dt.strftime("%H:%M") == time
    )
    rows = df[mask].index
    assert len(rows), f"no bar at {date} {time} in the fixture"
    return int(rows[0])


# ── 1. Pure gate function ─────────────────────────────────────────────────────

class TestDetectRoleFlipUnit:
    def test_confirms_flip_when_sustained_and_scored(self):
        """last_flip_idx=3, up_to_idx=9 -> 7 bars sustained >= ROLE_FLIP_SUSTAIN_BARS(3);
        memory_score=111 >= ROLE_FLIP_MEMORY_THRESHOLD(50) -> CONFIRMED."""
        df = _bars(10)
        lvl = _lvl(last_flip_idx=3)
        role, flipped_at, prov = detect_role_flip(lvl, df, up_to_idx=9)

        assert role == "resistance"
        assert flipped_at == df["timestamp_et"].iloc[3].isoformat()
        assert "745.40" in prov
        assert "memory_score=111" in prov
        assert "threshold 50" in prov

    def test_falls_back_to_prior_role_when_insufficient_sustain(self):
        """last_flip_idx=8, up_to_idx=9 -> only 2 bars sustained < sustain_bars(3): the flip is
        too fresh to confirm. Must report the PRIOR role (support, the opposite of the raw
        just-flipped "resistance"), with NO flipped_at/provenance -- this is the exact
        single-bar-whipsaw case BREAK_MARGIN alone lets through as noise."""
        df = _bars(10)
        lvl = _lvl(last_flip_idx=8)
        role, flipped_at, prov = detect_role_flip(lvl, df, up_to_idx=9)

        assert role == "support"
        assert flipped_at is None
        assert prov is None

    def test_gate_skipped_below_memory_threshold(self):
        """A well-sustained flip on a WEAK level (score < 50) is not worth confirming --
        untested levels flip too often to alert on. Passes the raw role through unchanged."""
        df = _bars(10)
        lvl = _lvl(mem=10.0, last_flip_idx=0)  # sustained since bar 0, but score too low
        role, flipped_at, prov = detect_role_flip(lvl, df, up_to_idx=9)

        assert role == "resistance"  # unchanged passthrough, not flipped-to-prior
        assert flipped_at is None
        assert prov is None

    def test_gate_skipped_when_never_flipped(self):
        """A level built via the OLD keyword-only Level(...) call sites (role_flips=0,
        last_flip_idx defaults to -1) must not spuriously report a flip -- backward-compat
        regression guard for existing Level(...) construction across the test suite."""
        lvl = Level(price=750.0, role="resistance", memory_score=100.0, touches=50, wicks=5,
                    bars_consolidated=5, role_flips=0, first_seen_idx=0, last_touch_idx=5)
        df = _bars(10)
        role, flipped_at, prov = detect_role_flip(lvl, df, up_to_idx=9)

        assert role == "resistance"
        assert flipped_at is None and prov is None

    def test_idempotent_flipped_at_across_later_bars(self):
        """Once confirmed, later calls at ADVANCING up_to_idx (no new flip) must keep reporting
        the SAME flipped_at -- it doesn't drift, re-trigger, or thrash every run."""
        df = _bars(20)
        lvl = _lvl(last_flip_idx=3)

        r1 = detect_role_flip(lvl, df, up_to_idx=9)
        r2 = detect_role_flip(lvl, df, up_to_idx=15)
        r3 = detect_role_flip(lvl, df, up_to_idx=19)

        assert r1[0] == r2[0] == r3[0] == "resistance"
        assert r1[1] == r2[1] == r3[1]  # identical flipped_at every time

    def test_custom_sustain_and_threshold_params_respected(self):
        """Params are overridable (not hardcoded globals) -- a level that fails the DEFAULT
        gate can pass a looser caller-supplied one, and vice versa."""
        df = _bars(10)
        lvl = _lvl(mem=30.0, last_flip_idx=8)  # 2 bars sustained, score 30

        # default gate (sustain=3, threshold=50): score too low -> passthrough unchanged
        role, flipped_at, _ = detect_role_flip(lvl, df, up_to_idx=9)
        assert role == "resistance" and flipped_at is None

        # loosen both: now confirms
        role, flipped_at, prov = detect_role_flip(
            lvl, df, up_to_idx=9, sustain_bars=2, memory_threshold=20.0)
        assert role == "resistance" and flipped_at is not None
        assert "threshold 20" in prov


# ── 2. Producer wiring (dict merge) ───────────────────────────────────────────

class TestApplyRoleFlipWiring:
    def test_tags_dicts_with_confirmed_flip(self):
        prod = _prod()
        df = _bars(10)
        raw = [_lvl(last_flip_idx=3)]
        selected = prod.select_levels(raw)
        out = prod.apply_role_flip(selected, raw, df, up_to_idx=9)

        assert len(out) == 1
        assert out[0]["role"] == "resistance" and out[0]["type"] == "resistance"
        assert out[0]["flipped_at"] == df["timestamp_et"].iloc[3].isoformat()
        assert "745.40" in out[0]["provenance"]

    def test_falls_back_to_prior_role_in_dict_when_not_sustained(self):
        prod = _prod()
        df = _bars(10)
        raw = [_lvl(last_flip_idx=8)]  # too fresh
        selected = prod.select_levels(raw)
        out = prod.apply_role_flip(selected, raw, df, up_to_idx=9)

        assert out[0]["role"] == "support" and out[0]["type"] == "support"
        assert out[0]["flipped_at"] is None and out[0]["provenance"] is None
        # label must be kept in sync with the corrected role, not stay stale ("MEMORY_RES_...")
        assert out[0]["label"].startswith("MEMORY_SUP_"), out[0]["label"]

    def test_every_output_dict_carries_flip_keys(self):
        """Schema consistency: flipped_at/provenance keys always present (None default) so
        downstream consumers (dashboard, confluence_producer) can rely on key presence."""
        prod = _prod()
        df = _bars(10)
        raw = [_lvl(price=745.40, last_flip_idx=3), _lvl(price=750.0, mem=5.0, last_flip_idx=0)]
        selected = prod.select_levels(raw)
        out = prod.apply_role_flip(selected, raw, df, up_to_idx=9)

        assert all("flipped_at" in d and "provenance" in d for d in out)


# ── 3. Golden: the real 2026-07-07 -> 2026-07-08 745.40 tape ─────────────────

class TestGolden745RoleFlip:
    """Reproduces J's real read using the actual SPY 5m tape (not synthetic)."""

    def test_level_was_support_before_the_overnight_break(self):
        df = _load_full_tape()
        lm = LevelMemory(df)
        i = _idx_at(df, "2026-07-07", "15:55")  # 07-07 EOD, before the overnight break
        snap = lm.snapshot(i, lookback_days=10)

        cands = [L for L in snap.levels if abs(L.price - 745.40) <= 0.50]
        assert cands, (
            "no level near J's 745.40 shelf at 07-07 EOD; levels="
            f"{[(round(L.price, 2), L.role, round(L.memory_score, 1)) for L in snap.levels[:10]]}"
        )
        confirmed = [detect_role_flip(L, lm.df, i) for L in cands]
        assert any(role == "support" for role, _, _ in confirmed), (
            f"expected >=1 candidate near 745.40 confirmed SUPPORT before the break, got {confirmed}"
        )

    def test_level_flip_confirmed_and_explains_the_1330_rejection(self):
        df = _load_full_tape()
        lm = LevelMemory(df)
        i = _idx_at(df, "2026-07-08", "13:30")
        snap = lm.snapshot(i, lookback_days=10)

        cands = [L for L in snap.levels if abs(L.price - 745.40) <= 0.50]
        assert cands, (
            "no level near J's 745.40 shelf at 07-08 13:30; levels="
            f"{[(round(L.price, 2), L.role, round(L.memory_score, 1)) for L in snap.levels[:10]]}"
        )

        results = [(L,) + detect_role_flip(L, lm.df, i) for L in cands]
        flipped = [(L, flipped_at, prov) for (L, role, flipped_at, prov) in results
                   if role == "resistance" and flipped_at is not None]
        assert flipped, (
            "no candidate near 745.40 shows a CONFIRMED sustained flip to resistance at "
            f"07-08 13:30 -- got {[(round(L.price, 2), role, fa) for (L, role, fa, _) in results]}"
        )

        lvl, flipped_at, prov = flipped[0]
        flip_ts = pd.Timestamp(flipped_at)
        rth_open = pd.Timestamp("2026-07-08 09:30", tz="America/New_York")
        assert flip_ts < rth_open, (
            "expected the flip to be confirmed BEFORE the 09:30 RTH open (J's 'broke overnight' "
            f"read) -- got flipped_at={flipped_at}"
        )
        assert f"{lvl.memory_score:.0f}" in prov
        assert "threshold 50" in prov

        # The 13:30 bar itself must be a REJECTION -- this is the live confirmation J traded off
        # (real high 746.09 / real close 745.55, both from the CSV -- see module docstring).
        assert snap.interaction.kind == "reject", (
            f"07-08 13:30 interaction was '{snap.interaction.kind}', expected 'reject'. "
            f"detail={snap.interaction.detail}"
        )

    def test_producer_wiring_confirms_the_flip_by_midday(self):
        """End-to-end through the ACTUAL producer path (select_levels + apply_role_flip,
        including the dedup-into-zones step) -- proves the wiring, not just the pure engine."""
        prod = _prod()
        df = _load_full_tape()
        i = _idx_at(df, "2026-07-08", "12:00")  # well past the overnight break, before the
        sliced = df.iloc[: i + 1].reset_index(drop=True)  # 13:20-13:30 whipsaw -- clean midday read
        levels = prod.build_levels(sliced)

        near = [d for d in levels if abs(d["price"] - 745.40) <= 0.50]
        assert near, f"no ~745.40 zone in producer output: {[d['price'] for d in levels]}"
        confirmed = [d for d in near if d["role"] == "resistance" and d["flipped_at"]]
        assert confirmed, f"producer output near 745.40 has no confirmed flip: {near}"
        assert "2026-07-08T04" in confirmed[0]["flipped_at"], (
            "expected the confirmed flip to trace back to the overnight/premarket break "
            f"(~04:xx ET), got {confirmed[0]['flipped_at']}"
        )

    def test_producer_wiring_resists_the_1330_whipsaw(self):
        """The same zone, evaluated exactly at the noisy 13:30 bar where the raw per-bar walk
        whipsaws (a fresh single-bar reversal that reverts within the same bar's neighborhood):
        the wired producer output must still report role=resistance (not flip to support on the
        single fresh close) -- the whole point of the sustain gate, proven through the full
        pipeline, not just the pure function."""
        prod = _prod()
        df = _load_full_tape()
        i = _idx_at(df, "2026-07-08", "13:30")
        sliced = df.iloc[: i + 1].reset_index(drop=True)
        levels = prod.build_levels(sliced)

        near = [d for d in levels if abs(d["price"] - 745.40) <= 0.50]
        assert near, f"no ~745.40 zone in producer output at 13:30: {[d['price'] for d in levels]}"
        assert all(d["role"] == "resistance" for d in near), (
            f"expected the 745.40 zone to STILL read resistance through the 13:30 whipsaw, got {near}"
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
