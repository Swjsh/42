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
| `ribbon_ride` | BEARISH_REJECTION_RIDE_THE_RIBBON<br>BULLISH_RECLAIM_RIDE_THE_RIBBON | stop -20% · TP1 +100% · sell 67% · trailing · runner 99.0x · trail 15% · arm +5% · mode STRUCTURE (cat -50%) |
| `vwap_continuation` | VWAP_CONTINUATION<br>vwap_continuation | stop -6% · TP1 +40% · sell 80% · fixed · runner 2.5x · trail 12% · arm +5% · mode premium |

Direction: both — the side comes from which side-block (bull/bear) fired; `enable_bullish=True` (safe). No per-strategy direction lock.

## 2b. Structure-stop (SS-B, v15.3 chart-stop-primary)

STOP-B (2026-07-09): for a strategy whose exit shape declares `stop_mode="structure"`, the chart level is the PRIMARY invalidation — exit on the first CLOSED 5m SPY bar beyond the entry's trigger level (side-aware: puts exit above, calls exit below), with the premium stop DEMOTED to a `catastrophe_stop_pct` intrabar floor. Resolved ONCE at entry (`exit_manager.ExitState.from_entry`) and never re-evaluated mid-trade — an open position keeps whatever mode it entered under even if the flag below flips intraday.

A position resolves to STRUCTURE mode only when ALL THREE hold at entry: the strategy declares `stop_mode="structure"` (§2 above) AND the flag below is ON AND a real `trigger_level` was available (the exact filter-matched level, or `exit_manager.nearest_active_level`'s proximity guess as fallback). Missing ANY of the three → that position opens in PREMIUM mode instead (the strategy's own `premium_stop_pct`), byte-identical to pre-STOP-B behavior.

- **Flag `structure_stop_enabled`:** safe `True` · bold `True` — params.json / aggressive/params.json (doc key `_structure_stop_enabled_doc` on both).
- **Strategies declaring `stop_mode="structure"`:** `ribbon_ride`.
  - `ribbon_ride`: catastrophe cap **-50%** (structure mode, live) · flag-off/no-level fallback stop **-20%** (premium mode).
- **Consumers:** fleet exit lane (`fleet_live._place_live` → `exit_actuator.register_entry` → `exit_manager.ExitState.from_entry`) + core lane (`heartbeat_core._execute`, same `register_entry` call). Both lanes now also render `stop_mode`/`trigger_level`/`stop_display` on the plan-log row so a structure-managed position never looks like a premium one in the logs.
- **Instant de-arm:** flip `structure_stop_enabled` to `false` (either/both params files) — new entries fall back to premium mode; in-flight positions are unaffected either way (resolved once, at entry).

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
- **Premium floor `min_entry_premium`: safe $0.30 · bold $0.30** — plan-time strategy admission in BOTH lanes (`heartbeat_core._execute` post-NO_PREMIUM; `fleet_executor.finalize` pre-check_order, shared by fleet_live decide_arm + run_dry). A sub-floor premium is a logged `SKIP_MIN_PREMIUM_FLOOR` row, never an order. Evidence: entry-exit-matrix-2026-07-09.md (T3 n=157; anchor −$72.50 vs −$757.10). 0/absent = OFF.
- **No passive/patience logic** — no limit-below-signal, no cancel/convert window. (The T3 entry-matrix studies exactly this axis; nothing is wired yet.)
- Stale un-crossed BUY limits from a prior tick are cancel-replaced each tick.

## 3c. Shadow machinery — built, NOT armed (T-W4/T-W5)

Zero arms consume either module below. Both ship freely as observability per HANDOFF-2026-07-11-CONFIRM-AND-WIRE (shadow/paper work needs no STOP sign-off; ARMING either needs its own P5-survivor pass + STOP-B).

- **exit-B per-band stop resolver** (`automation/state/fleet/per_band_stop.py`, `resolve_stop_pct`) — NOT ARMED. Pre-registered `EXIT_B_BAND_TABLE`:
  - premium <$0.20 → stop -25%
  - premium <$0.50 → stop -35%
  - premium >=$0.50 → stop -50%

- **entry-2 passive-limit state machine** (`automation/state/fleet/entry_manager.py`, `plan_entry_action`) — NOT ARMED. Pre-registered spec: limit @ signal×(1−10%), patience 3 bars, miss=cancel.
  - Shadow ledger: `automation/state/entry-shadow.jsonl` (runtime state, regenerate via `backtest/tools/shadow_entry_backfill.py`; stats reported in the firm brief, not on this drift-guarded card).

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
