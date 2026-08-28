# VIX-FLOOR-SHADOW pre-registration (2026-08-27)

> Pre-registered BEFORE any result is computed. Committed alone, before
> `vix_floor_shadow.py` writes a single ledger row. Per OP-16 eval-first gate
> and C6 no-look-ahead.

## Question

What would the bear setups that Filter 8 (VIX floor: `vix_now > 17.30 AND
vix_rising`, `backtest/lib/filters.py:1671-1693`) blocked SOLELY have done,
if traded through the live `ribbon_ride` exit shape?

## Population definition

- Source: `automation/state/core-decisions.jsonl` (live core-engine decision
  log, both accounts).
- Row qualifies iff `bear_blockers == [8]` **exactly** (single-element list;
  VIX is the ONLY reason the bear setup did not fire — every other filter,
  including Filter 10's >=2-of-4 trigger-count gate, already passed).
- No additional trigger-count/quality filter is applied at selection time.
  (A tighter "all 4 raw triggers present" sub-cut exists in the data — n=10,
  all on 2026-08-05 — and is reported separately as a sensitivity slice, never
  substituted for the primary population.)
- `account` field maps `safe` -> Safe-tier ATM strike table, `bold` ->
  Bold-tier table; both current-tier equities ($5,266 safe-2 / $5,048 bold-2,
  broker-verified 2026-08-18 per CLAUDE.md) sit inside the same `$2K-$10K`
  bracket for BOTH tables' bear side... **correction**: bear = puts, and only
  the SAFE ATM row (`V15_SAFE_TIERS`, offset 0) is used for this study, per
  the task's Safe-tier scope. Bold-account rows are included in the
  population (their VIX-blocked signal is real) but sized/strike-selected
  using the SAME Safe ATM convention, disclosed explicitly in the summary —
  this study answers "what would the ATM/Safe execution have captured",
  not a Bold-specific counterfactual.
- **One-open-position-at-a-time replication per account** (mirrors live
  `NOT_FLAT`): rows are walked in `ts_et` order per account. The first
  qualifying row becomes a shadow ENTRY. Every later qualifying row whose
  `ts_et` falls before that shadow position's exit timestamp is SKIPPED (it
  would have been blocked by the engine's own flat-check, not just by the
  VIX filter, had it also been live). The next row after the exit timestamp
  becomes the next shadow entry candidate. This collapses same-move
  re-triggers (a rejection setup can re-fire every engine tick, ~once/min,
  while the pattern is still valid) into ONE trade, not N.

## Entry convention

- Contract: SPY 0DTE, same calendar day as the signal.
- Strike: ATM, `crypto/lib/strike_selection.py#atm_strike(spot)` =
  `round(spot)` at the signal bar (`core-decisions.jsonl`'s `spy` field),
  offset 0 per `V15_SAFE_TIERS` for both accounts (see note above). Bear =
  PUT.
- OCC symbol built via `setup/scripts/spread_executor.py#occ_symbol("P",
  strike, expiry_yymmdd)`.
- Entry timing: **next-minute** option 1-min bar OPEN after the signal bar
  close (signal ts_et is the minute the engine evaluated the setup; entry is
  simulated one bar later, consistent with a human/engine reacting to a
  closed-bar signal) + 1 tick ($0.01) slippage against the trader (buy higher).
- Contracts with zero returned OPRA 1-min bars for that (symbol, date) are
  **EXCLUDED AND COUNTED** separately (pain-ledger convention) — never
  silently dropped from the denominator.

## Exit model

Drives the REAL, live `plan_exit_actions` pure decision core
(`automation/state/fleet/exit_manager.py`) via the same harness pattern as
the ratified `backtest/tools/exit_shape_parity_study.py` (PARITY-GAP-2
iteration-6 machinery, 6/6 fidelity) — not a re-implementation. Exit shape =
the LIVE `ribbon_ride` shape verbatim
(`automation/state/fleet/strategies.py#RIBBON_RIDE.exit`):

- `stop_mode="structure"`, `trigger_level` = the row's
  `bear_rejection_level_raw`, structure stop driven off REAL SPY 5-min SIP
  bars (`backtest/tools/alpaca_bars.py#fetch_spy_5m_sip`) — the same
  `last_closed_5m_close` vs `trigger_level` check the live actuator runs.
- `catastrophe_stop_pct = -0.50` (the intrabar hard cap when structure
  hasn't invalidated but premium craters).
- `tp1_premium_pct = 1.0` (+100%), `tp1_qty_fraction = 0.667` (sell 66%).
- `pre_tp1_ladder`, `pre_tp1_trail_arm_pct/pct`, `profit_lock_mode="trailing"`,
  `trail_pct=0.15`, `runner_target_pct=99.0` — all read verbatim off the
  live `RIBBON_RIDE.exit` dataclass (`dataclasses.asdict`), so this is
  byte-identical to what the live account would run today, not a
  reconstruction.
- Time stop 15:50 ET, same as live (`TIME_STOP_ET`).
- Qty fixed at 3 (Safe-tier minimum per CLAUDE.md rule 6: 2 TP + 1 runner).

## Promotion bar (fixed in advance)

Auto-promotable (ships to the recommendations queue as a candidate, still
requires the standing eval-first A/B before any live filter change) only if
**ALL** of:

1. `n >= 15` valid (non-excluded) shadow trades.
2. OOS-positive profit factor (PF > 1.0) on the OOS slice.
3. Walk-forward stability `WF >= 0.70` — IS/OOS date split at **2026-08-14**
   (chosen because it roughly bisects the trailing-window population by
   date-count, fixed BEFORE computing any result).
4. Sub-window stable (no single day > 50% of total P&L; disclosed either way).
5. Anchor no-regression: this shadow population is additive-only — it must
   NOT be pooled with or compared against the real trendline-bypass bear
   cohort's numbers (different setup shape, per task background); no
   existing ratified anchor's number changes as a result of this study.

Falling short of any gate = NOT promoted. The shadow ledger and summary are
still published as -- and only as -- mechanism evidence.

## Disclosures (C4)

- **Selection is on entry-time information only** (`bear_blockers`,
  `bear_score`, `spy`, `bear_rejection_level_raw` as they existed AT the
  signal tick) — no look-ahead into the bar's own future closes for entry
  eligibility (C6).
- **Synthetic fills are mechanism evidence, not P&L truth.** Real OPRA 1-min
  bars are used for the option premium walk, but there was never a live
  order, so there is no real fill, no real slippage beyond the modeled 1
  tick, and no real queue/liquidity friction. Treat all $ figures as "what
  the exit machinery would have produced against real market prices," not as
  money actually made or lost.
- **VIX regime concentration.** Per background: essentially all of August
  2026 sat in a narrow VIX 14-16 band (with occasional prints crossing the
  17.30 floor intraday, which is exactly what generates this population).
  This study speaks ONLY to that regime. It says nothing about how a lowered
  or removed VIX floor would perform in a genuinely elevated-VIX regime
  (VIX 20+), where Filter 8 was originally added to guard against mis-priced
  0DTE premium and stop misfires (L99/L100).
- **Different setup shape than the traded bear cohort.** The real August
  bear trades entered via the trendline-only bypass path — a structurally
  different trigger combination. This population and that cohort are
  reported and evaluated SEPARATELY. They are never pooled or averaged.
- **One-position collapse is a simplifying assumption**, not a claim that a
  human/engine would have picked exactly this first-touch entry over a
  later, possibly better-priced re-touch of the same level. Sensitivity: the
  summary also reports the raw (uncollapsed) row count so the size of the
  collapse is visible.
- **`--today` append mode** (Step 3) is documentation-only in this build —
  no scheduled task is created by this script or by this session. Suggested
  registration command is written into the summary JSON's `schedule_hint`
  field for J/a future session to wire via `mcp__scheduled-tasks__*` if
  wanted.

## Files this pipeline writes (SHADOW / ANALYSIS ONLY)

- `setup/scripts/vix_floor_shadow.py` (this build)
- `analysis/recommendations/vix-floor-shadow-ledger.jsonl`
- `analysis/recommendations/vix-floor-shadow-summary.json`

## Files this pipeline will NEVER touch

`automation/state/params.json`, `automation/state/fleet/aggressive/params.json`,
`setup/scripts/heartbeat_core.py`, `backtest/lib/filters.py`, any live-order
path, any scheduled-task registration.
