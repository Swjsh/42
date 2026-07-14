"""Repair dead premarket tape in spy_5m_*.csv caches (incident 2026-07-14).

Defect: every session appended by the yfinance-era append_today.py (2026-05-13
through 2026-07-14) carries premarket bars with volume=0 and is missing the
09:15-09:25 ET bars — Yahoo's extended-hours intraday feed simply has no
volume. Sessions sourced from the Alpaca SIP seed (<= 2026-05-29 in the
2026-05-19 chain) are correct.

Repair: for every session in the target CSV whose premarket (04:00-09:25 ET)
volume sums to zero while RTH volume is nonzero, drop the premarket rows and
replace them with Alpaca SIP bars (the seed's exact provenance — verified
bar-identical on 2026-05-27). RTH rows are NEVER touched.

Safety: original file is backed up to data/_backup_premarket_zero/ first;
write is atomic; post-write verification re-reads the file and asserts
(a) RTH rows are value-identical to the original, (b) every repaired session
now has nonzero premarket volume. Outcome is logged to
analysis/backtests/data-versions.jsonl with action="premarket_repair".

Usage:
    python tools/repair_premarket_volume.py --files <csv> [<csv> ...] [--dry-run]
    python tools/repair_premarket_volume.py            (auto: latest spy_5m chain file)
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from alpaca_bars import PREMARKET_START, RTH_START, fetch_spy_5m_sip  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
VERSIONS_LOG = REPO / "analysis" / "backtests" / "data-versions.jsonl"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    ts = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    df["_date"] = ts.dt.date
    df["_time"] = ts.dt.time
    df["_ts_utc"] = ts.dt.tz_convert("UTC")
    return df


def _broken_sessions(df: pd.DataFrame) -> list[dt.date]:
    """Sessions with premarket bars present, all volume zero, and live RTH."""
    pre = df[df["_time"] < RTH_START]
    rth = df[df["_time"] >= RTH_START]
    pre_vol = pre.groupby("_date")["volume"].sum()
    pre_n = pre.groupby("_date")["volume"].size()
    rth_vol = rth.groupby("_date")["volume"].sum()
    out = []
    for d, v in pre_vol.items():
        if v == 0 and pre_n.get(d, 0) > 0 and rth_vol.get(d, 0) > 0:
            out.append(d)
    return sorted(out)


def repair_file(path: Path, dry_run: bool) -> dict:
    df = _load(path)
    broken = _broken_sessions(df)
    if not broken:
        return {"status": "ok", "action": "noop", "file": path.name,
                "reason": "no zero-premarket sessions found"}

    print(f"{path.name}: {len(broken)} zero-premarket sessions "
          f"({broken[0]} .. {broken[-1]})")

    sip = fetch_spy_5m_sip(broken[0], broken[-1], include_premarket=True)
    if sip.empty:
        return {"status": "error", "action": "abort", "file": path.name,
                "reason": "Alpaca SIP fetch returned nothing — cache untouched"}
    sts = pd.to_datetime(sip["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    sip["_date"] = sts.dt.date
    sip["_time"] = sts.dt.time
    sip["_ts_utc"] = sts.dt.tz_convert("UTC")
    replacement = sip[(sip["_time"] >= PREMARKET_START)
                      & (sip["_time"] < RTH_START)
                      & (sip["_date"].isin(set(broken)))]

    # Every broken session must be covered by real, nonzero replacement volume.
    repl_vol = replacement.groupby("_date")["volume"].sum()
    uncovered = [d for d in broken if repl_vol.get(d, 0) <= 0]
    if uncovered:
        return {"status": "error", "action": "abort", "file": path.name,
                "reason": f"SIP replacement empty/zero for {uncovered} — cache untouched"}

    drop_mask = (df["_time"] < RTH_START) & (df["_date"].isin(set(broken)))
    dropped = int(drop_mask.sum())
    kept = df.loc[~drop_mask]
    combined = pd.concat([kept, replacement], ignore_index=True)
    combined = combined.sort_values("_ts_utc").reset_index(drop=True)
    out = combined.drop(columns=["_date", "_time", "_ts_utc"])

    result = {
        "status": "ok",
        "action": "premarket_repair",
        "file": path.name,
        "sessions_repaired": len(broken),
        "first_session": broken[0].isoformat(),
        "last_session": broken[-1].isoformat(),
        "rows_dropped": dropped,
        "rows_inserted": len(replacement),
        "rows_before": len(df),
        "rows_after": len(out),
    }
    if dry_run:
        result["action"] = "would_repair"
        return result

    backup_dir = DATA_DIR / "_backup_premarket_zero"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / path.name
    if not backup.exists():
        shutil.copy2(path, backup)
    result["backup"] = str(backup)
    result["hash_old"] = _sha256(path)

    tmp = path.with_suffix(path.suffix + ".pending")
    out.to_csv(tmp, index=False)
    tmp.replace(path)
    result["hash_new"] = _sha256(path)

    # ── Post-write verification against the ORIGINAL frame ────────────────
    check = _load(path)
    if _broken_sessions(check):
        result["status"] = "error"
        result["verify"] = "FAILED: zero-premarket sessions remain"
        return result
    old_rth = (df[df["_time"] >= RTH_START]
               .sort_values("_ts_utc")[["_ts_utc", "open", "high", "low", "close", "volume"]]
               .reset_index(drop=True))
    new_rth = (check[check["_time"] >= RTH_START]
               .sort_values("_ts_utc")[["_ts_utc", "open", "high", "low", "close", "volume"]]
               .reset_index(drop=True))
    if not old_rth.equals(new_rth):
        result["status"] = "error"
        result["verify"] = "FAILED: RTH rows changed"
        return result
    result["verify"] = (f"OK: RTH value-identical ({len(new_rth)} rows), "
                        f"{len(broken)} sessions now have live premarket volume")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", nargs="*", default=None,
                    help="Explicit CSV paths (default: latest spy_5m_*.csv in data/)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.files:
        targets = [Path(f) for f in args.files]
    else:
        chain = sorted(DATA_DIR.glob("spy_5m_*.csv"))
        if not chain:
            print(f"No spy_5m_*.csv under {DATA_DIR}")
            return 1
        targets = [chain[-1]]

    status = 0
    for path in targets:
        if not path.exists():
            print(f"SKIP missing: {path}")
            status = 1
            continue
        result = repair_file(path, dry_run=args.dry_run)
        for k, v in result.items():
            print(f"  {k}: {v}")
        if not args.dry_run and result["action"] != "noop":
            VERSIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
            row = {"ran_at": dt.datetime.now().isoformat(timespec="seconds"),
                   "symbol": "spy", **result}
            with VERSIONS_LOG.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
        if result["status"] == "error":
            status = 1
        print()
    return status


if __name__ == "__main__":
    raise SystemExit(main())
