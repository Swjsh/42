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
- **safe-3 took zero trades 08-11** while four siblings traded. Mine its decisions.jsonl
  verdict distribution vs risky-3's for the same ticks; identify the sole-blocking gate.
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
<!-- SPLICE: GAMMA-CHECKLIST-GAP-MAP -->

## 3. Repo hygiene work orders
<!-- SPLICE: STALE-INVENTORY -->

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
