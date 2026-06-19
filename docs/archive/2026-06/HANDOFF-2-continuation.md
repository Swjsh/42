# HANDOFF 2 — Continue the post-overhaul work (everything except the shadow loop)

**Paste this whole file as the first message of a new Sonnet chat in this project.**
You are continuing work on Project Gamma after a large review + the first live trading day. Read top to bottom first. Do NOT re-do the review — it's done. Your job is the remaining fixes.

---

## Where things stand (as of 2026-06-15 evening, ET close +1h)
A deep review + overhaul happened. Already DONE and validated:
- **OP-11 Karpathy shadow loop fixed** (it was a silent no-op): `backtest/lib/shadow.py` now feeds real `params.json` as the prod baseline; `orchestrator.py` now actually applies the v15.3 ribbon gates + the bear-stop mapping. 17 tests pass (`backtest/tests/test_op11_loop.py`, `test_graduated_guards.py`).
- **C3 reconciled**: `params.json` exits set to v15 (tp1 0.50, runner 2.5, **bear −0.20 added**) — they were stale at v14 while the heartbeat already traded v15. Pin-check confirmed clean live today.
- **Doctrine consolidated** in `CLAUDE.md`: OP-22/25 "never stop" → **"compound, don't accumulate"** + "human holds the off-switch"; 53 inline lessons → an 18-row themed index. Lessons **L77** (the OP-11 bug) and **L78** (the FUSE-mount gotcha) recorded.
- **Today's live day**: system was dormant ~1 week (PC asleep at the morning trigger times). Got it reconnected; Bold caught a **BULLISH_RECLAIM on SPY 752C**, TP1 banked **+$474** (+42% on a $1,122 account), runner closed green at the broker. **Engine/strategy worked great — every failure was operational.**

**Read these first** (they have the full context): `DEEP-REVIEW-2026-06-14.md`, `PROGRESS-2026-06-14.md`, `VALIDATION-2026-06-14.md`, `IMPLEMENTATION-PLAN-2026-06-14.md`, `DOCTRINE-CONSOLIDATION-2026-06-14.md`, and `CLAUDE.md`.

## Environment gotchas — READ THIS (lesson L78)
Repo is a **FUSE mount** into a Linux sandbox; real files on Windows at `C:\Users\jackw\Desktop\42`.
- **git does NOT work in the sandbox** — corrupts itself. Git runs on Windows only via `setup/setup-git.ps1`. There is **no version control yet** — so **back up every file before editing**: `cp file _local_backups_YYYYMMDD/` (writes are allowed; deletes are NOT — `rm` fails).
- **The mount serves TRUNCATED reads of files you just edited.** Read/Grep tools (Windows side) see the full file — trust those. To run/validate Python, copy to **`/tmp`** and run with `PYTHONPYCACHEPREFIX=/tmp/pyc`.
- Sandbox Python = **3.10**; project venv (`backtest/.venv`) = **3.13**. Validate logic in /tmp; authoritative run is Windows.
- **NEVER run heavy work during market hours 09:30–15:55 ET** — it starves the live heartbeat's shared rate-limit pool (this caused today's blind window). Do all of this after-hours/weekends.
- You can drive the Windows machine via computer-use (TradingView is "read" tier — viewable, not clickable; File Explorer is full tier — run `.bat`s via the address bar). The TradingView/Alpaca MCPs are NOT in your chat session — they live in the heartbeat's headless runs.

## The remaining work (priority order)

### FIX 5a — sizing enforcement  ⚠️ NEEDS J's DECISION FIRST
**Problem:** Bold account `min_contracts: 5` (in `automation/state/aggressive/params.json`), account ~$1,122. A $2 option → 5 contracts = $1,030 = **92%** of the account, exceeding both the v15 40% max-premium gate (G6b) and the 50% risk cap. The gate is a **prompt instruction** in `heartbeat.md` (gate G6/G6b, ~line 636) and the LLM **skipped it**.
**Fix:** ask J to pick: **(a)** BLOCK the trade when `min_contracts × premium × 100 > equity × risk_cap` (safest — account too small for that premium); **(b)** lower `min_contracts` for sub-$2K accounts; **(c)** force a cheaper further-OTM strike that fits. **Recommended: (a).** Then — critically — **move the sizing check into CODE** (a small Python pre-order gate the heartbeat must call and obey), because the LLM demonstrably skips prose gates. Graduate it with a test like the ones in `backtest/tests/test_graduated_guards.py`.

### FIX 2 — broker-side stop-loss leg  (LIVE-ORDER CHANGE — be careful)
**Problem:** entries place an entry+take_profit bracket but `stop_loss: null` (see today's `current-position-bold.json` history). The stop is heartbeat-managed only — so a blinded heartbeat can't stop a LOSER until the 15:55 EOD flatten. Today's bracket TP leg saved a *winner*; the loser case is the scary one.
**Fix:** in `automation/prompts/heartbeat.md` and `automation/prompts/aggressive/heartbeat.md`, the `place_option_order` call should include a **broker-side premium stop-loss leg** as a disaster safety-net (e.g. at the `premium_stop_pct` level: Safe bear −20%/bull −8%, Bold bear −15%/bull −5%). Keep the tighter heartbeat-managed chart stop as primary; the broker stop is the catch-all. First **verify the Alpaca MCP `place_option_order` schema supports a stop/bracket leg** (read the tool params). Test on ONE paper entry and confirm the stop leg appears at the broker. Have J review before it's the default.

### FIX 4 — EOD close-recording from Alpaca
**Problem:** when the heartbeat blinds, the close never reaches `journal/trades.csv` (today's +$474 win wasn't journaled; the position file drifted to stale `open_runner` until manually reconciled). The EOD review then can't grade the day.
**Fix:** in the EOD flatten/summary step (`automation/prompts/eod-flatten.md` + aggressive, and/or the eod-summary), query Alpaca for the day's filled orders, reconcile against local position + `trades.csv`, and **journal any unrecorded close with the real fills**. Read + journal only — no live-order risk.

### FIX 1 — heartbeat isolation
Two branches depending on the shadow-loop result (HANDOFF 1):
- **If staying on Claude (paid):** wire `setup/scripts/run-heartbeat.ps1` + `run-heartbeat-aggressive.ps1` to export `ANTHROPIC_API_KEY` from a gitignored file (e.g. `automation/state/.heartbeat-api-key`) before the `claude --print` call, falling back to the Max plan if the file is absent. J creates the key (console.anthropic.com). ~$5–10/day, isolates the pool.
- **If the shadow loop proves Nemotron is good enough (free):** build the OpenRouter heartbeat harness instead. Bigger job — only do this after the shadow agreement numbers justify it.

### Lower priority / needs J direction
- **OP-16 / strategy gap (#17):** the engine captures little of J's anchor edge under real fills and the edge-floor is non-discriminating. Strategy-direction call — see `DEEP-REVIEW` §OP-16 and `PROGRESS`.
- **v15.3 parity (open from L77):** should `run.py` + the grinders load `params.json` so ALL backtests reflect v15.3 (not just the shadow A/B)? Changes the research baseline — get J's nod.
- **Git:** ask J to run `setup/setup-git.ps1` on Windows then `git push` to `github.com/Swjsh/42` — that's the rollback safety net for everything above.

## The meta-lesson from today (put this in front of J)
The **engine traded beautifully** — the BULLISH_RECLAIM at the 752 level the premarket flagged, TP1 +42%, runner green. **Every failure was operational**, not strategic: (1) rate-pool starvation blinded management (caused by an interactive Claude session during market hours), (2) no broker stop-loss leg, (3) prompt-only sizing the LLM skipped → 92% position, (4) state drift + un-journaled close. Fixes 1/2/4/5a close exactly those. Don't touch the strategy to fix operational bugs.

## When you finish each fix
Update `PROGRESS-2026-06-14.md` (append a dated section), back up originals, validate in `/tmp`, and tell J what changed + what still needs a Windows run or his decision. Mark it clearly if a change affects live orders.
