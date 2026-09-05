"""engine_gaps.py -- shared RTH tick-gap detector (per-account), factored out of
engine_health.py so intervention_counter.py can use the IDENTICAL gap logic.

WHY THIS EXISTS (2026-09-05, post-mortem on the 2026-09-04 09:51-10:46 ET blackout):
the box lost power at 09:51 ET while safe-2 held 3x SPY260904P00772000 and bold-2 held
5x SPY260904P00770000 (both entered 09:46 ET). core-decisions.jsonl has NO rows for
either core account 09:51:03 -> 10:46:15 ET -- a 55-minute hole in a 1-minute engine,
DURING RTH, while both accounts were exposed. J closed both positions from the Alpaca
web dashboard at 10:46:06/07 ET (broker `source: null`, vs the engine's own orders which
always carry `source: "access_key"`). intervention_counter.py's existing classifier saw
only "an exit whose entry attribution is engine and exit attribution is not engine" and
filed it as `engine_entered_manual_exit` -- indistinguishable from J second-guessing a
live, healthy engine (the exact "cuts winners early" risk pattern the counter exists to
police) -- when it was in fact a RESCUE during a blackout the engine could not see or
report. Meanwhile engine_health.py's existing liveness checks (check_engine_core) only
ever ask "is the newest row fresh RIGHT NOW" -- by the time any post-blackout fire ran,
the engine had resumed on its own and the newest row was fresh, so the 55-minute
interior hole was invisible (the exact C7 silent-failure class this project keeps
re-discovering).

ONE gap definition, TWO consumers:
  - engine_health.py's `rth_tick_gaps` check: any gap found today/yesterday is a
    finding (RED if it overlapped an open position, YELLOW otherwise).
  - intervention_counter.py's `rescue_exit` category: a manual exit whose own
    timestamp falls within RESCUE_WINDOW_MIN minutes after a gap's END is a rescue,
    not an intervention against the Sept ZERO target.

Both read core-decisions.jsonl (bounded tail read, never the full ~100MB ledger) and
fills-ledger.jsonl (broker-fills ground truth, same source intervention_counter.py
already trusts). Pure functions where possible; fail-open everywhere (empty list /
False on any parse or read error) -- a broken detector must never crash either caller
or manufacture a false RED/rescue.

Run standalone for a quick look:
    python setup/scripts/engine_gaps.py --account safe --day 2026-09-04
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
CORE_DECISIONS = STATE / "core-decisions.jsonl"
FILLS_PATH = STATE / "fills-ledger.jsonl"

# A healthy tick is ~1/min; >3min between consecutive rows for one account is
# unambiguously a hole, not scheduler/IO jitter (mirrors the spirit of
# CORE_STALE_MIN=8 in engine_health.py, but this is an INTERIOR gap check, not a
# right-now-staleness one, so it can afford a tighter bound).
GAP_THRESHOLD_MIN = 3.0

# A manual exit landing within this many minutes AFTER a gap's END is presumed to be
# the human closing a position the engine could not see/manage during the blackout --
# not a second-guess of a healthy, ticking engine.
RESCUE_WINDOW_MIN = 5.0

RTH_START = "09:30:00"
RTH_END = "15:55:00"

# Core arms trade under these account labels in core-decisions.jsonl; fills-ledger.jsonl
# tags the same positions by their fleet arm name (CLAUDE.md Account context table).
ACCOUNT_TO_ARM = {"safe": "safe-2", "bold": "bold-2"}

# Bounded tail read: never load the full multi-GB-bound ledger. Current rows run
# ~5KB each (context_bundle/levels_active payloads); 25MB comfortably covers 2 accounts
# x 2 trading days x ~800 ticks/day with headroom, without ever risking an unbounded read
# (measured live 2026-09-05: ~4.9KB/row average over the last 405 rows in a 2MB tail).
DEFAULT_TAIL_BYTES = 25_000_000


def _parse_naive(ts: object) -> Optional[datetime]:
    """Parse a naive ET wall-clock timestamp string ('YYYY-MM-DDTHH:MM:SS...'). None on
    any non-conforming input -- callers treat that as 'skip this row', never a crash."""
    if not isinstance(ts, str) or len(ts) < 19:
        return None
    try:
        return datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


def load_core_rows_for_day(account: str, day: str, path: Path = CORE_DECISIONS,
                            tail_bytes: int = DEFAULT_TAIL_BYTES) -> list:
    """Tail-read core-decisions.jsonl; return the SORTED list of naive-ET datetimes for
    every row where account == `account` and ts_et starts with `day` (YYYY-MM-DD).
    Fail-open: [] on any read/parse error -- never raises."""
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            if size > tail_bytes:
                f.seek(size - tail_bytes)
            data = f.read()
    except OSError:
        return []
    out: list = []
    for raw in data.decode("utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(row, dict) or row.get("account") != account:
            continue
        ts = row.get("ts_et")
        if not isinstance(ts, str) or not ts.startswith(day):
            continue
        dt = _parse_naive(ts)
        if dt is not None:
            out.append(dt)
    out.sort()
    return out


def find_rth_gaps(timestamps: list, day: str, gap_min: float = GAP_THRESHOLD_MIN) -> list:
    """PURE: sorted naive-ET datetimes for one account/day -> list of
    {start, end, duration_min} for every consecutive pair strictly inside the RTH
    window [09:30, 15:55) on `day` whose gap exceeds `gap_min` minutes. Never raises
    on malformed input (an empty/singleton list just yields no gaps)."""
    try:
        rth_open = datetime.strptime(f"{day} {RTH_START}", "%Y-%m-%d %H:%M:%S")
        rth_close = datetime.strptime(f"{day} {RTH_END}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return []
    in_rth = sorted(t for t in timestamps if rth_open <= t < rth_close)
    gaps = []
    for prev, cur in zip(in_rth, in_rth[1:]):
        dur = (cur - prev).total_seconds() / 60.0
        if dur > gap_min:
            gaps.append({"start": prev, "end": cur, "duration_min": round(dur, 2)})
    return gaps


def load_fills(path: Path = FILLS_PATH) -> list:
    """Fail-open fills-ledger reader -- mirrors intervention_counter.load_fills exactly
    (duplicated, not imported, to keep this module dependency-free of that script)."""
    fills: list = []
    if not path.exists():
        return fills
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    fills.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return fills


def position_open_during(account: str, gap_start: datetime, fills: list) -> bool:
    """True if this account's arm carried a NET OPEN long qty > 0 at the moment the gap
    started -- i.e. a buy fill with no fully-offsetting sell fill before gap_start. A
    cheap running-net-quantity heuristic (not a full FIFO match): sufficient to answer
    "was ANYTHING open", which is all this check needs. Excludes crypto fills (never a
    live SPY-0DTE position per project scope). Fail-open: False on any malformed row or
    unknown account -- never manufactures a false RED."""
    arm = ACCOUNT_TO_ARM.get(account)
    if arm is None:
        return False
    net_qty = 0.0
    for f in fills:
        if not isinstance(f, dict) or f.get("arm") != arm or f.get("is_crypto"):
            continue
        ts = _parse_naive(f.get("ts_et"))
        if ts is None or ts > gap_start:
            continue
        side = f.get("side")
        try:
            qty = float(f.get("qty") or 0)
        except (TypeError, ValueError):
            continue
        if side == "buy":
            net_qty += qty
        elif side == "sell":
            net_qty -= qty
    return net_qty > 1e-9


def find_gaps_with_position_flag(account: str, day: str, gap_min: float = GAP_THRESHOLD_MIN,
                                  core_path: Path = CORE_DECISIONS,
                                  fills_path: Path = FILLS_PATH,
                                  tail_bytes: int = DEFAULT_TAIL_BYTES) -> list:
    """Full pipeline for engine_health's rth_tick_gaps check: core-decisions rows for
    `account`/`day` -> RTH gaps -> each gap annotated with 'account' and whether it
    overlapped an open position. [] (fail-open) on any error in either read."""
    timestamps = load_core_rows_for_day(account, day, core_path, tail_bytes)
    gaps = find_rth_gaps(timestamps, day, gap_min)
    if not gaps:
        return []
    fills = load_fills(fills_path)
    for g in gaps:
        g["account"] = account
        g["open_position"] = position_open_during(account, g["start"], fills)
    return gaps


def gaps_for_day(account: str, day: str, gap_min: float = GAP_THRESHOLD_MIN,
                  core_path: Path = CORE_DECISIONS,
                  tail_bytes: int = DEFAULT_TAIL_BYTES) -> list:
    """The {start, end, duration_min} dicts for every RTH gap for `account`/`day`, with
    no fills-ledger read (cheaper than find_gaps_with_position_flag when the caller only
    needs the window, not the open-position flag)."""
    timestamps = load_core_rows_for_day(account, day, core_path, tail_bytes)
    return find_rth_gaps(timestamps, day, gap_min)


def is_rescue_exit(account: str, exit_ts: datetime, day: str,
                    gap_min: float = GAP_THRESHOLD_MIN,
                    rescue_window_min: float = RESCUE_WINDOW_MIN,
                    core_path: Path = CORE_DECISIONS,
                    tail_bytes: int = DEFAULT_TAIL_BYTES) -> bool:
    """True if `exit_ts` (naive ET) falls DURING a detected gap, or within
    `rescue_window_min` minutes AFTER its END, for this account/day.

    WINDOW INCLUDES THE GAP ITSELF, not just the post-recovery grace period -- corrected
    against the REAL 2026-09-04 case (not a hypothetical): J's dashboard exit for safe-2
    landed at 10:46:06 ET, nine seconds BEFORE the engine's own next surviving tick
    (10:46:15, which is this gap's technical 'end'). A window defined as strictly-after-
    end would misclassify the exact rescue this module exists to catch. Practically, a
    human closing a position WHILE the engine is dark is the central rescue case; a close
    landing shortly after the engine resumes (still catching up / still deciding) is the
    secondary case the `rescue_window_min` grace period covers. Fail-open: False on any
    read/parse error -- a broken detector must never silently reclassify a real
    intervention as a rescue."""
    try:
        for g in gaps_for_day(account, day, gap_min, core_path, tail_bytes):
            if g["start"] <= exit_ts <= g["end"] + timedelta(minutes=rescue_window_min):
                return True
    except Exception:  # noqa: BLE001 -- fail-open, never raise into either caller
        return False
    return False


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    ap.add_argument("--account", default="safe", choices=sorted(ACCOUNT_TO_ARM))
    ap.add_argument("--day", required=True, help="YYYY-MM-DD")
    args = ap.parse_args(argv)
    gaps = find_gaps_with_position_flag(args.account, args.day)
    if not gaps:
        print(f"{args.account} {args.day}: no RTH gap >{GAP_THRESHOLD_MIN:.0f}m")
        return 0
    for g in gaps:
        flag = " OPEN POSITION" if g["open_position"] else ""
        print(f"{g['start']} -> {g['end']} ({g['duration_min']:.1f}m){flag}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
