# Futures Premarket — Gamma Futures Edition

> **When:** 08:30–09:30 ET daily
> **Purpose:** Establish key levels, bias, and risk budget before the first heartbeat tick.
> **Outputs:** `automation/state/futures/key-levels.json`, `journal/futures/YYYY-MM-DD.md` (bias section)
>
> **Futures mentality (read once):** [`docs/futures/README.md`](../../docs/futures/README.md). Futures are NOT 0DTE options — linear point-based P&L, no daily expiry, leverage via margin, cash-settled (no assignment). Stops are in POINTS not premium %. Levels are in index points (MNQ ~21,000–30,000 range).

---

## 0. Pre-checks

1. Read `automation/state/futures/account.json` — confirm equity and kill-switch floor.
2. Read `automation/state/futures/risk.json` — confirm PropAccount type and daily loss limit.
3. Read `automation/state/futures/position.json` — must show `"side": "flat"` before market open.

---

## 1. Pull futures bars (TradingView MCP)

```
chart_set_symbol("CME_MINI:MNQ1!")        # or MES1!
data_get_ohlcv(count=15, summary=true)    # ~15 days of context
```

Read the overnight range (Globex) — not included in RTH sim but context for gap assessment.

---

## 2. Identify key levels

**Standard levels to identify (same framework as SPY):**
- Prior day high (PDH) / prior day low (PDL)
- Prior week high (PWH) / prior week low (PWL)
- Overnight high (ONH) / overnight low (ONL) — relevant for gap trades
- Session VWAP (from MNQ/MES chart)
- Major round numbers (nearest 100pt below/above current price)
- Any visible swing highs/lows with 3+ touches

**VIX context:**
```
chart_set_symbol("TVC:VIX")
quote_get → current VIX level
data_get_ohlcv(count=5) → prior 5-day VIX range
```
- VIX >= 18: strategies engage (v3 / v3_mes config gate)
- VIX < 18: most signals blocked by config — log `VIX_GATE_LOW`, watch-only day

---

## 3. Write key-levels.json

```json
{
  "date": "2026-06-17",
  "instrument": "MNQ",
  "levels": [
    {"label": "PDH", "price": 21580.0, "rank": 2, "notes": "prior day session high"},
    {"label": "PDL", "price": 21350.0, "rank": 2, "notes": "prior day session low"},
    {"label": "ONH", "price": 21620.0, "rank": 1, "notes": "overnight Globex high"},
    {"label": "ONL", "price": 21310.0, "rank": 1, "notes": "overnight Globex low"},
    {"label": "PWH", "price": 21750.0, "rank": 3, "notes": "prior week high"},
    {"label": "R100", "price": 21600.0, "rank": 1, "notes": "round number resistance"},
    {"label": "S100", "price": 21400.0, "rank": 1, "notes": "round number support"}
  ],
  "vix": 20.3,
  "vix_5d_avg": 21.1,
  "vix_gate": true,
  "overnight_gap_pts": -30.0,
  "bias": "bearish",
  "bias_reason": "Gap below PDL, VIX elevated, overnight failed to reclaim ONH"
}
```

Write to `automation/state/futures/key-levels.json`.

---

## 4. Write bias to journal

Open `journal/futures/YYYY-MM-DD.md`:
```
# Futures — 2026-06-17

## Pre-market bias (08:30 ET)
**Instrument:** MNQ
**VIX:** 20.3 (gate: YES)
**Bias:** BEARISH — gap below PDL, overnight sellers, VIX above 20
**Key levels:** PDH=21580, PDL=21350, ONH=21620, ONL=21310

**Falsifiable hypothesis:** If MNQ reclaims ONL=21310 and holds as support by 10:00, the gap fill may be complete → bias shifts neutral.

## Trades
(populated by heartbeat)

## EOD reflection
(populated after 15:55)
```

---

## 4b. Rollover-week awareness check

Equity index futures roll quarterly: 3rd Friday of **Mar (H) / Jun (M) / Sep (U) / Dec (Z)**. Liquidity migrates to the next month ~8 days early ("Rollover Thursday" = 2nd Thursday before the 3rd Friday). See [`docs/futures/SESSIONS-ROLLOVER-TAX.md`](../../docs/futures/SESSIONS-ROLLOVER-TAX.md).

- Compute days-to-3rd-Friday for the current quarter month.
- If within **10 days of expiry** OR past Rollover Thursday: append `ROLLOVER_WEEK: front month {code} expires {date}; volume migrating to {next code}` to the journal bias section. Levels from the expiring contract may be thinning — treat with lower confidence; the `MNQ1!` chart auto-rolls but verify the heartbeat's broker orders route to the active month.
- Otherwise: note `ROLLOVER_OK: {N} days to expiry`.

## 5. Risk budget

- Start-of-day equity from `account.json`
- Kill-switch floor: equity − daily_loss_limit (from account.json). Current sandbox: $2K start, floor $1,600, daily limit −$200.
- Number of allowed trades today: conservative = 3 (1 per signal tier)
- **PDT status: N/A for futures** — the Pattern Day Trader rule does NOT apply to futures (it's an equities/options rule). Unlimited intraday round-trips. (See [`docs/futures/README.md`](../../docs/futures/README.md).)
- **Position sizing rule:** size so `stop_distance_points × point_value × qty ≤ per-trade $ risk cap`. MNQ point_value=$2, MES=$5. Size by what the STOP allows, never by what margin allows. See [`docs/futures/MARGIN-LEVERAGE-RISK.md`](../../docs/futures/MARGIN-LEVERAGE-RISK.md).

---

## Differences from SPY premarket

| Feature | SPY premarket | Futures premarket |
|---|---|---|
| Levels | SPY price ($700–780) | MNQ index points (21000–22000) |
| Gap | SPY gap in $ | Futures gap in index points |
| Overnight | ES/NQ overnight as proxy | Direct MNQ/MES overnight via CME_MINI chart |
| VIX gate | Not blocking (SPY has VIX regime gates per-signal) | VIX < 18 blocks most signals — note explicitly |
| Journal path | `journal/YYYY-MM-DD.md` | `journal/futures/YYYY-MM-DD.md` |
