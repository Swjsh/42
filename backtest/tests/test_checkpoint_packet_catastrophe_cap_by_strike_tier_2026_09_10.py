"""RED-proof for GOAL-LOSS-MECHANISMS-2026-09-08 L2: the catastrophe-cap-by-strike-tier
row must exist in checkpoint-2026-09-29-inventory.json and score via a registered scorer
(not fall through to UNKNOWN) so the nightly Gamma_CheckpointPacket regen and the 10-30
checkpoint markdown auto-discover it.

Before the L2 fix: prereg-catastrophe-cap-by-strike-tier-10-30-2026-09-08.json was FROZEN
on 2026-09-08 with NO matching inventory row and NO registered scorer -- confirmed absent
from checkpoint-packet-2026-09-10.json and SHADOW.md live before this fire. This test is
RED against that state (row missing entirely, or present with an unregistered scorer name
producing VERDICT_UNKNOWN) and GREEN once the row + scorer are both wired.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO / "setup" / "scripts"
for _p in (str(SCRIPTS_DIR), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import checkpoint_packet as cp  # noqa: E402


def _row():
    packet = cp.build_packet()
    return next(r for r in packet["rows"] if r["row_id"] == "catastrophe-cap-by-strike-tier")


def test_catastrophe_cap_by_strike_tier_row_exists_and_is_not_unknown():
    row = _row()
    assert row["verdict"] != cp.VERDICT_UNKNOWN, row.get("note")


def test_catastrophe_cap_by_strike_tier_routes_to_10_30_expansion():
    """This prereg's ACT branch WIDENS the ATM pool's catastrophe cap (-50% -> -70%) --
    a loosening, so per the goal's routing rule it must be classified expansion/2026-10-30,
    never 09-29, even though it is filed under the 09-29 inventory file's shared schema."""
    row = _row()
    assert row["classification"] == "expansion"
    assert row["checkpoint"] == "2026-10-30"


def test_catastrophe_cap_by_strike_tier_insufficient_n_while_frozen_live():
    """Live ledger as of this fire has 0 forward (post-2026-09-08) rows in either pool --
    must report INSUFFICIENT N, never a premature MET/NOT MET."""
    row = _row()
    assert row["verdict"] == cp.VERDICT_INSUFFICIENT_N
    assert row["numbers"]["atm_pool_forward_n"] == 0
    assert row["numbers"]["otm_pool_forward_n"] == 0


def test_catastrophe_cap_by_strike_tier_scorer_excludes_pre_freeze_rows(tmp_path, monkeypatch):
    """Synthetic ledger: rows dated on/before the prereg's frozen_at_et date must NOT
    count toward forward n (the pre-freeze disclosure look the prereg was built on must
    never leak into its own forward evidence), and pool membership must split by arm."""
    prereg_path = tmp_path / "prereg.json"
    prereg_path.write_text(json.dumps({
        "frozen_at_et": "2026-09-08 19:08 ET",
        "decision_rule": {"n_min_per_pool": 15},
    }), encoding="utf-8")

    ledger_path = tmp_path / "ledger.jsonl"
    rows = (
        # pre-freeze (same day as freeze) -- must be excluded
        [{"date_et": "2026-09-08", "arm": "safe-2"} for _ in range(20)]
        # pre-freeze, older -- must be excluded
        + [{"date_et": "2026-07-23", "arm": "bold-2"} for _ in range(16)]
        # forward, ATM pool
        + [{"date_et": "2026-09-09", "arm": "safe-2"} for _ in range(3)]
        + [{"date_et": "2026-09-10", "arm": "safe-3"} for _ in range(2)]
        + [{"date_et": "2026-09-10", "arm": "risky-1"} for _ in range(1)]
        # forward, OTM pool
        + [{"date_et": "2026-09-09", "arm": "bold-2"} for _ in range(5)]
        + [{"date_et": "2026-09-10", "arm": "risky-3"} for _ in range(1)]
    )
    ledger_path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    row = {
        "prereg_path": str(prereg_path.relative_to(REPO)) if prereg_path.is_relative_to(REPO)
        else str(prereg_path),
        "ledger_path": str(ledger_path.relative_to(REPO)) if ledger_path.is_relative_to(REPO)
        else str(ledger_path),
    }

    # cp._read_json / _read_jsonl resolve paths via REPO / row[...]; use absolute paths
    # directly by monkeypatching REPO join behavior is overkill -- instead call the
    # scorer's helpers directly against the absolute tmp paths.
    monkeypatch.setattr(cp, "REPO", tmp_path)
    result = cp._score_catastrophe_cap_by_strike_tier(
        {"prereg_path": "prereg.json", "ledger_path": "ledger.jsonl"}, "2026-09-10"
    )
    assert result["numbers"]["atm_pool_forward_n"] == 6  # 3 + 2 + 1
    assert result["numbers"]["otm_pool_forward_n"] == 6  # 5 + 1
    assert result["numbers"]["frozen_at_date"] == "2026-09-08"
    assert result["verdict"] == cp.VERDICT_INSUFFICIENT_N  # still < n_min_per_pool=15
