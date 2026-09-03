"""Guards for backtest/futures/futures_claim.py -- the cross-lane entry claim file lock
(queue.md FUTURES-MIRROR-CROSS-LANE-CLAIM, folded into FUTURES-LANE-WIRING-2 (b)).

Covers: fast-path acquire, contention (two lanes -> exactly one wins), stale-claim
recovery, owner-scoped release (idempotent, never steals a live claim from another owner),
release-then-reacquire by a different owner, and claim_active's read-only contract.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest",):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

import futures.futures_claim as fc  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_state(monkeypatch, tmp_path):
    monkeypatch.setattr(fc, "CLAIM_DIR", tmp_path / "claims")


def _now(offset_sec: float = 0.0) -> dt.datetime:
    return dt.datetime(2026, 9, 3, 10, 0, 0, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=offset_sec)


class TestAcquireFastPath:
    def test_first_claim_succeeds(self):
        assert fc.acquire_claim("MES", "lane_a", _now()) is True
        assert fc.claim_active("MES", _now(1)) is True

    def test_claim_file_records_owner_and_symbol(self, tmp_path):
        fc.acquire_claim("MES", "lane_a", _now())
        rec = json.loads((tmp_path / "claims" / "MES.json").read_text(encoding="utf-8"))
        assert rec["symbol"] == "MES"
        assert rec["owner"] == "lane_a"

    def test_symbols_are_independent(self):
        assert fc.acquire_claim("MES", "lane_a", _now()) is True
        assert fc.acquire_claim("MNQ", "lane_b", _now()) is True
        assert fc.claim_active("MES", _now(1)) is True
        assert fc.claim_active("MNQ", _now(1)) is True


class TestContention:
    def test_two_lanes_contend_one_wins(self):
        """The load-bearing property this module exists for: two independent lanes racing
        an entry for the SAME symbol must never both win."""
        first = fc.acquire_claim("MES", "futures_trader_core", _now())
        second = fc.acquire_claim("MES", "futures_mirror_shadow", _now(0.05))
        assert first is True
        assert second is False  # the loser MUST refuse -- this is the whole point

    def test_loser_does_not_overwrite_winners_claim(self, tmp_path):
        fc.acquire_claim("MES", "futures_trader_core", _now())
        fc.acquire_claim("MES", "futures_mirror_shadow", _now(0.05))
        rec = json.loads((tmp_path / "claims" / "MES.json").read_text(encoding="utf-8"))
        assert rec["owner"] == "futures_trader_core"

    def test_fresh_claim_refuses_even_the_same_owner(self):
        """Mirrors heartbeat_core's documented behavior: a fresh claim refuses regardless of
        who is asking -- one in-flight entry attempt at a time."""
        fc.acquire_claim("MES", "futures_trader_core", _now())
        assert fc.acquire_claim("MES", "futures_trader_core", _now(1)) is False


class TestStaleRecovery:
    def test_stale_claim_is_taken_over(self):
        fc.acquire_claim("MES", "futures_trader_core", _now(), ttl_sec=60)
        # advance past TTL
        later = _now(120)
        assert fc.acquire_claim("MES", "futures_mirror_shadow", later, ttl_sec=60) is True

    def test_taken_over_claim_records_new_owner(self, tmp_path):
        fc.acquire_claim("MES", "futures_trader_core", _now(), ttl_sec=60)
        fc.acquire_claim("MES", "futures_mirror_shadow", _now(120), ttl_sec=60)
        rec = json.loads((tmp_path / "claims" / "MES.json").read_text(encoding="utf-8"))
        assert rec["owner"] == "futures_mirror_shadow"

    def test_corrupt_claim_file_counts_as_stale(self, tmp_path):
        claims = tmp_path / "claims"
        claims.mkdir(parents=True, exist_ok=True)
        (claims / "MES.json").write_text("{not json", encoding="utf-8")
        assert fc.acquire_claim("MES", "futures_trader_core", _now()) is True

    def test_claim_active_false_once_stale(self):
        fc.acquire_claim("MES", "futures_trader_core", _now(), ttl_sec=60)
        assert fc.claim_active("MES", _now(120), ttl_sec=60) is False


class TestReleaseOnFlat:
    def test_release_by_owner_clears_the_claim(self):
        fc.acquire_claim("MES", "futures_trader_core", _now())
        assert fc.claim_active("MES", _now(1)) is True
        assert fc.release_claim("MES", "futures_trader_core", _now(2)) is True
        assert fc.claim_active("MES", _now(3)) is False

    def test_release_then_reacquire_by_a_different_owner_succeeds(self):
        """The exact scenario this ships to unblock: lane A goes flat and releases, lane B
        (a fresh signal firing moments later) must be able to win the claim immediately --
        not wait out the TTL."""
        fc.acquire_claim("MES", "futures_trader_core", _now())
        fc.release_claim("MES", "futures_trader_core", _now(1))
        assert fc.acquire_claim("MES", "futures_mirror_shadow", _now(2)) is True

    def test_release_never_touches_a_different_owners_live_claim(self, tmp_path):
        fc.acquire_claim("MES", "futures_trader_core", _now())
        result = fc.release_claim("MES", "futures_mirror_shadow", _now(1))
        assert result is False
        rec = json.loads((tmp_path / "claims" / "MES.json").read_text(encoding="utf-8"))
        assert rec["owner"] == "futures_trader_core"
        assert fc.claim_active("MES", _now(2)) is True

    def test_release_of_nonexistent_claim_is_a_noop_success(self):
        assert fc.release_claim("MES", "futures_trader_core", _now()) is True

    def test_release_is_idempotent(self):
        fc.acquire_claim("MES", "futures_trader_core", _now())
        assert fc.release_claim("MES", "futures_trader_core", _now(1)) is True
        assert fc.release_claim("MES", "futures_trader_core", _now(2)) is True


class TestClaimActive:
    def test_no_file_is_inactive(self):
        assert fc.claim_active("MES", _now()) is False

    def test_fresh_claim_is_active(self):
        fc.acquire_claim("MES", "futures_trader_core", _now())
        assert fc.claim_active("MES", _now(5)) is True
