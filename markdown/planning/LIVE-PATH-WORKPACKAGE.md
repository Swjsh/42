# LIVE-PATH WORK-PACKAGE — daytime / J-aware deliberate ship-steps

> **Why this doc exists.** The live order/entry path is the riskiest set of files in the rig. Overnight RESEARCH batches are forbidden from editing live watchers / `params.json` / the order builder. When a research batch validates a *shippable* live-path improvement, it appends a precise BUILD-SPEC here instead of touching the live path. J (or a daytime session) executes these deliberately: build behind an isolated flag (default OFF), gym + parity green, A/B confirmed, then ONE flag flip in daylight.
>
> **Discipline (every spec below):** exact file + isolated flag (default OFF) + gamma-sync targets + parity test (flag-OFF == current behavior) + the A/B numbers + the one-flag enable. Never silently change the live engine at 3am.
>
> **Source verdicts:** `markdown/research/STRATEGY-HUNT-BACKLOG.md` STATUS log + the per-angle scorecards in `analysis/recommendations/`.

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
