# Sizing-Scaling Decision Package — does wiring `position_sizing_tiers` into core help?

Generated 2026-08-02 (ET, offline research lane — no live/market-hours action taken).
Runner: `backtest/tools/sizing_scaling_decision_2026_08_03.py`. Guards (36 tests, RED-proofed
live this session — see §7): `backtest/tests/test_sizing_scaling_decision_2026_08_03.py`.
Raw data: `analysis/deep-research/SIZING-SCALING-DECISION-2026-08-03.json`.

**Scope: DECISION PACKAGE, NOT A SHIP.** Zero edits to any trading-path file
(`heartbeat_core.py`, `automation/state/fleet/*`, `params.json`/`aggressive/params.json`,
`exit_manager.py`, `exit_actuator.py`, `backtest/lib/option_pricing_real.py`,
`backtest/lib/exit_manager_walk.py` — all read-only this session, imported for reuse, never
modified). Sizing-scaling is a risk-posture change; it is J's call. This document hands him
the numbers, not a decision.

**The finding under test** (`analysis/deep-research/CAPITAL-EFFICIENCY-2026-08-03.md`):
core sizes every order at exactly `min_contracts` (Safe 3 / Bold 5) regardless of equity —
the capital curve is flat from $5K to $50K. The fleet lane already has a scaling mechanism
(`position_sizing_tiers`); core has never been wired to it.

---

## Verdict first

- **The naive port (fleet's own deny-not-shrink mechanism) is measurably BROKEN exactly at
  the equity band that matters most.** At Safe equity $2,000 (the tier's own first scaling
  step), the scaled arm makes **96% LESS** money than doing nothing over the full 18-month
  population ($207.90 vs baseline's $4,820.40) — not because the edge got worse, but because
  scaling qty up SHRINKS the per-contract premium ceiling under a fixed dollar cap, and
  112 of 191 candidate trades (58.6%) get refused outright that would have cleared at
  qty=3. At the task's own upper real-balance figure, $2,122, the scaled arm goes
  **negative** (-$640.00) against a strongly positive baseline (+$5,928.15). This is a
  specific, mechanical, avoidable bug in the DENY semantics — not a verdict on scaling itself
  (§2, §5).
- **At $5,000+ equity, scaling is unambiguously positive for both accounts, full-history,
  with ZERO incremental kill-switch breaches.** Safe: $9,680→$23,394 total (vs baseline's
  flat $3,822 at every level $5K+). Bold: $27,281→$78,104 (vs baseline's flat $21,304).
  Kill-switch breach count for Safe is **0 at every equity level, every arm, full-history AND
  recent** — the cleanest number in this whole document. Bold's one breach in the entire
  dataset occurs on the **baseline** arm at $2,000 (today's real 5-contract sizing, nothing
  to do with scaling) — and scaling at that same equity shows FEWER breaches, not more,
  because over-denial trades less (§2).
- **At today's REAL balances (Safe $1,160-$1,747, Bold $1,197.52), the lever is
  STRUCTURALLY INERT — proven by table lookup, not simulation.** Every one of those balances
  sits inside the tier table's own deliberately-unscaled $0-$2,000 band (`"structure": "no
  upsize - capital constraint"`, its own label) — tiered qty EXACTLY equals `min_contracts`
  there, by design. There is nothing to turn on yet (§5).
- **The task's own framing needed a factual correction, verified against live code, not
  assumed:** CLAUDE.md's "tp1_qty_fraction 0.8 Safe / 0.667 Bold" is TRUE OF THE PARAMS FILE
  but NOT of the live core `ribbon_ride` exit path — `heartbeat_core.py:2176-2182` shows core
  unconditionally uses `strategies.RIBBON_RIDE.exit.to_dict()` (hardcoded 0.667) for BOTH
  accounts' ribbon_ride positions; Safe's params.json 0.8 is read only for specific
  trade-to-learn extra setups, a narrower scope. Every trade in both populations tested here
  is ribbon_ride, so **0.667 governs both accounts' real leg splits, not 0.8/0.667** (§0, §4).
- **The leg split never hits a zero-qty leg at any tier this study tested** (Safe 3/5/8/10/15,
  Bold 5/8/12/15/20 — real `ExitState.from_entry`, not reimplemented) — but the REALIZED TP1
  fraction bounces between 60.0% and 66.7% against a 66.7% nominal (floor-rounding only ever
  takes FROM the TP1 leg, proven never adds to it), and this is not cosmetic: it is the
  demonstrated mechanism behind the ONE case where scaling underperforms a naive linear
  scale-up in the recency slice (Safe $25K recent: -$551.30 scaled vs a near-zero -$12.75
  baseline, far worse than pure 10/3× linear scaling of -$12.75 would predict) (§4).
- **Recency complicates, rather than confirms, the prior document's own encouraging recency
  read.** CAPITAL-EFFICIENCY-2026-08-03.md's "$64.41/trading-day recently, genuinely better"
  was computed at the SPECIFIC $1,746.75 baseline, whose tight cap incidentally filters out
  expensive recent trades. At a looser cap ($5K+), the SAME recent 33-trade Safe population
  reads flat-to-negative on the unscaled baseline arm (-$0.39/trade). This is a genuine,
  disclosed correction, not a restatement (§3).
- **C31 is fairly NOT directly implicated** — the sizing tested here is fixed-at-entry,
  equity-conditioned, never adjusted mid-trade or by "it's cheaper now" (the no-add guard
  stays fully untouched) — but C31's deeper lesson generalizes honestly: more contracts per
  trade means more dollars exposed to a bad STRETCH, and the population's own worst-stretch
  drawdown at low-to-mid equity runs 40%-313% of a static account reference. The DAILY kill
  switch does not fully neutralize that — it protects one bad day, not a multi-week bleed.
  This is J's risk-tolerance call, stated honestly, not resolved here (§6).
- **Recommendation (§8): ship the WIRING now (it is provably inert today, zero risk) — but
  wire it with core's existing SHRINK semantics (already present, currently dead code — see
  §1), never fleet's deny semantics. Do NOT arm scaled sizing live until a shrink-semantics
  re-run confirms the $2,000-band deadlock is actually closed.** This is not shipped here —
  a decision package, per this lane's charter, produces no trading-path edit.

---

## 0. A framing correction that had to happen before anything else could be trusted

The task brief (matching CLAUDE.md's account table) states tp1_qty_fraction as **0.8 Safe /
0.667 Bold**. Verified against live code this session, that is **true of the params files,
not true of the live core `ribbon_ride` exit path**:

```python
# setup/scripts/heartbeat_core.py:2176-2182 (CORE_MANAGES_EXITS branch, ribbon_ride's
# _xov is None -- the branch EVERY trade in both populations tested here takes)
else:
    try:
        import strategies as _strat
        _s = _strat.by_name("ribbon_ride")
        _shape = _s.exit.to_dict() if _s else None
    except Exception:
        _shape = None
```

```python
# automation/state/fleet/strategies.py -- RIBBON_RIDE.exit
exit=ExitShape(premium_stop_pct=-0.20, tp1_premium_pct=1.0, tp1_qty_fraction=0.667, ...)
```

Safe's params.json `tp1_qty_fraction: 0.8` is read ONLY inside the `_xov is not None` branch
(trade-to-learn extra setups like `vwap_continuation`) when that specific setup lacks its own
isolated `"tq"` override — a narrower scope than `ribbon_ride`, the setup family both
populations tested in this document are 100% composed of (`setups_allowed` in both params
files; `orchestrator.run_backtest` "only models the RIDE_THE_RIBBON family" per
`engine_fullhist_replay.py`'s own scope disclosure). **This document uses the verified live
value, 0.667, for both accounts, throughout.** CLAUDE.md's account table is stale on this one
field and should be corrected in a follow-up (flagged, not fixed here — out of this lane's
scope to edit doctrine).

This was verified, not assumed: `verdict.get("triggers_fired")` already exists on core's
verdict object at multiple call sites (`heartbeat_core.py:748,1068,1162,1377`), which matters
for §1's wiring spec.

---

## 1. MECHANISM — how fleet scales, whether it respects Rule 6, and the minimal core wiring

### 1a. The tier tables already exist in BOTH base params files (not just fleet's)

```json
// automation/state/params.json (Safe)
"position_sizing_tiers": [
  {"equity_min": 0,     "equity_max": 2000,       "base_qty": 3,  "elite_qty": 3,
   "structure": "2 TP1 + 1 conservative runner (no upsize - capital constraint)"},
  {"equity_min": 2000,  "equity_max": 10000,      "base_qty": 5,  "elite_qty": 8,
   "structure": "3 TP1 + 1 conservative + 1 aggressive runner"},
  {"equity_min": 10000, "equity_max": 999999999,  "base_qty": 10, "elite_qty": 15,
   "structure": "6 TP1 + 2 conservative + 2 aggressive runners"}
]
```

```json
// automation/state/aggressive/params.json (Bold)
"position_sizing_tiers": [
  {"equity_min": 0,     "equity_max": 2000,       "base_qty": 5,  "elite_qty": 5},
  {"equity_min": 2000,  "equity_max": 10000,      "base_qty": 8,  "elite_qty": 12},
  {"equity_min": 10000, "equity_max": 999999999,  "base_qty": 15, "elite_qty": 20}
]
```

Both live in the SAME base params files core already reads every tick — this is not a
fleet-only artifact that would need porting across files. It is dead data sitting next to
live data.

### 1b. `fleet_executor._qty_for` — the exact scaling function (reused, not reimplemented)

```python
# automation/state/fleet/fleet_executor.py:219-228
def _qty_for(tiers: Any, equity: float, elite: bool) -> Optional[int]:
    if not isinstance(tiers, list):
        return None
    for tier in tiers:
        lo, hi = tier.get("equity_min"), tier.get("equity_max")
        if lo is None or hi is None:
            continue
        if float(lo) <= equity < float(hi):
            return int(tier.get("elite_qty" if elite else "base_qty"))
    return None
```

`lo <= equity < hi` — confirmed by direct test (`test_qty_for_boundary_at_2000_is_inclusive_
to_the_upper_tier`): at EXACTLY $2,000 equity Safe already resolves to the [2000,10000) band
(qty 5/8), not the [0,2000) band. `elite` comes from `fleet_executor._is_elite` — a trade
whose trigger set includes `confluence` OR any `sequence_*` trigger — reused verbatim as
`classify_elite` in this study's harness.

### 1c. Does fleet respect Rule 6 at every tier? YES — but by DENYING, never shrinking

`fleet_executor.finalize()` calls `risk_gate.check_order(proposed_qty=plan.qty, ...)`
directly on the TIERED qty with no affordability pre-check. `check_order`'s RISK_CAP /
MAX_PREMIUM_TIER gates are hard ALLOW/DENY — there is no "reduce qty and retry" path
anywhere in the fleet call chain. A tiered qty that is too big for the cap is refused
**wholesale**, exactly like every other risk_gate deny. Rule 6 is never breached (verified:
`n_denied_risk_cap` in every capital-curve row below is trades EXCLUDED, never a smaller
order silently placed) — but the trade is lost entirely, not resized. This is the exact
mechanism behind §2's $2,000-band deadlock.

### 1d. Core's OWN shrink-down clamp already exists — and is currently DEAD CODE

```python
# setup/scripts/heartbeat_core.py:1964-1967 (READ ONLY this session, not modified)
qty = int(params.get("min_contracts", 3))
afford = rg.max_affordable_qty(equity=equity, premium=mid, params=params)
if afford and qty > afford:
    qty = afford
```

Trace the arithmetic: `qty` starts at exactly `min_contracts`. `max_affordable_qty` (`backtest/
lib/risk_gate.py:613-641`) returns EITHER `0` (deadlock — not even the floor fits) OR a value
`>= min_contracts` (by its own internal `if max_qty < min_contracts: return 0` guard — it can
never return a positive number below the floor). So `afford` is always in `{0} ∪
[min_contracts, ∞)`. Since `qty == min_contracts` exactly at this line, `qty > afford` can
only be true if `min_contracts > afford` — impossible under both cases (`afford=0` fails the
`if afford` truthiness check first; `afford >= min_contracts` fails `qty > afford`). **This
clamp cannot fire today, under any input** — it is inert scaffolding, apparently built ahead
of a wiring that never landed.

### 1e. The minimal wiring, stated precisely (specified, NOT implemented this session)

```python
# The ONLY change needed at heartbeat_core.py:1964, one line replacing the qty assignment:
_tiers = params.get("position_sizing_tiers")
_elite = fx._is_elite({"confluence": "confluence" in
                        [str(t).lower() for t in (verdict.get("triggers_fired") or [])],
                        "triggers_fired": verdict.get("triggers_fired") or []})
qty = (fx._qty_for(_tiers, equity, _elite) if _tiers else None) or int(params.get("min_contracts", 3))
# EVERYTHING BELOW THIS LINE IS ALREADY WRITTEN AND UNCHANGED:
afford = rg.max_affordable_qty(equity=equity, premium=mid, params=params)
if afford and qty > afford:
    qty = afford
```

Nothing downstream needs to change. `verdict["triggers_fired"]` already exists on core's
verdict object (confirmed, §0). The moment `qty` can exceed `min_contracts`, the existing
clamp becomes live and does exactly the graceful degrade-to-affordable behavior fleet's
mechanism lacks: a tiered qty that doesn't fit shrinks to the largest one that does (down to
a floor of `min_contracts`), and only a genuine floor-level deadlock still denies — the SAME
outcome baseline already produces for that trade, never worse. **This is why §2's numbers
are a lower bound on the scaled arm's true potential, not an upper bound** — they model
fleet's harsher deny-only mechanism throughout, deliberately, because that is the mechanism
that actually exists and runs today; a core-native shrink implementation was specified, not
built or measured, and is flagged everywhere it matters as the recommended (not tested)
alternative.

---

## 2. THE CAPITAL CURVE, pre-registered, with the kill-switch column

Real OPRA (`backtest/data/options/*.csv`), real bar-by-bar exit re-derivation
(`lib.exit_manager_walk.walk_exit_manager`, driving the REAL `exit_manager.py#
plan_exit_actions` core) at EVERY qty this study needed — not a linear rescale. Entry
metadata reused from the two already-validated populations (Safe 191 trades / Bold 315
admitted of 334 raw entries — `block_elite_bull=True`, current live). Sequential
one-position admission inherited from both source populations. **Kill switch simulated
explicitly, chronologically, per calendar day**: once a day's cumulative included P&L
breaches `-kill_pct × start_of_day_equity`, every subsequent same-day trade is EXCLUDED (it
would never have fired live) — the trade that trips the switch is itself still counted (it
already fired before the breach was known). `start_of_day_equity` = the grid level (a static
scaling exercise, matching CAPITAL-EFFICIENCY's own convention, not a compounding curve —
see the drawdown caveat below the tables).

### Safe (191 trades, full history, per_trade_risk_cap_pct=0.30, daily kill=-30%)

| Equity | Arm | Total P&L | $/trade | $/day | WR | n Included/Denied | **Max DD ($/%eq)** | Worst day | **KS breaches** |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| $2,000 | baseline | $4,820.40 | $28.03 | $37.08 | 29.7% | 172/19 | $1,709 / 85% | -$342 | **0** |
| $2,000 | **scaled** | **$207.90** | $2.63 | $3.20 | 21.5% | 79/112 | $1,923 / 96% | -$415 | **0** |
| $5,000 | baseline | $3,822.00 | $20.01 | $27.11 | 29.3% | 191/0 | $2,137 / 43% | -$825 | **0** |
| $5,000 | **scaled** | **$9,680.30** | $53.19 | $71.18 | 28.0% | 182/9 | $3,439 / 69% | -$701 | **0** |
| $10,000 | baseline | $3,822.00 | $20.01 | $27.11 | 29.3% | 191/0 | $2,137 / 21% | -$825 | **0** |
| $10,000 | **scaled** | **$18,395.90** | $102.20 | $135.26 | 28.3% | 180/11 | $6,959 / 70% | -$1,402 | **0** |
| $25,000 | baseline | $3,822.00 | $20.01 | $27.11 | 29.3% | 191/0 | $2,137 / 9% | -$825 | **0** |
| $25,000 | **scaled** | **$23,394.15** | $122.48 | $165.92 | 29.3% | 191/0 | $9,275 / 37% | -$4,125 | **0** |

### Bold (315 trades, full history, per_trade_risk_cap_pct=0.50, daily kill=-50%, no v15 tier)

| Equity | Arm | Total P&L | $/trade | $/day | WR | n Included/Denied | **Max DD ($/%eq)** | Worst day | **KS breaches** |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| $2,000 | baseline | $12,577.50 | $44.13 | $62.89 | 32.8% | 285/30 | $6,266 / 313% | -$1,020 | **1** |
| $2,000 | **scaled** | **$5,128.80** | $34.89 | $48.38 | 30.6% | 147/168 | $2,972 / 149% | -$968 | **0** |
| $5,000 | baseline | $21,304.10 | $67.63 | $96.40 | 33.1% | 315/0 | $4,133 / 83% | -$1,123 | **0** |
| $5,000 | **scaled** | **$27,281.10** | $90.33 | $127.48 | 31.9% | 302/13 | $8,382 / 168% | -$2,448 | **0** |
| $10,000 | baseline | $21,304.10 | $67.63 | $96.40 | 33.1% | 315/0 | $4,133 / 41% | -$1,123 | **0** |
| $10,000 | **scaled** | **$74,925.40** | $240.15 | $340.57 | 33.1% | 312/3 | $13,658 / 137% | -$4,080 | **0** |
| $25,000 | baseline | $21,304.10 | $67.63 | $96.40 | 33.1% | 315/0 | $4,133 / 17% | -$1,123 | **0** |
| $25,000 | **scaled** | **$78,104.15** | $247.95 | $353.41 | 33.1% | 315/0 | $13,013 / 52% | -$4,490 | **0** |

**Reading the kill-switch column straight** (the task's explicit priority): Safe never
breaches, anywhere, either arm. Bold's single breach in the ENTIRE dataset is on
**baseline** at $2,000 — today's real 5-contract sizing, nothing to do with scaling — and
the scaled arm at that same equity has FEWER breaches (0), not more, because over-denial
means fewer, smaller positions fire that day. **Scaling does not cost a single incremental
kill-switch breach anywhere in this measurement.**

**Reading $2,000 straight is the opposite story, and it is the load-bearing one:** Safe's
scaled total collapses to 4.3% of baseline's; `n_denied_risk_cap` jumps from 19 to 112 (of
191) — a 5.9× increase in refused trades. Mechanism: at $2,000, 30% cap = $600; qty 5 needs
premium ≤ $1.20/contract, qty 8 (elite) needs premium ≤ $0.75/contract — both far tighter
than qty 3's $2.00 ceiling. Real ATM 0DTE premiums routinely run $1-3, so the tier's own qty
jump prices itself out of the majority of its own opportunity set. This is the deny-not-
shrink mechanism from §1c, measured directly, at the exact equity band where both accounts
will land first as they grow.

**Drawdown caveat (disclosed, not hidden):** `max_drawdown_pct_of_grid_equity` running
40%-313% is a peak-to-trough measure over the population's OWN full 18-month cumulative P&L
curve against a STATIC (never-compounding, never-shrinking) equity reference — the SAME
static-equity convention `CAPITAL-EFFICIENCY-2026-08-03.md`'s own capital curve used,
extended here rather than reinvented. It answers "how bad was the worst unbroken losing
stretch across 18 months, relative to a fixed account size" — a genuine capital-adequacy
stress signal — but it is NOT the same claim as "the account would have been wiped out": a
real account's equity (and therefore its daily kill floor) shrinks with every losing day,
which this static reference does not model, and the daily kill switch (the `KS breaches`
column) is the mechanism that actually intervenes turn-by-turn. Treat the two columns as
complementary, not interchangeable — the task correctly named `KS breaches` as first-class;
drawdown is important context, not the primary gate.

---

## 3. THE RECENCY READ (J's dynamic-market rule — recency > aggregate)

Newest 25 trading days per account's own population (`regime_participation_study.
recent_n_trading_days`, the standing repo convention): Safe 2026-05-28→2026-07-21 (33
trades), Bold 2026-06-04→2026-07-21 (37 trades).

### Safe recent-25

| Equity | Arm | Total P&L | $/trade | $/day | WR | n Incl/Denied | KS breaches |
|---:|---|---:|---:|---:|---:|---:|---:|
| $2,000 | baseline | $1,027.75 | $36.71 | $46.72 | 42.9% | 28/5 | 0 |
| $2,000 | scaled | $634.00 | $70.44 | $79.25 | 44.4% | 9/24 | 0 |
| $5,000 | baseline | **-$12.75** | **-$0.39** | **-$0.51** | 39.4% | 33/0 | 0 |
| $5,000 | scaled | $2,465.80 | $88.06 | $112.08 | 42.9% | 28/5 | 0 |
| $10,000 | baseline | -$12.75 | -$0.39 | -$0.51 | 39.4% | 33/0 | 0 |
| $10,000 | scaled | $4,651.20 | $166.11 | $211.42 | 42.9% | 28/5 | 0 |
| $25,000 | baseline | -$12.75 | -$0.39 | -$0.51 | 39.4% | 33/0 | 0 |
| $25,000 | scaled | **-$551.30** | **-$16.71** | **-$22.05** | 39.4% | 33/0 | 0 |

### Bold recent-25

| Equity | Arm | Total P&L | $/trade | $/day | WR | n Incl/Denied | KS breaches |
|---:|---|---:|---:|---:|---:|---:|---:|
| $2,000 | baseline | $1,771.00 | $55.34 | $80.50 | 37.5% | 32/5 | 1 |
| $2,000 | scaled | $128.20 | $10.68 | $12.82 | 25.0% | 12/25 | 0 |
| $5,000 | baseline | $5,128.60 | $138.61 | $205.14 | 40.5% | 37/0 | 0 |
| $5,000 | scaled | **$3,724.90** | **$116.40** | **$169.31** | 37.5% | 32/5 | 0 |
| $10,000 | baseline | $5,128.60 | $138.61 | $205.14 | 40.5% | 37/0 | 0 |
| $10,000 | scaled | $21,945.15 | $609.59 | $877.81 | 41.7% | 36/1 | 0 |
| $25,000 | baseline | $5,128.60 | $138.61 | $205.14 | 40.5% | 37/0 | 0 |
| $25,000 | scaled | $19,215.15 | $519.33 | $768.61 | 40.5% | 37/0 | 0 |

**This is genuinely mixed, not a clean confirmation, and one number needs a direct
correction to prior work.** `CAPITAL-EFFICIENCY-2026-08-03.md` §5 reported the recent 25
days as "$64.41/trading-day live-faithful... genuinely better, not just noisier" — computed
at ONE specific point, the $1,746.75 baseline equity, whose tight ~$524 cap incidentally
filters OUT the recent window's more expensive (and, on this evidence, worse) trades. At a
looser cap ($5,000+, `n_denied=0`, every recent trade included), the SAME 33-trade Safe
population reads **flat-to-negative on the unscaled baseline arm** (-$0.39/trade,
-$0.51/day). The earlier "encouraging" read was real at its own tested equity, but was
partly an artifact of which trades that specific cap happened to exclude — not a robust,
equity-independent property of the recent window. Report this correction plainly rather than
letting the earlier number stand uncontested.

**Bold's $5,000 recent scaled arm actively underperforms its own baseline** ($3,724.90 vs
$5,128.60) — the mirror case: here the tighter qty-8 cap denies 5 of 37 trades that baseline
(qty 5, `n_denied=0`) keeps, and this time the excluded cohort reads net-positive for
baseline. The direction of the admission-set effect is not consistent — it genuinely depends
on which specific trades a given tier's premium ceiling excludes, in both directions, not a
one-way "scaling always denies away losers" or "scaling always denies away winners" story.

**Safe's $25,000 recent scaled row is the clearest illustration of §4's leg-split finding
mattering in practice, not just structurally.** At $25K neither arm denies anything
(`n_denied=0` both), so the ONLY difference is qty (10 scaled vs 3 baseline, same 33 trades)
— pure linear scaling of baseline's -$12.75 to qty 10 would predict roughly -$42.50
(-$12.75 × 10/3); the REAL re-walked number is **-$551.30**, an order of magnitude worse.
Mechanism: qty 10's realized TP1 fraction is 60.0% vs qty 3's 66.7% (§4's leg-split table) —
materially more runner-weighted — and in this specific 25-day window the runner leg is
evidently the worse-performing leg. This is a concrete, measured case of the leg-split
non-linearity the task asked to verify, not a theoretical caveat.

**Bold's $10,000 recent scaled number ($877.81/day) is large enough to warrant its own
too-good-to-be-true check** before anyone cites it. It is NOT a units or parsing artifact —
the underlying mechanics (real re-walk, `n_exit_reason_qty_variant_MUST_BE_ZERO: 0` across
every trade in both populations, confirmed empirically not just claimed) are independently
verified. It exceeds a naive 3× linear scale of baseline's $205.14/day partly because scaled
denies 1 fewer-favorable trade (`n_denied=1`) and partly because qty 15's realized TP1
fraction (66.67%, near-nominal) differs from qty 5's (60.0%) in a window where that shift
apparently helped. The primary reason for caution is the same one the source document
already applies to its own recency read: **n=36-37 trades over 25 days is a thin base** —
reported honestly as a real, mechanism-explained number, not inflated into a durable rate.

---

## 4. THE LEG-SPLIT VERIFICATION (real `ExitState.from_entry`, every qty this study used)

Nominal `tp1_qty_fraction` = 0.667 for both accounts (§0). `ExitState.from_entry`'s own
math: `tp1_qty = int(qty * frac)` — a FLOOR, never a round — so `realized_tp1_fraction` can
only equal or undershoot nominal, never exceed it (proven structurally, confirmed by the
guard `test_leg_split_row_realized_fraction_bounded_by_nominal_due_to_floor_rounding`).

| qty | tp1_qty | runner_qty | realized TP1 % | vs nominal 66.7% | zero-qty leg? |
|---:|---:|---:|---:|---:|:---:|
| 3 (Safe today) | 2 | 1 | 66.67% | -0.03pp | NO |
| 5 (Safe $2-10K base / **Bold today**) | 3 | 2 | 60.00% | -6.7pp | NO |
| 8 (Safe $2-10K elite / Bold $2-10K base) | 5 | 3 | 62.50% | -4.2pp | NO |
| 10 (Safe $10K+ base) | 6 | 4 | 60.00% | -6.7pp | NO |
| 12 (Bold $2-10K elite) | 8 | 4 | 66.67% | -0.03pp | NO |
| 15 (Safe $10K+ elite / Bold $10K+ base) | 10 | 5 | 66.67% | -0.03pp | NO |
| 20 (Bold $10K+ elite) | 13 | 7 | 65.00% | -1.7pp | NO |

**No zero-qty leg, no rounding pathology of the severe kind (a leg that vanishes), at any
tier either account's `position_sizing_tiers` table actually produces.** But it is not a
cosmetic non-finding either: the runner leg is **consistently equal-to-or-heavier** than the
66.7% nominal split intends (never lighter — the floor can only take FROM the TP1 leg), by
as much as 6.7 percentage points (a ~20% relative oversizing of the runner leg's contract
count at qty 5/10). Since `automation/state/fleet/exit_manager.py`'s own docstring calls the
trailing/chandelier runner "the ... runner engine" — the book's primary profit driver — a
persistently runner-heavy realized split at several tiers is not obviously bad, but it is a
real, quantified, previously-undocumented deviation from the DESIGNED 66.7/33.3 split, and
§3 shows a concrete case (Safe $25K recent) where it swung the outcome materially worse than
naive linear-scaling intuition would predict. **Report it as a known, bounded, real effect —
not as a defect requiring a fix, and not as a non-issue either.**

---

## 5. THE HONEST ALTERNATIVE — what does scaling buy at TODAY's real balances?

Task-supplied real-balance range: Safe $1,160-$2,122; Bold $1,197.52.

| Account | Equity | Arm | Total P&L | $/trade | n Included/Denied | Identical to baseline? |
|---|---:|---|---:|---:|---:|:---:|
| Safe | $1,160.42 | baseline | $1,806.50 | $19.22 | 94/97 | — |
| Safe | $1,160.42 | scaled | $1,806.50 | $19.22 | 94/97 | **YES — byte-identical** |
| Safe | $1,746.75 | baseline | $5,278.70 | $33.20 | 159/32 | — |
| Safe | $1,746.75 | scaled | $5,278.70 | $33.20 | 159/32 | **YES — byte-identical** |
| Safe | $2,122.00 | baseline | $5,928.15 | $33.30 | 178/13 | — |
| Safe | $2,122.00 | scaled | **-$640.00** | **-$7.03** | 91/100 | **NO — flips negative** |
| Bold | $1,197.52 | baseline | $7,448.40 | $47.75 | 156/159 | — |
| Bold | $1,197.52 | scaled | $7,448.40 | $47.75 | 156/159 | **YES — byte-identical** |

**Two structurally different findings, not one:**

1. **At every real balance up through $1,999.99, the lever does LITERALLY NOTHING —** not
   approximately, byte-identically. This is provable by table lookup alone
   (`test_todays_real_balances_all_fall_in_the_unscaled_band`, no simulation needed): the
   $0-$2,000 tier's own `base_qty`/`elite_qty` both equal `min_contracts` for BOTH accounts
   (Safe 3=3=3, Bold 5=5=5) — a deliberate design choice its own `structure` field labels
   "no upsize - capital constraint." **There is zero cost and zero benefit to shipping the
   wiring at today's actual equity** — it is provably a no-op until either account crosses
   $2,000.
2. **The task's own stated upper bound, $2,122, is PAST that threshold — and it is exactly
   where the $2,000-band deadlock trap (§2) bites.** Under deny-semantics, scaling flips a
   strongly positive $5,928.15 baseline into a **-$640.00 loss** at that specific equity.
   This is not a hypothetical edge of the grid — if the task's $2,122 figure reflects a real
   balance close to today's, either account could cross $2,000 within days of ordinary
   trading, and a naive deny-semantics port would degrade performance the moment it does,
   silently, with no error — just a wall of `RISK_CAP` denies that look like normal risk-gate
   activity in the logs unless someone is specifically looking for the deadlock signature.

**The equity level where this lever starts to matter, stated exactly: $2,000.00**, for both
accounts, by tier-table construction — not an estimate.

---

## 6. C31, weighed honestly both ways

**The case that C31 does NOT apply here:** C31's -$17,461 (3+ lots) vs +$4,576 (1-2 lots)
split, and its corrected L203 attribution ("the recoverable money is the no-add +
-50%-catastrophe-cap PACKAGE"), describe DISCRETIONARY behavior — averaging down, adding to
losers, sizing up mid-trade because "it's cheaper now" (Rule 4 violations). The sizing tested
here is categorically different: a FIXED qty selected ONCE, at entry, purely as a function of
account equity and the setup's elite/base classification — never touched again for the life
of the trade, never influenced by how the trade is going. The no-add guard (`fb.
is_flat_spy_options`, per CLAUDE.md, already structural, pinned by
`test_never_average_down_2026_07_20.py`) is completely untouched by this lever. Rule 6's cap
is enforced identically regardless of tier (§1c/§2) — no trade in this measurement ever
exceeded its account's legal per-trade risk limit.

**The case that C31's DEEPER lesson still generalizes:** the mechanism-level claim
"'profitable at 1-2 lots' was an accounting artifact" (per this repo's own WeBull
fresh-eyes correction) is a caution against a specific ERROR (mis-crediting size for what was
really a behavior problem), not a blanket claim that size itself is risk-free. More
contracts per trade unavoidably means more dollars exposed to whatever happens on that trade
— and §2's drawdown column shows that exposure is not small at low-to-mid equity (40%-313%
of a static reference over the worst 18-month stretch). The daily kill switch bounds a SINGLE
day's damage; it does not bound a slow multi-week bleed the way a compounding, equity-aware
system would need to be independently stress-tested to rule out. **Both readings are correct
simultaneously**: this lever is mechanically unlike C31's killer behavior, AND it introduces
a real, larger-magnitude risk surface that C31's own daily-kill-switch answer does not fully
retire. Neither side should be discarded to make the recommendation cleaner.

---

## 7. Guard tests (RED-proofed)

`backtest/tests/test_sizing_scaling_decision_2026_08_03.py` — 36 tests over every new pure
function (`reached_tp1`, `leg_split_row` — cross-checked directly against `ExitState.
from_entry`, `daily_kill_switch_walk`, `equity_curve_stats`, `classify_elite`,
`qty_values_needed`) plus integration-shape tests on `capital_curve` (denies-not-shrinks on a
cap breach; applies the kill-switch walk across same-day trades) and pinned regression tests
on both live `position_sizing_tiers` tables and the $2,000 boundary inclusivity.

RED-proofed live, this session: (1) flipped the kill-switch floor comparison from `<=` to
`<` — `test_kill_switch_walk_exact_floor_touch_trips` failed exactly as expected (an exact
floor touch stopped tripping the switch); (2) narrowed `reached_tp1`'s substring check to
only `"runner_stop"` — 4 tests failed exactly as expected (`runner_target`/structure-stop/
ribbon-flip/time-stop post-TP1 markers stopped being recognized). Both mutations reverted,
suite confirmed green again:

```
backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_sizing_scaling_decision_2026_08_03.py -q
36 passed in 0.97s
```

Empirical cross-check (not just a unit test — measured across the REAL population): the
qty-invariant-exit-timing assumption this whole methodology leans on
(`n_exit_reason_qty_variant_MUST_BE_ZERO`) held **exactly 0** across all 191 Safe trades ×
5 qty values (955 re-walks) and all 315 admitted Bold trades × 5 qty values (1,575 re-walks)
— zero exceptions, empirically confirmed, not assumed from the code reading alone.

Harness runtime: 80.9s total (Bold's `run_backtest` entry layer, 68.2s, is the only slow
step — every qty re-walk after that reuses cached OPRA bars + a cached ribbon join per
symbol, 3.9s for all 955 Safe re-walks, 8.5s for all 1,575 Bold re-walks).

---

## 8. Recommendation to J

The data does not support a clean "ship it" — the naive port (fleet's own mechanism) is
demonstrably a net-negative move at the first equity band either account will actually reach.
It also does not support a clean "kill it" — the underlying lever, wired correctly, is free
today and strongly positive at every equity level $5,000 and up, with zero measured
incremental kill-switch cost. The honest recommendation has three parts:

1. **Ship the WIRING now, using SHRINK semantics (§1e), not fleet's deny semantics.** It is
   provably a no-op at today's real equity (§5) — zero risk, reversible, matches this
   project's standing bar for a currently-inert change. Do not port fleet's mechanism
   verbatim; that specific implementation choice is what the $2,000-band deadlock (§2, §5)
   traces to, not the sizing concept itself.
2. **Do NOT arm it to actually change live qty until a shrink-semantics version of this exact
   harness is re-run and confirms the $2,000-band deadlock is closed.** This document
   measured the mechanism that exists (deny), and specified but did not measure the
   mechanism recommended (shrink) — that is a real gap, disclosed, not glossed over. The
   argument that shrink-semantics is at least as good as baseline everywhere is code-grounded
   (§1e) but unmeasured; re-verify before trusting it with capital.
3. **Before scaling is ever LIVE-armed at $5K+ equity, decide explicitly on the drawdown
   exposure (§2, §6)** — 40%-313% of a static reference over the worst historical stretch is
   a real number this document will not round down. The daily kill switch is a real, working
   guard against any SINGLE day; it was not designed to be, and this measurement does not
   claim it to be, a guard against a slow multi-week bleed at larger size. That tradeoff is
   J's sizing-posture call, not a risk-data verdict this lane can make for him.

If forced to compress to one line: **wire it, fix the mechanism the fleet copy would get
wrong, re-test that fix, and only then let equity growth actually change what gets traded —
never ship fleet's deny-on-breach behavior into core as-is.**

---

_Sources: `analysis/deep-research/CAPITAL-EFFICIENCY-2026-08-03.md` (motivating finding) ·
`analysis/recommendations/engine-fullhist-replay-2026-07-23.json` (Safe, 191-trade entry
metadata, exits re-derived fresh this session) · `backtest/tools/bold_fullhist_replay.py`
(Bold entry layer, `bold_base_live(block_elite_bull=True)`, current live) ·
`backtest/lib/exit_manager_walk.py#walk_exit_manager` · `automation/state/fleet/exit_manager.
py#ExitState.from_entry` (imported, not modified) · `automation/state/fleet/fleet_executor.py
#_qty_for/_is_elite` (imported, not modified) · `backtest/lib/risk_gate.py` (imported, not
modified) · `automation/state/params.json` / `automation/state/aggressive/params.json` ·
`markdown/doctrine/FOCUS-DOCTRINE.md` · `markdown/doctrine/LESSONS-LEARNED.md` L168/L203 ·
CLAUDE.md C31._
