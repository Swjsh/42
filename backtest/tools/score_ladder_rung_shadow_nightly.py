"""score_ladder_rung_shadow_nightly.py -- $0 nightly forward clock for LANE 1
(SCORE-LADDER-RUNG: single-demerit, bull-only, rungs risky-3=7 / risky-1=8; prereg
a780122e, runner 3b3072a9).

WHY THIS EXISTS (2026-08-07 evening HOLD decision -- full writeup:
analysis/deep-research/CLOSE-EXECUTION-2026-08-07.md): the frozen ship gate required BOTH
(a) week-added P&L > 0 on the real Friday cell (it was: +$1,866 = Mon-Thu's already-real
+$2,811 plus Friday's real -$945) AND (b) Friday not materially worse under the ladder than
without it. (a) passed. (b) FAILED hard: same-day binary_day_pnl was +$80 vs
ladder_day_pnl -$865 (a $945 swing attributable to the rescue lane ALONE, -17.7% of SOD
equity in one session) on 57 admitted rescue signals -- the HIGHEST admission count of the
week, above Wednesday's already-disclosed "chop bleeds" 19 and Thursday's 30. The one
headline anecdote (the 10:15 entry J's complaint was about) DID work (+$115, exited via
ribbon_flip_back one minute later -- NOT a catastrophe-cap death, NOT a missed TP1); the
day lost because of the other 56 admitted signals, mostly 1-minute round trips through a
choppy, twice-reversing tape. The patch is HELD, NOT applied -- accounts.json carries no
score_ladder_rung key, byte-identical binary behavior in production tonight.

THIS SCRIPT changes NOTHING on the live trading path, ever. It is pure forward
measurement: replay LANE 1's exact frozen admission rule against a day's REAL core-decisions
ledger + REAL OPRA bars (never EST -- by the time this fires, ~16:40 ET, same-day OPRA is
long unlocked) and append one row per LANE-1 arm to an append-only ledger. Nothing here
reads or writes accounts.json, places an order, or touches any live-config surface.

C14 (no drifted second copy): admission/walk logic is IMPORTED from
ladder_rung_replay_2026_08_07 (rung_admits, tick_events, load_core_rows, arm_day_config,
DayBars, walk_day, ARMS) -- this file is a thin nightly driver over the SAME mechanism the
ship-gate harness used, never a reimplementation that could quietly diverge from it.

Forward re-decision bar (frozen here, before any forward data, symmetric to LANE 2's own
staged bar): after >=10 further real sessions in this ledger, reconsider arming ONLY if (a)
extras (added_pnl) net > 0 across those sessions, (b) no single session worse than -$500 at
this replay's qty=5, (c) negative-extras sessions average no worse than -$300. Today
(2026-08-07, -$945) is session 1 of that forward count and, on its own, already breaches (b).

Usage: backtest/.venv/Scripts/python.exe backtest/tools/score_ladder_rung_shadow_nightly.py [--date YYYY-MM-DD]
Writes: analysis/arm-ladder/ladder-rung-shadow-ledger.jsonl (append-only, analysis-only)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

BACKTEST = Path(__file__).resolve().parents[1]
ROOT = BACKTEST.parent
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT), str(BACKTEST), str(BACKTEST / "tools"), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ladder_rung_replay_2026_08_07 as lrr  # noqa: E402

# Re-exported (not copied) for the C14 identity guard + any future caller.
rung_admits = lrr.rung_admits
walk_day = lrr.walk_day
DayBars = lrr.DayBars
ARMS = lrr.ARMS

# BULL-ONLY, matching the exact HELD ship variant (--sides C in the gate-decision run) --
# NOT the module's own default {"C", "P"}. lrr.walk_day() reads ALLOWED_RESCUE_SIDES as a
# plain module GLOBAL rather than a parameter (lrr.main() sets it from argparse before
# calling run_ledger_mode); a caller that imports walk_day directly without also setting
# this global silently gets the wrong (both-sides) admission set. CAUGHT LIVE this session
# (2026-08-07): an ad-hoc diagnostic call that skipped this line admitted bear (P) rescues
# too, which occupied the one-position slot and changed which bull rescues fired --
# risky-3 read n_added=40/added_pnl=-$1,284.10 instead of the correct bull-only
# n_added=57/added_pnl=-$945.00 that both official `--sides C` CLI runs reproduced
# identically. Setting it explicitly here, at import time, is the fix: every caller of this
# module (including the guard test) gets the correct bull-only mechanism with no
# action of its own required.
lrr.ALLOWED_RESCUE_SIDES = {"C"}

LEDGER_OUT = ROOT / "analysis" / "arm-ladder" / "ladder-rung-shadow-ledger.jsonl"

# Forward re-decision bar (see module docstring) -- recorded here, not just in prose, so a
# future reader can grep the number instead of re-deriving it from a paragraph.
FORWARD_BAR = {"min_sessions": 10, "extras_net_gt": 0.0, "no_session_worse_than": -500.0,
               "negative_session_avg_no_worse_than": -300.0, "qty": lrr.QTY_LEDGER}


def run_for_date(date_iso: str, retally: bool = False) -> int:
    """Replay LANE 1's frozen rule for ONE date on real OPRA, append per-arm rows. Returns
    0 always (fail-open) -- a no-data date (weekend/holiday, or a day whose safe-account
    ledger hasn't landed yet) is a silent no-op, not an error."""
    core = lrr.load_core_rows(date_iso)
    if not core:
        print(f"[ladder-rung-shadow] no safe-account core rows for {date_iso} -- no-op "
              "(weekend/holiday or not-yet-landed)")
        return 0

    # This is a post-close (~16:40 ET) nightly fire by design -- same-day OPRA is always
    # unlocked by the time it runs, so it always prices real, same as the harness's --no-est
    # flag. lrr.EST_DATES is module-global state (defaults to {"2026-08-07"}, the one day
    # that needed an EST fallback while the market was still open); discard defensively
    # rather than .clear() so a future date accidentally left in that default set never
    # silently EST-prices a shadow row.
    lrr.EST_DATES.discard(date_iso)
    events = lrr.tick_events(core)
    bars = lrr.DayBars(date_iso, core)  # est=False whenever date_iso is not in EST_DATES
    if bars.est:
        # Should never happen for a nightly post-close fire, but fail LOUD rather than
        # silently write an EST-priced row into what must always be a real-OPRA ledger.
        print(f"[ladder-rung-shadow] REFUSING {date_iso}: DayBars resolved EST pricing "
              "(same-day OPRA not yet unlocked?) -- run again after ~16:21 ET")
        return 0

    LEDGER_OUT.parent.mkdir(parents=True, exist_ok=True)
    already = existing_keys()
    todo = [a for a in lrr.ARMS if (date_iso, a["id"]) not in already]
    if not todo and not retally:
        print(f"[ladder-rung-shadow] {date_iso} already tallied for "
              f"{', '.join(a['id'] for a in lrr.ARMS)} -- refusing to duplicate. "
              "Pass --retally to append a superseding row.")
        return 0
    if retally:
        todo = list(lrr.ARMS)
    rows_written = 0
    with open(LEDGER_OUT, "a", encoding="utf-8") as f:
        for arm in todo:
            cfg = lrr.arm_day_config(arm["id"], date_iso)
            binary = lrr.walk_day(arm, events, bars, cfg, include_rescues=False, qty=lrr.QTY_LEDGER)
            ladder = lrr.walk_day(arm, events, bars, cfg, include_rescues=True, qty=lrr.QTY_LEDGER)
            added = [t for t in ladder["trades"] if t["lane"] == "rescue"]
            row = {
                "date": date_iso, "arm_id": arm["id"], "rung": arm["rung"],
                "tallied_at": dt.datetime.now().isoformat(),
                "est": bars.est, "n_added": len(added),
                "added_pnl": round(sum(t["dollar_pnl"] for t in added), 2),
                "binary_day_pnl": binary["day_pnl"], "ladder_day_pnl": ladder["day_pnl"],
                "delta_pnl": round(ladder["day_pnl"] - binary["day_pnl"], 2),
                "sod_equity": cfg.get("sod_equity"), "pdt_enforced": cfg.get("pdt_enforced"),
                "prereg": "analysis/recommendations/prereg-score-ladder-rung-2026-08-07.md (a780122e)",
                "hold_decision": "analysis/deep-research/CLOSE-EXECUTION-2026-08-07.md",
                # Marks a deliberate re-tally so read_deduped's last-wins rule is
                # auditable rather than accidental.
                "supersedes_prior": bool(retally and (date_iso, arm["id"]) in already),
            }
            f.write(json.dumps(row, default=str) + "\n")
            rows_written += 1
            print(f"[ladder-rung-shadow] {date_iso} {arm['id']} rung={arm['rung']}: "
                  f"n_added={row['n_added']} added_pnl=${row['added_pnl']:+.2f} "
                  f"delta_pnl=${row['delta_pnl']:+.2f}")
    print(f"[ladder-rung-shadow] appended {rows_written} row(s) to {LEDGER_OUT}")
    return 0



# --- IDEMPOTENCY (T6, 2026-08-20) --------------------------------------------
# The tally appended unconditionally, so every re-run of a date wrote duplicate
# rows: 2026-08-07 landed EIGHT times and 08-13 twice. Raw cumulative added_pnl
# read -$21,735 against a deduped ~-$3,380 / -$3,235 — a 6x inflation for anyone
# summing the file naively. The VERDICT never changed (8 of 9 live days negative),
# but a shadow whose own bookkeeping is wrong cannot be allowed to gate anything.
#
# History is NOT rewritten: this ledger is append-only by doctrine and the dupes
# are an honest record of re-runs. Instead: refuse to re-append by default, and
# give every consumer read_deduped() so naive summing is impossible to get wrong.

def existing_keys(path: Path = None) -> set:
    """(date, arm_id) pairs already tallied."""
    p = path or LEDGER_OUT
    keys = set()
    try:
        for line in p.open(encoding="utf-8", errors="replace"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("date") and r.get("arm_id"):
                keys.add((r["date"], r["arm_id"]))
    except OSError:
        pass
    return keys


def read_deduped(path: Path = None) -> list:
    """Ledger rows with one entry per (date, arm_id) — the LAST tally wins.

    Use this anywhere you would otherwise sum the raw file. The raw file is the
    audit trail; this is the answer.
    """
    p = path or LEDGER_OUT
    latest = {}
    try:
        for line in p.open(encoding="utf-8", errors="replace"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            k = (r.get("date"), r.get("arm_id"))
            if k[0] and k[1]:
                latest[k] = r          # later line supersedes earlier
    except OSError:
        return []
    return [latest[k] for k in sorted(latest)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--retally", action="store_true",
                    help="append a SUPERSEDING row for a date already tallied "
                         "(default: refuse, to keep the ledger free of accidental dupes)")
    args = ap.parse_args()
    return run_for_date(args.date, retally=args.retally)


if __name__ == "__main__":
    sys.exit(main())
