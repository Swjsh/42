"""multi/lib/position_state.py -- durable per-position state for the multi-symbol lane's
MULTI-DAY exit management (arm multi-1).

WHY THIS EXISTS. `multi/lib/exits.py`'s decision walk (theta budget, days-to-live, TP1,
trailing profit-lock, catastrophe cap) needs to remember, ACROSS ticks and across process
restarts, a handful of facts the broker itself does not carry on a position: the ENTRY
premium/underlying price (the broker only ever reports the current mark), whether TP1 has
already fired (so a second tick after the partial does not re-sell it), the high-water mark
premium (for the trailing floor), and the entry session date (so days-to-live can be counted
in TRADING SESSIONS, not calendar days). This module is that memory. It is deliberately dumb:
no market reads, no broker calls, no decision logic -- `exits.py` owns all of that and treats
this module purely as a load/save boundary.

THE DANGEROUS DIRECTION THIS GUARDS AGAINST. A state file that fails to load and is silently
replaced by `{}` is INDISTINGUISHABLE from "the lane has no open positions" -- exactly the
condition under which a caller would (correctly, if the file really were empty) skip exit
management entirely. If the file is actually corrupt, or was deleted, or the path resolved
wrong, silently returning `{}` means every open position on this account stops being managed
-- no theta check, no days-to-live flatten, no catastrophe cap -- while the ledger and the
caller both believe everything is fine. `load_state()` therefore RAISES on a missing or
corrupt file; the only way to get an empty state is to have explicitly written one (see
`save_state({})` / `ensure_initialized()` below), which is a deliberate, auditable act rather
than a silent fallback.

PERSISTENCE. `automation/state/multi/exit-state.json` (gitignored -- confirmed at
.gitignore:320). Writes are ATOMIC: the full payload is written to a temp file in the SAME
directory (so the eventual `os.replace` is same-volume and therefore atomic on both POSIX and
Windows), fsync'd, then swapped into place with `os.replace`. A crash/exception mid-write
leaves the temp file orphaned (or absent) and the real file byte-for-byte untouched -- there is
no window in which `exit-state.json` is a partially-written, unparseable JSON blob.

Pure I/O + one dataclass. No network, no broker, no other multi/lib import (mirrors
multi/lib/positions.py's "pure and side-effect-free" discipline so `exits.py` can compose
this with broker.py without either module reaching into the other's business).
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = REPO_ROOT / "automation" / "state" / "multi" / "exit-state.json"

# Bumped only on a breaking schema change. `load_state` refuses a file whose _schema does not
# match rather than guessing at a migration -- an unrecognized shape is corrupt, not "old".
SCHEMA_VERSION = 1


class PositionStateError(RuntimeError):
    """Raised on a missing, corrupt, or malformed-schema state file. NEVER caught internally
    and converted to an empty dict -- see the module docstring's 'dangerous direction'
    section. A caller that wants to bootstrap a fresh lane must call
    `ensure_initialized()` / `save_state({})` explicitly first; catching this error and
    substituting `{}` inline defeats the entire point of this exception existing."""


@dataclass(frozen=True)
class PositionRecord:
    """One managed position. Immutable -- every tick produces a NEW record via
    `dataclasses.replace` (coding-style: never mutate); the caller persists the returned
    record, never edits one in place.

    Fields required by the task brief: entry premium/qty/side/symbol/contract/expiry, entry
    session date, high-water mark, whether TP1 has fired, days held. Three additional fields
    are needed to actually EXECUTE the params.json exit math and are documented individually
    below -- they are not a scope expansion, they are what `tp1_premium_pct`,
    `theta_budget.thesis_progress_definition`, and the post-TP1 trailing profit-lock in
    params.json require to be evaluable at all:
      * `entry_underlying_price` -- the theta-budget thesis-progress test
        ("underlying has moved >= N*ATR14 in the trade's direction from entry") is defined
        relative to the underlying's price AT ENTRY, which the broker does not report back.
      * `runner_stop_premium` / `profit_lock_armed` -- the post-TP1 trailing floor (arms at
        `profit_lock_arm_pct`, trails `trail_pct` off the high-water mark) must ratchet
        across ticks the same way `automation/state/fleet/exit_manager.py`'s
        `runner_stop_premium` does; without persisting it here it would reset to nothing
        every tick and the trail would never hold a floor.
    """

    symbol: str                    # underlying root ticker, e.g. "NVDA" (never the OCC symbol)
    contract: str                  # OCC-shaped option symbol, e.g. "NVDA260626C00135000"
    side: str                      # "C" | "P"
    entry_premium: float
    entry_underlying_price: float
    qty: int                       # ORIGINAL entry qty -- never decremented; open_qty (broker
                                    # truth) is what shrinks after a partial close
    entry_session_date: str        # ISO date (ET calendar date the position was opened)
    expiry: str                    # ISO date of the contract's expiration
    hwm_premium: float             # high-water mark of best premium observed since entry
    tp1_filled: bool = False
    days_held: int = 0             # informational cache of trading-SESSION count, recomputed
                                    # fresh every evaluate_exit() call -- never trusted as the
                                    # decision input itself (see exits.py); persisted purely
                                    # for observability/journaling.
    runner_stop_premium: Optional[float] = None
    profit_lock_armed: bool = False
    strategy: str = ""

    def __post_init__(self) -> None:
        if self.side not in ("C", "P"):
            raise ValueError(f"PositionRecord.side must be 'C' or 'P', got {self.side!r}")
        if self.qty < 1:
            raise ValueError(f"PositionRecord.qty must be >= 1, got {self.qty!r}")
        if self.entry_premium <= 0:
            raise ValueError(f"PositionRecord.entry_premium must be > 0, got {self.entry_premium!r}")

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "contract": self.contract,
            "side": self.side,
            "entry_premium": self.entry_premium,
            "entry_underlying_price": self.entry_underlying_price,
            "qty": self.qty,
            "entry_session_date": self.entry_session_date,
            "expiry": self.expiry,
            "hwm_premium": self.hwm_premium,
            "tp1_filled": self.tp1_filled,
            "days_held": self.days_held,
            "runner_stop_premium": self.runner_stop_premium,
            "profit_lock_armed": self.profit_lock_armed,
            "strategy": self.strategy,
        }

    @staticmethod
    def from_dict(d: dict) -> "PositionRecord":
        try:
            return PositionRecord(
                symbol=str(d["symbol"]),
                contract=str(d["contract"]),
                side=str(d["side"]),
                entry_premium=float(d["entry_premium"]),
                entry_underlying_price=float(d["entry_underlying_price"]),
                qty=int(d["qty"]),
                entry_session_date=str(d["entry_session_date"]),
                expiry=str(d["expiry"]),
                hwm_premium=float(d["hwm_premium"]),
                tp1_filled=bool(d.get("tp1_filled", False)),
                days_held=int(d.get("days_held", 0)),
                runner_stop_premium=(
                    None if d.get("runner_stop_premium") is None
                    else float(d["runner_stop_premium"])
                ),
                profit_lock_armed=bool(d.get("profit_lock_armed", False)),
                strategy=str(d.get("strategy", "")),
            )
        except (KeyError, TypeError, ValueError) as e:
            raise PositionStateError(f"corrupt PositionRecord payload {d!r}: {e}") from e

    def touch(self, *, hwm_premium: Optional[float] = None, days_held: Optional[int] = None,
              **overrides) -> "PositionRecord":
        """Convenience wrapper over `dataclasses.replace` that never mutates `self`."""
        fields = dict(overrides)
        if hwm_premium is not None:
            fields["hwm_premium"] = hwm_premium
        if days_held is not None:
            fields["days_held"] = days_held
        return replace(self, **fields)


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write `payload` to `path` atomically: full write to a same-directory temp file,
    fsync, then `os.replace`. Any exception during the write (including one injected mid-way
    by a caller for testing) leaves `path` byte-for-byte as it was before this call -- the
    temp file is unlinked on the way out and `path` is never touched until the swap.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.stem}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)  # atomic swap: same directory => same volume
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def save_state(state: dict[str, PositionRecord], *, path: Path = STATE_PATH) -> None:
    """Persist the full position-state map (contract -> PositionRecord), atomically.

    `state == {}` is a legal, explicit call (bootstrapping a fresh lane / confirming the
    book is genuinely flat) -- it is the ONLY way an empty state should ever come to exist
    on disk. Never call this reflexively to "recover" from a `load_state` failure; that
    would silently paper over exactly the corruption this module exists to surface.
    """
    payload = {
        "_schema": SCHEMA_VERSION,
        "positions": {contract: rec.to_dict() for contract, rec in state.items()},
    }
    _atomic_write_json(path, payload)


def load_state(*, path: Path = STATE_PATH) -> dict[str, PositionRecord]:
    """Load the full position-state map. RAISES `PositionStateError` on a missing file,
    unreadable/non-JSON file, wrong/missing schema version, or any record that fails to
    parse -- never returns `{}` for any of those. A genuinely empty, well-formed file
    (`{"_schema": 1, "positions": {}}`, as written by `save_state({})`) returns `{}` cleanly;
    that is the only path by which an empty result is produced.
    """
    if not path.exists():
        raise PositionStateError(
            f"multi exit-state file missing at {path} -- refusing to treat this as \"no open "
            f"positions\". If the lane is genuinely starting fresh, call save_state({{}}) "
            f"once, explicitly, to create it."
        )
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise PositionStateError(f"cannot read {path}: {e}") from e
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise PositionStateError(f"{path} is not valid JSON: {e}") from e
    if not isinstance(raw, dict):
        raise PositionStateError(f"{path} top level must be a JSON object, got {type(raw).__name__}")
    if raw.get("_schema") != SCHEMA_VERSION:
        raise PositionStateError(
            f"{path} has _schema={raw.get('_schema')!r}, expected {SCHEMA_VERSION!r} -- "
            f"refusing to guess at a migration for an unrecognized shape."
        )
    positions = raw.get("positions")
    if not isinstance(positions, dict):
        raise PositionStateError(f"{path} is missing a 'positions' object")
    out: dict[str, PositionRecord] = {}
    for contract, rec in positions.items():
        if not isinstance(rec, dict):
            raise PositionStateError(f"{path}: record for {contract!r} is not an object")
        out[contract] = PositionRecord.from_dict(rec)
    return out


def ensure_initialized(*, path: Path = STATE_PATH) -> None:
    """Create an empty, well-formed state file IFF none exists yet. Idempotent -- a second
    call on an already-initialized (or populated) file is a no-op. This is the ONLY sanctioned
    way to bootstrap a fresh lane; it never runs implicitly from inside `load_state`."""
    if not path.exists():
        save_state({}, path=path)
