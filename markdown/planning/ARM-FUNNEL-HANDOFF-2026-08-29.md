# HANDOFF — ARM FUNNEL-DOWN: from 4 SPY arms to 1–2

> Prepared 2026-08-29 (Saturday, market closed) for a FRESH session to execute.
> J's directive: *"audit the current SPY trading arms for which one is doing the best and which one
> could potentially be cut — we need to start funneling down and figuring out how to properly trade
> just 1 or 2 accounts eventually."*
>
> **This document decides nothing and arms nothing.** It hands over a completed audit plus the
> constraints, so the next session can do the work without re-deriving the ground truth.

---

## 1. HARD CONSTRAINTS — read before touching anything

1. **⛔ CONFIG FREEZE 2026-08-31 open → ~2026-09-29** (set by a parallel Fable session, commit
   `d6f55f7a`, `analysis/deep-research/FABLE-FULL-REVIEW-2026-08-29.md`). No trading-path changes
   during the window except **pre-registered kill-type risk reductions**. The window exists to give
   `go_live_gate.py` 20 clean days to score. **Retiring or reconfiguring an arm mid-window destroys
   the window.** Therefore: DECIDE and PREPARE now, EXECUTE at window close (~09-29) unless the
   change qualifies as a kill-type risk reduction, which a retirement arguably does — that call
   needs to be made explicitly and recorded, not assumed either way.
2. **⛔ Arming live money is J's decision alone** (OP-0 #1). Nothing here authorizes it.
3. **A queued change already targets safe-2:** `SAFE-2-EXIT-SHAPE-AB-PREREG` (see
   `automation/overnight/queue.md`, HIGH) — safe-2 adopts risky-1's
   `exit_patch {tp1_premium_pct: 0.5, stop_mode: structure}`. Mechanism: safe-2's +100% TP1 is
   effectively unreachable on 0DTE. **Do not cut safe-2 before that fix has had its window** — its
   failure mode is diagnosed and has a pending remedy. Cutting a diagnosed-and-being-fixed arm
   destroys the evidence for whether the fix works.
4. **Do not pool arms as independent samples.** They share one signal generator; measured pairwise
   daily-P&L correlation is r ≈ 0.62–0.72, i.e. ~1.4 effective arms out of 4–5.
5. Every claim must survive the **ex-best-day** test. On this book that is the discriminator, not a
   tiebreaker — see §2.

---

## 2. THE AUDIT (completed 2026-08-29, from `analysis/trades-enriched.jsonl`, engine attribution)

### Full history — the ex-best-day column is the story

| Arm | n | days | Total | $/trade | WR | PF | Best day | **Ex-best** | Green |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **risky-1** | 79 | 26 | **+$1,292** | +$16.35 | 28% | 1.30 | +$1,041 | **+$251** ✅ | 8/26 |
| **safe-3** | 59 | 26 | **+$841** | +$14.25 | 31% | 1.33 | +$637 | **+$204** ✅ | 9/26 |
| bold-2 | 39 | 19 | +$215 | +$5.51 | 36% | 1.06 | +$479 | **−$264** ❌ | 11/19 |
| safe-2 | 86 | 29 | **−$434** | **−$5.05** | 24% | 0.89 | +$662 | **−$1,096** ❌ | 10/29 |

**Only safe-3 and risky-1 remain positive with their single best day removed.** bold-2 and safe-2
ARE their best day.

### August and post-fix (both windows flatter everything — treat with the stated caution)

| Arm | Aug total | Aug $/trade | Post-fix (08-19+) total | Post-fix $/trade | Post-fix days |
|---|---:|---:|---:|---:|---:|
| risky-1 | +$1,520 | +$27.64 | +$1,589 | +$144.45 | **5** |
| safe-3 | +$863 | +$26.97 | +$1,217 | +$101.42 | **6** |
| bold-2 | +$764 | +$23.88 | +$707 | +$54.38 | **5** |
| safe-2 | +$577 | +$12.82 | +$302 | +$17.76 | **7** |

⚠️ Post-fix n is **5–7 days per arm**. These numbers are directionally consistent with the
full-history ranking but cannot rank the arms on their own.

### Trend — all four improving, but from very different places

| Arm | Last 10 sessions $/trade | Lifetime $/trade | Read |
|---|---:|---:|---|
| safe-3 | **+$51.32** | +$14.25 | improving sharply |
| bold-2 | +$21.92 | +$5.51 | improving |
| risky-1 | +$20.92 | +$16.35 | stable-positive |
| safe-2 | **−$1.91** | −$5.05 | improving but **still negative** |

### What actually differs between the arms (data-derived, not config-claimed)

| Arm | avg qty | avg cost | Tier mix (top 2) | stop_mode mix |
|---|---:|---:|---|---|
| safe-3 | 3.4 | $256 | **ELITE 59** (nearly pure) | structure 40 / none 19 |
| risky-1 | 5.2 | $452 | ELITE 51, BASE 28 | structure 45 / premium 15 / none 19 |
| bold-2 | 5.1 | $406 | ELITE 17, TRENDLINE 16 | structure 36 / none 3 |
| safe-2 | 3.0 | $306 | **none 36, TRENDLINE 25** | structure 44 / none 42 |

**safe-3 is the most selective arm and has the best per-trade economics. safe-2 is the least
selective and the only money-loser.** This is the central mechanism finding.

### 🔑 The finding that reframes consolidation

Arms do **NOT** all trade the same signals:

- 105 distinct `(date, symbol)` signals across the 4 arms
- **50% (52) were taken by exactly ONE arm**
- Taken by 2 arms: 30% · 3 arms: 12% · all 4: only **8%**
- Signals taken by only one arm: **safe-2 = 32**, bold-2 = 11, safe-3 = 5, risky-1 = 4

**The worst-performing arm is the one taking signals every other arm rejects.** Therefore
consolidation is not merely "close accounts and keep the best" — the gain comes from **adopting the
surviving arm's SELECTIVITY**, and the next session must verify which gate/tier difference actually
produces safe-2's 32 unique (and unprofitable) signals.

---

## 3. THE WORK TO DO

**Primary question:** which ONE configuration should the consolidated account run — and is a second
(challenger) account worth keeping?

1. **Find the mechanism, not just the ranking.** Determine WHY safe-3 takes almost only ELITE while
   safe-2 takes 32 unique low-tier signals. Read the per-arm gate/threshold config (fleet registry,
   arm overrides, `shared-signal` consumption path) and name the specific setting that differs.
   The audit above says WHAT; the next session must establish WHY, because the winning config is the
   deliverable — not the winning account number.
2. **Test the consolidation counterfactual on real fills:** what would a single account running
   safe-3's selectivity at risky-1's sizing have produced over the full record? Use
   `analysis/trades-enriched.jsonl` + the ratified exit walk
   (`backtest/lib/exit_manager_walk.py`). Apply real costs (fees + exit slippage swept
   $0.00/$0.50/$1.00/$2.00 per contract — slippage is per-contract and does not dilute with size).
   Report with day-level bootstrap CI, ex-best-day, and signal-cluster n via
   `setup/scripts/lib/scorecard_guards.py`.
3. **Answer whether a challenger arm earns its keep.** Given r ≈ 0.62–0.72 between arms, quantify
   what a second account actually buys: is it diversification (little, given the correlation), or is
   it an A/B channel (valuable — it is how the exit-shape and sizing questions get answered at all)?
   Recommend explicitly, with the cost of losing that channel if we go to one account.
4. **Sequence the retirement safely.** For each arm proposed for cut, state: what evidence closes,
   what shadow/prereg depends on it, whether its account should be re-tasked (as risky-3's was to
   weekly-1 on 2026-08-28), and **whether EOD flatten coverage follows it** — `eod_flatten.ACCOUNTS`
   derives from `_active_arms()`, and the risky-3 retirement left `test_eod_flatten_coverage_2026_08_18.py`
   and 6 fleet routing/display-name tests stale. **Do not repeat that.** Fix the fixtures as part of
   the change, never by weakening the assertion.
5. **Deliver a pre-registration, not a config edit.** Given the freeze, the output is a frozen
   prereg (follow `analysis/recommendations/PREREG-TIGHT-LADDER-2026-08-28.md` as the format — it
   has start AND end dates registered, a primary concentration criterion, and a stated kill rule)
   plus a dated execution plan for window close.

---

## 4. ANTI-PATTERNS THIS PROJECT HAS ALREADY PAID FOR

- **Do not rank arms on a window that contains their best day** without showing the ex-best number
  beside it. On 2026-08-27 a full review produced 9 of 13 wrong claims exactly this way.
- **Do not treat post-fix n=5–7 days as evidence of a ranking.** It is consistent with the
  full-history ranking; it cannot establish one.
- **Do not cut an arm whose failure is diagnosed and has a pending fix** (safe-2 / the exit-shape A/B).
- **Do not assume a params key does anything** — vary-and-assert it (lesson C14: dead knobs).
- **Do not pool correlated arms as independent samples** (lesson C4 + the r≈0.62–0.72 measurement).
- **Verify, don't claim** (OP-33): quote real command output for every number.

## 5. STARTING POINTS

- `analysis/trades-enriched.jsonl` — canonical per-trade ledger (basis + FIFO reconciled)
- `analysis/deep-research/FABLE-FULL-REVIEW-2026-08-29.md` — the parallel session's review + the freeze
- `analysis/recommendations/PREREG-TIGHT-LADDER-2026-08-28.md` — prereg format to copy
- `setup/scripts/go_live_gate.py` / `analysis/go-live-gate.json` — the live gate (currently RED)
- `setup/scripts/lib/scorecard_guards.py` — required guard fields
- `automation/state/fleet/accounts.json` — arm roster (risky-3 retired 2026-08-28)
- `automation/overnight/queue.md` — `SAFE-2-EXIT-SHAPE-AB-PREREG`
- `MAP.md` → route here before any repo-wide search
