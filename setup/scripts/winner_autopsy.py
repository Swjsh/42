#!/usr/bin/env python
"""winner_autopsy.py -- the WINNER-side autopsy organ (J 2026-07-31: "We need to analyze
these winners just as much as the losers so we can figure out how to either stay in them
longer or get better exits").

WHY THIS EXISTS
---------------
`trade_autopsy.py` (Gamma_TradeAutopsy, 16:15 ET) owns learn-from-LOSSES: it replays a
counterfactual menu on dead trades and emits hypotheses about stops that were too tight.
Nothing did the mirror job for winners. The asymmetry was real and J named it by hand on
2026-07-31 after the risky-3 12:19 ET 746C trade, whose TP1 leg filled at +97% while its
RUNNER leg -- the leg that is supposed to be the upside -- exited at +45%. The runner GAVE
BACK. That question ("should we have held longer, or exited better?") had no standing
instrument; J had to ask. This module is that instrument.

DESIGN DECISION -- SEPARATE MODULE, SHARED I/O (not an extension of trade_autopsy.py)
-------------------------------------------------------------------------------------
Considered extending `trade_autopsy.py` and rejected it, for three reasons:
  1. SIZE. trade_autopsy.py is already ~1,300 lines carrying two lanes (SPY + TWIN). The
     repo coding standard is 800 lines max. A third lane makes an already-over-budget file
     worse.
  2. BLAST RADIUS. trade_autopsy.py IS the 16:15 ET production path, with its own honesty
     guards (`compute_pnl_status`/`resolve_net_pnl`), a hypothesis queue, a queue.md writer
     and a Discord outbox. A winner lane has no business being able to break any of that.
  3. CADENCE. The loss autopsy is a SAME-DAY job with a bounded bar-retry budget. Capture
     rate is a POPULATION statistic -- it must re-walk every historical winner every night.
     Different job, different runtime, different failure mode.
REUSE IS STILL REAL, and is the whole point: this module IMPORTS the position
reconstruction, the ledger loader, the strategy lookup and the bar fetcher rather than
reimplementing any of them --
    trade_autopsy.load_engine_positions / lookup_strategy / fetch_bars_cached
    exit_shape_parity_study.replay_position / fetch_option_bars
...so there is exactly ONE definition of "what is a position" and ONE OPRA fetch path in
the repo. If those change, this module changes with them for free.

WHAT IT ANSWERS, MECHANICALLY, FOR EVERY WINNING CLOSED TRADE
-------------------------------------------------------------
  * WHY IT ENTERED   -- setup_name, trigger_level, side, quality tier, risk_code, and the
                        engine's own `reason` string, read from the arm's decision ledger.
  * WHY THAT STRIKE  -- strike, its offset from the trigger level, the as-placed premium,
                        and the resolved exit contract (the `placement` block).
  * WHAT IT SAW      -- the in-trade timeline from the SAME `exit_pass` rows the live
                        exit_actuator wrote each tick: best/worst premium, tp1_filled,
                        the moving runner_stop, and every RATCHET.
  * WHY EACH LEG LEFT-- the exit_manager `stage` literal that closed each leg (tp1 / trail /
                        structure_stop / premium_stop / runner_target / time_stop).
  * WHAT IT GAVE BACK-- per leg: the position's high-water premium BEFORE that leg exited
                        vs what the leg actually realized.
  * WHAT ELSE WAS ON -- the live-executable exit-variant grid (EXIT_MENU below), each
    THE TABLE          replayed through the REAL `exit_manager.plan_exit_actions` on REAL
                        1-min OPRA bars.

THE METRIC: CAPTURE RATE
------------------------
"We capture X% of what our winners actually offered." Three numbers, deliberately, because
only one of them is honest as a headline and the other two are the disclosure:

  1. `capture_vs_best_policy` (THE HEADLINE, honest).
     realized_total / (total of the SINGLE best fixed policy in EXIT_MENU).
     One policy, chosen once, applied to every trade -- something you could actually have
     selected in advance and run. This is the only capture number that is not contaminated
     by hindsight, and it is the one that goes in the brief.

  2. `capture_vs_per_trade_best` (BIASED HIGH -- disclosed, never the headline).
     realized_total / sum(per-trade max over the menu). Picking the best shape PER TRADE
     is a hindsight selection: live, you do not know which shape wins on a given trade. It
     is reported because the gap between (1) and (2) measures how much of the "we left money
     on the table" feeling is really just shape-picking luck.

  3. `capture_vs_oracle` (UNACHIEVABLE REFERENCE -- labelled, never a target).
     realized_total / (sell 100% at the post-entry high-water bar). No live rule can do
     this. It exists only to bound the universe.

DISCIPLINE RAILS BUILT INTO THIS MODULE
---------------------------------------
  * DESCRIPTIVE ONLY. This module writes ONLY its own surfaces + the brief. It deliberately
    does NOT write `hypothesis-queue.jsonl` and does NOT append to `queue.md`, unlike
    trade_autopsy.py. A winner autopsy at n=21 is an ANECDOTE COLLECTION, and the single
    worst outcome available here is an exit change ratified off a good-looking small sample.
    Every aggregate it prints carries its own n. Any hypothesis that falls out is for a
    HUMAN to pre-register as a proper study.
  * RUNNER-COHORT SANCTITY. The RUNNER_TRAIL cohort is the book's profit engine. This module
    measures; it proposes nothing that could degrade it, because it proposes nothing at all.
  * REAL OPRA ONLY. Every P&L number is either a broker fill (realized) or a replay on real
    1-min OPRA bars. No synthetic pricing anywhere. A position whose bars are unavailable is
    EXCLUDED and COUNTED (`n_no_bars`) -- never silently dropped, never zero-filled (C7/L241).
  * ENTRY+1 CONVENTION (markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md). A
    position placed on tick N is not exit-checked until N+1, because the live engine manages
    exits BEFORE it evaluates entries within a tick. `exit_eligible_bars` enforces strict
    `>` against the ENTRY BAR's minute. Note this module pre-filters the bar list it hands
    to `esp.replay_position` rather than editing that shared function -- replay_position
    uses `>=` and is a frozen anchor for other studies (C34/blast radius).

COST: $0. Pure Python + the Alpaca OPRA bars endpoint already used by the loss autopsy.
No LLM anywhere. Cheap enough to run every night forever.

WS9 FOLD (2026-08-01): each full-population nightly fire also refreshes the MAE/MFE pain
ledger (`pain_ledger.build_ledger`, sharing this run's bar cache) -> analysis/pain-ledger/
mae-mfe.json. Prereg: analysis/pain-ledger/PREREG-2026-08-01.md. Fail-open, additive only.

Manual run:
    python setup/scripts/winner_autopsy.py              # full population
    python setup/scripts/winner_autopsy.py --date 2026-07-31
    python setup/scripts/winner_autopsy.py --symbol SPY260731C00746000
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, 2026-07-14 popup-storm fix) =====
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting
# can allocate a visible WindowsTerminal -Embedding window on the FIRST stderr/stdout
# write. Redirect stdio to log files BEFORE any other import gets a chance to write.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "winner-autopsy.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "winner-autopsy.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import argparse
import json
import sys
import time as _time_mod
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "automation" / "state" / "fleet",
           REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from et_clock import et_now  # noqa: E402

STATE = REPO / "automation" / "state"
OUT_DIR = REPO / "analysis" / "winner-autopsies"
LAST_JSON = STATE / "winner-autopsy-last.json"
ACCOUNTS_JSON = STATE / "fleet" / "accounts.json"

# Reused verbatim from trade_autopsy.py's taxonomy (single source of truth for which ledger
# FORMAT an arm's decisions live in). Imported rather than redeclared where possible.
CORE_DECISIONS = STATE / "core-decisions.jsonl"

# ---------------------------------------------------------------------------------------
# THE EXIT MENU -- fixed, pre-declared, and LIVE-EXECUTABLE.
#
# Every shape here is a dict of `exit_manager.ExitState.from_entry` keys, replayed through
# the REAL `plan_exit_actions` decision core. Nothing in this menu is a knob the live engine
# could not run tomorrow. The menu is DECLARED ONCE, HERE, and must not be tuned per-trade
# or per-run -- the moment it is fitted to the data, `capture_vs_best_policy` stops being an
# honest denominator.
#
# `profit_lock_arm_scope` is set EXPLICITLY on every shape (never left to the default) --
# L248/L234: a knob that is unconditional in production but optional in the study is exactly
# how a harness silently diverges from live. "post_tp1" is what live does today.
#
# The menu spans the axis J actually asked about -- take profit sooner vs hold the runner
# longer -- plus the two degenerate ends that bound it.
EXIT_MENU: dict[str, dict] = {
    # Sell the WHOLE position at TP1. The direct probe for "did the runner add anything?"
    "all_out_at_tp1_100": {
        "premium_stop_pct": -0.50, "tp1_premium_pct": 1.00, "tp1_qty_fraction": 1.0,
        "profit_lock_mode": "fixed", "trail_pct": 0.125, "runner_target_pct": 2.5,
        "profit_lock_arm_pct": 0.05, "profit_lock_arm_scope": "post_tp1"},
    # Take profit EARLIER, whole position. The scalp end of the axis.
    "all_out_at_tp1_50": {
        "premium_stop_pct": -0.50, "tp1_premium_pct": 0.50, "tp1_qty_fraction": 1.0,
        "profit_lock_mode": "fixed", "trail_pct": 0.125, "runner_target_pct": 2.5,
        "profit_lock_arm_pct": 0.05, "profit_lock_arm_scope": "post_tp1"},
    # v15.3-Safe-shaped: early TP1 on most of the position, runner trails.
    "tp1_30_trail_125": {
        "premium_stop_pct": -0.50, "tp1_premium_pct": 0.30, "tp1_qty_fraction": 0.8,
        "profit_lock_mode": "trailing", "trail_pct": 0.125, "runner_target_pct": 2.5,
        "profit_lock_arm_pct": 0.05, "profit_lock_arm_scope": "post_tp1"},
    # ZONE-RIDE-shaped: TP1 at +100%, 2/3 out, wide 20% trail on the runner.
    "tp1_100_trail_20": {
        "premium_stop_pct": -0.50, "tp1_premium_pct": 1.00, "tp1_qty_fraction": 0.667,
        "profit_lock_mode": "trailing", "trail_pct": 0.20, "runner_target_pct": 2.5,
        "profit_lock_arm_pct": 0.05, "profit_lock_arm_scope": "post_tp1"},
    # Same, but a TIGHT trail -- "would a tighter leash have kept more of the runner?"
    "tp1_100_trail_10": {
        "premium_stop_pct": -0.50, "tp1_premium_pct": 1.00, "tp1_qty_fraction": 0.667,
        "profit_lock_mode": "trailing", "trail_pct": 0.10, "runner_target_pct": 2.5,
        "profit_lock_arm_pct": 0.05, "profit_lock_arm_scope": "post_tp1"},
    # No TP1 at all -- pure trailing ride from the arm point. The "hold longer" end.
    #
    # arm_scope MUST be "full" here (2026-08-04 dead-knob fix). Every OTHER shape in this
    # menu pins "post_tp1" because that is what live does, but this shape switches TP1 OFF
    # (tp1_premium_pct 999 is unreachable by construction). Under "post_tp1" the profit lock
    # can only arm on a TP1 fill that never comes, so `trail_pct` was INERT and this policy
    # silently degenerated into a byte-identical copy of `hold_to_time_stop` -- verified on
    # 2026-08-04, where the two columns matched to the cent on all 10 winners ($23,380 each).
    # That made the "hold longer" end of the axis look twice as corroborated as it was, and
    # handed `capture_vs_best_policy` a denominator chosen from a menu with a duplicate in it.
    # "full" is a real production arm_scope value (ARM_SCOPE_FULL, used for simulator
    # parity), so this stays a live-executable policy -- it is now the shape its name
    # already claimed to be. Guarded by test_no_tp1_shapes_must_arm_the_lock_or_trail_is_dead.
    "trail_only_no_tp1": {
        "premium_stop_pct": -0.50, "tp1_premium_pct": 999.0, "tp1_qty_fraction": 1.0,
        "profit_lock_mode": "trailing", "trail_pct": 0.20, "runner_target_pct": 2.5,
        "profit_lock_arm_pct": 0.05, "profit_lock_arm_scope": "full"},
    # Ride to the 15:50 time stop / -50% cap. The degenerate "never take profit" bound.
    "hold_to_time_stop": {
        "premium_stop_pct": -0.50, "tp1_premium_pct": 999.0, "tp1_qty_fraction": 1.0,
        "profit_lock_mode": "fixed", "trail_pct": 0.125, "runner_target_pct": 999.0,
        "profit_lock_arm_pct": 0.05, "profit_lock_arm_scope": "post_tp1"},
}

# Aggregate-honesty floor. Below this many fully-replayed winners, the module still prints
# every per-trade row but REFUSES to headline a capture rate -- an aggregate over a handful
# of trades is an anecdote wearing a percent sign.
MIN_N_FOR_AGGREGATE = 8

# WAVE GROUPING (2026-08-04). The fleet's arms fill the SAME signal within seconds of each
# other, so the natural unit of "a trade the firm took" is not one arm's position but the
# WAVE: every arm's entry into the same impulse. Judging capture per-arm hides the thing J
# actually asked about -- on 08-04 five arms entered 763C between 09:50 and 09:58 and got
# five DIFFERENT outcomes from one signal. A new wave starts when the gap since the previous
# entry exceeds this many minutes.
WAVE_GAP_MIN = 15

# DATA-INTEGRITY RAIL (2026-08-04, the second silent degradation of this fetch path --
# cf. backtest/tests/test_exit_parity_data_creds_2026_08_03.py for the first).
#
# THE INVARIANT: a position in this module's population EXISTS because the broker filled it.
# A broker fill is proof the contract traded. Therefore ZERO OPRA bars for such a symbol is
# always a DATA FAULT (403/401/outage/indexing lag) and NEVER a legitimate "nothing to see".
# The old code counted `n_no_bars` and printed a warning, then went right on publishing a
# capture headline computed over whatever survived. On 2026-08-04 that turned 10 winners into
# 1 and headlined `capture_vs_best_policy=4.3%` -- a number assembled from a single $9 trade
# while $4,726 of winners sat unfetched. The warning was true and the headline was garbage,
# which is the exact C7 shape: audit the OUTPUT, not the exit code.
#
# So: any fetch loss at all DEGRADES the run, and a degraded run publishes NO headline
# capture number (None), while still printing every per-trade row it did manage to build.
# A missing number forces a human to look; a plausible wrong number does not.
DATA_INTEGRITY_OK = "OK"
DATA_INTEGRITY_DEGRADED = "DEGRADED_MISSING_BARS"

GIVEBACK_MATERIAL_PCT = 0.25   # a leg that realized <=75% of the premium available to it

# THE conditioning warning. Printed on every report, directly under the headline number,
# because it is the single most likely way a reader misuses this module's output.
SELECTION_CAVEAT = (
    "**⚠ WINNERS-ONLY SAMPLE — this is NOT a policy comparison.** Every number here is "
    "computed over trades that ALREADY WON. That conditions on the outcome: a policy's "
    "column total answers 'what would this policy have made on the trades our current "
    "exits happened to win', NOT 'what would this policy make'. Switching policy changes "
    "which trades win at all, and says nothing about its effect on the losers — which "
    "vastly outnumber these. A capture rate above 100% therefore means our shipped exits "
    "top this menu ON WINNERS; it is NOT evidence that the menu's runner-up should be "
    "adopted, and a capture rate below 100% is NOT evidence that it should. Only a "
    "pre-registered A/B over the FULL trade population can support an exit change.")


# ---------- pure helpers (unit-tested; no I/O) ---------------------------------------------

def entry_bar_minute(entry_ts_utc: str) -> str:
    """PURE: floor an ISO-8601 UTC fill timestamp to its owning 1-min BAR key.

    Bar `t` values from Alpaca are minute-aligned RFC-3339 (`2026-07-31T16:19:00Z`); a fill
    timestamp carries seconds/micros (`2026-07-31T16:19:02.259Z`). Comparing them as raw
    strings is what makes the entry-bar question ambiguous, so it is resolved ONCE here:
    everything is reduced to `YYYY-MM-DDTHH:MM`, the bar's identity."""
    s = str(entry_ts_utc).replace("Z", "").replace("+00:00", "")
    return s[:16]  # YYYY-MM-DDTHH:MM


def exit_eligible_bars(bars: list[dict], entry_ts_utc: str) -> list[dict]:
    """PURE: the bars a live position could actually have been EXITED on -- strictly AFTER
    the entry bar (entry+1).

    Per markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md: the live engine runs its
    exit-management pass BEFORE its entry pass within a tick, so a position created by tick
    N's entry branch does not exist when tick N's exit pass already ran -- its first possible
    exit evaluation is tick N+1. Enforced with strict `>` on the minute key, so the entry
    bar's own high can never be sold into."""
    ebm = entry_bar_minute(entry_ts_utc)
    return [b for b in bars if entry_bar_minute(b["t"]) > ebm]


def high_water(bars: list[dict]) -> tuple[float | None, str | None]:
    """PURE: (highest high, its bar timestamp) over `bars`. (None, None) when empty."""
    best_v, best_t = None, None
    for b in bars:
        h = float(b["h"])
        if best_v is None or h > best_v:
            best_v, best_t = h, b["t"]
    return best_v, best_t


def bars_between(bars: list[dict], entry_ts_utc: str, last_exit_ts_utc: str) -> list[dict]:
    """PURE: the exit-eligible bars during which the position was ACTUALLY OPEN -- entry+1
    through the bar carrying the final exit fill, inclusive.

    Kept distinct from the full post-entry day because the two answer DIFFERENT questions and
    conflating them is how a report lies: "what did the engine see while it was in the trade"
    (this) is not "what did the trade go on to do after we left" (the day-scoped view). On
    2026-07-31 the 746C position was flat by 12:43 ET while the contract's day high printed at
    15:54 ET -- reporting the latter as the position's high-water would have been nonsense."""
    ebm = entry_bar_minute(entry_ts_utc)
    xbm = entry_bar_minute(last_exit_ts_utc)
    return [b for b in bars if ebm < entry_bar_minute(b["t"]) <= xbm]


def oracle_pnl(bars: list[dict], entry_price: float, qty: float) -> float | None:
    """PURE: the UNACHIEVABLE reference -- sell the entire position at the post-entry
    high-water bar's HIGH. No live rule can time this; it exists only to bound the universe.
    Never a target, never a denominator for the headline.

    Day-scoped by design (the caller passes ALL post-entry eligible bars): the question it
    bounds is "what did this contract ever offer after we were in it", which is a strictly
    wider window than the position's own holding period."""
    hw, _ = high_water(bars)
    if hw is None or not qty:
        return None
    return round((hw - entry_price) * qty * 100, 2)


def entry_fill_quality(entry_price: float, entry_bar: dict | None) -> dict:
    """PURE: where in its own signal-minute the entry actually filled. The winner-side mirror
    of trade_autopsy's `paid_the_spike` tag: paying the entry bar's high is a real, silent
    cost on a trade that still ends up green, and it is invisible unless measured."""
    if not entry_bar:
        return {"bar_low": None, "bar_high": None, "paid_above_low_pct": None,
                "filled_at_bar_high": None}
    lo, hi = float(entry_bar["l"]), float(entry_bar["h"])
    return {
        "bar_low": lo, "bar_high": hi,
        "paid_above_low_pct": round(entry_price / lo - 1.0, 4) if lo > 0 else None,
        "filled_at_bar_high": bool(hi > 0 and entry_price >= hi - 1e-9),
    }


def leg_giveback(leg_price: float, peak_before_leg: float | None, qty: float) -> dict:
    """PURE: what ONE exit leg gave back -- the premium that was available to it (the
    position's high-water mark at or before that leg fired) vs what it actually realized.

    `peak_before_leg` None (no bar coverage) -> honest None fields rather than a guess."""
    if peak_before_leg is None or peak_before_leg <= 0:
        return {"peak_before": None, "giveback_per_contract": None,
                "giveback_dollars": None, "giveback_pct_of_peak": None}
    gb = round(peak_before_leg - leg_price, 4)
    return {
        "peak_before": round(peak_before_leg, 4),
        "giveback_per_contract": gb,
        "giveback_dollars": round(gb * qty * 100, 2),
        "giveback_pct_of_peak": round(gb / peak_before_leg, 4),
    }


def per_trade_capture(realized: float, variant_pnls: dict) -> dict:
    """PURE: the per-trade view. `best_variant` is the max over the FIXED menu -- note this
    is already a hindsight selection at trade level and is labelled as such everywhere it
    surfaces. None-valued variants (unreplayable) are ignored, not zero-filled."""
    usable = {k: v for k, v in variant_pnls.items() if v is not None}
    if not usable:
        return {"best_variant": None, "best_variant_pnl": None,
                "capture_vs_best_variant": None, "left_on_table": None}
    name = max(usable, key=lambda k: usable[k])
    best = usable[name]
    cap = round(realized / best, 4) if best > 0 else None
    return {"best_variant": name, "best_variant_pnl": round(best, 2),
            "capture_vs_best_variant": cap,
            "left_on_table": round(best - realized, 2)}


def aggregate_capture(rows: list[dict], menu_names: tuple[str, ...],
                      n_no_bars: int = 0) -> dict:
    """PURE: the population statistic -- THE deliverable.

    Only rows with a COMPLETE variant grid participate (`_complete` True): a trade missing
    one variant would otherwise inflate whichever policies it does have. Incomplete rows are
    COUNTED (`n_excluded_incomplete`), never silently dropped (C7).

    Returns `capture_vs_best_policy` -- realized_total over the best SINGLE fixed policy's
    total. That policy is selectable in advance and applied to every trade, which is what
    makes this the honest headline. `capture_vs_per_trade_best` (hindsight shape-picking)
    and `capture_vs_oracle` (unachievable) are returned alongside as disclosure only.

    Refuses to headline below MIN_N_FOR_AGGREGATE (`sufficient_n` False) -- the number is
    still computed and shown, but flagged as an anecdote, not a statistic.

    `n_no_bars` (>0) means the population was SILENTLY TRUNCATED by a data fault -- see the
    DATA_INTEGRITY_* rail above. Such a run publishes NO headline (`capture_vs_best_policy`
    is None) regardless of how good the surviving rows look, because the denominator is no
    longer the population it claims to be. Everything else is still computed so a human can
    inspect what did land."""
    complete = [r for r in rows if r.get("_complete")]
    n = len(complete)
    degraded = n_no_bars > 0
    out = {
        "n_winners_scored": n,
        "n_excluded_incomplete": len(rows) - n,
        "n_no_bars": n_no_bars,
        "data_integrity": DATA_INTEGRITY_DEGRADED if degraded else DATA_INTEGRITY_OK,
        "sufficient_n": n >= MIN_N_FOR_AGGREGATE,
        "min_n_for_aggregate": MIN_N_FOR_AGGREGATE,
        "realized_total": None, "policy_totals": {},
        "best_policy": None, "best_policy_total": None,
        "capture_vs_best_policy": None,
        "per_trade_best_total": None, "capture_vs_per_trade_best": None,
        "oracle_total": None, "capture_vs_oracle": None,
    }
    if not complete:
        return out
    realized_total = round(sum(r["realized_pnl"] for r in complete), 2)
    out["realized_total"] = realized_total

    totals = {name: round(sum(r["variants"][name] for r in complete), 2)
              for name in menu_names}
    out["policy_totals"] = totals
    best_name = max(totals, key=lambda k: totals[k])
    best_total = totals[best_name]
    out["best_policy"], out["best_policy_total"] = best_name, best_total
    # A non-positive denominator makes the ratio meaningless -- say None, never a number.
    out["capture_vs_best_policy"] = (round(realized_total / best_total, 4)
                                     if best_total > 0 else None)

    ptb = [r["capture"]["best_variant_pnl"] for r in complete
           if r.get("capture", {}).get("best_variant_pnl") is not None]
    if len(ptb) == n:
        ptb_total = round(sum(ptb), 2)
        out["per_trade_best_total"] = ptb_total
        out["capture_vs_per_trade_best"] = (round(realized_total / ptb_total, 4)
                                            if ptb_total > 0 else None)

    orc = [r["oracle_pnl"] for r in complete if r.get("oracle_pnl") is not None]
    if len(orc) == n:
        orc_total = round(sum(orc), 2)
        out["oracle_total"] = orc_total
        out["capture_vs_oracle"] = (round(realized_total / orc_total, 4)
                                    if orc_total > 0 else None)
    if degraded:
        # The population is not the population this ratio claims to describe. Withhold every
        # capture RATIO (the numbers a reader would quote) while leaving the raw totals and
        # per-trade rows visible for inspection. A missing number forces a human to look; a
        # plausible wrong number does not.
        out["capture_vs_best_policy"] = None
        out["capture_vs_per_trade_best"] = None
        out["capture_vs_oracle"] = None
    return out


def _ts_minutes(ts_utc: str) -> int:
    """PURE: minutes-since-midnight for an ISO-8601 UTC timestamp. Used only for GAP
    arithmetic between entries on the same date, so the date part is irrelevant."""
    hh, mm = int(str(ts_utc)[11:13]), int(str(ts_utc)[14:16])
    return hh * 60 + mm


def assign_waves(rows: list[dict], gap_min: int = WAVE_GAP_MIN) -> list[dict]:
    """PURE: group positions into ENTRY WAVES -- one wave per impulse the fleet traded.

    The fleet's arms all consume the same shared signal, so five arms entering 763C between
    09:50 and 09:58 are five expressions of ONE decision, not five decisions. Grouping by arm
    answers "how did safe-3 do"; grouping by WAVE answers "how did the firm do on that
    signal", which is the question a capture rate is actually for.

    A new wave opens when the gap since the PREVIOUS entry exceeds `gap_min` minutes. Note
    this deliberately clusters on TIME, not strike: on 2026-08-04 the open impulse spans two
    strikes (762C then 763C) and is one wave, while 769C appears in two waves 36 minutes
    apart (11:52, all losers; 12:28, all winners) -- collapsing those by strike would average
    a losing cohort into a winning one and hide the only interesting thing about them.

    Rows lacking `entry_ts_utc` are returned in a trailing `unassigned` wave rather than
    dropped (C7). Input rows are never mutated."""
    dated = [r for r in rows if r.get("entry_ts_utc")]
    orphans = [r for r in rows if not r.get("entry_ts_utc")]
    dated.sort(key=lambda r: str(r["entry_ts_utc"]))

    waves: list[dict] = []
    cur: list[dict] = []
    prev_m = None
    for r in dated:
        m = _ts_minutes(r["entry_ts_utc"])
        if prev_m is not None and (m - prev_m) > gap_min:
            waves.append({"rows": cur})
            cur = []
        cur.append(r)
        prev_m = m
    if cur:
        waves.append({"rows": cur})

    out = []
    for i, w in enumerate(waves, start=1):
        rs = w["rows"]
        strikes = sorted({str(r.get("symbol", ""))[-8:-3].lstrip("0") for r in rs})
        out.append({
            "wave_id": i,
            "label": "/".join(s for s in strikes if s) + "C",
            "t_start_et": (rs[0].get("entry", {}) or {}).get("ts_et")
            or str(rs[0]["entry_ts_utc"])[11:19],
            "t_end_et": (rs[-1].get("entry", {}) or {}).get("ts_et")
            or str(rs[-1]["entry_ts_utc"])[11:19],
            "n_positions": len(rs),
            "arms": sorted({r.get("arm") for r in rs if r.get("arm")}),
            "realized_pnl": round(sum(r.get("realized_pnl", 0.0) for r in rs), 2),
            "rows": rs,
        })
    if orphans:
        out.append({"wave_id": None, "label": "unassigned", "t_start_et": None,
                    "t_end_et": None, "n_positions": len(orphans),
                    "arms": sorted({r.get("arm") for r in orphans if r.get("arm")}),
                    "realized_pnl": round(sum(r.get("realized_pnl", 0.0)
                                              for r in orphans), 2),
                    "rows": orphans})
    return out


def wave_capture(waves: list[dict], menu_names: tuple[str, ...]) -> list[dict]:
    """PURE: per-wave capture, each wave scored by the SAME single-fixed-policy rule the book
    headline uses (`aggregate_capture`), so a wave row and the book row mean the same thing.

    Per-wave `best_policy` is NOT a proposal: the best policy for one wave is a hindsight
    selection over ~5 positions. It is reported to show WHERE the book's capture gap lives
    (which impulse leaked the money), not to pick a shape."""
    out = []
    for w in waves:
        agg = aggregate_capture(w["rows"], menu_names)
        out.append({
            "wave_id": w["wave_id"], "label": w["label"],
            "t_start_et": w["t_start_et"], "t_end_et": w["t_end_et"],
            "arms": w["arms"], "n_positions": w["n_positions"],
            "realized_total": agg["realized_total"],
            "best_policy": agg["best_policy"],
            "best_policy_total": agg["best_policy_total"],
            "capture_vs_best_policy": agg["capture_vs_best_policy"],
            "oracle_total": agg["oracle_total"],
            "policy_totals": agg["policy_totals"],
        })
    return out


def runner_cohort_stats(rows: list[dict]) -> dict:
    """PURE: the standing answer to J's 2026-07-31 question -- "the runner exited BELOW where
    TP1 exited; should we stay in longer or exit better?"

    Scoped to the only cohort the question is well-posed for: winners that scaled out (a TP1
    leg AND at least one later leg). A winner that closed in one leg has no runner to judge.
    Reports the median giveback rather than the mean -- one 90%-giveback runner should not
    set the number for the cohort."""
    both = [r for r in rows
            if any(lg.get("stage") == "tp1" for lg in r["legs"])
            and any(lg.get("stage") not in ("tp1", None) for lg in r["legs"])]
    gbs = sorted(lg["giveback"]["giveback_pct_of_peak"]
                 for r in both for lg in r["legs"]
                 if lg.get("stage") not in ("tp1", None)
                 and lg["giveback"]["giveback_pct_of_peak"] is not None)
    med = gbs[len(gbs) // 2] if gbs else None
    return {
        "n_scaled_out_winners": len(both),
        "n_runner_below_tp1": sum(1 for r in both
                                  if "runner_underperformed_tp1" in r["tags"]),
        "n_runner_material_giveback": sum(1 for r in both
                                          if "runner_material_giveback" in r["tags"]),
        "median_runner_giveback_pct": round(med, 4) if med is not None else None,
        "n_runner_legs_measured": len(gbs),
    }


def attribution_coverage(rows: list[dict]) -> dict:
    """PURE: how much of the report is actually attributed vs honestly unknown. A leg whose
    closing STAGE could not be matched to an engine action is counted, never quietly
    rendered as '?' and forgotten (C7 -- audit the output, not the exit code)."""
    total = sum(len(r["legs"]) for r in rows)
    unattr = sum(1 for r in rows for lg in r["legs"] if lg.get("stage") is None)
    return {"legs_total": total, "legs_unattributed": unattr,
            "attribution_pct": round((total - unattr) / total, 4) if total else None}


def classify_winner(realized: float, legs: list[dict], variant_pnls: dict) -> list[str]:
    """PURE: descriptive tags for ONE winning trade. Tags DESCRIBE, they never prescribe --
    no tag here is an instruction to change a knob."""
    tags: list[str] = []
    tp1_legs = [lg for lg in legs if lg.get("stage") == "tp1"]
    runner_legs = [lg for lg in legs if lg.get("stage") in ("trail", "be_stop", "structure_stop",
                                                            "premium_stop", "time_stop",
                                                            "runner_target")]
    # THE 2026-07-31 SHAPE: the runner realized a LOWER per-contract price than TP1 did.
    if tp1_legs and runner_legs:
        tp1_px = max(float(lg["price"]) for lg in tp1_legs)
        run_px = max(float(lg["price"]) for lg in runner_legs)
        if run_px < tp1_px:
            tags.append("runner_underperformed_tp1")
    for lg in runner_legs:
        gb = lg.get("giveback", {}).get("giveback_pct_of_peak")
        if gb is not None and gb >= GIVEBACK_MATERIAL_PCT:
            tags.append("runner_material_giveback")
            break
    usable = {k: v for k, v in variant_pnls.items() if v is not None}
    if usable and realized >= max(usable.values()):
        # Honesty tag, the mirror of trade_autopsy's `exit_beat_theta`: our SHIPPED exit beat
        # every fixed alternative on this trade. Without this the report only ever finds fault.
        tags.append("shipped_exit_beat_menu")
    if usable and max(usable.values()) > 0 and realized / max(usable.values()) < 0.5:
        tags.append("captured_under_half")
    return tags


def resolve_shipped_shape(placement: dict | None, arm_patch: dict | None) -> dict:
    """PURE: reconstruct the exit contract a position was ACTUALLY placed under, so the
    replay grid can carry a faithful `_shipped` control alongside the fixed menu.

    Layering mirrors fleet_executor._exit_shape_dict: exit_manager defaults <- the arm's
    accounts.json `params_patch.exit_patch` <- the as-placed `placement` block (most
    authoritative -- it is what the actuator actually resolved at entry time)."""
    shape = {"premium_stop_pct": -0.50, "tp1_premium_pct": 0.30, "tp1_qty_fraction": 0.667,
             "profit_lock_mode": "fixed", "trail_pct": 0.125, "runner_target_pct": 2.5,
             "profit_lock_arm_pct": 0.05, "profit_lock_arm_scope": "post_tp1"}
    for src in (arm_patch or {}, placement or {}):
        for k in ("premium_stop_pct", "tp1_premium_pct", "tp1_qty_fraction",
                  "profit_lock_mode", "trail_pct", "runner_target_pct",
                  "profit_lock_arm_pct", "profit_lock_arm_scope"):
            if src.get(k) is not None:
                shape[k] = src[k]
    # stop_mode is deliberately NOT carried through: `replay_position` never supplies
    # `last_closed_5m_close`, so a "structure" mode would silently become a no-op stop
    # rather than the chart stop it names. Premium mode with the -50% catastrophe cap is
    # the honest premium-only approximation, and the divergence is disclosed in the report.
    return shape


# ---------- I/O layer ----------------------------------------------------------------------

def load_arm_exit_patches(path: Path = ACCOUNTS_JSON) -> dict:
    """{arm_id: exit_patch} from the fleet roster. Fail-open -> {} (a missing patch only
    costs shipped-shape fidelity, never the run)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for arm in data.get("arms", []) or []:
        if not isinstance(arm, dict):
            continue
        aid = arm.get("arm_id") or arm.get("id")
        patch = (arm.get("params_patch") or {})
        if aid:
            out[str(aid)] = patch
    return out


def _decision_path(arm: str):
    """(path, is_core) for an arm's decision ledger. Mirrors trade_autopsy's taxonomy."""
    import trade_autopsy as ta
    if arm in ta.FLEET_REST_ARMS:
        return STATE / "fleet" / arm / "decisions.jsonl", False
    if arm in ta.CORE_ARM_ACCOUNT:
        return CORE_DECISIONS, True
    return None, False


def load_arm_rows(arm: str, date_et: str) -> list[dict]:
    """All decision rows for `arm` on `date_et`, in ts order. Core rows are filtered to the
    arm's account. Fail-open -> []."""
    import trade_autopsy as ta
    path, is_core = _decision_path(arm)
    if path is None:
        return []
    rows = ta.load_decision_rows(path)
    if is_core:
        account = ta.CORE_ARM_ACCOUNT.get(arm)
        rows = [r for r in rows if r.get("account") == account]
    out = [r for r in rows if str(r.get("ts_et", "")).startswith(date_et)]
    out.sort(key=lambda r: str(r.get("ts_et", "")))
    return out


def find_entry_decision(arm_rows: list[dict], symbol: str) -> dict | None:
    """The ENTER row that opened `symbol` -- matched on the placement/exec block's own
    symbol, so it can never bind to a different contract on a multi-trade day."""
    for r in arm_rows:
        for blk_key in ("placement", "exec"):
            blk = r.get(blk_key)
            if isinstance(blk, dict) and blk.get("symbol") == symbol and blk.get("placed"):
                return r
    for r in arm_rows:  # fallback: placed flag absent on some core rows
        for blk_key in ("placement", "exec"):
            blk = r.get(blk_key)
            if isinstance(blk, dict) and blk.get("symbol") == symbol:
                return r
    return None


def load_exit_trace(arm_rows: list[dict], symbol: str) -> list[dict]:
    """The engine's OWN in-trade record for `symbol`: every tick's `exit_pass` entry, which
    is what the live exit_actuator wrote as it managed the position. This is the literal
    answer to J's "what was it thinking while it was in the trade" -- not a reconstruction."""
    trace = []
    for r in arm_rows:
        for ep in (r.get("exit_pass") or []):
            if not isinstance(ep, dict) or ep.get("symbol") != symbol:
                continue
            trace.append({
                "ts_et": str(r.get("ts_et", ""))[11:19],
                "open_qty": ep.get("open_qty"),
                "best_premium": ep.get("best_premium"),
                "worst_premium": ep.get("worst_premium"),
                "tp1_filled": ep.get("tp1_filled"),
                "runner_stop": ep.get("runner_stop"),
                "stop_mode": ep.get("stop_mode"),
                "trigger_level": ep.get("trigger_level"),
                "last_closed_5m_close": ep.get("last_closed_5m_close"),
                "actions": [{"kind": a.get("kind"), "qty": a.get("qty"),
                             "stage": a.get("stage"), "reason": a.get("reason"),
                             "new_stop_premium": a.get("new_stop_premium")}
                            for a in (ep.get("actions") or []) if isinstance(a, dict)],
            })
    return trace


def stage_for_exit_fill(trace: list[dict], fill_ts_utc: str, qty: float) -> str | None:
    """Best-effort: which exit_manager STAGE closed a given broker exit fill.

    Matched on (qty, nearest preceding tick that emitted a SELL action of that qty). The
    engine logs its intent on the tick it acts; the broker fill lands seconds later, so the
    action always precedes its fill. None on any miss -- honest absence, never a guess."""
    fill_hhmmss = str(fill_ts_utc)[11:19]
    best = None
    for row in trace:
        for a in row["actions"]:
            if a.get("kind") not in ("SELL_PARTIAL", "SELL_ALL"):
                continue
            if a.get("qty") is not None and abs(float(a["qty"]) - float(qty)) > 1e-9:
                continue
            if row["ts_et"] <= fill_hhmmss and (best is None or row["ts_et"] >= best[0]):
                best = (row["ts_et"], a.get("stage"))
    return best[1] if best else None


def autopsy_winner(pos: dict, esp, bars: list[dict], arm_patches: dict) -> dict | None:
    """Full anatomy for ONE winning position. None when the bar record cannot support it."""
    entry_ts = pos["entry_ts_utc"]
    entry_price = float(pos["entry_price"])
    qty = float(pos["entry_qty"])
    elig = exit_eligible_bars(bars, entry_ts)
    if not elig:
        return None

    arm_rows = load_arm_rows(pos["arm"], pos["date_et"])
    entry_row = find_entry_decision(arm_rows, pos["symbol"])
    trace = load_exit_trace(arm_rows, pos["symbol"])
    placement = None
    if entry_row:
        placement = entry_row.get("placement") or entry_row.get("exec")

    # TWO high-water marks, deliberately separate (see bars_between's docstring):
    #   in-trade  -- what the engine actually saw while holding. Answers "what was it
    #                thinking / seeing in the trade".
    #   post-entry-- everything the contract offered after entry, including after we were
    #                flat. Answers "what did we leave", and is what the ORACLE bounds.
    last_exit_ts = max(ef["ts_utc"] for ef in pos["exit_fills"])
    in_trade = bars_between(bars, entry_ts, last_exit_ts)
    hw_in, hw_in_ts = high_water(in_trade)
    hw_day, hw_day_ts = high_water(elig)
    entry_bar = next((b for b in bars
                      if entry_bar_minute(b["t"]) == entry_bar_minute(entry_ts)), None)

    # ---- exit legs, each attributed to the rule that fired it + what it gave back --------
    legs = []
    for ef in sorted(pos["exit_fills"], key=lambda f: f["ts_utc"]):
        # The peak AVAILABLE to this leg = high-water over exit-eligible bars up to and
        # including the leg's own bar. A leg cannot be blamed for premium that only
        # printed after it had already left.
        upto = [b for b in elig if entry_bar_minute(b["t"]) <= entry_bar_minute(ef["ts_utc"])]
        peak_before, _ = high_water(upto)
        legs.append({
            "ts_et": str(ef.get("ts_et", ef["ts_utc"]))[11:19],
            "qty": ef["qty"], "price": ef["price"],
            "pnl": round((ef["price"] - entry_price) * ef["qty"] * 100, 2),
            "pct_vs_entry": round(ef["price"] / entry_price - 1.0, 4) if entry_price else None,
            "stage": stage_for_exit_fill(trace, ef["ts_utc"], ef["qty"]),
            "giveback": leg_giveback(float(ef["price"]), peak_before, ef["qty"]),
        })

    # ---- the live-executable exit-variant grid (entry+1 enforced by pre-filtering) -------
    # `esp.replay_position` filters `>= entry_ts` internally; handing it the already
    # entry+1-filtered list makes that internal filter a no-op instead of editing a shared
    # frozen function (C34 blast radius).
    variants: dict[str, float | None] = {}
    for name, shape in EXIT_MENU.items():
        try:
            variants[name] = esp.replay_position(pos, elig, shape).get("pnl")
        except Exception:  # noqa: BLE001 -- one bad shape must never kill the row
            variants[name] = None
    shipped_shape = resolve_shipped_shape(placement, arm_patches.get(pos["arm"]))
    try:
        shipped_replay = esp.replay_position(pos, elig, shipped_shape).get("pnl")
    except Exception:  # noqa: BLE001
        shipped_replay = None

    realized = round(pos["actual_exit_pnl"], 2)
    cap = per_trade_capture(realized, variants)
    orc = oracle_pnl(elig, entry_price, qty)

    import trade_autopsy as ta
    return {
        "date": pos["date_et"], "arm": pos["arm"], "symbol": pos["symbol"],
        # Raw entry timestamp: the key `assign_waves` clusters on. Kept as its own field
        # (not derived from entry.ts_et, which is None whenever the decision row could not
        # be matched) so wave grouping never silently loses a position.
        "entry_ts_utc": entry_ts,
        "strategy": ta.lookup_strategy(pos["arm"], pos["symbol"], entry_ts),
        # --- WHY IT ENTERED -------------------------------------------------------------
        "entry": {
            "ts_et": str(entry_row.get("ts_et", ""))[11:19] if entry_row else None,
            "action": entry_row.get("action") if entry_row else None,
            "setup_name": (entry_row.get("setup_name") or entry_row.get("setup")) if entry_row else None,
            "side": entry_row.get("side") if entry_row else None,
            "trigger_level": entry_row.get("trigger_level") if entry_row else None,
            "quality": entry_row.get("quality") if entry_row else None,
            "risk_code": entry_row.get("risk_code") if entry_row else None,
            "reason": entry_row.get("reason") if entry_row else None,
            "bull_score": entry_row.get("bull_score") if entry_row else None,
            "bear_score": entry_row.get("bear_score") if entry_row else None,
            # --- WHY THAT STRIKE --------------------------------------------------------
            "strike": entry_row.get("strike") if entry_row else None,
            "strike_minus_trigger": (
                round(float(entry_row["strike"]) - float(entry_row["trigger_level"]), 2)
                if entry_row and entry_row.get("strike") is not None
                and entry_row.get("trigger_level") is not None else None),
            "quoted_premium": entry_row.get("premium") if entry_row else None,
            "stop_display": (placement or {}).get("stop_display"),
            "stop_mode": (placement or {}).get("stop_mode"),
        },
        "entry_price": entry_price, "qty": qty,
        "entry_fill_quality": entry_fill_quality(entry_price, entry_bar),
        "realized_pnl": realized,
        # --- WHAT IT SAW ----------------------------------------------------------------
        # In-trade: the high-water the position actually lived through (entry+1 -> last exit).
        "in_trade_high": round(hw_in, 4) if hw_in is not None else None,
        "in_trade_high_ts_utc": hw_in_ts,
        "in_trade_high_pct": (round(hw_in / entry_price - 1.0, 4)
                              if hw_in and entry_price else None),
        # Day-scoped: everything after entry, including after we were flat. Oracle's window.
        "post_entry_day_high": round(hw_day, 4) if hw_day is not None else None,
        "post_entry_day_high_ts_utc": hw_day_ts,
        "post_entry_day_high_pct": (round(hw_day / entry_price - 1.0, 4)
                                    if hw_day and entry_price else None),
        "n_ticks_in_trade": len(trace),
        "timeline": trace,
        # --- WHY EACH LEG LEFT / WHAT IT GAVE BACK --------------------------------------
        "legs": legs,
        # --- WHAT ELSE WAS ON THE TABLE -------------------------------------------------
        "shipped_shape": shipped_shape,
        "shipped_shape_replay_pnl": shipped_replay,
        "variants": variants,
        "capture": cap,
        "oracle_pnl": orc,
        "tags": classify_winner(realized, legs, variants),
        "_complete": all(v is not None for v in variants.values()),
    }


# ---------- render -------------------------------------------------------------------------

def _pct(x) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def _usd(x) -> str:
    return "n/a" if x is None else f"${x:,.2f}"


def render_md(rows: list[dict], agg: dict, scope: str, n_no_bars: int,
              waves: list[dict] | None = None) -> str:
    L: list[str] = []
    L.append(f"# Winner autopsy — {scope}")
    L.append("")
    L.append(f"_Generated {et_now().isoformat()} ET · real OPRA 1-min bars · entry+1 convention "
             f"· $0 (pure Python)._")
    L.append("")
    L.append("> **DESCRIPTIVE ONLY.** This report measures; it ratifies nothing. Every exit "
             "variant below is a replay, not a proposal. Any change to a live exit knob "
             "requires its own pre-registered A/B — a good-looking number on a small winner "
             "population is an anecdote, not evidence.")
    L.append("")

    # ---- data integrity, ABOVE the headline -------------------------------------------
    # Deliberately first: a reader who stops after one screen must see that the population
    # was truncated BEFORE they see any number computed over it.
    if agg.get("data_integrity") == DATA_INTEGRITY_DEGRADED:
        L.append(f"> 🚨 **DATA-INTEGRITY: DEGRADED — no capture headline published.** "
                 f"{agg.get('n_no_bars')} winning position(s) that the broker DID fill could "
                 f"not be priced (zero OPRA bars returned). A broker fill proves the contract "
                 f"traded, so this is a DATA FAULT (403/401/indexing lag), never an absence "
                 f"of data. Every capture ratio is withheld — the surviving rows are not the "
                 f"population a ratio would claim to describe. Per-trade rows below are still "
                 f"valid individually. **Re-run once the data source is healthy.**")
        L.append("")

    # ---- the headline ---------------------------------------------------------------
    L.append("## Capture rate — how much of what our winners offered did we keep?")
    L.append("")
    n = agg["n_winners_scored"]
    if n == 0:
        L.append("- No fully-replayable winners in scope.")
    else:
        cap = agg["capture_vs_best_policy"]
        flag = "" if agg["sufficient_n"] else (
            f" ⚠ **n={n} < {agg['min_n_for_aggregate']} — ANECDOTE, not a statistic.**")
        L.append(f"- **CAPTURE (honest headline): {_pct(cap)}** of the best single fixed "
                 f"policy, over **n={n}** winners.{flag}")
        L.append(f"  - Realized (broker fills): **{_usd(agg['realized_total'])}**")
        L.append(f"  - Best single fixed policy: `{agg['best_policy']}` → "
                 f"{_usd(agg['best_policy_total'])}")
        L.append(f"- Disclosure — *hindsight shape-picking* (best variant chosen per trade, "
                 f"NOT live-selectable): {_pct(agg['capture_vs_per_trade_best'])} of "
                 f"{_usd(agg['per_trade_best_total'])}.")
        L.append(f"- Disclosure — *oracle* (sell 100% at the post-entry high; no live rule "
                 f"can do this): {_pct(agg['capture_vs_oracle'])} of "
                 f"{_usd(agg['oracle_total'])}.")
        if agg["n_excluded_incomplete"]:
            L.append(f"- ⚠ {agg['n_excluded_incomplete']} winner(s) excluded from the "
                     f"aggregate (incomplete variant grid).")
    if n_no_bars:
        L.append(f"- ⚠ {n_no_bars} winning position(s) had NO OPRA bars available and are "
                 f"absent entirely (never zero-filled).")
    L.append("")
    L.append(SELECTION_CAVEAT)
    L.append("")

    # ---- the runner question, standing ------------------------------------------------
    rc = runner_cohort_stats(rows)
    ac = attribution_coverage(rows)
    L.append("## The runner question (J 2026-07-31: \"stay in longer, or get better exits?\")")
    L.append("")
    if rc["n_scaled_out_winners"] == 0:
        L.append("- No scaled-out winners in scope (a one-leg winner has no runner to judge).")
    else:
        L.append(f"- **{rc['n_runner_below_tp1']} of {rc['n_scaled_out_winners']}** scaled-out "
                 f"winners had the RUNNER realize a **lower price than TP1** — the runner leg, "
                 f"which exists to capture the upside, came out worse than the leg that took "
                 f"profit early.")
        L.append(f"- **{rc['n_runner_material_giveback']} of {rc['n_scaled_out_winners']}** gave "
                 f"back ≥{int(GIVEBACK_MATERIAL_PCT * 100)}% of the premium the runner had "
                 f"already reached.")
        L.append(f"- **Median runner-leg giveback: {_pct(rc['median_runner_giveback_pct'])}** "
                 f"of its own peak (n={rc['n_runner_legs_measured']} runner legs).")
        L.append("")
        L.append("_This is a DESCRIPTIVE recurrence, not a mandate. Note the two answers point "
                 "in opposite directions: the giveback is real, but the 'just hold longer' "
                 "policies (`trail_only_no_tp1` / `hold_to_time_stop`) are usually the WORST "
                 "column in the table above. 'Exit better' and 'stay in longer' are different "
                 "hypotheses and only the first is supported here — both need their own "
                 "pre-registered A/B over the full population before anything is armed._")
    L.append(f"- Attribution coverage: {_pct(ac['attribution_pct'])} of exit legs matched to an "
             f"engine stage ({ac['legs_unattributed']}/{ac['legs_total']} unattributed and "
             f"shown as `?`).")
    L.append("")

    # ---- policy table ---------------------------------------------------------------
    if agg["policy_totals"]:
        L.append("### Fixed-policy totals over the same winners")
        L.append("")
        L.append("| Policy | Total P&L | vs realized |")
        L.append("|---|---:|---:|")
        rt = agg["realized_total"]
        L.append(f"| **(shipped, realized)** | **{_usd(rt)}** | — |")
        for name, tot in sorted(agg["policy_totals"].items(), key=lambda kv: -kv[1]):
            L.append(f"| `{name}` | {_usd(tot)} | {_usd(round(tot - rt, 2))} |")
        L.append("")
        L.append("_Every policy above is live-executable: each is a replay through the real "
                 "`exit_manager.plan_exit_actions` on real 1-min OPRA bars. The menu is "
                 "declared once in `EXIT_MENU` and is never fitted per-run._")
        L.append("")

    # ---- per-wave capture -------------------------------------------------------------
    if waves:
        L.append("### Capture by ENTRY WAVE — which impulse leaked the money?")
        L.append("")
        L.append("| # | wave | ET | arms | n | realized | best fixed policy | that policy | "
                 "capture | ORACLE (unreachable) |")
        L.append("|---:|---|---|---|---:|---:|---|---:|---:|---:|")
        for w in waves:
            L.append(f"| {w['wave_id'] or '—'} | `{w['label']}` | "
                     f"{w['t_start_et'] or '?'}–{w['t_end_et'] or '?'} | "
                     f"{len(w['arms'])} | {w['n_positions']} | "
                     f"{_usd(w['realized_total'])} | `{w['best_policy']}` | "
                     f"{_usd(w['best_policy_total'])} | "
                     f"{_pct(w['capture_vs_best_policy'])} | {_usd(w['oracle_total'])} |")
        L.append("")
        L.append("_A wave = every arm's entry into ONE impulse (new wave after a "
                 f">{WAVE_GAP_MIN}-minute gap). The per-wave `best fixed policy` is a "
                 "HINDSIGHT pick over a handful of positions — it localises WHERE capture "
                 "leaked, it does not nominate a shape. The ORACLE column is the "
                 "sell-everything-at-the-high bound: **unreachable by any live rule**, "
                 "printed only to size the universe, and never a target._")
        L.append("")

    # ---- per-trade anatomy ----------------------------------------------------------
    L.append("## Per-winner anatomy")
    L.append("")
    for r in sorted(rows, key=lambda x: (x["date"], x.get("entry", {}).get("ts_et") or "")):
        e = r["entry"]
        L.append(f"### {r['date']} · {r['arm']} · `{r['symbol']}` · "
                 f"realized {_usd(r['realized_pnl'])}")
        L.append("")
        L.append(f"- **Entry** {e.get('ts_et') or '?'} ET — `{e.get('setup_name') or r.get('strategy') or '?'}`"
                 f" ({e.get('action') or '?'}), quality **{e.get('quality') or '?'}**, "
                 f"trigger **{e.get('trigger_level')}**, risk `{e.get('risk_code')}`.")
        if e.get("reason"):
            L.append(f"  - engine's own words: _{e['reason']}_")
        L.append(f"- **Strike** {e.get('strike')} "
                 f"(trigger {e.get('trigger_level')}, offset "
                 f"{e.get('strike_minus_trigger')}), quoted premium {e.get('quoted_premium')}, "
                 f"filled **{r['entry_price']}** × {int(r['qty'])}, stop "
                 f"`{e.get('stop_display') or e.get('stop_mode') or '?'}`.")
        eq = r.get("entry_fill_quality") or {}
        if eq.get("paid_above_low_pct") is not None:
            spike = " ⚠ **filled at the entry bar's HIGH**" if eq.get("filled_at_bar_high") else ""
            L.append(f"- **Entry fill quality** — paid {_pct(eq['paid_above_low_pct'])} above "
                     f"the signal minute's low (bar {eq['bar_low']}–{eq['bar_high']}).{spike}")
        L.append(f"- **High-water WHILE IN THE TRADE** {r['in_trade_high']} "
                 f"({_pct(r['in_trade_high_pct'])} vs entry) at {r['in_trade_high_ts_utc']} UTC "
                 f"· {r['n_ticks_in_trade']} managed ticks.")
        L.append(f"- **High-water AFTER entry, day-scoped** (includes time we were already "
                 f"flat — this is what the oracle bounds, NOT what the position saw): "
                 f"{r['post_entry_day_high']} ({_pct(r['post_entry_day_high_pct'])}) at "
                 f"{r['post_entry_day_high_ts_utc']} UTC.")
        if r["legs"]:
            L.append("- **Exit legs** (which rule closed each, and what it gave back):")
            L.append("")
            L.append("  | ET | qty | price | vs entry | closed by | peak avail. | giveback |")
            L.append("  |---|---:|---:|---:|---|---:|---:|")
            for lg in r["legs"]:
                gb = lg["giveback"]
                L.append(f"  | {lg['ts_et']} | {int(lg['qty'])} | {lg['price']} | "
                         f"{_pct(lg['pct_vs_entry'])} | `{lg.get('stage') or '?'}` | "
                         f"{gb['peak_before'] if gb['peak_before'] is not None else 'n/a'} | "
                         f"{_usd(gb['giveback_dollars'])} ({_pct(gb['giveback_pct_of_peak'])}) |")
            L.append("")
        # J 2026-07-31: "I wanna know what it was thinking while it was in the trade." This is
        # not a reconstruction -- these are the exit_actuator's OWN per-tick rows.
        if r["timeline"]:
            L.append("- **In-trade timeline** (the engine's own per-tick exit_pass record):")
            L.append("")
            L.append("  | ET | open | best | worst | TP1? | runner stop | action |")
            L.append("  |---|---:|---:|---:|---|---:|---|")
            for t in r["timeline"]:
                acts = "; ".join(
                    f"**{a['kind']} {a.get('qty') or ''} `{a.get('stage')}`** "
                    f"({a.get('reason') or ''})".strip()
                    for a in t["actions"]) or "—"
                L.append(f"  | {t['ts_et']} | {t['open_qty']} | {t['best_premium']} | "
                         f"{t['worst_premium']} | {'yes' if t['tp1_filled'] else 'no'} | "
                         f"{t['runner_stop']} | {acts} |")
            L.append("")
        if r["tags"]:
            L.append(f"- **Tags:** {', '.join('`' + t + '`' for t in r['tags'])}")
        capr = r["capture"]
        L.append(f"- **This trade's variant grid** — best was `{capr.get('best_variant')}` at "
                 f"{_usd(capr.get('best_variant_pnl'))} "
                 f"(realized {_usd(r['realized_pnl'])}, "
                 f"delta {_usd(capr.get('left_on_table'))}); oracle "
                 f"{_usd(r['oracle_pnl'])}.")
        # PARITY CONTROL: the position's OWN as-placed shape, replayed. The gap between this
        # and the realized number is not a modelling choice -- it is slippage + tick
        # granularity + the unmodelled structure stop, i.e. the honest error bar on every
        # OTHER variant in the grid. Rendering it keeps the grid from looking more precise
        # than it is.
        sr = r.get("shipped_shape_replay_pnl")
        if sr is not None:
            L.append(f"- **Parity control** — this trade's own as-placed shape, replayed: "
                     f"{_usd(sr)} vs {_usd(r['realized_pnl'])} realized "
                     f"(gap {_usd(round(sr - r['realized_pnl'], 2))} = slippage + tick "
                     f"granularity + unmodelled structure stop). Treat that gap as the error "
                     f"bar on every variant below.")
        L.append("")
        L.append("  | Variant | P&L |")
        L.append("  |---|---:|")
        L.append(f"  | **(shipped, realized)** | **{_usd(r['realized_pnl'])}** |")
        for name, v in sorted(r["variants"].items(),
                              key=lambda kv: (-(kv[1] if kv[1] is not None else -1e9))):
            L.append(f"  | `{name}` | {_usd(v)} |")
        L.append("")
        if not r["_complete"]:
            L.append("  ⚠ Incomplete variant grid — excluded from the aggregate.")
            L.append("")

    L.append("---")
    L.append("")
    L.append("### Method / known biases (read before quoting any number)")
    L.append("")
    L.append("- **Realized** P&L is broker-fill truth from `fills-ledger.jsonl`. Every other "
             "number is a replay on real 1-min OPRA bars.")
    L.append("- **entry+1**: a position is not exit-eligible until the bar AFTER its entry "
             "bar, matching the live tick order (exits are managed before entries). "
             "See `markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md`.")
    L.append("- **Intrabar optimism**: `replay_position` evaluates each bar with its own "
             "high as `best_premium` and low as `worst_premium`. A TP that triggers "
             "intrabar is assumed filled at the target. This flatters the VARIANTS "
             "relative to realized fills, so true capture is likely HIGHER than the "
             "headline — the bias runs against us, not for us.")
    L.append("- **Structure stops are not modelled.** `replay_position` never supplies "
             "`last_closed_5m_close`, so chart-stop exits cannot fire in any variant; the "
             "variants use the -50% premium catastrophe cap instead. Trades whose live exit "
             "was `structure_stop` therefore diverge most from their replays.")
    L.append("- **Slippage**: variant fills are modelled at the rule's target price; real "
             "fills cross the spread. On 0DTE options this is material.")
    L.append("- **`capture_vs_best_policy` is the only non-hindsight number here.** The "
             "per-trade-best and oracle figures are upper bounds published for disclosure.")
    return "\n".join(L) + "\n"


# ---------- main ----------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Winner-side trade autopsy + capture rate.")
    ap.add_argument("--date", default=None, help="restrict to ONE ET date (default: all)")
    ap.add_argument("--symbol", default=None, help="restrict to ONE option symbol")
    ap.add_argument("--out", default=None, help="override output basename")
    args = ap.parse_args()

    started = et_now()
    scope = args.symbol or args.date or "all winners to date"
    try:
        import exit_shape_parity_study as esp
        import trade_autopsy as ta

        # Reuse the loss autopsy's ledger loader verbatim -- one definition of "position".
        if args.date:
            positions = ta.load_engine_positions(args.date)
        else:
            dates = sorted({d for d in _all_ledger_dates()})
            positions = []
            for d in dates:
                positions.extend(ta.load_engine_positions(d))
        winners = [p for p in positions if p["actual_exit_pnl"] > 0]
        if args.symbol:
            winners = [p for p in winners if p["symbol"] == args.symbol]

        arm_patches = load_arm_exit_patches()
        bar_cache: dict = {}
        rows, n_no_bars = [], 0
        for p in winners:
            bars = ta.fetch_bars_cached(esp, p["symbol"], p["date_et"], bar_cache)
            if not bars:
                n_no_bars += 1
                continue
            r = autopsy_winner(p, esp, bars, arm_patches)
            if r is None:
                n_no_bars += 1
                continue
            rows.append(r)
            _time_mod.sleep(0.05)

        agg = aggregate_capture(rows, tuple(EXIT_MENU.keys()), n_no_bars=n_no_bars)
        waves = wave_capture(assign_waves(rows), tuple(EXIT_MENU.keys()))

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        base = args.out or (args.date or "all")
        (OUT_DIR / f"{base}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""), encoding="utf-8")
        (OUT_DIR / f"{base}.md").write_text(
            render_md(rows, agg, scope, n_no_bars, waves), encoding="utf-8")

        last_payload = {
            "scope": scope,
            "generated_at": started.isoformat(),
            "n_winners_found": len(winners),
            "n_winners_scored": agg["n_winners_scored"],
            "n_no_bars": n_no_bars,
            # Consumers (firm_brief) MUST branch on this before quoting any capture ratio --
            # on a DEGRADED run every ratio below is deliberately None.
            "data_integrity": agg["data_integrity"],
            "sufficient_n": agg["sufficient_n"],
            "realized_total": agg["realized_total"],
            "best_policy": agg["best_policy"],
            "best_policy_total": agg["best_policy_total"],
            "capture_vs_best_policy": agg["capture_vs_best_policy"],
            "capture_vs_per_trade_best": agg["capture_vs_per_trade_best"],
            "capture_vs_oracle": agg["capture_vs_oracle"],
            "n_runner_underperformed_tp1": sum(
                1 for r in rows if "runner_underperformed_tp1" in r["tags"]),
            "n_shipped_beat_menu": sum(
                1 for r in rows if "shipped_exit_beat_menu" in r["tags"]),
            "runner_cohort": runner_cohort_stats(rows),
            "attribution": attribution_coverage(rows),
            # Wave rows carry no `rows` payload -- the per-position detail already lives in
            # the .jsonl; duplicating it here would let the two drift apart.
            "waves": waves,
            "winners_only_sample": True,  # consumers MUST NOT read this as a policy comparison
            "pain_ledger": None,  # WS9 fold fills this below; None on scoped fires / if killed
            "fill_latency": None,  # Next-Twelve #5 fold fills this below; same fold contract
            "catastrophe_cap_shadow": None,  # 2026-08-03 fold fills this below; same contract
            "md": f"analysis/winner-autopsies/{base}.md",
        }
        LAST_JSON.write_text(json.dumps(last_payload, indent=2), encoding="utf-8")

        # --- WS9 (2026-08-01): the MAE/MFE pain ledger rides this SAME nightly fire -------
        # (prereg: analysis/pain-ledger/PREREG-2026-08-01.md -- deliberately NO new scheduled
        # task). Runs LAST, after every winner-autopsy surface is already on disk, so a slow
        # pain walk (no-bars retry backoff ~300s/symbol worst case) hitting the task's 30-min
        # ExecutionTimeLimit can never cost the capture-rate product. Shares this run's
        # bar_cache so winners' bars are fetched once per fire. Fail-open. Population-product
        # only: a --date/--symbol scoped manual fire must not overwrite the ledger with a
        # slice. LAST_JSON is then re-written with the summary (idempotent second write).
        if not args.date and not args.symbol:
            try:
                import pain_ledger
                last_payload["pain_ledger"] = pain_ledger.build_ledger(bar_cache=bar_cache)
            except Exception as pe:  # noqa: BLE001 -- descriptive side-product, never fatal
                last_payload["pain_ledger"] = {"error": f"{type(pe).__name__}: {pe}"[:200]}
            # --- Next-Twelve #5 (2026-08-01): the fill-pipeline latency decomposition rides
            # this SAME nightly fire, SAME fold contract as pain_ledger immediately above (no
            # new scheduled task, fail-open, population-product only). Pure JSONL joins, zero
            # OPRA/network cost -- runs after pain_ledger so a failure there never blocks this.
            try:
                import fill_latency
                last_payload["fill_latency"] = fill_latency.build_ledger()
            except Exception as le:  # noqa: BLE001 -- descriptive side-product, never fatal
                last_payload["fill_latency"] = {"error": f"{type(le).__name__}: {le}"[:200]}
            # --- CATASTROPHE-CAP-WIDEN-WATCH accrual (2026-08-03) rides this SAME nightly
            # fire, SAME fold contract as pain_ledger/fill_latency above (no new scheduled
            # task, fail-open, population-product only, runs last). ACCRUAL ONLY -- shadow-
            # logs real catastrophe-cap fires + held-to-EOD counterfactual toward the n>=10
            # bar queue.md's CATASTROPHE-CAP-WIDEN-WATCH item requires before any decision.
            try:
                import catastrophe_cap_shadow_ledger as ccs
                last_payload["catastrophe_cap_shadow"] = ccs.run()
            except Exception as ce:  # noqa: BLE001 -- descriptive side-product, never fatal
                last_payload["catastrophe_cap_shadow"] = {"error": f"{type(ce).__name__}: {ce}"[:200]}
            LAST_JSON.write_text(json.dumps(last_payload, indent=2), encoding="utf-8")

        print(f"[winner-autopsy] {scope}: {len(winners)} winners found, {len(rows)} autopsied, "
              f"{n_no_bars} no-bars; capture_vs_best_policy="
              f"{agg['capture_vs_best_policy']} (n={agg['n_winners_scored']}) "
              f"-> {OUT_DIR / (base + '.md')}")
    except Exception as e:  # noqa: BLE001 -- notify-only: never propagate a failure
        print(f"[winner-autopsy] ERROR (fail-open): {type(e).__name__}: {e}", file=sys.stderr)
        try:
            LAST_JSON.write_text(json.dumps({
                "scope": scope, "error": f"{type(e).__name__}: {e}"[:300],
                "generated_at": started.isoformat()}, indent=2), encoding="utf-8")
        except OSError:
            pass
    return 0


def _all_ledger_dates() -> set:
    """Every ET date carrying at least one engine option fill. Fail-open -> set()."""
    import trade_autopsy as ta
    out = set()
    try:
        for line in ta.LEDGER.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if (r.get("attribution") == "engine" and r.get("is_option")
                    and not r.get("is_crypto") and r.get("date_et")):
                out.add(r["date_et"])
    except OSError:
        pass
    return out


if __name__ == "__main__":
    sys.exit(main())
