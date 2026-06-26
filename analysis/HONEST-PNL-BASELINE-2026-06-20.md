# Honest P&L Baseline — 2026-06-20

> The trustworthy "where we actually stand" snapshot, anchored in live Alpaca broker
> equity (Rule C11: broker is source of truth), not the state files or the auto-EOD
> reports (which are demonstrably buggy — see caveats). This is the line we freeze
> against before measuring edge. Paper money throughout.

## Live equity (broker truth, market closed)

| Account | Alpaca # | Equity | Cash | Positions | Created |
|---|---|---|---|---|---|
| Gamma-Safe-2 | PA3S2PYAS2WQ | **$2,000.00** | $2,000 | flat | 2026-06-16 |
| Gamma-Risky-2 (Bold) | PA33W2KUAT40 | **$1,648.75** | $1,648.75 | flat | 2026-05-20 |
| **Combined** | | **$3,648.75** | | flat | |

Bold SMA = $1,673.16 → started ~$1,673, down ~$24 (the 6/18 746C trade). Safe is fresh
$2,000 wired 2026-06-15, untouched since.

## The headline truth

**The autonomous engine has not demonstrated edge.** Every clean profit traces to J's
discretionary reads, not the engine's own decisions:

- **3 anchor winners** (4/29 +$342, 5/01 +$470, 5/04 +$730) = J's **pre-rules manual** trades.
- **Biggest system-era win** (5/14 745C +$1,500) = J hands-on (`j_override=Y`), on the old ~$100K paper account (so +1.5%, not the windfall it looks like).
- **Only autonomous winner** (6/15 752C +$552) was a **Rule-6 sizing violation** (92% of equity).
- **Strip those out → the engine's own autonomous decisions are net negative.**

## Validation gate (the system's own scorecard, [W24 §6](2026-W24.md))

| Threshold | Required | Actual | Status |
|---|---|---|---|
| Logged paper trades | ≥ 20 | 8 (counted) / ~13–17 (true) | ✗ FAIL |
| Win rate | ≥ 45% | **25%** | ✗ FAIL |
| Expectancy / trade | > 0 | +$34 (skewed by 1 outlier) | ~ |
| New-account max DD | ≤ 30% | old Safe −28.6% | ⚠ near-breach |

Old Safe $1,000→$714 (−28.6%) and old Bold $1,500→$1,122 (−25.2%) both **underperformed
flat SPY by ~25–28pp**. Current "even" equity exists only because the accounts were
**recapitalized** with fresh paper on 6/15 — the drawdown was reset, not earned back.

## Why you can't even do a clean reconciliation (the real finding)

`journal/trades.csv` holds 13 unique trades. The [W24 review](2026-W24.md) references **at
least 4 more that never made it into the CSV** (5/19 −$36, 5/20 −$180, 6/2 +$33, 6/2 −$156).
**The trade ledger is incomplete** — you cannot sum your own P&L from the system of record.

Confirmed broken measurement (4+ consecutive weeks, all "pending"):
- EOD report fabricates **−100% / equity→$0 on a market holiday** ([eod-deep-2026-06-19](eod-deep-2026-06-19.md)).
- `decision_grade` = `null` on 100% of decisions (R-0008).
- `setup-performance.json` stale 30+ days (R-0007).
- Watchers 0/6 active, all silent (6/19 EOD §watcher_fleet).
- Heartbeat went **dark 12 days** (June 2–14) — caught only by the weekly review, not any alarm.

## What this baseline locks in

1. **Freeze line:** combined $3,648.75, 25% WR, engine-net-negative. Any future claim of
   improvement must beat this on a *frozen ruleset* with N≥30 clean trades.
2. **Trust nothing downstream of the broken pipelines** until R-0007/R-0008 + the EOD bug
   are fixed. Numbers in auto-reports are fiction until then.
3. **Edge attribution is the open question:** is the directional read good (option tax
   kills it) or is the read itself coin-flip? Resolve via the futures control experiment.

_Anchored from live Alpaca `get_account_info` on both servers, 2026-06-20._
