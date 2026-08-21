# OPUS WORKER HANDOFF — the one-gate problem (filed 2026-08-20 evening)

> **J's question (verbatim intent):** "I am failing to understand why we can see a setup all day, and one gate prevents us from getting in. Review from every angle — all the gates, all the arms, all the possibilities if we would have gotten in."
>
> **This document is the work package.** It encodes what is already settled (do NOT retest it), what is genuinely open, and the exact matrices to run. Nothing in here ships to the entry path without a pre-registered A/B clearing the standing bar (OOS positive AND WF ≥ 0.70 AND sub-window stable AND anchor no-regression, per OP-11), plus a random-entry null.

---

## Part A — WHY one gate can hold the whole book out (the mechanism chain)

This is not one bug; it is four design decisions multiplying:

1. **Entry is binary.** ANY blocker vetoes (`filters.py`; CLAUDE.md: "entry is binary, not laddered"). A 9/10 with one blocker is identical to a 2/10 at the order gate.
2. **Five arms, one signal.** All arms consume `build_shared_signal` — arms are RISK profiles (sizing/stops/caps), not independent looks. Disclosed correlation r=0.846. When the signal is gated, the whole book is gated; the arms cannot rescue it.
3. **Exactly one relief valve.** The trendline-only bypass (strips blockers 5/8/9 when `trendline_rejection` fires ALONE) is the single alternative path. ~89% of bear ENTERs over 33 sessions came through it; on 2026-08-20 it was 100%.
4. **Gate 8 is a proxy, and the proxy inverts on grind-down days.** Bear filter 8 requires `VIX > 17.30 AND rising` (+ L115: 5d MA < 20d MA). It encodes "short only when fear is exploding." On an orderly low-VIX decline (08-20: VIX 15.49–16.13, ribbon+HTF BEAR 772/772 ticks, −5.7 pts) it is **unpassable by construction**. Prior art already doubted this shape: **L93** ("if a VIX gate is needed, test DECLINING direction only", quoted at `filters.py:46`) and **C5** ("VIX *character* > VIX level").

Plus a doctrine gap: **gate 8 has no revalidation clock** (J directive 2026-07-31: every armed gate needs one). Whatever survives this package, wire the clock.

---

## Part B — WHAT IS ALREADY SETTLED (do not re-litigate; cite instead)

| Question | Verdict | Where |
|---|---|---|
| Extend the 5/8/9 bypass to level_rejection/confluence? | **NULL twice.** Recent Δ +$1,616→**−$562** on roll-forward; G2+G3 FAIL | `g2-trendline-bypass-2026-08-01/20.json`, `G2-RERUN-VERDICT-2026-08-20.md` |
| Remove the bypass? | **NULL twice**, worse | same |
| Enter at score ≥9 + confluence + HTF BEAR (J's 11:00-class cohort)? | **FAIL, pre-registered**: 109 trades, −$3,864, WR 22%, fails day-majority + drop-best. *Wrinkle: held-out last-25% was +$2,327/25tr — reported, not gating* | `analysis/arm-ladder/LADDER-SUBSET-VERDICT-2026-07-28.md` |
| Let risky arms enter at rung 7/8 (live shadow, running daily since 08-07)? | **8 of 9 days NEGATIVE.** Deduped cumulative added P&L: rung-7 ≈ **−$3,380**, rung-8 ≈ **−$3,235**. On 2026-08-20 itself: rung-7 +36 trades = **−$345**, rung-8 +29 = −$320 | `analysis/arm-ladder/ladder-rung-shadow-ledger.jsonl` |

**Read that last row again.** On the exact day J is asking about, the more-permissive engine *loses* $345. The engine's +$811 was not despite the gates; the recent evidence says it was partly because of them.

⚠️ **Ledger defect found while reading it:** the shadow ledger has duplicate tallies (2026-08-07 appears ~8×, 08-13 twice). The raw cumulative (−$21,735) is inflated ~6×. Deduped numbers above are computed on unique (date, arm) keeping the latest tally. Fix is T6.

---

## Part C — WHAT IS GENUINELY UNTESTED (the package)

The prior studies relaxed by **score** (any blocker) or by **bypass scope** (which triggers get relief). Nobody has ever stratified by **WHICH blocker was missing**. "Score 9 missing the VIX proxy" and "score 9 missing volume confirmation" are pooled in every existing result. J's 48-tick cohort (score 9, blockers == [8], 10:01→15:38) is precisely the un-isolated cell.

### T0 — Data authority (PREREQUISITE, blocks T5)
The engine tick feed and `spy_5m_2026-05-19_2026-08-20.csv` disagree on 08-20 session OHLC (open 768.74 vs 765.95; low 763.04 vs 762.04). Per the data-provenance doctrine (spy_5m caches are a feed patchwork — check the source seam first): identify each source's provenance, scan the full window for divergence days, declare ONE authoritative series for counterfactual replays, and document it. Any sim built on the wrong feed is garbage.

### T1 — Gate-8 provenance dossier
`git log -S "VIX_BEAR_THRESHOLD"` dead-ends in a squashed snapshot (d0c8ac06, 2026-06-15). Archaeology required: CHANGELOG.md, `markdown/doctrine/`, LESSONS-LEARNED L40/44/45/73/93/115, original scorecards. Deliver: when 17.30-AND-rising was armed, from what n, what window, what regime — and whether that evidence predates the current regime. If provenance is thin, that reframes every other task; if solid, we learn the gate is deliberate and today was its known cost.

### T2 — Blocker-stratified re-cut (CHEAP — do this first, it re-uses existing replay data)
Re-cut `analysis/arm-ladder/LADDER-FULLHIST-2026-07-27.json` per-trade detail, stratified by **which blocker(s) the entry was missing**:

| Stratum | Question |
|---|---|
| missing = [8] only | Is the VIX-proxy miss different from the rest? **This is J's cell.** |
| missing = [9] only | volume-confirmation miss |
| missing = [10] only | trigger-count miss |
| missing = [7] only | volume-divergence miss |
| ≥2 missing | control for the pooled result |

Columns per stratum: n, total, WR, per-trade, drop-best, day-majority, recent-25 vs full, trend-day vs chop-day split (day-range metric), HTF-agreement split. **Kill criterion, pre-registered before running:** if missing-[8] does not beat the pooled cohort by a stated margin, the "gate 8 is uniquely miscalibrated" hypothesis dies and T3 shrinks to provenance-only.

### T3 — Matrix M1: gate-8 isolation A/B (only if T2 keeps the hypothesis alive)
`vix_soft_mode` **already exists** as a parameter in `evaluate_bearish_setup` — arm (b) is a flag flip, not new code.

| Arm | Gate-8 treatment |
|---|---|
| CONTROL | as-is (hard: >17.30 AND rising, + L115) |
| SOFT | `vix_soft_mode=True` (−1 demerit, existing flag) |
| HTF-CONDITIONED | hard, EXCEPT waived when ribbon==BEAR AND htf_15m==BEAR at the tick |
| ALIGN-CONDITIONED | waived when alignment_score ≤ −3 |
| L93 | replace level+rising with the declining-direction test L93 recommended |
| LADDER-16 / LADDER-15 | threshold 17.30→16.00/15.00, keep "rising" |

All arms keep filters 5/9/10 fully enforced — this isolates 8, which no prior study did. Population 2025-01-02→2026-08-20, real-OPRA walks only, synthetic disclosed+excluded. Gates: the standing bar + random-entry null (same per-day trade counts, random timestamps) + recent-25 primary per the recency directive. Report every cell.

### T4 — Matrix M2: bypass third cell
G2 tested `trendline_only` vs `all_level_tied` vs `none`. The untested value: **`trendline_present`** — relief fires when trendline_rejection fired *at all*, alone or corroborated. This is the "corroboration should never block" fix (12:51–12:55 scar: two triggers → HOLD; one trigger → ENTER). One new enum value on the existing flag; anchor-no-regression is the load-bearing gate since this widens the only live entry path.

### T5 — Exit-survival counterfactual (blocked on T0)
Take the blocker-[8]-only cohort (48 ticks on 08-20; extract the full cohort across all sessions in `core-decisions.jsonl`), simulate entry at each tick, and push every position through **`exit_manager` replay at live scope** (profit-lock scope memory: sim-lock pre-TP1 vs live post-TP1 — use live scope or the result is fiction). The question is NOT "would 11:11 have been ITM by EOD" — it is "would our actual chart-stop/chandelier exits have survived the 90-minute chop." Report MAE/MFE per entry-hour bucket.

### T6 — Ladder-ledger hygiene + reconciliation
Fix the duplicate-tally bug (idempotency key on date+arm+rung; C7 class). Reconcile `binary_day_pnl` (530.4 for risky-3 on 08-20) against the fills-ledger FIFO (+370 gross) — different accounting scopes must be named or the shadow can't be trusted. Then wire a **revalidation clock** on gate 8 (and on whatever T3 ships) per the standing directive.

---

## Part D — Rules for the worker

- **Order:** T0 ∥ T1 ∥ T2 first (T2 is hours, not days). T3 only if T2's kill criterion passes. T4 independent. T5 after T0. T6 anytime.
- **Pre-register before running** T2's margin, T3's arms, T4's cell — freeze at `analysis/recommendations/prereg-*.json` BEFORE the first run, per the G2 pattern.
- After-hours only; backtest venv (reaper-exempt); never during 09:30–15:55 ET.
- **Do not** retest the settled cells in Part B. **Do not** touch the bull side. **Do not** ship anything from n=1 day. Trendline anchors doctrine unaffected (all-wick XOR all-body).
- Honest accounting: today's +$811 with the primary path gated for 6.5h is luck-adjacent; equally, the ladder shadow's −$345 today is n=1 too. Both are motivating observations, neither is evidence. The matrices are the evidence.

## The one-line answers to J

- **Why can one gate hold us out?** Binary entry × one shared signal × one relief valve × a proxy gate that inverts on calm downtrends. Single point of failure by construction.
- **What if we'd gotten in?** Every measured version of "get in more" — extend the bypass, remove it, enter at rung 7/8, enter on score-9+confluence — **loses money on recent data**. The one version never measured is *score 9 missing exactly the VIX gate with everything else clean*. That's T2/T3, and it's cheap to answer properly.
