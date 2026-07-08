# HANDOFF 2026-07-09 — TRUTH & EXITS

**Written by Fable 2026-07-08 evening after the full-day audit + self-review. Executor: Sonnet
(all judgment calls are pre-made here; do NOT re-litigate them, DO verify every claim you build
on). Two STOP checkpoints route interpretation back to Opus/Fable/J — do not cross them alone.**

## THE FIRM IN 5 BOXES (hold this model; every task below lives in one box)
```
BRAIN → HANDS → BROKER → OBSERVERS → J
core signal   fleet places   Alpaca = truth   ledgers/pings/digests   decides
```
2026-07-08 proved: Brain works (09:51 ELITE ENTER_BEAR = J's exact 745-rejection read). Hands
work (09:52, all 4 fleet arms filled 741P ~$0.97, `risk_code: ALLOW`). Broker holds the truth.
**OBSERVERS are the broken box** — they read the Brain's diary (decisions.jsonl) instead of the
Broker's bank statement, which produced a week of "0 fills ever" while the fleet traded daily.
J's box is overloaded (64 tasks, ~7 status surfaces). This handoff: point every gauge at the
Broker (WS1), study the exit shape that turned a correct trade into a loss (WS2), design the two
chart concepts J trades that the engine lacks (WS3), shrink the cockpit (WS4).

## GROUND RULES — the traps that ate 2026-07-08 (violating any of these voids the work)
1. **⏰ EVERY broker/state timestamp is UTC unless it carries an offset.** Alpaca
   `transaction_time` ends in `Z` = UTC. 13:52Z = 09:52 ET. THREE separate wrong narratives on
   07-08 came from reading Z-times as ET (including in Fable's own audit). Convert via
   `setup/scripts/et_clock.py` before ANY reasoning about "when." Never Bash `TZ`.
2. **Broker = truth for fills/P&L. Ledgers = decisions only.** decisions.jsonl / core-decisions
   structurally lack fleet fills (reconciliation only runs on the core path). Any "did we trade /
   how much" number must originate from Alpaca activities/orders.
3. **Verify-don't-claim (OP-33):** every "done" needs the actual output quoted from THIS session.
   Exit code 0 ≠ working. Registered ≠ firing (trigger `StartBoundary` already past on install
   day = task never repeats that day — bit us twice).
4. Every code change: **red-proofed guard** (revert → RED → restore) + path-scoped commit +
   pre-commit gate PASS (if a guard trips, FIX the cause — e.g. document new tasks in
   SCHEDULED-TASKS.md + bump the count — never `--no-verify`).
5. **NO entry-path changes** (gates, triggers, level feeds, shapes the engine trades) without an
   A/B on real fills AND the STOP checkpoint. Shadow/observability work ships freely (paper).
6. `page_size` max is 100 on Alpaca activities. Paginate with `page_token` for full history.
7. Market hours: building is allowed (engine is pure-Python, pool-independent) but NEVER edit
   live-engine files 09:30–15:55 ET. Observability modules (new files) are fine anytime.

---

## WS1 — TRUTH (P0, do first, all shadow/observability — ships freely)

### T1. Broker-truth fills instrument (the keystone)
Build `setup/scripts/broker_fills.py`: pulls FILL activities for ALL 6 accounts
(`fleet_broker.load_creds()`, paginate `page_token`, backfill since 2026-06-25), normalizes
(UTC→ET via et_clock, symbol, side, qty, price, account), pairs round-trips per (account,
symbol), computes realized P&L, and writes:
- `automation/state/fills-ledger.jsonl` (append-only, deduped by activity id)
- `automation/state/pnl-statement.json` — per-account + per-day: n_fills, realized P&L,
  engine-vs-manual attribution. **Attribution rule (pre-decided):** fleet arms (safe-1, safe-3,
  risky-1, risky-3) = 100% engine. safe-2/bold-2 = manual UNLESS the order matches a PLACED row
  in that account's decisions ledger (then engine). Crypto = manual, excluded from engine P&L.
**Acceptance:** (a) reconstructs 2026-07-08 fully — expect **~28 fill IDs** (morning 8 = the
741P round trip −$283ish, PLUS an uncounted ~13:08–13:20 ET cluster — Fable's audit missed it;
the total day P&L is the FIRST real deliverable of this task); (b) fleet lifetime P&L within
~$50 of the equity-implied check (starting equities 2000 each → current ≈ 1877/1802/1642/1838 →
expect ≈ **−$840 ± drift**); (c) quote the numbers in your report.
Schedule it (10-min RTH + one EOD fire) via the wscript→pythonw pattern
(`setup/install-level-memory.ps1` is the clone target). **Register the trigger StartBoundary
in the FUTURE** (ground rule 3) and verify TWO consecutive scheduled fires advance LastRunTime.

### T2. Rewire every fill-truth consumer onto T1 (kill the mirror class)
- `setup/scripts/sim_live_parity.py` (currently scans decisions.jsonl → reported "0 fills ever")
- `setup/scripts/fill_funnel.py` (NOT_FLAT/PLACED counts stay ledger-based — those ARE decisions
  — but any fills/P&L figure must come from T1)
- the EOD digest / analyst pipeline (find where it states "trades today" — 07-08's digest was
  almost certainly wrong; regenerate it from T1 as proof)
- `trade_today_watcher.py` already reads the broker — leave it; just point its file into the
  same dedup store if trivial.
**Graduated guard (required):** a test asserting no fill-truth surface derives fills/P&L from
decisions ledgers — grep-based static check over the four consumers, red-proofed. This encodes
the May-13 lesson ("poll Alpaca for 'did we trade'") as code, which is how it should have been
stored all along.

### T3. Alert delivery — the last yard (the ONLY reason J missed the first fill)
The 09:54 ET "FIRST ENGINE FILL EVER" ping was queued AND drained by the bridge (outbox line
~1505) — J never saw it. Diagnose the Discord hop: which channel does the bridge post to
(`.discord-config.json` channel_id) vs where J actually looks? Send ONE test ping end-to-end and
get **J's human confirmation he sees it on his phone**. If the channel is wrong, fix the config
(J: say which channel you watch). Acceptance = J's word, nothing less.

### T4. PDT policy consistency (doctrine hole, decide-and-document — no behavior change)
Core risk_gate enforces Rule 7 via pdt_tracker (blocked the 09:51 entry; count was REAL — J's 8
manual round-trips). Fleet arms log `day_trades: 0` and don't check (safe-1 has 10 by pdt_tracker
yet entered ALLOW). On paper Alpaca doesn't enforce, so this is a doctrine/live-readiness gap,
not a bug. **Pre-made call:** document the asymmetry in `markdown/0dte/risk-rules.md` (fleet =
paper-only until PDT-wired; core = enforced) + file the wiring task in queue.md. Do NOT wire PDT
into the fleet now (it would silence the only trading arms while the exit study runs).

## WS2 — EXITS (P1 — the money question)

### T5. Shape provenance (investigation, read-only)
The 07-08 fleet trade ran `tp1_premium_pct: 1.5, premium_stop_pct: -0.2`, trailing runner_stop
0.84 off HWM 1.08 (~22% trail), no partial TP. Which frozen arm config produced this shape
(automation/state/fleet/accounts.json + arm params)? Was it ever validated on real fills, or is
it an unratified default? Map arm → shape → provenance (scorecard link or "NONE"). Quote the
config lines.

### T6. Exit-parity study on ALL real fleet fills (now possible because T1 exists)
For every real fleet round-trip since 06-25 (n expected 40–90): replay the SAME entries under
candidate shapes on real quote/OPRA data — (a) the actual shape, (b) v15.3 Safe ratified shape
(tp1 +30%, tp1_qty_fraction 0.8, −50% cap, chart-stop), (c) J-style scalp (80% off at +50%,
runner with chandelier), (d) no-trail hold-to-time-stop. Report per-shape realized P&L,
WR, drop-top-3, and specifically: **how many stopped-then-thesis-paid trades does each shape
surrender** (07-08's morning trade is the type specimen: stopped −19% at 10:01, SPY paid the
thesis by 11:00). OPRA discipline: ONE process, reaper-exempt venv.
### ⛔ STOP CHECKPOINT 1: results go to Opus/Fable/J for interpretation. Do NOT change any live
shape yourself regardless of how decisive the numbers look. A shape change is an entry-path
change (ground rule 5).

## WS3 — CONCEPTS (P2, design + shadow only — the two reads J trades that no producer captures)

### T7. Role-flip (support-broken-becomes-resistance)
J's entire 745 edge on 07-08: 745.4 was support (07-07 wick shelf), broke overnight, therefore
resistance today — confirmed by the 13:30 tag-746.09-close-744.39 rejection. No producer holds
the concept (key-levels tagged 745.21 "support" all day). Spec + implement in the SHADOW layer:
when price CLOSES through a level with memory_score ≥ X and stays beyond it for N bars, flip its
role and tag `flipped_at` + provenance. Feed key-levels-memory.json (shadow) only. Guard with
the 07-07→07-08 tape as the golden test. NO live key-levels.json write (that's G11, blocked).

### T8. Multi-day trendlines
`trendline_engine.py` fetches ONLY today's bars — it structurally cannot represent J's line from
07-06 15:30 (752.29 wick). Extend lookback to N=5 days, anchor on multi-day swing wicks
(all-wicks-or-all-bodies, never mixed — J's rule, keep it). **Golden acceptance test:** it must
reproduce J's line — anchors at/near 07-06 15:30 @ 752.29 descending through 07-07's afternoon
lower-high — and project 744.2–745.5 for 07-08 13:30 ET (where the real 746.09-tag rejection
happened). Shadow file only (trendlines-live.json).

## WS4 — SHRINK (P2 — J: "the project is so big I can't grasp it")

### T9. One page = the whole firm
Build `setup/scripts/firm_brief.py` + ONE daily output (`automation/state/firm-brief.md`, EOD +
premarket fires): engine P&L yesterday/today from T1 (broker-truth), one line per engine trade
(entry→exit→shape verdict), what's blocked on J (max 3, from the J-DECISIONS lists), one system
health word (from self_check). Everything else becomes a feeder. Discord-ping the brief link
daily. Acceptance: J can answer "how's the firm" from one screen.

### T10. Task census (kill the sprawl)
64 scheduled tasks. Classify every Gamma_* into KEEP / MERGE / KILL with a one-line reason
(orphan producers with no consumer = KILL per OP-22; the audit keeps finding dark ones). Target
< 40 after merge. Propose-only doc → J approves the kill list in one message. Do NOT unregister
anything without the approval.

---

## J-DECISIONS (carry-forward — surface in T9's brief until answered)
- **Account split**: J's manual trading in safe-2 burned the core's PDT budget (blocked its only
  valid entry 07-08) + contaminates measurement. Rec: J manual-trades a dedicated account the
  engine never touches. [J: yes/no + which account]
- D4 Safe-2 paper-reset to $2K w/ epoch ledger (rec: yes, strengthened)
- D5 min-1 contract for single-exit shapes (Rule 6 amendment)
- D6 activate EOD-flatten backstop cd-2026-06-27-001 (rec: yes)
- D-SIP $99/mo Algo Trader Plus (unlocks REAL volume — free IEX undercounts ~28x — J's
  volume-shelf reads need this) [J: yes/no]
- Which Discord channel does J actually watch (for T3)?

## DEFINITION OF DONE (for the executor's final report)
1. `pnl-statement.json` exists, scheduled, and its 07-08 + lifetime numbers are QUOTED.
2. The mirror-class guard is red-proofed and green.
3. J has confirmed, in his own words, that he received a test trade-ping.
4. T6 results table delivered to STOP CHECKPOINT 1 (not acted on).
5. T7/T8 golden tests green in shadow.
6. Every claim in the final report carries its quoted evidence per OP-33.
**Tells you're failing:** you asserted a fill count from a ledger; you read a Z-time as ET; you
"fixed" an exit shape; a task you registered shows an empty NextRunTime or never fired twice.
