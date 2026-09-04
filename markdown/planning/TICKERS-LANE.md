# TICKERS LANE — three dedicated non-SPY 0DTE paper accounts, production scorer

> Opened 2026-09-04 ~01:00 ET from J's directive (00:4x ET): *"wire these 3 accounts for all non SPY
> options trading ... just like how we trade spy 0dte ... they trade tomorrow ... test everything
> thoroughly."* Living doc — append, never fork (OP-22). Goal file:
> [`GOAL-TICKERS-LANE-2026-09-04.md`](../../automation/state/goals/GOAL-TICKERS-LANE-2026-09-04.md).
> Prereg (frozen before the executor existed, `5062ea52`):
> [`prereg-tickers-lane-production-scorer-2026-09-04.json`](../../analysis/recommendations/prereg-tickers-lane-production-scorer-2026-09-04.json).

## 1. What this lane is, in one paragraph

Every non-SPY test this shop has run scored a **copy** of the engine — `multi/lib/filters.py`,
1,211 lines against production's 2,342, ~2,700 differing lines, dollar tolerances re-derived as
ATR-relative. Weekly lane (684 real fills), multi lane (7,489 signals), catalysts (7,019 signals):
all ~49%, all on the copy. The **production** scorer (`backtest/lib/filters.py`) has never been run
on any name but SPY. This lane runs it **unmodified**, on the multi lane's audited plumbing, on
three **dedicated** paper accounts that share nothing with the SPY fleet or the crypto twin — so
for the first time, a non-SPY account's equity is evidence for its own lane. multi-1's kill rule
("a NEW signal and a NEW pre-registration") is satisfied: different code, this prereg.

## 2. The three arms

| Arm | Account | Universe | Why these |
|---|---|---|---|
| `tickers-1` | Tickers-1 (paper) | NVDA AAPL AMZN | tightest 0DTE spreads at the 2026-09-03 close: AAPL 0.46% · NVDA 1.28% · AMZN 1.52% |
| `tickers-2` | Tickers-2 (paper) | TSLA META AVGO | wider but inside the lane's 8% live gate: 1.83% · 4.00% · 4.93% |
| `tickers-3` | Tickers-3 (paper) | QQQ IWM GLD | daily-expiry ETFs: 1.06% · 4.44% · 6.37% |

Split universes so **no contract is ever held twice across accounts** (the SPY fleet's r=0.846
correlation scar). **SPY is never in any universe** — the executor asserts it and refuses the arm.
Excluded by the same screen: MSFT 5.55%, AMD 7.18%, GOOGL 7.71%, SMH 14.9%, XLF 18.2%
(`analysis/multi-lane/universe-screen-0dte-2026-09-04.json`, indicative feed, post-close).

## 3. The pipeline (what fires every 2 minutes, 09:35–14:55 ET)

```
Gamma_TickersLane (07:35 LOCAL = 09:35 ET, PT2M)
  └─ multi/execute.py  [holds automation/state/tickers/.lane.lock for the pass; a second instance skips (LOCK_HELD)]
       ├─ invariants: arm=="tickers", scorer=="production", no SPY, max_contracts<=5,
       │             base_url contains "paper", weekday 09:30-15:00 ET     (any fail -> arm aborted, loudly)
       ├─ creds: multi/lib/creds.resolve(key_source=tickers-N) -> automation/state/tickers/secrets.json
       │         missing? -> NO_CREDS logged, retried next tick (self-heal; never crashes)
       ├─ market clock: broker /v2/clock is_open (holidays, early closes) -> closed = one MARKET_CLOSED row per arm,
       │                pass ends; unreadable = CLOCK_READ_ERROR disclosed, proceed under the weekday/window invariants
       ├─ account PIN: first verify writes <arm>/account.json; a different number later -> REFUSE
       ├─ reconcile (every tick, before exits): sweep resting BUY orders in this arm's universe (STALE_ORDER_CANCELED;
       │             SELL legs + foreign roots left alone) · adopt any broker position the state never recorded (POSITION_ADOPTED)
       ├─ funnel bars ONCE (daily) + scanners -> attention
       └─ per arm: multi/core.py::tick(scorer=production, state_path=<arm>/exit-state.json, ...)
            ├─ EXITS FIRST: open_qty = BROKER positions (never record.qty; a record the broker no longer
            │             holds -> STALE_STATE row, dropped) · underlying = LIVE last trade (daily close only as a
            │             disclosed fallback) -> exits.evaluate_exit -> SELL_ALL/SELL_PARTIAL -> qty clamped to
            │             get_position_qty at the last moment (0 held -> EXIT_SKIPPED_FLAT) -> broker.market_sell(armed=True)
            │             -> finalize_order (not fully filled -> cancel remainder -> re-read to a terminal status)
            └─ ENTRIES: production evaluate_*_setup -> admission (kill switch, 1 concurrent)
                        -> nearest listed expiry (0DTE) -> ATM strike -> liquidity gate (<=8% spread, mid >= $0.20, indicative)
                        -> size_entry -> HARD CLAMP qty=3 -> entry window <=14:30 ET
                        -> broker.place_bracket(simple_fallback=True) [Alpaca rejects option brackets -> simple limit]
                        -> finalize_order: poll -> not FULLY filled? cancel the remainder -> re-read to a terminal status
                           (ENTRY_CANCELED = no record; partial = record the ACTUAL qty, ENTRY_PARTIAL_REMAINDER_CANCELED)
                        -> PositionRecord + journal/trades-tickers-<arm>.csv
                        -> FIRST fill of the lane's life -> STATUS.md ## Known broken line (the REVOKE surface)
Gamma_TickersEodFlatten (12:52 LOCAL = 14:52 ET)
  └─ multi/tickers_flatten.py -> waits ≤90s for .lane.lock then proceeds regardless (LOCK_FORCED) -> close_all_equity_options(armed=True)
     per arm -> verify FLAT from broker -> pops every record, journal EXIT row from the closing fills, day-file P&L
     (FLATTEN_PNL_UNRESOLVED if the lookup fails; the record is still dropped -- broker is truth)
Gamma_TickersDayCheck (07:40 + 13:05 LOCAL = 09:40 + 15:05 ET, READ-ONLY -- goal T6's instrument)
  └─ multi/tickers_day_check.py -> rows-exist (09:40) / flat-at-broker (15:05) verdict -> day-check-<date>-<phase>.json
     + a PROGRESS LOG line in the goal file + a TICKERS-DAY-CHECK line on STATUS ## Known broken when RED
```

**Ledger vocabulary** (beyond HOLD / BLOCKED / WOULD_PLACE): `ENTRY_FILLED` `ENTRY_CANCELED` `ENTRY_PARTIAL_REMAINDER_CANCELED` `ORDER_LIMBO` `EXIT_FILLED` `EXIT_PARTIAL` `EXIT_CANCELED` `EXIT_SKIPPED_FLAT` `EXIT_QTY_READ_ERROR` `STALE_STATE`→`STATE_RECORD_DROPPED` `STALE_ORDER_CANCELED` `FOREIGN_OPEN_ORDER` `POSITION_ADOPTED` `ADOPTION_FAILED` `MARKET_CLOSED` `CLOCK_READ_ERROR` `NO_CREDS` `INVARIANT_FAIL` `ACCOUNT_PIN_MISMATCH` `KILL_BLOCKED` `SHADOW_ONLY_INTERLOCK`; stderr-only: `LOCK_HELD` `LOCK_FORCED` `FLATTEN_PNL_UNRESOLVED`. Every exit_eval row also discloses `open_qty`/`open_qty_source` and `underlying_price`/`underlying_source`.

**The scorer.** `multi/lib/scorer_production.py` builds a production `BarContext` (production ribbon
from `backtest/lib/ribbon.py`, production 20-bar vol/range baselines, the multi lane's level
reconstruction + level_states + htf_15m) and calls `backtest/lib/filters.py::evaluate_bearish_setup`
/ `evaluate_bullish_setup` with production defaults. It returns the exact dict shape the fork
returns, so `tick()` needs no logic change — only `params.scorer` dispatches, vary-and-assert guarded.
**One variable moves vs multi-1: the scoring code.** Gating is the lane's own (risk / liquidity /
sizing), **not** `engine_cli`'s SPY-specific gates — disclosed on every row.

## 4. Day-one clamps (frozen by the prereg — raising any is a risk EXPANSION)

| Knob | Value | Where |
|---|---|---|
| qty per entry | **exactly 3** (Rule 6 min; `risk.max_contracts` hard clamp in the executor) | `params.risk` |
| affordability cap | **30%** of equity (Rule 6 Safe value) — NOT the risk control, only what lets `size_entry` afford a 3-lot; the accounts are **$5,000 each** (verified 2026-09-04, not the $100K the prereg assumed), so a 3-lot is affordable up to a ~$5 premium and a pricier name (TSLA ~$5.5) is refused, never rounded up | `params.risk.per_trade_risk_cap_pct` |
| concurrent positions | 1 per arm | `params.risk.max_concurrent_positions` |
| daily kill | 1% of equity → blocks NEW entries; exits + flatten always run | `params.risk.daily_loss_kill_switch_pct` |
| entry window | 09:35–14:30 ET | `params.tick_cadence.last_entry_et` |
| exits (0DTE = expiry day) | soft time stop 14:45 · hard 14:50 · DNE sweep 14:55 · flatten task 14:52 | `params.flatten_schedule_et` |
| exit shape | TP1 +45% / sell 50% · runner 1.75× · trail 20% off HWM · lock arms +15% · catastrophe −50% · theta budget 30% bleed w/o ≥0.5 ATR progress | `params.exits` — **COPIED_FROM_SPY_ENGINE_UNVALIDATED_ON_THESE_NAMES**; this window measures them |
| feed | indicative (no OPRA) — every spread and fill carries the label | `params.entry.liquidity_gate.feed` |
| premium floor | mid ≥ **$0.20** (added pre-window from the 2026-09-04 review: a sub-$0.20 0DTE contract × 3 is lottery noise; absent = off, so multi-1 is unchanged) | `params.entry.liquidity_gate.min_premium_dollars` |

## 5. Separation and safety — the invariants

- **Paper only, permanently.** `multi/lib/creds.py` raises on any base_url without `paper`.
  `live:false` is not a knob. OP-0 #1 is J's alone.
- **`multi/core.py` still has NO order path** — `test_multi_core.py` parses its AST for
  `place_bracket`/`market_sell`/`armed=`. Orders exist only in `multi/execute.py` and
  `multi/tickers_flatten.py`.
- **Config freeze** (2026-08-31 → 2026-10-30): `backtest/lib/filters.py` is imported, never
  edited. No SPY params, no `accounts.json`, no `heartbeat_core.py`.
- **Per-arm state** under `automation/state/tickers/<arm>/` (exit-state, level-states, ledger,
  cascade, day file, account pin). Journal `journal/trades-tickers-<arm>.csv`. Nothing shared
  with `automation/state/multi/`, `fleet/`, or `crypto-twin/`.
- **Secrets**: `automation/state/tickers/secrets.json` (gitignored, `.gitignore:388`, verified
  before the file existed). Template `secrets.json.example`. J pastes; the rig's write-time
  credential guard blocks a session from writing a key literal and it is not defeated.

## 6. Revoke — one line each

- Stop new entries now: set `"shadow_only": true` in `automation/state/tickers/params.json`
  (takes effect next tick; exits and the flatten still run).
- Stop everything: `Unregister-ScheduledTask Gamma_TickersLane -Confirm:$false` (and the flatten
  task if positions are already flat).
- Day-check only: `Unregister-ScheduledTask Gamma_TickersDayCheck -Confirm:$false` (it never trades).
- Undo the code: `git revert <sha>` per commit (all listed in the goal file's PROGRESS LOG).

## 7. What the evidence has to clear (prereg, verbatim rule)

≥20 scored trading days **and** ≥30 fills **per arm** before any verdict. PASS per arm = PF
CI-lower(2.5%) > 1.0 as-traded **and** ex-best-day **and** cost-adjusted (go_live_gate's own
method) **and** the signed-return control beats the random-entry null MAX at +30 min. FAIL flips
that arm to shadow. 3% cumulative loss before the minimums = early money-kill, disclosed as such.
A pass authorizes more paper and a promotion instrument — **never live**.

## 8. Known limitations, stated up front

- The 58.23% live SPY figure reflects live curated levels / trendlines / level memory this lane
  does not have. If the edge lives there, it will not travel here — and that is a finding.
- A −50% catastrophe cap checked every 2 minutes can overshoot on a fast single name.
- Alpaca's expiration-day cutoff for single-name options (~15:15 ET) forces a 14:45 soft stop —
  earlier than the SPY arms' 15:50, so the hold window is shorter.
- The prereg assumed fresh $100K accounts; they are $5,000 each (verified 03:5x ET 2026-09-04). Sizing pressure therefore exists here too, and the frozen 1% daily kill ($50) means one losing 3-lot ends an arm's day.

## 9. Log

- 2026-09-04 ~01:00 ET — opened. Prereg + foundation `5062ea52`. Scorer adapter and executor
  building. Found: `install-multi-core.ps1` registered `Gamma_MultiCore` at local 09:35 = 11:35 ET
  (the 2h scar); the tickers installers use local 07:35.
- 2026-09-04 ~02:00 ET -- registered (`Gamma_TickersLane` 09:35 ET/PT2M, `Gamma_TickersEodFlatten` 14:52 ET). Shadow E2E probe x3 on a real account found and fixed two day-one blockers (sector buckets fail-closed; 2% cap could not afford 3 contracts) and proved the last mile (NVDA 0DTE put, 39 -> 3, limit ask+0.01, nothing sent). Two core.py bugs fixed on the way: WOULD_PLACE qty=None (would have blocked every entry) and the triggers key. Human step remaining: paste secrets, run `python multi/tickers_verify.py`.
- 2026-09-04 02:42 ET -- adversarial review of the executor: 2 BLOCKERs (exit qty was the ORIGINAL entry qty, never broker truth -- after TP1 every SELL_ALL would have been rejected; unconfirmed/partial orders were left resting with the id discarded, so the next tick could stack a second entry), 1 HIGH (theta budget compared an intraday entry against YESTERDAY's close), 2 MED (no lane/flatten lock; no premium floor), 2 LOW. All fixed on two builders with disjoint files + a market-clock gate for Monday's Labor Day holiday, then a fourth shadow E2E probe on the merged build: NVDA WOULD_PLACE qty 3 -> SHADOW_ENTRY_PREVIEW, 14s. T6 instrumented (`Gamma_TickersDayCheck`). Follow-up named, not done: split execute.py's pure helpers into multi/lib/tickers_order_lifecycle.py (1,2xx lines > 800 guideline).
- 2026-09-04 08:35 ET -- creds loaded + verified (tickers_verify.py 03:5x ET: tickers-1 PA39FKBSPLPR / tickers-2 PA3K6MNSXGE6 / tickers-3 PA3RBOSIUBTR -- equity $5,000 each, buying_power 20,000, options_approved_level 3, ACTIVE; account pins written). J: use the pasted paper keys as-is. $5K accounts -> affordability cap 0.30. Per-arm runtime dirs gitignored.
