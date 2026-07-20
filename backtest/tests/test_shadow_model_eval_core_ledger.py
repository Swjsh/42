"""Guard for the 2026-07-20 shadow-eval core-ledger fix.

ROOT CAUSE (queue.md SHADOWEVAL-WEEKLY-TRIGGER-VS-DAILY-DOCS investigation): the live
engine migrated from two per-account ledgers (automation/state/decisions.jsonl +
automation/state/aggressive/decisions.jsonl) to ONE consolidated both-accounts ledger
(automation/state/core-decisions.jsonl) around 2026-06-25. setup/scripts/shadow_model_eval.py
never followed the migration -- SAFE_LEDGER/BOLD_LEDGER kept pointing at the now-frozen
legacy files, so `Gamma_ShadowEval` fired daily (real logs exist for every weekday
2026-06-29..2026-07-20), Task Scheduler reported success, but the script printed
"No ticks found -- skipping" every single day and NO scorecard has been produced since
2026-06-24 -- a full month of silent C7 failure (a re-violated lesson: the same "silent
success is failure" class already fixed for other producers, never applied here because
nothing was watching this specific producer's real output, only its exit code).

This test guards the fix: load_ticks_for_date() now falls back to CORE_LEDGER (normalized
via _normalize_core_row) whenever the legacy per-account ledger has nothing for the
requested date, while leaving pre-migration (legacy-ledger-has-data) behavior untouched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "setup" / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO / "setup" / "scripts"))

import shadow_model_eval as sme  # noqa: E402


# --------------------------------------------------------------------------- #
# _normalize_core_row
# --------------------------------------------------------------------------- #


def _core_row(**overrides) -> dict:
    row = {
        "ts_et": "2026-07-20T14:01:02",
        "account": "safe",
        "spy": 744.54,
        "vix": 18.19,
        "ribbon": "BEAR",
        "spread_cents": 54.8,
        "htf_15m": "BEAR",
        "verdict": "ENTER_BEAR",
        "side": "P",
        "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
        "bear_score": 9,
        "bull_score": 7,
        "triggers": ["trendline_rejection"],
        "reason": "BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring",
        "exec": {"entry_px": 0.83, "tp": 1.17, "stop": 0.415},
    }
    row.update(overrides)
    return row


def test_normalize_core_row_maps_legacy_field_names():
    norm = sme._normalize_core_row(_core_row(), "safe", tick_id=7)
    assert norm is not None
    assert norm["date"] == "2026-07-20"
    assert norm["time_et"] == "14:01"
    assert norm["tick_id"] == 7
    assert norm["action"] == "ENTER_BEAR"
    assert norm["ribbon_stack"] == "BEAR"          # ribbon -> ribbon_stack
    assert norm["htf_15m_stack"] == "BEAR"         # htf_15m -> htf_15m_stack
    assert norm["setup_name"] == "BEARISH_REJECTION_RIDE_THE_RIBBON"  # setup -> setup_name
    assert norm["trigger"] == "trendline_rejection"  # triggers[0] -> trigger
    assert norm["bull_score"] == 7
    assert norm["bear_score"] == 9
    assert norm["entry_px"] == 0.83
    assert norm["tp1_px"] == 1.17
    assert norm["stop_px"] == 0.415
    # position_status not tracked in core-decisions.jsonl -> None, downstream defaults to "flat"
    assert norm["position_status"] is None


def test_normalize_core_row_wrong_account_returns_none():
    assert sme._normalize_core_row(_core_row(account="bold"), "safe", tick_id=0) is None


def test_normalize_core_row_missing_verdict_returns_none():
    row = _core_row()
    row["verdict"] = None
    assert sme._normalize_core_row(row, "safe", tick_id=0) is None


def test_normalize_core_row_malformed_ts_returns_none():
    assert sme._normalize_core_row(_core_row(ts_et="bad"), "safe", tick_id=0) is None
    assert sme._normalize_core_row(_core_row(ts_et=""), "safe", tick_id=0) is None


def test_normalize_core_row_no_triggers_gives_none_trigger():
    norm = sme._normalize_core_row(_core_row(triggers=[]), "safe", tick_id=0)
    assert norm["trigger"] is None


def test_normalize_core_row_missing_exec_block_gives_none_prices():
    row = _core_row()
    del row["exec"]
    norm = sme._normalize_core_row(row, "safe", tick_id=0)
    assert norm["entry_px"] is None
    assert norm["tp1_px"] is None
    assert norm["stop_px"] is None


# --------------------------------------------------------------------------- #
# load_ticks_for_date -- fallback to CORE_LEDGER
# --------------------------------------------------------------------------- #


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def test_load_ticks_falls_back_to_core_ledger_when_legacy_empty(tmp_path, monkeypatch):
    legacy = tmp_path / "decisions.jsonl"  # does not exist -> triggers fallback
    core = tmp_path / "core-decisions.jsonl"
    _write_jsonl(
        core,
        [
            _core_row(ts_et="2026-07-20T09:30:04", verdict="HOLD", account="safe"),
            _core_row(ts_et="2026-07-20T14:01:02", verdict="ENTER_BEAR", account="safe"),
            _core_row(ts_et="2026-07-20T09:31:04", verdict="HOLD", account="bold"),  # other acct
            _core_row(ts_et="2026-07-19T14:01:02", verdict="ENTER_BEAR", account="safe"),  # wrong date
        ],
    )
    monkeypatch.setattr(sme, "CORE_LEDGER", core)

    ticks = sme.load_ticks_for_date(legacy, "2026-07-20", account="safe")

    assert len(ticks) == 2  # only safe, only 2026-07-20
    actions = [t["action"] for t in ticks]
    assert actions == ["HOLD", "ENTER_BEAR"]  # sorted by tick_id/time_et ascending


def test_load_ticks_prefers_legacy_ledger_when_present(tmp_path, monkeypatch):
    """Pre-migration dates must stay byte-identical -- CORE_LEDGER must NOT be consulted
    when the legacy ledger already has data for the requested date."""
    legacy = tmp_path / "decisions.jsonl"
    core = tmp_path / "core-decisions.jsonl"
    _write_jsonl(
        legacy,
        [
            {
                "date": "2026-06-01",
                "time_et": "09:30",
                "tick_id": 1,
                "action": "HOLD",
                "bull_score": 3,
                "bear_score": 2,
            }
        ],
    )
    # If the fallback fired, this row would leak into the result -- it must NOT.
    _write_jsonl(core, [_core_row(ts_et="2026-06-01T09:30:04", verdict="ENTER_BEAR")])
    monkeypatch.setattr(sme, "CORE_LEDGER", core)

    ticks = sme.load_ticks_for_date(legacy, "2026-06-01", account="safe")

    assert len(ticks) == 1
    assert ticks[0]["action"] == "HOLD"


def test_load_ticks_no_account_no_fallback(tmp_path, monkeypatch):
    """Without an account hint (legacy call signature) the fallback must never fire --
    core-decisions.jsonl has no per-account isolation, so a account-less read could
    silently blend safe+bold ticks together."""
    legacy = tmp_path / "decisions.jsonl"  # missing
    core = tmp_path / "core-decisions.jsonl"
    _write_jsonl(core, [_core_row(ts_et="2026-07-20T09:30:04", verdict="HOLD")])
    monkeypatch.setattr(sme, "CORE_LEDGER", core)

    ticks = sme.load_ticks_for_date(legacy, "2026-07-20")

    assert ticks == []


def test_load_ticks_missing_core_ledger_fails_open(tmp_path, monkeypatch):
    legacy = tmp_path / "decisions.jsonl"  # missing
    core = tmp_path / "does-not-exist.jsonl"
    monkeypatch.setattr(sme, "CORE_LEDGER", core)

    ticks = sme.load_ticks_for_date(legacy, "2026-07-20", account="safe")

    assert ticks == []


# --------------------------------------------------------------------------- #
# Live-data sanity: the real ledger this fire actually fixed
# --------------------------------------------------------------------------- #


def test_live_core_ledger_produces_ticks_for_a_real_recent_date():
    """Regression pin against the REAL production ledger (not a fixture) -- proves the
    fix works end-to-end against live data, not just synthetic rows. Skips gracefully
    if the live ledger doesn't exist (e.g. a fresh checkout) rather than failing CI."""
    if not sme.CORE_LEDGER.exists():
        pytest.skip("live core-decisions.jsonl not present in this checkout")

    # Find a date known to be in the live ledger without hardcoding a specific day that
    # may eventually age out of any log-rotation policy: scan for the newest date present.
    newest_date = None
    with open(sme.CORE_LEDGER, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = str(row.get("ts_et") or "")
            if len(ts) >= 10:
                d = ts[:10]
                if newest_date is None or d > newest_date:
                    newest_date = d

    assert newest_date is not None, "live core-decisions.jsonl has no parseable ts_et rows"

    legacy_missing = _REPO / "automation" / "state" / "_does_not_exist_decisions.jsonl"
    ticks = sme.load_ticks_for_date(legacy_missing, newest_date, account="safe")
    assert len(ticks) > 0, (
        f"expected >0 normalized ticks for {newest_date} from the live core ledger "
        "-- if this fails, the fallback has regressed"
    )
