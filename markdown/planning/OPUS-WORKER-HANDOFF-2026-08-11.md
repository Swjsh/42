# OPUS-WORKER HANDOFF — engine work map (frozen 2026-08-11 night)

> For the next working session (Opus-tier judgment; mechanical fan-outs go to Sonnet per
> §1 routing). Read [TWO-WEEK-ENGINE-RETRO](../../analysis/deep-research/2026-08-11-audit/TWO-WEEK-ENGINE-RETRO.md)
> first — it is the evidence base for every priority below. Broker-realized P&L and the live
> decisions ledger are the only oracles; the exit-replay harness is admissible ONLY at
> calibration v5 (`extreme` fills + 1¢ slippage + full SPY union feed, bias −$7.4/pos, 95%
> sign) and ONLY after `harness_fidelity_anchor.py` passes on the question's population.

---

## 0. J's direct questions, answered honestly

**"The one-minute trades today — has that been fixed?" — NO.**
`ribbon_flip_back` still liquidates a whole position on a SINGLE flipped tick
(`exit_manager.py:555`: the confirmation buffer was "aspirational, never implemented"). On
08-11 it killed three profitable puts in 11 minutes (57–60s holds); the 771P it dumped at
0.54 printed 1.29 four hours later — we captured 10.7% of a move we caught at the exact
right minute. It is PARKED, not fixed, because it has fired only **5 times in ledger
history** — no backtest can validate a change; only a forward trial can. Spec in P2.

**"10 contracts at $50 — how does that scale to 20 with a bunch of runners?"**
Contract count already scales automatically: sizing is %-of-equity (Rule 6: 30%/50% caps),
so 2× equity ⇒ 2× contracts at identical risk. The four REAL constraints, in the order they
bind:
1. **Exit architecture** — `exit_manager` expresses exactly TWO tranches (`tp1_qty` +
   `runner_qty`). J's 10→5/3/2 laddered runners **cannot be expressed**. P3 build.
2. **Book-level correlation** — all 5 arms trade the same signal. Today's worst case is
   ~26–31 contracts in one strike cluster; at 2× sizing, a stop cascade market-sells 50–60
   contracts within seconds of each other. No book-level exposure cap exists. P4.
3. **Chop-day amplification** — sizing up multiplies −$2,687 days before it multiplies
   +$3,624 days. **Order of operations: regime filter (P1) lands BEFORE any size-up.**
4. **PDT at live-money time** — paper doesn't enforce; live <$25k margin = 3 day-trades/5bd
   against a book cadence of 5–10 round trips/day. Live requires ≥$25k per account or a
   cadence redesign. This is the structural gate between paper success and real money.
   And C31 stands: J's own 667-trade history says the killer is sizing UP mid-trade —
   scale-up preserves one-entry / laddered-exits / never-add (guard-pinned).

**Growth ladder:** $5k arm (now, 10 lots) → $10k (20 lots automatic; REQUIRES P3+P4 first
or 20 lots exit as a crude 13/7) → $25k+ (live-eligible; re-anchor the 1¢ slippage
assumption at size before trusting any projection).

---

## 1. Priority-ordered work map

### P0 — Diagnostics (Sonnet, hours)
- ~~safe-3 took zero trades 08-11~~ **ANSWERED same night:** safe-3's stricter quality gate
  (`1 triggers < 2` ×26, `requires confluence/sequence` ×11) correctly refused the day's
  single-trigger VWAP setups. Not a defect. The REAL finding underneath: **ribbon_ride fired
  ZERO entries book-wide on 08-11 — the entire book traded `vwap_continuation`.** Two
  consequences: (a) the ladder (ribbon-scoped, C29) never applied to most of the day, so
  08-11 is NOT ladder evidence; (b) the VWAP stop-widening clock in P6 governs the currently
  ACTIVE revenue path, upgrading its priority. New measured question: does safe-3's
  2-trigger gate earn its keep (its era P&L −$10/tr vs siblings' churn)?
- **`winner-autopsy-last.json` carries `date: None`** (partial-run signature) and the pain
  ledger silently skipped 08-01→08-10 before self-healing. Find the failing branch; add a
  loud STATUS line on partial runs (C7).
- **Remove `safe-1` from secrets.json** (dead key, 401s on every sweep). J rotates keys;
  the work order is removal + a creds-health line in the nightly brief.

### P1 — Regime discriminator, forward (the only lane touching the #1 loss driver)
SHADOW RUNNING: `Gamma_RegimeShadow` (16:35 ET nightly), prereg
`REGIME-CONDITIONAL-EXIT-2026-08-11`, threshold FROZEN at ER30=0.35.
- Origin window: low-ER days 1/8 green, −$2,336; ladder helps exactly those days (+$702)
  and hurts trend days (−$2,364) — one mechanism, two independent views.
- G1 forward 0/25 days; G5 auto-kill if >30% of forward low-ER days print green.
- Worker job: NOTHING until the clock fills. Then adjudicate against the frozen gates.
  Do not tune the threshold on the origin window (explicitly forbidden in the prereg).

### P2 — Ribbon-flip confirmation buffer (forward trial spec, ready to build)
- Change: pre-TP1 `ribbon_flip_back` requires **N=2 consecutive** flipped ticks (persisted
  per-position counter in ExitState, same additive-field pattern as the ladder ship).
  Post-TP1 unchanged. Per-arm flag, default OFF; arm ONE fleet arm.
- Inertness contract + RED-proofed guards mandatory (the ladder ship is the template).
- Forward kill criteria (pre-register before arming): any single give-back day where the
  delayed exit costs >$150 vs the single-tick counterfactual (loggable from the ledger),
  or 10 forward fires with net cost > $0.
- Why forward-only: 5 lifetime fires — there is no population to backtest.

### P3 — N-tranche exit architecture (the biggest engine build on the board)
- `ExitState`: replace the tp1/runner pair with `tranches: [[trigger_pct, qty_fraction],…]`
  + a back-compat shim that maps today's shape to 2 tranches **byte-identically**
  (inertness guard, RED-proof by shim removal).
- `exit_actuator`: SELL_PARTIAL per tranche, per-tranche dupe-guard, versioned
  to_dict/from_dict (state files survive restarts mid-position).
- Study FIRST, build SECOND: the multi-leg walker (`multileg_exit_walk.py`) already models
  partials — run J's 5/3/2 shapes vs current on the anchored population at calibration v5,
  prereg frozen before the runner. Ship only what the study + a forward arm trial support.

### P4 — Book-level exposure cap (prerequisite to ANY size-up)
- Compute cross-arm same-direction exposure at plan time (sum of open+planned contracts ×
  premium across arms); refuse entries that push the book past a cap (start: 2× today's
  worst case). Refuse-only — never sizes up, never widens. Guards + one-line revert.

### P5 — The PRE-FLIGHT CARD (J: "Gamma needs to be like a person")
One JSON snapshot logged per entry decision, AT decision time — the 12-item checklist:
sizing math, kill-switch state, PDT budget, VIX level+trend, key-level proximity (zones),
multi-timeframe read (15m/1h/4h/daily), news calendar (CPI/FOMC/NFP), regime (ER30-so-far),
time-of-day, spread/liquidity check, recency verdict, book exposure.
- **Phase 1 = LOG ONLY.** No gating. It builds the dataset that converts "should Gamma
  check the 4-hour?" from a vibe into a measurable per-factor edge question.
- Phase 2 = factors graduate to gates one at a time, each through its own prereg.
- The gap map below shows which items already exist on the live path vs need wiring.

### P6 — Clocks that fire on their own (no work until they do)
| clock | fires | action licensed |
|---|---|---|
| risky-3 stop_mode | day 20 (now 2/20) | revert premium→structure if expectancy still negative & below risky-1 |
| VWAP stop widening | fill-day 8 (now 4/8) | widen −6% → structure/−50% on ONE arm, new prereg |
| Ladder verdict | rolling | winner_autopsy nightly ladder-vs-actual; regime split per P1 |

---

## 2. Checklist gap map (evidence-based)

Full file:line audit: [GAMMA-CHECKLIST-GAP-MAP.md](../../analysis/deep-research/2026-08-11-audit/GAMMA-CHECKLIST-GAP-MAP.md)
(traced `heartbeat_core → engine_cli → score/gates → risk_gate` + fleet path).

**Scorecard: 3 WIRED-LIVE · 7 PARTIALLY WIRED · 2 ABSENT** of J's 12 checklist items.

| status | items |
|---|---|
| ✅ WIRED-LIVE | risk sizing · daily kill switch · time-of-day gates |
| 🟡 PARTIAL | VIX (level only, not character) · key levels (point prices, zone logic unverified downstream) · trend/regime (see below) · spread/premium floor · PDT · recency gating · multi-timeframe |
| ❌ ABSENT | **news/economic calendar** (built for the retired LLM heartbeat, never ported — zero matches in heartbeat_core; in the KNOWN_DEAD registry) · **book-level exposure across arms** (risk_gate.check_order has no cross-account term; one signal fans to 6 arms uncapped — confirms P4) |

**The finding that reframes P5:** the multi-timeframe/regime machinery J asked for *already
exists* — `context_bundle_producer.py` computes the daily/hourly/15m trend-alignment bundle on
schedule, and `market_structure.py` carries full BOS/CHoCH — but both are **logged-only**:
"nothing on the score/gates path reads it," by its own docstring. Only a narrow
`classify_trend()` binary veto is live, and it explicitly does NOT fire on chop ("range /
unknown ⇒ NO veto") — which is mechanically the same hole as the 113-tick blind window and
the chop-day losses. **P5 Phase 1 is therefore cheaper than drafted: the card mostly wires
EXISTING producers into one at-decision snapshot rather than building new sensors.**
Honest caveat carried from the audit: item 5's zone-vs-price verdict is partially unverified
(filters.py touch-tolerance not traced) — flagged, not guessed.

## 3. Repo hygiene work orders

Full inventory: [STALE-INVENTORY.md](../../analysis/deep-research/2026-08-11-audit/STALE-INVENTORY.md).
Executed same night: 10-file scratch cluster deleted (spot-checked, tracked = revertible);
3 doctrine corrections applied (decayed 92/100 figure per L291; VWAP "−6% validated" banner-
corrected against n=126 broker truth; HARNESS-CALIBRATION v4 headline superseded-pointer to v5).

Remaining orders for a Sonnet worker:
- **28 delete-candidates** (22 in `backtest/tools/`, 6 in `setup/scripts/`) — agent-verified
  zero-reference but only the cluster was independently spot-checked. Verify per-file
  (grep + SCHEDULED-TASKS.md + .ps1), then pathspec-scoped delete. Never delete untracked files.
- **`analysis/recommendations/` retention** — 833 files, 3 months, no consolidation ever
  (OP-22 breach by drift). Design a cap: fold superseded scorecards into per-topic living
  verdicts; the ledger index (`recommendations-log.jsonl`) stays canonical.
- **`sampling-gap.json`** 9 days stale, cadence unconfirmed — determine one-time vs nightly.
- 3 ARCHIVE-CANDIDATEs per the inventory's §1 table.

---

## 4. Standing methodology (non-negotiable for any worker session)
1. **Anchor before you simulate**: no exit study is admissible until
   `harness_fidelity_anchor.py` reproduces broker truth on that population. Three confident
   wrong answers this week came from skipping exactly this.
2. **Prereg before runner**, kill criteria included, committed (git-provable). The preregs
   blocked two premature ships this week — that is them working.
3. **Broker truth > live ledger > calibrated harness > everything else.** One day is never
   evidence (08-04 is 100%+ of the config's net; drop-best before believing anything).
4. Commit via `setup/scripts/commit_scoped.py`; never bare `git commit`; never push 09:30–15:55 ET.
5. Workers report deltas + evidence, TLDR-style; UNVERIFIED stays labeled.

---

## P7 — Exit-Supervisor shadow (J directive 2026-08-11 evening: "use Opus at entry to evaluate everything")

Evidence forcing this lane: THREE independent same-harness measurements now agree the exit lever
is DAY TYPE, not shape values — ribbon ladder net +$224/23d (wash, +chop/-trend split),
VWAP ladder **NO-SHIP all gates** (-$411, 100% on the 08-04 trend day; never arms on chop),
ER30 origin split. Any FIXED shape loses somewhere. J's instinct ("each trade needs to be
dynamic; the Python engine may not see the big picture") matches the data.

**Architecture — judgment PLANS, determinism EXECUTES** (respects the retired-LLM-heartbeat scar,
market-hours Max-pool starvation, no-LLM-in-order-path):
- Slow path (at entry, seconds-tolerant): model reads the full picture (regime, key-level zones +
  multi-day level history, 4h/15m structure, VIX character, volume) → writes a STRUCTURED exit
  plan (hold-to level, stop basis, invalidation conditions). Hot path (60s): exit_manager executes
  mechanically; fail-open to current shape on any model failure. Model never touches orders.
- **Step 1 ($0, offline)**: replay real entries' FROZEN at-entry context bundles through the
  judgment layer; score its plans vs engine actual exits on broker truth. Contamination guard:
  inputs strictly the at-entry snapshot. Grading machinery already exists (shadow_model_eval /
  free-model trust gate: >=85% over >=15 evidence).
- Step 2 (live shadow, needs API key = J action; est **$2-5/day** at 5-10 entries, Opus-low):
  plans logged at real entries, zero authority.
- Step 3 (only on Step-2 pass): advisor — plan feeds exit_manager params within guardrails.
- **Flywheel**: every place judgment beats the engine, distill WHY into a deterministic rule →
  prereg → ship. Opus is a rule-miner, not a tick-decider.
- Cheapest 80% first: the sensors already exist LOGGED-ONLY (context_bundle daily/1h/15m,
  market_structure BOS/CHoCH, key-level zones, chop meter) — P5 wires them before paying a model
  to look at a picture the engine already computes but never reads.

**P0 addendum (same night):** replay coverage limiter is NOT market data — same-day OPRA fetch
works (today's 4 contracts backfilled at 21:00 ET), bars gap now ZERO. 81/274 rows lack
placement-CONFIG reconstruction from the decisions ledger. Worker order: extend
`harness_fidelity_anchor.placement_configs()` fallback (journal/params history) to recover the
81 rows, then core-account pre-06-26 fills become replayable too. 08-07 book-exposure anatomy
(FRIDAY-REPLAY fold) hardens P4: no kill breach — the loss was 3 same-thesis waves x 5 arms
x same second, incl. re-buying a just-stopped strike.

---

## 5. Night-of results (2026-08-11 late / 08-12 early) — read before picking up P0-P7

Full evidence: [UNLOCK-AND-BREAKEVEN-2026-08-11.md](../../analysis/deep-research/2026-08-11-audit/UNLOCK-AND-BREAKEVEN-2026-08-11.md)

**P0 coverage item CLOSED — and the diagnosis in §1 was wrong.** The limiter was never OPRA and
never "config reconstruction" generically: `placement_configs()` globbed only the fleet directory,
so **safe-2 and bold-2 (the core accounts) were invisible to every replay study**. Recovered from
`core-decisions.jsonl` with per-field provenance stamps. Population **193 -> 240 of 274**, days
22 -> 27, accounts 4/6 -> **6/6**. OPRA bar gap is now **zero** (same-day fetch works). 7 guards,
RED-proofed. Live-path blast radius zero.

**Four questions answered, all NO-SHIP — the engine is unchanged and that is the correct outcome:**

| question | verdict |
|---|---|
| Un-scope the ladder to all strategies (J's challenge) | 🔴 VWAP cohort −$411, all 4 gates fail. Ladder stays ribbon-only. |
| Ladder helps bulls / hurts bears? | ⚪ Bootstrap: both CIs straddle zero (p=0.12 / p=0.70). Noise. |
| Nth-trade-of-day is negative EV? | ⚪ No effect (1st −$8 vs later −$5, WR flat ~20%). |
| Relax the paper PDT simulation (68 blocked trades)? | 🔴 Net −$62, 13/18 losers. PDT was protective. Closed. |
| Is the recency qty-clamp mis-firing? | 🔴 Hypothesis REJECTED — clamp is worth **+$876**. Stays. |

**THE NUMBER THAT MATTERS — August crossed breakeven, with no cushion:**
avg win $312 / avg loss $127 = 2.45x → **breakeven WR 29.0%, actual 29.7%.** Era WR went
10.9% (Jun) → 27.8% (Jul) → **29.7% (Aug)**, net −$1,289 → −$617 → **+$286**. Drop-best August
is still −$3,338. Not "profitable" — *first non-negative era, 0.7pp of margin*.

**Re-prioritised work map.** Every exit-shape knob is now measured as a wash or worse
(ladder scope, ladder tuning, PDT, trade sequencing, clamp removal — all dead). Two levers remain:
1. **Cut average loss** (−$127 book, −$147 safe-3). Each $10 off moves breakeven WR ~0.6pp.
2. **Regime selection** (P1/ER30, forward 0/25) — unchanged as #1.

**NEW top-of-queue question, evidence-backed (CORRECTED after reading the source):** the recency
clamp's **release hysteresis**. Note two corrections to my first pass -- `fleet_executor.py:302-352`
has **TWO** clamps with near-identical log lines: `FULL_SEND min size` (unconditional on a full-send
arm) and `recency RED` (global verdict). `risky-1` is the FULL-SEND arm, so its 08-07 protection
(+$921) was by-design min-sizing, NOT a recency signal. And the recency verdict is **GLOBAL** (one
shared `recency-confirmation.json`, read live per tick), so it cannot differ per arm -- risky-3 DID
clamp 12->5 on 08-04 from 11:27 on, and `recency_min_size_enabled=True` in both params files.
The real mechanism: the global verdict was **not RED on the morning of 08-07**, so safe-3 and
risky-3 entered at full tier size into the worst day, having been RED through 08-04 and returning
to RED by 08-10. Prereg to write: should release require N consecutive non-RED sessions instead of
tracking a signal that went non-RED for a single morning?
Live state at handoff: `_recency_verdict()` == **RED**, so all arms size at `min_contracts`
(safe 3 / bold 5) on the next session.

**Methodology note for the next worker — two of my own errors were caught mid-analysis, both by
process rather than luck:** a linear-scaling counterfactual gave the clamp result the WRONG SIGN
(caught by the prereg's mandated non-linear replay), and a `(arm, symbol, date)` join key
double-counted split fills (caught by refusing to report an unexplained sign flip and tracing one
position to leg level). **Do not report a reversal you cannot explain mechanically.**
