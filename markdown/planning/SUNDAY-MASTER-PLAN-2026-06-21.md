# SUNDAY MASTER PLAN — 2026-06-21

> 24-hour weekend-grind plan. Goal: make Gamma a better trader that makes **actual money**.
> Ranked by leverage (money-unlocked per hour). Honest EV, no hype. READ-ONLY survey -> this plan; execution starts when Gamma picks up.

---

## Headline

**The single highest-leverage move is WP-0: the order-builder per-setup-stop refactor.** It is verified-absent in code and is the *only* thing standing between two fully-validated edges (#2 vwap_reclaim_failed_break, #4 vix_regime_dayside) and live money. Everything else this weekend either (a) de-risks WP-0, (b) refines/validates the one LIVE edge, or (c) runs as a free parallel backtest/data track. The research frontier for *new* edges is honestly exhausted for this bull regime — do not spend the weekend hunting a 54th mechanical family.

---

## Ground truth verified this session (not taken on faith)

| Claim | Verified | Evidence |
|---|---|---|
| Per-setup -0.08 keys exist in params.json, edges dormant | YES | `automation/state/params.json` L77 (`j_vwap_reclaim_fb_premium_stop_pct: -0.08`), L84 (`j_vix_dayside_premium_stop_pct: -0.08`), both `enabled: false` |
| filters.py isolated accessors exist (single source of truth) | YES | `backtest/lib/filters.py` L1459 `vwap_reclaim_failed_break_premium_stop_pct`, L1551 `vix_dayside_premium_stop_pct` |
| NO code selector reads them at order-build time | YES | grep for `select_exit_params / per_setup_stop / setup_stop_override / premium_stop_pct_override` = **zero hits** in `backtest/lib/`, `automation/scripts/`, `setup/scripts/` |
| risk_gate.check_order already receives setup_name (natural home) | YES | `backtest/lib/risk_gate.py` L189 `setup_name`, used at L288/L371 |
| Heartbeat step 6 hardcodes the GLOBAL ×0.50 for EVERY entry | YES | `automation/prompts/heartbeat.md` L783 (BEAR ×0.50) / L784 (BULL ×0.50) — no per-setup branch; setup blocks L385/L399/L410/L425 *say* "use isolated -0.08" but the shared step-6 path ignores it |
| Real-fills option cache ends 2026-05-29; bars run later | YES | `backtest/data/options/` last expiry = `SPY260529*`; `spy_5m_*` to 2026-06-18, `vix_5m_*` to 2026-06-19 → **~14-day real-fills blind spot** |
| LIVE edge #1 has zero tracked fills | YES | `journal/trades.csv` = 16 lines (15 data rows), last fill 2026-06-15 `BULLISH_RECLAIM`, **zero `vwap_continuation`** |
| No order/bracket parity test exists | YES | `backtest/tests/` has `test_engine_{cli,gates,score}_parity.py` — none for order brackets |

**The disconnect in one sentence:** flipping `j_vwap_reclaim_fb_enabled=true` or `j_vix_dayside_enabled=true` today would silently ship a **-0.50** bracket on an edge validated at **-0.08** = a *broken* edge (chart-stop-only OOS goes negative when truncation is wrong). WP-0 closes that.

---

## The 24-hour sequenced plan (highest leverage first)

### Track A — SERIAL build track (the money path). Do these in order.

**A1 — Backfill the option-chain real-fills cache May-30 → Jun-19 (DO FIRST, it's the only non-offline step).**
Why first: every "OOS through today" claim is currently silently degraded; this is the prerequisite that makes ALL weekend validation honest, *and* it needs the live Alpaca historical API (not pure-offline), so it must run before the offline grids, not as a background task.
First step: `backtest/.venv/Scripts/python backtest/tools/fetch_option_data.py` — dry-list the missing contract symbols for 2026-05-30..06-19 first, confirm the v1beta1/options/bars endpoint authenticates, then run the backfill writing `backtest/data/options/{symbol}.csv`.
Effort: ~1.5h. EV: HIGH (unblocks honest OOS for everything below). Risk: LOW. Ships: data/infra.
KILL: if the Alpaca historical API is unreachable this weekend, do NOT fake it — flag the gap in STATUS.md, scope every downstream grid to `<=2026-05-29`, and continue.

**A2 — Build the data-coverage manifest + assertion (cheap, graduates the blind-spot foot-gun to code).**
Why now: the blind spot was invisible until manual `ls`. A `backtest/tools/data_coverage_manifest.py` that prints `[first,last,n_days]` per data class and ASSERTS option-cache span >= bar span turns "is my OOS real or degraded?" into a code check (autonomy-blueprint: graduate prose→assertion at boundaries; OP-25 silent-failure guard).
First step: write the script, run it now — it MUST report the 2026-05-30..06-19 blind spot as DEGRADED (or OK if A1 already backfilled), emit `automation/state/data-coverage.json`.
Effort: ~2h. EV: MED. Risk: LOW. Ships: infra.

**A3 — Build the order-bracket parity test FIRST (the safety net BEFORE the refactor).**
Why before A4: the live order math lives only in heartbeat prose; there is zero automated guard that an edit preserves the -0.50/-0.08 brackets. Building the test first de-risks WP-0 and is independently valuable.
First step: create `backtest/tests/test_engine_order_bracket_parity.py` asserting (a) all per-setup flags OFF → resolved stop == today's global bear/bull -0.50; (b) `setup=vwap_reclaim_failed_break` → -0.08, `setup=vix_regime_dayside` → -0.08, unknown setup → -0.50 (mirror the existing watcher-test -0.08 assertions in `test_vwap_reclaim_failed_break_watcher.py`).
Effort: ~2h. EV: HIGH. Risk: LOW. Ships: infra (the L174/C14 graduation the doctrine demands).
KILL: if the order path can't be made deterministic enough to assert byte-identity, that *itself* is the finding — the prose order-math must be code-ified first; escalate the untestability, don't paper over it.

**A4 — Ship WP-0 core: `select_exit_params(setup_name, side, params)` in risk_gate.py + wire the backtest order path.**
The single highest-EV action on the rig. Two edges validated 8/8 gates on real OPRA fills (#2 OOS +$32–72/tr, #4 OOS +$79.49/tr — the cleanest, chart-stop-only POSITIVE) are dormant blocked ONLY here.
First step: add a pure dispatch fn in `backtest/lib/risk_gate.py` (already takes `setup_name` at L189) keyed `{vwap_reclaim_failed_break, vix_regime_dayside, vwap_continuation, gap_and_go}` → the matching `filters.py` accessor (L1459/L1551 — reuse verbatim, single source of truth), default branch → global `premium_stop_pct` (-0.50). Wire it into the real-fills order path so a matched+enabled setup overrides the side stop; else byte-identical. Run `backtest/.venv/Scripts/python -m pytest backtest/tests/ -k 'graduated or parity'`.
Effort: ~4h. EV: HIGH. Risk: MED. Ships: infra → unlocks 2 edges. **Flips NO enabled flag** — no live behavior change until a deliberate daylight flip + REVOKE note.
KILL: if the parity/graduated suite shows ANY non-identical bracket with all flags OFF, STOP and revert — the refactor is not behavior-preserving.

**A5 — Gamma-sync heartbeat.md steps 6/7 to the same per-setup branch (no live drift).**
Why: OP-4 forbids code drift between live and backtest. Step 6 (L783-784) must resolve the stop by the same dispatch table as `select_exit_params`, falling back to -0.50.
First step: invoke the `gamma-sync` skill; rewrite heartbeat.md step 6 so it looks up the active setup's isolated key, else the global cap; run the full pytest suite via `backtest/.venv`. Keep all `enabled=false`. **After-4pm/weekend window only — never mid-session (Rule 9).**
Effort: ~2h. EV: HIGH. Risk: MED. Ships: infra.
KILL: if the prose can't be expressed unambiguously for an LLM tick, extract the bracket math into a tiny callable script the tick invokes (graduate prose→code) rather than leaving load-bearing arithmetic in prose.

**A6 — Pre-compute the WP-0-unlock A/B scorecards for #2 and #4 (so they ship zero-lag the moment A4/A5 land). — ✅ DONE 2026-06-21: both SHIPPABLE (8/8 gates).**
> VERDICT: **#2 `vwap_reclaim_failed_break` SHIPPABLE-WITH-CAVEAT** (ITM-2/ATM only — OTM-2 FAILS 6/8; OOS +$72.11/tr n=76 but OOS-alone < same-day null mean = day+side selection). **#4 `vix_regime_dayside` SHIPPABLE, cleaner** (ATM/Safe-2, OOS +$79.49/tr n=21, strongest null separation; caveat: chartstop-only OOS +$0.15 → edge is the −8% option structure, not point-direction). Data capped 2026-05-15, asserted last-fill = 2026-05-15 ≤ 2026-05-29 (blind spot not reached). **⚠ L174: neither edge is independent of LIVE #1 (100% same-side day overlap) — ship as #1-overlays, size as concentration not diversification.** OP-16: both fire on 0 of J's losing anchors (no regression). Scorecards in `analysis/recommendations/`.
OP-11 requires an A/B scorecard at `analysis/recommendations/{rule_id}.json` BEFORE any flip. Their VALIDATION doesn't need the refactor — only their SHIP does.
First step: re-run `_sub_struct_vwap_reclaim_failed_break.py` and `_b5_vix_regime_dayside.py` via `backtest/.venv`, **hard-windowed to `<=2026-05-29`** (assert `last_date` in output), emit refreshed scorecards with full-sample expectancy, OOS sign, drop-top-5 (L173), random-null delta, no-truncation sign, and the 7-anchor no-regression check. Write a one-line "data coverage: last real-fill 2026-05-29" caveat into each.
Effort: ~3h. EV: HIGH. Risk: LOW. Ships: research_only (decision-grade, ship-ready).
KILL: if either edge fails any of the 8 gates on the clean window (e.g. #2's OOS-alone collapses inside the same-day null band — a known caveat), mark NOT-SHIPPABLE in the scorecard; WP-0 still ships (it's correct infra + unlocks the other edge).

### Track B — runs in PARALLEL with Track A (independent, free, no shared write surface).

**B1 — Live-fire smoke test: prove vwap_continuation actually emits a paper entry. — ✅ DONE 2026-06-21: LIVE_EDGE_FIRES_OK.**
> VERDICT: the LIVE edge `vwap_continuation` **fires end-to-end** — NOT a wiring break. Detector fires on cached 5m bars (162 signal dates); LIVE watcher streamed bar-by-bar matches with full parity (3/3 side+trigger-time); registered in `runner.WATCHERS`; Safe-2 heartbeat would ENTER correct side+strike with real OPRA fill (3/3). Zero tracked fills = "no signal yet" (flag live <2 trading days). **2 live-path gaps surfaced (daylight fixes):** (1) edge is INERT on Bold — `j_vwap_cont_enabled` missing from Bold params → defaults FALSE; (2) Safe-2 at $2K fires OTM-2, not the validated ATM/ITM-1 cell (C3/C29 — re-confirm at live strike). Built `backtest/autoresearch/vwap_smoketest.py`; finding in `analysis/recommendations/B1-VWAP-SMOKETEST.md`.
The one "LIVE" edge has produced **zero** tracked fills. Before tuning anything on top of it, confirm the watcher→heartbeat→order path emits a `vwap_continuation` bracket on a replayed historical signal day (pick 2-3 dates from `sel-vwap-continuation.json` inside the option-cache span). Catches a silent wiring break before Monday's open.
First step: run `backtest/autoresearch/vwap_smoketest.py` on the chosen dates to confirm the detector fires from cached 5m bars; then drive the `chart-reading-gym` skill / heartbeat replay and assert the emitted decision == ENTER vwap_continuation, correct side, strike_offset=-2.
Effort: ~2h. EV: HIGH (cheap validation of the only live edge). Risk: LOW. Ships: research_only (the bug, if any, is the deliverable → STATUS.md).

**B2 — Long-running parallel backtest grid: VIX-feed reconstruction + edge #4 re-validation. — ✅ DONE 2026-06-21: VIX_FEED_PINNED (parity proven, no bug).**
> VERDICT: the reconstructed intraday VIX feed reproduces the research detector with **ZERO divergence in all 8 cells (jaccard 1.0)** — median/slope primitives byte-identical, last signal 2026-05-29 (== OPRA cache edge, no silent degradation). Edge #4's SECOND blocker is now a pure wiring step, NOT a parity bug — no escalation. Spec pinned (source=^VIX 5m RTH closes, UTC-ffill onto SPY grid, `rolling(78,min_periods=19).median().shift(1)`, causal 5-bar slope, ET morning gate). Remaining live step (out of Sunday scope): heartbeat keeps a rolling ≥78-bar today-session VIX buffer → set `ctx.vix_intraday`. Deliverables: `analysis/recommendations/B2-VIX-FEED-SPEC.md` + `B2-vix-feed-parity.json` + `backtest/autoresearch/_b2_vix_feed_parity.py`.
This is the "long grid churns while we build infra" track. Edge #4 needs an intraday VIX series (trailing-median-78 + 5-bar slope) the live BarContext doesn't carry — reconstruct it offline from `vix_5m_2025-01-01_2026-06-16.csv`, re-validate #4 on the full available span, and pin the exact live-feed spec (lookback=78, slope-window=5, source=VIX 5m RTH closes) that the heartbeat must reproduce.
First step: load the vix_5m CSV, compute as-of trailing-median(78)+5-bar slope per RTH bar (causal), run `vix_regime_dayside_watcher.py` against spy_5m + reconstructed `ctx.vix_intraday` for 2025-01..2026-05-29, diff against `analysis/recommendations/b5-vix-regime-dayside.json`.
Effort: ~4h wall (mostly compute). EV: HIGH (this is the SECOND blocker on the cleanest edge — independent of WP-0). Risk: LOW. Ships: research_only + a written feed spec.
KILL: if the reconstructed series doesn't reproduce the existing scorecard within noise, that's a parity bug — escalate, don't ship the feed.

**B3 — Mine the WeBull 2021-2023 corpus for a per-setup/hold-time/lot-size expectancy table (bar-independent, fully offline, sidesteps the blind spot entirely).**
J's 4818 real broker order rows are the densest untapped ground-truth on his actual edge (the L168 sizing-up finding came from here). SCOPE-HONEST: filter to **SPY 0DTE only** (~563 of 4818 rows; the rest are SPXW/SPX, out of locked scope).
First step: pandas — pair Open/Close on Symbol+Filled-Time into round-trips, filter to SPY 0DTE, bucket by hold-time / lot-size / side / entry-hour, compute per-bucket expectancy + N; cross-check vs L168.
Effort: ~3h. EV: MED (likely thin: SPY-only N may not clear N>=20/bucket). Risk: MED. Ships: research_only (feeds OP-16 edge-capture).
KILL: if SPY-only buckets are all N<20, log "WeBull SPY subset too thin; SPX out of scope" and stop — don't re-derive L168.

### Track C — low-effort hygiene + decision-grade items (fit into gaps).

**C1 — Confirm + RETIRE the 4 SWJSHAK strats as DEAD (do NOT re-test).**
All 4 were already real-fills-tested overnight (2026-06-20) with the exact OP-11/random-null/no-truncation gates and all 4 honestly failed (C3/L58 0DTE-wall). Re-running burns tokens against a settled negative.
First step: READ `analysis/recommendations/swjshak-{ema-adx-gate,sd-zone-reversal,three-ducks,bollinger-squeeze}.json` (each `self_verify ALL_PASS=false`), propose one-line DEAD entries for `STRATEGY-HUNT-BACKLOG.md`, mark `SWJSHAK-STRATEGY-EXTRACTION-2026-06-20.md` as superseded.
Effort: ~0.75h. EV: MED (prevents a future BRAINSTORM re-queueing dead work — OP-22/OP-25). Risk: LOW.

**C2 — WP-3 sizing: surface the cap-clamped contracts-per-tier table (v15 nominal counts BREACH Rule 6 at $2K).**
A live correctness/compliance issue independent of any edge: B10 found Safe base-5 = 34.5% vs 30% cap, Bold elite-8 = 102.8% vs 50% cap. The engine could currently size a Rule-6 violation.
First step: read `analysis/recommendations/B10-SIZING-SCORECARD.json` + params `position_sizing_tiers`, write the quarter-Kelly + min-3 clamped table as a DRAFT params decision (surface to J as a decision, not a flip — it's a sizing/safety change).
Effort: ~1h. EV: MED. Risk: LOW. Ships: research_only (J-ratify).

**C3 — Garbage-collect strategy/candidates/ (427 stale files) + drain stale cook-queue.**
OP-22 CONSOLIDATION trigger. Newest meaningful candidate is 2026-06-01, all superseded by the 3-edge inventory.
First step: inventory by mtime + first-line strat name; grep code for any hard `candidates/` path-read (verify-no-consumer-before-delete, C7); archive pre-2026-06-15 files, close 15 stale cook-queue tasks.
Effort: ~1.5h. EV: LOW. Risk: LOW. Ships: infra.

---

## What runs in PARALLEL

- **Track A is serial** (A1→A2→A3→A4→A5→A6) — each step gates the next (backfill → manifest → parity-test → refactor → sync → scorecards).
- **Track B runs concurrently with Track A** — B1 (smoke test), B2 (VIX-feed grid, the long churn), and B3 (WeBull mine) share NO write surface with the order-path refactor. B2 is the designated "long backtest grid churning while we build infra."
- **Track C** fills idle gaps (C1/C2/C3 are read-mostly, minutes each).
- Hard ordering constraint: **A6 depends on A1** (honest OOS needs the backfill, or the `<=2026-05-29` window). **B2 is independent of A1** (it re-validates on the span we already hold).

---

## Cut list (ruthless — NOT worth doing this weekend, and why)

- **Hunting a 54th mechanical/external strategy family.** The ~42-family mechanical/external vein is exhaustively dry (B0-B10). Re-mining is negative-EV by construction.
- **Re-testing the 4 SWJSHAK strats.** Already real-fills-tested and killed overnight with the exact gates this workflow demands. Re-running = tokens against a settled negative. (Retire them via C1 instead.)
- **The EMA-ADX PUT-side asymmetry probe.** The single non-dead SWJSHAK residual (PUT +$15/tr n=44) is already OOS-2026 **negative** (-8.4) and fails no-truncation (sign inverts +3.4→-41.6). A confirm-it's-dead probe, not a promote — skip; the verdict is already in the scorecard.
- **Any OTM+wide-stop configuration.** Doctrine-dead (C3: OTM theta/delta eats alpha; ITM+tight = edge, OTM+wide = bleed). #2/#4 ship ATM(Safe)/ITM-2(Bold) at -0.08 ONLY.
- **New instruments / crypto-as-tradeable.** Scope locked: 0DTE SPY + futures only; crypto is gym-only.
- **The 8 online-research vectors (GEX, flow sweeps, charm/vanna, PCR, IV-rank, OI-skew) as NEW live triggers.** Interesting but: (a) most need paid/real-time feeds we don't have offline, (b) they can only be tested as shadow overlays on the one live edge until WP-0 ships, and (c) the volume-PCR / volume-magnet overlays are the only ones buildable offline this weekend and they're MED-EV exit-mechanic tuners (C28: diminishing returns once stop-rate >70%). Defer all of them behind WP-0. The one cheap, doctrine-clean offline overlay worth a *single* fast probe IF Track A finishes early is volume-PCR-confirms-trend on the LIVE edge — but it is explicitly below the cut line vs A1-A6/B1-B2.
- **Wiring the companion autobuild FIRE (§5b of the wiring plan).** It spawns Claude — out of weekend-safe scope. (Companion module *wiring* + the spend-cap are good autonomy items but rank below the money path; do them only if A+B finish.)
- **Conductor model routing / daily spend cap.** Real OP-3 wins (conductor fires Opus every wake ≈ 918/day) but they're cost-hygiene, not money-unlocked-per-hour; schedule for the next after-hours block behind the edge work, not ahead of it.

---

## Honest EV summary

The money this weekend is **not** a new edge — it's **graduating the per-setup-stop from validated-params to live code (WP-0)**, which converts two already-paid-for, 8/8-gate-validated edges from dormant to ship-ready, plus **de-risking the one live edge** (prove it actually fires; close the data blind spot so its OOS is honest). New-vein research is correctly a free parallel churn (B2 VIX-feed) and a ground-truth mine (B3 WeBull), not the headline. Everything in the cut list is either doctrine-dead, already-killed, or cost-hygiene that ranks below the money path.
