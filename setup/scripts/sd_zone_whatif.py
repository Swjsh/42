"""sd_zone_whatif.py -- headless, $0 SD-ZONE WHAT-IF shadow lane (GOAL-SD-LIQUIDITY-ZONES-
2026-09-11 item f, built 2026-09-14).

WHY THIS EXISTS: `backtest/tools/trigger_anchor_class_read.py --sd-zone` only ever labels
REAL engine fills in_zone/out_of_zone -- on a day the engine took zero SPY trades it produces
zero evidence. 2026-09-14: SPY bounced clean off the 757.88-758.58 demand zone at 11:06 and
ran to 760.80; the engine took 0 fills; that reader has nothing to say about it. This script
PLAYS the zone itself -- zone -> wait for the return -> confirmation -> hypothetical entry ->
walk the REAL production exit-stack decision core -- across a pre-registered grid of
confirmation rules, exit shapes, strikes and arm sizings, so the 2026-10-30 promotion decision
has evidence in hand even on days the live gate never fired. Rule set frozen verbatim in
`analysis/recommendations/prereg-sd-zone-anchor-promotion-2026-09-12.md` section 9.

Pure simulation logic lives in `backtest/lib/sd_zone_whatif.py` (touch/confirmation
detection, strike math, sizing, the exit walk) -- READ THAT MODULE'S DOCSTRING for the 4
disclosed simplifications (ribbon-flip inert, arm $ linearly scaled from one canonical walk,
no re-entry variant, sizing formula is Rule-6 plain English not a risk_gate.py port) before
trusting a number from this lane. This file is I/O + orchestration ONLY: never imports
heartbeat_core / build_shared_signal / fleet_broker / exit_actuator / any order-placing
module, and never writes key-levels.json / params*.json / automation/state/fleet/* (guard #1,
backtest/tests/test_sd_zone_whatif.py).

Usage:
    python setup/scripts/sd_zone_whatif.py                       # today (et_clock)
    python setup/scripts/sd_zone_whatif.py --day 2026-09-14
    python setup/scripts/sd_zone_whatif.py --since 2026-09-12 --until 2026-09-14
    python setup/scripts/sd_zone_whatif.py --day 2026-09-14 --dry-run
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, matches every other pythonw-launched producer)
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "sd-zone-whatif.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "sd-zone-whatif.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import argparse
import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path
from typing import Optional

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "setup" / "scripts", REPO / "backtest" / "lib",
           REPO / "backtest" / "tools", REPO / "crypto" / "lib"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from et_clock import et_now  # noqa: E402
import status_known_broken  # noqa: E402
from option_pricing_real import option_symbol  # noqa: E402
from _option_bars_1min_cache import fetch_1min_cached  # noqa: E402
import sd_zone_whatif_sim as core  # noqa: E402  -- backtest/lib/sd_zone_whatif_sim.py (named
# _sim, not sd_zone_whatif, to avoid a basename collision with THIS file)

LEDGER_OUT = REPO / "analysis" / "sd-zone-whatif" / "ledger.jsonl"
SUMMARY_JSON = REPO / "analysis" / "sd-zone-whatif" / "summary.json"
SUMMARY_MD = REPO / "analysis" / "sd-zone-whatif" / "SUMMARY.md"
FORWARD_CLOCK_FILE = REPO / "automation" / "state" / "sd-zone-forward-clock.json"
INTRADAY_ARCHIVE_DIR = REPO / "journal" / "sd-zones-archive" / "intraday"
EOD_ARCHIVE_DIR = REPO / "journal" / "sd-zones-archive"
ACCOUNTS_JSON = REPO / "automation" / "state" / "fleet" / "accounts.json"
STATUS_MARKER = "SD-ZONE-WHATIF:"

RETENTION_DAYS = 120


# --------------------------------------------------------------------------- data loading

def _mcp_creds() -> tuple[str, str]:
    m = json.loads((REPO / ".mcp.json").read_text(encoding="utf-8"))
    env = m["mcpServers"]["alpaca"]["env"]
    return env["ALPACA_API_KEY"], env["ALPACA_SECRET_KEY"]


def fetch_spy_day_bars(day: str, timeframe: str) -> list[dict]:
    """SPY bars for one ET calendar day, direct Alpaca REST (same un-blockable path as
    refresh_levels_intraday.py's `_fetch_bars_rest` -- read-only reuse of the credential
    convention, no import, since that function is day-window/timeframe-fixed and this
    needs a single arbitrary day at either 1Min or 5Min). Returns bars sorted ascending as
    {"ts": tz-naive ET datetime (bar OPEN), "open","high","low","close","volume"}."""
    key, sec = _mcp_creds()
    start = f"{day}T09:30:00-04:00"
    end = f"{day}T16:10:00-04:00"
    url = (f"https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe={timeframe}"
           f"&start={start}&end={end}&limit=1000&feed=iex&adjustment=raw&sort=asc")
    req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = json.loads(r.read()).get("bars") or []
    out = []
    for b in raw:
        ts = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
        ts_et = ts.astimezone(dt.timezone(dt.timedelta(hours=-4))).replace(tzinfo=None)
        out.append({"ts": ts_et, "open": b["o"], "high": b["h"], "low": b["l"],
                     "close": b["c"], "volume": b.get("v", 0)})
    return sorted(out, key=lambda r: r["ts"])


def bars_5m_dataframe(bars_5m: list[dict]) -> pd.DataFrame:
    """The DataFrame shape `walk_exit_manager`/`structure_shift.py` need: a `timestamp_et`
    column (tz-naive), plus open/high/low/close."""
    df = pd.DataFrame(bars_5m)
    if df.empty:
        return pd.DataFrame(columns=["timestamp_et", "open", "high", "low", "close"])
    df = df.rename(columns={"ts": "timestamp_et"}).sort_values("timestamp_et").reset_index(drop=True)
    return df


def load_zone_snapshots(day: str) -> list[dict]:
    """Intraday snapshots first (no look-ahead source, sd_zones_producer.py deliverable A);
    falls back to the single EOD archive file (one-entry list -> zone_set_as_of tags every
    row that day `eod_snapshot_only`) when no intraday captures exist for the day."""
    day_dir = INTRADAY_ARCHIVE_DIR / day
    out: list[dict] = []
    if day_dir.is_dir():
        for f in sorted(day_dir.glob("*.json")):
            try:
                snap = json.loads(f.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                continue
            if snap.get("as_of"):
                out.append({"as_of": snap["as_of"], "zones": snap.get("zones") or []})
    if out:
        return sorted(out, key=lambda s: s["as_of"])
    eod_path = EOD_ARCHIVE_DIR / f"{day}.json"
    if eod_path.exists():
        try:
            snap = json.loads(eod_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return []
        if snap.get("as_of"):
            return [{"as_of": snap["as_of"], "zones": snap.get("zones") or []}]
    return []


def load_arm_equity() -> dict[str, float]:
    """Per-arm `starting_equity` from accounts.json (machine-readable source; CLAUDE.md's
    broker-verified live equity table may differ intraday -- this is the frozen figure the
    grid sizes against, disclosed not silently treated as live)."""
    out: dict[str, float] = {}
    try:
        data = json.loads(ACCOUNTS_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {a: 5000.0 for a in core.ARM_IDS}
    for arm in data.get("arms", []):
        if arm.get("id") in core.ARM_IDS:
            out[arm["id"]] = float(arm.get("starting_equity") or 5000.0)
    for a in core.ARM_IDS:
        out.setdefault(a, 5000.0)
    return out


def forward_clock_eligible() -> bool:
    try:
        clock = json.loads(FORWARD_CLOCK_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(clock.get("eligible_for_forward_read"))


# --------------------------------------------------------------------------- day simulation

def simulate_day(day: str, arm_equity: dict[str, float]) -> dict:
    """Returns {"rows": [...], "narrative": [...], "warnings": [...]}. Every failure inside
    a single cell is caught locally (fail-open per cell, never per day -- one bad option-bar
    fetch must not blank the whole day's evidence)."""
    trade_date = dt.date.fromisoformat(day)
    snapshots = load_zone_snapshots(day)
    warnings: list[str] = []
    if not snapshots:
        return {"rows": [], "narrative": [], "warnings": [f"no zone snapshots for {day}"]}

    bars_1m = fetch_spy_day_bars(day, "1Min")
    bars_5m = fetch_spy_day_bars(day, "5Min")
    if not bars_1m or not bars_5m:
        return {"rows": [], "narrative": [], "warnings": [f"no SPY bars for {day}"]}
    bars_5m_df = bars_5m_dataframe(bars_5m)

    def snapshot_lookup(ts: dt.datetime):
        return core.zone_set_as_of(snapshots, ts)

    touches = core.find_touch_events(bars_1m, snapshot_lookup)
    narrative: list[dict] = []
    rows: list[dict] = []
    # single-slot enforcement PER (confirmation, exit_variant, strike_label) cell, across
    # ALL zones touched this day, in chronological order (see module docstring / prereg S9).
    busy_until: dict[tuple, dt.datetime] = {}
    opt_cache: dict[str, Optional[pd.DataFrame]] = {}

    for touch in touches:
        zone = touch["zone"]
        side = "C" if zone["kind"] == "demand" else "P"
        zone_note = {"touch_ts_et": touch["touch_ts"].isoformat(), "zone": zone,
                     "lookahead_caveat": touch["lookahead_caveat"], "confirmations": {}}
        for confirmation in core.CONFIRMATIONS:
            confirmed_ts = core.run_confirmation(confirmation, bars_5m, bars_5m_df, zone, touch["touch_ts"])
            zone_note["confirmations"][confirmation] = (confirmed_ts.isoformat() if confirmed_ts else None)
            if confirmed_ts is None:
                continue
            entry_ts = core.entry_ts_after(bars_1m, confirmed_ts)
            if entry_ts is None:
                continue
            spot_row = next((b for b in bars_1m if b["ts"] == entry_ts), None)
            spot = spot_row["open"] if spot_row else None
            if spot is None:
                continue

            for strike_label in core.STRIKE_LABELS:
                strike = core.strike_for_label(spot, strike_label, side)
                contract = option_symbol(trade_date, strike, side)
                if contract not in opt_cache:
                    df, _src = fetch_1min_cached(contract, day)
                    opt_cache[contract] = df
                opt_df = opt_cache[contract]

                for exit_variant in core.EXIT_VARIANTS:
                    cell_key = (confirmation, exit_variant, strike_label)
                    row_base = {
                        "day": day, "touch_ts_et": touch["touch_ts"].isoformat(),
                        "zone": zone, "confirmation": confirmation,
                        "confirmed_ts_et": confirmed_ts.isoformat(),
                        "exit_variant": exit_variant, "strike_label": strike_label,
                        "strike": strike, "contract": contract, "side": side,
                        "lookahead_caveat": touch["lookahead_caveat"],
                        "reentry_variant": 0, "walker_resolution": "1min",
                        "frame": "wall-v1",
                    }
                    if cell_key in busy_until and entry_ts < busy_until[cell_key]:
                        row_base.update(unpriceable=False, skipped_reason="slot_busy",
                                         entry_ts_et=None, entry_premium=None)
                        rows.append(row_base)
                        continue
                    if opt_df is None or opt_df.empty:
                        row_base.update(unpriceable=True, skipped_reason="no_option_bars",
                                         entry_ts_et=None, entry_premium=None)
                        rows.append(row_base)
                        continue
                    entry_rows = opt_df[opt_df["timestamp_et"] >= entry_ts]
                    if entry_rows.empty:
                        row_base.update(unpriceable=True, skipped_reason="no_option_bar_after_entry",
                                         entry_ts_et=None, entry_premium=None)
                        rows.append(row_base)
                        continue
                    used_entry_ts = entry_rows.iloc[0]["timestamp_et"]
                    used_entry_ts = (used_entry_ts.to_pydatetime()
                                      if hasattr(used_entry_ts, "to_pydatetime") else used_entry_ts)
                    entry_premium = float(entry_rows.iloc[0]["open"])

                    try:
                        if exit_variant == "ribbon_ride":
                            result = core.walk_ribbon_ride(
                                contract=contract, side=side, entry_ts=used_entry_ts,
                                entry_premium=entry_premium, zone=zone, opt_df=opt_df,
                                five_min_spy_df=bars_5m_df)
                            zz_meta = None
                        else:
                            result, zz_meta = core.walk_zone_to_zone(
                                contract=contract, side=side, entry_ts=used_entry_ts,
                                entry_premium=entry_premium, zone=zone,
                                all_zones=snapshot_lookup(used_entry_ts)[0], bars_1m=bars_1m,
                                opt_df=opt_df, five_min_spy_df=bars_5m_df)
                    except Exception as exc:  # noqa: BLE001 -- one bad cell never blanks the day
                        row_base.update(unpriceable=True, skipped_reason=f"walk_error:{type(exc).__name__}:{exc}"[:200],
                                         entry_ts_et=used_entry_ts.isoformat(), entry_premium=entry_premium)
                        rows.append(row_base)
                        continue

                    pnl_per_contract = round(result.dollar_pnl / core.CANONICAL_QTY, 4)
                    arms = {}
                    for arm in core.ARM_IDS:
                        qty = core.size_qty(entry_premium, arm_equity.get(arm, 5000.0), arm)
                        arms[arm] = {"qty": qty, "pnl": round(pnl_per_contract * qty, 2)}
                    busy_until[cell_key] = result.exit_time_et or used_entry_ts

                    row_base.update(
                        unpriceable=False, skipped_reason=None,
                        entry_ts_et=used_entry_ts.isoformat(), entry_premium=entry_premium,
                        exit_ts_et=(result.exit_time_et.isoformat() if result.exit_time_et else None),
                        exit_reason=result.exit_reason, hold_minutes=result.hold_minutes,
                        pnl_per_contract=pnl_per_contract, dollar_pnl_canonical=result.dollar_pnl,
                        canonical_qty=core.CANONICAL_QTY, arms=arms,
                        zone_to_zone=zz_meta,
                        legs=[{"kind": leg.kind, "qty": leg.qty, "fill_price": leg.fill_price,
                               "reason": leg.reason, "stage": leg.stage, "ts_et": leg.ts_et.isoformat(),
                               "leg_pnl": leg.leg_pnl} for leg in result.legs],
                    )
                    rows.append(row_base)
        narrative.append(zone_note)

    if len(rows) > core.MAX_ROWS_WARN:
        warnings.append(f"{len(rows)} rows > {core.MAX_ROWS_WARN} -- keeping all (no truncation, OP-33)")
    return {"rows": rows, "narrative": narrative, "warnings": warnings}


# --------------------------------------------------------------------------- ledger + summary

def _load_ledger() -> list[dict]:
    if not LEDGER_OUT.exists():
        return []
    out = []
    for line in LEDGER_OUT.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def write_ledger(day: str, rows: list[dict], reference_day: str) -> int:
    """Idempotent per day (replaces `day`'s rows) + a 120-day retention prune anchored on
    `reference_day` (OP-22)."""
    existing = _load_ledger()
    cutoff = dt.date.fromisoformat(reference_day) - dt.timedelta(days=RETENTION_DAYS)
    kept = [r for r in existing if r.get("day") != day and dt.date.fromisoformat(r["day"]) >= cutoff]
    all_rows = kept + rows
    LEDGER_OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = LEDGER_OUT.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for r in all_rows:
            fh.write(json.dumps(r, default=str) + "\n")
    tmp.replace(LEDGER_OUT)
    return len(all_rows)


def _priced(rows: list[dict]) -> list[dict]:
    return [r for r in rows if not r.get("unpriceable") and r.get("skipped_reason") is None
            and r.get("pnl_per_contract") is not None]


def build_summary(all_rows: list[dict], today_result: dict, day: str) -> dict:
    priced = [r for r in all_rows if r.get("lookahead_caveat") != "eod_snapshot_only"]
    priced = _priced(priced)

    def variant_stats(rows: list[dict]) -> dict:
        n = len(rows)
        wins = sum(1 for r in rows if r["pnl_per_contract"] > 0)
        total = round(sum(r["pnl_per_contract"] for r in rows), 4)
        return {"n": n, "wr": (round(wins / n, 3) if n else None), "total_per_contract": total}

    by_confirmation = {c: variant_stats([r for r in priced if r["confirmation"] == c])
                        for c in core.CONFIRMATIONS}
    by_exit = {e: variant_stats([r for r in priced if r["exit_variant"] == e])
               for e in core.EXIT_VARIANTS}
    by_strike = {s: variant_stats([r for r in priced if r["strike_label"] == s])
                 for s in core.STRIKE_LABELS}
    primary = [r for r in priced if r["confirmation"] == core.PRIMARY_CONFIRMATION
               and r["exit_variant"] == core.PRIMARY_EXIT and r["strike_label"] == core.PRIMARY_STRIKE]
    primary_arms = {}
    for arm in core.ARM_IDS:
        n = len(primary)
        total = round(sum(r["arms"][arm]["pnl"] for r in primary), 2) if n else 0.0
        primary_arms[arm] = {"n": n, "total_pnl": total}

    last10_days = sorted({r["day"] for r in priced})[-10:]
    last10 = {d: variant_stats([r for r in priced if r["day"] == d]) for d in last10_days}

    eligible = forward_clock_eligible()
    return {
        "generated_at_et": et_now().isoformat(),
        "label": ("CURIOSITY -- forward clock not eligible" if not eligible
                   else "FORWARD-READ ELIGIBLE (clock cleared)"),
        "primary_variant": {"confirmation": core.PRIMARY_CONFIRMATION, "exit_variant": core.PRIMARY_EXIT,
                             "strike_label": core.PRIMARY_STRIKE, "arms": primary_arms,
                             "n_legs": len(primary),
                             "total_per_contract": round(sum(r["pnl_per_contract"] for r in primary), 4) if primary else 0.0},
        "by_confirmation": by_confirmation, "by_exit_variant": by_exit, "by_strike": by_strike,
        "last_10_sessions": last10,
        "n_ledger_rows_total": len(all_rows), "n_priced_rows_total": len(priced),
        "today": {"day": day, "warnings": today_result["warnings"],
                   "n_touches": len(today_result["narrative"]),
                   "narrative": today_result["narrative"]},
    }


def render_markdown(summary: dict) -> str:
    lines = [f"# SD-ZONE WHAT-IF -- {summary['label']}", "",
             f"Generated {summary['generated_at_et']}", "",
             "## Primary variant (structure_shift x ribbon_ride x ATM)",
             f"n_legs={summary['primary_variant']['n_legs']} "
             f"total_per_contract=${summary['primary_variant']['total_per_contract']}", ""]
    lines.append("| arm | n | total $ |")
    lines.append("|---|---|---|")
    for arm, v in summary["primary_variant"]["arms"].items():
        lines.append(f"| {arm} | {v['n']} | {v['total_pnl']:+.2f} |")
    lines += ["", "## By confirmation", "| confirmation | n | WR | total/contract |", "|---|---|---|---|"]
    for k, v in summary["by_confirmation"].items():
        lines.append(f"| {k} | {v['n']} | {v['wr']} | {v['total_per_contract']} |")
    lines += ["", "## By exit variant", "| exit | n | WR | total/contract |", "|---|---|---|---|"]
    for k, v in summary["by_exit_variant"].items():
        lines.append(f"| {k} | {v['n']} | {v['wr']} | {v['total_per_contract']} |")
    lines += ["", "## By strike", "| strike | n | WR | total/contract |", "|---|---|---|---|"]
    for k, v in summary["by_strike"].items():
        lines.append(f"| {k} | {v['n']} | {v['wr']} | {v['total_per_contract']} |")
    lines += ["", f"## Today ({summary['today']['day']})", ""]
    if summary["today"]["warnings"]:
        for w in summary["today"]["warnings"]:
            lines.append(f"- WARNING: {w}")
    if not summary["today"]["narrative"]:
        lines.append("- no zone touches recorded")
    for note in summary["today"]["narrative"]:
        z = note["zone"]
        lines.append(f"- {note['touch_ts_et']} touched {z['kind']} zone {z['low']:.2f}-{z['high']:.2f} "
                     f"(caveat={note['lookahead_caveat'] or 'none'})")
        for conf, ts in note["confirmations"].items():
            lines.append(f"    - {conf}: {'fired ' + ts if ts else 'never fired'}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- CLI

def run_one_day(day: str, arm_equity: dict[str, float], dry_run: bool) -> dict:
    result = simulate_day(day, arm_equity)
    if dry_run:
        print(json.dumps({"day": day, "n_rows": len(result["rows"]),
                          "warnings": result["warnings"]}, indent=2, default=str))
        return result
    n_total = write_ledger(day, result["rows"], reference_day=day)
    all_rows = _load_ledger()
    summary = build_summary(all_rows, result, day)
    SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON.write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    SUMMARY_MD.write_text(render_markdown(summary), encoding="utf-8")
    print(f"[sd-zone-whatif] {day}: {len(result['rows'])} rows this day, {n_total} in ledger. "
          f"touches={len(result['narrative'])} warnings={result['warnings']}")
    status_known_broken.upsert(STATUS_MARKER, None)
    return result


def _date_range(since: str, until: str) -> list[str]:
    d0, d1 = dt.date.fromisoformat(since), dt.date.fromisoformat(until)
    out = []
    d = d0
    while d <= d1:
        out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--day", default=None)
    ap.add_argument("--since", default=None)
    ap.add_argument("--until", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.since or args.until:
        if not (args.since and args.until):
            print("--since and --until must be given together", file=sys.stderr)
            return 2
        days = _date_range(args.since, args.until)
    else:
        days = [args.day or et_now().strftime("%Y-%m-%d")]

    arm_equity = load_arm_equity()
    failures = []
    for day in days:
        try:
            run_one_day(day, arm_equity, args.dry_run)
        except Exception as exc:  # noqa: BLE001 -- one bad day never blocks the rest, but is loud
            msg = f"{type(exc).__name__}: {exc}"
            print(f"[sd-zone-whatif] ERROR {day}: {msg}", file=sys.stderr)
            failures.append((day, msg))
    if failures:
        stamp = et_now().isoformat()
        lines = "; ".join(f"{d}: {m}" for d, m in failures)
        status_known_broken.upsert(
            STATUS_MARKER, f"- [{stamp} ET] {STATUS_MARKER} {lines}"[:1000])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
