#!/usr/bin/env python
"""bull_trendline_reclaim_graduation_2026_08_09.py -- TASK 1 evidence refresh: does
`detect_trendline_reclaim_bullish` (backtest/lib/filters.py:944, SHADOW-LOGGED since
the 2026-07-15 fix-ship task) clear the bar to graduate from shadow to a live bull
trigger?

CONTEXT -- do not re-derive, EXTEND: `SHADOW-SIGNAL-INVENTORY-2026-07-31.md` /
`backtest/tools/shadow_signal_edge_2026_07_31.py` already ran this exact signal as a
STANDALONE-TRIGGER, real-OPRA, real-exit-manager (walk_exit_manager, RIBBON_RIDE
shape), BH-FDR, day-level-block-tested study and found:
    trendline_reclaim: n=27 (3 unbiased days: 07-20/07-21/07-22), total -$1,097
    (-$1,588 at the true -50% catastrophe cap), -$40.64/trade, WR 14.8%,
    day-level stat=-3.401 p=0.00067 (normal approx) / p=0.077 (Student-t df=2,
    the more honest small-n estimator), 3/3 days negative.
    VERDICT: SIGNIFICANT NEGATIVE -- stands unqualified, keep quarantined.

Per the standing "recency > aggregate" doctrine (J 2026-07-31: every armed/tested gate
needs a revalidation clock, not a stale aggregate), this script REFRESHES that result
with 9 additional trading days of OPRA cache that did not exist on 2026-07-31
(2026-08-03..08-07 are now cached -- verified via `ls backtest/data/opra_1m_cache`
this session) using the IDENTICAL methodology (imports `shadow_signal_edge_2026_07_31`
as a module and reuses its `fully_covered_days`, `run_one`, `day_level_test`,
`one_sample_p`, `bh_fdr`, `exit_fallback_audit`, `EXIT_SHAPE` verbatim -- only the SPY5M
window and the ledger read-window are extended; the coverage-bias-control logic,
exit-manager wiring, and stats are byte-identical to the 07-31 study).

ADDS three things the 07-31 study did not have reason to compute:
  (1) HARD-GATE DISCLOSURE for 2026-08-04 (the task's named day, +$3,624 real book P&L,
      all 5 accounts) -- an explicit, always-printed line reporting whether the signal
      fired IN SHADOW at all that day, regardless of which "unbiased" bucket it lands
      in. (Cross-checked by hand this session across core-decisions.jsonl + all 3 fleet
      ledgers before this script was written: zero firings, either date, any account --
      this script re-derives the same count from the same ledgers for a single
      reproducible artifact.)
  (2) WIDE-POPULATION FREQUENCY (391-day pinned lineage, 2025-01-02..2026-07-31, PLUS
      the truncated tail through the newest cached SPY data) via DIRECT detector replay
      -- no OPRA needed, so it is not bounded by cache coverage. Answers "how often
      would it have fired" as its own, cheaper, non-P&L number, kept separate from the
      OPRA-bounded $ figure per the 07-31 study's own scope discipline (never mix a
      frequency claim with a P&L claim from a different evidentiary basis).
  (3) STRUCTURAL note (documented, not newly re-derived): `backtest/lib/engine/
      engine_cli.py` `_derive_tier` (line ~484) reads `len(winning_triggers) >= 3` for
      the SUPER-tier bump, and `_derive_routing` (line ~465) breaks bear/bull ties by
      trigger COUNT. Wiring `trendline_reclaim` into `triggers` is therefore not
      provably inert even on trades that ALREADY qualify via a different trigger -- it
      can change TIER/SIZING or which side wins a count-tied bar. This is a citation of
      already-read code, not a new empirical test (out of scope given the P&L verdict
      below already fails; flagged for any future re-open).

$0, pure Python, offline (cached OPRA + production ledgers + cached SPY bars only).
Places no orders, edits no engine code. ANALYSIS ONLY.

Run: backtest/.venv/Scripts/python.exe backtest/tools/bull_trendline_reclaim_graduation_2026_08_09.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "setup" / "scripts"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))

from et_clock import et_now  # noqa: E402 -- this box is MOUNTAIN time; ET = local + 2h
from lib.filters import (  # noqa: E402
    detect_trendline_reclaim_bullish,
    TRENDLINE_LOOKBACK_BARS,
    TRENDLINE_MIN_SWINGS,
)

import shadow_signal_edge_2026_07_31 as sse  # noqa: E402 -- REUSE, do not re-derive

OUT = REPO / "analysis" / "deep-research" / "BULL-TRENDLINE-RECLAIM-GRADUATION-2026-08-09.json"

CORE_LEDGER = REPO / "automation" / "state" / "core-decisions.jsonl"
FLEET_LEDGERS = sorted((REPO / "automation" / "state" / "fleet").glob("*/decisions.jsonl"))
NEW_SPY5M = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-08-07.csv"
HARD_GATE_DATE = "2026-08-04"
HARD_GATE_PNL = 3624.00  # EOD-2026-08-06.md week-rollup TOTAL row, Tue 08-04, all 5 accounts

# Widest available continuous SPY 5m lineage for the frequency-only pass (no OPRA needed).
FREQ_OLD_SPY = REPO / "backtest" / "data" / "spy_5m_2025-01-01_2026-07-22.csv"
FREQ_NEW_SPY = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-08-07.csv"
FREQ_TAIL_AFTER = dt.date(2026, 7, 22)


def log(m: str) -> None:
    print(f"[bull-trendline-graduation] {m}", flush=True)


# --------------------------------------------------------------------------------- #
# Part 1: production shadow-log tally, ALL 5 real accounts, full logged window.
# Cheap (JSON field reads only, no OPRA). This is "the real-fill book" reading of the
# task's ask: the actual production ledgers that produced the actual real fills.
# --------------------------------------------------------------------------------- #
def production_tally() -> dict:
    ledgers = [("core", CORE_LEDGER)] + [(p.parent.name, p) for p in FLEET_LEDGERS]
    per_day: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    accounts_seen: set[str] = set()
    date_min, date_max = None, None
    for arm_label, path in ledgers:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = r.get("ts_et") or ""
                if len(ts) < 10:
                    continue
                d = ts[:10]
                date_min = d if date_min is None else min(date_min, d)
                date_max = d if date_max is None else max(date_max, d)
                acct = r.get("account") or r.get("arm_id") or arm_label
                accounts_seen.add(acct)
                bucket = per_day[d]
                bucket["rows"] += 1
                fired = r.get("shadow_triggers_fired") or []
                if "trendline_reclaim" in fired:
                    bucket["trendline_reclaim_shadow"] += 1
                if r.get("action") == "ENTER_BULL" or (r.get("verdict") == "ENTER" and r.get("side") == "C"):
                    bucket["real_enter_bull"] += 1

    total_rows = sum(v["rows"] for v in per_day.values())
    total_tl = sum(v["trendline_reclaim_shadow"] for v in per_day.values())
    total_enter = sum(v["real_enter_bull"] for v in per_day.values())
    days_with_fire = sorted(d for d, v in per_day.items() if v["trendline_reclaim_shadow"] > 0)

    hard_gate = per_day.get(HARD_GATE_DATE, {"rows": 0, "trendline_reclaim_shadow": 0, "real_enter_bull": 0})
    monday_before = per_day.get("2026-08-03", {"rows": 0, "trendline_reclaim_shadow": 0, "real_enter_bull": 0})

    return dict(
        accounts_scanned=sorted(accounts_seen),
        ledgers_scanned=[str(p.relative_to(REPO)).replace("\\", "/") for _, p in ledgers if p.exists()],
        window=[date_min, date_max],
        n_trading_days_logged=len(per_day),
        total_rows=total_rows,
        total_trendline_reclaim_shadow_fires=total_tl,
        total_real_enter_bull=total_enter,
        fires_per_row_pct=round(100.0 * total_tl / max(1, total_rows), 3),
        days_with_at_least_one_fire=days_with_fire,
        n_days_with_fire=len(days_with_fire),
        hard_gate_day=dict(date=HARD_GATE_DATE, **{k: hard_gate.get(k, 0) for k in
                            ("rows", "trendline_reclaim_shadow", "real_enter_bull")},
                            book_pnl_that_day_all_5_accounts=HARD_GATE_PNL,
                            verdict=("PASS -- signal fired ZERO times across ALL scanned "
                                     "accounts on this date; wiring it live could not have "
                                     "changed any decision, tier, or fill that day"
                                     if hard_gate.get("trendline_reclaim_shadow", 0) == 0
                                     else "REVIEW REQUIRED -- signal fired; manual trace needed")),
            monday_before_day=dict(date="2026-08-03", **{k: monday_before.get(k, 0) for k in
                                    ("rows", "trendline_reclaim_shadow", "real_enter_bull")}),
        per_day=dict(sorted(per_day.items())),
        structural_note=(
            "engine_cli.py _derive_tier (~line 484) bumps to SUPER when "
            "len(winning_triggers)>=3; _derive_routing (~line 465) breaks bear/bull ties "
            "by trigger COUNT. Wiring trendline_reclaim into `triggers` is therefore not "
            "provably inert even on bars that already qualify via a DIFFERENT trigger -- "
            "it can change TIER/SIZING or which side wins a count-tied bar. Documented, "
            "not empirically re-quantified here (the P&L verdict below already fails; "
            "flagged for any future re-open)."
        ),
    )


# --------------------------------------------------------------------------------- #
# Part 2: OPRA-backed standalone-trigger P&L refresh, trendline_reclaim ONLY, extended
# through the newest cached OPRA date. Reuses shadow_signal_edge_2026_07_31's exact
# machinery (fully_covered_days, run_one, day_level_test, one_sample_p, EXIT_SHAPE).
# --------------------------------------------------------------------------------- #
def load_trendline_events() -> list[dict]:
    """Same (signal, date, 5-min bar) dedup convention as sse.load_events(), scoped to
    trendline_reclaim only, reading the CURRENT (larger) core-decisions.jsonl."""
    seen: set[tuple[str, str]] = set()
    events: list[dict] = []
    with sse.LEDGER.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            fired = r.get("shadow_triggers_fired") or []
            if "trendline_reclaim" not in fired:
                continue
            ts = r.get("ts_et") or ""
            if len(ts) < 16:
                continue
            date, hh, mm = ts[:10], ts[11:13], ts[14:16]
            bar = f"{hh}:{int(mm) // 5 * 5:02d}"
            key = (date, bar)
            if key in seen:
                continue
            seen.add(key)
            events.append(dict(
                signal="trendline_reclaim", date=date, bar=bar, spy=r.get("spy"),
                trigger_level=r.get("bull_reclaim_level_raw") or r.get("trigger_level_exact"),
                bull_score=r.get("bull_score"), verdict=r.get("verdict"),
            ))
    return events


def opra_refresh() -> dict:
    # Point the reused module at the NEWER SPY5M file (extends coverage through the
    # newest cached OPRA date) -- module globals are looked up at call time in Python,
    # so this rebind is honored by sse.load_spy() without editing that file.
    sse.SPY5M = NEW_SPY5M
    events = load_trendline_events()
    spy_by_day = sse.load_spy()

    results = []
    for ev in events:
        day = spy_by_day.get(ev["date"])
        if day is None:
            results.append(dict(ev, status="NO_SPY_DAY"))
            continue
        results.append(sse.run_one(ev, day))

    unbiased_days, cov_detail = sse.fully_covered_days(events)
    ok = [r for r in results if r.get("status") == "OK"]
    pnls = [r["pnl"] for r in ok]

    by_day_all: dict[str, float] = defaultdict(float)
    for r in ok:
        by_day_all[r["date"]] += r["pnl"]

    unb_rows = [r for r in results if r["date"] in unbiased_days]
    unb_ok = [r for r in unb_rows if r.get("status") == "OK"]
    unb_pnls = [r["pnl"] for r in unb_ok]
    unb_by_day: dict[str, float] = defaultdict(float)
    for r in unb_ok:
        unb_by_day[r["date"]] += r["pnl"]
    unb_total = round(sum(unb_pnls), 2)
    dl = sse.day_level_test(unb_by_day)

    # HARD-GATE line: 2026-08-04, regardless of unbiased bucket.
    gate_events = [e for e in events if e["date"] == HARD_GATE_DATE]
    gate_rows = [r for r in results if r["date"] == HARD_GATE_DATE]

    excl = defaultdict(int)
    for r in results:
        if r.get("status") != "OK":
            excl[r.get("status", "?")] += 1

    return dict(
        method="IDENTICAL to shadow_signal_edge_2026_07_31.py (fully_covered_days, run_one, "
               "day_level_test, one_sample_p, EXIT_SHAPE, RIBBON_RIDE real exit-manager walk) "
               "-- only SPY5M extended to spy_5m_2026-05-19_2026-08-07.csv so post-07-31 "
               "events resolve instead of excluding as NO_SPY_DAY.",
        spy5m_used=str(NEW_SPY5M.relative_to(REPO)).replace("\\", "/"),
        n_events_total=len(events),
        n_resolved_all=len(ok),
        excluded=dict(excl),
        coverage_audit=dict(unbiased_days=sorted(unbiased_days), per_day=cov_detail),
        all_days_BIASED=dict(
            total_pnl=round(sum(pnls), 2) if pnls else None,
            per_trade=round(sum(pnls) / len(pnls), 2) if pnls else None,
            win_rate_pct=round(100.0 * sum(1 for p in pnls if p > 0) / len(pnls), 1) if pnls else None,
            per_day={d: round(v, 2) for d, v in sorted(by_day_all.items())},
            WARNING="OPRA cache selection is not random -- disclosure only, not a verdict basis.",
        ),
        unbiased_days_only=dict(
            n=len(unb_ok), n_days=len(unb_by_day),
            total_pnl=unb_total,
            per_trade=round(unb_total / len(unb_ok), 2) if unb_ok else None,
            win_rate_pct=round(100.0 * sum(1 for p in unb_pnls if p > 0) / len(unb_pnls), 1) if unb_pnls else None,
            per_day={d: round(v, 2) for d, v in sorted(unb_by_day.items())},
            day_level_test=dl,
            p_value_per_trade=sse.one_sample_p(unb_pnls) if unb_pnls else None,
        ),
        hard_gate_2026_08_04=dict(
            date=HARD_GATE_DATE,
            n_shadow_events_that_day=len(gate_events),
            n_opra_resolved_that_day=sum(1 for r in gate_rows if r.get("status") == "OK"),
            pnl_that_day_standalone_trigger=round(sum(r["pnl"] for r in gate_rows if r.get("status") == "OK"), 2),
            is_unbiased_day=HARD_GATE_DATE in unbiased_days,
            verdict=("PASS (trivial) -- zero shadow events fired this date; no standalone-"
                     "trigger backtest cell touches it at all"
                     if len(gate_events) == 0 else
                     "see pnl_that_day_standalone_trigger -- must be >= 0 to clear the gate"),
        ),
        prior_study_2026_07_31=dict(
            file="analysis/deep-research/SHADOW-SIGNAL-EDGE-2026-07-31.json",
            trendline_reclaim_unbiased=dict(n=27, days=3, total_pnl=-1097, per_trade=-40.64,
                                             win_rate_pct=14.8,
                                             day_level_stat=-3.401, p_normal_approx=0.00067,
                                             p_student_t_df2=0.077, n_days_negative=3,
                                             counterfactual_true_50pct_cap=-1588),
        ),
    )


# --------------------------------------------------------------------------------- #
# Part 2b: CORRECTION -- position-limited re-walk. The raw Part-2 number (and the
# 07-31 precedent it extends) scores every firing as an INDEPENDENT entry with no
# single-position constraint. On 2026-07-29 this produced +$10,107.47 in one day and
# flipped the whole 10-day aggregate from negative to positive -- inspected by hand
# (fable-too-good discipline: hunt the artifact before trusting a result this good)
# and found to be 15 CONSECUTIVE 5-min-bar firings (12:00-13:10 ET) during one
# sustained uptrend, each independently "entered" and independently walked to its own
# runner_stop exit -- i.e. the harness let one continuous trending move buy the same
# directional exposure ~15 times over. The REAL system is single-position-at-a-time
# per account (Rule constraints, C11 "verify flat before entry") and could never have
# held all 15 concurrently. This function re-walks the SAME events but enforces that
# constraint: process each day's firings in time order, skip any firing whose bar is
# before the prior trade's own exit_time_et (the account is still in a position),
# exactly mirroring how the real engine would have been blocked from re-entering.
# --------------------------------------------------------------------------------- #
def run_one_capture_exit_time(ev: dict, spy_day: pd.DataFrame):
    """Byte-identical to sse.run_one() (same strike/entry/exit logic) but also returns
    the raw walk_exit_manager result so its exit_time_et is available for sequencing --
    sse.run_one() discards this field, which its own scope (day-sum only) never needed."""
    out = dict(ev)
    spot = ev.get("spy")
    if not spot:
        return dict(out, status="NO_SPOT"), None
    strike = int(round(float(spot)))
    date = dt.date.fromisoformat(ev["date"])
    sym = sse.option_symbol(date, strike, "C")
    out["symbol"] = sym
    opt = sse.load_contract_bars(sym)
    if opt is None or opt.empty:
        return dict(out, status="UNCOVERED_NO_OPRA"), None

    entry_ts = pd.Timestamp(f"{ev['date']} {ev['bar']}:00")
    opt = opt.copy()
    opt["timestamp_et"] = pd.to_datetime(opt["timestamp_et"])
    if getattr(opt["timestamp_et"].dt, "tz", None) is not None:
        opt["timestamp_et"] = opt["timestamp_et"].dt.tz_localize(None)
    entry_rows = opt[opt["timestamp_et"] >= entry_ts]
    if entry_rows.empty:
        return dict(out, status="NO_ENTRY_BAR"), None
    er = entry_rows.iloc[0]
    entry_premium = float(er["vwap"]) if float(er.get("vwap") or 0) > 0 else float(er["close"])
    if entry_premium <= 0:
        return dict(out, status="BAD_PREMIUM"), None
    out["entry_premium"] = round(entry_premium, 4)
    out["entry_bar_et"] = str(er["timestamp_et"])

    opt_idx_ts = opt["timestamp_et"]
    spy_on_opt = spy_day.set_index("timestamp_et")["close"].reindex(opt_idx_ts).ffill()
    rib = sse.compute_ribbon(pd.Series(spy_on_opt.values))
    ribbon_tick_df = pd.DataFrame({"stack": rib["stack"].values})

    try:
        res = sse.walk_exit_manager(
            symbol=sym, side="C", entry_time_et=er["timestamp_et"].to_pydatetime(),
            entry_premium=entry_premium, qty=sse.QTY, exit_shape=sse.EXIT_SHAPE,
            structure_stop_enabled=True, trigger_level=ev.get("trigger_level"),
            strategy="ribbon_ride", time_stop_et=sse.TIME_STOP,
            opt_df=opt, ribbon_tick_df=ribbon_tick_df, five_min_spy_df=spy_day,
        )
    except Exception as exc:  # noqa: BLE001 -- report, never silently drop
        return dict(out, status=f"WALK_ERROR:{type(exc).__name__}:{exc}"), None

    pnl = getattr(res, "total_pnl", None)
    if pnl is None:
        pnl = sum(leg.leg_pnl for leg in (getattr(res, "legs", []) or []))
    out["status"] = "OK"
    out["pnl"] = round(float(pnl), 2)
    out["exit_reason"] = getattr(res, "exit_reason", None)
    out["entry_time_et"] = er["timestamp_et"]
    out["exit_time_et"] = getattr(res, "exit_time_et", None)
    return out, res


def position_limited_rewalk(events: list[dict], spy_by_day: dict) -> dict:
    by_day: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        by_day[e["date"]].append(e)

    kept_trades, skipped_overlap, skipped_other = [], [], []
    for date, evs in sorted(by_day.items()):
        day_spy = spy_by_day.get(date)
        if day_spy is None:
            continue
        evs_sorted = sorted(evs, key=lambda e: e["bar"])
        blocked_until = None
        for ev in evs_sorted:
            bar_ts = pd.Timestamp(f"{ev['date']} {ev['bar']}:00")
            if blocked_until is not None and bar_ts < blocked_until:
                skipped_overlap.append(dict(ev, reason="position_still_open_until",
                                             blocked_until=str(blocked_until)))
                continue
            row, res = run_one_capture_exit_time(ev, day_spy)
            if row.get("status") != "OK":
                skipped_other.append(row)
                continue
            kept_trades.append(row)
            exit_t = row.get("exit_time_et")
            if exit_t is not None:
                blocked_until = pd.Timestamp(exit_t)
                if blocked_until.tzinfo is not None:
                    blocked_until = blocked_until.tz_localize(None)

    by_day_pnl: dict[str, float] = defaultdict(float)
    for t in kept_trades:
        by_day_pnl[t["date"]] += t["pnl"]
    unbiased_days, _ = sse.fully_covered_days(events)
    unb_kept = [t for t in kept_trades if t["date"] in unbiased_days]
    unb_by_day: dict[str, float] = defaultdict(float)
    for t in unb_kept:
        unb_by_day[t["date"]] += t["pnl"]
    dl = sse.day_level_test(unb_by_day)
    pnls_unb = [t["pnl"] for t in unb_kept]
    win_days = sum(1 for v in unb_by_day.values() if v > 0)
    n_days = len(unb_by_day)
    drop_best_remainder = None
    if pnls_unb:
        winners = [p for p in pnls_unb if p > 0]
        drop_best_remainder = round(sum(pnls_unb) - max(winners), 2) if winners else round(sum(pnls_unb), 2)

    return dict(
        note="POSITION-LIMITED re-walk of the SAME trendline_reclaim shadow firings: "
             "within each day, a firing is only counted as a tradeable entry if the "
             "account would actually be flat at that bar (i.e. the prior kept trade's "
             "own exit_time_et has passed) -- mirrors the real single-position-at-a-time "
             "constraint (Rule 4 / C11) the raw standalone-trigger scope (07-31 study's "
             "own disclosed limitation: 'take every firing as an entry') does not enforce.",
        n_events_in=len(events), n_kept_as_tradeable=len(kept_trades),
        n_skipped_overlap=len(skipped_overlap), n_skipped_other_exclusion=len(skipped_other),
        all_days_total_pnl=round(sum(t["pnl"] for t in kept_trades), 2),
        all_days_per_day={d: round(v, 2) for d, v in sorted(by_day_pnl.items())},
        unbiased_days_only=dict(
            n=len(unb_kept), n_days=n_days,
            total_pnl=round(sum(pnls_unb), 2) if pnls_unb else 0.0,
            per_trade=round(sum(pnls_unb) / len(pnls_unb), 2) if pnls_unb else None,
            win_rate_pct=round(100.0 * sum(1 for p in pnls_unb if p > 0) / len(pnls_unb), 1) if pnls_unb else None,
            per_day={d: round(v, 2) for d, v in sorted(unb_by_day.items())},
            day_majority_win_days=win_days, day_majority_total_days=n_days,
            day_majority_is_majority=(win_days > n_days / 2.0) if n_days else None,
            drop_best_remainder=drop_best_remainder,
            drop_best_still_positive=(drop_best_remainder is not None and drop_best_remainder > 0),
            day_level_test=dl,
        ),
        example_2026_07_29_overlap_evidence=dict(
            n_events_that_day=len(by_day.get("2026-07-29", [])),
            n_kept_after_position_limit=sum(1 for t in kept_trades if t["date"] == "2026-07-29"),
            corrected_total_pnl_that_day=round(sum(t["pnl"] for t in kept_trades if t["date"] == "2026-07-29"), 2),
        ),
    )


# --------------------------------------------------------------------------------- #
# Part 3: wide-population FREQUENCY (no OPRA needed) -- direct detector replay over the
# pinned 391-day lineage + newest available tail. Continuous global bar_idx, RTH-only,
# matching lib/orchestrator.py's own ctx construction (prior_bars=spy_df WHOLE frame,
# bar_idx=global row index -- confirmed by reading orchestrator.py this session, NOT
# assumed).
# --------------------------------------------------------------------------------- #
def build_rth(df: pd.DataFrame) -> pd.DataFrame:
    mask = ((df["timestamp_et"].dt.time >= dt.time(9, 30))
            & (df["timestamp_et"].dt.time < dt.time(16, 0)))
    return df.loc[mask].reset_index(drop=True)


def load_merged_simple(old_path: Path, new_path: Path, tail_after: dt.date) -> pd.DataFrame:
    """Ported convention from bull_gate_f5class_requal_2026_08_01.py's load_merged (old file
    + strictly-after-tail_after tail of new file) -- not re-derived, just inlined to avoid
    importing that module's heavier side-loaded prereg/eb machinery for one utility."""
    old = pd.read_csv(old_path)
    new = pd.read_csv(new_path)
    for df in (old, new):
        df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    tail = new[new["timestamp_et"].dt.date > tail_after]
    out = (pd.concat([old, tail], ignore_index=True)
             .sort_values("timestamp_et").reset_index(drop=True))
    return out.drop_duplicates(subset="timestamp_et").reset_index(drop=True)


def wide_population_frequency() -> dict:
    spy = load_merged_simple(FREQ_OLD_SPY, FREQ_NEW_SPY, FREQ_TAIL_AFTER)
    rth = build_rth(spy)
    n = len(rth)
    fires = 0
    fire_dates: set[str] = set()
    day_of = rth["timestamp_et"].dt.date.astype(str).values
    eligible = 0
    for idx in range(TRENDLINE_LOOKBACK_BARS + 2, n):
        bar = rth.iloc[idx]
        eligible += 1
        lvl = detect_trendline_reclaim_bullish(
            bar, rth, idx,
            lookback_bars=TRENDLINE_LOOKBACK_BARS, min_swings=TRENDLINE_MIN_SWINGS,
        )
        if lvl is not None:
            fires += 1
            fire_dates.add(day_of[idx])
    n_days_total = len(set(day_of))
    return dict(
        window=[str(rth["timestamp_et"].iloc[0].date()), str(rth["timestamp_et"].iloc[-1].date())],
        n_sessions_in_window=n_days_total,
        n_rth_bars_total=n,
        n_bars_eligible_after_warmup=eligible,
        n_fires=fires,
        fires_per_eligible_bar_pct=round(100.0 * fires / max(1, eligible), 2),
        n_days_with_ge1_fire=len(fire_dates),
        pct_days_with_ge1_fire=round(100.0 * len(fire_dates) / max(1, n_days_total), 1),
        note="Price-only detector replay, continuous global bar_idx (matches "
             "lib/orchestrator.py's ctx construction: prior_bars=whole spy_df, "
             "bar_idx=global row index -- NOT per-day reset). No OPRA needed; this is a "
             "FREQUENCY number only, never mixed with the $ P&L figures above (different "
             "evidentiary basis, per the 07-31 study's own scope discipline).",
    )


def main() -> int:
    t0 = et_now()
    log(f"start {t0.isoformat()}")

    log("Part 1: production shadow-log tally (all 5 real accounts)...")
    part1 = production_tally()
    log(f"  total_rows={part1['total_rows']} trendline_reclaim_fires={part1['total_trendline_reclaim_shadow_fires']} "
        f"days_with_fire={part1['n_days_with_fire']}/{part1['n_trading_days_logged']}")
    log(f"  HARD GATE {HARD_GATE_DATE}: {part1['hard_gate_day']}")

    log("Part 2: OPRA-backed standalone-trigger P&L refresh...")
    part2 = opra_refresh()
    log(f"  unbiased: n={part2['unbiased_days_only']['n']} days={part2['unbiased_days_only']['n_days']} "
        f"total=${part2['unbiased_days_only']['total_pnl']} per_trade=${part2['unbiased_days_only']['per_trade']}")
    log(f"  day_level_test={part2['unbiased_days_only']['day_level_test']}")
    log(f"  HARD GATE {HARD_GATE_DATE}: {part2['hard_gate_2026_08_04']}")

    log("Part 2b: fable-too-good check -- position-limited re-walk (same events, "
        "single-position-at-a-time enforced)...")
    sse.SPY5M = NEW_SPY5M
    events = load_trendline_events()
    spy_by_day = sse.load_spy()
    part2b = position_limited_rewalk(events, spy_by_day)
    log(f"  kept {part2b['n_kept_as_tradeable']}/{part2b['n_events_in']} events after position-limit "
        f"({part2b['n_skipped_overlap']} skipped as overlapping an open position)")
    log(f"  unbiased: n={part2b['unbiased_days_only']['n']} total=${part2b['unbiased_days_only']['total_pnl']} "
        f"day_majority={part2b['unbiased_days_only']['day_majority_win_days']}/{part2b['unbiased_days_only']['day_majority_total_days']} "
        f"drop_best_still_positive={part2b['unbiased_days_only']['drop_best_still_positive']}")
    log(f"  2026-07-29 (the outlier day): {part2b['example_2026_07_29_overlap_evidence']}")

    log("Part 3: wide-population frequency (price-only, no OPRA)...")
    part3 = wide_population_frequency()
    log(f"  window={part3['window']} sessions={part3['n_sessions_in_window']} "
        f"fires={part3['n_fires']} ({part3['fires_per_eligible_bar_pct']}% of eligible bars) "
        f"days_with_fire={part3['n_days_with_ge1_fire']}/{part3['n_sessions_in_window']} "
        f"({part3['pct_days_with_ge1_fire']}%)")

    report = dict(
        _doc="TASK 1 evidence refresh -- bull-side detect_trendline_reclaim_bullish "
             "graduation decision. ANALYSIS ONLY, ships nothing.",
        generated_at_et=et_now().strftime("%Y-%m-%dT%H:%M:%S"),
        hard_gate_date=HARD_GATE_DATE,
        hard_gate_book_pnl=HARD_GATE_PNL,
        production_shadow_tally=part1,
        opra_standalone_trigger_refresh=part2,
        position_limited_rewalk_correction=part2b,
        wide_population_frequency=part3,
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT.relative_to(REPO).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
