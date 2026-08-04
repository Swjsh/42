"""test_risky_divergence_weekly_2026_08_04.py -- guards for the weekly risky-vs-safes
marginal-cohort instrument (setup/scripts/full_send_vs_gated.py, RISKY3-SPECULATIVE lane).

WHAT THIS PINS:
  1. L244 SHAPE-CORRECT core counting: extra_exec is a LIST of per-setup dicts -- a
     PLACED element counts as a core entry; the dict-shaped mistake (wall #5 of
     EOD-2026-08-03, which made three counters blind to safe-2's +$67.85 entry) must
     never come back. A WATCH_NOT_ARMED row must NOT count.
  2. MARGINAL DEFINITION: a risk-arm placed entry is marginal iff NEITHER safe-3 placed
     NOR core safe-2 entered the same minute -- and its real closed P&L joins via
     fills_fifo (the single FIFO implementation).
  3. WEEKDAY WINDOW: last_n_session_days skips weekend dates a stray weekend fire wrote
     into a ledger (caught live 2026-08-04: risky-3 carries Saturday 2026-08-01 rows
     that silently evicted the oldest real session from the 5-session window).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "setup" / "scripts"), str(_REPO / "automation" / "state" / "fleet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import full_send_vs_gated as fsg  # noqa: E402


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------------
# 1. L244: extra_exec LIST parse
# ---------------------------------------------------------------------------------
def test_core_counting_is_extra_exec_list_aware(tmp_path):
    core = tmp_path / "core-decisions.jsonl"
    _write_jsonl(core, [
        # counts: top-level ENTER
        {"ts_et": "2026-08-03T10:00:03-04:00", "account": "safe", "action": "ENTER_BULL"},
        # counts: extra_exec LIST with PLACED (the wall-#5 shape)
        {"ts_et": "2026-08-03T13:21:03-04:00", "account": "safe", "action": "SKIP_X",
         "extra_exec": [{"setup": "bollinger_squeeze", "action": "PLACED"}]},
        # does NOT count: WATCH_NOT_ARMED element
        {"ts_et": "2026-08-03T13:30:03-04:00", "account": "safe", "action": "HOLD",
         "extra_exec": [{"setup": "gap_and_go", "action": "WATCH_NOT_ARMED"}]},
        # does NOT count: bold account row
        {"ts_et": "2026-08-03T13:40:03-04:00", "account": "bold", "action": "ENTER_BEAR"},
        # does NOT count (defensive): dict-shaped extra_exec is not iterated as PLACED
        {"ts_et": "2026-08-03T13:50:03-04:00", "account": "safe", "action": "HOLD",
         "extra_exec": {"setup": "x", "action": "PLACED"}},
    ])
    out = fsg.load_core_safe_entry_minutes({"2026-08-03"}, path=core)
    assert out == {
        "2026-08-03T10:00": "core_enter",
        "2026-08-03T13:21": "extra_exec:bollinger_squeeze",
    }, out


# ---------------------------------------------------------------------------------
# 2. Marginal definition + real-P&L join
# ---------------------------------------------------------------------------------
def test_marginal_cohort_and_pnl_join(tmp_path, monkeypatch):
    fleet = tmp_path / "fleet"
    days = {"2026-08-03"}
    # risky-3: 3 placed -- one shared with safe-3, one covered by core extra, one MARGINAL
    _write_jsonl(fleet / "risky-3" / "decisions.jsonl", [
        {"ts_et": "2026-08-03T09:42:03-04:00", "arm_id": "risky-3", "action": "ENTER_BULL",
         "quality": "ELITE", "qty": 5, "premium": 0.38, "reason": "ribbon_ride C (ELITE)",
         "placement": {"placed": True, "symbol": "SPY260803C00754000"}},
        {"ts_et": "2026-08-03T13:21:10-04:00", "arm_id": "risky-3", "action": "ENTER_BEAR",
         "quality": "BASE", "qty": 5, "premium": 0.50, "reason": "ribbon_ride P (BASE)",
         "placement": {"placed": True, "symbol": "SPY260803P00752000"}},
        {"ts_et": "2026-08-03T11:00:03-04:00", "arm_id": "risky-3", "action": "ENTER_BEAR",
         "quality": "BASE", "qty": 8, "premium": 0.44,
         "reason": "vwap_reclaim_failed_break P (BASE)",
         "placement": {"placed": True, "symbol": "SPY260803P00753000"}},
    ])
    _write_jsonl(fleet / "risky-1" / "decisions.jsonl", [])
    _write_jsonl(fleet / "safe-3" / "decisions.jsonl", [
        {"ts_et": "2026-08-03T09:42:03-04:00", "arm_id": "safe-3", "action": "ENTER_BULL",
         "quality": "ELITE", "qty": 3, "premium": 0.38, "reason": "ribbon_ride C (ELITE)",
         "placement": {"placed": True, "symbol": "SPY260803C00754000"}},
    ])
    core = tmp_path / "core-decisions.jsonl"
    _write_jsonl(core, [
        {"ts_et": "2026-08-03T13:21:03-04:00", "account": "safe", "action": "HOLD",
         "extra_exec": [{"setup": "bollinger_squeeze", "action": "PLACED"}]},
    ])
    fills = tmp_path / "fills-ledger.jsonl"
    _write_jsonl(fills, [
        {"arm": "risky-3", "attribution": "engine", "symbol": "SPY260803P00753000",
         "side": "buy", "qty": 8, "price": 0.44, "ts_et": "2026-08-03T11:00:05-04:00",
         "date_et": "2026-08-03"},
        {"arm": "risky-3", "attribution": "engine", "symbol": "SPY260803P00753000",
         "side": "sell", "qty": 8, "price": 0.55, "ts_et": "2026-08-03T11:30:05-04:00",
         "date_et": "2026-08-03"},
    ])
    monkeypatch.setattr(fsg, "FLEET", fleet)
    monkeypatch.setattr(fsg, "CORE_DECISIONS", core)
    monkeypatch.setattr(fsg, "_arms", lambda: [
        {"id": "risky-3", "status": "active", "execution": "fleet_rest", "gate_override": {}},
        {"id": "risky-1", "status": "active", "execution": "fleet_rest", "gate_override": {}},
        {"id": "safe-3", "status": "active", "execution": "fleet_rest", "gate_override": {}},
    ])
    import fills_fifo
    monkeypatch.setattr(fills_fifo, "FILLS_LEDGER_PATH", fills)

    mc = fsg.marginal_cohort(days)
    r3 = mc["arms"]["risky-3"]
    assert r3["placed"] == 3
    assert r3["marginal_n"] == 1, r3
    marg = [e for e in r3["entries"] if e["marginal"]]
    assert marg[0]["symbol"] == "SPY260803P00753000"
    # (0.55-0.44)*8*100 = +$88.00 -- joined from the FIFO round trip
    assert marg[0]["real_pnl_closed"] == 88.0
    assert r3["marginal_closed_pnl"] == 88.0
    # the shared-minute entry and the core-covered entry are NOT marginal
    by_sym = {e["symbol"]: e for e in r3["entries"]}
    assert by_sym["SPY260803C00754000"]["marginal"] is False   # safe-3 same minute
    assert by_sym["SPY260803P00752000"]["marginal"] is False   # core extra same minute
    assert by_sym["SPY260803P00752000"]["core_safe_same_minute"] == "extra_exec:bollinger_squeeze"


# ---------------------------------------------------------------------------------
# 3. Weekend rows must not eat a session slot
# ---------------------------------------------------------------------------------
def test_last_n_session_days_skips_weekend_rows(tmp_path, monkeypatch):
    fleet = tmp_path / "fleet"
    rows = []
    for d in ("2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31",
              "2026-08-01",  # SATURDAY -- the live foot-gun this guard pins
              "2026-08-03"):
        rows.append({"ts_et": f"{d}T10:00:03-04:00", "arm_id": "risky-3", "action": "HOLD",
                     "reason": "x", "placement": {}})
    _write_jsonl(fleet / "risky-3" / "decisions.jsonl", rows)
    monkeypatch.setattr(fsg, "FLEET", fleet)
    days = fsg.last_n_session_days(5)
    assert days == {"2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31", "2026-08-03"}, \
        "Saturday 2026-08-01 must not evict the oldest real session"
