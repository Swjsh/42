# J-Entry-Quality — "Make Better Entries" (reconstruct his read, separate good from bad, ship the filter)

> **Generated:** 2026-06-20 · **Author:** Gamma (autonomous research) · **Status:** analysis + propose-only (J decides any live flip)
> **Numbers:** [`analysis/recommendations/j-entry-quality.json`](../analysis/recommendations/j-entry-quality.json) (OUR-data validation) · [`analysis/webull-j-trades/entry_quality.json`](../analysis/webull-j-trades/entry_quality.json) (his-data discriminators)
> **Scripts:** [`backtest/autoresearch/webull_entry_quality.py`](../backtest/autoresearch/webull_entry_quality.py) (his entry reads + discriminators) · [`backtest/autoresearch/j_entry_quality_validate.py`](../backtest/autoresearch/j_entry_quality_validate.py) (OUR-data A/B) — both pure Python, $0, py_compile clean
> **Companion (the HOLD):** [`markdown/specs/EXIT-DISCIPLINE-SPEC.md`](EXIT-DISCIPLINE-SPEC.md) — proves the engine's mechanical hold survives the pokes that shook J out. This spec does the **entry** half: *which trades to take in the first place.*

---

## 0. The question, and the answer

J: *"see what I was theorizing when I got in and make better entries as well as build the discipline."*

We proved the HOLD on his losers (companion spec): **68% of his losers were the RIGHT thesis** — he capitulated on a temporary poke right before the reversal he was right about. That leaves the other side of the coin: the **~32% that were genuinely BAD entries** (wrong read, went against him and stayed) — plus the question of whether his good entries could have been *better-timed*. This is that analysis.

**The headline, on his 655 real Webull round-trips (2021-2023, SPX/SPY family, full population — winners AND losers):**

| Finding | Number |
|---|---|
| Entries where his READ was right (GOOD-thesis) | **383 / 655 = 58.5%** — these won **71.5%** of the time |
| Entries where his READ was wrong (BAD-thesis: went against him and stayed) | **272 / 655 = 41.5%** — these won **14.3%** of the time |
| **The #1 thing separating his good from bad entries** | **Did the 5m entry bar CLOSE in his direction?** Confirmed-close → **56.6% WR**; entered into an unconfirmed/counter bar → **33.2% WR** (a **+23.4pp** swing) |
| **#2 separator** | **VWAP alignment** (the known leak): aligned **52.4% WR / −$8.8 avg**; counter-VWAP **36.6% WR / −$44 avg** |
| **The poke is the tell of a bad read** | BAD-thesis entries poke a median **0.91 SPY pts** adverse in the first 20 min (≈ −20% premium EST); GOOD-thesis entries poke only **0.31 pts** (≈ −8% EST). A wrong read goes offside ~3x harder, immediately. |

**The single best better-entry rule — "wait for the 5m bar to CLOSE in your direction before entering" — is already RATIFIED and LIVE on the Safe account for the bear side** ([`safe_entry_body_gate.json`](../analysis/recommendations/safe_entry_body_gate.json), 2026-06-18, WF=7.19, OOS +$566). J's 2021-23 data independently re-derives the *same* rule as his #1 entry discriminator. That cross-era agreement is the strongest validation we can get. The net-new proposal below is extending it to the **bull** side.

> **Honesty contract.** His **behaviour is EXACT** (his real entry/exit fills, qty, P&L). The **"theory"/read at each entry is INFERRED** look-ahead-free from the SPY 5m tape — Webull records the trade, not the thought; every read is a reconstruction. The **GOOD/BAD-thesis label is EXACT direction** (the SPY underlying continued his way after entry, SPX/SPY ~10:1). The **premium-MAE "poke" is an ESTIMATE** (Black-Scholes, IV implied from his own entry fill); the **underlying-points poke is EXACT**. OUR-data validation uses **real OPRA fills**, causal, full bar.

---

## 1. PART A — what J was theorizing at entry (the read distribution, INFERRED)

Reconstructed at his entry bar from the tape (no notes). What he was actually trading:

**Trigger he was acting on** (n=655):

| Trigger (inferred) | n | share | WR | avg P&L | good-thesis% |
|---|---|---|---|---|---|
| breakout (fresh session extreme his way) | 254 | 39% | 52.8% | −$13.6 | 61.0% |
| pullback (with-VWAP re-entry) | 229 | 35% | 50.7% | −$7.4 | 60.7% |
| **reclaim (crossed to his side counter to prior — counter-VWAP)** | **171** | **26%** | **36.8%** | **−$42.7** | **51.5%** |

**Time of day** (entry): front-loaded — 09:30 bucket 162, 10:00 bucket 133, 10:30 bucket 82. ~58% of his entries are before 11:00. (His morning entries are NOT cleaner than his afternoon ones — see §2; the morning skew is volume, not edge.)

**VWAP relation at entry:** 464 aligned (71%) vs 191 counter-VWAP (29%). He mostly traded with the side price was on — his dominant good instinct.

**Read in one sentence:** *J was a momentum-and-pullback trader who entered early in the session, mostly on the side of VWAP — and his edge leak was the 26% of entries where he reclaimed AGAINST VWAP (the counter-trend "it's turning here" entry), which won only 37% and bled −$43 each.*

---

## 2. PART B — the entry-quality discriminator (good read vs bad read, RANKED)

GOOD-thesis = the underlying continued his way **meaningfully** (≥0.25% of spot ≈ $1 on SPY) after entry — the read was right regardless of whether his exit captured it (= all winners + the 68% right-thesis "stopped then printed" losers). BAD-thesis = no meaningful favorable move AND it closed against him (read was wrong).

**Discriminators, ranked by how cleanly they separate GOOD from BAD entries (separation + WR-lift, support-weighted):**

| Rank | TAKE-filter | TAKE n / WR / avgP$ | AVOID n / WR / avgP$ | WR-lift | Reads as |
|---|---|---|---|---|---|
| **1** | **confirmed_close** (entry 5m bar closes his way) | 408 / **56.6%** / **+8.7** | 247 / 33.2% / **−65.0** | **+23.4pp** | The dominant, clean one. The AVOID side bleeds −$65/trade. |
| **2** | **aligned & confirmed_close** | 324 / **59.3%** / **+13.7** | 331 / 36.6% / −51.2 | +22.7pp | Stack the top two → 59% WR and *positive* avg P&L. |
| **3** | **not_reclaim** (drop counter-VWAP reclaims) | 484 / 51.7% / −10.7 | 171 / 36.8% / −42.7 | +14.9pp | Removing his counter-VWAP leak. |
| **4** | **vwap_aligned** | 464 / 52.4% / −8.8 | 191 / 36.6% / −44.0 | +15.8pp | The known leak, quantified. |
| 5 | aligned & near-VWAP (≤25bp) | 249 / 53.0% / −9.3 | 406 / 44.6% / −25.1 | +8.4pp | Marginally better than alignment alone. |
| 6 | morning (<11:00) | 377 / 49.1% / −25.4 | 278 / 46.0% / −10.5 | +3.1pp | Weak. Morning is volume, not edge. |
| — | **not_stretched (run<2.5×ATR)** | 470 / 45.3% / −26.2 | 185 / **54.1%** / −1.0 | **−8.8pp** | **INVERTED — see below.** |
| — | **not_chasing_open (ext<0.5%)** | 454 / 44.9% / −28.9 | 201 / **54.2%** / +3.0 | **−9.3pp** | **INVERTED — see below.** |

### 2a. The "don't chase" hypothesis does NOT hold for J — and that's a real finding

The task hypothesized that chasing an extended move (far from VWAP/open) is a mean-revert risk. **On J's data the opposite is true:** his *stretched / chasing* entries won MORE (54% vs 45%), and the continuous contrast agrees — GOOD and BAD entries had nearly identical extension-from-open (medians both ≈0.23%). **Why:** J's dominant good thesis is *momentum continuation* — when price is extended past VWAP in his direction, that's a strong trend (the thing to ride), not a reversal setup. "Don't chase" would have cut his trend-continuation winners. **So extension/chasing is NOT a usable AVOID filter for his style.** (It may still matter for mean-reversion setups, which J did not predominantly trade.)

### 2b. The poke IS the signature of a bad read (the entries↔hold link)

This is the bridge to the companion HOLD spec. Immediate adverse excursion (first 20 min post-entry), GOOD vs BAD thesis:

| | median MAE (SPY pts, EXACT) | median MAE (premium %, EST) |
|---|---|---|
| **GOOD-thesis entries** | **0.31 pts** | **−8%** |
| **BAD-thesis entries** | **0.91 pts** | **−20%** |

A wrong read goes offside ~3x harder, immediately. **Implication:** the engine's mechanical hold (which the companion spec proves survives a ~−23% premium dip) is *safe to apply to GOOD-thesis entries* — they only dip ~−8% — but it should NOT be asked to sit through a BAD-thesis entry's ~−20% first-poke. The entry filter's job is to keep the engine out of the −20% pokes; the hold's job is to sit through the −8% ones. **Better entries make the hold easier.**

### 2c. Does entering a hair EARLY cause the poke? (the timing/confirmation finding)

Yes — directionally, but it is the *smaller* of two effects. Among **GOOD-thesis trades only** (read ultimately right), entering on an UNCONFIRMED bar pokes **0.325 pts** vs **0.292 pts** on a confirmed bar (+11% bigger poke; premium −8.5% vs −7.9% EST). So entering before the bar closes does buy you a slightly deeper adverse excursion even when you are right.

**But the bigger reason `confirmed_close` works (+23pp WR) is SELECTION, not poke-reduction:** confirmed-close entries are **61.3% good-thesis vs 53.8%** for unconfirmed. Waiting for the close mostly filters out *wrong reads*, and secondarily shrinks the poke on the right ones. Both effects point the same way: **wait for the 5m close.**

---

## 3. PART C — the BETTER-ENTRY rule set, validated on OUR 2025-26 data (real OPRA fills)

J's patterns are 2021-23. A rule only ships if it transfers to OUR engine on OUR SPY 0DTE real-fills data (2025-01..2026-06), causal, through the standard gate: **OOS-positive AND WF≥0.70 AND SW_hurt≤1 AND anchor-no-regression.**

| Rule | Type | His-data evidence | OUR-data verdict | Status |
|---|---|---|---|---|
| **Wait for confirming 5m close — BEAR side** (`entry_bar_body_pct_min=0.20`) | TIMING | #1 discriminator, +23pp WR | **Already RATIFIED + LIVE** (Safe, 2026-06-18): IS +$295, **OOS +$566**, WF=7.19, 5/5 gates pass | **SHIP — already live** |
| **Wait for confirming 5m close — BULL side** (`entry_bar_body_pct_min_bull=0.20`) | TIMING | confirmed_close helps both sides; `aligned&confirmed` is #2 | IS **+$2,683** (10 bad bull entries removed, +$268 each), 2/3 sub-windows up, anchor-safe — **but OOS −$1,240 on a single removed trade that won** (n=1 OOS, statistically meaningless) | **WATCH** (IS-validated, needs OOS depth) |
| **Trade WITH session VWAP / drop counter-VWAP reclaims** | TAKE/AVOID | #3–#4 discriminator, +15pp WR | Already shipped as a setup: [`vwap-trend-pullback-LIVE.json`](../analysis/recommendations/vwap-trend-pullback-LIVE.json) (SHIP-LIVE, WATCH_ONLY→heartbeat, regime-gated) | **SHIP — already live (as the VWAP-pullback detector)** |
| **Don't chase extension** | AVOID | **FAILED on his data** (inverted: chasing won more) | not tested (no his-data support to carry forward) | **REJECTED** (do not implement) |
| **Prefer morning entries** | TAKE | weak (+3pp) | not promoted | **WATCH/low-priority** |
| **Enter at a level vs mid-air** | TAKE | **metric degenerate** (round-dollar always "near") — undecidable as built | n/a | **INCONCLUSIVE** (needs a real named-level feed to test) |

### 3a. The keystone: confirmed-close is cross-era validated

The rule that best separates J's good entries from his bad ones (2021-23) is the *same* rule already proven to improve our live engine (2025-26). On the Safe book the bear-side gate removed 4 OOS trades that **all lost** (avg −$141). That is two independent datasets, four years apart, agreeing that **entering before a 5m bar closes in your direction is a −EV habit.** This is the highest-confidence better-entry finding.

### 3b. The bull-side extension: real candidate, not yet shippable (honest)

Extending confirmed-close to the bull side is **strongly IS-positive (+$2,683, +$268 per removed bad entry) and sub-window-stable**, but the OOS window (May–Jun 2026) contained only **one** bull doji-entry to remove, and it happened to win — so OOS is −$1,240 on n=1. That fails the OOS gate on noise, not on signal. **Do not ship yet; accumulate OOS bull doji-entry instances and re-test.** The mechanism (a doji/wick bull entry = no conviction) is identical to the proven bear case, so this is a high-prior WATCH, not a dead end.

### 3c. What does NOT transfer (the honesty the task demanded)

- **"Don't chase / avoid extension" is a foot-gun for J's style.** It inverts on his data because he's a momentum trader. Carrying it into the engine would cut trend-continuation winners. Rejected.
- **The aggressive (Bold/ITM) book rejected the entry-body gate entirely** ([`agg_entry_body_gate.json`](../analysis/recommendations/agg_entry_body_gate.json): IS delta negative). Per L29, exit/entry knobs proven on one strike tier (Safe/OTM-2) **do not transfer** to another (Bold/ITM-2) without independent A/B. The confirmed-close rule is a **Safe-book** rule.

---

## 4. Proposed wiring (propose-only — J flips, not Gamma)

1. **(Already live, no action)** Bear-side confirmed-close: `entry_bar_body_pct_min=0.20` on Safe. Documented here for completeness as the validated keystone.
2. **(PROPOSE → WATCH)** Bull-side confirmed-close: `entry_bar_body_pct_min_bull=0.20`. Knob is fully wired in `orchestrator.py` (line 1602) + `lib/engine/gates.py` (SKIP_DOJI_ENTRY_BAR_BULL) with parity tests — flipping it is a one-line `params.json` change. **Hold until OOS depth exists** (currently n=1 OOS). Re-run `j_entry_quality_validate.py` after ~10+ bull doji-entry OOS instances accrue; ship if OOS turns positive with the other gates holding.
3. **(Already live)** VWAP-continuation / drop-counter-VWAP: served by the live `vwap_trend_pullback` detector. J's data is corroborating evidence that this is his real edge, not just an engine artifact.
4. **The entry-quality take-filter composes with the VWAP-continuation detector:** `confirmed_close` is orthogonal to (and stacks with) VWAP alignment — on his data `aligned & confirmed_close` is the cleanest cell (59.3% WR, +$13.7 avg, the only *positive*-expectancy filter). The wiring already reflects this: VWAP-pullback selects the setup; the entry-body gate sharpens the entry bar within it.

---

## 5. Reproduce

```bash
# his entry reads + GOOD/BAD discriminators (writes analysis/webull-j-trades/entry_quality.json)
backtest/.venv/Scripts/python.exe backtest/autoresearch/webull_entry_quality.py

# OUR-data A/B of the carried-forward rules (writes analysis/recommendations/j-entry-quality.json)
backtest/.venv/Scripts/python.exe backtest/autoresearch/j_entry_quality_validate.py
```

Both reuse the existing bar caches (`winner_bar_cache.json` + `loser_bar_cache.json`, 214/214 dates covered) and the canonical look-ahead-free entry-read extractor (`webull_daily_pattern_miner.extract_features`). No engine code touched — pure analysis + propose-only.
