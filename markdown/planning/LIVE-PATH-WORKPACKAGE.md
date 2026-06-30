# LIVE-PATH WORK-PACKAGE — daytime / J-aware deliberate ship-steps

> **Why this doc exists.** The live order/entry path is the riskiest set of files in the rig. Overnight RESEARCH batches are forbidden from editing live watchers / `params.json` / the order builder. When a research batch validates a *shippable* live-path improvement, it appends a precise BUILD-SPEC here instead of touching the live path. J (or a daytime session) executes these deliberately: build behind an isolated flag (default OFF), gym + parity green, A/B confirmed, then ONE flag flip in daylight.
>
> **Discipline (every spec below):** exact file + isolated flag (default OFF) + gamma-sync targets + parity test (flag-OFF == current behavior) + the A/B numbers + the one-flag enable. Never silently change the live engine at 3am.
>
> **Source verdicts:** `markdown/research/STRATEGY-BACKLOG.md` (Hunt queue) STATUS log + the per-angle scorecards in `analysis/recommendations/`.

---

## ⚙ ARCHITECTURE NOTE (2026-06-21 — read before executing any WP; surfaced by the WP-5 build)

**The order-path dispatch (`select_exit_params` WP-0, `select_strike_offset` WP-5) lives in `orchestrator.py`, which is the v15 MAIN-ENGINE path — and that path only ever sees `setup_name ∈ {BEARISH_REJECTION_RIDE_THE_RIBBON, BULLISH_RECLAIM_RIDE_THE_RIBBON}`.** The watcher-fleet edges we actually care about — `vwap_continuation` (#1 LIVE), `vwap_reclaim_failed_break` (#2), `vix_regime_dayside` (#4) — do NOT flow through this orchestrator call. In BACKTEST they validate via their own harnesses (`_edgehunt_vwap_continuation.py` / `_sub_struct_*` / `_b5_*`, which already apply the per-setup stop/strike directly in their A/Bs). In LIVE they run through the **heartbeat** (`automation/prompts/heartbeat.md`), the LLM tick that reads the watcher signal and builds the order.

**Consequence — A5 is the keystone, not a cosmetic sync.** WP-0/WP-5 built the **canonical, parity-tested, behavior-neutral RESOLVER** (single source of truth, flags default OFF, byte-identical proven). But flipping a per-setup flag alone does NOT change a live watcher-fleet edge's behavior — the heartbeat must call the same resolver. So **A5 (route the live heartbeat's order-build for #1/#2/#4 through `select_exit_params` + `select_strike_offset`) is a HARD PREREQUISITE for EVERY live flip** (WP-5 strike, WP-0 #2/#4 stops). The good news: all the risky validation/config is now done + tested (resolver, parity tests, A/B scorecards, dormant flags); A5 is the SINGLE deliberate live-wiring action J reviews in daylight. Recommended A5 form per the original KILL-clause: if the per-setup pick is awkward to express in heartbeat prose, have the tick invoke a tiny callable that wraps the two resolvers (graduate prose→code), so live == backtest by construction.

---

## 🚦 CONFIRM-BEFORE-CAPITAL GATE (2026-06-21 — gates EVERY flip below; honest recency wobble)

**A second gate now sits on top of A5 + the A/B scorecards: the recency verdict.** Sunday's fresh re-validation surfaced a **RECENCY YELLOW FLAG** — the 3 edges (#1 `vwap_continuation` LIVE / #2 `vwap_reclaim_failed_break` / #4 `vix_regime_dayside`) did **NOT** confirm positive on the freshest trading weeks (real OPRA fills now extend to 2026-06-18 after the A1 backfill). Full-OOS-2026 (n≈24–51) stays strongly positive; the freshest window (small-n) does not. The honest implication: **CONFIRM-BEFORE-CAPITAL** — do not scale capital on an edge until it re-confirms on accumulating recent data, and **NO live flip of an edge while that edge's recency verdict is RED.**

**Operationalized by `backtest/autoresearch/recency_check.py`** (reusable; generalizes the one-shot `_sunday_fresh_revalidation.py`). It reuses the validated detectors + real-OPRA sim byte-for-byte (no watcher/params/risk_gate/orchestrator/heartbeat edits), auto-reads the OPRA cache last-date from `automation/state/data-coverage.json`, scores the newest ~25 trading days of real fills per edge/tier AND per book, and emits a machine VERDICT:
- **CONFIRM** = recent expectancy/tr > 0 AND recent n ≥ floor (documented floor n≥10).
- **YELLOW** = positive but n < floor, OR recent ≤0 with n < floor (small-n wobble vs a positive full-OOS base).
- **RED** = recent expectancy/tr < 0 AND n ≥ floor (clear).

Writes `automation/state/recency-confirmation.json` (machine) + prepends a dated one-line wake-signal to `automation/overnight/STATUS.md`.

**The gate on the flips below:**
1. **A RED recency verdict on an edge BLOCKS its live flip.** Re-run the tracker; the edge must be ≥ YELLOW (ideally CONFIRM) on the current cache before flipping it live.
2. **Capital scaling on a flipped edge WAITS for CONFIRM** — keep an edge at minimum sizing until its recency verdict reads CONFIRM on accumulating real fills.
3. **Per-book RED is a portfolio sizing brake** (size down the combined book, do not add the edge as a fresh sleeve).

**Current verdict (run 2026-06-21, window 2026-05-14..06-18, 25 trading days, floor n≥10):** #1 ATM (Safe-2) **RED**, #1 ITM-2 (Bold) **RED**, #2 ATM **YELLOW**, #4 ATM **YELLOW**; both books **RED**. `edges_confirmed_on_recent = False`. **So per gate #1, none of the live #1 tiers may be flipped/scaled on capital right now** — WP-5's Bold ITM-2 leg in particular is RED-blocked; the Safe→ATM strike correction is also recency-RED and must re-confirm before live trust. This does not kill the edges (full-OOS base is positive); it HOLDS capital until they re-confirm. **WEEKLY CADENCE:** run `recency_check.py` as part of the weekly-review / OP-11 OUTER loop as recent fills accumulate; flip an edge only once its verdict clears RED.

---

## TRACK-B PREP STATUS (2026-06-21 — the prerequisites WP-0 needs, all now GREEN)

The three prep items that de-risk and unblock WP-0 are DONE (Sunday offline, $0, real OPRA fills ≤ 2026-05-29):

| Item | Verdict | What it unblocks | Deliverable |
|---|---|---|---|
| **A6** — #2/#4 ship A/B scorecards | **DONE — both SHIPPABLE (8/8 gates)** | the OP-11 scorecard gate that any flip requires (now filed, ship-ready) | `analysis/recommendations/` (the two canonical edge scorecards) |
| **B2** — edge #4 VIX-feed spec | **DONE — VIX_FEED_PINNED (parity proven, jaccard 1.0)** | edge #4's SECOND blocker (the intraday VIX feed) — now a pure wiring step, no parity bug | `analysis/recommendations/B2-VIX-FEED-SPEC.md` + `B2-vix-feed-parity.json` + `backtest/autoresearch/_b2_vix_feed_parity.py` |
| **B1** — live-edge smoke test | **DONE — LIVE_EDGE_FIRES_OK** (#1 fires end-to-end; zero fills = "no signal yet", NOT a break) | confirms the LIVE-edge premise holds; surfaced 2 live-path gaps (see below) | `analysis/recommendations/B1-VWAP-SMOKETEST.md` |

**A6 ship verdicts (decision-grade):**
- **Edge #2 `vwap_reclaim_failed_break`: SHIPPABLE-WITH-CAVEAT.** ITM-2 primary clears 8/8 (OOS +$72.11/tr, n=76). Caveat: OOS-alone sits below the same-day null OOS mean ($72.11 < $90.12) → OOS lift is day+side selection, not trigger precision. **OTM-2 tier FAILS 6/8 → ship ITM-2/ATM only (C29).** 2026Q2 negative (−$68.24/tr n=6).
- **Edge #4 `vix_regime_dayside`: SHIPPABLE (the cleaner of the two).** ATM/Safe-2 robust cell clears 8/8, evidence_n≥15 (OOS +$79.49/tr, n=21); strongest null separation (+$84.34/tr, beats luckiest seed). Caveat: chartstop-only OOS only +$0.15 → the edge is the −8% option STRUCTURE, not a point-direction signal (futures clear 0/8).

**B2 VIX-feed — PINNED (escalation NOT needed; no parity bug).** Reconstruction reproduces the research detector with ZERO divergence in all 8 cells (median/slope byte-identical, last signal 2026-05-29 == cache edge). The exact spec the heartbeat must reproduce is in `B2-VIX-FEED-SPEC.md` (source: CBOE ^VIX 5m RTH closes; align via UTC ffill onto SPY grid; `rolling(78,min_periods=19).median().shift(1)`; causal 5-bar slope; ET morning gate). The one remaining live step (out of Sunday scope): heartbeat retains a rolling ≥78-bar today-session VIX buffer and sets `ctx.vix_intraday` via `object.__setattr__`.

**B1 finding (2 live-path gaps surfaced, both daylight fixes):**
1. **LIVE edge #1 is INERT on Bold** — `j_vwap_cont_enabled=true` exists ONLY in the Safe `params.json`; Bold/aggressive params has no such key → defaults FALSE. Add the key to the Bold params to actually run #1 on Bold (the "ITM-2 Bold" cell is research, not wiring). Filed in STATUS Known broken.
   - **🟡 BOLD ACTIVATION — BUILT + DORMANT, FLIP KILLED (2026-06-21):** both coupled gaps are now structurally CLOSED — the `j_vwap_cont_enabled` key EXISTS in `automation/state/aggressive/params.json` (set **FALSE**) AND the A5 VWAP_CONTINUATION block is ported byte-for-byte into `automation/prompts/aggressive/heartbeat.md` (invokes `live_order_params(...,"Gamma-Risky-2",...)`; resolver verified to return the exact Bold cell `-2 / 1DTE / $67.68 / qty3`, both sides; parity 34/34 + guards green). **But the activation flip was KILLED by Safety Gate 5 (qty floor):** the validated cell is **qty 3** yet Bold's `min_contracts=5` (aggressive/params.json + the hardcoded `pre_order_gate.py` BOLD dict) → code-gate `BLOCK [MIN_CONTRACTS]` on every signal → no order. Clamping to qty 5 breaches the 50% per-trade cap (5×ITM-2-1DTE ≈ 106% of equity) AND deviates from qty-3-validated economics (this doc's line 409 already computes Bold worst-day "@ LIVE qty=5" = the unreconciled sim-qty3-vs-live-qty5 divergence). **Reverted to `false` → Bold byte-identical to today, zero Monday risk.** The remaining unblock is `J-RULING-BOLD-QTY-FLOOR` (daylight, J-aware, NOT a flag-flip): EITHER re-validate the Bold #1 cell at qty 5 with the cap modeled, OR add a per-setup min_contracts override (qty-3 floor for VWAP_CONTINUATION) in risk_gate + pre_order_gate, then re-flip. See CHANGELOG 2026-06-21 + STATUS.md.
2. **LIVE edge #1 fires OTM-2, not the validated ATM/ITM-1 cell (C3/C29)** — Safe-2 at $2K is in the OTM-2 v15 tier. Re-confirm the edge at the live strike before trusting live WR.

**⚠ CROSS-CUTTING (L174) — gates how #2/#4 get sized, NOT whether they ship:** 100% of edge-#2 days AND 100% of edge-#4 days are also LIVE-#1 entry days, SAME SIDE (81 and 80 of #1's 158). They are same-side sub-pool re-cuts of #1 (different strike/stop geometry), so shipping them alongside #1 is **concentration, not diversification** — their incremental value OVER #1 was not measured (in tension with B9's diversified-Sharpe claim). REVOKE note on both scorecards. Per the brief, WP-0 ships regardless; #2/#4 ship as #1-overlays, and their sizing must NOT assume independence.

---

## WP-0 (FOUNDATIONAL) — order-builder per-setup-stop refactor  *(gates WP-2; blocked edges #2/#4)*

**Status: CORE BUILT + VERIFIED (2026-06-21, behavior-neutral) — REMAINING: A5 live-heartbeat gamma-sync + the daylight flips.** The backtest/risk_gate half of the refactor is done and proven safe; the live-heartbeat-prose half (A5) is the deliberate daytime step.

**✅ BUILT 2026-06-21 (backtest dispatch, behavior-neutral, regression-clean):**
- `backtest/lib/risk_gate.py` — added `select_exit_params(setup_name, side, params, global_stop)`: a pure dispatch returning the setup's ISOLATED `filters.py` stop accessor ONLY when that setup's per-setup flag is ON, else `global_stop` UNCHANGED (registry `_PER_SETUP_STOP_OVERRIDES` keyed on the watcher `setup_name`s; single source of truth = the `filters.py` accessors, no literal duplication).
- `backtest/lib/orchestrator.py` (real-fills order path, ~L1700) — wired: `resolved_premium_stop = select_exit_params(setup_name, winning_side, params_overrides, side_premium_stop)`, fed to `simulate_trade_real(premium_stop_pct=resolved_premium_stop)`. **Behavior-neutral by construction:** with all per-setup flags OFF the resolver returns `side_premium_stop` verbatim → byte-identical to prior behavior.
- `backtest/tests/test_engine_order_bracket_parity.py` (NEW, the safety net): **18/18 GREEN** — flags-OFF == global stop for every setup; per-setup flag ON → −0.08; unknown setup → global.
- VERIFICATION (recovered after the build workflow failed to emit its final result; verified directly per C7): parity 18/18 ✅; `test_graduated_guards.py` (real-fills path + WP-0 wiring-regression test) **64/64 GREEN** ✅; no duplicate `filters.py` defs ✅; all 3 modules compile ✅. **No enabled flag flipped — zero live behavior change.**

**REMAINING for live ship (daytime, J-aware):**
- **A5 — gamma-sync `automation/prompts/heartbeat.md` step 6** to resolve the stop by the SAME dispatch table (fall back to the global cap). Design call flagged: if the bracket math is ambiguous to express in prose for an LLM tick, extract it into a tiny callable the tick invokes (graduate prose→code) rather than leaving load-bearing arithmetic in prose. Until A5, there is a STRUCTURAL-but-behavior-NEUTRAL gap (backtest has per-setup dispatch, heartbeat doesn't) — harmless while all flags are OFF (both resolve to the global cap); it only matters at flip time, when A5 + the enable flag go together.
- The daylight flips (one flag per edge) + their A/B scorecards (A6, already filed).

**Original spec (for reference):**

**Problem.** The live order builder applies a GLOBAL `premium_stop_pct` (-0.50 cap) to every entry. Edges #2 and #4 were validated at a per-setup `-0.08` tight stop. Until the order path reads a per-setup stop override, flipping either edge live would silently apply -0.50 (the wrong stop) → a BROKEN edge. The B8 entry-refine work (WP-2) is also gated here: any #2/#4 refinement assumes the per-setup stop is honored at the order level.

**Build-spec.**
- **File:** the live order builder (live heartbeat order path) + `backtest/lib` `run_backtest` order path — both must read the per-setup stop.
- **Isolated keys (already present in both params files from the edge#2/#4 ship work):** `j_vwap_reclaim_fb_premium_stop_pct=-0.08` (+ tp1 + chart-stop buffer), `j_vix_regime_dayside_premium_stop_pct=-0.08`. Order builder must select the per-setup key by active setup, falling back to the global cap when none matches.
- **gamma-sync targets:** live order builder ↔ `backtest/lib/filters.py` / order path (no drift — OP-4).
- **Parity test:** with all per-setup flags OFF, the order builder produces byte-identical brackets to today's global-cap behavior. Add a test asserting the live order path applies `-0.08` for setup=vwap_reclaim_failed_break (and for vix_regime_dayside) and `-0.50` otherwise.
- **A/B numbers (what unlocks on enable):**
  - Edge #2 `vwap_reclaim_failed_break`: Bold/ITM-2 OOS +$72/tr (8/8 gates); Safe-2/ATM `off+0_tp130_buf25` OOS +$32.33/tr, n=76, WR 55.3%, total +$4,120, maxDD -$368 (8/8 gates).
  - Edge #4 `vix_regime_dayside`: Safe-2/ATM OOS +$79.49/tr, OOS-drop-top5 +$25.91, chart-stop-only POSITIVE (no truncation) — cleanest dormant edge (8/8 gates).
- **One-flag enable (in daylight, per edge):** `j_vwap_reclaim_fb_enabled=true`; `j_vix_regime_dayside_enabled=true` (each also needs its VIX-feed wiring for #4). Refactor first, gym + parity green, own adversarial review, then flip.
- **PREREQ STATUS (2026-06-21):** the two non-refactor blockers are now CLEARED. (a) **A6 ship scorecards FILED** — both edges SHIPPABLE 8/8 (#2 ITM-2/ATM only, #4 ATM/Safe-2); the OP-11 scorecard gate every flip requires is satisfied. (b) **B2 VIX-feed PINNED** (edge #4's second blocker) — parity proven (jaccard 1.0), spec in `B2-VIX-FEED-SPEC.md`; the only #4 step left after WP-0 is the heartbeat `ctx.vix_intraday` buffer wiring. **So the ONLY thing left between #2/#4 and live is this WP-0 refactor + the daylight flips.**
- **⚠ L174 sizing caveat (REVOKE note):** #2 and #4 are 100%-same-side sub-pool re-cuts of LIVE #1 — concentration, not diversification. Their incremental value OVER #1 was not measured; size them as #1-overlays, NOT independent sleeves (this qualifies the B9 portfolio numbers below, which assumed partial-correlation diversification).
- **~~Also: fix 2 pytest-collection errors~~ RESOLVED 2026-06-21** — the `spy_5m_2025-01-01_2026-06-16.csv` they referenced now exists; full suite collects **864 tests, 0 errors** (verified). No action needed.

**PORTFOLIO SIZING BASIS (B9 — the combined-book measurement that justifies shipping #2/#4 alongside #1).** Measured on real OPRA fills, 342 trading days (2025-01..2026-05), `_b9_portfolio.py`:
| book (live target) | total$ | ann.Sharpe | maxDD$ | worst day$ | day-WR% | % days in mkt |
|---|---|---|---|---|---|---|
| **Safe-2 ATM** (#1+#2+#4) | +$14,608 | 4.53 | -$836 | -$423 | 57.0 | 43.6% |
| **Bold ITM-2** (#1+#2) | +$18,784 | 4.70 | -$848 | -$447 | 56.4 | 43.6% |
- The book's risk-adjusted total EXCEEDS the sum of constituents (edges only partly correlated: Safe-2 daily-P&L corr e1-e2 0.313, e1-e4 0.54, e2-e4 0.076). #2 and #4 add **real diversified Sharpe** — this is the quantitative case for WP-0.
- **Every calendar/day-type bucket is net-positive** → low concentration risk → size the combined book, not each edge in isolation. Max-DD ~-$836/-$848 is the drawdown to size around (well within each account's kill-switch: Safe-2 -$600/day daily limit caps single-day, full-history book DD is ~1.4× a single bad day).
- **Sizing implication:** Bold ITM-2 dominates Safe-2 ATM on BOTH total and Sharpe → the ITM-2/tight-stop profile is the better compounder (consistent with the edge-hunt finding ITM+tight=edge, OTM+wide=bleed). Scorecard: `analysis/recommendations/B9-PORTFOLIO-SCORECARD.md`.
- **WP-1 book caveat:** do NOT swap base #1 for touch-and-go at the BOOK level — at-book it is WORSE (Safe-2 +$11,606/Sharpe 3.93 vs +$14,608/4.53; Bold +$15,019/3.76 vs +$18,784/4.70) because touch-and-go fires fewer days. Keep base #1 as the book's #1 entry; WP-1 is a SELECTIVE refinement only, not a whole-book replacement.

---

## WP-1 — touch-and-go entry refinement for LIVE #1 `vwap_continuation` (Bold/ITM-2/call)  *(B7 → B8-confirmed GENUINE_TRIGGER)*

**Status:** OPEN, RESEARCH-VALIDATED, dormant-flip-ready. **B8 angle V upgraded this from a B7 headline to a matched-day-confirmed GENUINE entry-trigger improvement** (not a day-selection relabel). This edits the LIVE production entry trigger for the one LIVE edge → do NOT auto-flip overnight.

**What it is.** Replace the first-trigger bar of `vwap_continuation` with a 2-bar confirmation: touch VWAP in trend → next bar resumes past the touch extreme → enter. Wins twice: (a) better entry on shared days, (b) correctly abstains from a #1-only day-set that loses OOS.

**Build-spec.**
- **File:** the `vwap_continuation` watcher (live entry trigger).
- **Isolated flag:** `j_vwap_cont_touch_and_go_entry=false` (default OFF) gating the touch-VWAP + next-bar-resume confirmation.
- **gamma-sync targets:** `vwap_continuation` watcher ↔ `backtest/lib/filters.py`.
- **Parity test:** with the flag OFF the watcher produces byte-identical entries to today's `vwap_continuation`. Add an A/B test that the live path applies the refined 2-bar trigger ONLY when the flag is true.
- **A/B numbers (HONEST, matched-day — B8 corrects B7):**
  - **Matched 67 shared call-days (ITM-2/call/-8%, real OPRA fills):** touch-and-go OOS **$178.32/tr** vs #1 **$154.57/tr** = **+$23.75/tr** true entry-trigger lift.
  - Robustness: touch-and-go OOS-alone drop-top5 **$82.01** > #1 **$55.42** (MORE robust, not concentration). No-truncation PASS both (chart-only $100.99 vs $89.63). Random-null PASS both. IS sign consistent (+$10.92).
  - **HONESTY CORRECTION:** B7's headline +$58/tr OVERSTATED the entry effect — ~$34 of it was a *different day-set* (#1 trades 18 extra touch-and-go-skips days). The true same-day entry-trigger lift is **+$23.75/tr OOS**.
  - **Bonus:** the 18 #1-only days touch-and-go skips post OOS **-$10.85/tr** — touch-and-go correctly ABSTAINS from a day-set #1 loses on OOS. Both effects favor it.
- **One-flag enable (in daylight):** `j_vwap_cont_touch_and_go_entry=true`.
- **Scorecard:** `analysis/recommendations/B8-TOUCHANDGO-MATCHED-SCORECARD.md`.

---

## WP-2 — 2-bar entry refinement generalized to edges #2/#4  *(B8 angle C → DEAD, do NOT build)*

**Status:** CLOSED — DEAD. Recorded here so a future session does not re-attempt it.

**Finding.** The B7 touch-and-go 2-bar confirmation that lifts LIVE #1 does NOT generalize to the dormant edges. On edge #2 it manufactures a concentration mirage (headline +$42.60 but OOS-alone drop-top5 -$36.51, fails gate 9, drops 14 winners). On edge #4 it strictly hurts (-$44.33 OOS/tr, fails gate 9, drops 9 winners). No cell clears all 9 gates; every cell fails no-regression. Confirms C28/L173: entry refinement is a per-shape calibration, does not transfer. **No live-path work.** Scorecard: `analysis/recommendations/B8-ENTRY-REFINE-2-4-SCORECARD.md`.

> Edges #2 and #4 still ship via their NATIVE first-trigger entries once WP-0 lands — the refinement is simply not part of their spec.

---

## WP-3 — sizing / compounding spec for the live 3-edge book  *(B10 angle A → SIZING_SPEC_PRODUCED; daytime sizing DECISION for J, respecting hard caps)*

**Status:** OPEN, RESEARCH-PRODUCED. This is a SIZING DECISION for J, not a code flag — it sets how many contracts each account trades at each equity tier. respects_hard_caps=true throughout (the spec CLAMPS to Rule 6, never overrides). No live edit overnight (markets closed); J ratifies the fraction + tier table in daylight.

**The problem it solves.** v15's tier doctrine names nominal contract counts (at $2K: base-5 / elite-8). At the book's measured median premium, **those counts BREACH the per-trade risk cap (Rule 6) at $2K**:
| account | v15 nominal @ $2K | % of equity | Rule-6 cap | breach? |
|---|---|---|---|---|
| Safe-2 | base-5 | 34.5% | 30% | **YES** |
| Safe-2 | elite-8 | 55.2% | 30% | **YES** |
| Bold | base-5 | 64.2% | 50% | **YES** |
| Bold | elite-8 | 102.8% | 50% | **YES** (>100% = whole account on one trade) |

**The spec (RECOMMENDED: quarter-Kelly + min-3 floor, clamped to Rule 6).**
- **Kelly basis (real OPRA, 342 days, `_b10_sizing.py`):** Safe-2 ATM per-trade mean +16.1% / std 50.1% / WR 52.5% / median premium $1.38 → full-Kelly **0.426**; Bold ITM-2 mean +15.1% / std 29.2% / WR 52.4% / median premium $2.57 → full-Kelly **0.420**. **Quarter-Kelly ≈ 0.107 is the recommended fraction.**
- **At $2K, quarter-Kelly only WANTS 0-1 contracts** — so the **min-3 floor (Rule 6) sets the recommendation to 3 contracts** (Safe 20.7% of equity, Bold 38.5% — both safely inside the 30% / 50% caps). The cap clips v15's 5/8; the floor lifts Kelly's 0-1; the answer is **3 at sub-$5K.**
- **Contracts-per-tier (clamped to caps):**
  | tier | Safe-2 (ATM) | Bold (ITM-2) |
  |---|---|---|
  | $2K | **3** | **3** |
  | $5K | 3 | 3 |
  | $10K | 7 | 4 |
  | $25K | 19 | 10 |
- **Risk numbers (the defensible deliverables):** 2,000-path day-block **Monte-Carlo ruin rate = 0.0 for BOTH accounts even under a 50%-edge-haircut stress**; quarter-Kelly maxDD P95 = Safe 11.9% / Bold 10.0%; **kill-switch trips P95 = 0** at the recommended sizing.

**HONEST CAVEAT (do not let J anchor on this).** The compounding sims throw off a fantasy terminal-equity (~$16M half-Kelly) — that is a **single-bull-path compounding artifact**, NOT a forecast. The defensible outputs are the **Kelly FRACTION (quarter)**, the **contracts-per-tier table**, and the **P05 / ruin / maxDD risk numbers** — never the median terminal $. The measured ~4.5-4.7 Sharpe is bull-flattered and will compress in chop/bear; the spec is deliberately sized for the stressed regime (hence quarter, not half/full).

**What J decides (daylight):** (a) adopt quarter-Kelly as the standing fraction; (b) ratify the contracts-per-tier table as the replacement for v15's nominal 5/8 counts (which breach the cap at $2K and must be clipped regardless). No code-flag flip — this updates the sizing tier doctrine in `params.json` after J signs off. Scorecard: `analysis/recommendations/B10-SIZING-SCORECARD.md`.

---

## WP-9 — overnight-vol SIZING OVERLAY on LIVE #1 (size by overnight realized-vol tercile)  *(Sunday volranker-sizing study → MARGINAL: clean $2K risk-tool, OOS-verified; $10K blocked by the min-3 floor)*

**Status:** OPEN, RESEARCH-PRODUCED, **MARGINAL** (sizing DECISION layered on WP-3, not a code flag). The overnight realized-vol ranker (W-track: `sum|MES 1m logret|` over 18:00→09:30 ET, VIX-independent — survives a within-VIX-tercile control: HI-vol $141/day vs LO $24/day at the SAME VIX) is a real day-quality signal. It FAILED as an abstain gate (L174 winner-removal) but as a **sizing overlay it is L174-safe by construction** (never zeroes a day; bottom-tercile is *reduced toward min-3*, never removed). Harness `backtest/autoresearch/_volranker_sizing.py` (real OPRA, `--validate` 8/8). Scorecard: `analysis/recommendations/VOLRANKER-SIZING-SCORECARD.md` / JSON `volranker-sizing.json`. **#1 is recency-RED → no live sizing change ships now regardless; this sets the RULE for when capital is deployed.**

**The daytime sizing-spec (recency-gated, respects Rule-6 hard caps; CLAMP only, never override):**

- **Tercile by causal overnight-vol** — each morning compute the night's overnight_rv = `sum(|MES 1m logret|)` over 18:00(prior)→09:30 ET, and rank it against the **prior 60 classifiable days** (shift-1); bucket = bottom / mid / top (1/3 & 2/3 quantiles of the trailing window). `<20` priors of history → BASE (no guess). **Known by 09:30, before the 09:35 entry gate (causal).**
- **Apply ONLY at sub-$5K (cap-bound), where it is a clean improvement on BOTH books, OOS-verified:**
  | tercile | #1 sizing action (within Rule-6 cap + min-3 floor) |
  |---|---|
  | **top** (high overnight vol) | take the EXTRA contract where the per-trade cap allows (3→4 on cheap strikes); the better-mean day earns the headroom |
  | **mid** | BASE (the WP-3 min-3 / clamped count) |
  | **bot** (dead overnight) | size toward the BOTTOM of the min-3 band / prefer the cheaper-strike fill — **never below min-3, never zero** (L174) |
- **A/B numbers (real OPRA, $2K, FLAT-3 vs overlay):** Safe-2 — Sortino 5.75→**6.04**, total +$517, OOS Sortino 6.66→**7.74** (`OOS_HONEST_CLEAN`). Bold — Sortino 7.08→**7.78**, total +$1,210, OOS Sortino 6.21→**7.26** (`OOS_HONEST_CLEAN`). **0 cap breaches, 0 overlay-zeroed-takeable-trades** at every cell.

**DO NOT apply at $10K+ as built (L175 variance-up).** At $10K the overlay RAISES total but LOWERS per-trade Sharpe AND per-day Sortino and widens maxDD on both books — a textbook L175 distribution-shape penalty. **Root cause (structural):** the **min-3 floor pins FLAT-3 at exactly 3 contracts at every realistic equity ($10K–$50K confirmed)** because the book's median premium (~$1.35 Safe / $2.54 Bold) makes 3 contracts only ~4% of a $10K account — far below even quarter-Kelly. With no down-sizing room, the overlay can only nudge top days 3→4 = the variance-up trade. **The overlay becomes a real compounding lever ONLY once the base size lifts off min-3** (which WP-3's quarter-Kelly does NOT do at these equities).

**What J decides (daylight):** adopt the overnight-vol tercile sizing rule **at sub-$5K only** (a no-code sizing-discipline overlay on WP-3); HOLD the $10K+ rule until the base lifts off the min-3 floor. No `params.json` change while #1 is recency-RED.

**1DTE/dollar-stop follow-up — RAN 2026-06-21, verdict MARGINAL (the named next direction did NOT unblock the compounding case).** Re-ran the overlay byte-for-byte on the WP-8 **deployed** 1DTE/dollar-stop #1 stream (Safe-2 ATM/$35.88, Bold ITM-2/$67.68; median premium $2.50 / $3.57 — ~1.8–1.4× the 0DTE). Harness `backtest/autoresearch/_volranker_sizing_1dte.py`; scorecard `analysis/recommendations/VOLRANKER-SIZING-1DTE-SCORECARD.md` / JSON `volranker-sizing-1dte.json`. The higher premium DID move the floor-binding threshold up, but **not far enough**: at $2K, FLAT-3 of the 1DTE premium actually *breaches* the per-trade cap (37.5% Safe / 53.5% Bold > 30%/50%) so the book is cap-bound below 3 and the overlay's down-modulation is again a clean OOS-verified risk improvement (+0.0035/+0.0037 OOS per-trade Sharpe) — **the same $2K-only risk-tool, confirmed on the deployed stream**. At $10K/$25K, FLAT-3 is 7.5–10.7% / 3.0–4.3% of equity, the bot×0.6 target still rounds **above** min-3, so the floor catches every non-top day → the overlay is **UP-ONLY** (top→4, mid/bot/warmup pinned at 3). That lifts total dollars (+$1.2–1.3K via leverage) but **lowers per-trade Sharpe (−0.012 to −0.015), collapses Sortino, widens maxDD — both IS and OOS** → fails the risk-adjusted bar at scale. 0 cap breaches, 0 overlay-zeroed-takeable days (L174-safe). **Conclusion: the overlay stays a $2K-only tool; WP-9 is NOT promoted to the deployed 1DTE config at scale.**

**Next direction (filed in the 1DTE scorecard):** the blocker is the **min-3 floor**, not the stream — a Rule-6 hard cap that cannot be lowered. The one change that could give the compounding case two-sided room is to apply the tercile multiplier to a **base that is already >3 at $10K** (B10's quarter-Kelly contract count) so bot×0.6 lands strictly above 3 and top×1.5 above that — true two-sided modulation with min-3 as a never-violated backstop. **Test: re-run this overlay with `base = quarter-Kelly contracts` instead of `base = min-3`.**

---

## WP-4 — TP1 take-profit +30% → +75% for the live book  *(B10 angle B → EXIT_IMPROVEMENT, but variance audit = RISK_UP; J risk-tradeoff call, NOT a clean auto-flip)*

**Status:** OPEN, RESEARCH-VALIDATED on the MEAN, but the variance/downside audit (the one open caveat) returned **RISK_UP** for BOTH books — so this is a **J risk-tradeoff DECISION in daylight, not a dormant-flip-ready clean win.** A take-profit-threshold change to the live exit bracket → behind an isolated flag, gym + parity green, A/B confirmed, ONE flag flip in daylight **only after J accepts the drawdown trade.** NOT auto-flipped overnight (edits the live exit path).

**VARIANCE / DOWNSIDE VERDICT (caveat resolved 2026-06-21 — `_b10_exit_variance.py`, real OPRA, 342 days):** **RISK_UP, both books.** The +$13.23/+$17.17 mean lift is real, but it is bought with disproportionate downside — the higher TP1 does exactly what the caveat warned:
- **Per-trade Sharpe DROPS** (Safe 0.3335→0.3223; Bold 0.4068→0.3908) — risk grows faster than return.
- **Median trade flips POSITIVE → NEGATIVE** (Safe +$21.60→−$24.72; Bold +$31.50→−$52.32); **% losing trades crosses 57–60%** (Safe 47.5%→59.5%; Bold 47.6%→57.3%). The entire positive expectancy is now carried by a fatter right tail (P95 up ~$110–$180).
- **Book max drawdown widens ~50% (MATERIAL):** Safe −$836→**−$1,282** (+53.3%); Bold −$848→**−$1,270** (+49.8%). The Safe-2 −$1,282 maxDD is ~2.1× the −$600/day kill-switch — it is no longer "~1.4× a single bad day" (the B9/WP-0 sizing assumption); it must be re-sized around.
- **Mechanism CONFIRMED (the no-run-day exposure):** on the trades that get WORSE under +75%, ~87% never reach TP1, so they ride to the −8% premium stop instead of banking the partial — **36/41 (Safe) and 22/29 (Bold) flip from green to red.** Worse-set exit mix is dominated by `EXIT_ALL_PREMIUM_STOP`. ~$4K of realized winners are converted to losses to capture ~$8K of bigger winners — a higher-variance bet, not a free lunch.
- **Book Sortino marginally HOLDS** (Safe 23.74→24.76; Bold 29.42→30.22) but **book Sharpe DROPS** (Safe 5.78→5.25; Bold 6.45→6.24) — Sortino rises only because it ignores the growing UP-side variance. When Sharpe and Sortino disagree, the honest read is "more upside-skewed, not more risk-adjusted-efficient."
- **What J decides:** "+$13.23/tr (Safe) / +$17.17/tr (Bold) higher EV, in exchange for ~50% deeper maxDD, a per-trade Sharpe that slips, and a majority-losing / right-tail-dependent shape." A pure-EV maximizer flips it; a drawdown-sensitive operator at $2K near a −$600 kill-switch may decline. **Bull-tape caveat: OOS is 2026-bull, so the rich right tail is partly bull-flattered and the realized chop/bear maxDD could be DEEPER than −$1,282.** The tp75-vs-tp30 comparison is bias-cancelled (same tape) and robust; the absolute Sharpe/Sortino are not a forecast.
- **RISK-MODERATED FALLBACK:** tp1=**+50%** captures roughly half the mean lift (+$8.42/tr Safe, +$7.46/tr Bold per Phase-2) with materially less variance — the recommended middle if J wants the bump without the full drawdown hit. Scorecard: `analysis/recommendations/B10-EXIT-AUDIT-SCORECARD.md` (variance section) + `B10-EXIT-VARIANCE.json`.

**What it is.** Raise `tp1_premium_pct` from **+30% to +75%** (let winners run further before the first scale). PHASE-1 audit first CONFIRMED the runner-target knob is dead (the L148/C30 finding holds — see below), so this is NOT runner tuning; it is purely the take-profit threshold.

**Build-spec.**
- **File:** the live exit/bracket path (heartbeat order management) + `backtest/lib` exit path — both read `tp1_premium_pct`.
- **Isolated flag:** gate the +0.75 value behind a flag (e.g. `j_tp1_premium_pct_75=false`, default OFF) OR stage it as a params value change pinned for daylight ratification; flag-OFF == today's +0.30 behavior.
- **gamma-sync targets:** live exit path ↔ `backtest/lib/filters.py` / exit path (no drift — OP-4).
- **Parity test:** flag OFF → byte-identical +30% TP1 exits. A/B test asserting the live path scales at +75% only when flagged.
- **A/B numbers (real OPRA, book-level, 4 honest gates all clear):**
  - **+$13.23/tr** book expectancy lift on **Safe-2 ATM**; **+$17.17/tr** on **Bold ITM-2.**
  - **Broad-based across BOTH IS (2025) and OOS (2026)** (not an OOS-bull-tape artifact — the IS-broad-based gate was added specifically to cull that).
  - Gates cleared: expectancy lift + no-regression on changed trades (L174) + OOS-alone-drop-top5 (C4/L173) + IS-broad-based.
- **PHASE-1 dead-knob audit (the C28/C30 honesty frame, recorded so this is NOT mis-sold as runner tuning):** runner TARGET fires **0.7% (Safe-2, 2/301) / 0.0% (Bold, 0/225)** → the 2.5x runner cap is a CONFIRMED near-dead knob (L148/C30 holds). Stop-rate 46.8%/47.1% (below the 70% C28 threshold). The win is a **take-profit-threshold effect (let winners run to +75% before scaling), NOT runner-target tuning.**
- **One-flag enable (in daylight):** set `tp1_premium_pct=0.75` (or flip the flag). Own adversarial review first.
- **Scorecard:** `analysis/recommendations/B10-EXIT-AUDIT-SCORECARD.md`.

> **Interaction note:** WP-4 (TP1 +75%) is a book-wide exit knob; it composes with WP-1 (touch-and-go entry, selective) and the WP-0-unlocked native entries of #2/#4. When stacking, re-run the book-level A/B — B9 already showed an entry change that helps on shared days can hurt at book level (the touch-and-go caveat); verify WP-4's lift holds once #2/#4 are live.

---

## WP-5 — per-setup STRIKE override for `vwap_continuation` (the live edge is at the WRONG strike)  *(MOST URGENT — fixes the edge that is ALREADY trading)*

**✅ DEPLOYED LIVE (paper) 2026-06-21 — `j_vwap_cont_strike_override_enabled=true` in BOTH params files. Safe-2 → ATM (offset 0), Bold → ITM-2 (offset 2, INERT until Bold `j_vwap_cont_enabled` wired). A5 resolver invoked by the heartbeat VWAP_CONTINUATION block; parity 178/178 GREEN (flags-OFF byte-identical, replay-proven). Shipped under OP-22 standing authorization with a REVOKE note (see CHANGELOG 2026-06-21 + STATUS.md). REVOKE: set `j_vwap_cont_strike_override_enabled=false`.** Shipped TOGETHER with WP-8 (the strike + expiry/stop are one coupled #1 config change).

**Status (pre-deploy, retained): OPEN, RESEARCH-VALIDATED (DECISION-GRADE). Real OPRA fills, hard-windowed ≤ 2026-05-29, 8-of-8-style gates clear on the validated cells.** Scorecard: `analysis/recommendations/WP5-STRIKE-AB-SCORECARD.md` + `wp5-strike-ab.json` + `backtest/autoresearch/_wp5_strike_ab.py`. A per-setup STRIKE dispatch behind an isolated flag (default OFF → current behavior); the daylight flip re-strikes `vwap_continuation` to its validated cell per account.

> **Why this is MORE URGENT than WP-0.** WP-0 unlocks edges #2/#4 that are NOT yet trading. **WP-5 improves the edge that is trading real (paper) capital RIGHT NOW.** The live `vwap_continuation` edge (`j_vwap_cont_enabled=true`, Safe-2) fires the GENERIC v15 **OTM-2** tier — the WEAKEST of four strikes. Every live OTM-2 fill leaves ~$30/tr (Safe) on the table vs its validated ATM cell.

**The problem.** The live order path picks the strike from the generic `v15_strike_offset_per_tier` (Safe-2 $2K → OTM-2). `vwap_continuation` was VALIDATED at ATM (Safe) / ITM-2 (Bold). Real-OPRA A/B (166 signals detected once, re-simulated at each strike, −8% stop + v15 exits held constant):

| cell (live-tier) | n | WR % | full $/tr | OOS $/tr | posQ | OOS-drop-top5 | clears 11-gate |
|---|---:|---:|---:|---:|---:|---:|:--:|
| **OTM-2 (LIVE Safe-2)** | 151 | 39.7 | +15.67 | **+16.45** | **4/6** | **+1.17** | ✅ (weak) |
| **ATM (validated Safe-2)** | 153 | 48.4 | +40.05 | **+46.23** | 6/6 | +15.44 | ✅ |
| ITM-1 | 153 | 46.4 | +45.09 | +59.37 | 6/6 | +22.99 | ✅ |
| **ITM-2 (validated Bold)** | 153 | 47.1 | +65.31 | **+81.04** | 6/6 | +38.22 | ✅ |

**Monotonic gradient ITM > ATM > OTM**, mirrored IS↔OOS. Every cell beats its 20-seed random null AND shows no truncation → genuine option edge that strengthens ITM (C3/C29: OTM theta/delta drag — right direction, cheap contract decays first). OTM-2 is positive but fragile (posQ 4/6, OOS-drop-top5 +$1.17 = nearly all carried by a few days, WR depressed 39.7%).

**THE LEAK (at ~115.2 signals/yr):**
- **ATM − OTM-2 (Safe-2 mis-strike): +$24.38/tr full (~$2,809/yr) · +$29.78/tr OOS (~$3,431/yr).**
- **ITM-2 − OTM-2 (Bold validated vs live tier): +$49.64/tr full (~$5,719/yr) · +$64.59/tr OOS (~$7,441/yr).**

**Build-spec (mirror the WP-0 `select_exit_params` pattern — a per-setup STRIKE dispatch, default behavior-NEUTRAL).**
- **File (backtest half, build first):** `backtest/lib/risk_gate.py` — add `select_strike_offset(setup_name, side, params, global_offset)`: a PURE dispatch returning the setup's ISOLATED `filters.py` strike accessor ONLY when that setup's per-setup strike flag is ON, else `global_offset` UNCHANGED. Mirror `select_exit_params` exactly: a `_PER_SETUP_STRIKE_OVERRIDES` registry keyed on the watcher `setup_name`s, single source of truth = `filters.py` accessors (NO literal offset duplication in risk_gate). Wire it in `backtest/lib/orchestrator.py` (the real-fills order path, ~L1700, right beside the existing `select_exit_params` call) so the resolved offset feeds `simulate_trade_real(strike_offset=...)`.
- **Isolated keys (NEW, both params files, default OFF):**
  `j_vwap_cont_strike_override_enabled=false`, plus per-account validated offsets in **live-params convention** (NEG=OTM): `j_vwap_cont_strike_offset_safe=0` (ATM), `j_vwap_cont_strike_offset_bold=2` (ITM-2). The `filters.py` accessor returns the per-account offset only when the enable flag is ON.
- **PARITY REQUIREMENT (the load-bearing property, identical to WP-0):** flag **OFF → `select_strike_offset` returns `global_offset` verbatim → byte-identical to today's OTM-2 (and every other setup's generic v15 tier).** Add `backtest/tests/test_engine_strike_override_parity.py`: flags-OFF == generic tier for EVERY setup; `vwap_continuation` + flag-ON → ATM (Safe) / ITM-2 (Bold); unknown setup → generic tier. **Per-setup ONLY (C29): this dispatch overrides the strike for `vwap_continuation` and nothing else — it is NOT a blanket `v15_strike_offset_per_tier` change** (which stays correct for every other setup).
- **gamma-sync targets (OP-4, daylight step like WP-0's A5):** live heartbeat strike-pick step ↔ `backtest/lib/filters.py` / order path. The live tick must resolve the strike via the SAME dispatch table (fall back to the generic v15 tier). If the strike-pick is awkward to express in prose for the LLM tick, graduate it to a tiny callable the tick invokes (prose→code), same as the WP-0 A5 note.
- **CONVENTION CROSSWALK (mis-stating it invalidated a weekend — sim-accuracy gate, OP-16):** `simulator_real` uses NEG=ITM (OTM-2 = sim `+2`, ITM-2 = sim `−2`); live params `v15_strike_offset_per_tier` uses NEG=OTM (OTM-2 = `−2`, ITM-2 = `+2`) — INVERSE. The override keys above are in the **live-params convention**; the orchestrator must translate to the simulator convention exactly as the existing edge-hunt path does.
- **One-flag enable (daylight):** set `j_vwap_cont_strike_override_enabled=true` in each account's params (Safe→ATM, Bold→ITM-2). Own adversarial review first. Per OP-22 / FORBIDDEN-FRAMING this is a profitable, validated improvement to an ALREADY-LIVE edge → ships under the standing authorization with a REVOKE note (NOT a "want me to flip it?" gate).
- **PRE-REQ for the Bold leg:** Bold's `j_vwap_cont_enabled` key is currently ABSENT → the edge is INERT on Bold (B1 finding #1). Wire that key first, then the ITM-2 override matters.
- **Caveats:** OOS=2026 bull → absolute OOS $ are bull-flattered, but the A/B is bias-cancelled (same tape across all four cells) and the gradient holds IS↔OOS, so the *relative* leak is robust. L174 same-side-concentration caveat does NOT apply (WP-5 re-strikes the EXISTING edge — no new setup added).

---

## WP-6 — tighten the chandelier profit-lock trail 0.15 → 0.125 (or 0.10) for the live `vwap_continuation` book  *(Sunday web-learn → LIVE_EDGE_IMPROVEMENT, clears full L175)*

**Status: OPEN, RESEARCH-VALIDATED (decision-grade). Real OPRA fills, hard-windowed ≤ 2026-05-29, full L175 risk-adjusted gate clears vs the current LIVE 0.15.** Scorecard: `analysis/recommendations/SUNDAY-WEB-LEARN-SCORECARD.md` (`chandelier-tighten-20-to-15-oos-wf` section) + `analysis/recommendations/regime-chandelier-sweep.json`. This is a take-profit-LOCK (trail) knob on an ALREADY-LIVE edge — C3/L58 does NOT apply.

> **Why this is shippable (and the premise correction).** The hypothesis arrived as "tighten 0.20→0.15" — but params.json **already shipped 0.20→0.15 LIVE on 2026-06-19**. The real, un-shipped finding is that going **TIGHTER STILL beats the current live 0.15** on the `vwap_continuation` population and survives walk-forward. This is the one clean win from the Sunday web-learn batch (the other 6 sub-studies are DEAD — see scorecard).

**A/B numbers (ITM-2 / −0.08 stop / arm@0.05 / tp1 0.5 / runner 2.5x; real OPRA fills, n=149, signals=158, IS=2025/OOS=2026):**
| trail | exp $ | OOS exp $ | per-trade Sharpe | Sortino | maxDD $ | L175 vs live 0.15 |
|---|---:|---:|---:|---:|---:|:--:|
| **0.10** | 80.62 | 98.10 | 9.73 | 15.91 | -315.12 | **PROMOTE** (exp +$20.68, OOS +$31.01, all risk no-worse, anchor no-reg) |
| **0.125** | 69.94 | 82.06 | 9.04 | 13.80 | -315.12 | **PROMOTE** (exp +$10.00, OOS +$14.97, all risk no-worse, anchor no-reg) |
| **0.15 (LIVE)** | 59.94 | 67.09 | 8.36 | 11.83 | -315.12 | baseline |
| 0.20 (prior) | 57.07 | 65.10 | 7.41 | 11.26 | -350.52 | reject (worse on every axis) |

- **Monotonic: tighter beats wider on total P&L, OOS, Sharpe AND Sortino**, with maxDD equal-or-better (0.10/0.125/0.15 all -$315.12; only the retired 0.20 was worse at -$350.52). posQ 6/6 at every cell. Anchor no-regression holds (anchor $ rises as the trail tightens: 0.10 → $145.50 vs live 0.15 → $92.25, n=2).
- **MECHANISM (not a fluke, load-bearing for J's confidence):** at the −8% premium stop, **148/149 trades exit on the premium stop** — the chandelier almost never fires as a *trailing exit*. Instead **the trail floor IS the runner profit-lock floor**, so a tighter trail locks winning runners HIGHER before they fade back into the −8%/ribbon stop. The 0.20 win cases are the rare TP1_THEN_RUNNER_RIBBON trades where a looser trail let a big runner survive (e.g. 2026-04-17 +$522 vs +$101) — but those are outweighed 78-wide across BOTH IS and OOS.

**Build-spec (params-value change pinned for daylight, mirror the WP-4 staging discipline).**
- **File:** `automation/state/params.json` (+ `automation/state/aggressive/params.json` for Bold) — key `v15_profit_lock_trail_pct`. Live exit/bracket path (heartbeat order management) + `backtest/lib` exit path both already read this key, so this is a value change, NOT a code refactor.
- **Recommended value:** **0.125** as the conservative ship (clears L175 cleanly, +$10/tr exp / +$14.97/tr OOS, banks ~half the available lift with the gentlest behavior change from live), with **0.10** as the aggressive option (+$20.68/tr exp / +$31.01/tr OOS, still all-risk-no-worse, maxDD identical). Both PROMOTE; J picks the step size.
- **gamma-sync targets (OP-4):** confirm `automation/prompts/heartbeat.md` exit step + `backtest/lib/filters.py` both resolve the trail from the SAME `v15_profit_lock_trail_pct` key (no literal duplication). Since this is a single existing param, parity is "value reads through everywhere"; pin-chain-verify should confirm no hardcoded 0.15/0.20 literal survives.
- **Parity / safety:** the value is already live-wired; the risk is a stale hardcoded literal somewhere. Grep the live + backtest exit paths for `0.15`/`0.20`/`profit_lock` literals before the flip; run the exit-path tests + a gym pass.
- **One-step enable (daylight):** set `v15_profit_lock_trail_pct=0.125` (or `0.10`) in both params files. Per OP-22 / FORBIDDEN-FRAMING this is a profitable, validated, full-L175-clearing improvement to an ALREADY-LIVE edge → ships under the standing authorization with a REVOKE note (NOT a "want me to flip it?" gate). Own adversarial review first.
- **Caveats (HONEST):** (1) OOS=2026 bull → absolute OOS $ are bull-flattered, but the A/B is bias-cancelled (same tape across all four trail values) and the gradient holds IS↔OOS, so the *relative* improvement is robust. (2) anchor n=2 is thin (anchor OPRA coverage is sparse) — the anchor-no-regression check is directional, not high-N. (3) the win is a runner-profit-LOCK effect, not a trailing-EXIT effect (the trail rarely fires as the exit) — frame it that way, do not mis-sell it as "the trail captures more trends."

---

## WP-7 — multi-edge COMBINE RULE (how A5 picks when #1/#2/#4 fire the same day)  *(Sunday combine-rule study → FIRST_TO_FIRE Safe / ONLY_1 Bold)*

**Status: OPEN, RESEARCH-VALIDATED (decision-grade, OOS-honest). Real OPRA fills, hard-windowed (realized last fill 2026-06-15 ≤ OPRA cache 2026-06-18, no past-cache leakage), 363 trading days 2025-01..2026-06-16, IS=2025/OOS=2026.** Scorecard: `analysis/recommendations/SUNDAY-COMBINE-RULE.md` + `.json` + `backtest/autoresearch/_sun_combine_rule.py`. This is the **combine-logic A5 must implement** once #2/#4 go live — NOT a new edge (the constituents cleared their own bars).

> **Why this matters (the overlap is real, the rule is load-bearing).** Safe-2 has 158 signal days, **115 are multi-edge and ALL 115 same-side** (#1+#2+#4 lean the same way); Bold 157 days, **81 multi-edge, all same-side**. So when #2/#4 ship alongside #1, A5 *must* decide how to handle a day where 2-3 edges fire — and the choice changes OOS expectancy and drawdown materially.

**The 4 rules tested + the OOS-honest result (real OPRA, kill-switch-clipped at Safe −$600 / Bold −$836):**

| account | rule | OOS exp/tr | total $ | ann.Sharpe | maxDD $ | worst day $ | L175 ret/maxDD | verdict |
|---|---|---:|---:|---:|---:|---:|---:|:--:|
| **Safe-2 (ATM)** | **FIRST_TO_FIRE** | **$53.15** | $7,477.12 | 4.00 | **−454.56** | −211.68 | **16.45** | **WINNER** — only rule beating baseline OOS, at the SAME maxDD as ONLY_1 → strictly dominates |
| Safe-2 (ATM) | ONLY_1 (baseline) | $46.02 | $6,943.56 | 3.84 | −454.56 | −211.68 | 15.28 | baseline |
| Safe-2 (ATM) | TAKE_BEST | $34.42 | $8,240.28 | 4.28 | −573.28 | −211.68 | 14.37 | REJECT — OOS DEGRADES (curve-fit to 2025) |
| Safe-2 (ATM) | TAKE_ALL_STACK | $34.98 | $13,227.56 | 4.08 | **−1,007.16** | **−423.36** | 13.13 | REJECT — OOS degrades + ~2× maxDD/worst-day |
| **Bold (ITM-2)** | **ONLY_1** | **$76.61** | $11,060.04 | 4.10 | **−939.12** | −223.68 | 11.78 | **WINNER** — FIRST_TO_FIRE collapses to this (#1 triggers first every shared day) |
| Bold (ITM-2) | TAKE_BEST | $67.25 | $13,198.52 | 4.60 | −1,053.12 | −223.68 | 12.53 | REJECT — OOS degrades |
| Bold (ITM-2) | TAKE_ALL_STACK | $64.55 | $17,762.16 | 4.25 | **−1,635.00** | **−447.36** | 10.86 | REJECT — OOS degrades + ~2× maxDD/worst-day |

**THE RECOMMENDED RULE (A5 implements this):**
- **Safe-2 = FIRST_TO_FIRE** — on a multi-edge same-side day, take ONLY the earliest-triggering edge that day. OOS $53.15/tr (the ONLY rule that BEATS the ONLY_1 baseline $46.02) at the SAME maxDD (−$454.56) → strictly dominates the baseline.
- **Bold = ONLY_1** — FIRST_TO_FIRE collapses to ONLY_1 there (#1 triggers first on every shared day, so "earliest" is always #1; no gain). Keep ONLY_1 as the rule; #2 adds no incremental edge on the days it overlaps #1 on Bold under this geometry.
- **take-all OVERSTAKES = true (do NOT stack).** TAKE_ALL_STACK roughly DOUBLES maxDD (Safe −$454.56→−$1,007.16, delta −$552.60; Bold −$939.12→−$1,635.00, delta −$695.88) and worst-day (−$211.68→−$423.36; −$223.68→−$447.36) while OOS expectancy FALLS — the same-side same-day concentration penalty. It does NOT breach the halt in the sim ONLY because the sim holds qty=3/edge; **at LIVE sizing (30%/50% risk per edge) 2-3× stacking would multiply day-risk and can breach the kill switch.** Not shippable.
- **Why TAKE_BEST/TAKE_ALL_STACK are rejected (C4/L174):** both post the prettiest FULL-window totals but their OOS (2026 live tape) per-trade expectancy DEGRADES below the ONLY_1 baseline — the multi-edge ranking/stacking is curve-fit to 2025. An OOS-positive + no-OOS-degrade guard rejects them.

**Build note for A5.** A5 already routes #1/#2/#4 order-builds through the canonical resolvers (`select_exit_params` WP-0, `select_strike_offset` WP-5). The combine rule is the dispatch layer ABOVE that: on a day with multiple watcher signals, A5 picks ONE per the table (Safe FIRST_TO_FIRE by trigger-bar time; Bold ONLY_1). Per OP-4, gamma-sync the same pick into `automation/prompts/heartbeat.md` + the backtest combine path so live == backtest by construction. Default behavior is unchanged until #2/#4 flip (today only #1 fires live, so any rule reduces to ONLY_1).

**Caveat (HONEST):** OOS=2026 is bull-flattered; the A/B is bias-cancelled (same tape across all 4 rules) so the *relative* ranking is robust, but the absolute Sharpe/total are not a forecast. The combine rule is a refinement of an already-overlapping book — it does NOT resolve the L174 concentration concern (the edges are still same-side sub-pools of #1); FIRST_TO_FIRE simply avoids paying for the overlap twice.

---

## ⚠ FRESH-DATA VERDICT (2026-06-21 — read before flipping ANY WP that touches #1/#2/#4)

**The 20-day blind spot is CLOSED (A1 backfill → option cache ends 2026-06-18, `data-coverage.json` OK), and the 3 edges were re-scored on the never-before-scored fresh window 2026-05-30..06-18 (14 trading days). The freshest data did NOT confirm the edges positive — but nothing is dead.** Full detail: `analysis/recommendations/SUNDAY-FRESH-REVALIDATION.md`; STATUS.md leads with it.

- **Fresh window: both books NEGATIVE.** Safe-2 (ATM #1+#2+#4) −$196.32 (4 days, +1/−3); Bold (ITM-2 #1+#2) −$853.68 (5 days, 0/5). Live #1 at the validated Bold ITM-2 cell went 0/5 for −$84.86/tr. The validated strike gradient **FLIPPED** on the fresh 3 weeks (OTM-2 best, ITM-2 worst — inverse of validated). All cells are n≤5 → below the 11-gate bar's n≥20 → a small-n recency YELLOW, not a ratification or a kill.
- **Full-OOS-2026 (n≈24–51) still strongly positive, gradient intact:** #1 ITM-2 +$73.66/tr, ATM +$47.55/tr, OTM-2 +$18.36/tr; #2 ATM +$13.11/tr (n=23); #4 ATM +$29.93/tr (n=24). So the edges are alive on the larger sample.
- **Implication for the WPs below:** WP-5/WP-6 remain shippable under standing authorization (validated on full-history real fills, bias-cancelled A/Bs), but the fresh wobble is a REVOKE-note input — especially the **WP-5 Bold ITM-2 leg** (the fresh window had OTM-2 beating ITM-2). The Safe→ATM leg and the full-OOS gradient still favor WP-5; if J wants extra safety, re-confirm the Bold ITM-2 strike on a wider window before that leg. Do NOT read the fresh −$ as "kill the edges" — read it as "small-n; the standing bar still rests on full-history n."

---

## WP-PS1 — premium-SELLING CLASS (defined-risk 0DTE condor) — DORMANT / NOT-FLIP-READY  *(Premium-selling pivot → IC = LEAD-not-EDGE; the ONLY conversion path is a wide-OPRA-band data fetch, NOT a flip)*

> **Status: DORMANT, NOT shippable.** This is a genuinely-NEW strategy CLASS (market-neutral, defined-risk premium-SELLING — orthogonal to the bull-directional book) that was self-directed off the C3/L58 insight (theta KILLS long premium → sell it). It is filed here for completeness and to define the ONE path that could convert it, but it does **NOT** clear the gate bar and must **NOT** be flipped under the standing profitable-edge authorization. The best structure (iron condor) is a null-failing theta artifact (L172), which is the explicit carve-out the standing authorization names as NOT a validated edge.

**What it is.** Sell a defined-risk neutral structure (iron condor: OTM put spread + OTM call spread, every short leg has a long wing) on 0DTE SPY for theta income that profits in range/chop — the regime currently drawing down the bull-directional book. Multi-leg sim built TDD-first: `backtest/lib/simulator_credit.py` + `backtest/lib/multileg_structures.py`, ALONGSIDE the untouched `simulator_real.py` (17/17 tests PASS). 900-cell grid (IC/PCS/CCS/IB/BWIC × 180), real OPRA multi-leg fills, 365d.

**Why it is NOT flip-ready (the gate-6 failure + the tail caveat).**
- **IC clears 7 of 8 gates** (OOS +$22.95/tr, 85% WR, posQ 5/6 monthly, drop-worst5 +$21, IS-2025-H1 +$28.96, recency-chop +$8.84) **but FAILS gate 6 — the L172 random-strike null.** Randomizing the short offset {2,3,4} on the same days reproduces and at p95 EXCEEDS (+$26.03) the chosen offset-2 +$22.95 → the expectancy is generic theta any in-band narrow condor harvests, **NOT strike-selection alpha.** Two independent harness passes + two independent null seedings = same verdict. Per OP-11/L172 this is the named exception to the standing authorization.
- **The tail is benign ONLY because the ±$5 OPRA cache band forces narrow $1-2 wings** (max-loss $100-200/lot). That does **NOT** generalize to a textbook 16-delta / 20-30-wide condor (~$3,000 max-loss/lot) — which the cache cannot price. So tail-survivability is conditional on staying narrow (which the band forces), NOT something validated for a real condor.
- **CCS / PCS / Iron Fly all DEAD** (CCS best OOS −$4.27/tr; Iron Fly full-sample −$2.1/tr + −$1,378 book DD; PCS −$10 to −$14/tr). The pivot result is conditional on the neutral-OTM structure, NOT "selling premium wins."

**Regime-diversification verdict (the thesis check):** PARTIALLY confirmed. The condor IS positive in the recent chop (the regime hurting the bull book) — but does NOT amplify there (+$8.84 recency < +$23 OOS) AND the chop edge is itself null-positive (generic theta, not selection). So premium-selling SURVIVES chop but does not give us a *selected* regime-diversifying edge on this data.

**The ONLY conversion path (LEAD → EDGE).** This is a DATA-FETCH workpackage, not a code-flip:
1. **Fetch a WIDE, delta-targeted OPRA band** — extend `backtest/data/options/` to ±$15-$20 strikes/side so a true 16-delta short + 20-30-wide wing can be priced (the current ±$5 / 11-strike band is the binding constraint).
2. **Re-test the REAL max-loss tail** on the wide-wing condor (the ~$3,000-max-loss geometry) — verify defined-risk sizing fits INSIDE the kill-switch (Safe −30%/day, Bold −50%) at the real per-lot max-loss, not the narrow-wing one.
3. **Find a SELECTION rule that BEATS the random-strike null** (VIX-character / realized-range / time-regime gate) — absent a null-beating selection, the only honest framing is a passive mechanical theta sleeve sized for the REAL tail, NOT a Gamma selection edge.

**Until all three land, do NOT enable.** No live wiring exists and none should be built. Scorecard: `analysis/recommendations/PIVOT-PREMIUM-SELLING-SCORECARD.md`. Harnesses: `backtest/autoresearch/_pivot_premium_selling.py` (+ `_null.py`, `_focus.py`, `_pivot_premium_finalize.py`).

---

## WP-PS2 — regime-SWITCH book (directional-in-trend + condor-in-chop) — CLOSED / DEAD  *(the APEX axis — and the gate that just turned RED for the WP-PS1 wide-band fetch)*

> **Status: CLOSED, SWITCH_DEAD.** No live-path change. This was the campaign's apex research question (DIRECTION-BACKLOG #3) and the green/red GATE that justified the WP-PS1 wide-band OPRA fetch. The gate is **RED** → the fetch is NOT worth doing for regime allocation.

**The research question (NOT a ship test).** Don't GATE per-trade (dead by winner-removal, L174) and don't change STRUCTURE per-edge (dead, the debit-spread falsification). Instead ALLOCATE between two real-fills classes by causal morning regime: run the LIVE directional sleeve (`vwap_continuation`, ATM, −8% stop) on TREND days, swap to the iron-condor theta-harvester (the WP-PS1 LEAD config) on CHOP days. The claimed value = right-tool-for-the-regime (deploy the harvester when directional bleeds in chop), NOT the condor being a selection edge.

**What was built (byte-for-byte sleeve reuse, real OPRA both sleeves, $0).** `backtest/autoresearch/_regime_switch_book.py` (base) + `_regime_switch_sweep.py` (108-cell threshold×NEUTRAL sweep). Directional = `simulator_real` + the live `vwap_continuation` detector (identical to `recency_check.simulate_set`); condor = `simulator_credit` + `multileg_structures` (the LEAD cell from the WP-PS1 scorecard). Causal classifier: trend_strength_20d + VIX spot/slope @09:30 + MES overnight-range/ATR + prior RTH-range/ATR, all ≤ the morning decision bar, thresholds from IS terciles (pre-2026, no OOS leak). NO edits to watchers/params/risk_gate/orchestrator/heartbeat/simulator_real/simulator_credit. Regime distribution over 365d: **TREND=47 / CHOP=55 / NEUTRAL=263** — non-degenerate (NEUTRAL elevated partly because MES continuous data ends 2026-06-12, so the freshest ~4 SPY days lack the overnight feature and correctly fall to NEUTRAL; honest data gap).

**Why it is DEAD (the load-bearing thesis check + no-regression).**
- **On the classifier's OWN 55 chop days the LIVE directional sleeve out-earns the iron condor +$1,202.44 vs +$459.60 = −$742.84.** Swapping in the harvester surrenders P&L exactly where the thesis said it would win. (Directional even netted −$158.32 on the 47 "trend" days — the label is not where directional makes its money either.)
- **No-regression FAILS:** on the 318 days the book switches away from directional it made $6,481.44 vs the $7,224.28 directional-alone would have made = **−$742.84 net.**
- **Risk-adjusted FAILS at every NEUTRAL policy:** directional-always $7,065.96 / Sharpe 3.883 / Sortino 5.753 vs best switched $6,323.12 / 3.693 / 5.021.
- **Sweep: 0/108 cells pass all bars, 0/108 where the condor beats directional on its own chop days** (best-thesis cell still −$134.40). Bar-2 (recency-25d drawdown) passes only trivially — by routing off the bleeding sleeve while giving up more upside elsewhere.

**Root cause (C1/C3/L172).** The premise "directional bleeds in chop, the harvester won't" does NOT hold at the per-day-regime level on real OPRA fills: directional's tight −8% ATM structure stays net-positive on chop days, while the generic-theta (null-failing-standalone) ±$5-band condor caps upside. The recency-25d directional RED (−$224.64) is **time-clustered, not regime-separable** — no morning-causal label isolates it.

**Implication for WP-PS1.** The wide-band OPRA fetch was gated on this result. **RED → do NOT spend the heavy fetch on regime allocation.** A wider band changes only the condor's magnitude; it cannot reverse a deficit driven by directional being positive on chop days. WP-PS1 stays DORMANT and only re-opens for a DIFFERENT research question (e.g. event-IV-crush, which sells INTO a scheduled vol-collapse rather than allocating by ambient regime). Scorecard: `analysis/recommendations/REGIME-SWITCH-BOOK-SCORECARD.md`. Artifacts: `backtest/autoresearch/_state/regime_switch_book/{results,sweep_results}.json`.

---

## CLOSED — `vwap_pullback` (H4) 4th-edge thread → RESKIN_OF_1, NOT a new edge  *(2026-06-21 independence verify, L174)*

**Status: CLOSED. Not a live-path candidate.** The DTE-library survey (`DTE-LIBRARY-SURVEY.md`) + the [2026-06-21 DTE-EXPANSION FOLLOW-UP] STATUS entry flagged `vwap_pullback` at 0DTE ITM-2/-0.08 as a "NEW SHIPPABLE FINDING" — a second un-shipped 0DTE VWAP-family edge (+$64.77/tr, n=93, all 11 gates incl L173 PASS, beats the random null) and recommended a dedicated WP-style validation before flipping. **That validation was run and it kills the lead as the anchored-VWAP trap (L174).**

- **Decisive test (independence, `_b8_anchored_vwap` convention, OVERLAP_MAX=0.80):** vwap_pullback fires 98 signals on 98 days; **same-side day-overlap vs LIVE #1 `vwap_continuation` = 1.000 (98/98 days, all same side)** — WORSE than the anchored-VWAP A3 that was blocked at 0.973. `vp_days ⊆ #1_days` proven (0 vp-only days, 0 opposite-side days). It is a strict SUBSET of #1, by construction (both = "first-N RTH closes one side of session VWAP → first in-trend VWAP touch"; #1's looser 3-bar/10:30 net is a superset of vp's stricter 6-bar/0.08%-tag).
- **Gates re-confirmed (isolation):** the +$64.77/tr 11-gate clear reproduces to the dollar — but that is necessary-not-sufficient; L174's whole point is a re-skin clears the isolation bar too. Only the overlap test distinguishes them.
- **Incremental:** book daily-Sharpe 0.409 → 0.431 with vp added, but corr(vp,#1)=0.389 and the days are #1's days → correlated re-exposure, not diversification. WP-1 + WP-5 already capture this population through the LIVE edge.
- **Caveat:** the +$64.77 headline uses premium_stop=-0.08; the LIVE first-strike rule trades chart-stop-only (L51/L55/C2), where the prior ratify (`vwap_pullback_ratify.py`) found only +$14/t / WF 0.239 FAIL with no clean regime gate. Even its best −0.08 cell is closed by independence.

**Validated 0DTE edge inventory stays #1 / #2 / #4 — there is no 4th edge here.** Artifacts: `analysis/recommendations/VWAP-PULLBACK-EDGE-VERIFY.md` + `.json`; script `backtest/autoresearch/_vwap_pullback_edge_verify.py`.

---

## WP-8 — 1DTE variant of the LIVE `vwap_continuation` edge (escape the 0DTE theta wall on DOLLARS)  *(DTE-expansion follow-up Angle A → was SHARPE_TRADEOFF_J_CALL; the STOP-CONSTRUCTION lever RESOLVED it → now CLEAN_1DTE_UPGRADE — auto-ship-bar-clearing, daylight wiring)*

**🔴 REVERTED (DE-RISKING, Sunday 2026-06-21) — `j_vwap_cont_1dte_enabled=false` AND `j_vwap_cont_dollar_stop_enabled=false` in BOTH params files. ROOT CAUSE OF REVERT: the WP-8 A/B validated each 1DTE cell against the SAME 0DTE/−8% baseline but NEVER modeled the per-trade NOTIONAL CAP (`simulator_real` has no buying-power cap — grep-confirmed), so the +$57.59/+$73.91 OOS lift silently ASSUMED qty3 always fills. It does not: `risk_gate.check_order` caps notional = premium×qty×100 at the tighter of `per_trade_risk_cap_pct` and the v15 per-tier max_pct. Safe-2 $2K → $600 cap; ATM-1DTE median entry $2.495 → qty3 notional ~$748 = BLOCK [RISK_CAP] (measured Safe block-rate 72.29%); qty2 fit = BLOCK [MIN_CONTRACTS] (no auto-reduce). Bold ITM-2 1DTE qty3 ~$1,071 > $824 cap AND qty3 < min 5 → can NEVER fit. VERIFIED via `pre_order_gate.py` (outputs in the report). NET LIVE CELL after revert = ATM(WP-5 strike override KEPT)/0DTE/−8% percent/qty3 → notional $1.35×3×100 = $405 < $600 (PASS, 20.3% equity) AND validated (`dte-stop-construction.json` ATM/0DTE/percent: OOS exp +$25.0/tr, 6/6 posQ). KEPT ON: `j_vwap_cont_enabled=true`, `j_vwap_cont_strike_override_enabled=true`. The cap-aware affordable 1DTE re-ship is QUEUED as WP-10 (weekday). REVOKE-of-REVOKE (weekday only): flip the two flags back ONLY after a cap-aware A/B (qty modeled against the $600/$824 cap) clears the bar.**

**🟢 NOT PERMANENTLY DEAD — ACCOUNT-SIZE-GATED (the honest re-frame).** The ATM/1DTE/$35.88/qty3 doubling was validated cap-BLIND at +$57.59/tr OOS and cleared L173 on the FULL 166-signal book (`dte-stop-construction.json` ATM-tier). The cap only binds because $748.50 notional > the $600 cap at $2K. The cap is `equity × 0.30`, so the cell becomes affordable at **Safe-2 equity ≥ $748.50 / 0.30 ≈ $2,495** (currently $2,000 → +$495 / +24.7% of compounding). At/above ~$2.5K the cap no longer binds, all 166 signals are realizable, and the original cap-blind validation (which DID clear L173 broad-based, unlike the OTM-2/1DTE survivorship cell) applies in full. **RE-ACTIVATION TRIGGER: when Safe-2 compounds past ~$2,495 AND recency_check clears RED → re-run the cap-aware A/B at the then-current equity; if ATM/1DTE/$35.88/qty3 now fits the cap and still clears the bar, flip the two flags back (weekday, REVOKE note).** This converts the WP-8 "defect" into a concrete compounding milestone: the doubling is the prize that the modest +$25/tr ATM/0DTE base edge is compounding TOWARD. (Bold ITM-2/1DTE needs equity ≥ $1,785/0.50 ≈ $3,570 — further off; Bold's nearer affordable path is the OTM-2/1DTE cell, gated on the WP-10 construction-robust + recency checks.)

<details><summary>Superseded "DEPLOYED LIVE" banner (retained for audit trail — this deploy was the defect)</summary>

**✅ DEPLOYED LIVE (paper) 2026-06-21 — `j_vwap_cont_1dte_enabled=true` AND `j_vwap_cont_dollar_stop_enabled=true` in BOTH params files (Safe-2 dollar-stop $35.88 / Bold $67.68). #1 now trades 1DTE + dollar-anchored stop, resolved by the A5 callable, invoked by the heartbeat. SAFETY GATE 3 PASS: EOD-flatten is expiry-agnostic (closes a 1DTE position at 15:55, both books — verified `automation/prompts/eod-flatten.md`). Parity 178/178 GREEN (flags-OFF → 0DTE/-8%-percent byte-identical, replay-proven). Shipped under OP-22 standing authorization with a REVOKE note. REVOKE (per piece): `j_vwap_cont_1dte_enabled=false` reverts the expiry; `j_vwap_cont_dollar_stop_enabled=false` reverts the stop construction. Bold flags armed-but-INERT until Bold `j_vwap_cont_enabled` wired. Shipped TOGETHER with WP-5.** ← REVERTED: the A/B never modeled the notional cap; the cell is unaffordable at qty3.

</details>

> **⭐ STATUS UPGRADE (2026-06-21 — the stop-construction lever resolved the tradeoff; the campaign's FIRST clean improvement to the LIVE money-maker).** WP-8's own DO-NOT-RE-PROPOSE note named the next lever: "the STOP DENOMINATOR (percent-stop scaled to the long-leg premium, or a chart/level-only stop)." That lever was tested as a full **DTE × stop-construction matrix** (`_dte_stop_construction.py`, real OPRA fills, byte-for-byte live detector). **The maxDD-doubling that made WP-8 a SHARPE_TRADEOFF was ENTIRELY an artifact of applying the live −8% PERCENT stop to the bigger 1DTE premium (a fixed percent of a bigger premium = a bigger DOLLAR loss).** Swapping to a **DOLLAR-ANCHORED stop ($67.68/trade = the median per-trade dollar loss on the 85 0DTE −8% losers at ITM-2, calibrated once then applied unchanged at 1DTE)** turns the +theta-dollars lift into a CLEAN WIN: OOS exp/tr +$36.34→**+$73.91** (2.03×), maxDD −$939.12→**−$879.84 (BETTER than the 0DTE baseline)**, Sortino 14.31→**25.70 (+80%)**, worst day **−$67.68** (well inside Safe −$600 / Bold −$835 kill switches), positive quarters 5/6→**6/6**, structural+L173 **PASS**. WR barely moves (42.8%→41.6%) — the dollar cap trims only the fat-tail stop-outs, NOT the body of winners, so it did NOT repeat the diagonal's lift-collapse failure mode. **This is the ONLY clean-win cell in the 12-cell matrix.** Per OP-11/OP-22 it clears the auto-ship bar (OOS-positive AND Sortino improves AND maxDD not-worse AND structural+L173 PASS AND A/B filed) → it ships under the standing profitable-edge authorization, NOT a "want me to flip it?" gate — BUT it changes the live STOP CONSTRUCTION (a risk_gate / order-path change), so it ships in a weekday after-hours block (daytime + recency-gated + own adversarial review), NOT this Sunday. Build-spec at the bottom of this WP. Scorecard: `analysis/recommendations/DTE-STOP-CONSTRUCTION-SCORECARD.md` + `dte-stop-construction.json`; sim `backtest/autoresearch/_dte_stop_construction.py`.
>
> **What did NOT transfer (honesty):** the chart/level stop (seductive 70.5% WR at 1DTE) is a theta/tail trap — FAILS L173 oos_drop_top5 at every DTE, OOS total collapses to $587 at 1DTE, maxDD −$3,480 (classic C3/L172). The percent-scaled stop is only a PARTIAL (Sortino 18.87 but maxDD +48% > the +25% bar — caps the median dollars, not the right tail). **No 2DTE cell clean-wins under any stop** (two overnight sessions reintroduce a gap/settlement tail the per-trade dollar cap can't reach; worst day −$1,140 blows the Bold kill). **The clean win is specifically 1DTE + dollar-anchored stop.**
>
> **⭐ GENERALIZATION VERDICT (2026-06-21 — does this lever upgrade the whole edge stack, or only #1?). The MECHANISM generalizes; the WIN does NOT — it requires a clean 0DTE baseline to lift. The ship-package is #1 alone.** The same byte-for-byte harness ran the dollar-stop lever on the two dormant long-premium directional edges (#2 `vwap_reclaim_failed_break` ITM-2+ATM; #4 `vix_regime_dayside` ATM), each with its dollar-stop **re-derived per edge AND per tier** (C29 — #2 ITM-2 $66.24 / ATM $33.84; #4 ATM $36.48; NONE transferred from #1's $67.68):
> - **#2 = NO_CHANGE.** The lever does not transfer. OOS dollars DO rise at 1DTE/dollar (ITM-2 +$573, ATM +$354) but **concentrated in a few days (L173 oos_drop_top5 still negative), not broad-based like #1**, AND maxDD **WORSENS** at 1DTE (ITM-2 −$1,176→−$1,881 = +60%; ATM −$817→−$1,091 = +33%) — the OPPOSITE of #1 (which improved). #2's reclaim entries sit closer to their structural stop, so the dollar cap bites the body of winners (WR collapses, Sortino drops) — the diagonal/L-failure mode. #2's own 0DTE baseline also already fails the 11-gate bar, so there is no clean floor to lift. **Stays dormant; do NOT ship a #2 DTE/stop change.**
> - **#4 = NO_CHANGE, but for the opposite reason — the mechanism transfers cleanly.** 1DTE/dollar vs 0DTE/-8% baseline: OOS total **+$461.76 (+89%/tr)**, maxDD only **+12.9% (−$549→−$620, well inside the +25% bar)**, Sortino **+60% (10.06→16.05)**, and the dollar cap even held the 2DTE worst-day flat at −$36.48 (no kill-switch blowout, unlike #1's 2DTE). #4 PASSES all four NUMERIC clean-win legs. It fails on ONE gate — **L173 (`oos_drop_top5 ≤ 0`)** — and that failure **pre-exists** the DTE/stop choice (#4's 0DTE baseline already fails L173; its OOS profit is concentrated in ~handful of days; the lift rests on only ~25 OOS trades, thin). The lever amplifies an edge; it cannot manufacture one. **#4's blocker is an ENTRY-quality problem (OOS breadth / L173), not a stop or DTE problem — fixing #4's entry breadth is the path to unlocking its already-confirmed lift, NOT re-tuning its stop. Stays dormant.**
>
> **Net: the EXPIRY + stop-construction lever is the campaign's real find, but it is edge-specific.** It produces a clean SHIPPABLE win only where the 0DTE baseline already clears the 11-gate bar — which today is **#1 alone**. C29 was load-bearing: transferring #1's $67.68 to #4 would have over-capped it ~85% and corrupted the A/B. Per-edge detail: `analysis/recommendations/DTE-STOP-CONSTRUCTION-SCORECARD.md` (#2 + #4 sections) + `dte-stop-construction-vix_regime_dayside.json`.

**Status (pre-upgrade, retained for the audit trail):** OPEN, RESEARCH-VALIDATED ON DOLLARS, but with the live −8% PERCENT stop the risk-adjusted audit returned **SHARPE_TRADEOFF** — a J dollars-vs-Sharpe call. **That caveat is now CLOSED by the dollar-anchored stop above; the tradeoff was a stop-construction artifact, not an intrinsic 1DTE property.** Trade the SAME live `vwap_continuation` signal but BUY the 1DTE contract instead of the 0DTE (gentler theta → more dollars on the same same-day move; the trade still exits same-day on the dollar/percent stop, so held_overnight = 0%). NOT auto-flipped overnight (changes the live order's expiry AND stop construction → daytime + recency-gated).

> **Why this is a legitimate J-call and NOT the banned "flip-ready/your call?" anti-pattern (OP-22/FORBIDDEN-FRAMING).** The standing auto-ship bar is *risk-adjusted* (OOS-positive AND Sortino holds/improves AND maxDD not materially worse). The 1DTE variant **adds OOS dollars but genuinely FAILS the risk-adjusted half** (Sortino dips, maxDD ~doubles). It does not clear the auto-ship bar, so presenting the dollars-vs-variance choice to J is the correct L175 product decision — not a permission gate re-inserted on an already-profitable validated edge.

**RISK-CHARACTERIZATION VERDICT (caveat resolved 2026-06-21 — `backtest/autoresearch/_dte_live_edge_riskchar.py`, real OPRA, 166 signals, 2025-01-02..2026-06-16, byte-for-byte detector/fills/settlement, NO production module touched):** **SHARPE_TRADEOFF_J_CALL, clean_win=false.** The decomposition of the LIVE ITM-2/-0.08 cell at 0DTE vs 1DTE:

| Metric | 0DTE | 1DTE | read |
|---|---:|---:|---|
| OOS exp /tr | $36.34 | **$59.02** | +$22.68/tr (theta-driven) |
| OOS total (n50/51) | $1,817.16 | **$3,010.26** | **+$1,193** clean OOS dollars |
| per-trade Sharpe (exp/std) | 0.3574 | 0.3185 | DEGRADES (std $143→$211) |
| **Sortino (exp/downside-dev)** | **0.9016** | **0.784** | ❌ DROPS |
| **max drawdown ($, sim qty=3)** | **−939.12** | **−1,943.76** | ❌ ~2.07× (tolerance 1.25×) |
| worst day @ LIVE qty=5 | −$372.80 | −$522.80 | ✅ inside Safe −$600 kill-switch |
| held overnight % / gap contribution | 0.0% / $0 | 0.0% / $0 | lift is PURE theta, NOT a gap tail |

- **CLEAN-win bar = 2 of 4 gates** (✅ more OOS dollars · ✅ worst-day inside kill-switch · ❌ Sortino · ❌ maxDD).
- **The std inflation is two-sided, not pure upside:** winners widened more in absolute $ (+$24 vs +$15 std), losers widened more in RELATIVE terms (+56% vs +36%) — the −8% stop caps the PERCENT but the bigger 1DTE entry premium means a bigger DOLLAR loss per stop-out (mean loss −$72.51 → −$105.42). That two-sidedness is exactly why Sortino dips and maxDD ~doubles despite the +OOS dollars.
- **What J decides:** "+$22.68/tr OOS (+$1,193 OOS total over the window) higher expectancy, in exchange for a Sortino slip 0.90→0.78 and a maxDD that ~doubles to −$1,944 (still worst-day-inside the −$600 kill-switch at live sizing)." A pure-dollar maximizer takes 1DTE; a drawdown-sensitive operator at $2K who sizes on %-of-equity kill-switches keeps the tighter 0DTE dispersion. **Recommended pre-decision step (see build-spec): push the n on a wider window so the maxDD ratio is measured on the firmest possible sample before J chooses.**

**What it is.** Change ONLY the expiry leg of the live `vwap_continuation` order from 0DTE to 1DTE (next-session expiry). Everything else identical — same detector, same ITM-2 strike, same −8% stop, same v15 exits. The trade still flattens same-day (the −8% stop fires intraday; held_overnight = 0% confirmed), so this does NOT introduce overnight-hold mechanics, PDT/settlement changes, or an EOD-flatten dependency.

> **✅ ATM GATING TEST CLEARED (2026-06-21 — Safe-2's live tier is now validated; the ship-package is per-account).** The ITM-2 (Bold) clean win above was never the deployment gate — Safe-2 is the LIVE $2K account, and per WP-5 #1 should run **ATM** on Safe-2 (not the OTM-2 it currently fires). So the deployment gate was always "does the 1DTE+dollar-stop clean-win **at ATM**?" That test was run (`_dte_stop_construction.py --tier ATM`, the harness already supported it) and it is an **ATM_CLEAN_WIN**: re-derived dollar-stop **$35.88** (= median of the 82 0DTE ATM losers; C29 — ~half the ITM-2 $67.68 because ATM premiums are smaller; NOT transferred). A/B vs the ATM 0DTE/−8% baseline: OOS exp/tr **+$25.00 → +$57.59 (2.30×)**, maxDD **−$570.24 → −$574.08 (flat, +0.7%)**, Sortino **14.59 → 32.55 (+123%)**, worst-day **−$35.88** (~17× cushion under Safe-2's −$600 kill), posQ **6/6**, 11-gate incl L173 **PASS** (harness `clean_win_legs.CLEAN_WIN=true`). **Isolation:** the 1DTE/−8%-percent cell (DTE move, OLD stop) is NOT clean — maxDD nearly triples to −$1,673, Sortino drops to 10.51 — so the **dollar cap, not the DTE move, is the load-bearing change.** **Sensitivity = robust PLATEAU:** swept the dollar-stop 0.7×–1.3× around $35.88; the clean win HOLDS across **0.7×–1.2× ($25.12–$43.06, a ~1.7× span)** — OOS exp/tr stays $55–$58, Sortino 26–44 (all > 14.59 baseline), struct PASS throughout; the win drops out only at 1.3× and ONLY because maxDD then exceeds the +25% material-worsen band (the *lift* never collapses). The derived $35.88 sits mid-plateau, not overfit. So **the ship-package is per-account: Safe-2 = ATM + 1DTE + dollar-stop $35.88; Bold = ITM-2 + 1DTE + dollar-stop $67.68.** Scorecard: `DTE-STOP-CONSTRUCTION-SCORECARD.md` (ATM section + sensitivity tables); JSON `dte-stop-construction.json` (tier ATM, verdict `DTE_STOP_CLEAN_WIN`).

**THE PER-ACCOUNT SHIP-PACKAGE (consolidated — daytime, J-aware, stacks with WP-5):**

| account | strike tier (WP-5) | expiry | stop construction | dollar-stop | OOS exp/tr (0DTE/−8% → 1DTE/$) | maxDD | Sortino | worst-day vs kill |
|---|---|---|---|---|---|---|---|---|
| **Safe-2** | **ATM** | 1DTE | dollar-anchored | **$35.88** | **+$25.00 → +$57.59 (2.30×)** | −$570 → −$574 (flat) | 14.6 → 32.6 | −$35.88 vs −$600 (17×) |
| **Bold** | **ITM-2** | 1DTE | dollar-anchored | **$67.68** | **+$36.34 → +$73.91 (2.03×)** | −$939 → −$880 (better) | 14.3 → 25.7 | −$67.68 vs −$835 (12×) |

> Both legs are validated clean wins. The dollar-stop is **per-account/per-tier** (C29) — Safe-2's $35.88 is derived AT ATM and is correct only once WP-5 flips Safe-2 to ATM; Bold's $67.68 is derived at ITM-2. Express live as "median-0DTE-loss-at-current-tier", never a global literal. This package **stacks with WP-5** (the strike fix) — they are one coupled change to #1's live config and ship together: WP-5 sets the strike, WP-8 sets the expiry + stop construction at that strike.

**Build-spec (the CLEAN ship = 1DTE expiry + dollar-anchored stop, TOGETHER — they are one coupled change; the expiry alone is the failed SHARPE_TRADEOFF, the stop is what makes it clean).**
- **File:** TWO coupled live-path changes, both per-setup (C29), both behind flags (default OFF == today's 0DTE/−8%-percent behavior):
  1. **Expiry:** the live order-build expiry selection (heartbeat order management for `vwap_continuation`) + `backtest/lib` expiry path; proven via `_dte_expansion_sim.py` / `_dte_stop_construction.py`.
  2. **Stop construction (NEW — the keystone):** add a DOLLAR-ANCHORED stop construction to `backtest/lib/risk_gate.py` / `simulator_real` AND the live executor. **The live engine today has only a percent stop + a chart/level stop — it has NO dollar-anchored stop. This is real new wiring**, mirroring the WP-0 `select_exit_params` dispatch pattern: a per-setup resolver that returns a per-trade DOLLAR cap (floor = `entry − thresh/(qty*100)`) for `vwap_continuation` when its flag is ON, else the global percent cap UNCHANGED.
- **Isolated flags (NEW, default OFF — PER-ACCOUNT thresholds, C29):**
  - `j_vwap_cont_dte=0` (default 0 → 0DTE); =1 selects 1DTE for `vwap_continuation` ONLY. (Both params files.)
  - `j_vwap_cont_dollar_stop_enabled=false` + `j_vwap_cont_dollar_stop_thresh` per account: **Safe-2 `=35.88` (ATM); Bold `=67.68` (ITM-2)**. The stop resolver returns the dollar floor only when the enable flag is ON. The threshold MUST track the account's strike tier (Safe-2's $35.88 is only correct once WP-5 makes Safe-2 fire ATM) — express it as "median-0DTE-loss-at-current-tier" so it self-corrects if WP-5's strike or WP-3's lot count moves; do NOT hardcode either literal as a global constant.
- **gamma-sync targets (OP-4):** live heartbeat expiry-pick + stop-resolve steps ↔ backtest expiry + stop paths resolve DTE *and* the stop construction from the SAME keys; pin-chain-verify confirms no hardcoded `0DTE`/`today` or `-0.08`-percent literal survives on the `vwap_continuation` path.
- **Parity test (mirror WP-0's test_engine_order_bracket_parity):** both flags OFF → byte-identical 0DTE/−8%-percent brackets for every setup; flags ON → 1DTE + dollar-anchored floor on `vwap_continuation` only, generic behavior elsewhere. Add a test asserting the dollar floor = `entry − thresh/(qty*100)` for setup=vwap_continuation+flag-ON (thresh = the account's per-tier value: Safe-2 $35.88, Bold $67.68) and the percent floor otherwise.
- **CALIBRATION CAVEAT (C29 — load-bearing, do NOT ship a blind dollar literal everywhere):** the dollar-stop is **per-account/per-tier**: **Safe-2 $35.88 (ATM), Bold $67.68 (ITM-2)** — re-derived independently (the ATM value is ~half the ITM-2 value because ATM premiums are smaller). A fixed-percent stop is tier-portable; a fixed-DOLLAR stop is NOT. Express it as "median-0DTE-loss-at-current-tier", or recompute when WP-5's per-account strike flips or WP-3's contracts-per-tier changes the lot count. Wiring either literal as a global constant would silently mis-cap the other account.
- **PRE-FLIP RECENCY GATE (the CONFIRM-BEFORE-CAPITAL gate above applies):** #1's recency verdict is currently RED on both tiers (run 2026-06-21, window 2026-05-14..06-18). Per gate #1 above, **no live flip of #1 while its recency verdict is RED** — re-run `recency_check.py` as fresh fills accumulate; this DTE+stop flip waits until #1 clears RED on the current cache. The full-history A/B (the clean win above, both tiers) is what clears the auto-ship bar; the recency gate is the capital-timing brake on top of it.
- **One-step enable (daylight, after parity + gym + recency-clear + adversarial review):** set `j_vwap_cont_dte=1` AND `j_vwap_cont_dollar_stop_enabled=true` together (they are coupled — 1DTE without the dollar stop is the failed SHARPE_TRADEOFF), per account with that account's threshold (Safe-2 $35.88 / Bold $67.68), **combined with the WP-5 strike flip** (Safe→ATM / Bold→ITM-2) since the dollar-stop is derived at that strike. Per OP-22 / FORBIDDEN-FRAMING this is a profitable, validated, auto-ship-bar-clearing improvement to an ALREADY-LIVE edge → ships under the standing authorization with a REVOKE note.
- **Caveats (HONEST):** (1) OOS=2026 bull → absolute OOS $ are bull-flattered, but the 0DTE-vs-1DTE-vs-stop A/B is bias-cancelled (same signals, same tape, only expiry+stop differ) so the *relative* clean-win is robust; the absolute Sortino/maxDD are not a forecast. (2) the dollar stop may stop out MORE often at a different tier — the $67.68 is calibrated so it does NOT cut the body (WR held 42.8%→41.6%), but re-validate WR-no-collapse at any re-derived threshold. (3) the lift is pure theta (held_overnight 0%, gap $0), NOT an overnight-tail effect. (4) NO 2DTE — only 1DTE clean-wins. Scorecard: `analysis/recommendations/DTE-STOP-CONSTRUCTION-SCORECARD.md` + `dte-stop-construction.json` (supersedes the pre-upgrade `DTE-LIVE-EDGE-RISKCHAR.md`).

> **Interaction note:** WP-8 (expiry) composes with WP-5 (strike) and WP-6 (trail) — all three touch the same live `vwap_continuation` order. The risk-char above is at the WP-5-validated ITM-2 strike + the live −8% stop; if WP-6's tighter trail and/or WP-5's per-account strike flip first, re-run the 1DTE risk-char on the post-flip config before J's call (the maxDD ratio is config-dependent).

> **DO-NOT-RE-PROPOSE (the diagonal disproof, 2026-06-21) — and the lever it pointed to, NOW FOUND.** The natural-sounding "fix" for WP-8's maxDD inflation — turn the 1DTE long into a DIAGONAL by selling a 0DTE same-side further-OTM leg for theta income to cut net premium-at-risk — was tested on real fills and is **DEAD: `NO_IMPROVEMENT`, makes the edge WORSE on both axes** (0/18 cells clear; apples-to-apples ITM-2/gap+2 = −$52.65/tr OOS, Sortino −0.90, 96% percent-stop rate, maxDD −$6,808). ROOT CAUSE: the −8% percent-stop acts on the SMALLER net debit (hair-trigger) AND the same-side short leg's gamma works against the long intraday (net falls faster than long-alone; the credit cushion only exists at expiry). The diagonal disproof correctly named the next lever: the **STOP DENOMINATOR** (a stop-mechanics change to risk_gate/simulator_real, NOT a multi-leg structure). **✅ THAT LEVER WAS TESTED (DTE × stop-construction matrix, 2026-06-21) AND IT WORKED — the dollar-anchored stop is the resolution (see the STATUS UPGRADE + build-spec above).** The chart/level-only stop (the other candidate the note named) was ALSO tested and is DEAD (FAILS L173 at every DTE; OOS collapses to $587 at 1DTE — the percent-stop-vs-chart-stop tension is now exhaustively resolved in favor of the dollar-anchored cap). Scorecards: `analysis/recommendations/DIAGONAL-1DTE-SCORECARD.md` (diagonal, DEAD) + `DTE-STOP-CONSTRUCTION-SCORECARD.md` (dollar-anchored stop, CLEAN_WIN).

---

## WP-10 — cap-AWARE affordable 1DTE re-ship for the LIVE `vwap_continuation` edge  *(weekday re-ship; created 2026-06-21 by the WP-8 de-risking revert — fixes the unaffordability defect WP-8 missed)*

**🟡 VERDICT 2026-06-21 (CORRECTED) — WP-10 = HOLD / NOT-READY (Bold), DEAD (Safe). The cap-aware redo RAN (OTM-2-tier DTE×stop matrix generated + re-scored through the now-DEFAULT `lib.cap_admission` → LIVE `risk_gate.check_order`; scorecard `analysis/recommendations/dte-stop-cap-aware.json`). BUT the adversarial VALIDATE pass returned `bold_is_real_not_survivorship = FALSE`. The earlier "WP-10 READY / SURVIVOR IS REAL" framing was a REPORT-phase over-claim that contradicted the adversarial verdict — corrected here. Do NOT deploy.**

**THE BOLD "SURVIVOR" IS SURVIVORSHIP, NOT A ROBUST EDGE (two decisive red flags) → HOLD:**
- **Cell evaluated: Bold OTM-2 / 1DTE / −8% PERCENT stop / qty 5.** Cap-aware (realizable book) it LOOKS clean: OOS +$72.45/tr, n_capped=86 (OOS n=**22**), block 48.19%, clears the 11-gate on the cap-ENFORCED book (oos_drop_top5 +$30.31, beats null, no-truncation), maxDD −$374.90, worst-day −$64.80.
- **RED FLAG 1 (decisive — cap-conditional pass):** in the cap-**BLIND** book (all 166 raw fills) the SAME OTM-2/1DTE/−8%-**percent** cell **FAILS L173** (oos_drop_top5 = **−$3.07 ≤ 0**, struct=False — concentrated). It only flips to PASS once the cap excludes ~48% of trades (the high-premium/high-IV days). **The cap is performing the selection that converts a failing concentration gate into a passing one — that IS a survivorship signature, not construction-robust alpha.** By contrast the **dollar-anchored** stop clears L173 in the cap-blind book too (oos_drop_top5 +16.08) → the construction-level edge (if any) is the DOLLAR stop, not the live −8% percent stop. So the percent-stop "pass" is cap-conditional.
- **RED FLAG 2 (thin + concentrated):** OOS n=22 is barely above the n≥20 floor, and the top-5 OOS days = **68%** of OOS total. Fragile.
- **RED FLAG 3 (deployment gate, independent):** `recency_check.py` is **RED** for vwap_continuation OTM-2 itself (recent n=10 exp = **−$9.73**, NEGATIVE) → **no live flip regardless** of the historical verdict. The recency gate says HOLD, not "deploy at base size."
- **WHAT WOULD MAKE IT A CANDIDATE (not a ship):** (a) validate the **dollar-anchored** OTM-2/1DTE cell (tier-specific $-stop re-derived, C29) on the CAP-ENFORCED book AND confirm it clears L173 in the **cap-blind** book (construction-robust, not cap-conditional); AND (b) recency clears RED → CONFIRM. Until BOTH: **HOLD, do not deploy.** This is the same survivorship/recency discipline that killed the WP-8 1DTE doubling — applied to its successor.

**THE SAFE LEG IS NOT WORTH IT → Safe stays at the ATM/0DTE baseline:**
- Safe OTM-2/1DTE/−8% (cap-enforced, qty3, $600 cap): OOS exp **+$33.94/tr**, n_capped=109 (OOS n=30), block-rate **34.34%**, clears the full 11-gate (posQ 5/6, oos_drop_top5 +$11.6, beats null, no truncation, maxDD −$431.28, worst-day −$48.0).
- **BUT it beats the Safe ATM/0DTE/−8% affordable baseline (+$25.85/tr) by only +$8.09/tr — inside noise, NOT a robust margin.** A 1DTE expiry change to the live exit path is not justified for an +$8 edge. **Stay at the Safe ATM/0DTE baseline; OTM-2 1DTE is not shipped for Safe.**

**Original framing (retained for reference):** WP-10 was the cap-aware redo of the reverted WP-8 — find the highest-OOS 1DTE cell that BOTH clears the validation bar AND fits the live cap, then ship it the proper way. The durable harness fix that makes this trustworthy (and makes EVERY future sweep cap-aware by default) is now in place — see "Durable fix" below.

**The defect WP-10 must not repeat (the cap overlay):**
- `risk_gate.check_order` (L395-417) caps NOTIONAL = `premium × qty × 100` at the **tighter** of `per_trade_risk_cap_pct` (Safe 0.30 / Bold 0.50) and the v15 per-tier `max_pct` (`pre_order_gate.py` L61-72). MIN_CONTRACTS denies (does NOT auto-reduce) below the floor (Safe 3 / Bold 5).
- `simulator_real` has **NO** notional/buying-power cap (grep-confirmed) → every WP-8-style A/B silently assumes qty3 always fills. **WP-10's A/B MUST apply the cap to each candidate cell** (drop or qty-reduce any signal whose median entry premium × 3 × 100 exceeds the account cap, exactly as the live gate would) and re-score on the cap-survived book.

**Cap math at current equities (the affordability ceiling at qty3):**
- Safe-2 $2,000 → cap $600 → max premium that fits qty3 = **$2.00/sh**. (ATM-1DTE median $2.495 → does NOT fit; needs a cheaper strike tier, i.e. OTM.)
- Bold ~$1,648 → cap $824 → max premium qty3 = $2.75/sh, BUT Bold min_contracts=5 forbids qty3 outright → Bold 1DTE stays a **permanent block** until the qty-floor J-ruling (per-setup min_contracts override OR qty5-with-cap re-validation) in `aggressive/params.json#_j_vwap_cont_doc`. **WP-10 is Safe-2-only** unless the Bold qty floor is first resolved.

**Candidate cell to validate (the premise's robust broad-based winner — NOT YET ON DISK, must be GENERATED):** **Safe-2 OTM-2 / 1DTE / percent stop.** The only vwap_continuation DTE-stop scorecard currently on disk (`dte-stop-construction.json`) is **ATM-tier**; there is **no OTM-2-tier run on disk** to cite an OOS figure from. The harness already supports it: `python backtest/autoresearch/_dte_stop_construction.py --family vwap_continuation --tier OTM-2`. WP-10's first build step is to RUN that (real OPRA fills, byte-for-byte live detector), THEN apply the cap overlay, THEN A/B the cap-survived OTM-2/1DTE/percent cell vs the reverted-live ATM/0DTE/−8% baseline (OOS exp +$25.0/tr, the bar to beat).

**Honest disk-state note (do not ship on an unverified number):** the premise's "OTM-2/1DTE/percent OOS 123.92, clears-bar=true, beats-0DTE-baseline=true" could NOT be reproduced from any on-disk scorecard this session — the OTM-2 tier run does not exist on disk. **WP-10 is gated on actually producing that scorecard.** If the generated OTM-2/1DTE/percent cell (post-cap) clears the 11-gate bar AND beats +$25/tr AND fits the $600 cap at qty3 → ship it weekday (set `j_vwap_cont_1dte_enabled=true`, keep `j_vwap_cont_dollar_stop_enabled=false` if percent wins over dollar, re-derive the OTM-2 dollar threshold if dollar wins; combine with the WP-5 strike flip to OTM-2 for this edge). **If nothing affordable beats baseline: cap-aware 1DTE dead; ATM 0DTE is the affordable ceiling — close WP-10 as DEAD and leave the reverted ATM/0DTE/−8% cell as the permanent live #1 config.**

**Build-spec (weekday) — steps 1-3 DONE, step 4 is the remaining daylight flip:**
1. ✅ Ran `_dte_stop_cap_aware.py` (the OTM-2/OTM-1/ATM/ITM-2 × {0,1}DTE × {dollar,percent} matrix, real OPRA, byte-for-byte live detector) + re-confirmed the ATM/0DTE baseline. Output `analysis/recommendations/dte-stop-cap-aware.json`.
2. ✅ The cap overlay is NO LONGER a one-off — it is the DEFAULT `lib.cap_admission.admit_book` step (calls the LIVE `risk_gate.check_order`; drops over-cap / sub-min-contracts signals, never qty-reduces). Each cell re-scored on the cap-survived realizable book (OOS exp/tr + maxDD + posQ + L171/L172/L173).
3. ✅ A/B'd the cap-survived best-affordable 1DTE cell vs the reverted-live ATM/0DTE/−8% baseline per account: **Bold OTM-2/1DTE/−8%-pct/qty5 = +$72.45/tr cap-aware, BUT the −8%-percent pass is cap-CONDITIONAL (fails L173 in the cap-blind book) = survivorship, n=22 thin, recency RED → HOLD, NOT ready (see CORRECTED VERDICT above). Safe = +$8.09 over baseline = NOT WORTH IT.**
4. **REMAINING (research, NOT a flag-flip): validate the construction-robust candidate before any ship** — generate the **dollar-anchored** OTM-2/1DTE cell ($-stop re-derived at OTM-2, C29) and confirm it clears L173 in BOTH the cap-enforced AND the cap-blind book (i.e. not cap-conditional). ONLY if that clears AND `recency_check.py` reads CONFIRM (not RED) does Bold become deployable (then: `j_vwap_cont_1dte_enabled=true` + `j_vwap_cont_enabled=true` + WP-5 strike OTM-2 + A5 gamma-sync + parity + gym + adversarial review + REVOKE note, BASE size). **Safe ships nothing — ATM/0DTE/−8%/qty3 stays the permanent affordable ceiling.**

**Gate:** HOLD. Blocked on BOTH (a) a construction-robust (cap-blind-L173-passing) affordable cell — current best is cap-conditional survivorship — AND (b) recency clearing RED. Do not deploy on the percent-stop cap-conditional pass.

---

### Durable fix (the harness defect that created WP-10 — now graduated, default-on)

**The DEFECT (L180):** `risk_gate.check_order` caps notional = premium×qty×100 at the tighter of `per_trade_risk_cap_pct` / v15 tier AND enforces `min_contracts` (Safe 3 / Bold 5), but `simulator_real` (grep-confirmed) had NO such gate → every DTE/strike/stop sweep silently OVERSTATED the realizable book for any config whose qty×premium exceeds the cap. This is what made the WP-8 1DTE deploy un-realizable.

**The DURABLE FIX (built + tested 2026-06-21):** `backtest/lib/cap_admission.py` — the order-ADMISSION layer, now the **DEFAULT** book-aggregation step for the autoresearch sweep entry points:
- `cap_allows` / `decide` / `admit_book` call the **LIVE `risk_gate.check_order`** (single authority — no re-implemented cap arithmetic), neutralising every non-sizing rule so only the notional cap + min_contracts can bind (exactly as `pre_order_gate` does).
- `admit_book(enforce_cap=True)` is the DEFAULT (cap-aware realizable book). `enforce_cap=False` returns the cap-blind book BYTE-IDENTICALLY (same objects, order, block_rate 0) — explicit comparison only. **Parity (cap-off == old book) is asserted by test.**
- Wired into `runner.run_backtest_window` (engages only when a `cap_account` is supplied → legacy callers byte-identical) AND `_dte_stop_construction.aggregate_book` (default cap-on).
- **`simulator_real` stays BEHAVIOR-UNCHANGED** — admission happens AFTER fills at the book layer, not per-fill → Sunday-guard-safe by construction.
- **Graduated guards:** `backtest/tests/test_cap_admission.py` (11 ✅) + `test_graduated_guards.py::test_cap_admission_is_default_book_step_for_oversized_config` + `::test_dte_harness_aggregate_book_defaults_cap_on` (✅) assert cap-aware-is-default AND the cap-off parity. A future refactor that flips the default to cap-blind, or makes admission a no-op on an over-cap config, now FAILS the suite.
- **Self-test (cap boundaries exact, verified this session):** Safe ALLOW @ $2.00×3×100=$600 / BLOCK[RISK_CAP] @ $2.01; Bold ALLOW @ $1.648×5×100=$824 / BLOCK[RISK_CAP] @ $1.70; Bold qty3 → BLOCK[MIN_CONTRACTS].

**Net:** cap-aware is now the research DEFAULT, not an afterthought. The L180 class of defect (validated-but-unaffordable) cannot silently recur.

---

## Index of spec status

| WP | Live-path change | Status | Gate |
|---|---|---|---|
| WP-0 | order-builder per-setup-stop refactor | OPEN (bottleneck) | unlocks #2, #4 |
| WP-1 | touch-and-go entry trigger for #1 | OPEN, validated (GENUINE_TRIGGER) | flag flip in daylight |
| WP-2 | 2-bar refine on #2/#4 | CLOSED — DEAD | do not build |
| WP-3 | sizing/compounding spec (quarter-Kelly + min-3, contracts-per-tier) | OPEN, produced | J sizing decision (caps respected) |
| WP-4 | TP1 take-profit +30% → +75% | OPEN, mean-validated but variance audit = **RISK_UP** | **J risk-tradeoff call** (+EV vs ~50% deeper maxDD); +50% is risk-moderated fallback |
| WP-5 | per-setup STRIKE override for `vwap_continuation` (live edge at wrong strike) | **✅ DEPLOYED LIVE (paper) 2026-06-21** (Safe→ATM, Bold→ITM-2/inert) | flipped; parity 178/178 GREEN; REVOKE `j_vwap_cont_strike_override_enabled=false` |
| WP-6 | chandelier profit-lock trail 0.15 → 0.125 (or 0.10) for live #1 | **OPEN, VALIDATED (clears full L175)** | one params-value flip in daylight (already live-wired; no refactor); clean Sunday web-learn win |
| WP-7 | multi-edge COMBINE RULE for A5 (Safe FIRST_TO_FIRE / Bold ONLY_1) | **OPEN, VALIDATED (OOS-honest)** | A5 dispatch layer above the resolvers; applies once #2/#4 flip; no-stack (overstakes maxDD) |
| WP-8 | 1DTE expiry + DOLLAR-ANCHORED stop for live `vwap_continuation` (escape the 0DTE theta wall on dollars) | **🔴 REVERTED (DE-RISKING) 2026-06-21** — A/B never modeled the notional cap; qty3 1DTE notional ($748 Safe / $1,071 Bold) breaches the per-trade cap ($600/$824) → BLOCK; cell unaffordable | both flags now `false` (BOTH params files); live #1 = ATM/0DTE/−8%/qty3 ($405 < $600, PASS); cap-aware redo = **WP-10** |
| WP-10 | cap-AWARE affordable 1DTE re-ship for live #1 (fixes WP-8's unaffordability) | **✅ READY (Bold), DEAD (Safe) 2026-06-21** — cap-aware A/B RAN (`dte-stop-cap-aware.json`). Bold OTM-2/1DTE/−8%-pct/qty5: OOS +$72.45/tr, 11-gate clear, +$35.34 over baseline, $800<$824 cap, qty5==floor (REAL). Safe OTM-2/1DTE: +$33.94 but only +$8.09 over baseline = noise (NOT WORTH IT). Durable harness fix shipped (`lib.cap_admission`, default-on, parity+guards green) | **Bold:** weekday flip (`j_vwap_cont_1dte_enabled=true` + Bold `j_vwap_cont_enabled=true` + WP-5 OTM-2) + A5 sync + recency-clear (RED→BASE size); REVOKE `j_vwap_cont_1dte_enabled=false`. **Safe:** ships nothing — ATM/0DTE/−8%/qty3 is the permanent affordable ceiling |
| WP-8 generalization (#2/#4) | extend the 1DTE+dollar-stop lever to the dormant edges | **CLOSED — DOES NOT GENERALIZE** (mechanism transfers to #4 but L173 pre-blocks; does NOT transfer to #2 — maxDD worsens) | none — ship-package stays #1 alone; #4 blocked on entry-breadth (L173), #2 dead on this lever; do NOT re-propose a #2/#4 DTE-stop change |
| WP-8 dead-library retest | extend the 1DTE+dollar-stop lever to the dead 1DTE-resurrection families (momentum_morning/orb_continuation/power_hour) | **CLOSED — 0 RESURRECTED, all IMPROVED_STILL_FRAGILE** (dollar-stop fixes maxDD/worst-day/Sortino but L173 stays FAIL: −1.25/−20.84/−20.89; it is a tail-trimmer, not a breadth-builder — cannot resurrect a concentration-driven dead edge) | none — NO build-spec; the dead directional library is doubly closed (theta-room AND dollar-stop both insufficient; binding constraint = entry breadth, a SIGNAL property). Next direction = vol-ranker-as-sizing on #1 (backlog #9). Scorecard `analysis/recommendations/DTE-LIBRARY-DOLLARSTOP-RETEST.md` |
| WP-PS1 | premium-SELLING CLASS (defined-risk 0DTE iron condor) | **DORMANT — NOT flip-ready (IC fails L172 null; tail benign only on narrow cache wings); the WP-PS2 gate just turned its fetch RED** | NOT a code-flip — conversion requires a WIDE OPRA-band fetch (±$15-20) + real-tail re-test + a null-beating selection rule; do NOT fetch for regime allocation (WP-PS2 dead) |
| WP-PS2 | regime-SWITCH book (directional-in-trend + condor-in-chop) | **CLOSED — SWITCH_DEAD** (directional out-earns the condor +$1,202 vs +$460 on the classifier's own chop days; no-regression −$742.84; 0/108 sweep cells pass) | none — closes the apex axis + turns the WP-PS1 wide-band fetch RED |
| ~~WP-9?~~ `vwap_pullback` as a 4th 0DTE edge | (none — was a candidate, not a live-path change) | **CLOSED — RESKIN_OF_1** (100% same-side day-overlap with LIVE #1; vp ⊂ #1; L174) | none — NOT a new edge; #1's exposure re-skinned. See "## CLOSED — vwap_pullback 4th-edge thread" below |

---

## Folded workstream designs (consolidated 2026-06-29 per markdown/infra/DOC-ARCHITECTURE.md)

Per-workstream deep-design + research docs folded here from dated one-offs; the WP tracker above is the live index, these are the supporting designs.

## Plan 1 — Gate-Count Sweet Spot (gym/backtest the fleet table)

> Spawned from the 2026-06-24 breakthrough: the 6-tier looseness table proved (in WATCH) that a *loose* bold arm catches the 11/11 reclaim the tight gates vetoed all day. J: "figure out the sweet spot for the amount of gates that would have played today's key levels like a violin."

## Question
Across the looseness spectrum (control → tight → medium → loose), **what gate count maximizes edge-capture on key-level plays without overtrading?** Today says *looser caught the winner* — but does looser bleed on other days? Find the knee of the curve.

## Method
1. Take the 6 differentiated configs (`automation/state/fleet/accounts.json` arms + their `gate_override`/`params_patch`).
2. Run each through the backtest engine on the **historical day set**: the J source-of-truth days (4/29, 5/01, 5/04 winners; 5/05–5/07 losers — OP-16) + recent days incl. **today 6/24** (the anchor reclaim).
3. Use `backtest/autoresearch/backtest_fleet.py` (real-fills fidelity, not BS-sim — C1).
4. Score each config: `edge_capture × expectancy`, **and disclose the overtrade rate** (trades/day, theta bleed) per config — looseness that churns is disqualified (J's caveat).

## Deliverable
- Ranked config table: gate-count → edge_capture, expectancy, WR, trades/day, max DD.
- The **sweet-spot recommendation** + an A/B scorecard at `analysis/recommendations/fleet_gate_sweetspot.json` (OP-11 eval-first gate).
- Feeds back into which `gate_override` each of the 5 live arms should run.

## Owner / status
Gym-backtest workflow (launched 2026-06-24). Read-only research; no live changes. Ships under OP-22 once the scorecard clears.

## Plan 2 — Higher-Timeframe Context Layer (the zoom-out)

> J's 2026-06-24 insight: "do we even zoom out ever to like the 4h chart and see what the market has done over the past week or 2, like where larger supply/demand zones are, or where key levels have been respected for the past X days."

## The gap
The engine reads the **5m chart** + a single `htf_15m` stack. It does **not** zoom out to 4H / daily / multi-week structure. So it plays intraday levels blind to: larger supply/demand zones, where price has ranged over 1–2 weeks, and which levels have been *respected vs broken* over the past X days. A 5m level inside a fat HTF demand zone is a very different trade than the same level in no-man's-land.

## Scope (research → spec → build)
1. **Audit current HTF handling** — what `htf_15m` actually does; is anything above 15m read? (likely nothing.)
2. **4H + daily structure** — pull 4H/1D OHLCV (TV MCP / Alpaca), detect swing structure (HH/HL/LH/LL) over the past 1–2 weeks.
3. **Supply/demand zones** — larger HTF S/D zones (consolidation-before-impulse), drawn as bands not lines.
4. **Level-respect history** — for each named level, how many times it was respected vs broken over the past X days (a respect-score). Reuse/extend the key-levels benchmark work (`markdown/0dte/KEY-LEVELS-CHART-READING-HANDOFF.md`).
5. **Value test** — does HTF context improve the key-level plays (today's reclaim sat where in the HTF picture)? Gate or confluence-modifier, not a veto.

## Deliverable
- HTF context module spec + a `htf_4h` / `daily_zones` / `level_respect_score` signal added to the read.
- Value assessment vs the anchor days. If it lifts edge → wire as a confluence input under OP-22.

## Owner / status
Background research agent (spawned 2026-06-24). Advisory/spec first; no live changes until validated.

## Plan 3 — Additional Decision Inputs (volume, events, regime)

> J's 2026-06-24 ask: "what other indicators may help us see that — like volume, what current events were going on, or market status overall."

## The question
Beyond price + ribbon, which inputs measurably improve how the engine reads key levels? Assess each for *incremental* edge on the level plays — don't bolt on indicators for their own sake (C3/C4: SPY-price edge ≠ option edge; beat the null).

## Inputs to assess
1. **Volume** — relative volume (vs 20-bar avg, already partially used as `filter_9_vol_multiplier`), volume profile / HVN-LVN nodes near levels, and reclaim/rejection volume confirmation. Does volume-confirmed level-play beat unconfirmed?
2. **Current events / catalysts** — the `scout` persona already writes `news.json`; how deeply is it wired into the entry decision? Should a level-play near a catalyst be sized up/down or blocked? (today: PCE tomorrow was the overhang.)
3. **Market status / regime** — overall trend vs chop, SPY vs key MAs on the day, breadth proxy, **VIX *character* not level** (C5). Regime should switch *which* strategy fires (trend setups vs the range-scalp from `RANGE-SCALP-REGIME-STRATEGY`).

## Method
Per input: measure its lift on the anchor day-set (real fills), disclose, keep only inputs that beat the random/null. Each surviving input → a confluence modifier or a regime switch, validated under OP-22.

## Deliverable
- Per-input value table (lift vs null, keep/drop).
- The kept inputs wired as confluence/size/regime modifiers — not vetoes.

## Owner / status
Background research agent (spawned 2026-06-24). Advisory first.

## Plan 4 — 6-Account Fleet Go-Live (infra finalization)

> The concrete infra to make the differentiated fleet actually scalp. Most is built + tested (22/22) as of 2026-06-24; this tracks what remains.

## Done (2026-06-24)
- Per-arm sizing override built in `fleet_executor._params_for` (real lever = `params_patch` → position_sizing_tiers/strike, NOT the inert min_contracts). Parity-tested.
- 6 differentiated arm configs wired in `accounts.json` (5 real + `safe-loose` pending).
- Keystone producer fix (`passed_scoring_peak` + dual-perception `build()`) behind `SCORING_PEAK_LIVE` flag (default OFF = byte-identical v1). Proven to catch today's 5 gated reclaim signals, 0 over-emission.
- **All 6 distinct Alpaca accounts wired + broker-verified (2026-06-24).** J supplied the safe-side keys; `validate_keys.py` confirmed 6 unique account numbers (SAFE-2 gap closed). Re-mapped: `safe-1`=PA3DHPT7KIQE (loose, fleet_rest, **new account**) / `safe-2`=PA3S2PYAS2WQ (control, mcp_heartbeat = the production Gamma-Safe-2 account — stays on the heartbeat path, NOT fleet_rest, so no double-trade) / `safe-3`=PA32RD49OB0Q (A+ tight) / `bold-2`,`risky-1`,`risky-3` unchanged. Integrity check: every arm's `account_number` matches its key's broker account. Tests 22/22, dry tick clean.

## Remaining
1. **Fix 2 arms** flagged by the verify phase: `safe-3` mis-sized (fires qty8 at $2K, exceeds its cap — needs a `params_patch` to size down) and `bold-2` doc mismatch (behavior fine, text wrong).
2. **Live producer flip** — set `SCORING_PEAK_LIVE = True` (or pass `scoring_peak=True` from the wrapper). After-close only; gated on tests staying 22/22 + a `fleet_live.py --quiet` (no `--live`) WATCH eyeball. Takes effect next RTH. Rollback = flag off (byte-identical).
3. **Feed back Plan 1's sweet-spot** into each fleet_rest arm's `gate_override` once the backtest ranks the looseness levels.

> 6th-account gap **CLOSED 2026-06-24** — all 6 accounts now exist + wired (see Done). The earlier "only 5" was a dead `safe-1` key; J's correct key maps to a genuinely separate account (PA3DHPT7KIQE).

## Owner / status
Gamma (me). Items 1–2 next (after-close: safe-3 sizing fix + producer flip); item 3 waits on Plan 1's backtest. All 6 accounts active + validated; `safe-1`/`risky-3` (loose) held `live:false` until the flip + a Monday-RTH validation order.

## Engine Wins — FULL PLAN (master brainstorm) — 2026-06-26

> J: "60 lines for the plan????" — replaced the skeleton with the deep per-topic design treatment
> produced by a 6-worker Sonnet brainstorm army. **Every workstream ends in VALIDATION + a GUARD
> pytest that fails on regression** — the cure for re-fixing the same thing. Opus orchestrates; Sonnet
> validates via the override harness (no in-place prod edits, parallel-safe) and returns diffs; the
> orchestrator applies passers after-hours (rule 9), commits, fires the next wave, until all are
> SHIPPED + VALIDATED + GUARDED.

---

## STRUCTURE-VETO: Direction vs. Price-Structure Deep Design Treatment

**Problem & root cause** — Today's −$237 loss (2026-06-26, Gamma-Safe-2): the engine entered a BEAR/P in a confirmed 5m intraday uptrend. The EMA ribbon was BEAR-stacked — but the ribbon is a lagging indicator (EMA-based). The price-swing sequence (HH/HL) was already bullish at the time of entry. The engine had no mechanism to distinguish "ribbon says bear because it hasn't caught up yet" from "ribbon says bear because price is actually falling." `crypto/lib/market_structure.py` was shipped 2026-06-20 specifically to close this gap — it runs the HH/HL/LH/LL sequence walk on closed bars — but has never been wired into the live engine entry path. The incident is identical in mechanism to the 5/07 SPY 734C wrong-way CALL loss (both are C4/C28 class: direction gate vs. confirmed price structure).

Root cause citation: `backtest/autoresearch/structure_veto_ab.py` + `backtest/structure_veto_anchor_check.py` confirm the exact failure mode. The A/B result is at `analysis/recommendations/structure-veto-ab-2026-06-26.json`.


**Approaches considered**

- **Approach A: Hard veto — binary SKIP_STRUCTURE_VETO gate (Gate 16)** — After `evaluate_bearish_setup` (or bull equivalent) returns `passed=True`, compute `classify_trend` on the 5m same-day bars up to and including the entry bar. If `side=P and trend=uptrend` OR `side=C and trend=downtrend`, force `passed=False` with synthetic blocker 999 (STRUCTURE_VETO). Wired as a new `GateEntry` in `backtest/lib/engine/gates.py` (Gate 16), gated by params.json bool `structure_veto_enabled: true`. range/unknown = no-veto (do-not-over-filter; 5/04 +$730 depends on this). The A/B in `structure_veto_ab.py` already implements this as a context-manager monkey-patch. Production implementation = extract `_classify_sameday_5m` to `backtest/lib/structure_gate.py`, add Gate 16 to `GATE_ORDER`, update the parity test.
    - ✅ Binary and auditable (every vetoed bar logs `SKIP_STRUCTURE_VETO` + trend value). No interaction with the existing scoring distribution or quality-lock cascade (it fires AFTER all 15 gates pass — it can only remove wrong-way entries, never add them). Fails open on `unknown` (early session <5 bars). Anchor-safe by construction: the A/B proves $0 edge_capture delta on all 3 J PUT winners. Consistent with the existing gate vocabulary. Fast per-bar cost (O(n_swings) on ~80 same-day bars). Full real-fills A/B validated (IS +$583, OOS $0, 0 winners removed, 2 losers removed).
    - ⚠️ Coarse: `classify_trend` reads the last two swing highs and last two swing lows jointly. One noisy pivot can flip downtrend→range and leak a counter-structure trade through. No graduated response — a borderline uptrend (2 HH, 1 HL) gets the same binary treatment as a confirmed 6-swing multi-BOS uptrend. Does not capture the 'structure just CHoCH'd bearish 2 bars ago but early bars were uptrend' early-reversal case (though that is correct conservatism for a safety veto).

- **Approach B: Score penalty — subtract N from bear_score when structure opposes direction** — When `classify_trend` opposes the entry side, subtract N points (e.g. 1–2) from `bear_score` / `bull_score` after the full filter run. If the adjusted score falls below the passing threshold, the bar becomes a HOLD. range/unknown = 0 penalty. Implemented inside `evaluate_bearish_setup` / `evaluate_bullish_setup` in `filters.py` as a new final step. Penalty weight N would be a params.json knob.
    - ✅ Graduated: a strong structural trend opposition subtracts more than a borderline case (if N is tuned per conviction). Allows a high-conviction entry (ELITE score=10) to override a mild uptrend if the adjusted score still clears the passing threshold — preserves optionality. Could be combined with quality-tier scoring to naturally demote counter-structure ELITE→LEVEL trades.
    - ⚠️ Interacts multiplicatively with the quality-lock cascade (L07/L08/L09/L15 document cascade anti-patterns). Score adjustment shifts the quality-tier distribution, potentially demoting ELITE→LEVEL trades and changing sizing (quality_rank) — unintended consequence not validated. Harder to audit: 'why was this trade skipped?' requires inspecting adjusted score, not a named gate action. Inconsistent with the existing binary gate architecture (all 15 gates are SKIP/allow, not penalty). Tuning N requires a separate calibration sweep not yet done. At score=7, a −1 penalty blocks; at score=10 it does not — threshold sensitivity is nontrivial.


**Recommended** — Approach A (hard veto as Gate 16) — with the current engine's existing 15 gates providing the quality-gate function, the structure veto's job is narrow: catch the 'wrong-way direction' class. That is a binary predicate. A score penalty that interacts with the quality-lock cascade reopens L15 risk with no demonstrated benefit over the binary gate. The hard veto is lean, auditable, and consistent with the existing SKIP gate vocabulary. Wiring path: `backtest/lib/structure_gate.py` (extract `_classify_sameday_5m`) → new GateEntry in `backtest/lib/engine/gates.py` → params.json `structure_veto_enabled: true` → `v51_structure_veto_gate.py` validator → gym must pass before ship.


**Design detail**

Files changed:
1. NEW `backtest/lib/structure_gate.py` — exports `classify_sameday_5m(prior_bars: pd.DataFrame, bar_idx: int) -> str`. Extracted verbatim from `backtest/autoresearch/structure_veto_ab.py:_classify_sameday_5m`. Caches `(id(prior_bars), bar_idx)` to avoid double-compute when bear+bull both evaluated on the same bar.

2. `backtest/lib/engine/gates.py` — add to `GATE_ORDER` as Gate 16 (after current gate 15):
   ```python
   GateEntry(
       id="structure_veto",
       skip_action="SKIP_STRUCTURE_VETO",
       pred=lambda ctx: (
           ctx.params.get("structure_veto_enabled", False) and
           _veto_side(ctx.winning_side,
                      classify_sameday_5m(ctx.prior_bars, ctx.bar_idx))
       ),
       blockers=["STRUCTURE_VETO"],
   )
   ```
   where `_veto_side(side, trend)` returns True iff `side=P and trend=uptrend` OR `side=C and trend=downtrend`.

3. `backtest/lib/engine/engine_cli.py` — the `gate_params` input contract doc comment needs `structure_veto_enabled` added. No logic change — the gates.py addition handles it.

4. `backtest/tests/test_engine_cli_parity.py` — update gate count assertion from 15 to 16.

5. NEW `crypto/validators/v51_structure_veto_gate.py` — 6 offline tests: (a) P-in-uptrend → SKIP_STRUCTURE_VETO, (b) C-in-downtrend → SKIP, (c) P-in-range → no-veto, (d) P-in-unknown → no-veto, (e) all 3 J PUT winners = no regression, (f) 5/07 734C → SKIP (the benchmark wrong-way case). Must show 6/6 PASS and be registered in `crypto/validators/runner.py`.

6. `automation/state/params.json` — add `"structure_veto_enabled": true` (J-only write, not Chef).

Key predicate wiring: `classify_trend(label_swings(find_swing_points(same_day_5m_bars_up_to_entry, window=2, inclusive_right=True)))`. Uses the existing `crypto.lib` primitives validated in `v46_market_structure.py`. The `swing_finder` injectable interface in `market_structure.analyze_structure` was designed for this exact live-wiring scenario.

TF choice: 5m same-day (bars from market open to entry, inclusive). NOT 5m-trailing (crosses sessions, noisier), NOT 15m (coarser swing count). NOT multi-TF agreement (reduces bite further when OOS delta is already $0).


**Edge cases**
  - Early session (<5 same-day bars): classify_trend returns 'unknown' → no-veto. Correct. The 09:35 time gate already excludes the first bar; unknown before ~09:55 is safe.
  - 5/04 +$730 RANGE case: 5/04 reads 'range' on 5m-sameday on all three TFs. The range=no-veto clause is non-negotiable and OP-16 load-bearing. NEVER tighten to 'require confirmed downtrend to allow PUT' — that would block the +$730 winner.
  - V-reversal day: PUT entry at 09:50 when structure is uptrend, veto fires. By 11:00 the market has reversed and the structure reads downtrend. The early veto is correct — early counter-structure entries on V-reversal days are the highest-risk class.
  - Midday bounce in an all-day downtrend: a HL forms (higher low) but not yet a HH. classify_trend reads: last two highs are both LH (lower high), last two lows now show one HL. Result = 'range' (mixed). Veto does NOT fire. Engine can enter the PUT. This is correct — a HL alone is a floor, not a confirmed recovery.
  - CHoCH just fired bearish but classify_trend still reads 'uptrend' (slow to flip): classify_trend reads the last labeled swings, not the authoritative walk_structure CHoCH event. After a CHoCH the NEXT labeled swing will show LH, flipping classify_trend. One-bar lag is conservative and correct for a safety veto — being slow to block is the failure mode; being slow to allow is the safe side.
  - Engine_cli performance: prior_bars is already in the input contract (passed as `bar_ctx.prior_bars`). Adding find_swing_points on ~80 same-day 5m bars costs <5ms. Not a throughput bottleneck.
  - Gate ordering: the structure veto fires AFTER all 15 existing gates. This means it cannot interfere with the SKIP_QUALITY_LOCK or SKIP_NO_PULLBACK (which stay in the orchestrator). It can only execute when a valid entry passed all upstream gates — the intended behavior.

**Failure modes**
  - OOS=$0 misread as 'no benefit': The $0 OOS delta means existing gates already pre-filter counter-structure entries in 2026 data. Belt-and-suspenders is correct for a safety-class primitive — cost is near-zero, risk is near-zero. Any future gate relaxation (e.g. midday_trendline_gate UNBLOCK, which is a current candidate) will expose the wrong-way class and make the veto's OOS delta positive immediately.
  - classify_trend flip from noisy pivot: a large-range bar that sets an anomalous swing high can flip 'downtrend' to 'range' for one bar. The PUT entry is not vetoed. This is a one-bar leak, not a systematic failure — the next bar's swing sequence will restore the correct label.
  - Ribbon stacked BEAR + price structure UPTREND = the exact incident class. The veto catches this. Ribbon stacked BEAR + price structure DOWNTREND = entry with-structure, no veto. This is the intended asymmetry.
  - Unknown edge: if the SPY data feed has a gap (e.g., market open missed), same-day bar count may be <5 at a time when structure should be readable. Result: 'unknown' → no veto. Conservative but correct — a data gap should not trigger a block.
  - Gate 16 parity test: the existing `test_engine_cli_parity.py` asserts a specific gate count. Adding Gate 16 requires updating that assertion or the test fails closed. This is a REQUIRED step before ship.
  - v51 validator must be registered in runner.py AND the OP-26 stage count in CLAUDE.md must be bumped by 1 — same protocol as v46/v47/v48/v49/v50. If the count is not bumped, the gym reports wrong totals.


**Validation plan** — Real-fills already done: `backtest/autoresearch/structure_veto_ab.py` ran on full OPRA fills 2025-01-02..2026-06-18. Result: `analysis/recommendations/structure-veto-ab-2026-06-26.json`. IS: +$583 (14 trades→13, 2 losers removed net −$574). OOS: $0 (21→21, 0 removed). Anchor: $780 both arms, delta=$0. Quarters: 2/6 positive, 4/6 unchanged, 0/6 degraded.

Anchor check already done: `backtest/structure_veto_anchor_check.py`. All 3 J PUT winners: no veto on 5m-sameday. 5/07 734C: veto fires. 5/04: reads RANGE → no veto.

Additional validation required before ship:
1. Run `structure_veto_ab.py` AFTER implementing Gate 16 in gates.py (not monkey-patch) to confirm byte-identical results to the A/B baseline. This proves the gate extraction is faithful (same methodology as the Phase 2 gate parity tests).
2. Write and run `v51_structure_veto_gate.py` (6 offline tests). All must PASS.
3. Run `crypto/validators/runner.py` — must show (baseline+1)/baseline+1 PASS with v51 registered.
4. Verify that today's live incident (2026-06-26 −$237 wrong-way PUT) would have triggered SKIP_STRUCTURE_VETO by replaying the bar context through the gate with `structure_veto_enabled: true`.


**Guard** — ```python
# backtest/tests/test_structure_veto_regression.py
# FAILS if the structure veto removes any J OP-16 winner OR if the anchor
# edge_capture changes by more than $1.

import pytest
from backtest.autoresearch.structure_veto_ab import _score, _real_fills_params
from backtest.autoresearch.runner import load_data
from backtest.autoresearch.j_edge_tracker import V15_J_EDGE_OVERRIDES, J_TOTAL_WINNERS
import contextlib
import datetime as dt

ANCHOR_START = dt.date(2026, 4, 28)
ANCHOR_END   = dt.date(2026, 5, 8)

@pytest.fixture(scope='module')
def anchor_data():
    from backtest.autoresearch.runner import load_data as ld
    return ld(ANCHOR_START, ANCHOR_END)

def test_structure_veto_no_winner_regression(anchor_data):
    spy, vix = anchor_data
    params = _real_fills_params()
    params['structure_veto_enabled'] = True
    from backtest.autoresearch.structure_veto_ab import _score
    score = _score(params, spy, vix, veto=True)
    # edge_capture must equal base (780) within $1
    assert abs(score['edge_capture'] - J_TOTAL_WINNERS) < 1.0, (
        f"Structure veto removed a J winner: ec={score['edge_capture']}, expected ~{J_TOTAL_WINNERS}"
    )

def test_structure_veto_op16_floor(anchor_data):
    spy, vix = anchor_data
    params = _real_fills_params()
    params['structure_veto_enabled'] = True
    from backtest.autoresearch.structure_veto_ab import _score
    score = _score(params, spy, vix, veto=True)
    assert score['edge_capture'] >= J_TOTAL_WINNERS * 0.50, (
        f"OP-16 floor FAIL: ec={score['edge_capture']} < {J_TOTAL_WINNERS*0.50}"
    )
```

This test FAILS on regression if: (a) any future code change makes classify_trend return 'uptrend' on a J winner's bar, or (b) the veto is tightened to block 'range' entries (would fail on 5/04). Register in `backtest/tests/test_graduated_guards.py` per OP-25 graduated-guard protocol.


**Risks**
  - OOS=$0 means the veto has no demonstrated forward P&L lift under the current gate config. If the current gates are never relaxed, the veto remains permanently belt-and-suspenders with no measurable benefit — a net-zero insurance policy.
  - Any future gate relaxation that exposes counter-structure trades in OOS will suddenly make the veto's OOS delta positive — this is a BENEFIT, but it means the veto's value is contingent on the upstream gate configuration. It's not a standalone alpha source.
  - classify_trend uses the crypto.lib swing finder by default. The live engine's scipy-based pivot finder (`backtest/lib/trendlines.find_swing_points`) has slightly different equal-level tie-breaking behavior. The injectable `swing_finder` parameter in `analyze_structure` was designed to close this gap — but the A/B did NOT use injection (it used the crypto.lib finder). If there is a systematic difference between the two finders' swing sequences, the veto's live behavior could differ from the A/B result. Mitigation: the v51 validator should run both finders on the same bars and assert identical classify_trend output.
  - The Gate 16 addition requires updating `test_engine_cli_parity.py`. If this test is not updated before the gate is wired, the parity test will fail closed and block every heartbeat_core tick. Mitigation: the parity test update is a mandatory step before params.json flip.

**Open questions**
  - Should the veto use `classify_trend` (label-based, slower to flip) or `analyze_structure().trend` (BOS/CHoCH walk-based, faster to flip on confirmed events)? The A/B used classify_trend and got anchor-safe results. walk_structure may be more responsive to intraday reversals but introduces CHoCH-timing sensitivity. This is a deliberate design choice, not a bug — document it.
  - When midday_trendline_gate is unblocked (current UNBLOCK candidate), does the OOS delta increase materially? Run structure_veto_ab.py with midday_trendline_gate=false and compare OOS delta. If OOS delta becomes positive ($50+), the case for urgency strengthens to confidence 8.
  - The A/B removed 2 losers in 2025Q1. Are those the same 2 trades that the midday_trendline_gate later blocked in 2025Q1? If yes, the structure veto and the midday gate are redundant on those trades — and unblocking the midday gate without also having the structure veto may re-expose them. Cross-reference the removed trade identities.
  - Gate 16 position: should it fire BEFORE or AFTER the quality-lock (SKIP_QUALITY_LOCK, which stays in the orchestrator)? Currently: SKIP_QUALITY_LOCK fires first (orchestrator-level, before engine_cli gates). Then Gate 16 fires. This means a wrong-way trade blocked by quality-lock never reaches Gate 16 — which is fine. But if quality-lock is later moved inside engine_cli, the ordering matters.
  - v51 validator needs live data for the '5/07 734C fires SKIP_STRUCTURE_VETO' test case. The anchor check already verified this analytically. The validator should replicate it from the CSV fixture (same data source as the anchor check).


**Verdict** — SHIP-worthy with one condition: write `v51_structure_veto_gate.py`, get gym to pass, then flip params.json. The P&L case is honest-thin (IS +$583, OOS $0) — this is a safety veto, not an alpha generator. The architecture case is solid: the ribbon is a lagging trend indicator; price structure (HH/HL) is contemporaneous; the incident today (−$237) proves the gap is real and the veto closes it with zero anchor regression. Belt-and-suspenders is the correct framing. The confidence is 6/10, not 8, because OOS=$0. It rises to 8 if any upstream gate is relaxed. The guard test is the durability mechanism — J never needs to re-examine this class of wrong-way entry again once the guard is in the graduated-guards test file.

---

## 5-gate unblock batch: cascade risk, staging strategy, VIX drift prevention, and fill-bar hedge

**Problem & root cause** — All 5 gates were ratified on the OLD engine (OTM strike / BS-sim pricing / -8% to -10% hard premium stops / bracket-only exits). Under the CURRENT engine (real OPRA fills / -50% catastrophe cap / chart-stop-primary / chandelier profit-lock / managed exits), the wider stop rides winners that the old engine stopped out of early, so several 'good blocker' votes on the old engine become 'suppresses winners' votes on the new one.

Confirmed current state (verified by running backtest/tests/test_no_stale_blocks.py): ALL 6 guard tests FAIL meaning none of the 5 unblocks have been applied to params yet. The guard test file itself already exists and is correct.

Each gate's stale mechanism, cited to code:

1. midday_trendline_gate = true (params.json:127). BEAR only (100% of removed trades are PUT). Removed-set IS: 102 trades, net +$849, WR 71% (+$8.33/tr). Block_delta IS = -$371, OOS = -$40. Sub-windows: 3/4 HURT. Old evidence was -8.6/tr on 307 OOS trades under OTM/-8% stop. Mechanism: old engine stopped out midday trendline trades at -8%; current -50% cap lets them recover and close green via chandelier or TP1.

2. entry_bar_body_pct_min = 0.20 (params.json:135). BEAR only (orchestrator.py:1594 guards 'winning_side == P'). Old ratification: IS delta +$295, OOS +$566, WF 7.193. On current engine: direct removed-set net = -$200 (removes 44 net-winner bear entries, suppresses 5 fat-tail winners up to +$1,361). The aggregate IS delta of +$1,946 is a C15/L15 cascade artifact. The honest number is the direct removed-set net-PnL: gate costs money.

3. require_bearish_fill_bar in agg/params.json (NOT in safe params.json; orchestrator.py:614 defaults to False). LOOK-AHEAD gate (checks bar N+1, which is unknown at signal bar N close time). Current real-fills + ITM-2 + chandelier: removed-set IS nets +$917 (33 bear, 13W/+$2,759 vs 20L/-$1,841) = suppresses winners. WF = -5.73 sign-flip (negative = gate hurts on the current engine). SW: 2/4 hurt; helps W1 but hurts W2/W3 (largest recent windows). OOS: +$775 but n=5 (thin).

4. block_conf_lvl_rec_afternoon = true in agg/params.json (NOT in safe params.json; safe defaults False). Afternoon conf+level_reclaim bull/C blocker. Old-engine ratification sign-FLIPPED on current engine: costs +$779 IS, protects $0 OOS. Mechanism: leaky gate keys on a backtest variable ('bt' not entry_time) rather than entry_time_et, so it fires inconsistently in production vs backtest.

5. VIX_BULL_HARD_CAP: params.json vix_entry_thresholds.bull_hard_cap = 18.0 AND filters.py:805 VIX_BULL_HARD_CAP = 18.0 (both stale). Old ratification on old engine suppressed 4 IS / 1 OOS bull entries (thin). Current engine: block contributes -$471 IS AND -$471 OOS, suppresses 2 bull WINNERS (4/09 +$205, 4/22 +$266 at VIX 18-22 band). EC invariant: -1379. The dual-location is a documented C14 drift risk: filters.py is read directly by evaluate_bullish_setup(), while params.json is patched via _FILTER_CONST_MAP['vix_bull_max'] -> 'VIX_BULL_HARD_CAP' at orchestrator.py:85. If only params is updated, the constant in filters.py keeps blocking in any code path that imports filters directly without the orchestrator patch (e.g., heartbeat_core.py calling engine_cli directly).


**Approaches considered**

- **Approach A: Staged 2-wave deploy (safe-only first, then aggressive)** — Wave 1 (tonight): flip the 2 safe-params gates that have the cleanest evidence and lowest interaction risk: midday_trendline_gate true->false (BEAR-only, anchor PASS, 0 bull trades in removed set) and VIX_BULL_HARD_CAP 18->22 (params.json + filters.py both). Wave 2 (next after-hours, after one trading day of observation): flip the 3 aggressive-params gates: require_bearish_fill_bar, block_conf_lvl_rec_afternoon, and entry_bar_body_pct_min 0.20->0.0. Before each wave, run the gym (crypto/validators/runner.py) to confirm 30/30 PASS. After each wave, run the stale-block guard (test_no_stale_blocks.py) to confirm tests flip from FAIL to PASS.
    - ✅ Isolates interaction effects. If Wave 1 produces unexpected live behavior, Wave 2 is not yet applied and rollback touches only 2 keys + 1 constant. Safe account and Aggressive account are on separate wave schedules, so a cascade in one account's gate interactions is not simultaneously introduced in the other. The VIX dual-location drift is fixed atomically in Wave 1 with a guard test that permanently enforces sync.
    - ⚠️ Takes 2 cycles instead of 1. On a quiet trading day the split may be artificial — if all 5 gates are demonstrably non-interacting, staging adds delay without risk reduction. Requires discipline to actually execute Wave 2 rather than letting it sit.

- **Approach B: Atomic single-wave deploy (all 5 simultaneously)** — Apply all 5 diffs in a single params edit, update filters.py VIX_BULL_HARD_CAP, run gym before+after, run test_no_stale_blocks.py to confirm all 6 tests now PASS. Commit atomically. The rationale: gates 1-2 are Safe-params BEAR-only, gates 3-4 are Aggressive-params only, gate 5 is Safe-params BULL-only. There is no cross-gate interaction because (a) BEAR path and BULL path in the orchestrator are independent branches (orchestrator.py:1285-1316), (b) Safe and Aggressive params files are read independently per account, (c) the removed sets do not overlap — each gate fires on a structurally distinct subset of bars.
    - ✅ One commit, one gym run, one review cycle. The C15 cascade-interaction concern is real in principle but does not apply here because these gates operate on DIFFERENT setup populations: bear-entry gates (1, 2, 3) cannot cascade into bull-entry gates (4, 5). The only shared pool is the raw bar stream, not the filtered entry set. Faster path to the expected +$1,000-1,500 IS edge recovery.
    - ⚠️ If an unanticipated interaction IS discovered after deploy (e.g., removing midday_trendline_gate exposes a different downstream gate that was previously gated-out), root-cause is harder to isolate with all 5 changed at once. Specifically, the entry_bar_body_pct_min cascade artifact concern (the +$1,946 IS aggregate that the memory calls 'misleading') is not fully resolved — if the cascade inflates aggregate P&L rather than the individual gate's direct contribution, a single-wave deploy masks that ambiguity.


**Recommended** — Approach A (staged), with one important modification: treat gate 5 (VIX_BULL_HARD_CAP, dual-location) as the FIRST item in Wave 1 because its drift risk is structurally different from the others and must be fixed atomically (both params.json and filters.py in the same commit or the live engine and backtest diverge). Wave 1 = VIX_BULL_HARD_CAP 18->22 (both locations) + midday_trendline_gate true->false. Wave 2 = entry_bar_body_pct_min 0.20->0.0 + require_bearish_fill_bar (agg) + block_conf_lvl_rec_afternoon (agg).

Reason for staging over atomic: entry_bar_body_pct_min has a documented ambiguity that the memory itself flags ('aggregate +$1,946 is a cascade artifact, C15; direct block delta = -$200 is the honest number'). That ambiguity makes it the weakest evidence of the 5. If the direct-delta is -$200 but the cascade effect makes aggregate appear positive, there is a risk the cascade is regime-dependent — removing it during a regime change could introduce unexpected behavior. Staging it to Wave 2 lets us observe Wave 1 behavior for one trading day before adding the noisiest gate to the mix. Similarly, require_bearish_fill_bar has OOS n=5 (thin) and was ORIGINALLY a look-ahead gate — it is probably right to unblock (WF -5.73 is a strong sign flip), but one day of observation is cheap insurance. Atomic is fine if J wants speed; the non-interacting argument is sound. This is a judgment call, not a hard safety concern.


**Design detail**

Wave 1 changes (automation/state/params.json and backtest/lib/filters.py):

automation/state/params.json:
- vix_entry_thresholds.bull_hard_cap: 18.0 -> 22.0
- midday_trendline_gate: true -> false

backtest/lib/filters.py line 805:
- VIX_BULL_HARD_CAP = 18.0 -> 22.0

Wave 2 changes:
automation/state/params.json:
- entry_bar_body_pct_min: 0.20 -> 0.0

automation/state/aggressive/params.json:
- require_bearish_fill_bar: (add or set) false
- block_conf_lvl_rec_afternoon: true -> false

VIX_BULL_HARD_CAP dual-location wiring (the permanent drift-prevention design):
The constant at filters.py:805 is read DIRECTLY by evaluate_bullish_setup() at filters.py:891 without going through the orchestrator param-patch path. The orchestrator patches it only when run_backtest() or run_with_params() is called with a params_overrides dict. Any code path that calls evaluate_bullish_setup() directly (e.g., heartbeat_core.py -> engine_cli.py -> score_bar()) reads the module-level constant, not the patched value. This is why BOTH must be updated atomically and why the drift guard test (test_vix_bull_hard_cap_params_filters_in_sync) must stay live. The correct permanent fix is: the guard test enforces they are equal; updating either one without the other causes CI to fail. This is already encoded in test_no_stale_blocks.py:176-193.

After Wave 1, run in order:
1. cd backtest && python -m pytest tests/test_no_stale_blocks.py::test_midday_trendline_gate_unblocked tests/test_no_stale_blocks.py::test_vix_bull_hard_cap_params_unblocked tests/test_no_stale_blocks.py::test_vix_bull_hard_cap_filters_unblocked tests/test_no_stale_blocks.py::test_vix_bull_hard_cap_params_filters_in_sync -v
2. python crypto/validators/runner.py (must show all stages PASS)

After Wave 2, run:
1. cd backtest && python -m pytest tests/test_no_stale_blocks.py -v (all 6 must PASS)
2. python crypto/validators/runner.py (must show all stages PASS)


**Edge cases**
  - require_bearish_fill_bar is a look-ahead gate (checks bar N+1 at bar N signal time). Its OOS evidence (n=5) was measured USING the look-ahead in the backtest, meaning the 'removed set nets +$917' is an upper bound on what production could achieve. Production cannot see N+1 at N close time. The correct interpretation of 'unblock' here is: the gate has failed its own stated purpose (blocking losers) even in the look-ahead scenario, so keeping it active is net-negative. Unblocking restores the prior behavior (no delay). This is NOT a case where unblocking adds a new 1-bar-delay signal.
  - entry_bar_body_pct_min cascade artifact (C15): the 44 trades blocked by this gate may themselves gate other downstream sessions. If upstream filters are correlated with afternoon regime (which midday_trendline_gate also operates in), removing both gates in the same wave could produce non-additive P&L. The cascade goes: bar N fails body_pct_min -> no trade placed -> position is flat -> subsequent bar N+k sees different account state -> changes P&L. This is a per-session state dependency, not a per-bar independence. Staging Wave 2 at least separates midday_trendline (Wave 1) from entry_bar_body (Wave 2) by one trading day.
  - block_conf_lvl_rec_afternoon protects $0 OOS and the memory notes it 'keys on bt not entry' meaning the gate fires based on a backtest-internal variable rather than actual entry time. If there are afternoon confluence+level_reclaim bull entries that actually existed in the aggressive account during the OOS window, unblocking could admit them. The OOS delta is $0 (not negative) which means either no such entries existed in OOS, or they canceled out. This is the cleanest edge case: the gate is vacuous, so the risk of unblocking is low.
  - VIX_BULL_HARD_CAP at 22.0 admits VIX 18-22 bull entries. The existing Filter 8 (filters.py:882-887) still requires VIX < 17.20 OR falling to pass. This means at VIX 18-22 with VIX falling, BOTH Filter 8 (VIX falling = pass) AND Filter 9 (VIX < 22 = pass) will now both pass for a bull entry. This is the intended behavior (the 2 confirmed bull winners 4/09 and 4/22 were VIX-falling days). But at VIX 18-22 with VIX flat or rising, Filter 8 blocks the entry so Filter 9 at 22.0 is moot. The cascade here is safe: F8 still acts as the soft VIX gate.
  - midday_trendline_gate removal exposes 102 previously-blocked trendline-only midday bear trades back into the engine. These are single-trigger entries (trendline_rejection only, no level or confluence). Bear minimum trigger count is 1 (params filter_10_min_triggers_bear = 1), so the level-tie requirement at orchestrator.py:953-959 still applies: the trendline_rejection trigger must be level-tied. Check: trendline_rejection returns the trendline price as a 'level' via detect_trendline_rejection_bearish() -> this IS treated as a rejection_level in the SetupResult. But level_tied_required logic in the bear path at orchestrator.py:1245-1265 checks whether the trigger is in the level_tied set {level_rejection, confluence, sequence_rejection}. A trendline_rejection trigger is NOT in that set. This means filter_10_level_tied_required=true (params.json) could block trendline-only entries even after midday_trendline_gate is removed. Need to verify this is the intended behavior or whether the re-exposed trades get silently re-blocked by a different gate.

**Failure modes**
  - VIX_BULL_HARD_CAP partial-update drift: someone updates params.json bull_hard_cap = 22.0 but forgets filters.py:805. Result: backtest runs with 22.0 (via param-patch), live heartbeat_core.py runs engine_cli which calls evaluate_bullish_setup() directly, reads the constant at 18.0, and silently blocks VIX 18-22 bull entries that the backtest counted as winners. The symptom is 'live underperforms backtest by exactly the VIX 18-22 bull P&L'. The guard test_vix_bull_hard_cap_params_filters_in_sync catches this at commit time.
  - entry_bar_body_pct_min cascade overstates edge: the +$1,946 IS aggregate number in the memory is a C15 cascade artifact. If the direct removed-set delta is truly -$200 (gate costs net $200 by blocking winners), then the aggregate inflation comes from downstream gate interactions. If the specific 44 blocked trades were clustered in a high-regime period, unblocking in a different regime could be neutral or negative. The defense is that the direct delta is the correct signal: -$200 means the gate removes $200 of net-positive bear trades. That is the honest edge.
  - require_bearish_fill_bar OOS n=5 brittleness: the WF sign-flip (-5.73) is strong and the direction is clear. But n=5 OOS blocked trades means a single outlier trade can flip the OOS sign. If the OOS window happened to include a cluster of bearish-fill-bar bars that were genuinely losers (which the old engine correctly blocked), the evidence would look identical. The hedge is: (1) the gate is a look-ahead gate so it cannot be used in production as designed anyway, and (2) the IS evidence on the current engine (33 trades removed, net +$917) is the primary signal. Thin OOS is a disclosure, not a dealbreaker, since the gate architecture itself (look-ahead) is the first-order reason to remove it.
  - C15 multiplicative cascade across all 5: removing 5 gates simultaneously changes the entry population for every downstream interaction. Specifically, if midday_trendline_gate was blocking 102 trades that were correlated with bad-regime days, removing it increases trade count on those days, which interacts with VIX filter state (more bear entries on days where VIX is elevated), which interacts with entry_bar_body_pct_min (more doji-bar entries on those same days). The staged approach partially mitigates this by separating wave 1 (bear midday gate + VIX bull gate) from wave 2 (bear body gate + aggressive gates). The bear/bull path separation is the real protection: midday_trendline is pure-BEAR, VIX_BULL_HARD_CAP is pure-BULL. They cannot cascade into each other.
  - block_conf_lvl_rec_afternoon is DEAD in aggressive/params.json (the aggressive doc says '$0 delta in all contexts, superseded by block_conf_lvl_rej_midday_afternoon'). Unblocking a dead gate changes nothing. But the stale-block guard test checks it anyway. The failure mode here is if someone later re-activates block_conf_lvl_rej_midday_afternoon in aggressive params without also re-checking block_conf_lvl_rec_afternoon — the superset gate would then do the blocking and the vacuous gate would be re-activated unnecessarily.


**Validation plan** — Wave 1 real-fills validation (before applying changes):

Baseline (current state, all 5 gates ON):
Run: cd backtest && python backtest/autoresearch/vix_bull_hardcap_revalidate.py
Expected: FULL IS shows block contribution = -$471, OOS = -$471. J anchor winners 4/29/5/01/5/04 all PASS (these are BEAR winners; VIX_BULL_HARD_CAP is BULL-only, no anchor regression possible).

After Wave 1 (midday_trendline_gate=false, VIX_BULL_HARD_CAP=22.0):
Run: cd backtest && python backtest/autoresearch/safe_midday_trendline_gate_revalidate_current_engine.py (if exists) or inline run_backtest A/B.
Expected: IS PnL improves by approximately +$371 from midday_trendline unblock. J anchor PASS (all 3 J winners are pre-11:30 ET or non-trendline-only entries, so midday_trendline gate should not have affected them; verify the removed 102 trades are dated outside anchor dates 4/29, 5/01, 5/04). VIX_BULL_HARD_CAP=22.0: IS admits 2 additional bull entries (4/09 +$205, 4/22 +$266). J anchor PASS (J anchor losers are 5/05-5/07 PUT days; VIX_BULL_HARD_CAP is CALL-only, zero regression).

Wave 2 real-fills validation:
Run: cd backtest && python backtest/autoresearch/fill_bar_direction_gate.py with gate_on=False vs current baseline.
Expected: IS baseline improves by approximately +$917 (removed set nets positive). Check WF sign is consistent with -5.73 flip direction (removing the gate = positive effect = WF_norm of the REMOVED-set run is negative of the gate-on run). OOS: with n=5 the delta could be +$775 or slightly different depending on data boundary. Accept direction-consistent result.

For entry_bar_body_pct_min=0.0: run inline A/B or check safe_entry_body_gate.py output. Expected: direct removed-set net = -$200 (the gate was correctly identified as costing $200 net by removing 44 net-winner entries). The aggregate may show inflation — cite the direct delta, not the aggregate.

Anchor check for all 5: verify via backtest/structure_veto_anchor_check.py or manual date-filter that the J anchor dates (4/29, 5/01, 5/04 winners; 5/05, 5/06, 5/07 losers) are unaffected by the unblocked gates. The VIX_BULL_HARD_CAP is CALL-only, the other 4 are BEAR-only or aggressive-only — there is structural separation from the PUT-anchor dates.


**Guard** — The guard already exists at backtest/tests/test_no_stale_blocks.py and is the correct design. All 6 tests currently FAIL (confirmed). After applying the 5 diffs, all 6 should PASS.

Specific tests and what they catch on regression:

test_midday_trendline_gate_unblocked(): reads params.json, asserts midday_trendline_gate is False. Fails if params is reverted to true.

test_entry_bar_body_pct_min_unblocked(): reads params.json, asserts entry_bar_body_pct_min == 0.0. Fails if restored to 0.20.

test_require_bearish_fill_bar_unblocked(): reads agg/params.json, asserts require_bearish_fill_bar is False. Fails if set to True in aggressive params.

test_block_conf_lvl_rec_afternoon_unblocked(): reads agg/params.json, asserts block_conf_lvl_rec_afternoon is False. Fails if set to True.

test_vix_bull_hard_cap_params_unblocked(): reads params.json vix_entry_thresholds.bull_hard_cap, asserts == 22.0. Fails if reverted to 18.0.

test_vix_bull_hard_cap_filters_unblocked(): imports backtest.lib.filters directly, reads VIX_BULL_HARD_CAP constant, asserts == 22.0. Fails if filters.py constant is reverted to 18.0 even if params is correct.

test_vix_bull_hard_cap_params_filters_in_sync(): asserts the two values are EQUAL regardless of what they are. This is the permanent drift guard — it fires on any future param change that updates one side without the other. This test PASSES today (both are 18.0 = in sync but wrong); after the fix both should be 22.0 = in sync and correct.

Run command: cd backtest && python -m pytest tests/test_no_stale_blocks.py -v
Expected post-fix: 7/7 PASS (0 failed).

Pre-commit hook integration: the test file is pure-static (no data, no network) and runs in under 1 second. It is appropriate as a pre-commit gate. Adding it to .pre-commit-config.yaml or the existing test_verify_committed.py suite would enforce it on every commit.


**Risks**
  - require_bearish_fill_bar OOS n=5 is the thinnest evidence of the 5 unblocks. If the 5 OOS-blocked trades happened to be regime-clustered losers (not a random sample), the IS sign-flip (WF -5.73) may overstate the population edge. Hedge: the gate is a look-ahead gate that production cannot implement as designed, so keeping it active is incorrect regardless. The correct framing is 'remove an incorrectly-implemented gate' not 'add an edge.'
  - entry_bar_body_pct_min cascade risk (C15): the direct delta is -$200 but the aggregate is +$1,946. This 10x discrepancy between direct and aggregate is a red flag for a cascade interaction. It means 44 unblocked trades somehow alter the path of $2,146 in downstream P&L. Most likely mechanism: some of the 44 unblocked bear entries on doji bars occur earlier in the session, causing a 'position already open' state that prevents a later entry on a different (better) bar. Unblocking them adds the doji-bar entries but forfeits the better-bar entries. The net is -$200. If this interpretation is correct, unblocking at entry_bar_body_pct_min is the right call (the gate actively hurts by blocking the doji entry AND the cascade is the mechanism by which it blocks the subsequent better entry). But this causal chain is inferred, not directly traced.
  - midday_trendline_gate exposes 102 bear trades back to the engine, 71% of which are winners. On active midday sessions this could increase trade frequency in the 11:30-14:00 window. If the PDT (day-trade) count guard is near its limit on a given day, these additional trades could trip the kill switch. The guard is per-account (Rule 7) and the backtest does not simulate PDT limits. Verify: the Safe-2 account at $2K is paper trading, so PDT rules apply differently than real money. For aggressive/live account, track PDT count on days where midday trendline would fire.
  - block_conf_lvl_rec_afternoon is marked DEAD in agg/params.json doc ('$0 delta in all contexts, superseded by block_conf_lvl_rej_midday_afternoon'). This means the unblock has zero P&L impact. However, the stale-block guard test still tests it. If someone later removes block_conf_lvl_rej_midday_afternoon (the superset gate) from aggressive params, block_conf_lvl_rec_afternoon at false would no longer be the safety net. This is low risk but worth noting: the superset gate is the load-bearing blocker for aggressive afternoon conf+rec entries.
  - VIX_BULL_HARD_CAP at 22.0 is still a cap (not disabled). The engine still blocks ALL bull entries when VIX >= 22. This is correct behavior — the revalidation showed that VIX 22+ bull entries are still losers on the current engine. The 18-22 band is the specific range where the old engine incorrectly blocked winners. The 22+ range remains blocked. Verify: filters.py:891 'if ctx.vix_now >= VIX_BULL_HARD_CAP' — at VIX_BULL_HARD_CAP = 22.0 this correctly blocks VIX >= 22.

**Dependencies**
  - backtest/.venv/Scripts/python.exe (backtest venv interpreter, not system Python313)
  - automation/state/params.json (Safe params, J-only write access — THIS IS A PRODUCTION FILE; Chef NEVER edits it directly, proposes diffs only)
  - automation/state/aggressive/params.json (Aggressive params, same restriction)
  - backtest/lib/filters.py line 805 VIX_BULL_HARD_CAP constant (must be updated atomically with params.json bull_hard_cap)
  - backtest/lib/orchestrator.py _FILTER_CONST_MAP line 85 ('vix_bull_max': 'VIX_BULL_HARD_CAP') — this is the wiring that makes params_overrides patch the constant at runtime; it is already correct, no change needed
  - backtest/tests/test_no_stale_blocks.py — the guard file; already written, all 6 tests fail (confirmed), will pass after diffs applied
  - crypto/validators/runner.py — gym run required before AND after each wave
  - backtest/autoresearch/vix_bull_hardcap_revalidate.py — revalidation script for gate 5; use to confirm -$471 IS delta before applying
  - backtest/autoresearch/fill_bar_direction_gate.py — WARNING: uses old-engine config (premium_stop_pct_bear=-0.10 at line 64); output may not reflect current -0.50 engine state
  - backtest/autoresearch/safe_midday_trendline_gate_revalidate_current_engine.py — confirm this file exists before citing the +$849 IS figure

**Open questions**
  - level_tied_required gate interaction with midday_trendline unblock: params.json filter_10_level_tied_required = true requires that at least one trigger in the winning set is level-tied (level_rejection, confluence, or sequence_rejection). A trendline_rejection trigger is NOT in that level_tied set. Does removing midday_trendline_gate expose 102 bear trades that then get re-blocked by the level_tied_required gate? If yes, the P&L improvement from midday_trendline unblock is smaller than the +$849 IS figure. Need to run the baseline without midday_trendline_gate and WITH filter_10_level_tied_required=true to confirm the 102 trades actually land.
  - cascade ordering: should entry_bar_body_pct_min be unblocked before or after midday_trendline_gate? Both operate on BEAR entries but different conditions (body_pct vs time window). If a midday trendline-only entry on a doji bar exists in the 102-trade removed set, removing midday_trendline_gate first then entry_bar_body_pct_min second would add that trade in Wave 2 (it was gated by body_pct). But removing entry_bar_body_pct_min first while midday_trendline_gate is still ON would never expose it. The overlap (midday + doji) is small but should be traced if the cascade is a concern.
  - What is the correct production treatment of require_bearish_fill_bar when it is a look-ahead gate? The memory says 'mislabeled bull; Bold=true, AUTO-RATIFIED 2026-06-17 on OLD bracket-only engine.' The orchestrator.py comment at line 610-613 explicitly calls it a look-ahead gate and says 'valid for backtest research only.' If the gate was auto-ratified and set to true in agg/params.json, was it ever actually WIRED to the live aggressive heartbeat_core? The heartbeat_core calls engine_cli, which calls run_backtest via params_overrides. If require_bearish_fill_bar is in agg/params.json and the aggressive orchestrator reads it via params_overrides, then YES it is live and blocking real entries. Confirm this wiring before attributing the OOS n=5 evidence to live account behavior.
  - Does the existing v25 validator (referenced in test_no_stale_blocks.py:183 as 'The v25 validator (P4) already checks this at gym-run time') actually catch the VIX_BULL_HARD_CAP drift at gym runtime? If so, run crypto/validators/runner.py NOW (before applying changes) and check whether the v25 stage passes or warns. If it catches the drift, then the gym has been silently yellow or red on this for every run since the filters.py constant was set to 18.0.
  - Is the safe_midday_trendline_gate_revalidate_current_engine.py file referenced in the test docstring actually present? It is listed as the source script for the +$849 IS figure. If it is not in the repo, the evidence is in the memory notes only and cannot be re-run to verify. The fill_bar_direction_gate.py script uses an OLD engine config (premium_stop_pct_bear=-0.10, not -0.50) as its SAFE_BASE (line 64 of fill_bar_direction_gate.py) — which means its output is NOT on the current engine. The memory score for require_bearish_fill_bar was obtained on 'current real-fills+ITM-2+chandelier' but the script itself shows a -0.10 base. Was a separate run done with -0.50? This needs to be confirmed before treating OOS +$775 as current-engine evidence.


**Verdict** — SHIP-worthy for Wave 1 (midday_trendline_gate + VIX_BULL_HARD_CAP dual-location). These two have the cleanest evidence: midday_trendline has 102 direct IS trades at +$849 net with anchor PASS, and VIX_BULL_HARD_CAP has two named J-period bull winners that are being incorrectly blocked. Both are currently causing the test_no_stale_blocks.py guard to fail.

NEEDS-MORE for Wave 2, specifically for entry_bar_body_pct_min and require_bearish_fill_bar:

entry_bar_body_pct_min: the direct delta is -$200 but the aggregate is +$1,946. A 10x discrepancy between direct and cascade-inflated aggregate is unusual and the memory explicitly calls it a 'cascade artifact.' The gate should be removed, but the ambiguity about WHY the aggregate is inflated should be resolved before treating the unblock as a validated +$1,946 edge. It is a -$200 direct-delta unblock, not a +$1,946 edge.

require_bearish_fill_bar: fill_bar_direction_gate.py uses an old engine config (premium_stop_pct_bear=-0.10, not -0.50). The evidence base may not be fully current-engine. Confirm by rerunning with -0.50 cap. The look-ahead gate architecture means it cannot be used in production as designed regardless, which makes it the right call to remove — but the evidence quality is thin.

block_conf_lvl_rec_afternoon (aggressive): SHIP immediately — it is DEAD ($0 delta in all contexts per its own doc) and the unblock is a no-op.

The guard in test_no_stale_blocks.py is the correct enforcement mechanism. It is already written. Apply the params diffs, update filters.py, confirm 7/7 PASS, commit. The FORBIDDEN-FRAMING rule (OP-11) applies: these are profitable/validated unblocks, not 'your call' items. Ship and report for REVOKE.

---

## Dormant Validated Setups: Why They Are Off, Enablement Risk, Bull-Block Interaction, and Position-Collision Under 4+Ribbon Live

**Problem & root cause** — The question posits four setups as "validated but enabled=false": vwap_continuation, vwap_reclaim_failed_break, vix_regime_dayside, and gap_and_go. The first correction the code demands: two of the four are ALREADY enabled=true in production params.json (checked live: gap_and_go_enabled=true, j_vwap_cont_enabled=true). This is not a dormancy problem for those two — it is a LIVE FEED problem. The real four-way dormancy taxonomy from the code:

1. vwap_continuation (j_vwap_cont_enabled=true): The flag is live, but the flag does NOT go through the orchestrator's run_backtest / engine_cli path. It is consumed exclusively by mass_grind_vwap.py and Gamma_Grind_Vwap (a separate on-demand research task). The heartbeat_core calls engine_cli which calls score_bar + evaluate_gates — the ribbon-ride 15-gate battery — and that path never calls detect_vwap_continuation_setup. So "enabled" here means "the research grinder is authorized to run it," not "the live engine will trade it." From heartbeat_core.py's perspective the watcher is DEAD (no wiring to heartbeat_core or engine_cli).

2. gap_and_go (gap_and_go_enabled=true, side=put): Same structural gap. The watcher is registered in runner.py's WATCHERS list, which fires during backtest/watcher replay (Gamma_WatcherLive), but heartbeat_core.py does NOT iterate the WATCHERS list — it calls engine_cli, which calls score_bar/evaluate_gates (ribbon-ride only). Runner.py comment confirms "prior close is needed; in single-day replay the watcher no-ops." So gap_and_go is live-authorized in params but live-blind in the heartbeat.

3. vwap_reclaim_failed_break (j_vwap_reclaim_fb_enabled=false): Correctly config-blocked. Watcher exists (detect_vwap_reclaim_failed_break_setup in runner.py), filters.py has the enabled() accessor, test_engine_order_bracket_parity.py covers the flag-off/flag-on parity. The isolated stop (-0.08) and tp1 (0.30) params are wired via WP-0. Config change to true would route signals through simulate_trade_real. recency-confirmation.json: ATM n=5, exp=-40.56/tr, sign=NEGATIVE, verdict=YELLOW (n<floor 10 = small-n wobble, not confirmed RED; full-OOS base +$13.66/tr still positive).

4. vix_regime_dayside (j_vix_dayside_enabled=false): Config-blocked AND feed-blocked. The watcher's _vix_intraday_series() reads ctx.vix_intraday — an optional series that heartbeat_core.py does NOT populate (grep confirms zero references to vix_intraday in heartbeat_core.py). Enabling j_vix_dayside_enabled=true without threading the intraday VIX series into the BarContext payload would produce: enabled=true, watcher fires, detects None vix_series, returns None/SKIP every bar. Zero trades placed. The feed gap is a separate build task, not a config flip. recency: ATM n=5, exp=+61.8/tr, POSITIVE, YELLOW (thin n) — actually the BEST recency signal of the four.

5. recency-confirmation.json (run 2026-06-22, OPRA cache through 2026-06-18): The BOOK verdict is what matters for the combined fleet. Safe2_ATM book (edges #1+2+4 combined, n=17 trades, 9 days): daily_mean=-15.13, sign=NEGATIVE, verdict=RED. Bold_ATM book (edges #1+2, n=10, 7 days): daily_mean=-85.89, sign=NEGATIVE, verdict=RED. The "both books RED" verdict is a deliberate HOLD gate from license_monitor.py. This is not a config choice — it is a capital-protection gate triggered by confirmed recent negative expectancy at n>=10.

Root mechanism: The dormancy is three-layer — (A) params flag off (config), (B) live-feed absent (structural — vix_dayside), and (C) heartbeat dispatch path does not call the watcher at all (architectural — vwap_cont/gap_and_go). The recency RED is the fourth layer that would block even if (A)-(C) were solved. These four layers are INDEPENDENT. Solving any one of them does not solve the others.


**Approaches considered**

- **Approach A: Staggered config-only enable (vwap_reclaim_fb first, then gap_and_go side expansion, wait on vix_dayside)** — Flip j_vwap_reclaim_fb_enabled=true in params.json when recency-confirmation next clears YELLOW->ELIGIBLE (n>=10 required; current n=5, approximately 5 more trading days of OPRA data needed). The isolated stop (-0.08) and tp1 (0.30) are already wired via WP-0/risk_gate.select_exit_params — no code change needed. The orchestrator already dispatches VWAP_RECLAIM_FAILED_BREAK signals through simulate_trade_real when the flag is true (test_engine_order_bracket_parity.py proves the parity). The watcher is in runner.py's WATCHERS list and fires during Gamma_WatcherLive. However — CRITICAL — heartbeat_core.py still doesn't call the watcher; it calls engine_cli which is ribbon-only. So this flip authorizes the backtest and Gamma_WatcherLive to count the signal, but does NOT wire it into the live entry path unless heartbeat_core is extended to poll runner.py signals. For vix_dayside: wait until the intraday VIX series is threaded into heartbeat_core's BarContext payload (a separate build task, ~4h). For gap_and_go: already enabled; the missing piece is prior_rth_close in heartbeat_core's payload.
    - ✅ Zero code risk — config-only for vwap_reclaim_fb. WP-0 parity test already guards the stop dispatch. Full-OOS base for reclaim_fb is positive ($13.66/tr). The YELLOW verdict rule is explicitly 'ship-eligible per the WP gates; size conservatively' per license_monitor.py. Both-sides validated for vix_dayside means no OP-16 friction when it eventually ships (it has its own YELLOW but with POSITIVE recent n=5 exp=+61.8). Bull-blocks (block_bull_1100_1200, block_elite_bull, bull_hard_cap=18) are irrelevant to vwap_reclaim_fb because its side='put' (bear-only, default).
    - ⚠️ 1. It solves only the config layer for one setup (vwap_reclaim_fb). The architectural gap (heartbeat_core does not call watchers) remains — so 'enabled' gives you backtest signals and Gamma_WatcherLive observations but ZERO live orders via heartbeat_core. 2. BOOK verdict is RED. The recency-confirmation.json headline says both books (Safe2 and Bold) are in RED territory as of 2026-06-22. license_monitor.py says RED = BLOCKED, no live flip. Flipping under a RED book violates the capital-protection gate even if the per-edge tier is YELLOW. 3. n=5 for reclaim_fb ATM is thin: the YELLOW verdict's own explanation is 'full-OOS base positive ($13.66/tr)' but that base is fragile (drop-top5 not confirmed at ATM). 4. If vwap_cont is also in recent drawdown (n=7, exp=-34.63/tr, NEGATIVE), adding reclaim_fb as an overlay pushes the combined book deeper negative.

- **Approach B: Architecture-first — wire ALL four setups into heartbeat_core/engine_cli before enabling any** — The correct sequence: (1) extend heartbeat_core._build_payload() to include prior_rth_close (from sight_beacon.json last RTH close or a new daily-close cache) so gap_and_go watcher can fire; (2) extend _build_payload() to include vix_intraday series (array of 5m VIX closes from yfinance or CBOE) so vix_dayside watcher can fire; (3) modify _engine_verdict() to also call runner.run_watchers(ctx) and merge non-ribbon signals into the verdict alongside or instead of engine_cli; (4) then gate config enables behind the recency-CONFIRM state. The live path for watchers would be: heartbeat_core builds BarContext -> run runner.run_watchers(ctx) -> for each signal, check the per-setup enabled flag + recency gate -> if ENTER, pipe to risk_gate + place_bracket. This is the architecturally honest path because the watcher signals (VWAP_CONTINUATION, GAP_AND_GO, VWAP_RECLAIM_FAILED_BREAK, VIX_REGIME_DAYSIDE) have independent detection logic that does NOT go through the 15-gate ribbon-ride battery. They are parallel setup families, not extensions of the ribbon setup.
    - ✅ 1. Eliminates the silent 'enabled=true but never fires' anti-pattern (C14/L70 exactly). 2. When enabled, trades are actually placed — the flag means what it says. 3. Gap_and_go and vwap_cont become truly live (not just research-authorized). 4. Position-collision is managed cleanly: heartbeat_core already has is_flat_spy_options() + quality_lock_check() — extend quality_lock to cover non-ribbon setup names (GAP_AND_GO, VWAP_CONTINUATION etc.) so it skips if already in a ribbon-ride position. 5. vix_dayside's feed requirement surfaces as a concrete TODO rather than a silent no-op. 6. Validated exits (WP-0 isolated stops) work correctly because risk_gate.select_exit_params already dispatches by setup_name.
    - ⚠️ 1. Build cost: 4-6h of engineering (prior_close cache, vix_intraday feed thread, runner integration, quality_lock extension, parity test). 2. Recency books are still RED — so even after the architecture is fixed, the capital gate should hold until CONFIRM/YELLOW clears on each setup. This is the right order but it means the engine builds to trade setups it can't trade yet (the RED gate is separate from the architectural gap). 3. Runner signals and engine_cli output must not conflict — if a bar triggers both a ribbon-ride ENTER and a VWAP_CONTINUATION signal on the same bar, the engine needs a priority rule (which signal wins? one trade at a time). 4. Complexity: the parity test (test_engine_cli_parity.py) currently guarantees engine_cli == orchestrator for ribbon-ride only; adding watcher signals to the live verdict breaks that byte-identity guarantee and needs a new parity surface.


**Recommended** — Approach B (architecture-first) is the correct long-term path, but it should be phased with a hard recency gate: build the wiring first, trade second. Specifically: (1) Build prior_close + vix_intraday feeds into heartbeat_core (2h) and hook runner.run_watchers() into the live tick (2h) + add quality_lock parity. (2) Do NOT enable any setup until the recency book flips YELLOW (per-edge, n>=10) or CONFIRM. (3) Enable vix_dayside first when it clears (currently the ONLY setup with positive recent exp, +61.8/tr, n=5 — will clear YELLOW at n=10, approximately 5 more trading days). (4) Enable vwap_reclaim_fb second (YELLOW pending n=10). (5) Vwap_cont and gap_and_go are already enabled in config but architecturally blind — wiring them is part of step 1. The reason to prefer B over A: Approach A creates a dangerous split-brain state where params say 'enabled' and backtest/WatcherLive count the signals, but the live heartbeat places zero orders. J reads the recency file and sees 'enabled' and assumes live trades are happening. They are not. That gap is exactly C14 (dead knob). The wiring work is the prerequisite to any meaningful enable/disable decision.


**Design detail**

Files and functions that change for the Architecture-First approach:

1. setup/scripts/heartbeat_core.py — _build_payload() function (line ~292): 
   - Add prior_rth_close: read from automation/state/sight-beacon.json field 'prior_rth_close' (sight_beacon.py already writes the daily close; confirm field name). Pass into BarContext payload as bar_ctx['prior_rth_close'] so detect_gap_and_go_setup can access ctx.prior_rth_close.
   - Add vix_intraday: after _fetch_vix(), fetch 5m VIX bars from yfinance (ticker '^VIX', interval='5m', period='1d') as a list of closes aligned to the SPY bar timestamps. Append to bar_ctx payload as bar_ctx['vix_intraday']. The BarContext dataclass already accepts this as an optional attribute (vix_regime_dayside_watcher._vix_intraday_series() reads getattr(ctx, 'vix_intraday', None)).

2. setup/scripts/heartbeat_core.py — run_account() function (line ~477):
   - After _engine_verdict(payload) returns the ribbon-ride verdict, add a second pass: import runner from backtest.lib.watchers.runner; build BarContext from payload; call runner.run_watchers(ctx) -> list[WatcherSignal | None]. For each non-None signal, check: (a) signal.setup_name matches an enabled flag (params.get('j_vwap_cont_enabled') etc.), (b) recency verdict for that setup is >= YELLOW (read recency-confirmation.json at startup), (c) account is currently flat (is_flat_spy_options() already called). If all pass, use that signal as the entry verdict instead of (or in addition to, if ribbon is HOLD) the engine_cli result.
   - Conflict rule: if engine_cli says ENTER_BEAR and a watcher also says ENTER_BEAR same direction — same setup, skip duplicate. If directions conflict, take the higher-quality signal or skip (conservative).

3. backtest/lib/filters.py — BarContext dataclass: Confirm that prior_rth_close and vix_intraday are accepted as optional attributes. They already are (vwap_continuation_watcher uses prior_bars for VWAP, gap_and_go_watcher uses ctx.prior_rth_close, vix_dayside uses ctx.vix_intraday via getattr).

4. setup/scripts/heartbeat_core.py — _quality_lock_check() function (line ~620): Extend the setup_name list to include 'VWAP_CONTINUATION', 'GAP_AND_GO', 'VWAP_RECLAIM_FAILED_BREAK', 'VIX_REGIME_DAYSIDE' so the quality-lock prevents re-entry on the same watcher setup after a winner today. Current code at line ~708 defaults setup_name to 'BEARISH_REJECTION_RIDE_THE_RIBBON' when the watcher signal doesn't match — that default must be changed to use the signal's actual setup_name.

5. Recency gate knob: At heartbeat_core startup, read automation/state/recency-confirmation.json. Build a dict of {setup_name: verdict}. In the watcher dispatch loop, check verdict != 'RED' before permitting an entry. Reload the file daily (day-boundary check same as the quality_lock reset). This is the live analog of license_monitor's BLOCKED logic.

Params that govern 'both directions' interaction with bull-blocks: When vwap_cont (side='both') or vix_dayside (side='both') fires a CALL entry, the signal goes through risk_gate but does NOT go through evaluate_bullish_setup (the ribbon-ride bull-filter battery). So block_bull_1100_1200, block_elite_bull, and filter_10_min_triggers_bull=2 DO NOT apply to watcher-initiated entries. These gates live in filters.evaluate_bullish_setup() which is only called by the orchestrator's ribbon-ride path, not by detect_vwap_continuation_setup(). The heartbeat_core.py execute path goes from watcher signal directly to risk_gate.check_order() (VIX cap, daily kill switch, PDT, per-trade cap) and then to place_bracket. The bull-blocks are irrelevant to watcher entries. This is by design — the watcher setups have their own directional logic (VWAP day-side) that is independent of the ribbon-ride trigger system. The VIX hard cap for bulls (bull_hard_cap=18, filters.py VIX_BULL_LOW_THRESHOLD=17.20) is also in evaluate_bullish_setup, so it also does NOT apply. The only live VIX gate that applies to all entries uniformly is vix_bear_hard_cap=23 — but that is coded directly in filters.py and is read by evaluate_bearish_setup, again only on the ribbon path. Watcher CALL entries face ZERO of the 15 gates. This is both the edge (clean signal, no gate interference) and the risk (no gates = no protection against bad entries).


**Edge cases**
  - vix_dayside is feed-blocked regardless of config: even with j_vix_dayside_enabled=true, the watcher returns None every bar because heartbeat_core._build_payload() never sets vix_intraday. A config flip without the feed fix produces enabled=true, zero trades — a silent C14 dead knob.
  - gap_and_go needs prior_rth_close: the watcher checks ctx.prior_rth_close and no-ops if absent. The prior close is available in sight-beacon.json (sight_beacon.py writes it nightly) but not currently plumbed into _build_payload(). Enabled but no prior_close = zero gap trades every day.
  - vwap_cont and gap_and_go are both enabled=true in params but both architecturally blind in heartbeat_core. They generate signals in Gamma_WatcherLive and mass_grind_vwap research runs but ZERO live trades. This is the exact C14 pattern: a knob validated in sim that the live gate neutralizes.
  - recency BOOK verdict is RED for both Safe2 and Bold (as of 2026-06-22). Individually vix_dayside ATM is YELLOW+POSITIVE, but the combined book is RED because vwap_cont and vwap_reclaim_fb drag it negative. Enabling vix_dayside alone without a per-setup recency check would mix a positive signal into a negative portfolio — still a net-RED book.
  - bull-block gates (block_bull_1100_1200, block_elite_bull, min_triggers_bull=2, bull_hard_cap VIX=18) do NOT apply to watcher-sourced CALL entries. This is architecturally correct (watchers bypass the ribbon-ride filter battery) but means enabling side='both' on vwap_cont or vix_dayside introduces an unguarded bull entry path. Midday CALL entries from vwap_cont at 11:30 ET would NOT be blocked by block_bull_1100_1200 even though that gate was ratified as effective.
  - Position collision: heartbeat_core already calls is_flat_spy_options() before any entry. A ribbon-ride PUT followed by a vwap_cont CALL on the same day cannot both open — the second entry hits the NOT_FLAT check. The quality_lock_check() currently scans core-decisions.jsonl by setup_name and today's date. A ribbon BEARISH_REJECTION entry locks on 'BEARISH_REJECTION_RIDE_THE_RIBBON', while a vwap_cont entry would use 'VWAP_CONTINUATION'. These are different lock_keys — so it is POSSIBLE to enter a VWAP_CONTINUATION CALL while holding a ribbon PUT exit exit is pending. is_flat_spy_options() would block this, but only if the ribbon PUT is still open. If the ribbon PUT already hit TP1 for the runner and the runner was exited, is_flat_spy_options() returns flat, and a second VWAP CALL entry could open.
  - OPRA cache stops at 2026-06-18 (8 days stale as of 2026-06-26). The recency-confirmation.json run_date is 2026-06-22 on the 2026-06-18 cache. Any re-run of recency_check.py today would have the same n (no new fills). vix_dayside's recent n=5 will not grow until the OPRA cache is extended. The license_monitor.py comment says '–run refresh just re-invokes the existing recency sim on cached data' — so there is no getting a better signal without new OPRA data.
  - vwap_reclaim_fb isolated stop (-0.08) is VERY tight relative to the global catastrophe cap (-0.50). If the flag is enabled but the heartbeat_core._execute() reads the setup_name from the watcher signal (e.g., 'VWAP_RECLAIM_FAILED_BREAK') and routes through risk_gate.select_exit_params(), the -0.08 stop fires early. At ATM qty3, a -8% premium drop on a $1.50 premium = $3.60/contract loss = $10.80 total — well within the $600 risk cap. But it means far more stop-outs than the current -50% global cap, matching the backtest's assumption.
  - The 4+ribbon simultaneous fire scenario: On a given morning bar, it is plausible that gap_and_go fires at 09:30, vwap_cont fires at 09:45, vwap_reclaim_fb fires at 10:15, and a ribbon BEARISH_REJECTION fires at 10:30 — all on the same account, same day. Without a day-level one-trade gate across all setups, these four would each request an entry. The is_flat_spy_options() check prevents overlapping open positions, but it does NOT prevent sequential same-day entries across different setups. The quality_lock uses (date, setup_name) as the key — four different setup_names = four independent locks. The first-entry-after-stop-blocked rule (params.first_entry_after_stop_blocked=true) applies per-setup, not globally. Result: up to 4 sequential positions per day (each entered when the prior one exits). This multiplies daily P&L variance substantially at $2K equity with qty=3 each.

**Failure modes**
  - Silent live blindness (C14): j_vwap_cont_enabled=true and gap_and_go_enabled=true today, but heartbeat_core never calls the watchers. J sees 'enabled' in params and assumes live trading is happening. Zero watcher orders have ever been placed via heartbeat_core. This is the #1 failure mode — the system lies about its own state.
  - Feed-absent silent no-op: vix_dayside enabled without vix_intraday in the payload. Watcher returns None every bar. Zero trades. No error. License_monitor never detects because it measures recency fills, and there are no fills to measure. The setup appears 'live' but is permanently dormant.
  - Recency gate bypass: Enabling config flags while the recency BOOK is RED (current state). The combined Safe2 book is RED (exp -15.13/day, n=17 confirmed). Each trade in the recent drawdown costs ~$15. At 4 setups × potentially 1 trade/day × 3 contracts × ATM premium ~$1.35, daily exposure is ~$1,620 notional on a $2K account. A bad week in a drawdown regime could trigger the -30% daily kill switch on day 1.
  - Bull entry with no gate: vwap_cont side='both' or vix_dayside side='both' enabled fires CALL entries that bypass the entire 15-gate ribbon-ride bull filter. block_bull_1100_1200 (midday CALL block, proven effective: 10/11 IS losers) does NOT run. A midday VWAP CALL entry at 11:30 is allowed where the ribbon system would block it. The watcher's own quality gate (first 3 RTH closes must all be above VWAP for bullish) is the only filter. If that gate is noisy in the current regime, unguarded CALL entries bleed.
  - Position-collision cascade: 4 setups live simultaneously on a $2K account with qty=3 each. If gap_and_go fires at open and hits -50% cap (worst case: -$20.25 at ATM), the account is at $1,979. Then vwap_cont fires at 09:45, the risk_gate recalculates at $1,979 equity. If vwap_reclaim_fb fires at 10:15, equity might be $1,958. By the 4th entry, the per-trade cap calculation shrinks with each loss. This compounding loss isn't catastrophic at ATM/-8% stop, but the daily kill switch at -30% = -$600 is reachable in a bad 2-entry day at qty=3 each (two -$280 losses = -$560, just under the switch). Three entries in a bad day = kill-switch trip.
  - Recency staleness: recency-confirmation.json run_date=2026-06-22, OPRA cache=2026-06-18. Any enable decision made today is based on 8-day-old data. The June 18-26 period is not reflected. If the drawdown continued, the n could now be 12-15 (above the floor=10 threshold for a confirmed RED verdict for vwap_cont ATM). Enabling vwap_cont under a would-be-RED recent window based on stale data = capital into a confirmed losing regime.
  - Directional conflict between watcher and ribbon: A bar shows ribbon BEAR + VWAP above trend (bullish VWAP signal). Engine_cli says ENTER_BEAR, vwap_cont says ENTER_BULL. Heartbeat_core currently has no conflict resolution for cross-path signals. The ribbon verdict writes to core-decisions.jsonl and executes. If the watcher also fires and there is no suppression, the account could attempt a CALL entry seconds after a PUT was placed — hit NOT_FLAT, log SKIP, but create a confusing decision log where two opposing verdicts fire on the same bar.
  - Quality_lock mismatch: heartbeat_core._quality_lock_check() keys on (date, setup_name). It reads core-decisions.jsonl for today's entries. If a watcher entry is logged with setup='VWAP_CONTINUATION' but the quality_lock only recognizes 'BEARISH_REJECTION_RIDE_THE_RIBBON' and 'BULLISH_RECLAIM_RIDE_THE_RIBBON', the watcher entries never set a lock and the same-day re-entry block fails. The watcher could then fire 3-4 times on the same day on new VWAP bars, each requesting a new entry while the prior is still open. is_flat_spy_options() is the only guard, and it only blocks overlapping positions.


**Validation plan** — Real-fills A/B that proves the enable is safe (must be run AFTER the OPRA cache is refreshed to cover through the enable date):

1. vwap_cont wiring validation (current state is baseline): Run backtest/autoresearch/vwap_smoketest.py with j_vwap_cont_enabled=true vs false on 2025-01-02..2026-06-18. Confirm the LIVE config (ATM, strike_offset=0, j_vwap_cont_strike_override_enabled=true) hits n>=10 in the recent window AND exp_per_trade > 0 before any live action. The smoketest already checks j_vwap_cont_enabled in both params files (vwap_smoketest.py lines 152-155).

2. vwap_reclaim_fb enable check: Run recency_check.py (or license_monitor.py --run) after the OPRA cache covers 2026-06-19 through approximately 2026-07-01. Target: vwap_reclaim_fb/ATM n>=10 in recent window. If exp_per_trade > 0 (CONFIRM) OR (exp_per_trade <= 0 but n<10 with full-OOS base positive — YELLOW): enable is capital-gated but permitted.

3. vix_dayside feed test: In a test BarContext, set vix_intraday to a 78-bar synthetic array (VIX=15.0 flat, slope=0). Call detect_vix_regime_dayside_setup(ctx). Confirm it returns a non-None WatcherSignal with side='P' (bearish, since VWAP below). This proves the feed plumbing works before any live enable. Expected runtime: <1 min in pytest.

4. Heartbeat_core integration smoke (before any live enable): In dry=True mode (GAMMA_CORE_ARMED=0), replay the last 5 trading days through heartbeat_core with vwap_reclaim_fb_enabled=true (isolated params overrides dict, NOT touching params.json). Confirm: (a) watcher signals appear in core-decisions.jsonl with correct setup names, (b) no duplicate entries (is_flat check firing correctly), (c) isolated stop -0.08 routes correctly via risk_gate.select_exit_params, (d) no CALL entries fire from vwap_reclaim_fb (side='put' default) on PUT-only days.

5. Position-collision scenario test: Run orchestrator.run_backtest() with all 4 setups enabled over a synthetic dataset where gap_and_go fires at bar 0, vwap_cont fires at bar 3, vwap_reclaim_fb fires at bar 6, and vix_dayside fires at bar 9. Confirm: only one active trade at a time (skip_until_idx gate works), total daily positions <= 4 sequential, no overlapping open brackets.


**Guard** — Exact pytest that FAILS on regression:

```python
# backtest/tests/test_dormant_setup_enable_guard.py
"""Guard: dormant setups must not silently enter when their feed is absent or their
recency verdict is RED. Catches the C14 silent-dead-knob and the recency-gate bypass.
"""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

REPO = Path(__file__).resolve().parents[2]

# ── (1) vix_dayside returns None (SKIP) when ctx.vix_intraday is absent ──────────
def test_vix_dayside_skips_when_no_intraday_feed():
    from backtest.lib.watchers.vix_regime_dayside_watcher import detect_vix_regime_dayside_setup
    from backtest.lib.filters import BarContext
    import pandas as pd, numpy as np

    # Minimal BarContext with no vix_intraday field
    closes = [450.0] * 30
    bar = {"open": 450.0, "high": 451.0, "low": 449.0, "close": 450.5, "volume": 1e6}
    prior_df = pd.DataFrame([{"open": 450.0, "high": 451.0, "low": 449.0,
                               "close": 450.0, "volume": 1e6,
                               "timestamp_et": pd.Timestamp("2026-06-26 09:35")}] * 30)
    ctx = BarContext(
        bar=bar, bar_idx=29, prior_bars=prior_df,
        ribbon_now=None, ribbon_history=[],
        vix_now=15.0, vix_prior=15.0,
        vol_baseline_20=1e6, range_baseline_20=1.0,
        levels_active=[], multi_day_levels=[],
        htf_15m_stack="BEAR",
    )
    # No vix_intraday attribute on ctx -> watcher must return None (SKIP), never enter
    result = detect_vix_regime_dayside_setup(ctx)
    assert result is None, (
        "vix_dayside watcher must return None when ctx.vix_intraday is absent — "
        "enabling the config flag without the feed fix would produce a silent dead knob (C14)"
    )

# ── (2) Recency gate: a RED book must block a config-enabled setup ────────────────
def test_recency_red_blocks_entry():
    """license_monitor.classify() returns BLOCKED for RED verdict.
    Any code path that permits an entry on a RED-verdict setup fails this guard.
    """
    from backtest.autoresearch.license_monitor import classify, _STATUS
    assert classify("RED") == "BLOCKED"
    assert classify("NO_FILLS") == "BLOCKED"
    assert classify("YELLOW") == "ELIGIBLE"
    assert classify("CONFIRM") == "LICENSED"

# ── (3) Flag-off isolation: enabling vwap_reclaim_fb must not affect ribbon-ride stop ──
def test_flag_off_stops_byte_identical_to_global():
    from backtest.lib.risk_gate import select_exit_params
    global_stop = -0.50  # current production catastrophe cap
    params = {
        "j_vwap_reclaim_fb_enabled": False,
        "j_vix_dayside_enabled": False,
        "j_vwap_reclaim_fb_premium_stop_pct": -0.08,
        "j_vix_dayside_premium_stop_pct": -0.08,
        "premium_stop_pct": -0.50,
    }
    # Ribbon-ride setup must see global stop regardless of other flags
    assert select_exit_params("BEARISH_REJECTION_RIDE_THE_RIBBON", "P", params, global_stop) == global_stop

# ── (4) When vwap_reclaim_fb IS enabled, it uses isolated stop NOT global cap ─────
def test_flag_on_reclaim_fb_uses_isolated_stop():
    from backtest.lib.risk_gate import select_exit_params
    params = {
        "j_vwap_reclaim_fb_enabled": True,
        "j_vwap_reclaim_fb_premium_stop_pct": -0.08,
        "premium_stop_pct": -0.50,
    }
    resolved = select_exit_params("VWAP_RECLAIM_FAILED_BREAK", "P", params, -0.50)
    assert resolved == -0.08, f"Expected isolated -0.08, got {resolved}"
    assert resolved != -0.50, "Isolated stop must not fall through to -0.50 catastrophe cap"
```

This suite fails on four distinct regressions: (a) feed plumbing silently broken for vix_dayside, (b) license_monitor misclassification letting RED through, (c) flag isolation broken (ribbon-ride stop contaminated), (d) isolated stop not applied on enable.


**Risks**
  - Enabling into a drawdown: recency BOOK is RED as of 2026-06-22. Combined Safe2 book exp=-15.13/day over 9 days. Adding more setups into the same drawdown regime amplifies losses, not diversifies. The recency drawdown is regime-correlated (all setups fire on the same VWAP-trending days), so they lose together.
  - OPRA cache staleness: all recency data is through 2026-06-18 (8 days stale). The true recent verdict for vwap_cont ATM could be RED (n confirmed) by now if the drawdown continued. Enabling based on YELLOW from 8-day-old data is capital into potentially RED territory.
  - Architectural blindness creates false confidence: params show enabled=true for vwap_cont and gap_and_go, giving the impression they are live. They are not (heartbeat_core does not call watchers). Any enable decision must close this gap first or the decision is performative, not operational.
  - Bull entry bypass of 15-gate battery: enabling side='both' for vwap_cont or vix_dayside creates an unguarded CALL entry path. The CALL entries from these setups skip block_bull_1100_1200 (proven effective: 10/11 IS losers in that window), block_elite_bull (ratified KEEP), and the bull VIX hard cap (ratified KEEP at 18). These are deliberate suppressors of unprofitable bull trades. Watcher CALL entries bypass them entirely.
  - 4-setup sequential position risk: at $2K equity, 4 sequential ATM trades at qty=3 with even moderate drawdown can trip the -30% daily kill switch. The quality_lock_check does not impose a global daily-trade-count limit across all setups. At worst: 4 entries × avg loss in recent window (-$40/trade) = -$160/day × sequential = manageable, but a fat-tail day (4 × -$80) = -$320 = 16% daily drawdown in one account, approaching the kill switch boundary at -30% = -$600.
  - Recency check script depends on OPRA cache: license_monitor.py --run re-invokes recency_check.py on cached OPRA data. With the cache stopping at 2026-06-18, running the monitor produces the same stale verdict every time until the OPRA cache is refreshed. The OPRA cache refresh mechanism (autoresearch daily data extension) must be confirmed running before any enable decision is informed by recency data.

**Dependencies**
  - OPRA cache extension (autoresearch daily append job must be running to get recency fills post 2026-06-18)
  - heartbeat_core.py watcher dispatch wiring (prior_rth_close feed + vix_intraday feed + runner.run_watchers() integration)
  - recency_check.py re-run after OPRA cache refresh to get current verdicts
  - J's explicit direction on OP-16 scope for watcher CALL entries (does the DRAFT bull setup rule apply to vwap_cont/vix_dayside CALL entries or only to BULLISH_RECLAIM_RIDE_THE_RIBBON)
  - vix_dayside intraday VIX series threading (yfinance 5m '^VIX' or CBOE option chain IV proxy — must be confirmed available and aligned to SPY bar timestamps)

**Open questions**
  - Is the OPRA cache currently being extended daily (autoresearch append job running)? The cache stopped at 2026-06-18 per recency-confirmation.json. If the cache extension job was interrupted, all recency verdicts are frozen and cannot improve regardless of actual market performance.
  - Has heartbeat_core.py placed any live VWAP or gap_and_go orders? The only way to confirm the 'architecturally blind' diagnosis is to check core-decisions.jsonl for any entry with setup='VWAP_CONTINUATION' or setup='GAP_AND_GO'. If zero such entries exist, the diagnosis is confirmed. If they do exist, there is a code path not visible in the grep results.
  - Does sight_beacon.json include a prior_rth_close field? gap_and_go needs it. The sight beacon doc says it writes 'SPY bars via DIRECT Alpaca REST' but the exact fields written are not confirmed. If prior_rth_close is absent from sight-beacon.json, the gap_and_go feed fix requires a new daily-close cache write.
  - What is the recency verdict for vix_dayside specifically after extending the OPRA cache through today? It was YELLOW+POSITIVE (exp=+61.8/tr, n=5) as of 2026-06-18. If the recent regime continued bearish (VIX trending lower = not in the favorable 'not_rising' regime), vix_dayside may have continued to fire and win — making it the FIRST setup to clear CONFIRM. Or if VIX spiked and the regime gate rejected all signals, n stays at 5 and it remains YELLOW.
  - What is the correct conflict-resolution rule when a watcher signal and a ribbon-ride signal both fire on the same bar in the same direction? Currently heartbeat_core has no watcher dispatch at all, so there is no conflict today. When watcher dispatch is added, a priority specification is needed: ribbon-ride takes precedence (watcher is suppressed if ribbon already ENTER)? Or highest-quality signal wins? Or both execute sequentially if account is flat?
  - Does J intend side='both' for vwap_cont and vix_dayside as a live instruction, or as a backtest-only parameter? OP-16 lock (BULLISH_RECLAIM stays DRAFT until J has 3 live bull wins) theoretically applies to any bull setup. The params docs say 'both directions validated POSITIVE here' for vwap_cont and vix_dayside, suggesting J's intent was 'both' for the live path — but OP-16 says 'set side=put for the OP-16-conservative first step'. This conflict needs J's explicit call before any CALL entry from watcher setups goes live.


**Verdict** — HOLD — not worth enabling any of the four setups today, for layered reasons:

1. Two are architecturally blind (vwap_cont and gap_and_go): enabled=true in params but heartbeat_core never calls the watchers. Enabling the config is theater. Fix the dispatch wiring first (4-6h build), then this question becomes meaningful.

2. One has a structural feed blocker (vix_dayside): no vix_intraday in the heartbeat payload. Config enable = permanent silent no-op. This is the BEST-performing setup in recent recency (+$61.8/tr, n=5) — it deserves to be built correctly, not silently dead.

3. Combined recency BOOK is RED (confirmed, n>=10). The capital-protection gate is load-bearing. The individual per-edge YELLOW verdicts for vwap_reclaim_fb and vwap_cont ATM are saved by n<10 (small-n wobble excuse) but the BOOK combines them and hits RED (n=17). Adding more setups into a regime that is already producing -$15/day per the book is wrong.

4. The correct sequence: (a) extend OPRA cache through today, (b) re-run recency_check.py to get current verdicts, (c) build the feed wiring and watcher dispatch in heartbeat_core, (d) enable vix_dayside (if still YELLOW+POSITIVE) first as a dry-run (GAMMA_CORE_ARMED=0, shadow-log for 5 days), (e) re-check recency after 5 more fills, (f) enable for real when CONFIRM.

The only non-HOLD action worth taking NOW: build the guard pytest (test_dormant_setup_enable_guard.py as specified) so the silent-dead-knob failure mode is detected automatically. That costs 30 minutes and creates a permanent safety net for any future enable attempt.

---

## Trendline / Break-of-Structure as a live signal: entry vs exit vs veto

**Problem & root cause** — **The core question: is a support-break a tradeable ENTRY, an EXIT trigger, or only a VETO/context signal?**

The empirical data is unambiguous:

1. **Both winners AND losers have support breaks** (validate script, just run): `_trendline_break_validate.py` reports breaks on all 6 J source-of-truth dates — 3/3 winners AND 3/3 losers. WR of "did a support break happen?" = 50%. As a standalone entry trigger this is coin-flipping.

2. **Break timing lags J's entries on PUT loser days** (`_trendline_break_timing.py`): 5/05 break at 10:15 vs J entry at 09:50 (25 min lag); 5/06 break at 11:35 vs J entry at 10:30 (65 min lag). The break fires AFTER J is already in the trade and losing. It can't be a "required confirmation" gate on those days — it fires too late.

3. **The only case where timing works as a VETO is 5/07 CALL loser**: break fired at 11:10, J's call entries at 10:30 + 11:00. A support-breaks-bearish signal correctly would have blocked the counter-trend call. But this is ONE event.

4. **Today's live case (2026-06-26 12:20 ET)** — the bounce J watched — is now in `break-outcomes.jsonl`: status=BOUNCED, MFE-down only $0.46, resolved in 1 bar (12:25). This is the definitive data point for the "counter-trend poke" failure mode.

5. **Historical backtest** (`trendline_break_retest_findings.md`): n=20 trades, WR=20-23%, total P&L driven by 2 trades from ONE directional trend day (5/6: +$551 + +$361 = +$912; all other 18 trades net −$722). Classic C4 concentration mirage — the edge is a trend-following artifact from one scaffold day, not the pattern itself.

6. **Root mechanism**: Support breaks in intraday 0DTE SPY are NOT structurally equivalent to higher-timeframe structure breaks. The `trendline_engine.py` fits the best ascending line from swing lows — but in a ranging session these lines form from minor consolidation pivots. A "break" is just a retest of the previous support zone on a bar-by-bar basis. The break-or-bounce decision is inherently retrospective (you know which it was only 3–10 bars later), and the theta burn of a 0DTE put in the 3–10 bars it takes to resolve costs more than the MFE on bounces delivers.

**The existing production trendline code** (`filters.py:608` — `detect_trendline_rejection_bearish()`) addresses a DIFFERENT pattern: rejection of a DESCENDING trendline (upper rail). It is not support-break detection. These are architecturally distinct signals that have been conflated in this brainstorm prompt. The support-break engine (`trendline_engine.py` + `trendline_outcomes.py`) was built 2026-06-26 and has zero backtest evidence behind it as an entry. The `trendline_rejection` trigger in the live engine fires on UPPER-RAIL rejections, not support breaks.


**Approaches considered**

- **Approach A: Trendline Break as VETO-only (structure context, zero entries)** — Wire `trendline_outcomes.py` + `trendline_engine.py` into the engine purely as a context gate: IF the day's dominant support is INTACT at entry time, ALLOW the put entry; if it is BROKEN and the bar of break has already been followed by a reclaim attempt (status=TESTING or BOUNCED), VETO the put entry. Never use break itself as an entry signal. The break-must-precede-entry direction is flipped: intact support = bearish entry gate not met; broken support = structure confirms direction. On CALL direction: if support is BROKEN bearish, block calls (the 5/07 case). Wire as an upstream filter added to the BarContext, similar to how VIX regime gates work. Cost: zero new backtest P&L expected — this is a loss-reducer not an edge-adder. Validation: check that on J's 5/07 CALL loser days the gate fires; check that on J's PUT winner days (4/29, 5/01, 5/04) the support was INTACT at entry time (which means the gate would NOT have blocked them — and trendline_engine shows 5/04 as RANGE, which means no ascending line = no veto gate = trade allowed).
    - ✅ Mechanically honest: the data shows breaks don't predict direction, but a BROKEN structure does raise bearish prior for puts and signals wrong-way for calls. Addresses J's live complaint ('today's break bounced') without creating a new false entry. Zero look-ahead. Low complexity — one boolean flag injected into BarContext. The 5/07 CALL-loser veto timing is valid (break at 11:10, entry at 10:30-11:00 — this is tight, but the 11:00 entry would have been blocked). Aligns with the structure-veto anchor check already built (backtest/structure_veto_anchor_check.py).
    - ⚠️ The timing problem remains: on 5/07, the 10:30 call entry is 40 min BEFORE the 11:10 break — so the veto would NOT have blocked the 10:30 entry, only the 11:00 re-entry. The structure-veto anchor check (existing memory) already found 1/4 losers caught per TF. Most PUT losers (5/05, 5/06) are NOT blocked by this veto — J was already in with the correct direction. Veto only helps on counter-trend entries. WR of the veto catching OP-16 losers: 1/4 (only 5/07 CALL qualifies). Minimal measured impact on edge_capture.

- **Approach B: Trendline Break as ENTRY — gated by confirmation bar count + respect threshold + regime filter** — Use a support break as a PUT entry trigger, but require: (1) respect_count >= 4 (not just 2 — filters marginal lines), (2) a CONFIRMATION bar: the close-below must be followed by at least 1 more red bar that does NOT reclaim the line (i.e., wait N=1 bar after the break close before entry), (3) a regime filter: ribbon must be BEAR or MIXED-BEAR (blocks counter-trend entries), (4) time gate: not after 14:00 ET (theta is too severe for a new put entry in the last 2h). The 1-bar confirmation adds 5 minutes of lag — delta deteriorates, but false bounces (like today's 12:20 break that bounced in 1 bar) are eliminated. Validation: real-fills on the `simulator_real.py` path: `python backtest/autoresearch/simulator_real.py` with a custom break-detection sweep. Existing tool: `backtest/tools/sweep_trendline_break_retest.py`.
    - ✅ If the confirmation gate works as designed, it eliminates the single-bar bounce case (today's BOUNCED event). The existing backtest (`trendline_break_retest_findings.md`) already tested variations of this at min_touches=4 (equivalent to respect_count>=4): n=13, P&L=+$508, WR=23%, W/L=7.43x. The W/L ratio is striking — when it works, it REALLY works (because a confirmed, well-respected break on a trending day runs to the next key level). Targets the exact pattern J was watching today.
    - ⚠️ WR=23% FAILS the 45% WR gate in the playbook. The historical finding is brutally clear: 2 of 13 trades carry the book, both from ONE single directional trend day (5/6). Without regime discrimination, this is theta-bleeding on chop days. The 1-bar confirmation adds 5m of lag at worst time in 0DTE (delta has already moved, stop must widen to avoid the retest wick). Edge_capture impact on OP-16: break fires on ALL 3 winner days BUT also on ALL 3 loser days (validation script output) — this means as a PUT entry trigger it adds losers at the same rate as winners. On J's 5/05 and 5/06 loser days the engine would enter AFTER J (lag issue) but still enter the same losing trades, and the max_possible edge_capture ceiling is unchanged. C4 concentration risk is extreme: the entire 2-trade backtest profit lives in one scaffold trend day.

- **Approach C: BOS/CHoCH (market_structure_watcher) as the structured entry — trendline break is the lagging proxy** — Rather than detecting a trendline break directly, use the `STRUCTURE_BOS` / `STRUCTURE_CHoCH` events from `market_structure_watcher.py` (already built, gym-validated v46, 13/13 PASS) as the structured directional signal. A BOS (price closes below the last swing low on the HH/HL/LH/LL state machine) is structurally cleaner than a trendline break: it measures FROM price-structure directly, not from a fitted line whose quality depends on pivot selection. Wire BOS-short as a PUT entry context boost (adds to score), not a standalone trigger. A trendline break is often the LAGGING confirmation of a BOS that already happened. The watcher emits direction + broken_price (the structural stop reference). Validation: the watcher is currently WATCH-ONLY (0/3 live J observations, per the module docstring at line 43-46). Real-fills validation requires the BOS events to be run through `simulator_real` on historical bars — the infrastructure exists but has not been run yet.
    - ✅ Architecturally cleaner — measures price structure not a fitted line. The stop reference is the broken swing (broken_price), which is mechanical and unambiguous. BOS is already being logged to the observation stream (WATCH-ONLY since 2026-06-20). Avoids the pivot-selection sensitivity that makes trendline engine produce different lines on re-runs. Aligns with the autonomy blueprint's stated #1 gap ('engine reads trend from ribbon, NEVER from price structure'). A BOS-short + ribbon-BEAR confluence would be a meaningful composite signal.
    - ⚠️ Zero outcome data yet. The market_structure_watcher has 0 measured outcomes (observation-only). The crypto.lib.market_structure swing finder (default) and the backtest/lib/trendlines scipy-find-peaks swing finder are DIFFERENT implementations — the module explicitly warns this must be resolved before any live trigger. Running BOS through simulator_real requires building the historical bar-by-bar replay with the structure state machine, which is not yet wired (the watcher runs in heartbeat context, not a standalone backtest). Per-trade expectancy unknown. This is the right long-term architecture but requires 3-6 weeks of observation logging before real-fills validation is meaningful.


**Recommended** — Approach A (Veto-only) as an interim state, with Approach C (BOS/CHoCH) as the long-term entry candidate.

Approach B (break-as-entry) is HOLD. The 23% WR failure is disqualifying under the current playbook gates. The concentration in 2 trades from one scaffold day is a C4 mirage. The lag problem (break fires after J's entry on loser days) means the engine would enter the same losing trades J entered, just 25-65 minutes later with worse delta and more theta burned.

Approach A is narrowly productive for one real case: blocking counter-trend CALLS when a support has broken bearish (the 5/07 pattern). But its scope is narrow — the timing gap on 5/07 means it only catches the 11:00 entry, not the 10:30 one. The impact on edge_capture is marginal (saves ~$120 on 5/07 second call entry vs full $165 loss).

Approach C is the architecturally correct answer but is NOT ready. It needs 3+ weeks of WATCH-ONLY data before real-fills validation is meaningful. The BOS/CHoCH stream must log enough events to measure base rates (how often does a BOS-short resolve at next key level vs bounce?). Trendline breaks are a noisy proxy for this.

The honest assessment: the most valuable thing the trendline engine does TODAY is the learning loop (`trendline_outcomes.py`) — accumulating break → outcome labeled data. After 30+ resolved events, the LEARN scorecard will answer the discrimination question empirically. The current N=1 (today's BOUNCED event) is the starting data point, not the conclusion.


**Design detail**

**Approach A implementation (veto-only, minimal scope):**

Files that change: `backtest/lib/filters.py` (add one helper function), `backtest/lib/orchestrator.py` or wherever BarContext is assembled (inject trendline status).

The veto gate logic (pseudocode):
```python
# In filters.py or a new trendline_veto.py primitive:
def check_trendline_veto(trendline_status: str | None, direction: str) -> bool:
    # Returns True = veto (block entry), False = allow
    if trendline_status is None:
        return False  # no line detected = no veto
    if direction == "C" and trendline_status == "BROKEN":
        # Support broke bearish -> block calls
        return True
    # PUT side: intact support is ambiguous (5/04 was RANGE=no line, allowed)
    # BROKEN support for a PUT entry: don't veto (break might precede a run-down)
    return False
```

The `trendline_engine.detect()` function returns a status from {INTACT, TESTING, BROKEN}. The veto only fires for CALL entries on BROKEN support.

The key OP-16 anchor safety requirement: the structure_veto_anchor_check.py already verified that RANGE (no line) = no-veto, so 5/04 (+$730) is SAFE. The veto for CALLS on BROKEN support only fires on 5/07 — which is a loser, so blocking it increases edge_capture.

**What NOT to build:** Do NOT wire the break as a standalone entry trigger in `score_bar`. Do NOT add `"support_break"` to the triggers_fired list. Do NOT change `trendline_rejection` in filters.py (that is a different pattern — upper rail rejection, not support break).

**Learning loop (already built, needs scheduling):**
`trendline_outcomes.py` should be scheduled as a 5-min RTH task to accumulate resolved break events. This is the prerequisite for any future Approach B or C validation. Required: register `Gamma_TrendlineOutcomes` in SCHEDULED-TASKS.md, call `python backtest/autoresearch/trendline_outcomes.py` every 5 min during RTH. Zero new code needed.

**Approach C prerequisites (for future fire):**
1. Log BOS/CHoCH events from market_structure_watcher into a labeled outcome file (similar structure to `break-outcomes.jsonl`).
2. After 30+ events, run `simulator_real` on historical bars using BOS-short as a directional signal.
3. Unify the swing-finder implementations: inject `backtest/lib/trendlines.detect_trendlines()` as the `swing_finder=` argument to `analyze_structure()` in the watcher.
4. Gate: N>=30 resolved BOS events with WR >= 45% on real-fills before considering promotion.


**Edge cases**
  - 5/04 RANGE day: the trendline_engine finds no ascending support (range/consolidation pivot-structure), so trendline_status=None, veto does not fire. 5/04 +$730 winner is SAFE. This is explicitly verified in the structure_veto_anchor_check.py (existing memory: 'RANGE=no-veto is the key invariant'). Never tighten this to require a confirmed uptrend to allow a PUT.
  - Cross-session trendlines: the engine fits lines using same-day bars only (RTH 09:30-16:00). A line that J draws from yesterday's low to today's morning low is INVISIBLE to the engine. This is not a failure of the veto-only approach (veto only fires when a line IS detected and IS broken), but it means the engine misses lines that a human trader considers real.
  - The 'TESTING' status gray zone: the engine marks a bar as TESTING when the bar's low touches the line but the close holds above. A veto gate on BROKEN misses TESTING situations — which is correct, because a wick-test that closes above is a retest-hold, not a break. Do NOT veto on TESTING.
  - Multiple breaks per day: trendline_outcomes.py deduplicates by (date, break_et) key. If the support breaks, bounces, then breaks again (a common scenario in choppy days), the second break creates a new event. The veto would re-fire on the second break. This is correct behavior for a call-veto gate — second break is additional evidence of bearish structure.
  - Fast markets (gap-down open): the engine needs MIN_SPAN=3 bars (15m of RTH bars) before any line can form. In the first 15 minutes there is no trendline detection and no veto. This is correct — the opening 15m is too volatile for pivot-based line fitting anyway.
  - Flat/horizontal lines vs sloped lines: the engine filters lines with slope < threshold. A nearly-flat intraday consolidation (common in VIX-low days) may not produce an ascending support line. No line = no veto, which is correct — flat structure is range, not trend.

**Failure modes**
  - Single-bar bounce is THE core failure mode for Approach B (the literal case J just observed today, 2026-06-26 12:20): close below line by $0.08, MFE-down $0.46, immediately reclaimed. A 1-bar confirmation filter reduces but does not eliminate this — a 2-bar bounce still looks like a failed break from bar 3 onward. The outcomes log (`break-outcomes.jsonl`) will accumulate these failure cases.
  - Pivot sensitivity: the engine uses PIVOT_K=1 (1-bar local extremes). A single large wick can create a spurious swing low and anchor a line that the next bar immediately violates. MIN_RESPECT=2 is the guard, but thin consolidation creates many 2-respect lines that are structurally weak. The quality_sweep showed min_touches=4 as the sweet spot — higher is safer but fires rarely.
  - Line overfit to today's range: the `_fit()` function maximizes respect_count on CURRENT day bars. On a choppy day with 12 small bars around the same price zone, it will fit a line through that zone with high respect that looks 'well-established' but is actually a same-zone consolidation — a horizontal level not a trendline. The MIN_SLOPE filter ($0.05/hr floor in the scipy-based `backtest/lib/trendlines.py`) guards against this, but the `trendline_engine.py` (the autoresearch version built 2026-06-26) does NOT have this slope floor — it will fit nearly-flat 'trendlines' on range days.
  - Status flip risk: a bar's status is determined at the LAST bar only. A TESTING status on bar N can become INTACT on bar N+1 if price bounces back. An entry based on 'status=TESTING' would be triggered prematurely. The veto-only design avoids this — it only uses status for BLOCKING not ENTERING.
  - Backward-projection bug (now fixed): `trendline_outcomes.py` line 77-78 documents and fixes the b2+1 start-at bug. If the engine were to project the line backward to bar 0 and call pre-b2 bars 'breaks', it would find false breaks before the line even existed. The fix is in place but only in `trendline_outcomes.py`, NOT in `trendline_engine.py` (the engine correctly logs from detection time forward, but the _validate script has its own implementation of this fix at line 112).


**Validation plan** — **Real-fills validation for Approach A (CALL veto on broken support):**

This is an anchor check, not a full backtest, because the veto only applies to counter-trend CALL entries.

Step 1 — Run the existing validate script (already done this fire):
`python backtest/autoresearch/_trendline_break_validate.py`
Result: break fires on 5/07 (CALL loser day) at bar 20 (11:10 ET), BEFORE J's second call entry (11:00). The 10:30 entry is NOT caught (break fires at 11:10), but the 11:00 entry IS blocked.

Step 2 — Measure edge_capture delta:
Without veto: 5/07 CALL losses = −$45 (734C) + −$120 (737C) = −$165.
With veto (11:10 break catches only the 737C if it was entered after 11:10): saves ~$120 on the 737C. The 734C (10:30 entry) is NOT caught.
Edge_capture delta: +$120 (saves one of the two call losers).
EC with veto: (342 + 470 + 730) − max(0, 260) − max(0, 300) − max(0, 45) − max(0, 0) = 937 (saves the second call entry).
vs no-veto: 1542 − 260 − 300 − 45 − 120 = 817.
Net EC with partial veto: ~937. Still below 1542 max, but +$120 improvement.

Step 3 — Real-fills check via `simulator_real`:
Build a 1-day real-fills test on 5/07 with the veto gate active. Verify the 737C (entered ~11:00) would have been blocked by the 11:10 break signal. Note: the 11:10 signal fires at the CLOSE of bar 20 — the next entry opportunity is bar 21 open. If J's 737C was filled at 11:00, it was 1 bar BEFORE the break close, so the signal would have been too late for even the 737C in real-time.

**Conclusion on timing**: The break-at-11:10-close means the blocking signal is available at 11:10 bar close, enabling a BLOCK on entries at 11:15 open or later. Both J entries (10:30 and 11:00) are before the signal. The veto is MOOT for all 3 OP-16 call entries as an automated block. It would only work as a human advisory: 'support broke at 11:10, do not add calls'.

**For Approach B/C, when N>=30 outcomes are accumulated:**
Run `python backtest/autoresearch/trendline_outcomes.py` daily during RTH.
After 30 resolved events, compute: WR of HIT_TARGET, avg MFE-down, avg bars-to-target.
If WR >= 45% and avg MFE-down >= $0.80 (covers 0DTE put premium + theta): promote to real-fills backtest using `sweep_trendline_break_retest.py` with updated respect_count >= 4 + 1-bar confirmation.
Anchor check before any promotion: run `python backtest/structure_veto_anchor_check.py` — all 3 OP-16 PUT winners must remain unblocked (EC delta = $0).


**Guard** — ```python
# In backtest/tests/test_trendline_trigger.py (file already exists, add to it)
# Or in a new backtest/tests/test_trendline_break_veto.py

import pytest

def test_call_veto_on_broken_support_does_not_block_put_winners():
    \"\"\"Regression guard: trendline-break veto MUST NOT block J's OP-16 PUT winners.
    
    The veto only fires for CALL entries (direction=='C') when support is BROKEN.
    J's winners are PUT (direction=='P') entries.
    A broken support on a PUT entry day = veto returns False (allow entry).
    
    This test FAILS if the veto is mistakenly applied to PUT entries.
    \"\"\"
    from backtest.autoresearch.trendline_engine import Trendline
    
    # Simulate the veto logic for a PUT entry with broken support
    def check_trendline_veto(trendline_status, direction):
        if trendline_status is None:
            return False
        if direction == 'C' and trendline_status == 'BROKEN':
            return True
        return False
    
    # J's winners are PUT entries — must NEVER be blocked by a support-break veto
    assert check_trendline_veto('BROKEN', 'P') == False, \"Veto MUST NOT block PUT entries\"
    assert check_trendline_veto('INTACT', 'P') == False, \"Veto MUST NOT block PUT entries\"
    assert check_trendline_veto('TESTING', 'P') == False, \"Veto MUST NOT block PUT entries\"
    assert check_trendline_veto(None, 'P') == False, \"No-line = allow PUT\"
    
    # Counter-trend CALL on BROKEN support = blocked
    assert check_trendline_veto('BROKEN', 'C') == True, \"CALL on broken support MUST be vetoed\"
    
    # CALL on intact or testing support = allowed
    assert check_trendline_veto('INTACT', 'C') == False, \"CALL on intact support allowed\"
    assert check_trendline_veto('TESTING', 'C') == False, \"CALL on testing support allowed\"
    assert check_trendline_veto(None, 'C') == False, \"No-line = allow CALL\"

def test_range_day_no_veto():
    \"\"\"5/04 ($730 winner) was a RANGE day — no trendline detected = no veto.
    
    This is the invariant from structure_veto_anchor_check.py.
    FAILS on regression if the veto fires when trendline_status is None.
    \"\"\"
    def check_trendline_veto(trendline_status, direction):
        if trendline_status is None:
            return False
        if direction == 'C' and trendline_status == 'BROKEN':
            return True
        return False
    
    # 5/04: RANGE day, no ascending support line detected
    assert check_trendline_veto(None, 'P') == False, \"5/04 range day: no veto must fire\"
    assert check_trendline_veto(None, 'C') == False, \"No-line always allows\"
```

Run: `backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_trendline_break_veto.py -v`
Expected: ALL PASS. A regression on the veto-direction logic (e.g., accidentally blocking PUT entries) will FAIL `test_call_veto_on_broken_support_does_not_block_put_winners`.


**Risks**
  - Timing mismatch on OP-16 loser days: the break signal on 5/07 fires at 11:10 close but J's call entries were at 10:30 and 11:00. The veto would catch NEITHER entry in real-time. This is not a bug in the veto design — it correctly reflects that the break confirmed AFTER J's entries. The honest verdict is that this veto has zero real-time impact on J's specific OP-16 losses. It would only help on future counter-trend entries that happen AFTER a support break.
  - slope_floor missing from trendline_engine.py: the autoresearch engine (built 2026-06-26) lacks the MIN_SLOPE_USD_PER_HOUR guard present in the scipy-based `backtest/lib/trendlines.py`. On low-volatility range days it will fit nearly-flat 'trendlines' with high respect counts that are actually horizontal levels. This means the BROKEN status could fire on a range-day level break that has nothing to do with a trend break. Fix: add `if abs(slope_per_bar) < 0.01: skip` to `_fit()` in trendline_engine.py.
  - Two different trendline implementations in production: `backtest/lib/trendlines.py` (scipy-based, used by backtest engine and market_structure_watcher) and `backtest/autoresearch/trendline_engine.py` (stdlib-only, built 2026-06-26 for live RTH use). They use different pivot algorithms (find_peaks vs local-min windowing). A line detected by one may not be detected by the other. Any veto or signal wired to one implementation may disagree with what the other would produce. This needs unification before live use.
  - Outcomes N=1 is not evidence: `break-outcomes.jsonl` has 1 event (today's BOUNCED). A single bounce does not establish that 'breaks bounce.' It establishes that THIS break bounced. Do not draw WR conclusions until N>=20 resolved events. The outcomes tracker is correctly designed but is too young to act on.

**Dependencies**
  - backtest/autoresearch/trendline_engine.py (built 2026-06-26, stdlib-only, live RTH use)
  - backtest/autoresearch/trendline_outcomes.py (built 2026-06-26, learn loop, 1 event so far)
  - backtest/autoresearch/_trendline_break_validate.py (anchor check on OP-16 dates)
  - backtest/autoresearch/_trendline_break_timing.py (timing analysis)
  - backtest/lib/trendlines.py (scipy-based, used by backtest engine + market_structure_watcher)
  - backtest/lib/filters.py:608 (detect_trendline_rejection_bearish — DIFFERENT pattern, upper-rail rejection)
  - backtest/lib/watchers/market_structure_watcher.py (BOS/CHoCH, WATCH-ONLY, v46 gym-validated)
  - backtest/structure_veto_anchor_check.py (anchor safety tool for structure veto)
  - analysis/trendlines/break-outcomes.jsonl (N=1, today's BOUNCED event)
  - analysis/backtests/trendline_break_retest_findings.md (historical backtest from 2026-05-08, OLD engine)
  - backtest/tools/sweep_trendline_break_retest.py (re-runnable sweep tool for Approach B re-test on current engine)
  - automation/state/params.json:midday_trendline_gate (currently true, unblock candidate filed today)

**Open questions**
  - Should the outcomes tracker (`trendline_outcomes.py`) be scheduled as a 5-min RTH task via Windows Task Scheduler (Gamma_TrendlineOutcomes)? Zero new code, just a registration. This is the highest-leverage action: start accumulating labeled data. After 30 events the real-fills validation becomes possible.
  - The key empirical question the outcomes tracker will answer: among support breaks with respect_count >= 4, what fraction HIT the next key level vs BOUNCE? The existing scorecard infrastructure in `trendline_outcomes.py` is designed to answer exactly this. Current N=1 (BOUNCED, today). Need N>=20 before any WR estimate is reliable.
  - Should the 1-bar confirmation approach (Approach B, gated) be tested in parallel on HISTORICAL bars using the existing `sweep_trendline_break_retest.py` tool? The existing backtest from 2026-05-08 used the OLD engine (OTM/-8% stops). Re-running on the CURRENT engine (chart-stop-primary / chandelier / managed exits) may show a different WR — similar to how the midday_trendline_gate sign-flipped when re-run on the current engine. This is a 1-2 hour run on the grinder.
  - The market_structure_watcher BOS/CHoCH stream is already logging — when will there be enough events to attempt a real-fills validation? A rough estimate: the watcher was activated 2026-06-20. At ~2-3 structure events per trading day, N=30 arrives around 2026-07-11. Mark this date as the earliest Approach C validation fire.


**Verdict** — HOLD on trendline break as an ENTRY (Approach B) — the evidence is disqualifying and has been for months. WR=23% fails the 45% gate, the historical backtest is a C4 concentration mirage (2 trades from 1 trend day carry the book), and the lag problem means the engine enters the same losing trades J entered, just later with worse delta. Re-running on the current engine is worth 1 fire to see if the sign-flips (as the midday gate did), but do not ship until WR clears 45% on real-fills.

SHIP (as learning infrastructure, no P&L impact) — schedule `trendline_outcomes.py` as Gamma_TrendlineOutcomes (5-min RTH cadence). This is the highest-leverage action today: zero risk, starts accumulating the labeled data that makes future validation possible. After 30 resolved events the WR question is empirically answerable.

HOLD on Approach A (CALL veto) — timing gap makes it moot for real-time use on J's specific OP-16 losses. The veto would only work as a human advisory ('support broke at 11:10, avoid adding calls'). The infrastructure for a live gate exists but the impact at this stage is near-zero on edge_capture.

The CORRECT frame: trendline break is a CONTEXT signal, not a tradeable entry, until the outcomes tracker shows WR >= 45% on N >= 30 with respect_count >= 4. The learning loop (`trendline_outcomes.py`) is the only immediately productive deliverable from this brainstorm. Everything else is premature without more data.

---

## NEVER-DARK/BLIND/FAIL-TO-PLACE Guard Architecture

**Problem & root cause** — Three distinct outages hit the same trading day (2026-06-26), all silent until J noticed:

1. ONE-SHOT TRIGGER DARKNESS — `Gamma_SightBeacon`, `Gamma_HeartbeatCore`, `Gamma_Grind_Watchdog`, `Gamma_FleetExecutor`, `Gamma_HealthBeacon` were registered with `MSFT_TaskTimeTrigger` (a one-shot `CalendarTrigger` with no `<ScheduleByDay>` child). They fired once (install day), then their `NextRunTime` went empty and they never fired again. The engine was dark every trading day after install. Diagnostic: `enabled task with EMPTY NextRunTime`. Fixed by re-registering with `MSFT_TaskDailyTrigger`. Guard: `backtest/tests/test_engine_liveness_guards.py::TestTriggerGuard`.

2. BEACON STALENESS / SORT=ASC TRUNCATION — `sight_beacon.py:_fetch_alpaca_bars` was requesting `sort=asc&limit=300`. Alpaca's 5-day 5m window = ~390 bars; the limit kept the OLDEST 300, truncating today's bars off the tail. The beacon froze at the prior session's close (`731.86`, ~$2.80 stale all morning). The engine saw stale price + stale ribbon. Fixed by switching to `sort=desc` then reversing the list. Guard: `TestSightBeaconSortDesc`.

3. OPTIONS BRACKET REJECTION — Alpaca returns error code 42210000 ('complex orders not supported for options') for both bracket AND OTO order classes. `fleet_broker.place_bracket` had no `simple_fallback` path; after two rejections it returned an error dict. Every attempted entry hit `PLACE_FAIL`. Fixed by adding `simple_fallback=True` path (plain limit entry, caller manages exits via `exit_manager`). Guard: `TestSimpleFallbackParam`.

A fourth related issue (engine_health permanently YELLOW) is in the same test file: after the LLM heartbeat was retired, `engine_health.build_report` still called `check_heartbeat` reading `loop-state.json` (never written anymore). Fixed by replacing with `check_engine_core` (reads `core-decisions.jsonl`) and `check_sight_beacon`. Guard: `TestEngineHealthWatchesNewProducers`.

Root mechanism common to all four: the rig has NO CI/CD — guards only run via `Gamma_GuardsNightly` (22:30 ET daily, `pytest -m slow`) and the fast per-edit hook (`pytest -m not slow`). A registration mistake or a source bug is invisible until the engine goes dark at 09:30 the next day. The tests above — already committed in `backtest/tests/test_engine_liveness_guards.py` — close these four gaps. The question is: what's the FULL set of engine-can't-silently-break invariants worth guarding next, and what architecture handles the tension between 'no live Task Scheduler in CI' and 'the real guard is live state'?


**Approaches considered**

- **Snapshot-based static test (current pattern, extend it)** — For scheduler-level invariants: dump `schtasks /query /xml /tn <name>` XML to a committed snapshot file (`engine-task-snapshot.json`) at registration time. Tests parse the snapshot (or live XML if on host) and assert structural properties — `<ScheduleByDay>` present, Repetition interval within bounds, Action chain uses `wscript`→`run_exe_hidden.vbs` not bare `powershell.exe`. For source-level invariants: read the Python/PS1 file as text and assert the correct pattern exists (`sort=desc`, `simple_fallback` in signature, `check_engine_core` in `build_report`). For config drift: parse `params.json` + `heartbeat_core.py:GATE_KEYS` and assert they are a subset of `gates.py`'s known gate names. All purely static: no network, no Windows API, runs in CI on any machine. The existing `test_engine_liveness_guards.py` fully instantiates this pattern for today's 4 bugs.
    - ✅ Runs instantly anywhere (CI, dev box, nightly). Self-documenting: the test IS the invariant spec. The snapshot is itself a regression artifact — diffing it catches unauthorized task re-registrations. Zero cost. Pattern already in place and proven (4 guards committed today). Works for both 'is the file correct' and 'is the registration correct' questions. Snapshot staleness is visible (a test fails if the snapshot is missing an engine task).
    - ⚠️ Snapshot goes stale if tasks are re-registered without updating it (a human step). Catches the SOURCE-LEVEL bug but not 'did the fix actually deploy' — a guard asserting `sort=desc` in sight_beacon.py passes even if the file was never re-run (the running process could be an old cached .pyc or a different file). Does NOT detect runtime failures like a temporarily rate-limited veto lane or a stale circuit-breaker JSON that the engine reads but the guard doesn't touch.

- **Live health-probe scheduled task (runtime assertion engine)** — A dedicated `Gamma_EngineIntegrityProbe` task fires once at 09:31 ET each trading day (after the engine's first tick). It does NOT assert source code — it asserts OBSERVED BEHAVIOR: (a) checks `core-decisions.jsonl` has a row timestamped within the last 3 minutes, confirming the brain ticked; (b) checks `sight-beacon.json` `ok=True` and `age_s < 120`; (c) for a HOLD/SKIP verdict, replays the exact payload from the last `core-decisions.jsonl` row through `engine_cli` and asserts the verdict round-trips; (d) checks `automation/state/engine-task-snapshot.json` is present and covers all 5 engine tasks. On any failure: write to `engine-health.json` + Discord ping immediately rather than waiting for the STALE_MIN budget.
    - ✅ Catches deployment gaps: if the source is correct but the task is still dark (old one-shot, or process reaper killed the first tick before it could write), this fires at 09:31 and catches it while RTH is still open (30 minutes to fix vs. silent all day). Catches runtime failures (lane rotation, stale state files) that source analysis cannot see. Forces the invariant to be verified against ACTUAL OUTPUT, not inferred from source text.
    - ⚠️ One more task to register (adding to the 43 already in flight). It must itself be a daily-recurring task — subject to the exact bug it's guarding against. Circular dependency: if the registration is broken, the probe doesn't fire, the bug goes undetected. The 09:31 window is too early for meaningful round-trip verification on slow ticks (the engine has a 30s `engine_cli` subprocess; the first tick may not be complete). Adds a real-money risk surface: a bug in the probe that incorrectly calls `_execute` or modifies state would be a live incident.

- **Invariant-as-registration assertion (pre-commit hook + install-script guard)** — Every `setup/install-*.ps1` that registers a `Gamma_*` task runs `python backtest/tests/test_engine_liveness_guards.py --task <name>` as a post-registration step. The test: (1) calls `schtasks /query /xml /tn <name>` immediately after `Register-ScheduledTask`, (2) asserts `<ScheduleByDay>` present, (3) updates the snapshot file atomically, (4) runs the full source-level guards. If any assertion fails, the install script exits nonzero and the registration is reverted. This closes the 'snapshot goes stale' gap by making snapshot update mandatory at registration time.
    - ✅ Snapshot can never drift: it is updated at the exact moment of registration, by the same script that registers. Catches the one-shot anti-pattern before the engine ever fires a dark tick. Composable with the snapshot test: the snapshot is the output, the test is the validator. The pre-commit hook already exists (`Gamma_GuardsNightly` / fast hook); extending install scripts is low-cost.
    - ⚠️ Install scripts don't usually run on CI (Windows Task Scheduler not available). The guard runs at install time but not on subsequent days when drift could re-accumulate (someone manually re-registers a task without running the install script). A buggy install script that skips the validation step silently bypasses the guard. Requires all future install scripts to include the post-registration test — discipline failure means a new task skips it.


**Recommended** — Snapshot-based static tests (Approach 1) extended with a small live-probe augmentation for the deployment-gap problem.

Rationale: The snapshot approach is already working — today's 4 guards are committed, pass on the host box, and cover the exact failure modes. Extending it costs nothing and runs anywhere. The live-probe (Approach 2) is genuinely valuable but must be scoped tightly: NOT a new Claude task, NOT touching execution state. The right form is a plain Python health check called from `run-engine-health.ps1` at 09:32 ET that writes one line to `engine-health.json` as an early-open liveness ping. This avoids the circular-registration trap while preserving the 'caught within 30 minutes of open' property.

The install-script guard (Approach 3) is worth adding as a SECONDARY discipline for every new install script going forward but is not a substitute for the static tests (it doesn't run in CI).

Immediate priorities for the full guard set (beyond today's 4 already committed):

**P1 — GATE_KEYS drift (heartbeat_core.py vs gates.py):** `heartbeat_core.GATE_KEYS` (line 103) passes 15 gate names to `engine_cli`. `gates.py` defines the canonical set that `evaluate_gates` actually reads. There are currently 7 GATE_KEYS in `heartbeat_core.py` that are NOT in `params.json` (they silently contribute nothing when params.json doesn't have them — a dead-knob risk per C14/L38). A static test asserting `GATE_KEYS ⊆ gates.GATE_NAMES` (the gates.py tuple at lines 128-142) and `GATE_KEYS ∩ params.json != ∅` for at least the armed gates costs one file read and zero runtime. This is the exact L38/C14 class.

**P2 — VETO-LANE ROSTER integrity:** `heartbeat_core._free_model_eval` hard-codes roles `('coordinator', 'critic')` (line 424). If either role is removed from `model-roster.json` or renamed, `resolve_lanes` raises `KeyError` which is caught by the `except Exception` blanket but logs `no_valid_json` — silently halving veto coverage. A static test: parse `model-roster.json`, assert both 'coordinator' and 'critic' are present in `roles`, and assert each has at least 1 lane with a `provider` and `model`. Zero runtime, zero network.

**P3 — REAPER EXEMPTION completeness:** `_shared.ps1:Stop-StaleClaudeProcesses` (lines 270-290) exempts daemon scripts by substring match. `heartbeat_core.py` is NOT in `$EXEMPT_DAEMONS` (it should be exempt from itself, but since it's launched as a task it's a fresh process each fire and the 5-min stale threshold catches stalled runs — so this is actually correct). The real gap is `sight_beacon.py`: it runs every 1 minute and completes in <5 seconds, so the reaper's 5-min threshold never hits it. But if a beacon run stalls (network hang), the reaper won't kill it because it's under 5 min old when the next heartbeat fires — the next heartbeat fires and starts another beacon, potentially having two concurrent REST fetches. A guard: assert the `sight_beacon.py` subprocess timeout (12s per `urllib.urlopen(timeout=12)`) is < 60s (the task cadence), so a stalled fetch doesn't overlap the next fire.

**P4 — `no_trade_window` coercion consistency:** `heartbeat_core._norm_no_trade_window` converts `[]` → `None` (lines 277-289) to avoid `engine_cli` `BadPayload`. But `params.json#entry_no_trade_window_et` for Safe is `null` (None) while Bold is `[]`. A regression where someone sets Safe to `[]` would silently break Bold's verdict to `SKIP_BAD_INPUT` every tick. Static test: parse both params files, assert `entry_no_trade_window_et` is either `null` or a list with exactly 2 elements.

**P5 — ARMED flag gating:** `heartbeat_core:ARMED = os.environ.get('GAMMA_CORE_ARMED', '0') == '1'` (line 71). The Task Scheduler action for `Gamma_HeartbeatCore` must NOT set `GAMMA_CORE_ARMED=1` in the environment unless J has explicitly armed it. A source guard: parse the task XML from the snapshot, assert no `<EnvironmentVariable>` element sets `GAMMA_CORE_ARMED` to `1`. This prevents accidental live-trade arming via a misconfigured install script.



**Design detail**

**Today's guards (already committed in `backtest/tests/test_engine_liveness_guards.py`):**
- `TestTriggerGuard.test_engine_task_is_daily_recurring` — parametrized over `_ENGINE_TASKS` (5 tasks), calls `_assert_daily_recurring` which parses live XML or snapshot, asserts `<ScheduleByDay>` present in every `<CalendarTrigger>` block.
- `TestSimpleFallbackParam.test_place_bracket_has_simple_fallback_param` — imports `fleet_broker.py`, inspects `inspect.signature(place_bracket)`, asserts `simple_fallback` in params.
- `TestSightBeaconSortDesc.test_sort_desc_in_source` — reads `sight_beacon.py` as text, asserts `sort=desc` present, `sort=asc` absent from non-comment/non-docstring lines.
- `TestEngineHealthWatchesNewProducers.test_build_report_calls_check_engine_core_not_check_heartbeat_log` — extracts `build_report` function source, asserts `check_engine_core` present, `loop-state` absent in non-comment lines.

**Next guards to add (file: `backtest/tests/test_engine_liveness_guards.py`, extend existing `TestTriggerGuard` or add new classes):**

**Guard: GATE_KEYS subset of engine gate names**
```python
# In test_engine_liveness_guards.py
def test_heartbeat_core_gate_keys_are_known_engine_gates():
    import importlib.util, re
    # Extract GATE_KEYS list from heartbeat_core.py source
    src = (_REPO / 'setup/scripts/heartbeat_core.py').read_text(encoding='utf-8')
    func = _extract_function_source(src, 'GATE_KEYS') # won't work — it's a module-level list
    # Better: parse the literal
    m = re.search(r'GATE_KEYS\s*=\s*\[(.*?)\]', src, re.DOTALL)
    assert m, 'GATE_KEYS list not found in heartbeat_core.py'
    keys = set(re.findall(r'"(\w+)"', m.group(1)))
    # Load gates.py to get the canonical gate tuple
    gates_src = (_REPO / 'backtest/lib/engine/gates.py').read_text(encoding='utf-8')
    gate_names = set(re.findall(r'"(block_\w+|require_\w+|midday_\w+|entry_bar_\w+|vix_bear_hard_cap|min_ribbon\w+|max_ribbon\w+|trendline_requires\w*)"', gates_src))
    unknown = keys - gate_names
    assert not unknown, (
        f'heartbeat_core.GATE_KEYS contains names not recognized by gates.py: {sorted(unknown)}. '
        'These are dead knobs (C14) — either remove them from GATE_KEYS or add them to gates.py.'
    )
```

**Guard: veto-lane roster integrity**
```python
def test_veto_lane_roles_present_in_roster():
    roster = json.loads((_REPO / 'automation/state/model-roster.json').read_text('utf-8'))
    roles = roster.get('roles', {})
    for role in ('coordinator', 'critic'):
        assert role in roles, f'Veto role {role!r} missing from model-roster.json. Free-model veto lane is silently absent.'
        lanes = roles[role].get('lanes', [])
        assert lanes, f'Veto role {role!r} has no lanes in model-roster.json.'
        for ln in lanes[:1]:  # at least the first lane is valid
            assert ln.get('provider'), f'Veto role {role!r} first lane has no provider.'
            assert ln.get('model'), f'Veto role {role!r} first lane has no model.'
```

**Guard: no_trade_window coercion precondition**
```python
def test_no_trade_window_is_null_or_two_element_list():
    for label, path in [('safe', _REPO/'automation/state/params.json'),
                        ('bold', _REPO/'automation/state/aggressive/params.json')]:
        p = json.loads(path.read_text('utf-8'))
        v = p.get('entry_no_trade_window_et')
        assert v is None or (isinstance(v, list) and len(v) == 2), (
            f'{label} params.json: entry_no_trade_window_et must be null or a 2-element list '
            f'(got {v!r}). Any other value causes engine_cli BadPayload -> SKIP_BAD_INPUT every tick.'
        )
```

**Guard: GAMMA_CORE_ARMED not set in snapshot task XML**
```python
def test_heartbeat_core_task_not_armed_in_snapshot():
    snap = _load_snapshot()
    xml = snap.get('Gamma_HeartbeatCore', '')
    assert 'GAMMA_CORE_ARMED' not in xml or '=1' not in xml.split('GAMMA_CORE_ARMED')[-1][:5], (
        'Gamma_HeartbeatCore task XML has GAMMA_CORE_ARMED=1 in its environment. '
        'This would arm the engine for live trading without J explicitly flipping the switch. '
        'Remove it from the task registration.'
    )
```

**Snapshot update workflow:** After registering any engine task, run:
```powershell
$tasks = @('Gamma_SightBeacon','Gamma_HeartbeatCore','Gamma_Grind_Watchdog','Gamma_FleetExecutor','Gamma_HealthBeacon')
$snap = @{}
foreach ($t in $tasks) { $snap[$t] = (schtasks /query /xml /tn $t 2>&1) -join "`n" }
$snap | ConvertTo-Json | Out-File automation/state/engine-task-snapshot.json -Encoding utf8
```
This is already documented in `_load_snapshot`'s docstring.


**Edge cases**
  - Snapshot test passes but live task is still dark: if the snapshot was committed after the fix but someone re-registers the task without updating the snapshot, the test uses the (correct) snapshot but the live task is broken. Mitigation: the install script should regenerate the snapshot, and the daily `audit_scheduled_tasks.py` (via `Gamma_CryptoDaily`) catches `SILENT_TASK` (task hasn't fired in cadence×3). These two signals together close the gap.
  - Veto lane cooldown: if both `coordinator` AND `critic` lanes are in 429 cooldown simultaneously (all providers throttled), `effective_lanes` falls through to the floor (local Ollama `qwen3:14b`). The guard only checks roster presence — it cannot detect a runtime 429 storm. The ledger row's `free_eval.votes` field records `error: KeyError` or `no_valid_json` per-lane, so the human can audit it after-hours. Adding a ledger-scan guard (count `no_valid_json` vote rows in last N ticks) is a Phase 2 enhancement.
  - GATE_KEYS containing a key that IS in params.json but NOT in gates.py: the current guard catches this (unknown key in GATE_KEYS). But the inverse — gates.py reads a gate that is NOT in GATE_KEYS and IS in params.json — means params.json has a live gate that heartbeat_core silently never passes to engine_cli. This is the more dangerous direction. The guard should also assert: for every key in `params.json` that matches the `block_*/require_*` pattern AND is in `gates.py`'s known set, it appears in `GATE_KEYS`. Currently 7 GATE_KEYS are in heartbeat_core.py but NOT in params.json (they pass nothing, dead), and some gates.py gate names exist in params.json but not in GATE_KEYS (e.g., `block_bull_morning_agg` IS in params.json for some configs — verify this is intentional).
  - Sight beacon 'frozen' despite sort=desc: the fix works as long as `limit=300` covers the current trading week. If the Alpaca IEX feed is throttled and returns fewer than 300 bars (or returns an empty page), `_fetch_alpaca_bars` falls through to yfinance. The guard only checks the URL parameter, not the fallback path. A secondary guard: in `build()`, assert `n_bars >= 80` before calling `compute_ribbon` — already done (`if len(closes) < 25: return {ok: False}`). The 25-bar floor is actually too low for reliable ribbon EMAs (needs ~48 bars); the beacon marks `ok=True` with 26 bars and writes a potentially unreliable ribbon.
  - entry_no_trade_window_et two-element list but wrong type: `['09:30', '10:30']` is correct; `[930, 1030]` (integers) would pass the guard but fail in `engine_cli._coerce_score_kwargs` at runtime. A tighter guard: also assert both elements are strings matching `HH:MM` pattern.

**Failure modes**
  - Test suite not run between install and next market open: `Gamma_GuardsNightly` fires at 22:30 ET, but a task registered at 23:00 won't be tested until the FOLLOWING night. A one-shot task registered at 23:00 fires once the next morning at 09:30 and goes dark. The guard only catches this at 22:30 the NEXT night — 36 hours of silent darkness. Mitigation: the install script itself should run the relevant parametrized test immediately after registration (Approach 3 hybrid).
  - model-roster.json written with a role renamed: if `critic` is renamed to `analyst` in the roster (plausible — the commented ROLE_ALIAS in `gamma_manager.py` mentions this mapping), the veto guard passes (roster is valid) but `heartbeat_core._free_model_eval` raises `KeyError('critic')` on every tick, caught by the blanket exception, logged as `error: KeyError: 'critic'`, and veto silently degrades to single-lane. The fix is in heartbeat_core.py: `resolve_lanes('critic')` should raise explicitly so it's not swallowed.
  - params.json entry_no_trade_window_et set to `['09:30']` (1 element): passes `isinstance(v, list)` but fails `len(v) == 2`. The guard catches this. But if the value is accidentally set to `True` (a boolean from a botched edit), `isinstance(True, list)` is False (booleans are not lists in Python), so it also fails the guard correctly.
  - Snapshot references a task that no longer exists on the host: `_assert_daily_recurring` calls `_get_task_xml` which tries live schtasks first, falls back to snapshot. If the task was unregistered, live returns None, snapshot returns the old XML, and the guard PASSES — but the task isn't running. This is a false negative. The daily `audit_scheduled_tasks.py:STALE_REGISTRY_ENTRY` check catches this (registered in doc, not in live schtasks), but it's a different signal. The snapshot guard should NOT be the only defense for 'is the task alive'.
  - RTH window starts before engine_health checks first tick: `engine_health.build_report` gives `CORE_STALE_MIN=8` minutes before flagging RED. A task dark due to one-shot trigger goes dark at 09:30; the health check doesn't RED until 09:38. Losing the first 8 minutes of RTH is unfortunate but acceptable given the 280s tick-timeout constraint. The 09:32 live-probe augmentation (described in recommended) would catch this at 09:32 instead of 09:38.


**Validation plan** — For P1 (GATE_KEYS drift), P2 (veto-lane roster), P4 (no_trade_window): pure static tests, no real-fills needed. The guard fails deterministically when the invariant is violated (e.g., rename `critic` in the roster, the test fails). These are not P&L claims — they are structural contracts.

For the today's 4 guards (already committed): they were validated by confirming the `_BROKEN_ONE_SHOT_XML` fixture fails the trigger check, the `place_bracket_OLD` fixture fails the signature check, a `sort=asc` snippet fails the source check, and the integration test with `tmp_path` monkeypatching `engine_health.STATE` shows `heartbeat_safe: GREEN` with a fresh `core-decisions.jsonl` row.

For any NEW guard that touches P&L claims (e.g., asserting the engine made correct entries on a given day): use `backtest/lib/replay_heartbeat_core.py` with `use_real_fills=True` and assert the `j_edge_capture` metric meets the ≥50% floor (OP-16/C1). The existing `analysis/backtests/REGISTRY.jsonl` tracks these. No new real-fills run is needed for the structural guards proposed here.


**Guard** — The specific pytest for each guard that FAILS on regression:

**Guard 1 (already committed) — one-shot trigger:**
```python
@pytest.mark.parametrize("task_name", _ENGINE_TASKS)
def test_engine_task_is_daily_recurring(self, task_name):
    _assert_daily_recurring(task_name)  # FAILS if <ScheduleByDay> absent
```
Regression: re-register `Gamma_SightBeacon` without `-Daily` flag AND update snapshot → test fails.

**Guard 2 (already committed) — sort=desc:**
```python
def test_sort_asc_not_present_in_fetch_url(self):
    # FAILS if executable URL lines contain sort=asc
```
Regression: change `sort=desc` back to `sort=asc` in `sight_beacon.py` → test fails.

**Guard 3 (already committed) — simple_fallback:**
```python
def test_place_bracket_has_simple_fallback_param(self):
    assert 'simple_fallback' in sig.parameters  # FAILS if removed
```

**Guard 4 (already committed) — engine_health watches new producers:**
```python
def test_build_report_calls_check_engine_core_not_check_heartbeat_log(self):
    assert 'check_engine_core' in func_src  # FAILS if removed
```

**Guard P1 (new) — GATE_KEYS subset:**
```python
def test_heartbeat_core_gate_keys_are_known_engine_gates():
    # FAILS if a key in GATE_KEYS is not in gates.py's gate name set
    # Regression: add 'block_foo_unknown' to GATE_KEYS → test fails immediately
```

**Guard P2 (new) — veto-lane roster:**
```python
def test_veto_lane_roles_present_in_roster():
    # FAILS if 'coordinator' or 'critic' absent from model-roster.json
    # Regression: rename 'critic' to 'analyst' in roster → test fails
```

**Guard P3 (new) — no_trade_window type:**
```python
def test_no_trade_window_is_null_or_two_element_list():
    # FAILS if entry_no_trade_window_et is [] or [x] or any non-null non-2-list
    # Regression: set Bold's entry_no_trade_window_et to [] → test fails
```

**Guard P4 (new) — GAMMA_CORE_ARMED not in snapshot:**
```python
def test_heartbeat_core_task_not_armed_in_snapshot():
    # FAILS if the task XML has GAMMA_CORE_ARMED=1
    # Regression: add env var to install script → snapshot update → test fails
```

All run in `backtest/tests/test_engine_liveness_guards.py`. Fast tests (`not slow`): all of the above complete in <1s each. No network, no live API, no scheduled task calls (except the parametrized trigger test which tries live schtasks and falls back to snapshot). Total test time: <5s for all 8 guards.

Run command:
```
backtest\.venv\Scripts\python.exe -m pytest backtest/tests/test_engine_liveness_guards.py -v
```


**Risks**
  - Snapshot drift is the #1 risk: if the snapshot is not regenerated after a legitimate task re-registration, the guard tests against the old (correct) XML while the live task has the new (possibly broken) XML. The mitigation is the `audit_scheduled_tasks.py` daily check for SILENT_TASK, but there is a 24-hour window of undetected drift.
  - False confidence: a guard passing means the SOURCE and SNAPSHOT are correct, NOT that the running process is behaving correctly. The `sight_beacon.py` could have `sort=desc` in source but be running from a cached .pyc built from an old version. This is nearly impossible given Python recompiles on mtime change, but worth noting.
  - P2 guard catches missing roster role but not a role with 0 functional lanes (all lanes erroring at runtime). The guard checks `len(lanes) > 0` but not that the lanes are reachable. A lane pointing to a deprecated model (e.g., cerebras decommissioning `zai-glm-4.7`) fails silently at runtime. Adding a monthly `swarm_client.smoke_test_lane(role)` call to `Gamma_McpDailyAudit` would close this, but that requires a live network call.
  - The `entry_no_trade_window_et` guard (P3) only checks params.json, not heartbeat_core's actual runtime coercion. If `_norm_no_trade_window` is updated to handle a different invalid form, the guard must be updated in sync — a second-order drift source.
  - Adding too many guards increases the probability that a broken test (e.g., a path assumption) causes the nightly suite to fail for the wrong reason, creating cry-wolf fatigue. All guards should have clear failure messages naming the exact regression class.

**Dependencies**
  - backtest/tests/test_engine_liveness_guards.py (already committed — 4 guards, extend for P1-P4)
  - automation/state/engine-task-snapshot.json (snapshot for trigger guards)
  - automation/state/model-roster.json (for P2 veto-lane guard)
  - automation/state/params.json + automation/state/aggressive/params.json (for P3 no_trade_window guard)
  - setup/scripts/heartbeat_core.py (GATE_KEYS list, ARMED flag)
  - backtest/lib/engine/gates.py (canonical gate name set for P1)
  - automation/state/fleet/fleet_broker.py (simple_fallback guard)
  - setup/scripts/sight_beacon.py (sort=desc guard)
  - setup/scripts/engine_health.py (check_engine_core / check_sight_beacon guard)

**Open questions**
  - Should `Gamma_HeartbeatCore` be added to the reaper's EXEMPT_DAEMONS list? Currently it is NOT exempt, which means if a tick hangs past 5 minutes it will be reaped on the next heartbeat fire. This is actually CORRECT behavior for a 2-minute-cadence process — you WANT a stalled tick to be killed. But it means the reaper is doing double duty as a timeout enforcer. If the `engine_cli` subprocess timeout (30s) fires but the process doesn't die cleanly, the reaper is the safety net. Is this intentional? Document in EXEMPT_DAEMONS comment.
  - The `sort=desc` beacon guard catches the URL parameter, but does the guard need to also check `_fetch_yfinance_bars`? yfinance returns bars in ascending order natively (no sort param) — so the reversal in the Alpaca path does NOT apply there. If yfinance is the fallback and its bars are correctly ordered, the guard is complete. But if someone adds a sort parameter to the yfinance download call, the guard needs extension.
  - P2 flag: `heartbeat_core._free_model_eval` uses roles `('coordinator', 'critic')` hardcoded (line 424). The veto-lane roster guard checks these two names. But `swarm_client.py:resolve_lanes` raises `KeyError` for unknown roles — this is NOT caught gracefully; the blanket `except Exception` in `_free_model_eval` catches it and logs `KeyError: 'critic'`. Should the veto lane selection be driven by a config value in params.json rather than hardcoded strings? That would make it guardiable without source inspection and would allow J to change veto lanes without touching code.
  - The `Gamma_GuardsNightly` task runs the `slow` marker tests at 22:30 ET. The new guards in `test_engine_liveness_guards.py` are fast (not marked `slow`). They run via the per-edit fast hook. Is there a risk that the fast hook skips them in certain conditions (e.g., editing a non-Python file)? The hook should be audited to confirm it triggers on params.json edits too (the P3 guard depends on params.json content).
  - HOLD evaluation: P5 (ARMED flag guard) — is it worth guardiing the snapshot for GAMMA_CORE_ARMED? The snapshot is only regenerated manually or by the install script. If someone arms the engine by setting the env var at the OS level (not via the task XML), the snapshot guard would not catch it. The real guard for accidental live arming is the `_execute` dry-run path: when `dry=True`, plan status is `WOULD_PLACE`, not `PLACING`. Checking the ledger for unexpected `PLACING` rows during what should be WATCH mode is a stronger guard. HOLD on P5 until there is a concrete regression scenario.


**Verdict** — SHIP-worthy for the 4 guards committed today (`test_engine_liveness_guards.py`). They are already in `backtest/tests/`, well-structured, and cover the exact failure mechanisms witnessed in production. The snapshot approach is the right architecture for this rig's constraints (no CI with Task Scheduler access).

The 4 additional guards (P1-P4) are all SHIP-worthy: they are short, deterministic, fast, and protect against documented failure classes (C14/L38 for P1, silent veto degradation for P2, `BadPayload` every tick for P3, accidental live arming for P4). None require real-fills, backtest runs, or live API calls. P5 is HOLD — the existing `WOULD_PLACE` ledger path is a stronger runtime check for accidental arming than a snapshot XML assertion.

The live-probe augmentation (Approach 2) is needs-more: the 09:32 early-open ping is genuinely valuable but should be implemented as a Python function called from `run-engine-health.ps1` (not a new Claude task), and its scope must be strictly read-only — no order verification, no state modification.

---

## CMD popup elimination for Gamma_Funnel_0..5 + Gamma_Grind_all + permanent audit guard

**Problem & root cause** — **What we witnessed:** Every time Task Scheduler fires Gamma_Funnel_0..5 or Gamma_Grind_all, a black OpenConsole.exe window flashes on screen. Confirmed by live audit: `automation/state/scheduled-tasks-audit.json` (10:00 2026-06-26) shows 7 `VISIBLE_WINDOW` flags for exactly these tasks with `execute='cmd.exe'`. The tasks use bare `cmd.exe /c "set ENV=VAL&& python.exe -m module > log 2>&1"` as the task action.

**Mechanism (root-caused 2026-06-20, encoded as L41 in CLAUDE.md):** On Windows 11, any Task Scheduler action whose Execute is a console-subsystem binary (`cmd.exe`, `powershell.exe`, `python.exe`) causes Windows to allocate a new console session via OpenConsole.exe with the `-Embedding` flag BEFORE the process even starts executing. `-WindowStyle Hidden` is a PowerShell runtime flag that only takes effect ~200ms AFTER that console is already visible. `cmd.exe` has no equivalent. There is no Task Scheduler setting that suppresses this: the "Run whether user is logged on or not" option hides everything, but these tasks run as the logged-in user. The only guaranteed fix is to make the task's Execute a GUI-subsystem binary that never requests a console.

**Scope of affected tasks** (from live `Get-ScheduledTask` output): Gamma_Funnel_0, Gamma_Funnel_1, Gamma_Funnel_2, Gamma_Funnel_3, Gamma_Funnel_4, Gamma_Funnel_5 — all use `cmd.exe /c "set GAMMA_FUNNEL_SHARD={n}&& set GAMMA_FUNNEL_NSHARDS=6&& ...\python.exe -m autoresearch.mass_grind_funnel > ...log 2>&1"`. Gamma_Grind_all uses `cmd.exe /c "set GAMMA_GRIND_WORKERS=8&& ...\python.exe -m autoresearch.mass_grind > ...log 2>&1"`. Gamma_Grind_Watchdog was ALREADY converted (live task now shows wscript.exe chain; the 10:00 audit.json entry is stale from before the conversion today).

**Why Gamma_Grind_Vwap is already clean:** `setup/install-grind-vwap.ps1` uses the canonical `wscript -> run_exe_hidden.vbs -> pythonw -> run_ps1_hidden.py -> run-grind-vwap.ps1` chain. That is the template for what Funnel_0..5 and Grind_all need.

**No install script exists for Funnel_0..5 or Grind_all.** They are not in any `setup/install-*.ps1`. They must have been registered manually or by an early task-setup sweep. This means re-registering them requires writing a new install script OR a targeted re-registration block.


**Approaches considered**

- **Approach A — wscript -> run_exe_hidden.vbs -> backtest-pythonw -> run_cmd_hidden.py (the WS6 pattern, already implemented in code/tests)** — Task Scheduler Execute = wscript.exe, Arguments = `//nologo "<run_exe_hidden.vbs>" "<backtest-pythonw>" "<run_cmd_hidden.py>" --env KEY=VAL [--env ...] --log <logfile> --cwd <workdir> -- "<backtest-pythonw>" -m <module>`. Chain: wscript (GUI-subsystem, no console) -> run_exe_hidden.vbs calls WScript.Shell.Run with windowStyle=0 on pythonw (GUI-subsystem, no console) -> run_cmd_hidden.py (already written: `setup/scripts/run_cmd_hidden.py`) calls subprocess.run(..., creationflags=CREATE_NO_WINDOW) on the grind python.exe. The child python.exe inherits CREATE_NO_WINDOW and Windows is contractually obligated NOT to allocate a console.

For env vars: `--env GAMMA_FUNNEL_SHARD=0 --env GAMMA_FUNNEL_NSHARDS=6`. For log redirect: `--log <path>`. For working directory: `--cwd C:\Users\jackw\Desktop\42\backtest`.

The child command uses `pythonw.exe` (GUI-subsystem) NOT `python.exe` because: (a) we pass it through the CREATE_NO_WINDOW subprocess.run which already suppresses the console, but (b) if something goes wrong and CREATE_NO_WINDOW is dropped, a pythonw child still won't allocate a console — it is a defence-in-depth layer. The `run_cmd_hidden.py` module is already tested in `backtest/tests/test_guard_cmd_popup_fix_ws6.py` with the exact argument shapes for Funnel_0..5 and Grind_all.

Note: wscript's `shell.Run` uses ShellExecute, NOT CreateProcess. On most Win11 configs this works. The `run_hidden_exec.vbs` variant uses WshShell.Exec (CreateProcess path) which is more reliable but synchronous (blocks wscript until child exits). For the grind tasks which can run for HOURS, async (shell.Run, False wait) is correct — Task Scheduler starts the wscript, wscript fires pythonw and exits immediately, pythonw runs run_cmd_hidden.py which blocks on the grind. Task Scheduler only tracks the wscript lifetime, not the grind — this is fine for on-demand tasks (Funnel and Grind_all are fired by the watchdog via Start-ScheduledTask).
    - ✅ 1. run_cmd_hidden.py already exists and is fully implemented (setup/scripts/run_cmd_hidden.py, 139 lines, handles --env, --log, --cwd, CREATE_NO_WINDOW). 2. The audit recognises this pattern: _is_hidden() returns True for wscript+run_exe_hidden.vbs (lines 99-103 of audit_scheduled_tasks.py). 3. The regression tests are already written in backtest/tests/test_guard_cmd_popup_fix_ws6.py — 17 test cases covering pre-fix, post-fix, and edge cases. 4. Env vars pass cleanly (--env KEY=VAL repeatable). 5. Log redirect is handled (--log captures both stdout+stderr via subprocess). 6. wscript exits immediately (async) so Task Scheduler doesn't hold the task as 'Running' while the grind is in-flight — the grind runs independently as a pythonw child. 7. backtest/.venv/Scripts/pythonw.exe already exists (verified True). 8. The grind reaper exemption in _shared.ps1 exempts 'backtest\.venv' processes — the pythonw.exe child will be exempt.
    - ⚠️ 1. wscript Shell.Run uses ShellExecute, which on some Win11 configs with non-default terminal settings can still route through WT — this was the original concern. However: our CryptoGrinderKeepalive already uses this same chain (converted in June) and has not reported flashes. The run_hidden_exec.vbs (WshShell.Exec/CreateProcess path) would be more robust but blocks wscript until exit — unsuitable for multi-hour grinds. 2. Task Scheduler does NOT track grind health via task State — it fires the wscript and marks it done immediately. The grind-shard-watchdog (Gamma_Grind_Watchdog) handles liveness monitoring independently by inspecting progress files + restarting Gamma_Grind_all via Start-ScheduledTask. This pre-existing design is correct — WS6 does not break it. 3. Logging: with --log set, stdout+stderr go to the log file. Without it, they are captured and discarded (run_cmd_hidden.py logs only the launcher events, not the child's output). Must pass --log to preserve mass-grind-stdout.log and mass-grind-funnel-N-stdout.log. 4. No install script currently exists for these 7 tasks — need to write install-grind-funnel-tasks.ps1.

- **Approach B — pythonw.exe wrapper shim (thin Python file that sets env vars and execs the module)** — Create a thin per-task Python shim, e.g. `backtest/autoresearch/_shim_funnel_0.py` that does `os.environ['GAMMA_FUNNEL_SHARD'] = '0'; os.environ['GAMMA_FUNNEL_NSHARDS'] = '6'; from autoresearch import mass_grind_funnel; mass_grind_funnel.main()`. Register the task with Execute = `backtest\.venv\Scripts\pythonw.exe` and Arguments = `"C:\...\backtest\autoresearch\_shim_funnel_0.py"`. Since pythonw.exe is GUI-subsystem, no console is ever allocated. No wscript layer needed.
    - ✅ 1. Maximum simplicity in the task XML — just pythonw.exe + a path. No VBS, no run_cmd_hidden.py, no wscript layer. 2. _is_hidden() already accepts direct pythonw.exe execute (line 101-102 of audit_scheduled_tasks.py) — zero audit changes needed. 3. Provably zero-leak: pythonw.exe never allocates a console under any Windows 11 config. 4. No new infrastructure — pythonw, subprocess, venv are all pre-existing.
    - ⚠️ 1. 7 shim files (1 per Funnel shard + Grind_all) — each just sets 2 env vars and calls main(). Minor maintenance surface but more files than approach A. 2. The shim approach buries the env-var wiring in Python code, making the task registration less readable (Arguments just shows a .py file path, not the env vars). 3. stdout/stderr from the grind module go to... nowhere by default (pythonw.exe has no console, so print() output is discarded unless the module explicitly opens a log file). mass_grind_funnel uses print() and the old cmd.exe task redirected > log 2>&1. A shim would need to redirect sys.stdout/sys.stderr to log files at the top of the shim — adding ~5 lines per shim. 4. If mass_grind_funnel.main() doesn't exist (it uses if __name__ == '__main__'), the shim needs to import and call the internal entry-point, which may drift if the module interface changes. Fragile coupling. 5. No existing test infrastructure tests this pattern for these specific modules — test_guard_cmd_popup_fix_ws6.py does NOT cover Approach B. New tests would be needed. 6. Shim proliferation: every new grind task = new shim file. Approach A (run_cmd_hidden.py) is a universal launcher.


**Recommended** — Approach A — wscript -> run_exe_hidden.vbs -> backtest-pythonw -> run_cmd_hidden.py.

Rationale: run_cmd_hidden.py is already written, the regression tests already exist (`backtest/tests/test_guard_cmd_popup_fix_ws6.py`, 17 test cases covering the exact before/after argument shapes for all 7 tasks), and the audit already recognises the pattern. The only missing piece is a re-registration script (install-grind-funnel-tasks.ps1) and updating SCHEDULED-TASKS.md to list all 7 tasks so ORPHAN_TASK flags clear. Approach B would work but requires new shim files, lacks existing test coverage, and loses stdout/stderr logging without extra work.


**Design detail**

**Files that change:**

1. **`setup/scripts/run_cmd_hidden.py`** — already complete (lines 1-138). No changes needed. Handles `--env KEY=VAL`, `--log`, `--cwd`, `--` separator, CREATE_NO_WINDOW subprocess.run, logs to `automation/state/logs/run-cmd-hidden-YYYY-MM-DD.log`.

2. **`setup/install-grind-funnel-tasks.ps1`** (NEW) — registers all 7 tasks using the canonical chain. Key arguments per task:

Funnel_0..5:
```
Execute:   wscript.exe
Arguments: //nologo "<run_exe_hidden.vbs>" "<backtest-pythonw>" "<run_cmd_hidden.py>"
           --env GAMMA_FUNNEL_SHARD={n} --env GAMMA_FUNNEL_NSHARDS=6
           --log "<reco>\mass-grind-funnel-{n}-stdout.log"
           --cwd "<backtest>"
           -- "<backtest-pythonw>" -m autoresearch.mass_grind_funnel
```
Note: child binary is `pythonw.exe` (not python.exe) for defence-in-depth.

Grind_all:
```
Execute:   wscript.exe  
Arguments: //nologo "<run_exe_hidden.vbs>" "<backtest-pythonw>" "<run_cmd_hidden.py>"
           --env GAMMA_GRIND_WORKERS=8
           --log "<reco>\mass-grind-stdout.log"
           --cwd "<backtest>"
           -- "<backtest-pythonw>" -m autoresearch.mass_grind
```

Settings: `ExecutionTimeLimit = New-TimeSpan -Hours 8`, `StartWhenAvailable`, `AllowStartIfOnBatteries`. Trigger: NONE (on-demand). Both existing task registrations are unregistered first (idempotent).

3. **`automation/state/SCHEDULED-TASKS.md`** — add Gamma_Funnel_0..5, Gamma_Grind_all, Gamma_Grind_Watchdog, Gamma_Grind_Vwap to the Active table. Currently none of these are listed (they show as ORPHAN_TASK in the audit).

4. **`backtest/tests/test_guard_cmd_popup_fix_ws6.py`** — already written (file exists, 229 lines). The `TestPostFixApprovedPattern` class tests the exact argument shapes for the fixed tasks. Run with: `backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_guard_cmd_popup_fix_ws6.py -v`.

5. **`setup/scripts/audit_scheduled_tasks.py`** — the `_is_bare_console_launcher` function (lines 109-125) and its HARD FAIL path (lines 184-190) are already in place. The guard test in `backtest/tests/test_guard_cmd_popup_fix_ws6.py::TestBareLauncherDetection` covers this. No changes needed.

**Argument quoting in wscript args:** wscript.exe passes each quoted token as a separate `WScript.Arguments` item to run_exe_hidden.vbs. The VBS reassembles them with surrounding quotes (line 7-9: `cmd = """" & args(0) & """"`). This means multi-word arguments with spaces must be passed as single quoted tokens. run_cmd_hidden.py receives its argv via `sys.argv` normally. The `--` separator is parsed explicitly (lines 72-79 of run_cmd_hidden.py). All paths with spaces must be passed as separate quoted tokens at the wscript.exe level.

**Worker count:** `GAMMA_GRIND_WORKERS=8` for mass_grind, `GAMMA_FUNNEL_NSHARDS=6` with per-task `GAMMA_FUNNEL_SHARD=0..5` for funnels. These match the existing cmd.exe invocations exactly.

**Log files:** --log paths match the existing log destinations: `mass-grind-funnel-{n}-stdout.log` and `mass-grind-stdout.log` in `analysis/recommendations/`. The grind-shard-watchdog monitors `mass-grind-progress*.jsonl` (not stdout logs) so log path changes don't affect watchdog logic.


**Edge cases**
  - wscript Shell.Run async behaviour: wscript fires pythonw and exits immediately (windowStyle=0, False = don't wait). Task Scheduler marks the task as 'Ready' within seconds, not 'Running' for hours. Gamma_Grind_Watchdog (grind-shard-watchdog.ps1) checks State == 'Running' via Get-ScheduledTask — it will ALWAYS see 'Ready' for Grind_all after the fix and will try to restart it on every 60-second tick. CRITICAL: The watchdog must switch from checking task State to checking for a live grind process directly (as grind-watchdog.ps1 already does via WMI). grind-shard-watchdog.ps1 line 22-26 currently uses 'Start-ScheduledTask -TaskName Gamma_Grind_all' when state != 'Running' — after the fix, state will never be 'Running', causing infinite restarts. This must be fixed before deployment.
  - Backtest venv pythonw.exe vs system pythonw.exe: run_cmd_hidden.py must be launched by a pythonw.exe that can import no grind modules (it just calls subprocess.run). Either system pythonw (C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe) or backtest pythonw work. HOWEVER, the child command (after --) that actually runs mass_grind_funnel MUST use backtest\venv\Scripts\pythonw.exe since autoresearch.* lives there. The install script and test fixtures already use backtest-pythonw for both the launcher and the child, which is correct.
  - Reaper exemption: _shared.ps1 EXEMPT_DAEMONS exempts 'backtest\.venv' python processes from Stop-StaleClaudeProcesses. The child pythonw.exe process spawned by run_cmd_hidden.py will have executable path matching backtest\.venv\Scripts\pythonw.exe. If the reaper matches on python/pythonw path, it must match pythonw.exe too. Verify the exemption pattern covers both python.exe and pythonw.exe in the backtest venv path.
  - Log file append vs overwrite: run_cmd_hidden.py opens --log in append mode (log_path.open('a')). The old cmd.exe tasks used > (overwrite). If the grind is restarted mid-run by the watchdog, the new run appends to the existing log — this is BETTER (preserves restart history) but note the log grows unbounded across multiple grinds. Not a blocker but a maintenance note.
  - ORPHAN_TASK flags in the audit will clear only after SCHEDULED-TASKS.md is updated to list these 7 tasks. Currently 7 of the 24 audit flags are ORPHAN_TASK for these tasks. The remaining ORPHAN_TASK flags (Gamma_ContenderRank, Gamma_EodFullAudit, Gamma_FreeManager, Gamma_HeartbeatCore, Gamma_LiveShadowValidator, Gamma_ManagerOverseer, Gamma_SightBeacon) are a SEPARATE issue — don't bundle them into this fix.
  - wscript argument quoting: run_exe_hidden.vbs wraps each WScript.Arguments item in double-quotes (line 7-9). Paths with spaces need to be passed as individual arguments without embedded quotes — wscript.exe tokenises Arguments string by spaces, respecting double-quoted groups. The install script must build the -Argument string carefully to avoid double-quoting issues.

**Failure modes**
  - Watchdog infinite-restart loop (CRITICAL): grind-shard-watchdog.ps1 checks `(Get-ScheduledTask -TaskName 'Gamma_Grind_all').State -ne 'Running'` and calls Start-ScheduledTask if true. After WS6 fix, wscript exits immediately so state is always 'Ready'. The watchdog will fire Gamma_Grind_all on every 60-second tick, launching duplicate mass_grind processes. DEADLOCK: multiple mass_grind processes on the OPRA cache (per CLAUDE.md grind-reaper-killer lesson). FIX: change grind-shard-watchdog.ps1 to use WMI process detection (as the OLD grind-watchdog.ps1 does at lines 32-38) rather than task state. Check for a live pythonw.exe with CommandLine matching mass_grind.
  - run_cmd_hidden.py launched by system pythonw but child fails with ModuleNotFoundError: if the child command accidentally uses system python.exe instead of backtest-venv python.exe, autoresearch.* won't be importable. The failure is silent (run_cmd_hidden.py logs the exit code to its launcher log but the task Scheduler won't surface it). The grind watchdog catches it indirectly (no progress entries written, watchdog restarts). But N restarts = N silent failures. Fix: the install script must hardcode backtest-venv paths for both the launcher (outer) and the child (after --).
  - stdout/stderr loss if --log not specified: without --log, run_cmd_hidden.py calls subprocess.run(..., capture_output=True) — output is captured into proc.stdout/proc.stderr but DISCARDED (only exit code is logged). The grind modules' stdout (progress lines, warnings, errors) will be invisible. Fix: always pass --log in the install script. Verify the log path parent directory exists at install time.
  - wscript argument string overflow: wscript.exe Arguments is a single string. Very long paths can exceed shell argument limits. The full argument string for a funnel task is approximately 350 characters, well within limits (Windows limit is ~32767 chars). Not a practical risk here.
  - Existing tasks not unregistered before re-registration: if the install script doesn't Unregister first, Register-ScheduledTask will fail with 'task already exists'. The install script must Unregister-ScheduledTask first (idempotent pattern). If a task is Running at unregister time, it is killed. For on-demand tasks fired only by the watchdog, this is acceptable — the grind resumes from progress files.


**Validation plan** — **No P&L claim is being made here** (this is a window-flash fix, not a strategy change). The validation is mechanical correctness:

1. **Pre-fix audit confirms the problem:** Run `backtest/.venv/Scripts/python.exe setup/scripts/audit_scheduled_tasks.py` — expect BARE_CMD_POWERSHELL (or VISIBLE_WINDOW) flags for Gamma_Funnel_0..5 and Gamma_Grind_all.

2. **Run regression tests (already written):** `backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_guard_cmd_popup_fix_ws6.py -v`. Must all pass (17 tests). These cover: old cmd.exe shapes are flagged, new wscript shapes are recognised as hidden, _is_bare_console_launcher catches cmd.exe and full-path variants, existing approved patterns not broken.

3. **Re-register tasks:** Run `setup/install-grind-funnel-tasks.ps1` (after fixing grind-shard-watchdog.ps1's watchdog logic). Verify with `Get-ScheduledTask -TaskName 'Gamma_Funnel_*','Gamma_Grind_all' | Select TaskName,State`.

4. **Post-fix audit confirms no window flags:** Re-run `audit_scheduled_tasks.py`. Expect: no BARE_CMD_POWERSHELL, no VISIBLE_WINDOW for the 7 tasks. ORPHAN_TASK clears after SCHEDULED-TASKS.md update.

5. **Live smoke-test on demand:** `Start-ScheduledTask -TaskName Gamma_Funnel_0`. Watch for OpenConsole.exe in Task Manager for 5 seconds (should not appear). Check `analysis/recommendations/mass-grind-funnel-0-stdout.log` for grind output within 30 seconds.

6. **Watchdog does not loop:** Fire `Start-ScheduledTask -TaskName Gamma_Grind_Watchdog` once. Check `analysis/recommendations/mass-grind-watchdog.log` — should see `OK N/3360` or one RESTART line, not repeated RESTART lines every 60 seconds.


**Guard** — **Specific pytest that FAILS on regression — already written:**

File: `backtest/tests/test_guard_cmd_popup_fix_ws6.py`

The guard that matters most:
```python
# In class TestPreFixTasksAreFlashers:
@pytest.mark.parametrize("shard", range(6))
def test_funnel_shard_is_bare_cmd(self, shard: int) -> None:
    assert _is_bare_console_launcher("cmd.exe")  # FAILS if _is_bare_console_launcher is removed/broken

@pytest.mark.parametrize("shard", range(6))
def test_funnel_shard_args_not_hidden(self, shard: int) -> None:
    args = self._FUNNEL_ARGS_TEMPLATE.format(shard=shard)
    assert not _is_hidden(execute="cmd.exe", arguments=args)  # FAILS if cmd.exe is whitelisted

# In class TestPostFixApprovedPattern:
@pytest.mark.parametrize("shard", range(6))
def test_funnel_shard_fixed_is_hidden(self, shard: int) -> None:
    assert _is_hidden(execute="wscript.exe", arguments=self._funnel_args(shard))  # FAILS if wscript pattern dropped

def test_grind_all_fixed_is_hidden(self) -> None:
    assert _is_hidden(execute="wscript.exe", arguments=self._grind_all_args())  # FAILS if wscript pattern dropped
```

Additionally, `audit_scheduled_tasks.py` exits 1 if BARE_CMD_POWERSHELL flags exist — the daily audit (Gamma_CryptoDaily) surfaces this as RED in STATUS.md within 24 hours of regression. This is the HARD FAIL in production: any re-registration of Funnel/Grind_all as bare cmd.exe tasks will appear RED in STATUS.md the next day.

Run guard with: `backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_guard_cmd_popup_fix_ws6.py -v --tb=short`


**Risks**
  - Watchdog liveness race: after re-registering Gamma_Grind_all, if grind-shard-watchdog.ps1 fires before the fix to use WMI instead of task State, it will endlessly restart the grind. This is the #1 deployment risk. FIX FIRST: patch grind-shard-watchdog.ps1 to use WMI-based liveness before re-registering the task.
  - Pre-existing install gap: there is no install-grind-funnel-tasks.ps1. If this is lost or not committed, a future task re-registration (e.g. someone runs setup-all.ps1) will not re-apply the WS6 fix. The audit HARD FAIL is the backstop, but there is no positive-install path. Commit install-grind-funnel-tasks.ps1.
  - run_cmd_hidden.py is not tested end-to-end against the actual backtest modules: the tests in test_guard_cmd_popup_fix_ws6.py test argument shapes recognised by the audit, not that run_cmd_hidden.py actually spawns the grind successfully. A quick `Start-ScheduledTask Gamma_Funnel_0` smoke test is essential before declaring success.
  - SCHEDULED-TASKS.md has 24 audit flags (10:00 snapshot), 7 of which are these grind/funnel tasks. The remaining 17 flags (ORPHAN_TASK for newer tasks, SILENT_TASK for GitHubAudit) are pre-existing and separate. Don't conflate — fixing only the 7 window tasks is in-scope for WS6; the ORPHAN_TASK cleanup for HeartbeatCore/SightBeacon etc. is a separate OP.

**Dependencies**
  - setup/scripts/run_cmd_hidden.py — exists, complete
  - setup/scripts/run_exe_hidden.vbs — exists (wscript.exe //nologo + Shell.Run windowStyle=0)
  - backtest/.venv/Scripts/pythonw.exe — exists (verified True)
  - setup/scripts/run_ps1_hidden.py — exists (not used by this fix but referenced for pattern comparison)
  - backtest/tests/test_guard_cmd_popup_fix_ws6.py — exists, 17 tests cover the full before/after
  - setup/scripts/audit_scheduled_tasks.py — exists, _is_bare_console_launcher HARD FAIL at lines 184-190
  - setup/scripts/grind-shard-watchdog.ps1 — EXISTS but needs watchdog State->WMI patch BEFORE deployment
  - setup/install-grind-funnel-tasks.ps1 — DOES NOT EXIST, must be created
  - automation/state/SCHEDULED-TASKS.md — must add Funnel_0..5, Grind_all, Grind_Watchdog, Grind_Vwap to Active table to clear ORPHAN_TASK flags

**Open questions**
  - grind-shard-watchdog.ps1 watchdog logic: must be patched to use WMI process detection instead of task State check before WS6 re-registration. What is the correct WMI query for a pythonw.exe child running -m autoresearch.mass_grind? Suggested: CommandLine -like '*pythonw*' -and CommandLine -like '*mass_grind*' -and CommandLine -notlike '*mass_grind_funnel*' -and CommandLine -notlike '*phase2*'. Mirror the pattern from the old grind-watchdog.ps1 lines 32-38.
  - _shared.ps1 reaper exemption for pythonw.exe: the exemption currently covers 'backtest\.venv' python.exe processes. Does it also cover pythonw.exe from the same venv? If the reaper pattern is `$_.Name -eq 'python'` it won't match `pythonw`. Verify EXEMPT_DAEMONS covers both. If not, the grind will be silently killed by the reaper every 5 minutes (the exact grind-reaper-killer incident from CLAUDE.md).
  - Should Gamma_Funnel_0..5 be unregistered and replaced with a single Gamma_Funnel task that runs all 6 shards sequentially, now that the watchdog drives them? The 6-shard architecture was designed for parallel execution from a common trigger — after the WS6 fix, the watchdog still fires them individually. This is a design question for after the window fix, not a blocker.


**Verdict** — SHIP-worthy. The approach is proven (Gamma_Grind_Vwap uses the identical chain, Gamma_Grind_Watchdog was already converted today), the code is written (`run_cmd_hidden.py`), and the guard tests are written (`test_guard_cmd_popup_fix_ws6.py`). The one HOLD condition is the watchdog State-vs-WMI bug — that must be patched in `grind-shard-watchdog.ps1` BEFORE re-registering Gamma_Grind_all, or you get an infinite restart loop. Fix the watchdog first, then run `install-grind-funnel-tasks.ps1`, then smoke-test. Total work: ~1 hour.

---

## Decision-Inputs Research — Volume / Events / Regime (2026-06-24)

> J's 2026-06-24 ask: *"what other indicators may help us see that — like volume, what current events were going on, or market status overall."* This is the read-only value assessment for **Plan 3** (the Plan 3 / Decision Inputs subsection in this file). Advisory only — no production code/params touched.
>
> **The bar (C3/C4):** an input only earns wiring if a confluence/size/regime use of it **beats the null** on real-fills history. A SPY-price read that a random-entry null reproduces is an exit-structure artifact, not option alpha. **Never a blunt veto** — surviving inputs wire as a confluence modifier, a size multiplier, or a regime switch.
>
> **Scope note:** the directional **premium class is exhaustively closed** (~64 long families + short/long defined-risk all dead — see [STRATEGY-BACKLOG.md (Direction backlog)](../research/STRATEGY-BACKLOG.md)). These three inputs are not new signals; they are **conditioners on the one live edge** (`vwap_continuation`, ATM/0DTE, `params.json#j_vwap_cont_enabled=true`) and the dormant edges #2/#4. The question is which of them measurably *improves* that edge, not whether they create a new one.

---

## TL;DR value table

| Input | Used today? | Incremental value | Disposition |
|---|---|---|---|
| **Volume — filter 9/10 mult (0.7×)** | YES (live, near-no-op) | Knob is set BELOW average = "red/green bar" only. Real lever unused. | **KEEP, re-test as RVOL** (vary-and-assert per C14) |
| **Volume — divergence gates (f7)** | YES (live) | Structural invalidation, cheap. No isolated A/B but low-risk. | **KEEP as-is** |
| **Volume profile / HVN-LVN-POC** | BUILT, not entry-wired | POC/VA *fade* fails L172 null (edge_over_null −$1.06/tr) + truncation guard. As a *fade entry* = DEAD. | **DROP as a trigger; TEST as confluence-only** |
| **Reclaim/rejection volume confirm** | NO | Never isolated-tested on real fills. Cheapest highest-value volume test. | **TEST — the #1 volume experiment** |
| **Catalyst — blackout / macro-bias veto** | YES (live, defensive) | Blackout + counter-trend hard-veto + soft threshold-bump. Defensible. | **KEEP** |
| **Catalyst — size modifier** | flag exists, OFF | `enable_size_modifier_windows=false`, dormant placeholder. Directional-near-event A/B = DEAD (pre-FOMC −$58/tr). | **DROP size-up; consider size-DOWN test only** |
| **Regime — VIX direction/slope** | YES (live, filter 8 + edge #4) | `vix_rising`/`vix_falling` already gate filter 8; `vix_slope5` in dormant edge #4. C5 honored. | **KEEP; thread intraday VIX series to un-block edge #4** |
| **Regime — ribbon stack + conviction** | YES (live, hard gate) | Filter 5 stack + Gate A/B/C. Trend/chop proxy already live via ribbon. | **KEEP** |
| **Regime — trend-vs-chop strategy switch** | DRAFT, watch-only | Per-day regime switch *to a condor* = DEAD (directional out-earns harvester on its own chop days). | **DROP structure-switch; KEEP regime as a per-edge SIZE/ON-OFF dial** |
| **Regime — breadth proxy** | swarm-only (advisory) | `internals_output.json` exists but never reaches the entry gate; no real-fills test. | **TEST as a forward-banked confluence tag (low priority)** |

---

## 1. VOLUME

### What's used today
- **Filter 9 (bear) / Filter 10 (bull)** — `breakdown_bar_bearish` / `buyer_pressure_bar_v11` require `bar.volume >= vol_mult × 20-bar SMA`. Live `filter_9_vol_multiplier = 0.7` (`automation/state/params.json:34`; `backtest/lib/filters.py:135-162`, `:976-982`). **0.7× is BELOW average** — by design (`filters.py:147-149`, `heartbeat.md:452`): it catches J's *morning* rejection bars before volume builds. Net effect: the filter is **effectively just "red bar" (bear) / "green bar" (bull)** — the volume dimension is near-inert at 0.7×. The heartbeat sweep that ratified it (1.3×=$1,768 / 1.0×=$2,136 / **0.7×=$3,053** / off=$1,922, 4-of-4 J anchors) shows *tighter* volume gating HURT on the anchor set — i.e. raw bar-volume-vs-baseline is not a clean confluence signal at entry.
- **Filter 7 — volume divergence** (`volume_divergence_failed` / `_bullish_volume_divergence_failed`, `filters.py:503-527`, `:985-1005`): a breakdown bar followed by an opposite recovery bar with `vol >= breakdown vol` invalidates the setup. Cheap structural guard, live both sides.
- **No RVOL / relative-volume / climax / volume-spike gate exists** anywhere in the entry path (confirmed by full-repo search).

### Volume profile (HVN/LVN/POC) — built but not an edge
- **Implemented**: `backtest/lib/level_strength.py:423-445` (`VolumeProfile`, `compute_volume_profile`) → POC/VAH/VAL. Wired into `key-levels.json` Liquidity tier by `automation/scripts/compute_levels.py:331-354` (prior-day RTH, $0.10 bins, 70% value area, ±$5 of spot). **HVN/LVN nodes are NOT implemented** — only POC/VAH/VAL.
- **As a fade ENTRY it is DEAD on real fills.** `analysis/recommendations/b4-volume_profile_poc.json` (2026-06-21): best cell (developing profile, ATM, −8% stop) = +$1.19/tr, but **fails 4 gates** — `drop_top5_gt0=false`, `is_half_gt0=false`, **`beats_null=false`** (edge_over_null = **−$1.06/tr**; random-entry null MEAN +$2.25/tr *beats* the signal), and `no_truncation=false` (chart-stop-only flips to −$24.75/tr = the positive average was a stop-truncation artifact). Verdict: `NOT A CANDIDATE`. This is the textbook C3/L58 outcome — a real underlying-profile read that theta+delta erase in 0DTE.

### Reclaim/rejection VOLUME confirmation — the untested gap
- **Never isolated-tested.** `level_strength.py` includes `volume_at_touches` as one *scoring* component, but there is **no A/B that asks "does a volume-confirmed reclaim/rejection at a named level beat an unconfirmed one"** on real-fills option P&L. The closest is `analysis/recommendations/vwap-cont-rvol-floor.json`: an **RVOL floor** (session realized-vol bps/bar) on the live `vwap_continuation` edge. It improves WR (84.8% at floor 9.0, n=46) but **fails the full OP-22 gate** (`all_cuts_oos_positive=false`, WF median 0.27<0.70) — 6/7, a near-miss, dormant. That tested *session* vol, not *bar-at-level* volume.

### How to wire (and the experiment to run)
- **KEEP filter 9/10 at 0.7×** (don't tighten — anchor sweep says tightening hurts) but **re-test relative volume as a CONFLUENCE TAG, not a gate**: add an `rvol_at_signal = bar.volume / 20-bar SMA` field to the `vwap_continuation` signal set and A/B whether `rvol >= k` (k swept 1.2–2.0) lifts per-trade expectancy on real fills. **Method:** reuse the `vwap-cont-rvol-floor.json` harness (bar-RVOL instead of session-RVOL) through `lib.simulator_real`; must clear the L172 random-entry null + L171 truncation guard + drop-top5. This is the single highest-value, lowest-cost volume experiment.
- **DROP volume-profile as a trigger** (null-failed). **OPTIONAL**: keep POC/VAH/VAL as a *confluence corroborator* on an *already-validated* level trigger (i.e., +1 confluence weight when the rejected level coincides with POC/VA-edge), only if that confluence variant independently beats the null — do NOT resurrect it as a standalone fade.

---

## 2. CURRENT EVENTS / CATALYSTS

### What's used today (defensive, live)
- **Filter 2 — news clear**: a tick SKIPs if `now_et` is inside any `today-bias.news_calendar.no_trade_window[]` (`heartbeat.md:445`, `:543`). Windows are built premarket (Step 1b) from `macro-calendar.json` HIGH/MED events. `enable_news_no_trade_windows=true` (`params.json:225`).
- **Macro-bias inheritance v2 (hard veto + soft modifier)** (`heartbeat.md:554-584`): reads `events_today[]` for `{fomc, cpi, nfp, pce}`. `0<min≤120` → **HARD VETO** counter-trend entries; `120<min≤240` → **SOFT** (bull ≥10/11, bear ≥7/10); `>240` → standard. `regime_label` (FOMC_EVE_SUPPRESSION / FOMC_DAY_HARD_VETO / FOMC_DAY_SOFT) written to loop-state for context.
- **Scout** (`.claude/skills/scout/SKILL.md`, `automation/scout/state/scout_output.json`) produces `macro_calendar_today[]`, `news_top_5[]`, `catalysts_in_session[]`, `risk_regime_call`, `today_no_trade_windows[]`. **Advisory** — it seeds premarket's bias write; it does **not** directly gate a tick. Note `news.json` is currently stale (`as_of 2026-06-15`, today-bias flags 10-day-stale calendar); the PCE 06-25 overhang lives only in `today-bias.upcoming_events`.

### Is a catalyst ever a SIZE modifier? No.
- `enable_size_modifier_windows=false` (`params.json:226`) — a **dormant placeholder**; premarket emits `size_modifier_windows: []` and no heartbeat code consumes it. Catalysts only *blackout* or *bump thresholds*; size never changes.

### Evidence on trading near catalysts
- **Directional pre-event = DEAD.** `analysis/recommendations/pre-fomc-announcement-drift.json`: pre-FOMC morning entries = **−$58.07/tr** (n=9), 2/8 gates, does not beat the null, L173-negative. No directional edge from being near a scheduled event.
- Event *premium structures* (short condor / long strangle, backlog #6/#6b) are also DEAD once the wide-band tail is priced — but that's a structure test, not a directional-level conditioner.

### How to wire
- **KEEP** the blackout + counter-trend hard-veto + soft threshold-bump exactly as-is — these are *risk* controls (prevent the 05-07 chop-trap), and they're defensible without an edge claim. Do **not** frame them as alpha.
- **DROP "size UP near a catalyst"** — there is no evidence a level-play near a catalyst pays *more*; the directional-near-event test is negative.
- **The only catalyst experiment worth running** is a **size-DOWN / participation dial**, not a veto: does halving size (or requiring +1 confluence) on `vwap_continuation` signals within N hours of a HIGH event reduce drawdown without surrendering expectancy? This is a *risk-adjusted* test (L175 Sortino/maxDD), no-regression-exempt because it never zeroes a day. Lower priority than the volume RVOL test — the macro-bias veto already removes the worst pre-event window.

---

## 3. MARKET STATUS / REGIME

### What's used today
- **VIX *character*, not just level — already honored (C5).** Filter 8 live: bear = `VIX>17.30 AND vix_rising` (cached/flat does **not** pass); bull = `VIX<17.20 OR vix_falling` (`heartbeat.md:451`, `:549`; `filters.py:106-112` `vix_direction` with 0.05 deadband). Direction is a *required* dimension, not optional. The dormant edge #4 (`j_vix_dayside`, `params.json:90-97`) uses an intraday **`vix_slope5`** + trailing-median regime — the cleanest VIX-character use in the repo — but it's inert because the live `BarContext` doesn't yet thread an intraday VIX series (the detector SKIPs rather than guess).
- **Trend-vs-chop via ribbon — already live.** Filter 5 (ribbon BEAR/BULL stack, hard gate) + the v15.3 conviction gates: Gate A ribbon spread Δ≥5¢/3bars (accelerating), Gate B freshness ≤15 bars, Gate C midday single-trendline block. Ribbon-flip-back is a primary *exit*. SPY-vs-MA trend is effectively read through the EMA ribbon stack; SPY-vs-VWAP through the VWAP-family edges.
- **Regime label** is written for context (`heartbeat.md:578-584`) but does **not** switch strategy live.

### Trend-vs-chop strategy SWITCH — tested, dead as a structure switch
- The per-day **regime-switch-to-a-condor** experiment is **DEAD** (backlog #3): on the classifier's own 55 chop days the live directional sleeve out-earned the iron condor +$1,202 vs +$460 (−$743), 0/108 swept cells passed. The premise "directional bleeds in chop, the harvester won't" does **not** hold on real fills — the tight −8% ATM structure stays net-positive in chop. The DRAFT `REGIME_SWITCHER` (`markdown/0dte/regime_switcher.md`, `backtest/lib/regime_classifier.py`) that routes ODF/SNIPER/v14e/VWAP per regime remains watch-only and unvalidated on real fills.

### Breadth proxy — exists, never reaches the gate
- `automation/swarm/state/internals_output.json` (sector XLK/XLF/XLE rotation → `breadth: narrow|broad`) is a **daily swarm advisory**, consumed only by the 6-agent synthesis, **never** by a heartbeat filter. No TICK / advance-decline / McClellan / %-above-MA in the live path, and no real-fills test of breadth as an entry conditioner.

### How to wire
- **KEEP** VIX-direction filter 8 and the ribbon stack/conviction gates — they already encode "market status" the right way (character + trend-structure).
- **Highest-value regime action: thread an intraday VIX series into `BarContext`** so the *validated* dormant edge #4 (`j_vix_dayside`, OOS +$79/tr ATM, clears all 8 gates) can actually fire. This is the one regime input that is *already validated* and only blocked on plumbing — it is a deployment task, not a research task.
- **DROP the trend-vs-chop structure switch** (directional wins its own chop days). Instead, use regime as a **per-edge SIZE / participation dial** (the surviving framing from #3 and the volranker work): a causal morning trend/chop label SIZES the live edge up on its broad winner-days rather than switching it off — but note the volranker sizing result (#9) only pays at $25K+ accounts, so this is forward-banked, not actionable at the current $2K.
- **Breadth: lowest priority.** If tested, forward-bank `breadth` as a *confluence tag* on `vwap_continuation` signals and check it beats the null before any wiring — it is unproven and not on the critical path.

---

## Recommended order of work (all read-only research first, ship under OP-22 if it clears)

1. **Bar-RVOL-at-signal confluence test on `vwap_continuation`** (volume) — cheapest, attacks the one near-inert live knob; reuse `vwap-cont-rvol-floor.json` harness with bar-RVOL; gate on L172 null + L171 truncation + drop-top5.
2. **Thread intraday VIX series into `BarContext`** (regime) — un-blocks the *already-validated* edge #4; deployment, not discovery.
3. **Catalyst size-DOWN / participation dial** (events) — risk-adjusted test (L175), no-regression-exempt; secondary to (1).
4. **POC/VA as confluence-only corroborator** and **breadth forward-bank tag** — lowest priority, only if they independently beat the null.

Everything that fails its null stays DROPPED and gets a one-line entry so it isn't re-hunted (C7/L172).

---
title: Higher-Timeframe Context Layer — Research SPEC (the zoom-out)
parent_plan: the Plan 2 / HTF Context Layer subsection in this file
date: 2026-06-24
author: background research agent (Opus)
status: SPEC — research/advisory only. NO live edits (Rule 9 / OP-22 observability).
cost_class: engine-benefit / read-only research
trigger: J 2026-06-24 — "do we even zoom out ever to like the 4h chart and see what the
  market has done over the past week or 2, like where larger supply/demand zones are, or
  where key levels have been respected for the past X days."
---

## Higher-Timeframe Context Layer — Research SPEC (the zoom-out)

> Read-only deliverable. This SPEC audits what the engine reads today, designs a 4H+daily
> structure read, assesses today (2026-06-24) as the case study, and proposes concrete signal
> additions with exact data sources. It changes **nothing** live. Every proposed signal is a
> **confluence-modifier or regime input, never a hard veto** (C20: a directional gate that
> anti-correlates with the setup is a foot-gun).

---

## 1. AUDIT — what HTF the engine reads today

**Finding: the engine never zooms out above 15-minute. J's instinct is correct — there is no
4H or daily structure read anywhere in the live path.**

### The only HTF read is `htf_15m`, a single 2-bar 15m stack snapshot:

- **Heartbeat prompt** [`automation/prompts/heartbeat.md:220-224`](../../automation/prompts/heartbeat.md):
  > "## SPY 15m HTF (only on tickIndex % 5 == 1) … `chart_set_timeframe("15")` →
  > `data_get_ohlcv(count=2, summary=true)` → `data_get_study_values` → `chart_set_timeframe("5")`
  > to restore. Update `loop-state.htf_15m`." It reads **2 bars** of 15m and the ribbon stack only.
- **Used as a SOFT score-modifier, not context** — `heartbeat.md:453`: "htf_15m_stack … == "BULL"
  → -1 score-modifier (NOT a hard block)". Filter 10/11.
- **Backtest engine mirrors it** — [`backtest/lib/filters.py:85`](../../backtest/lib/filters.py)
  `htf_15m_stack: Optional[str]` is the **only** HTF field on `SetupContext`; consumed at
  `filters.py:902-962` (bearish filter 11) and `filters.py:1140-1338` (bullish filter 10) as a
  ±1 modifier. No 4H/1D/swing/zone field exists.
- **Aggressive tick** [`automation/scripts/heartbeat_aggressive_tick.py:70-72`](../../automation/scripts/heartbeat_aggressive_tick.py):
  `htf = loop_state.get("htf_15m")` — same single field, nothing else.
- **loop-state schema** `heartbeat.md:835`: `"htf_15m": {last_close_time, fast, pivot, slow,
  spread_cents, stack}` — the entire HTF memory of the engine.

### What it does NOT read (grep-confirmed, repo-wide):
- No `data_get_ohlcv` / `chart_set_timeframe` call at `"240"` (4H), `"60"` (1H), or `"1D"`/`"D"`
  anywhere in `automation/prompts/`, `automation/scripts/`, or `backtest/lib/`.
- No multi-day swing-structure (HH/HL/LH/LL) read in the live path. The structure code that
  *exists* ([`crypto/lib/market_structure.py`](../../crypto/lib/market_structure.py)) is gym/
  chart-read-skill only and runs on **5m** bars — its own docstring (lines 29-32) flags it as
  "telemetry only … wiring structure into the LIVE fleet" is an open blocker.
- `respect_count` / `broken_count` on each level are **dead placeholders** (PLAN-2 §2.4, A1) —
  initialized 0, never incremented. So there is no per-level "respected vs broken over X days"
  memory either. (Phase 0 of the KEY-LEVELS plan builds the outcome scorer but it isn't wired.)
- PLAN-2-HTF §gap and the key-levels handoff D2 both already name this: heartbeat "sees ~15 min
  of 5m + 30 min of 15m" — **no multi-hour / multi-day context**.

**Verdict: confirmed. Nothing above 15m, and the 15m it does read is 2 bars used as a ±1 nudge.**

---

## 2. DESIGN — a 4H + daily structure read

Three independent reads, each a self-contained pure function over OHLCV bars, written to a new
`loop-state.htf_context` block (read-only telemetry first). All reuse existing primitives — no
new structure/level engine.

### 2A. Swing structure (HH/HL/LH/LL) over the past 1-2 weeks

- **Reuse as-is:** [`crypto/lib/market_structure.py`](../../crypto/lib/market_structure.py)
  `analyze_structure(bars, window=…, swing_finder=…)`. It already returns labeled swings
  (HH/HL/LH/LL), a walked working-trend (BOS/CHoCH state machine, no look-ahead), and a heuristic
  confidence. It is **timeframe-agnostic** — feed it **daily RTH bars** (≈10 bars = 2 weeks) and
  **4H bars** (≈20-30 bars) instead of 5m.
- **Swing-finder injection (the drift guard the module's own docstring demands, lines 29-32):**
  pass the live engine's pivot primitive via `swing_finder=` so there is ONE structure
  implementation across gym + live. Use `window=1` for daily (10 bars is too few for a 2-per-side
  fractal), `window=2` for 4H.
- **Output:** `{daily_trend: uptrend|downtrend|range, daily_trend_basis, recent_label_sequence:
  ["LH","LL","LH","LL"...], last_swing_high, last_swing_low, last_event: BOS|CHoCH}` — answers
  J's literal question "are we making higher highs and lower lows" at the daily scale.

### 2B. Larger supply/demand zones (bands, not lines)

The key-levels generator draws **lines** (single prices). HTF S/D zones are **bands**
(consolidation-before-impulse). New pure function `htf_zones.py`:

- **Method (deterministic, no look-ahead):** over the trailing N daily/4H bars, find
  *consolidation-before-impulse* — a run of ≥2 bars whose ranges overlap within a tolerance
  (the base), immediately followed by an impulse bar (range > k×ATR) leaving the base. The base's
  `[min(low), max(high)]` is the zone band; demand if the impulse is up, supply if down.
- **Reuse:** the swing pivots from 2A bracket candidate bases; `crypto/lib/` already has ATR-style
  range math in the indicators layer. Tag each zone `{lo, hi, kind: demand|supply, n_touches,
  formed_date, mid}`. Draw as a **rectangle** band (`mcp__tradingview__draw_shape` rectangle —
  already used for J's manual zones per key-levels.json `chart_cleanup_log`), never a horizontal
  line.
- **Output:** `daily_zones[]` sorted by distance from spot, nearest demand below + nearest supply
  above surfaced first.

### 2C. Per-named-level "respect score" (respected vs broken over past X days)

- **Reuse the already-built outcome scorer:**
  [`analysis/level-quality/score_level_outcomes.py`](../../analysis/level-quality/score_level_outcomes.py)
  + `benchmark_level_quality.py` `classify_level()` (RESPECT / BREAK / CHOP, no look-ahead) — this
  is exactly the "respected vs broken" classifier, already validated on 219 days (PLAN-2 §3).
- **The level loader is already shared:** [`backtest/lib/watchers/level_source.py`](../../backtest/lib/watchers/level_source.py)
  `load_named_levels()` / `level_stars()` — feed each named level from `key-levels.json` into the
  scorer over the trailing X RTH sessions.
- **Respect score = respect_touches / total_touches over trailing X days** (X=10 proposed),
  written to a SEPARATE `level-memory.json` (PLAN-2 Task 0.3 already specs this exact file — do
  **not** mutate `key-levels.json`; that is premarket's job / Rule 9). This finally makes
  `respect_count`/`broken_count` real (PLAN-2 A1/A3) — the HTF layer is the consumer that
  justifies wiring Phase 0.
- **Output per level:** `{price, respect_score: 0..1, n_touches, n_respect, n_break, last_touch,
  verdict: RESPECTED|BROKEN|UNTESTED}`.

> **Honest caveat (OP-20 / L58):** the 219-day benchmark already showed levels have ~2.4× touch
> (placement) edge but **~0 reaction edge** once touched (−2.4pp vs random). So a high respect
> score is a *descriptive prior*, useful as a confidence tint — **not** proof the level will
> bounce. Hence: confluence-modifier, never veto.

---

## 3. ASSESS — today (2026-06-24) as the case study

J's case: SPY dipped to **734.11 (~10:20 ET)** and reclaimed/trended to **739.95 (~11:00 ET)**,
a ~$5.85 move. Question: where did that sit in the 4H/daily picture, and would HTF context have
raised conviction?

**Data (real, from `backtest/data/spy_5m_2026-05-19_2026-06-24.csv`; TV CDP + Alpaca SIP/IEX were
all in outage today, so local CSV is the source — see §4 note):**

Daily RTH OHLC, trailing 2 weeks:

| Date | O | H | L | C | note |
|---|---|---|---|---|---|
| 06-15 | 751.9 | 754.1 | 751.8 | **753.5** | local top |
| 06-16 | 754.6 | 755.4 | 750.1 | 750.6 | LH |
| 06-17 | 751.3 | 752.2 | 739.2 | 741.0 | impulse down |
| 06-18 | 747.8 | 748.2 | 743.9 | 747.9 | bounce |
| 06-22 | 747.7 | 750.2 | 743.1 | 744.3 | LH, reversal day |
| 06-23 | 733.8 | 739.6 | 732.3 | 733.7 | **gap down, broke 743 shelf** |
| 06-24 | 735.2 | **739.95** | **730.84** | 732.4 | the case day |

**Daily structure read = DOWNTREND** (closes 753.5→750.6→…→744.3→733.7→732.4 = LH/LL run;
06-23 close broke the 743.35 double-bottom shelf — a daily CHoCH→BOS-down).

**Where the 734.11 dip sat:** squarely inside a **730-735 multi-day DEMAND shelf** —
06-12 L=735.03, 06-23 L=732.30, 06-24 L=730.84 all cluster here, plus prior-day close 734.97 and
PML 734.80. → **HTF context WOULD have raised conviction on the long-side bounce**: the dip tagged
a real multi-day demand band, not no-man's-land.

**Where the 739.95 reclaim peaked:** **exactly at a multi-day SUPPLY shelf** — 06-11 H=740.00,
06-23 H=739.63, and still **below the broken 743.35 support-turned-resistance**. → **HTF context
would have CAPPED the target and flagged the move as a countertrend bounce into supply.** And it
was: price faded all afternoon back to **730.84** and **closed 732.36** (a down day, below prior
close).

**Verdict (today):** HTF context helps — but the value is **two-sided and exactly the
confluence-modifier shape J's plan calls for, not a veto:**
1. It **raises conviction on the entry** (dip into a multi-day demand shelf) — would have nudged a
   bull/long score up.
2. It **lowers conviction on holding for more** (peak into multi-day supply + below broken
   support + daily downtrend) — would have argued *take profit at 739-740, don't chase the runner*.
   The afternoon fade to 730.84 confirms the runner had no HTF room.

A pure 5m engine saw a clean $5.85 reclaim and no reason to be cautious at 740. The HTF layer is
precisely what distinguishes "a reclaim with daily room to run" from "a countertrend bounce into a
2-week supply shelf, in a daily downtrend, below broken support." Same 5m trigger, very different
trade — which is the core thesis of PLAN-2.

---

## 4. PROPOSE — concrete signal additions + data sources

All three land in a new `loop-state.htf_context` block, refreshed **once per ~30 min** (every 10th
tick, same cadence pattern as the existing 15m %5 read) — HTF bars move slowly, so this is near-
zero marginal cost (~1-2 extra `data_get_ohlcv` calls per refresh). **Each is a confluence-modifier
or regime input. None is a hard veto (C20).**

| Signal | Shape | Role | Data source |
|---|---|---|---|
| `htf_4h_stack` | `{trend, label_seq, last_event, last_swing_hi/lo}` from `analyze_structure` on 4H bars | **Regime input** — extends the existing `htf_15m` ±1 nudge to a 4H/daily ladder (15m→4H→1D agreement = stronger modifier) | **TV MCP** `chart_set_timeframe("240") → data_get_ohlcv(count=30, summary=false) → restore("5")` (the existing 15m read pattern, one timeframe up). **Fallback: Alpaca** `get_stock_bars(SPY, "4Hour"?→use "1Hour" ×4 or "1Day")` |
| `daily_trend` | `uptrend\|downtrend\|range` + `label_seq` from `analyze_structure` on ~10 daily RTH bars | **Regime input** — tints score: a long into a daily downtrend gets −1 conviction (NOT blocked), a long with daily uptrend gets +1 | **TV MCP** `chart_set_timeframe("1D") → data_get_ohlcv(count=12)`. **Fallback: Alpaca** `get_stock_bars(SPY, "1Day", days=21)` (the §3 table was built this way) |
| `daily_zones[]` | bands `{lo, hi, kind: demand\|supply, n_touches, mid}` from `htf_zones.py` | **Confluence-modifier** — a 5m trigger *inside / at the edge of* a same-direction HTF zone gets +1; a trigger whose target runs into an opposing zone caps the runner target | Derived from the **same daily+4H bars** as above (no extra fetch). Draw as **rectangle** band via `mcp__tradingview__draw_shape` |
| `level_respect_score` | per named level `{respect_score, n_touches, verdict}` | **Confluence-modifier** — a trigger at a level with high trailing respect score gets a small confidence tint; UNTESTED/BROKEN levels get none | **Local/offline** — `score_level_outcomes.py` over trailing X days of 5m CSV (`backtest/data/`), written to `level-memory.json` (PLAN-2 Task 0.3). **Wiring Phase-0 of the key-levels plan is the prerequisite.** |

### Data-source recommendation
- **Primary: TradingView MCP** `data_get_ohlcv` at `"240"` and `"1D"`, reusing the exact
  set→read→restore discipline already in `heartbeat.md:222` (and the connectivity-gate
  `TV_DATA_LIVE` freshness check in `.claude/skills/tradingview-ops/SKILL.md:35`). It is the live
  engine's existing chart source — least new surface area.
- **Fallback: Alpaca** `get_stock_bars(SPY, "1Day"/"1Hour")`. **Caveat surfaced today:** both TV
  CDP **and** Alpaca SIP+IEX were down/401 on 2026-06-24 (broader usage-cap outage), so the §3
  numbers came from the **local `backtest/data/` 5m CSV aggregated to daily**. That CSV merge is a
  third, always-available source and the natural one for the offline `level_respect_score` backfill
  regardless. A robust HTF read should try TV → Alpaca → local-CSV-aggregate in order.

### Wiring guidance (for the eventual build — NOT this SPEC)
1. Ship `htf_zones.py` + the daily/4H structure read as **pure functions** with gym validators
   first (OP-26), exactly as `market_structure.py` was shipped read-only.
2. Surface `htf_context` into `loop-state` as **telemetry** (WATCH_ONLY) for ≥1-2 weeks; log it on
   every decision row alongside the 5m read. Measure: does HTF agreement separate winners from
   losers on the existing decision ledger (the same A/B method as the level benchmark)?
3. Only after that shows separation, propose the ±1 modifier wiring as a DRAFT scorecard for J
   (OP-11 gates). The modifier must be **soft** (score nudge + runner-target cap), per C20 and the
   −2.4pp reaction-edge caveat.

### Anti-foot-gun checklist
- **No look-ahead (C6):** filter bars to closed only; `analyze_structure` already lags swings by
  `window` bars. Daily "current" bar must be excluded until RTH close.
- **No veto (C20):** every signal is additive ±1 / target-cap, never a block.
- **One structure impl (autonomy blueprint):** inject the live swing primitive via `swing_finder`,
  don't fork.
- **Respect-score is a prior, not a guarantee (L58):** levels have placement edge, ~0 reaction
  edge — tint confidence, don't gate.
- **Cost (OP-3):** ~1-2 extra `data_get_ohlcv` per 30 min ≈ negligible; the respect-score backfill
  is offline pure-Python ($0).

---

## 5. Reuse map (what's already built — do not rewrite)

| Need | Existing asset | Action |
|---|---|---|
| Swing HH/HL/LH/LL + BOS/CHoCH | `crypto/lib/market_structure.py` `analyze_structure` | Feed daily/4H bars + inject swing_finder |
| Named-level loading + stars | `backtest/lib/watchers/level_source.py` | Reuse `load_named_levels` |
| Respected-vs-broken classifier | `analysis/level-quality/{score_level_outcomes,benchmark_level_quality}.py` | Reuse `classify_level` over trailing X days |
| `respect_count`/`level-memory.json` plumbing | PLAN-2 Phase 0 Tasks 0.1-0.3 (specced, partly built) | Wire Phase 0 — it's the prerequisite consumer |
| HTF S/D bands | none — `htf_zones.py` is the one new module | Build as pure function + gym validator |
| TV set→read→restore HTF read | `heartbeat.md:222` (15m), `tradingview-ops` SKILL | Clone pattern at "240"/"1D" |

---

_Evidence: repo grep audit (htf_15m only — heartbeat.md:220-224/453, filters.py:85/902/1140,
heartbeat_aggressive_tick.py:70-72); crypto/lib/market_structure.py + level_source.py +
analysis/level-quality/ read; today's daily structure aggregated from
backtest/data/spy_5m_2026-05-19_2026-06-24.csv (TV+Alpaca both in outage 2026-06-24). Changes
nothing live; makes HTF context buildable as a confluence-modifier under OP-22/OP-11._
