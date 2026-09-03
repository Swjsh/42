# ZERO-FOR-TWELVE-POSTMORTEM — status check, 2026-09-03

Queue item: `automation/overnight/queue.md` line 192-336 (`### ZERO-FOR-TWELVE-POSTMORTEM (HIGH, filed 2026-07-25 with the disarm)`), `status:CLOSED (2026-08-02)`.

## Verdict

**CLOSED-ATTRIBUTED.** The 0-for-12 is fully attributed to (a) the entry-bar-convention audit ruling entry+1 as live-faithful and NOT the cause, plus (b) both setups deriving `side` from the identical `session_vwap_asof` classifier, which collapses the "12 independent trials at p<1%" framing to 4 distinct (day,side) buckets live and a 94.1%-overlapping OOS population historically — ordinary post-hoc selection/small-effective-n, not a validation-pipeline falsification. No unexplained residual remains open.

## 1. Entry-bar convention (prime suspect at filing) — RULED, PARTIALLY EXONERATING

- Ruling: `markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md`, dated **2026-07-25**. Entry+1 (exit-check starts the tick AFTER entry) is live-faithful — matches `heartbeat_core.py:975-987`, which manages exits BEFORE evaluating a new entry.
- Pinned by `backtest/tests/test_exit_manager_walk_entry_bar_convention.py`, docstring: "a position placed on tick N is NOT exit-checked until tick N+1... So the entry bar's own quote must never resolve the position." Explained 91.1% of a $39.71/tr parity gap on the RIDE_THE_RIBBON family specifically.
- **Does not apply to the two disarmed setups.** Code-read (queue progress note, 2026-07-25 ~20:30-21:05 ET): both `vwap_continuation` and `vix_regime_dayside` call `lib.simulator_real.simulate_trade_real` directly (the same already-correct entry+1 convention) and derive triggers from `session_vwap_asof` (pure OHLCV), with zero references to the curated/memory-merged `key-levels.json` feed that caused the RIDE_THE_RIBBON gap. This fully closed off the entry-bar/batch-vs-live hypothesis for these two setups.

## 2. Setup states + fills since 07-25

- `automation/state/params.json#extra_setup_exec_armed`: `vwap_continuation: false`, `vix_regime_dayside: false` — both still disarmed (confirmed by direct read today).
- `analysis/trades-enriched.jsonl` (404 rows, spans through 2026-09-02): `vwap_continuation` last fill 2026-07-22; `vix_regime_dayside` last fill 2026-07-21. **Zero fills of either setup since the 07-25 disarm** — the file has fills through 09-02, so this isn't a staleness artifact.
- `vwap-family-killcheck-prereg-2026-08-18.json` (a related-but-separate measurement, not this queue item): **PARKED 2026-09-03 04:31 ET** — `status: RETIRED_UNRUNNABLE_AS_FROZEN`. Its forward clock needed 20 sessions / n≥25 forward positions from `vwap_continuation`, which has taken zero fills since disarm; parked as an unresolvable measurement, not a verdict on the underlying hypothesis. `reopen_condition`: re-arm `vwap_continuation`.

## 3. Adjudications + lessons filed

- 2026-07-25 (commit `9ad0a907`): day-clustered the live 12 CSV rows → 4 distinct calendar days / 4 distinct (day,side) buckets (TP1+runner leg splits + both setups firing PUT off the identical VWAP classifier on 07-21). Reframes "0-for-12 p<1%" to "0-for-4 correlated day-outcomes, ~1.7-4.1%." → **L258** (`markdown/doctrine/LESSONS-LEARNED.md:5547`, anchor-matcher strike+side-only false-positive) and **L259** (adjacent, since-arm-fills-are-not-independent-trials).
- 2026-08-02: re-ran each setup's own detector over the 2026 OOS window → `vix_regime_dayside`'s 34 signals are 94.1% (32/34) the same (date,side) as `vwap_continuation`'s 61 signals, matching the params.json arm-time caveat ("L174 NOT INDEPENDENT... 100% same-side subset") that was never quantified until then. Closes the historical-OOS half. → **L272** (`markdown/doctrine/LESSONS-LEARNED.md:5717`, two "independent" setups' OOS populations can be a near-total same-day/same-side overlap).
- Artifacts: `backtest/tools/zero_for_twelve_oos_day_cluster_2026_08_02.py`, `analysis/recommendations/zero-for-twelve-oos-day-cluster-2026-08-02.json`, guard `backtest/tests/test_zero_for_twelve_oos_day_cluster.py` (3/3 per queue note).
- No open thread found in `analysis/deep-research/` or `STATUS.md` Known-broken referencing this item — consistent with the queue's own `status:CLOSED`.

## 4. What remains open

Nothing unexplained on the ZERO-FOR-TWELVE-POSTMORTEM question itself. Both named suspects were run to ground: entry-bar convention ruled irrelevant to these two setups; the "p<1% pipeline falsification" framing was itself the artifact (correlated/overlapping trials, not independent ones). The only adjacent open thread is the VWAP kill-check prereg, which is parked (not failed) purely because the producer stays disarmed — reopening it requires a re-arm decision, which is outside this item's scope.

## Unverified / not independently re-run this session

- Did not re-execute `zero_for_twelve_oos_day_cluster_2026_08_02.py` or its guard test — relied on the queue's own recorded results (3/3 PASS) and the JSON artifact's presence.
- Did not re-run `test_exit_manager_walk_entry_bar_convention.py` — relied on reading its docstring/ruling reference; task scope was report-only, no test runs performed.
