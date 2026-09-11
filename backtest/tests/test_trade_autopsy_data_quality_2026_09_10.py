"""Guard for W11 (GOAL-WHY-THIS-WEEK-2026-09-10): Gamma_TradeAutopsy's exit_shape_parity_study
bar-fetch component can 403 on Alpaca's options-bar endpoint (OPRA indexing-lag right after the
16:00 ET close -- reproduced live this session, not an entitlement/malformed-request defect),
write pnl_status="unverified_no_bars" to trade-autopsy-last.json, and STILL exit 0 (main()'s
deliberate notify-only contract). Task Scheduler reads that fire GREEN. The pre-existing
output_freshness check in scheduled_task_staleness.py only asks "did the timestamp advance" --
it never reads pnl_status, so a completely blind day passes it too.

check_trade_autopsy_data_quality() is the content-level check that closes this gap: RED when
pnl_status == "unverified_no_bars", GREEN for "verified"/"flat", UNKNOWN when the file is
missing/unreadable. This file pins that behavior and the fact that a RED here reaches
STATUS.md's Known-broken channel via post_output_freshness_status().

RED-PROOF: before this change, `scheduled_task_staleness.check_trade_autopsy_data_quality`
did not exist and `Gamma_TradeAutopsy` was not even in TASK_OUTPUT_MAP -- test_function_exists
below fails on pre-fix code with AttributeError, and test_unverified_no_bars_is_red fails
because the RED verdict + the STATUS.md wiring did not exist. Both pass after the fix.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "setup" / "scripts" / "scheduled_task_staleness.py"


def _load():
    spec = importlib.util.spec_from_file_location("scheduled_task_staleness_dq", MODULE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["scheduled_task_staleness_dq"] = mod
    spec.loader.exec_module(mod)
    return mod


sts = _load()


def _write_last_json(root: Path, payload: dict) -> None:
    state = root / "automation" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "trade-autopsy-last.json").write_text(json.dumps(payload), encoding="utf-8")


def test_function_exists():
    """Pre-fix code has no such attribute -- this alone is the RED half of the RED-proof."""
    assert hasattr(sts, "check_trade_autopsy_data_quality")


def test_unverified_no_bars_is_red(tmp_path):
    _write_last_json(tmp_path, {
        "date": "2026-09-10", "pnl_status": "unverified_no_bars",
        "n_no_bars": 4, "n_positions_found": 4, "net_pnl": None,
    })
    entry = sts.check_trade_autopsy_data_quality(root=tmp_path)
    assert entry["verdict"] == "RED"
    assert "unverified_no_bars" in entry["reason"]
    assert "2026-09-10" in entry["reason"]


def test_verified_is_green(tmp_path):
    _write_last_json(tmp_path, {
        "date": "2026-09-09", "pnl_status": "verified",
        "n_no_bars": 0, "n_positions_found": 2, "net_pnl": -50.0,
    })
    entry = sts.check_trade_autopsy_data_quality(root=tmp_path)
    assert entry["verdict"] == "GREEN"


def test_flat_day_is_green(tmp_path):
    _write_last_json(tmp_path, {"date": "2026-09-06", "pnl_status": "flat", "net_pnl": 0.0})
    entry = sts.check_trade_autopsy_data_quality(root=tmp_path)
    assert entry["verdict"] == "GREEN"


def test_missing_file_is_unknown_not_green(tmp_path):
    entry = sts.check_trade_autopsy_data_quality(root=tmp_path)
    assert entry["verdict"] == "UNKNOWN"


def test_gamma_trade_autopsy_registered_in_output_freshness_map():
    """Previously ABSENT from TASK_OUTPUT_MAP entirely -- its output timestamp was never
    checked for staleness at all, on top of the content-blindness this file fixes."""
    assert "Gamma_TradeAutopsy" in sts.TASK_OUTPUT_MAP


def test_build_report_carries_data_quality_key(monkeypatch, tmp_path):
    _write_last_json(tmp_path, {
        "date": "2026-09-10", "pnl_status": "unverified_no_bars",
        "n_no_bars": 1, "n_positions_found": 1,
    })
    monkeypatch.setattr(sts, "ROOT", tmp_path)
    report = sts.build_report([], quiet_log_text="", run_cmd_hidden_log_text="")
    assert "data_quality" in report
    assert any(f["verdict"] == "RED" for f in report["data_quality"])


def test_red_data_quality_reaches_status_md(monkeypatch, tmp_path):
    """A RED in data_quality must flow into the SAME STATUS.md Known-broken upsert as an
    exit-code or output-freshness RED -- otherwise the content check is computed but never
    surfaced, which is exactly the silent-success-is-failure shape this ticket exists to
    close."""
    calls = []

    class _FakeSKB:
        @staticmethod
        def upsert(marker, line, status_path=None):
            calls.append((marker, line))
            return True

    monkeypatch.setattr(sts, "skb", _FakeSKB)
    report = {
        "generated_at_et": "2026-09-10 16:20:00 ET",
        "exit_codes": [], "output_freshness": [],
        "data_quality": [{"task": "Gamma_TradeAutopsy", "verdict": "RED",
                          "reason": "2026-09-10: pnl_status=unverified_no_bars"}],
    }
    result = sts.post_output_freshness_status(report, status_path=tmp_path / "STATUS.md")
    assert result is True
    assert calls, "post_output_freshness_status never called status_known_broken.upsert()"
    marker, line = calls[0]
    assert marker == sts.TASK_OUTPUT_FRESHNESS_MARKER
    assert "Gamma_TradeAutopsy" in line
