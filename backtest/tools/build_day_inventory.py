"""backtest/tools/build_day_inventory.py -- Step 1 of the EDGE-MATRIX-NIGHTLY-RERUN standing
loop (backtest/tools/edge_matrix_rerun.py). Forward-extends the FROZEN day inventory
(day-inventory-2026-07-23.json) with any new trading days that have accrued in the SPY/VIX
5m caches since its last day (2026-07-22), WITHOUT ever mutating the frozen original and
WITHOUT ever touching heldout_days (frozen last-25%-by-date OOS boundary).

NAMING (deliberate, differs from edge_matrix_rerun.py's docstring which said "day-inventory-
<today>.json"): that literally collides with the frozen original's own filename the very
first time this runs, since today (2026-07-23) IS the frozen original's date suffix -- that
suffix encodes which EDGE MATRIX build the inventory belongs to, not a run date. This script
instead writes a single, stable, always-latest derived file:

    analysis/edge-matrix/day-inventory-extended.json

Consumers that want forward days read `-extended.json`. The 6 family runners' hardcoded
INVENTORY_PATH constants stay pointed at the frozen original until a future fire wires
per-runner --days-after flags (Step 2 of the rerun protocol) -- this script does NOT change
what the runners consume; it only makes forward days computable and inspectable.

WHAT IS FROZEN (never touched):
  - The original file day-inventory-2026-07-23.json is read-only to this script.
  - heldout_days: carried through VERBATIM from the original. Recomputing it after new days
    accrue would shift the OOS cutoff -- forbidden by the rerun protocol's rule 2.
  - Every row for a date <= the original's last day: copied through unchanged.

WHAT --extend COMPUTES for each NEW date (> the original's last day), honest + disclosed:
  - has_opra / n_opra_files: same convention as _amend_day_inventory_opra_gap.py
    (backtest/data/options/SPY<yymmdd>*.csv, glob count).
  - n_rth_bars / partial / gap_pct: mechanical, from the TRUE-ET RTH SPY 5m frame (09:30 <=
    t < 16:00 America/New_York, DST-aware). Coverage rule matches the original's own `method`
    field: day included iff >= 30 RTH bars; partial flag if < 70. gap_pct = (rth_open -
    prev_covered_day_rth_close) / prev_close * 100, where "prev covered day" walks the
    COMBINED (original + already-appended-this-run) days list.
  - day_type / vix_band: computed with the SAME formulas recorded in the original's own
    `method` field (atr20 = mean of prior <=20 covered days' RTH ranges, min 5 samples else
    "unclassified"; day_vix = mean RTH VIX 5m close, band low<15/mid 15-20/elevated 20-25/
    high>=25). VERIFIED this build (grep across all 6 edge_matrix_*.py family runners):
    day_type/vix_band are DISCLOSURE-ONLY fields (regime_split breakdowns), never a gate or
    filter on which days/fills are included -- so a best-effort forward classification is
    safe to ship without independently proving it byte-identical to whatever pipeline built
    the frozen original's historical rows.
  - source_file: whichever top-level backtest/data/spy_5m_*.csv file yields the MOST true-ET
    RTH bars for that date among all candidate files (tie: lexicographically last filename --
    generalizes the original's own "max RTH bars wins, tie lexicographically last" rule from
    a single designated file to a forward-day scan across all available caches).

USAGE:
    python backtest/tools/build_day_inventory.py --extend   # idempotent; 0 new days = no-op write
    python backtest/tools/build_day_inventory.py --status   # pending-day count only, no write

COST: $0 / pure-Python+pandas / backtest/.venv interpreter. Read-only against the frozen
original and the raw caches; only ever writes day-inventory-extended.json.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from datetime import date, datetime, time as dtime
from pathlib import Path
from typing import Optional

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
EM_DIR = REPO / "analysis" / "edge-matrix"
DATA_DIR = REPO / "backtest" / "data"
OPTIONS_DIR = DATA_DIR / "options"
FROZEN_ORIGINAL = EM_DIR / "day-inventory-2026-07-23.json"
EXTENDED_PATH = EM_DIR / "day-inventory-extended.json"

_SPY_FILE_RE = re.compile(r"^spy_5m_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})(?:_merged)?\.csv$")
_VIX_FILE_RE = re.compile(r"^vix_5m_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})(?:_merged)?\.csv$")


def log(msg: str) -> None:
    print(f"[build-day-inventory] {msg}", flush=True)


def _true_et(series: pd.Series) -> Optional[pd.Series]:
    """TRUE-ET frame (matches the day-inventory's own `method.rth` note and the edge_matrix
    family runners' `_true_et`): per-row offset -> UTC -> DST-aware America/New_York -> naive
    wall. Returns None (not raises) if the series carries no per-row offsets -- the caller
    treats an offset-less candidate file as unusable for forward extension (C6: refuse to
    guess a frame), same fail-open discipline as load_spy_frame's re-sourcing fallback."""
    s = series.astype(str)
    if not s.str.contains(r"(?:Z|[+-]\d{2}:?\d{2})\s*$", regex=True).all():
        return None
    ts = pd.to_datetime(s, format="mixed", utc=True)
    return ts.dt.tz_convert("America/New_York").dt.tz_localize(None)


def _candidate_files(pattern_re: re.Pattern, prefix: str) -> list[Path]:
    out = []
    for f in DATA_DIR.glob(f"{prefix}_5m_*.csv"):
        if pattern_re.match(f.name):
            out.append(f)
    return out


def _load_rth(path: Path, value_cols: list[str]) -> Optional[pd.DataFrame]:
    """Load one 5m cache file, return TRUE-ET RTH-only rows, or None if unusable."""
    try:
        raw = pd.read_csv(path)
    except Exception as exc:  # pragma: no cover -- defensive, surfaces in --extend output
        log(f"  WARN: could not read {path.name}: {exc}")
        return None
    if "timestamp_et" not in raw.columns:
        return None
    et = _true_et(raw["timestamp_et"])
    if et is None:
        return None
    raw = raw.copy()
    raw["timestamp_et"] = et
    for c in value_cols:
        if c in raw.columns:
            raw[c] = pd.to_numeric(raw[c], errors="coerce")
    m = (raw["timestamp_et"].dt.time >= dtime(9, 30)) & (raw["timestamp_et"].dt.time < dtime(16, 0))
    keep = ["timestamp_et"] + [c for c in value_cols if c in raw.columns]
    d = raw.loc[m, keep].drop_duplicates(subset="timestamp_et", keep="last").sort_values("timestamp_et")
    return d


def _pending_dates(original: dict) -> list[str]:
    """New calendar dates present in any SPY cache beyond the original's last covered day,
    with >=1 raw row (before the >=30-bar coverage filter -- this is the raw candidate set;
    _extend_new_days applies the real coverage rule per date)."""
    last_day = max(r["date"] for r in original["days"])
    candidates: set[str] = set()
    for f in _candidate_files(_SPY_FILE_RE, "spy"):
        d = _load_rth(f, ["open", "high", "low", "close", "volume"])
        if d is None or d.empty:
            continue
        dates = sorted({str(x) for x in d["timestamp_et"].dt.date.astype(str).unique() if x > last_day})
        candidates.update(dates)
    return sorted(candidates)


def cmd_status() -> int:
    original = json.loads(FROZEN_ORIGINAL.read_text(encoding="utf-8"))
    last_day = max(r["date"] for r in original["days"])
    pending = _pending_dates(original)
    out = {
        "frozen_original_last_day": last_day,
        "pending_dates_raw": pending,
        "pending_count": len(pending),
        "today": date.today().isoformat(),
        "extended_file_exists": EXTENDED_PATH.exists(),
    }
    print(json.dumps(out, indent=2))
    return 0


def _atr20(prior_ranges: list[float]) -> Optional[float]:
    tail = prior_ranges[-20:]
    if len(tail) < 5:
        return None
    return sum(tail) / len(tail)


def _classify_day_type(range_ratio: Optional[float], body_frac: Optional[float]) -> str:
    if range_ratio is None or body_frac is None:
        return "unclassified"
    if range_ratio >= 1.0 and body_frac >= 0.5:
        return "trend"
    if range_ratio < 0.75:
        return "chop"
    return "range"


def _vix_band(day_vix: Optional[float]) -> Optional[str]:
    if day_vix is None:
        return None
    if day_vix < 15:
        return "low"
    if day_vix < 20:
        return "mid"
    if day_vix < 25:
        return "elevated"
    return "high"


def _extend_new_days(original: dict) -> dict:
    """Returns the extended inventory dict (does NOT write). Pure function for testability."""
    last_day = max(r["date"] for r in original["days"])
    pending = _pending_dates(original)
    days = [dict(r) for r in original["days"]]  # copy-through, never mutate originals in place
    opra_days = list(original["opra_days"])
    excluded_fragments = [dict(r) for r in original.get("excluded_fragments", [])]
    prior_ranges = [r["rth_range"] for r in days if r.get("rth_range") is not None]
    spy_files = _candidate_files(_SPY_FILE_RE, "spy")
    # The frozen original's rows don't store rth_close (only rth_range/day_type/etc.), so
    # gap_pct continuity for the FIRST forward day needs the last original day's actual RTH
    # close recomputed from its own designated source_file -- never invented/estimated.
    prev_close: Optional[float] = None
    last_day_row = next((r for r in days if r["date"] == last_day), None)
    if last_day_row is not None:
        src = DATA_DIR / last_day_row["source_file"]
        if src.exists():
            frame = _load_rth(src, ["open", "high", "low", "close", "volume"])
            if frame is not None:
                last_rows = frame[frame["timestamp_et"].dt.date.astype(str) == last_day]
                if not last_rows.empty:
                    prev_close = float(last_rows.iloc[-1]["close"])
        if prev_close is None:
            log(f"  WARN: could not recompute {last_day}'s RTH close from "
                f"{last_day_row['source_file']} -- first forward day's gap_pct will be null")
    vix_files = _candidate_files(_VIX_FILE_RE, "vix")
    forward_days: list[str] = []
    for d in pending:
        # pick the file yielding the MOST RTH bars for this date; tie -> lexicographically last name
        best: Optional[tuple[str, pd.DataFrame]] = None
        for f in spy_files:
            frame = _load_rth(f, ["open", "high", "low", "close", "volume"])
            if frame is None:
                continue
            day_rows = frame[frame["timestamp_et"].dt.date.astype(str) == d]
            if day_rows.empty:
                continue
            if best is None or len(day_rows) > len(best[1]) or (
                len(day_rows) == len(best[1]) and f.name > best[0]):
                best = (f.name, day_rows)
        if best is None:
            continue
        src_name, day_rows = best
        n_bars = len(day_rows)
        if n_bars < 30:
            excluded_fragments.append({"date": d, "n_rth_bars": n_bars})
            log(f"  {d}: {n_bars} RTH bars (<30) -- excluded as fragment, not added to days[]")
            continue
        partial = n_bars < 70
        rth_open = float(day_rows.iloc[0]["open"])
        rth_close = float(day_rows.iloc[-1]["close"])
        rth_high = float(day_rows["high"].max())
        rth_low = float(day_rows["low"].min())
        rth_range = rth_high - rth_low
        gap_pct = None
        if prev_close is not None and prev_close != 0:
            gap_pct = round((rth_open - prev_close) / prev_close * 100, 3)
        range_ratio = None
        atr20 = _atr20(prior_ranges)
        if atr20:
            range_ratio = round(rth_range / atr20, 3)
        body_frac = round(abs(rth_close - rth_open) / rth_range, 3) if rth_range else None
        day_type = _classify_day_type(range_ratio, body_frac)
        ymd = d[2:4] + d[5:7] + d[8:10]
        n_opra_files = len(list(OPTIONS_DIR.glob(f"SPY{ymd}*.csv")))
        has_opra = n_opra_files > 0
        # VIX day_vix
        day_vix = None
        for vf in vix_files:
            vframe = _load_rth(vf, ["close"])
            if vframe is None:
                continue
            vrows = vframe[vframe["timestamp_et"].dt.date.astype(str) == d]
            if not vrows.empty:
                day_vix = round(float(vrows["close"].mean()), 3)
                break
        row = {
            "date": d,
            "has_opra": has_opra,
            "n_opra_files": n_opra_files,
            "gap_pct": gap_pct,
            "day_type": day_type,
            "vix_band": _vix_band(day_vix),
            "day_vix": day_vix,
            "rth_range": round(rth_range, 4),
            "range_ratio": range_ratio,
            "body_frac": body_frac,
            "n_rth_bars": n_bars,
            "partial": partial,
            "source_file": src_name,
        }
        days.append(row)
        prior_ranges.append(rth_range)
        prev_close = rth_close
        forward_days.append(d)
        if has_opra:
            opra_days.append(d)
    extended = {
        "extended_from": FROZEN_ORIGINAL.name,
        "extended_at": datetime.now().isoformat(timespec="seconds"),
        "frozen_original_last_day": last_day,
        "forward_days": forward_days,
        "built": original["built"],
        "built_for": original["built_for"],
        "method": original["method"],
        "counts": {
            **original["counts"],
            "opra_days": len(opra_days),
            "forward_days_added": len(forward_days),
        },
        "days": days,
        "opra_days": sorted(opra_days),
        "heldout_days": list(original["heldout_days"]),  # FROZEN, verbatim, never touched
        "excluded_fragments": excluded_fragments,
        "manual_amendments": list(original.get("manual_amendments", [])),
    }
    return extended


def cmd_extend() -> int:
    original = json.loads(FROZEN_ORIGINAL.read_text(encoding="utf-8"))
    extended = _extend_new_days(original)
    EXTENDED_PATH.write_text(json.dumps(extended, indent=2), encoding="utf-8", newline="\n")
    n = len(extended["forward_days"])
    log(f"forward_days added this run: {n} {extended['forward_days']}")
    log(f"wrote {EXTENDED_PATH.relative_to(REPO)} "
        f"(days={len(extended['days'])}, opra_days={len(extended['opra_days'])}, "
        f"heldout_days={len(extended['heldout_days'])} unchanged)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Forward-extend the frozen edge-matrix day inventory")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--extend", action="store_true", help="compute + write day-inventory-extended.json")
    g.add_argument("--status", action="store_true", help="pending-day count only, no write")
    args = ap.parse_args()
    if args.status:
        return cmd_status()
    return cmd_extend()


if __name__ == "__main__":
    raise SystemExit(main())
