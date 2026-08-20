"""Guard: entry-claim acquisition is ATOMIC -- concurrent processes get exactly one winner.

THE INCIDENT (2026-08-14 09:46). The box slept 04:27-09:46 ET. On wake, the scheduled
heartbeat launch (09:46:02) and the self-healer's re-fire (09:46:06) produced two live engine
processes. The claim guard was check-then-write: _claim_active() early in _execute, a blind
best-effort _write_claim just before the POST. Both processes passed the check before either
wrote -- orders 21ms apart, two distinct client_order_ids, safe-2 filled 6 contracts instead of
3 and bold-2 10 instead of 5 (~-$371 of the day's -$1,569), with the surplus legs invisible to
the exit manager.

THE FIX. _acquire_claim uses os.open(O_CREAT|O_EXCL): the KERNEL arbitrates, exactly one
process wins, the loser refuses with SKIP_DUPLICATE_CLAIM. Placement now REQUIRES holding the
claim. The race window is not narrowed -- it does not exist.

Scope deliberately widened: a fresh claim for a DIFFERENT symbol also refuses (one in-flight
entry per arm), because two different-symbol entries 21ms apart on one arm is the same accident
in a disguise.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import sys
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HC = REPO / "setup" / "scripts" / "heartbeat_core.py"

NOW = datetime.datetime(2026, 8, 14, 9, 46, 12)
SYM = "SPY260814C00778000"


@pytest.fixture()
def hc(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("_hc_claim_probe", HC)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_hc_claim_probe"] = m
    try:
        spec.loader.exec_module(m)
    except SystemExit:
        pass
    monkeypatch.setattr(m, "STATE", tmp_path)   # _claim_path derefs STATE fresh per call
    return m


@pytest.fixture
def hc_factory(hc, tmp_path):
    """Same module, a FRESH claim-state directory per call -- so repeated-contention trials
    each start from a clean stale claim instead of inheriting the previous trial's file."""
    counter = {"n": 0}

    def _make():
        counter["n"] += 1
        d = tmp_path / f"trial{counter['n']}"
        d.mkdir(parents=True, exist_ok=True)
        hc.STATE = d
        return hc

    return _make


def _storm(hc, n, symbol, now, arm="safe-2"):
    """n simultaneous acquirers released by a barrier -- the 09:46 wake-storm, amplified."""
    results: list[bool] = []
    barrier = threading.Barrier(n)

    def worker():
        barrier.wait()
        results.append(hc._acquire_claim(arm, symbol, now))

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


# ------------------------------------------------------------------ the race itself


def test_exactly_one_winner_under_simultaneous_acquisition(hc):
    """THE INCIDENT, amplified 4x. Two processes produced two fills; eight must produce one."""
    wins = sum(_storm(hc, 8, SYM, NOW))
    assert wins == 1, (
        f"{wins} of 8 simultaneous acquirers won the entry claim. Anything but 1 means the "
        "check-then-write race is back and a wake-storm can double-place again.")


def test_a_fresh_claim_blocks_every_later_acquirer(hc):
    assert hc._acquire_claim("safe-2", SYM, NOW) is True
    assert all(hc._acquire_claim("safe-2", SYM, NOW) is False for _ in range(3))


def test_a_fresh_claim_blocks_a_DIFFERENT_symbol_too(hc):
    """One in-flight entry per arm. The old per-symbol scope would let two different-symbol
    entries through 21ms apart -- the same accident in a disguise."""
    assert hc._acquire_claim("safe-2", SYM, NOW) is True
    assert hc._acquire_claim("safe-2", "SPY260814P00776000", NOW) is False


def test_arms_do_not_block_each_other(hc):
    """The claim is per-arm. safe-2 holding a claim must not block bold-2's entry."""
    assert hc._acquire_claim("safe-2", SYM, NOW) is True
    assert hc._acquire_claim("bold-2", SYM, NOW) is True


def test_stale_claim_is_reclaimable_by_exactly_one(hc):
    assert hc._acquire_claim("safe-2", SYM, NOW) is True
    later = NOW + datetime.timedelta(seconds=hc.ENTRY_CLAIM_TTL_SEC + 5)
    wins = sum(_storm(hc, 8, "SPY260814P00776000", later))
    assert wins == 1, f"{wins} of 8 won a STALE claim -- remove+retry must still be arbitrated"


def test_stale_takeover_is_arbitrated_under_REPEATED_contention(hc_factory):
    """THE TEST THAT ACTUALLY CAUGHT THE BUG -- and the reason it is written this way.

    The single-shot storm above PASSED in isolation and FAILED inside a 1,000-test run. That
    is not flakiness; that is a race whose window only opens under load, which is exactly the
    condition it matters in (the 2026-08-14 double entry happened during a wake-storm). The
    original implementation removed the stale claim UNCONDITIONALLY before recreating it, so a
    slow contender could delete the FRESH claim a fast contender had just won and then create
    its own -- two winners.

    Measured on the pre-fix shape: 6 multi-winner outcomes in 300 trials x 16 threads (2%).
    Post-fix (rename-arbitrated takeover): 0 in 300. This test runs enough trials to make that
    2% effectively certain to surface (1 - 0.98^40 > 55%, and in practice it fires far sooner),
    so the guard fails on the DEFECT rather than on the scheduler's mood.
    """
    counts = []
    for _ in range(40):
        hc = hc_factory()                      # fresh STATE sandbox per trial
        assert hc._acquire_claim("safe-2", SYM, NOW) is True
        later = NOW + datetime.timedelta(seconds=hc.ENTRY_CLAIM_TTL_SEC + 5)
        counts.append(sum(_storm(hc, 16, SYM, later)))
    assert max(counts) <= 1, (
        f"{sum(1 for c in counts if c > 1)}/40 trials produced MORE THAN ONE stale-claim "
        f"winner (max {max(counts)}) -- that is a double entry on the exact path the "
        "2026-08-14 incident took")
    assert min(counts) == 1, (
        f"{sum(1 for c in counts if c == 0)}/40 trials produced NO winner -- a stale claim "
        "must always be reclaimable by someone, or the arm is wedged until the file ages out")


def test_toctou_steals_a_legitimately_fresh_claim_from_under_a_new_owner(hc_factory, monkeypatch):
    """2026-08-19 regression -- the ACTUAL mechanism behind incident_fix_status.py's 1/40
    multi-winner finding (probabilistic storm test above: 0/300 at ship time, 1/40 measured
    2026-08-19 -- a real residual race, not flakiness).

    THE BUG: staleness is judged by READING `path` BEFORE the takeover rename, but the
    takeover rename itself does not re-check what it is actually renaming -- it blindly takes
    over whatever currently sits at `path`. That is a classic TOCTOU: a slow contender (T1)
    can read the ORIGINAL stale record, get preempted, and while it sleeps a fast contender
    (T2) legitimately wins a full stale-takeover and installs a brand-new FRESH claim. When T1
    wakes it acts on its STALE verdict from moments ago and renames-away T2's fresh claim
    anyway -- deleting the legitimate winner's reservation and installing its own. Both T1 and
    T2 return True: two winners on the exact incident path (double entry).

    This test forces that exact interleaving via a monkeypatched json.loads that pauses T1
    immediately after it reads (and judges stale) the ORIGINAL record, releasing it only once
    T2 has completed an entire independent, legitimate stale-takeover end to end. Must fail
    (both True) on the pre-fix "check staleness before takeover" shape and pass once staleness
    is judged on the content the renamer actually now privately owns (after the takeover, not
    before it)."""
    hc = hc_factory()
    assert hc._acquire_claim("safe-2", SYM, NOW) is True
    later = NOW + datetime.timedelta(seconds=hc.ENTRY_CLAIM_TTL_SEC + 5)

    real_loads = hc.json.loads
    gap_entered = threading.Event()
    proceed = threading.Event()
    call_count = {"n": 0}
    lock = threading.Lock()

    def _hooked_loads(s, *a, **kw):
        rec = real_loads(s, *a, **kw)
        with lock:
            call_count["n"] += 1
            is_first = call_count["n"] == 1
        if is_first:
            # T1 just finished reading + judging the ORIGINAL stale record. Pause here, BEFORE
            # T1's takeover rename, so an independent contender (T2) can win a full legitimate
            # stale-takeover cycle -- installing a brand-new FRESH claim -- in the meantime.
            gap_entered.set()
            proceed.wait(timeout=5)
        return rec

    monkeypatch.setattr(hc.json, "loads", _hooked_loads)

    results: dict[str, bool] = {}

    def _late_renamer():
        results["late_t1"] = hc._acquire_claim("safe-2", SYM, later)

    t = threading.Thread(target=_late_renamer)
    t.start()
    assert gap_entered.wait(timeout=5), "T1 never reached the staleness read -- test setup broken"
    results["legit_winner_t2"] = hc._acquire_claim("safe-2", SYM, later)
    proceed.set()
    t.join(timeout=5)

    winners = sum(1 for v in results.values() if v)
    assert winners == 1, (
        f"{winners} of 2 contenders (a legitimate stale-takeover winner T2, plus a slow "
        f"contender T1 acting on a stale staleness-verdict) both claimed True: {results} -- "
        "T1 renamed T2's brand-new fresh claim away out from under it. This is the exact "
        "TOCTOU double-entry race the 2026-08-19 fix closes by judging staleness on content "
        "taken into custody, never on a read performed before the takeover.")


def test_corrupt_claim_counts_as_stale_one_winner(hc, tmp_path):
    d = tmp_path / "fleet" / "safe-2"
    d.mkdir(parents=True, exist_ok=True)
    (d / "entry-claim.json").write_text("NOT JSON", encoding="utf-8")
    wins = sum(hc._acquire_claim("safe-2", SYM, NOW) for _ in range(2))
    assert wins == 1


def test_winner_leaves_a_parseable_claim(hc, tmp_path):
    assert hc._acquire_claim("safe-2", SYM, NOW) is True
    rec = json.loads((tmp_path / "fleet" / "safe-2" / "entry-claim.json").read_text(encoding="utf-8"))
    assert rec["symbol"] == SYM
    assert rec["claimed_at_et"].startswith("2026-08-14T09:46:12")


# ------------------------------------------------------------------ the wiring


def test_placement_requires_the_claim_not_a_blind_write():
    """The POST site must be gated on _acquire_claim; a blind write there IS the bug. Also
    pins that the loser exits with the fleet lane's SKIP_DUPLICATE_CLAIM vocabulary."""
    src = HC.read_text(encoding="utf-8")
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    assert "def _write_claim" not in code, (
        "_write_claim is back -- the blind best-effort write is the exact shape that "
        "double-entered on 2026-08-14")
    assert "if not _acquire_claim(" in code, "placement no longer requires acquiring the claim"
    i = code.index("if not _acquire_claim(")
    block = code[i:i + 400]
    assert "SKIP_DUPLICATE_CLAIM" in block, "the refusal path lost its SKIP_DUPLICATE_CLAIM status"
    assert "_place_simple_entry" in code[i:], (
        "_place_simple_entry no longer follows the claim gate -- verify the ordering: "
        "acquire FIRST, place second")
    j = code.index("_place_simple_entry(creds", i)
    assert j > i, "the broker POST happens before the claim acquire -- the guard is decorative"


def test_excl_flag_is_actually_used():
    """The atomicity comes from O_EXCL specifically. os.open without it is just a slower
    version of the old write."""
    src = HC.read_text(encoding="utf-8")
    start = src.index("def _acquire_claim")
    end = src.index("\ndef ", start)  # next TOP-LEVEL def -- the nested _try_excl must stay inside
    fn = src[start:end]
    assert "os.O_EXCL" in fn, "_acquire_claim lost O_EXCL -- the kernel no longer arbitrates"
    assert "FileExistsError" in fn, "the loser path no longer catches FileExistsError"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
