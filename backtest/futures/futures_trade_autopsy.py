"""futures_trade_autopsy.py -- the smallest useful post-trade autopsy for the futures lane.

WHY THIS EXISTS (queue.md FUTURES-POST-TRADE-AUTOPSY-MISSING, filed 2026-08-29 Fable futures
parity audit). SPY has `winner_autopsy.py` + `trade_autopsy.py` scheduled nightly, feeding
`analysis/winner-autopsies/`; futures had NOTHING that asks "what does futures money look
like" -- `futures_eod.py::rule_audit()` is a compliance check (did the lane follow its own
rules), not pattern-mining. This module is the futures-side mirror of that missing organ,
kept deliberately small: the futures lane has taken very few real (BROKER) fills so far, so
population-level pattern-mining (the SPY autopsy's whole point) would be premature. Read
this as a REPORTING tool over the existing ledger, not a hypothesis engine -- it writes NO
`hypothesis-queue.jsonl` entry and appends to NOTHING else, mirroring winner_autopsy.py's
own "descriptive only" discipline for exactly the same small-n reason.

WHAT IT READS
  journal/futures/trades.csv  -- the ONE canonical closed-round-trip ledger
                                  (backtest/futures/futures_journal.py::record_trade schema).
                                  Every row already carries `fills` (SIMULATED/BROKER/UNKNOWN)
                                  -- this module NEVER aggregates across that column; SIMULATED
                                  and BROKER are reported as two separate blocks, same
                                  discipline as futures_journal.summarize().

WHAT IT COMPUTES, PER CLOSED TRIP
  entry/exit time + price, exit_reason (the stage that closed it: TP1_FULL / FULL_STOP /
  BROKER_CLOSE / time_stop / etc, straight from the ledger's own `exit_reason` column),
  points and $ pnl (ledger's own `dollar_pnl` -- never recomputed, so this can never disagree
  with the number of record), and MAE/MFE in points -- BEST EFFORT from the lane's own 5m
  live bar cache (`futures.futures_live_data.load_series(..., mode="live")`), which is the
  SAME cache the live engine appends to every tick (never re-fetched here; read-only). MAE/MFE
  is `None` with an explicit reason (never silently 0.0 or omitted -- C7) when the cache does
  not cover the trade's hold window (pre-cache history, or a coverage gap).

WHAT IT WRITES
  analysis/futures/autopsy-latest.md   -- one table per fills-class, human-readable
  analysis/futures/autopsy-latest.json -- the same data, machine-readable

NOT SCHEDULED TONIGHT (queue.md item is explicit: "no scheduled task tonight -- registration
is off-limits"). Intended cadence for whoever wires the scheduled task next: after
`Gamma_FuturesEod2` (the existing rule_audit fire), same 5-6pm ET after-hours window,
$0 marginal cost (pure Python over an existing CSV + an existing local cache file, no network
calls of its own).

CLI:
    python -m futures.futures_trade_autopsy               # writes both surfaces, prints the table
    python -m futures.futures_trade_autopsy --fills BROKER # one class only
"""
from __future__ import annotations

import argparse
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

from futures.futures_journal import read_trades  # noqa: E402

OUT_DIR = REPO / "analysis" / "futures"
OUT_MD = OUT_DIR / "autopsy-latest.md"
OUT_JSON = OUT_DIR / "autopsy-latest.json"

FILLS_CLASSES = ("BROKER", "SIMULATED", "UNKNOWN")


def _et_now() -> dt.datetime:
    p = str(REPO / "setup" / "scripts")
    if p not in sys.path:
        sys.path.insert(0, p)
    from et_clock import et_now  # noqa: PLC0415

    return et_now().replace(tzinfo=None)


def _parse_ts(raw: str) -> Optional[dt.datetime]:
    """Ledger timestamps are NOT uniformly shaped: `time_entry_et` is naive ET (written by
    the trader's own et_now()), `time_exit_et` is sometimes a tz-aware UTC ISO string (written
    from a broker fill timestamp). Normalize both to naive ET so they compare against the
    (naive ET) bar cache on equal footing. Never raises -- returns None for anything
    unparseable, and every caller must treat None as 'timing unavailable', not a crash."""
    if not raw:
        return None
    try:
        ts = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if ts.tzinfo is not None:
        import zoneinfo  # noqa: PLC0415

        ts = ts.astimezone(zoneinfo.ZoneInfo("America/New_York")).replace(tzinfo=None)
    return ts


def _mae_mfe(instrument: str, side: str, entry_px: float, entry_ts: Optional[dt.datetime],
            exit_ts: Optional[dt.datetime]) -> dict:
    """Best-effort MAE/MFE (points) from the lane's own 5m live bar cache. Returns a dict
    with `available: bool` and either the two numbers or an explicit `reason` -- never a bare
    None (C7: a skip must say why)."""
    if entry_ts is None or exit_ts is None:
        return {"available": False, "reason": "unparseable_timestamp"}
    if entry_px is None:
        return {"available": False, "reason": "no_entry_price_on_ledger_row"}
    try:
        from futures.futures_live_data import load_series  # noqa: PLC0415

        # live_path()/master_path() key the cache files by the CONTRACT ROOT as traded
        # (MES_5m_live.csv, MNQ_5m_live.csv) -- NOT the underlying-index ticker (ES/NQ). The
        # ledger's `instrument` column already holds that same root ("MES"), so pass it
        # through unchanged; stripping the leading "M" would look for a file that doesn't
        # exist (ES_5m_live.csv) and silently degrade every row to bar_cache_empty.
        bars = load_series(instrument, "5m", mode="live")
    except Exception as e:  # noqa: BLE001 -- a missing/broken cache degrades, never crashes
        return {"available": False, "reason": f"bar_cache_load_failed: {type(e).__name__}: {e}"}
    if bars is None or bars.empty:
        return {"available": False, "reason": "bar_cache_empty"}

    window = bars[(bars["timestamp_et"].dt.tz_localize(None) >= entry_ts) &
                 (bars["timestamp_et"].dt.tz_localize(None) <= exit_ts)]
    if window.empty:
        return {"available": False, "reason": "no_bar_coverage_for_hold_window"}

    hi = float(window["high"].max())
    lo = float(window["low"].min())
    if side.upper() == "BUY":  # long: adverse = down, favorable = up
        mae = round(entry_px - lo, 4)
        mfe = round(hi - entry_px, 4)
    else:  # short: adverse = up, favorable = down
        mae = round(hi - entry_px, 4)
        mfe = round(entry_px - lo, 4)
    return {"available": True, "mae_points": mae, "mfe_points": mfe, "bars_in_window": len(window)}


def build_autopsy(fills: str = "BROKER") -> dict:
    """PURE (given the ledger + bar-cache files on disk): reads trades.csv filtered to one
    fills class, computes MAE/MFE per row, returns the full report dict. Never writes."""
    rows = read_trades(fills=fills)
    trips = []
    total_pnl = 0.0
    for r in rows:
        entry_ts = _parse_ts(r.get("time_entry_et", ""))
        exit_ts = _parse_ts(r.get("time_exit_et", ""))
        try:
            entry_px = float(r["entry_px"]) if r.get("entry_px") else None
        except (TypeError, ValueError):
            entry_px = None
        try:
            dollar_pnl = float(r["dollar_pnl"]) if r.get("dollar_pnl") else 0.0
        except (TypeError, ValueError):
            dollar_pnl = 0.0
        total_pnl += dollar_pnl
        mae_mfe = _mae_mfe(r.get("instrument", ""), r.get("side", ""), entry_px, entry_ts, exit_ts)
        trips.append({
            "date": r.get("date"), "instrument": r.get("instrument"),
            "setup": r.get("setup"), "direction": r.get("direction"), "side": r.get("side"),
            "qty": r.get("qty"),
            "time_entry_et": r.get("time_entry_et"), "time_exit_et": r.get("time_exit_et"),
            "hold_minutes": r.get("hold_minutes"),
            "entry_px": r.get("entry_px"), "exit_px": r.get("exit_px"),
            "stop_px": r.get("stop_px"), "tp1_px": r.get("tp1_px"),
            "exit_reason": r.get("exit_reason") or "UNKNOWN",
            "dollar_pnl": dollar_pnl, "r_multiple": r.get("r_multiple"),
            "backend": r.get("backend"),
            "mae_mfe": mae_mfe,
        })
    wins = [t for t in trips if t["dollar_pnl"] > 0]
    return {
        "generated_at_et": _et_now().isoformat(timespec="seconds"),
        "fills": fills,
        "evidence_class": ("mechanism only -- simulated fills are never edge evidence"
                           if fills == "SIMULATED" else
                           "broker fills" if fills == "BROKER" else "undisclosed -- data hygiene issue"),
        "n_trips": len(trips),
        "total_pnl_usd": round(total_pnl, 2),
        "win_rate": round(len(wins) / len(trips), 4) if trips else None,
        "trips": trips,
    }


def _fmt_row(t: dict) -> str:
    mm = t["mae_mfe"]
    mae_str = f"{mm['mae_points']:.2f}" if mm.get("available") else f"n/a ({mm.get('reason')})"
    mfe_str = f"{mm['mfe_points']:.2f}" if mm.get("available") else "n/a"
    return (f"| {t['date']} | {t['setup']} | {t['direction']}/{t['side']} | {t['qty']} | "
           f"{t['entry_px']} -> {t['exit_px']} | {t['exit_reason']} | "
           f"${t['dollar_pnl']:.2f} | {mae_str} | {mfe_str} | {t['hold_minutes']}m |")


def render_markdown(reports: list[dict]) -> str:
    lines = [f"# Futures trade autopsy -- {reports[0]['generated_at_et'] if reports else ''}",
            "",
            "> Descriptive only (per winner_autopsy.py's own small-n discipline). No "
            "hypothesis queued, nothing else appended. SIMULATED and BROKER are never "
            "aggregated together.", ""]
    for rep in reports:
        lines.append(f"## {rep['fills']} ({rep['evidence_class']})")
        lines.append("")
        lines.append(f"n={rep['n_trips']} -- total_pnl=${rep['total_pnl_usd']:.2f} -- "
                     f"win_rate={rep['win_rate']}")
        lines.append("")
        if rep["trips"]:
            lines.append("| date | setup | dir/side | qty | entry->exit | exit_reason | "
                         "$pnl | MAE(pts) | MFE(pts) | hold |")
            lines.append("|---|---|---|---|---|---|---|---|---|---|")
            for t in rep["trips"]:
                lines.append(_fmt_row(t))
        else:
            lines.append("_no closed trips in this class_")
        lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Futures post-trade autopsy (descriptive, read-only)")
    ap.add_argument("--fills", choices=list(FILLS_CLASSES), default=None,
                    help="one class only; default = all three classes, reported separately")
    args = ap.parse_args(argv)

    classes = [args.fills] if args.fills else list(FILLS_CLASSES)
    reports = [build_autopsy(f) for f in classes]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(reports, indent=2, default=str), encoding="utf-8")
    md = render_markdown(reports)
    OUT_MD.write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
