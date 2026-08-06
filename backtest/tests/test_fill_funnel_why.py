"""Guards for fill_funnel.py's WHY-THIS-ARM-DID-OR-DID-NOT-TRADE instrument.

Shipped 2026-08-06 off EOD-2026-08-05-SILENT-ARMS. OP-33e: a repeated question from J
("why didn't arm X trade?") is a MISSING INSTRUMENT, not a query.

The 2026-08-05 ground truth these guards pin (broker-verified: bold-2 and safe-3 each
took ZERO legs while three siblings took 29 off the same shared signal):
  * bold-2  silence cause = FREE_MODEL_VETO (13x), NOT PDT (3x)  -- the prime suspect
            was the MINORITY cause and the instrument must say so.
  * safe-3  silence cause = ARM_GATE (30x), and its risk gate was never consulted.
Two silent arms, two DIFFERENT causes on the same day -- a single-cause report is wrong.

Additivity is the load-bearing safety property: self_check / gamma_glance /
gamma_narrative / eod_fallback all read funnel stages + flags + verdict, and this
feature must not move any of them.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import fill_funnel as ff  # noqa: E402

DAY = "2026-08-05"


# --------------------------------------------------------------------------- fixtures
def _core(ts: str, action: str, *, status: str | None = None, setup: str = "S") -> dict:
    row = {"ts_et": f"{DAY}T{ts}", "account": "bold", "action": action, "setup": setup}
    if status is not None:
        row["exec"] = {"status": status, "reason": f"reason for {status}"}
    return row


def _fleet(ts: str, action: str, *, reason: str = "", risk_code=None,
           killed: bool = False) -> dict:
    return {"ts_et": f"{DAY}T{ts}", "arm_id": "safe-3", "action": action,
            "reason": reason, "risk_code": risk_code, "killed": killed}


def _write(tmp_path: Path, core_rows: list[dict], fleet_rows: list[dict]):
    core = tmp_path / "core-decisions.jsonl"
    core.write_text("\n".join(json.dumps(r) for r in core_rows), encoding="utf-8")
    fleet_dir = tmp_path / "fleet"
    (fleet_dir / "safe-3").mkdir(parents=True)
    (fleet_dir / "safe-3" / "decisions.jsonl").write_text(
        "\n".join(json.dumps(r) for r in fleet_rows), encoding="utf-8")
    return core, fleet_dir


# --------------------------------------------------------------------------- taxonomy
@pytest.mark.parametrize("action,status,expected", [
    ("VETOED_BY_MODELS", None, ff._WHY_MODEL_VETO),
    ("RISK_DENY_PDT", "RISK_DENY_PDT", ff._WHY_PDT),
    ("RISK_DENY_BUDGET", None, ff._WHY_RISK),
    ("NOT_FLAT", "NOT_FLAT", ff._WHY_NOT_FLAT),
    ("SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY", None, ff._WHY_SKIP),
    ("SKIP_STALE_TRIGGER", None, ff._WHY_SKIP),
    ("PLACED", "PLACED", ff._WHY_TRADED),
    ("HOLD", None, ff._WHY_NO_SETUP),
])
def test_core_cause_taxonomy(action, status, expected):
    assert ff._why_core(_core("11:00:00", action, status=status)) == expected


@pytest.mark.parametrize("action,reason,risk_code,killed,expected", [
    ("ENTER_BEAR", "", "ALLOW", False, ff._WHY_TRADED),
    ("HOLD", "gate: 1 triggers < 2", None, False, ff._WHY_GATE),
    ("HOLD", "gate: requires confluence/sequence", None, False, ff._WHY_GATE),
    ("HOLD", "risk_gate denied: position already open", "NOT_FLAT", False, ff._WHY_NOT_FLAT),
    ("HOLD", "no live signal", None, False, ff._WHY_NO_FEED),
    ("HOLD", "no qualifying setup (no strategy fired)", None, False, ff._WHY_NO_SETUP),
    ("HOLD", "anything", None, True, ff._WHY_KILLED),
    ("ERROR", "account fetch: 500", None, False, ff._WHY_ERROR),
])
def test_fleet_cause_taxonomy(action, reason, risk_code, killed, expected):
    assert ff._why_fleet(_fleet("11:00:00", action, reason=reason,
                                risk_code=risk_code, killed=killed)) == expected


def test_malformed_row_never_raises_and_degrades_to_no_setup():
    """One bad row must never blind the whole instrument (C7 fail-open)."""
    assert ff._why_core({}) == ff._WHY_NO_SETUP
    assert ff._why_fleet({}) == ff._WHY_NO_SETUP
    d = ff._silence_diagnosis([{"action": None}, None], "fleet", {"filled": 0})
    assert d["top_cause"] == ff._WHY_NO_SETUP


# --------------------------------------------------------------- the 08-05 ground truth
def test_bold2_dominant_cause_is_model_veto_not_pdt(tmp_path):
    """RED-PROOF ANCHOR: on 2026-08-05 bold-2's silence was 13x free-model veto and only
    3x PDT. An instrument that named PDT (the prime suspect) would be WRONG."""
    core = ([_core(f"11:{m:02d}:00", "VETOED_BY_MODELS") for m in range(13)]
            + [_core(f"11:{m:02d}:00", "RISK_DENY_PDT", status="RISK_DENY_PDT")
               for m in (20, 21, 22)]
            + [_core(f"12:{m:02d}:00", "HOLD") for m in range(30)])
    cp, fd = _write(tmp_path, core, [_fleet("11:00:00", "HOLD",
                                            reason="no qualifying setup")])
    f = ff.compute_funnel(DAY, core_path=cp, fleet_dir=fd)
    why = f["accounts"]["core:bold"]["why"]
    assert why["traded"] is False
    assert why["top_cause"] == ff._WHY_MODEL_VETO
    assert why["cause_counts"][ff._WHY_MODEL_VETO] == 13
    assert why["cause_counts"][ff._WHY_PDT] == 3
    assert "FREE_MODEL_VETO" in why["headline"]
    assert "RISK_DENY_PDT" in why["headline"]      # the minority cause is still disclosed


def test_safe3_dominant_cause_is_its_own_arm_gate(tmp_path):
    """safe-3's silence was 30x its accounts.json gate_override -- the risk gate was
    never consulted, so PDT can NOT be the reported cause for this arm."""
    fleet = ([_fleet(f"09:{m:02d}:00", "HOLD", reason="gate: requires confluence/sequence")
              for m in range(12)]
             + [_fleet(f"11:{m:02d}:00", "HOLD", reason="gate: 1 triggers < 2")
                for m in range(18)]
             + [_fleet(f"13:{m:02d}:00", "HOLD", reason="no qualifying setup")
                for m in range(40)])
    cp, fd = _write(tmp_path, [_core("11:00:00", "HOLD")], fleet)
    f = ff.compute_funnel(DAY, core_path=cp, fleet_dir=fd)
    why = f["accounts"]["fleet:safe-3"]["why"]
    assert why["traded"] is False
    assert why["top_cause"] == ff._WHY_GATE
    assert why["cause_counts"][ff._WHY_GATE] == 30
    assert ff._WHY_PDT not in why["cause_counts"]
    assert "gate: requires confluence/sequence" in why["headline"]


def test_quiet_tape_is_not_reported_as_an_engine_refusal(tmp_path):
    """A day where nothing set up is the MARKET's doing. It must NOT read as a block --
    that distinction is the entire value of the instrument."""
    cp, fd = _write(tmp_path, [_core(f"1{h}:00:00", "HOLD") for h in range(4)],
                    [_fleet(f"1{h}:00:00", "HOLD", reason="no qualifying setup")
                     for h in range(4)])
    f = ff.compute_funnel(DAY, core_path=cp, fleet_dir=fd)
    for key in ("core:bold", "fleet:safe-3"):
        why = f["accounts"][key]["why"]
        assert why["top_cause"] == ff._WHY_NO_SETUP
        assert why["blocking_ticks"] == 0
        assert "quiet tape" in why["headline"]


def test_traded_arm_reports_traded_and_still_lists_its_blocks(tmp_path):
    core = [_core("11:00:00", "PLACED", status="PLACED"),
            _core("11:01:00", "VETOED_BY_MODELS"),
            _core("11:02:00", "HOLD")]
    core[0]["exec"] = {"status": "PLACED", "symbol": "SPY260805P00772000",
                       "qty": 3, "broker": {"id": "abc", "filled_qty": "3"}}
    core[0]["verdict"] = "ENTER_BEAR"
    cp, fd = _write(tmp_path, core, [_fleet("11:00:00", "HOLD", reason="no setup")])
    f = ff.compute_funnel(DAY, core_path=cp, fleet_dir=fd)
    why = f["accounts"]["core:bold"]["why"]
    assert why["traded"] is True
    assert why["top_cause"] == ff._WHY_TRADED
    assert "FREE_MODEL_VETO" in why["headline"]


# ------------------------------------------------------------------------- additivity
def test_silence_diagnosis_is_additive_stages_and_verdict_unchanged(tmp_path, monkeypatch):
    """VARY-AND-ASSERT (C14): with the WHY computation disabled, every funnel STAGE,
    every flag and the verdict must be byte-identical. Only the `why` key differs."""
    core = ([_core(f"11:{m:02d}:00", "VETOED_BY_MODELS") for m in range(5)]
            + [_core("11:30:00", "RISK_DENY_PDT", status="RISK_DENY_PDT")])
    core[-1]["verdict"] = "ENTER_BEAR"
    fleet = [_fleet("11:00:00", "HOLD", reason="gate: 1 triggers < 2")]
    cp, fd = _write(tmp_path, core, fleet)

    with_why = ff.compute_funnel(DAY, core_path=cp, fleet_dir=fd)
    monkeypatch.setattr(ff, "_silence_diagnosis",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("off")))
    without = ff.compute_funnel(DAY, core_path=cp, fleet_dir=fd)

    assert with_why["verdict"] == without["verdict"]
    assert with_why["flags"] == without["flags"]
    assert with_why["totals"] == without["totals"]
    for key in with_why["accounts"]:
        a, b = dict(with_why["accounts"][key]), dict(without["accounts"][key])
        a.pop("why", None)
        b.pop("why", None)
        assert a == b, f"{key}: WHY changed a funnel stage"
    # ...and the fail-open path really did drop the key rather than crashing the funnel
    assert all("why" not in a for a in without["accounts"].values())


def test_renderers_emit_a_line_per_arm(tmp_path):
    cp, fd = _write(tmp_path, [_core("11:00:00", "VETOED_BY_MODELS")],
                    [_fleet("11:00:00", "HOLD", reason="gate: 1 triggers < 2")])
    f = ff.compute_funnel(DAY, core_path=cp, fleet_dir=fd)
    txt = ff.render_text(f)
    assert "why each arm did / did not trade" in txt
    assert txt.count("DID NOT TRADE") == 2
    md = ff.render_markdown(f, repo=REPO)
    assert "**Why each arm did / did not trade:**" in md
    assert "| account | traded | dominant cause | detail |" in md
    assert md.count("`ARM_GATE`") == 1
    assert md.count("`FREE_MODEL_VETO`") == 1
