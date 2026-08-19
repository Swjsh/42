"""Book-level exposure across ALL correlated arms -- the ceiling that did not exist.

THE GAP THIS CLOSES (found 2026-08-18, J-directed fix). Each of the 5 SPY arms is a separate
Alpaca paper account with its OWN isolated kill switch (Rule 5) and its OWN per-trade risk cap
(Rule 6). Those work correctly and independently -- and that independence was the whole
problem: all 5 arms consume ONE shared signal (measured r=0.846, 95.7% sign agreement), and
NOTHING anywhere summed what they could commit simultaneously. A single correlated tick could
put ~42% of the book into one same-direction bet with no code measuring it, let alone capping
it. Per-account discipline plus perfect correlation equals book-level concentration that no
per-account rule can see.

CALIBRATION IS MEASURED, NOT GUESSED. Replayed over every real closed round trip (5 arms,
2026-06-26..2026-08-18) by walking entry/exit events in timestamp order and tracking the
running sum of open notional:

    max concurrent book notional observed : $4,596  (18.7% of a ~$24.5K book)
    when                                  : 2026-08-14 09:47:11 ET
    composition                           : ALL FIVE arms open at once, 100% same-direction
    theoretical max under Rule 6 alone    : ~42% of book

Note the date: 2026-08-14 was also the book's second-worst day (-$1,837). Peak correlated
exposure and peak damage are the same moment, which is exactly the mechanism this module
exists to bound.

DEFAULT CAP = 25% of aggregate book equity. Chosen so it would NOT have bound on a single
historical entry (observed peak 18.7%) while removing the 42% tail. A guard that changes no
past behaviour and only truncates the tail is the correct shape for a first arming -- if it
starts binding, that is new information about the book, not a mis-set knob.

FAIL-OPEN, LOUDLY. If exposure cannot be computed, this returns allowed=True with a populated
`degraded` reason. That is deliberate and it is not laziness: this rig's OP-32 scar is a
market-hours guard that locked J out of his own system. A risk cap that halts all trading
because a state file was briefly unreadable is worse than the concentration it prevents. The
degraded path must be visible in the decision log so silence is never mistaken for safety.

NOT WIRED TO ANY ENTRY PATH BY THIS MODULE. This file only measures and judges. Wiring is a
separate, reviewable change.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
ACCOUNTS_PATH = REPO_ROOT / "automation" / "state" / "fleet" / "accounts.json"

# Fraction of AGGREGATE book equity that may be committed to open option premium at once.
# See the calibration block in the module docstring before changing this.
DEFAULT_MAX_BOOK_EXPOSURE_PCT = 0.25

# Observed historical peak, kept here so a future editor can see what "normal" was.
OBSERVED_PEAK_PCT = 0.187
OBSERVED_PEAK_USD = 4596.0
OBSERVED_PEAK_AT_ET = "2026-08-14T09:47:11"


def active_spy_arms(accounts_path: Path = ACCOUNTS_PATH) -> list[dict]:
    """Active SPY arms from the fleet registry. Paper accounts only (account_number 'PA...').

    Derived, never hardcoded -- a hardcoded roster is how this repo previously ended up with
    four account identifiers that existed nowhere in the system.
    """
    try:
        reg = json.loads(accounts_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for arm in reg.get("arms", []):
        acct = arm.get("account_number")
        if not isinstance(acct, str) or not acct.startswith("PA"):
            continue  # skips the futures sim arms, which are not SPY and not paper-Alpaca
        if str(arm.get("status") or "").lower() != "active":
            continue
        out.append({"arm_id": arm.get("id") or arm.get("arm_id"), "account_number": acct})
    return out


def position_notional(qty: Any, premium: Any, multiplier: int = 100) -> float:
    """Dollar premium at risk for an option position. Long options: max loss IS the premium."""
    try:
        return abs(float(qty)) * abs(float(premium)) * multiplier
    except (TypeError, ValueError):
        return 0.0


def evaluate(open_positions_by_arm: dict[str, list[dict]],
             equity_by_arm: dict[str, float],
             prospective_notional: float = 0.0,
             max_pct: float = DEFAULT_MAX_BOOK_EXPOSURE_PCT) -> dict:
    """Judge whether adding `prospective_notional` would breach the book-level ceiling.

    open_positions_by_arm: {arm_id: [{"qty": n, "premium": p}, ...]}
    equity_by_arm:         {arm_id: equity_usd}
    prospective_notional:  premium the candidate entry would commit (0 to just measure)

    Returns a dict that is safe to log verbatim into a decision row. `allowed` is ALWAYS a
    bool; `degraded` is None on a clean evaluation and a reason string otherwise. Callers
    must treat degraded=True as "could not measure", not as "measured zero".
    """
    book_equity = 0.0
    for v in equity_by_arm.values():
        try:
            book_equity += float(v)
        except (TypeError, ValueError):
            continue

    current = 0.0
    per_arm: dict[str, float] = {}
    for arm_id, positions in (open_positions_by_arm or {}).items():
        arm_total = 0.0
        for pos in positions or []:
            arm_total += position_notional(pos.get("qty"), pos.get("premium"))
        per_arm[arm_id] = round(arm_total, 2)
        current += arm_total

    try:
        prospective = max(0.0, float(prospective_notional))
    except (TypeError, ValueError):
        prospective = 0.0

    projected = current + prospective

    # FAIL OPEN, LOUDLY. No equity reading means no denominator -- we cannot judge, so we do
    # not block. See the module docstring for why this is deliberate (OP-32 lockout scar).
    if book_equity <= 0:
        return {
            "allowed": True,
            "degraded": "book_equity_unavailable -- cannot compute a ceiling, failing OPEN",
            "book_equity": 0.0,
            "current_notional": round(current, 2),
            "prospective_notional": round(prospective, 2),
            "projected_notional": round(projected, 2),
            "projected_pct": None,
            "max_pct": max_pct,
            "per_arm_notional": per_arm,
        }

    projected_pct = projected / book_equity
    allowed = projected_pct <= max_pct
    return {
        "allowed": allowed,
        "degraded": None,
        "book_equity": round(book_equity, 2),
        "current_notional": round(current, 2),
        "prospective_notional": round(prospective, 2),
        "projected_notional": round(projected, 2),
        "projected_pct": round(projected_pct, 4),
        "max_pct": max_pct,
        "per_arm_notional": per_arm,
        "reason": (
            None if allowed else
            f"BOOK_EXPOSURE_CAP: {projected_pct:.1%} of ${book_equity:,.0f} book would exceed "
            f"the {max_pct:.0%} ceiling across {len(per_arm)} correlated arms "
            f"(r=0.846 -- these arms are one bet in five sizes, so per-account caps do not "
            f"bound this)"
        ),
    }


# --------------------------------------------------------------------------------------- #
# Live readers -- local state only. NO broker calls.
# --------------------------------------------------------------------------------------- #
# WHY LOCAL STATE AND NOT THE BROKER: this runs on the 1-minute hot path. Polling 5 accounts
# per tick would be 5 extra REST round-trips every minute of every session -- a cost and a
# latency the cap does not need. Each arm ALREADY fetches its own equity on its own tick, so
# it simply records it; and open positions are already persisted per arm by the exit manager.
EQUITY_SNAPSHOT_NAME = "book-equity-snapshot.json"
# An equity reading older than this is not trusted as a denominator.
EQUITY_STALE_MINUTES = 90.0


def record_arm_equity(arm_id: str, equity: float, state_dir: Path, now_et_iso: str) -> None:
    """Record ONE arm's equity into the shared snapshot. Fail-soft: never raises.

    Read-modify-write of a small dict. Concurrent arms can interleave; a lost update costs
    at most one stale-but-recent reading, which the staleness check already tolerates. Worth
    far less than the complexity of locking on a hot path.
    """
    try:
        path = Path(state_dir) / EQUITY_SNAPSHOT_NAME
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except (OSError, ValueError):
            data = {}
        data[str(arm_id)] = {"equity": float(equity), "ts_et": str(now_et_iso)}
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001 -- telemetry must never break a tick
        pass


def _minutes_old(ts_et: str, now_et_iso: str) -> float | None:
    import datetime as _dt
    try:
        a = _dt.datetime.fromisoformat(str(ts_et).replace("Z", ""))
        b = _dt.datetime.fromisoformat(str(now_et_iso).replace("Z", ""))
    except (TypeError, ValueError):
        return None
    if a.tzinfo and not b.tzinfo:
        a = a.replace(tzinfo=None)
    if b.tzinfo and not a.tzinfo:
        b = b.replace(tzinfo=None)
    return abs((b - a).total_seconds()) / 60.0


def read_book_state(state_dir: Path, now_et_iso: str,
                    accounts_path: Path = ACCOUNTS_PATH) -> tuple[dict, dict, str | None]:
    """(open_positions_by_arm, equity_by_arm, degraded_reason).

    Positions come from each arm's exit-state.json -- a dict keyed by option symbol whose
    records carry `entry_premium` and `total_qty` (see fleet/exit_manager.ExitState). An
    absent or empty file means that arm is FLAT, which is a real reading, not a gap.

    Equity comes from the shared snapshot. A MISSING or STALE arm makes the whole reading
    DEGRADED rather than silently shrinking the denominator -- a smaller denominator would
    make the cap stricter, i.e. fail CLOSED, which is precisely the behaviour the OP-32
    lockout scar forbids.
    """
    state_dir = Path(state_dir)
    arms = active_spy_arms(accounts_path)
    if not arms:
        return {}, {}, "registry_unreadable -- no active arms resolved"

    positions: dict[str, list[dict]] = {}
    for arm in arms:
        aid = str(arm["arm_id"])
        rec_path = state_dir / "fleet" / aid / "exit-state.json"
        rows: list[dict] = []
        try:
            blob = json.loads(rec_path.read_text(encoding="utf-8"))
            if isinstance(blob, dict):
                for rec in blob.values():
                    if isinstance(rec, dict):
                        rows.append({"qty": rec.get("total_qty"),
                                     "premium": rec.get("entry_premium")})
        except (OSError, ValueError):
            rows = []          # absent file == flat, per the exit manager's own contract
        positions[aid] = rows

    equity: dict[str, float] = {}
    stale: list[str] = []
    try:
        snap = json.loads((state_dir / EQUITY_SNAPSHOT_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        snap = {}
    for arm in arms:
        aid = str(arm["arm_id"])
        row = snap.get(aid) if isinstance(snap, dict) else None
        if not isinstance(row, dict):
            stale.append(f"{aid}:missing")
            continue
        age = _minutes_old(row.get("ts_et", ""), now_et_iso)
        if age is None or age > EQUITY_STALE_MINUTES:
            stale.append(f"{aid}:stale({age if age is None else round(age)}m)")
            continue
        try:
            equity[aid] = float(row["equity"])
        except (TypeError, ValueError, KeyError):
            stale.append(f"{aid}:unreadable")

    degraded = None
    if stale:
        degraded = ("equity unavailable for " + ", ".join(stale) +
                    " -- denominator incomplete, failing OPEN")
    return positions, equity, degraded


def evaluate_live(state_dir: Path, now_et_iso: str, prospective_notional: float = 0.0,
                  max_pct: float = DEFAULT_MAX_BOOK_EXPOSURE_PCT,
                  accounts_path: Path = ACCOUNTS_PATH) -> dict:
    """Convenience wrapper: read local state, then judge. Always returns a loggable dict."""
    positions, equity, degraded = read_book_state(state_dir, now_et_iso, accounts_path)
    if degraded:
        return {"allowed": True, "degraded": degraded, "book_equity": None,
                "current_notional": None, "prospective_notional": round(prospective_notional, 2),
                "projected_pct": None, "max_pct": max_pct, "per_arm_notional": {}}
    return evaluate(positions, equity, prospective_notional, max_pct)
