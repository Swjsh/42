# Regime-Aware Multi-Setup Book — Architecture

> **Status: DESIGN + LEAN SCAFFOLD (propose-only, Rule 9).** This document + `backtest/lib/engine/regime_book.py` define the architecture that ends the **one-setup fragility** by deploying *the right setup per regime*. **Nothing here is wired into the live heartbeat, params, or any trading path.** The regime→setup map is **provisional** — populated by candidates found on **proxy ★★ levels** this weekend (`analysis/recommendations/fleet-standalone-regime.json`), each of which must still **earn its place on real ★★★ levels** before it goes regime-active. The book is the *framework*; the validated setups slot into it as they pass the promotion bar.
>
> Authored 2026-06-19. Inputs: `fleet-standalone-regime.json`, `bullish-reclaim-standalone.json`, `WEEKEND-FINDINGS-RATIFICATION-2026-06-19.md`, `backtest/lib/engine/gex_regime.py`.

---

## 1. The problem this solves

Today the engine trades **one setup**: `BEARISH_REJECTION_RIDE_THE_RIBBON`. The whole weekend's research re-confirmed it is *the* edge — the only entry that fires with J's bearish-continuation winners (`WEEKEND-FINDINGS-RATIFICATION` "THE STANDING TRUTH"). But a one-setup book is **structurally fragile**:

- **It only earns in its own regime.** A bearish-continuation setup is dead weight (or worse, a bleed) on a quiet bull-grind day or a low-vol pin day. The engine is flat-or-losing on every day the market is *not* trending down.
- **No diversification of return.** All P&L is correlated to one market state. A regime drought = an account drought.
- **The biased-gate trap.** The weekend's *first* pass gated every candidate setup on `edge_capture` vs J's **bearish** anchors (all down-days). A bullish or mean-reversion setup that works on **up/range days cannot capture a put winner by construction** — so it was auto-rejected. That is **selection bias, not absence of edge** (`fleet-standalone-regime.json#method_contrast`, `bullish-reclaim-standalone.json#framing_correction`). The corrected, **unbiased standalone** re-eval found *other* setups carry their own per-regime edge.

**The fix is not "find a better single setup." It is a BOOK: a small roster of setups, each scoped to the regime where it has edge, with a cheap classifier routing each bar to the eligible setup(s).** When the regime is bear-trend, the bearish setup is live; when it's a low-vol range, a mean-reversion/double-bottom setup is live instead; when it's a bull-grind, the reclaim setup. The engine is *never* forced to trade the wrong tool for the day — and on a day with no edge-aligned setup, it correctly **abstains** (a high-score + 0-trade + wrong-regime day is a *correct* abstention, theme C5).

This kills the fragility three ways: **(1)** return is spread across regimes, not concentrated in one; **(2)** each setup only fires where it has measured edge, so the off-regime bleed disappears; **(3)** the book is **data-driven config**, so a newly-validated setup is *added*, not *rebuilt* — the architecture scales as research earns it.

---

## 2. The three layers

```
            ┌─────────────────────────────────────────────────────────────┐
            │  BarContext (filters.BarContext) — VIX, ribbon, range, levels │
            │             + optional GexRegime tag (live-only)              │
            └───────────────────────────────┬─────────────────────────────┘
                                            │
                            ┌───────────────▼───────────────┐
                            │   LAYER 1: classify_regime()   │   pure, $0
                            │   → Regime (bull_trend /       │   from signals
                            │     bear_trend / range_pin /   │   we already have
                            │     high_vol / neutral)        │
                            └───────────────┬───────────────┘
                                            │  Regime
                            ┌───────────────▼───────────────┐
                            │   LAYER 2: REGIME_SETUP_MAP     │   DATA (a dict),
                            │   regime → [SetupSlot, ...]     │   not logic.
                            │   select_setups(regime)         │   Add/promote
                            │   → only ACTIVE slots           │   setups here.
                            └───────────────┬───────────────┘
                                            │  [SetupSlot] (eligible setups)
                            ┌───────────────▼───────────────┐
                            │   LAYER 3 (existing engine):    │   UNCHANGED.
                            │   each setup's own filters/     │   The regime layer
                            │   gates score the bar           │   only decides
                            │   (engine.score + engine.gates) │   WHICH runs.
                            └─────────────────────────────────┘
```

**The contract between the layers is the key design choice:** the regime layer decides **eligibility** (which setup the engine is *allowed* to consider this bar); each setup's **own** filters/gates still decide whether it actually *fires*. The regime layer never relaxes a setup's gate, never invents a trigger, never sizes a position by itself. It is a **router**, not a strategy. A setup that is "regime-active" still has to pass all 10/11 of its own filters before a single contract trades — so the regime layer **adds** discipline (it can *forbid* an off-regime setup) and never *removes* any.

---

## 3. Layer 1 — the regime classifier (`classify_regime`)

**Design principle: classify from signals we already compute, at $0, with no look-ahead.** Every input is already on the `BarContext` (or derivable from it) at or before the trigger bar — no new data feed, no network, no clock.

### 3.1 The signals (all already in `BarContext`)

| Signal | Source field | What it reads |
|---|---|---|
| **VIX level** | `ctx.vix_now` | Absolute fear level. Buckets (from the weekend proxy): LOW < 15, MID, HIGH ≥ 19. |
| **VIX character** | `ctx.vix_now` vs `ctx.vix_prior` (via `filters.vix_direction`, 0.05 deadband) and vs `ctx.vix_5d_ma` | *Rising / falling / level.* Character > level (theme C5): the bearish edge needs **rising** VIX; bullish-reclaim needs **low/falling** VIX (`bullish-reclaim-standalone#regime_gate_finding`). |
| **Trend vs range (intraday MA stack)** | `ctx.ribbon_now.stack` ∈ {BULL, BEAR, MIXED} | The fast/pivot/slow EMA stack. Strict BULL/BEAR ordering = a trend; MIXED = chop/range. This is the cheapest ADX-lite we have and it's already computed every bar. |
| **Trend vs range (higher timeframe)** | `ctx.htf_15m_stack` ∈ {BULL, BEAR, MIXED, None} | 15m ribbon stack — corroborates the 5m read so a 1-bar 5m flip doesn't whipsaw the regime. |
| **Range compression** | current bar range vs `ctx.range_baseline_20` | The weekend's `pin_proxy` ingredient: `today_range / trailing_median_range < 0.85` ⇒ compressed/pinning. A LEAN stand-in for a quiet/range tape. |
| **Dealer gamma (LIVE only, optional)** | `gex_regime.compute_gex_regime(...).regime` ∈ {long_gamma_pin, short_gamma_trend, flat} | The one *peer-reviewed* regime signal (Barbon-Buraschi, Baltussen JFE 2021). **Cannot be backtested** (no historical chain OI — `gex_regime.assess_backtest_feasibility`). It is a **live-going-forward corroborator**, passed in as an optional override hint; absent in all backtests. |

### 3.2 The regime labels

`classify_regime(ctx) → Regime`, a frozen enum-like value, one of:

| Regime | Definition (lean, from the signals above) | The market state |
|---|---|---|
| **`bear_trend`** | ribbon BEAR (5m) **and not** VIX-falling — i.e. a down-stack with stable/rising fear. | Trending down. The confirmed bearish-continuation regime. |
| **`bull_trend`** | ribbon BULL (5m), VIX **not** rising, not compressed. | Grinding up. |
| **`range_pin`** | ribbon MIXED **and** compressed (`range_ratio < 0.85`) **and** VIX low (< 16). (LIVE: corroborate with GEX `long_gamma_pin`.) | Quiet, mean-reverting, pinned. |
| **`high_vol`** | VIX ≥ 19 (HIGH bucket), regardless of stack. | Elevated fear — a distinct population (theme C23: tier labels conflate VIX regimes; high-vol is its own bucket). |
| **`neutral`** | none of the above fire cleanly (e.g. MIXED stack, mid VIX, no compression). | No clean read → conservative default. |

**Precedence (declared, deterministic):** `high_vol` is checked **first** (an elevated-fear day is high-vol *whatever* the stack says — this prevents a BEAR-stacked panic day from masquerading as an ordinary `bear_trend`). Then `bear_trend`, then `bull_trend`, then `range_pin`, else `neutral`. Precedence is a **declared constant** (`REGIME_PRECEDENCE`) so the order is auditable and testable, never buried in `if/elif` nesting (coding-style: no deep nesting, no hidden control flow).

**Honest scope of the classifier:** it is a **coarse 5-way tag**, deliberately. It is *not* a probabilistic regime model, not an HMM, not a fitted classifier. The whole point is leanness — the signals are crude but free and look-ahead-safe, and the *book* (Layer 2) is where the intelligence lives. If a finer regime read is ever needed, it slots in behind this same `classify_regime` interface without touching Layers 2-3.

---

## 4. Layer 2 — the regime→setup routing (`REGIME_SETUP_MAP` + `select_setups`)

**Design principle: the map is DATA, not code.** A `dict[Regime, tuple[SetupSlot, ...]]`. Adding a setup, promoting a setup, or re-scoping a setup is a **data edit** (or, later, a JSON/params load) — never a logic change. This is the single most important property: it is what lets the book grow as research validates setups, with no engine surgery (theme C14: knobs must be data the engine reads, not hardcoded constants).

### 4.1 The `SetupSlot` record (one entry in the map)

A frozen dataclass — pure data describing *how* a setup participates in a regime:

```
SetupSlot(
    setup:        str,            # canonical setup id, e.g. "BEARISH_REJECTION_RIDE_THE_RIBBON"
    status:       PromotionStatus # WATCH_ONLY | REGIME_ACTIVE | RETIRED
    sizing_tier:  str,            # "base" | "elite" | "half" — advisory hint to the sizer; NEVER a position itself
    evidence:     Evidence,       # exp / wr / n / dsr_verdict / oos_sign_stable / low_power — provenance, carried verbatim
    note:         str,            # one-line human rationale + caveat
)
```

`evidence` is **provenance, carried in the data** — the standalone expectancy, WR, n, DSR verdict and OOS-stability from the scorecard that justified the slot. This means the map is **self-documenting**: anyone reading `REGIME_SETUP_MAP` sees *why* each setup is there and *how strong* the evidence is, without cross-referencing a JSON. It also makes the promotion gate (§5) checkable **in code** against the slot's own evidence.

### 4.2 `select_setups(regime, *, include_watch=False)`

The selector. Given a regime, returns the slots mapped to it. **By default it returns only `REGIME_ACTIVE` slots** — the ones that have earned live eligibility. `WATCH_ONLY` slots are **excluded** from the live-eligible set; they live in the map (so the framework is populated and visible) but the selector filters them out of any trading decision. Passing `include_watch=True` returns them too — for research/shadow-mode/reporting only. `RETIRED` slots are never returned.

This is the **safety property that makes the whole thing propose-safe**: because the entire current map is `WATCH_ONLY` (no setup has cleared the real-★★★ bar yet), `select_setups(regime)` with defaults returns **an empty roster for every regime today**. The book is wired-up but inert — exactly the propose-only posture Rule 9 requires. The day a setup is promoted to `REGIME_ACTIVE` (a one-line data edit, after the bar is met), it becomes selectable; not before.

### 4.3 The provisional map (today — ALL `WATCH_ONLY`)

From `fleet-standalone-regime.json#diversified_book_regime_map` (the corrected, unbiased standalone real-fills eval). **Every number is on ★★ proxy levels and every slot is `WATCH_ONLY`.** This is the framework's *seed*, not its trading config.

| Regime | Candidate setup(s) | In-regime exp / WR / n (proxy) | Status | Provenance / caveat |
|---|---|---|---|---|
| **bear_trend** | `BEARISH_REJECTION_RIDE_THE_RIBBON` | the confirmed edge (J-anchored) | `WATCH_ONLY`† | †The *only* setup with J's real winners. Bar to promote = re-confirm on real ★★★ + the live archive. |
| | `NAMED_LEVEL_SECOND_TEST` (long) | +8.65 / 63.2% / 144 | `WATCH_ONLY` | DSR WEAK; proxy levels. |
| **bull_trend** | `DOUBLE_BOTTOM_MORNING_LOW_VOL` | +20.6 / 66.7% / 24 | `WATCH_ONLY` | Best standalone exp; DSR WEAK. |
| | `DOUBLE_BOTTOM_BASE_QUIET` | +9.95 / 58.3% / 24 | `WATCH_ONLY` | OOS sign **unstable** standalone. |
| | `BULLISH_RECLAIM_RIDE_THE_RIBBON` | +10.33 / 54.9% / 82 | `WATCH_ONLY` | Low-VIX (14-16) is the positive slice only. |
| **high_vol** | `NAMED_LEVEL_SECOND_TEST` | +22.26 / 66.7% / 144 | `WATCH_ONLY` | Strongest in-regime cell; DSR WEAK but best of fleet. |
| | `DOUBLE_BOTTOM_MORNING_LOW_VOL` | +80.9 / 80% / 5 | `WATCH_ONLY` | **low_power (n=5)** — do not over-read (C24). |
| **range_pin** | *(empty — see note)* | — | — | The bounce family **may** revive here on real levels; `FLOOR_HOLD_BOUNCE` revived in-regime on proxies but n=2. Slot stays **empty** until real-level evidence exists. |
| **neutral** | *(empty)* | — | — | No edge-aligned setup → **abstain.** Correct behavior, not a gap. |

> **Note on `range_pin` / the bounce family.** The unbiased eval found `FLOOR_HOLD_BOUNCE` is *dead unconditioned* but flips **positive in-regime** (`range_pin`/`ribbon_mixed`) — REVIVED-IN-REGIME (`fleet-standalone-regime.json#h2_regime_conditioned_meanrev`). But the in-regime n is 2-11 (**low_power**), and the exit geometry that earned it is the **mean-reversion exit** (ITM-2 + tight TP), *not* the engine's default chart-stop-only (the weekend's uniform exit itself biased the bounce family's exp downward — `op20_disclosures#exit_geometry`). So `range_pin` is **deliberately left empty** in the seed map: the candidate exists, but it has not cleared the bar, and wiring it on `n=2` proxy evidence would be exactly the over-fit this architecture exists to prevent. It is a **named target for the next real-fills re-test**, recorded as a `WATCH_ONLY` candidate in the doc, not a live slot.

**This is the diversification thesis, stated as a map:** different regimes route to *different* setups, so the book earns across the regime cycle instead of betting everything on bear-trend days — once each slot earns promotion.

---

## 5. Layer 3 — integration with the existing engine

The regime layer sits **in front of** the existing decision-lib (`engine/score.py`, `engine/gates.py`) and changes **nothing** below it. The intended call shape (for a *future* Phase 4 cutover, **not** wired now):

```
regime  = classify_regime(ctx)                       # Layer 1 — $0, look-ahead-safe
slots   = select_setups(regime)                      # Layer 2 — only REGIME_ACTIVE (empty today)
for slot in slots:
    # Layer 3 — the setup's OWN filters/gates still decide if it fires:
    score = engine.score.score_bar(ctx, ...)         # unchanged
    block = engine.gates.evaluate_gates(gate_ctx, …) # unchanged
    # slot.sizing_tier is an ADVISORY hint to the existing sizer; the sizer + risk_gate still own the position.
```

**Why this is the right seam:**

- **It composes with the shared decision library, doesn't fork it.** `engine/score.py` and `engine/gates.py` are the parity-proven core both backtest and live will call (`SHARED-DECISION-LIBRARY-MIGRATION.md`). The regime book is a **pre-filter on which setup string the engine evaluates** — it rides *on top of* that core, so it inherits the same backtest-equals-live guarantee for free, and adds no new drift vector.
- **It composes with the GEX tag.** `gex_regime.py` produces a live-only `long_gamma_pin` / `short_gamma_trend` tag. `classify_regime` accepts it as an **optional corroborator** (`gex_hint`): when present (live), a `short_gamma_trend` reading reinforces `bear_trend`/`high_vol`; `long_gamma_pin` reinforces `range_pin`. When absent (every backtest, since there's no historical chain OI — `assess_backtest_feasibility`), the classifier falls back cleanly to the VIX+ribbon+compression signals. **No code path requires GEX**, so the classifier is fully backtestable today and *strictly improves* live once the chain-snapshot archive banks.
- **It composes with risk_gate + the sizer.** `slot.sizing_tier` is an **advisory string** the existing sizer can read; it is **never** a position. `risk_gate.check_order` remains the final authority on size and the per-account caps. The regime layer cannot size up, cannot bypass the kill switch, cannot place an order (Rule 9 + the 10 rules are downstream and untouched).

---

## 6. The promotion lifecycle (how a setup earns a live slot)

A setup moves through three states. **The default and current state of every setup in the seed map is `WATCH_ONLY`** — present in the framework, excluded by `select_setups` from any live decision.

```
   WATCH_ONLY  ──(meets PROMOTION BAR)──►  REGIME_ACTIVE  ──(regresses / J revoke)──►  RETIRED
       │                                        │
       └──────────── stays inert ──────────────┘   (only REGIME_ACTIVE is selectable live)
```

### 6.1 The promotion bar (the gate to `REGIME_ACTIVE`)

A `WATCH_ONLY` slot becomes `REGIME_ACTIVE` **only** when *all* of the following hold — this reuses the existing OP-21 / auto-ratify gate, applied **per regime**:

1. **Standalone real-fills positive on REAL ★★★ levels.** Not proxy ★★ levels. The entire seed map is proxy-bounded (L58: PDL-class proxies understate ★★★ WR by up to ~20pp); the ★★★ archive (just stood up, now accruing — `WEEKEND-FINDINGS-RATIFICATION` "BUILT / UNBLOCKED") must bank ~20-30 trading days, then **re-run the in-regime real-fills eval on real levels.** This is the single highest-value unblock.
2. **OOS sign-stable** in that regime (the corrected-split discipline; theme C4 — normalize OOS).
3. **DSR clears the selection-adjusted bar** (≥ 0.90, per the existing scorecard gate). Today every fleet candidate is DSR **WEAK** on proxies — *none* would pass yet, which is correct.
4. **Anchor no-regression** — the change must not regress J's source-of-truth trades (OP-16). For bear_trend this means J's 7 anchors; for a *new* regime/setup, J needs his **own logged winners** for that setup (the seed map's bull/mean-reversion/double-bottom setups have **no J winners yet** — `op20_disclosures#j_examples_caveat`), so J confirmation is part of the bar for any non-bearish slot.
5. **A/B scorecard filed** at `analysis/recommendations/{setup}-{regime}.json` (the eval-first gate, OP-11 / OP-21).
6. **`evidence_n ≥ 15`** advisory (prefer it; J's explicit authorization can override per OP-16/OP-21).

**Who promotes:** per the "J is NOT a ratification gate" doctrine (OP-21, 2026-06-16), a slot that clears bars 1-5 on **real ★★★ levels** ships **autonomously** after-hours — **except** that any **non-bearish** slot additionally needs J's own logged winners for that setup (bar 4), because we have none today. J's standing role is **REVOKE**, not approve. Promotion is a **one-line data edit** (`status=WATCH_ONLY → REGIME_ACTIVE` in `REGIME_SETUP_MAP`) plus the filed scorecard — *no engine code changes*, which is the entire payoff of the data-driven map.

### 6.2 Demotion (`RETIRED`)

A `REGIME_ACTIVE` slot drops to `RETIRED` on (a) J revoke (Rule 9 — J's off-switch), or (b) a measured regression in its regime (the existing drift/no-regression checks). `RETIRED` slots are never selected; they stay in the map as a **record** (so we don't re-cook a known-dead setup — theme C24).

### 6.3 Why this lifecycle prevents the over-fit it's meant to cure

The danger of a multi-setup book is **multiplying the surface for curve-fitting** — more setups × more regimes = more knobs to over-tune on thin slices. The lifecycle is the guard: a setup is **inert until it independently clears the same bar the single setup had to clear**, *in its specific regime*, on *real* levels. The map being all-`WATCH_ONLY` today means the architecture ships **without changing a single trade** — it is pure scaffolding until evidence promotes a slot. That is the propose-only contract made structural.

---

## 7. What this is NOT (honest boundaries)

- **Not wired live.** No heartbeat, params, or order path imports `regime_book`. `select_setups()` returns empty for every regime today (all `WATCH_ONLY`).
- **Not a claim the candidates are ready.** The seed map is **proxy-★★-level, mostly-DSR-WEAK, some low-power** evidence. These are *"worth a real-★★★ re-test"*, **not** *"trade them."* (`fleet-standalone-regime.json#op20_disclosures#not_a_promotion`.)
- **Not a replacement for the setups' own gates.** The regime layer gates **eligibility**; each setup's filters/gates still gate **firing**. It can only ever *forbid* an off-regime setup, never *admit* one that fails its own checks.
- **Not a finished classifier.** `classify_regime` is a coarse, lean, $0 5-way tag. It is intentionally crude; the interface is stable so a better classifier can replace the internals later.
- **Not GEX-dependent.** GEX is a live-only optional corroborator; the classifier is fully backtestable without it.

---

## 8. Files

| File | Role |
|---|---|
| `markdown/research/REGIME-AWARE-BOOK.md` | This design doc. |
| `backtest/lib/engine/regime_book.py` | The lean scaffold: `classify_regime()`, `REGIME_SETUP_MAP`, `select_setups()`, the `Regime` / `PromotionStatus` / `SetupSlot` / `Evidence` records. Pure, no I/O, not wired live. |
| `backtest/tests/test_regime_book.py` | Pure unit tests: every classification path, precedence, the map is data-driven, the selector's `WATCH_ONLY` exclusion (the propose-only safety property), promotion-status filtering. |

**Next real step (not this task):** once the ★★★ archive banks ~20-30 days, re-run the in-regime standalone real-fills eval **on real levels**, file per-regime A/B scorecards, and promote any slot that clears the §6.1 bar — a data edit, not a rebuild.
