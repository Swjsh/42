"""Guard: conviction_shadow_report.py -- the weekly would_block distribution.

The load-bearing property is the FIX-BOUNDARY PARTITION, so most of these tests attack it.

WHY IT MATTERS (2026-08-15). `974ca235` fixed a transposed key that had degraded C4
range_extreme -- and left C5 structure unthreaded -- on every conviction row ever written.
Measured on the real ledger: max observed score 4 against a MINIMUM effective floor of 5, so
all 102 pre-fix rows were structurally incapable of clearing their floor. `would_block
102/102` is therefore an arithmetic certainty, not a measurement of signal quality.

If those rows are ever pooled with post-fix rows, the report says "conviction blocks ~100% of
entries" and the component gets killed on evidence that was an artifact of two dead
components (L248 -- quote the refinement cell, not |BASELINE). Hence: counted, labelled,
reported separately, NEVER merged and never silently dropped.

Pure: tmp files + synthetic rows. No network, no PowerShell, no live-state coupling.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import conviction_shadow_report as csr  # noqa: E402


def _row(ts, *, block=True, total=3, k=1, floor=5, degraded=(), components=None, arm="core"):
    return {
        "arm": arm, "ts_et": ts, "date": ts[:10], "account": "safe", "side": "P",
        "conviction": {
            "total": total, "max": 8, "k": k, "floor_effective": floor,
            "would_block": block, "shadow_only": True,
            "components": components or {key: 0 for key in csr.COMPONENT_KEYS},
            "degraded_components": list(degraded),
        },
    }


BEFORE = "2026-08-14T13:35:06"       # a real pre-fix row timestamp
AFTER = "2026-08-17T09:31:00"        # first plausible post-fix session
EXACT = csr.FIX_BOUNDARY_ET          # the boundary instant itself


# ---------------------------------------------------------------------------
# The partition
# ---------------------------------------------------------------------------

def test_pre_fix_rows_never_enter_the_post_fix_population():
    """RED-PROOF: this is the whole point of the module. 102 real rows blocked 100% with
    C4/C5 dead; pooling them would report that artifact as the ratchet's block rate."""
    rows = [_row(BEFORE, block=True) for _ in range(102)] + [_row(AFTER, block=False)]
    rep = csr.build_report(rows, "2026-08-15T13:00:00")
    assert rep["post_fix"]["n"] == 1
    assert rep["post_fix"]["would_block"] == 0
    assert rep["post_fix"]["block_rate_pct"] == 0.0
    assert rep["pre_fix_DO_NOT_POOL"]["n"] == 102
    assert rep["pre_fix_DO_NOT_POOL"]["block_rate_pct"] == 100.0


def test_boundary_instant_counts_as_post_fix():
    """A row written AT the fix commit's instant scored with the fix in place."""
    assert csr.is_post_fix(_row(EXACT)) is True
    assert csr.is_post_fix(_row("2026-08-14T19:15:21")) is False


def test_pre_fix_rows_are_reported_not_dropped():
    """Silently discarding them would hide that the population exists at all -- the
    report must be able to say WHY the post-fix set is small."""
    rep = csr.build_report([_row(BEFORE) for _ in range(5)], "t")
    assert rep["pre_fix_DO_NOT_POOL"]["n"] == 5
    assert "DO_NOT_POOL" in "".join(rep.keys())
    assert rep["_meta"]["fix_commit"] == "974ca235"
    assert "L248" in rep["_meta"]["partition_rationale"]


# ---------------------------------------------------------------------------
# Honest reporting of an empty population
# ---------------------------------------------------------------------------

def test_empty_post_fix_says_no_evidence_not_zero_percent():
    """RED-PROOF (C7 class): an empty table must not render as a finding. On 2026-08-15 the
    post-fix set is genuinely empty -- the fix landed after the last tick -- and a report
    that showed '0% block rate' would be read as 'conviction now allows everything'."""
    rep = csr.build_report([_row(BEFORE)], "t")
    assert rep["post_fix"] == {"n": 0}
    status = rep["_meta"]["status"]
    assert "EMPTY" in status and "no evidence yet" in status
    text = csr.render(rep)
    assert "(no rows)" in text
    assert "0.0%" not in text.split("PRE-FIX")[0]  # no fake rate in the post-fix section


def test_render_is_ascii_safe_for_a_cp1252_console():
    """The first version crashed on a Windows console with UnicodeEncodeError."""
    rep = csr.build_report([_row(BEFORE), _row(AFTER)], "t")
    csr.render(rep).encode("cp1252")  # must not raise


def test_report_declares_itself_disarmed():
    rep = csr.build_report([_row(AFTER)], "t")
    assert rep["_meta"]["armed"] is False
    assert "DISARMED" in rep["_meta"]["shadow_only"]


# ---------------------------------------------------------------------------
# Distribution shape
# ---------------------------------------------------------------------------

def test_block_rate_is_broken_out_by_k():
    """The gate is floor + step*k, so a pooled block rate averages over a MOVING bar.
    k must be visible or the number is close to meaningless."""
    rows = [_row(AFTER, k=0, block=False), _row(AFTER, k=0, block=False),
            _row(AFTER, k=3, block=True)]
    sec = csr.build_report(rows, "t")["post_fix"]
    assert sec["by_k"]["0"]["block_rate_pct"] == 0.0
    assert sec["by_k"]["3"]["block_rate_pct"] == 100.0


def test_degraded_components_are_surfaced():
    """A degraded component silently caps the achievable score -- exactly the defect that
    produced the pre-fix artifact. It must never be invisible again."""
    rows = [_row(AFTER, degraded=("range_extreme", "structure")) for _ in range(3)]
    sec = csr.build_report(rows, "t")["post_fix"]
    assert sec["degraded_components"]["range_extreme"] == 3
    assert sec["degraded_components"]["structure"] == 3


def test_component_hit_rate_counts_only_scoring_components():
    comps = {key: 0 for key in csr.COMPONENT_KEYS}
    comps["named_level"] = 2
    rows = [_row(AFTER, components=comps), _row(AFTER)]
    sec = csr.build_report(rows, "t")["post_fix"]
    assert sec["component_hit_rate_pct"]["named_level"] == 50.0
    assert sec["component_hit_rate_pct"]["zone_stack"] == 0.0


# ---------------------------------------------------------------------------
# Never breaks
# ---------------------------------------------------------------------------

def test_errored_rows_are_counted_not_crashed_on():
    rows = [_row(AFTER)]
    rows.append({"arm": "core", "ts_et": AFTER, "date": AFTER[:10],
                 "conviction": {"error": "ValueError: x", "shadow_only": True}})
    sec = csr.build_report(rows, "t")["post_fix"]
    assert sec["n"] == 2 and sec["n_errored"] == 1


def test_no_rows_at_all_is_a_clean_empty_report():
    rep = csr.build_report([], "t")
    assert rep["post_fix"] == {"n": 0}
    assert rep["pre_fix_DO_NOT_POOL"] == {"n": 0}
    csr.render(rep)  # must not raise


def test_load_rows_tolerates_malformed_ledger_lines(tmp_path, monkeypatch):
    """Fail-open: a truncated/garbage line must not take down the reporter."""
    state = tmp_path / "state"
    state.mkdir()
    ledger = state / "core-decisions.jsonl"
    good = {"ts_et": AFTER, "account": "safe", "side": "P",
            "conviction": {"total": 5, "would_block": False, "k": 0,
                           "floor_effective": 5, "components": {}, "degraded_components": []}}
    ledger.write_text(
        "not json at all\n"
        + json.dumps({"ts_et": AFTER, "conviction": "not a dict"}) + "\n"
        + json.dumps({"conviction": {"total": 1}}) + "\n"          # no ts_et
        + json.dumps(good) + "\n",
        encoding="utf-8")
    monkeypatch.setattr(csr, "STATE", state)
    rows = csr.load_rows()
    assert len(rows) == 1
    assert rows[0]["conviction"]["total"] == 5


def test_run_writes_the_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(csr, "STATE", tmp_path / "nonexistent")
    monkeypatch.setattr(csr, "OUT_DIR", tmp_path / "out")
    monkeypatch.setattr(csr, "OUT_PATH", tmp_path / "out" / "conviction-shadow-report.json")
    rep = csr.run(write=True)
    on_disk = json.loads((tmp_path / "out" / "conviction-shadow-report.json")
                         .read_text(encoding="utf-8"))
    assert on_disk["_meta"]["armed"] is False
    assert on_disk["post_fix"] == rep["post_fix"]


# ---------------------------------------------------------------------------
# Outcome join -- "would blocking have HELPED?", not just "how often would it block?"
# ---------------------------------------------------------------------------

def test_outcome_join_is_strictly_one_to_one(monkeypatch):
    """RED-PROOF, and this bug was live for one commit's worth of minutes before it was caught.

    Conviction logs on EVERY ENTER tick, so the 09:46 / 09:47 / 09:48 rows all sit inside the
    join window of the SINGLE 09:46 fill. A nearest-match-per-row join lets one round trip be
    claimed 3-4 times. Measured on the real ledger it turned 11 distinct round trips into 34
    'joined' rows and -$317 into -$1,750 -- a 5.5x inflation of the headline number, and the
    exact round-trips-are-not-decisions class this repo documented the same day.

    A many-to-one relation joined without CLAIMING is a silent multiplier on every downstream
    dollar figure."""
    ticks = [_row(f"2026-08-17T09:4{i}:0{i}", block=True) for i in (6, 7, 8)]
    for t in ticks:
        t["account"] = "safe"
        t["date"] = "2026-08-17"

    fake_rt = [{"date": "2026-08-17", "symbol": "SPY260817C00780000",
                "entry_ts_et": "2026-08-17T09:46:14", "real_pnl": -282.0}]
    monkeypatch.setitem(sys.modules, "fills_fifo",
                        type(sys)("fills_fifo"))
    sys.modules["fills_fifo"].mine_real_arm_fills = (
        lambda arm: fake_rt if arm == "safe-2" else [])

    joined = csr._attach_outcomes(ticks)
    assert joined == 1, f"one fill must be claimed ONCE, got {joined} claims"
    matched = [t for t in ticks if t.get("real_pnl") is not None]
    assert len(matched) == 1
    assert sum(t["real_pnl"] for t in matched) == -282.0, "P&L must not be multiplied"


def test_outcome_cells_split_block_vs_allow(monkeypatch):
    """The decision-relevant contrast. A gate with an EMPTY allow-cell has no discriminating
    power -- its 'delta if armed' is just the book's P&L negated, which is the sit-out result,
    not evidence about the gate."""
    rows = [_row("2026-08-17T09:46:00", block=True), _row("2026-08-17T10:00:00", block=False)]
    rows[0]["real_pnl"], rows[1]["real_pnl"] = -100.0, 50.0
    cells = csr.outcome_cells(rows)
    assert cells["n_joined"] == 2
    assert cells["WOULD_BLOCK"]["total_pnl"] == -100.0
    assert cells["WOULD_ALLOW"]["total_pnl"] == 50.0
    assert cells["delta_if_armed_usd"] == 100.0


def test_outcome_cells_are_honest_when_nothing_joined():
    cells = csr.outcome_cells([_row("2026-08-17T09:46:00")])
    assert cells["n_joined"] == 0
    assert "no outcome evidence" in cells["note"]


def test_delta_if_armed_carries_its_caveat():
    """A dollar figure with no OOS split, no null and no random-suppression control must say
    so in the artifact -- the 2026-08-12 teardown killed a '+$594' cell of exactly this shape
    because ANY rule deleting k trades on a losing day earns the base rate for free."""
    rows = [_row("2026-08-17T09:46:00", block=True)]
    rows[0]["real_pnl"] = -100.0
    reading = csr.outcome_cells(rows)["_reading"]
    assert "not a scorecard" in reading.lower()
    assert "suppress-k-at-random" in reading or "random" in reading


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
