"""Regression guard for self_check.check_engine_tradeability — the DATA-GATED-vs-FAULT split.

THE FOOT-GUN (2026-06-30, L189): `check_engine_tradeability` flagged "ENGINE CANNOT ENTER"
as BROKEN on ANY trigger-fired-but-gate-blocked SKIP, including `SKIP_ELITE_BULL_LEVEL_RECLAIM`.
But the 2026-06-30 bull-unblock audit CLOSED that thread: `block_elite_bull` is proven KEEP
(removed cohort net -$241 on the fresh OPRA window, DRY_AT_ZERO), `detect_sequence_reclaim` is
structurally coupled off, and the whole 0DTE-SPY bull frontier is DATA-GATED, not a bug. So the
live self-check sat perpetually-RED on validated-correct behavior (386 ticks / 0 ENTER / 32x
SKIP_ELITE_BULL on a bull day) — which is the exact "persistently-RED audit masks new orphans"
anti-pattern: a GENUINE future "cannot enter" fault (an unexpected block, or the live BEAR
direction failing to convert) would hide behind the always-on RED.

THE FIX: only a NON-data-gated block verdict is BROKEN; a validated data-gated block is the
engine correctly sitting out (silent). High-conviction-no-trigger is flagged ONLY on the LIVE
bear direction (a real detector concern) — the bull straddle-only reclaim gap is the closed,
data-gated structural condition and stays silent.

This guard pins that split so a refactor can't silently re-broaden the monitor back to
perpetual-RED (mask) OR silently swallow a genuine fault (miss). $0, pure-Python, no network.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MOD_PATH = REPO / "setup" / "scripts" / "self_check.py"

_spec = importlib.util.spec_from_file_location("self_check", MOD_PATH)
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)

# A fixed weekday, after 10:30 ET so the tradeability check actually runs.
NOW = dt.datetime(2026, 6, 30, 11, 0, 0)  # Tuesday 11:00
DAY = NOW.strftime("%Y-%m-%d")


def _row(verdict, *, bull=5, bear=5, triggers=None, account="safe", i=0):
    return {
        "ts_et": f"{DAY}T{10 + i // 60:02d}:{i % 60:02d}:00",
        "account": account,
        "verdict": verdict,
        "bull_score": bull,
        "bear_score": bear,
        "triggers": triggers if triggers is not None else [],
    }


def _write(tmp_path, rows) -> Path:
    p = tmp_path / "core-decisions.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return p


def test_constant_contains_the_validated_elite_bull_block():
    """The data-gated benign set MUST contain the proven-KEEP block (thread-closed 2026-06-30)."""
    assert "SKIP_ELITE_BULL_LEVEL_RECLAIM" in sc._DATA_GATED_BLOCK_VERDICTS


def test_all_elite_bull_blocks_are_silent(tmp_path):
    """GOLDEN: 32x SKIP_ELITE_BULL with triggers + high bull scores, 0 ENTER -> NOT flagged.
    This is the exact live 2026-06-30 signature; the fix flips it BROKEN->GREEN."""
    rows = [_row("SKIP_ELITE_BULL_LEVEL_RECLAIM", bull=10, bear=3, triggers=["level_reclaim"], i=i)
            for i in range(60)]
    out = sc.check_engine_tradeability(NOW, _write(tmp_path, rows))
    assert out == [], f"data-gated bull sit-out must be silent, got {out}"


def test_bull_high_conviction_no_trigger_is_silent(tmp_path):
    """The straddle-only reclaim gap (bull>=9, no trigger) is the CLOSED data-gated condition."""
    rows = [_row("HOLD", bull=10, bear=2, triggers=[], i=i) for i in range(60)]
    out = sc.check_engine_tradeability(NOW, _write(tmp_path, rows))
    assert out == [], f"bull straddle-gap must be silent, got {out}"


def test_unexpected_block_still_flags_broken(tmp_path):
    """BITE (non-vacuous): a NON-data-gated block with triggers MUST still flag ENGINE CANNOT ENTER
    -> proves the suppression is scoped to the benign verdict, not a blanket mute."""
    rows = [_row("SKIP_LIQUIDITY", bull=3, bear=10, triggers=["rejection"], i=i) for i in range(60)]
    out = sc.check_engine_tradeability(NOW, _write(tmp_path, rows))
    assert any("CANNOT ENTER" in p for p in out), f"real block must flag, got {out}"
    # and it must escalate to BROKEN severity: run()'s _broken predicate keys on 'CANNOT ENTER'
    assert any("CANNOT ENTER" in p for p in out)


def test_mixed_benign_plus_one_real_block_flags_the_real_one(tmp_path):
    """A day dominated by benign blocks but with ONE unexpected block still surfaces the fault."""
    rows = [_row("SKIP_ELITE_BULL_LEVEL_RECLAIM", bull=10, bear=3, triggers=["level_reclaim"], i=i)
            for i in range(58)]
    rows += [_row("SKIP_LIQUIDITY", bull=3, bear=9, triggers=["rejection"], i=58 + j) for j in range(2)]
    out = sc.check_engine_tradeability(NOW, _write(tmp_path, rows))
    assert any("CANNOT ENTER" in p and "SKIP_LIQUIDITY" in p for p in out), out


def test_live_bear_high_conviction_no_trigger_flags(tmp_path):
    """The LIVE bear direction scoring high with no trigger IS a genuine detector concern -> flag
    (DEGRADED, not BROKEN — 'NOT ENTERING' does not match the _broken predicate)."""
    rows = [_row("HOLD", bull=2, bear=10, triggers=[], i=i) for i in range(60)]
    out = sc.check_engine_tradeability(NOW, _write(tmp_path, rows))
    assert any("NOT ENTERING (bear)" in p for p in out), out


def test_enter_present_is_always_fine(tmp_path):
    """If the engine reached ENTER, tradeability is fine regardless of blocks."""
    rows = [_row("SKIP_ELITE_BULL_LEVEL_RECLAIM", bull=10, bear=3, triggers=["level_reclaim"], i=i)
            for i in range(59)]
    rows += [_row("ENTER_BEAR", bull=3, bear=10, triggers=["rejection"], i=59)]
    out = sc.check_engine_tradeability(NOW, _write(tmp_path, rows))
    assert out == [], out


def test_weekend_and_early_are_skipped(tmp_path):
    """Off-hours / weekend -> no judgement (not enough session elapsed)."""
    rows = [_row("SKIP_LIQUIDITY", bull=3, bear=10, triggers=["rejection"], i=i) for i in range(60)]
    p = _write(tmp_path, rows)
    saturday = dt.datetime(2026, 6, 27, 11, 0, 0)  # Saturday
    early = dt.datetime(2026, 6, 30, 9, 45, 0)      # weekday but before 10:30
    assert sc.check_engine_tradeability(saturday, p) == []
    assert sc.check_engine_tradeability(early, p) == []
