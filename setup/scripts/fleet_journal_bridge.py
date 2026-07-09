"""fleet_journal_bridge.py -- closes the Rule-8 journaling debt for the 4
fleet_rest arms (safe-1, safe-3, risky-1, risky-3): their real round-trip fills
were never reaching `journal/trades.csv`, so per doctrine ("if it's not in the
journal, it didn't happen") 193+ real fills were invisible to the journal system
of record. This script is that bridge. It does NOT touch the core accounts'
existing journaling path (safe-2/bold-2, written by the live heartbeat) and does
NOT touch analysis/autopsies/ (a separate consumer being fixed elsewhere).

SOURCE (preferred -- C1 real-fills authority): `automation/state/pnl-statement.json`'s
`round_trips` array. That file is built by `setup/scripts/broker_fills.py` via
`fleet_broker.load_creds()` READ-ONLY GETs against Alpaca `/v2/account/activities/FILL`,
and is already refreshed every 10 min 09:00-16:00 ET + one 16:05 ET EOD fire by the
`Gamma_BrokerFills` scheduled task. This bridge does NOT re-call Alpaca or import
`fleet_broker` itself: it is a PURE local-file transform (zero network calls, zero
credentials touched, stdlib-only) that reads the already-materialized broker-truth
artifact. Re-deriving FIFO round-trip pairing here would duplicate broker_fills.py's
tested logic and risk drift between two independently-computed P&L truths -- reading
its output instead guarantees this journal always agrees with what J already sees in
fill_funnel.py / firm_brief.py. Setup/strategy/exit-stage context (not present in the
fills-only statement) is joined in via `automation/state/fills-ledger.jsonl`
(activity_id -> order_id) and each arm's `automation/state/fleet/<arm>/decisions.jsonl`
(order_id -> ENTER decision row / exit action), both also pure local reads.

FALLBACK (only used for an (arm, date) pnl-statement.json has NOTHING for -- e.g. a
day before broker_fills.py's backfill window, or a fresh clone before it has fired):
reconstruct an approximate round trip directly from that arm's decisions.jsonl ENTER
row + the exit_pass action that closed it. Lower fidelity -- there is no true fill
price in the decision ledger, so the exit price is parsed from the exit action's own
threshold text (e.g. "premium_stop @ 0.43"); if no usable price is found the leg is
SKIPPED, never fabricated. Rows built this way are labeled
`fill_quality=decisions_reconstruction (approximate)` so they are never mistaken for
broker-truth. (`automation/state/trade-today.json` is a core-account-only state file,
not per-arm, and is intentionally not used here.)

SCOPE: SPY 0DTE options only. A few of these accounts' Alpaca histories also contain
crypto fills (symbol contains "/") -- excluded here: crypto is gym-only per doctrine
and the option-shaped trades.csv columns (contract/dte/strike/c_or_p) don't fit it.

IDEMPOTENT: `automation/state/.fleet-journal-watermark.json` records every
(arm, entry_activity_id, exit_activity_id) key already written. Re-running (including
across the primary/fallback boundary) appends zero duplicate rows. Rows are appended
(never rewrites/reformats existing trades.csv lines -- some pre-existing rows have
non-canonical quoting; this script only adds well-formed lines after them).

CLI:  backtest/.venv/Scripts/python.exe setup/scripts/fleet_journal_bridge.py
        [--date YYYY-MM-DD] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
FLEET_DIR = STATE / "fleet"
PNL_STATEMENT = STATE / "pnl-statement.json"
FILLS_LEDGER = STATE / "fills-ledger.jsonl"
ACCOUNTS_JSON = FLEET_DIR / "accounts.json"
TRADES_CSV = REPO / "journal" / "trades.csv"
WATERMARK = STATE / ".fleet-journal-watermark.json"

# The 4 fleet_rest arms (execution=fleet_rest -> 100% engine per broker_fills.py's
# attribution rule). Intentionally re-declared here (not imported from broker_fills)
# to keep this module dependency-free -- see module docstring.
FLEET_REST_ARMS: tuple[str, ...] = ("safe-1", "safe-3", "risky-1", "risky-3")

# Canonical trades.csv schema (43 columns). Source of truth: journal/trades.csv header.
# Identical to backtest/autoresearch/webull_winner_journal.py's SCHEMA (the codebase's
# other trades.csv-shaped bridge) -- kept independent (different subsystem/venv) but
# byte-for-byte matched to the live header.
SCHEMA: list[str] = [
    "date", "time_entry", "time_exit", "setup", "contract", "dte", "strike",
    "c_or_p", "qty", "entry_px", "exit_px", "premium_paid", "premium_received",
    "dollar_pnl", "r_multiple", "stop_px", "target_px", "dollar_risk",
    "pct_risk_of_acct", "account_equity_pre", "followed_rules", "setup_quality",
    "fill_quality", "gamma_recommended", "j_override", "hold_minutes",
    "trade_grade", "trade_grade_score", "delta_at_entry", "iv_at_entry",
    "iv_regime", "slippage_cents", "exit_slippage_cents", "tod_bucket",
    "bars_after_trigger", "entry_relative_to_bar", "hold_quality_pct",
    "cf_time_stop_pnl", "cf_high_water_pnl", "archetype_match_json",
    "tape_assistance", "notes_short", "account_id",
]

_OCC_RE = re.compile(r"^([A-Z]+)(\d{2})(\d{2})(\d{2})([CP])(\d{8})$")
_PRICE_RE = re.compile(r"@\s*([\d.]+)")

PRIMARY_SOURCE_LABEL = "pnl-statement.json (T1 broker-truth round_trips)"
FALLBACK_SOURCE_LABEL = "decisions.jsonl reconstruction (approximate -- broker fills unavailable)"


# --------------------------------------------------------------------------- #
# small pure helpers
# --------------------------------------------------------------------------- #
def _is_option(symbol: str) -> bool:
    """OCC option symbols are >=15 chars; crypto pairs contain '/'. Mirrors
    broker_fills._is_option (duplicated intentionally -- see module docstring)."""
    return isinstance(symbol, str) and len(symbol) >= 15 and "/" not in symbol


def _parse_occ_symbol(symbol: str) -> Optional[dict[str, Any]]:
    m = _OCC_RE.match(symbol or "")
    if not m:
        return None
    root, yy, mm, dd, right, strike_raw = m.groups()
    try:
        strike = int(strike_raw) / 1000.0
    except ValueError:
        return None
    return {"root": root, "expiry": f"20{yy}-{mm}-{dd}", "right": right, "strike": strike}


def _fmt_num(x: Any) -> str:
    """Number -> trades.csv-style string (no trailing .0, no float noise)."""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return ""
    if f == int(f):
        return str(int(f))
    return f"{f:g}"


def _tod_bucket(hhmm: str) -> str:
    try:
        h, m = (int(x) for x in hhmm.split(":")[:2])
    except (ValueError, AttributeError):
        return ""
    minutes = h * 60 + m
    if minutes < 11 * 60:
        return "MORNING"
    if minutes < 14 * 60:
        return "MIDDAY"
    return "AFTERNOON"


def _hold_minutes(entry_ts_et: str, exit_ts_et: str) -> str:
    try:
        a = dt.datetime.fromisoformat(entry_ts_et)
        b = dt.datetime.fromisoformat(exit_ts_et)
        return str(int(round((b - a).total_seconds() / 60)))
    except (ValueError, TypeError):
        return ""


def _rt_key(rt: dict) -> str:
    return f"{rt.get('arm')}::{rt.get('entry_activity_id')}::{rt.get('exit_activity_id')}"


# --------------------------------------------------------------------------- #
# ledger / index readers (all pure local-file reads)
# --------------------------------------------------------------------------- #
def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def _load_accounts_meta(accounts_json_path: Path) -> dict[str, dict]:
    if not accounts_json_path.exists():
        return {}
    try:
        data = json.loads(accounts_json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, dict] = {}
    for a in data.get("arms", []):
        aid = a.get("id")
        if aid:
            out[aid] = {"cell": a.get("cell"), "starting_equity": a.get("starting_equity")}
    return out


def _build_activity_to_order(fills_ledger_path: Path, arms: tuple[str, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in _load_jsonl(fills_ledger_path):
        if row.get("arm") not in arms:
            continue
        aid, oid = row.get("activity_id"), row.get("order_id")
        if aid and oid:
            out[aid] = oid
    return out


def _build_decision_index(fleet_dir: Path, arm: str) -> tuple[dict[str, dict], dict[str, dict]]:
    """order_id -> ENTER decision row, order_id -> exit action info, for one arm."""
    path = fleet_dir / arm / "decisions.jsonl"
    by_order_entry: dict[str, dict] = {}
    by_order_exit: dict[str, dict] = {}
    for row in _load_jsonl(path):
        placement = row.get("placement") or {}
        broker = placement.get("broker") or {}
        oid = broker.get("id")
        if oid and str(row.get("action", "")).startswith("ENTER"):
            r = dict(row)
            r["_order_id"] = oid
            by_order_entry.setdefault(oid, r)
        for ep in (row.get("exit_pass") or []):
            for act in (ep.get("actions") or []):
                b = act.get("broker") or {}
                eoid = b.get("id")
                if eoid and act.get("placed"):
                    by_order_exit.setdefault(eoid, {
                        "stage": act.get("stage", ""), "reason": act.get("reason", ""),
                        "kind": act.get("kind", ""), "_order_id": eoid,
                    })
    return by_order_entry, by_order_exit


def _load_watermark(path: Path) -> dict:
    if not path.exists():
        return {"schema": "fleet-journal-watermark-v1", "processed": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"schema": "fleet-journal-watermark-v1", "processed": {}}
    data.setdefault("processed", {})
    return data


def _save_watermark(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")


# --------------------------------------------------------------------------- #
# round-trip sources
# --------------------------------------------------------------------------- #
def _primary_round_trips(pnl_statement_path: Path, arms: tuple[str, ...],
                          date_filter: Optional[str]) -> list[dict]:
    if not pnl_statement_path.exists():
        return []
    try:
        stmt = json.loads(pnl_statement_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for rt in stmt.get("round_trips", []):
        if rt.get("arm") not in arms:
            continue
        if not _is_option(rt.get("symbol", "")):
            continue  # crypto / non-option -- out of scope (crypto is gym-only)
        if date_filter and rt.get("date_et") != date_filter:
            continue
        out.append(rt)
    return out


def _fallback_round_trips(fleet_dir: Path, arms: tuple[str, ...],
                           date_filter: Optional[str]) -> list[dict]:
    """Single forward pass per arm: track open entries by symbol, close them out
    against the first placed exit_pass action seen for that symbol. Never invents
    a price -- a leg with no parseable exit price is dropped, not guessed."""
    out: list[dict] = []
    for arm in arms:
        path = fleet_dir / arm / "decisions.jsonl"
        open_lots: dict[str, dict] = {}
        for row in _load_jsonl(path):
            placement = row.get("placement") or {}
            broker = placement.get("broker") or {}
            action = str(row.get("action", ""))
            symbol = placement.get("symbol")
            if action.startswith("ENTER") and broker.get("id") and symbol and _is_option(symbol):
                entry_row = dict(row)
                entry_row["_order_id"] = broker.get("id")
                open_lots[symbol] = entry_row
            for ep in (row.get("exit_pass") or []):
                sym = ep.get("symbol")
                entry_row = open_lots.get(sym)
                if not entry_row:
                    continue
                for act in (ep.get("actions") or []):
                    if not act.get("placed"):
                        continue
                    entry_placement = entry_row.get("placement") or {}
                    entry_px = entry_placement.get("entry_px")
                    entry_ts = entry_row.get("ts_et", "")
                    date_et = entry_ts[:10]
                    qty = entry_row.get("qty")
                    exit_ts = row.get("ts_et", "")
                    exit_broker = act.get("broker") or {}
                    m = _PRICE_RE.search(act.get("reason", ""))
                    exit_px = float(m.group(1)) if m else None
                    del open_lots[sym]
                    if date_filter and date_et != date_filter:
                        break
                    if exit_px is None or entry_px is None or qty is None:
                        break  # never fabricate a price/pnl -- drop this leg
                    pnl = round((exit_px - float(entry_px)) * 100 * float(qty), 2)
                    out.append({
                        "arm": arm, "symbol": sym,
                        "entry_activity_id": f"decisions:{entry_row['_order_id']}",
                        "exit_activity_id": f"decisions:{exit_broker.get('id') or exit_ts}",
                        "entry_price": entry_px, "exit_price": exit_px, "qty": qty,
                        "pnl": pnl, "entry_ts_et": entry_ts, "exit_ts_et": exit_ts,
                        "attribution": "engine", "date_et": date_et,
                        "_entry_dec": entry_row,
                        "_exit_info": {"stage": act.get("stage", ""), "reason": act.get("reason", ""),
                                       "_order_id": exit_broker.get("id")},
                    })
                    break
    return out


# --------------------------------------------------------------------------- #
# row assembly
# --------------------------------------------------------------------------- #
def build_row(rt: dict, entry_dec: Optional[dict], exit_info: Optional[dict],
              arm_meta: dict, source_label: str) -> Optional[dict[str, str]]:
    """One round trip + joined decision context -> one canonical trades.csv row.
    Returns None only if the symbol itself isn't a parseable SPY option (defensive;
    callers already filter to _is_option before reaching here)."""
    parsed = _parse_occ_symbol(rt.get("symbol", ""))
    if not parsed:
        return None

    arm = rt["arm"]
    qty = rt.get("qty")
    entry_px = rt.get("entry_price")
    exit_px = rt.get("exit_price")
    pnl = rt.get("pnl")
    entry_ts = rt.get("entry_ts_et", "") or ""
    exit_ts = rt.get("exit_ts_et", "") or ""
    date_et = rt.get("date_et") or entry_ts[:10]

    premium_paid = round((float(entry_px) if entry_px is not None else 0.0) * 100 * (float(qty) if qty else 0.0), 2)
    premium_received = round((float(exit_px) if exit_px is not None else 0.0) * 100 * (float(qty) if qty else 0.0), 2)

    entry_dec = entry_dec or {}
    exit_info = exit_info or {}
    placement = entry_dec.get("placement") or {}

    setup_name = entry_dec.get("setup_name") or "UNKNOWN_FLEET_FILL"
    quality = entry_dec.get("quality", "")
    entry_reason = entry_dec.get("reason", "")
    stop_px = placement.get("stop", "")
    target_px = placement.get("tp", "")
    decision_entry_px = placement.get("entry_px")
    equity_pre = entry_dec.get("equity")
    if equity_pre is None:
        equity_pre = arm_meta.get("starting_equity")

    exit_stage = exit_info.get("stage", "")
    exit_reason = exit_info.get("reason", "")

    pct_risk = ""
    try:
        if equity_pre:
            pct_risk = f"{(premium_paid / float(equity_pre)) * 100:.1f}%"
    except (TypeError, ZeroDivisionError, ValueError):
        pct_risk = ""

    slippage_cents = ""
    try:
        if decision_entry_px is not None and entry_px is not None:
            slippage_cents = str(round((float(entry_px) - float(decision_entry_px)) * 100))
    except (TypeError, ValueError):
        slippage_cents = ""

    entry_hhmm = entry_ts.split("T", 1)[1][:5] if "T" in entry_ts else ""
    attribution = rt.get("attribution", "engine")
    is_engine = attribution == "engine"
    is_broker_truth = source_label == PRIMARY_SOURCE_LABEL

    order_bits = []
    if rt.get("entry_activity_id"):
        order_bits.append(f"entry_act={str(rt['entry_activity_id']).split('::')[-1][:8]}")
    if rt.get("exit_activity_id"):
        order_bits.append(f"exit_act={str(rt['exit_activity_id']).split('::')[-1][:8]}")

    notes = (
        f"FLEET ARM {arm} ({arm_meta.get('cell', '?')}). "
        f"Entry reason: {entry_reason or 'n/a'}. "
        + (f"Exit stage={exit_stage} ({exit_reason}). " if exit_stage else "")
        + f"Source: {source_label}. "
        + (f"{', '.join(order_bits)}. " if order_bits else "")
        + "Backfilled by fleet_journal_bridge.py (Rule-8 fleet journaling debt, 2026-07-09)."
    )
    if not is_engine:
        notes = "UNEXPECTED attribution=manual on a fleet_rest arm -- verify. " + notes

    arch_json = json.dumps({
        "arm": arm, "cell": arm_meta.get("cell"), "quality": quality,
        "attribution": attribution, "source": source_label,
        "entry_order_id": entry_dec.get("_order_id"),
        "exit_order_id": exit_info.get("_order_id"),
    }, separators=(",", ":"))

    return {
        "date": date_et,
        "time_entry": entry_ts.split("T", 1)[1][:8] if "T" in entry_ts else "",
        "time_exit": exit_ts.split("T", 1)[1][:8] if "T" in exit_ts else "",
        "setup": setup_name,
        "contract": f"{parsed['root']} {parsed['expiry']} {_fmt_num(parsed['strike'])}{parsed['right']}",
        "dte": "0",
        "strike": _fmt_num(parsed["strike"]),
        "c_or_p": parsed["right"],
        "qty": _fmt_num(qty),
        "entry_px": _fmt_num(entry_px),
        "exit_px": _fmt_num(exit_px),
        "premium_paid": _fmt_num(premium_paid),
        "premium_received": _fmt_num(premium_received),
        "dollar_pnl": _fmt_num(pnl),
        "r_multiple": "N/A",
        "stop_px": _fmt_num(stop_px),
        "target_px": _fmt_num(target_px),
        "dollar_risk": _fmt_num(premium_paid),
        "pct_risk_of_acct": pct_risk,
        "account_equity_pre": _fmt_num(equity_pre) if equity_pre is not None else "",
        "followed_rules": "N/A",
        "setup_quality": quality or "",
        "fill_quality": "real_fill" if is_broker_truth else "decisions_reconstruction (approximate)",
        "gamma_recommended": "Y" if is_engine else "N/A",
        "j_override": "N" if is_engine else "N/A",
        "hold_minutes": _hold_minutes(entry_ts, exit_ts),
        "trade_grade": "",
        "trade_grade_score": "",
        "delta_at_entry": "",
        "iv_at_entry": "",
        "iv_regime": "",
        "slippage_cents": slippage_cents,
        "exit_slippage_cents": "",
        "tod_bucket": _tod_bucket(entry_hhmm) if entry_hhmm else "",
        "bars_after_trigger": "",
        "entry_relative_to_bar": "",
        "hold_quality_pct": "",
        "cf_time_stop_pnl": "",
        "cf_high_water_pnl": "",
        "archetype_match_json": arch_json,
        "tape_assistance": "",
        "notes_short": notes,
        "account_id": arm,
    }


def _append_rows(trades_csv_path: Path, rows: list[dict]) -> None:
    trades_csv_path.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not trades_csv_path.exists() or trades_csv_path.stat().st_size == 0
    with trades_csv_path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if needs_header:
            w.writerow(SCHEMA)
        for r in rows:
            w.writerow([r.get(c, "") for c in SCHEMA])


# --------------------------------------------------------------------------- #
# orchestration (pure function -- all paths injectable for tests)
# --------------------------------------------------------------------------- #
def run_bridge(*, pnl_statement_path: Path = PNL_STATEMENT, fills_ledger_path: Path = FILLS_LEDGER,
               fleet_dir: Path = FLEET_DIR, accounts_json_path: Path = ACCOUNTS_JSON,
               trades_csv_path: Path = TRADES_CSV, watermark_path: Path = WATERMARK,
               date_filter: Optional[str] = None, dry_run: bool = False,
               arms: tuple[str, ...] = FLEET_REST_ARMS) -> dict:
    arm_meta_all = _load_accounts_meta(accounts_json_path)
    watermark = _load_watermark(watermark_path)
    processed: dict = watermark.get("processed", {})

    primary = _primary_round_trips(pnl_statement_path, arms, date_filter)
    activity_to_order = _build_activity_to_order(fills_ledger_path, arms) if primary else {}
    decision_idx = {arm: _build_decision_index(fleet_dir, arm) for arm in arms} if primary else {}

    candidates: list[tuple[dict, Optional[dict], Optional[dict], str]] = []
    covered: set[tuple[str, str]] = set()
    for rt in primary:
        covered.add((rt["arm"], rt["date_et"]))
        by_entry, by_exit = decision_idx.get(rt["arm"], ({}, {}))
        eoid = activity_to_order.get(rt.get("entry_activity_id"))
        xoid = activity_to_order.get(rt.get("exit_activity_id"))
        entry_dec = by_entry.get(eoid) if eoid else None
        exit_info = by_exit.get(xoid) if xoid else None
        candidates.append((rt, entry_dec, exit_info, PRIMARY_SOURCE_LABEL))

    # Fallback only fills (arm, date) gaps the primary source had nothing for --
    # it never shadows or duplicates a real broker-truth round trip.
    for rt in _fallback_round_trips(fleet_dir, arms, date_filter):
        if (rt["arm"], rt["date_et"]) in covered:
            continue
        candidates.append((rt, rt.get("_entry_dec"), rt.get("_exit_info"), FALLBACK_SOURCE_LABEL))

    new_rows: list[dict] = []
    per_arm: Counter = Counter()
    dates_seen: set[str] = set()
    skipped_existing = 0
    skipped_unparsed = 0
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    for rt, entry_dec, exit_info, label in candidates:
        key = _rt_key(rt)
        if key in processed:
            skipped_existing += 1
            continue
        arm_meta = arm_meta_all.get(rt["arm"], {})
        row = build_row(rt, entry_dec, exit_info, arm_meta, label)
        if row is None:
            skipped_unparsed += 1
            continue
        new_rows.append(row)
        per_arm[rt["arm"]] += 1
        dates_seen.add(rt["date_et"])
        processed[key] = {"date_et": rt["date_et"], "written_at_utc": now_iso, "source": label}

    if new_rows and not dry_run:
        _append_rows(trades_csv_path, new_rows)
        watermark["processed"] = processed
        watermark["updated_at_utc"] = now_iso
        _save_watermark(watermark_path, watermark)

    return {
        "n_written": len(new_rows), "per_arm": dict(per_arm),
        "dates": sorted(dates_seen), "skipped_existing": skipped_existing,
        "skipped_unparsed": skipped_unparsed, "rows": new_rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Bridge fleet_rest (safe-1/safe-3/risky-1/risky-3) broker-truth "
                     "fills into journal/trades.csv (Rule 8).")
    ap.add_argument("--date", default=None, help="restrict to one ET date YYYY-MM-DD "
                     "(default: all not-yet-journaled history in pnl-statement.json)")
    ap.add_argument("--dry-run", action="store_true", help="compute + report, write nothing")
    args = ap.parse_args()

    summary = run_bridge(date_filter=args.date, dry_run=args.dry_run)
    tag = "(dry-run) " if args.dry_run else ""
    print(f"[fleet_journal_bridge] {tag}{summary['n_written']} new row(s) written, "
          f"{summary['skipped_existing']} already journaled, "
          f"{summary['skipped_unparsed']} skipped (unparseable symbol).")
    if summary["dates"]:
        print(f"  span: {summary['dates'][0]} .. {summary['dates'][-1]} "
              f"({len(summary['dates'])} distinct day(s))")
    for arm, n in sorted(summary["per_arm"].items()):
        print(f"  {arm}: {n} row(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
