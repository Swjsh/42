# Daily Review — template

> Filed at 16:30 ET each trading day, appended to `journal/YYYY-MM-DD.md` under a `## Daily Review` heading. The EOD reflection (auto-written at 15:50) covers what happened. The Daily Review is the **strategic** layer: prediction quality, lessons, levels for tomorrow.

---

## When to write it

- **When:** 16:30 ET (40 min after EOD reflection writes at 15:50). After J is back from work, but while market memory is fresh.
- **Trigger:** Manual (J prompts "daily review") or automatic if Task Scheduler picks up the EOD job and chains.
- **Required reads:**
  - `journal/{today}.md` (EOD reflection)
  - `automation/state/today-bias.json` (pre-market predictions)
  - `automation/state/loop-state.json` (final filter snapshots)
  - `automation/state/key-levels.json` (yesterday's levels for comparison)

---

## Sections (each one mandatory)

### 1. Pre-market thesis (what we expected)
Pull from `today-bias.json` AS WRITTEN AT 08:30 ET (do NOT use a mid-day update — the review grades the **morning prediction**, not a revised intraday view). Restate as a single paragraph + bullet levels. Don't paraphrase — just lift the actual prediction.

**The hypothesis must be falsifiable before the day starts.** That means premarket writes:
- Bias direction (bullish/bearish/no-trade)
- Specific levels marked with type (support/resistance/transition)
- A concrete prediction for at least one of: "725 will hold as resistance" / "722 will be tested" / "VIX will rise above 17.30 if SPY pulls back" / "no setup will fire today"
- The conditions that would prove the prediction wrong

Without a falsifiable prediction, there is nothing to grade. The Daily Review can only judge what was actually predicted.

### 2. What actually played out
A table of the day's pivotal events with timestamps. Each row gets a `Predicted? ✅/❌/Partial` column. Pull events from journal entries during the session. Aim for 5–8 rows — pivot moments, not every tick.

### 3. Where the predictions held
1–4 bullet points on what we got right. Specifics matter — "predicted 723.65 as resistance, capped the morning at 723.74" is useful; "bias was correct" is not.

### 4. Where the predictions missed
1–4 bullet points on what we got wrong. Same standard — specifics, not vague self-criticism. Each miss should include *why*, not just *what*. Misses fall into three buckets:
- **Coverage gap** — we didn't have a setup armed for what fired (e.g., "no bullish playbook for the 1:50 breakout")
- **Bias error** — we saw it correctly but interpreted wrong (e.g., "held bearish thesis 1hr after intraday flip")
- **Filter gap** — a setup fired that we have but didn't catch (e.g., "loop wasn't running before 12:00")

### 5. Surprise events
What the chart did that *nothing in our preparation accounted for*. These become the seed material for new playbook setups. If we keep seeing the same surprise, it's not a surprise — it's a setup we haven't named yet.

### 6. Lesson of the day
One paragraph. The single most actionable takeaway. Not "be more disciplined" — instead, "X happened because Y, fix is Z." Lessons get tagged for the weekly review and roll up into rule changes if they repeat.

### 7. Key levels for tomorrow (drawn on chart)
Table with: Price | Type (resistance/support/transition) | Color | Reasoning.
- **At least 4, max 7 levels.** Less is too sparse, more is noise.
- Each level **must** be drawn on the chart via `mcp__tradingview__draw_shape` AND saved to `automation/state/key-levels.json`.
- Color convention:
  - **Red** — fresh resistance (capped today, or session high)
  - **Green** — confirmed support (defended today, ribbon respected)
  - **Yellow dashed** — transition level (broken today, weak in tomorrow's frame)
  - **Blue** — deeper support tier (untested today but structural)
  - **Blue dashed** — multi-day reference (swing high/low not in today's range)

---

## What this enables

This file is the **bridge between sessions**. Tomorrow's pre-market routine reads `key-levels.json` (set by today's review) and starts with structure already loaded. Without this bridge, every day starts from scratch, and the levels J trades against are reset every morning.

The Daily Review is also the only place where we write down *quality of prediction*, not just *quality of execution*. The EOD captures whether we followed rules. The Daily Review captures whether the rules were aimed at the right thing.

---

## Common mistakes to avoid

- **Don't restate the EOD.** EOD is mechanical (entries, blocks, P&L). Daily Review is strategic (predictions, lessons, levels). If you find yourself copying EOD bullets, stop — those go in EOD, not here.
- **Don't grade in vague language.** "We did well" is useless. "We marked 723.65 and price capped at 723.74" is the standard.
- **Don't add a level just to fill the table.** Each level needs a reason it'll matter tomorrow. If you can't write the reasoning, drop the level.
- **Don't change the lesson based on P&L.** A losing day with a process win and a winning day with a process loss should produce the same lessons. Process is the signal, P&L is the noise.
