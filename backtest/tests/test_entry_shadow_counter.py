"""Guards for the V-d1/V-e3 forward shadow counter (LANE 4, 2026-08-06).

Pins: (1) V-d1 semantics (last closed 5m bar against trade direction blocks; abstain on
no closed bar), (2) V-e3 semantics (structure ABSENCE blocks; quorum 20 abstains),
(3) idempotent tally upsert (reruns never dupe), (4) summary math vs the forward prereg's
F-gates, (5) the SHADOW-ONLY surface: neither module can reach an order-placement path.

RED-proof protocol (run manually, after-hours): mutate entry_quality_ledger.blocked_by's
V-d1 comparison (!= -> ==), watch test_vd1_* go RED, restore byte-identical, watch green.
Green-without-RED-proof is NOT a guard.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import entry_shadow_counter as esc  # noqa: E402
import entry_quality_ledger as eql  # noqa: E402


def _event(**kw) -> dict:
    base = {
        "date_et": "2026-08-06", "activity_id": "A1", "arm": "safe-2",
        "symbol": "SPY260806P00770000", "opt_side": "P", "ts_et": "2026-08-06T10:31:53",
        "qty": 3.0, "price": 1.28, "pnl": 100.0,
        "n_closed_5m": 12, "n_closed_1m": 60,
        "d_last5_dir": "down", "s1_kind": "BOS",
    }
    base.update(kw)
    return base


# ---------- V-d1 semantics ------------------------------------------------------------------

def test_vd1_blocks_last_bar_against_long():
    e = _event(opt_side="C", d_last5_dir="down")
    assert esc.shadow_flags(e)["vd1"] is True


def test_vd1_keeps_last_bar_with_long():
    e = _event(opt_side="C", d_last5_dir="up")
    assert esc.shadow_flags(e)["vd1"] is False


def test_vd1_blocks_last_bar_against_put():
    e = _event(opt_side="P", d_last5_dir="up")
    assert esc.shadow_flags(e)["vd1"] is True


def test_vd1_keeps_last_bar_with_put():
    e = _event(opt_side="P", d_last5_dir="down")
    assert esc.shadow_flags(e)["vd1"] is False


def test_vd1_abstains_with_no_closed_bar():
    e = _event(d_last5_dir=None)
    assert esc.shadow_flags(e)["vd1"] is None


def test_vd1_flat_bar_blocks():
    # frozen: flat (close==open) is not agreement, so it blocks
    e = _event(opt_side="C", d_last5_dir="flat")
    assert esc.shadow_flags(e)["vd1"] is True


# ---------- V-e3 semantics ------------------------------------------------------------------

def test_ve3_blocks_structure_absence():
    e = _event(n_closed_1m=25, s1_kind=None)
    assert esc.shadow_flags(e)["ve3"] is True


def test_ve3_keeps_when_any_event_exists():
    e = _event(n_closed_1m=25, s1_kind="CHoCH")
    assert esc.shadow_flags(e)["ve3"] is False


def test_ve3_abstains_below_quorum():
    # frozen: fewer than 20 closed 1m bars -> ABSTAIN (never block), even with no event
    e = _event(n_closed_1m=19, s1_kind=None)
    assert esc.shadow_flags(e)["ve3"] is None


def test_ve3_quorum_boundary_exactly_20_is_eligible():
    e = _event(n_closed_1m=20, s1_kind=None)
    assert esc.shadow_flags(e)["ve3"] is True


# ---------- tally upsert idempotence --------------------------------------------------------

def test_upsert_is_idempotent_per_activity_id():
    r1 = esc.tally_row(_event(activity_id="X1", pnl=-50.0))
    r2 = esc.tally_row(_event(activity_id="X2", pnl=25.0, ts_et="2026-08-06T11:00:00"))
    merged, n_new, n_upd = esc.upsert_rows([], [r1, r2])
    assert (len(merged), n_new, n_upd) == (2, 2, 0)
    merged2, n_new2, n_upd2 = esc.upsert_rows(merged, [r1, r2])
    assert (len(merged2), n_new2, n_upd2) == (2, 0, 2)
    assert {r["activity_id"] for r in merged2} == {"X1", "X2"}


# ---------- summary math vs forward gates ---------------------------------------------------

def test_summary_forward_delta_and_f_gates():
    rows = [
        esc.tally_row(_event(activity_id="B1", opt_side="C", d_last5_dir="down", pnl=-100.0)),
        esc.tally_row(_event(activity_id="B2", opt_side="C", d_last5_dir="up", pnl=200.0)),
        esc.tally_row(_event(activity_id="B3", opt_side="C", d_last5_dir="down", pnl=40.0)),
    ]
    s = esc.build_summary(rows, "2026-08-06T19:00:00")
    v = s["vd1"]
    assert v["n_blocked"] == 2 and v["n_kept"] == 1
    assert v["forward_delta_usd"] == 60.0          # -(-100 + 40)
    assert v["blocked_winner_usd"] == 40.0 and v["blocked_loser_usd"] == 100.0
    assert v["f_gate_progress"]["F1_direction_delta_positive"] is True
    assert v["f_gate_progress"]["F2_not_winner_killer"] is True
    assert v["f_gate_progress"]["F3_frequency_n_blocked_ge_8"] is False
    assert s["_meta"]["forward_window"]["sessions_elapsed"] == 1


# ---------- shadow-only surface -------------------------------------------------------------

def test_nightly_fold_is_wired_into_winner_autopsy():
    """C35: built != shipped. The counter must actually ride the nightly fire -- pin the
    fold block so a refactor of winner_autopsy.main cannot silently drop it."""
    src = (REPO / "setup" / "scripts" / "winner_autopsy.py").read_text(encoding="utf-8")
    assert "import entry_shadow_counter" in src, "nightly fold missing from winner_autopsy"
    assert '"entry_shadow"' in src, "entry_shadow payload key missing from winner_autopsy"


def test_shadow_only_no_order_placement_surface():
    """The counter and the ledger must be structurally incapable of trading: no order
    placement call, no signal-file write, no engine import. C6-adjacent but really C7:
    a 'measurement-only' organ that could place an order is a lie waiting to happen."""
    forbidden = ("place_option_order", "place_stock_order", "submit_order",
                 "shared-signal.json", "entry_manager", "fleet_executor",
                 "heartbeat_core")
    for mod in (esc, eql):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        for bad in forbidden:
            assert bad not in src, f"{mod.__name__} references {bad!r} -- shadow-only broken"
