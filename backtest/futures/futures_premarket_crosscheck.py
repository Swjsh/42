"""futures_premarket_crosscheck.py -- CROSS-CHECK ONLY, closes FUTURES-PREMARKET-LEVELS-
CONSUMER (queue.md, DECIDED 2026-09-03 03:43 ET Fable: "cross-check only (freeze-safe
default); implementation folded into FUTURES-LANE-WIRING-2 (c)").

`futures_trader_core.run_tick()` computes its OWN support/resistance levels every tick via
`lib.levels._detect_from_history` fed the live bar spine (the same helper
`futures_heartbeat_core.compute_latest_signals` uses internally -- but that function does
not surface the level set to its caller). `Gamma_FuturesPremarket2` separately writes a
labeled level set (PDH/PDL/PDC/ONH/ONL) to `automation/state/futures/key-levels.json` before
the open. Neither has ever consumed the other (`futures_premarket.py`'s own docstring: "NO
execution lane reads these files yet").

THIS MODULE MAKES NO ENTRY DECISION AND CHANGES NO BEHAVIOUR. It is a read-only diagnostic:
for each session, once, it measures the nearest-distance (points) from every premarket level
to the closest internally-detected level and appends ONE row to
`automation/state/futures/premarket-crosscheck.jsonl`. Nothing in the trading path reads
that file back.

WHY ONCE PER SESSION, NOT EVERY TICK: the lane ticks every 5 min during RTH (~78x/day); both
level sets are derived from the same PRIOR-day-closed bars and do not meaningfully change
intraday, so logging on every tick would just be duplicate noise. `already_logged_today()`
makes the append idempotent per `for_session` (today's calendar date, ET).

Row shape (queue.md FUTURES-LANE-WIRING-2 (c)):
    {date, instrument, n_internal, n_premarket, matched_within_2pts, max_gap_pts,
     unmatched_premarket: [{label, price, nearest_internal_gap_pts}, ...]}
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest",):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

import pandas as pd  # noqa: E402

# Module attributes (not locals) so tests can monkeypatch them the same way every other
# futures test isolates state (see test_futures_mirror_shadow.py's _isolate_state).
CROSSCHECK_OUT = REPO / "automation" / "state" / "futures" / "premarket-crosscheck.jsonl"
KEY_LEVELS_PATH = REPO / "automation" / "state" / "futures" / "key-levels.json"
MATCH_THRESHOLD_PTS = 2.0


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def already_logged_today(for_session: str, *, path: Path = None) -> bool:
    """True iff a row for this session date already exists in the crosscheck ledger --
    makes the append idempotent across a session's ~78 ticks. Fail-open: an unreadable file
    reads as "not logged yet" (the worst case is one harmless extra row, never a block)."""
    p = path if path is not None else CROSSCHECK_OUT
    if not p.exists():
        return False
    try:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("date") == for_session:
                    return True
    except OSError:
        return False
    return False


def _load_premarket_levels(symbol: str, *, path: Path = None) -> Optional[list]:
    """Returns the premarket producer's `levels` list for `symbol`, or None when the file
    is missing/unreadable/absent for this instrument, or the instrument's own block is not
    status=="OK" (e.g. DATA_MISSING) -- never fabricated, never guessed."""
    p = path if path is not None else KEY_LEVELS_PATH
    if not p.exists():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    inst_block = (doc.get("instruments") or {}).get(symbol)
    if not inst_block or inst_block.get("status") != "OK":
        return None
    levels = inst_block.get("levels") or []
    return [lv for lv in levels if isinstance(lv.get("price"), (int, float))]


def compute_internal_levels(bars: "pd.DataFrame | None", today: dt.date) -> list:
    """The SAME level detector the SEE step already runs internally
    (`lib.levels._detect_from_history`), reused here rather than reimplemented, fed bars
    <= today only (no look-ahead). Returns the flat `active` level list (plain floats --
    the internal detector carries no labels)."""
    from lib.levels import _detect_from_history  # noqa: PLC0415

    if bars is None or bars.empty:
        return []
    bars_to_now = bars[bars["timestamp_et"].dt.date <= today]
    if bars_to_now.empty:
        return []
    lset = _detect_from_history(bars_to_now, today)
    return list(lset.active)


def crosscheck_and_log(symbol: str, bars: "pd.DataFrame | None", now_et: dt.datetime,
                       *, key_levels_path: Path = None, out_path: Path = None,
                       match_threshold_pts: float = MATCH_THRESHOLD_PTS) -> Optional[dict]:
    """Compare internal vs premarket levels for `symbol` and append ONE row for today's
    session. Returns None (no-op) when: the premarket file/instrument block is missing
    (cross-check-only per the DECIDED item -- never fabricates a comparison it can't make),
    or a row for today already exists (idempotent per session). NEVER raises -- diagnostic
    only, must never affect the caller's entry/exit decisions."""
    try:
        klp = key_levels_path if key_levels_path is not None else KEY_LEVELS_PATH
        outp = out_path if out_path is not None else CROSSCHECK_OUT

        for_session = now_et.date().isoformat()
        if already_logged_today(for_session, path=outp):
            return None
        premarket_levels = _load_premarket_levels(symbol, path=klp)
        if premarket_levels is None:
            return None
        internal_levels = compute_internal_levels(bars, now_et.date())

        unmatched = []
        nearest_gaps = []
        matched = 0
        for lv in premarket_levels:
            price = float(lv["price"])
            nearest = min((abs(price - p) for p in internal_levels), default=None)
            if nearest is not None:
                nearest_gaps.append(nearest)
            if nearest is not None and nearest <= match_threshold_pts:
                matched += 1
            else:
                unmatched.append({
                    "label": lv.get("label"),
                    "price": price,
                    "nearest_internal_gap_pts": (round(nearest, 4) if nearest is not None
                                                 else None),
                })

        row = {
            "date": for_session,
            "instrument": symbol,
            "n_internal": len(internal_levels),
            "n_premarket": len(premarket_levels),
            "matched_within_2pts": matched,
            "max_gap_pts": round(max(nearest_gaps), 4) if nearest_gaps else None,
            "unmatched_premarket": unmatched,
        }
        _append_jsonl(outp, row)
        return row
    except Exception:  # noqa: BLE001 -- diagnostic-only, never breaks the tick
        return None
