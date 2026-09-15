# HANDOFF 2026-09-15 — Trading follow-ups from the 09-15 audit (fresh session)

> Paste the **Prompt** section into a fresh Claude Code session in `C:\Users\jackw\Desktop\42`.
> Orchestrator = judgment; research/build → Sonnet workers (`model: "sonnet"`), max 2 at a time.
> Links: [[analysis/eod-deep/eod-deep-2026-09-15|09-15 audit]] ·
> [[analysis/deep-research/2026-09-15-ladder-rung1-mfe-study|ladder rung-1 study]] ·
> [[markdown/0dte/EXIT-SHAPE-TRUTH|EXIT-SHAPE-TRUTH]]

---

## Prompt

You are taking over the **trading follow-ups** from the 2026-09-15 full-day audit for Project
Gamma (paper 0DTE SPY options). Read `CLAUDE.md` first. Doctrine that binds everything below:
**config freeze until 2026-10-30.** Trading-path edits are blocked. Pre-registered kill-type risk
reductions may ship at the **2026-09-29 checkpoint**, each with prereg, guard, RED-proof and revert
line, applied with `GAMMA_FREEZE_OVERRIDE`. Risk expansions wait for 10-30. Rule 9: nothing
changes during RTH. Live money needs J. Push only outside 09:30–15:55 ET. Commit with
`python setup/scripts/commit_scoped.py "<message>" <paths...>`. Timestamps via `setup/scripts/et_clock.py`.

### What 09-15 showed (verified, sources in the audit)

- One ELITE signal at 10:38 ET, `BEARISH_REJECTION_RIDE_THE_RIBBON` @757.315 (trigger 757.44). Five arms entered.
  Book −$530.05 (net): bold-2 +74.75; safe-2 −105.15; safe-3 −114.15; risky-1 −195.25; risky-3 −190.25.
  No rule breaks. Engine 386/386 ticks.
- safe-2 peaked +45.4% (1.57 @10:52). Ladder rung 1 needs +50%, so its stop stayed at 0.54 and it exited on
  structure_stop. bold-2 reached +57%, rung 1 locked 0.611, and it exited +32%.
- Day was tagged `range-chop`. Regime context is logged-only, never gating.
- Premarket bias was the degraded deterministic fallback because the Claude CLI is logged out
  (refresh token expired 09-14 12:25 ET). J must run `claude` → `/login`.

### Work, in order

1. **Ladder rung-1 prereg evidence (research only).** Study n=221 (4 arms since 2026-08-10):
   91 trades never reached +50% MFE (−$8,351 on the 86 losers). Simulated first rung at +30% = +$1,424 net
   (+$4,583 on never-TP1 trades, −$3,159 on TP1 winners stopped early); +40% = +$1,267. The study's own
   artifact hunt already caught and fixed one inflated first pass. Before any prereg:
   a. Reconcile the **$460 gap**: study Σ +$1,507 vs orchestrator FIFO recount from `fills-ledger.jsonl`
      of +$1,047 over 231 round trips (all setups).
   b. Re-count by **distinct signal/day**, not arm-rows (one signal fires on up to 4 arms). Bootstrap at day level.
   c. Run the OP-11 battery: OOS split, walk-forward ≥0.70, sub-window stability, anchor no-regression.
      Include the cost side explicitly (TP1 winners cut early).
   d. Only if it passes: draft a prereg for 09-29. Is a lower rung a risk *reduction* that qualifies
      for the checkpoint? Decide with doctrine citations. If unclear, it waits for 10-30.
   Data/script: `analysis/deep-research/2026-09-15-ladder_study.py`, `2026-09-15-ladder_results.json`.
2. **Chop-regime shadow track.** Log, per entry, the regime tag + range position at entry vs the
   outcome, as a shadow ledger (no gate). Check first whether an existing shadow lane already
   covers it (`SHADOW.md`, `analysis/recommendations/*shadow*`) and extend it rather than fork a new one.
3. **Open audit loose ends (non-trading-path, shippable):**
   - Fleet decisions.jsonl shows 384 rows/arm vs core 386. Find the cause.
   - `Gamma_BrokerFills` had pnl-statement stale 775 min before the TV watchdog self-healed it. Find the scheduling gap.
   - STATUS.md: 7 task-output-freshness findings and full pytest suite 24 failed (05:13 ET). Triage.
   - `Gamma_FreeManager` result=1 but task Disabled. Confirm intentional or clean up the registry.
   - `fast_path_executor.py` (trading-path) still reads the dead `current-position-*.json` before its Alpaca
     re-check. Candidate cleanup for the 09-29 checkpoint only. No edit before then.
4. **Rule 8 process question:** journal rows are post-hoc backfills (`fleet_journal_bridge.py`). Decide,
   citing doctrine, whether the engine decision row is the thesis-of-record. If yes, write it down in
   `markdown/0dte/journaling-guide.md`. Don't build new machinery.

Report to J: verdict first, measured numbers, every UNVERIFIED labelled.
