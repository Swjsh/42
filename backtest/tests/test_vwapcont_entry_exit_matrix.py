"""Guard for backtest/tools/vwapcont_entry_exit_matrix.py (the OWED vwap_continuation
entry/exit matrix, STOP-A ground rule 11).

Protects the invariants that make the study trustworthy:
  1. The pre-registration hash/version pins used by the study match the frozen file --
     if someone edits the preregistration or the study's expected constants drift apart,
     this REDs (mirrors test_vwapcont_exit_ab_ship_gate.py's pinning style).
  2. C6 (no look-ahead): the VWAP structure-stop only fires on a CLOSED 5m bar's breach,
     at the NEXT bar's OPEN -- never mid-bar, never on the breaching bar's own close.
  3. The 24-cell grid is exactly what the preregistration says (no silent drift).
  4. shape_of() demotes STRUCT cells to the -50% catastrophe cap, never the raw axis value.
  5. battery()'s IS/OOS_old/fresh-tail date-boundary split is exact (off-by-one here would
     silently leak burned data into the "never touched" fresh-tail evidence the pass bar
     leans on).
  6. entry_fill() reproduces t3_entry_matrix.py's market/limit/patience/miss semantics.
  7. Real-fills anchor position reconstruction correctly AGGREGATES partial fills of the
     SAME order_id into one position (regression test for a bug caught live 2026-07-09:
     a 2-partial-fill entry was silently split into two positions, one of them a
     zero-exit-fill phantom, before this fix).

These are pure-logic guards (no OPRA fetch, no live ledger read) so they run in CI. The
real-fills numbers live in analysis/recommendations/vwapcont-entry-exit-matrix.json.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(BACKTEST / "tools"), str(REPO / "automation" / "state" / "fleet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

from autoresearch.infinite_ammo_discovery import session_vwap_asof  # noqa: E402
import vwapcont_entry_exit_matrix as m  # noqa: E402

PREREG = REPO / "analysis" / "recommendations" / "vwapcont-matrix-preregistration.json"


# ---------------------------------------------------------------------------------------------
# 1. PRE-REGISTRATION PIN
# ---------------------------------------------------------------------------------------------
def test_preregistration_file_exists_and_matches_module_constants():
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert preg["version"] == m.EXPECTED_PREREG_VERSION
    assert preg["signal_population"]["signal_set_sha256_16"] == m.EXPECTED_SHA16
    assert preg["signal_population"]["n_signals_old_window_le_20260515"] == 158
    assert preg["strategy"] == "vwap_continuation"


def test_preregistration_grid_has_24_cells_no_duplicates_control_present():
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    cells = preg["exit_grid"]["cells"]
    assert len(cells) == 24
    ids = [c["id"] for c in cells]
    assert len(ids) == len(set(ids)), "duplicate cell id in the frozen grid"
    assert preg["exit_grid"]["control_id"] == "P1T1F1L1"
    assert any(c["id"] == "P1T1F1L1" and c["stop"] == -0.06 and c["tp1"] == 0.40
              and c["frac"] == 0.8 and c["lock"] == ["fixed", 0.0] for c in cells)


def test_preregistration_pass_bar_requires_all_four_conditions():
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    stmt = preg["pass_bar"]["statement"]
    for token in ("IS", "fresh tail", "drop-top-3", "anchor"):
        assert token.lower().replace("-", "") in stmt.lower().replace("-", ""), token


def test_module_grid_loader_matches_preregistration_exactly():
    """load_grid_cells() must read the SAME frozen list -- no in-code grid drift from the file."""
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert m.load_grid_cells() == preg["exit_grid"]["cells"]


# ---------------------------------------------------------------------------------------------
# 2. C6 -- STRUCTURE STOP ONLY FIRES ON A CLOSED BAR'S BREACH, AT THE NEXT BAR'S OPEN
# ---------------------------------------------------------------------------------------------
def _mk_rth_vwap(rows: list[dict]) -> pd.DataFrame:
    """rows: [{'t': datetime, 'o','h','l','c': float, 'v': float}]. Builds the AS-OF vwap_asof
    column exactly the way build_vwap_cache does (session_vwap_asof), so the test exercises the
    SAME formula the study uses, not a hand-rolled stand-in."""
    df = pd.DataFrame({
        "timestamp_et": [r["t"] for r in rows],
        "open": [r["o"] for r in rows], "high": [r["h"] for r in rows],
        "low": [r["l"] for r in rows], "close": [r["c"] for r in rows],
        "volume": [r["v"] for r in rows],
    })
    df["vwap_asof"] = session_vwap_asof(df).values
    return df


def test_structure_stop_fires_at_next_bar_open_not_same_bar_close():
    """A call (side C) position whose price closes BELOW vwap on bar[2] must breach at
    bar[2].timestamp + 5min (== bar[3]'s open time), NOT at bar[2]'s own timestamp."""
    base = dt.datetime(2026, 1, 7, 9, 30)
    rows = [
        {"t": base, "o": 600, "h": 601, "l": 599.5, "c": 600.5, "v": 1000},               # bar0: vwap ~600.5, close>vwap (fine)
        {"t": base + dt.timedelta(minutes=5), "o": 600.5, "h": 601.5, "l": 600, "c": 601, "v": 1000},  # bar1: still above
        {"t": base + dt.timedelta(minutes=10), "o": 601, "h": 601, "l": 598, "c": 598.5, "v": 1000},   # bar2: CLOSES below cum vwap -> breach
        {"t": base + dt.timedelta(minutes=15), "o": 598.5, "h": 599, "l": 598, "c": 598.7, "v": 1000},  # bar3: whatever
    ]
    rth_vwap = _mk_rth_vwap(rows)
    entry_ts = base
    ss_time = m.structure_stop_time_vwap(rth_vwap, "C", entry_ts)
    assert ss_time is not None
    expected_fire_time = rows[2]["t"] + dt.timedelta(minutes=5)
    assert ss_time == expected_fire_time, (
        f"structure stop must fire at the BREACHING bar's close-time+5min (next bar's open), "
        f"got {ss_time}, expected {expected_fire_time}")
    # and it must NOT equal the breaching bar's own timestamp (that would be a same-bar,
    # not-yet-knowable fill -- the C6 violation this test exists to catch)
    assert ss_time != rows[2]["t"]


def test_structure_stop_puts_breach_is_close_above_vwap():
    base = dt.datetime(2026, 1, 7, 9, 30)
    rows = [
        {"t": base, "o": 600, "h": 600.5, "l": 599, "c": 599.3, "v": 1000},
        {"t": base + dt.timedelta(minutes=5), "o": 599.3, "h": 599.5, "l": 598.5, "c": 598.8, "v": 1000},
        {"t": base + dt.timedelta(minutes=10), "o": 598.8, "h": 601, "l": 598.5, "c": 600.9, "v": 1000},  # closes ABOVE cum vwap -> breach for P
    ]
    rth_vwap = _mk_rth_vwap(rows)
    ss_time = m.structure_stop_time_vwap(rth_vwap, "P", base)
    assert ss_time == rows[2]["t"] + dt.timedelta(minutes=5)


def test_structure_stop_returns_none_when_never_breached():
    base = dt.datetime(2026, 1, 7, 9, 30)
    rows = [
        {"t": base, "o": 600, "h": 601, "l": 599.5, "c": 600.6, "v": 1000},
        {"t": base + dt.timedelta(minutes=5), "o": 600.6, "h": 601.5, "l": 600.2, "c": 601.2, "v": 1000},
        {"t": base + dt.timedelta(minutes=10), "o": 601.2, "h": 602, "l": 600.9, "c": 601.8, "v": 1000},
    ]
    rth_vwap = _mk_rth_vwap(rows)
    assert m.structure_stop_time_vwap(rth_vwap, "C", base) is None


def test_structure_stop_fires_on_the_first_breach_not_a_later_one():
    """If bar[1] AND bar[3] both breach, the fire time must be bar[1]'s, not bar[3]'s."""
    base = dt.datetime(2026, 1, 7, 9, 30)
    rows = [
        {"t": base, "o": 600, "h": 601, "l": 599.5, "c": 600.6, "v": 1000},
        {"t": base + dt.timedelta(minutes=5), "o": 600.6, "h": 600.7, "l": 598, "c": 598.2, "v": 1000},   # first breach (C)
        {"t": base + dt.timedelta(minutes=10), "o": 598.2, "h": 601, "l": 598, "c": 600.9, "v": 1000},    # recovers above
        {"t": base + dt.timedelta(minutes=15), "o": 600.9, "h": 601, "l": 597, "c": 597.5, "v": 1000},    # breaches again
    ]
    rth_vwap = _mk_rth_vwap(rows)
    ss_time = m.structure_stop_time_vwap(rth_vwap, "C", base)
    assert ss_time == rows[1]["t"] + dt.timedelta(minutes=5)


def test_structure_stop_only_scans_bars_at_or_after_entry():
    """A breach BEFORE entry_ts must be ignored (the position wasn't open yet)."""
    base = dt.datetime(2026, 1, 7, 9, 30)
    rows = [
        {"t": base, "o": 600, "h": 600.2, "l": 597, "c": 597.2, "v": 1000},   # breach, but BEFORE entry
        {"t": base + dt.timedelta(minutes=5), "o": 597.2, "h": 601, "l": 597, "c": 600.9, "v": 1000},   # entry bar, above vwap
        {"t": base + dt.timedelta(minutes=10), "o": 600.9, "h": 601, "l": 600.5, "c": 600.8, "v": 1000},  # stays above
    ]
    rth_vwap = _mk_rth_vwap(rows)
    entry_ts = rows[1]["t"]
    assert m.structure_stop_time_vwap(rth_vwap, "C", entry_ts) is None


def test_structure_stop_none_when_rth_vwap_is_none():
    """Fail-open: missing day data -> no structure check, never a crash."""
    assert m.structure_stop_time_vwap(None, "C", dt.datetime(2026, 1, 7, 9, 30)) is None


# ---------------------------------------------------------------------------------------------
# 3. shape_of() -- STRUCT cells demote to the catastrophe cap, never the raw stop axis
# ---------------------------------------------------------------------------------------------
def test_shape_of_struct_cell_uses_catastrophe_cap():
    cell = {"id": "STRUCT_BASE", "stop": "STRUCT", "tp1": 0.40, "frac": 0.8, "lock": ["fixed", 0.0]}
    shape = m.shape_of(cell)
    assert shape["premium_stop_pct"] == -0.50
    assert m.is_structure_cell(cell) is True


def test_shape_of_premium_cell_uses_its_own_stop():
    cell = {"id": "P2T1F1L1", "stop": -0.12, "tp1": 0.40, "frac": 0.8, "lock": ["fixed", 0.0]}
    shape = m.shape_of(cell)
    assert shape["premium_stop_pct"] == -0.12
    assert m.is_structure_cell(cell) is False


def test_shape_of_runner_target_fixed_across_every_cell():
    """Not a swept axis -- every cell, incl. STRUCT, keeps the control's 2.5x runner target."""
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    for cell in preg["exit_grid"]["cells"]:
        assert m.shape_of(cell)["runner_target_pct"] == m.RUNNER_TARGET_PCT == 2.5


# ---------------------------------------------------------------------------------------------
# 4. battery() -- IS / OOS_old / fresh-tail date-boundary split (off-by-one would leak burned
#    data into the pass bar's decisive fresh-tail evidence)
# ---------------------------------------------------------------------------------------------
def _trade(date_str: str, pnl: float) -> dict:
    return {"date": dt.date.fromisoformat(date_str), "date_str": date_str, "side": "C",
            "direction": "bull", "band": "0.50-1.00", "pnl": pnl, "structure_fired": False}


def test_battery_is_oos_fresh_boundaries_exact():
    trades = [
        _trade("2025-12-31", 10.0),   # last day of IS
        _trade("2026-01-01", 20.0),   # first day of OOS_old (OOS_BOUNDARY)
        _trade("2026-05-15", 30.0),   # last day of OOS_old (OLD_END)
        _trade("2026-05-16", 40.0),   # first day of fresh tail
    ]
    b = m.battery(trades)
    assert b["is_n"] == 1 and b["is_exp"] == 10.0
    assert b["oos_old_n"] == 2 and b["oos_old_total"] == 50.0
    assert b["fresh_n"] == 1 and b["fresh_exp"] == 40.0


def test_battery_drop_top3_and_qpf():
    trades = [_trade(f"2025-01-{i:02d}", p) for i, p in
              enumerate([100.0, 90.0, 80.0, 5.0, -3.0, -4.0], start=1)]
    b = m.battery(trades)
    assert b["drop_top3"]["n_dropped"] == 3
    assert b["drop_top3"]["total_ex_topk"] == round(5.0 - 3.0 - 4.0, 2)
    assert b["drop_top3"]["positive"] is False   # 5-3-4 = -2, NOT positive
    assert b["n"] == 6


def test_battery_empty_returns_n_zero():
    assert m.battery([]) == {"n": 0}


# ---------------------------------------------------------------------------------------------
# 5. entry_fill() -- T3 (t3_entry_matrix.py) market/limit/patience/miss semantics
# ---------------------------------------------------------------------------------------------
def _bars(lows: list[float]) -> list:
    base = dt.datetime(2026, 1, 7, 9, 30)
    return [m.sss.NormBar(base + dt.timedelta(minutes=5 * i), 1.0, 1.0, lo, 1.0)
            for i, lo in enumerate(lows)]


def test_entry_fill_market_always_fills_at_signal_price():
    bars = _bars([0.9, 0.9, 0.9])
    f = m.entry_fill(bars, 1.00, {"type": "market"})
    assert f == {"entry": 1.00, "fill_idx": 0}


def test_entry_fill_limit_fills_when_low_dips_enough_within_patience():
    # delta=0.05 -> L = 0.95; fill needs low <= 0.95 - 0.01 = 0.94
    bars = _bars([0.99, 0.93, 0.80])   # dips enough on bar index 1
    f = m.entry_fill(bars, 1.00, {"type": "limit", "delta": 0.05, "patience": 2})
    assert f is not None and f["fill_idx"] == 1
    assert abs(f["entry"] - 0.95) < 1e-9


def test_entry_fill_limit_misses_when_never_dips_within_patience():
    bars = _bars([0.99, 0.98, 0.50])   # would fill on bar 2, but patience=2 only checks bars 0,1
    f = m.entry_fill(bars, 1.00, {"type": "limit", "delta": 0.05, "patience": 2})
    assert f is None   # honest miss -- priced at $0 by the caller, never silently converted


def test_entry_fill_limit_boundary_needs_a_full_cent_below_limit():
    # L=0.95 exactly; low==0.95 must NOT fill (needs <= L-0.01), low==0.94 must fill
    bars_no_fill = _bars([0.95])
    assert m.entry_fill(bars_no_fill, 1.00, {"type": "limit", "delta": 0.05, "patience": 1}) is None
    bars_fill = _bars([0.94])
    f = m.entry_fill(bars_fill, 1.00, {"type": "limit", "delta": 0.05, "patience": 1})
    assert f is not None and f["fill_idx"] == 0


# ---------------------------------------------------------------------------------------------
# 6. REGRESSION: partial-fill aggregation (real-fills anchor position reconstruction)
# ---------------------------------------------------------------------------------------------
def test_reconstruct_vwap_positions_aggregates_partial_fills_of_one_order(tmp_path, monkeypatch):
    """Bug caught live 2026-07-09: one order_id filled in 2 partial buy legs (1@1.65 + 2@1.67)
    was silently split into TWO positions (one a zero-exit-fill phantom) before this fix --
    verified against the REAL ledger (order 30d82b55...). This test reproduces that exact
    shape with synthetic data so the fix stays red-proofed without depending on live state."""
    core_dec = tmp_path / "core-decisions.jsonl"
    ledger = tmp_path / "fills-ledger.jsonl"

    core_dec.write_text(json.dumps({
        "ts_et": "2026-07-02T09:57:03", "account": "safe",
        "extra_exec": [{"setup": "vwap_continuation", "action": "PLACED",
                        "exec": {"symbol": "SPY260702C00750000", "qty": 3,
                                "broker": {"id": "order-partial-test"}}}],
    }) + "\n", encoding="utf-8")

    fills = [
        {"order_id": "order-partial-test", "arm": "safe-2", "symbol": "SPY260702C00750000",
         "side": "buy", "qty": 1.0, "price": 1.65, "ts_utc": "2026-07-02T13:57:15Z",
         "date_et": "2026-07-02", "is_option": True, "is_crypto": False},
        {"order_id": "order-partial-test", "arm": "safe-2", "symbol": "SPY260702C00750000",
         "side": "buy", "qty": 2.0, "price": 1.67, "ts_utc": "2026-07-02T13:57:16Z",
         "date_et": "2026-07-02", "is_option": True, "is_crypto": False},
        {"order_id": "exit-order", "arm": "safe-2", "symbol": "SPY260702C00750000",
         "side": "sell", "qty": 3.0, "price": 1.40, "ts_utc": "2026-07-02T14:11:15Z",
         "date_et": "2026-07-02", "is_option": True, "is_crypto": False},
    ]
    with ledger.open("w", encoding="utf-8") as fh:
        for f in fills:
            fh.write(json.dumps(f) + "\n")

    monkeypatch.setattr(m, "CORE_DECISIONS", core_dec)
    monkeypatch.setattr(m, "LEDGER", ledger)

    positions, status = m.reconstruct_vwap_positions()
    assert status == "ok"
    assert len(positions) == 1, f"partial fills must aggregate to ONE position, got {len(positions)}"
    p = positions[0]
    assert p["entry_qty"] == 3
    raw_avg = (1 * 1.65 + 2 * 1.67) / 3   # code computes pnl from the RAW average, rounds only at output
    assert p["entry_price"] == round(raw_avg, 4)
    assert len(p["exit_fills"]) == 1
    expected_pnl = round((1.40 - raw_avg) * 3 * 100, 2)
    assert p["actual_exit_pnl"] == expected_pnl


def test_reconstruct_vwap_positions_no_source_file_is_inconclusive_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "CORE_DECISIONS", tmp_path / "does-not-exist.jsonl")
    monkeypatch.setattr(m, "LEDGER", tmp_path / "also-missing.jsonl")
    positions, status = m.reconstruct_vwap_positions()
    assert positions == []
    assert status != "ok"


def test_build_real_fills_anchor_marks_inconclusive_when_unavailable(monkeypatch):
    monkeypatch.setattr(m, "reconstruct_vwap_positions", lambda: ([], "no_vwap_placed_orders_found"))
    anchor = m.build_real_fills_anchor(m.load_grid_cells(), {})
    assert anchor["anchor_verdict"] == "INCONCLUSIVE-ANCHOR"
    assert anchor["status"] == "UNAVAILABLE"
