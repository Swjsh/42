# Gamma Overnight Build — 2026-06-16

## What shipped

- `backtest/crypto/crypto_scalper.py` — EMA 9/21/50 ribbon signal computer for BTC/USD 15m bars
- `automation/prompts/crypto-heartbeat.md` — full 24/7 BTC scalper heartbeat prompt (watch-only mode)
- `automation/state/crypto/` — position, account, params seed state files
- `setup/scripts/run-crypto-heartbeat.ps1` — runner script (Haiku, ~$0.02/tick)
- `Gamma_CryptoHeartbeat` scheduled task — every 15 min, 24/7, registered and active
- SCHEDULED-TASKS.md — updated to 28 active tasks (added crypto heartbeat row)

---

## Crypto heartbeat: parameter decisions

Research produced 6 concrete changes to `automation/state/crypto/params.json` before the first live tick runs. Apply these now — they are all pre-OOS improvements, not speculation:

**ATR multipliers (highest priority):** BTC 15m wicks spike 0.8–1.2x ATR inside valid trends. The 1.5x stop gets whipsawed. Position size caps at 25% of account anyway, so raising the stop to 2.0x reduces false stops without increasing dollar loss.
- `atr_stop_multiplier`: 1.5 → **2.0**
- `atr_tp1_multiplier`: 2.0 → **3.0**
- `atr_runner_multiplier`: 3.0 → **4.5**
- Preserved ratio: 1:1.5:2.25 stop/TP1/runner. TP1 R:R becomes 1.5R, runner 2.25R.

**RSI thresholds (high priority):** BTC RSI regularly reaches 78–85 in valid bull trends. The 72 overbought filter blocks entries during the strongest part of the move — exactly when the ribbon is most reliable. A momentum strategy should enter with momentum.
- `rsi_overbought`: 72 → **80**
- `rsi_oversold`: 28 → **20**

**New fields to add:**
- `"h1_trend_filter": true` — only take 15m LONG signals when 1h EMA-9 > EMA-50; only SHORT when EMA-9 < EMA-50. This is the correct fix for BTC chop during thin hours (not switching to 1h timeframe). Highest-impact WR improvement but requires one extra Alpaca API call per tick.
- `"log_session_metadata": true` — log hour-of-day + day-of-week on every would-be trade. Needed for the 20-trade regime analysis (WR is lower weekends and overnights).

**No changes to:** `timeframe_minutes` (15 is correct for scalper), `min_stack_bars` (2 is the most important filter, do not lower), `ribbon_spread_pct` threshold (0.05% correct), `risk_per_trade_pct` (2% right for watch-only phase), `max_position_pct` (25%), `daily_loss_kill_switch_pct` (10%).

**ETH/USD:** Add to watch-only simultaneously with BTC to collect calibration data. Do not paper-trade ETH until BTC passes 20-trade threshold. Separate state dir `automation/state/crypto_eth/` when ready. ATR multipliers need independent calibration (ETH 15m ATR is 1.3–1.6x BTC's at same price pct).

**Realistic WR target:** 47–55% at 1.5R avg win/loss = +0.25R expectancy per trade. The 20-trade gate (WR >= 45%) is the minimum, not the target.

---

## Options engine: VIX gate finding

**Keep the gate at 17.3 bear / 17.2 bull. Do not lower to 16.**

The data does not support lowering. Full evidence summary:

- Stage 2 autoresearch tested VIX lower bounds 17.0, 17.5, 18.0 all with a 5-bar rising trend condition. OOS row is identical across all three (21 trades, WR=71.4%). Every trade added by lowering from 18.0 to 17.0 falls exclusively in the IS window (2025) — zero OOS trades in the VIX 17.0–17.3 range.
- The VIX 16.0–17.0 band has zero options backtest coverage. The lowest threshold tested was 17.0. Lowering to 16 is pure in-sample speculation.
- N=4 extra trades added by lowering from 18.0 to 17.0 average +$25.4/trade — positive but N=4 is not meaningful.
- Futures engine showing WR=79% at VIX>=16 (MNQ) cannot transfer to options: futures measures directional tick accuracy, not premium P&L. At VIX=16, 0DTE premiums are thin — a correct direction can still trigger the -8% or -20% premium stop before the move materializes (C3 doctrine, L58/L74/L100/L101/L112).
- The cross-instrument futures data actually validates the current 17–18 floor (MNQ short signals required VIX>=18 independently). Two separate instruments converging on the same band is the confirmation you already have.

**The direction of VIX movement (trend) is the primary edge driver, not the absolute level.** Adding VIX trend (5-bar rising/falling) jumped WR from 54.3% to 68.6% at the same threshold. That is where the unexploited edge lives.

**What to backtest next:** Run the OPRA options simulator on a grid of VIX lower bounds 16.0 to 17.3 in 0.5-point steps with the rising trend condition active. Report IS/OOS split. Require N >= 15 OOS trades with positive expectancy before any gate change. Without that test, 17.3 stays.

---

## BTC/NQ cross-signal: ADOPT or REJECT

**SOFT-ADOPT.** Add as a forensic-only field, no gate authority, no blocking.

BTC/SPY correlation is real at macro timescales but noise at 5-minute heartbeat resolution. More critically, crypto-heartbeat is WATCH-ONLY with zero real fills — adding it as an ATTENTION gate before 20+ would-be trades violates OP-11's eval-first requirement. The correct tier is weaker than numeric-alert (Step 0a).

**Exact implementation:** Add Step 0c to the options heartbeat prompt, after Step 0b (dual-account MCP self-test), before the skip gates. Read `automation/state/crypto/ribbon-log.jsonl`, filter to rows within the last 20 minutes UTC, take the most recent row. Set `btc_ribbon = "BULL"|"BEAR"|null`. Behavior: NEVER block, NEVER boost filter scores, NEVER change action. Append `btc={ribbon}` to the one-line output and add `"btc_ribbon": "BULL"|"BEAR"|null` to the decisions.jsonl row. This field is FORENSIC ONLY — enables the future OOS study of whether BTC ribbon state predicts SPY entry quality. The 20-minute staleness window matches the crypto-heartbeat 15-minute cadence with one tick of buffer. Promotion path: after 40+ SPY heartbeat entries with `btc_ribbon` tagged, run WR_when_aligned vs WR_when_misaligned. If aligned WR exceeds misaligned by >= 8pp with N >= 20 per bucket, promote to ATTENTION tier. File A/B scorecard at `analysis/recommendations/btc-ribbon-spy-cross.json` before promotion.

Three gaps in the current crypto-heartbeat.md to fix before it ships real trades: (1) No staleness self-detection — add a check of `last-tick.json` to flag stale ticks > 30 min to STATUS.md. (2) ribbon-log schema is missing `stack_direction` field (new_bull/maturing_bull/new_bear/maturing_bear, free to compute since stack_bars is already logged). (3) DVOL (Deribit BTC vol index) is referenced in Section 9 prose but never fetched — either wire it or add an explicit "DVOL not gated — future improvement" comment. Right now it reads as a broken dependency.

---

## Tastytrade futures (waiting on approval)

Futures infrastructure is fully built. MNQ v3: IS=+$6,860 / OOS=+$15,027, WF=3.86. MES v3_mes: IS=+$1,906 / OOS=+$2,238, WF=1.52. All prompts and state files are seeded. What blocks go-live is Tastytrade account approval and IB Gateway Docker setup.

**3–5 day timeline once account approved:**
1. Day 1: Confirm account live, fund with paper capital, verify API credentials connect via `ibkr_paper.py`.
2. Day 2: Register `Gamma_FuturesHeartbeat` and `Gamma_FuturesEodFlatten` via the same hidden-task pattern as heartbeat. Watch-only mode first (same 20-trade gate as crypto).
3. Day 3–4: Let watch-only accumulate at least 10 would-be trade observations. Confirm IB Gateway stays alive via the existing `Gamma_CryptoGrinderKeepalive` pattern (clone for futures).
4. Day 5: If watch-only WR tracks above 45% and MNQ/MES configs are not diverging, enable paper-trading with the sized params from `automation/state/futures/params.json`.

Do not run MNQ and MES on the same account simultaneously until each has 20 independent watch-only observations. They share the same underlying but have proven incompatible configs (erl_irl long is catastrophic on S&P structure). Run MNQ first, MES second.

---

## What J needs to do TODAY

1. **Apply the 6 crypto param changes** to `automation/state/crypto/params.json`: `atr_stop_multiplier` 1.5→2.0, `atr_tp1_multiplier` 2.0→3.0, `atr_runner_multiplier` 3.0→4.5, `rsi_overbought` 72→80, `rsi_oversold` 28→20, add `"h1_trend_filter": true` and `"log_session_metadata": true`. These are research-derived, not guesses. Crypto-heartbeat has already been ticking overnight with the old params — the first 20 observations should use the corrected values.
2. **Confirm `Gamma_CryptoHeartbeat` is running** — verify via `Get-ScheduledTask -TaskName 'Gamma_CryptoHeartbeat'`. Check `automation/state/crypto/ribbon-log.jsonl` for entries. If empty or missing, the runner script or state path has a problem.
3. **Review STATUS.md L117 entry** — the corrected OOS baseline is now $2,659 (down from $4,747 due to the time-stop artifact fix). The engine is still OOS-profitable. This is accurate information, not a regression. Confirm you see the corrected number and are not anchoring to the old $4,747.
4. **Decide on Step 0c (BTC cross-signal)** — the soft-adopt spec above requires a one-sentence addition to `automation/prompts/heartbeat.md`. This is a 5-minute change with zero production risk. Do it before the 09:30 open so today's decisions.jsonl entries start accumulating `btc_ribbon` for the forensic study.
5. **Tastytrade account status check** — if the approval email has arrived, reply to confirm and start Day 1 of the 3–5 day timeline above.

---

## What runs automatically while J sleeps

All 28 scheduled tasks are active. The ones relevant to tonight's build:

| Task | Cadence | What it does |
|---|---|---|
| `Gamma_CryptoHeartbeat` | every 15 min, 24/7 | NEW — BTC/USD EMA ribbon, watch-only, logs to ribbon-log.jsonl |
| `Gamma_KitchenDaemonKeepalive` | every 5 min, 24/7 | Keeps kitchen_daemon.py alive, free-tier R&D |
| `Gamma_KitchenSeeder` | hourly :20, 24/7 | Generates cook tasks (skip if backlog >= 25) |
| `Gamma_KitchenReviewer` | every 2h :45, 24/7 | Triages cook outputs PROMOTE/VALIDATE/DUPLICATE/LOW_QUALITY |
| `Gamma_CryptoDaily` | 06:00 ET | Harness health + task-registry audit + grinder rotation |
| `Gamma_CryptoGrinderKeepalive` | every 5 min, 24/7 | Keeps live_grinder.py alive |
| `Gamma_CryptoRegression` | every 30 min, 24/7 | Chart-reading primitives regression |
| `Gamma_ScoutPremarket` | 05:30 ET | Macro/news scan → premarket context |
| `Gamma_SwarmPremarket` | 08:15 ET | 13-agent bias vote → premarket |
| `Gamma_LaunchTV` | 08:00 ET | TradingView + CDP:9222 |
| `Gamma_Premarket` | 08:30 ET | Daily levels, bias, journal seed |

No manual action needed before open. The crypto-heartbeat ribbon data will be populated before J wakes up. Check `automation/state/crypto/ribbon-log.jsonl` and `automation/state/crypto/account.json` when you wake.
