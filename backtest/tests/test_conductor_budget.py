"""Guards for conductor_budget -- the nightly spend governor.

Context: a measured census (2026-07-25) found the conductor family = 93.3% of automation token
burn. The subtle failure mode this file pins: the conductor UNDER-REPORTS its own cost by ~2.2x
($3.44 self-reported vs $7.69 measured), so a cap read naively off `cost_usd` would silently
permit ~2x the intended spend. The correction is the point of the module.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "setup" / "scripts"))

from conductor_budget import (  # noqa: E402
    EXIT_EXHAUSTED,
    EXIT_PROCEED,
    SELF_REPORT_CORRECTION,
    check,
    load_config,
    main,
    spend_today,
)

DAY = "2026-07-25"


def _outcomes(tmp_path: Path, rows) -> Path:
    p = tmp_path / "conductor-outcomes.jsonl"
    with open(p, "w", encoding="utf-8") as fh:
        for cost in rows:
            fh.write(json.dumps({"fired_at": f"{DAY}T02:00:00+00:00",
                                 "task_id": "T", "cost_usd": cost}) + "\n")
    return p


def _cfg(cap=30.0, fires=4, enabled=True):
    return {"daily_cap_usd": cap, "max_fires": fires, "enabled": enabled}


# ------------------------------------------------------- the correction factor (the whole point)
def test_self_report_is_corrected_upward():
    assert SELF_REPORT_CORRECTION > 1.0, "the conductor under-reports; correction must scale UP"


def test_the_2x2_correction_is_actually_applied(tmp_path):
    """A $15 self-reported day must read as EXHAUSTED against a $30 cap ($15 x 2.2 = $33)."""
    led = _outcomes(tmp_path, [5.0, 5.0, 5.0])  # raw $15
    s = spend_today(DAY, led)
    assert s["raw_usd"] == 15.0
    assert s["corrected_usd"] == round(15.0 * SELF_REPORT_CORRECTION, 2)
    res = check(DAY, _cfg(cap=30.0, fires=99), led)
    assert res["verdict"] == "EXHAUSTED", "naive (uncorrected) math would have said PROCEED here"


def test_uncorrected_reading_would_have_passed_same_data(tmp_path):
    """Explicitly pins the bug being prevented: raw $15 < $30, corrected $33 >= $30."""
    led = _outcomes(tmp_path, [15.0])
    s = spend_today(DAY, led)
    assert s["raw_usd"] < 30.0 <= s["corrected_usd"]


# ------------------------------------------------------- proceed / exhaust behaviour
def test_fresh_day_proceeds(tmp_path):
    res = check(DAY, _cfg(), _outcomes(tmp_path, []))
    assert res["verdict"] == "PROCEED"
    assert res["fires"] == 0


def test_under_cap_proceeds(tmp_path):
    res = check(DAY, _cfg(cap=100.0, fires=99), _outcomes(tmp_path, [3.0, 3.0]))
    assert res["verdict"] == "PROCEED"


def test_fire_count_cap_independently_exhausts(tmp_path):
    """Even with trivial cost, too many fires stops the night."""
    res = check(DAY, _cfg(cap=10_000.0, fires=3), _outcomes(tmp_path, [0.01] * 5))
    assert res["verdict"] == "EXHAUSTED"
    assert "fires" in res["reason"]


def test_disabled_config_always_proceeds(tmp_path):
    res = check(DAY, _cfg(cap=0.01, fires=1, enabled=False), _outcomes(tmp_path, [99.0] * 9))
    assert res["verdict"] == "PROCEED"


# ------------------------------------------------------- fail-open contract
def test_missing_ledger_fails_open(tmp_path):
    res = check(DAY, _cfg(), tmp_path / "nope.jsonl")
    assert res["verdict"] == "PROCEED", "a governor must never block on its own missing telemetry"


def test_garbled_rows_are_skipped_not_fatal(tmp_path):
    p = tmp_path / "conductor-outcomes.jsonl"
    p.write_text("{broken\n" + json.dumps({"fired_at": f"{DAY}T01:00:00", "cost_usd": "NaNish"})
                 + "\n" + json.dumps({"fired_at": f"{DAY}T02:00:00", "cost_usd": 2.0}) + "\n",
                 encoding="utf-8")
    s = spend_today(DAY, p)
    assert s["fires"] == 2 and s["raw_usd"] == 2.0


def test_missing_config_uses_safe_defaults(tmp_path):
    cfg = load_config(tmp_path / "absent.json")
    assert cfg["daily_cap_usd"] > 0 and cfg["max_fires"] > 0 and cfg["enabled"] is True


def test_other_days_do_not_count(tmp_path):
    p = tmp_path / "conductor-outcomes.jsonl"
    p.write_text(json.dumps({"fired_at": "2026-07-24T02:00:00", "cost_usd": 500.0}) + "\n",
                 encoding="utf-8")
    assert spend_today(DAY, p)["fires"] == 0


# ------------------------------------------------------- CLI exit codes (what conductor.md reads)
def test_cli_exit_codes(tmp_path, monkeypatch, capsys):
    import conductor_budget as cb

    monkeypatch.setattr(cb, "OUTCOMES", _outcomes(tmp_path, []))
    monkeypatch.setattr(cb, "CONFIG", tmp_path / "absent.json")
    assert main(["--check", "--date", DAY]) == EXIT_PROCEED

    monkeypatch.setattr(cb, "OUTCOMES", _outcomes(tmp_path, [50.0] * 3))
    assert main(["--check", "--date", DAY]) == EXIT_EXHAUSTED
    capsys.readouterr()


def test_status_never_blocks(tmp_path, monkeypatch, capsys):
    import conductor_budget as cb

    monkeypatch.setattr(cb, "OUTCOMES", _outcomes(tmp_path, [99.0] * 9))
    monkeypatch.setattr(cb, "CONFIG", tmp_path / "absent.json")
    assert main(["--status", "--date", DAY]) == EXIT_PROCEED
    capsys.readouterr()
