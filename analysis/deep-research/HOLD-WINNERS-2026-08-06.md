# HOLD OUR WINNERS — the runner-shape A/B (2026-08-06, Lane 3)

_Clock verified before work: `et_clock.py` → `2026-08-06 18:46:29 Thursday EDT, market_hours=False`.
Executes **PREREG-RUNNER-BE-FLOOR-2026-08-06** (`analysis/recommendations/prereg-runner-be-floor-2026-08-06.json`,
commit `61bc6507`, frozen and committed BEFORE the runner existed — git-provable). Real broker
fills + real OPRA 1-min only. Exits via `walk_exit_manager → exit_manager.plan_exit_actions`
(the live decision core). Never simulator_real._

---

## VERDICT — 🔴 **REGIME-CONDITIONAL (trend). DO NOT ARM.**

**The BE floor is not a "hold our winners" upgrade — it is a trend-day amplifier that this
record week flattered.** The pre-registered gates (frozen before the run) decided:

| Gate (frozen 61bc6507) | Result | Value |
|---|---|---:|
| G1 overall delta > 0 | ✅ pass | **+$4,026.15** |
| G2 survives on chop | ❌ **FAIL** | **−$320.75** (109 chop positions) |
| G3 ex-best-day > 0 | ✅ pass (fragile) | +$346.15 after removing 08-04's +$3,680 |
| G4 sub-window stability | ❌ **FAIL** | thirds: [−$409.70, +$47.35, **+$4,388.50**] |

The prereg's own rule: G1 pass + G2 fail → **REGIME_CONDITIONAL_TREND__DO_NOT_ARM**. There is
no lookahead-safe archetype classifier at entry (STOPPED-THEN-PAID settled: 20.9% vs 39.1%),
so a regime-conditional exit shape is not armable. The chandelier trail stays.

**The one number that kills it:** ex-THIS-WEEK (the 22 prior dates), the BE floor **loses
−$1,095.25** vs the trail. 100% of the positive effect is Mon 08-03 + Tue 08-04
(+$1,625.80 and +$3,680.00). This is the base-rate-negative book wearing its best week.

---

## Scope guard (stated per prereg)

This tested **POST-TP1 runner management only** — the runner has already banked TP1;
`profit_lock_arm_scope` stayed `"post_tp1"` in every cell. Under that scope,
`plan_exit_actions` consults `profit_lock_mode` **only** in its post-TP1 branch
(`exit_manager.py:514`), so no cell here can touch pre-TP1 behavior by construction. This is
**NOT** the five-times-dead PRE-TP1 arm-scope cell (`arm_scope="full"`, last killed at n=190:
G4 runner cohort −$7,758.85, 22 worse / 0 better — permanent graveyard).

## What was run

- **Population (frozen):** every closed engine SPY-option position in `fills-ledger.jsonl`,
  all 6 arms, **208 positions**, 26 dates 2026-06-26 → 2026-08-06, **including all losers**.
  192 walked; 16 were re-entries suppressed in ALL cells by the sequential one-position
  convention (their live P&L: −$552.00, disclosed); 0 lost to missing bars (71/71
  contract-days already in `opra_1m_cache`).
- **Cells:** CONTROL (each position's resolved live shape — registry + arm `exit_patch` +
  core isolated overrides), **B_BE_FLOOR** (`profit_lock_mode="fixed"`, all else identical),
  C_BE_FLOOR_TGT25 (exploratory, declared pre-run: fixed + finite 2.5 target where the shape
  had the 99.0 sentinel).
- **Fidelity upgrades over prior population replays:** structure stops ARE modeled
  (per-entry `trigger_level` from the arm's own ledger row + 5-min SPY frame). Ribbon flips
  are NOT modeled (identical omission in every cell, disclosed).
- **Model vs broker truth (walked subset):** CONTROL $1,870.68 vs actual $2,334.01
  (−19.9%); big days tight: 08-04 model $3,962.98 vs actual $3,768.00; 08-03 $620.70 vs
  $534.00; 08-05 −$1,494.66 vs −$1,935.00. Deltas are within-model, apples-to-apples.
- **Exhibit reproduction:** risky-1's 08-04 763C runner reproduces in-walk:
  `runner_target @ +250%`, +$625.50 (live: +$640) — the same single `runner_target` exit the
  live ledgers show.

## Where the delta actually lives

| Slice | n | CONTROL | B (BE floor) | Δ B−CONTROL | Δ C−CONTROL |
|---|---:|---:|---:|---:|---:|
| **Overall** | 192 | $1,870.68 | $5,896.83 | **+$4,026.15** | +$1,950.65 |
| Trend-like (trend-up/down, gap-go) | 83 | $4,761.08 | $9,107.98 | **+$4,346.90** | +$2,025.40 |
| **Chop-like** (range-chop, pin, gap-fade, V, inv-V) | 109 | −$2,890.40 | −$3,211.15 | **−$320.75** | −$74.75 |
| This week (08-03..08-06) | 46 | $3,555.62 | $8,677.02 | **+$5,121.40** | +$1,746.40 |
| **Ex-this-week** (22 prior dates) | 146 | −$1,684.94 | −$2,780.19 | **−$1,095.25** | **+$204.25** |
| Winners cohort (actual P&L > 0) | 36 | $9,516.75 | $13,724.70 | +$4,207.95 | +$2,132.45 |
| Losers cohort | 156 | −$7,646.07 | −$7,827.87 | −$181.80 | −$181.80 |

- **The lever exists on 30 positions.** Only 30/192 ever reach TP1; 29 have nonzero deltas
  and they sum to the entire +$4,026.15. **n=29 is the honest sample size — SMALL-N.**
- **Mechanism shift:** in B, 14 runners ride all the way to `time_stop_15:40` (ribbon_ride's
  99.0 sentinel means a BE-floored runner has no upside exit at all) — that is where
  Mon/Tue's +$5,121 came from: bold-2 763C +$1,468.20, safe-2/safe-3 763C +$734.10 each,
  risky-1/risky-3 754C +$653.00/+$662.00.
- **The disconfirming TREND day (07-29, trend-down):** Δ **−$906.60**. Three ribbon_ride 740C
  runners had trailed to ~2.6–2.7; the BE floor gave it all back to ~0.84. "Hold our winners"
  cuts both ways even on trend days — the trail IS the hold-our-winners mechanism on any day
  that doesn't close at its high.
- **On Wednesday's loss day (08-05, gap-fade):** B made the day **worse** (−$112.50). The BE
  floor is not a loss-control lever; it is pure upside-shape.
- Fallback attribution (22 positions, mostly core safe-2 extra-exec entries with no PLACED
  row) contributes **+$21.25** of the delta with 2 TP1-reachers — cannot move the verdict.
- Archetype labels are whole-session post-hoc (regime_slice charter) — used for SLICING only,
  never as an entry-time signal.

## The runner_target audit (J's "dead knob?" question) — the sentinel is REAL and LOAD-BEARING

| Surface | Says | Status |
|---|---|---|
| CLAUDE.md doctrine | "runner target 2.5×" | **STALE/incomplete** for ribbon_ride |
| `params.json` `runner_max_premium_pct` 2.5 (safe) / 5.0 (agg) | 2.5×/5× | **VESTIGIAL** on the live path — heartbeat_core & fleet both arm exits from the strategy REGISTRY, not these keys (same C14 family as the strike-ladder prose) |
| `strategies.py#RIBBON_RIDE` | `runner_target_pct=99.0` | **REAL + DELIBERATE** — the SS-B validated cell's "tgt-none" (its own comment: "runner exits via structure/trail/EOD only"). Not an accident. |
| vwap-family shapes | 2.5 (dataclass default) | REAL — this is the only place 2.5 is live |
| Live behavior (all ledger history) | trail exits 91 (fleet 34+39+18) + 33 (core) vs `runner_target` **2 fleet / 0 core** | Confirms both: ribbon_ride never target-exits; the one famous +250% exit (08-04 risky-1) was a vwap shape |

**Which is real:** the per-strategy registry. The doctrine line should read: *"runner target
2.5× on vwap-family shapes; ribbon_ride deliberately has NO finite runner target (SS-B
tgt-none cell) — its runner exits via structure/trail/EOD."* Doctrine-text fix only; no code
change proposed (the sentinel is part of the validated cell — C29 forbids mixing fields
across cells).

**Interaction disclosed:** the 99.0 sentinel is exactly why cell B rides to the 15:40 time
stop — under a BE floor the sentinel converts "no target" into "hold to close", which is the
graveyard's hold-longer shape wearing a runner-only costume. That is the mechanism of both
the Tuesday +$3,680 and the 07-29 −$906.60.

## The one genuinely interesting survivor (NOT armed, NOT clean)

Cell C (BE floor + finite 2.5 target on ribbon_ride) was the only variant positive
**ex-this-week** (+$204.25), least-bad on chop (−$74.75), and positive on the disconfirming
07-29 (+$146.90) — it banks the runner at +250% instead of round-tripping. It was declared
EXPLORATORY in the frozen prereg; no arming decision reads it. **Registered as a follow-up
prereg candidate** (`PREREG-RUNNER-FINITE-TGT` — candidate cells: trailing+2.5 AND fixed+2.5
vs CONTROL) with an explicit contamination disclosure: the hypothesis was surfaced by this
same 26-day window, so the follow-up must lean on forward paper evidence, not a re-run of
the window that generated it.

## Caveats

1. **n=29 nonzero-delta positions**; 26 trading days; the biggest single day is 91% of the
   gross effect. Nothing here is armable, in either direction, on this sample alone.
2. Ribbon-flip exits not modeled (8 in live core history) — identical omission in all cells.
3. Point-sample fill convention (walk_exit_manager's live-NBBO analog); limit fills at level.
4. Sequential suppression means variant cells never trade entries the engine took while a
   variant was still holding — symmetric across cells, counts identical here (16, all-cells).
5. CONTROL−actual gap −$463.33 (−19.9%) on the walked subset — ranking-grade, not
   absolute-P&L-grade.
6. 🔮 No oracle columns anywhere in this study.

## Artifacts

- `analysis/recommendations/prereg-runner-be-floor-2026-08-06.json` — frozen prereg (commit `61bc6507`, BEFORE runner)
- `backtest/tools/hold_winners_runner_ab_2026_08_06.py` — the runner
- `analysis/deep-research/HOLD-WINNERS-2026-08-06.json` — full grids: per-day, per-archetype,
  per-arm, cohorts, sub-windows, exit-mechanism distributions, all 192 per-position rows
- Prior evidence chain: `EOD-2026-08-04-WINNERS.md` §2/§6 (the prereg's origin; its winners-only
  +$1,912 was non-reproducible, re-derived +$2,229.70 same-sign; tonight's all-in 08-04 delta
  +$3,680 is the same phenomenon measured with losers + suppression + structure stops)
