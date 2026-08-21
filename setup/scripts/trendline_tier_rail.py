"""trendline_tier_rail.py -- standing real-fills tally for the TRENDLINE-ONLY bypass cohort.

WHY THIS EXISTS
---------------
The trendline-only bypass (backtest/lib/filters.py:1661-1672) strips bear blockers 5, 8
and 9 when `trendline_rejection` is the SOLE level-tied trigger, charging -1 score per
stripped blocker. On calm downtrends -- VIX below the gate-8 threshold -- it is the ONLY
road into a bear trade. On 2026-08-21 it fired once and the resulting wave cost the book
-$449, which is what prompted this module.

But the cohort's actual track record is CONTESTED, and that -- not today's loss -- is the
reason a standing rail is warranted. Three measurements disagree:

  1. PNL-ATTRIBUTION-2026-07-28 (quoted in heartbeat_core.py:1355-1391):
     trendline-only = -$1,830, WR 0.19, n=124, vs level-tied +$6,895 / n=66.
  2. LADDER T2 blocker-stratified re-cut (2026-08-20, LADDER-FULLHIST replay population):
     entries missing ONLY blocker 8 = -$36.79/trade, WR 22.6%, n=137.
  3. THIS module's population -- REAL BROKER FILLS, safe-2 + bold-2, 2026-07-02..2026-08-21:
     n=31, +$14.97/trade, WR 38.7%. The opposite sign.

(1) and (2) are replay/attribution populations over longer windows; (3) is real fills over
the freshest ~7 weeks. They are not the same question, and quoting whichever one suits the
argument is how a cohort stays permanently unresolved. This rail fixes ONE population --
real fills -- and reports it the same way every night.

THE HONEST READ AT BUILD TIME (2026-08-21), disclosed here so it is never overstated:
BOTH cohorts are concentration-driven, and the trendline edge does NOT survive its own
best day:

    cohort            mean/trade   DROP-BEST-DAY   WR      days positive
    trendline-only     +$14.97       -$1.88       38.7%       6/15
    everything else    -$19.92      -$36.29       20.5%       5/26

So the defensible claim is NOT "the bypass is profitable". It is: on recent real fills the
bypass cohort is roughly BREAKEVEN while the rest of the book is clearly negative, and the
gap (~$34/trade after dropping each cohort's best day) persists on the same 15 sessions
(non-trendline restricted to those days: -$23.61/trade, WR 18.2%).

WHAT THIS DOES / DOES NOT DO
  Reads decisions + fills, tags positions, writes automation/state/trendline-tier-rail.json,
  and appends ONE escalation line to the Discord outbox on a transition into a triggered
  state. It never places, cancels, resizes, blocks, or edits params. It is a measurement.

REVERT INSTRUCTION -- READ BEFORE PROMISING A SWITCH
  `trendline_bypass_scope` (filters.py:1436) is a BACKTEST-ONLY knob. It appears in no
  params.json, is not plumbed through orchestrator.py, and is not in engine_cli's
  passthrough -- production ALWAYS runs "trendline_only". There is therefore NO one-line
  live revert for the bypass today. The live-reachable lever is `midday_trendline_gate`
  (backtest/lib/engine/gates.py:361-369, currently false in both params files), which
  blocks trendline-only entries between 11:30 and 14:00 ET. Saying otherwise would be
  promising a switch that does not exist.

KNOWN POPULATION DIVERGENCE (pinned by the guards)
  gates.py's `_is_tl_only` uses `len(trigs) == 1`; filters.py's `_trendline_only_shape`
  additionally permits a co-occurring `ribbon_flip`. This module measures the STRICT shape
  (triggers == ["trendline_rejection"]) because that is what joins cleanly to fills. The
  looser filters.py population is therefore a superset; do not conflate the two.

Structure, escalation-dedup idiom, atomic write and fail-open contract are copied
deliberately from setup/scripts/bold_tier_rail.py -- the rail that fired correctly on the
ATM strike tier and was honoured.

USAGE
    backtest/.venv/Scripts/python.exe setup/scripts/trendline_tier_rail.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))
sys.path.insert(0, str(REPO / "setup" / "scripts"))

DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
OUT_JSON = REPO / "automation" / "state" / "trendline-tier-rail.json"
OUTBOX = REPO / "automation" / "state" / "discord-outbox.jsonl"

ARMS = ("safe-2", "bold-2")
COHORT_TRIGGERS = ["trendline_rejection"]     # STRICT shape; see docstring
ESCALATION_N = 20                             # mirrors bold_tier_rail

# The cohort escalates only when its DROP-BEST-DAY mean is worse than this. A raw-net
# threshold would fire on a single bad session and, worse, would have read "profitable"
# at build time purely because one 2026-08-20 session contributed 110% of the net.
DROP_BEST_MEAN_FLOOR = -25.0

REVERT_INSTRUCTION = (
    "There is NO one-line live revert: trendline_bypass_scope (filters.py:1436) is "
    "backtest-only and production always runs 'trendline_only'. The live lever is "
    "midday_trendline_gate (gates.py:361-369, currently false), which blocks "
    "trendline-only entries 11:30-14:00 ET. Arming it is a live behaviour change and "
    "needs OP-11 gates, not a flip."
)


def _et_now():
    from et_clock import et_now
    return et_now()


# ------------------------------------------------------------------ pure layer
def cohort_stats(positions: list) -> dict:
    """n / net / mean / WR / drop-best-day, from a list of reconstructed positions."""
    if not positions:
        return {"n": 0, "net_usd": 0.0, "mean_usd": None, "win_rate": None,
                "days": 0, "days_positive": 0, "drop_best_day_net_usd": None,
                "drop_best_day_mean_usd": None, "top_day": None,
                "top3_share_of_net": None}
    pnl = [p["actual_exit_pnl"] for p in positions]
    by_day: dict = {}
    for p in positions:
        by_day[p["date_et"]] = by_day.get(p["date_et"], 0.0) + p["actual_exit_pnl"]
    net = sum(pnl)
    top_day = max(by_day, key=by_day.get)
    rest = [p["actual_exit_pnl"] for p in positions if p["date_et"] != top_day]
    top3 = sorted(by_day.values(), reverse=True)[:3]
    return {
        "n": len(pnl),
        "net_usd": round(net, 2),
        "mean_usd": round(net / len(pnl), 2),
        "win_rate": round(sum(1 for v in pnl if v > 0) / len(pnl), 4),
        "days": len(by_day),
        "days_positive": sum(1 for v in by_day.values() if v > 0),
        # Concentration is reported WITH the headline, never after it. At build time the
        # raw net read +$464 while drop-best-day read -$49 -- the same number, two stories.
        "drop_best_day_net_usd": round(sum(rest), 2) if rest else None,
        "drop_best_day_mean_usd": round(sum(rest) / len(rest), 2) if rest else None,
        "top_day": top_day,
        "top3_share_of_net": round(sum(top3) / net, 3) if net else None,
    }


def rail_status(stats: dict, escalation_n: int = ESCALATION_N,
                floor: float = DROP_BEST_MEAN_FLOOR) -> str:
    """NO_DATA / ACCRUING / TRIGGERED_NEGATIVE / HOLDING.

    Judged on the DROP-BEST-DAY mean, not raw net: a cohort whose entire result rests on
    one session has not demonstrated anything, in either direction.
    """
    if stats["n"] == 0:
        return "NO_DATA"
    if stats["n"] < escalation_n:
        return "ACCRUING"
    dbm = stats.get("drop_best_day_mean_usd")
    if dbm is None:
        return "ACCRUING"
    return "TRIGGERED_NEGATIVE" if dbm <= floor else "HOLDING"


def verdict_line(tl: dict, other: dict, status: str) -> str:
    if tl["n"] == 0:
        return "No trendline-only fills on record yet."
    # drop_best_day_* is None when the cohort spans a SINGLE session -- there is no "rest"
    # to keep. Formatting it blindly crashed the whole rail on a one-day cohort, which is
    # precisely the state it is in on day one of any new tier. Say "n/a (single session)"
    # rather than pretending a drop-best number exists.
    def _db(s):
        v = s.get("drop_best_day_mean_usd")
        return f"${v:+.2f}/trade" if v is not None else "n/a (single session)"

    base = (f"TRENDLINE-only cohort: n={tl['n']} over {tl['days']} sessions, "
            f"${tl['net_usd']:+,.0f} net (${tl['mean_usd']:+.2f}/trade, WR "
            f"{tl['win_rate']:.1%}); DROP-BEST-DAY {_db(tl)}.")
    if other["n"]:
        base += (f" Rest of book: ${other['mean_usd']:+.2f}/trade "
                 f"(drop-best {_db(other)}), WR {other['win_rate']:.1%}.")
    if status == "TRIGGERED_NEGATIVE":
        base += " RAIL TRIGGERED: the cohort is negative even after dropping its best session."
    elif status == "ACCRUING":
        base += f" Accruing to n={ESCALATION_N}."
    else:
        base += " Holding -- not negative on a drop-best-day basis."
    return base


def build_report(tl_positions: list, other_positions: list, *, generated_at_et: str,
                 prior: dict | None = None, escalation_n: int = ESCALATION_N) -> dict:
    tl = cohort_stats(tl_positions)
    other = cohort_stats(other_positions)

    # Same-window comparison: the cohorts span different date ranges, so the raw means are
    # not directly comparable. Restrict the rest of the book to the trendline cohort's own
    # sessions before claiming any gap between them.
    tl_days = {p["date_et"] for p in tl_positions}
    other_same = cohort_stats([p for p in other_positions if p["date_et"] in tl_days])

    status = rail_status(tl, escalation_n)
    prior_status = (prior or {}).get("escalation", {}).get("last_escalated_status")
    escalate = status == "TRIGGERED_NEGATIVE" and prior_status != "TRIGGERED_NEGATIVE"

    esc = {"posted_this_run": False,
           "last_escalated_status": status,
           "finding": None, "posted_at_et": None,
           "revert_instruction": REVERT_INSTRUCTION}
    if escalate:
        esc["finding"] = (
            f"TRENDLINE-TIER RAIL TRIGGERED. {verdict_line(tl, other, status)} "
            f"{REVERT_INSTRUCTION}"
        )
        esc["posted_at_et"] = generated_at_et
        esc["posted_this_run"] = True
    elif prior_status == status and (prior or {}).get("escalation", {}).get("finding"):
        esc["finding"] = prior["escalation"]["finding"]
        esc["posted_at_et"] = prior["escalation"].get("posted_at_et")

    return {
        "_doc": "Standing real-fills tally for the trendline-only bypass cohort. "
                "See setup/scripts/trendline_tier_rail.py docstring for the three "
                "conflicting prior measurements and why this one fixes ONE population.",
        "generated_at_et": generated_at_et,
        "population": {
            "decisions": "automation/state/core-decisions.jsonl",
            "fills": "automation/state/fills-ledger.jsonl",
            "arms": list(ARMS),
            "cohort_rule": 'action=="PLACED" AND triggers==["trendline_rejection"] (STRICT)',
            "join": "decision exec.broker.id (+ extra_exec[].exec.broker.id) == fills order_id",
            "position_def": "exit_shape_parity_study.reconstruct_positions",
            "note": "filters.py's bypass shape also permits a co-occurring ribbon_flip, so "
                    "this STRICT population is a subset. gates.py uses len(trigs)==1.",
        },
        "escalation_n": escalation_n,
        "drop_best_mean_floor": DROP_BEST_MEAN_FLOOR,
        "trendline_only": tl,
        "rest_of_book": other,
        "rest_of_book_same_sessions": other_same,
        "rail_status": status,
        "verdict": verdict_line(tl, other, status),
        "escalation": esc,
        "warnings": [
            "Concentration is severe in BOTH cohorts -- always read drop_best_day_mean_usd, "
            "never net_usd alone.",
            "Real fills only. Contradicts two replay/attribution populations "
            "(PNL-ATTRIBUTION-2026-07-28; LADDER T2 2026-08-20) that measured different "
            "windows and different definitions -- see the module docstring.",
            "SHADOW: this rail never blocks, sizes, or edits params.",
        ],
    }


# ------------------------------------------------------------------ I/O layer
def load_cohorts(decisions: Path = DECISIONS, ledger: Path = LEDGER, arms=ARMS):
    """(trendline_positions, other_positions). Fail-open: any failure -> ([], [])."""
    try:
        import exit_shape_parity_study as esp
    except Exception:                                    # noqa: BLE001
        return [], []
    tl_orders = set()
    try:
        with decisions.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("action") != "PLACED" or r.get("triggers") != COHORT_TRIGGERS:
                    continue
                # extra_exec carries the SECOND leg of a multi-setup tick. Skipping it
                # silently drops half the cohort.
                for ex in [r.get("exec")] + [x.get("exec") for x in (r.get("extra_exec") or [])]:
                    oid = ((ex or {}).get("broker") or {}).get("id")
                    if oid:
                        tl_orders.add(oid)
    except OSError:
        return [], []
    try:
        fills = esp.load_fleet_engine_fills(ledger, arms=tuple(arms))
        positions = esp.reconstruct_positions(fills)
    except Exception:                                    # noqa: BLE001
        return [], []
    # reconstruct_positions does not carry order_id, but the entry ts_utc is taken verbatim
    # from the first BUY fill -- so (arm, symbol, entry_ts_utc) is a reliable back-pointer.
    # Building the map here rather than editing the shared loader keeps bold_tier_rail's
    # frozen regression anchor untouched.
    buys = {f["order_id"]: f for f in fills if f.get("side") == "buy"}
    keys = {(buys[o]["arm"], buys[o]["symbol"], buys[o]["ts_utc"])
            for o in (tl_orders & set(buys))}
    tl = [p for p in positions if (p["arm"], p["symbol"], p["entry_ts_utc"]) in keys]
    other = [p for p in positions if (p["arm"], p["symbol"], p["entry_ts_utc"]) not in keys]
    return tl, other


def _load_prior(path: Path = OUT_JSON):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def run(out_path: Path = OUT_JSON, outbox: Path = OUTBOX, dry_run: bool = False) -> dict:
    tl, other = load_cohorts()
    report = build_report(tl, other, generated_at_et=_et_now().isoformat(timespec="seconds"),
                          prior=_load_prior(out_path))
    if dry_run:
        return report
    if report["escalation"]["posted_this_run"]:
        try:
            with outbox.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"content": report["escalation"]["finding"],
                                     "source": "trendline_tier_rail",
                                     "queued_at": report["generated_at_et"]}) + "\n")
        except OSError:
            # Roll the escalation back so the NEXT run retries, rather than recording a
            # post that never happened (bold_tier_rail's rollback, copied deliberately).
            report["escalation"]["posted_this_run"] = False
            report["escalation"]["finding"] = None
            report["escalation"]["posted_at_et"] = None
            report["escalation"]["last_escalated_status"] = \
                (_load_prior(out_path) or {}).get("escalation", {}).get("last_escalated_status")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2), encoding="utf-8")
    tmp.replace(out_path)
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    try:
        rep = run(dry_run=a.dry_run)
        print(f"[trendline-tier-rail] {rep['rail_status']} :: {rep['verdict']}")
    except Exception as exc:                             # noqa: BLE001 - never break the fire
        print(f"[trendline-tier-rail] FAILED: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
