"""TRADE-TO-LEARN CUMULATIVE DIGEST — "since arm date" P&L per trade-to-learn setup.

THE GAP IT CLOSES (F3-RED-BOOK-STILL-ARMED close, 2026-07-18): `recency_check.py` /
`license_monitor.py` only answer "is edge X RED on a rolling 25-day window *right now*".
There was NO standing surface showing CUMULATIVE real P&L for a trade-to-learn-armed
setup since its ACTUAL arm date (params.json `extra_setup_exec_armed[setup]=true`,
2026-07-01 grant). A rolling window can sit RED-ish on noise while the all-time total
is fine (or vice-versa) — nobody had an easy answer to "is trade-to-learn setup X
actually working since day 1" without re-deriving it by hand each time.

WHAT THIS IS (deliberately NOT a re-simulation): unlike `recency_check.py` (which
re-detects signals and re-simulates real-OPRA fills via `lib.simulator_real`), this
reads the ACTUAL placed-and-filled paper trades from `journal/trades.csv` — the
literal fills the live engine put on, tagged by `setup`. That is a smaller, honest n
(most trade-to-learn setups have fired rarely or not at all since arm — that itself
is the finding), but it is ground truth for "did this setup actually trade, and how
did it do", not a re-derived estimate.

NEVER flips anything (Rule 9) — visibility only, no auto-disarm (per F3's own
close: disarming a trade-to-learn setup on rolling-window noise is a J-facing
edge-continuation call, not something this digest, or any automated loop, should
decide). Pure $0 monitor — no network, one CSV read.

ARM_DATES is a documented, HAND-MAINTAINED map (setup -> ISO arm date), not derived
from params.json (params.json has no arm-date field to derive from). The guard
`test_trade_to_learn_digest.py::test_arm_dates_cover_every_live_armed_setup` is the
presence ratchet that keeps this from silently drifting the next time a setup gets
armed (C14: a newly-True `extra_setup_exec_armed` key with no matching ARM_DATES
entry fails the guard loudly instead of silently vanishing from the digest).

Run (nightly, folded into license_monitor's digest — see license_monitor.py):
  backtest/.venv/Scripts/python.exe backtest/autoresearch/trade_to_learn_digest.py
Standalone (prints only, writes the JSON, no STATUS/Discord touch):
  ... trade_to_learn_digest.py --dry-run
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
TRADES_CSV = ROOT / "journal" / "trades.csv"
PARAMS_JSON = ROOT / "automation" / "state" / "params.json"
OUT_JSON = ROOT / "automation" / "state" / "trade-to-learn-digest.json"

# Hand-maintained: setup (params.json extra_setup_exec_armed key, lowercase snake_case,
# matches setup_dispatch.DISPATCH_ROSTER's setup_name) -> documented ISO arm date.
# Sourced from git history of automation/state/params.json (the commit that flipped
# extra_setup_exec_armed[setup] true -> false), NOT guessed:
#   vwap_continuation / vwap_reclaim_failed_break / vix_regime_dayside /
#   double_bottom_base_quiet -> commit 4e71618 "arm 3 validated setups on Safe paper
#   (trade-to-learn, J ratified 2026-07-01)" — 2026-07-01 (double_bottom_base_quiet rode
#   the same commit despite the message saying "3"; verified via `git show 4e71618`).
#   bollinger_squeeze -> commit 004e7ea "WIRE-BOLLINGER" — 2026-07-02.
ARM_DATES: dict[str, str] = {
    "vwap_continuation": "2026-07-01",
    "vwap_reclaim_failed_break": "2026-07-01",
    "vix_regime_dayside": "2026-07-01",
    "double_bottom_base_quiet": "2026-07-01",
    "bollinger_squeeze": "2026-07-02",
}


def live_armed_setups(params_path: Path = PARAMS_JSON) -> list[str]:
    """Setups with extra_setup_exec_armed[setup]=True in the given params file."""
    try:
        p = json.loads(params_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    armed = p.get("extra_setup_exec_armed", {}) or {}
    return sorted(k for k, v in armed.items() if v)


def load_real_fills(csv_path: Path = TRADES_CSV) -> list[dict]:
    """Read journal/trades.csv rows with a parseable date/setup/dollar_pnl.

    Only reads the EARLY columns (date, setup, c_or_p, dollar_pnl) — a known pre-existing
    CSV quoting defect in some rows' `archetype_match_json` field (unescaped literal `"` in
    embedded notes text) corrupts LATER columns (account_id, notes_short) for those rows,
    but never the early ones csv.DictReader parses before hitting the bad quote
    (verified 2026-07-18: dollar_pnl parses clean for all 179 rows regardless; c_or_p sits
    even earlier in the header than dollar_pnl, same guarantee applies). Flagged as a
    separate lesson-inbox note, not fixed here (out of this bounded task's scope).
    """
    if not csv_path.exists():
        return []
    rows: list[dict] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        for raw in csv.DictReader(f):
            setup = (raw.get("setup") or "").strip()
            date_s = (raw.get("date") or "").strip()
            pnl_s = (raw.get("dollar_pnl") or "").strip()
            side = (raw.get("c_or_p") or "").strip().upper()
            if not setup or not date_s or not pnl_s:
                continue
            try:
                d = dt.date.fromisoformat(date_s)
                pnl = float(pnl_s)
            except Exception:
                continue
            rows.append({"date": d, "setup_key": setup.lower(), "pnl": pnl, "side": side})
    return rows


def compute_since_arm(*, csv_path: Path = TRADES_CSV, params_path: Path = PARAMS_JSON,
                       today: dt.date | None = None) -> dict:
    """Per-setup cumulative real-fill P&L since each setup's documented arm date.

    Also reports EFFECTIVE INDEPENDENT TRIALS (ZERO-FOR-TWELVE-POSTMORTEM, 2026-07-25):
    n_fills counts CSV rows, which over-counts same-day re-entries and same-signal
    TP1/runner leg splits as independent trials. n_distinct_days / n_distinct_day_side
    are the honest lower bound — a losing STREAK measured in n_fills can be a losing
    streak of 4 correlated DAYS wearing a 12-trial costume. Verified mechanism (this
    date): vwap_continuation + vix_regime_dayside both derive `side` from the identical
    `session_vwap_asof`/day-trend-side classifier (autoresearch/infinite_ammo_discovery.py,
    imported verbatim by both) — so cross_setup_same_day_side below also surfaces when
    two DIFFERENT armed setups are riding the same underlying day-call, not two
    independent bets, even though they show up as separate setups in n_fills.
    """
    today = today or dt.date.today()
    fills = load_real_fills(csv_path)
    armed = live_armed_setups(params_path)

    setups_out: dict[str, dict] = {}
    unmapped: list[str] = []
    for setup in armed:
        arm_date_s = ARM_DATES.get(setup)
        if arm_date_s is None:
            unmapped.append(setup)
            continue
        arm_date = dt.date.fromisoformat(arm_date_s)
        matched = [r for r in fills if r["setup_key"] == setup and r["date"] >= arm_date]
        n = len(matched)
        total = round(sum(r["pnl"] for r in matched), 2)
        wins = sum(1 for r in matched if r["pnl"] > 0)
        days_armed = (today - arm_date).days
        distinct_days = sorted({str(r["date"]) for r in matched})
        distinct_day_side = sorted({(str(r["date"]), r["side"]) for r in matched})
        setups_out[setup] = {
            "arm_date": arm_date_s,
            "days_since_arm": days_armed,
            "n_fills": n,
            "n_distinct_days": len(distinct_days),
            "n_distinct_day_side_buckets": len(distinct_day_side),
            "total_dollar_pnl": total,
            "avg_dollar_pnl": round(total / n, 2) if n else None,
            "wr_pct": round(100 * wins / n, 1) if n else None,
            "first_fill": min((str(r["date"]) for r in matched), default=None),
            "last_fill": max((str(r["date"]) for r in matched), default=None),
            "status": "ACTIVE" if n else "NO_FILLS_SINCE_ARM",
        }

    # Cross-setup correlation: (date, side) buckets hit by 2+ DIFFERENT armed setups.
    # A shared bucket means those setups' fills that day are NOT independent evidence
    # of each other — they likely rode the same underlying day-trend/side call.
    by_date_side: dict[tuple, set] = {}
    for r in fills:
        if r["setup_key"] not in armed:
            continue
        arm_date_s = ARM_DATES.get(r["setup_key"])
        if arm_date_s is None or r["date"] < dt.date.fromisoformat(arm_date_s):
            continue
        key = (str(r["date"]), r["side"])
        by_date_side.setdefault(key, set()).add(r["setup_key"])
    cross_setup_same_day_side = [
        {"date": k[0], "side": k[1], "setups": sorted(v)}
        for k, v in sorted(by_date_side.items()) if len(v) >= 2
    ]

    return {
        "digest": "TRADE-TO-LEARN-CUMULATIVE-DIGEST — since-arm real-fill P&L per armed setup",
        "generated_at": today.isoformat(),
        "gate": "VISIBILITY ONLY (Rule 9) — never auto-disarms; disarm is a J-facing call.",
        "fills_authority": "journal/trades.csv (actual placed-and-filled paper trades, not a re-sim)",
        "setups": setups_out,
        "unmapped_armed_setups": unmapped,  # non-empty = a new arm with no ARM_DATES entry (drift)
        "cross_setup_same_day_side": cross_setup_same_day_side,
    }


def format_lines(digest: dict) -> list[str]:
    lines = []
    for setup, s in sorted(digest["setups"].items()):
        if s["n_fills"] == 0:
            lines.append(f"{setup} (armed {s['arm_date']}, {s['days_since_arm']}d ago): "
                         f"0 fills since arm — no live signal yet")
        else:
            days_note = ""
            if s["n_distinct_days"] < s["n_fills"]:
                days_note = (f" [{s['n_distinct_days']}d/{s['n_distinct_day_side_buckets']} "
                             f"day+side buckets -- {s['n_fills']} rows are NOT independent trials]")
            lines.append(f"{setup} (armed {s['arm_date']}): since-arm {s['n_fills']}tr "
                         f"${s['total_dollar_pnl']:+.2f} (${s['avg_dollar_pnl']:+.2f}/tr, "
                         f"{s['wr_pct']}% WR){days_note}")
    for c in digest.get("cross_setup_same_day_side", []):
        lines.append(f"WARNING CORRELATED: {c['date']} side={c['side']} fired in BOTH "
                     f"{'+'.join(c['setups'])} -- same underlying day-call, not independent")
    if digest.get("unmapped_armed_setups"):
        lines.append(f"⚠️ ARM_DATES missing for: {', '.join(digest['unmapped_armed_setups'])} "
                     f"(newly armed, digest can't date it — add to trade_to_learn_digest.ARM_DATES)")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="print only, do not write the JSON")
    args = ap.parse_args()

    digest = compute_since_arm()
    for line in format_lines(digest):
        print(f"[trade-to-learn] {line}", flush=True)

    if not args.dry_run:
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(digest, indent=2), encoding="utf-8")
        print(f"[trade-to-learn] wrote {OUT_JSON}", flush=True)

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
