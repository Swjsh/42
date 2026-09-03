#!/usr/bin/env python
"""retest_zone_shadow.py -- F3 RETEST ZONE-WIDTH GRID + ZONE-WIDTH PERSISTENCE
(analysis/recommendations/prereg-retest-zone-grid-2026-09-03.md).

BACKGROUND. `analysis/deep-research/2026-09-03-money/retest-entry-variant.md` (H10,
"RETEST ENTRY") found the sign of a retest-entry variant's aggregate P&L effect FLIPS
depending on the retest zone's width -- a parameter this project could not pin down from
history because no archived `key-levels.json` snapshot in the current window carries a
`zone_width` field per level. That report's own Recommendation (item 1) is: "Start
persisting historical zone widths... so a future replay of this exact hypothesis has real,
not assumed, inputs," and (item 2) "run a pre-registered zone-width grid ($0.20/$0.30/
$0.40/$0.50/$0.75) with the decision rule fixed before looking at results." This module is
both: a per-trade zone-width RESOLVER (persists which width was actually in force, from the
dated archive when available) and the frozen GRID scorer.

STEP 1 FINDING (this build, verified fresh): `journal/key-levels-archive/` holds 18 dated
snapshots, `key-levels-2026-05-19.json` .. `key-levels-2026-07-02.json` -- and NONE of the
18 carry a `zone_width` field on any level (schema_version 3 throughout; the field was added
to `automation/state/key-levels.json`'s schema only after this archive went stale). Neither
`Gamma_ArchiveKeyLevels` (never registered as a scheduled task -- `Get-ScheduledTask` returns
nothing) nor `Gamma_DailyReview` (registered but State=Disabled, confirmed this build) is
currently firing, so the archive has not advanced in >2 months (last snapshot 2026-07-02,
today 2026-09-03). `analysis/level-quality/snapshots/` holds only 2 dates (2026-06-16,
2026-06-19), also pre-dating the zone_width field. PRACTICAL CONSEQUENCE: every trade this
backfill scores resolves to `zone_source="default"` ($0.30) -- the "in-force width" column is
NOT yet discriminable from the $0.30 grid point for the historical population. This is
disclosed on every row (`zone_in_force.source`) and in the summary
(`in_force_zone_source_counts`), never silently assumed away. IF a future snapshot is
archived (the task remains dead at this build's time) AND that snapshot's schema carries
zone_width (only today's LIVE `automation/state/key-levels.json` does), forward rows will
begin resolving real in-force widths automatically -- no code change needed, this module
already reads whatever the dated snapshot contains.

WHAT IT MEASURES, PER RIDE_THE_RIBBON ENTRY (setup in BEARISH_REJECTION_RIDE_THE_RIBBON /
BULLISH_RECLAIM_RIDE_THE_RIBBON), ALL ARMS, sourced from the enriched, broker-truth
`analysis/entry-quality/entry-quality-ledger.json` (`events`, already carries `setup`,
`trigger_level`, `arm`, and is refreshed nightly by an existing producer -- EXTEND, DON'T
FORK, same convention `tp1_r50_forward_shadow.py` documents for the same file):
  1. Resolve the zone width IN FORCE for the entry's `trigger_level` from
     `journal/key-levels-archive/key-levels-<date_et>.json` (nearest level within $0.01 of
     the trigger; falls back to the $0.30 default with `zone_source="default"` when no
     snapshot exists, no level matches, or the matched level has no `zone_width` key -- see
     Step 1 finding above).
  2. Walk the ACTUAL breakout entry through the REAL production exit code
     (`backtest.lib.exit_manager_walk.walk_exit_manager`, via
     `backtest/tools/money_retest_entry_variant.py`'s own `walk_one` -- REUSED BY IMPORT,
     never modified, never copy-pasted-and-drifted).
  3. Score the RETEST variant (`money_retest_entry_variant.retest_decision` -- same function,
     same import) at the FROZEN grid {0.20, 0.30, 0.40, 0.50, 0.75} AND at the resolved
     in-force width, walking each confirmed retest entry through the identical exit code.
  4. Every row is tagged `in_sample` -- `True` for the ONE-TIME backfill of the population
     that exists at this build's freeze date (`FREEZE_DATE = "2026-09-03"`, `date_et <=
     FREEZE_DATE`), `False` for every trade closed AFTER the freeze date (forward, judged
     data). This mirrors `tp1_r50_forward_shadow.py`'s ACCRUAL_START_DATE contract but keeps
     the (contaminated, already-studied-once) historical population visible for disclosure
     rather than discarding it -- the frozen decision rule in the prereg reads ONLY the
     forward (`in_sample=False`) rows, exactly like H10's own Recommendation intended.

FIDELITY CAVEAT (governs every dollar figure). Per
`analysis/deep-research/WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md`, `walk_exit_manager`
magnitude-fidelity vs real fills PASSES only for safe-2. Every other arm's dollars here are
SIGN-ONLY. Every summary cut discloses this split explicitly (`safe2_trusted` vs
`other_arms_sign_only`), never blends them into one trusted number.

VIX JOIN (disclosed approximation, non-critical to the zone-width finding itself): fleet
arms (safe-1/safe-3/risky-1/risky-3) resolve `order_id -> core_tick_id` from their own
`automation/state/fleet/<arm>/decisions.jsonl` (`placement.broker.id` -> top-level
`core_tick_id`, that file's own field, read not re-derived). Core arms (safe-2/bold-2)
resolve `order_id -> decision_tick_id` from `automation/state/fills-enriched.jsonl` (already
joined by that file's own producer: `fills.order_id -> core-decisions.jsonl ::
exec.broker.id`, populated on entry/buy legs for core arms only). Either tick id then joins
`core-decisions.jsonl`'s `vix` field (`money_retest_entry_variant.load_core_tick_vix`,
reused, tick-level and shared across every arm consuming the same signal tick, exactly as
`retest-entry-variant.md`'s own Method documents). A trade with no resolvable tick carries
`vix=None` and is excluded from the VIX-band split only, never fabricated.

NO LOOK-AHEAD. Population is CLOSED trades only (`exit_qty >= qty`). The retest decision at
trigger tick t0 only reads SPY 1-minute bars strictly after t0 (unmodified
`money_retest_entry_variant.retest_decision`). The zone-width resolution reads only the
ARCHIVED snapshot dated to the trade's own session (never today's live file, never a future
snapshot). A trade whose own session's cached bars are not yet available (still-open session)
is skipped with a reason (`skip_no_option_bars` / `skip_no_spy_1m_for_ribbon`), retried next
run, never backfilled with an assumption.

COST: $0. Pure local computation over cached bars + already-written JSON/JSONL artifacts --
no bar fetch, no OPRA, no LLM, no network call of any kind, exactly the sibling shadow
clocks' cost profile.

Run: python setup/scripts/retest_zone_shadow.py
  (or backtest/.venv/Scripts/python.exe -- either interpreter has pandas; this script adds
  both `backtest/tools` and the repo root to sys.path itself.)

Outputs:
  analysis/recommendations/retest-zone-shadow-ledger.jsonl   append-only, dedup on
                                                               activity_id
  analysis/recommendations/retest-zone-shadow-summary.json   per-width + per-in-force-width
                                                               totals, CI, VIX split, big days
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import os
import random
import sys
from pathlib import Path

# === HEADLESS STDIO REDIRECT (same idiom as run_cmd_hidden.py's OP-27 L41 layer 3) ======
# Under the scheduled task's pythonw hop, run_cmd_hidden.py launches this script with
# capture_output=True -- a real (non-None) pipe, but one nobody ever reads, so this
# script's own print()/log() diagnostics (including the run() error-dict on a caught
# exception) were previously discarded with no trace. Redirecting to a dedicated log file
# makes that visible without changing behavior under a normal console run. Defensive
# guard against sys.stdout/stderr being None outright (some embedded/frozen interpreters)
# is a side effect of the same branch.
if os.path.basename(sys.executable).lower().startswith("pythonw") or sys.stdout is None:
    _log_dir = Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    sys.stdout = open(_log_dir / "retest-zone-shadow.stdout.log", "a", buffering=1, encoding="utf-8")
    sys.stderr = open(_log_dir / "retest-zone-shadow.stderr.log", "a", buffering=1, encoding="utf-8")
# ==========================================================================================

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
TOOLS_DIR = BACKTEST / "tools"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
SCRIPTS_DIR = REPO / "setup" / "scripts"
for _p in (REPO, BACKTEST, TOOLS_DIR, FLEET_DIR, SCRIPTS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

import money_retest_entry_variant as mrev  # noqa: E402 -- REUSED, never modified (task constraint)

ENTRY_QUALITY_LEDGER = REPO / "analysis" / "entry-quality" / "entry-quality-ledger.json"
FILLS_ENRICHED = REPO / "automation" / "state" / "fills-enriched.jsonl"
ARCHIVE_DIR = REPO / "journal" / "key-levels-archive"

OUT_DIR = REPO / "analysis" / "recommendations"
LEDGER = OUT_DIR / "retest-zone-shadow-ledger.jsonl"
SUMMARY = OUT_DIR / "retest-zone-shadow-summary.json"
PREREG_REL = "analysis/recommendations/prereg-retest-zone-grid-2026-09-03.md"

RIBBON_ENTRY_SETUPS = frozenset({"BEARISH_REJECTION_RIDE_THE_RIBBON", "BULLISH_RECLAIM_RIDE_THE_RIBBON"})
ZONE_GRID = (0.20, 0.30, 0.40, 0.50, 0.75)
DEFAULT_ZONE_WIDTH = 0.30
LEVEL_MATCH_TOLERANCE = 0.01     # dollars -- a trigger_level IS a level's price at trigger time
BIG_WINNER_DAYS = ("2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28")   # per H10's report
TRUSTED_MAGNITUDE_ARMS = frozenset({"safe-2"})   # WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md
FREEZE_DATE = "2026-09-03"        # this build's own date -- backfill-once boundary (task: "Backfill once as in_sample:true")
FORWARD_MIN_SESSIONS = 20         # prereg forward bar (a)
FORWARD_MIN_SIGNALS = 40          # prereg forward bar (b)
MAX_ENTRIES_PER_RUN = 1000        # safety cap; measured full-history run is far under this (~2-3s/200 entries)


def log(msg: str) -> None:
    print(f"[retest-zone-shadow] {msg}", flush=True)


# ------------------------------------------------------------------------------------------
# ledger I/O (same tolerant-of-a-torn-last-line contract as the sibling shadow ledgers)
# ------------------------------------------------------------------------------------------
def _read_ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    rows = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue          # a torn last line must never kill the accrual
    return rows


def _stamp_now_et() -> str:
    try:
        from et_clock import et_now  # noqa: PLC0415
        return et_now().isoformat()
    except Exception:  # noqa: BLE001 -- a stamp must never break the clock
        return ""


# ------------------------------------------------------------------------------------------
# zone-width resolution -- archived snapshot for the trade's own date, else the $0.30 default
# ------------------------------------------------------------------------------------------
def resolve_zone_width(trigger_level: float, date_str: str) -> dict:
    """Resolve the zone width IN FORCE for a trigger level from the archived
    key-levels.json snapshot for that date. Falls back to DEFAULT_ZONE_WIDTH (flagged
    zone_source='default') when no snapshot exists for the date, no level in that snapshot
    is within LEVEL_MATCH_TOLERANCE of the trigger, or the matched level carries no
    zone_width field at all (true for the entire current archive -- see module docstring
    Step 1 finding)."""
    path = ARCHIVE_DIR / f"key-levels-{date_str}.json"
    if not path.exists():
        return {"width": DEFAULT_ZONE_WIDTH, "source": "default",
                "reason": f"no archived snapshot for {date_str}", "matched_level_price": None,
                "matched_level_label": None}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"width": DEFAULT_ZONE_WIDTH, "source": "default",
                "reason": f"snapshot unreadable: {type(exc).__name__}: {exc}",
                "matched_level_price": None, "matched_level_label": None}
    levels = doc.get("levels") or []
    best, best_dist = None, None
    for lvl in levels:
        price = lvl.get("price")
        if price is None:
            continue
        dist = abs(float(price) - float(trigger_level))
        if dist <= LEVEL_MATCH_TOLERANCE and (best_dist is None or dist < best_dist):
            best, best_dist = lvl, dist
    if best is None:
        return {"width": DEFAULT_ZONE_WIDTH, "source": "default",
                "reason": f"no level within ${LEVEL_MATCH_TOLERANCE} of trigger {trigger_level}",
                "matched_level_price": None, "matched_level_label": None}
    zw = best.get("zone_width")
    if zw is None:
        return {"width": DEFAULT_ZONE_WIDTH, "source": "default",
                "reason": "matched level carries no zone_width field",
                "matched_level_price": float(best["price"]), "matched_level_label": best.get("label")}
    return {"width": float(zw), "source": "archive",
            "reason": f"matched level {best.get('label')!r} zone_width={zw}",
            "matched_level_price": float(best["price"]), "matched_level_label": best.get("label")}


# ------------------------------------------------------------------------------------------
# VIX join -- order_id -> tick_id (fleet arms from their own decisions.jsonl; core arms
# safe-2/bold-2 from fills-enriched.jsonl's own existing join) -> vix (core-decisions.jsonl)
# ------------------------------------------------------------------------------------------
def _load_fleet_order_to_tick() -> dict[str, str]:
    out: dict[str, str] = {}
    for arm in ("safe-1", "safe-3", "risky-1", "risky-3"):
        path = FLEET_DIR / arm / "decisions.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            tick = d.get("core_tick_id")
            broker_id = ((d.get("placement") or {}).get("broker") or {}).get("id")
            if tick and broker_id and broker_id not in out:
                out[broker_id] = tick
    return out


def _load_core_arm_order_to_tick() -> dict[str, str]:
    """safe-2/bold-2 entries: fills-enriched.jsonl already carries decision_tick_id on
    entry (buy) legs, joined by that file's own producer (fills.order_id ->
    core-decisions.jsonl :: exec.broker.id) -- read, not re-derived."""
    out: dict[str, str] = {}
    if not FILLS_ENRICHED.exists():
        return out
    for line in FILLS_ENRICHED.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("side") != "buy":
            continue
        tick = d.get("decision_tick_id")
        oid = d.get("order_id")
        if tick and oid and oid not in out:
            out[oid] = tick
    return out


# ------------------------------------------------------------------------------------------
# per-entry scoring -- actual walk (once) + retest at every grid width + the in-force width
# ------------------------------------------------------------------------------------------
def score_entry(event: dict, spy_5m_rth: pd.DataFrame, ribbon_5m: pd.DataFrame,
                 vix: float | None) -> dict | None:
    trigger_level = event.get("trigger_level")
    if trigger_level is None:
        return None
    activity_id = event["activity_id"]
    symbol, side, date_str = event["symbol"], event["opt_side"], event["date_et"]
    setup, qty = event["setup"], event["qty"]
    trigger_level = float(trigger_level)
    entry_premium = float(event["price"])
    t0 = mrev._parse_naive(event["ts_et"])

    opt_df, opt_res = mrev.load_opt_bars(symbol, date_str)
    if opt_df is None:
        return {"activity_id": activity_id, "status": "skip_no_option_bars"}

    if opt_res == "5min":
        ribbon_tick_df, _n = mrev.day_slice(spy_5m_rth, ribbon_5m, date_str)
    else:
        spy_1m_day_for_ribbon = mrev.load_spy_1m(date_str)
        if spy_1m_day_for_ribbon is None:
            return {"activity_id": activity_id, "status": "skip_no_spy_1m_for_ribbon"}
        day5, _n = mrev.day_slice(spy_5m_rth, ribbon_5m, date_str)
        spy_5m_day = spy_5m_rth.loc[
            spy_5m_rth["timestamp_et"].dt.strftime("%Y-%m-%d") == date_str
        ].reset_index(drop=True)
        five = spy_5m_day[["timestamp_et"]].copy()
        five["five_idx"] = five.index
        merged = pd.merge_asof(
            spy_1m_day_for_ribbon[["timestamp_et"]].sort_values("timestamp_et"),
            five.sort_values("timestamp_et"), on="timestamp_et", direction="backward")
        ribbon_tick_df = day5.loc[merged["five_idx"].values].reset_index(drop=True)

    actual = mrev.walk_one(symbol, side, t0, entry_premium, qty, trigger_level, setup,
                            opt_df, ribbon_tick_df, spy_5m_rth, opt_res)

    spy_1m_day = mrev.load_spy_1m(date_str)
    in_force = resolve_zone_width(trigger_level, date_str)

    def _score_at(width: float) -> dict:
        if spy_1m_day is None or spy_1m_day.empty:
            return {"outcome": "no_1m_spy_data", "retest_walk_pnl": 0.0,
                    "retest_entry_time": None, "retest_exit_reason": None, "retest_hold_min": None}
        decision = mrev.retest_decision(spy_1m_day, t0, trigger_level, side, zone_width=width)
        row = {"outcome": decision["outcome"], "retest_walk_pnl": 0.0,
               "retest_entry_time": None, "retest_exit_reason": None, "retest_hold_min": None}
        if decision["outcome"] == "confirmed":
            confirm_ts = decision["ts"]
            retest_entry_time = confirm_ts + dt.timedelta(minutes=1)
            retest_open = mrev.bar_open_at_or_after(opt_df, retest_entry_time)
            if retest_open is None:
                row["outcome"] = "confirmed_no_option_data"
            else:
                rw = mrev.walk_one(symbol, side, retest_entry_time, retest_open, qty,
                                    trigger_level, setup, opt_df, ribbon_tick_df,
                                    spy_5m_rth, opt_res)
                row["retest_walk_pnl"] = rw.dollar_pnl
                row["retest_exit_reason"] = rw.exit_reason
                row["retest_hold_min"] = rw.hold_minutes
                row["retest_entry_time"] = retest_entry_time.isoformat()
        return row

    grid_results = {f"{w:.2f}": _score_at(w) for w in ZONE_GRID}
    in_force_label = f"{in_force['width']:.2f}"
    if in_force_label in grid_results:
        in_force_result = dict(grid_results[in_force_label])
        in_force_result["reused_grid_label"] = in_force_label
    else:
        in_force_result = _score_at(in_force["width"])
        in_force_result["reused_grid_label"] = None

    return {
        "activity_id": activity_id, "arm": event["arm"], "symbol": symbol, "side": side,
        "setup": setup, "date_et": date_str, "ts_et": event["ts_et"],
        "trigger_level": trigger_level, "qty": qty, "entry_premium": entry_premium,
        "opt_resolution": opt_res, "vix": vix, "big_winner_day": date_str in BIG_WINNER_DAYS,
        "magnitude_trusted": event["arm"] in TRUSTED_MAGNITUDE_ARMS,
        "in_sample": date_str <= FREEZE_DATE,
        "zone_in_force": in_force,
        "actual_walk_pnl": actual.dollar_pnl, "actual_walk_exit_reason": actual.exit_reason,
        "actual_walk_hold_min": actual.hold_minutes,
        "widths": {"grid": grid_results, "in_force": in_force_result},
    }


# ------------------------------------------------------------------------------------------
# summary statistics
# ------------------------------------------------------------------------------------------
VIX_BANDS = (("lt15", lambda v: v < 15), ("15to17", lambda v: 15 <= v <= 17), ("gt17", lambda v: v > 17))


def _bootstrap_day_clustered_delta(rows: list[dict], n_boot: int = 2000,
                                    seed: int = 20260903) -> dict | None:
    """Percentile bootstrap resampling trading DAYS with replacement over per-trade
    (retest - actual) deltas, matching go_live_gate.bootstrap_pf_ci's day-clustering
    methodology (and tp1_r50_forward_shadow's own sibling implementation)."""
    by_day: dict[str, list[float]] = collections.defaultdict(list)
    for r in rows:
        by_day[r["date_et"]].append(r["retest"] - r["actual"])
    days = sorted(by_day)
    if len(days) < 2:
        return None
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        sample_days = [days[rng.randrange(len(days))] for _ in range(len(days))]
        vals = [v for d in sample_days for v in by_day[d]]
        if vals:
            means.append(sum(vals) / len(vals))
    if not means:
        return None
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[min(int(0.975 * len(means)), len(means) - 1)]
    return {"n_boot": n_boot, "n_days_clustered": len(days),
            "ci_lower_2.5": round(lo, 4), "ci_upper_97.5": round(hi, 4)}


def _width_stats(rows: list[dict], get_result) -> dict:
    """rows: ledger rows to aggregate. get_result(row) -> the {'outcome','retest_walk_pnl',...}
    dict for the width/cut being scored (a fixed grid label, or each row's own in-force
    result). Retest contributes $0 for any non-'confirmed' outcome, matching H10's own
    convention (an un-confirmed retest is a trade not taken, not a trade scored at zero
    skill)."""
    n_confirmed = 0
    actual_total = retest_total = 0.0
    trusted_rows: list[dict] = []
    other_rows: list[dict] = []
    scored_rows: list[dict] = []
    for r in rows:
        w = get_result(r)
        if w is None:
            continue
        actual = r["actual_walk_pnl"]
        retest = w.get("retest_walk_pnl", 0.0) or 0.0
        actual_total += actual
        retest_total += retest
        if w.get("outcome") == "confirmed":
            n_confirmed += 1
        rec = {"date_et": r["date_et"], "actual": actual, "retest": retest}
        scored_rows.append(rec)
        (trusted_rows if r.get("magnitude_trusted") else other_rows).append(rec)

    trusted_delta = round(sum(t["retest"] - t["actual"] for t in trusted_rows), 2) if trusted_rows else None
    other_delta = round(sum(t["retest"] - t["actual"] for t in other_rows), 2) if other_rows else None
    trusted_ci = _bootstrap_day_clustered_delta(trusted_rows) if trusted_rows else None

    vix_split = {}
    for band_name, pred in VIX_BANDS:
        band_rows = [r for r in rows if r.get("vix") is not None and pred(r["vix"]) and get_result(r) is not None]
        if not band_rows:
            vix_split[band_name] = None
            continue
        b_actual = sum(r["actual_walk_pnl"] for r in band_rows)
        b_retest = sum((get_result(r) or {}).get("retest_walk_pnl", 0.0) or 0.0 for r in band_rows)
        vix_split[band_name] = {"n": len(band_rows), "actual": round(b_actual, 2),
                                 "retest": round(b_retest, 2), "delta": round(b_retest - b_actual, 2)}

    big_days = {}
    for d in BIG_WINNER_DAYS:
        d_rows = [r for r in rows if r["date_et"] == d and get_result(r) is not None]
        if not d_rows:
            big_days[d] = None
            continue
        d_actual = sum(r["actual_walk_pnl"] for r in d_rows)
        d_retest = sum((get_result(r) or {}).get("retest_walk_pnl", 0.0) or 0.0 for r in d_rows)
        big_days[d] = {"n": len(d_rows), "actual": round(d_actual, 2), "retest": round(d_retest, 2),
                        "delta": round(d_retest - d_actual, 2),
                        "sign_flip": (d_actual > 0) != (d_retest > 0)}

    return {
        "n_scored": len(scored_rows), "n_confirmed": n_confirmed,
        "actual_total": round(actual_total, 2), "retest_total": round(retest_total, 2),
        "delta_total": round(retest_total - actual_total, 2),
        "safe2_trusted": {"n": len(trusted_rows), "delta": trusted_delta,
                           "session_clustered_ci": trusted_ci},
        "other_arms_sign_only": {
            "n": len(other_rows), "delta": other_delta,
            "note": ("SIGN-ONLY per WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md -- "
                     "walk_exit_manager magnitude fidelity passes only for safe-2; "
                     "direction of this delta is indicative, the dollar figure is not.")},
        "vix_band_split": vix_split,
        "big_winner_days": big_days,
    }


def _by_all_cuts(rows: list[dict]) -> dict:
    grid_labels = [f"{w:.2f}" for w in ZONE_GRID]
    by_grid = {label: _width_stats(rows, (lambda r, lbl=label: r["widths"]["grid"].get(lbl)))
               for label in grid_labels}
    in_force = _width_stats(rows, lambda r: r["widths"].get("in_force"))
    return {"grid": by_grid, "in_force": in_force}


def _summarize(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {
            "prereg": PREREG_REL, "generated_at_et": _stamp_now_et(), "n_scored": 0,
            "status": "ARMED_AWAITING_FILLS", "by_all_time": {}, "by_forward_only": {},
            "in_force_zone_source_counts": {}, "in_force_zone_width_counts": {},
            "n_in_sample_backfill": 0, "n_forward": 0, "n_forward_days": 0,
            "note": ("No qualifying RIDE_THE_RIBBON entries scored yet. An empty clock right "
                     "after freeze is expected, NOT a failure -- but still empty after several "
                     "trading days means entry-quality-ledger.json stopped feeding it."),
        }

    days = sorted({r["date_et"] for r in rows})
    forward_rows = [r for r in rows if not r.get("in_sample", False)]
    backfill_rows = [r for r in rows if r.get("in_sample", False)]
    forward_days = sorted({r["date_et"] for r in forward_rows})

    in_force_source_counts = collections.Counter(r["zone_in_force"]["source"] for r in rows)
    in_force_width_counts = collections.Counter(f"{r['zone_in_force']['width']:.2f}" for r in rows)

    bar_met = len(forward_days) >= FORWARD_MIN_SESSIONS and len(forward_rows) >= FORWARD_MIN_SIGNALS

    return {
        "prereg": PREREG_REL,
        "generated_at_et": _stamp_now_et(),
        "n_scored": n,
        "days_scored": len(days),
        "date_span": f"{days[0]}..{days[-1]}",
        "n_in_sample_backfill": len(backfill_rows),
        "n_forward": len(forward_rows),
        "n_forward_days": len(forward_days),
        "forward_bar": {
            "min_forward_sessions": FORWARD_MIN_SESSIONS, "min_forward_signals": FORWARD_MIN_SIGNALS,
            "sessions_to_bar": max(0, FORWARD_MIN_SESSIONS - len(forward_days)),
            "signals_to_bar": max(0, FORWARD_MIN_SIGNALS - len(forward_rows)),
            "bar_met": bar_met,
        },
        "in_force_zone_source_counts": dict(in_force_source_counts),
        "in_force_zone_width_counts": dict(in_force_width_counts),
        "by_all_time": _by_all_cuts(rows),
        "by_backfill_only": _by_all_cuts(backfill_rows) if backfill_rows else {},
        "by_forward_only": _by_all_cuts(forward_rows) if forward_rows else {},
        "status": "BAR_MET_AWAITING_VERDICT" if bar_met else "ACCRUING",
        "decision_rule": (
            "Read ONCE, on FORWARD (in_sample=False) data only, at >=20 forward sessions AND "
            ">=40 forward signals: ship-candidate only if by_forward_only.in_force."
            "safe2_trusted.session_clustered_ci.ci_lower_2.5 > 0 AND no by_all_time.in_force."
            "big_winner_days entry has sign_flip=true. The grid columns (0.20/0.30/0.40/0.50/"
            "0.75) are disclosure-only -- no width may be picked after reading them. Full "
            f"rule: {PREREG_REL}"),
    }


def _input_health(events: list[dict]) -> dict:
    ribbon = [e for e in events if e.get("setup") in RIBBON_ENTRY_SETUPS]
    newest = max((e.get("date_et", "") for e in ribbon), default="")
    today = dt.date.today()
    back = 1 if today.weekday() != 0 else 3
    prev_session = today - dt.timedelta(days=back)
    while prev_session.weekday() >= 5:
        prev_session -= dt.timedelta(days=1)
    stale = bool(newest) and newest < prev_session.isoformat()
    return {"input_ledger_newest_ribbon_date": newest or None,
            "input_expected_through": prev_session.isoformat(),
            "input_stale": stale,
            "input_note": ("STALE -- entry-quality-ledger.json has not advanced to the last "
                           "completed session; this clock is not being fed, NOT a real absence "
                           "of ribbon fills." if stale else "fed")}


def _archive_health() -> dict:
    dated = sorted(p.name for p in ARCHIVE_DIR.glob("key-levels-*.json")) if ARCHIVE_DIR.exists() else []
    n_with_zone_width = 0
    for name in dated:
        try:
            doc = json.loads((ARCHIVE_DIR / name).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if any(isinstance(lvl, dict) and lvl.get("zone_width") is not None for lvl in doc.get("levels", [])):
            n_with_zone_width += 1
    return {"n_dated_snapshots": len(dated),
            "first_snapshot": dated[0].replace("key-levels-", "").replace(".json", "") if dated else None,
            "last_snapshot": dated[-1].replace("key-levels-", "").replace(".json", "") if dated else None,
            "n_snapshots_with_any_zone_width": n_with_zone_width,
            "note": ("Gamma_ArchiveKeyLevels is not a registered scheduled task; Gamma_DailyReview "
                     "is registered but State=Disabled (both confirmed this build) -- the archive "
                     "is not currently advancing.")}


# ------------------------------------------------------------------------------------------
def run() -> dict:
    """Nightly entry point. Fail-open by contract, own scheduled task."""
    try:
        if not ENTRY_QUALITY_LEDGER.exists():
            raise RuntimeError(f"entry-quality ledger missing: {ENTRY_QUALITY_LEDGER}")
        doc = json.loads(ENTRY_QUALITY_LEDGER.read_text(encoding="utf-8"))
        events = doc.get("events", [])

        ribbon_events = [e for e in events if e.get("setup") in RIBBON_ENTRY_SETUPS]
        closed = [e for e in ribbon_events
                  if float(e.get("exit_qty") or 0) >= float(e.get("qty") or 0) - 1e-6]
        n_no_trigger = sum(1 for e in closed if e.get("trigger_level") is None)
        scoreable = [e for e in closed if e.get("trigger_level") is not None]

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        existing = _read_ledger()
        seen_ids = {r.get("activity_id") for r in existing}
        todo = [e for e in scoreable if e.get("activity_id") not in seen_ids][:MAX_ENTRIES_PER_RUN]
        log(f"{len(ribbon_events)} ribbon events, {len(closed)} closed, "
            f"{n_no_trigger} excluded (no trigger_level), {len(scoreable)} scoreable, "
            f"{len(existing)} already in ledger, {len(todo)} to score this run")

        appended: list[dict] = []
        skipped: list[dict] = []
        if todo:
            spy_5m_rth, ribbon_5m = mrev.load_spy_5m_and_ribbon()
            order_to_tick = _load_fleet_order_to_tick()
            order_to_tick.update(_load_core_arm_order_to_tick())
            vix_by_tick = mrev.load_core_tick_vix()

            for e in sorted(todo, key=lambda e: e["ts_et"]):
                tick = order_to_tick.get(e.get("order_id"))
                vix = vix_by_tick.get(tick) if tick else None
                try:
                    result = score_entry(e, spy_5m_rth, ribbon_5m, vix)
                except Exception as row_exc:  # noqa: BLE001 -- one bad row must never
                    # abort the whole batch and silently skip the summary write for the
                    # (N-1) already-good rows (2026-09-03 fire: a single KeyError from a
                    # NaN-filled merge_asof index on one date killed 200 already-scored
                    # entries' worth of visibility -- see run-cmd-hidden log evidence).
                    skipped.append({"activity_id": e.get("activity_id"),
                                     "reason": f"exception: {type(row_exc).__name__}: {row_exc}"[:300]})
                    continue
                if result is None:
                    skipped.append({"activity_id": e.get("activity_id"),
                                     "reason": "no trigger_level (defensive -- already filtered upstream)"})
                    continue
                if "status" in result:
                    skipped.append({"activity_id": result["activity_id"], "reason": result["status"]})
                    continue
                appended.append(result)

            if appended:
                with LEDGER.open("a", encoding="utf-8") as fh:
                    for r in appended:
                        fh.write(json.dumps(r, default=str) + "\n")

        all_rows = existing + appended
        summary = _summarize(all_rows)
        summary["new_this_run"] = len(appended)
        summary["skipped_this_run"] = skipped
        summary["population"] = {
            "n_ribbon_events_total": len(ribbon_events), "n_closed": len(closed),
            "n_no_trigger_level_excluded": n_no_trigger, "n_scoreable": len(scoreable),
            "n_scored_cumulative": len(all_rows),
        }
        summary["archive_health"] = _archive_health()
        summary.update(_input_health(events))
        SUMMARY.write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
        log(f"wrote {len(appended)} new rows; cumulative {len(all_rows)}; status={summary.get('status')}")
        return summary
    except Exception as e:  # noqa: BLE001 -- descriptive side-product, never fatal
        return {"error": f"{type(e).__name__}: {e}"[:400], "prereg": PREREG_REL}


def main() -> int:
    out = run()
    print(json.dumps(out, indent=1, default=str)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
