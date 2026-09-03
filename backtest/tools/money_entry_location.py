"""money_entry_location.py -- scratch analysis for H1 ENTRY LOCATION hypothesis.

Read-only over cached local data ONLY (no network, no broker/market-data calls).
Population: analysis/pain-ledger/mae-mfe.json trades since 2026-08-06 (real-fills-derived
reconstructed positions, real OPRA bars for MAE/MFE, realized_pnl from broker fills).

For each trade, computes:
  - range_position at the entry tick = (spy_price_at_entry - session_lo) / (session_hi - session_lo)
    where session_hi/lo = max/min of the 'spy' field logged in core-decisions.jsonl (1/min,
    both safe+bold accounts, same underlying instrument for every arm) over ticks with
    ts_et <= entry_ts (same trading date). NO LOOKAHEAD: only ticks at or before the entry
    timestamp are used.
  - vix_at_entry = vix field on the last such tick.
  - first_exit_stage = the 'stage' of the earliest placed exit_pass action recorded for that
    (arm, date, symbol) across core-decisions.jsonl (safe-2/bold-2) or the matching
    automation/state/fleet/<arm>/decisions.jsonl (safe-3/risky-1/risky-3).

Writes a single JSON blob to stdout-redirected file for the report writer to consume.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path("C:/Users/jackw/Desktop/42")
ET = ZoneInfo("America/New_York")

CUTOFF_DATE = "2026-08-06"
OCC_RE = re.compile(r"^SPY(\d{6})([CP])(\d{8})$")

CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
MAE_MFE = REPO / "analysis" / "pain-ledger" / "mae-mfe.json"
FLEET_ARMS = ["safe-3", "risky-1", "risky-3"]
FLEET_FILES = {a: REPO / "automation" / "state" / "fleet" / a / "decisions.jsonl" for a in FLEET_ARMS}
ACCOUNT_TO_ARM = {"safe": "safe-2", "bold": "bold-2"}


def parse_utc(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def to_et_naive(ts_aware_or_offset: dt.datetime) -> dt.datetime:
    """Convert a timezone-aware datetime to naive ET wall-clock (matches core-decisions ts_et)."""
    return ts_aware_or_offset.astimezone(ET).replace(tzinfo=None)


def parse_ts_et_field(ts: str) -> dt.datetime | None:
    """core-decisions ts_et is naive ET ('2026-08-06T09:30:03'); fleet ts_et carries an
    explicit -04:00/-05:00 offset ('2026-06-21T21:53:32.493267-04:00'). Normalize both to
    naive ET wall-clock datetimes so they compare directly."""
    if not ts:
        return None
    try:
        d = dt.datetime.fromisoformat(ts)
    except ValueError:
        return None
    if d.tzinfo is not None:
        d = to_et_naive(d)
    return d


def main() -> None:
    # ---- 1. load mae-mfe trades since cutoff ----------------------------------------------
    mm = json.loads(MAE_MFE.read_text(encoding="utf-8"))
    trades = [t for t in mm["trades"] if t["date"] >= CUTOFF_DATE]

    # ---- 2. build per-date SPY/VIX tick series from core-decisions (both accounts) --------
    ticks_by_date: dict[str, list[tuple[dt.datetime, float, float | None]]] = defaultdict(list)
    conviction_by_key: dict[tuple[str, str, str], dict] = {}  # (arm,date,symbol) -> conviction dict (last seen)
    exit_actions: dict[tuple[str, str, str], list[tuple[str, str]]] = defaultdict(list)

    n_core = 0
    with CORE_DECISIONS.open(encoding="utf-8") as f:
        for line in f:
            n_core += 1
            ts_raw = None
            if '"ts_et"' not in line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts_raw = r.get("ts_et")
            if not ts_raw or ts_raw[:10] < CUTOFF_DATE:
                continue
            d = ts_raw[:10]
            acct = r.get("account")
            arm = ACCOUNT_TO_ARM.get(acct)

            spy = r.get("spy")
            if spy is not None:
                tdt = parse_ts_et_field(ts_raw)
                if tdt is not None:
                    ticks_by_date[d].append((tdt, float(spy), r.get("vix")))

            if arm and r.get("action") == "PLACED":
                conv = r.get("conviction")
                exec_ = r.get("exec") or {}
                sym = exec_.get("symbol")
                if conv and sym:
                    conviction_by_key[(arm, d, sym)] = conv

            if arm:
                for ep in (r.get("exit_pass") or []):
                    sym = ep.get("symbol")
                    if not sym:
                        continue
                    for a in (ep.get("actions") or []):
                        if a.get("placed"):
                            exit_actions[(arm, d, sym)].append((ts_raw, a.get("stage")))

    for d in ticks_by_date:
        ticks_by_date[d].sort(key=lambda x: x[0])

    # ---- 3. fleet decisions: exit_pass stream only (no 'spy'/'conviction' fields there) ---
    n_fleet = 0
    for arm, path in FLEET_FILES.items():
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            for line in f:
                n_fleet += 1
                if '"exit_pass"' not in line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_raw = r.get("ts_et")
                if not ts_raw or ts_raw[:10] < CUTOFF_DATE:
                    continue
                d = ts_raw[:10]
                for ep in (r.get("exit_pass") or []):
                    sym = ep.get("symbol")
                    if not sym:
                        continue
                    for a in (ep.get("actions") or []):
                        if a.get("placed"):
                            exit_actions[(arm, d, sym)].append((ts_raw, a.get("stage")))

    for k in exit_actions:
        exit_actions[k].sort(key=lambda x: x[0])

    # ---- 4. per-trade enrichment -----------------------------------------------------------
    out_rows = []
    n_no_tick_coverage = 0
    for t in trades:
        sym = t["symbol"]
        m = OCC_RE.match(sym)
        side = m.group(2) if m else None
        date = t["date"]
        arm = t["arm"]

        entry_utc = parse_utc(t["entry_ts_utc"])
        entry_et = to_et_naive(entry_utc)

        ticks = ticks_by_date.get(date, [])
        subset = [tk for tk in ticks if tk[0] <= entry_et]
        range_position = None
        session_hi = session_lo = spy_at_entry = vix_at_entry = None
        n_ticks_used = len(subset)
        if subset:
            session_hi = max(tk[1] for tk in subset)
            session_lo = min(tk[1] for tk in subset)
            spy_at_entry = subset[-1][1]
            vix_at_entry = subset[-1][2]
            if session_hi is not None and session_lo is not None and session_hi > session_lo:
                range_position = round((spy_at_entry - session_lo) / (session_hi - session_lo), 4)
        else:
            n_no_tick_coverage += 1

        acts = exit_actions.get((arm, date, sym))
        first_exit_stage = acts[0][1] if acts else None
        n_exit_actions_matched = len(acts) if acts else 0

        conv = conviction_by_key.get((arm, date, sym))
        conv_range_position = None
        conv_range_extreme = None
        if conv:
            comps = conv.get("components") or {}
            conv_range_position = comps.get("range_position")
            conv_range_extreme = comps.get("range_extreme")

        out_rows.append({
            "date": date,
            "arm": arm,
            "symbol": sym,
            "side": side,
            "setup": t.get("setup"),
            "outcome": t.get("outcome"),
            "realized_pnl": t.get("realized_pnl"),
            "qty": t.get("qty"),
            "entry_price": t.get("entry_price"),
            "hold_minutes": t.get("hold_minutes"),
            "entry_ts_utc": t["entry_ts_utc"],
            "entry_et": entry_et.isoformat(),
            "range_position": range_position,
            "session_hi": session_hi,
            "session_lo": session_lo,
            "spy_at_entry": spy_at_entry,
            "n_ticks_used_for_range": n_ticks_used,
            "vix_at_entry": vix_at_entry,
            "first_exit_stage": first_exit_stage,
            "n_exit_actions_matched": n_exit_actions_matched,
            "stop_basis": (t.get("stop") or {}).get("stop_basis"),
            "conv_range_position": conv_range_position,
            "conv_range_extreme": conv_range_extreme,
        })

    result = {
        "generated_note": "money_entry_location.py -- cached-data-only, no network",
        "n_core_lines_scanned": n_core,
        "n_fleet_lines_scanned": n_fleet,
        "n_trades_since_cutoff": len(trades),
        "n_trades_no_tick_coverage": n_no_tick_coverage,
        "n_trades_with_range_position": sum(1 for r in out_rows if r["range_position"] is not None),
        "n_trades_with_conviction_row": sum(1 for r in out_rows if r["conv_range_position"] is not None),
        "n_trades_with_exit_stage": sum(1 for r in out_rows if r["first_exit_stage"] is not None),
        "rows": out_rows,
    }
    out_path = REPO / "analysis" / "deep-research" / "2026-09-03-money" / "entry-location-rows.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"wrote {out_path} -- {len(out_rows)} rows")
    print(f"n_no_tick_coverage={n_no_tick_coverage}")
    print(f"n_with_range_position={result['n_trades_with_range_position']}")
    print(f"n_with_conviction_row={result['n_trades_with_conviction_row']}")
    print(f"n_with_exit_stage={result['n_trades_with_exit_stage']}")


if __name__ == "__main__":
    main()
