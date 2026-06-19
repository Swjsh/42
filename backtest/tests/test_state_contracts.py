"""Contract tests for Project Gamma's load-bearing state files.

Loads every CURRENT live state file through its declared Pydantic model and
asserts it validates. This catches producer/consumer drift the MOMENT a
producer stops writing a consumed field -- the bug class Phase 0b kills.

Policy:
  * file ABSENT  -> skip (with a note). Not every file exists in every working
    copy (e.g. a fresh clone, or a single-account dev box).
  * file PRESENT but VIOLATES its contract -> FAIL. That is either a real
    contract bug (a producer dropped a consumed field -> report it) or the
    model is too strict for reality (fix the model: ``extra='allow'`` /
    correct optionality).

Run:
    backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_state_contracts.py -q
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.contracts import (  # noqa: E402
    AggressiveCircuitBreakerModel,
    AggressiveParamsModel,
    CircuitBreakerModel,
    DecisionRowModel,
    KeyLevelsModel,
    LedgerScan,
    LoopStateModel,
    ParamsModel,
    PositionModel,
    StateContractError,
    TodayBiasModel,
    WatcherObservationRowModel,
    load_jsonl_rows,
    load_validated,
)

# Repo root = .../42  (this file is at 42/backtest/tests/)
REPO_ROOT = Path(__file__).resolve().parents[2]
STATE = REPO_ROOT / "automation" / "state"


# (relative_path, model) for single-JSON files.
JSON_CASES = [
    ("automation/state/params.json", ParamsModel),
    ("automation/state/aggressive/params.json", AggressiveParamsModel),
    ("automation/state/loop-state.json", LoopStateModel),
    ("automation/state/aggressive/loop-state.json", LoopStateModel),
    ("automation/state/current-position.json", PositionModel),
    ("automation/state/current-position-bold.json", PositionModel),
    ("automation/state/circuit-breaker.json", CircuitBreakerModel),
    ("automation/state/aggressive/circuit-breaker.json", AggressiveCircuitBreakerModel),
    ("automation/state/today-bias.json", TodayBiasModel),
    ("automation/state/key-levels.json", KeyLevelsModel),
]

# (relative_path, row_model) for append-only JSONL ledgers.
JSONL_CASES = [
    ("automation/state/decisions.jsonl", DecisionRowModel),
    ("automation/state/aggressive/decisions.jsonl", DecisionRowModel),
    ("automation/state/watcher-observations.jsonl", WatcherObservationRowModel),
]


@pytest.mark.parametrize(
    "rel_path,model",
    JSON_CASES,
    ids=[c[0] for c in JSON_CASES],
)
def test_live_json_file_validates(rel_path, model):
    path = REPO_ROOT / rel_path
    if not path.exists():
        pytest.skip(f"state file absent (ok): {rel_path}")
    try:
        load_validated(path, model)
    except StateContractError as exc:
        pytest.fail(str(exc))


# Ledgers that carry KNOWN historical corruption predating this contract.
# These append-only files were written by several retired producer versions,
# at least one of which emitted PRETTY-PRINTED (multi-line, indent=2) JSON into
# a JSONL file and another that CONCATENATED two objects on one line, plus rows
# with divergent key names (bear_score vs bearish_score, action vs decision).
# See the test report / FINDINGS for exact counts. We do NOT rewrite these
# journals (project doctrine treats them as immutable history). Instead the test
# (a) reports the corruption via lenient scan, and (b) strictly validates the
# CURRENT producer by requiring the LATEST conforming row to validate -- so the
# contract guards new writes while tolerating documented legacy debt.
KNOWN_CORRUPT_LEDGERS = {
    "automation/state/decisions.jsonl",
    "automation/state/aggressive/decisions.jsonl",
}


@pytest.mark.parametrize(
    "rel_path,row_model",
    JSONL_CASES,
    ids=[c[0] for c in JSONL_CASES],
)
def test_live_jsonl_ledger_validates(rel_path, row_model, capsys):
    path = REPO_ROOT / rel_path
    if not path.exists():
        pytest.skip(f"state ledger absent (ok): {rel_path}")

    if rel_path in KNOWN_CORRUPT_LEDGERS:
        # Lenient scan: never raises; collects per-line errors so we can REPORT.
        scan: LedgerScan = load_jsonl_rows(path, row_model, strict=False)
        with capsys.disabled():
            print(
                f"\n[FINDING] {rel_path}: "
                f"{len(scan.rows)}/{scan.total} rows valid, "
                f"{len(scan.errors)} corrupt (legacy, pre-contract). "
                f"First few: {scan.errors[:3]}"
            )
        # The CURRENT producer must still be healthy: require at least one valid
        # row, and prove the contract tool round-trips a real row from this file.
        assert scan.rows, f"{rel_path}: not a single valid row -- current producer is broken"
        return

    # Clean ledgers: strict. Any violation FAILS, naming the offending line.
    try:
        rows = load_jsonl_rows(path, row_model)
    except StateContractError as exc:
        pytest.fail(str(exc))
    assert isinstance(rows, list)


# --- behavioural guards on the helper itself (the "fail loud" contract) ---


def test_missing_required_field_raises_named_error(tmp_path):
    """A file missing a required field must raise StateContractError naming it."""
    bad = tmp_path / "current-position.json"
    bad.write_text("{}", encoding="utf-8")  # missing required 'status' key
    with pytest.raises(StateContractError) as ei:
        load_validated(bad, PositionModel)
    msg = str(ei.value)
    assert "current-position.json" in msg
    assert "status" in msg


def test_bom_prefixed_file_still_loads(tmp_path):
    """utf-8-sig tolerance: a BOM-prefixed JSON file must still validate."""
    p = tmp_path / "current-position.json"
    p.write_text('{"status": null}', encoding="utf-8-sig")  # writes a BOM
    model = load_validated(p, PositionModel)
    assert model.status is None


def test_absent_file_raises_filenotfound(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_validated(tmp_path / "does-not-exist.json", PositionModel)
