# Risk Rules — Project Gamma

> The numbers J committed to. Gamma enforces them; doesn't soften them, doesn't tighten them mid-session.
>
> **Canonical numeric values live in [`automation/state/params.json`](../../automation/state/params.json) (Safe) and [`automation/state/aggressive/params.json`](../../automation/state/aggressive/params.json) (Bold).** This file describes the WHY and the boundaries; params.json holds the WHAT (current value). Drift between the two is detected at premarket Step 1a and produces a kill-switch.

**Version:** 2.1 (2026-05-08) — replaces v2.0; numeric values now reference params.json instead of restating them.
**Rule version (canonical):** v15.3 (Safe) / v15.2 (Bold) — see [`automation/state/params.json#rule_version`](../../automation/state/params.json).
**Account context:** Dual-account ($2K Safe-2 + ~$1.65K Bold-2). The single-account "The numbers" tables below are **LEGACY** ($1K-era); see "Dual-Account Rules" below + params.json for current values.

> **⚠️ LEGACY BANNER:** The single-account "The numbers" / "$1K math" / position-sizing-schedule tables in the next several sections are the **original $1,000-paper-account doctrine** and are kept for the WHY/derivation only. They are **NOT current authority** — for live values (rule version, stops, TP1, sizing tiers, kill switches per account) **[`automation/state/params.json`](../../automation/state/params.json) + [`automation/state/aggressive/params.json`](../../automation/state/aggressive/params.json) are authoritative**, and the "Dual-Account Rules" section is the current account model.

---

## The numbers

| Parameter | Value |
|---|---|
| **Starting paper account** | $1,000 |
| **Max risk per trade** | **50% of current account equity** |
| **Daily P&L target** | **10–15% of current account equity** |
| **Daily loss kill switch** | **−50% of starting-of-day equity** (= one max loss → day is done) |
| **Min position size** | **3 contracts** (2 take-profit legs + 1 runner) |
| **Scale-up trigger** | At account ≥ $2,000 → **5 contracts** (RATIFIED 2026-05-07 — was 4 prior); at account ≥ $10,000 → **10 contracts** |

### Position sizing schedule (RATIFIED 2026-05-07)

| Account equity | Contracts | Mechanics |
|---|---|---|
| $0 – $2,000 | **3** | 2 TP1 + 1 conservative runner |
| $2,000 – $10,000 | **5** | 3 TP1 + 1 conservative + 1 aggressive runner |
| $10,000+ | **10** | 6 TP1 + 2 conservative + 2 aggressive runners |

Scale up only after the account has CLOSED above the threshold for ≥ 3 trading days
(prevents whipsaw scale changes during a single bad trade).


| **Live deployment threshold** | ≥ 20 paper trades, win rate ≥ 45%, positive expectancy, ≤ 2 rule breaks across sample |

---

## What the per-trade math actually looks like at $1K

Max $-risk per trade: **$500.**

Position structure: 3 contracts minimum, scale-out structure = 2 + 1 runner.

Premium math examples (paper, $1K account):

| Entry premium | 3 contracts deployed | Loss to hit $500 stop | Stop as % of premium |
|---|---|---|---|
| $0.50 | $150 | $500 (impossible — would need to lose more than deployed) → effective max loss = $150 | n/a (capped at total) |
| $1.00 | $300 | $500 (impossible — capped at $300 deployed) | n/a |
| $1.67 | $501 | $500 (≈ −100% premium) | −100% |
| $2.50 | $750 | $500 ÷ 750 = −67% premium | −67% |
| $3.50 | $1050 | over deployment cap, doesn't fit |  |

**Key implication:** at $1K account size, premium per contract should generally be ≤ ~$3.30 to fit a 3-contract entry under the 50% risk cap. Cheap-to-mid premium 0DTE strikes are the ones we trade.

Gamma will compute exact $-risk and % of account before every entry and refuse trades that exceed.

---

## Position structure

### Minimum: 3 contracts (current — $1K to $2K account)
- **Contract 1 & 2:** scale out at first take-profit target.
- **Contract 3:** runner — trail to next target / second support level.

### Scale-up: 4 contracts (account ≥ $2K)
- **Contract 1 & 2:** scale out at TP1.
- **Contract 3 & 4:** runners with TP2 and trailing stop.

### Scale-up beyond $2K
TBD when we get there. Don't pre-optimize.

---

## Daily P&L targets and stop

- **Target:** 10–15% of account per day. On $1K: $100–$150.
- **Stop:** −50% of starting-of-day equity in realized + open P&L. On $1K: −$500.

When daily target is hit: J can choose to flatten and walk away, or take additional setups with strict trailing-stop discipline (this is J's choice; Gamma will note it but not refuse).

When daily stop is hit: trading is **done for the day**, no exceptions. Gamma will refuse to engage with new setups. Hard veto, even if J insists. *Especially* if J insists.

---

## The math behind the daily stop

At max-risk-per-trade = 50% and daily-stop = 50%, by construction:

> **One max-loss trade = day is done.**

This is intentional. The system is designed so that a single losing trade doesn't get followed by a revenge trade. The kill switch fires on the same trade that hit the per-trade risk cap. Behavioral protection.

---

## Pre-entry liquidity gate (added 2026-05-07)

Every entry must clear an `mcp__alpaca__get_option_snapshot` check on the candidate strike BEFORE order placement. Hard rejections:

| Check | Threshold | Why |
|---|---|---|
| Bid-ask spread | `spread > max($0.08, mid × 0.10)` | Wider than 8 cents OR 10% of mid = your 50% premium stop is theoretical, fill is brutal. |
| Delta | `|delta| < 0.30` OR `|delta| > 0.55` | Outside the ATM-ish band. <0.30 = too OTM (low gamma, premium evaporates on small move). >0.55 = effectively a stock proxy, options leverage gone. |
| Open interest | `OI < 500` | Bid evaporates on fast moves; partial fills become likely. |
| Quote validity | `bid <= 0` OR `ask <= 0` | Broken quote — never trade through it. |

On reject, try the next strike one notch toward ATM (or further if delta too high). Max 2 retries. Still failing → emit `SKIP_LIQUIDITY` and log the failed metric to journal under `## Setups skipped`. Do NOT place the order.

### Liquidity-aware qty downsizing (NEW 2026-05-09)

Before rejecting on a wide-spread environment, try **reducing qty** rather than skipping the trade entirely. The setup edge is intact; the only change is fewer contracts to absorb the wider slippage. Source of truth: `params.json#position_sizing_tiers` × the multiplier below.

| Spread observed | Qty multiplier | Rationale |
|---|---|---|
| ≤ $0.08 | **1.00× (full)** | Normal liquidity, no adjustment |
| $0.09 – $0.12 | **0.67×** | Wider spread, modest slippage cost — reduce to ⅔ qty |
| $0.13 – $0.18 | **0.33×** | Significant slippage — reduce to ⅓ qty (min 3 contracts always) |
| > $0.18 | **0.00× (skip)** | Slippage swamps edge — emit `SKIP_LIQUIDITY` |

Floor: `qty_after = max(min_contracts (3), round(qty_base × multiplier))`. The 3-contract minimum preserves the 2 TP1 + 1 runner structure that the playbook depends on; below that the management mechanics break.

Heartbeat logs `QTY_REDUCED: spread=$X.XX qty_base=N qty_after=M` to journal entry thesis when the multiplier fires. Surfaces in EOD-summary as `liquidity_downsized: true` flag on the trade row in trades.csv.

## Bracket-order execution (added 2026-05-07)

Entry orders use `mcp__alpaca__place_option_order` with `order_class="bracket"`:

- **Parent leg:** limit at mid (or limit-cross-the-spread by 1¢ if spread ≤ 5¢ for fast fills).
- **Take-profit leg:** limit sell of 2/3 (or 2/4) of qty at TP1 price (= +30% of premium OR first major support/resistance, whichever is closer).
- **Stop-loss leg:** stop-market for full qty at chart-stop (50% premium stop OR price-level stop, whichever is closer).
- **After TP1 fills:** heartbeat issues `mcp__alpaca__replace_order_by_id` to move the runner stop to **breakeven + 1¢** for the remaining 1/3 (or 2/4) contracts.

**Why bracket and not naked limit:** in P0 we observed that throttle-skipped ticks during fast moves can mean the heartbeat sees the move only AFTER the stop level is breached. Exchange-resident stops fill regardless of whether Gamma is awake.

**Fallback if Alpaca paper rejects `order_class="bracket"` for options:** try `order_class="oto"` (one-triggers-other — submits stop after parent fills), and log a warning `BRACKET_FALLBACK` to the journal. If OTO also rejected: naked limit + heartbeat-monitored stop. **The fallback does not change the rules; it changes the implementation.**

## First-entry rule (added 2026-05-07)

If the same setup name (e.g. BEARISH_REJECTION_RIDE_THE_RIBBON) has been entered AND stopped out today, **no second entry on that setup name today** — even if a fresh trigger fires. The lesson: when a setup pattern fails once on a given day, the day's regime is wrong for that setup. A second entry is laddering down. Use the second trigger as observation only; log it to skipped-setups.csv.

If the prior entry was a TP (winner) and a fresh trigger fires for the same setup later in the day: a second entry IS allowed, but with reduced size (`qty = max(min_qty, prior_qty - 1)`) — book-some, risk-less.

## What's banned (specials for this account size and style)

- **Adding to losers without a NEW confirmed signal.** If the original trigger fires twice, that's not adding to a loser — that's a new entry. If the price just moved against you and the setup is the same: do not add.
- **Trading the open (first 5 min)** unless the playbook explicitly defines an open-bell setup. Spreads are wide, fills are bad.
- **Trading the last 30 min** unless the setup is explicitly a closing-rotation play. Liquidity dries; theta on 0DTE is brutal at the bell.
- **Trading FOMC / CPI / NFP release minute.** Spreads explode; fills are awful. Wait for post-release direction.
- **Holding 0DTE through close.** All flat by 15:50 ET unless the setup explicitly says otherwise.
- **Selling naked options.** Margin and assignment risk incompatible with this account.

---

## Live deployment thresholds

Live trading starts only when **all** of these clear on paper:

| Metric | Threshold |
|---|---|
| Logged paper trades | ≥ 20 |
| Win rate | ≥ 45% |
| Avg winner / avg loser | ≥ 1.5× (favorable expectancy) |
| Expectancy per trade | > 0 net of costs |
| Max drawdown in test period | ≤ 30% of paper equity |
| Days following all process rules | ≥ 90% (≤ 2 rule breaks across sample) |

When all clear: deploy $500–$1,000 of real money. Start with **3-contract minimum, same as paper** — don't size up just because it's real.

---

## Dual-Account Rules (effective 2026-05-18)

As of 5/18, Gamma trades **two paper accounts simultaneously** off the same heartbeat. See [`dual-account-design.md`](dual-account-design.md) for the full design. Risk rules summary:

### Per-account kill switches (fully isolated)

| Parameter | Gamma-Safe (Account 1) | Gamma-Bold (Account 2) |
|---|---|---|
| Max risk per trade | **30% of equity** | **50% of equity** |
| Daily loss kill switch | **−30% of start-of-day equity** | **−50% of start-of-day equity** |
| Premium stop | **−50% (catastrophe cap; chart-stop is primary, C2)** | **−7% bear / −5% bull** |

**Kill switches are fully isolated.** Safe hitting its −30% daily limit does NOT halt Bold. Bold blowing up does NOT halt Safe. Each account fails and recovers independently.

### Setups by account

| Setup | Safe | Bold |
|---|---|---|
| BEARISH_REJECTION_RIDE_THE_RIBBON | ✅ | ✅ |
| BULLISH_RECLAIM_RIDE_THE_RIBBON | ✅ | ✅ |
| SNIPER_LEVEL_BREAK (DRAFT) | ❌ | ✅ |
| All WATCH-ONLY watchers | ❌ | ✅ |
| Counter-trend / role-reversal reclaims | ❌ | ✅ |

### Overlap: when both accounts see the same setup

Both execute on the same tick with different params (see [`dual-account-design.md`](dual-account-design.md#overlap-resolution) for full table). Safe takes OTM-2 strike + 50% TP1 (per-tier; params.json). Bold takes ITM-2 + 75% TP1. Kill switches and position state tracked independently.

### Journal tagging (mandatory)

Every row in `trades.csv` must include `account_id` field (`safe` or `bold`). Decisions in `decisions.jsonl` must include `account_id`. Premarket reconciliation gate checks both `current-position-safe.json` and `current-position-bold.json` — HALT on mismatch in either.

---

## Audit cadence

- **End of session:** journal + trades.csv updated.
- **End of week (Sunday):** weekly review in `analysis/YYYY-Www.md`. Compute the metrics above on the paper sample.
- **End of month:** rule review. Adjust in writing, log in CLAUDE.md update log.

---

## How Gamma calls position sizing out loud

Before any entry, expect this kind of explicit math:

> "OK, paper account $1,000. Daily P&L so far: $0. Daily budget remaining: $500.
> Setup is BEARISH_REJECTION_RIDE_THE_RIBBON, trigger fired at 13:36 (rejection candle close + ribbon flip).
> Proposed contract: SPY 723P 0DTE (ITM-2) at $1.20 mid (delta ~0.7).
> 3 contracts × $1.20 × 100 = $360 deployed. Chart stop is the primary invalidation (rejected level + $0.50 buffer); premium catastrophe cap at −50% (params.json#premium_stop_pct) = $0.60 backstop.
> Chart-stop risk to invalidation ≈ $30. $30 / $1,000 = 3% account risk. Within the per-trade cap. ✅
> TP1 at +50% = $1.80 for 2 of 3 contracts (qty_fraction 0.667), or first chart-level past entry, whichever first. Runner moves to BE after TP1.
> Placing bracket order via Alpaca paper. Thesis logged."

That kind of explicit, math-first dialogue is what these rules are for. If the math doesn't fit, the trade resizes or doesn't happen.
