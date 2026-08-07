# PRE-REGISTRATION — SCORE LADDER RUNG (demotable-demerit admission), 2026-08-07

**Status: FROZEN before the replay runner exists or runs.** Commit timestamp of this file is
the freeze proof (git-provable; the runner `backtest/tools/ladder_rung_replay_2026_08_07.py`
is committed AFTER this file). Written mid-session Friday 2026-08-07 (~12:20 ET, market
open) — this prereg + runner + guard tests + dormant patch are all analysis/new-module scope;
NO trading-path file is edited while market_hours=True.

Directive: J, 4th+ ask (verbatim today): *"I've said how many times now that risky accounts
are able to get in on an eight out of ten, a seven out of ten, a nine out of ten. So why are
we sitting out of anything that's a ten out of eleven?"* First logged 2026-07-27
(pk-2026-07-27); standing paper autonomy + 4 asks = authorization to ship to the RISKY arms
tonight IF the replay evidence clears the frozen gates below.

---

## 1. Central claim (the frozen partition)

An arm's admission threshold is a **SCORE, not a gate cascade** (J's words define it). For
LADDER arms, **DEMOTABLE** filters no longer veto — each active demotable blocker subtracts
its demerit from the score — while **NON-DEMOTABLE** gates remain absolute vetoes on every
rung. The arm enters when `adjusted_score >= rung`.

### Demerit derivation (from filters.py, not invented)

The scorer already subtracts **exactly 1 point per blocker**:
- `backtest/lib/filters.py:1758` — `bear_score = 10 - len(blockers)`
- `backtest/lib/filters.py:1273` — `bull_score = 11 - len(blockers)`

Therefore each demotable filter's demerit = **1 point** (the score points it already
represents in the scorer), and `adjusted_score` is IDENTICAL to the score the engine already
logs per tick. Ladder admission reduces to, per side:

```
ENTER iff  (active blockers ⊆ DEMOTABLE_side)  AND  (logged score >= rung)
           AND every non-scoring absolute gate below passes
```

### The partition — BULL side (bull_score /11; today's incident side)

| Filter | Mechanism (filters.py) | Class |
|---|---|---|
| 1 | entry time window (>=09:35 / no_trade windows) | **NON-DEMOTABLE** |
| 5 | ribbon BULL-stacked (`:1172`) | DEMOTABLE |
| 6 | ribbon spread >= 30c (`:1177`, RIBBON_SPREAD_MIN_CENTS=30) | **NON-DEMOTABLE** |
| 7 | NOT bullish volume-divergence (`:1182`) | DEMOTABLE |
| 8 | VIX < 17.20 OR falling — soft (`:1188`) | DEMOTABLE |
| 9 | VIX < 22 HARD (`:1201`, VIX_BULL_HARD_CAP=22.0) | **NON-DEMOTABLE** |
| 10 | buyer pressure close>open AND vol>=0.7x (`:1206`) | DEMOTABLE |
| 11 | >= min_triggers (live 2) AND >=1 level-tied trigger (`:1265-1271`) | **NON-DEMOTABLE** |
| 12 | sweep blocker (off by default) (`:1222`) | **NON-DEMOTABLE** |

### The partition — BEAR side (bear_score /10; mechanism-mapped, NOT number-mapped)

The directive's filter numbers are bull-side numbers. Bear maps by MECHANISM:

| Filter | Mechanism (filters.py) | Class |
|---|---|---|
| 1 | entry time window (`:1466`) | **NON-DEMOTABLE** |
| 5 | ribbon BEAR-stacked (`:1487`) | DEMOTABLE |
| 6 | ribbon spread >= 30c (`:1505`) | **NON-DEMOTABLE** |
| 7 | NOT volume-divergence-failed (`:1510`) | DEMOTABLE |
| 8 (vix <= 23.0) | VIX>17.30-AND-rising soft condition (`:1514-1536`) | DEMOTABLE |
| 8 (vix > 23.0) | VIX hard cap — VIX_HARD_CAP_BEAR embedded in the same blocker (`:1521`) | **NON-DEMOTABLE** |
| 9 | breakdown-bar seller pressure — the bear analog of bull F10 (`:1538`) | DEMOTABLE |
| 10 | >= min_triggers (live 1) AND >=1 level-tied trigger — the bear analog of bull F11 (`:1725-1733`) | **NON-DEMOTABLE** |
| 11 | sweep blocker (off by default) (`:1735`) | **NON-DEMOTABLE** |

Bear F8 decomposition is clean because `VIX_DECLINING_REQUIRED_BEAR = False` (filters.py:44
— the L115 multi-day-declining branch is disarmed), so the ONLY two ways bear F8 blocks are
(a) VIX low/falling (soft, demotable) or (b) vix_now > 23.0 (hard cap, veto). The replay
decides (a)-vs-(b) from each ledger row's own `vix` field; the production patch decides from
the live tick's vix. `vix_bear_hard_cap = 23.0` per automation/state/params.json (live).

### Absolute gates that are NEVER scored through (any rung)

- **risk_gate** — Rule 5 kill switch, Rule 6 per-trade cap, PDT (Rule 7), NOT_FLAT/no-add
  (Rule 4), min_contracts. The ladder plan rides the normal downstream path
  (`fleet_executor` finalize + risk_gate.check_order) UNTOUCHED — same contract as the
  existing floor/probe/full-send lanes.
- **min_entry_premium floor** ($0.30 live, both param files) — untouched downstream.
- **Filter 11's level-tied requirement (bull) / filter 10's (bear)** — a bare-confirmation
  entry is the measured **-$103/entry, 0% WR** cohort (ENTRY-QUALITY-2026-08-06); it is
  never admitted on any rung. Enforced twice: the blocker itself is non-demotable AND the
  producer block requires a raw level-tied trigger + a numeric raw level (chart-stop anchor;
  no level, no trade).
- **Entry window, spread, VIX hard caps** — per the tables above.

## 2. Arms and rungs (frozen)

| Arm | Account | Rung | Mechanism |
|---|---|---|---|
| risky-3 (FLEET-LOOSE-R) | PA31WIU8X15Q | **7** | `gate_override.score_ladder_rung: 7` |
| risky-1 (FLEET-TIGHT-R) | PA3W17FD8G19 | **8** | `gate_override.score_ladder_rung: 8` |
| safe-3, safe-2, bold-2 | — | **binary (control)** | no key; byte-identical behavior |

Rungs are applied literally to each side's own scale (bear /10, bull /11) — same disclosed
convention as ARM-LADDER-V1-2026-07-27. Both sides are in scope (bull included: today's
refused cohort is bull; validation is the only scope, direction is not — OP-16).

Default ABSENT key = **byte-identical binary behavior** (C14 vary-and-assert; guard tests
committed with this change RED against HEAD until the patch is applied, then GREEN).

## 3. Graveyard distinction (why this is not a dead idea re-run)

- **NOT filter deletion** (dead) and **NOT filter-8 relax** (dead): those removed a gate for
  ALL arms unconditionally. This is per-arm, score-conditional admission with the safe arms
  as an in-fleet control.
- **NOT the 2026-07-27 `score_ladder_floor` lane** (DISARMED ~23:30 ET 2026-07-27 on
  evidence: floor=8 lane -$16,642 over 725 trades vs baseline +$5,307 —
  analysis/arm-ladder/LADDER-FULLHIST-2026-07-27.md). That lane admitted on RAW score with
  **blocker identity ignored**: spread-blocked, entry-window-blocked and hard-VIX-blocked
  ticks were all admitted if score cleared the floor, and it was **bear-only**. The rung
  lane vetoes every non-demotable blocker absolutely, decomposes bear F8 hard-vs-soft, and
  covers bull (today's actual miss shape: 80 ticks sole-blocked by bull F10 and 10 by F7 at
  score 10/11 while SPY ran 770.50→773.17). The killed lane's population number is re-run
  here as an honest reference cell, not hidden.

## 4. Evidence plan (cells frozen before running)

All cells reported, none dropped (honest-cells rule). BH correction across cells within
each family where p-values are computed.

1. **TODAY (2026-08-07), ledger replay** — every safe-account core tick, per-arm rungs at
   signal level, sequential one-position per arm, PDT/kill modeled per arm. Same-day OPRA
   is 403 until ~16:21, so today's premiums are the engine's own per-tick spy/vix track
   priced via the repo BS lib — **every today cell is labeled EST** and never blended with
   real-OPRA cells. EST pricer calibration error is reported against the engine's own real
   fetched mids on today's priced ticks (n≈11/arm).
2. **THE WEEK (08-03..08-06), ledger replay on real OPRA** — same walk with real OPRA
   contract bars (fetched via the existing fetch_option_data infrastructure for uncached
   days). Any candidate without a cached/fetchable contract is EXCLUDED from P&L and
   counted/disclosed (repo convention; C1 real-fills authority).
3. **POPULATION (2025-01-02..2026-07-27, 390 RTH days)** — the fullhist machinery
   (run_backtest + walk_exit_manager, real OPRA only) with rung-semantics admission, BOTH
   sides, rungs 7 and 8, vs (a) binary baseline and (b) the killed raw-floor lanes.
   Slices: per-side, per-admitting-blocker cohort, held-out last-25%, drop-best-day,
   day-majority, max DD.
4. **Exit convention** — `walk_exit_manager` -> exit_manager.plan_exit_actions ONLY
   (RIBBON_RIDE exit shape, structure stop, trigger_level = the raw detection's own level;
   entry+1 next-bar convention, option bar OPEN). Sequential walks, one position per arm.
5. **Sizing** — population lane qty=3 (comparability with the killed lane + baseline);
   today/week cells ALSO shown at the risky arms' real min_contracts=5. Per-trade averages
   reported so size never manufactures a verdict.

## 5. Ship gates (frozen; evaluated tonight after 16:00 ET)

- **G-WEEK (primary, recency-first per J 2026-07-31 doctrine):** the ladder-ADDED trades
  (net of what binary already took) across 08-03..08-07 are net positive for the shipped
  arm's rung. EST cells count but are labeled; if the week verdict flips sign on EST-only
  cells, ship waits for the 16:21 OPRA re-price of today.
- **G-POP (guard, not the bar):** the rung lane's population avg-per-added-trade must be
  > -$5/trade AND the lane must not show the killed-lane shape (avg <= -$20/trade). A
  G-POP miss with a G-WEEK pass = STAGED, reported to J, not silently shipped.
- **G-HONEST:** all cells reported; EST vs real never blended; excluded-candidate counts
  disclosed; per-blocker cohort table included.
- Ship action if gates pass: apply the dormant patch (fleet-only), set
  `score_ladder_rung` 7/risky-3 and 8/risky-1 in accounts.json gate_override, commit,
  report for REVOKE. Safe arms stay binary regardless — that IS the ladder.

## 6. Production mechanism under test (dormant patch, NOT applied while market open)

Smallest change, fleet-only (`heartbeat_core`'s core hook untouched — core arms are all
binary controls):

1. `build_shared_signal._ladder_block_from_row` — additionally emit a `bull` block (score,
   blockers, triggers_raw, level) and add `vix` to both blocks. Pure additive producer
   data; every existing reader keys off config keys, so emission alone changes nothing
   (same inertness contract as `probe`/`ladder`/`full_send`).
2. `fleet_executor._ladder_rung_plan` — new lane behind `gate_override.score_ladder_rung`,
   same call-site pattern as `_ladder_plan`, implementing the partition above; risk chain
   downstream untouched.

Patch text: analysis/arm-ladder/score-ladder-rung-2026-08-07.patch (also inlined in
analysis/deep-research/CLOSE-PACKAGE-LADDER-ADDENDUM-2026-08-07.md). Guard tests:
backtest/tests/test_score_ladder_rung_2026_08_07.py (RED against HEAD = the proof they
test something; the RED run is quoted in the build doc; behavior tests carry
skip-until-implemented markers so the suite stays green until the patch lands).
