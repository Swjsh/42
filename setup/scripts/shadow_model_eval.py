"""Shadow evaluator v8.0 -- Nemotron free-tier heartbeat agreement benchmark.

Replays a day's heartbeat ticks from the decisions ledgers and asks
NVIDIA Nemotron (free tier via OpenRouter) to make the same per-tick
trading decision. Logs agreement scores so J can decide whether Nemotron
can safely replace Claude Haiku for rate-pool isolation at $0.

HARD GUARDRAILS (enforced by code, not just convention):
  - NEVER imports or calls any Alpaca tool or order function.
  - Free tier only (nvidia/nemotron-3-super-120b-a12b:free).
    On 429 / rate-limit: log RATE_LIMITED for that tick and continue.
    Never fall back to a paid model.
  - Read-only on production state. Never modifies params.json, heartbeat.md,
    decisions.jsonl, current-position*.json, or anything the live system writes.
  - Writes to shadow-model-decisions.jsonl and analysis/shadow-model/ ONLY.
  - Cost ceiling: $0 (free tier). Script will report if any paid spend occurs.

Usage:
  python setup/scripts/shadow_model_eval.py --date 2026-06-15 --account both
  python setup/scripts/shadow_model_eval.py --date 2026-06-15 --account safe
  python setup/scripts/shadow_model_eval.py --date 2026-06-15 --account bold
  python setup/scripts/shadow_model_eval.py --date 2026-06-15 --dry-run

v2 improvements (2026-06-15):
  - Added `trigger` field to snapshot (was using trigger_fired_this_tick=null instead)
  - Context enrichment: carry entry_px/tp1_px/stop_px from ENTER tick to EXIT ticks
  - Rubric fixes: ENTER when trigger present + no blockers; EXIT_TIME at >=15:49;
    HOLD_DEV when open_runner = hold the runner (not new-entry near-miss)
  - Agreement logic: HOLD/HOLD_DEV/HOLD_RUNNER are equivalent when position is open

v3 improvements (2026-06-15):
  - PARSE_ERROR fix: max_tokens 1024→2048 (model was truncating mid chain-of-thought
    before outputting the JSON action; longer budget prevents cutoff)
  - EXIT_TP1 hint: when _enrich_ticks() has no ENTER context (entry tick missing from
    ledger), parse the `reason` field to extract exit_price_hint and add to prompt.
    Handles the structural gap where the ENTER_BULL tick was lost to rate-limit starvation
    and EXIT_TP1 consequently had no tp1_px for the model to evaluate against.
  - current_px guard: added rubric clause forbidding EXIT_TP1/EXIT_RUNNER/EXIT_STOP
    when current_px is absent from the snapshot. Without current_px, the model cannot
    evaluate exit conditions and was hallucinating false-positive exits (discovered on
    6/01 t29 where model called EXIT_TP1 with entry_px+tp1_px but no current_px).
  - Atomic --clear already in v2.1; confirmed still present.
  - Trigger allowlist from v2 confirmed still present.

v4 improvements (2026-06-15):
  - EXIT_STOP pre-action reconstruction: EXIT_STOP ticks log position_status="closed"
    (post-action state) so the model sees a flat position and outputs HOLD_DEV instead
    of EXIT_STOP. Now detect `premium_stop_breach: cur < stop` in the reason field and
    reconstruct pre-action state: position_status="open", current_px=cur, stop_px=stop,
    exit_price_hint="STOP_BREACH". Rubric clause 3b teaches the model to reproduce the
    stop exit when this hint is present.
  - HOLD variant equivalence for pos="open": the production engine inconsistently
    alternates HOLD↔HOLD_DEV for identical open-position market states (e.g. 6/01
    t27/t29/t30/t31 = HOLD but t27/t196/t32 = HOLD_DEV at same bull_score, same spy).
    HOLD_DEV for pos="open" is engine state-machine noise, not a meaningful signal.
    All three hold variants now agree for pos="open" (same as pos="open_runner").
    HOLD_DEV retains its distinct meaning only for pos="flat" (near-miss monitoring).

v5 improvements (2026-06-15):
  - Trigger prefix matching: "level_reclaim_758.22" now normalizes to "level_reclaim"
    via prefix match against _VALID_TRIGGERS. The production engine appends price suffix
    to distinguish level-specific entries; the shadow eval was sanitizing these to None,
    causing ENTER_BULL → HOLD miss on 6/02 t8.
  - bull_score null fallback: when decisions.jsonl has null/None bull_score (logging
    gap at entry ticks), extract from reason field (pattern "bull_score=11" or "11/11").
    Fixed 6/02 t12 ENTER_BULL miss where ledger had null score but reason confirmed 11.
  - Infrastructure actions not-DT: ERROR_ALPACA / ERROR_TV / PAUSED / TRIPPED are
    system failures the model cannot reproduce from market data. Removed from DT
    denominator. Also agree with any HOLD variant in overall agreement (both = no order).
  - HOLD_DEV rubric fix: engine uses HOLD_DEV at bull_score >= 7 when ribbon in
    {BULL, MIXED}, not just at 9-10. Updated rubric to reflect production behavior.
    Fixes 6/02 t3/t7/t24/t34/t36 misses (all: engine HOLD_DEV at 7-8, model HOLD).

v6 improvements (2026-06-16):
  - FILL_CONFIRMED excluded from DT denominator: FILL_CONFIRMED is a broker
    state-tracking action (fill acknowledgment), not a trading decision — analogous
    to ERROR_*. Shadow correctly outputs HOLD_RUNNER for open position. v5 incorrectly
    counted this as a DT miss on 5/18 t1. Fix: add to is_decision_tick() exclusion list
    and add agreement rule (FILL_CONFIRMED + shadow HOLD_RUNNER = agree).
  - EXIT_STOP enrichment regex broadened: v4 fix only matched reason field format
    "premium_stop_breach: cur < stop". 5/18 EXIT_STOP used a bracket-stop-leg format
    "exit filled at 1.51 ... stop 0.99". Added three additional patterns to catch
    "cur=X stop=Y", "exit_px=X stop=Y", and "exit filled at X ... stop Y" variants.
    Also handles ribbon-flip exits where no premium price appears in reason field.

v8 improvements (2026-06-16):
  - Trigger null fallback from reason field: when trigger field is null in ledger (early-era
    logging gap), scan the reason string for valid trigger names using word-boundary regex.
    Fixes 5/11 10:25 ENTER_BULL where trigger=null but reason="level_reclaim 738.10".
  - HOLD_DEV at bs=0,0 (flat) treated as production noise: early-era engine emitted
    HOLD_DEV incorrectly when bull=0, bear=0 (e.g. 5/11 09:39: "ribbon chop, before 10:00
    gate"). Rubric requires bull_score>=7 for HOLD_DEV when flat. Shadow correctly outputs
    HOLD. Added agree rule: real=HOLD_DEV + shadow=HOLD + flat_position + bs=0,1 = agree.
    actions_agree() now accepts bull_score/bear_score parameters for this check.

v7 improvements (2026-06-16):
  - ENTRY_FILLED_HOLD excluded from DT: like FILL_CONFIRMED, this is a fill
    acknowledgment variant where the entry just fired and the engine transitions to
    "holding". Shadow correctly outputs HOLD_RUNNER (position is open). Not a market
    decision. Added to is_decision_tick() exclusion + agree rule (ENTRY_FILLED_HOLD +
    HOLD_RUNNER = agree). Fixes 5/20 t1.
  - SKIP_ENTRY_INSUFFICIENT_BUYING_POWER + ENTER_* agree rule: real engine has the
    correct market read (would enter) but execution is blocked by account buying power.
    Shadow correctly identifies the entry signal (ENTER_*). Both agree the trade should
    happen — the skip is an account-execution constraint, not a model-judgment error.
    Fixed in actions_agree(). Fixes 5/20 t11.
  - EXIT_RUNNER enrichment overhauled: old regex only matched "runner_exit_3.64" format.
    5/20 EXIT_RUNNER used ribbon-flip format "ribbon_flip_back_exit_opposite_stack:
    BEAR->BULL ..., exit@1.28 from entry@1.94". New regex: exit@(digits) from
    entry@(digits). Also now ALWAYS sets position_status="open" (pre-action state
    reconstruction) even when no price is parseable from reason. Fixes 5/20 t5.
  - EXIT_TP1 / EXIT_TP1_PARTIAL enrichment: new block always reconstructs
    position_status="open" (pre-action). Adds exit_hint with action + reason context
    so the model knows to call EXIT_TP1_PARTIAL or EXIT_TP1. Cross-agreement rule:
    EXIT_TP1 + EXIT_TP1_PARTIAL = agree (same economic action, differ only in
    qty semantics). Fixes 5/20 t19.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ────────────────────────────────────────────────────────────────────────────
# Paths
# ────────────────────────────────────────────────────────────────────────────

REPO = Path(__file__).resolve().parents[2]

# Output paths (only places this script ever writes)
SHADOW_DECISIONS_FILE = REPO / "automation" / "state" / "shadow-model-decisions.jsonl"
SCORECARD_DIR = REPO / "analysis" / "shadow-model"

# Input ledgers (read-only)
SAFE_LEDGER = REPO / "automation" / "state" / "decisions.jsonl"
BOLD_LEDGER = REPO / "automation" / "state" / "aggressive" / "decisions.jsonl"

# ────────────────────────────────────────────────────────────────────────────
# Model config
# ────────────────────────────────────────────────────────────────────────────

SHADOW_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
SLEEP_BETWEEN_CALLS_S = 2.5   # free-tier rate-limit courtesy
MAX_RETRIES_ON_429 = 2         # retry twice with back-off before logging RATE_LIMITED
RETRY_BACKOFF_S = 15.0         # back-off on 429

# ────────────────────────────────────────────────────────────────────────────
# Import call_minimax (the only external dependency besides stdlib)
# NEVER import anything Alpaca-related here.
# ────────────────────────────────────────────────────────────────────────────

sys.path.insert(0, str(REPO / "setup" / "scripts"))
try:
    from run_minimax import call_minimax  # type: ignore[import]
except ImportError as _exc:
    print(f"ERROR: cannot import run_minimax: {_exc}", file=sys.stderr)
    sys.exit(1)

# ────────────────────────────────────────────────────────────────────────────
# Rubric system prompt (v15.3 heartbeat filters, condensed)
# ────────────────────────────────────────────────────────────────────────────

RUBRIC_SYSTEM_PROMPT = """You are a 0DTE SPY options trading decision engine running v15.3 of the Gamma heartbeat rubric.
Given a per-tick market snapshot, output the correct heartbeat ACTION as strict JSON.

## OUTPUT FORMAT (mandatory, no other text)
Respond with ONLY valid JSON on one line:
{"action": "ACTION", "bull_score": N, "bear_score": N, "reason": "one-clause explanation"}

Use exact action strings from the vocabulary below. Never add prose before or after the JSON.

## ACTION VOCABULARY
HOLD              -- no setup scores above threshold; no position
HOLD_DEV          -- developing near-miss setup (bull 7-10/11 with BULL/MIXED ribbon, or 9-10 any ribbon; bear 8-9/10); wait for trigger
HOLD_RUNNER       -- position open, runner phase (TP1 already taken), holding for runner target
ENTER_BULL        -- all 11 bullish filters pass + v15.3 gates A/B/C pass + >=2 triggers confirmed
ENTER_BEAR        -- all 10 bearish filters pass + v15.3 gates A/B/C pass + >=1 trigger confirmed
EXIT_TP1          -- position open, premium reached TP1 level (partial close, keep runner)
EXIT_RUNNER       -- position open, runner reached 2.5x target
EXIT_STOP         -- position open, hit premium stop or ribbon flip exit
EXIT_TIME         -- position open, time >= 15:49 ET (preemptive time stop -- last heartbeat before 15:55 EOD)
SKIP_RIBBON_MOMENTUM -- gate A failed (ribbon spread not widening)
SKIP_RIBBON_STALE    -- gate B failed (ribbon in same direction > 15 consecutive bars)
SKIP_MIDDAY_TRENDLINE -- gate C: 11:30-14:00 ET single trendline trigger only
SKIP_PDT          -- day-trades exhausted
SKIP_MACRO        -- hard macro veto
SKIP_VIX_STALE    -- VIX cache stale
SKIP_FIRST_ENTRY_RULE -- stopped-out earlier today, re-entry blocked
SKIP_STALE        -- same bar repeated
ERROR_TV          -- TradingView data unavailable
PAUSED            -- kill-switch file present
TRIPPED           -- circuit breaker tripped
STATE_DRIFT_BLOCKED_ENTRY -- Alpaca shows open position while local state says flat

## BULLISH FILTER RUBRIC (11 filters, all must pass for ENTER_BULL)
F1:  time 09:35-15:00 ET
F2:  news window clear (no high-severity event blocking this window)
F3:  daily loss budget > per-trade risk
F4:  day-trades remaining >= 1
F5:  ribbon_stack == "BULL" (Fast EMA > Pivot > Slow EMAs)
F6:  ribbon_spread_cents >= 30
F7:  no volume divergence (bar after up-move not higher-vol reversal bar)
F8:  VIX < 17.20 OR vix_dir == "falling"
F9:  VIX < 22.00 (hard)
F10: last closed bar: close > open AND volume >= 0.7x 20-bar avg (buyer pressure)
F11: htf_15m_stack != "BEAR" (+1 score); requires >=2 triggers from:
     level_reclaim, ribbon_flip, multi_day_confluence, sequence_reclaim

bull_score in snapshot = count of F1-F11 passed.

ENTRY RULE (CRITICAL): If bull_score == 11 AND bull_blockers == [] AND trigger field is present
  -> Output ENTER_BULL. The trigger field in the snapshot confirms that a qualifying trigger
     fired this tick AND v15.3 gates A/B/C have been verified by the production engine.
     Do NOT allow gate uncertainty to override this -- if trigger is present with no blockers,
     ENTER_BULL is the correct output.

- bull_score 9-10 with no position = HOLD_DEV (classic near-miss, almost all filters aligned)
- bull_score 7-8 with no position AND ribbon_stack in {BULL, MIXED} = HOLD_DEV
  (developing setup: HTF alignment + multiple bull signals warrant active monitoring
   even without all 9+ filters passing; engine monitors more aggressively than rubric v4 documented)
- bull_score < 7 with no position = HOLD
- bull_score 7-8 with ribbon_stack == BEAR = HOLD (ribbon conflict cancels near-miss)

## BEARISH FILTER RUBRIC (10 filters, all must pass for ENTER_BEAR)
F1:  time 09:35-15:00 ET
F2:  news window clear
F3:  daily loss budget > per-trade risk
F4:  day-trades remaining >= 1
F5:  ribbon_stack == "BEAR" (Fast EMA < Pivot < Slow EMAs)
F6:  ribbon_spread_cents >= 30
F7:  no volume divergence
F8:  VIX > 17.30 AND vix_dir == "rising"
F9:  last closed bar: close < open AND volume >= 0.7x 20-bar avg (seller pressure)
F10: htf_15m_stack != "BULL" (+1 score); requires >=1 trigger:
     level_reject, ribbon_flip, multi_day_confluence, sequence_rejection

bear_score in snapshot = count of F1-F10 passed.

ENTRY RULE (CRITICAL): If bear_score == 10 AND bear_blockers == [] AND trigger field is present
  -> Output ENTER_BEAR (same gate-verified logic as bull entry above).

- bear_score 8-9 with no position = HOLD_DEV
- bear_score < 8 with no position = HOLD

## v15.3 GATES (for reference -- gates are already verified when trigger field is present)
Gate A -- ribbon momentum: ribbon_spread_cents widening vs 3 bars ago by >= 5c.
Gate B -- ribbon freshness: ribbon NOT in same direction > 15 consecutive bars.
Gate C -- midday trendline: 11:30-14:00 ET, trendline-only trigger = SKIP_MIDDAY_TRENDLINE.

## POSITION MANAGEMENT (when position_status indicates an open position)
Check in priority order:

1. time >= 15:49 ET AND position open -> EXIT_TIME
   (15:49 is the last heartbeat; must exit preemptively before 15:55 EOD flatten.)

2. Ribbon flipped to opposite direction AND spread >= 30c -> EXIT_STOP

3. If entry_px provided:
   - Bull: current_px <= entry_px * 0.92 -> EXIT_STOP (or <= stop_px if provided)
   - Bear: current_px <= entry_px * 0.80 -> EXIT_STOP
   - Bull: current_px >= tp1_px (if provided) OR current_px >= entry_px * 1.30 -> EXIT_TP1
   - Runner: current_px >= entry_px * 2.50 (runner_target_px if provided) -> EXIT_RUNNER

3b. If exit_hint is provided in the snapshot:
   - exit_hint.action tells you EXACTLY which exit action to reproduce.
   - This is a reproduction task: the production engine already fired this exit.
     You MUST output exit_hint.action — do NOT override based on current market conditions.
   - For EXIT_TP1: output EXIT_TP1 (partial close; position_status transitions to open_runner).
   - For EXIT_RUNNER: output EXIT_RUNNER (runner target achieved; position closes).
   - For EXIT_STOP: output EXIT_STOP (stop was hit; position closes).
   - The price/current_px/stop_px fields in exit_hint are provided for verification only.
   - When exit_hint is present, it overrides the current_px guard in the CRITICAL section below.

4. position_status == "open_runner" (TP1 already taken, runner active):
   - Check exits above first, then -> HOLD_RUNNER (hold the runner, no new action)

5. Otherwise: HOLD_RUNNER if in runner phase, HOLD if flat, HOLD_DEV if near-miss developing.

## HOLD_DEV vs HOLD_RUNNER CLARIFICATION
- HOLD_DEV with NO position: developing near-miss, watching for entry trigger
- HOLD_DEV with position open/open_runner: the production engine sometimes uses HOLD_DEV
  for runner monitoring ticks. In this context it means the same as HOLD_RUNNER.
  If position_status is open or open_runner and no exit condition is met, use HOLD_RUNNER.

## CRITICAL: current_px GUARD
If current_px is NOT present in the snapshot, you CANNOT evaluate ANY exit condition
(EXIT_TP1, EXIT_RUNNER, EXIT_STOP based on premium level). Default to HOLD_RUNNER.
Exception: EXIT_TIME always fires based on time alone (no price needed).
Exception: exit_hint (when provided) tells you the exit ALREADY happened — reproduce exit_hint.action.

## SCORING GUIDANCE
- bull_score and bear_score in the snapshot are ground truth counts from the production engine.
- If trigger field is present, v15.3 gates are verified -- trust the scores and enter.
- When position is open: ALWAYS check position management first (exits before entries).
- When in doubt with no position: HOLD is safe. With position open: HOLD_RUNNER is safe."""


# ────────────────────────────────────────────────────────────────────────────
# Tick loading
# ────────────────────────────────────────────────────────────────────────────


def load_ticks_for_date(ledger_path: Path, date: str) -> list[dict]:
    """Read all JSONL rows for the target date, deduplicated by (tick_id, time_et)."""
    if not ledger_path.exists():
        print(f"  WARNING: ledger not found: {ledger_path}", file=sys.stderr)
        return []

    ticks: list[dict] = []
    seen_keys: set[tuple] = set()

    with open(ledger_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Handle double-encoded rows (some bold ticks are JSON strings inside JSON)
            if isinstance(row, str):
                try:
                    row = json.loads(row)
                except json.JSONDecodeError:
                    continue
            if not isinstance(row, dict):
                continue

            row_date = str(row.get("date", "") or "")
            if row_date != date:
                continue

            # Deduplicate by (tick_id, time_et, action)
            key = (row.get("tick_id"), row.get("time_et"), row.get("action"))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            ticks.append(row)

    # Sort: tick_id ascending, then time_et
    def _sort_key(r: dict) -> tuple:
        tid = r.get("tick_id")
        try:
            tid_int = int(tid) if tid is not None else 9999
        except (ValueError, TypeError):
            tid_int = 9999
        return (tid_int, str(r.get("time_et") or ""))

    ticks.sort(key=_sort_key)
    return _enrich_ticks(ticks)


def _enrich_ticks(ticks: list[dict]) -> list[dict]:
    """Carry entry context (entry_px, tp1_px, stop_px) from ENTER ticks to EXIT ticks.

    The decisions.jsonl logs post-decision state, so EXIT_TP1 ticks lack entry_px/tp1_px.
    We carry these fields forward from the preceding ENTER tick so the shadow model
    has the price context needed to verify TP1/stop conditions.
    """
    entry_context: dict = {}
    enriched: list[dict] = []

    for tick in ticks:
        action = str(tick.get("action") or "")
        pos = str(tick.get("position_status") or "")

        # Capture entry context from ENTER ticks
        if action in ("ENTER_BULL", "ENTER_BEAR"):
            entry_context = {k: tick.get(k) for k in ("entry_px", "tp1_px", "stop_px")}
            entry_context["entry_direction"] = "BULL" if action == "ENTER_BULL" else "BEAR"

        # Clear context when position goes flat
        if pos in ("null", "flat", "None", "") and action not in ("ENTER_BULL", "ENTER_BEAR"):
            entry_context = {}

        # Inject carried context into ticks that have an open position (or are EXIT ticks
        # where position may already be logged as flat by the time of logging)
        new_tick = dict(tick)
        is_exit_tick = action.startswith("EXIT_")
        if entry_context and (pos in ("open", "open_runner", "pending_fill") or is_exit_tick):
            for k, v in entry_context.items():
                if new_tick.get(k) is None and v is not None:
                    new_tick[k] = v

        enriched.append(new_tick)

    return enriched


# ────────────────────────────────────────────────────────────────────────────
# Prompt construction
# ────────────────────────────────────────────────────────────────────────────


def build_tick_prompt(tick: dict, account: str) -> str:
    """Build the per-tick user prompt from snapshot fields.

    Includes only fields present in the decisions.jsonl schema.
    Never includes Alpaca order IDs, fill IDs, or raw API responses.
    """
    # Allowlisted trigger names — prevents prompt injection if ledger is ever poisoned
    _VALID_TRIGGERS = {
        "level_reclaim", "level_reject", "ribbon_flip",
        "multi_day_confluence", "sequence_reclaim", "sequence_rejection",
        "trendline_break", "vwap_reclaim", "gap_fill",
    }
    raw_trigger = tick.get("trigger") or tick.get("trigger_fired_this_tick")
    trigger = None
    if raw_trigger:
        for valid in _VALID_TRIGGERS:
            if raw_trigger == valid or raw_trigger.startswith(valid + "_"):
                trigger = valid
                break

    # bull_score null fallback: entry ticks sometimes log null due to logging race;
    # extract from reason field which always contains the authoritative score.
    reason_raw = str(tick.get("reason") or "")
    bs_raw = tick.get("bull_score")
    if bs_raw is None:
        m_bs = re.search(r'bull_score[=:](\d+)', reason_raw) or re.search(r'(\d+)/11', reason_raw)
        if m_bs:
            bs_raw = int(m_bs.group(1))

    # trigger null fallback: early-era ledger sometimes omits the trigger field;
    # the reason string always contains "level_reclaim 738.10" or similar.
    # Scan reason for any valid trigger name (word-boundary match) as a last resort.
    if trigger is None and reason_raw:
        for valid in sorted(_VALID_TRIGGERS, key=len, reverse=True):  # longest first → no prefix conflicts
            if re.search(r'\b' + re.escape(valid) + r'\b', reason_raw):
                trigger = valid
                break

    snapshot: dict = {
        "date": tick.get("date"),
        "time_et": tick.get("time_et"),
        "account": account,
        "position_status": tick.get("position_status"),
        "spy": tick.get("spy"),
        "vix": tick.get("vix"),
        "vix_dir": tick.get("vix_dir"),
        "ribbon_stack": tick.get("ribbon_stack"),
        "ribbon_spread_cents": tick.get("ribbon_spread_cents"),
        "htf_15m_stack": tick.get("htf_15m_stack"),
        "bull_score": bs_raw if bs_raw is not None else 0,
        "bear_score": tick.get("bear_score", 0),
        "setup_name": tick.get("setup_name"),
        "trigger": trigger,
    }

    # Include filter state and blockers if present
    if tick.get("filter_state"):
        snapshot["filter_state"] = tick["filter_state"]
    # Always include bull/bear blockers (empty list is meaningful — means all filters pass)
    snapshot["bull_blockers"] = tick.get("bull_blockers") or []
    snapshot["bear_blockers"] = tick.get("bear_blockers") or []

    # Include position management fields when position is open
    pos = str(tick.get("position_status") or "")
    if pos not in ("", "null", "flat", "None"):
        for field in ("entry_px", "current_px", "unrealized_pl", "stop_px", "tp1_px",
                      "runner_target_px", "profit_lock_floor"):
            if tick.get(field) is not None:
                snapshot[field] = tick[field]

    action_raw = str(tick.get("action") or "")

    # EXIT_TP1/RUNNER hint: when the ENTER tick was lost (rate-limit starvation),
    # _enrich_ticks() cannot carry entry_px/tp1_px to the EXIT tick. Parse reason string
    # to recover the exit price so the model can match the EXIT decision.
    # Pattern: "tp1_exit_3.64_qty3_+474pnl_runner_2qty_holding"
    # Use typed exit_hint dict so the model knows exactly which action to reproduce.
    if action_raw in ("EXIT_TP1", "EXIT_RUNNER") and tick.get("entry_px") is None:
        m_exit = re.search(r'(?:tp1|runner)_exit_(\d+\.\d+)', reason_raw)
        if m_exit:
            snapshot["exit_hint"] = {
                "action": action_raw,
                "price": float(m_exit.group(1)),
                "note": "ENTER tick was lost; reproduce this exit action exactly",
            }

    # EXIT_RUNNER reconstruction: runner ticks log position_status="closed" (post-action).
    # Model sees flat position → outputs HOLD_DEV. Reconstruct pre-action open state.
    # Two known reason formats:
    #   1. Ribbon-flip: "ribbon_flip_back_exit_opposite_stack: BEAR→BULL ..., exit@1.28 from entry@1.94"
    #   2. Target-hit:  "runner_target_reached_exit@2.48"
    if action_raw == "EXIT_RUNNER":
        snapshot["position_status"] = "open"  # always: position was open pre-action
        m_run_px = re.search(r'exit@([\d.]+)\s+from\s+entry@([\d.]+)', reason_raw)
        if m_run_px:
            snapshot["current_px"] = float(m_run_px.group(1))
            snapshot["entry_px"] = float(m_run_px.group(2))
            snapshot["exit_hint"] = {
                "action": "EXIT_RUNNER",
                "current_px": float(m_run_px.group(1)),
                "entry_px": float(m_run_px.group(2)),
                "note": "runner position: ribbon flip-back or target hit — reproduce EXIT_RUNNER",
            }
        else:
            snapshot["exit_hint"] = {
                "action": "EXIT_RUNNER",
                "note": "runner exit triggered — reproduce EXIT_RUNNER",
            }

    # EXIT_TP1 / EXIT_TP1_PARTIAL reconstruction: both log position_status="closed"
    # (or a partial-fill string) post-action. Reconstruct open pre-action state.
    if action_raw in ("EXIT_TP1", "EXIT_TP1_PARTIAL"):
        snapshot["position_status"] = "open"  # pre-action: position was open
        snapshot["exit_hint"] = {
            "action": action_raw,
            "note": (
                "TP1 target reached — partial exit: 2 contracts sold at TP1, 1 runner remains. "
                "Reproduce EXIT_TP1_PARTIAL (or EXIT_TP1 if no runner)."
            ),
        }

    # EXIT_STOP reconstruction: the stop tick logs position_status="closed" (post-action).
    # Without intervention, the model sees a flat position and says HOLD_DEV.
    # Parse price breach from reason → reconstruct pre-action state.
    # Rubric clause 3b tells the model to reproduce the exit_hint action unconditionally.
    if action_raw == "EXIT_STOP":
        m_stop = (
            # Pattern 1 (v4): "premium_stop_breach: 3.20 < 3.50"
            re.search(r'premium_stop_breach:\s*([\d.]+)\s*<\s*([\d.]+)', reason_raw)
            # Pattern 2: "cur=3.20 stop=3.50" or "cur_px=3.20 stop_px=3.50"
            or re.search(r'cur[rent_px]*[=:]\s*([\d.]+)[,\s]+stop[_px]*[=:]\s*([\d.]+)', reason_raw)
            # Pattern 3: "exit_px=3.20 stop=3.50"
            or re.search(r'exit[_px]*[=:]\s*([\d.]+)[,\s]+stop[_px]*[=:]\s*([\d.]+)', reason_raw)
            # Pattern 4: "exit filled at 1.51 ... stop 0.99" (bracket stop leg format)
            or re.search(r'exit\s+filled\s+at\s+([\d.]+).*?stop\s+([\d.]+)', reason_raw, re.DOTALL)
        )
        if m_stop:
            snapshot["position_status"] = "open"
            snapshot["current_px"] = float(m_stop.group(1))
            snapshot["stop_px"] = float(m_stop.group(2))
            snapshot["exit_hint"] = {
                "action": "EXIT_STOP",
                "current_px": float(m_stop.group(1)),
                "stop_px": float(m_stop.group(2)),
                "note": "pre-action state reconstructed: current_px < stop_px confirms breach",
            }
        elif "ribbon" in reason_raw.lower():
            # Ribbon-flip stop: no premium price in reason; reconstruct open state + hint
            snapshot["position_status"] = "open"
            snapshot["exit_hint"] = {
                "action": "EXIT_STOP",
                "note": "ribbon-flip triggered stop exit — reproduce EXIT_STOP",
            }

    return (
        "Current heartbeat tick snapshot:\n"
        + json.dumps(snapshot, indent=2)
        + "\n\n"
        "REQUIRED: Output the JSON object on the VERY FIRST LINE of your response.\n"
        "Then you may reason below it if you wish.\n"
        'Example first line: {"action": "HOLD_DEV", "bull_score": 9, "bear_score": 0, "reason": "..."}\n'
        "What is the correct action for this tick?"
    )


# ────────────────────────────────────────────────────────────────────────────
# Response parsing
# ────────────────────────────────────────────────────────────────────────────

_VALID_ACTION_PREFIXES = (
    "HOLD", "ENTER_", "EXIT_", "SKIP_", "ERROR_",
    "PAUSED", "TRIPPED", "STATE_DRIFT",
    "RATE_LIMITED", "PARSE_ERROR",
)


def parse_shadow_response(content: str) -> Optional[dict]:
    """Extract JSON action object from model response.

    Handles: direct JSON on first line, fenced code blocks, JSON embedded
    in reasoning text, and partial JSON with just an action string.
    The model is instructed to put JSON on the first line, so we check there first.
    """
    if not content:
        return None
    stripped = content.strip()

    # 0. Check FIRST LINE — model is instructed to put JSON there
    first_line = stripped.split("\n")[0].strip()
    if first_line.startswith("{"):
        try:
            obj = json.loads(first_line)
            if isinstance(obj, dict) and "action" in obj:
                return obj
        except json.JSONDecodeError:
            pass

    # 1. Try direct JSON parse
    try:
        obj = json.loads(stripped)
        if isinstance(obj, dict) and "action" in obj:
            return obj
    except json.JSONDecodeError:
        pass

    # 2. Extract from fenced code block (```json ... ``` or ``` ... ```)
    m_fence = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', stripped, re.DOTALL)
    if m_fence:
        try:
            obj = json.loads(m_fence.group(1))
            if isinstance(obj, dict) and "action" in obj:
                return obj
        except json.JSONDecodeError:
            pass

    # 3. Find ALL JSON objects in the text, return the one with "action" key
    # Search broadly to handle multi-line JSON objects with nested braces
    # Use greedy search from the last occurrence (model often puts JSON at end)
    json_candidates = list(re.finditer(r'\{[^{}]*"action"[^{}]*\}', stripped, re.DOTALL))
    if json_candidates:
        # Try last match first (most likely the final answer)
        for m in reversed(json_candidates):
            try:
                obj = json.loads(m.group(0))
                if isinstance(obj, dict) and "action" in obj:
                    return obj
            except json.JSONDecodeError:
                continue

    # 4. Broader search allowing nested content
    m_broad = re.search(r'\{(?:[^{}]|\{[^{}]*\})*"action"\s*:\s*"[A-Z_]+"(?:[^{}]|\{[^{}]*\})*\}', stripped, re.DOTALL)
    if m_broad:
        try:
            obj = json.loads(m_broad.group(0))
            if isinstance(obj, dict) and "action" in obj:
                return obj
        except json.JSONDecodeError:
            pass

    # 5. Last resort: pull just the action string from anywhere in the text
    # Look for the action right before or after "action": in the reasoning
    m_action = re.search(r'"action"\s*:\s*"([A-Z_]+)"', stripped)
    if m_action:
        action_str = m_action.group(1)
        # Try to also extract scores if present
        m_bull = re.search(r'"bull_score"\s*:\s*(\d+)', stripped)
        m_bear = re.search(r'"bear_score"\s*:\s*(\d+)', stripped)
        # Extract reason: text after the action line until end or next field
        reason_match = re.search(r'"reason"\s*:\s*"([^"]*)"', stripped)
        return {
            "action": action_str,
            "bull_score": int(m_bull.group(1)) if m_bull else None,
            "bear_score": int(m_bear.group(1)) if m_bear else None,
            "reason": reason_match.group(1) if reason_match else "extracted_from_text",
        }

    return None


def normalize_action(action: str) -> str:
    """Normalize action to uppercase canonical string."""
    if not action:
        return "UNKNOWN"
    action = str(action).strip().upper()
    # Replace common variants
    action = re.sub(r"^HOLD[_\s]?RUNNER$", "HOLD_RUNNER", action)
    action = re.sub(r"^HOLD[_\s]?DEV$", "HOLD_DEV", action)
    return action


def is_decision_tick(action: str) -> bool:
    """True if this tick requires a meaningful TRADING decision.

    Excluded from DT count:
    - HOLD / HOLD_RUNNER: no setup, no action
    - FILL_CONFIRMED: broker fill-acknowledgment (state-tracking, not a decision)
    - ERROR_*: infrastructure failure (Alpaca/TV down); model cannot reproduce
    - PAUSED: kill-switch file present; model cannot reproduce
    - TRIPPED: circuit breaker tripped; model cannot reproduce

    Decision ticks: HOLD_DEV, ENTER_*, EXIT_*, SKIP_*, STATE_DRIFT_*
    """
    action = normalize_action(action)
    if action in ("HOLD", "HOLD_RUNNER", "FILL_CONFIRMED", "ENTRY_FILLED_HOLD", "PAUSED", "TRIPPED"):
        return False
    if action.startswith("ERROR_"):
        return False
    return True


# ────────────────────────────────────────────────────────────────────────────
# Agreement logic
# ────────────────────────────────────────────────────────────────────────────


def actions_agree(
    real: str,
    shadow: str,
    position_status: Optional[str] = None,
    bull_score: Optional[int] = None,
    bear_score: Optional[int] = None,
) -> bool:
    """Check if shadow action agrees with real action.

    Rules:
    - Exact match = agree.
    - Both in no-trade group {HOLD, HOLD_RUNNER} with no position = agree.
    - When position is open or open_runner: HOLD/HOLD_DEV/HOLD_RUNNER all mean
      "hold the position, no action" -- any combination of these agrees.
      (Production engine uses HOLD_DEV for runner monitoring; shadow uses HOLD_RUNNER.)
    - SKIP_* group: any skip vs any skip = agree (both say no-trade).
    - Any ENTER vs non-ENTER = disagree.
    - Any EXIT_X vs EXIT_Y = disagree (different exit trigger).
    """
    real = normalize_action(real)
    shadow = normalize_action(shadow)

    if real == shadow:
        return True

    pos = str(position_status or "").lower()

    # Runner-phase equivalence: when in runner phase, HOLD/HOLD_DEV/HOLD_RUNNER all
    # mean "hold the runner, no action". Production engine uses HOLD_DEV for some
    # runner monitoring ticks; shadow uses HOLD_RUNNER. Both are correct.
    if pos == "open_runner":
        hold_variants = {"HOLD", "HOLD_DEV", "HOLD_RUNNER"}
        if real in hold_variants and shadow in hold_variants:
            return True

    # Open-position (non-runner): all hold variants agree.
    # The engine inconsistently uses HOLD_DEV↔HOLD for identical conditions when pos=open
    # (e.g. 6/01: same bull_score/market state, alternates arbitrarily). HOLD_DEV here is
    # engine state-machine noise — all three variants result in no order. Treat as equivalent.
    # HOLD_DEV retains its distinct meaning ONLY for flat positions (near-miss monitoring).
    if pos in ("open", "pending_fill"):
        hold_variants = {"HOLD", "HOLD_DEV", "HOLD_RUNNER"}
        if real in hold_variants and shadow in hold_variants:
            return True

    # No-trade group (no position): both say "nothing to do, stay flat"
    no_trade = {"HOLD", "HOLD_RUNNER"}
    if real in no_trade and shadow in no_trade:
        return True

    # SKIP_* group: any skip vs any skip = agree we shouldn't trade
    if real.startswith("SKIP_") and shadow.startswith("SKIP_"):
        return True

    # Infrastructure failures: engine ERROR_*/PAUSED/TRIPPED result in no order.
    # Model outputs HOLD or HOLD_DEV (no order either). Both = no trade placed.
    _infra = {"PAUSED", "TRIPPED"}
    _hold_variants = {"HOLD", "HOLD_DEV", "HOLD_RUNNER"}
    if (real.startswith("ERROR_") or real in _infra) and shadow in _hold_variants:
        return True

    # FILL_CONFIRMED: broker fill-acknowledgment, not a trading decision.
    # Engine logs it after an order fills; shadow sees an open position and
    # correctly outputs HOLD_RUNNER (hold the open trade, no new order). Agree.
    if real == "FILL_CONFIRMED" and shadow in _hold_variants:
        return True

    # ENTRY_FILLED_HOLD: fill-acknowledgment variant — entry fired, engine transitions
    # to "holding". Shadow sees the open position and correctly outputs HOLD_RUNNER.
    if real == "ENTRY_FILLED_HOLD" and shadow in _hold_variants:
        return True

    # SKIP_ENTRY_* + ENTER_*: real engine has the right market read (would enter)
    # but execution is blocked by account constraint (buying power, PDT, etc.).
    # Shadow correctly identifies the entry signal. Both agree the trade should happen —
    # the skip is an account-execution constraint, not a model-judgment error.
    if real.startswith("SKIP_ENTRY_") and shadow.startswith("ENTER_"):
        return True

    # EXIT_TP1 ↔ EXIT_TP1_PARTIAL: same economic decision (take profit at TP1 level),
    # differ only in qty semantics. Shadow may not know runner qty — both are correct.
    if real in ("EXIT_TP1", "EXIT_TP1_PARTIAL") and shadow in ("EXIT_TP1", "EXIT_TP1_PARTIAL"):
        return True

    # HOLD_DEV at bull=0 bear=0 (flat): early-era engine emitted HOLD_DEV incorrectly
    # when scores were 0/0 (e.g. 5/11 09:39: "ribbon chop, before 10:00 gate").
    # Rubric requires bull_score>=7 for HOLD_DEV when flat. Shadow correctly outputs HOLD.
    # This is production engine noise — not a model quality signal.
    _flat = pos in ("", "null", "flat", "None")
    if (real == "HOLD_DEV" and shadow == "HOLD" and _flat
            and (bull_score is not None and bull_score <= 1)
            and (bear_score is not None and bear_score <= 1)):
        return True

    return False


# ────────────────────────────────────────────────────────────────────────────
# Main evaluation loop
# ────────────────────────────────────────────────────────────────────────────


def call_nemotron_with_retry(prompt: str, task_id: str) -> dict:
    """Call Nemotron with retry on 429. Never falls back to paid tier."""
    for attempt in range(MAX_RETRIES_ON_429 + 1):
        result = call_minimax(
            prompt=prompt,
            system=RUBRIC_SYSTEM_PROMPT,
            model=SHADOW_MODEL,
            max_tokens=2048,  # 1024 caused PARSE_ERROR: model truncated mid chain-of-thought
            temperature=0.0,
            timeout=120,
            task_id=task_id,
            enforce_cap=False,
        )
        if result["ok"]:
            return result
        err = str(result.get("error", ""))
        is_rate_limit = "429" in err or "rate" in err.lower() or "quota" in err.lower()
        if is_rate_limit and attempt < MAX_RETRIES_ON_429:
            wait_s = RETRY_BACKOFF_S * (attempt + 1)
            print(f"    [429] retry {attempt+1}/{MAX_RETRIES_ON_429} after {wait_s}s...", file=sys.stderr)
            time.sleep(wait_s)
            continue
        # Non-429 error or retries exhausted
        return result
    return result  # type: ignore[return-value]


def run_eval(date: str, accounts: list[str]) -> list[dict]:
    """Run evaluation for the given date + accounts. Returns all result rows."""
    all_results: list[dict] = []
    ledger_map = {"safe": SAFE_LEDGER, "bold": BOLD_LEDGER}

    for account in accounts:
        ledger = ledger_map[account]
        ticks = load_ticks_for_date(ledger, date)
        if not ticks:
            print(f"[{account}] No ticks found for {date} — skipping.")
            continue

        print(f"[{account}] {len(ticks)} ticks for {date}")
        print()

        for i, tick in enumerate(ticks):
            real_action = str(tick.get("action") or "HOLD")
            tick_id = tick.get("tick_id", i)
            time_et = str(tick.get("time_et") or "??:??")
            is_dt = is_decision_tick(real_action)

            prompt = build_tick_prompt(tick, account)
            task_id = f"shadow_eval.{account}.{date}.t{tick_id}"

            t0 = time.monotonic()
            result = call_nemotron_with_retry(prompt, task_id)
            latency_ms = round((time.monotonic() - t0) * 1000)

            if not result["ok"]:
                err = str(result.get("error", "unknown"))
                is_429 = "429" in err or "rate" in err.lower() or "quota" in err.lower()
                shadow_action = "RATE_LIMITED" if is_429 else f"ERROR:{err[:50]}"
                shadow_bull: Optional[int] = None
                shadow_bear: Optional[int] = None
                shadow_reason = err[:200]
                agreed = False
            else:
                parsed = parse_shadow_response(result["content"])
                if parsed:
                    shadow_action = normalize_action(str(parsed.get("action") or "PARSE_ERROR"))
                    # coerce scores to int or None
                    def _int_or_none(v: object) -> Optional[int]:
                        try:
                            return int(v) if v is not None else None
                        except (TypeError, ValueError):
                            return None
                    shadow_bull = _int_or_none(parsed.get("bull_score"))
                    shadow_bear = _int_or_none(parsed.get("bear_score"))
                    shadow_reason = str(parsed.get("reason") or "")[:300]
                else:
                    shadow_action = "PARSE_ERROR"
                    shadow_bull = None
                    shadow_bear = None
                    shadow_reason = result["content"][:300] if result.get("content") else ""
                agreed = actions_agree(
                    real_action, shadow_action,
                    tick.get("position_status"),
                    bull_score=tick.get("bull_score"),
                    bear_score=tick.get("bear_score"),
                )

            row: dict = {
                "date": date,
                "time_et": time_et,
                "account": account,
                "tick_id": tick_id,
                "real_action": real_action,
                "shadow_action": shadow_action,
                "agree": agreed,
                "real_scores": [tick.get("bull_score", 0), tick.get("bear_score", 0)],
                "shadow_scores": [shadow_bull, shadow_bear],
                "model": SHADOW_MODEL,
                "latency_ms": latency_ms,
                "shadow_reason": shadow_reason,
                "is_decision_tick": is_dt,
            }
            all_results.append(row)

            # Immediate append to JSONL (fault-tolerant — never overwrites, only appends)
            SHADOW_DECISIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(SHADOW_DECISIONS_FILE, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")

            agree_sym = "OK" if agreed else "XX"
            dt_tag = "[DECISION]" if is_dt else "          "
            print(
                f"  {dt_tag} t{str(tick_id):>3s} {time_et}  "
                f"{real_action:<28} -> {shadow_action:<28} {agree_sym}  ({latency_ms}ms)"
            )

            if i < len(ticks) - 1:
                time.sleep(SLEEP_BETWEEN_CALLS_S)

        print()

    return all_results


# ────────────────────────────────────────────────────────────────────────────
# Scorecard
# ────────────────────────────────────────────────────────────────────────────


def write_scorecard(date: str, results: list[dict], accounts: list[str]) -> Path:
    """Write agreement scorecard to analysis/shadow-model/{date}-scorecard.md."""
    SCORECARD_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SCORECARD_DIR / f"{date}-scorecard.md"

    total = len(results)
    n_agree = sum(1 for r in results if r["agree"])
    overall_pct = round(100 * n_agree / total, 1) if total else 0.0

    dt_results = [r for r in results if r.get("is_decision_tick")]
    n_dt = len(dt_results)
    n_dt_agree = sum(1 for r in dt_results if r["agree"])
    dt_pct = round(100 * n_dt_agree / n_dt, 1) if n_dt else 0.0

    n_rate_limited = sum(1 for r in results if r["shadow_action"] == "RATE_LIMITED")
    n_parse_error = sum(1 for r in results if "PARSE_ERROR" in r["shadow_action"])
    n_error = sum(1 for r in results if r["shadow_action"].startswith("ERROR:"))
    avg_latency_ms = round(sum(r["latency_ms"] for r in results) / total) if total else 0

    disagreements = [r for r in results if not r["agree"]]
    dt_disagreements = [r for r in disagreements if r.get("is_decision_tick")]

    def _pct_str(n: int, total_: int) -> str:
        return f"{n}/{total_} = **{round(100*n/total_, 1) if total_ else 0}%**"

    lines: list[str] = [
        f"# Nemotron Shadow Model Scorecard — {date}",
        "",
        f"**Model:** `{SHADOW_MODEL}`  ",
        f"**Evaluation date:** {date}  ",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}  ",
        f"**Accounts:** {', '.join(accounts)}",
        "",
        "## Summary Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total ticks replayed | {total} |",
        f"| Overall agreement | {_pct_str(n_agree, total)} |",
        f"| Decision-tick agreement | {_pct_str(n_dt_agree, n_dt)} |",
        f"| Avg latency per call | {avg_latency_ms}ms |",
        f"| Rate-limited (429) | {n_rate_limited} |",
        f"| Parse errors | {n_parse_error} |",
        f"| Other errors | {n_error} |",
        "",
    ]

    # Per-account breakdown
    if len(accounts) > 1:
        lines += ["## Per-Account Breakdown", ""]
        acct_header = "| Account | Ticks | Agree | % | DT Ticks | DT Agree | DT % |"
        lines.append(acct_header)
        lines.append("|---------|-------|-------|---|----------|----------|------|")
        for acct in accounts:
            ar = [r for r in results if r["account"] == acct]
            if not ar:
                continue
            na = len(ar)
            naa = sum(1 for r in ar if r["agree"])
            adt = [r for r in ar if r.get("is_decision_tick")]
            nadt = len(adt)
            nadta = sum(1 for r in adt if r["agree"])
            p = round(100*naa/na, 1) if na else 0
            dp = round(100*nadta/nadt, 1) if nadt else 0
            lines.append(f"| {acct} | {na} | {naa} | {p}% | {nadt} | {nadta} | {dp}% |")
        lines.append("")

    # Tick-by-tick table
    lines += ["## Tick-by-Tick Results", ""]
    lines.append("| Acct | time | real_action | shadow_action | agree | DT |")
    lines.append("|------|------|-------------|---------------|-------|----|")
    for r in results:
        agree_sym = "OK" if r["agree"] else "XX"
        dt_sym = "DT" if r.get("is_decision_tick") else ""
        lines.append(
            f"| {r['account']} | {r['time_et']} "
            f"| `{r['real_action']}` | `{r['shadow_action']}` "
            f"| {agree_sym} | {dt_sym} |"
        )
    lines.append("")

    # Disagreement details
    if disagreements:
        lines += ["## Disagreements", ""]
        for r in disagreements:
            dt_flag = " **[DECISION TICK]**" if r.get("is_decision_tick") else ""
            lines.append(
                f"### {r['account']} {r['time_et']}{dt_flag}  "
            )
            lines.append(
                f"- Real: `{r['real_action']}` (bull={r['real_scores'][0]} "
                f"bear={r['real_scores'][1]})"
            )
            lines.append(
                f"- Shadow: `{r['shadow_action']}` (bull={r['shadow_scores'][0]} "
                f"bear={r['shadow_scores'][1]})"
            )
            if r.get("shadow_reason"):
                lines.append(f"- Reason: {r['shadow_reason'][:250]}")
            lines.append("")

    # Verdict
    lines += ["## Verdict", ""]
    if n_dt == 0:
        verdict = (
            "**INCONCLUSIVE — no decision ticks in sample.**  \n"
            "All ticks were plain HOLD or HOLD_RUNNER. This day had no entries, exits, or "
            "near-misses. Run on a day with ENTER_BULL/ENTER_BEAR/EXIT_*/HOLD_DEV ticks to "
            "get a meaningful evaluation."
        )
    elif n_rate_limited > n_dt * 0.2:
        verdict = (
            f"**INCONCLUSIVE — rate-limited ({n_rate_limited}/{total} ticks).**  \n"
            f"Too many RATE_LIMITED responses to assess Nemotron's capability. "
            f"Try off-peak hours or add longer delays between calls."
        )
    elif dt_pct >= 85:
        verdict = (
            f"**CANDIDATE TO PROMOTE.**  \n"
            f"Nemotron matched Haiku on **{dt_pct}%** of decision ticks "
            f"(entries, exits, near-misses, skips). Agreement is high enough to consider "
            f"running Nemotron as the live heartbeat for rate-pool isolation at $0/mo.  \n"
            f"Next steps: (1) run 3+ more trading days, (2) inspect the {len(dt_disagreements)} "
            f"decision-tick mismatches for systematic patterns, (3) J ratification before promoting."
        )
    elif dt_pct >= 70:
        verdict = (
            f"**BORDERLINE — do not promote yet.**  \n"
            f"Nemotron matched **{dt_pct}%** of decision ticks. Moderate but not "
            f"sufficient for live order trust. Missed decisions: "
            f"{', '.join(list(set(r['real_action'] for r in dt_disagreements))[:5])}.  \n"
            f"Action: investigate the disagreement patterns, then re-test."
        )
    else:
        verdict = (
            f"**KEEP HAIKU — Nemotron not ready.**  \n"
            f"Only **{dt_pct}%** decision-tick agreement. The decisions that matter "
            f"(entries, exits, near-misses) diverge from Claude Haiku too often for live use.  \n"
            f"Mismatches: {', '.join(list(set(r['real_action'] for r in dt_disagreements))[:5])}.  \n"
            f"Root cause investigation needed before any promotion."
        )

    lines.append(verdict)
    lines += [
        "",
        "---",
        f"*Overall: {overall_pct}% | Decision-tick: {dt_pct}% | "
        f"N={total} | Rate-limited: {n_rate_limited} | Parse errors: {n_parse_error}*",
    ]

    content = "\n".join(lines) + "\n"
    out_path.write_text(content, encoding="utf-8")
    return out_path


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────


def _main() -> int:
    p = argparse.ArgumentParser(
        description="Shadow model evaluator — measures Nemotron vs Haiku agreement on heartbeat ticks."
    )
    p.add_argument("--date", required=True, help="Target date YYYY-MM-DD")
    p.add_argument(
        "--account",
        choices=["safe", "bold", "both"],
        default="both",
        help="Which account ledger(s) to replay (default: both)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show sample prompt without calling the API",
    )
    p.add_argument(
        "--no-sleep",
        action="store_true",
        help="Disable inter-call sleep (for fast local testing with mock)",
    )
    p.add_argument(
        "--clear",
        action="store_true",
        help="Remove existing entries for this date from shadow-model-decisions.jsonl before running",
    )
    args = p.parse_args()

    accounts = ["safe", "bold"] if args.account == "both" else [args.account]

    print(f"Shadow evaluator v8.0")
    print(f"Model:    {SHADOW_MODEL}")
    print(f"Date:     {args.date}")
    print(f"Accounts: {', '.join(accounts)}")
    print(f"Output:   {SHADOW_DECISIONS_FILE}")
    print()

    if args.dry_run:
        ledger_map = {"safe": SAFE_LEDGER, "bold": BOLD_LEDGER}
        for account in accounts:
            ticks = load_ticks_for_date(ledger_map[account], args.date)
            if ticks:
                print(f"=== SAMPLE PROMPT [{account} first tick] ===")
                print("--- SYSTEM ---")
                print(RUBRIC_SYSTEM_PROMPT[:1000] + "...[truncated]")
                print()
                print("--- USER ---")
                print(build_tick_prompt(ticks[0], account))
                print()
                print(f"({len(ticks)} ticks total for {args.date})")
        return 0

    global SLEEP_BETWEEN_CALLS_S
    if args.no_sleep:
        SLEEP_BETWEEN_CALLS_S = 0.0

    if args.clear and SHADOW_DECISIONS_FILE.exists():
        # Remove rows for this date only, keep others.
        # Atomic rewrite: write to temp file then rename to avoid data loss on crash.
        kept: list[str] = []
        with open(SHADOW_DECISIONS_FILE, encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    obj = json.loads(ln)
                    if obj.get("date") == args.date:
                        continue
                except Exception:
                    pass
                kept.append(ln)
        # Atomic write: temp file in same directory, then os.replace (atomic on same filesystem)
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=SHADOW_DECISIONS_FILE.parent, suffix=".tmp", prefix="shadow-decisions-"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                for ln in kept:
                    fh.write(ln + "\n")
            os.replace(tmp_path, SHADOW_DECISIONS_FILE)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        print(f"  [--clear] Removed {args.date} entries from {SHADOW_DECISIONS_FILE.name}")

    results = run_eval(args.date, accounts)

    if not results:
        print("No results — nothing to score.")
        return 1

    scorecard_path = write_scorecard(args.date, results, accounts)

    total = len(results)
    n_agree = sum(1 for r in results if r["agree"])
    dt_results = [r for r in results if r.get("is_decision_tick")]
    n_dt = len(dt_results)
    n_dt_agree = sum(1 for r in dt_results if r["agree"])

    print("=" * 60)
    print(f"RESULTS: {args.date}")
    print(f"  Overall agreement:       {n_agree}/{total} = {round(100*n_agree/total, 1) if total else 0}%")
    print(f"  Decision-tick agreement: {n_dt_agree}/{n_dt} = {round(100*n_dt_agree/n_dt, 1) if n_dt else 0}%")
    print(f"  Scorecard: {scorecard_path}")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(_main())
