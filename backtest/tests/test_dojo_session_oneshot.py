"""Guards for setup/scripts/dojo_session.py -- the WS10 one-command dojo harness.

Pins (RED-proofed 2026-08-01 -- each guard was demonstrated to FAIL under a deliberate
mutation of the invariant it pins, then the mutation reverted):
  1. population window: hard [2025-01-02, 2026-07-31], weekdays only, broken session
     2026-06-15 excluded, half-day 2025-07-03 kept (the 2024 stratum stays locked).
  2. seeded picker: deterministic under a fixed log state; NEVER returns an
     already-reviewed day; fake-mode rows never burn a day; out-of-window explicit
     --day rejected loudly.
  3. call parser: direction+price required (loud reject), stop extraction, long/short
     vocabulary both sides.
  4. dojo fence: every write path refuses to land outside automation/state/dojo/.
  5. comparison-card totals: BS-synthetic positions are EXCLUDED from the real-OPRA
     headline (disclosed separately) -- the Free-Kitchen-Plan-B rule, enforced.

No network, no TV, no broker. Only the REAL spy/vix cache files are read (population
enumeration); everything written goes to tmp_path via a re-rooted fence.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", "backtest"):
    _ap = str(_ROOT / _p)
    if _ap not in sys.path:
        sys.path.insert(0, _ap)

import dojo_session as ds  # noqa: E402
from dojo import session as spine  # noqa: E402


# --------------------------------------------------------------------------- fixtures
@pytest.fixture()
def tmp_dojo(tmp_path, monkeypatch):
    """Re-root the ENTIRE dojo state surface (harness + spine + fence) into tmp_path.
    The fence stays ACTIVE -- just re-rooted -- so fence behaviour is still exercised."""
    dojo_dir = tmp_path / "dojo"
    sessions = dojo_dir / "sessions"
    sessions.mkdir(parents=True)
    monkeypatch.setattr(spine, "DOJO_DIR", dojo_dir)
    monkeypatch.setattr(spine, "SESSIONS_DIR", sessions)
    monkeypatch.setattr(ds, "DOJO_DIR", dojo_dir)
    monkeypatch.setattr(ds, "SESSIONS_DIR", sessions)
    monkeypatch.setattr(ds, "SESSIONS_LOG", dojo_dir / "sessions.jsonl")
    monkeypatch.setattr(ds, "CURRENT_PTR", dojo_dir / "current-session.json")
    return dojo_dir


@pytest.fixture(scope="module")
def population():
    pop = ds.population_days()
    assert pop, "population enumeration returned nothing -- caches missing?"
    return pop


# --------------------------------------------------------------------------- 1. population
def test_population_hard_window_and_weekdays(population):
    assert population[0] >= date(2025, 1, 2)
    assert population[-1] <= date(2026, 7, 31)
    assert all(d.weekday() < 5 for d in population)
    # 2024 stratum locked until the backfill declaration doc exists
    assert not any(d.year == 2024 for d in population)


def test_population_excludes_broken_keeps_half_days(population):
    assert date(2026, 6, 15) not in population, "12-bar broken session must be excluded"
    assert date(2025, 7, 3) in population, "half day (46 RTH bars) must stay in population"
    assert len(population) >= 380, f"population collapsed to {len(population)}"


# --------------------------------------------------------------------------- 2. picker
def _log_row(day: str, event: str = "pick", mode: str = "real") -> dict:
    return {"event": event, "replay_day": day, "mode": mode, "session_id": f"x-{day}"}


def test_pick_is_deterministic_under_fixed_log(tmp_dojo, population):
    a = ds.pick_day()
    b = ds.pick_day()
    assert a["replay_day"] == b["replay_day"]
    assert a["seed"] == f"{ds.BASE_SEED}:0" == b["seed"]
    assert a["replay_day"] in {d.isoformat() for d in population}


def test_pick_never_repeats_reviewed_day(tmp_dojo, monkeypatch):
    """DETERMINISTIC no-repeat pin: with a 2-day population and 1 day reviewed, the
    eligible set must be exactly the other day -- no rng luck involved (the first
    RED-proof round showed a chance-based version of this guard passes under the
    broken-exclusion mutation ~99% of the time; eligible_n pins the mechanism)."""
    two = [date(2026, 6, 24), date(2026, 6, 25)]
    monkeypatch.setattr(ds, "population_days", lambda: two)
    ds._fenced_append_jsonl(ds.SESSIONS_LOG, _log_row("2026-06-24", event="reviewed"))
    row = ds.pick_day()
    assert row["eligible_n"] == 1, "reviewed day still in the eligible set"
    assert row["replay_day"] == "2026-06-25"
    assert row["seed"] == f"{ds.BASE_SEED}:0"


def test_fake_rows_never_burn_a_day(tmp_dojo):
    first = ds.pick_day()["replay_day"]
    ds._fenced_append_jsonl(ds.SESSIONS_LOG, _log_row(first, mode="fake"))
    # same pick_index bump, but the day itself stays eligible
    assert first not in {d.isoformat() for d in ds.reviewed_days()}


def test_legacy_state_files_exclude_their_day(tmp_dojo):
    st = {"session_id": "legacy-1", "replay_day": "2026-06-24", "phase": "CLOSED",
          "created_et": "x"}
    (ds.SESSIONS_DIR / "legacy-1.state.json").write_text(json.dumps(st), encoding="utf-8")
    assert date(2026, 6, 24) in ds.reviewed_days()
    assert ds.pick_day()["replay_day"] != "2026-06-24"


def test_explicit_day_outside_window_rejected(tmp_dojo):
    with pytest.raises(ValueError, match="outside the verified population window"):
        ds.pick_day("2024-06-03")
    with pytest.raises(ValueError):
        ds.pick_day("2026-06-15")  # broken session is not pickable either


# --------------------------------------------------------------------------- 3. parser
def test_parse_call_long_with_stop():
    p = ds.parse_call_text("long 737.7 here, stop under the wick at 737.2")
    assert p == {"direction": "C", "price": 737.7, "stop": 737.2,
                 "rationale": "long 737.7 here, stop under the wick at 737.2"}


def test_parse_call_puts_no_stop():
    p = ds.parse_call_text("puts 746.9, momentum gone")
    assert (p["direction"], p["price"], p["stop"]) == ("P", 746.9, None)


def test_parse_call_loud_rejects():
    with pytest.raises(ValueError, match="no direction word"):
        ds.parse_call_text("something happened at 746")
    with pytest.raises(ValueError, match="no price"):
        ds.parse_call_text("long here, looks good")
    with pytest.raises(ValueError, match="empty"):
        ds.parse_call_text("   ")


# --------------------------------------------------------------------------- 4. fence
def test_fence_refuses_write_outside_dojo(tmp_dojo, tmp_path):
    outside = tmp_path / "not-dojo" / "escape.txt"
    with pytest.raises(PermissionError, match="DOJO fence"):
        ds._fenced_write_text(outside, "nope")
    with pytest.raises(PermissionError, match="DOJO fence"):
        ds._fenced_append_jsonl(outside, {"x": 1})
    assert not outside.exists()


def test_fence_allows_write_inside_dojo(tmp_dojo):
    p = ds.SESSIONS_DIR / "ok.txt"
    ds._fenced_write_text(p, "fine")
    assert p.read_text(encoding="utf-8") == "fine"


# --------------------------------------------------------------------------- 5. card totals
def _pos(pid: str, pnl: float, synthetic: bool, status: str = "CLOSED") -> dict:
    return {"position_id": pid, "arm": "safe", "symbol": "S", "side": "C", "strike": 1,
            "qty": 3, "status": status, "entry_time_et": "2026-07-17T10:45:00",
            "entry_premium": 1.0, "exit_time_et": "2026-07-17T11:00:00",
            "exit_reason": "tp1", "realized_pnl": pnl, "unrealized_pnl": 0.0,
            "price_source": "bs_synthetic" if synthetic else "opra_5m",
            "is_synthetic": synthetic, "note": None}


def test_lane_totals_exclude_synthetic_from_headline():
    positions = {"a": _pos("a", 100.0, synthetic=False),
                 "b": _pos("b", 900.0, synthetic=True),
                 "c": _pos("c", -40.0, synthetic=False),
                 "d": _pos("d", 0.0, synthetic=False, status="NO_FILL")}
    t = ds._lane_totals(positions)
    assert t["real_opra_pnl"] == pytest.approx(60.0), \
        "synthetic P&L leaked into the real-OPRA headline"
    assert t["n_real"] == 2
    assert t["synthetic_pnl_EXCLUDED"] == pytest.approx(900.0)
    assert t["n_synthetic_EXCLUDED"] == 1
    assert t["n_no_fill_or_error"] == 1


def test_card_headline_uses_synthetic_excluded_totals():
    j = {"a": _pos("a", 50.0, synthetic=False), "b": _pos("b", 500.0, synthetic=True)}
    card = ds._build_card("sid", "2026-07-17", "fake", {}, [], [], j, {}, 0, 78, 0, {})
    assert card["totals"]["j_real_opra_pnl"] == pytest.approx(50.0)
    assert card["j_calls"]["totals"]["n_synthetic_EXCLUDED"] == 1
    assert any("EXCLUDED" in c or "synthetic" in c.lower() for c in card["caveats"])
