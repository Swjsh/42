"""regime_slice.py -- one-call per-archetype slicing for any study (WS6, 2026-08-01).

Reads the deterministic day-archetype library built by
backtest/tools/build_day_archetypes.py from analysis/regime-library/day-archetypes.json
and lets any study report per-archetype rows with one call.

Pure stdlib (no pandas) so importing this never drags heavy deps into a runner.
DESCRIPTIVE ONLY -- archetypes carry no trading verdicts. Distinct from
backtest/lib/regime_classifier.py (the pre-open lookahead-safe strategy router):
these labels use the WHOLE session (post-hoc), so they must NEVER feed a live
entry decision for the same day -- slicing/reporting/attribution only.

Typical use in a study runner:

    from lib.regime_slice import per_archetype_rows
    rows = per_archetype_rows({"2026-07-31": 145.0, "2026-07-30": -60.0})
    # -> [{"archetype": "V-reversal", "n": 1, "total": 145.0, "mean": 145.0}, ...]

Dates the library does not know land in an explicit "UNTAGGED" bucket -- loud,
never silently dropped (C7).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Iterable, Mapping

REPO = Path(__file__).resolve().parents[2]
DEFAULT_LIBRARY_PATH = REPO / "analysis" / "regime-library" / "day-archetypes.json"

# Canonical report order (matches builder ARCHETYPES + the two service buckets).
ARCHETYPES = (
    "trend-up", "trend-down", "V-reversal", "inverted-V",
    "range-chop", "pin-day", "gap-go", "gap-fade",
)
DATA_INCOMPLETE = "data-incomplete"
UNTAGGED = "UNTAGGED"

_cache: dict[str, dict] = {}


def _iso(d) -> str:
    if isinstance(d, str):
        return d
    if isinstance(d, (dt.date, dt.datetime)):
        return (d.date() if isinstance(d, dt.datetime) else d).isoformat()
    raise TypeError(f"unsupported date key type: {type(d)!r}")


def load_library(path: Path | str | None = None) -> dict:
    """Load (and memoize) the archetype library artifact."""
    p = Path(path) if path is not None else DEFAULT_LIBRARY_PATH
    key = str(p)
    if key not in _cache:
        with open(p, "r", encoding="ascii") as fh:
            _cache[key] = json.load(fh)
    return _cache[key]


def archetype_of(day, path: Path | str | None = None) -> str | None:
    """Archetype for one date (str/date/datetime), or None if untagged."""
    rec = load_library(path)["days"].get(_iso(day))
    return rec["archetype"] if rec else None


def slice_days(dates: Iterable | None = None,
               path: Path | str | None = None) -> dict[str, list[str]]:
    """archetype -> sorted date list. dates=None slices the whole library.

    Unknown dates go under "UNTAGGED"; data-incomplete sessions keep their own
    bucket. Empty buckets are omitted.
    """
    lib = load_library(path)["days"]
    out: dict[str, list[str]] = {}
    keys = sorted(lib.keys()) if dates is None else sorted(_iso(d) for d in dates)
    for k in keys:
        rec = lib.get(k)
        bucket = rec["archetype"] if rec else UNTAGGED
        out.setdefault(bucket, []).append(k)
    return out


def per_archetype_rows(values: Mapping, path: Path | str | None = None) -> list[dict]:
    """The one-call study report: {date-like: number} -> per-archetype rows.

    Returns rows in canonical order (then data-incomplete, then UNTAGGED),
    each {"archetype", "n", "total", "mean"}, followed by an "ALL" summary row.
    Buckets with n=0 are omitted (except ALL, always present).
    """
    lib = load_library(path)["days"]
    buckets: dict[str, list[float]] = {}
    for d, v in values.items():
        rec = lib.get(_iso(d))
        bucket = rec["archetype"] if rec else UNTAGGED
        buckets.setdefault(bucket, []).append(float(v))
    order = list(ARCHETYPES) + [DATA_INCOMPLETE, UNTAGGED]
    rows = []
    for name in order:
        vals = buckets.get(name)
        if not vals:
            continue
        rows.append({"archetype": name, "n": len(vals),
                     "total": round(sum(vals), 2),
                     "mean": round(sum(vals) / len(vals), 4)})
    allv = [x for vs in buckets.values() for x in vs]
    rows.append({"archetype": "ALL", "n": len(allv),
                 "total": round(sum(allv), 2),
                 "mean": round(sum(allv) / len(allv), 4) if allv else 0.0})
    return rows


def recent_mix(n: int = 25, path: Path | str | None = None) -> dict[str, int]:
    """Counts over the last n ASSIGNABLE days (mirrors the builder's window rule)."""
    lib = load_library(path)["days"]
    assignable = [(d, rec) for d, rec in sorted(lib.items())
                  if rec["archetype"] != DATA_INCOMPLETE]
    counts: dict[str, int] = {}
    for _, rec in assignable[-n:]:
        counts[rec["archetype"]] = counts.get(rec["archetype"], 0) + 1
    return counts
