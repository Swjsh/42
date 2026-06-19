# Futures Heartbeat — Gamma Futures Edition

> **Instrument:** MNQ (Micro E-mini Nasdaq) OR MES (Micro E-mini S&P 500)
> **Venue:** Tastytrade sandbox (paper) account — `pip install tastytrade`
> **Strategy:** Same watcher fleet as SPY engine; futures P&L (no theta, linear)
> **Config:** INSTRUMENT-SPECIFIC — see Section 3 below
> **Status:** WATCH-ONLY (paper). Live requires J's explicit ratification.
>
> CRITICAL: MNQ and MES require SEPARATE strategy configs. The same config applied to
> both instruments destroys edge on MES (erl_irl long is -$5,788 on real MES data).
> This heartbeat MIRRORS `automation/prompts/heartbeat.md` — same tick structure,
> same signal logic, same journaling. Only what changes: symbol, P&L math, broker.
>
> FUTURES MENTALITY ([`docs/futures/README.md`](../../docs/futures/README.md)): P&L is LINEAR and point-based — no
> theta, no premium decay. Stops/targets in POINTS, never premium %. pnl_usd =
> points × point_value × qty (MNQ $2/pt, MES $5/pt). Cash-settled, NO assignment risk.
> Flat-by-close is risk management (avoid overnight margin), NOT expiry defense.

---

## 0. Pre-tick safety checks (every fire)

**BEFORE reading the chart:**
1. Read `automation/state/futures/position.json` — current futures position state.
2. Check `automation/state/futures/account.json` — equity, daily P&L, drawdown floor.
3. Verify Tastytrade connection: `broker.connect()` (from `futures.tastytrade_paper import TastytradeBroker`). If fails → LOG, skip tick, update STATUS.
4. Confirm it is NOT 15:55–16:00 ET (EOD flatten window, handled by futures-eod-flatten.md).

**Kill switch check (PropAccount):**
- Load `automation/state/futures/risk.json` (daily start equity, peak equity, floor).
- If `equity <= floor` → HALT, log `KILL_SWITCH_TRIGGERED`, notify.
- If `daily_loss >= daily_loss_limit` → HALT.

---

## 1. Read the chart (MNQ or MES, configurable)

```
chart_set_symbol("CME_MINI:MNQ1!")          # or MES1! — from TV_SYMBOL map
data_get_ohlcv(count=3, summary=true)       # R1 fix: discard bar[-1] (in-progress)
data_get_study_values                       # EMA ribbon (fast/pivot/slow)
chart_set_symbol("TVC:VIX") + quote_get    # VIX level
restore chart_set_symbol("CME_MINI:MNQ1!")
```

**Closed-bar rule (R1):** bar is closed iff `bar_open_time + 5min <= now_et`. Discard index[-1].

---

## 2. Build context (same as SPY heartbeat)

- Compute ribbon state (fast/pivot/slow, stack direction, spread_pts).
  - **NOTE:** Ribbon spread is in INDEX POINTS (not cents). For MNQ ~21,000, a 20pt spread
    = ~0.1% move. Adjust `spread_cents` threshold proportionally: old SPY threshold 50c ≈ MNQ 5pt.
- Read key levels from `automation/state/futures/key-levels.json` (pre-market populated).
- VIX: current level, trend vs prior session.
- HTF: on GAMMA_HTF_TICK, switch to 15m, get 2 bars, restore 5m.

**ORB note:** ORB watcher was tested on 18 months of futures data and found NOT viable.
- MNQ: N=5 total, WR=40%, OOS=0 signals → Gate FAIL. OR gate blocks 94% of days (SPY-calibrated 2pt gate maps to ~69pts; MNQ typical OR=100-200pts).
- MES: N=22 total, WR=59% — OOS gate pending; even if PASS, N too small for production.
- Decision: DO NOT call `set_futures_range_scale()` in this heartbeat. ORB is excluded from both v3 and v3_mes configs. No ORB setup needed.

---

## 3. Entry logic — INSTRUMENT-SPECIFIC curated config rules

**Entry gate:** same structure as SPY heartbeat. Position must be FLAT (verify via IBKR, not just local state — ghost prevention, L76).

**MNQ config** (`strategy_config_v3.py`). IS=+$6,860 / OOS=+$15,027. WF PASS.
```
erl_irl_watcher         long  high   VIX>=16   → WR=79%, $37/trade — #1 MNQ edge
shotgun_scalper_watcher long  medium VIX>=16   → WR=73%, +$3,794 full period
shotgun_scalper_watcher long  high   VIX>=16   → WR=68%, +$2,644 full period
shotgun_scalper_watcher short high   VIX>=16   → WR=67%, +$2,486 (Nasdaq shorts work)
tbr_high_vol_watcher    long  medium VIX>=16   → WR=71%
tbr_high_vol_watcher    short medium VIX>=16   → WR=71%
erl_irl_watcher         short medium 16<=VIX<22
v14_enhanced_watcher    short medium VIX>=18
v14_enhanced_watcher    short high   VIX>=18
```

**MES config** (`strategy_config_v3_mes.py`). IS=+$1,906 / OOS=+$2,238. WF PASS (1.52).
⚠️ +2 tick stress: only +$664 — thin edge. Start paper with MNQ; add MES after fleet validates.
⚠️ DO NOT use MNQ config on MES — erl_irl long destroys $5,788 on real S&P bars.
```
shotgun_scalper_watcher long  high   VIX>=16   → WR=64%, $35/trade — #1 MES edge
v14_enhanced_watcher    short high   VIX>=18   → WR=64%, $24/trade
tbr_high_vol_watcher    short medium VIX>=16   → WR=58%, $2/trade
v14_enhanced_watcher    short medium VIX>=18   → WR=30%, $5.6/trade (asymmetric R:R)
```

**Select config at runtime:**
```python
from futures.strategy_config_v3     import should_take as should_take_v3
from futures.strategy_config_v3_mes import should_take_v3_mes
config_fn = should_take_v3 if INSTRUMENT == "MNQ" else should_take_v3_mes
```

**Sizing (futures):**
- Read current equity: `broker.get_account_equity()` or fall back to `account.json`.
- Stop distance in points (from watcher's `stop_price`).
- `size_contracts = floor(equity * 0.02 / (stop_pts * point_value))` → min 1, max per prop rules.
- For paper trading: fix qty=3 until account grows to justify dynamic sizing.

**Order:** bracket order via TastytradeBroker:
```python
from futures.tastytrade_paper import TastytradeBroker
broker = TastytradeBroker()
broker.connect()
order_ids = broker.place_bracket(
    instrument=INSTRUMENT,          # "MNQ" or "MES"
    side="BUY" if direction=="long" else "SELL",
    qty=qty,
    entry_price=entry,
    tp1_price=tp1,
    stop_price=stop,
    runner_price=runner,            # optional
    tp1_qty=tp1_q,                  # optional, defaults to qty//2
)
```
Places: entry LIMIT (DAY) + TP1 LIMIT (GTC) + STOP (GTC) as 3 separate orders.
On TP1 fill: cancel the full-qty stop, place new stop at break-even for runner.

---

## 4. Position management

**While holding:**
- Check current price vs TP1 / stop each tick.
- After TP1 fills: cancel stop, place new stop at break-even (entry).
- Runner target: watcher's `runner_price` (or entry + 2.5 * (entry - stop) for longs).
- Hard time stop: 15:50 ET — close all. Futures EOD flatten at 15:55.

**TP1 split:** tp1_qty_fraction = 0.5 (same as options engine).

---

## 5. Journaling (same format as SPY engine)

Write to `journal/futures/YYYY-MM-DD.md` and `journal/futures/trades.csv`.
Every entry: timestamp, instrument, direction, entry, stop, tp1, runner, qty, thesis.
Every exit: fill price, P&L (points + dollars), outcome.
Update `automation/state/futures/position.json` and `automation/state/futures/account.json`.

---

## 6. Output (each tick)

```json
{
  "tick_time": "2026-06-16T10:30:00",
  "instrument": "MNQ",
  "price": 21450.25,
  "vix": 17.5,
  "ribbon": "BULL",
  "action": "HOLD_FLAT | ENTER_LONG | HOLD_RUNNER | EXIT_TP1",
  "signal": null,
  "position": {"side": "long", "qty": 3, "entry": 21420.0, "stop": 21390.0},
  "account": {"equity": 5000, "daily_pnl": 120.0, "floor": 4500}
}
```

---

## 7. What WATCH-ONLY mode means

Currently set to WATCH-ONLY:
- All entry/exit logic runs.
- Orders are NOT placed (comment out the `ib.placeOrder` calls).
- Log every would-be trade to `journal/futures/would-be-trades.jsonl`.
- After 20+ would-be trades with positive expectancy → J ratifies for paper live.
- After 3+ paper live wins → J ratifies for real money.

---

## 8. Differences from SPY heartbeat

| Feature | SPY options heartbeat | Futures heartbeat |
|---|---|---|
| Symbol | BATS:SPY | CME_MINI:MNQ1! |
| P&L math | BS-sim / options pricing | Linear points × $2/pt (MNQ) |
| Stop type | % premium | Fixed index points |
| Theta | Yes (decay hurts) | None |
| Broker | Alpaca paper | IBKR paper (port 4002) |
| Kill switch | -30% equity/day | PropAccount floor (EOD trailing) |
| Sizing | OTM-2 strikes | Contracts via risk.py |
| EOD flatten | 15:50 ET | 15:50 ET (same) |
| Overnight | Not applicable | Flat by EOD for now |
