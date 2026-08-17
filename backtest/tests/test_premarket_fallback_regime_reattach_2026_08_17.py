"""Guard: premarket_deterministic_fallback.py must never silently wipe
today-bias.json#regime_context (WS6 RED, live-observed 2026-08-17).

Root cause: `run()` writes today-bias.json WHOLESALE from `build()`'s output
dict, which never includes `regime_context` (that key belongs to
`regime_stamp.py`, Gamma_RegimeStamp, 08:22/08:40 ET). The 08:40 ET repatch
trigger only re-heals Premarket's (08:30 ET) transcription -- it does NOT
cover an ad-hoc invocation of THIS script at an arbitrary later time. That is
exactly what happened 2026-08-17: the box slept through both regime-stamp
triggers, Task Scheduler's missed-trigger catch-up produced a same-day
regime-stamp.json around 09:35 ET, then the incident-repair sequence ran
premarket_deterministic_fallback.py (to re-date today-bias.json) AFTER that,
silently dropping `regime_context` with no third safety net -- monday_verify's
WS6 check went RED (`regime_context.stamp_date=None`).

Fix: `run()` now calls `_reattach_regime_context()` immediately after every
write, re-applying the same 4-field patch shape from today's regime-stamp.json
if one exists and is dated today. This test reproduces the exact live drift
and proves the reattach heals it, is idempotent, and fails open when no
same-day stamp exists (rail-2).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO / "setup" / "scripts"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import premarket_deterministic_fallback as pdf  # noqa: E402

TODAY = "2026-08-17"

FAKE_STAMP = {
    "date": TODAY,
    "one_liner": "Yesterday 2026-08-14 (Fri) = range-chop (range 0.43%, gap +0.10%, close_loc 0.26).",
    "yesterday": {"archetype": "range-chop"},
}


def _write_bias(tmp_path: Path, regime_context: dict | None) -> Path:
    bias_path = tmp_path / "today-bias.json"
    payload = {"date": TODAY, "bias": "no-trade", "degraded": True}
    if regime_context is not None:
        payload["regime_context"] = regime_context
    bias_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return bias_path


def _write_stamp(tmp_path: Path, stamp: dict | None) -> Path:
    stamp_path = tmp_path / "regime-stamp.json"
    if stamp is not None:
        stamp_path.write_text(json.dumps(stamp, indent=2), encoding="utf-8")
    return stamp_path


def test_reattach_heals_the_live_observed_2026_08_17_drift(tmp_path, monkeypatch):
    """Reproduce the exact live drift: a fresh today-bias.json (as
    premarket_deterministic_fallback.run() writes it, no regime_context key at
    all) plus a same-day regime-stamp.json that was already correctly written
    -- prove the reattach restores the 4-field patch."""
    bias_path = _write_bias(tmp_path, regime_context=None)
    stamp_path = _write_stamp(tmp_path, FAKE_STAMP)
    monkeypatch.setattr(pdf, "TODAY_BIAS", bias_path)
    monkeypatch.setattr(pdf, "REGIME_STAMP", stamp_path)

    healed = pdf._reattach_regime_context(TODAY)
    assert healed is True

    bias = json.loads(bias_path.read_text(encoding="utf-8"))
    rc = bias["regime_context"]
    assert rc["one_liner"] == FAKE_STAMP["one_liner"]
    assert rc["yesterday_archetype"] == "range-chop"
    assert rc["stamp_date"] == TODAY
    assert rc["source"] == "regime_stamp_0822ET"
    # rest of the file survives untouched
    assert bias["bias"] == "no-trade"
    assert bias["degraded"] is True


def test_reattach_is_idempotent(tmp_path, monkeypatch):
    correct = {
        "one_liner": FAKE_STAMP["one_liner"],
        "yesterday_archetype": "range-chop",
        "stamp_date": TODAY,
        "source": "regime_stamp_0822ET",
    }
    bias_path = _write_bias(tmp_path, regime_context=correct)
    stamp_path = _write_stamp(tmp_path, FAKE_STAMP)
    monkeypatch.setattr(pdf, "TODAY_BIAS", bias_path)
    monkeypatch.setattr(pdf, "REGIME_STAMP", stamp_path)

    assert pdf._reattach_regime_context(TODAY) is True
    bias = json.loads(bias_path.read_text(encoding="utf-8"))
    assert bias["regime_context"] == correct


def test_reattach_no_op_when_stamp_missing(tmp_path, monkeypatch):
    bias_path = _write_bias(tmp_path, regime_context=None)
    stamp_path = tmp_path / "regime-stamp.json"  # never written
    monkeypatch.setattr(pdf, "TODAY_BIAS", bias_path)
    monkeypatch.setattr(pdf, "REGIME_STAMP", stamp_path)

    assert pdf._reattach_regime_context(TODAY) is False
    bias = json.loads(bias_path.read_text(encoding="utf-8"))
    assert "regime_context" not in bias


def test_reattach_no_op_when_stamp_is_stale(tmp_path, monkeypatch):
    """A yesterday-dated stamp (Task Scheduler didn't catch up yet) must NOT
    be attached -- stale > absent for a descriptive-only field."""
    bias_path = _write_bias(tmp_path, regime_context=None)
    stale_stamp = {**FAKE_STAMP, "date": "2026-08-16"}
    stamp_path = _write_stamp(tmp_path, stale_stamp)
    monkeypatch.setattr(pdf, "TODAY_BIAS", bias_path)
    monkeypatch.setattr(pdf, "REGIME_STAMP", stamp_path)

    assert pdf._reattach_regime_context(TODAY) is False
    bias = json.loads(bias_path.read_text(encoding="utf-8"))
    assert "regime_context" not in bias


def test_reattach_fails_open_when_bias_file_missing(tmp_path, monkeypatch):
    missing_bias = tmp_path / "does-not-exist.json"
    stamp_path = _write_stamp(tmp_path, FAKE_STAMP)
    monkeypatch.setattr(pdf, "TODAY_BIAS", missing_bias)
    monkeypatch.setattr(pdf, "REGIME_STAMP", stamp_path)

    assert pdf._reattach_regime_context(TODAY) is False


def test_run_wires_reattach_after_write(tmp_path, monkeypatch):
    """End-to-end: run() writes today-bias.json (via a stubbed build()) then
    must call the reattach so regime_context survives on the very first
    write, not just on a manual second call."""
    stamp_path = _write_stamp(tmp_path, FAKE_STAMP)
    bias_path = tmp_path / "today-bias.json"
    monkeypatch.setattr(pdf, "TODAY_BIAS", bias_path)
    monkeypatch.setattr(pdf, "REGIME_STAMP", stamp_path)

    def _fake_build(repo_root=None, now_et=None, **kwargs):
        return {"ok": True, "date": TODAY, "bias": "no-trade", "degraded": True}

    monkeypatch.setattr(pdf, "build", _fake_build)

    result = pdf.run(dry_run=False)
    assert result["ok"] is True

    bias = json.loads(bias_path.read_text(encoding="utf-8"))
    assert bias["regime_context"]["stamp_date"] == TODAY
