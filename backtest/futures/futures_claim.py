"""futures_claim.py -- cross-lane entry claim file lock for the futures paper sandbox.

WHY THIS EXISTS (queue.md FUTURES-MIRROR-CROSS-LANE-CLAIM, folded into FUTURES-LANE-WIRING-2
(b), filed 2026-09-03). `futures_trader_core.run_tick()` (backend=tastytrade) and
`futures_mirror_shadow.py`'s armed leg (`_broker_execute_entry`, MIRROR_ARMED=1) both trade
the SAME instrument on the SAME Tastytrade sandbox account (5WW73759) on independent
schedules. Both already read `broker.is_flat(symbol)` before placing -- but that is a
TOCTOU, explicitly disclosed in futures_mirror_shadow.py's own "CROSS-LANE SAFETY" docstring
section ("a same-5-minute-window TOCTOU race between the two independently-scheduled lanes
is possible in principle... a shared OS-level claim file is a disclosed follow-up"). This
module IS that follow-up.

PORTS setup/scripts/heartbeat_core.py's `_acquire_claim`/`_claim_active` design (see that
module's "ORDER-LEVEL IDEMPOTENCY GUARD" block, 2026-08-02/08-14/08-19) rather than
reimplementing it: same O_CREAT|O_EXCL fast path for the uncontested common case, same
msvcrt byte-range-lock takeover for the contended/stale case (never a remove/rename dance --
that shape cost that module 3 fix rounds and a documented TOCTOU scar; a claim file must
never be observably ABSENT from the directory once created, or an unrelated contender's own
fast path can slip through the gap), same fail-open-on-unexpected-OSError posture, same
SKIP_* naming convention. Windows-only (`msvcrt`), matching the rest of this codebase.

WHAT DIFFERS FROM THE SPY VERSION, ON PURPOSE:
  * Keyed by SYMBOL (e.g. "MES"), not by (arm, symbol) -- the whole point here is that only
    ONE lane may hold an in-flight claim for a given contract; `owner` records WHICH lane
    holds it (a string, e.g. "futures_trader_core" / "futures_mirror_shadow"), for
    diagnosability only -- it is not part of the arbitration key.
  * Adds an explicit `release_claim()` the SPY version does not have (that one only ever
    expires via TTL, which is fine for its ~180s broker-propagation-lag use case). This
    lane's callers hold a claim across a real bracket-order round trip and want to free the
    slot the moment they observe `broker.is_flat()` again, not wait out the TTL -- so
    release is a real operation, not just an expiry. Release is OWNER-SCOPED and never
    deletes the file (same "never let it go missing" discipline as acquire): a release from
    a non-owner, of an already-released claim, or of a claim it never held is a silent
    no-op, never a crash and never someone else's claim getting stolen.

CONTRACT:
  acquire_claim(symbol, owner, now_et, ttl_sec=DEFAULT_TTL_SEC) -> bool
      True iff THIS call now holds the claim (fresh first claim, or a stale/released one
      taken over). False means a DIFFERENT fresh, unreleased claim exists -- caller MUST
      NOT place an order for `symbol` right now.
  release_claim(symbol, owner, now_et) -> bool
      True iff a claim was released (or none existed -- idempotent). Only clears the claim
      when the CURRENT holder's owner matches (or the file is already stale/corrupt/absent);
      a live claim held by a DIFFERENT owner is left untouched (defensive -- this should
      never be attempted by a correctly-written caller, since only the winner of
      acquire_claim should ever call release_claim, but a caller bug here must not let one
      lane silently steal or clear another's active claim).
  claim_active(symbol, now_et, ttl_sec=DEFAULT_TTL_SEC) -> bool
      Read-only peek: True iff an unexpired, non-released claim exists. Diagnostics/tests.

Fail-open throughout, same posture as the SPY original: a claim-file problem must never
itself block a legitimate paper entry. `broker.is_flat()` remains the fail-CLOSED authority
underneath this -- the claim file only serializes the WINDOW between two lanes' independent
is_flat() reads and their place_bracket() calls; it does not replace that check.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest",):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

# Referenced fresh via the module attribute on every call (never captured into a local at
# import time) so a test's monkeypatch.setattr(fc, "CLAIM_DIR", tmp_path) sandboxes this
# exactly like heartbeat_core.py's own STATE attribute is sandboxed -- zero extra wiring.
CLAIM_DIR = REPO / "automation" / "state" / "futures" / "claims"

DEFAULT_TTL_SEC = 180.0  # same value/rationale as heartbeat_core.ENTRY_CLAIM_TTL_SEC: bridges
                         # broker propagation lag across a few ticks, never blocks a
                         # legitimate later entry (which needs a fresh trigger anyway).


def _claim_path(symbol: str, claim_dir: "Path | None" = None) -> Path:
    d = claim_dir if claim_dir is not None else CLAIM_DIR
    d.mkdir(parents=True, exist_ok=True)  # may be a bare tmp_path in tests
    return d / f"{symbol}.json"


def _read_record(fd) -> "dict | None":
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        data = os.read(fd, 1 << 20)
        if not data:
            return None
        return json.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _record_is_live(rec: "dict | None", now_et: datetime, ttl_sec: float) -> bool:
    """A record counts as a LIVE (unexpired, unreleased) claim iff it has a non-null owner
    and its age is within [0, ttl_sec). Missing/corrupt/owner-less/stale -> not live."""
    if not rec or not rec.get("owner"):
        return False
    try:
        claimed_at = datetime.fromisoformat(str(rec["claimed_at_et"]))
    except (KeyError, ValueError, TypeError):
        return True  # unparseable timestamp on an owned record -- treat as live/unknown-age,
                     # never silently steal a claim we cannot prove is stale (fail toward
                     # refusing a new entry, not toward a double entry).
    if claimed_at.tzinfo is None:
        claimed_at = claimed_at.replace(tzinfo=now_et.tzinfo)
    age = (now_et - claimed_at).total_seconds()
    return 0 <= age < ttl_sec


def claim_active(symbol: str, now_et: datetime, ttl_sec: float = DEFAULT_TTL_SEC,
                 *, claim_dir: "Path | None" = None) -> bool:
    """Read-only peek. Fail-open (False) on any missing/corrupt file -- same contract as
    heartbeat_core._claim_active."""
    path = _claim_path(symbol, claim_dir)
    if not path.exists():
        return False
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return _record_is_live(rec, now_et, ttl_sec)


def acquire_claim(symbol: str, owner: str, now_et: datetime,
                  ttl_sec: float = DEFAULT_TTL_SEC, *,
                  claim_dir: "Path | None" = None) -> bool:
    """ATOMICALLY reserve the entry claim for `symbol` BEFORE the broker POST. Ports
    heartbeat_core._acquire_claim's O_CREAT|O_EXCL-then-lock-takeover shape verbatim (see
    module docstring); the only behavioural addition is that a record with `owner=None`
    (an explicit release) counts as takeable exactly like a stale one, via
    `_record_is_live`. `claim_dir` overrides the module-level CLAIM_DIR for this call only
    (callers that already resolve their OWN state root -- e.g. futures_trader_core deriving
    it from STATE_DIR -- pass it explicitly so test isolation of that root covers this too,
    with zero extra per-test wiring; omit it to use CLAIM_DIR, which itself stays
    monkeypatch-friendly for direct callers/tests of this module)."""
    path = _claim_path(symbol, claim_dir)
    payload = json.dumps({"symbol": symbol, "owner": owner,
                          "claimed_at_et": now_et.isoformat()}).encode("utf-8")

    def _try_excl() -> "bool | None":
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return None
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)
        return True

    try:
        if _try_excl():
            return True
        import msvcrt  # noqa: PLC0415 -- Windows-only primitive, imported where it is used
        try:
            fd = os.open(str(path), os.O_RDWR)
        except FileNotFoundError:
            return bool(_try_excl())
        try:
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError:
                return False  # someone else holds the lock right now -- refuse, never guess
            try:
                rec = _read_record(fd)
                if _record_is_live(rec, now_et, ttl_sec):
                    return False  # fresh, someone else's live claim -- refuse, untouched
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(fd, payload)
                os.ftruncate(fd, len(payload))
                return True
            finally:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        finally:
            os.close(fd)
    except OSError:
        return True  # documented fail-open; broker-side is_flat() stays fail-CLOSED


def release_claim(symbol: str, owner: str, now_et: datetime, *,
                  claim_dir: "Path | None" = None) -> bool:
    """Best-effort release, called by the CURRENT holder once it observes `broker.is_flat()`
    again. Owner-scoped: only overwrites the record (never deletes the file -- see module
    docstring) when there is no record, the record is already released/stale, OR the
    record's owner matches `owner`. A live claim held by a DIFFERENT owner is left
    untouched. Idempotent and fail-open: any lock contention or OSError is treated as
    'nothing to do here', never raised -- a release must never itself block a tick.
    `claim_dir` overrides CLAIM_DIR for this call only -- see acquire_claim's docstring."""
    path = _claim_path(symbol, claim_dir)
    if not path.exists():
        return True  # nothing to release
    tombstone = json.dumps({"symbol": symbol, "owner": None,
                            "released_by": owner,
                            "released_at_et": now_et.isoformat()}).encode("utf-8")
    try:
        import msvcrt  # noqa: PLC0415
        try:
            fd = os.open(str(path), os.O_RDWR)
        except FileNotFoundError:
            return True
        try:
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError:
                return False  # someone mid-takeover right now -- do not fight it, next call retries
            try:
                rec = _read_record(fd)
                current_owner = rec.get("owner") if rec else None
                if current_owner is not None and current_owner != owner:
                    return False  # a DIFFERENT lane's live claim -- never touch it
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(fd, tombstone)
                os.ftruncate(fd, len(tombstone))
                return True
            finally:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        finally:
            os.close(fd)
    except OSError:
        return True  # fail-open: an unreleasable claim self-heals via TTL expiry regardless
