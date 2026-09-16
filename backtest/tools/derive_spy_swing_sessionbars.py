"""Derive DAILY SessionBar files for SPY multi-day option contracts from the ALREADY-FETCHED
real 3DTE/4DTE intraday OPRA cache — the DATA step of GOAL-GAMMA-STATION item (14) "SPY swing
lane by evidence" (order fixed: data -> prereg -> null -> shadow fork; never live).

WHY DERIVE INSTEAD OF RE-FETCH ($0, no new network calls)
-----------------------------------------------------------
`backtest/data/options_3dte/` and `options_4dte/` already hold REAL 5-minute OPRA bars for
2,961 SPY contracts (chef 2026-07-07 offline backfill, `_dte34_multiday_backfill.py`), each
file spanning every session from entry day T through expiry — exactly the multi-day path
`multiday_walk.walk()` needs. `multiday_walk.load_contract_bars` expects ONE ROW PER SESSION
(open/high/low/close/volume/is_expiry_day), not 5-minute bars, so this tool aggregates.

HONEST COVERAGE NOTE (read before trusting any downstream walk)
------------------------------------------------------------------
This derives DTE=3 and DTE=4 contracts ONLY — the two buckets that were actually fetched as
TRUE multi-day (bars for every session T..expiry). The existing `options_1dte`/`options_2dte`
caches store bars for the ENTRY DAY T ONLY (per `_dte34_multiday_backfill.py`'s own docstring)
and therefore CANNOT support a true multi-day walk at 1-2 DTE without a fresh fetch. DTE 5-10
have never been fetched at all. The goal's "SPY 1-10 DTE" ask is therefore PARTIALLY met by
this tool (3-4 DTE, real data, $0) — extending to 1-2 DTE and 5-10 DTE is a follow-up fetch
(the same shape as `_dte34_multiday_backfill.py`, extended to more DTE buckets), not this tool.

AGGREGATION RULES
------------------
- open  = first intraday bar's open for that session (bars are timestamp-sorted on read)
- high  = max(intraday highs)
- low   = min(intraday lows)
- close = last intraday bar's close for that session
- volume/trade_count = summed
- vwap  = volume-weighted average of the intraday vwaps (falls back to close if volume==0)
- is_expiry_day = session date == the contract's expiry (parsed from the OCC symbol)
- bar_utc = the last intraday bar's own timestamp for that session (best-available anchor;
  there is no true "daily bar" UTC stamp in the source — this is a derived proxy, not a raw
  provider field, and is documented as such here rather than presented as raw truth)

Output: backtest/data/weekly-options/SPY/{OCC}.csv, same CSV_COLUMNS as
`fetch_weekly_option_data.py` so `multiday_walk.load_contract_bars(contract, "SPY")` reads it
identically regardless of which tool produced it.

Pure stdlib. $0. Read-only against an existing cache; places no orders; touches nothing on
FROZEN_TRADING_PATH.

Run:
  backtest/.venv/Scripts/python.exe backtest/tools/derive_spy_swing_sessionbars.py
  backtest/.venv/Scripts/python.exe backtest/tools/derive_spy_swing_sessionbars.py --dry-run
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIRS = {
    3: REPO_ROOT / "backtest" / "data" / "options_3dte",
    4: REPO_ROOT / "backtest" / "data" / "options_4dte",
}
OUT_ROOT = REPO_ROOT / "backtest" / "data" / "weekly-options" / "SPY"
MANIFEST = REPO_ROOT / "backtest" / "data" / "weekly-options" / "SPY" / "_derive-manifest.json"

OCC_RE = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")

CSV_COLUMNS = [
    "contract", "root", "expiry", "strike", "right",
    "bar_utc", "bar_date_et", "is_expiry_day",
    "open", "high", "low", "close", "volume", "trade_count", "vwap",
]


class DeriveError(RuntimeError):
    """Raised so a malformed source file fails loud rather than writing a plausible cache."""


def parse_occ(stem: str) -> tuple[str, dt.date, str, float]:
    m = OCC_RE.match(stem)
    if not m:
        raise DeriveError(f"cannot parse OCC symbol from filename stem {stem!r}")
    root, ds, side, strike8 = m.groups()
    expiry = dt.datetime.strptime(ds, "%y%m%d").date()
    strike = int(strike8) / 1000.0
    return root, expiry, side, strike


def load_intraday(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise DeriveError(f"{path} exists but has zero intraday rows")
    for r in rows:
        r["_ts"] = dt.datetime.fromisoformat(r["timestamp_et"])
    rows.sort(key=lambda r: r["_ts"])
    return rows


def aggregate_sessions(rows: list[dict], expiry: dt.date) -> list[dict]:
    by_date: dict[dt.date, list[dict]] = {}
    for r in rows:
        by_date.setdefault(r["_ts"].date(), []).append(r)

    out = []
    for d in sorted(by_date):
        day_rows = by_date[d]
        vol = sum(float(r["volume"] or 0) for r in day_rows)
        vwap_num = sum(float(r["vwap"] or r["close"]) * float(r["volume"] or 0) for r in day_rows)
        vwap = (vwap_num / vol) if vol > 0 else float(day_rows[-1]["close"])
        out.append({
            "bar_utc": day_rows[-1]["timestamp_et"],
            "bar_date_et": d.isoformat(),
            "is_expiry_day": int(d == expiry),
            "open": float(day_rows[0]["open"]),
            "high": max(float(r["high"]) for r in day_rows),
            "low": min(float(r["low"]) for r in day_rows),
            "close": float(day_rows[-1]["close"]),
            "volume": vol,
            "trade_count": sum(float(r["trade_count"] or 0) for r in day_rows),
            "vwap": vwap,
        })
    return out


def write_session_csv(contract: str, root: str, expiry: dt.date, strike: float, side: str,
                       sessions: list[dict]) -> Path:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    path = OUT_ROOT / f"{contract}.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for s in sessions:
            row = {
                "contract": contract, "root": root, "expiry": expiry.isoformat(),
                "strike": strike, "right": side,
                **s,
            }
            w.writerow(row)
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="plan + count only, write nothing")
    ap.add_argument("--limit", type=int, default=0, help="cap contracts processed (0=all)")
    args = ap.parse_args(argv)

    jobs: list[tuple[int, Path]] = []
    for dte, d in SRC_DIRS.items():
        if not d.exists():
            continue
        for p in sorted(d.glob("*.csv")):
            jobs.append((dte, p))

    if args.limit:
        jobs = jobs[: args.limit]

    print(f"source contracts found: {len(jobs)} (3DTE={sum(1 for j in jobs if j[0]==3)}, "
          f"4DTE={sum(1 for j in jobs if j[0]==4)})", file=sys.stderr)

    if args.dry_run:
        print("[dry-run] nothing written", file=sys.stderr)
        return 0

    ok = fail = 0
    total_sessions = 0
    fail_samples: list[str] = []
    for dte, path in jobs:
        stem = path.stem
        try:
            root, expiry, side, strike = parse_occ(stem)
            rows = load_intraday(path)
            sessions = aggregate_sessions(rows, expiry)
            if not sessions:
                raise DeriveError(f"{stem}: aggregation produced zero sessions")
            write_session_csv(stem, root, expiry, strike, side, sessions)
            ok += 1
            total_sessions += len(sessions)
        except DeriveError as e:
            fail += 1
            fail_samples.append(str(e))
        if ok % 500 == 0 and ok:
            print(f"  ...{ok}/{len(jobs)} derived", file=sys.stderr)

    print(f"DONE ok={ok} fail={fail} total_session_rows={total_sessions} "
          f"avg_sessions/contract={(total_sessions/ok) if ok else 0:.2f}", file=sys.stderr)
    if fail_samples:
        print(f"fail_samples: {fail_samples[:5]}", file=sys.stderr)

    import json
    manifest = {
        "generated_at_et": dt.datetime.now().isoformat(timespec="seconds"),
        "generator": "derive_spy_swing_sessionbars.py",
        "source": "backtest/data/options_3dte + options_4dte (real OPRA 5m bars, chef 2026-07-07 backfill)",
        "dte_coverage": [3, 4],
        "dte_gap": "1,2,5,6,7,8,9,10 NOT covered -- 1dte/2dte caches are entry-day-only (no true "
                   "multi-day path); 5-10dte never fetched. Extending is a fresh fetch, same "
                   "shape as _dte34_multiday_backfill.py, not this derivation tool.",
        "contracts_ok": ok,
        "contracts_fail": fail,
        "total_session_rows": total_sessions,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return 1 if fail and not ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
