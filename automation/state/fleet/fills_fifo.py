"""fills_fifo.py -- the ONE FIFO round-trip reconstructor for per-arm REAL fills.

EXTRACTED VERBATIM from `backtest/tools/fleet_arm_replay.py#mine_real_arm_fills`
(2026-08-04, RISKY3-SPECULATIVE lane) so the standing weekly divergence instrument
(`setup/scripts/full_send_vs_gated.py`, stdlib-only, scheduled-task-friendly) and the
heavy replay harness can share ONE implementation instead of drifting two copies (C14).
`fleet_arm_replay.mine_real_arm_fills` now delegates here -- same name, same signature,
same behavior; its tests (`backtest/tests/test_fleet_arm_replay.py`) exercise THIS body
through that re-export.

STDLIB ONLY by design: no pandas/numpy -- this must be importable by a per-minute-safe,
$0 scheduled reporting script without the backtest venv.

THE BUG THIS BODY ALREADY CARRIES THE FIX FOR (do not "simplify" it away): OCC symbols
are date-scoped but NOT round-trip-scoped -- the same contract can be bought, fully
sold, and bought again the same day. The accumulator MUST flush and reset the instant
open_qty returns to zero, or a real same-day re-entry gets blended into one fictional
weighted-average anchor (caught 2026-08-02: replayed +$605 against a real -$80 while
the aggregate net still summed correctly). See fleet_arm_replay.py's module docstring.
"""
from __future__ import annotations

import json
from pathlib import Path

_FLEET_DIR = Path(__file__).resolve().parent
REPO_ROOT = _FLEET_DIR.parents[2]
FILLS_LEDGER_PATH = REPO_ROOT / "automation" / "state" / "fills-ledger.jsonl"


def mine_real_arm_fills(arm_id: str, ledger_path: Path = FILLS_LEDGER_PATH) -> list[dict]:
    """FIFO-reconstruct CLOSED round trips for `arm_id` from fills-ledger.jsonl,
    `attribution=='engine'` rows only (never J's manual fills). Partial exits (TP1 +
    runner, 2 sell legs) are summed into ONE round trip. Returns dicts:
    date/symbol/side/entry_ts_et/entry_premium/exit_ts_et/exit_premium/qty/real_pnl.
    `exit_premium` is None (and `_note` explains) whenever >1 sell leg resolved the
    position -- real_pnl (the FIFO net) is still exact regardless."""
    if not ledger_path.exists():
        return []
    by_symbol: dict[str, list[dict]] = {}
    with ledger_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("arm") != arm_id or row.get("attribution") != "engine":
                continue
            by_symbol.setdefault(row["symbol"], []).append(row)

    out: list[dict] = []
    for symbol, legs in by_symbol.items():
        legs = sorted(legs, key=lambda r: r["ts_et"])
        side_p_or_c = symbol[-9]
        if side_p_or_c not in ("C", "P"):
            continue  # defensive: malformed symbol, skip rather than fabricate a side
        open_qty = 0.0
        buy_notional = 0.0
        buy_qty = 0.0
        sell_legs: list[dict] = []
        entry_ts = None
        for leg in legs:
            side = leg.get("side")
            q = float(leg.get("qty") or 0.0)
            px = float(leg.get("price") or 0.0)
            if side == "buy":
                if open_qty <= 1e-9:
                    # starting a FRESH round trip -- either the very first buy on this
                    # symbol, or a re-entry after a prior one fully closed (reset below).
                    entry_ts = leg["ts_et"]
                    buy_notional = 0.0
                    buy_qty = 0.0
                    sell_legs = []
                open_qty += q
                buy_notional += q * px
                buy_qty += q
            elif side == "sell":
                if open_qty <= 1e-9:
                    continue  # sell with nothing open -- data anomaly, skip defensively
                open_qty -= q
                sell_legs.append(leg)
                if abs(open_qty) > 1e-6:
                    continue  # still open (partial exit) -- keep accumulating this round trip
                # ROUND TRIP CLOSED -- flush exactly this one; a later buy starts fresh.
                sell_notional = sum(float(s["qty"]) * float(s["price"]) for s in sell_legs)
                sell_qty = sum(float(s["qty"]) for s in sell_legs)
                real_pnl = round((sell_notional - buy_notional) * 100.0, 2)
                entry_premium = round(buy_notional / buy_qty, 4) if buy_qty else None
                out.append({
                    "date": legs[0]["date_et"], "symbol": symbol, "side": side_p_or_c,
                    "entry_ts_et": entry_ts, "entry_premium": entry_premium,
                    "exit_ts_et": sell_legs[-1]["ts_et"],
                    "exit_premium": (round(sell_notional / sell_qty, 4) if len(sell_legs) == 1 else None),
                    "qty": int(round(buy_qty)), "real_pnl": real_pnl,
                    "_note": (f"{len(sell_legs)}-leg exit" if len(sell_legs) > 1 else None),
                })
        # leftover open position (open_qty > 0) is never flushed -- "still open", excluded.
    return sorted(out, key=lambda r: r["entry_ts_et"])
