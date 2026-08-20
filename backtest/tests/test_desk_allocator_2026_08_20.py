"""Guard: the master must never let a cleared arming bar rot unnoticed.

WHY THIS EXISTS
  conductor.md STAGE 1 drains a FLAT global queue. With four desks that
  structurally starves whichever desk nobody happened to write a queue item for
  — and that is exactly what happened: the futures desk's MES mirror reached
  armable:true (59/20 round trips, +$1,269, beating its own -$4,934 null) and
  nothing surfaced it. J found out by asking "SO IS FUTURES WORKING".

  desk_allocator.py is the master's ALLOCATE arm: it reads each desk's own
  pre-registered scoreboard and ranks who gets the next fire. These tests pin the
  ordering rules so the ranking cannot silently invert.

The scoring is deliberately NOT P&L-driven — a desk being down is not a reason to
spend the next fire on it (that is revenge-engineering). What earns a fire is a
DECISION waiting, a BREAK, or PROXIMITY to a pre-registered bar.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import desk_allocator as da                    # noqa: E402


def _a(**kw):
    base = {"real_fills": False, "armable_unarmed": False, "dead_signal": False,
            "progress": 0.0, "broken": []}
    base.update(kw)
    return base


def test_cleared_arming_bar_outranks_everything_else():
    """The scar case: work finished, value unrealised, nobody looking."""
    rotting, _ = da.score(_a(armable_unarmed=True, progress=1.0))
    broken_real, _ = da.score(_a(real_fills=True, broken=["engine RED"], progress=1.0))
    assert rotting > broken_real, (rotting, broken_real)


def test_broken_real_money_desk_outranks_broken_shadow_desk():
    """OP-33 function-first: a break where money lives is worth more attention."""
    real, _ = da.score(_a(real_fills=True, broken=["stale lane"]))
    shadow, _ = da.score(_a(broken=["stale lane"]))
    assert real > shadow, (real, shadow)


def test_dead_signal_is_deprioritised_not_zeroed():
    """Do not polish a corpse — but the machinery may still be reusable."""
    dead, why = da.score(_a(dead_signal=True))
    alive, _ = da.score(_a())
    assert dead < alive
    assert any("corpse" in w for w in why), why


def test_a_dead_signal_desk_still_loses_to_a_rotting_decision():
    dead, _ = da.score(_a(dead_signal=True, progress=1.0))
    rot, _ = da.score(_a(armable_unarmed=True))
    assert rot > dead


def test_progress_is_monotonic():
    scores = [da.score(_a(progress=p))[0] for p in (0.0, 0.25, 0.5, 0.75, 1.0)]
    assert scores == sorted(scores), scores


def test_every_score_carries_its_reasons():
    """A bare number the master cannot explain is not an allocation, it is a guess."""
    pts, why = da.score(_a(armable_unarmed=True, real_fills=True, broken=["x"], progress=0.5))
    assert why and all(isinstance(w, str) and w.strip() for w in why)
    assert len(why) >= 3, why


def test_pnl_level_alone_never_earns_a_fire():
    """Losing money is not by itself a reason to spend the next fire on a desk."""
    a1 = _a(real_fills=True, progress=1.0)
    a2 = _a(real_fills=True, progress=1.0)
    assert da.score(a1)[0] == da.score(a2)[0], "score must not read P&L level"


def test_live_allocation_runs_and_ranks_all_registered_desks():
    res = da.allocate()
    assert res["desks"], "no desks assessed"
    assert res["winner"], "no winner chosen"
    pts = [d["points"] for d in res["desks"]]
    assert pts == sorted(pts, reverse=True), "output is not ranked"
    for d in res["desks"]:
        assert d.get("why"), "desk %s ranked with no reasons" % d["id"]


def test_futures_currently_wins_because_its_bar_is_cleared():
    """Live-state canary. If this flips, the MES mirror decision was either made
    or lost — either way the master's ranking should be re-read, not ignored."""
    res = da.allocate()
    fut = [d for d in res["desks"] if d["id"] == "futures"]
    assert fut, "futures desk missing from the registry"
    if fut[0]["armable_unarmed"]:
        assert res["winner"] == "futures", (
            "futures has a cleared, unarmed bar but did not win allocation: %r" % res["winner"])
