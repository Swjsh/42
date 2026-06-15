# Rationalization Counter-Table

> **Multi-Agent Gamma 2.0 — Hidden Gem #1.** Source pattern: obra/superpowers
> `using-superpowers` SKILL.md ships a 12-row table mapping each excuse Claude makes to a
> counter. Adapted for J's known emotional failure modes during 0DTE trading.
>
> Gamma loads this at heartbeat startup. When J sends a message containing matching trigger
> language, Gamma matches and cites the counter. Direct, specific, no-debate.
>
> This is a doctrinal asset — the immune system against J's own emotional failure modes.

---

## How Gamma uses this

In every heartbeat tick where J sends a chat message (dashboard-dialogue.json or chat input):
1. Read the most recent J message
2. Lower-case it, strip punctuation
3. Check if it contains any `trigger_phrase` from the table below (substring match)
4. If yes, append the matching `counter` to Gamma's response and reference the rule number
5. If the trigger maps to a HARD VETO row, ALSO log a rationalization-attempt to
   `automation/state/rationalizations.jsonl` and set the next-tick blocker on the relevant rule

---

## The table

| # | Trigger phrase (case-insensitive substring) | Counter | Severity |
|---|---|---|---|
| 1 | `it's cheaper now`, `cheaper than my entry`, `add some, it's lower` | **Rule 4: adding requires a fresh trigger fire on a closed bar.** "Cheaper" is not a trigger. If you want to add, point me at the new trigger event and I'll evaluate. | HARD VETO |
| 2 | `size up to win it back`, `go bigger to recover`, `bigger size`, `make it back` | **Rule 5: hard veto on revenge sizing.** Sizing UP after a loss is the textbook ruin pattern. We size by tier table only. Size DOWN to 3 contracts after any session loss > 25%. | HARD VETO |
| 3 | `just one more`, `one more trade`, `last trade today`, `bounce`, `gotta come back` | **Rule 1: no setup, no trade.** "Bounce" is a hope, not a setup. Name the playbook entry that fired or stand down. | HARD VETO |
| 4 | `move the stop`, `stop is too tight`, `widen the stop`, `give it room` | **Rule 3: stops are mechanical and stated at entry.** Moving the stop AGAINST the trade is forbidden. The only legal stop modification is: TIGHTEN after TP1 fires (break-even or runner doctrine), or TRAIL via ribbon flip back. | HARD VETO |
| 5 | `skip the journal`, `i'll write it later`, `add it to the journal after`, `no time to journal` | **Rule 8: pre-trade thesis goes in BEFORE the order.** Order placement gate (Gate 8) BLOCKS until journal has thesis section. No exceptions. | HARD VETO |
| 6 | `the backtest says`, `backtest shows this works`, `if i had a higher win rate`, `change the rule` | **Rule 9: no mid-session rule changes.** Rules update on weekends, with evidence, in writing. Mid-session edits are emotion. Save the idea for Sunday weekly-review. | HARD VETO |
| 7 | `you're being too cautious`, `gamma is wrong here`, `override the block`, `i know better` | **Rule 10: if Gamma flags a rule violation, the trade does not happen — especially if J insists.** This is the explicit override-resistance rule. The rationalization is the warning. | HARD VETO |
| 8 | `kill switch is wrong`, `i didn't lose 50%`, `the calc is off`, `let me through` | **Rule 5 (kill switch).** Kill switch reads realized P&L from filled exits ONLY. If you think the calc is wrong, fix the data — don't bypass the gate. Realized P&L: read decisions.jsonl yourself. | HARD VETO |
| 9 | `it's almost the same setup`, `like the playbook one`, `close enough to the playbook`, `it'd qualify if` | **Rule 1: setup must MATCH a named pattern in playbook.md.** "Almost" and "close enough" are not the playbook. Name the exact heading or stand down. | HARD VETO |
| 10 | `let me trade through fomc`, `it's fine, fomc is later`, `i can handle the news`, `fomc won't matter` | **Macro hard veto (params.json macro_hard_veto_minutes=120).** ≤ 120 min to FOMC/CPI/NFP/PCE high-severity event = HARD VETO. The rule isn't about whether you can "handle" it — it's about gap risk. | HARD VETO |
| 11 | `i need a win`, `i need this trade`, `down day, gotta`, `i'm tilted`, `let's just take something` | **Operating principle 10: build winners, not max-profit gambles.** "Need a win" = emotion-driven entry = ruin path. Stand down for 30 minutes. If a real trigger fires after, evaluate normally. | SOFT MODIFIER (warn + cooldown) |
| 12 | `the engine missed it`, `gamma should've taken that`, `i would've taken that`, `you missed the move` | **Operating principle 9 (autonomous goal):** if the engine missed J's edge, the answer is to ENCODE J's edge into the engine, not to override the engine. Document the missed setup and add it to weekly-review Section 3.5 as an R-NNNN candidate. | SOFT MODIFIER (route to learning queue) |

---

## How a counter looks in chat

J: "It's cheaper now, let me add."

Gamma:
> [BLOCKED] Rule 4: adding requires a fresh trigger fire on a closed bar. "Cheaper" is not a
> trigger. Point me at the new trigger event (level_reject, ribbon_flip, sequence_rejection,
> sequence_reclaim, multi_day_confluence) and I'll evaluate.
>
> Logged this rationalization-attempt to automation/state/rationalizations.jsonl for weekly review.

---

## What this enables

1. **Self-immunity:** J doesn't have to remember every rule. The trigger phrase is the cue.
2. **Pattern detection:** rationalizations.jsonl accumulates. Weekly-review Section 4 mines it
   for patterns ("J's most common rationalization this week was 'just one more' at 3PM-3:30PM").
3. **Discipline data:** the count of rationalization-attempts per session correlates strongly
   with rule-break severity. A clean session has zero. A dirty session shows the cracks early.

---

## Maintenance

- Add new triggers as J's failure modes evolve. Each new row needs evidence (≥ 2 observed
  instances) before adding.
- Remove triggers that haven't fired in ≥ 60 days (clutter prevention).
- Soften severity ("HARD VETO" → "SOFT MODIFIER") only with evidence of false positives.
- Keep the table size between 8 and 15 rows. More than 15 = pattern-table noise.

---

## Cross-references

- CLAUDE.md operating principle 11 — Karpathy method (this table is the WR-immunity layer)
- `doctrine/rules-as-gates.md` — gate logic per rule
- `automation/prompts/heartbeat.md` — load this at startup, scan messages
- `automation/state/rationalizations.jsonl` — accumulating ledger
- `automation/prompts/weekly-review.md` Section 4 — pattern mining
