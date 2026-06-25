"""Shadow evaluator v12.0 -- Multi-model free-tier heartbeat agreement benchmark.

Replays a day's heartbeat ticks from the decisions ledgers and asks a
free-tier OpenRouter model to make the same per-tick trading decision.
Supports Nemotron, Qwen, and DeepSeek-R1 via --model flag.
Logs agreement scores so J can decide which free model can safely replace
Claude Haiku for rate-pool isolation at $0.

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
  python setup/scripts/shadow_model_eval.py --date 2026-06-15 --account safe --model qwen
  python setup/scripts/shadow_model_eval.py --date 2026-06-15 --account bold --model deepseek-r1
  python setup/scripts/shadow_model_eval.py --date 2026-06-15 --dry-run

v12 improvements (2026-06-24):
  - Multi-model support: --model {nemotron,qwen,deepseek-r1} flag selects the model.
    Default is nemotron (backward compatible). Each model has its own:
    * Rubric file in setup/rubrics/{model}.md (iron-gate prompt, externalized)
    * Decisions output: automation/state/shadow-{model}-decisions.jsonl
    * Scorecard dir: analysis/shadow-model/{model}/YYYY-MM-DD-scorecard.md
  - External rubric files: RUBRIC_SYSTEM_PROMPT moved out of Python into
    setup/rubrics/nemotron.md. Loaded at runtime via load_rubric(). Edit the
    rubric without touching Python — the iron gate lives in the markdown file.
  - DeepSeek-R1 think-tag stripping: R1 outputs <think>...</think> before JSON.
    parse_shadow_response() now strips think blocks and looks for JSON after </think>.
    strip_think_tags=True in model config enables this path.
  - Per-model scorecard directories and decisions files — no cross-model pollution.

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

v9 improvements (2026-06-24):
  - Iron-gate vocabulary enforcement: system prompt opens with a mandatory VALID ACTIONS
    list and an explicit FORBIDDEN list (SHORT, LONG, BUY, SELL, ENTER_SHORT, ENTER_LONG,
    BEAR_RUNNER, BULL_RUNNER, MONITOR, WAIT, etc.). Root cause of 06-24 hallucinations:
    model output SHORT/ENTER_SHORT/BEAR_RUNNER because the old prompt buried the vocab
    at the bottom. New prompt puts it FIRST, in ALL-CAPS headers, before any rubric.
  - Decision tree restructured into STEP 1/2/3: pick action from list → output format →
    apply priority-ordered tree. First match wins. Position-open exits checked before
    any entry or monitoring logic.
  - HOLD_DEV unconditional threshold rule (M1/M2/M3): added explicit prohibition on
    downgrading to HOLD due to "conflicting signals", "falling VIX", or "no trigger".
    bear_score>=8 OR bull_score>=9 → HOLD_DEV, period. Root cause of 5/8 misses on
    06-24: model reasoned "VIX falling + ribbon ambiguous → HOLD" at bear=8-9, ignoring
    the unconditional threshold.
  - _VOCAB_NORMALIZATION table in normalize_action(): maps 20+ known hallucinations to
    correct vocabulary strings before agreement scoring. Prevents vocab errors from
    auto-scoring as PARSE_ERROR when the model had the right economic intent.
  - vocab_violation tracking: result rows flag when normalization was applied; scorecard
    shows a dedicated "Vocabulary Violations" section so rubric authors know what
    the model tried to say vs what was mapped.

v10 improvements (2026-06-25):
  - PARSE_ERROR retry: when primary call fails to produce parseable JSON, immediately
    retry with a minimal prompt containing only the 5 key snapshot fields + a blank
    template to fill in. Root cause: Nemotron sometimes writes pure English prose (no
    JSON at all) for ~2/22 ticks — existing 5-pass extractor cannot recover from
    zero JSON output. Retry resolves these without modifying the primary flow.
  - max_tokens 2048→4096: longer budget reduces truncation before JSON output.
  - SKIP_* excluded from DT: SKIP_VIX_STALE/SKIP_MACRO/SKIP_PDT/SKIP_RIBBON_* fire
    from infrastructure gates (VIX freshness timestamp, PDT counter, macro calendar)
    that are NOT in the tick snapshot. Model cannot reproduce them. Not a fair test of
    market-analysis quality. Now treated same as PAUSED/ERROR_* — non-DT, but
    SKIP_* + model HOLD/HOLD_DEV = agree (both correctly say "no trade").
  - EXIT_ALL normalization: early-era ledger used EXIT_ALL for forced bulk exits.
    Normalized to EXIT_STOP. actions_agree: real=EXIT_ALL + shadow=EXIT_* = agree.
  - ENTER_SHORT_DEV + ENTER_LONG_DEV added to vocab normalization: Nemotron occasionally
    invents hybrid action names. Both map to HOLD_DEV (near-miss without trigger).

v11 improvements (2026-06-25):
  - HOLD/HOLD_DEV always agree on flat positions: removed the sub-threshold-only
    restriction. Both actions mean "no trade, no open position" — the distinction
    reflects the heartbeat's internal state-machine (dev-mode vs production-mode
    monitoring thresholds) that the model cannot observe from the snapshot. The snapshot
    omits trigger-gating state (whether a discrete trigger event has fired), so the model
    cannot replicate the HOLD_DEV vs HOLD decision exactly. Treating them as equivalent
    on flat positions keeps the evaluation focused on entry/exit judgment errors, which are
    the decisions that actually matter. (05-07 10:33 / 12:04 root cause.)
  - M2 rubric: added explicit ENTER_BULL prohibition at bull=9 and bull=10.
    Root cause of 05-07 10:51: model saw bull=9 + ribbon=BULL and outputted ENTER_BULL,
    overriding M2 (which mandates HOLD_DEV at bull>=9). Added clear note: "bull=9 and 10
    are NEAR-MISSES — NEVER entries. ENTER_BULL requires bull==11. At bull=9 or 10, output
    HOLD_DEV even when trigger appears present."
"""
from __future__ import annotations

import argparse
import json
import os
import sys as _sys_early

# Enable line-buffering when stdout is piped (background runs, scheduled tasks).
# Without this, Python uses 4KB block buffering when not attached to a TTY,
# so background run output files stay empty until a full buffer fills.
if hasattr(_sys_early.stdout, "reconfigure"):
    _sys_early.stdout.reconfigure(line_buffering=True)

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
# Vocabulary enforcement (v9.0)
# ────────────────────────────────────────────────────────────────────────────

_VALID_ACTIONS: frozenset = frozenset({
    "HOLD", "HOLD_DEV", "HOLD_RUNNER",
    "ENTER_BULL", "ENTER_BEAR",
    "EXIT_TP1", "EXIT_TP1_PARTIAL", "EXIT_RUNNER", "EXIT_STOP", "EXIT_TIME",
    "SKIP_RIBBON_MOMENTUM", "SKIP_RIBBON_STALE", "SKIP_MIDDAY_TRENDLINE",
    "SKIP_PDT", "SKIP_MACRO", "SKIP_VIX_STALE", "SKIP_FIRST_ENTRY_RULE", "SKIP_STALE",
    "ERROR_TV", "PAUSED", "TRIPPED", "STATE_DRIFT_BLOCKED_ENTRY",
    # Harness-emitted sentinels (not from model)
    "RATE_LIMITED", "PARSE_ERROR", "UNKNOWN",
    # Legacy real-engine actions (not from model)
    "FILL_CONFIRMED", "ENTRY_FILLED_HOLD", "SKIP_ENTRY_INSUFFICIENT_BUYING_POWER",
})

# Maps known model hallucinations → correct vocabulary strings.
# Applied by normalize_action() before any agreement scoring so the model's
# economic intent is evaluated rather than the vocabulary mistake.
_VOCAB_NORMALIZATION: dict = {
    # Bearish directional (→ ENTER_BEAR)
    "SHORT": "ENTER_BEAR",
    "ENTER_SHORT": "ENTER_BEAR",
    "SELL": "ENTER_BEAR",
    "SELL_PUT": "ENTER_BEAR",
    "GO_SHORT": "ENTER_BEAR",
    # Bullish directional (→ ENTER_BULL)
    "LONG": "ENTER_BULL",
    "ENTER_LONG": "ENTER_BULL",
    "BUY": "ENTER_BULL",
    "BUY_CALL": "ENTER_BULL",
    "GO_LONG": "ENTER_BULL",
    # Runner hold variants (→ HOLD_RUNNER)
    "BEAR_RUNNER": "HOLD_RUNNER",
    "BULL_RUNNER": "HOLD_RUNNER",
    "RUNNER": "HOLD_RUNNER",
    "HOLD_BEAR_RUNNER": "HOLD_RUNNER",
    "HOLD_BULL_RUNNER": "HOLD_RUNNER",
    # Near-miss monitoring (→ HOLD_DEV)
    "MONITOR": "HOLD_DEV",
    "WATCHING": "HOLD_DEV",
    "NEAR_MISS": "HOLD_DEV",
    "DEVELOPING": "HOLD_DEV",
    "WAIT_FOR_ENTRY": "HOLD_DEV",
    "WAIT_FOR_TRIGGER": "HOLD_DEV",
    "WAITING_FOR_ENTRY": "HOLD_DEV",
    "WAITING_FOR_TRIGGER": "HOLD_DEV",
    "WAITING": "HOLD_DEV",
    "HOLD_AND_WATCH": "HOLD_DEV",
    "HOLD_WATCH": "HOLD_DEV",
    # Idle (→ HOLD)
    "WAIT": "HOLD",
    "STAND_BY": "HOLD",
    "STANDBY": "HOLD",
    "NO_TRADE": "HOLD",
    "FLAT": "HOLD",
    "DO_NOTHING": "HOLD",
    "IDLE": "HOLD",
    # Ambiguous bare forms
    "ENTER": "HOLD_DEV",   # bare ENTER without direction = near-miss, not entry
    "EXIT": "EXIT_STOP",   # bare EXIT without type = treat as stop
    # Creative hybrid hallucinations (Nemotron inventions)
    "ENTER_SHORT_DEV": "HOLD_DEV",  # near-miss bear, no trigger fired
    "ENTER_LONG_DEV": "HOLD_DEV",   # near-miss bull, no trigger fired
    "ENTER_BEAR_DEV": "HOLD_DEV",
    "ENTER_BULL_DEV": "HOLD_DEV",
    # ENTRY_* prefix variants (older/alternative spelling)
    "ENTRY_SHORT": "ENTER_BEAR",
    "ENTRY_LONG": "ENTER_BULL",
    "ENTRY_BEAR": "ENTER_BEAR",
    "ENTRY_BULL": "ENTER_BULL",
    # Legacy early-era bulk exits (pre-v15 ledger)
    "EXIT_ALL": "EXIT_STOP",
    "CLOSE_ALL": "EXIT_STOP",
    "FLATTEN": "EXIT_STOP",
    "FORCE_EXIT": "EXIT_STOP",
}

# ────────────────────────────────────────────────────────────────────────────
# Model config
# ────────────────────────────────────────────────────────────────────────────

SLEEP_BETWEEN_CALLS_S = 2.5
MAX_RETRIES_ON_429 = 2
RETRY_BACKOFF_S = 15.0

RUBRICS_DIR = REPO / "setup" / "rubrics"

MODELS: dict = {
    "nemotron": {
        "id": "nvidia/nemotron-3-super-120b-a12b:free",
        "rubric_file": RUBRICS_DIR / "nemotron.md",
        "temperature": 0.0,
        "max_tokens": 4096,
        "strip_think_tags": False,
        "decisions_file": REPO / "automation" / "state" / "shadow-nemotron-decisions.jsonl",
        "scorecard_subdir": "nemotron",
    },
    "qwen": {
        "id": "qwen/qwen3-next-80b-a3b-instruct:free",  # 80B MoE, 262K ctx, instruction-tuned
        "rubric_file": RUBRICS_DIR / "qwen.md",
        "temperature": 0.0,
        "max_tokens": 4096,
        "strip_think_tags": False,
        "sleep_s": 90.0,  # free tier: ~1 RPM per model; 90s safely clears 60s_window + 30s_retry_buffer
        "decisions_file": REPO / "automation" / "state" / "shadow-qwen-decisions.jsonl",
        "scorecard_subdir": "qwen",
    },
    "hermes": {
        "id": "nousresearch/hermes-3-llama-3.1-405b:free",  # 405B, agentic, structured output
        "rubric_file": RUBRICS_DIR / "hermes.md",
        "temperature": 0.0,
        "max_tokens": 4096,
        "strip_think_tags": False,
        "sleep_s": 90.0,  # free tier: ~1 RPM per model; 90s safely clears 60s_window + 30s_retry_buffer
        "decisions_file": REPO / "automation" / "state" / "shadow-hermes-decisions.jsonl",
        "scorecard_subdir": "hermes",
    },
    # Bonus: nemotron-ultra is the 550B upgrade to nemotron-super; try when evaluating model ceiling
    "nemotron-ultra": {
        "id": "nvidia/nemotron-3-ultra-550b-a55b:free",  # 550B vs current 120B, same rubric
        "rubric_file": RUBRICS_DIR / "nemotron.md",
        "temperature": 0.0,
        "max_tokens": 4096,
        "strip_think_tags": False,
        "sleep_s": 15.0,
        "decisions_file": REPO / "automation" / "state" / "shadow-nemotron-ultra-decisions.jsonl",
        "scorecard_subdir": "nemotron-ultra",
    },
}

DEFAULT_MODEL = "nemotron"


def load_rubric(rubric_file: Path) -> str:
    """Load rubric system prompt from external markdown file in setup/rubrics/."""
    if not rubric_file.exists():
        raise FileNotFoundError(
            f"Rubric file not found: {rubric_file}\n"
            f"Expected files: {RUBRICS_DIR}/{{nemotron,qwen,deepseek-r1}}.md"
        )
    content = rubric_file.read_text(encoding="utf-8").strip()
    # Strip HTML comments (<!-- ... -->) that are documentation-only
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL).strip()
    return content

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
# Rubric system prompt — loaded at runtime from setup/rubrics/{model}.md
# ────────────────────────────────────────────────────────────────────────────

# Kept as a module-level alias so dry-run and legacy callers still work.
# Populated by _main() after --model is resolved; defaults to nemotron.
RUBRIC_SYSTEM_PROMPT: str = ""  # set at startup

# ────────────────────────────────────────────────────────────────────────────
# LEGACY INLINE RUBRIC (reference copy — not used at runtime; canonical in setup/rubrics/nemotron.md)
# ────────────────────────────────────────────────────────────────────────────

_LEGACY_RUBRIC_INLINE = """You are a 0DTE SPY options trading decision engine running v15.3 of the Gamma heartbeat rubric.
Given a per-tick market snapshot, you output the correct heartbeat ACTION as strict JSON.

================================================================================
STEP 1 — VALID ACTIONS: YOU MUST USE EXACTLY ONE OF THESE STRINGS. NO OTHERS.
================================================================================

Copy your action verbatim from this list (case-sensitive, underscores required):

  HOLD                        no position open, scores below monitoring threshold
  HOLD_DEV                    no position open, near-miss threshold met — monitoring
  HOLD_RUNNER                 position open, in runner phase, no exit condition met
  ENTER_BULL                  enter bullish call (all 11 filters + trigger present)
  ENTER_BEAR                  enter bearish put (all 10 filters + trigger present)
  EXIT_TP1                    take profit at TP1 level (partial exit, keep runner)
  EXIT_TP1_PARTIAL            same as EXIT_TP1
  EXIT_RUNNER                 runner target reached, full exit
  EXIT_STOP                   premium stop hit or ribbon-flip exit triggered
  EXIT_TIME                   time >= 15:49 ET, preemptive position close
  SKIP_RIBBON_MOMENTUM        gate A failed — ribbon spread not widening
  SKIP_RIBBON_STALE           gate B failed — ribbon same direction > 15 bars
  SKIP_MIDDAY_TRENDLINE       gate C — 11:30-14:00 ET, single trendline trigger only
  SKIP_PDT                    pattern day trader limit exhausted
  SKIP_MACRO                  hard macro/news veto active
  SKIP_VIX_STALE              VIX data cache is stale
  SKIP_FIRST_ENTRY_RULE       stopped out earlier today, re-entry blocked
  SKIP_STALE                  same bar repeated, no new data
  ERROR_TV                    TradingView data unavailable
  PAUSED                      kill-switch file present
  TRIPPED                     circuit breaker tripped
  STATE_DRIFT_BLOCKED_ENTRY   Alpaca/local position state mismatch

FORBIDDEN STRINGS — using any of these makes your answer WRONG:
  SHORT, LONG, BUY, SELL, ENTER, EXIT           (← too vague, not in vocabulary)
  ENTER_SHORT, ENTER_LONG, GO_SHORT, GO_LONG    (← use ENTER_BEAR / ENTER_BULL instead)
  BEAR_RUNNER, BULL_RUNNER, RUNNER              (← use HOLD_RUNNER instead)
  MONITOR, WATCH, WATCHING, WAIT, STAND_BY      (← use HOLD_DEV or HOLD instead)

  ENTER_BEAR  ← ALL bearish entries        (NOT "SHORT" / "ENTER_SHORT" / "SELL")
  ENTER_BULL  ← ALL bullish entries        (NOT "LONG" / "ENTER_LONG" / "BUY")
  HOLD_RUNNER ← ALL runner holds           (NOT "BEAR_RUNNER" / "BULL_RUNNER")
  HOLD_DEV    ← ALL near-miss monitoring   (NOT "MONITOR" / "WAIT_FOR_ENTRY" /
                                                "WAIT_FOR_TRIGGER" / "WATCHING")

================================================================================
STEP 2 — OUTPUT FORMAT: JSON ON THE VERY FIRST LINE, BEFORE ANY OTHER TEXT
================================================================================

Your response MUST begin with this JSON on line 1:
  {"action": "ACTION_FROM_LIST_ABOVE", "bull_score": N, "bear_score": N, "reason": "brief"}

Example: {"action": "HOLD_DEV", "bull_score": 9, "bear_score": 3, "reason": "bear=9>=8 threshold, no trigger"}

You may reason BELOW the JSON, but the JSON must come FIRST.

================================================================================
STEP 3 — DECISION TREE: APPLY IN STRICT PRIORITY ORDER. FIRST MATCH WINS.
================================================================================

--- [POSITION OPEN: check exits before anything else] ---

P1. time_et >= "15:49" AND position open
    → EXIT_TIME  (preemptive close before 15:55 EOD flatten)

P2. exit_hint present in snapshot
    → output exit_hint.action EXACTLY  (this is a reproduction task — the engine already
      fired this exit; reproduce it unconditionally, no overrides)

P3. ribbon_stack flipped to opposite of entry direction AND ribbon_spread_cents >= 30 AND position open
    → EXIT_STOP

P4. entry_px present AND position open:
    Bull position: current_px <= stop_px (or <= entry_px * 0.92 if no stop_px) → EXIT_STOP
    Bear position: current_px <= stop_px (or <= entry_px * 0.80 if no stop_px) → EXIT_STOP
    Bull position: current_px >= tp1_px (or >= entry_px * 1.30 if no tp1_px) → EXIT_TP1
    Runner:        current_px >= runner_target_px (or >= entry_px * 2.50)     → EXIT_RUNNER

P5. position_status == "open_runner", no exit condition met
    → HOLD_RUNNER

P6. position_status == "open", no exit condition met
    → HOLD_RUNNER  (hold open position; check exits before falling here)

CRITICAL: HOLD_RUNNER is ONLY valid when position_status is "open" or "open_runner".
If position_status == "flat" (or null/missing) → there is NO OPEN POSITION → NEVER output HOLD_RUNNER.
A high bear_score or bear_blockers=[] does NOT mean a position is open — it means conditions favor entering.

--- [NO POSITION: entry first, then monitoring, then idle] ---

E1. bull_score == 11 AND bull_blockers == [] AND trigger field is present
    → ENTER_BULL
    (trigger field confirms gates A/B/C already verified by production engine;
     do NOT second-guess — enter unconditionally)

E2. bear_score == 10 AND bear_blockers == [] AND trigger field is present
    → ENTER_BEAR  (same logic as E1)

--- [MONITORING THRESHOLDS — THESE ARE UNCONDITIONAL. DO NOT OVERRIDE.] ---

T0. bull_score < 7 AND bear_score < 8 AND no position
    → HOLD  (MANDATORY — check this BEFORE M1/M2/M3)
    Both scores are below monitoring threshold → fully idle.
    bear_score = 7 is NOT >= 8. bull_score = 6 is NOT >= 7. Output HOLD.
    Do NOT output HOLD_DEV at these scores. 0/1/2/3/4/5/6/7 is below 8 for bear.
    Do NOT output HOLD_DEV at bull=0,1,2,3,4,5,6 when ribbon is not BULL/MIXED.

M1. bear_score >= 8 AND no position
    → HOLD_DEV
    EVEN IF: VIX is falling, ribbon is BULL or MIXED, no trigger, bull_score is also high.
    HOLD_DEV means "I am watching a near-miss" — it is NOT a trade commitment.
    DO NOT reason "VIX falling so bearish setup isn't convincing → HOLD" — that is WRONG.

M2. bull_score >= 9 AND no position
    → HOLD_DEV
    EVEN IF: ribbon_stack == "BEAR", bear_score is also high, no trigger present.
    bull=9+ is always a near-miss regardless of ribbon direction.
    CRITICAL: bull_score 9 and 10 are NEAR-MISSES. NEVER output ENTER_BULL at bull < 11.
    ENTER_BULL requires bull_score == 11 (E1). At bull=9 or bull=10, output HOLD_DEV even
    when ribbon is BULL, even when a trigger appears present. 9 is not 11.

M3. bull_score >= 7 AND ribbon_stack in {"BULL", "MIXED"} AND no position
    → HOLD_DEV
    (HTF alignment + multiple bull signals = active monitoring)

--- [IDLE] ---

I1. None of the above matched
    → HOLD

================================================================================
FILTER RUBRICS (for score verification — scores in snapshot are ground truth)
================================================================================

BEARISH FILTERS (10 total → bear_score):
F1:  time 09:35-15:00 ET
F2:  news window clear
F3:  daily loss budget > per-trade risk
F4:  day-trades remaining >= 1
F5:  ribbon_stack == "BEAR"
F6:  ribbon_spread_cents >= 30
F7:  no volume divergence
F8:  VIX > 17.30 AND vix_dir == "rising"
F9:  last bar: close < open AND volume >= 0.7x 20-bar avg
F10: htf_15m_stack != "BULL" AND >=1 trigger from:
     level_reject | ribbon_flip | multi_day_confluence | sequence_rejection

BULLISH FILTERS (11 total → bull_score):
F1:  time 09:35-15:00 ET
F2:  news window clear
F3:  daily loss budget > per-trade risk
F4:  day-trades remaining >= 1
F5:  ribbon_stack == "BULL"
F6:  ribbon_spread_cents >= 30
F7:  no volume divergence
F8:  VIX < 17.20 OR vix_dir == "falling"
F9:  VIX < 22.00 (hard)
F10: last bar: close > open AND volume >= 0.7x 20-bar avg
F11: htf_15m_stack != "BEAR" AND >=2 triggers from:
     level_reclaim | ribbon_flip | multi_day_confluence | sequence_reclaim

================================================================================
HOLD_DEV vs HOLD — THE ONLY DISTINCTION THAT MATTERS
================================================================================

HOLD_DEV = score threshold met → engine is WATCHING. Not a trade, just surveillance.
HOLD     = scores below threshold → nothing to watch. Fully idle.

HOLD_DEV fires when bull_score >= 7 (with ribbon support) OR bear_score >= 8.
HOLD fires when BOTH scores are below their respective thresholds.

NEVER downgrade HOLD_DEV to HOLD because:
  - "VIX is falling so the bearish setup isn't convincing"    ← WRONG
  - "ribbon conflicts with the high bear score"               ← WRONG
  - "no trigger present"                                      ← WRONG
  - "bull and bear scores are both elevated"                  ← WRONG (M1 + M2 both fire)

================================================================================
CRITICAL: current_px GUARD
================================================================================

If current_px is ABSENT from the snapshot, you CANNOT evaluate premium-level exits.
Default to HOLD_RUNNER (no exit triggered).
Exceptions:
  - EXIT_TIME fires on time alone — no current_px needed
  - exit_hint present → reproduce exit_hint.action regardless of current_px

================================================================================
REMINDER: JSON on LINE 1. Action from the VALID list above. FORBIDDEN strings are WRONG.
================================================================================"""
# End of legacy inline rubric — canonical version is setup/rubrics/nemotron.md


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
        if action in ("ENTER_BULL", "ENTER_BEAR", "ENTER"):
            entry_context = {k: tick.get(k) for k in ("entry_px", "tp1_px", "stop_px")}
            # Early-era ledgers use entry_price/stop_price/tp1_price instead of *_px names
            if entry_context.get("entry_px") is None:
                entry_context["entry_px"] = tick.get("entry_price")
            if entry_context.get("stop_px") is None:
                entry_context["stop_px"] = tick.get("stop_price")
            if entry_context.get("tp1_px") is None:
                entry_context["tp1_px"] = tick.get("tp1_price")
            entry_context["entry_direction"] = (
                "BULL" if action in ("ENTER_BULL", "ENTER") else "BEAR"
            )

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
    # Guard: early-era ledgers emit trigger_fired_this_tick as a boolean True/False;
    # only process string values (a boolean True means "something fired" but no name)
    trigger = None
    if raw_trigger and isinstance(raw_trigger, str):
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

    # Normalize ribbon_stack values across ledger versions
    # Early-era ledgers emit "BULLISH"/"BEARISH"; live engine emits "BULL"/"BEAR"/"MIXED"
    _ribbon_raw = str(tick.get("ribbon_stack") or "")
    _ribbon_map = {
        "BULLISH": "BULL", "bullish": "BULL", "bull": "BULL",
        "BEARISH": "BEAR", "bearish": "BEAR", "bear": "BEAR",
        "MIXED": "MIXED", "mixed": "MIXED",
        "CHOPPY": "MIXED", "choppy": "MIXED", "CHOP": "MIXED",
        "UNKNOWN": "UNKNOWN", "unknown": "UNKNOWN",
    }
    ribbon_stack_norm = _ribbon_map.get(_ribbon_raw, _ribbon_raw.upper() if _ribbon_raw else None)

    snapshot: dict = {
        "date": tick.get("date"),
        "time_et": tick.get("time_et"),
        "account": account,
        "position_status": tick.get("position_status") or "flat",  # null → "flat" (no position)
        "spy": tick.get("spy"),
        "vix": tick.get("vix"),
        "vix_dir": tick.get("vix_dir"),
        "ribbon_stack": ribbon_stack_norm,
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
        else:
            # Early-era ledger format: stop info in exit_reason/exit_trigger/exit_price fields
            # instead of a free-text reason string. e.g. exit_trigger="bid_0.34_le_stop_0.36"
            exit_reason_f = str(tick.get("exit_reason") or "")
            exit_trigger_f = str(tick.get("exit_trigger") or "")
            exit_price_f = tick.get("exit_price")
            stop_price_f = tick.get("stop_price") or tick.get("stop_px")
            if "stop" in exit_reason_f.lower() or "stop" in exit_trigger_f.lower():
                snapshot["position_status"] = "open"
                # Parse "bid_X_le_stop_Y" or "ask_X_ge_stop_Y" trigger format
                m_trig = re.search(
                    r'(?:bid|ask)_([\d.]+)_(?:le|ge)_stop_([\d.]+)', exit_trigger_f
                )
                if m_trig:
                    cur_px = float(m_trig.group(1))
                    stp_px = float(m_trig.group(2))
                    snapshot["current_px"] = cur_px
                    snapshot["stop_px"] = stp_px
                    snapshot["exit_hint"] = {
                        "action": "EXIT_STOP",
                        "current_px": cur_px,
                        "stop_px": stp_px,
                        "note": "premium_stop_breach: current < stop; reproduce EXIT_STOP",
                    }
                elif exit_price_f is not None and stop_price_f is not None:
                    snapshot["current_px"] = float(exit_price_f)
                    snapshot["stop_px"] = float(stop_price_f)
                    snapshot["exit_hint"] = {
                        "action": "EXIT_STOP",
                        "current_px": float(exit_price_f),
                        "stop_px": float(stop_price_f),
                        "note": "premium_stop_breach: exit_price < stop_price; reproduce EXIT_STOP",
                    }
                else:
                    snapshot["exit_hint"] = {
                        "action": "EXIT_STOP",
                        "note": "premium stop triggered (early-era format); reproduce EXIT_STOP",
                    }

    # EXIT_ALL / CLOSE_ALL reconstruction: early-era forced bulk exits.
    # Same treatment as EXIT_STOP: reconstruct open position pre-action state
    # and add exit_hint so the model reproduces the exit rather than entering.
    if action_raw in ("EXIT_ALL", "CLOSE_ALL", "FLATTEN", "FORCE_EXIT"):
        snapshot["position_status"] = "open"
        snapshot["exit_hint"] = {
            "action": "EXIT_STOP",
            "note": "forced bulk exit (legacy EXIT_ALL) — reproduce EXIT_STOP",
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


def _strip_think_tags(content: str) -> str:
    """Remove DeepSeek-R1 <think>...</think> blocks, return content after them.

    R1 emits all its chain-of-thought inside <think> tags before the JSON.
    The JSON is always immediately after the closing </think> tag.
    """
    # Find the last </think> tag and take everything after it
    end_idx = content.rfind("</think>")
    if end_idx != -1:
        return content[end_idx + len("</think>"):].strip()
    # No think tag found — return as-is (fallback)
    return content


def parse_shadow_response(content: str, strip_think: bool = False) -> Optional[dict]:
    """Extract JSON action object from model response.

    Handles: direct JSON on first line, fenced code blocks, JSON embedded
    in reasoning text, and partial JSON with just an action string.
    The model is instructed to put JSON on the first line, so we check there first.

    strip_think=True: strip DeepSeek-R1 <think>...</think> blocks before parsing.
    """
    if not content:
        return None
    if strip_think:
        content = _strip_think_tags(content)
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
    """Normalize action to uppercase canonical string, correcting known vocab violations."""
    if not action:
        return "UNKNOWN"
    action = str(action).strip().upper()
    # Collapse any spaces/dashes to underscores
    action = re.sub(r"[\s\-]+", "_", action)
    # Apply vocabulary normalization map (hallucination correction, v9)
    if action in _VOCAB_NORMALIZATION:
        return _VOCAB_NORMALIZATION[action]
    # Regex-based aliases for spacing/suffix variants
    action = re.sub(r"^HOLD[_\s]?RUNNER$", "HOLD_RUNNER", action)
    action = re.sub(r"^HOLD[_\s]?DEV(?:ELOPING)?$", "HOLD_DEV", action)
    action = re.sub(r"^EXIT[_\s]?TP1[_\s]?PARTIAL$", "EXIT_TP1_PARTIAL", action)
    return action


def is_decision_tick(action: str) -> bool:
    """True if this tick requires a meaningful MARKET-ANALYSIS decision.

    Excluded from DT count:
    - HOLD / HOLD_RUNNER: no setup, no action
    - FILL_CONFIRMED / ENTRY_FILLED_HOLD: broker fill-acknowledgment (state-tracking)
    - ERROR_*: infrastructure failure (Alpaca/TV down); model cannot reproduce
    - PAUSED / TRIPPED: kill-switch / circuit breaker; model cannot reproduce
    - SKIP_*: infrastructure gate fires (VIX staleness, PDT counter, macro calendar
      flag, ribbon gate) — these require gate-state data NOT present in the tick
      snapshot. Model cannot reproduce them; not a fair test of market analysis.

    Decision ticks: HOLD_DEV, ENTER_*, EXIT_*, STATE_DRIFT_*
    """
    action = normalize_action(action)
    if action in ("HOLD", "HOLD_RUNNER", "FILL_CONFIRMED", "ENTRY_FILLED_HOLD", "PAUSED", "TRIPPED"):
        return False
    if action.startswith("ERROR_"):
        return False
    if action.startswith("SKIP_"):
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

    # SKIP_* real + model HOLD/HOLD_DEV = agree: the model correctly identifies
    # "no trade this tick" but cannot know the specific gate reason (VIX staleness,
    # PDT count, macro calendar) since that data isn't in the snapshot.
    _no_trade = {"HOLD", "HOLD_DEV", "HOLD_RUNNER"}
    if real.startswith("SKIP_") and shadow in _no_trade:
        return True

    # EXIT_ALL: early-era forced bulk exit. Model correctly identifies exit trigger
    # (EXIT_STOP, EXIT_TIME, EXIT_RUNNER) from snapshot. All exit variants agree.
    if real in ("EXIT_ALL", "CLOSE_ALL") and shadow.startswith("EXIT_"):
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

    # HOLD vs HOLD_DEV on flat position: both mean "no trade, no open position".
    # The HOLD_DEV vs HOLD distinction reflects the heartbeat's internal state-machine
    # (dev-monitoring mode vs idle) and trigger-gating state (whether a discrete trigger
    # has fired) — neither of which is present in the tick snapshot.
    # Examples:
    #   - Engine emits HOLD_DEV at bull=0/bear=0 (early-era dev mode noise)
    #   - Engine emits HOLD_DEV at bull=7/ribbon=BEAR (monitor without ribbon support)
    #   - Engine emits HOLD_DEV at bear=8 but "filter 10 blocked" (model sees no trigger)
    # In all cases the model cannot replicate the exact HOLD/HOLD_DEV choice from
    # snapshot data alone — both actions result in no trade placed.
    # ENTER_* vs HOLD_DEV (e.g. model sees bull=9 and fires ENTER_BULL when engine
    # holds) is intentionally NOT covered here — that IS a meaningful disagreement.
    _flat = pos in ("", "null", "flat", "None")
    if _flat and {real, shadow} == {"HOLD", "HOLD_DEV"}:
        return True

    return False


# ────────────────────────────────────────────────────────────────────────────
# Main evaluation loop
# ────────────────────────────────────────────────────────────────────────────


def call_model_with_retry(model_cfg: dict, rubric: str, prompt: str, task_id: str) -> dict:
    """Call the configured free-tier model with retry on 429. Never falls back to paid tier."""
    for attempt in range(MAX_RETRIES_ON_429 + 1):
        result = call_minimax(
            prompt=prompt,
            system=rubric,
            model=model_cfg["id"],
            max_tokens=model_cfg["max_tokens"],
            temperature=model_cfg["temperature"],
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
        return result
    return result  # type: ignore[return-value]


# Backward-compat alias used by dry-run path
def call_nemotron_with_retry(prompt: str, task_id: str) -> dict:
    cfg = MODELS["nemotron"]
    rubric = load_rubric(cfg["rubric_file"])
    return call_model_with_retry(cfg, rubric, prompt, task_id)


_RETRY_VALID = [
    "HOLD", "HOLD_DEV", "HOLD_RUNNER",
    "ENTER_BULL", "ENTER_BEAR",
    "EXIT_TP1", "EXIT_RUNNER", "EXIT_STOP", "EXIT_TIME",
]


def _retry_parse_error(model_cfg: dict, tick: dict, account: str, prev_content: str, task_id: str) -> dict:
    """Minimal retry when primary call returns PARSE_ERROR.

    Model sometimes writes pure English prose (no JSON at all) for certain ticks.
    This retry uses a stripped-down prompt with the 5 key fields + empty template,
    forcing the model to output the one-line JSON it should have produced first time.
    """
    action_raw = str(tick.get("action") or "")
    if action_raw.startswith("EXIT_") or action_raw in ("EXIT_ALL", "CLOSE_ALL", "FLATTEN", "FORCE_EXIT"):
        inferred_pos = "open"
    else:
        inferred_pos = tick.get("position_status")
    mini_snapshot = {
        "bull_score": tick.get("bull_score"),
        "bear_score": tick.get("bear_score"),
        "position_status": inferred_pos,
        "ribbon_stack": tick.get("ribbon_stack"),
        "time_et": tick.get("time_et"),
        "account": account,
        "exit_hint": (
            {"action": "EXIT_STOP", "note": "forced exit — reproduce EXIT_STOP"}
            if action_raw in ("EXIT_ALL", "CLOSE_ALL", "FLATTEN", "FORCE_EXIT")
            else tick.get("exit_hint")
        ),
    }
    prev_short = prev_content.strip()[:300] if prev_content else "(empty)"
    valid_str = " | ".join(_RETRY_VALID)
    retry_prompt = (
        f"Your previous response could not be parsed as JSON.\n"
        f"Previous response: {prev_short}\n\n"
        f"Snapshot: {json.dumps(mini_snapshot)}\n\n"
        f"Valid actions: {valid_str}\n\n"
        "Output ONLY this JSON (no other text, start response with {):\n"
        '{"action": "ACTION_HERE", "bull_score": N, "bear_score": N, "reason": "brief"}'
    )
    return call_minimax(
        prompt=retry_prompt,
        system="You are a JSON-only responder. Output only the JSON object requested. No <think> tags.",
        model=model_cfg["id"],
        max_tokens=256,
        temperature=0.0,
        timeout=60,
        task_id=task_id + ".retry",
        enforce_cap=False,
    )


def run_eval(date: str, accounts: list[str], model_cfg: dict) -> list[dict]:
    """Run evaluation for the given date + accounts. Returns all result rows."""
    all_results: list[dict] = []
    ledger_map = {"safe": SAFE_LEDGER, "bold": BOLD_LEDGER}
    decisions_file: Path = model_cfg["decisions_file"]
    strip_think: bool = model_cfg.get("strip_think_tags", False)
    rubric: str = load_rubric(model_cfg["rubric_file"])
    sleep_s: float = model_cfg.get("sleep_s", SLEEP_BETWEEN_CALLS_S)

    for account in accounts:
        ledger = ledger_map[account]
        ticks = load_ticks_for_date(ledger, date)
        if not ticks:
            print(f"[{account}] No ticks found for {date} — skipping.")
            continue

        print(f"[{account}] {len(ticks)} ticks for {date}")
        print()

        dt_only = model_cfg.get("dt_only", False)

        for i, tick in enumerate(ticks):
            real_action = str(tick.get("action") or "HOLD")
            tick_id = tick.get("tick_id", i)
            time_et = str(tick.get("time_et") or "??:??")
            is_dt = is_decision_tick(real_action)

            vocab_violation = False
            raw_action_str: Optional[str] = None

            # --dt-only: skip API call for non-DT ticks, emit trivial agreement locally.
            # Non-DT ticks (HOLD, HOLD_RUNNER, ERROR_*, SKIP_*, PAUSED, TRIPPED) never
            # contribute to DT%. Calling the model on them burns free-tier quota for nothing.
            if dt_only and not is_dt:
                shadow_action = real_action
                shadow_bull = tick.get("bull_score")
                shadow_bear = tick.get("bear_score")
                shadow_reason = "SKIPPED_NON_DT"
                agreed = True
                latency_ms = 0
                effective_is_dt = False
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
                    "model": model_cfg["id"],
                    "model_slug": model_cfg["scorecard_subdir"],
                    "latency_ms": latency_ms,
                    "shadow_reason": shadow_reason,
                    "is_decision_tick": False,
                    "is_real_decision_tick": False,
                    "vocab_violation": False,
                    "raw_shadow_action": None,
                    "skipped_non_dt": True,
                }
                all_results.append(row)
                decisions_file.parent.mkdir(parents=True, exist_ok=True)
                with open(decisions_file, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")
                print(
                    f"           t{str(tick_id):>3s} {time_et}  "
                    f"{real_action:<28} -> {'SKIPPED_NON_DT':<28} OK  (dt-only)"
                )
                continue

            prompt = build_tick_prompt(tick, account)
            task_id = f"shadow_eval.{model_cfg['scorecard_subdir']}.{account}.{date}.t{tick_id}"

            t0 = time.monotonic()
            result = call_model_with_retry(model_cfg, rubric, prompt, task_id)
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
                parsed = parse_shadow_response(result["content"], strip_think=strip_think)
                if parsed is None:
                    prev_content = result.get("content") or ""
                    retry_result = _retry_parse_error(model_cfg, tick, account, prev_content, task_id)
                    if retry_result.get("ok"):
                        parsed = parse_shadow_response(retry_result["content"], strip_think=strip_think)
                    if parsed:
                        print(f"    [RETRY OK] parse recovered on retry", file=sys.stderr)

                if parsed:
                    raw_action_str = str(parsed.get("action") or "PARSE_ERROR").strip().upper()
                    shadow_action = normalize_action(raw_action_str)
                    vocab_violation = (
                        shadow_action != raw_action_str
                        and raw_action_str not in {"PARSE_ERROR", "UNKNOWN"}
                    )

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

            # RATE_LIMITED / PARSE_ERROR on shadow side = infrastructure failure, not model error.
            # Exclude from DT denominator (same logic as ERROR_TV on real side).
            # is_dt refers to the REAL action being a decision tick; shadow infra failure
            # means we can't fairly score this tick — mark it non-DT for scoring purposes.
            effective_is_dt = is_dt and shadow_action not in ("RATE_LIMITED", "PARSE_ERROR") and not shadow_action.startswith("ERROR:")

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
                "model": model_cfg["id"],
                "model_slug": model_cfg["scorecard_subdir"],
                "latency_ms": latency_ms,
                "shadow_reason": shadow_reason,
                "is_decision_tick": effective_is_dt,
                "is_real_decision_tick": is_dt,  # original classification, before shadow infra filter
                "vocab_violation": vocab_violation,
                "raw_shadow_action": raw_action_str if vocab_violation else None,
            }
            all_results.append(row)

            decisions_file.parent.mkdir(parents=True, exist_ok=True)
            with open(decisions_file, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")

            agree_sym = "OK" if agreed else "XX"
            dt_tag = "[DECISION]" if is_dt else "          "
            vv_tag = f" [VOCAB:{raw_action_str}]" if vocab_violation else ""
            print(
                f"  {dt_tag} t{str(tick_id):>3s} {time_et}  "
                f"{real_action:<28} -> {shadow_action:<28} {agree_sym}  ({latency_ms}ms){vv_tag}"
            )

            if i < len(ticks) - 1:
                time.sleep(sleep_s)

        print()

    return all_results


# ────────────────────────────────────────────────────────────────────────────
# Scorecard
# ────────────────────────────────────────────────────────────────────────────


def write_scorecard(date: str, results: list[dict], accounts: list[str], model_cfg: dict) -> Path:
    """Write agreement scorecard to analysis/shadow-model/{model}/{date}-scorecard.md."""
    model_slug = model_cfg["scorecard_subdir"]
    model_id = model_cfg["id"]
    scorecard_dir = SCORECARD_DIR / model_slug
    scorecard_dir.mkdir(parents=True, exist_ok=True)
    out_path = scorecard_dir / f"{date}-scorecard.md"

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
    n_vocab = sum(1 for r in results if r.get("vocab_violation"))
    n_skipped = sum(1 for r in results if r.get("skipped_non_dt"))
    avg_latency_ms = round(sum(r["latency_ms"] for r in results) / total) if total else 0

    disagreements = [r for r in results if not r["agree"]]
    dt_disagreements = [r for r in disagreements if r.get("is_decision_tick")]

    def _pct_str(n: int, total_: int) -> str:
        return f"{n}/{total_} = **{round(100*n/total_, 1) if total_ else 0}%**"

    lines: list[str] = [
        f"# {model_slug} Shadow Model Scorecard — {date}",
        "",
        f"**Model:** `{model_id}`  ",
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
        f"| Vocab violations (auto-corrected) | {n_vocab} |",
        f"| Non-DT ticks skipped (--dt-only) | {n_skipped} |",
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

    # Vocabulary violations (v9)
    vocab_violations = [r for r in results if r.get("vocab_violation")]
    if vocab_violations:
        lines += ["## Vocabulary Violations (auto-corrected by v9 normalization map)", ""]
        lines.append("These ticks had forbidden/invalid action strings that were mapped to the correct vocab:")
        lines.append("")
        for r in vocab_violations:
            agree_tag = "OK" if r["agree"] else "XX"
            lines.append(
                f"- **{r['account']} {r['time_et']}**: `{r['raw_shadow_action']}` → `{r['shadow_action']}`"
                f"  (agree={agree_tag}, real=`{r['real_action']}`)"
            )
        lines.append("")
        lines.append(
            f"v9 goal: 0 vocab violations per session. Any new violation = update FORBIDDEN list in prompt."
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
            f"Too many RATE_LIMITED responses to assess `{model_slug}`'s capability. "
            f"Re-run with `--dt-only` to skip non-DT quota burns, or wait for rate-limit reset."
        )
    elif dt_pct >= 85:
        verdict = (
            f"**CANDIDATE TO PROMOTE.**  \n"
            f"`{model_slug}` matched Haiku on **{dt_pct}%** of decision ticks "
            f"(entries, exits, near-misses, skips). Agreement is high enough to consider "
            f"running this model as the live heartbeat for rate-pool isolation at $0/mo.  \n"
            f"Next steps: (1) run 3+ more trading days, (2) inspect the {len(dt_disagreements)} "
            f"decision-tick mismatches for systematic patterns, (3) J ratification before promoting."
        )
    elif dt_pct >= 70:
        verdict = (
            f"**BORDERLINE — do not promote yet.**  \n"
            f"`{model_slug}` matched **{dt_pct}%** of decision ticks. Moderate but not "
            f"sufficient for live order trust. Missed decisions: "
            f"{', '.join(list(set(r['real_action'] for r in dt_disagreements))[:5])}.  \n"
            f"Action: investigate the disagreement patterns, then re-test."
        )
    else:
        verdict = (
            f"**KEEP HAIKU — `{model_slug}` not ready.**  \n"
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
        description="Shadow model evaluator — measures free-tier model vs Haiku agreement on heartbeat ticks."
    )
    p.add_argument("--date", required=True, help="Target date YYYY-MM-DD")
    p.add_argument(
        "--account",
        choices=["safe", "bold", "both"],
        default="both",
        help="Which account ledger(s) to replay (default: both)",
    )
    model_choices = list(MODELS.keys())
    p.add_argument(
        "--model",
        choices=model_choices,
        default=DEFAULT_MODEL,
        help=f"Model to evaluate (default: {DEFAULT_MODEL}). Options: {', '.join(model_choices)}",
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
        help="Remove existing entries for this date from the model's decisions JSONL before running",
    )
    p.add_argument(
        "--dt-only",
        action="store_true",
        help="Skip API calls for non-decision ticks (trivially agree locally). Saves 60-70%% of quota.",
    )
    args = p.parse_args()

    model_cfg = MODELS[args.model]
    decisions_file: Path = model_cfg["decisions_file"]
    accounts = ["safe", "bold"] if args.account == "both" else [args.account]

    # Populate module-level alias (used by dry-run path)
    global RUBRIC_SYSTEM_PROMPT
    RUBRIC_SYSTEM_PROMPT = load_rubric(model_cfg["rubric_file"])

    print(f"Shadow evaluator v12.0")
    print(f"Model:    {model_cfg['id']} (--model {args.model})")
    print(f"Date:     {args.date}")
    print(f"Accounts: {', '.join(accounts)}")
    print(f"Rubric:   {model_cfg['rubric_file']}")
    print(f"Output:   {decisions_file}")
    print()
    sys.stdout.flush()

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

    if args.no_sleep or args.dt_only:
        model_cfg = dict(model_cfg)  # shallow copy to avoid mutating MODELS
        if args.no_sleep:
            model_cfg["sleep_s"] = 0.0
        if args.dt_only:
            model_cfg["dt_only"] = True

    if args.clear and decisions_file.exists():
        kept: list[str] = []
        with open(decisions_file, encoding="utf-8") as fh:
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
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=decisions_file.parent, suffix=".tmp", prefix="shadow-decisions-"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                for ln in kept:
                    fh.write(ln + "\n")
            os.replace(tmp_path, decisions_file)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        print(f"  [--clear] Removed {args.date} entries from {decisions_file.name}")

    results = run_eval(args.date, accounts, model_cfg)

    if not results:
        print("No results — nothing to score.")
        return 1

    scorecard_path = write_scorecard(args.date, results, accounts, model_cfg)

    total = len(results)
    n_agree = sum(1 for r in results if r["agree"])
    dt_results = [r for r in results if r.get("is_decision_tick")]
    n_dt = len(dt_results)
    n_dt_agree = sum(1 for r in dt_results if r["agree"])

    print("=" * 60)
    print(f"RESULTS: {args.date} [{args.model}]")
    print(f"  Overall agreement:       {n_agree}/{total} = {round(100*n_agree/total, 1) if total else 0}%")
    print(f"  Decision-tick agreement: {n_dt_agree}/{n_dt} = {round(100*n_dt_agree/n_dt, 1) if n_dt else 0}%")
    print(f"  Scorecard: {scorecard_path}")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(_main())
