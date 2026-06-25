# Multi-Model Shadow Eval Scorecard

**Benchmark:** Decision-tick agreement vs live Haiku heartbeat (v15.3)  
**Method:** `shadow_model_eval.py` v12.0 with `--dt-only --account safe`  
**DT definition:** Any tick where real_action ∉ {HOLD, HOLD_RUNNER, ERROR_*, SKIP_*, PAUSED, TRIPPED, FILL_CONFIRMED}  
**Rate-limit handling (v12):** RATE_LIMITED ticks excluded from DT denominator (not penalized)  
**Graduation bar:** ≥85% DT across ≥15 real trading days for live promotion  
**Ensemble bar:** ≥85% DT across ≥4 test dates → eligible for 2-of-3 ensemble  

---

## Live Model

| Model | Status | DT % | N days |
|-------|--------|------|--------|
| Nemotron Super 120B (`nvidia/nemotron-3-super-120b-a12b:free`) | **PROMOTED** | **100%** | 4 |

Full Nemotron hardening history: [PROMOTION-SCORECARD.md](PROMOTION-SCORECARD.md)

---

## Challenger Models

| Model | Status | DT % | N clean DTs | Dates Covered | Notes |
|-------|--------|------|-------------|---------------|-------|
| Hermes 3 Llama 405B (`nousresearch/hermes-3-llama-3.1-405b:free`) | **ENSEMBLE-ELIGIBLE** | **100% (4 dates)** | 7/7 | 05-19 ✓, 05-07 ✓, 05-20 ✓, 06-24 ✓ | 4 dates × 100% DT; 5 RATE_LIMITED on 06-24 excluded per effective_is_dt rule |
| Qwen3 80B MoE (`qwen/qwen3-next-80b-a3b-instruct:free`) | EVALUATING | 100% (1 date) | 2/2 | 05-19 ✓, rest pending quota reset | Daily RPD exhausted 2026-06-24; re-run via `run_qwen_evals_tomorrow.ps1` |

*Legend: ✓ = complete, 🔄 = in progress, ⏳ = pending*

---

## Per-Date Results

### Hermes 3 Llama 405B

| Date | DT Agree | DT Total | DT % | Rate-limited | Notes |
|------|----------|----------|------|-------------|-------|
| 2026-05-19 | 2 | 2 | **100%** | 0 | ENTER+EXIT_STOP; clean run |
| 2026-05-07 | 2 | 2 | **100%** | 1 (t5 excluded) | HOLD_DEV monitoring; 1 DT missed (inter-run retries extended RPM window past 90s) |
| 2026-05-20 | 1 | 1 | **100%** | 0 | EXIT_ALL→EXIT_STOP via exit_hint P2 rule; 4 non-DT ticks skipped |
| 2026-06-24 | 2 | 2 | **100%** | 5 (t20-22, t23b, t25) | 7 DTs = HOLD_DEV bear=8; 5 quota-exhausted excluded; 2 answered = HOLD_DEV match |

### Qwen3 80B MoE

| Date | DT Agree | DT Total | DT % | Rate-limited | Notes |
|------|----------|----------|------|-------------|-------|
| 2026-05-19 | 2 | 2 | **100%** | 0 | Clean run (first call of day) |
| 2026-05-07 | — | — | — | — | Quota exhausted; pending re-run |
| 2026-05-20 | — | — | — | — | Quota exhausted; pending re-run |
| 2026-06-24 | — | — | — | — | Pending |

---

## Rate Limit Architecture (Confirmed 2026-06-24)

- OpenRouter free tier: **~1 RPM per model** (60s window)
- **Rate limits are per-model** (not per-key): Hermes and Qwen have separate buckets
- **Daily quota** (approximate): Qwen's daily RPD was exhausted after ~40+ calls (with retries burning 3× per 429)
- **Retry extension**: When a DT call retries (15s+30s), the last retry is 45s AFTER the call start, extending the effective RPM window to ~105s from first attempt. The 90s inter-run sleep was too short in this case.
- **Prevention**: `sleep_s = 62s` in model config; `--dt-only` skips non-DT ticks (50-70% savings); `run_cold_evals.py` uses **120s** inter-run sleep (covers 60s_window + 45s_retries + 15s_buffer)

---

## Rubric Files

| Model | File | Version | Hardening Rounds |
|-------|------|---------|-----------------|
| Nemotron | `setup/rubrics/nemotron.md` | v11.0 | 11 rounds |
| Hermes | `setup/rubrics/hermes.md` | v1.0 | 0 (cold start) |
| Qwen | `setup/rubrics/qwen.md` | v1.0 | 0 (cold start) |

---

## Next Steps

1. **Run Qwen suite** after quota reset (Qwen bucket fresh now): `& setup\scripts\run_qwen_evals_tomorrow.ps1` (05-07, 05-20, 06-24 still needed; 05-19 clean)
2. **Hermes quota re-exhausted** during 06-24 batch — run `run_hermes_evals_tomorrow.ps1` after next midnight UTC for full 06-24 DT coverage (5 gaps)
3. **Wire ensemble** (2-of-3 majority): Hermes ENSEMBLE-ELIGIBLE; wire once Qwen also clears 4 dates ≥85%
4. **Expand to 15+ dates** for graduation: `Gamma_ShadowEval` now accumulates Hermes+Qwen daily (no manual action needed)

---

*Updated: 2026-06-25 03:19 UTC — Hermes ENSEMBLE-ELIGIBLE: 7/7 DT = 100% across 4 dates; Qwen re-run pending (05-07/20/06-24 quota gaps)*
