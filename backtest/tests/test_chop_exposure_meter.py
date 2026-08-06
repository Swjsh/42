"""Guards for the CHOP EXPOSURE METER (chop_exposure_meter.py) + its firm_brief line.

Pins, per the frozen prereg (chop-defense-prereg-2026-08-06.json @ 5737488a):
  1. exact per-column counts on a synthetic day (ord>=4 / against-V-d1 /
     zero-structure / rr<0.70 / consec-loss runs),
  2. the fleet-pooled REALIZED path: floor, latch time, would_trip at -600
     (the BRK600 forward-evidence recorder),
  3. fail-open: bars unavailable -> bar columns None + WARN, ledger columns live,
  4. structure-event PARITY with the admissibility battery's definition,
  5. firm_brief's chop line: fail-open on a missing artifact, renders the line
     from a real one, and NEVER touches any other section.

All synthetic; no network (bars injected, fetch=False).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "setup" / "scripts", REPO / "backtest" / "tools",
           REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import chop_exposure_meter as cm  # noqa: E402

DAY = "2026-08-06"


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _bar(hhmm: str, o: float, h: float, l: float, c: float) -> dict:  # noqa: E741
    hh, mm = hhmm.split(":")
    return {"t": dt.datetime(2026, 8, 6, int(hh), int(mm)), "o": o, "h": h, "l": l, "c": c}


def _today_bars() -> list[dict]:
    """Swing high 103 at idx2 (confirmed idx4); break close 103.5 > 103 at idx5
    -> ONE bullish event, knowable at 10:00. Last closed bar at 09:50 is idx3
    (DOWN); last closed bar at >=10:05 is idx6 (UP)."""
    return [
        _bar("09:30", 100.0, 101.0, 99.0, 100.0),
        _bar("09:35", 100.0, 102.0, 100.0, 101.0),
        _bar("09:40", 101.0, 103.0, 101.0, 102.0),   # swing high 103
        _bar("09:45", 102.0, 102.5, 101.0, 101.5),   # DOWN bar
        _bar("09:50", 101.5, 101.8, 100.8, 101.0),
        _bar("09:55", 101.0, 104.0, 101.0, 103.5),   # break bar (close > 103)
        _bar("10:00", 103.5, 104.0, 103.0, 103.8),   # UP bar
    ]


def _bars_by_day() -> dict:
    """Today (range 5.0 by 10:05) + 20 prior trading days each with range 10.0
    from the first bar -> rr = 0.4..0.5 < 0.70 for every entry."""
    out = {DAY: _today_bars()}
    d = dt.date(2026, 8, 6)
    added = 0
    while added < 20:
        d -= dt.timedelta(days=1)
        if d.weekday() >= 5:
            continue
        bars = []
        for i, hhmm in enumerate(("09:30", "09:35", "09:40", "09:45", "09:50",
                                  "09:55", "10:00")):
            hh, mm = hhmm.split(":")
            bars.append({"t": dt.datetime(d.year, d.month, d.day, int(hh), int(mm)),
                         "o": 100.0, "h": 105.0, "l": 95.0, "c": 100.0})
            del i
        out[d.isoformat()] = bars
        added += 1
    return out


def _fill(arm: str, sym: str, side: str, qty: float, price: float, hhmmss: str) -> dict:
    ts_et = f"{DAY}T{hhmmss}"
    return {"attribution": "engine", "is_option": True, "is_crypto": False,
            "arm": arm, "symbol": sym, "side": side, "qty": qty, "price": price,
            "ts_utc": f"{DAY}T{hhmmss}Z", "ts_et": ts_et, "date_et": DAY}


def _ledger(tmp_path: Path) -> Path:
    """6 positions:
      armA C776 x4: entries 10:05:30/10:20/10:30/10:40, pnls -50/-60/-70/+80
                    (exit times 10:15/10:25/10:35/11:00) -> ord>=4 x1, contract run 3
      armA P770 x1: entry 10:06 (against V-d1: last closed bar UP), pnl -700 @10:50
      armB C776 x1: entry 09:50 (zero-structure; last closed bar idx3 DOWN ->
                    against V-d1), pnl +10 @10:10
    Exit-ordered cum: +10, -40, -100, -170, -870 (latch 10:50), -790.
    """
    C, P = "SPY260806C00776000", "SPY260806P00770000"
    rows = [
        # armA C: four sequential positions (entry 1.00, exits priced for the pnl)
        _fill("armA", C, "buy", 1, 1.00, "10:05:30"),
        _fill("armA", C, "sell", 1, 0.50, "10:15:00"),   # -50
        _fill("armA", C, "buy", 1, 1.00, "10:20:00"),
        _fill("armA", C, "sell", 1, 0.40, "10:25:00"),   # -60
        _fill("armA", C, "buy", 1, 1.00, "10:30:00"),
        _fill("armA", C, "sell", 1, 0.30, "10:35:00"),   # -70
        _fill("armA", C, "buy", 1, 1.00, "10:40:00"),
        _fill("armA", C, "sell", 1, 1.80, "11:00:00"),   # +80
        # armA P: one big loser
        _fill("armA", P, "buy", 1, 8.00, "10:06:00"),
        _fill("armA", P, "sell", 1, 1.00, "10:50:00"),   # -700
        # armB C: early winner, zero-structure
        _fill("armB", C, "buy", 1, 1.00, "09:50:00"),
        _fill("armB", C, "sell", 1, 1.10, "10:10:00"),   # +10
    ]
    p = tmp_path / "fills-ledger.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def _meter(tmp_path: Path) -> dict:
    return cm.compute_meter(DAY, ledger_path=_ledger(tmp_path),
                            bars_by_day=_bars_by_day(), fetch=False,
                            now=dt.datetime(2026, 8, 6, 16, 8, 0))


# ---------------------------------------------------------------------------
# 1. exact counts
# ---------------------------------------------------------------------------

def test_counts_ord4_vd1_zero_structure_rr(tmp_path):
    m = _meter(tmp_path)
    assert m["n_entries"] == 6
    assert m["n_ord4plus"] == 1                     # armA C 4th entry
    assert m["n_against_vd1"] == 2                  # armA P (UP vs P) + armB C (DOWN vs C)
    assert m["n_zero_structure"] == 1               # armB 09:50, before the 10:00 event
    assert m["n_rr_below_070"] == 6                 # every entry, rr ~0.4-0.5
    assert m["bars_degraded"] is False
    assert m["error"] is None
    assert m["max_consec_loss_per_arm"]["armA"] == 4   # C,C,C loss + P loss, exit-ordered
    assert m["max_consec_loss_same_contract"] == 3     # the C776 run


def test_fleet_realized_floor_latch_and_would_trip(tmp_path):
    m = _meter(tmp_path)
    fr = m["fleet_realized"]
    assert fr["day_total"] == -790.0
    assert fr["intraday_floor"] == -870.0
    assert fr["floor_time_et"] == "10:50:00"
    assert fr["would_trip_600"] is True
    assert fr["latch_time_et"] == "10:50:00"


def test_render_line_contains_every_column(tmp_path):
    line = cm.render_line(_meter(tmp_path))
    for frag in ("6 entries", "ord>=4: 1", "against V-d1: 2", "zero-structure: 1",
                 "rr<0.70: 6", "worst consec-loss run: 4 (contract 3)",
                 "BRK600 would-trip: YES @ 10:50:00", "floor -870"):
        assert frag in line, f"missing {frag!r} in {line!r}"


# ---------------------------------------------------------------------------
# 2. fail-open (prereg contract)
# ---------------------------------------------------------------------------

def test_bars_unavailable_fails_open_ledger_columns_live(tmp_path):
    m = cm.compute_meter(DAY, ledger_path=_ledger(tmp_path), bars_by_day=None,
                         fetch=False, now=dt.datetime(2026, 8, 6, 16, 8, 0))
    assert m["bars_degraded"] is True
    assert m["n_against_vd1"] is None
    assert m["n_zero_structure"] is None
    assert m["n_rr_below_070"] is None
    # ledger-derived columns still report
    assert m["n_entries"] == 6
    assert m["n_ord4plus"] == 1
    assert m["fleet_realized"]["would_trip_600"] is True
    line = cm.render_line(m)
    assert "WARN bars n/a" in line
    assert "against V-d1: n/a" in line


def test_no_entries_renders_quiet_line(tmp_path):
    p = tmp_path / "empty.jsonl"
    p.write_text("", encoding="utf-8")
    m = cm.compute_meter(DAY, ledger_path=p, bars_by_day=None, fetch=False,
                         now=dt.datetime(2026, 8, 6, 16, 8, 0))
    assert m["n_entries"] == 0
    assert cm.render_line(m) == f"CHOP METER {DAY}: no engine entries."


# ---------------------------------------------------------------------------
# 3. structure parity with the admissibility battery
# ---------------------------------------------------------------------------

def test_structure_parity_with_battery():
    import chop_admissibility_2026_08_06 as battery
    bars = _today_bars()
    a = cm.day_structure_events(bars)
    b = battery.day_structure_events(bars)
    assert [(e["kind"], e["direction"], e["break_close_et"]) for e in a] \
        == [(e["kind"], e["direction"], e["break_close_et"]) for e in b]
    assert len(a) >= 1                      # the fixture must actually produce an event
    assert a[0]["break_close_et"] == dt.datetime(2026, 8, 6, 10, 0)


# ---------------------------------------------------------------------------
# 4. firm_brief chop line: fail-open + additive
# ---------------------------------------------------------------------------

def test_firm_brief_chop_line_fail_open_and_renders(tmp_path):
    import firm_brief
    # missing artifact -> honest not-run line, never an exception
    lines = firm_brief.render_chop_lines({})
    assert len(lines) == 1 and "not run" in lines[0]
    # real artifact -> the meter line verbatim
    m = _meter(tmp_path)
    lines = firm_brief.render_chop_lines(m)
    assert len(lines) == 1
    assert "CHOP METER" in lines[0] and "ord>=4: 1" in lines[0]


def test_firm_brief_brief_still_builds_with_and_without_chop_artifact():
    """The section is ADDITIVE: build_brief must render with a missing meter
    artifact (fail-open) and include the section header either way."""
    import firm_brief
    now = dt.datetime(2026, 8, 6, 16, 10, 0)
    text = firm_brief.build_brief({}, {}, [], now)
    assert "## Chop exposure" in text
