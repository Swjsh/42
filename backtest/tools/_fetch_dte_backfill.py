"""FULL 1DTE+2DTE backfill scoped to the REAL signal-day set (not all days/strikes).

Reads backtest/tools/_dte_signal_days.json (produced by _dte_signal_days.py = the
byte-for-byte detectors run over full history). For each signal day T and the side(s)
that fired that day, fetches entry-day(T) 5m bars for the T+1 (1DTE) and T+2 (2DTE)
expiry contracts across a +/-BAND strike window on the SIGNAL SIDE only (the sim only
ever prices the signal side; opposite side is never needed).

PRIMARY = vwap_continuation (the test that must reach n>=20 OOS). SECONDARY = one dead
family (orb_continuation). --family-set picks which families' days to include.

Resume-safe: {symbol}.csv on bars, {symbol}.csv.empty sentinel on no-bars. Writes to
backtest/data/options_1dte/ + options_2dte/ (same 8-col schema as the 0DTE cache).

OCC symbol + schema + fetch window are byte-for-byte _fetch_1dte_2dte_sample.py.
Pure stdlib + pandas. $0 (read-only historical market data, working Safe-2 key).

Run:
  backtest/.venv/Scripts/python.exe backtest/tools/_fetch_dte_backfill.py --family-set vwap_continuation
  backtest/.venv/Scripts/python.exe backtest/tools/_fetch_dte_backfill.py --family-set vwap_continuation,orb_continuation
"""
from __future__ import annotations
import argparse, csv, datetime as dt, json, sys, time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _alpaca_creds import resolve_alpaca_creds  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
SPY_MASTER = REPO / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
DIR_1DTE = REPO / "data" / "options_1dte"
DIR_2DTE = REPO / "data" / "options_2dte"
SIGNAL_DAYS = Path(__file__).resolve().parent / "_dte_signal_days.json"
URL = "https://data.alpaca.markets/v1beta1/options/bars"

BAND = 4   # +/-4 strikes on the SIGNAL SIDE (covers offsets -2..+2 plus snap radius 4)
SLEEP = 0.25
FIELDS = ["timestamp_et", "open", "high", "low", "close", "volume", "vwap", "trade_count"]


def occ(expiry: dt.date, strike: int, side: str) -> str:
    return f"SPY{expiry.strftime('%y%m%d')}{side}{int(round(strike)) * 1000:08d}"


def trading_calendar() -> list[dt.date]:
    df = pd.read_csv(SPY_MASTER, usecols=["timestamp_et"])
    df["date"] = pd.to_datetime(df["timestamp_et"]).dt.date
    return sorted(df["date"].unique())


def fetch(sym: str, trade_day: dt.date, key: str, secret: str) -> list[dict]:
    params = {"symbols": sym, "timeframe": "5Min",
              "start": f"{trade_day.isoformat()}T13:30:00Z",
              "end": f"{trade_day.isoformat()}T21:00:00Z", "limit": 200}
    req = Request(URL + "?" + urlencode(params),
                  headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})
    with urlopen(req, timeout=30) as r:
        payload = json.loads(r.read().decode())
    bars = payload.get("bars", {}).get(sym, []) or []
    rows = []
    for b in bars:
        ts_utc = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
        ts_et = ts_utc - dt.timedelta(hours=4)
        rows.append({"timestamp_et": ts_et.strftime("%Y-%m-%dT%H:%M:%S-04:00"),
                     "open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"],
                     "volume": b["v"], "vwap": b.get("vw", b["c"]), "trade_count": b.get("n", 0)})
    return rows


def write_cache(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)


def already(path: Path) -> bool:
    return (path.exists() and path.stat().st_size > 100) or path.with_suffix(".csv.empty").exists()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family-set", default="vwap_continuation",
                    help="comma list of families from _dte_signal_days.json")
    ap.add_argument("--dte", default="1,2", help="comma list of DTEs to fetch")
    args = ap.parse_args()
    fams = [f.strip() for f in args.family_set.split(",") if f.strip()]
    dtes = [int(x) for x in args.dte.split(",")]

    sig = json.loads(SIGNAL_DAYS.read_text())
    cal = trading_calendar()
    cal_idx = {d: i for i, d in enumerate(cal)}

    # Build per-day required (side -> atm). A day can need both sides across families.
    need: dict[dt.date, dict[str, int]] = {}
    for fam in fams:
        for r in sig.get(fam, []):
            d = dt.date.fromisoformat(r["date"]); need.setdefault(d, {})[r["side"]] = int(r["atm"])
    print(f"families={fams} signal_days={len(need)}")

    DIRS = {1: DIR_1DTE, 2: DIR_2DTE}
    jobs = []  # (dte, path, trade_day, expiry, sym)
    skip_no_expiry = 0
    for d in sorted(need):
        if d not in cal_idx:
            continue
        i = cal_idx[d]
        for dte in dtes:
            if i + dte >= len(cal):
                skip_no_expiry += 1
                continue
            expiry = cal[i + dte]
            for side, atm in need[d].items():
                for off in range(-BAND, BAND + 1):
                    sym = occ(expiry, atm + off, side)
                    jobs.append((dte, DIRS[dte] / f"{sym}.csv", d, expiry, sym))

    todo = [j for j in jobs if not already(j[1])]
    print(f"total_contracts={len(jobs)} todo={len(todo)} cached={len(jobs)-len(todo)} "
          f"skip_no_expiry={skip_no_expiry}")

    creds = resolve_alpaca_creds()
    print(f"creds source={creds.source} key={creds.key[:4]}...")

    ok = empty = fail = 0
    errs = []
    for n, (dte, path, day, expiry, sym) in enumerate(todo, 1):
        for attempt in range(1, 5):
            try:
                rows = fetch(sym, day, creds.key, creds.secret)
                if rows:
                    write_cache(path, rows); ok += 1; tag = f"OK {len(rows)}b"
                else:
                    p = path.with_suffix(".csv.empty"); p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text("", encoding="utf-8"); empty += 1; tag = "EMPTY"
                if n % 50 == 0:
                    print(f"[{n}/{len(todo)}] {dte}DTE {sym} T={day} exp={expiry} {tag} "
                          f"(ok={ok} empty={empty} fail={fail})", flush=True)
                break
            except HTTPError as e:
                if e.code == 429 and attempt < 4:
                    time.sleep(2 ** attempt); continue
                body = e.read().decode("utf-8", "replace")[:120]
                errs.append({"sym": sym, "code": e.code, "body": body}); fail += 1
                print(f"[{n}/{len(todo)}] {sym} FAIL {e.code} {body}", flush=True); break
            except (URLError, TimeoutError) as e:
                if attempt < 4:
                    time.sleep(2 ** attempt); continue
                errs.append({"sym": sym, "error": repr(e)}); fail += 1
                print(f"[{n}/{len(todo)}] {sym} URLERR {e}", flush=True); break
        time.sleep(SLEEP)

    print(f"\nDONE ok={ok} empty={empty} fail={fail}")
    if errs:
        print("errors_sample:", json.dumps(errs[:10]))
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
