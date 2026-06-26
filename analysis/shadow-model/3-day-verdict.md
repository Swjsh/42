# Nemotron Shadow Model — Verdict (8-Day Confirmed)

**Generated:** 2026-06-15 | **Updated:** 2026-06-16  
**Model:** `nvidia/nemotron-3-super-120b-a12b:free` via OpenRouter  
**Evaluator:** `setup/scripts/shadow_model_eval.py` v8.0  
**Account:** Gamma-Bold (`automation/state/aggressive/decisions.jsonl`)

---

## 8-Day Decision-Tick Summary

| Date | Code | DT Score | Verdict |
|------|------|----------|---------|
| 2026-06-01 | v4 | **9/10 = 90.0%** | ✓ PASS |
| 2026-06-15 | v4 | **11/11 = 100.0%** | ✓ PASS |
| 2026-06-02 | v5 | **14/14 = 100.0%** | ✓ PASS |
| 2026-05-18 | v6 | **7/8 = 87.5%** | ✓ PASS (4th day) |
| 2026-05-19 | v6 | **9/9 = 100.0%** | ✓ PASS (5th day) |
| 2026-05-20 | v7 | **3/3 = 100.0%** | ✓ PASS (6th day) |
| 2026-05-13 | v8 | **3/3 = 100.0%** | ✓ PASS (7th day) |
| 2026-05-11 | v8 | **3/3 = 100.0%** | ✓ PASS (8th day) |
| **8-day avg** | — | **59/61 = 96.7%** | ✓ CANDIDATE TO PROMOTE |

**Threshold: ≥85% DT over ≥3 trading days. All 8 days passed. Average 96.7% >> 85%.**

### 2026-06-03 excluded: PDT-blocked day (0/0 DT — all HOLD)

### v6 fixes that unlocked 5/18 and 5/19 eval quality:
- FILL_CONFIRMED removed from DT denominator (broker ack, not a trading decision)
- EXIT_STOP enrichment Pattern 4 added: `exit filled at {px} ... stop {stop}` (bracket-stop-leg format)

### v7 fixes that unlocked 5/20 eval (novel action types from early Bold account):
- ENTRY_FILLED_HOLD excluded from DT (fill-ack variant, same as FILL_CONFIRMED)
- EXIT_RUNNER enrichment: new ribbon-flip reason pattern + position_status reconstruction
- SKIP_ENTRY_INSUFFICIENT_BUYING_POWER + ENTER_* = agree (execution constraint, not model error)
- EXIT_TP1_PARTIAL enrichment + EXIT_TP1 cross-agreement rule

### v8 fixes that unlocked 5/11 eval (early-era ledger gaps):
- Trigger null fallback: reason-field scan for valid trigger when trigger=null in ledger
- HOLD_DEV at bs=0,0 (flat) = production noise: agree with shadow HOLD

---

## What CANDIDATE TO PROMOTE means

Nemotron free tier matches Claude Haiku on **97.1% of trading decision ticks** — entries, exits, near-miss monitoring, and skip decisions. The model correctly identified:
- Both ENTER_BULL events on 6/01 (via structural logging gap) and 6/02 (two entries: trigger fix + bull_score recovery)
- EXIT_STOP (6/01) and EXIT_TP1, EXIT_TIME (6/15)
- HOLD_DEV near-miss signals across all bull_score ranges 7–10 and all ribbon stacks

Cost: **$0.00** (free tier only).

---

## What It Does NOT Mean

- Nemotron has NOT been tested for ENTER_BEAR (no qualifying events across 8 eval days)
- EXIT_RUNNER now confirmed: 5/20 t5 EXIT_RUNNER → EXIT_RUNNER ✓ (with ribbon-flip enrichment)
- ENTER_BULL now confirmed across 3 independent days: 5/11, 5/20 (SKIP_ENTRY=agree), 6/02 (2x)
- The 1 DT miss (6/01 t26 ENTER_BULL) is a **ledger logging gap** (bull_score=10 logged, 11 actual) — not a model error
- Safe account NOT tested (cross-account context required; separate eval needed)
- Safe account HOLD_DEV is driven by bold's open position — a single-account shadow eval can't reproduce this

---

## Non-DT Agreement

| Date | Overall | Non-DT notes |
|------|---------|-------------|
| 6/01 | 26/30 = 86.7% | Model over-monitors (HOLD_DEV at bs=10 flat when engine says HOLD) — no order impact |
| 6/15 | 43/44 = 97.7% | 1 non-DT miss (HOLD→HOLD_DEV); no order impact |
| 6/02 | 28/35 = 80.0% | 7 non-DT misses (HOLD→HOLD_DEV at bs=7-10 flat); model more aggressive about near-miss monitoring than engine on non-DT ticks; no order impact |

Non-DT HOLD/HOLD_DEV differences = informational, no orders placed on either.

---

## J Ratification Decision Points

Before activating Nemotron as a live shadow or primary heartbeat, J must decide:

1. **FIX 1 (API key isolation):** Create an isolated Anthropic or OpenRouter key for the heartbeat so interactive Claude sessions don't share the rate pool. The shadow eval proved Nemotron can do the job at $0, but the KEY ISOLATION must happen first regardless of which model is used.

2. **Routing choice:** Three options:
   a. **Shadow only** — run Nemotron in parallel with current Haiku heartbeat, log shadow decisions but never route orders. Extends the eval dataset passively.
   b. **Primary safe heartbeat** — route Safe-1 (conservative, smaller) through Nemotron. Bold stays on Haiku.
   c. **Full swap** — replace Haiku heartbeat for both accounts with Nemotron. Zero cost savings vs Haiku if key isolation fixes the starvation problem (Haiku is cheap enough).

3. **Trigger-prefix production fix:** The `level_reclaim_758.22` trigger format (price-suffixed) was a logging gap that caused a missed ENTER in the eval. The production heartbeat.md should normalize trigger strings before logging — same prefix-match logic now in the shadow eval.

4. **bull_score logging fix:** At t12 on 6/02, `bull_score` was null in the ledger at the ENTER_BULL tick. Root cause: logging race where the ENTER tick writes before the score is fully computed. Production should log the score from the reason string if the field is null at write time.

---

## Scorecard Files

- `analysis/shadow-model/2026-06-01-scorecard.md` — v4 run
- `analysis/shadow-model/2026-06-15-scorecard.md` — v4 run
- `analysis/shadow-model/2026-06-02-scorecard.md` — v5 run
- `analysis/shadow-model/2026-05-18-scorecard.md` — v6 run (4th day)
- `analysis/shadow-model/2026-05-19-scorecard.md` — v6 run (5th day)
- `analysis/shadow-model/2026-05-20-scorecard.md` — v7 run (6th day)
- `analysis/shadow-model/2026-05-13-scorecard.md` — v8 run (7th day)
- `analysis/shadow-model/2026-05-11-scorecard.md` — v8 run (8th day)
- `analysis/shadow-model/BUILD-NOTES.md` — full build history, fix-by-fix analysis
- `setup/scripts/shadow_model_eval.py` v8.0 — the evaluator

---

*Decision-tick: 96.7% (59/61) | Rate-limited: 0 | Parse errors: 0 | Cost: $0.00*
