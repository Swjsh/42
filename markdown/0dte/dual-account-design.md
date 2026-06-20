# Dual-Account Design — Project Gamma

> **Effective:** 2026-05-18 (both accounts reset/seeded on this date)
> **Ratified:** 2026-05-14 by J
> **Canonical configs:** [`automation/state/params_safe.json`](../automation/state/params_safe.json) · [`automation/state/params_bold.json`](../automation/state/params_bold.json)
> **Why this exists:** Controlled A/B experiment. Same signal engine, two expression layers. Equal capital. Real trading data to build the account-scaling doctrine we don't yet have evidence for.

---

## Why Two Accounts

The single-account model can't answer the question that matters most for scaling:

> *At $1K–$25K, what risk profile — tight stops / early TP vs wide stops / late TP — produces better compounding?*

Backtests can't answer it cleanly (sim artifacts, survivorship bias). Paper trading ONE style gives you one data point. Running BOTH simultaneously on identical signals gives you **paired observations** — same day, same setup, different expression, different outcome.

After 20+ trading days (~4 weeks), the log becomes the empirical foundation for:
- Which risk profile reaches the 45% WR / positive expectancy live-deployment threshold first
- Whether ATM or ITM-2 compounds better at the $1K tier
- Whether +30% TP1 or +75% TP1 produces better expectancy at low account size
- The real drawdown profile of each style (not backtested, not simulated — lived)

---

## Account Definitions

### Account 1 — Gamma-Safe

| Attribute | Value |
|---|---|
| **Alpaca alias** | `alpaca` (current credentials in `~/.claude/.mcp.json`, reset 5/18) |
| **Starting equity** | $1,000 |
| **Config file** | `automation/state/params_safe.json` |
| **Position state** | `automation/state/current-position-safe.json` |
| **Philosophy** | Capital preservation. Win rate over raw P&L. Never blow up before the lesson is learned. |

**Parameter table:**

| Parameter | Safe Value | Base (params.json) | Why |
|---|---|---|---|
| `per_trade_risk_cap_pct` | **30%** | 50% | Lose 3 in a row without hitting kill switch |
| `daily_loss_kill_switch_pct` | **−30%** | −50% | Tighter — $300 max daily loss on $1K |
| `premium_stop_pct` | **−8% (symmetric)** | −8% bear / −5% bull | No asymmetry complexity |
| `tp1_premium_pct` | **+30%** | +75% | Take profit early; prioritize WR |
| `tp1_qty_fraction` | **0.667** (2 of 3) | 0.333 | Get paid early; 1 runner only |
| `runner_target_pct` | **2.0×** | 5.0× | Runner to 2× entry premium then trail |
| `entry_gate_et` | **10:00** | 09:35 | Fully formed market context |
| `no_trade_window` | **14:00–15:00 ET** | 13:45–15:45 ET | Narrower rest window |
| `strike_offset` | **ATM (0)** | ITM-2 | delta ~0.50; no gamma leverage risk |
| `vix_bull_max` | **17.20** | 20.00 | Only calls in genuinely low-vol regime |
| `vix_bear_min` | **17.30** | 15.00 | Only puts in genuinely elevated regime |
| `vix_hard_cap` | **22.00** | 30.00 | Current standard cap |
| `confluence_min` | **2 of 3** | 1 of 3 | Level + ribbon required; no single triggers |
| `setups_allowed` | **CONFIRMED only** | ALL | BEARISH_REJECTION + BULLISH_RECLAIM only |
| `quality_gate_min` | **BASE** | WATCH | No draft or watch-only setups |

**Sizing math at $1K:**
- Max capital per trade: $1,000 × 30% = **$300**
- ATM premium $1.00 → 3 contracts ($300 / $100) ✅
- ATM premium $1.50 → 2 contracts ($300 / $150) → below min-3 floor → **skip or wait for better premium**
- ATM premium $0.75 → 4 contracts ($300 / $75) → cap at 5 ✅

---

### Account 2 — Gamma-Bold

| Attribute | Value |
|---|---|
| **Alpaca alias** | `alpaca_aggressive` (already in `~/.claude/.mcp.json` as of 5/14) |
| **Starting equity** | $1,000 |
| **Config file** | `automation/state/params_bold.json` |
| **Position state** | `automation/state/current-position-bold.json` |
| **Philosophy** | Max P&L when signals are right. Expect bigger drawdowns. The account WILL blow up faster on bad days — that's the data. Document every blowup so we know what NOT to do at $25K. |

**Parameter table:**

| Parameter | Bold Value | Base (params.json) | Why |
|---|---|---|---|
| `per_trade_risk_cap_pct` | **50%** | 50% | Full risk — one max loss = day done |
| `daily_loss_kill_switch_pct` | **−50%** | −50% | Standard kill switch |
| `premium_stop_pct_bear` | **−15%** | −8% | Room for puts to breathe (v15 doctrine) |
| `premium_stop_pct_bull` | **−5%** | −5% | Calls fail fast |
| `tp1_premium_pct` | **+75%** | +75% | Let winners develop |
| `tp1_qty_fraction` | **0.333** (1 of 3) | 0.333 | Take 1 off; 2 runners ride |
| `runner_target_pct` | **5.0×** | 5.0× | Ribbon ride to 5× premium |
| `entry_gate_et` | **09:35** | 09:35 | v15 gate — catches gap fills and ORB |
| `no_trade_window` | **13:45–15:45 ET** | 13:45–15:45 ET | v15 window |
| `strike_offset` | **ITM-2** | ITM-2 | More delta, more P&L per SPY point |
| `vix_bull_max` | **20.00** | 20.00 | Mid-VIX calls allowed |
| `vix_bear_min` | **15.00** | 15.00 | Low-VIX puts allowed |
| `vix_hard_cap` | **30.00** | 30.00 | Active in vol spikes |
| `confluence_min` | **1 of 3** | 1 of 3 | Single trigger on ★★+ levels |
| `setups_allowed` | **ALL** | ALL | CONFIRMED + DRAFT + WATCH-ONLY |
| `quality_gate_min` | **WATCH** | WATCH | Every named setup Gamma knows |

**Sizing math at $1K:**
- Max capital per trade: $1,000 × 50% = **$500**
- ITM-2 premium $2.50 → 2 contracts ($500 / $250) ✅
- ITM-2 premium $1.50 → 3 contracts ($450 / $150) ✅
- ITM-2 premium $1.00 → 5 contracts ($500 / $100) → cap at 5 ✅

---

## Overlap Resolution

When the same setup fires for both accounts simultaneously (the highest-value case):

| Decision Point | Gamma-Safe | Gamma-Bold |
|---|---|---|
| **Strike** | ATM (offset 0) | ITM-2 (offset −2) |
| **Entry time** | 10:00 ET gate | 09:35 ET gate |
| **Stop** | −8% symmetric | −15% bear / −5% bull |
| **TP1 threshold** | +30% | +75% |
| **TP1 fraction** | 2 of 3 (67%) off | 1 of 3 (33%) off |
| **Runner target** | 2× entry premium | 5× entry premium |
| **Risk capital** | 30% of account | 50% of account |

**Both execute on the same tick.** Gamma places two independent bracket orders (one per Alpaca account). Both rows logged to `decisions.jsonl` with `account_id: safe` and `account_id: bold`.

**When Bold sees a setup Safe doesn't:** Bold enters; Safe holds. No cross-contamination. Safe's stricter filters protect it from DRAFT/WATCH-ONLY setups.

**When Safe sees a setup but Bold is already positioned:** Bold may skip the new setup (already in a position); Safe may still enter. Kill-switch isolation: Safe's −30% stop does NOT halt Bold (and vice versa).

---

## Infrastructure

### State Files

| File | Account |
|---|---|
| `automation/state/current-position-safe.json` | Gamma-Safe live position state |
| `automation/state/current-position-bold.json` | Gamma-Bold live position state |
| `automation/state/params_safe.json` | Safe parameter overrides |
| `automation/state/params_bold.json` | Bold parameter overrides |

### Heartbeat Processing (per tick)

```
For each account in [safe, bold]:
  1. Load params.json (base)
  2. Apply account overlay (params_{account}.json)
  3. Read current-position-{account}.json
  4. Check kill switch for this account only
  5. Evaluate filters with account-specific params
  6. If ENTER: place order via account-specific Alpaca keys
  7. Write position state to current-position-{account}.json
  8. Append to decisions.jsonl with account_id field
```

Kill switches are **fully isolated**: Safe's daily loss limit firing does NOT affect Bold's trading and vice versa.

### Journal Schema (effective 2026-05-18)

`journal/trades.csv` — new column `account_id` (values: `safe` | `bold`):
- All new rows include `account_id`
- Historical rows pre-5/18 have `account_id = safe` (legacy single-account = Safe equivalent)

`automation/state/decisions.jsonl` — new field `account_id` on every entry.

`automation/state/watcher-observations.jsonl` — new field `account_id`; Bold is the primary watcher vehicle.

### EOD Summary

Reports both accounts side by side:
- `safe_pnl_today`, `safe_equity_eod`, `safe_trades_today`, `safe_wr_today`
- `bold_pnl_today`, `bold_equity_eod`, `bold_trades_today`, `bold_wr_today`
- `divergence_flag`: true if |safe_pnl - bold_pnl| > 2× safe_daily_target (worth journaling)

### MCP Config

Both Alpaca MCP servers are **already configured** in `~/.claude/.mcp.json`:
- `alpaca` → Gamma-Safe → tools: `mcp__alpaca__*` (always available)
- `alpaca_aggressive` → Gamma-Bold → tools: `mcp__alpaca_aggressive__*` (available when server connects; REST fallback when not)

**Bold MCP self-test:** Heartbeat Step 0b probes `mcp__alpaca_aggressive__get_account_info` on tick 0. If unavailable, it sets `loop-state.bold_mcp_mode = "rest"` and uses direct REST API calls for that session. Behavior is identical either way.

### Account configuration (applied 2026-05-14)

| Setting | Gamma-Safe | Gamma-Bold | Why |
|---|---|---|---|
| `max_margin_multiplier` | 1 | 1 | Cash-like: no leverage on options buys |
| `dtbp_check` | exit | exit | No entry blocks on day trading buying power |
| `pdt_check` | entry | **exit** | Bold: no PDT entry blocks (cash account behavior) |
| `no_shorting` | false | **true** | Bold: long options only, matches strategy |
| `options_trading_level` | 3 | 3 | Full options access on both |

Bold is effectively cash-account-equivalent: `pdt_check: exit` + `dtbp_check: exit` means no trade is ever blocked at entry for PDT/DTBP reasons — same behavior as Webull cash account.

---

## Pre-5/18 Checklist

- [ ] J creates Account 2 in Alpaca paper dashboard → provides BOLD API key + secret
- [ ] Add `ALPACA_BOLD` entry to `~/.claude/.mcp.json` (mirror of current `alpaca-mcp` entry)
- [ ] Verify both Alpaca accounts show $1,000 balance on 5/18 premarket
- [ ] Verify `current-position-safe.json` and `current-position-bold.json` both show `status: null`
- [ ] Verify premarket reconciliation gate checks BOTH position files
- [ ] Verify EOD-flatten covers BOTH accounts
- [ ] Verify EOD-summary reports both P&L lines
- [ ] Verify kill switches are isolated (Safe kill does not halt Bold)

---

## What This Builds Toward

After 20+ trading days (~4 weeks) with both accounts live:

1. **`markdown/0dte/account-scaling-guide.md`** gets its first real data: WR, expectancy, max-DD per style at $1K
2. **Live deployment decision:** which account earns the 45% WR threshold first?
3. **v16 research question:** does Bold's wider-stop + later-TP approach outperform Safe on a WR-adjusted basis at equal capital?
4. **Real-money sizing:** when J crosses $25K live threshold, do we go Safe-style or Bold-style? The data decides, not intuition.

The goal is not to prove Bold is better or Safe is better. The goal is to **measure** — and let the market answer.
