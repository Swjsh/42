"""Data-coverage manifest + assertion (WP-0 / plan item A2).

Turns the silent real-fills blind spot into a check the conductor can read.

The 0DTE real-fills simulator can only price an entry on a day for which the
option-chain cache (``backtest/data/options/``) has bars. When that cache lags
the SPY price bars, every "OOS through <today>" claim is silently scoring only
the days the option cache happens to cover -- the exact OP-25 silent-degradation
foot-gun (the cache dead-ended 2026-05-29 while bars ran to 06-18, a ~14-day
blind spot that was invisible until someone ran ``ls`` by hand).

This module reports, per data class, ``[first, last, n_days]`` and flags
``DEGRADED`` when the option-cache last day is older than the price-bar last day.

    python backtest/tools/data_coverage_manifest.py            # report + write json
    python backtest/tools/data_coverage_manifest.py --assert   # also exit 1 if degraded

Writes ``automation/state/data-coverage.json`` for the conductor / health beacon.
Path-anchored to __file__ (never the cwd) per lesson C9.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "backtest" / "data"
OPTIONS = DATA / "options"
STATE = ROOT / "automation" / "state"
OUT = STATE / "data-coverage.json"

# SPY{YYMMDD}{C|P}{strike}.csv  ->  the YYMMDD trade/expiry date
_OPT_RE = re.compile(r"SPY(\d{2})(\d{2})(\d{2})[CP]\d+", re.IGNORECASE)
# ..._{YYYY-MM-DD}_{YYYY-MM-DD}[_suffix].csv  ->  every ISO date in the name
_ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _safe(fn):
    """Run a collector, degrade to an error stub rather than throwing."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - a manifest must never crash a caller
        return {"first": None, "last": None, "n_days": 0, "error": str(exc)}


def _option_cache_span() -> dict:
    if not OPTIONS.is_dir():
        return {"first": None, "last": None, "n_days": 0, "error": "options dir missing"}
    days: set[date] = set()
    for p in OPTIONS.glob("SPY*.csv"):
        m = _OPT_RE.match(p.name)
        if not m:
            continue
        yy, mm, dd = (int(g) for g in m.groups())
        try:
            days.add(date(2000 + yy, mm, dd))
        except ValueError:
            continue
    if not days:
        return {"first": None, "last": None, "n_days": 0, "error": "no parseable option files"}
    return {"first": min(days).isoformat(), "last": max(days).isoformat(), "n_days": len(days)}


def _bar_span(prefix: str) -> dict:
    """Span across all ``{prefix}_*.csv`` files, using the dates encoded in names."""
    days: list[date] = []
    for p in DATA.glob(f"{prefix}_*.csv"):
        for yyyy, mm, dd in _ISO_RE.findall(p.name):
            try:
                days.append(date(int(yyyy), int(mm), int(dd)))
            except ValueError:
                continue
    if not days:
        return {"first": None, "last": None, "n_days": 0, "error": f"no {prefix} files"}
    # n_days here is the covered range endpoints span, not a per-day count
    return {"first": min(days).isoformat(), "last": max(days).isoformat(), "n_days": (max(days) - min(days)).days}


def build_manifest() -> dict:
    classes = {
        "option_chain_realfills": _safe(_option_cache_span),
        "spy_5m_bars": _safe(lambda: _bar_span("spy_5m")),
        "vix_5m": _safe(lambda: _bar_span("vix_5m")),
    }

    opt_last = classes["option_chain_realfills"].get("last")
    bar_last = classes["spy_5m_bars"].get("last")

    status = "OK"
    gap = None
    if opt_last and bar_last:
        o = datetime.fromisoformat(opt_last).date()
        b = datetime.fromisoformat(bar_last).date()
        if o < b:
            status = "DEGRADED"
            gap = {"from": (o).isoformat(), "to": b.isoformat(), "missing_calendar_days": (b - o).days}
    elif not opt_last:
        status = "DEGRADED"
        gap = {"reason": "option cache empty/unparseable"}

    return {
        "generated_by": "backtest/tools/data_coverage_manifest.py",
        "status": status,
        "realfills_gap": gap,
        "note": (
            "option_chain_realfills.last < spy_5m_bars.last means real-fills OOS "
            "silently scores only days the option cache covers. Backfill via "
            "backtest/tools/fetch_option_data.py or hard-window grids to the cache last day."
        ),
        "classes": classes,
    }


def _fmt(c: dict) -> str:
    if c.get("error"):
        return f"{'(none)':<12} -> {'(none)':<12}  ERROR: {c['error']}"
    return f"{str(c.get('first')):<12} -> {str(c.get('last')):<12}  span/count={c.get('n_days')}"


def main(argv: list[str]) -> int:
    manifest = build_manifest()
    STATE.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print("=== Data coverage manifest ===")
    for name, c in manifest["classes"].items():
        print(f"  {name:<26} {_fmt(c)}")
    print(f"\n  STATUS: {manifest['status']}")
    if manifest["realfills_gap"]:
        print(f"  REAL-FILLS GAP: {manifest['realfills_gap']}")
    print(f"\n  written -> {OUT.relative_to(ROOT)}")

    if "--assert" in argv and manifest["status"] == "DEGRADED":
        print("\n  ASSERT FAILED: real-fills coverage is DEGRADED.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
