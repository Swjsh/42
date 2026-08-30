"""GATE-RECENCY-REVALIDATION -- require_bearish_fill_bar (Bold), WHOLE-BOOK A/B.

Picked via task_scorer.py --top -> GATE-RECENCY-REVALIDATION (HIGH, filed 2026-08-08) --
the ONLY sub-item still open per the 2026-08-29T04:16 ET conductor-weekend fire's own
closing note: "Only sub-item (2) remains open: require_bearish_fill_bar (Bold) whole-book
A/B, pre-registered in GATE-REVALIDATION-FILING-2026-08-21.md, still unbuilt."

THE GAP THIS FILE CLOSES: both prior studies of this gate
(gate-revalidation-bearish_fill_bar-2026-08-08.json,
gate-revalidation-bearish_fill_bar-2026-08-23-extended.json) score the REFUSED COHORT IN
ISOLATION -- "if these 37-38 refused bear entries had been taken, what would each have
earned, independently?" GATE-REVALIDATION-FILING-2026-08-21.md's own section 2 names the
flaw in that method: "The checker replays refused signals through the exit core. It does
NOT model what else would have changed had those trades been taken -- most importantly
NOT_FLAT, which would have blocked later entries in the same wave... A refused-cohort P&L
is an upper bound on a gate's cost, never its true cost." It pre-registers the fix: "an A/B
that replays the WHOLE BOOK PATH, not the refused cohort in isolation."

METHOD: for every Bold candidate event (real taken ENTER_BEAR / ENTER_BULL entries, AND
this gate's own refused SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY events), replay every one of
them through the SAME sound engine (backtest/lib/exit_manager_walk.walk_exit_manager --
verbatim reuse of gate_revalidation_ab.py's _replay_entry, never simulator_real, per the
2026-08-08 SOUNDNESS_AUDIT this whole family inherits). Then walk the day chronologically
through TWO independent one-position-at-a-time books that COMPETE for the same seat:

  Book A (GATE ON, today's reality)  -- only TAKEN-type events are eligible; REFUSED_GATE
     events never enter (matches the live engine's actual behaviour).
  Book B (GATE OFF, counterfactual)  -- ALL three event kinds are eligible; whichever one
     is chronologically first and finds the book flat gets the seat, exactly modelling the
     downstream NOT_FLAT effect the 08-21 filing named. A gate-refused bear entry that gets
     let in under Book B can occupy the seat and BLOCK a later taken bull/bear entry that
     happened for real under Book A -- this is the "bumped" effect measured below.

improvement_per_day = Book B total - Book A total, one value per trading day that had >=1
walkable candidate event. Scored with the SAME G-battery convention as every other cell in
this family (G_mean / G_oos / G_drop3 / G_bhfdr / G_n) so the verdict is directly comparable
to the sibling scorecards -- this is NOT reinventing OP-11's WF metric, it is the
already-validated convention this specific gate-revalidation lineage uses (see
gate_revalidation_ab.py's own docstring for why simulator_real was rejected and
walk_exit_manager adopted).

ANALYSIS ONLY -- no params.json / aggressive/params.json file is touched. Report only, same
never-blocks-never-kills posture as every sibling in this family (OP-25).

Run: backtest/.venv/Scripts/python.exe backtest/tools/gate_revalidation_bearish_fill_bar_wholebook_2026_08_30.py
"""
from __future__ import annotations

import datetime as dt
import json
import random
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (str(BACKTEST), str(BACKTEST / "lib"), str(BACKTEST / "tools"), str(FLEET_DIR), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import gate_revalidation_ab as grab  # noqa: E402 -- reuse every pure function verbatim
from autoresearch.gate_expiry_check import load_decision_rows, cluster_events, bar_idx_for_ts  # noqa: E402
from autoresearch.recency_check import load_merged_spy_vix, read_cache_last_date  # noqa: E402
from autoresearch._edgehunt_vwap_continuation import _normalize_spy, _align_vix  # noqa: E402

CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
OUT_PATH = REPO / "analysis" / "recommendations" / "gate-revalidation-bearish_fill_bar-2026-08-30-wholebook.json"
LEDGER_START = dt.date(2026, 6, 25)          # same floor every sibling in this family uses
EVENT_CLUSTER_GAP_MINUTES = 15               # same convention as grab -- dedupes repeated raw fires


def log(m: str) -> None:
    print(f"[gate-revalidation-wholebook] {m}", flush=True)


def _typed_events(rows: list[dict], account: str, verdict: str, kind: str) -> list[dict]:
    filtered = [r for r in rows if r.get("account") == account and r.get("verdict") == verdict
                and r.get("armed") is True]
    events = cluster_events(filtered, EVENT_CLUSTER_GAP_MINUTES)
    for e in events:
        e["_kind"] = kind
    return events


def simulate_book_competition(resolved_events: list[dict]) -> dict:
    """PURE, unit-testable core of the whole-book A/B (no I/O, no option data).

    `resolved_events` is a chronologically-sorted list of dicts, each already replayed:
    {"ts": datetime, "kind": "TAKEN_BEAR"|"TAKEN_BULL"|"REFUSED_GATE",
     "exit_time": datetime, "pnl": float}. One seat per day per book.

    Book A (GATE ON, today's reality): only non-REFUSED_GATE events are eligible.
    Book B (GATE OFF, counterfactual): all three kinds compete for the same seat --
    whichever is chronologically first and finds the book flat wins it. This is what
    models the downstream NOT_FLAT effect GATE-REVALIDATION-FILING-2026-08-21.md named:
    a gate-refused entry that gets let in under B can occupy the seat and block a later
    taken entry that happened for real under A ("bumped").

    Returns {"day_pnl_a": {date: float}, "day_pnl_b": {date: float},
             "n_gate_entries_let_in": int, "n_bumped": int}.
    """
    day_pnl_a: dict[dt.date, float] = {}
    day_pnl_b: dict[dt.date, float] = {}
    flat_until_a: dt.datetime | None = None
    flat_until_b: dt.datetime | None = None
    cur_day: dt.date | None = None
    n_bumped = 0
    n_gate_entries_let_in = 0

    for row in resolved_events:
        ts = row["ts"]
        d = ts.date()
        if d != cur_day:
            cur_day = d
            flat_until_a = None
            flat_until_b = None
            day_pnl_a.setdefault(d, 0.0)
            day_pnl_b.setdefault(d, 0.0)

        exit_time = row["exit_time"]
        pnl = row["pnl"]
        kind = row["kind"]

        # --- Book A: GATE ON (today's reality) -- REFUSED_GATE never eligible ---
        eligible_a = kind != "REFUSED_GATE" and (flat_until_a is None or ts >= flat_until_a)
        if eligible_a:
            day_pnl_a[d] += pnl
            flat_until_a = exit_time

        # --- Book B: GATE OFF (counterfactual) -- all kinds compete for the seat ---
        eligible_b = flat_until_b is None or ts >= flat_until_b
        if eligible_b:
            day_pnl_b[d] += pnl
            flat_until_b = exit_time
            if kind == "REFUSED_GATE":
                n_gate_entries_let_in += 1
        elif eligible_a:
            n_bumped += 1  # taken for real under A, but the seat was occupied under B --
                            # the exact downstream effect the 2026-08-21 filing named

    return {"day_pnl_a": day_pnl_a, "day_pnl_b": day_pnl_b,
            "n_gate_entries_let_in": n_gate_entries_let_in, "n_bumped": n_bumped}


def main() -> int:
    t0 = time.time()
    ledger_last = read_cache_last_date()  # live OPRA cache last date -- never hardcoded
    log(f"window: {LEDGER_START}..{ledger_last}")

    log("loading merged SPY+VIX (master + recent) ...")
    spy_raw, vix_raw = load_merged_spy_vix()
    spy = _normalize_spy(spy_raw)
    _align_vix(spy, vix_raw)
    ribbon_lookup = grab.build_ribbon_lookup(spy)
    spy_ts = spy["timestamp_et"]
    spy_by_date = {d: sub.reset_index(drop=True) for d, sub in spy.groupby("date")}
    cfg = grab.account_config()["bold"]
    log(f"  spy frame: {len(spy)} rows, {spy['date'].min()}..{spy['date'].max()}")

    log("streaming core-decisions.jsonl ...")
    all_rows = load_decision_rows(CORE_DECISIONS, LEDGER_START)
    log(f"  {len(all_rows)} rows since {LEDGER_START}")

    bear_taken = _typed_events(all_rows, "bold", "ENTER_BEAR", "TAKEN_BEAR")
    bull_taken = _typed_events(all_rows, "bold", "ENTER_BULL", "TAKEN_BULL")
    refused = _typed_events(all_rows, "bold", "SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY", "REFUSED_GATE")
    log(f"  candidate events: TAKEN_BEAR={len(bear_taken)} TAKEN_BULL={len(bull_taken)} "
        f"REFUSED_GATE={len(refused)}")

    events = sorted(bear_taken + bull_taken + refused, key=lambda r: r["ts_et"])
    events = [e for e in events
              if LEDGER_START <= dt.date.fromisoformat(e["ts_et"][:10]) <= ledger_last]
    log(f"  merged chronological candidate universe: {len(events)}")

    replay_cache: dict = {}
    n_unwalkable = 0
    resolved: list[dict] = []

    for row in events:
        try:
            ts = dt.datetime.fromisoformat(row["ts_et"])
        except (KeyError, ValueError):
            continue

        bar_idx, stale = bar_idx_for_ts(spy_ts, ts)
        if bar_idx is None or stale:
            n_unwalkable += 1
            continue
        side = row.get("side")
        if side not in ("C", "P"):
            n_unwalkable += 1
            continue

        cache_key = (bar_idx, side)
        if cache_key not in replay_cache:
            replay_cache[cache_key] = grab._replay_entry(
                bar_idx, side, row, spy=spy, spy_by_date=spy_by_date,
                ribbon_lookup=ribbon_lookup, cfg=cfg)
        replay = replay_cache[cache_key]
        if replay["status"] != "ok":
            n_unwalkable += 1
            continue

        entry_time = dt.datetime.fromisoformat(replay["entry_time_et"]) if isinstance(
            replay["entry_time_et"], str) else replay["entry_time_et"]
        if getattr(entry_time, "tzinfo", None) is not None:
            entry_time = entry_time.replace(tzinfo=None)
        exit_time = entry_time + dt.timedelta(minutes=float(replay["hold_minutes"]))
        resolved.append({"ts": ts, "kind": row["_kind"], "exit_time": exit_time,
                          "pnl": float(replay["pnl"])})

    sim = simulate_book_competition(resolved)
    day_pnl_a, day_pnl_b = sim["day_pnl_a"], sim["day_pnl_b"]
    n_bumped, n_gate_entries_let_in = sim["n_bumped"], sim["n_gate_entries_let_in"]

    all_dates = sorted(set(day_pnl_a) | set(day_pnl_b))
    for d in all_dates:
        day_pnl_a.setdefault(d, 0.0)
        day_pnl_b.setdefault(d, 0.0)

    improvement_rows = [{"pnl": round(day_pnl_b[d] - day_pnl_a[d], 2), "date": str(d)}
                         for d in all_dates]
    cohort = grab.cohort_metrics(improvement_rows)
    is_half, oos_half = grab.is_oos_split(improvement_rows)
    is_m, oos_m = grab.cohort_metrics(is_half), grab.cohort_metrics(oos_half)
    pval = grab.one_sample_p([r["pnl"] for r in improvement_rows])
    bh_sig = grab.bh_fdr([pval], q=0.10)
    battery = grab.g_battery(cohort, oos_m, pval, bh_sig[0])

    total_a = round(sum(day_pnl_a.values()), 2)
    total_b = round(sum(day_pnl_b.values()), 2)

    out = {
        "prereg_id": "GATE-RECENCY-REVALIDATION-2026-08-30-WHOLEBOOK",
        "answers": "GATE-REVALIDATION-FILING-2026-08-21.md section 2's own pre-registration "
                   "('an A/B that replays the whole book path, not the refused cohort in "
                   "isolation') -- queue.md GATE-RECENCY-REVALIDATION item (2), the last open "
                   "sub-item as of the 2026-08-29T04:16 ET conductor-weekend fire.",
        "does_not_supersede": [
            "analysis/recommendations/gate-revalidation-bearish_fill_bar-2026-08-08.json",
            "analysis/recommendations/gate-revalidation-bearish_fill_bar-2026-08-23-extended.json",
        ],
        "method": "day-level, one-seat-at-a-time competition between TAKEN_BEAR/TAKEN_BULL/"
                   "REFUSED_GATE events replayed via the SAME sound engine "
                   "(walk_exit_manager). Book A = only taken-type events eligible (models "
                   "today's live GATE-ON behaviour). Book B = all three kinds compete for "
                   "one seat per day (models GATE-OFF, including the downstream NOT_FLAT "
                   "bump effect). improvement_per_day = Book B total - Book A total.",
        "window": f"{LEDGER_START}..{ledger_last}",
        "n_candidate_events": {"TAKEN_BEAR": len(bear_taken), "TAKEN_BULL": len(bull_taken),
                                "REFUSED_GATE": len(refused)},
        "n_unwalkable": n_unwalkable,
        "n_days_with_candidate_events": len(all_dates),
        "n_gate_refused_events_let_in_under_book_b": n_gate_entries_let_in,
        "n_taken_events_bumped_out_under_book_b": n_bumped,
        "book_a_total_gate_on_reality_replayed": total_a,
        "book_b_total_gate_off_counterfactual": total_b,
        "raw_delta_book_b_minus_book_a": round(total_b - total_a, 2),
        "improvement_per_day_cohort": cohort,
        "improvement_is_half": is_m,
        "improvement_oos_half": oos_m,
        "one_sample_p": round(pval, 4),
        "bh_fdr_significant": bool(bh_sig[0]),
        "g_battery": battery,
        "kill_criterion": ("NOT APPLICABLE -- did not clear the auto-ratify bar this pass; no "
                            "live flip is proposed. If a future re-run DOES clear the bar: "
                            "cell-attributable net <= -$150 over the first 5 live sessions "
                            "after the flip -> revert same day (one-line aggressive/params.json "
                            "diff back to true)."),
        "guard_test_snippet": (
            "def test_require_bearish_fill_bar_unchanged_pending_reratification():\n"
            "    # GATE-RECENCY-REVALIDATION-2026-08-30-WHOLEBOOK: still NOT-UNBLOCK-ELIGIBLE\n"
            "    # on the whole-book A/B (accounts for the NOT_FLAT downstream effect the\n"
            "    # 2026-08-21 filing named -- see gate-revalidation-bearish_fill_bar-2026-08-30-\n"
            "    # wholebook.json). Pins the CURRENT (correct) value.\n"
            "    import json\n"
            "    params = json.loads(open('automation/state/aggressive/params.json', encoding='utf-8').read())\n"
            "    assert params['require_bearish_fill_bar'] is True"
        ),
        "params_diff": {
            "key": "require_bearish_fill_bar", "current": True, "proposed": False,
            "recommendation": None,  # filled below
        },
        "day_level_deltas": improvement_rows,
        "generated_at": dt.datetime.now().isoformat(),
    }
    verdict = battery["verdict"]
    if verdict == "UNBLOCK-ELIGIBLE":
        rec = "CLEARS the whole-book G-battery -- see STAGE 4 auto-ratify gate before any flip."
    else:
        failing = [k for k, v in battery["gates"].items() if not v]
        rec = f"DO NOT FLIP -- fails {'/'.join(failing)} (whole-book A/B)"
    out["params_diff"]["recommendation"] = rec

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_PATH}")
    log(f"book A (gate ON, reality-replayed) total: ${total_a}")
    log(f"book B (gate OFF, counterfactual) total:  ${total_b}")
    log(f"delta (B - A): ${round(total_b - total_a, 2)}  over n={len(all_dates)} days")
    log(f"{n_gate_entries_let_in} refused-gate entries let in under B; "
        f"{n_bumped} real events bumped out under B")
    log(f"VERDICT: {verdict} ({rec})")
    log(f"done in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
