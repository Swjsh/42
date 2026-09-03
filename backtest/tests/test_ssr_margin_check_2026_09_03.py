"""Guard: SSR's fundability gauge must measure MARGIN, not notional.

WHY THIS EXISTS (queue item SSR-FUNDABILITY-MEASURES-NOTIONAL-NOT-MARGIN, filed 2026-08-23
Opus adjudication). ssr_shadow.py's `_fundability` computes notional/equity, but a futures
account posts MARGIN, not notional -- the binding constraint is day-trade margin AND
overnight/initial margin per contract, and SSR holds positions ACROSS SESSIONS, so overnight
margin is the real gate. setup/scripts/ssr_margin_check.py answers that directly against the
broker's own margin-report fields (GET /margin/accounts/{acct}/requirements), never the
notional/equity ratio.

This file pins `compute_fundability` (pure -- no network) against fixture snapshots shaped
exactly like the real payloads seen live (2026-09-03, sandbox account 5WW73759): a fully
populated margin report, a report with a missing symbol, an entry with only a flat
margin_requirement (no initial/maintenance split), and the empirically-observed 502/flat
account case that must resolve to DATA_MISSING/UNPROVEN, never GREEN.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "setup" / "scripts" / "ssr_margin_check.py"


@pytest.fixture(scope="module")
def mc():
    for p in ("backtest", "setup/scripts"):
        pp = str(REPO / p)
        if pp not in sys.path:
            sys.path.insert(0, pp)
    spec = importlib.util.spec_from_file_location("_ssr_margin_check_probe", MODULE)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_ssr_margin_check_probe"] = m
    spec.loader.exec_module(m)
    return m


def _snapshot(*, groups=None, errors=None, connected=True):
    return {
        "connected": connected, "account_number": "5WW73759",
        "positions": [], "margin_report_groups": groups,
        "account_balance": None, "errors": errors or [],
    }


# ── the empirically-observed live case (2026-09-03): must be DATA_MISSING/UNPROVEN ─────────
def test_flat_account_with_502_margin_endpoint_is_data_missing_and_unproven(mc):
    """Live sandbox probe 2026-09-03 (3 consecutive attempts): get_positions returned [],
    get_margin_requirements 502'd every time. margin_report_groups is therefore None. Neither
    MNQ nor MGC can have a real day/overnight figure -- the gauge must read UNPROVEN, and
    NEVER borrow the account-level aggregate balance fields (observed same day: those read
    $17,107.20 despite zero positions -- an internally inconsistent stale snapshot)."""
    snap = _snapshot(groups=None, errors=["get_margin_requirements_failed:TastytradeError:502"])
    r = mc.compute_fundability(snap, equity=2000.0, equity_source="account.json:equity")
    assert r["any_missing"] is True
    assert r["day_ok"] is False
    assert r["overnight_ok"] is False
    assert r["gauge"] == "UNPROVEN"
    for sym in ("MNQ", "MGC"):
        assert r["per_symbol"][sym]["day_margin"] is None
        assert r["per_symbol"][sym]["overnight_margin"] is None
        assert "DATA_MISSING" in r["per_symbol"][sym]["source"]
    assert r["combined_day_margin_usd_at_qty"] is None
    assert r["combined_overnight_margin_usd_at_qty"] is None


def test_gauge_never_reads_green_from_account_level_aggregate_fields(mc):
    """Even when account_balance IS present (get_balances succeeded) with nonzero aggregate
    futures_intraday/overnight_margin_requirement, compute_fundability must never substitute
    those into a per-symbol figure -- only margin_report_groups counts."""
    snap = _snapshot(groups=None, errors=[])
    snap["account_balance"] = {
        "futures_intraday_margin_requirement": 17107.2,
        "futures_overnight_margin_requirement": 17107.2,
        "net_liquidating_value": 2000.0,
    }
    r = mc.compute_fundability(snap, equity=2000.0, equity_source="account.json:equity")
    assert r["gauge"] == "UNPROVEN", (
        "gauge went GREEN off the account-level aggregate balance fields -- those price "
        "whatever the account holds in aggregate, not qty-of-one-symbol, and must never be "
        "laundered into a per-symbol day/overnight figure")
    assert r["broker_account_balance"]["futures_overnight_margin_requirement"] == 17107.2


# ── fully populated margin report (initial/maintenance split present) ──────────────────────
def test_full_split_data_computes_day_and_overnight_and_can_go_green(mc):
    groups = [
        {"underlying_symbol": "MNQ", "margin_requirement": 300.0,
         "initial_requirement": 300.0, "maintenance_requirement": 450.0},
        {"underlying_symbol": "MGC", "margin_requirement": 200.0,
         "initial_requirement": 200.0, "maintenance_requirement": 320.0},
    ]
    snap = _snapshot(groups=groups)
    r = mc.compute_fundability(snap, equity=5000.0, equity_source="account.json:equity")
    assert r["any_missing"] is False
    assert r["per_symbol"]["MNQ"] == {
        "day_margin": 300.0, "overnight_margin": 450.0,
        "source": "GET /margin/accounts/{account}/requirements",
    }
    assert r["per_symbol"]["MGC"]["overnight_margin"] == 320.0
    # qty=3 (imported from ssr_shadow.QTY) -> combined day = (300+200)*3 = 1500,
    # combined overnight = (450+320)*3 = 2310 -- both <= 5000 equity -> OK -> GREEN
    assert r["qty"] == 3
    assert r["combined_day_margin_usd_at_qty"] == pytest.approx(1500.0)
    assert r["combined_overnight_margin_usd_at_qty"] == pytest.approx(2310.0)
    assert r["day_ok"] is True
    assert r["overnight_ok"] is True
    assert r["gauge"] == "GREEN"


def test_overnight_margin_exceeding_equity_fails_gauge_even_if_day_ok(mc):
    """SSR holds across sessions -- day_ok alone must never be enough to arm GREEN."""
    groups = [
        {"underlying_symbol": "MNQ", "margin_requirement": 300.0,
         "initial_requirement": 300.0, "maintenance_requirement": 900.0},
        {"underlying_symbol": "MGC", "margin_requirement": 200.0,
         "initial_requirement": 200.0, "maintenance_requirement": 700.0},
    ]
    snap = _snapshot(groups=groups)
    # day total = (300+200)*3 = 1500 <= 2000 equity -> day_ok True
    # overnight total = (900+700)*3 = 4800 > 2000 equity -> overnight_ok False
    r = mc.compute_fundability(snap, equity=2000.0, equity_source="account.json:equity")
    assert r["day_ok"] is True
    assert r["overnight_ok"] is False
    assert r["gauge"] == "UNPROVEN"


# ── partial data: one symbol present, one missing ───────────────────────────────────────────
def test_one_symbol_missing_marks_the_whole_gauge_unproven(mc):
    """Only MGC held right now (MNQ position closed / never opened) -- MNQ has no groups
    entry. The WHOLE gauge must go UNPROVEN, never GREEN on partial coverage."""
    groups = [
        {"underlying_symbol": "MGC", "margin_requirement": 200.0,
         "initial_requirement": 200.0, "maintenance_requirement": 320.0},
    ]
    snap = _snapshot(groups=groups)
    r = mc.compute_fundability(snap, equity=5000.0, equity_source="account.json:equity")
    assert r["any_missing"] is True
    assert r["per_symbol"]["MGC"]["overnight_margin"] == 320.0
    assert r["per_symbol"]["MNQ"]["overnight_margin"] is None
    assert r["gauge"] == "UNPROVEN"


# ── flat margin_requirement only, no initial/maintenance split ─────────────────────────────
def test_flat_margin_requirement_used_for_both_legs_and_labeled(mc):
    groups = [
        {"underlying_symbol": "MNQ", "margin_requirement": 350.0,
         "initial_requirement": None, "maintenance_requirement": None},
        {"underlying_symbol": "MGC", "margin_requirement": 250.0,
         "initial_requirement": None, "maintenance_requirement": None},
    ]
    snap = _snapshot(groups=groups)
    r = mc.compute_fundability(snap, equity=5000.0, equity_source="account.json:equity")
    assert r["any_missing"] is False
    assert r["per_symbol"]["MNQ"]["day_margin"] == 350.0
    assert r["per_symbol"]["MNQ"]["overnight_margin"] == 350.0
    assert "split unavailable" in r["per_symbol"]["MNQ"]["source"]
    assert r["gauge"] == "GREEN"  # both legs equal the flat figure, still <= equity


# ── equity missing entirely ─────────────────────────────────────────────────────────────────
def test_missing_equity_never_fabricated_into_ok(mc):
    groups = [
        {"underlying_symbol": "MNQ", "margin_requirement": 300.0,
         "initial_requirement": 300.0, "maintenance_requirement": 450.0},
        {"underlying_symbol": "MGC", "margin_requirement": 200.0,
         "initial_requirement": 200.0, "maintenance_requirement": 320.0},
    ]
    snap = _snapshot(groups=groups)
    r = mc.compute_fundability(snap, equity=None, equity_source="unavailable")
    assert r["day_ok"] is False
    assert r["overnight_ok"] is False
    assert r["gauge"] == "UNPROVEN"


# ── symbols/qty are derived from the live SSR spec, never hand-typed ───────────────────────
def test_symbols_and_qty_are_imported_from_live_ssr_spec_not_hardcoded(mc):
    import ssr_shadow  # noqa: PLC0415
    assert mc.SYMBOLS == tuple(ssr_shadow.CONFIGS)
    assert mc.QTY == ssr_shadow.QTY


def test_never_raises_on_a_completely_empty_snapshot(mc):
    r = mc.compute_fundability({}, equity=2000.0, equity_source="account.json:equity")
    assert r["gauge"] == "UNPROVEN"
    assert r["any_missing"] is True


def test_state_file_written_by_run_has_the_required_top_level_shape(mc, tmp_path, monkeypatch):
    """run() must persist to STATE_DIR/ssr-fundability.json with the {as_of, per_symbol, qty,
    equity, day_ok, overnight_ok} shape the queue item asks for. Network is monkeypatched out
    entirely -- this test makes ZERO broker calls."""
    fake_out = tmp_path / "ssr-fundability.json"
    monkeypatch.setattr(mc, "OUT_FILE", fake_out)
    monkeypatch.setattr(mc, "STATE_DIR", tmp_path)
    monkeypatch.setattr(mc, "fetch_margin_snapshot",
                        lambda **kw: _snapshot(groups=[
                            {"underlying_symbol": "MNQ", "margin_requirement": 300.0,
                             "initial_requirement": 300.0, "maintenance_requirement": 450.0},
                            {"underlying_symbol": "MGC", "margin_requirement": 200.0,
                             "initial_requirement": 200.0, "maintenance_requirement": 320.0},
                        ]))
    monkeypatch.setattr(mc, "_load_book_equity", lambda: (5000.0, "account.json:equity"))
    r = mc.run()
    assert fake_out.exists()
    import json
    on_disk = json.loads(fake_out.read_text(encoding="utf-8"))
    for key in ("as_of", "per_symbol", "qty", "equity", "day_ok", "overnight_ok"):
        assert key in on_disk, f"ssr-fundability.json is missing required field {key}"
    assert on_disk["gauge"] == "GREEN"
    assert r["gauge"] == "GREEN"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
