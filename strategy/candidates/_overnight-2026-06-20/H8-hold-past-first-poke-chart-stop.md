# H8 — Structural Chart-Stop, Hold-Past-First-Poke

**Rank:** 8 of 8 · **Score:** 5.0 · **Seam:** exit / loss-rescue (bounded by C28) · **Status:** PROPOSAL (test, do not ship — exit work, lower priority per C28)

---

## The setup / signal

Make the **primary** stop unambiguously *structural* (thesis-level breaks on a **closed** bar) rather than premium-based, with the -50% premium level demoted to a pure **catastrophe backstop**. Specifically: do **not** exit on a single intrabar wick or one adverse 5m bar inside structure; require the thesis-defining level/swing to **close** broken before stopping.

## The insight (why it should have edge)

This is the most directly evidenced exit hypothesis in the project, from `J-LOSERS-STOPPED-THEN-PRINTED`:

> "After he exited, the underlying continued meaningfully his way (>=0.25% ~ $1 SPY) on **67.9% of his losers** ... the contract he'd just dumped peaked at >=2x his exit price on **21.4%** ... His median loser exit was **-42%** ... Many exits happened on the first 5m red bar."

And the explicit recommendation:

> "Candidate: **explicitly require the thesis level to break on a *closed* bar before stopping**, rather than reacting to an intrabar wick (already the spirit of chart-stop-primary; this data quantifies the payoff)."

J's account died on the panic-sell at the first adverse poke right before two-thirds of his trades continued his way. A closed-bar structural stop is the mechanical version of "hold past the first poke."

## EXACT backtest to validate — and the C28 caveat (why this is ranked LAST)

**C28 (L139,141,156,157) is a standing caution:** *"exit mechanics are locally optimal; focus research on ENTRIES — exit tuning has diminishing returns once stop-rate > 70%."* And the loser study's own honest finding: on the loser-only subset the structural exit nets only **+$3.2K _EST_** because **83% hit the -50% cap anyway**. So this is included for completeness and because the *closed-bar* nuance may be under-tested, but it is explicitly the lowest-priority item.

1. **Knob:** `stop_requires_closed_bar_break` {off, on} x `chart_stop_buffer` {current, +$0.25} — applied to the structural stop only; -50% catastrophe cap unchanged.
2. **Measure on the FULL population** (not loser-only — the loser study warns the loser subset is a higher-variance, misleading sample; the real edge is holding *winners*): total P&L, stop-rate, % of stops that were intrabar-wick vs closed-break, and the count of "stopped then recovered to +30%" trades rescued.
3. **Anchor (OP-16):** 4/29//5/01//5/04 — verify the closed-bar rule does not *widen* a stop into a bigger loss on any anchor (it shouldn't; all three were winners) and does not convert an anchor winner's clean exit into a worse one. `edge_capture` must hold.
4. **Real-fills:** mandatory — exit-timing edges are exactly where SPY-space lies (C3). Top cell OPRA-validated.
5. **Guards:** L171 truncation (demoting the premium stop *is* the chart-stop-only pole — this hypothesis literally tests the L171 axis; the closed-bar variant must beat both premium-stop and naive chart-stop), L172 less applicable (exit knob), C30 (audit what % of exits actually hit each mechanism before sweeping — the exit-reason breakdown is mandatory).
6. **Scorecard:** `analysis/recommendations/h8-closed-bar-chart-stop.json` with the exit-reason histogram and the rescued-trade count.

## Kill criteria (reject if ANY)

- Closed-bar stop *widens* average loss more than it rescues recoveries on the full population (the -50% cap dominates anyway — the loser study's +$3.2K-only result suggests this is plausible).
- `edge_capture < baseline` (an anchor's exit got worse).
- Real-fills shows the SPY-space improvement does not survive the option transform (C3).
- Stop-rate already >70% with the win concentrated in held winners (C28 — diminishing returns confirmed, stop down the research).

## Expected edge_capture x feasibility

**edge_capture MED** (loss-rescue is real but bounded — 83% hit the cap regardless). **feasibility HIGH** (an exit knob, no new detector) — but **deliberately ranked last** because C28 says exits are near-optimal and entries are where the edge lives. Included so the closed-bar nuance is on record; should only be cooked after H1-H7.

## Disclosure (OP-20)

Be honest per the loser study: mechanical exits net only +$3.2K _EST_ on the loser-only subset; the engine's true edge is holding *winners* to targets on the full population, not rescuing losers. Do NOT tighten the premium cap toward J's -42% (the exact level that whipsawed him — L-doc). The catastrophe cap stays; only the *primary* exit becomes structural/closed-bar.
