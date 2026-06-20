<!-- Filed by Gamma (interactive session 2026-06-14). NOT RATIFIED — Rule 9 review required before any production change. -->
<!-- Source: J-supplied Reddit post (r/FuturesTradingNQ, "I've been paid $95,336 from prop firms trading NQ") + follow-up ERL→IRL trade recap. -->
<!-- Surfaces touched: strategy/candidates/ ONLY. No params*.json, no heartbeat*.md, no order placement. -->

# CANDIDATE: REDDIT_ORB15_AND_ERL_IRL_FVG

**Filed:** 2026-06-14
**Filer:** Gamma (interactive, J-directed)
**Type:** (1) parameter variant of a deployed watcher + (2) new trade class (watch-only)
**Status:** BUILT + WIRED (WATCH-ONLY) + VALIDATED — **DO-NOT-PROMOTE** (real-fills FAIL). See §8.
**Source:** External (NQ/ES futures trader). Translation to SPY 0DTE options is non-trivial — see §0.

---

## 0. Honest framing before anything else

The post describes **two NQ/ES futures setups**. Two structural facts gate every adoption decision below:

1. **Linear vs non-linear.** NQ is linear: 1 tick = $5, delta is constant, a 165-point move is a 165-point move whether it takes 5 minutes or 5 hours. SPY 0DTE options are non-linear — delta < 1, theta bleeds the whole hold, and our own evidence (L51, L55, L74) shows that price-space edge does **not** survive translation to option P&L without real-fills validation. **No claim in this doc is "validated" until it clears the real-fills gate (OP-16 sim-accuracy + OP-20 disclosure 4).**

2. **Hold time.** The author's flagship ERL→IRL example was held **5h 26m** for a +165pt swing with $1.47 max drawdown. On a futures contract that's a clean swing. On a 0DTE SPY option, a 5-hour hold is the *worst case* for theta — by mid-afternoon the contract is decaying fast and we are flat by 15:50 ET regardless (Rule: all flat by EOD). So we adopt the **entry mechanic**, never the swing-hold timeframe.

The good news: neither setup is alien to Gamma. One is already deployed; the other is ~70% built from existing primitives.

---

## 1. Strategy A — "15-Minute ORB" → variant of the EXISTING `orb_watcher.py`

### What the post does
Take the high/low of the **first 15 minutes** (09:30–09:45 ET), trade the breakout of that range for "opening momentum," hard stop, target a measured move.

### What we already have
`backtest/lib/watchers/orb_watcher.py` is **production** (leaderboard #4 `ORB_NARROW_OR_GATE` + #5 `ORB_DIRECTION_FILTER`). It is a full breakout→retest→entry state machine. Differences vs the post:

| Dimension | Gamma `orb_watcher.py` | Reddit "15-min ORB" | Adoptable delta |
|---|---|---|---|
| Opening-range window | **30 min** (`OR_START 09:30` → `OR_END 10:00`) | **15 min** (09:30–09:45) | Test 15-min OR as a parameter |
| Entry trigger | Break → **wait for retest** → retest-held green bar | "Opening momentum" (break; retest optional) | Test break-entry vs retest-entry timing |
| Direction | long-only (`ORB_DIRECTION_FILTER="long"`, evidence-backed) | both | Keep long-only unless 15-min window changes the short edge |
| OR-range quality gate | `MAX_OR_RANGE=2.00` (narrow-OR only, WF Sharpe 1.149) | none | Re-fit the gate threshold for a 15-min window (range scales down) |

**The adoption is therefore NOT a new watcher.** It is a **parameterization experiment** on a watcher we already trust, exactly the kind of sweep the Kitchen runs (cf. `2026-06-07-…-orb-narrow-or-gate-param-sweep.md`).

### Concrete change (R&D only)
Add `OR_WINDOW_MINUTES` (default 30) to `compute_opening_range()` so `OR_END` is derived, not hardcoded. Then grind **{15, 30} × {break-entry, retest-entry} × MAX_OR_RANGE∈{1.0,1.25,1.5,2.0}** through the Stage-1→Stage-5 pipeline. The narrower 15-min window produces a tighter range, so `MAX_OR_RANGE` must be re-fit (a 2.00 cap calibrated on 30-min ranges is too loose for 15-min ranges).

### Hypothesis worth the compute
The author's whole thesis is that the *earlier* you capture the opening drive, the cleaner it is. Gamma's ORB enters late (post-10:00, after a 30-min range + retest). A 15-min window with optional break-entry would fire **15–40 min earlier** — which is when theta is least punishing on a 0DTE call. If the 15-min variant holds WR within a few points of the 30-min while entering earlier, it strictly improves the option-P&L profile even at equal price-space WR. That is the falsifiable claim to test.

### Risk-philosophy mapping (already covered — log only)
Post-1's discipline ("small size, hard stops, take the loss, don't double down, don't catch a falling knife, 1–2 trades a day") is **already encoded** in Rules 3, 4, 5, 6, the "no second entry after a stop-out" refusal, and L51/L55 (don't fade the violent first bounce). The one idea *not* fully encoded is **daily selectivity** ("my best months I take 1–2 trades"). Gamma fires up to 127 ticks/day; the author's edge is in *not* trading. That maps to tightening the ELITE-tier gate, **but that touches heartbeat selectivity = forbidden surface for me to change → J-ratification item, noted not shipped.**

---

## 2. Strategy B — "ERL → IRL" → new watch-only watcher built mostly from existing primitives

### What the post does (ICT vocabulary)
- **ERL** = External Range Liquidity = liquidity resting beyond swing highs/lows / prior-day H/L. Price **sweeps** a key low (runs the stops below it).
- **Displacement** = a strong move off the sweep that leaves a **Fair Value Gap (FVG)** = a 3-candle imbalance (candle-1 high and candle-3 low don't overlap on a bullish FVG).
- **IRL** = Internal Range Liquidity = that FVG. Price retraces **into the FVG**, and you enter there.
- **Target** = the opposite **external** liquidity (buyside high).

So: **sweep external low → displace up → enter on the FVG retrace → target the external high.**

### What we already have (≈70%)
- **ERL sweep:** `filters.py::detect_level_sweep()` (line ~344) is exactly the wick-through-close-back pattern, with `clean_prior_bars` confirmation. Mirrors `crypto/lib/sweep.py`.
- **External levels:** Gamma's named key levels (PDH/PDL, Carry, ★-rated S/R) ARE the ERL pool. `BarContext.levels_active` already carries them.
- **Reclaim / sequence logic:** `detect_level_reclaim()` and `detect_sequence_rejection()` already model "swept then reclaimed."
- **Anchor overlap:** J's two best anchor wins (4/29, 5/04) are described as "ribbon-flip-at-level" entries — conceptually a sweep/reclaim at a key level. ERL→IRL is a **more precise entry trigger** for the same family of edge.

### The genuinely NEW primitive: a Fair Value Gap detector
Grep confirms **no FVG implementation exists** (only doc mentions in `FUTURE-IMPROVEMENTS.md`/`docs/`). This is the one new, well-defined, fully-computable thing to build:

```
detect_fvg(prior_bars, idx, direction, min_gap_dollars) -> Optional[FVG]
  bullish FVG at bar i:  low[i]  > high[i-2]      (gap = low[i] - high[i-2])
  bearish FVG at bar i:  high[i] < low[i-2]       (gap = low[i-2] - high[i])
  require gap >= min_gap_dollars  (displacement strength filter)
  return zone = (gap_bottom, gap_top) as the IRL entry band
```

Then a watch-only `erl_irl_watcher.py` composes the existing pieces:

1. **ERL sweep** of a `levels_active` external low (use `detect_level_sweep(direction="bullish")`).
2. **Displacement** off the sweep that prints an FVG (`detect_fvg`), gap ≥ threshold.
3. **IRL entry** when a later bar retraces into the FVG zone and holds (analogous to the ORB retest-held confirmation already in `orb_watcher.py`).
4. **Target** = next external `levels_active` high (buyside). **Stop** = below the swept low (chart stop).
5. Emit a `WatcherSignal` (`setup_name="ERL_IRL_SWEEP_FVG"`), **WATCH-ONLY**, per OP-21 (`promotion_status="WATCH_ONLY"`, `op21_live_confirmed=0/3`).

### Non-negotiable 0DTE adaptations (this is where futures edge dies if ignored)
- **Intraday-compressed only.** Use 5-min/15-min FVGs inside the session, never the 30-min weekly-swing version. The author himself says "some days it's a 5-minute scalp" — that's the version 0DTE can hold.
- **ITM strikes + chart-stop only.** Multi-hour or even multi-bar holds toward "the next external level" will get chopped by theta and premium-stop misfires at ATM. This is precisely L74 (ATM 0DTE fails: delta half-capture + theta drag + −15% stop misfire on retest wicks) → **ITM-2 rescue + larger absolute stop**, and L51/L55 (premium stops incompatible with first-bounce-at-level → `premium_stop=-0.99`, chart-stop governs).
- **Regime-gated.** L73/L74: this family of edge fires in **trending, high-vol** regimes, not chop. Expect a VIX-character gate (VIX ≥ threshold AND escalating vs 5-day avg) to be part of the final config, mirroring SNIPER #14/#15.

---

## 3. What we explicitly do NOT adopt

- **The 5-hour swing hold** — theta-incompatible with 0DTE (§0.2).
- **Linear R:R math** — the post's "141 pts risk / 229 pts reward = 1.16R" is contract math; option R:R must be measured in *premium* via real-fills, not price.
- **MNQ contract sizing / "$327 × 4 accounts"** — irrelevant; our sizing is Rules 6 + the v13b tiers.
- **Both-direction ORB** — our evidence already says long-only ORB; don't reintroduce wide-short drag without re-proving it on the 15-min window.

---

## 4. Validation plan (gates BEFORE anything approaches `params.json`)

Follows `markdown/research/BACKTESTING-PLAYBOOK.md` 5-stage grinder + the OP-16/OP-20/OP-21 stack.

1. **Stage 1 (price-space scan):** Backfill both setups over the 16-month SPY 5m archive. ORB-15 vs ORB-30 head-to-head; ERL→IRL frequency + price-space WR.
2. **Stage 2–3 (real-fills, MANDATORY):** Re-price every signal through `option_pricing_real.py` / `simulator_real.py` (NOT BS-sim — L71). ATM **and** ITM-2 variants for ERL→IRL. Gate: WR and expectancy positive on real fills, not price.
3. **OP-16 anchor preservation:** Replay the 7 source-of-truth days. New logic must NOT degrade the 3 winners (4/29, 5/01, 5/04) and must NOT newly enter the 4 losers (5/05, 5/06, 5/07). `edge_capture ≥ 771` or the candidate is rejected at the door. (ORB-15 is a variant of a setup that already passes; ERL→IRL is a new class — guard-check it fires 0× on the loser days.)
4. **OOS walk-forward:** OOS/IS Sharpe ratio ≥ 0.50, sub-window stable. Watch for the single-quarter concentration that flagged ORB-narrow (Q2-2026) and SNIPER (Q1-2026).
5. **OP-21 watch-first:** Ship both as **watch-only** observers writing to `watcher-observations.jsonl`. Promotion needs N≥15 historical + walk-forward + real-fills + **3 live J-confirmed wins** before any heartbeat wiring (Rule 9).

### OP-20 disclosures (pre-filled)
1. **Account-size:** contract counts assume tier sizing; $1K paper ≈ 3-contract floor.
2. **Sample bias:** ERL→IRL depends on named-level archive quality; historical key-levels are sparse pre-2026 (same limitation that blocked BEARISH_REJECTION_MORNING #20 and CLOSE_CEILING #L59).
3. **OOS:** needs held-out window; small-N FVG events risk overfit.
4. **Real-fills:** ATM expected to FAIL for ERL→IRL (L74 analog) → ITM-2 is the likely production config.
5. **Failure modes:** worst case = FVG entries during chop (no displacement follow-through) → death by a thousand premium-stop cuts. Regime gate is the mitigation.
6. **Concentration:** flag if top-5 days > 40% of P&L.

---

## 5. Recommended next actions (Kitchen cook tasks — exact commands)

```bash
# A. ORB 15-min vs 30-min window + entry-timing sweep (variant of deployed watcher)
python setup/scripts/kitchen_daemon.py enqueue \
  --task "Add OR_WINDOW_MINUTES param to orb_watcher.compute_opening_range (default 30, no prod change); Stage-1 grind 15min vs 30min OR window x {break-entry,retest-entry} x MAX_OR_RANGE{1.0,1.25,1.5,2.0}, long-only; report WR/expectancy + entry-time delta + OP-16 anchor preservation" \
  --priority high --source claude

# B. FVG detector primitive (pure function, unit-testable, no order path)
python setup/scripts/kitchen_daemon.py enqueue \
  --task "Implement detect_fvg(prior_bars, idx, direction, min_gap_dollars) in backtest/lib/filters.py: bullish low[i]>high[i-2], bearish high[i]<low[i-2], min-gap displacement filter; add 8 unit tests to test_filters.py" \
  --priority high --source claude

# C. ERL->IRL watch-only watcher, intraday-compressed, ITM-2 + chart-stop
python setup/scripts/kitchen_daemon.py enqueue \
  --task "Build erl_irl_watcher.py WATCH-ONLY: detect_level_sweep(bullish) on levels_active low -> detect_fvg displacement -> FVG-retrace-held entry -> target next external high; Stage-1 scan + real-fills ATM vs ITM-2; premium_stop=-0.99 chart-stop only (L51/L55/L74); VIX-character gate per L73; OP-16 loser-day guard must be 0 fires" \
  --priority high --source claude
```

(If J prefers I scaffold the `detect_fvg` function + `erl_irl_watcher.py` skeleton directly in this session instead of via the Kitchen, that's also a clean watch-only/engine-benefit change — say the word.)

---

## 6. Guardrail compliance

- Touches **`strategy/candidates/` only**. No `params*.json`, no `heartbeat*.md`, no order placement.
- ERL→IRL ships **watch-only** (OP-21); ORB-15 is an R&D variant of a deployed watcher behind a defaulted-off param.
- Daily-selectivity idea (§1) flagged as a **J-only** heartbeat change, not shipped.
- Real-fills + OP-16 anchor preservation are hard pre-merge gates (OP-16 sim-accuracy gate, L74 ATM-fail precedent).

## 7. Confidence

**ORB-15 variant: 7/10** — refines a watcher that already passes OOS + real-fills; downside is bounded, upside (earlier entry = less theta) is plausible and testable.
**ERL→IRL: 5/10** — the FVG primitive is sound and the sweep half already exists, but the multi-hour-hold heritage is the exact profile that L74 shows fails at ATM; viability hinges entirely on the ITM-2 + regime-gated real-fills result. Genuinely novel for us either way (first FVG/IRL machinery in the codebase).

---

## 8. BUILD + VALIDATION RESULTS (2026-06-14) — everything ran; verdict is DO-NOT-PROMOTE

**What shipped (code complete, tested, wired WATCH-ONLY into the live fleet):**

- `backtest/lib/filters.py` — `FVG` dataclass + `detect_fvg()` (first FVG/IRL primitive in the codebase). 6 unit tests in `test_filters.py` (all pass; 31/31 filter suite green).
- `backtest/lib/watchers/orb15_watcher.py` — self-contained 15-min ORB (break + retest modes, long-only, narrow-OR gate). Deployed 30-min `orb_watcher.py` untouched (zero production risk).
- `backtest/lib/watchers/erl_irl_watcher.py` — ERL sweep → FVG displacement → retrace entry → next-external target. Intraday-compressed, ITM-2 + chart-stop (premium_stop=-0.99).
- Registered in `lib/watchers/runner.py` + `__init__.py` as **WATCH-ONLY** (observation only, no order path). `run_all_watchers` imports clean; 60/60 functional tests green (`test_filters`, `test_reddit_watchers`, `test_new_watchers_smoke`, `test_simulator`, `test_ribbon`).
- Validation harness: `backtest/autoresearch/validate_reddit_watchers.py`. Full results: `analysis/recommendations/reddit-watchers-validation.json`.

**Stage-1 — 16-month SPY-space scan (2025-01-01 → 2026-05-22), deduped per L67:**

| Stream | N (deduped) | WR | exp $/contract | total $ | verdict |
|---|---:|---:|---:|---:|---|
| ORB15_break | 96 | 42.7% | **−0.75** | −71.54 | net negative |
| ORB15_retest | 63 | 49.2% | **−2.37** | −149.01 | net negative |
| ERL_IRL | 329 | 69.3% | **+0.38** | +126.44 | marginal, regime-fragile (Q1-2026 −$729) |

**Real-fills (option P&L, Q2-2026 anchor quarter, capped N≤80/stream) — the decisive gate:**

| Stream | strike | N | WR | exp $/contract | total $ |
|---|---|---:|---:|---:|---:|
| ORB15_retest | ATM | 9 | 55.6% | +30.0 | +270 |
| ERL_IRL | ATM | 75 | 54.7% | **−25.4** | −1,903 |
| ERL_IRL | ITM-2 | 71 | 45.1% | **−58.7** | −4,166 |

**Findings (honest):**

1. **ERL→IRL fails real-fills decisively** — and ITM-2 is *worse* than ATM, the opposite of the L74 rescue. Root cause: the chart stop sits below the *swept low*, which the liquidity grab places far from entry, so the rare full-stop losses dwarf the many small wins. SPY-space WR 69% collapses to ~50% option WR (textbook L50). The post's edge does **not** survive translation to 0DTE under this exit structure. Needs a fundamentally different exit (tight fixed-$ stop or FVG-floor stop, target ≥ 2× risk) before it could work — that is a redesign, not a tune.
2. **ORB-15 is net-negative** over 16 months in SPY-space (both modes). The only positive signal is retest-mode real-fills in Q2-2026 (+$30/trade) but N=9 in the single most favorable regime — not promotable. The deployed 30-min ORB remains the better-evidenced variant.
3. **OP-16 anchor preservation FAILS** — ERL→IRL loses on 2 of 3 J winner days (4/29 −$99, 5/01 −$174) and *makes* money on 2 of 3 loser days. Edge-capture is poor; this is not J's edge.
4. **Selectivity gap** — ERL fires ~5×/day raw (1,884 over 16mo) vs the author's 1–2 trades/day. As-coded the detector is far looser than the post's "wait for the clean one" discipline.

**Verdict:** both setups are now first-class WATCH-ONLY citizens of the engine (they run every bar and log observations), but **neither clears the OP-21 real-fills gate or OP-16 anchor test, so neither is promoted to live order placement.** The build is complete and the validation is what gates them — exactly the eval-first contract (OP-11/OP-20).

## 9. The single remaining ratification gate (J-only, by design)

Live order placement was deliberately NOT wired — it is the one surface that alters live-order conditions (Rule 9 / OP-21 / the engine-benefit autonomy discriminator). Given the validation verdict, the correct next action is **not** to ratify but to either (a) leave them accumulating live watch-only observations, or (b) redesign ERL→IRL exits and re-validate. If a future variant *did* pass all gates, promotion would be a heartbeat.md edit behind J ratification + 3 live J-confirmed wins — never an autonomous flip.
