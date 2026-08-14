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
