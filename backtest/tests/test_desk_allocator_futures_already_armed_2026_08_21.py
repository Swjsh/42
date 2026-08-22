"""Guard: assess_futures() must not keep screaming DECISION ROTTING once the MES mirror
has actually been armed.

WHY THIS EXISTS
  desk_allocator.py's armable_unarmed flag for the futures desk used to be a bare re-read
  of shadow-progress.json's own "armable" field -- true forever once the arming bar clears,
  even AFTER Gamma_FuturesMirror --armed was registered and the lane started executing real
  (sandbox) broker calls on 2026-08-20. That cost at least two conductor fires
  (2026-08-21 01:20 ET, and the 20:30 ET fire that filed this test) re-deriving "already
  armed" by hand from worker-registry.json prose instead of the allocator saying so itself.

  mirror-broker-orders.jsonl is written ONLY by the real armed code path
  (_broker_execute_entry in futures_mirror_shadow.py, gated on MIRROR_ARMED=1) -- any row in
  it, regardless of outcome, is hard evidence the lane is armed. Presence there should
  silence the rotting alarm; absence should not (an armable-but-never-armed lane is still
  the scar case test_desk_allocator_2026_08_20.py pins).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import desk_allocator as da                    # noqa: E402


ARMING_BAR_DOC = {
    "updated_et": "2026-08-21T16:05:02",
    "n_round_trips": 66,
    "total_pnl_usd": 1517.15,
    "arming_bar": {"round_trips_needed": 20, "round_trips_have": 66,
                    "expectancy_positive": True, "beats_null": True, "armable": True},
}


def _futures_dir(tmp_path: Path) -> Path:
    fut = tmp_path / "futures"
    fut.mkdir(parents=True)
    (fut / "shadow-progress.json").write_text(json.dumps(ARMING_BAR_DOC), encoding="utf-8")
    return fut


def test_armable_and_never_armed_still_rots(tmp_path, monkeypatch):
    """The original scar case must still fire when there is truly no broker-orders evidence."""
    monkeypatch.setattr(da, "STATE", tmp_path)
    _futures_dir(tmp_path)
    a = da.assess_futures()
    assert a["armable_unarmed"] is True
    assert "ARMABLE" in a["headline"]
    assert "ARMED" not in a["headline"].replace("ARMABLE", "")


def test_armable_and_broker_orders_present_is_not_rotting(tmp_path, monkeypatch):
    """A real (even if empty-outcome) row in mirror-broker-orders.jsonl proves the lane is
    already armed -- the allocator must stop flagging it as an unrealised decision."""
    monkeypatch.setattr(da, "STATE", tmp_path)
    fut = _futures_dir(tmp_path)
    row = {"ts_et": "2026-08-21T11:10:01", "signal_ref": "long|2026-08-21T11:07",
           "order_ids": [], "placed": False, "fills": "BROKER"}
    (fut / "mirror-broker-orders.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    a = da.assess_futures()
    assert a["armable_unarmed"] is False
    assert "ARMED (awaiting live fills)" in a["headline"]


def test_empty_broker_orders_file_still_counts_as_rotting(tmp_path, monkeypatch):
    """An empty (0-byte) file must not be mistaken for arming evidence -- e.g. a stale
    touch(), or a file created but never actually written to."""
    monkeypatch.setattr(da, "STATE", tmp_path)
    fut = _futures_dir(tmp_path)
    (fut / "mirror-broker-orders.jsonl").write_text("", encoding="utf-8")

    a = da.assess_futures()
    assert a["armable_unarmed"] is True
