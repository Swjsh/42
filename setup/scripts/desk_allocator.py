"""desk_allocator.py - the master's ALLOCATE arm, made deterministic.

THE GAP THIS CLOSES
-------------------
The centralized-orchestration pattern J drew has three jobs on the master box:
"Coordinate Task", "Interpret Worker response", "Task Reassignment and
reconfiguration". This rig had the first (conductor.md STAGE 1 picks a task) and,
since 2026-08-19, the second (worker_output_verify.py refuses fabricated
completions). It had nothing for the third.

Worse, STAGE 1 picks the next task from a FLAT global queue. With four desks
(SPY 0DTE / futures / multi-sector / prediction markets) a flat queue silently
starves whichever desk nobody happens to have written a queue item for -- which
is exactly how the futures desk's MES mirror sat at armable:true, unnoticed,
while queue items were drained elsewhere.

WHAT THIS DOES
--------------
Reads every desk's OWN scoreboard (each desk already self-scores against its own
pre-registered arming bar) and ranks which desk deserves the next fire. Pure
Python, $0, no LLM, no orders. The conductor reads the ranking; a human can too.

THE SCORING, AND WHY EACH TERM EXISTS
-------------------------------------
  DECISION_ROTTING (+100)  a desk that has CLEARED its arming bar but is not
                           armed is the single most valuable thing in the firm:
                           the work is DONE and the value is unrealised. This
                           term exists because MES mirror cleared 59/20 and
                           nothing surfaced it.
  BROKEN (+80 real / +40 shadow)  a stale or failing lane. Weighted by whether
                           the desk has real fills -- a broken desk with money on
                           it outranks a broken shadow desk (OP-33: function first).
  PROGRESS (0..+30)        proportional distance to the arming bar. A desk at
                           15/20 is worth more attention than one at 2/20.
  DEAD_SIGNAL (-50)        a desk whose signal failed its null gets DEPRIORITISED,
                           not zeroed. Polishing a corpse is this repo's
                           documented failure mode (C4/C27); but the machinery
                           may still be reusable, so it is not banned outright.
  NO_EDGE_YET (-10)        shadow desks with nothing proven yet rank below desks
                           with a live edge, all else equal.

DELIBERATELY NOT SCORED: P&L level. A desk being down is not by itself a reason
to spend the next fire on it -- that is how you get revenge-engineering. What
earns a fire is a DECISION waiting, a BREAK, or PROXIMITY to a pre-registered bar.

USAGE
  python setup/scripts/desk_allocator.py            # ranked table
  python setup/scripts/desk_allocator.py --json     # machine-readable
  python setup/scripts/desk_allocator.py --top      # just the winning desk id
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
REGISTRY = STATE / "worker-registry.json"
OUT = STATE / "desk-allocation.json"

STALE_H = 24.0          # a lane that has not written in a full day missed a session


def _age_h(p: Path):
    try:
        return (datetime.now() - datetime.fromtimestamp(p.stat().st_mtime)).total_seconds() / 3600.0
    except OSError:
        return None


def _json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _rows(p: Path) -> int:
    try:
        return sum(1 for line in p.open(encoding="utf-8", errors="replace") if line.strip())
    except OSError:
        return 0


def assess_spy() -> dict:
    cal = _json(REPO / "analysis" / "journal" / "calendar-data.json")
    s = ((cal or {}).get("views", {}).get("BOOK", {}) or {}).get("summary", {})
    broken = []
    for f in ("engine-health.json", "self-check-last.json"):
        d = _json(STATE / f)
        if d and str(d.get("verdict", "")).upper() in ("RED", "DEGRADED"):
            broken.append("%s=%s" % (f, d["verdict"]))
    return {
        "real_fills": True, "armable_unarmed": False, "dead_signal": False,
        "progress": 1.0, "broken": broken,
        "headline": "%s net over %s days" % (
            _money(s.get("total_pnl_net")), s.get("trading_days", "?")) if s else "no scoreboard",
    }


def assess_futures() -> dict:
    fut = STATE / "futures"
    lanes = ["trader/heartbeat.json", "trader-broker/heartbeat.json", "shadow-progress.json",
             "edge3-sim-progress.json", "ssr-shadow-progress.json"]
    broken = [l for l in lanes if (_age_h(fut / l) or 1e9) > STALE_H]
    mirror = _json(fut / "shadow-progress.json") or {}
    bar = mirror.get("arming_bar", {})
    have, need = bar.get("round_trips_have", 0), max(1, bar.get("round_trips_needed", 20))
    armable = bool(bar.get("armable"))
    return {
        "real_fills": False, "armable_unarmed": armable, "dead_signal": False,
        "progress": min(1.0, have / need), "broken": broken,
        "headline": "MES mirror %s/%s trips, %s%s" % (
            have, need, _money(mirror.get("total_pnl_usd")),
            ", ARMABLE" if armable else ""),
    }


def assess_multi_sector() -> dict:
    """Two lanes live here and conflating them mis-ranks the desk.

    The weekly-options v1 signal IS dead (failed its random-entry null). But
    multi-1 (Gamma_MultiCore, ~72 names, 15-min RTH shadow) is LIVE and ticking.
    Scoring the whole desk dead_signal=True applied a -50 to a desk that is
    actively gathering evidence -- found 2026-08-20 when the doc guard surfaced
    the undocumented task.
    """
    mu, wk = STATE / "multi", STATE / "weekly"
    n_multi = _rows(mu / "shadow-ledger.jsonl")
    n_weekly = _rows(wk / "variant-daily-ledger.jsonl") + _rows(wk / "expiry-experiment-shadow-ledger.jsonl")
    age = _age_h(mu / "shadow-ledger.jsonl")
    live = age is not None and age <= STALE_H
    return {
        "real_fills": False, "armable_unarmed": False,
        # dead only if the live lane is not running; the retired weekly signal
        # alone must not condemn the desk.
        "dead_signal": not live,
        "progress": min(1.0, n_multi / 20.0) if live else 0.0,
        "broken": [] if live else ["multi/shadow-ledger.jsonl stale"],
        "headline": "multi-1 %d shadow rows%s; weekly v1 killed (%d archived)" % (
            n_multi, "" if live else " STALE", n_weekly),
    }


def _kalshi_weather_scorecard(preds_path: Path) -> dict:
    """Minimal re-derivation of automation/kalshi/kalshi_auto.py#scorecard() -- kept
    INLINE (stdlib json only) rather than imported, because that module pulls in
    `requests` + `cryptography` for its live-trading path, which this allocator (by
    its own design: "Pure Python, $0, no LLM, no orders") should not need just to
    read a scorecard. Bar constants (20 days / 45% hit / 1.6F err) mirror that
    module's MIN_SCORED_DAYS / MIN_HIT_RATE / MAX_MEAN_ABS_ERR -- if either drifts,
    both must be checked (flagged in the 2026-08-21 lesson-inbox item)."""
    out: dict[str, dict] = {}
    try:
        lines = preds_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("observed") is None:
            continue
        s = out.setdefault(r.get("series", "?"), {"n": 0, "hits": 0, "err_sum": 0.0})
        s["n"] += 1
        s["hits"] += 1 if r.get("pick_won") else 0
        s["err_sum"] += r.get("abs_err", 0.0)
    for s in out.values():
        s["hit_rate"] = s["hits"] / s["n"] if s["n"] else 0.0
        s["mean_abs_err"] = s["err_sum"] / s["n"] if s["n"] else float("inf")
        s["earned"] = s["n"] >= 20 and s["hit_rate"] >= 0.45 and s["mean_abs_err"] <= 1.6
    return out


def assess_prediction_markets() -> dict:
    """DEFECT FIXED 2026-08-20: this counted rows and never asked whether the lane
    was still RUNNING. Kalshi's last tick was 10.3 DAYS old while the desk was
    being reported as a healthy shadow lane progressing toward its bar. A row
    count is a measure of history, not of life.

    SECOND DEFECT FIXED 2026-08-21: the liveness check above still read the WRONG
    producer. `last-tick.json` / `shadow-ledger.jsonl` belong to kalshi_tick.py, the
    original SPY-directional Kalshi lane -- superseded the SAME DAY (2026-08-09) by
    kalshi_auto.py, the weather lane that is the one actually scheduled
    (`Gamma_KalshiAuto`, 18:10 ET daily; confirmed via Get-ScheduledTask that no task
    for kalshi_tick.py exists at all). last-tick.json has sat frozen since 2026-08-09
    BY DESIGN (its lane was retired, not broken), so this desk was permanently
    reporting BROKEN against a dead sibling while the real lane
    (weather-predictions.jsonl) ran clean the entire time -- the SAME bug class the
    2026-08-20 fix above already caught once, on assess_multi_sector's two lanes."""
    k = STATE / "kalshi"
    preds = k / "weather-predictions.jsonl"
    age = _age_h(preds)
    live = age is not None and age <= 48        # daily lane: two missed days is dead
    card = _kalshi_weather_scorecard(preds) if live else {}
    best_n = max((c["n"] for c in card.values()), default=0)
    earned = sum(1 for c in card.values() if c.get("earned"))
    return {
        "real_fills": False, "armable_unarmed": False, "dead_signal": False,
        "progress": min(1.0, best_n / 20.0) if live else 0.0,
        "broken": [] if live else ["kalshi weather-predictions.jsonl %s" % (
            "%.0fh stale" % age if age is not None else "MISSING")],
        "headline": "%d cities scored, best n=%d/20, %d earned%s" % (
            len(card), best_n, earned, "" if live else " — LANE NOT TICKING"),
    }


ASSESSORS = {
    "spy-0dte": assess_spy,
    "futures": assess_futures,
    "multi-sector": assess_multi_sector,
    "prediction-markets": assess_prediction_markets,
}


def _money(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "?"
    return ("+$" if v >= 0 else "-$") + format(abs(v), ",.0f")


def score(a: dict) -> tuple:
    """Return (points, reasons). Reasons are the audit trail — never a bare number."""
    pts, why = 0, []
    if a["armable_unarmed"]:
        pts += 100
        why.append("+100 DECISION ROTTING: cleared its arming bar, not armed")
    if a["broken"]:
        w = 80 if a["real_fills"] else 40
        pts += w
        why.append("+%d BROKEN (%s desk): %s" % (
            w, "real-fills" if a["real_fills"] else "shadow", ", ".join(a["broken"])[:80]))
    prog = int(30 * a["progress"])
    if prog:
        pts += prog
        why.append("+%d PROGRESS toward the arming bar (%.0f%%)" % (prog, 100 * a["progress"]))
    if a["dead_signal"]:
        pts -= 50
        why.append("-50 DEAD SIGNAL: failed its null; do not polish a corpse")
    if not a["real_fills"] and not a["armable_unarmed"]:
        pts -= 10
        why.append("-10 no proven edge yet")
    return pts, why


def allocate() -> dict:
    reg = _json(REGISTRY) or {}
    rows = []
    for d in reg.get("desks", []):
        did = d.get("id")
        fn = ASSESSORS.get(did)
        if not fn:
            rows.append({"id": did, "name": d.get("name"), "points": 0,
                         "headline": "no assessor wired", "why": ["no assessor for this desk id"],
                         "status": d.get("status", "")})
            continue
        a = fn()
        pts, why = score(a)
        rows.append({"id": did, "name": d.get("name"), "points": pts,
                     "headline": a["headline"], "why": why, "status": d.get("status", ""),
                     "broken": a["broken"], "armable_unarmed": a["armable_unarmed"]})
    rows.sort(key=lambda r: -r["points"])
    return {
        "computed_at": datetime.now().isoformat(timespec="seconds"),
        "winner": rows[0]["id"] if rows else None,
        "desks": rows,
        "_doc": "Deterministic desk allocation. The master reads this to decide which desk "
                "gets the next fire, instead of draining a flat queue that structurally "
                "starves whichever desk nobody wrote a queue item for.",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Rank which trading desk deserves the next fire.")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--top", action="store_true", help="print only the winning desk id")
    a = ap.parse_args()

    res = allocate()
    try:
        OUT.write_text(json.dumps(res, indent=2), encoding="utf-8")
    except OSError:
        pass

    if a.top:
        print(res["winner"] or "")
        return 0
    if a.json:
        print(json.dumps(res, indent=2))
        return 0

    print("DESK ALLOCATION  (computed %s)" % res["computed_at"])
    print("-" * 78)
    for i, r in enumerate(res["desks"], 1):
        mark = " <- NEXT FIRE" if i == 1 else ""
        print("%d. %-22s %4d pts  %s%s" % (i, r["name"], r["points"], r["headline"][:40], mark))
        for w in r["why"]:
            print("      %s" % w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
