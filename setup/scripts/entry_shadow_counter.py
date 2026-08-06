#!/usr/bin/env python
"""entry_shadow_counter.py -- the V-d1 / V-e3 FORWARD SHADOW COUNTER (LANE 4, 2026-08-06).

THE INSTRUMENT for analysis/recommendations/entry-structure-forward-prereg-2026-08-06.json:
every night, for every engine entry the book actually took, tally whether each frozen
shadow rule WOULD have blocked it -- so the forward gates (F1-F5) are measurable from a
standing artifact instead of a human re-deriving them.

  V-d1  refuse when the LAST FULLY CLOSED 5m bar closed AGAINST the trade direction.
  V-e3  refuse when >=20 closed 1m RTH bars exist and market_structure (window=5) reports
        NO BOS/CHoCH at all (structure ABSENCE, not disagreement).

⛔ SHADOW ONLY -- MEASUREMENT ONLY. This module NEVER blocks an entry, never touches the
trading path, never writes any engine/params/signal surface. Its entire write surface is:
    analysis/entry-quality/shadow-tally.jsonl    (one row per entry event, idempotent
                                                  per activity_id -- reruns never dupe)
    analysis/entry-quality/shadow-summary.json   (running forward-window scorecard)

SEMANTICS SINGLE-SOURCED: would_block flags come from entry_quality_ledger.blocked_by
(cells 'V-d1-rescore' / 'R-PRES-1m'), the SAME frozen implementation the admissibility
battery scored -- two implementations of one rule is how replay engines silently
disagree (L251), so there is exactly one.

FORWARD WINDOW: sessions strictly AFTER the prereg freeze (frozen pre-dawn 2026-08-06,
market CLOSED), i.e. 2026-08-06 is forward session #1. Window = the next 10 trading
sessions with >=1 engine fill; gates adjudicated per the prereg's F1-F5 ladder, in the
prereg's words, by a future session -- this counter only measures.

NIGHTLY: rides the existing Gamma_WinnerAutopsy 16:25 ET fire (same fold contract as
pain_ledger / fill_latency / catastrophe_cap_shadow -- fail-open, additive, no new
scheduled task). Manual:
    python setup/scripts/entry_shadow_counter.py                # all forward dates
    python setup/scripts/entry_shadow_counter.py --date 2026-08-07

REVERT (one line): remove the entry_shadow fold block in winner_autopsy.py main()
(or delete this file); artifacts are inert data.

COST: $0 -- SIP bars come from entry_quality_ledger's per-day disk cache (at most one
new day per night); everything else is local JSONL.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import entry_quality_ledger as eql  # noqa: E402  (the ONE rule implementation)

OUT_DIR = REPO / "analysis" / "entry-quality"
TALLY_PATH = OUT_DIR / "shadow-tally.jsonl"
SUMMARY_PATH = OUT_DIR / "shadow-summary.json"
FORWARD_PREREG = "analysis/recommendations/entry-structure-forward-prereg-2026-08-06.json"
FORWARD_FIRST_DATE = "2026-08-06"   # prereg frozen pre-dawn 08-06 -> 08-06 = session #1
FORWARD_WINDOW_SESSIONS = 10        # frozen in the prereg
RULES = {"vd1": "V-d1-rescore", "ve3": "R-PRES-1m"}   # eql cell ids


# ---------- pure core (guard-tested with fixtures; no I/O, no network) ----------------------

def shadow_flags(event: dict) -> dict:
    """would_block booleans (True/False/None=abstain) for one featured entry event."""
    return {name: eql.blocked_by(event, cell) for name, cell in RULES.items()}


def tally_row(event: dict) -> dict:
    flags = shadow_flags(event)
    return {
        "date": event["date_et"], "activity_id": event["activity_id"],
        "arm": event["arm"], "symbol": event["symbol"], "opt_side": event["opt_side"],
        "ts_et": event["ts_et"], "qty": event["qty"], "entry_price": event["price"],
        "pnl": round(float(event["pnl"]), 2),
        "vd1_would_block": flags["vd1"], "ve3_would_block": flags["ve3"],
        "n_closed_5m": event.get("n_closed_5m"), "n_closed_1m": event.get("n_closed_1m"),
        "d_last5_dir": event.get("d_last5_dir"), "s1_kind": event.get("s1_kind"),
    }


def upsert_rows(existing: list[dict], new_rows: list[dict]) -> tuple[list[dict], int, int]:
    """Idempotent merge on activity_id: reruns update in place, never duplicate."""
    by_id = {r["activity_id"]: r for r in existing}
    n_new = n_updated = 0
    for r in new_rows:
        if r["activity_id"] in by_id:
            by_id[r["activity_id"]] = r
            n_updated += 1
        else:
            by_id[r["activity_id"]] = r
            n_new += 1
    merged = sorted(by_id.values(), key=lambda r: (r["date"], r["ts_et"], r["activity_id"]))
    return merged, n_new, n_updated


def build_summary(rows: list[dict], generated_at_et: str) -> dict:
    """The running forward scorecard against the prereg's F-gates (measure, not adjudicate)."""
    dates = sorted({r["date"] for r in rows})
    out = {"_meta": {
        "generated_at_et": generated_at_et,
        "builder": "setup/scripts/entry_shadow_counter.py",
        "forward_prereg": FORWARD_PREREG,
        "shadow_only": "⛔ MEASUREMENT ONLY -- neither rule refuses a live entry.",
        "forward_window": {"first_date": FORWARD_FIRST_DATE,
                           "sessions_required": FORWARD_WINDOW_SESSIONS,
                           "sessions_elapsed": len(dates), "dates": dates},
        "n_entries": len(rows)},
    }
    for name in RULES:
        key = f"{name}_would_block"
        blocked = [r for r in rows if r[key] is True]
        kept = [r for r in rows if r[key] is False]
        abstain = [r for r in rows if r[key] is None]
        bw = round(sum(r["pnl"] for r in blocked if r["pnl"] > 0), 2)
        bl = round(-sum(r["pnl"] for r in blocked if r["pnl"] < 0), 2)
        out[name] = {
            "n_blocked": len(blocked), "n_kept": len(kept), "n_abstain": len(abstain),
            "forward_delta_usd": round(-sum(r["pnl"] for r in blocked), 2),
            "blocked_winner_usd": bw, "blocked_loser_usd": bl,
            "blocked_wr_pct": (round(100 * sum(1 for r in blocked if r["pnl"] > 0)
                                     / len(blocked), 1) if blocked else None),
            "f_gate_progress": {
                "F1_direction_delta_positive": (-sum(r["pnl"] for r in blocked)) > 0,
                "F2_not_winner_killer": bw < bl,
                "F3_frequency_n_blocked_ge_8": len(blocked) >= 8,
                "note": "F4 (pooled permutation) + F5 (regime split) are adjudicated by a "
                        "future session per the prereg -- not computed nightly.",
            },
        }
    return out


# ---------- I/O -----------------------------------------------------------------------------

def _load_tally() -> list[dict]:
    if not TALLY_PATH.exists():
        return []
    rows = []
    with open(TALLY_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_tally(rows: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = TALLY_PATH.with_suffix(".jsonl.tmp")
    tmp.write_text("".join(json.dumps(r, default=str) + "\n" for r in rows),
                   encoding="utf-8")
    tmp.replace(TALLY_PATH)


def featured_events(dates: list[str]) -> list[dict]:
    """Population events for `dates`, with factors, via the ONE ledger implementation."""
    events, _meta = eql.build_population()
    events = [e for e in events if e["date_et"] in set(dates)]
    if not events:
        return []
    need = sorted({e["date_et"] for e in events})
    m1, m5 = eql.load_bars("1m", need), eql.load_bars("5m", need)
    eql.build_features(events, m1, m5, eql.load_levels_timeline(), eql.load_pain_index())
    return events


def run_nightly(date_et: str | None = None) -> dict:
    """Tally forward dates (or one date), refresh the summary. Fail-open at the caller."""
    from et_clock import et_now
    now_iso = et_now().isoformat()
    if date_et is not None:
        dates = [date_et]
    else:
        events_all, _ = eql.build_population()
        dates = sorted({e["date_et"] for e in events_all if e["date_et"] >= FORWARD_FIRST_DATE})
    events = featured_events(dates)
    rows = [tally_row(e) for e in events]
    merged, n_new, n_updated = upsert_rows(_load_tally(), rows)
    _write_tally(merged)
    summary = build_summary(merged, now_iso)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"[entry-shadow] {len(merged)} tally rows ({n_new} new, {n_updated} refreshed) "
          f"across {len(summary['_meta']['forward_window']['dates'])} forward session(s); "
          f"vd1 blocks {summary['vd1']['n_blocked']}, ve3 blocks {summary['ve3']['n_blocked']} "
          f"-> {SUMMARY_PATH.relative_to(REPO)}")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="V-d1/V-e3 forward shadow counter (shadow only).")
    ap.add_argument("--date", default=None, help="tally exactly one ET date")
    args = ap.parse_args()
    try:
        run_nightly(args.date)
    except Exception as e:  # noqa: BLE001 -- measurement organ: never propagate
        print(f"[entry-shadow] ERROR (fail-open): {type(e).__name__}: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
