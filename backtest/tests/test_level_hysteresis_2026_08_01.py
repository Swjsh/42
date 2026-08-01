"""WS3 guard — level-feed HYSTERESIS (2026-08-01): a level that blinks is not a level.

THE INCIDENT (2026-07-31): the 28-session shelf level 743.25 dropped out of the engine's
levels_active 14 times across 386 core ticks (present only 331/386; safe+bold ledgers
identical, so it was the FILE changing, not the read). Root cause, reproduced from
Friday's tape through the real daily_context._shelf_zones: the 5-min refresh re-derives
shelf zones from scratch with today's live-FORMING daily bar as both candidate seed and
touch-counter; two near-tied overlapping bands (742.45-744.05 @8t vs 741.56-743.16 @10t
once today's bar lands in-band) swap the greedy winner-take-all merge as spot wobbles,
renaming the written level (743.25 <-> 742.36) — and refresh_levels_intraday strips +
re-derives every family with no cross-run identity, so the wobble reached the engine.

THE FIX under guard: refresh_levels_intraday._hysteresis_carry — a previously-written
ACTIVE level missing from the fresh set is carried until it has been missing
HYSTERESIS_MISS_N consecutive refreshes (N=5, from the observed Friday absence-run
distribution {1 refresh: x5, 2: x1, 4: x1} -> max gap 4) or expires for the session.
Conservative by construction: only verbatim prior-file levels are ever re-emitted.

RED-PROOF: test_friday_flicker_sequence_red_proof drives the REAL observed Friday
fire-state sequence through OLD logic (fresh-only, pre-fix) and NEW logic (fresh+carry):
old drops 743.25 on 14 transitions, new holds it on every fire after first qualification.
Neuter the carry and the new-logic assertion goes RED.

$0, pure-Python, no network.
"""
from __future__ import annotations

import importlib.util
import json
from types import SimpleNamespace
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
MOD_PATH = REPO / "setup" / "scripts" / "refresh_levels_intraday.py"

_spec = importlib.util.spec_from_file_location("refresh_levels_intraday", MOD_PATH)
rli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rli)

_SC_PATH = REPO / "setup" / "scripts" / "self_check.py"
_sc_spec = importlib.util.spec_from_file_location("self_check", _SC_PATH)
sc = importlib.util.module_from_spec(_sc_spec)
_sc_spec.loader.exec_module(sc)

TODAY = rli.et_now().strftime("%Y-%m-%d")
NOW_ISO = f"{TODAY}T10:00:00-04:00"
SPOT = 743.74  # Friday 09:30 spot (0930 snapshot spot_at_compute)


def _shelf_level(price: float, lo: float, hi: float, *, streak: int | None = None,
                 expires: str | None = None) -> dict:
    lv = {"price": price, "type": "resistance", "role": "resistance",
          "label": f"SHELF_{lo:.2f}_{hi:.2f}_{TODAY}", "tier": "Active",
          "source": "daily_context_shelf", "verified_at": NOW_ISO,
          "expires_at": expires if expires is not None else f"{TODAY}T16:00:00-04:00",
          "zone_width": round((hi - lo) / 2, 4), "weight": 5}
    if streak is not None:
        lv["hyst_miss_streak"] = streak
    return lv


# Friday's two observed file states (snapshots 0930 vs 1200): shelf A mid 743.25
# (742.45-744.05) vs shelf B mid 742.36 (741.56-743.16); PML 742.79 stable in both.
SHELF_A = _shelf_level(743.25, 742.45, 744.05)
SHELF_B = _shelf_level(742.36, 741.56, 743.16)
PML = {"price": 742.79, "type": "support", "role": "support",
       "label": f"INTRADAY_PML_{TODAY}", "tier": "Active", "source": "premarket_low",
       "verified_at": NOW_ISO, "expires_at": f"{TODAY}T16:00:00-04:00"}


def _present(levels: list[dict], price: float) -> bool:
    return any(abs(float(lv["price"]) - price) < 0.005 for lv in levels)


def _old_logic(fresh: list[dict]) -> list[dict]:
    """Pre-fix behavior: the fresh set is the file (strip + re-derive, no carry)."""
    return rli._normalize_levels([dict(lv) for lv in fresh], spot=SPOT)


def _new_logic(prior: list[dict], fresh: list[dict]) -> list[dict]:
    held = rli._hysteresis_carry(prior, fresh, TODAY, NOW_ISO)
    return rli._normalize_levels([dict(lv) for lv in fresh] + held, spot=SPOT)


# --- THE RED-proof: Friday's real fire-state sequence ------------------------------------

# Observed per-fire shelf state, RTH fires 09:33..15:53 ET (core-decisions.jsonl transitions
# land at the tick right after each fire; both accounts identical). A = 743.25 written,
# B = 742.36 written. B-runs last {2,1,1,1,1,4,1} consecutive fires — max 4 < N=5.
_CHANGES = {"09:43": "B", "09:53": "A", "10:03": "B", "10:08": "A", "10:33": "B",
            "10:38": "A", "10:43": "B", "10:48": "A", "10:53": "B", "10:58": "A",
            "11:53": "B", "12:13": "A", "12:18": "B", "12:23": "A"}


def _friday_fire_states() -> list[str]:
    fires, state, out = [], "A", []
    for h in range(9, 16):
        for m in range(0, 60, 5):
            hm = f"{h:02d}:{m + 3:02d}"
            if hm < "09:33" or hm > "15:53":
                continue
            fires.append(hm)
    for hm in fires:
        state = _CHANGES.get(hm, state)
        out.append(state)
    return out


def test_friday_fire_state_fixture_matches_observed_distribution():
    """The fixture IS the observed evidence: 14 transitions; absence-run distribution
    {1: x5, 2: x1, 4: x1} — the basis for N=5 (max observed gap 4, bridged by 5)."""
    states = _friday_fire_states()
    trans = sum(1 for i in range(1, len(states)) if states[i] != states[i - 1])
    assert trans == 14
    runs, i = [], 0
    while i < len(states):
        j = i
        while j + 1 < len(states) and states[j + 1] == states[i]:
            j += 1
        if states[i] == "B":
            runs.append(j - i + 1)
        i = j + 1
    assert sorted(runs) == [1, 1, 1, 1, 1, 2, 4]
    assert max(runs) < rli.HYSTERESIS_MISS_N


def test_friday_flicker_sequence_red_proof():
    """Inject Friday's real flicker sequence: OLD logic drops 743.25 on every B-fire
    (14 transitions); NEW logic holds it on every fire after first qualification (0
    transitions). This is the guard's bite — remove the carry and the new-logic
    assertion fails exactly like production did on 07-31."""
    states = _friday_fire_states()
    old_743, new_743, old_742, new_742 = [], [], [], []
    prior: list[dict] = []
    for st in states:
        fresh = [dict(PML), dict(SHELF_A if st == "A" else SHELF_B)]
        old_out = _old_logic(fresh)
        old_743.append(_present(old_out, 743.25))
        old_742.append(_present(old_out, 742.36))
        written = _new_logic(prior, fresh)
        new_743.append(_present(written, 743.25))
        new_742.append(_present(written, 742.36))
        prior = written

    def _trans(seq):
        return sum(1 for i in range(1, len(seq)) if seq[i] != seq[i - 1])

    # THE headline: 743.25's absence gaps are all < N (max 4), so hysteresis bridges every
    # one — old logic reproduces the observed 14 transitions, fixed logic has ZERO.
    assert _trans(old_743) == 14               # pre-fix: the observed flicker, reproduced
    assert not all(old_743)                    # old logic genuinely drops it (bite)
    assert all(new_743)                        # fixed: present at EVERY fire
    assert _trans(new_743) == 0
    # The transient alternate mid 742.36: hysteresis bridges its SHORT gaps (<N) but its
    # long absences (a 5-fire and an 11-fire A-run, and the end-of-day tail) exceed N, so
    # it still RETIRES — stability is added, nothing becomes wrongly sticky.
    assert _trans(new_742) < _trans(old_742)   # strictly fewer flips than pre-fix (14 -> 6)
    assert _trans(old_742) == 14
    assert _trans(new_742) == 6
    assert not new_742[-1]                     # retired by end of day
    last_b = len(states) - 1 - states[::-1].index("B")
    assert all(new_742[last_b:last_b + rli.HYSTERESIS_MISS_N])     # held through N-1 misses
    assert not any(new_742[last_b + rli.HYSTERESIS_MISS_N:])       # gone from the Nth on


# --- retirement still works (no wrongly-sticky levels) -----------------------------------

def test_retires_after_n_consecutive_misses():
    """A genuinely-gone level survives exactly N-1 missing refreshes and is retired on the
    Nth — a broken/stale level still leaves the file (~25 min at the 5-min cadence)."""
    prior = [dict(SHELF_A), dict(PML)]
    fresh = [dict(PML)]                        # shelf never re-qualifies again
    presence = []
    for _run in range(rli.HYSTERESIS_MISS_N + 1):
        written = _new_logic(prior, fresh)
        presence.append(_present(written, 743.25))
        prior = written
    # held on runs 1..N-1 (4 runs at N=5), retired from run N onward
    assert presence == [True] * (rli.HYSTERESIS_MISS_N - 1) + [False, False]


def test_streak_continues_across_runs_and_resets_on_requalification():
    prior = [dict(SHELF_A), dict(PML)]
    # two misses -> streak 2
    for _ in range(2):
        prior = _new_logic(prior, [dict(PML)])
    held = [lv for lv in prior if abs(lv["price"] - 743.25) < 0.005]
    assert held and held[0]["hyst_miss_streak"] == 2
    # re-qualifies -> fresh copy written, streak field gone
    prior = _new_logic(prior, [dict(PML), dict(SHELF_A)])
    back = [lv for lv in prior if abs(lv["price"] - 743.25) < 0.005]
    assert back and "hyst_miss_streak" not in back[0]
    # a fresh miss cycle starts at 1 again -> full N-1 holds available
    prior = _new_logic(prior, [dict(PML)])
    held2 = [lv for lv in prior if abs(lv["price"] - 743.25) < 0.005]
    assert held2 and held2[0]["hyst_miss_streak"] == 1


# --- conservative by construction --------------------------------------------------------

def test_never_synthesizes_a_level_that_never_qualified():
    """Every carried entry is a verbatim prior-file level: carry output is a subset of
    prior identities; no new price can appear via hysteresis."""
    prior = [dict(SHELF_A), dict(PML), _shelf_level(730.00, 729.2, 730.8)]
    fresh = [dict(PML)]
    held = rli._hysteresis_carry(prior, fresh, TODAY, NOW_ISO)
    prior_ids = {(lv["label"], round(float(lv["price"]), 2)) for lv in prior}
    for lv in held:
        assert (lv["label"], round(float(lv["price"]), 2)) in prior_ids
    assert {round(float(lv["price"]), 2) for lv in held} == {743.25, 730.00}


def test_expired_by_date_never_carried():
    """Session boundary: yesterday's levels (expires_at < today) are never resurrected —
    hysteresis cannot leak levels across sessions."""
    stale = _shelf_level(743.25, 742.45, 744.05, expires="2026-07-31T16:00:00-04:00")
    if TODAY <= "2026-07-31":  # pragma: no cover — guard is dated after the incident
        pytest.skip("test assumes today > 2026-07-31")
    assert rli._hysteresis_carry([stale], [dict(PML)], TODAY, NOW_ISO) == []


def test_tier_expired_and_malformed_never_carried():
    dead = {**dict(SHELF_A), "tier": "expired"}
    junk = {"label": "NO_PRICE", "tier": "Active"}
    assert rli._hysteresis_carry([dead, junk], [dict(PML)], TODAY, NOW_ISO) == []


def test_moved_detector_retires_old_price_instantly_by_label():
    """A detector that legitimately MOVES its level (same label, new price beyond EPS)
    must NOT leave the stale price behind: label identity re-qualifies the prior entry, so
    only the fresh price is written. Zero added staleness for legitimate evolution."""
    old_swing = {"price": 743.10, "role": "resistance", "type": "resistance",
                 "label": f"INTRADAY_SWING_HIGH_{TODAY}", "tier": "Active",
                 "source": "intraday_swing_high", "expires_at": f"{TODAY}T16:00:00-04:00"}
    new_swing = {**old_swing, "price": 743.56}
    held = rli._hysteresis_carry([old_swing], [new_swing, dict(PML)], TODAY, NOW_ISO)
    assert held == []


def test_eps_wobble_requalifies_without_duplicate():
    """The 742.51 <-> 742.49 memory-score wobble (0.02 apart): the fresh copy represents
    the zone; the prior is re-qualified (no carry), so no near-duplicate pair forms."""
    prior_mem = {"price": 742.51, "role": "support", "type": "support",
                 "label": "MEMORY_SUP_103", "tier": "Active", "source": "level_memory",
                 "expires_at": f"{TODAY}T16:00:00-04:00"}
    fresh_mem = {"price": 742.49, "role": "resistance", "type": "resistance",
                 "label": "MEMORY_RES_99", "tier": "Active", "source": "level_memory",
                 "expires_at": f"{TODAY}T16:00:00-04:00"}
    held = rli._hysteresis_carry([prior_mem], [fresh_mem], TODAY, NOW_ISO)
    assert held == []


def test_held_never_within_eps_of_fresh_so_no_contradictory_pair():
    """Invariant behind role integrity: anything carried is >EPS from every fresh price
    (else it would have re-qualified), so hysteresis can never create the contradictory
    ceiling+floor-at-one-price shape self_check REDs on."""
    prior = [dict(SHELF_A), dict(SHELF_B), dict(PML)]
    fresh = [dict(PML), dict(SHELF_B)]
    held = rli._hysteresis_carry(prior, fresh, TODAY, NOW_ISO)
    fresh_prices = [742.79, 742.36]
    for lv in held:
        assert all(abs(lv["price"] - fp) > rli.HYSTERESIS_MATCH_EPS for fp in fresh_prices)


# --- integration through refresh() -------------------------------------------------------

_RTH = [
    ("09:35", 738.0, 736.0, 737.5, 100_000),
    ("09:45", 739.9, 738.0, 738.5, 200_000),
    ("09:55", 738.5, 736.5, 737.0, 300_000),
    ("10:05", 737.5, 735.5, 736.0, 250_000),
]
_PRE = [
    ("08:00", 736.5, 735.5, 736.0, 40_000),
    ("08:30", 737.5, 736.0, 737.0, 35_000),
    ("09:00", 738.1, 737.0, 737.8, 45_000),
]


def _make_df(rth_bars, pre_bars=()):
    today = rli.et_now().strftime("%Y-%m-%d")
    rows = []
    for hm, hi, lo, cl, vol in list(pre_bars) + list(rth_bars):
        rows.append({"date": today, "hm": hm, "high": hi, "low": lo,
                     "close": cl, "volume": vol})
    return pd.DataFrame(rows)


def _zone(lo: float, hi: float, touches: int) -> dict:
    return {"band_low": lo, "band_high": hi, "touches": touches, "span_sessions": 28,
            "broken": False, "break": None, "backside_retest": None}


def _dctx_stub(zones: list[dict]):
    return SimpleNamespace(compute_daily_context=lambda now=None: {"ok": True, "shelf_zones": zones})


@pytest.fixture
def _state(tmp_path, monkeypatch):
    kl = tmp_path / "key-levels.json"
    bias = tmp_path / "today-bias.json"
    bias.write_text(json.dumps({"key_levels": {}}), encoding="utf-8")
    monkeypatch.setattr(rli, "KEY_LEVELS", kl)
    monkeypatch.setattr(rli, "TODAY_BIAS", bias)
    monkeypatch.setattr(rli, "PARAMS", tmp_path / "params.json")       # memory wire OFF
    monkeypatch.setattr(rli, "MEMORY_MAP", tmp_path / "no-mem.json")   # no memory map
    monkeypatch.setattr(rli, "daily_context", None)
    return kl, bias


def test_refresh_end_to_end_shelf_retiling_is_bridged(_state, monkeypatch):
    """THE incident, end-to-end through refresh(): run 1 derives shelf A (743.25); run 2's
    daily_context re-tiles to shelf B (742.36). Post-fix the written file carries BOTH —
    the engine's levels_active keeps 743.25 — and the run output logs the hold (C7)."""
    kl, _ = _state
    df = _make_df(_RTH, _PRE)
    monkeypatch.setattr(rli, "daily_context", _dctx_stub([_zone(742.45, 744.05, 8)]))
    out1 = rli.refresh(df=df)
    assert out1["ok"] and any(abs(p - 743.25) < 0.005 for p in out1["engine_active_levels"])
    monkeypatch.setattr(rli, "daily_context", _dctx_stub([_zone(741.56, 743.16, 10)]))
    out2 = rli.refresh(df=df)
    act = out2["engine_active_levels"]
    assert any(abs(p - 742.36) < 0.005 for p in act)     # fresh retiled mid present
    assert any(abs(p - 743.25) < 0.005 for p in act)     # held mid STILL present (the fix)
    assert any(abs((h["price"] or 0) - 743.25) < 0.005 and h["miss_streak"] == 1
               for h in out2["hysteresis_held"])
    # producer/consumer contract: the held+fresh union still passes level integrity
    assert sc.check_level_integrity(path=kl) == []


def test_refresh_end_to_end_retiles_back_and_forth_stays_stable(_state, monkeypatch):
    """Alternate A/B for 8 runs (worse than Friday): 743.25 present in the written file
    on EVERY run; 742.36 present from its first qualification onward."""
    kl, _ = _state
    df = _make_df(_RTH, _PRE)
    for i in range(8):
        zones = [_zone(742.45, 744.05, 8)] if i % 2 == 0 else [_zone(741.56, 743.16, 10)]
        monkeypatch.setattr(rli, "daily_context", _dctx_stub(zones))
        out = rli.refresh(df=df)
        assert any(abs(p - 743.25) < 0.005 for p in out["engine_active_levels"]), f"run {i}"
        if i >= 1:
            assert any(abs(p - 742.36) < 0.005 for p in out["engine_active_levels"]), f"run {i}"
    assert sc.check_level_integrity(path=kl) == []


def test_refresh_end_to_end_gone_shelf_still_retires(_state, monkeypatch):
    """No wrongly-sticky levels: after the shelf stops qualifying for N consecutive runs it
    leaves the written file for good."""
    kl, _ = _state
    df = _make_df(_RTH, _PRE)
    monkeypatch.setattr(rli, "daily_context", _dctx_stub([_zone(742.45, 744.05, 8)]))
    rli.refresh(df=df)
    monkeypatch.setattr(rli, "daily_context", _dctx_stub([]))   # shelf universe now empty
    presence = []
    for _i in range(rli.HYSTERESIS_MISS_N + 1):
        out = rli.refresh(df=df)
        presence.append(any(abs(p - 743.25) < 0.005 for p in out["engine_active_levels"]))
    assert presence == [True] * (rli.HYSTERESIS_MISS_N - 1) + [False, False]
    data = json.loads(kl.read_text(encoding="utf-8"))
    assert not any(abs(float(lv.get("price") or 0) - 743.25) < 0.005 for lv in data["levels"])


def test_refresh_dctx_outage_freezes_streak_not_a_miss():
    """A daily_context outage keeps prior shelves verbatim (pre-existing fail-open): the
    held copy self-matches, so the miss-streak does NOT advance on outage runs — absence
    evidence only accrues when the family actually re-derived."""
    prior_held = _shelf_level(743.25, 742.45, 744.05, streak=2)
    # outage run: shelf family not stripped -> the held copy is IN the fresh assembly
    held = rli._hysteresis_carry([prior_held], [dict(prior_held), dict(PML)], TODAY, NOW_ISO)
    assert held == []   # self-matched -> no additional carry, streak stays 2 in the file
