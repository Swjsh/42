# 01 — INVESTIGATION: how to find what's actually wrong

> Task type: "why is X broken / not trading / weird." The failure mode this chapter prevents: plausible-sounding diagnosis built on unread evidence, patched with a knob-tweak, declared fixed, broken again tomorrow.

## The procedure (in order, no skipping)

### Step 1 — Define the FUNCTION, not the symptom
Write one sentence: *what outcome should exist that doesn't?* Not "the kitchen crashes" but "no research result has ever reached the engine." Not "engine seems off" but "zero filled orders exist on the core accounts." The function statement determines what evidence matters. If you can't state the missing outcome, you're not ready to investigate.

### Step 2 — Pull PRIMARY evidence before ANY hypothesis
Primary = ledgers (core-decisions.jsonl, fleet decisions, trades CSVs), broker REST truth (positions/orders/account), logs (stderr/stdout of the actual process), file mtimes/hashes, git history of the exact file. NOT primary: docs, code comments, STATUS entries, memory notes, prior session claims — those are CLAIMS to be tested (this codebase's docs have been wrong about "LIVE", "data-blocked", "profitable", and "working" — repeatedly).
Quote what you pull. If your diagnosis paragraph contains no quoted line from a ledger/log/API response, it is a guess.

**Worked example (the stale-signal hunt, 07-02):** symptom = "engine entered at 09:30 against a 09:35 gate." Wrong path: assume the gate is mis-configured, change the config. Actual path: pull the 09:30:03 ledger row → it carries `spy=746.26` → fetch bars → 746.26 is *yesterday's 15:50 close* → the entry was scored on the prior session's bar → the floor checks BAR time, which yesterday's bar passes trivially. The smoking gun was one number in one ledger row, matched against one bar fetch. Config was innocent. **Lesson: the evidence names the mechanism; hypotheses don't.**

### Step 3 — Walk the MONEY PATH end-to-end
For any "X never happens" problem: write the full chain from origin to outcome (signal → score → gates → route → size → place → accept → fill → register → manage → exit → journal), then check EACH handoff for the last time it demonstrably completed. The break is the first link with zero completions. Components can all be individually "healthy" while the chain has never completed once — that was this entire project's disease (pipeline audit 07-01: every single research→engine handoff was broken while every component looked green).
Distinguish four states per link: code exists → runs on schedule → produced output → **output was consumed downstream**. Only the fourth counts.

### Step 4 — Name the failure SIGNATURE before the mechanism
- Silent death + clean stderr + no crash log = **external kill** (this rig kills its own processes — check the reaper first) or an uncatchable exception class (SystemExit escaped `except Exception` — the kitchen poison pill).
- Same input always fails = deterministic bug. Intermittent = race/resource/state-shape. **One account fails, the other doesn't = state-shape luck** (Bold's tz crash fired only because its exit filled in ONE piece while Safe's filled in partials — same code, different data shape). When only one instance fails, diff the DATA between instances before diffing the code.
- Fixed cadence between failures = a scheduler/watchdog is involved.
- Worked at time T, broken after = `git log` the touched files between T and now; suspect the port/refactor (dozens of params keys died silently in the 06-25 engine port).

### Step 5 — The stale-clock hunt (this rig's #1 recurring class)
Any time-adjacent misbehavior, check IN ORDER: (a) wall-clock vs bar-timestamp confusion (the 09:30 escape); (b) tz-aware vs naive mixing (`can't subtract offset-naive and offset-aware` — grep the exact subtraction); (c) ET derived correctly (rig is on Mountain; ONLY et_clock.py or PowerShell — Bash TZ returns UTC here); (d) fixed offsets stored year-round in data files (the −04:00 winter clip); (e) "is the input bar from TODAY'S session" freshness (no freshness check = yesterday's signal trades at the open).

### Step 6 — One hypothesis → one probe → confirmed mechanism
State the mechanism in one sentence ("stage5's argparse reads the daemon's argv → SystemExit(2) → escapes except Exception → daemon dies"). Then confirm it with a minimal reproduction (a unit test that triggers the exact error, a replay of the exact row). NEVER shotgun several changes; never declare victory because it "seems fine now" — reproduce the failure, apply the fix, show the same probe now passes.

### Step 7 — The fix is not done until (all four):
1. Root cause stated in one sentence, with the file:line;
2. A guard test exists that REDs if the bug returns — and you RED-PROOFED it (temporarily reverted the fix, watched the guard fail, restored it);
3. The class is checked, not just the instance (found a tz-mix in one function? grep every datetime subtraction on the same path; found one dead knob? run the params↔consumer reconciliation);
4. If the same class fired twice ever → graduate it into a permanent structural guard or reconciliation test (see test_graduated_guards.py, the params ratchet).

## Anti-patterns (each one burned this project before)
- **Tuning knobs before naming the cause** (timeouts, retries, sizes). If you can't say why it broke, you can't say why your knob fixes it.
- **Trusting a green wrapper**: LastTaskResult=0 while the inner python exited 1; `placed:true` meaning "not rejected," not "filled." Always check the layer that touches reality.
- **A monitor that stays RED on known-correct behavior** trains everyone to ignore RED — but the fix is to split real-fault from benign, never to delete the alarm (self_check tradeability fix, 06-30).
- **Repeating the failing action**: if your last two steps were "it failed" → "ran it again," STOP and go to Step 2.
- **Inheriting a wall**: "the data only goes to X", "that's blocked on Y" — re-MEASURE shared walls from source before accepting them (the 25-day OPRA wall was a stale comment; the data was on disk all along).
