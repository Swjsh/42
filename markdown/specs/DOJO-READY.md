# DOJO-READY — J's one-pager (start a replay training session in one line)

> Built + smoke-tested 2026-08-01 (WS10). The full agent checklist lives in
> [DOJO-SESSION-RUNBOOK.md](DOJO-SESSION-RUNBOOK.md); the concept in
> [DOJO-REPLAY-TRAINING-SPEC.md](DOJO-REPLAY-TRAINING-SPEC.md). You never need either to
> sit down — this page is enough.

---

## 1. How you start (one line)

Say to Claude:

> **"Run the dojo."**

That's it. The agent runs `setup/scripts/dojo_session.py --start`, which:

- **picks a day you haven't seen** — pseudo-random, seeded + logged
  (`automation/state/dojo/sessions.jsonl`), never repeats a reviewed day, drawn from the
  **393 replayable days** 2025-01-02..2026-07-31 (verified lineage minus broken tapes;
  studies' "391" additionally drops short sessions — join on date, not ordinal),
- puts TradingView into **bar replay at that day** (replay tools verified working
  2026-08-01) and fast-forwards premarket,
- opens the capture file and the engine whisper loop.

You are NOT told which day it is beyond the date — you see the chart cold, forming
bar by bar. Want a specific day instead? "Run the dojo on 2026-06-30."

No Claude in the room? Terminal: `backtest\.venv\Scripts\python.exe setup\scripts\dojo_session.py --start`
then click TV's own Replay button on the printed date — your calls still capture.

## 2. What you say during it

Each bar, the agent steps the chart and reads you the engine's mind (scores, gates,
would-it-place, per arm). You just talk:

- **"long 737.7 here, stop under the wick at 737.2"** → captured: side C, price 737.7,
  stop 737.2, your words as rationale, anchored to the current bar.
- **"puts 746.9, momentum gone"** → side P, no stop = your standing stop discipline.
- **"nothing to do here"** → say it and move on — silence at a bar is a validated
  NEGATIVE label, as valuable as a call.
- **"step"** / "run to 10:30" / "done for the day" → drive words, not trades.

Direction word + a price are required (the parser rejects loudly, never guesses). Stops
are optional. If you direct something the rig can't express, the agent logs it as a
capability gap in the moment — say it anyway.

## 3. What you get after ("finish the dojo")

`--finish` (~2 min) produces the **comparison card** —
`automation/state/dojo/sessions/<session>-comparison.md`:

- **Your calls vs the engine's decisions vs what real OPRA paid for each** — every trade
  filled from the real option tape (entry at the bar after your call, exits walked
  through the REAL exit engine; entry+1 convention). Synthetic-priced rows are flagged
  and EXCLUDED from headline totals.
- **Divergences both directions**: bars where you called and the engine held; entries
  the engine took while you were silent — each with the dollar outcome.
- **Harvest doc** with LANE A (plumbing gaps → build queue) / LANE B (policy ideas →
  pre-registered hypothesis) candidates auto-seeded for routing. One replayed day is
  n=1 — the card is a scoreboard, never ship evidence; Lane B pre-reg is the path.
- The day is marked reviewed — the picker will never serve it again.

## 4. Proof it works (verified fresh, 2026-08-01)

- TV MCP replay: `replay_start(date=2026-07-17)` → cursor 2026-07-16 19:59:59 ET;
  each `replay_step` = one 5-min bar; `replay_status.current_date` = epoch seconds. All
  four tools returned success against the live TV desktop.
- Fake end-to-end session (no TV, no J): 10 bars stepped through the real engine,
  2 calls captured + parsed, both filled on **real OPRA** (`opra_5m`, 0 synthetic),
  structure stop honored at the stated 745.9, card + harvest + review row written.
  Re-run reproduced identical totals. Guards: `backtest/tests/
  test_dojo_session_oneshot.py` (14, RED-proofed) + 61 sibling dojo guards green.
- Fence: everything writes under `automation/state/dojo/` only; no broker imports; no
  git ops; sim-only. Smoke it yourself anytime: `dojo_session.py --fake`.
