# Journal — How we do this

> Journaling is not optional. If a trade isn't journaled, it didn't happen — and we can't learn from it.

---

## Files

- **`YYYY-MM-DD.md`** — one per trading day. Pre-market plan, every trade considered, end-of-day reflection.
- **`trades.csv`** — structured row per trade. Used for stats. Columns documented in the file header.
- **`mistakes.md`** — every rule break. Read every Monday before market open.
- **`weekly-template.md`** *(in `analysis/`)* — Sunday review structure.

---

## Daily journal template

Every day starts a new file. Use this skeleton (Gamma will create it on request):

```markdown
# Journal — YYYY-MM-DD

## Pre-market
- Account equity: $X (paper)
- Daily loss budget: $Y (3% of equity)
- Day-trades remaining: N
- News calendar: <CPI / FOMC / earnings / nothing>
- Overnight futures: <ES direction, %>
- Key SPY levels: <PDH, PDL, ON H/L, VWAP-from-yesterday's-close, key MAs>
- IV/VIX: <level + context>
- **Bias:** <bullish / bearish / neutral / no-trade> — why.

## Trades
### Trade #1 — <setup name>
- **Pre-trade thesis:** <what's setting up, what triggers entry, where stop, where target>
- **Contract:** SPY <expiry> <strike><c|p>
- **Plan:** entry <px>, stop <px>, target <px>, qty <n>, $-risk <$>, % of account <%>
- **Pre-trade checklist:** all boxes ticked? yes/no
- **Actual entry fill:** <px @ time>
- **Management notes:** <stop adjustments toward BE, partial fills, etc.>
- **Actual exit fill:** <px @ time>
- **P&L:** $<gain/loss> / <R multiple>
- **Lesson (one sentence):** <what to remember>

### Trade #2 — ...

## Setups skipped (and why)
- <pattern>: triggered but I skipped because <reason>. Was the skip correct in hindsight?

## End-of-day reflection
- Did I follow the rules? Any breaks? *(Be honest. If yes → mistakes.md.)*
- What did the market actually do vs. my morning bias?
- One thing I did well today.
- One thing I'll change tomorrow.
- Tomorrow's bias / no-trade decision.
```

---

## trades.csv

Structured trade log. Schema (see file header for actual columns):

```
date, time_entry, time_exit, setup, contract, dte, strike, c_or_p,
qty, entry_px, exit_px, premium_paid, premium_received, dollar_pnl,
r_multiple, stop_px, target_px, $-risk, %-risk-of-acct, account_equity_pre,
followed_rules (Y/N), notes_short
```

Every closed trade gets exactly one row. No exceptions.

---

## mistakes.md

When a rule was broken, write it here even if the trade made money. **Especially if the trade made money** — that's how habits form that blow up later.

Structure:

```markdown
## YYYY-MM-DD — <one-line summary>
**Rule broken:** <which rule, exact citation>
**What I did:** <factual>
**Why I did it:** <emotional / situational driver>
**Outcome:** $X / R / "got lucky"
**Pattern? Have I done this before?:** <reference past entries>
**Fix:** <process change to prevent recurrence>
```

Read it every Monday morning before placing a trade.

---

## What Gamma does

- Creates today's journal file on first message of the day.
- Logs pre-trade thesis before entry.
- Updates the trade record after fill and after exit.
- Appends to `trades.csv`.
- Flags rule breaks to `mistakes.md` with J's confirmation.
- Compiles weekly review every Sunday.

J writes the *qualitative* parts (lessons, reflections). Gamma ensures the *structural* parts are never missed.
