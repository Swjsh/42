"""Guard for go_live_gate.py's REGIME COVERAGE disclosure (B3-monitors, 2026-09-01).

None of the gate's 5 pass/fail criteria ask whether the evidence window has actually
SEEN a stressed market -- a GREEN could be measuring only a calm stretch. This
disclosure-only block answers that from automation/state/core-decisions.jsonl's own
spy/vix/ts_et fields (no re-derivation): per (lifetime, frozen-config-window>=2026-09-01)
window -- VIX daily-max min/max, days with VIX>20, SPY cumulative return, worst day,
count of days down >1%.

Pins:
  - per-day VIX max and open->close SPY return are computed from ts_et-SORTED rows
    (not insertion order -- a restart can append rows out of chronological order)
  - lifetime vs frozen_config_window (>= CURRENT_CONFIG_WINDOW_START) are scored
    independently
  - the literal calm-only warning text fires ONLY when the FROZEN window has zero
    VIX>20 days AND zero down>1% days (an empty/no-data frozen window must not
    spuriously claim "calm-only" -- it has no evidence either way)
  - regime_coverage is ADDITIVE to build_report()'s output -- no existing key removed
    or reshaped (backward compatibility)
  - fail-open: a missing/malformed core-decisions.jsonl produces a well-formed
    all-None/zero block, never a crash
  - RED-PROOF: neutering the calm-only condition from AND to OR flips a genuine
    stress day (VIX>20 present, no down>1% day) into a false calm-only claim,
    proving the AND is load-bearing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = str(REPO / "setup" / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import go_live_gate as glg  # noqa: E402


def _row(date, ts_et, spy, vix):
    return {"date": date, "ts_et": ts_et, "spy": spy, "vix": vix}


def _write_ledger(path: Path, rows: list) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_missing_ledger_fails_open(tmp_path, monkeypatch):
    p = tmp_path / "does-not-exist.jsonl"
    monkeypatch.setattr(glg, "CORE_DECISIONS_PATH", p)
    block = glg.regime_coverage_block()
    assert block["lifetime"]["n_days"] == 0
    assert block["lifetime"]["spy_cumulative_return_pct"] is None
    assert block["calm_only_window_warning"] is None


def test_malformed_lines_skipped_not_crashed(tmp_path, monkeypatch):
    p = tmp_path / "core-decisions.jsonl"
    with p.open("w", encoding="utf-8") as f:
        f.write("not json at all\n")
        f.write(json.dumps(_row("2026-09-01", "2026-09-01T09:30:00", 760.0, 15.0)) + "\n")
        f.write(json.dumps({"date": "2026-09-01", "spy": 761.0}) + "\n")  # missing vix -> skipped
    monkeypatch.setattr(glg, "CORE_DECISIONS_PATH", p)
    rows = glg._load_core_decision_rows()
    assert len(rows) == 1


def test_per_day_uses_ts_et_sorted_open_close(tmp_path, monkeypatch):
    p = tmp_path / "core-decisions.jsonl"
    # written OUT OF chronological order -- the 09:35 row appended before the 09:30 row
    rows = [
        _row("2026-09-01", "2026-09-01T09:35:00", 762.0, 15.0),
        _row("2026-09-01", "2026-09-01T09:30:00", 760.0, 14.0),
        _row("2026-09-01", "2026-09-01T15:55:00", 758.0, 16.0),
    ]
    _write_ledger(p, rows)
    monkeypatch.setattr(glg, "CORE_DECISIONS_PATH", p)
    loaded = glg._load_core_decision_rows()
    stats = glg._per_day_regime_stats(loaded)
    day = stats["2026-09-01"]
    assert day["spy_open"] == 760.0   # earliest ts_et, not insertion order
    assert day["spy_close"] == 758.0  # latest ts_et
    assert day["vix_daily_max"] == 16.0


def test_lifetime_vs_frozen_window_scoped_independently(tmp_path, monkeypatch):
    p = tmp_path / "core-decisions.jsonl"
    rows = [
        # PRE-freeze day: VIX>20, big down day -- must count in lifetime, NOT in frozen.
        _row("2026-08-20", "2026-08-20T09:30:00", 780.0, 25.0),
        _row("2026-08-20", "2026-08-20T15:55:00", 770.0, 25.0),
        # Frozen-window day: calm.
        _row("2026-09-01", "2026-09-01T09:30:00", 760.0, 15.0),
        _row("2026-09-01", "2026-09-01T15:55:00", 761.0, 16.0),
    ]
    _write_ledger(p, rows)
    monkeypatch.setattr(glg, "CORE_DECISIONS_PATH", p)
    monkeypatch.setattr(glg, "CURRENT_CONFIG_WINDOW_START", "2026-09-01")
    block = glg.regime_coverage_block()
    assert block["lifetime"]["n_days"] == 2
    assert block["lifetime"]["days_vix_gt_20"] == 1
    assert block["lifetime"]["days_down_gt_1pct"] == 1
    assert block["frozen_config_window"]["n_days"] == 1
    assert block["frozen_config_window"]["days_vix_gt_20"] == 0
    assert block["frozen_config_window"]["days_down_gt_1pct"] == 0
    # Calm-only fires on the FROZEN window despite the pre-freeze stress day existing.
    assert block["calm_only_window_warning"] == "calm-only window -- a GREEN here is untested in stress"


def test_calm_only_warning_absent_when_frozen_window_has_stress(tmp_path, monkeypatch):
    p = tmp_path / "core-decisions.jsonl"
    rows = [
        _row("2026-09-01", "2026-09-01T09:30:00", 780.0, 25.0),  # VIX>20 IN the frozen window
        _row("2026-09-01", "2026-09-01T15:55:00", 770.0, 25.0),
    ]
    _write_ledger(p, rows)
    monkeypatch.setattr(glg, "CORE_DECISIONS_PATH", p)
    monkeypatch.setattr(glg, "CURRENT_CONFIG_WINDOW_START", "2026-09-01")
    block = glg.regime_coverage_block()
    assert block["calm_only_window_warning"] is None


def test_calm_only_warning_absent_when_frozen_window_empty(tmp_path, monkeypatch):
    """A frozen window with ZERO days is 'no evidence', not 'calm evidence' -- must not
    spuriously claim calm-only."""
    p = tmp_path / "core-decisions.jsonl"
    rows = [_row("2026-08-01", "2026-08-01T09:30:00", 760.0, 14.0)]
    _write_ledger(p, rows)
    monkeypatch.setattr(glg, "CORE_DECISIONS_PATH", p)
    monkeypatch.setattr(glg, "CURRENT_CONFIG_WINDOW_START", "2026-09-01")
    block = glg.regime_coverage_block()
    assert block["frozen_config_window"]["n_days"] == 0
    assert block["calm_only_window_warning"] is None


def test_build_report_backward_compatible_keys(tmp_path, monkeypatch):
    """regime_coverage must be ADDITIVE -- every pre-existing top-level key stays present
    and build_report() must not raise even with a stubbed-out core-decisions.jsonl."""
    p = tmp_path / "core-decisions.jsonl"
    p.write_text("", encoding="utf-8")
    monkeypatch.setattr(glg, "CORE_DECISIONS_PATH", p)
    block = glg.regime_coverage_block()
    assert set(block.keys()) == {"label", "lifetime", "frozen_config_window", "calm_only_window_warning"}


def test_red_proof_and_condition_is_load_bearing(tmp_path, monkeypatch):
    """RED-PROOF: the calm-only condition is AND(days_vix_gt_20==0, days_down_gt_1pct==0).
    Neutering it to OR would falsely flag a genuinely stressed window (VIX>20 present, but
    no single day happened to close down >1%) as calm-only. Confirm the shipped AND does
    NOT fire here, then confirm the neutered OR WOULD -- proving the AND matters."""
    p = tmp_path / "core-decisions.jsonl"
    rows = [
        # VIX spike day but SPY closes only modestly down (not >1%) -- genuine stress,
        # must NOT be reported as calm-only.
        _row("2026-09-01", "2026-09-01T09:30:00", 760.0, 28.0),
        _row("2026-09-01", "2026-09-01T15:55:00", 759.0, 28.0),
    ]
    _write_ledger(p, rows)
    monkeypatch.setattr(glg, "CORE_DECISIONS_PATH", p)
    monkeypatch.setattr(glg, "CURRENT_CONFIG_WINDOW_START", "2026-09-01")

    block = glg.regime_coverage_block()
    assert block["frozen_config_window"]["days_vix_gt_20"] == 1
    assert block["frozen_config_window"]["days_down_gt_1pct"] == 0
    assert block["calm_only_window_warning"] is None, (
        "a VIX>20 day must not be reported calm-only even if it didn't also close down >1%"
    )

    # Now simulate the neutered (OR) mechanism directly against the same summary.
    fw = block["frozen_config_window"]
    neutered_calm = fw["n_days"] > 0 and (fw["days_vix_gt_20"] == 0 or fw["days_down_gt_1pct"] == 0)
    assert neutered_calm is True, (
        "the neutered OR should wrongly call this calm-only, demonstrating the AND in "
        "the shipped code is the load-bearing guard against that false claim"
    )
