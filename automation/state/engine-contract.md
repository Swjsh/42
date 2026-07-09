# ENGINE CONTRACT — what the engine is actually taking right now

> AUTO-GENERATED from code+params by `setup/scripts/engine_contract.py`. **Do not hand-edit** — regenerated every Gamma_FirmBrief fire; a diff here means a source changed (arms / strategies / params / cap tables). The drift guard `test_engine_contract_drift.py` RE-DERIVES this and REDs on any mismatch.

Sources: `automation/state/fleet/accounts.json` (arms) · `automation/state/fleet/strategies.py` (exit shapes) · `automation/state/params.json` + `automation/state/aggressive/params.json` (control configs) · `backtest/lib/cap_admission.py` (sizing tables).

## 1. Arms (an account is a sizing×gate profile, NOT a strategy)

Every validated strategy in §2 runs on EVERY active arm via `fleet_executor.plan_all`. The arm only sets gate-strictness and position size.

| arm | cell | execution | live | gate | strike | note |
|---|---|---|---|---|---|---|
| `safe-3` | safe x tight | fleet_rest | ✅ | min_triggers=2, confluence/sequence | bold tier table (patch) | active |
| `safe-2` **(CONTROL)** | safe x base (CONTROL) | mcp_heartbeat | ✅ | base (production default) | safe params.json v15 tier | active |
| `safe-1` | safe x loose | fleet_rest | ✅ | min_triggers=1 | bold tier table (patch) | active |
| `risky-1` | risky x tight | fleet_rest | ✅ | min_triggers=2, confluence/sequence | inherit bold | active |
| `bold-2` **(CONTROL)** | risky x base (CONTROL) | mcp_heartbeat | ✅ | base (production default) | bold params.json | active |
| `risky-3` | risky x loose | fleet_rest | ✅ | min_triggers=1 | inherit bold | active |

Futures arms (not in the SPY 0DTE loop): `mes-linear-sim` (pending_build), `mes-mnq-div-futures` (dormant).

## 2. Strategies + their proven exit shapes (fleet_rest arms)

The exit shape is a property of the STRATEGY (the grind proved it), realized by the live `exit_manager`. Fleet_rest arms (safe-1/safe-3/risky-1/risky-3) trade these shapes.

| strategy | entry setups | exit shape |
|---|---|---|
| `ribbon_ride` | BEARISH_REJECTION_RIDE_THE_RIBBON<br>BULLISH_RECLAIM_RIDE_THE_RIBBON | stop -20% · TP1 +150% · sell 80% · fixed · runner 2.5x · trail 12% · arm +5% |
| `vwap_continuation` | VWAP_CONTINUATION<br>vwap_continuation | stop -8% · TP1 +30% · sell 67% · trailing · runner 2.5x · trail 12% · arm +5% |

Direction: both — the side comes from which side-block (bull/bear) fired; `enable_bullish=True` (safe). No per-strategy direction lock.

## 3. Control arms (mcp_heartbeat) — what they ACTUALLY trade

Options can't bracket at Alpaca → entries are SIMPLE limits with **no broker-side TP/stop**; the `exit_manager` owns every exit (production sets `GAMMA_CORE_MANAGES_EXITS=1` in `run-heartbeat-core.ps1`). Which shape it runs:

- **Generic ribbon setups** (BEARISH_REJECTION / BULLISH_RECLAIM): the control arms register **strategies.py `ribbon_ride`'s shape (§2)** with the exit_manager — the SAME shape the fleet_rest arms trade, NOT the params tp/stop below.
- **Per-setup isolated exits** (`_SETUP_EXIT_OVERRIDES`, heartbeat_core) — these armed extra setups trade their OWN validated cells from params keys:

| setup | stop | TP1 | extra knobs |
|---|--:|--:|---|
| `vwap_continuation` | -6% | +40% | — |
| `vwap_reclaim_failed_break` | -8% | +30% | — |
| `vix_regime_dayside` | -8% | +30% | — |
| `double_bottom_base_quiet` | -99% | +30% | runner |
| `bollinger_squeeze` | -8% | +30% | tq, plmode, trail |

- **params.json bracket values** (plan/log reference only — shown so drift is visible):

| control | source | stop | TP1 | sell frac | runner | time-stop |
|---|---|---|---|---|---|---|
| `safe-2` | params.json | -50% | +50% | 80% | 2.5x | 15:40 ET |
| `bold-2` | aggressive/params.json | -7% | +75% | 67% | 5.0x | 15:40 ET |

## 3b. Entry policy (all arms — the current order type)

- **Marketable simple limit: `ask + entry_cross_buffer` ($0.03)** — `fleet_broker.marketable_limit_price` / `heartbeat_core` #15 pricing. Crosses the spread to fill NOW (pays up into the signal bar).
- **No premium floor** — sub-$0.20 contracts are admitted (T2 diagnostics: a −20% stop there = ~2 ticks ≈ the spread).
- **No passive/patience logic** — no limit-below-signal, no cancel/convert window. (The T3 entry-matrix studies exactly this axis; nothing is wired yet.)
- Stale un-crossed BUY limits from a prior tick are cancel-replaced each tick.

## 4. Sizing math (risk_gate.check_order — the single order authority)

- **Per-trade risk cap:** Safe 30% · Bold 50% of equity (notional = premium×qty×100).
- **Min contracts:** Safe 3 · Bold 5 (below floor = hard DENY, never auto-reduced).
- **v15 per-tier max-premium (the usually-binding cap; tighter of this and risk cap):**

| equity band | Safe max% | Bold max% |
|---|---|---|
| $0–$2,000 | 40% | 50% |
| $2,000–$10,000 | 30% | 40% |
| $10,000–$25,000 | 25% | 35% |
| $25,000+ | 20% | 25% |

- **v15 strike ladder (safe params, negative=OTM in live convention):** $0+ → OTM-3 (J style - lean + leveraged) · $2,000+ → OTM-2 · $10,000+ → OTM-1 / ATM · $25,000+ → ITM-2 (current v14)

## 5. Hard floors (always bind, every arm)

- **Kill switch (Rule 5, per-account ISOLATED):** Safe −30% · Bold −50% of start-of-day equity. Safe halting does NOT halt Bold.
- **Time stop (in-engine):** Safe 15:40 ET · Bold 15:40 ET. **EOD-flatten backstop:** 15:55 ET (Gamma_EodFlatten closes any 0DTE not out by 15:50).
- **PDT (Rule 7):** ≥3 day-trades in rolling 5 business days AND equity <$25K → deny.
- **Flat-before-entry (Rule 4 / C11):** any open position blocks a NEW entry.

---
_One screen. If a number here looks wrong, the SOURCE is wrong — fix the source and regenerate; do not edit this file._
