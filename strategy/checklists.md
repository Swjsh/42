# Checklists — Project Gamma

> Run these out loud (or in chat) before/after every trade. Yes, every one. Yes, even the obvious ones. Especially the obvious ones.

---

## Pre-market checklist (run once per session)

- [ ] Account equity confirmed (paper or live).
- [ ] Daily loss budget computed (50% of start-of-day equity). Note the dollar amount.
- [ ] Day-trades remaining in PDT window (if margin account).
- [ ] Economic calendar checked: FOMC? CPI? NFP? Earnings of mega-caps that move SPY?
- [ ] Overnight futures direction noted (ES).
- [ ] Key SPY levels marked: prior day H/L, overnight H/L, VWAP from open, key MAs.
- [ ] Current IV / VIX context noted.
- [ ] Bias for the day stated explicitly: bullish / bearish / neutral / no-trade.
- [ ] If "no-trade" day: walk away. Don't manufacture setups.

---

## Pre-trade checklist (run before every entry)

- [ ] Setup matches a named pattern in `playbook.md`. *(If no: stop. Log as observation only.)*
- [ ] All context filters for that setup are satisfied. *(Read them aloud. If even one is shaky: skip.)*
- [ ] Entry trigger is happening *now*, not "about to" or "almost."
- [ ] Stop level is defined in price/premium terms. Stated.
- [ ] Target is defined. Stated.
- [ ] Position size computed by Gamma from risk-rules.md.
- [ ] $-risk on the trade ≤ 50% of account equity.
- [ ] Min 3 contracts (2 TP + 1 runner). 4 contracts if account ≥ $2K.
- [ ] Daily loss budget remaining > $-risk on this trade.
- [ ] PDT day-trade count remaining ≥ 1 (if margin and day-trade).
- [ ] No major scheduled news in next 30 minutes.
- [ ] Pre-trade thesis written into the daily journal.
- [ ] J ready to mechanically obey the stop. State this aloud.

If any box is unchecked: **the trade does not happen.**

---

## In-trade checklist (run if hesitating to manage)

- [ ] Has the stop been hit? → If yes: exit. No discussion.
- [ ] Is the playbook's invalidation event happening? → If yes: exit.
- [ ] Has the time-stop fired? → If yes: exit.
- [ ] Is target hit (or partial)? → Execute the scale-out plan.
- [ ] Am I considering moving the stop further from price? → **No.** Never.
- [ ] Am I considering adding to the loser? → **No.** Never.

---

## Post-trade checklist (run after every exit)

- [ ] Actual fill price logged.
- [ ] P&L (in $ and R) logged.
- [ ] `journal/trades.csv` updated with structured row.
- [ ] Daily journal entry updated with what happened vs plan.
- [ ] One-sentence lesson written.
- [ ] If a rule was broken: red-flagged in `journal/mistakes.md`.
- [ ] Day-trade count incremented (if applicable).
- [ ] Daily P&L vs daily loss budget checked. If over: trading is done for the day.

---

## End-of-day checklist

- [ ] All open positions either closed or have explicit hold-overnight thesis written down.
- [ ] Daily journal complete: bias, trades, lessons, screenshot of SPY chart.
- [ ] Trades.csv up to date.
- [ ] Tomorrow's bias / no-trade decision written.
- [ ] Mistakes file updated if needed.

---

## Weekly checklist (Sunday)

- [ ] All daily journals complete for the week.
- [ ] Compute metrics: trades, win rate, avg winner / avg loser, expectancy, max DD.
- [ ] Read `journal/mistakes.md` end-to-end. What's repeating?
- [ ] Review every losing trade: rule break or correct execution + bad luck?
- [ ] Review every winning trade: did playbook trigger fire correctly, or was it luck?
- [ ] Decide: any rule changes for next week? Document in CLAUDE.md update log.
- [ ] Set focus / theme for next week.
