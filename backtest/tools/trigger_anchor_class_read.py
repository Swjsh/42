"""Trigger-anchor level-class read (ratifying instrument for
analysis/recommendations/prereg-trigger-anchor-level-class-2026-09-11.md).

Joins every fill in journal/trades.csv (all arms) to the core ENTER tick fired within
+-2 minutes of its entry time in automation/state/core-decisions.jsonl, takes that tick's
conviction.matched_level_label as the trigger anchor, and prints signals / legs / P&L per
anchor CLASS. One table. No side effects. Run on demand:

    backtest/.venv/Scripts/python.exe backtest/tools/trigger_anchor_class_read.py \
        --since 2026-09-14 --until 2026-09-28

Classes: SWING (INTRADAY_SWING_*), STRUCT (PRIOR_DAY_* / INTRADAY_PMH|PML|RTH_*),
SHELF (SHELF_*), MEMORY (MEMORY_*), NONE (no named level; ribbon-only rejection).
A "signal" is one (date, 3-minute entry slot) across all arms; legs are CSV rows.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "automation" / "state" / "core-decisions.jsonl"
TRADES = REPO / "journal" / "trades.csv"
SD_ZONE_ARCHIVE = REPO / "journal" / "sd-zones-archive"


def _cls(label: str | None) -> str:
    if not label:
        return "NONE"
    if label.startswith("INTRADAY_SWING"):
        return "SWING"
    if label.startswith("PRIOR_DAY") or label.startswith("INTRADAY_"):
        return "STRUCT"
    if label.startswith("SHELF"):
        return "SHELF"
    if label.startswith("MEMORY"):
        return "MEMORY"
    return "OTHER"


def _enter_ticks(since: str, until: str) -> dict[tuple[str, str], str | None]:
    out: dict[tuple[str, str], str | None] = {}
    with LEDGER.open(encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            head = line[:60]
            if '"ts_et": "' not in head and '"ts_et":"' not in head:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = str(row.get("ts_et", ""))
            day = ts[:10]
            if day < since or day > until or not str(row.get("verdict", "")).startswith("ENTER"):
                continue
            conv = row.get("conviction") or {}
            label = conv.get("matched_level_label") if isinstance(conv, dict) else None
            out.setdefault((day, ts[11:16]), label)
    return out


def read(since: str, until: str) -> dict:
    ticks = _enter_ticks(since, until)
    per_class = collections.defaultdict(lambda: {"legs": 0, "wins": 0, "pnl": 0.0,
                                                  "signals": collections.defaultdict(float)})
    unmatched = 0
    with TRADES.open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            day = row["date"]
            if day < since or day > until:
                continue
            try:
                t0 = datetime.strptime(row["time_entry"][:5], "%H:%M")
                pnl = float(row["dollar_pnl"] or 0)
            except ValueError:
                continue
            hit = None
            for off in (0, -1, 1, 2, -2):
                key = (day, (t0 + timedelta(minutes=off)).strftime("%H:%M"))
                if key in ticks:
                    hit = ticks[key]
                    break
            if hit is None and not any((day, (t0 + timedelta(minutes=o)).strftime("%H:%M")) in ticks
                                       for o in (0, -1, 1, 2, -2)):
                unmatched += 1
                continue
            bucket = per_class[_cls(hit)]
            bucket["legs"] += 1
            bucket["wins"] += pnl > 0
            bucket["pnl"] += pnl
            slot = f"{day} {(t0.hour * 60 + t0.minute) // 3}"
            bucket["signals"][slot] += pnl
    return {"since": since, "until": until, "unmatched_legs": unmatched,
            "classes": {k: {"signals": len(v["signals"]), "legs": v["legs"], "wins": v["wins"],
                            "pnl": round(v["pnl"], 2),
                            "signal_pnls": sorted(round(x) for x in v["signals"].values())}
                        for k, v in per_class.items()}}


def _load_zone_archive(day: str) -> list[dict] | None:
    """None = no archive exists yet for `day` (before sd_zones_producer.py started
    accruing, or a non-trading day). Distinct from an empty list (archive existed, zero
    zones survived that day's read) -- callers must never conflate the two."""
    path = SD_ZONE_ARCHIVE / f"{day}.json"
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    zones = raw.get("zones") if isinstance(raw, dict) else None
    return zones if isinstance(zones, list) else None


def _enter_ticks_with_spot(since: str, until: str) -> dict[tuple[str, str], float | None]:
    out: dict[tuple[str, str], float | None] = {}
    with LEDGER.open(encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            head = line[:60]
            if '"ts_et": "' not in head and '"ts_et":"' not in head:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = str(row.get("ts_et", ""))
            day = ts[:10]
            if day < since or day > until or not str(row.get("verdict", "")).startswith("ENTER"):
                continue
            out.setdefault((day, ts[11:16]), row.get("spy"))
    return out


def _in_zone(price: float, zones: list[dict]) -> dict | None:
    for z in zones:
        try:
            lo, hi = float(z["low"]), float(z["high"])
        except (KeyError, TypeError, ValueError):
            continue
        if lo <= price <= hi:
            return z
    return None


def sd_zone_read(since: str, until: str) -> dict:
    """Overlay read (GOAL-SD-LIQUIDITY-ZONES-2026-09-11 item d /
    prereg-sd-zone-anchor-promotion-2026-09-12.md): independent of the engine's own
    `matched_level_label` (the engine never anchors on a zone yet -- sd-zones.json is
    SHADOW-only), was the ENTRY's SPY spot actually sitting inside a Smart-Money-Concepts
    order-block zone that day? Reads `journal/sd-zones-archive/{day}.json`
    (sd_zones_producer.py's daily snapshot). Days before the archive existed are reported
    as `no_archive_days`, never silently dropped or silently counted as `out_of_zone`."""
    ticks = _enter_ticks_with_spot(since, until)
    buckets = {
        "in_zone": {"legs": 0, "wins": 0, "pnl": 0.0, "signals": collections.defaultdict(float)},
        "out_of_zone": {"legs": 0, "wins": 0, "pnl": 0.0, "signals": collections.defaultdict(float)},
    }
    no_archive_days: set[str] = set()
    unmatched = 0
    zone_cache: dict[str, list[dict] | None] = {}
    with TRADES.open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            day = row["date"]
            if day < since or day > until:
                continue
            try:
                t0 = datetime.strptime(row["time_entry"][:5], "%H:%M")
                pnl = float(row["dollar_pnl"] or 0)
            except ValueError:
                continue
            spy = None
            for off in (0, -1, 1, 2, -2):
                key = (day, (t0 + timedelta(minutes=off)).strftime("%H:%M"))
                if key in ticks:
                    spy = ticks[key]
                    break
            if spy is None:
                unmatched += 1
                continue
            if day not in zone_cache:
                zone_cache[day] = _load_zone_archive(day)
            zones = zone_cache[day]
            if zones is None:
                no_archive_days.add(day)
                continue
            hit = _in_zone(float(spy), zones)
            bucket = buckets["in_zone"] if hit else buckets["out_of_zone"]
            bucket["legs"] += 1
            bucket["wins"] += pnl > 0
            bucket["pnl"] += pnl
            slot = f"{day} {(t0.hour * 60 + t0.minute) // 3}"
            bucket["signals"][slot] += pnl
    return {
        "since": since, "until": until, "unmatched_legs": unmatched,
        "no_archive_days": sorted(no_archive_days),
        "buckets": {k: {"signals": len(v["signals"]), "legs": v["legs"], "wins": v["wins"],
                        "pnl": round(v["pnl"], 2),
                        "signal_pnls": sorted(round(x) for x in v["signals"].values())}
                    for k, v in buckets.items()},
    }


TICKERS_ARMS = ("tickers-1", "tickers-2", "tickers-3")
TICKERS_STATE_DIR = REPO / "automation" / "state" / "tickers"
TICKERS_JOURNAL_DIR = REPO / "journal"
# Trigger-name priority when a fill's WOULD_PLACE row carries more than one trigger for the
# acting side -- first match wins, mirroring the SPY engine's single anchor-per-signal shape.
_TICKERS_PROXY_ORDER = ("level_reclaim", "level_rejection", "trendline_rejection",
                        "ribbon_flip", "confluence")


def classify_tickers_row(row: dict) -> str:
    """PROXY class for one tickers-lane WOULD_PLACE/ledger row (GOAL-EARN-YOUR-KEEP item 3).

    2026-09-12 schema check (quoted in the goal's builder report): a tickers ENTER row has
    NO `conviction.matched_level_label` (or any `level`/`trigger_level_label`) field -- the
    SPY engine's named anchor-class taxonomy (INTRADAY_SWING_ / PRIOR_DAY_ / SHELF_ / MEMORY_)
    does not exist on this lane. `level-states/*.json` carries only a numeric price ladder
    with a generic `role` (`broken_to_support` / `broken_to_resistance` / null) -- not a class.
    The best available proxy is the row's own `bull_triggers`/`bear_triggers` list (whichever
    side the `action` fired on), bucketed by trigger NAME. This is a PROXY, not the SPY
    class read -- callers must label it as such rather than implying parity.
    """
    action = str(row.get("action") or "")
    side_key = "bull_triggers" if "BULL" in action else "bear_triggers" if "BEAR" in action else None
    triggers = set((row.get(side_key) or []) if side_key else
                   (row.get("bull_triggers") or []) + (row.get("bear_triggers") or []))
    for name in _TICKERS_PROXY_ORDER:
        if name in triggers:
            return name.upper()
    return "NONE"


def _tickers_ledger_rows(arm: str, state_dir: Path = TICKERS_STATE_DIR) -> list[dict]:
    path = state_dir / arm / "ledger.jsonl"
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open(encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def read_tickers_lane(since: str, until: str, *, state_dir: Path = TICKERS_STATE_DIR,
                       journal_dir: Path = TICKERS_JOURNAL_DIR, arms=TICKERS_ARMS) -> dict:
    """Anchor-class (PROXY) read over the non-SPY tickers lane's fills, `since`..`until`.

    Joins each arm's ENTRY_FILLED ledger row (has `contract`+`trade_id`) to the most recent
    prior WOULD_PLACE row for the same contract (carries the triggers -> classify_tickers_row),
    then to that trade_id's EXIT row in journal/trades-tickers-<arm>.csv for `pnl_dollars`.
    An EXIT not yet written (open/naked leg) is counted in `open_legs`, never silently
    dropped and never counted as a $0 leg.
    """
    per_class: dict[str, dict] = collections.defaultdict(
        lambda: {"legs": 0, "wins": 0, "pnl": 0.0, "signals": collections.defaultdict(float)})
    open_legs = 0
    unmatched = 0
    for arm in arms:
        rows = _tickers_ledger_rows(arm, state_dir)
        would_place_by_contract: dict[str, dict] = {}
        exits_by_trade_id: dict[str, dict] = {}
        journal_path = journal_dir / f"trades-tickers-{arm}.csv"
        if journal_path.exists():
            with journal_path.open(encoding="utf-8-sig") as fh:
                for jrow in csv.DictReader(fh):
                    if jrow.get("row_type") == "EXIT":
                        exits_by_trade_id[jrow["trade_id"]] = jrow

        for row in rows:
            day = str(row.get("ts_et", ""))[:10]
            if row.get("decision") == "WOULD_PLACE" and row.get("contract"):
                if since <= day <= until:
                    would_place_by_contract[row["contract"]] = row
                continue
            if row.get("decision") != "ENTRY_FILLED":
                continue
            if not (since <= day <= until):
                continue
            contract = row.get("contract")
            trade_id = row.get("trade_id")
            wp = would_place_by_contract.get(contract)
            cls = classify_tickers_row(wp) if wp else "NONE"
            jexit = exits_by_trade_id.get(trade_id)
            if jexit is None:
                open_legs += 1
                continue
            try:
                pnl = float(jexit.get("pnl_dollars") or 0)
            except ValueError:
                unmatched += 1
                continue
            bucket = per_class[cls]
            bucket["legs"] += 1
            bucket["wins"] += pnl > 0
            bucket["pnl"] += pnl
            bucket["signals"][f"{arm}:{trade_id}"] += pnl

    return {"since": since, "until": until, "unmatched_legs": unmatched, "open_legs": open_legs,
            "classes": {k: {"signals": len(v["signals"]), "legs": v["legs"], "wins": v["wins"],
                            "pnl": round(v["pnl"], 2),
                            "signal_pnls": sorted(round(x) for x in v["signals"].values())}
                        for k, v in per_class.items()}}


def _print_class_table(res: dict) -> None:
    print(f"{'class':16s} {'signals':>7s} {'legs':>5s} {'WR%':>5s} {'P&L':>9s}  signal P&Ls (sorted)")
    for name, c in sorted(res["classes"].items(), key=lambda kv: kv[1]["pnl"]):
        wr = (c["wins"] / c["legs"] * 100) if c["legs"] else 0
        print(f"{name:16s} {c['signals']:7d} {c['legs']:5d} {wr:5.0f} {c['pnl']:+9.0f}  {c['signal_pnls']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True)
    ap.add_argument("--until", default="2099-12-31")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--sd-zone", action="store_true",
                     help="overlay read: was the entry price inside a sd-zones-archive zone (item d)")
    ap.add_argument("--lane", choices=("spy", "tickers"), default="spy",
                     help="tickers: PROXY anchor-class read over the non-SPY lane (item 3, "
                          "GOAL-EARN-YOUR-KEEP-2026-09-12) -- no matched_level_label exists "
                          "on that lane, see classify_tickers_row's docstring")
    args = ap.parse_args()

    if args.lane == "tickers":
        res = read_tickers_lane(args.since, args.until)
        if args.json:
            print(json.dumps(res, indent=1))
            return 0
        print(f"tickers-lane PROXY anchor-class read {res['since']}..{res['until']}  "
              f"(unmatched legs: {res['unmatched_legs']}, open/unreconciled legs: {res['open_legs']})")
        _print_class_table(res)
        return 0

    if args.sd_zone:
        res = sd_zone_read(args.since, args.until)
        if args.json:
            print(json.dumps(res, indent=1))
            return 0
        print(f"sd-zone overlay read {res['since']}..{res['until']}  "
              f"(unmatched legs: {res['unmatched_legs']}, no-archive days: {len(res['no_archive_days'])})")
        print(f"{'bucket':12s} {'signals':>7s} {'legs':>5s} {'WR%':>5s} {'P&L':>9s}  signal P&Ls (sorted)")
        for name, c in sorted(res["buckets"].items(), key=lambda kv: kv[1]["pnl"]):
            wr = (c["wins"] / c["legs"] * 100) if c["legs"] else 0
            print(f"{name:12s} {c['signals']:7d} {c['legs']:5d} {wr:5.0f} {c['pnl']:+9.0f}  {c['signal_pnls']}")
        if res["no_archive_days"]:
            print(f"no_archive_days: {res['no_archive_days']}")
        return 0

    res = read(args.since, args.until)
    if args.json:
        print(json.dumps(res, indent=1))
        return 0
    print(f"trigger-anchor class read {res['since']}..{res['until']}  (unmatched legs: {res['unmatched_legs']})")
    print(f"{'class':8s} {'signals':>7s} {'legs':>5s} {'WR%':>5s} {'P&L':>9s}  signal P&Ls (sorted)")
    for name, c in sorted(res["classes"].items(), key=lambda kv: kv[1]["pnl"]):
        wr = (c["wins"] / c["legs"] * 100) if c["legs"] else 0
        print(f"{name:8s} {c['signals']:7d} {c['legs']:5d} {wr:5.0f} {c['pnl']:+9.0f}  {c['signal_pnls']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
