"""crypto_twin_pnl -- realized P&L reconstruction + morning report for the crypto twin.

WHY THIS EXISTS (2026-07-26): the twin placed 105 orders and closed 96 round trips without a
single P&L field anywhere in its schema. `journal.jsonl`'s CLOSED rows carry the raw PLACE
response, whose `filled_avg_price` is null, so outcome was not merely untracked -- it was
unrecoverable. TWIN-PNL wired `realized_usd`/`realized_pct` onto EXIT_FILLED rows going
forward; this module reads those AND reconstructs the historical trips by chronological
pairing, so there is one number to look at.

THE DISTINCTION THIS MODULE EXISTS TO ENFORCE: most of the twin's history is FORCED -- entries
scheduled by the `crypto_twin_scenarios` coverage battery to exercise code paths, not decisions.
Forced-trade P&L measures spread and random walk, nothing else, and must NEVER be read as
strategy performance. Organic trades (scenario ORGANIC_SIGNAL, or no forcing scenario) are the
only rows that mean anything. The report splits them and refuses to print a combined headline.

Pure Python, $0, READ-ONLY: never places an order, never mutates twin state, never imports a
broker. Safe to run at any time, including while the twin loop is mid-tick.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Optional

REPO = Path(__file__).resolve().parents[2]
TWIN_DIR = REPO / "automation" / "state" / "crypto-twin"
JOURNAL = TWIN_DIR / "journal.jsonl"
DECISIONS = TWIN_DIR / "decisions.jsonl"

# The twin marks forced entries with a scenario tag and leaves organic ones None
# (crypto_twin_core.py:730 -- "None for every organic entry"). Absence is therefore the
# DOCUMENTED organic marker, but absence is also what a dropped tag looks like, so this module
# refuses to classify on absence alone and cross-checks the decision row's `reason`, which
# carries a POSITIVE discriminator: forced entries say "--force-entry test flag (bypasses
# scoring...)", organic ones read like "BULL stack 52b + hold of Prior-UTC-day H @ 64412.5".
FORCE_MARKER = "force-entry"
_MATCH_WINDOW_SEC = 120.0

# Scenario tags written by the coverage battery. Anything in here was NOT a decision.
FORCED_SCENARIOS = frozenset({
    "ENTRY_TP1_TRAIL", "ENTRY_STRUCTURE_STOP", "ENTRY_CAT_CAP", "ENTRY_MAX_HOLD",
    "RESTART_OPEN_POSITION", "CHAOS_DRILL_PROCESS_KILL",
})
ORGANIC = "ORGANIC_SIGNAL"


def _rows(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(r, dict):
                    out.append(r)
    except OSError:
        return []
    return out


def _entry_evidence(decisions_path: Optional[Path] = None) -> list[tuple[float, bool]]:
    """[(epoch, was_forced)] for every decision row that actually ENTERED, sorted by time."""
    out: list[tuple[float, bool]] = []
    for r in _rows(decisions_path or DECISIONS):
        if r.get("action") != "ENTERED":
            continue
        ts = _epoch(r.get("ts_utc"))
        if ts is None:
            continue
        forced = bool(r.get("scenario")) or FORCE_MARKER in str(r.get("reason", "")).lower()
        out.append((ts, forced))
    out.sort()
    return out


def _epoch(ts: object) -> Optional[float]:
    from datetime import datetime
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _evidence_for(entry_ts: object, evidence: list[tuple[float, bool]]) -> Optional[bool]:
    """was_forced for the ENTERED decision nearest this entry, or None if none is close."""
    t = _epoch(entry_ts)
    if t is None or not evidence:
        return None
    best = min(evidence, key=lambda e: abs(e[0] - t))
    return best[1] if abs(best[0] - t) <= _MATCH_WINDOW_SEC else None


def reconstruct_trips(path: Optional[Path] = None,
                      decisions_path: Optional[Path] = None) -> list[dict]:
    """Round trips, newest last. Prefers the wired `realized_*` fields; falls back to
    chronological entry/exit pairing for the historical rows that predate TWIN-PNL.

    Pairing is valid ONLY because the twin holds at most one position at a time (enforced by
    the NOT_FLAT branch in crypto_twin_core). If a multi-position mode is ever added, this must
    switch to order-id linkage or it will silently mis-pair.
    """
    rows = _rows(path or JOURNAL)
    seq = [r for r in rows
           if r.get("event") in ("ENTRY_QUALITY", "EXIT_FILLED") and r.get("fill_price")]
    seq.sort(key=lambda r: str(r.get("ts_utc") or ""))

    evidence = _entry_evidence(decisions_path)

    trips: list[dict] = []
    open_row: Optional[dict] = None
    for r in seq:
        if r.get("event") == "ENTRY_QUALITY" and open_row is None:
            open_row = r
        elif r.get("event") == "EXIT_FILLED" and open_row is not None:
            trips.append(_mk_trip(open_row, r, _evidence_for(open_row.get("ts_utc"), evidence)))
            open_row = None
    return trips


def _mk_trip(entry: dict, exit_: dict, was_forced: Optional[bool] = None) -> dict:
    """One round trip. `source` records whether P&L was wired at exit time or inferred."""
    ep = float(entry.get("fill_price") or 0.0)
    xp = float(exit_.get("fill_price") or 0.0)
    scenario = exit_.get("scenario") or entry.get("scenario")
    wired_pct = exit_.get("realized_pct")

    if wired_pct is not None:
        pct, source = float(wired_pct), "wired"
    else:
        pct = ((xp - ep) / ep * 100.0) if ep > 0 else 0.0
        source = "reconstructed"

    usd = exit_.get("realized_usd")
    if usd is None and exit_.get("btc_qty"):
        usd = (xp - ep) * float(exit_["btc_qty"])

    return {
        "entry_ts": entry.get("ts_utc"), "exit_ts": exit_.get("ts_utc"),
        "entry_price": ep, "exit_price": xp,
        "pct": round(pct, 6), "usd": round(float(usd), 6) if usd is not None else None,
        "reason": (exit_.get("reason") or "").split(" @")[0],
        "scenario": scenario,
        "bucket": _bucket(scenario, was_forced),
        "source": source,
    }


def _bucket(scenario: Optional[str], was_forced: Optional[bool] = None) -> str:
    """ORGANIC / FORCED / UNKNOWN -- classified on POSITIVE evidence, never on absence.

    History worth keeping: the first cut read "no scenario tag" as organic and announced 10
    real decisions. The second over-corrected and quarantined every untagged trip as UNKNOWN,
    reporting ZERO organic trades -- which was equally wrong, because the twin's documented
    convention is that organic entries are deliberately left untagged
    (crypto_twin_core.py:730). Both cuts were guessing from a missing field.

    The fix is to stop inferring from absence: `was_forced` comes from the matching decision
    row, which carries a real discriminator (a forcing scenario, or a "--force-entry" reason).
    Absence of a match still means UNKNOWN -- we just no longer treat "untagged" as evidence
    in either direction.
    """
    if scenario == ORGANIC:
        return "ORGANIC"
    if scenario in FORCED_SCENARIOS:
        return "FORCED"
    if was_forced is True:
        return "FORCED"
    if was_forced is False:
        return "ORGANIC"
    return "UNKNOWN"


def summarize(trips: Iterable[dict]) -> dict:
    trips = list(trips)
    if not trips:
        return {"n": 0, "wins": 0, "win_rate": None, "total_pct": 0.0,
                "avg_pct": None, "total_usd": None, "n_with_usd": 0}
    pcts = [t["pct"] for t in trips]
    wins = sum(1 for p in pcts if p > 0)
    usd = [t["usd"] for t in trips if t["usd"] is not None]
    return {
        "n": len(trips), "wins": wins, "win_rate": round(100.0 * wins / len(trips), 1),
        "total_pct": round(sum(pcts), 4), "avg_pct": round(sum(pcts) / len(pcts), 5),
        # None, not 0.0: no dollar data and zero dollars must not look identical.
        "total_usd": round(sum(usd), 2) if usd else None, "n_with_usd": len(usd),
    }


def _usd(s: dict) -> str:
    return f"${s['total_usd']:+.2f}" if s["total_usd"] is not None else "$ n/a"


def _line(s: dict) -> str:
    return (f"{s['n']} round trips | {s['win_rate']}% WR | total {s['total_pct']:+.3f}% "
            f"| avg {s['avg_pct']:+.4f}%/trip | {_usd(s)}")


def _table(trips: list[dict]) -> list[str]:
    L = ["", "| exit_ts (UTC) | entry | exit | % | $ | exit reason |", "|---|---|---|---|---|---|"]
    for t in trips[-15:]:
        usd = f"{t['usd']:+.2f}" if t["usd"] is not None else "n/a"
        L.append(f"| {str(t['exit_ts'])[:19]} | {t['entry_price']:.2f} | {t['exit_price']:.2f} "
                 f"| {t['pct']:+.3f} | {usd} | {t['reason']} |")
    return L


def report(path: Optional[Path] = None, decisions_path: Optional[Path] = None) -> str:
    trips = reconstruct_trips(path, decisions_path)
    by = {b: [t for t in trips if t["bucket"] == b] for b in ("ORGANIC", "FORCED", "UNKNOWN")}
    s = {b: summarize(v) for b, v in by.items()}

    L = ["# Crypto twin -- realized P&L", "",
         "## ORGANIC -- real decisions. The ONLY rows that mean anything.", ""]
    if s["ORGANIC"]["n"] == 0:
        L.append("**ZERO organic round trips. The twin has never made a trade of its own.** "
                 "Every closed position was force-scheduled by the coverage battery or is "
                 "untagged. There is no strategy result to report -- stated plainly, not hedged.")
    else:
        L.append(f"- **{_line(s['ORGANIC'])}**")
        L += _table(by["ORGANIC"])

    L += ["", "## FORCED -- coverage battery. NOT a strategy result.", ""]
    L.append(f"- {_line(s['FORCED'])}" if s["FORCED"]["n"] else "- none")
    if s["FORCED"]["n"]:
        L.append("- NOT EDGE: scheduled by a test battery, not decided. Measures spread and "
                 "random walk only. Must never enter a scorecard.")

    L += ["", "## UNKNOWN -- untagged, provenance unclear. Also not evidence.", ""]
    L.append(f"- {_line(s['UNKNOWN'])}" if s["UNKNOWN"]["n"] else "- none")
    if s["UNKNOWN"]["n"]:
        L.append("- These rows carry no scenario tag, so we cannot prove they were decisions. "
                 "They are quarantined here deliberately: counting untagged trips as organic "
                 "once reported 10 real trades when the true count was zero.")
        L += _table(by["UNKNOWN"])

    wired = sum(1 for t in trips if t["source"] == "wired")
    L += ["", "---",
          f"_{len(trips)} total round trips | {wired} with P&L wired at exit time, "
          f"{len(trips) - wired} reconstructed by chronological pairing._"]

    # LADDER-VARIANT-SIM (2026-07-27): one additive footer line pointing at the ladder-sim
    # mechanism scorecard (crypto_twin_ladder_sim.py -- 15m-HTF-gate vs ribbon-stack-gate,
    # both lanes fully simulated, never a real order). Local import + try/except so a bug
    # in that module can never break THIS report (same fail-open discipline as every other
    # cross-module read in this file). Full per-lane numbers: `python -m
    # crypto_twin_ladder_sim --report`.
    try:
        _scripts_dir = str(Path(__file__).resolve().parent)
        if _scripts_dir not in sys.path:
            sys.path.insert(0, _scripts_dir)  # this file has no sys.path setup of its own
        import crypto_twin_ladder_sim as _ladder_sim  # noqa: PLC0415
        _lsum = _ladder_sim.summarize()
        _v, _b = _lsum["variant"], _lsum["baseline"]
        L += ["", "## Ladder-variant sim (mechanism only, never SPY/BTC edge)", "",
             f"- variant (15m-HTF-gate): {_v['n']} round trips" +
             (f" | {_v['win_rate']}% WR | avg {_v['avg_pct']:+.4f}%/trip" if _v["n"] else ""),
             f"- baseline (ribbon-stack-gate): {_b['n']} round trips" +
             (f" | {_b['win_rate']}% WR | avg {_b['avg_pct']:+.4f}%/trip" if _b["n"] else ""),
             "- full report: `python -m crypto_twin_ladder_sim --report`"]
    except Exception:  # noqa: BLE001 -- this footer must never break the P&L report itself
        pass

    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="machine-readable summary")
    a = ap.parse_args(argv)
    if a.json:
        trips = reconstruct_trips()
        print(json.dumps({
            b.lower(): summarize([t for t in trips if t["bucket"] == b])
            for b in ("ORGANIC", "FORCED", "UNKNOWN")
        } | {"n_trips": len(trips)}, indent=2))
    else:
        print(report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
