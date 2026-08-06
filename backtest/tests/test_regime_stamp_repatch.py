"""Guard: the 08:40 ET regime-stamp REPATCH trigger actually heals the Premarket
transcription drift observed live 2026-08-05.

Root cause (live-observed 2026-08-05, flagged simultaneously by monday_verify's WS6
check AND self_check's REGIME-STAMP DRIFT problem): `regime_stamp.py` (Gamma_RegimeStamp,
08:22 ET) correctly patches `today-bias.json#regime_context` with all 4 fields
(one_liner, yesterday_archetype, stamp_date, source). Premarket (Gamma_Premarket, 08:30
ET, an LLM-prompt-driven session) then rewrites today-bias.json WHOLESALE and is
instructed (premarket.md Step 3) to carry the same 4 fields forward -- but on
2026-08-05 only `one_liner` survived the transcription; `yesterday_archetype`,
`stamp_date`, and `source` all landed `null`, silently breaking the contract
(CLAUDE.md C14 class: a producer/consumer field that depends on prose-instruction
fidelity rather than code).

Fix: main() is idempotent and $0 -- re-running it at 08:40 ET (setup/install-regime-stamp.ps1,
second trigger) re-reads whatever today-bias.json Premarket just wrote and
unconditionally overwrites regime_context with the correct 4-field dict, so the
deterministic patch is always the LAST writer. This test proves that mechanism directly:
it reproduces the EXACT observed drift (a today-bias.json with a botched regime_context)
and asserts a `patch_today_bias` call repairs it to the correct 4-field shape.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO / "automation" / "scripts"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import regime_stamp as rstamp  # noqa: E402

FAKE_STAMP = {
    "date": "2026-08-05",
    "one_liner": "Yesterday 2026-08-04 (Tue) = gap-go (range 1.69%, gap +0.39%, close_loc 0.83).",
    "yesterday": {"archetype": "gap-go"},
}


def _write_bias(tmp_path: Path, regime_context: dict | None) -> Path:
    bias_path = tmp_path / "today-bias.json"
    payload = {"date": "2026-08-05", "bias": "no-trade"}
    if regime_context is not None:
        payload["regime_context"] = regime_context
    bias_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return bias_path


def test_repatch_heals_the_live_observed_drift(tmp_path, monkeypatch):
    """Reproduce the EXACT 2026-08-05 drift: one_liner present, other 3 fields null
    (what Premarket's imperfect transcription produced) -- prove patch_today_bias
    repairs all 4 fields from the authoritative stamp."""
    botched = {
        "one_liner": FAKE_STAMP["one_liner"],
        "yesterday_archetype": None,
        "stamp_date": None,
        "source": None,
    }
    bias_path = _write_bias(tmp_path, botched)
    monkeypatch.setattr(rstamp, "BIAS_PATH", bias_path)

    ok = rstamp.patch_today_bias(FAKE_STAMP)
    assert ok is True

    healed = json.loads(bias_path.read_text(encoding="utf-8"))
    rc = healed["regime_context"]
    assert rc["one_liner"] == FAKE_STAMP["one_liner"]
    assert rc["yesterday_archetype"] == "gap-go"
    assert rc["stamp_date"] == "2026-08-05"
    assert rc["source"] == "regime_stamp_0822ET"


def test_repatch_is_idempotent_on_already_correct_bias(tmp_path, monkeypatch):
    """Running the repatch against an ALREADY-correct regime_context (the happy path,
    most mornings) must be a no-op in effect -- same 4 fields, no crash, no corruption
    of the rest of today-bias.json."""
    correct = {
        "one_liner": FAKE_STAMP["one_liner"],
        "yesterday_archetype": "gap-go",
        "stamp_date": "2026-08-05",
        "source": "regime_stamp_0822ET",
    }
    bias_path = _write_bias(tmp_path, correct)
    monkeypatch.setattr(rstamp, "BIAS_PATH", bias_path)

    ok = rstamp.patch_today_bias(FAKE_STAMP)
    assert ok is True

    healed = json.loads(bias_path.read_text(encoding="utf-8"))
    assert healed["regime_context"] == correct
    assert healed["date"] == "2026-08-05"
    assert healed["bias"] == "no-trade"


def test_repatch_fails_open_when_bias_file_missing(tmp_path, monkeypatch):
    """No today-bias.json yet (e.g. Premarket hasn't run) -- patch_today_bias must
    return False, never raise (rail-2 fail-open discipline)."""
    missing_path = tmp_path / "does-not-exist.json"
    monkeypatch.setattr(rstamp, "BIAS_PATH", missing_path)
    assert rstamp.patch_today_bias(FAKE_STAMP) is False


def test_install_script_registers_two_daily_triggers():
    """RED-proof for the actual fix: the install script must register BOTH the
    08:22 ET rebuild+patch trigger AND the 08:40 ET repatch-only safety-net trigger --
    a single trigger is exactly the pre-fix state that let the drift go unhealed all
    day."""
    script = (REPO / "setup" / "install-regime-stamp.ps1").read_text(encoding="utf-8")
    assert '-At "06:22"' in script
    assert '-At "06:40"' in script
    assert script.count("New-ScheduledTaskTrigger -Daily -At") == 2
