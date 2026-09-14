"""Guards for the SD-ZONE WHAT-IF shadow lane (GOAL-SD-LIQUIDITY-ZONES-2026-09-11 item f):
`backtest/lib/sd_zone_whatif_sim.py` (pure simulation core) + `setup/scripts/sd_zone_whatif.py`
(I/O orchestrator). Offline only -- no live CDP/Alpaca dependency; every touch/confirmation/
sizing/walk test below runs against synthetic DataFrames.

Covers (deliverable D):
  1. Never imports a trading-path module (heartbeat_core / build_shared_signal / fleet_broker
     / exit_actuator / any order-placing module) and never writes key-levels.json / params*.json
     / any automation/state/fleet/* file (source-scan on both files).
  2. No look-ahead: a zone snapshot whose as_of postdates the touch minute is never used.
  3. Unpriceable / slot-busy legs are never synthesized a P&L and never counted in totals.
  4. Single slot per (confirmation, exit_variant, strike_label) cell across a day.
  5. Idempotent re-run: re-simulating a day replaces that day's rows, count unchanged.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "setup" / "scripts"), str(REPO / "backtest" / "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import sd_zone_whatif_sim as core  # noqa: E402
import sd_zone_whatif as cli  # noqa: E402

CLI_SRC = (REPO / "setup" / "scripts" / "sd_zone_whatif.py").read_text(encoding="utf-8")
LIB_SRC = (REPO / "backtest" / "lib" / "sd_zone_whatif_sim.py").read_text(encoding="utf-8")

FORBIDDEN_MODULES = ("heartbeat_core", "build_shared_signal", "fleet_broker", "exit_actuator",
                      "fleet_live", "fleet_executor")
FORBIDDEN_WRITE_TARGETS = ("key-levels.json", "params.json", "params_safe.json", "params_bold.json")


# --------------------------------------------------------------------------- 1. never on the trading path

def test_never_imports_a_trading_path_module():
    import_re = re.compile(r"^\s*(?:from|import)\s+([\w.]+)", re.MULTILINE)
    for src, name in ((CLI_SRC, "sd_zone_whatif.py"), (LIB_SRC, "sd_zone_whatif_sim.py")):
        modules = {m.split(".")[0] for m in import_re.findall(src)}
        hit = modules & set(FORBIDDEN_MODULES)
        assert not hit, f"{name} imports forbidden trading-path module(s): {hit}"


def test_never_writes_a_frozen_trading_path_file():
    """Neither file may WRITE key-levels.json / params*.json -- mere prose mentions (this
    guard's own docstring disclosure, e.g.) are fine; a write call adjacent to the filename
    is not. Scanned per-line so a docstring sentence naming the forbidden target next to
    'never'/'forbidden' is distinguished from an actual open(...)/write_text(...) call."""
    write_call_re = re.compile(r"open\(|\.write_text\(|json\.dump\(|\.to_csv\(")
    for src, name in ((CLI_SRC, "sd_zone_whatif.py"), (LIB_SRC, "sd_zone_whatif_sim.py")):
        for target in FORBIDDEN_WRITE_TARGETS:
            for line in src.splitlines():
                if target in line:
                    assert not write_call_re.search(line), (
                        f"{name} appears to WRITE forbidden target {target!r}: {line.strip()!r}")
        assert "place_option_order" not in src and "place_stock_order" not in src


def test_never_writes_under_automation_state_fleet():
    """The only fleet references allowed are READS (strategies.RIBBON_RIDE, exit_manager via
    walk_exit_manager, accounts.json's starting_equity) -- never a write call against that dir."""
    write_calls = re.findall(r'(?:open|write_text|to_csv)\([^)]*fleet[^)]*["\']w', CLI_SRC + LIB_SRC)
    assert not write_calls


# --------------------------------------------------------------------------- 2. no look-ahead

def test_zone_set_as_of_never_uses_a_future_snapshot():
    snapshots = [
        {"as_of": "2026-09-14T09:00:00", "zones": [{"low": 750.0, "high": 751.0, "kind": "demand"}]},
        {"as_of": "2026-09-14T13:07:17", "zones": [{"low": 757.88, "high": 758.58, "kind": "demand"}]},
    ]
    # a touch at 11:06 must see ONLY the 09:00 snapshot -- the 13:07 zone did not exist yet.
    zones, caveat = core.zone_set_as_of(snapshots, dt.datetime(2026, 9, 14, 11, 6))
    assert zones == snapshots[0]["zones"]
    assert caveat == ""

    # a touch before ANY snapshot exists gets an empty zone set, never the earliest one.
    zones, caveat = core.zone_set_as_of(snapshots, dt.datetime(2026, 9, 14, 8, 0))
    assert zones == []
    assert caveat == "no_snapshot_before_touch"

    # a touch after the later snapshot correctly sees the newer zone set.
    zones, caveat = core.zone_set_as_of(snapshots, dt.datetime(2026, 9, 14, 14, 0))
    assert zones == snapshots[1]["zones"]


def test_single_eod_snapshot_is_labeled_eod_snapshot_only():
    snapshots = [{"as_of": "2026-09-12T23:47:00", "zones": [{"low": 1.0, "high": 2.0, "kind": "demand"}]}]
    zones, caveat = core.zone_set_as_of(snapshots, dt.datetime(2026, 9, 12, 10, 0))
    assert zones == snapshots[0]["zones"]
    assert caveat == "eod_snapshot_only"


def test_find_touch_events_respects_the_entry_gate_and_hard_stop():
    zone = {"low": 750.0, "high": 750.5, "kind": "demand"}
    bars = [
        {"ts": dt.datetime(2026, 9, 14, 9, 31), "open": 750.2, "high": 750.3, "low": 750.2, "close": 750.2},
        {"ts": dt.datetime(2026, 9, 14, 11, 6), "open": 750.6, "high": 750.6, "low": 750.2, "close": 750.6},
        {"ts": dt.datetime(2026, 9, 14, 15, 45), "open": 750.2, "high": 750.3, "low": 750.2, "close": 750.2},
    ]

    def lookup(ts):
        return [zone], ""

    events = core.find_touch_events(bars, lookup)
    # 09:31 is before the 09:35 gate, 15:45 is after the 15:40 hard stop -- only 11:06 counts.
    assert len(events) == 1
    assert events[0]["touch_ts"] == dt.datetime(2026, 9, 14, 11, 6)


# --------------------------------------------------------------------------- 3. unpriceable never synthesized

def test_priced_filter_excludes_unpriceable_and_slot_busy_rows():
    rows = [
        {"pnl_per_contract": 12.5, "unpriceable": False, "skipped_reason": None},
        {"pnl_per_contract": None, "unpriceable": True, "skipped_reason": "no_option_bars"},
        {"pnl_per_contract": None, "unpriceable": False, "skipped_reason": "slot_busy"},
    ]
    priced = cli._priced(rows)
    assert len(priced) == 1
    assert priced[0]["pnl_per_contract"] == 12.5


def test_build_summary_totals_never_include_unpriceable_rows():
    rows = [
        {"day": "2026-09-14", "confirmation": "structure_shift", "exit_variant": "ribbon_ride",
         "strike_label": "ATM", "lookahead_caveat": "", "unpriceable": False, "skipped_reason": None,
         "pnl_per_contract": 100.0, "arms": {a: {"qty": 3, "pnl": 300.0} for a in core.ARM_IDS}},
        {"day": "2026-09-14", "confirmation": "structure_shift", "exit_variant": "ribbon_ride",
         "strike_label": "ATM", "lookahead_caveat": "", "unpriceable": True, "skipped_reason": "no_option_bars",
         "pnl_per_contract": None, "arms": None},
    ]
    today_result = {"narrative": [], "warnings": []}
    summary = cli.build_summary(rows, today_result, "2026-09-14")
    assert summary["primary_variant"]["n_legs"] == 1
    assert summary["primary_variant"]["total_per_contract"] == 100.0
    assert summary["n_ledger_rows_total"] == 2
    assert summary["n_priced_rows_total"] == 1


# --------------------------------------------------------------------------- 4. single slot per cell

def test_simulate_day_enforces_single_slot_per_cell(monkeypatch):
    """Two demand touches of DIFFERENT zones on the same synthetic day, close enough in time
    that the first (touch_close x ribbon_ride x <strike>) leg is still open when the second
    touch confirms -- the second must be recorded as 'slot_busy', not walked as a second
    concurrent hypothetical position in that same cell.

    Design: SPY sits flat at 756.0 all day (above BOTH zones' far edges, so touch_close
    confirms on the very bar each touch happens AND the structure stop -- trigger_level =
    zone.high, fires when the 5-min close drops BELOW it -- never trips for zone_a's leg,
    which is the whole point: it must still be open when zone_b's touch arrives 5 minutes
    later). Each touch is a single-minute LOW dip into its own zone band, nothing else
    about the tape moves."""
    day = "2026-09-14"
    zone_a = {"low": 750.0, "high": 750.5, "kind": "demand", "touches_uniform": 5}
    zone_b = {"low": 755.0, "high": 755.5, "kind": "demand", "touches_uniform": 5}
    snapshots = [{"as_of": f"{day}T09:00:00", "zones": [zone_a, zone_b]}]

    def mins(h, m):
        return dt.datetime(2026, 9, 14, h, m)

    bars_1m = []
    t = mins(9, 35)
    while t <= mins(15, 39):
        bars_1m.append({"ts": t, "open": 756.0, "high": 756.0, "low": 756.0, "close": 756.0, "volume": 100})
        t += dt.timedelta(minutes=1)

    def set_bar(ts, **kw):
        for b in bars_1m:
            if b["ts"] == ts:
                b.update(kw)

    set_bar(mins(10, 0), low=750.1)   # dips into zone_a only
    set_bar(mins(10, 5), low=755.1)   # dips into zone_b only

    bars_5m = []
    t = mins(9, 30)
    while t <= mins(15, 55):
        bars_5m.append({"ts": t, "open": 756.0, "high": 756.0, "low": 756.0, "close": 756.0})
        t += dt.timedelta(minutes=5)

    monkeypatch.setattr(cli, "load_zone_snapshots", lambda d: snapshots)
    monkeypatch.setattr(cli, "fetch_spy_day_bars",
                         lambda d, tf: bars_1m if tf == "1Min" else bars_5m)

    class _FlatOptDf:
        """A flat $1.00 option series long enough to cover the whole RTH window, every
        minute, so entries never go unpriceable and the walk resolves via time_stop."""
        pass

    def fake_fetch_1min(symbol, date_et):
        rows = []
        t2 = mins(9, 30)
        while t2 <= mins(16, 0):
            rows.append({"timestamp_et": t2, "open": 1.00, "high": 1.02, "low": 0.98, "close": 1.00})
            t2 += dt.timedelta(minutes=1)
        return pd.DataFrame(rows), "fake"

    monkeypatch.setattr(cli, "fetch_1min_cached", fake_fetch_1min)
    monkeypatch.setattr(cli, "option_symbol", lambda date, strike, side: f"SPY_{strike}{side}")

    arm_equity = {a: 5000.0 for a in core.ARM_IDS}
    result = cli.simulate_day(day, arm_equity)
    rows = result["rows"]
    assert rows, "expected at least one row"

    busy_rows = [r for r in rows if r.get("skipped_reason") == "slot_busy"]
    # zone_b's touch_close/ribbon_ride/ATM cell entry lands while zone_a's own leg in that
    # SAME cell is still open (both confirm same-bar, entries 1 minute apart, RIBBON_RIDE's
    # structure stop/TP1/trail rarely resolve within 60 seconds against a flat option tape)
    # -- at least one slot_busy row must exist, and it must carry no fabricated P&L.
    assert busy_rows, "expected at least one slot_busy row (single-slot-per-cell enforcement)"
    for r in busy_rows:
        assert r["entry_ts_et"] is None
        assert r["unpriceable"] is False  # disclosed as busy, not silently mis-tagged unpriceable


# --------------------------------------------------------------------------- 5. idempotent re-run

def test_write_ledger_is_idempotent_per_day(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(cli, "LEDGER_OUT", ledger)
    rows = [{"day": "2026-09-14", "touch_ts_et": "x", "pnl_per_contract": 1.0}]
    n1 = cli.write_ledger("2026-09-14", rows, reference_day="2026-09-14")
    n2 = cli.write_ledger("2026-09-14", rows, reference_day="2026-09-14")
    assert n1 == 1
    assert n2 == 1, "re-running the same day must REPLACE its rows, not accumulate duplicates"
    on_disk = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(on_disk) == 1


def test_write_ledger_prunes_rows_older_than_retention(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(cli, "LEDGER_OUT", ledger)
    old_day = (dt.date(2026, 9, 14) - dt.timedelta(days=core.CANONICAL_QTY and cli.RETENTION_DAYS + 5)).isoformat()
    cli.write_ledger(old_day, [{"day": old_day, "pnl_per_contract": 1.0}], reference_day=old_day)
    n = cli.write_ledger("2026-09-14", [{"day": "2026-09-14", "pnl_per_contract": 2.0}],
                          reference_day="2026-09-14")
    assert n == 1, "a row far older than RETENTION_DAYS must be pruned on the next write"


# --------------------------------------------------------------------------- strike math sanity

def test_strike_for_label_matches_itm_otm_sign_convention():
    spot = 758.30
    call_otm = core.strike_for_label(spot, "OTM-1", "C")
    call_itm = core.strike_for_label(spot, "ITM-1", "C")
    put_otm = core.strike_for_label(spot, "OTM-1", "P")
    put_itm = core.strike_for_label(spot, "ITM-1", "P")
    atm = core.atm_strike(spot) if hasattr(core, "atm_strike") else round(spot)
    assert call_otm > atm  # OTM call strikes ABOVE spot
    assert call_itm < atm  # ITM call strikes BELOW spot
    assert put_otm < atm   # OTM put strikes BELOW spot
    assert put_itm > atm   # ITM put strikes ABOVE spot


def test_size_qty_floors_at_min_contracts():
    # a huge premium collapses the risk-cap qty below the arm's min_contracts floor.
    qty = core.size_qty(entry_premium=50.0, equity=5000.0, arm_id="safe-2")
    assert qty == 3  # Safe min_contracts floor, per CLAUDE.md Rule 6
    qty_bold = core.size_qty(entry_premium=50.0, equity=5000.0, arm_id="bold-2")
    assert qty_bold == 5  # Bold min_contracts floor
