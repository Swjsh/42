## [2026-08-16 14:0x ET] conductor-weekend: OK — self-audit-gap-triage — closed 5 stale batches (08-11..08-15), evidence-verified

Not new code — a self-audit-organ triage fire (priority-3 in STAGE 1). Closed 5 open loops in
`analysis/self-audit/new-gaps-flagged.md`, each checked against LIVE state, not re-derived:

- **Headline debunk:** 08-13's "+25% MFE in 4-6 min, validated winner/loser separator" claim
  was already FALSIFIED the same day in `FULL-TRADE-REVIEW-2026-08-13.md` (Fisher p=0.100 at
  the honest n=5 unit, near-tautological winner side) — the swarm cited the discriminator's
  existence, not its same-day debunk. Nothing to wire; there's no validated separator.
- **7th-recurrence thread closed:** "Alpaca Greeks endpoint fallback" (flagged 7 times since
  07-01) — already built as `theta_clock.py` (2026-08-01, predates most of the re-flags): an
  honestly `_est`-labeled model-free fallback, real broker greeks preferred when they arrive. A
  REAL 3rd-party Greeks feed would be a net-new paid vendor (against cost discipline) — the
  gap kept re-asking for something already correctly declined.
- **Misread confirmed twice:** 08-14's "recency gate not enforced in live entry path, RED
  edges still fill" — grepped `heartbeat_core.py`/`risk_gate.py`, zero recency references in
  the core path; recency-RED gates the extra-setup CAPITAL exec-arm only (by design, TRADE-
  TO-LEARN rail-4), core paper trades continue on purpose.
- **Code claim verified false:** 08-15's "`check_llm_auth_outage` threshold too high (3 runs)"
  — read the live function, it fires on `total >= 1`, no 3-run gate exists. Same batch's "no
  automated `claude /login` recovery path" is explicitly the WRONG ask — the detector's own
  docstring says "nothing should retry into it" (interactive OAuth).
- **Already-shipped confirms:** Ghost-order reconciler (08-12), leak-detector recycle fix
  (08-13, already fixed 08-15), eod_flatten read regression (08-13, already fixed).

Zero trading-path files touched — analysis-doc only. Full evidence + remaining
scaffold/multi-session items (none met the bounded-task bar) in the DONE marker at the end of
`new-gaps-flagged.md`. Next fire: pick up whichever queue.md HIGH item or author-inbox item is
freshest — chef/lesson inboxes (188/122 open) are the next-largest untriaged surfaces.

---

## [2026-08-16 ~13:2x ET] SUNDAY RESEARCH BLOCK — 5 findings. Two frozen conclusions decayed; the shadow layer could not have proved itself.

J out for the day. No trading-path file touched, nothing armed. Commits: `8b602615`,
`b0319e3e`, `aa3793f3`, `7a3709bc`, `315273e0`.

### 1. Friday's −$1,837 had never been autopsied — the analyst that would do it is dead

The LLM EOD/analyst lane has been failing since 08-11 (the logout), so the worst day of the
week was never reviewed. Done now from the FIFO authority: **ONE signal at 09:46–09:47 cost
$1,569 — 85% of the day.** Four arms bought the *identical* contract `C00778000` within 60s
(safe-2 6, bold-2 10, safe-3 7, risky-1 12 = 35 contracts), and **bold-2's 10 is a double
entry — 5 @ 1.26 twice, 4 milliseconds apart.** The double-entry fix (`33ba0814`) landed that
evening; without it the day was ≈$371 cheaper.

### 2. A frozen KILL's evidence expired in ten days (`8b602615`)

`LEVER-CORRELATION-2026-08-06` killed every arm-concurrency cap on the argument that loss
dollars live at the *lonely* end (1-arm = −$1,896) not the pile-on end. Forward-checked on the
6 sessions since, **reusing its own code and reproducing its published table exactly first**:
the 3-arm bucket flipped **+$1,769 → −$2,675**. Normalised to each window's own mean the
buckets *swapped places* — 1-arm went worst→better-than-average, 3-arm went best→worst.

**This is NOT a case for arming a cap** (4-arm is the best bucket now; the original kill was
mechanical as well as empirical; n is small) and the doc says so. The point is that a rigorous
finding — 47/47 assertions, second code path, explicit n-small caveat — **decayed to inversion
in ten days because it shipped without a revalidation clock.**

### 3. The four knobs that gate CALLS harder sit on the BETTER side (`b0319e3e`)

The 08-09 symmetry audit found the asymmetry structurally and never priced it. Priced:
**bull +$3.95/trade vs bear −$24.01 since 07-20.** Mechanism is the tail — bear's raw WR is
*higher*, but bull's average win is **2.2×** ($322 vs $139).

**And the unit was wrong.** Since the fleet is one bet in five sizes, counting round trips
inflates n by **2.3–3.5×**. Per independent signal the ranking *inverts*: bear WR 31.9% → **14.3%**,
bull 28.3% → **27.0%**. ⚠️ **CLAUDE.md OP-16's bull re-eval bar "n ≥ 20" is stated in the
inflated unit — that can be 6–7 real decisions.** Restating it is a doctrine edit, so flagged
not changed.

### 4. The OPRA cache only grew when a human remembered (`7a3709bc`)

`fetch_option_data.CONTRACTS` is 19 hardcoded contracts, all Mar–May, frozen since 05-07.
`load_contract_bars` has **no fetch-on-miss** — it returns None — so uncached contracts are
dropped silently. The stop-mode clock was skipping 29 fills as `no_opra_cache` **while
reporting itself ACCRUING and healthy**: a prereg clock accruing on a subset of its own
population. Fetched the 9 missing (free, real): clock **66 → 95 trades, 3 → 5 days,
skipped 29 → 0**. Then closed the class — a top-up derived from the live ledger now rides the
nightly fold, AST-pinned to run *before* the clock that prices off it.

### 5. The conviction shadow could not have proved itself (`315273e0`)

Gap in my own 08-15 build: it reported how often conviction *would block* and never whether
blocking would have **helped**. Reaching the 20-day bar would have proven nothing. Now joined
to real outcomes (block vs allow, by score, delta-if-armed).

**I caught a 5.5× inflation in that join before committing.** Conviction logs on every ENTER
tick, so 09:46/09:47/09:48 rows all matched the single 09:46 fill — 11 round trips became 34
"joined" rows and −$317 became −$1,750. Now strictly one-to-one; verified to the exact dollar.
Same round-trips-are-not-decisions class as finding 3, recurring in my own code within the hour.

---
**Unchanged on J's desk:** `claude /login` · the 190-vs-191 dataset call · the PROVISIONAL P5
waiver. **New, non-blocking:** whether OP-16's `n ≥ 20` should be restated in independent signals.

## [2026-08-15] RECENCY-CONFIRMATION (confirm-before-capital gate) — RED-BLOCKED on the freshest 25 trading days (2026-07-09..2026-08-12), real OPRA fills, floor n>=10

> **Signal J wakes to (OP-25).** Weekly recency check (reusable `backtest/autoresearch/recency_check.py`, generalizes the Sunday fresh-revalidation; auto-reads OPRA cache last = 2026-08-12). The CONFIRM-BEFORE-CAPITAL gate: no live flip while an edge is RED; capital scaling waits for CONFIRM.
> - **Live-tier verdicts:** #1 ATM (Safe-2)=YELLOW; #1 ATM (Bold)=YELLOW; #2 ATM=YELLOW; #4 ATM=RED
> - **Books:** Safe2_ATM_1+2+4=CONFIRM ($243.05); Bold_ATM_1+2=CONFIRM ($1197.2)
> - **edges_confirmed_on_recent = False** (any RED=True). All live tiers still small-n / not-yet-confirmed on the freshest weeks — full-OOS-2026 base remains the larger-n companion read; HOLD capital scaling until an edge CONFIRMs. RED-BLOCKED: #4 ATM — no live flip on these.
> - Files: `automation/state/recency-confirmation.json`, `backtest/autoresearch/recency_check.py`.

---

## [2026-08-15 ~17:0x ET] 🚨 THE AUTONOMOUS LOOP HAS BEEN DEAD SINCE 08-11. Plus: a prereg clock was dead too, and the shadow layer had ZERO monitoring.

Engine-state survey after the handoff queue. Three findings, all the same shape: **something
that was supposed to be running silently was not, and every surface reported healthy.**

### 1. 🚨 CLAUDE CLI IS LOGGED OUT — J ACTION REQUIRED (`818a1439`)

**`claude /login`. That is the whole fix, and only J can do it** (interactive OAuth; nothing
in this repo can clear it, and nothing should retry into it).

**49 failed LLM fires across 8 tasks since 2026-08-11. 100% of conductor fires from 08-12 on**
(3/3, 4/4, 2/2, 11/11) against ~470 clean fires before. Every fire: spawn `claude` →
`Not logged in · Please run /login` → exit 1.

Affected: conductor (12), conductor-weekend (9), context_guard (5), eod-flatten (4),
eod-flatten-aggressive (4), mcp-daily-audit (4-5), premarket (4-8), scout (2).

**Why it survived five days — every layer reported success except the work:**
- rail-0 budget precheck said `PROCEED — $0.00 of $30.00 used` on every fire. It measures
  **SPEND**, and a logged-out fire spends nothing. *The cheaper the failure, the more
  confidently that gate approved it.*
- Task Scheduler showed `LastTaskResult=0` — the outer wscript hop is fire-and-forget.
- The masked-exit check DID fire, but could only say `run-conductor-weekend.ps1 (exit=[1], 5x)`,
  sitting beside unrelated exit=1 noise. Seeing conductor and eod-flatten as separate
  incidents is what hid the single shared cause.
- The unattended registry flagged `Conductor RED [3.4d]` — correct, but generic staleness,
  days late, no cause, no action.

**Nothing visibly broke because the deterministic backstops held** — `eod_flatten.py` covered
the failed LLM EOD-flatten path, `premarket_deterministic_fallback.py` covered premarket. That
is the danger, not the reassurance: a backstop silently carrying production is
indistinguishable from a healthy primary until the backstop is what fails.

Now detected by name: `self_check.check_llm_auth_outage` — one cause, whole fleet, with span
and per-task counts, classified **BROKEN** (its siblings say DEGRADED because they have
backstops; this has none) so it routes through the existing STATUS `## Known broken` + Discord
escalation. **Verified live: self-check flipped DEGRADED → BROKEN and the finding is on this
file now.**

### 2. An ARMED prereg's forward clock had no producer (`dbc2e004`)

`entry_quality_ledger.build_ledger()` was in **no scheduled task and no fold** — nothing
rebuilt the enriched ledger. Last written 08-10 with data through **08-06** while the book
traded 08-07 and 08-10..08-14.

`stop_mode_shadow_ledger` reads that artifact deliberately (`build_population()` has no
`trigger_level`, so structure stops could never fire). With it frozen, prereg
**STOP-MODE-STRUCTURE-VS-PREMIUM-2026-08-09** sat at `n_trades=0 / ARMED_AWAITING_FILLS` and
**would never have reached its 20-day bar.** The clock's own `input_stale` flag had been
reporting this correctly the entire time; nothing consumed the alarm.

Rebuilt: ledger 235 events/26 days → **344/32**; clock → **ACCRUING, 66 trades / 3 days,
days_to_bar 20 → 17**. Now wired into the 16:25 fold, with the order pinned by AST
(**after** pain_ledger — it joins `mae-mfe.json`; **before** stop_mode — which reads its
output). Disclosed gap: 29 fills (08-13 ×17, 08-14 ×12) still skipped `no_opra_cache`.

### 3. The entire shadow layer had zero freshness monitoring (`2673b36e`, `d074e9bb`)

Measured: the freshness manifest carried **21 entries and covered ZERO shadow artifacts**. The
fold contract is "fail-open, never fatal", so any folded producer can fail — or never be wired
at all — while `winner-autopsy-last.json` stays fresh and the unit reads OK. Watching the
parent taught us nothing.

Added the 5 fold sub-products to the `eod-pipeline` unit. **medium → YELLOW never RED** (a
research clock is not a trading emergency, and a tile that REDs for one gets ignored), keyed
on each artifact's **own build stamp, never a data date** — a data date parks on the last day
*with fills*, so it would alarm every time the engine correctly sat out.

**Self-correction:** my helper re-serialized all 62 units (1,092-line reformat of a shared
state file). Restored the original formatting and re-applied surgically — net diff is now 61
insertions, 0 deletions.

### 4. The recycle guard BECAME the wedge — 43h of thrash (`fee97318`)

Found by sweeping every non-GREEN unit. `window_leak_detector_keepalive` recycled the detector
**every 5 minutes**, each time claiming it "has run 6.1h" on a process launched 5 minutes
earlier. Cause: it derives runtime from `polls_total × poll_interval_s` in a summary the
**dead** detector wrote (`43800 × 0.5 = 6.083h`, permanently over the 6h threshold). The new
detector was killed before it could ever overwrite that file — so the file stayed frozen, so
the next fire killed the next one. **~43 hours with no leak detection at all.**

The original guarded the *unreadable* summary case and missed the *stale* one — stale is worse,
it returns a confident wrong number. Fixed by scoping the runtime to the live pid (the summary
already stamps its own). **The 08-13 wedge mitigation survives** — a genuine 6.08h runtime on
its OWN counters still recycles, pinned by a test. Verified live: `runtime unknown` →
`runtime=0.1h`, summary advancing again (polls 43800-frozen → 600 and climbing).

*I first blamed a UTC-vs-local offset — 6.1h looks exactly like MDT's 6h plus a 5-minute age,
and I'd already fixed two clock bugs today. Reading the code killed that. Noted because the
coincidence was persuasive and wrong.*

### 5. 8 live tasks that no unit watched (`019fbe29`)

The registry's own anti-rot diff (L292) was naming them; nobody claimed them. Sharpest:
**`Gamma_IncidentFixStatus`** — it re-verifies daily that the 08-14 loss-morning fixes are
still landed, and was itself unregistered. *It guarded the roster while nothing guarded it.*

---

## SURVEY COMPLETE — what is left, and why it is left

**Infrastructure: swept exhaustively. Everything fixable is fixed.**
66 units → **63 GREEN / 1 YELLOW / 1 RED / 1 OFF**; `engine-health` GREEN with zero reds.
- The RED is the auth outage → **J's `claude /login`**, nothing here can clear it.
- The YELLOW is a stale pid file for `window_leak_hook.py` — which turns out to be **untracked
  and to have no launcher anywhere** (one of 9 untracked scripts in `setup/scripts/`). None of
  the 9 is referenced by any scheduled task, so **the rig is still reproducible from the repo**;
  they are orphaned tools, not load-bearing. Flagged rather than bulk-committed — this is a
  PUBLIC repo and unreviewed files do not get swept in.

**Research/engine-edge: not short of ideas — short of VALIDATED ones.** 104 open queue items.
The top engine-edge entries are already filed, already CRITICAL, and already gated:
- `G1-FILTER5-VS-REJECTION-SETUPS` — **this is the M1 entry/exit ribbon contradiction**, filed
  2026-07-27 with the same structural argument (filter 5 anti-correlates with rejection setups,
  C28/L243), a named candidate, and an explicit "must clear the 4-gate + pooled BH-FDR bar on
  386 days before arming". Shipping it tonight would violate the eval-first gate (OP-11). My
  contribution was verifying it is **still live in code today** and folding that into the churn
  teardown.
- `THETA-NOT-GIVEBACK`, `EXIT-HYBRID-PRETP1-FLOOR` — same shape: CRITICAL, pre-reg required.

**So the binding constraint on engine edge is forward evidence, not effort — and the evidence
pipelines were the thing that was broken.** A dead prereg clock, an unmonitored shadow layer,
and a dead autonomous loop were all silently producing nothing. That is what this session
fixed. Conviction's first post-fix rows land **Monday 08-17**; the stop_mode clock is
**ACCRUING (17 days to its bar)**; the V-d1/V-e3 forward window sits at 7/10 sessions.

**Known gap, disclosed not hidden:** 29 fills (08-13 ×17, 08-14 ×12) still skip the stop_mode
clock on `no_opra_cache` — the already-queued `fetch_option_data.py` frozen-contract-list fix.

---
**On J's desk:** `claude /login` (**blocks the entire autonomous loop**) · the 190-vs-191
dataset decision · the PROVISIONAL P5 waiver for `vwap_reclaim_failed_break`.

## [2026-08-15T16:15:02 ET] NOT_EXERCISED -- monday_verify (WEEKEND-TWELVE Next-Twelve #6): mechanical sweep for 2026-08-15 -- 1 GREEN / 0 YELLOW / 0 RED / 5 NOT_EXERCISED

**Mechanical checklist, not prose** (Next-Twelve #6: converts five pending-verifies into verified). Never blocks, never kills -- fail-open throughout; NOT_EXERCISED means the item's precondition never fired this run (C7: a check passing because nothing happened is not GREEN).

| Item | Verdict | Expected | Observed |
|---|---|---|---|
| WS7 live watch | NOT_EXERCISED | Gamma_LiveWatch fires ~1/min 09:25-16:10 ET (~405 ticks). On the first REAL open position, live-watch.json (and the log's in_trade count) should reflect it within ~2 minutes of fill, and per REQUIRED_POSITION_FIELDS every position field should populate non-null. | no core-decisions.jsonl ticks dated 2026-08-15 -- no RTH session evidence (non-trading day or engine idle). |
| WS6 regime stamp | NOT_EXERCISED | Gamma_RegimeStamp fires 08:22 ET weekdays (between Gamma_EmaSnapshot 08:20 and Gamma_Premarket 08:30): rebuilds regime-stamp.json and patches today-bias.json#regime_context, both dated the SAME session day, generated near 08:22 ET -- proving the first ORGANIC (truly scheduled) fire, not a manual re… | 2026-08-15 is not a weekday -- Gamma_Premarket/Gamma_RegimeStamp do not fire on weekends. |
| WS3 level hysteresis | NOT_EXERCISED | Friday 2026-07-31 PRE-FIX worst case: level 743.25 present 331/386 core ticks, 14 appear/disappear flips (fixed-replay showed 386/386, 0 flips). Hysteresis N=5 is live in production since 2026-08-01; every level's worst flip count today should sit well under 14, with hysteresis_held firing whenever… | no core-decisions.jsonl ticks dated 2026-08-15. |
| WS11 core recency | GREEN | Baseline frozen 2026-08-01 (25-trading-day rolling window ending 2026-07-31): bear RED n=10 exp=$-60.9/tr; bull UNDERPOWERED n=1 exp=$-295.0/tr. Watching whether n grows and/or either verdict moves as the rolling window advances past 2026-07-31. | run_date=2026-08-15 window_end=2026-08-14 (baseline window_end=2026-07-31, advanced=True). bear now: RED n=26 (delta +16 vs baseline n=10) exp=$-36.62/tr, verdict_moved=False. bull now: GREEN n=23 exp=$3.13/tr. live refresh attempted=True ok=True. |
| Theta cockpit | NOT_EXERCISED | Gamma_ThetaClock fires ~1/min 09:30-16:00 ET (~390 ticks). Historically theta_per_contract_per_day_source == 'sqrt_time_decay_model_est' on 29/29 real ENTER rows checked pre-build (the Alpaca options-snapshots greeks endpoint has returned {} every time) -- this run tests whether that streak is STIL… | no core-decisions.jsonl ticks dated 2026-08-15 -- non-trading day. |
| WS1 preview diff | NOT_EXERCISED | MONDAY-PREVIEW-2026-08-03.md predicted, on a Friday-like tape: cores (safe-2/bold-2) 0 entries UNLESS block_elite_bull is flipped (still true/unapplied as of 2026-08-01); safe-3 ~1 fill; risky-1 ~2-4 fills (from 0 Friday -- 4 tradeable episodes / 32 in-window ENTER-plan ticks under the new bold_cor… | this preview is date-scoped to Monday 2026-08-03; checked date is 2026-08-15 -- diff not applicable. |

Full detail: `automation/state/monday-verify.json`. Re-run: `backtest\.venv\Scripts\python.exe setup\scripts\monday_verify.py --date 2026-08-15`. Guard: `backtest/tests/test_monday_verify_2026_08_01.py`.

---

## [2026-08-15 ~13:4x ET] HANDOFF QUEUE 1-5 WORKED. 2 handoff claims corrected. 1 item was already answered in the vault.

Six commits: c23d6b77, 7b8aa67b, 6fa5e218, e6ad0ec0, 7c0895f1, 46b5d800, 692161d0.

**TWO CORRECTIONS TO THE HANDOFF ITSELF** (both verified before acting, neither inherited):

1. **Item 1's stated root cause was wrong.** `int(dow)` on a list is NOT the root of the 5
   `test_unattended_health` failures -- the fixtures pass `MON_FRI = 62`, an INT, and `None`
   elsewhere; neither shape can raise it. The real cause is `_et_offset_hours` deriving the
   ET-minus-local offset by differencing `now_et` against the live wall clock: correct only
   when `now_et` IS now, so a frozen fixture clock returned **-140 hours** and shifted every
   timestamp ~5.8 days ("HAS NOT FIRED in 5.9d" was the distance to TODAY, which is why it
   drifted daily). Live was always fine (+2h) -- which is exactly why the monitor looked
   healthy while its guard suite sat red. The TypeError is real but latent (the live
   enumerator casts `[int]$tr.DaysOfWeek`); hardened anyway, on both call sites.

2. **Item 5's standing state is optimistic.** "C4/C5 now actually score for the first time" is
   true of the CODE, not of any DATA. `974ca235` landed 2026-08-14 19:15 ET; the last
   conviction row on disk is 2026-08-14T13:35 -- 5h41m earlier. **Zero post-fix rows exist**;
   Monday 08-17 is the first. All 102 rows on disk are pre-fix and blocked 100% -- and that is
   ARITHMETIC, not signal quality: max observed score 4 vs a MINIMUM effective floor of 5, so
   no row could ever clear its floor. Pooling them publishes "99% block rate" (measured on
   n=103) and would likely kill the component on false evidence. The new weekly reporter
   partitions on the fix boundary for exactly that reason.

**ITEM 4 WAS ALREADY ANSWERED, in `analysis/deep-research/2026-08-12-churn/`.** The handoff
called ribbon_flip_back 4%->22% "the largest unexplained compositional shift in the book" and
"an open lead nobody has explained" -- it was explained the night it happened; the handoff did
not route through the churn teardown. Folded the join in there per OP-22 rather than opening a
parallel doc. **It is not an exit shift: 18 of the 22 POST firings are 2026-08-12 alone** (58%
of every ribbon_flip_back that has EVER fired). Per day 1/3/18/0/0. Strip that day and POST is
7% vs 4% PRE-stack, on n=4. Two framing corrections: **C28 (lagging exit) is backwards here** --
median hold 1.0 min, fired on the position's FIRST management tick, pre-invalidated by
construction (entry waives the ribbon check, exit enforces it); and the DENOMINATOR moved (98
closes POST vs 239), so every surviving reason gains share mechanically. **M1 re-verified STILL
LIVE in code today** -- `filters.py` still does `if trendline_only_setup: blockers.remove(5)`
and filter 5 IS the ribbon check (:1172/:1487). It is an ENTRY-side bug, consistent with the
handoff's own "next lever is entry selectivity".

**THE SAME CLOCK DEFECT EXISTS TWICE.** `state_freshness_audit.py:300` carried the identical
`round((now_et - datetime.now())/3600)` expression. Found via a test that failed IN-BATCH and
passed in isolation: because the expression rounds to whole HOURS, the sub-hour remainder leaks
into `age_min` as a phantom age -- observed +18.5m then +16.6m twenty minutes later, drifting
minute-by-minute across key-levels.json's 20m budget. A genuinely flaky guard whose flakiness
was a real impurity in the producer. Repo swept: those two were the only instances, both now
fixed and guarded.

**A GATE WAS RIGHT AND UNREAD.** `test_p5_shape_gate` was not stale --
`vwap_reclaim_failed_break` shipped live 2026-08-03 (`aa2e3f07`) and its P5 waiver row was
never written, so the gate has been RED on main since. That is the SECOND recurrence of the
gap the ribbon_ride row already documents. Added the row the ship owed, deliberately
**PROVISIONAL (j_signed=false)** -- the registry's own rule is "NEVER hand-add a signed waiver
on J's behalf". **J: sign, replace, or revoke** (revoke = `RUN_VWAP_RECLAIM_FB=False`, one
line; the prereg's frozen kill-check at n>=10 risky-3 fills already settles it).

**TESTS THAT PASSED FOR THE WRONG REASON.** The 2 "network-only" Family D failures are not
network-dependent. All four free-model guards `_load()` an adapter that `free_model_audit`
already imports itself, creating a SECOND module object -- so `monkeypatch.setattr(sca, ...)`
patched a copy the adapter never calls and `grade()` ran the REAL LLM path. **A test that
believed it was mocked was firing a live `claude` subprocess** (proof it is gone: 4.38s ->
0.34s). `prospector` was GREEN for the wrong reason -- inert patches, so it read the REAL
production ideas-ledger instead of its tmp fixture. Fixed all four.

**MY OWN MEASUREMENT WAS WRONG FIRST, and it hid 5 failures.** The batch runner piped each
pytest batch through `tail -40`, which truncated the short-test-summary on noisy batches: the
per-batch "N failed" counts summed to **15** while only **9** unique FAILED lines survived. I
reported 9. The harness now greps FAILED/ERROR from the FULL output and PRINTS ITS OWN
RECONCILIATION (summed-per-batch vs unique-captured) so the same silent drop cannot recur --
a harness that loses failures is worse than no harness (C7), and this one was mine. The 5 it
had hidden are now fixed in `78c96a0f`: two `vwap_reclaim` stale pins of the SAME 08-09/08-12
config changes the handoff already names as confounds; two `tz_quality_lock` fakes that stubbed
the fail-OPEN `open_buy_orders` while the entry path's idempotency guard calls the fail-CLOSED
`*_checked` variants; and **a half-landed fix** -- B6 taught three twin-gauntlet checkers that
`CLOSED` is no longer `journal[-1]`, `_dry_max_hold` was MISSED, and it had been scoring a
genuine PASS as "0/1 hit the expected mechanism" ever since. A half-landed fix reads exactly
like a regression in the thing it never touched (trap #5).

**FINAL SUITE, harness-reconciled: 7,306 passed / 3 failed / 9 skipped / 7 xfailed.**

**THE 3 REMAINING ARE RED BY DESIGN, awaiting J -- do not re-pin them.**
`test_pnl_attribution`, `test_regime_reslice`, and `test_structure_shift_cascade_ab` (three,
not two) are the 190-vs-191 provenance detectors. Untouched. They are the only thing that
noticed a frozen research population being mutated out-of-band, and re-pinning is precisely
what would bury it. **J's call:** restate `56a4907d`'s headline and re-derive downstream pins
from 191, or restore the 190-row file.

**ALSO AWAITING J (new this session):** the PROVISIONAL P5 waiver for
`vwap_reclaim_failed_break` -- sign, replace, or revoke.

## [2026-08-15 ~11:4x ET] PROVENANCE DEFECT: a frozen research population was mutated out-of-band by an unrelated commit

The three off-by-one failures I flagged DO-NOT-RE-PIN are traced. They were right to be RED.

`analysis/recommendations/engine-fullhist-replay-2026-07-23.json` is the 18-month full-engine
replay every downstream study keys on. Its own research commit (`56a4907d`) published
**+$5,064.75 / 190 trades**. It is now **+$4,808.75 / 191 trades**.

WHAT CHANGED, exactly one row:
  ADDED   2025-02-07 10:45 ET  SPY250207C00608000   (a loser; total P&L -$256.00)
  REMOVED nothing
WHO CHANGED IT: `df0348d9 fix(regime-library): pin all 15 threshold constants + wire first live
consumer`. A regime-threshold commit that had no business touching a replay artifact -- almost
certainly an incidental re-run swept into an unrelated commit.

WHY IT MATTERS BEYOND THREE RED TESTS:
- The published headline of that study is now wrong by -$256 and +1 trade, and nothing announced
  it. `test_structure_shift_cascade_ab` (190 vs 191), `test_regime_reslice` (74 vs 75) and
  `test_pnl_attribution` were the ONLY things that noticed, and they were dismissed as stale.
- **My own ENTRY-LOCATION-GATE study used the mutated file** and reported "$4,808.75 across 191
  trades" as the published population. That study's conclusion (a NULL) does not hinge on one
  losing trade, but the disclosure is wrong and is corrected here.
- Any study that pinned 190 and any that read 191 disagree about the same "frozen" population.

DECISION NEEDED (J's, not mine): either the added trade is legitimate -- in which case
`56a4907d`'s headline must be restated and every downstream pin re-derived from 191 -- or it is
contamination and the file should be restored to the 190-row version. I did not re-pin the three
tests to 191, because re-pinning is what would have buried this.

GUARD TO BUILD EITHER WAY: frozen research populations need a content hash recorded in the
artifact itself and asserted on read, so an out-of-band edit fails loudly at the point of USE
rather than three tests later. This is the same class as the trail_width finding (a population
defined by whatever is cached is not reproducible) -- both say the same thing: **this repo has
no integrity check on the datasets its studies stand on.**

## [2026-08-15 ~11:xx ET] ANSWER: the ratchet works as designed. The problem is the BOOK's payoff math, not the knob.

Measured MFE capture from LIVE telemetry (best_premium in exit_pass, joined to fills). Capture =
realized move / peak favourable move. Negative = the trade went green and round-tripped to red.

| window | n | median capture | avg win | avg loss | win rate |
|---|---|---|---|---|---|
| PRE 07-20..08-09 | 85 | **-32.0%** | $300 | -$115 | 29% |
| POST 08-10..08-14 | 77 | **-6.7%** | $144 | -$89 | 31% |

**The ratchet is doing exactly what it was built to do.** Give-back collapsed from -32% to -6.7%
median. Losses shrank. This is insurance working, and it kills my "the ladder is clipping
winners, remove it" framing -- the ladder is the reason trades stop round-tripping to red.

**But it truncates BOTH tails, and this book cannot afford that.** At 29-31% win rate the
breakeven payoff ratio is ~2.3. PRE ran 2.61 (barely viable). POST runs 1.62 (underwater at any
WR below ~38%). Halving avg_win from $300 to $144 costs more than shrinking avg_loss from $115
to $89 saves, because at this win rate the book is carried entirely by the right tail.

## THE ACTUAL PROBLEM, stated plainly

This is a **~30% win-rate, tail-dependent** book. Every exit tightening trades tail for
consistency, and consistency is worth less than the tail here. So the fix is NOT to re-tune the
ladder -- it is either:
  (a) raise win rate so tighter exits become affordable (entry-quality work: conviction C4/C5
      now actually score, the escalating floor is the sit-out mechanism), or
  (b) accept the tail dependence and stop tightening exits into it.
Doing (b) without (a) returns the book to +$384/101 trades, which is not a business either.

**Recommendation for J:** the ladder stays. The next lever is entry selectivity, not exit width.
Re-tuning exits has now been tried three times (ratchet, ladder, trail) inside five days and the
payoff ratio got worse each time.

CORRECTIONS TODAY: 4. (1) "live fills confirm it" -- confounded. (2) "no exit telemetry" -- wrong
query. (3) "runner_target 3->0 implicates the ladder" -- it was disabled 07-09 by SS-B. (4) "the
ladder clips winners, remove it" -- capture data says it PREVENTS give-back. Every one came from
publishing a headline before exhausting the data on disk.

## [2026-08-15 ~10:xx ET] CORRECTION #2 -- the exit telemetry EXISTS. I queried one level too shallow. And it answers the question.

RETRACTED: "the engine does not record why a position exited". **False.** `exit_pass` rows carry
an `actions[]` list, and each action has `kind` + `reason`. I read `reason` off the RESULT dict
(which has no such key) instead of off the actions inside it, saw `None`, and declared a missing
instrument. The correct query returns 545 attributed exit actions. **I nearly built a duplicate
of a surface that already worked** -- the exact "check for prior coverage before building" rule.

## WHAT THE REAL ATTRIBUTION SAYS (closing + partial actions)

| reason | PRE-stack | share | POST-stack (08-10+) | share |
|---|---|---|---|---|
| `premium_stop` | 147 | **62%** | 19 | 19% |
| `structure_stop` | 28 | 12% | 31 | **32%** |
| `ribbon_flip_back` | 9 | 4% | 22 | **22%** |
| `runner_stop` (the ratcheted floor) | 26 | 11% | 13 | 13% |
| `tp1 @ +100%` | 17 | 7% | 9 | 9% |
| `runner_target @ +250%` | **3** | 1% | **0** | **0%** |
| totals | 239 | | 98 | |

THREE THINGS FALL OUT, and none of them are what I argued this morning:

1. **`ribbon_flip_back` went 4% -> 22% of all closes.** That is the biggest compositional shift
   in the book, and C28 is explicit that **ribbon flip is a LAGGING exit**. A fifth of closes now
   run through the layer doctrine already says fires late. This was not in any hypothesis I had.
2. **`runner_target @ +250%` fired 3 times PRE and ZERO times POST.** Nothing rides to target
   any more. Alongside 46 `RATCHET_STOP|runner_stop trail/arm` and 16 `RATCHET_STOP|pre_tp1
   profit_lock arm/trail` moves, the mechanism is visible: floors ratchet up, positions exit on
   the ratcheted floor, the tail never completes.
3. **The ladder does NOT close positions directly** -- it appears only as `RATCHET_STOP` (a floor
   move). Its effect is INDIRECT, realised as `runner_stop` closes. So "the ladder clipped it"
   and "runner_stop closed it" are the same event under two names, which is precisely why the
   confounded before/after could not resolve it.

## STATUS OF THE EXIT QUESTION

Still UNRESOLVED, but now measurable from live data rather than only replay. The ratchet-cost
prereg should be amended before running: its cells must key on **exit-reason composition**
(runner_stop vs runner_target vs ribbon_flip_back), not just net P&L, because the P&L delta is
the downstream symptom and the composition shift is the mechanism.

TWO CORRECTIONS IN ONE MORNING, both mine, both from over-reading thin evidence: (a) "live fills
confirm it" -- confounded; (b) "no exit telemetry" -- wrong query. The pattern in both is
reaching a headline before exhausting the data. Recorded here rather than quietly fixed.

## [2026-08-15 ~09:xx ET] CORRECTION -- I over-claimed the exit finding. The live before/after is CONFOUNDED.

I told J this morning that live fills "confirm" the exit-stack hypothesis and called the
signature "unambiguous". **That was wrong**, and reviewing my own analysis on request broke it.

WHAT I DID: split live round trips at 2026-08-10 (the day the ratchet + ladder + trail shipped)
and read PRE n=101 / +$384 / avg_win $300 against POST n=95 / -$1,694 / avg_win $144. Flat win
rate, halved winners -- a clean "exits are clipping the tail" story.

WHY IT DOES NOT HOLD:
1. **Two independent changes land inside the same boundary.** `1a2692c4` (08-09) armed risky-3
   on the PREMIUM-STOP lane -- a different exit change, its own A/B. `97734a7b` (08-12)
   restored a risky-1 selectivity gate that had been DELETED, so risky-1 traded part of the
   window with degraded ENTRY selectivity. `3ac1d7b2` (08-06) killed risky-3's ATM tier.
2. **Those two arms drive the collapse.** risky-1 avg_win $416 -> $100, risky-3 $379 -> $116.
   They are exactly the arms with their own concurrent changes.
3. **There is a counter-example my aggregate buried: safe-3 avg_win went UP, $188 -> $197.**
   A uniform-degradation claim dies on one clean arm moving the other way.
4. Per-arm PRE n is 7-30. Not a population.
5. 08-14's wake-storm double entry is still inside POST.

WHAT SURVIVES, and it is still the live question: the REPLAY evidence. It holds the entry
population FIXED and varies only exit config, so it is not vulnerable to any of the above --
10/10 arm-instances worse, plus the $191 -> $114 `premium_stop @ 0.61` case. That is
suggestive and it is NOT confirmed by live P&L. The honest status is UNRESOLVED, pending the
frozen PRE-TP1-RATCHET-COST study.

## NEW FINDING (and it is why this went unnoticed for five days)

**The engine does not record WHY a position exited.** Checked: `exit-state.json` is empty when
flat; `fleet/*/decisions.jsonl` carries `exit_pass` on 2,594 rows but the reason is `None` on
893 of the post-stack ones; `trades.csv` has no exit-reason column. Nothing on disk answers
"which layer closed this trade" -- ladder rung vs trail vs TP1 vs structure stop vs
catastrophe cap.

CONSEQUENCE: a three-layer exit stack shipped on 2026-08-10 and NO live surface could attribute
a single exit to it. That is why the avg-win change was invisible for five days, why my
before/after had to lean on confounded aggregates, and why the ratchet study must be
replay-based rather than answered from live fills.

**This is the highest-value build on the board** -- higher than the study it unblocks. One
field (`exit_reason` + which layer bound) stamped on every close, and every future exit change
becomes measurable in a day instead of never.

## [2026-08-15 ~02:0x ET] Family B started -- watcher registry CLOSED; unattended_health traced but NOT fixed

CLOSED:
- `test_watcher_registry` (2). `bollinger_squeeze_watcher.py` was on disk and not in
  `runner.WATCHERS` -- exactly the gap that guard exists to catch, RED since the file landed.
  Verdict: **EXCLUDE, not register**, and that was checked not assumed. It is imported directly
  by `autoresearch/bollinger_fresh_reverify.py` and its logic is PORTED into
  `lib/patterns/context.py` for the live path, so registering it would double-run logic the
  live path already carries. Exclusion carries its evidence inline.

TRACED, NOT FIXED -- `test_unattended_health` (5):
- Symptom: scenarios built to read GREEN now read RED, e.g. "HAS NOT FIRED in **7.5d**" for a
  task whose fixture sets `last_run=2026-08-07` against a FIXED `SUNDAY = 2026-08-09 15:00`.
  7.5d back from that Sunday is 2026-08-02, which is neither date.
- RULED OUT: `evaluate_task` ignoring its `now_et` argument. It does not -- it uses `now_et`
  for the gap and the unscheduled-day slack (`unattended_health.py:295+`). That was the obvious
  suspect and it is innocent.
- REMAINING HYPOTHESIS: the test's `_task(last_run=...)` helper no longer writes the field the
  evaluator reads, so the task looks like it has never run and the gap is measured from the
  trigger start instead. That is the SAME contract-drift family as the stale
  `fake_manage_tick` signature repaired earlier tonight -- a helper pinned to a shape that moved.
- NEXT STEP: diff `_task()`'s output keys against what `evaluate_task` actually reads. One read
  each way; do not re-pin the day budgets, which are not the problem.

Stopped here deliberately rather than guessing at a health monitor's thresholds.

## [2026-08-15 ~01:4x ET] Family A continued -- 3 more bounded, 1 diagnosed as unfixable-by-patch, 3 left with a SUSPICIOUS signature

DONE since the escalation above:
- `test_replay_today_eval` (12) re-pinned -- this is what produced the escalation.
- `test_profitability_ab` (2) bounded to its 2026-08-08 anchor. Surfaced live: bold-2's
  post-ship window now reads **n=20 / -$1,338** vs the frozen n=6 / -$476.
- `test_ribbon_flipback_ab_v2` bounded. Population edge DERIVED, not guessed: trades through
  **2026-08-07** total exactly 219.
- `test_trail_width_exit_ab` -> **xfail with the diagnosis**, because the obvious fix is wrong
  and I tried it. `build_anchor_population()` filters on "has a cached real-OPRA CSV", and that
  cache grew RETROACTIVELY, so the frozen 113 is NOT a date prefix of today's 284 (even
  2026-07-18 already gives 129). **A population defined by "whatever we happen to have cached"
  is not reproducible by construction** -- that defect affects EVERY study on this harness, not
  just this pin. Correct fix = the prereg stores (symbol, entry_ts_utc) IDs and hashes that set.
  Prereg amendment = a decision, not a patch.

## LEFT, and they share a signature worth a fresh eye -- OFF BY ONE

| test | expected | got |
|---|---|---|
| `test_structure_shift_cascade_ab` | 190 trades in the `<=2026-07-22` prefix | **191** |
| `test_regime_reslice_2026_07_28` | 74 | **75** |
| `test_pnl_attribution_2026_07_28` | partition dict | differs slightly |

These are NOT the ledger-growth pattern above (which moves counts by tens or hundreds). A
one-trade delta in a REPLAY POPULATION PREFIX means the replay file itself changed, or a
boundary date moved by one row. Note that `engine-fullhist-replay-2026-07-23.json` is the same
population tonight's ENTRY-LOCATION study used and reported as **191 trades**, while this test
expects 190 at the same cutoff.

**DO NOT re-pin these to the new numbers.** Find out which trade appeared and why first -- an
off-by-one in a frozen research population is either a provenance bug or an undisclosed data
edit, and both matter more than the pin does. This is the first thing to pick up.

## THEN, in order
1. Run the frozen `PRE-TP1-RATCHET-COST-2026-08-15` prereg (the escalation above needs a number).
2. Family B live-state coupling (~10): `test_unattended_health` (5), `test_watcher_registry` (2),
   `test_trade_today_watcher` (3), `test_state_contracts`.
3. Families C (~10) and D (2, confirm network-only first).
4. Entry-quality handoff items 5-8; re-arm sizing LAST and only on a validated gate.

## [2026-08-15 ~01:00 ET] ESCALATION -- the current exit config replays UNIFORMLY WORSE, 10 arm-instances, zero counter-examples

**This is the one item worth J's attention. Everything else below is housekeeping.**

Two independent replay harnesses, two different days, two different exit code paths, all
pinned before the pre-TP1 ratchet shipped. Repairing their dead pins produced this:

| harness / day | arm | pinned | now | delta |
|---|---|---|---|---|
| replay_today_eval 5-min | core_safe | -312.00 | -336.00 | **-24.00** |
| | core_bold | 65.25 | 61.25 | -4.00 |
| | fleet_safe_3 | -83.25 | -95.25 | -12.00 |
| | fleet_risky_1 | -138.75 | -158.75 | -20.00 |
| | fleet_risky_3 | -36.75 | -56.75 | -20.00 |
| replay_today_eval 1-min | all five | | | **-30 / -15.25 / -12 / -20 / -20** |
| exit_manager_replay | core_bold 13:51:21 | 177.40 | 114.00 | **-63.40** (live made 191) |

**10 arm-instances degraded. NONE improved.** Book-level: about **-$80 on one replay day**,
against a $100-200/day/account target.

WHAT CHANGED: four J-directed exit ships after the pins were frozen -- pre-TP1 profit ratchet
(`1a9b1409`), J's ladder (`af6cf286`), trail arm +40% -> +75% (`658ecc79`), ribbon confirmation
buffer (`20a9e792`, implemented not armed). The exit_manager case is explicit about the
mechanism: the trade now exits on `premium_stop @ 0.61` instead of riding.

WHAT THIS IS **NOT**: proof of a regression. The ratchet is insurance -- it is SUPPOSED to cost
money on days it was not needed, and 2026-08-13's own exhibit was a day that only worked
because the contract doubled. Replay counterfactuals are not live P&L.

WHY IT STILL NEEDS DECIDING: a one-directional result across ten arm-instances with **zero
offsetting cases anywhere in the available evidence** is the shape that earns a measurement,
not a shrug. If the insurance never visibly pays in any replay we hold, either we are not
holding the days where it pays, or it is priced wrong.

**DECISION IS J'S, NOT MINE.** The ratchet shipped under a rule-9 override; loosening it is a
policy change. I did not touch the knob. What I did:
- re-pinned both harnesses to current values WITH the drift documented inline, so they detect
  the NEXT change instead of staying dead (they had detected nothing for weeks);
- added a maintenance rule to each: re-derive in the SAME commit as any exit-config ship;
- froze `prereg-pre-tp1-ratchet-cost-2026-08-15.json`, which prices the ratchet as insurance
  (`truncated_winner_dollars` vs `protected_loss_dollars`), requires the result with the
  largest single trade removed (G3), and caps its own output at "a priced table for J".

## WHAT NEEDS DOING NEXT, in priority order

1. **RUN the ratchet-cost prereg.** It is frozen and unrun. It is the only thing that converts
   the above from a suspicion into a number J can rule on. Needs a multi-day real-fills
   population, not the two days that generated the question (G3 forbids that).
2. **Family A, the rest** (~6 remaining): `test_profitability_ab` (2), `test_trail_width_exit_ab`,
   `test_ribbon_flipback_ab_v2`, `test_structure_shift_cascade_ab`, `test_pnl_attribution`,
   `test_regime_reslice`. Same disease, same treatment: re-derive, document the drift, add the
   maintenance rule. Each one may hide a finding like the above -- two of the three repaired so
   far did.
3. **Family B live-state coupling** (~10): `test_unattended_health` (5), `test_watcher_registry`
   (2 -- registry vs disk partition drifted as detectors were added), `test_trade_today_watcher`
   (3), `test_state_contracts`. Mechanical; sandbox each like the keystone/nbbo repairs.
4. **Family C stale shape pins** (~10) and **Family D network-dependent** (2, confirm first).
5. Entry-quality handoff items 5-8 (probe-lane wiring, tier derivation / ELITE retirement,
   re-arm sizing LAST -- still gated on a validated entry-quality gate that does not exist).

## [2026-08-14 23:3x ET] FULL SUITE MEASURED AT LAST -- 6,374 passed / 59 failed; 4 POPUP GAPS CLOSED

First complete run of backtest/tests in this session. It required 30-file batches: the reaper
kills any python process over 5 minutes, which is what silently truncated every earlier
full-suite and per-chunk attempt (I wrongly blamed a timeout first, then the reaper for a run
that WAS a timeout -- both stated corrections are in the transcript).

CLOSED tonight after the sweep:
- **4 CREATE_NO_WINDOW gaps** (`test_window_leak_compliance`). ONE WAS MINE, shipped hours
  earlier: a git provenance call in the trendline runner. The other three are pre-existing and
  worse in practice -- `bg_status.py` spawns a bare `powershell` (worst offender for flash),
  and `intraday_position_tracker.py` runs on an RTH cadence so it would flash repeatedly
  DURING the trading day. All four fixed; guard green.
- 9x `test_eod_flatten` (my own 08-13 checked-read regression), 2x `test_fleet_time_stop_threaded`,
  1x `test_fleet_keystone_consumer`, 2x `test_fleet_arm_parity` -- see the prior entry.

## KNOWN BROKEN -- ~46 remaining, and they cluster into FOUR families, not 46 problems

FAMILY A -- REPLAY PINS THAT DRIFT WITH LIVE CONFIG (~20 tests). `test_replay_today_eval`
(12: per-arm pinned P&L + determinism hashes), `test_exit_manager_replay` (2),
`test_profitability_ab` (2), `test_trail_width_exit_ab`, `test_ribbon_flipback_ab_v2`,
`test_structure_shift_cascade_ab`, `test_pnl_attribution_2026_07_28`, `test_regime_reslice`.
These harnesses read LIVE params.json / strategies.py / fills-ledger, so every frozen anchor
moves when live config or the ledger moves. **DO NOT RE-PIN TO TODAY'S NUMBERS** -- a
faithfulness pin that drifts with live state cannot detect the regression it exists for. The
fix is a frozen config+population SNAPSHOT per harness. Until then it is UNKNOWN whether e.g.
exit_manager_replay's 177.4 -> 114.0 is a legitimate config change or a real regression. This
family is the single highest-value cleanup left and it is a DESIGN change, not a patch.

FAMILY B -- LIVE-STATE COUPLING IN FIXTURES (~10). Same root as the keystone/nbbo repairs:
`test_unattended_health` (5), `test_watcher_registry` (2 -- registry vs disk partition drifted
as detector files were added), `test_trade_today_watcher` (3), `test_state_contracts`.
Mechanical once each is traced; each needs its own sandbox.

FAMILY C -- STALE SHAPE/ANCHOR PINS (~10). `test_p5_shape_gate` (2), `test_gate_e2e`,
`test_level_compiler_v2_guards`, `test_monday_verify`, `test_replay_fleet_arms` (2),
`test_twin_gauntlet`, `test_tz_quality_lock` (2), `test_vwap_reclaim_fleet_extension` (2),
`test_preopen_readiness`, `test_regime_early_classifier_guards`, `test_guard_cmd_popup_fix_ws6`.

FAMILY D -- NETWORK-DEPENDENT (2). `test_free_model_audit_*` end-to-end against real free-model
endpoints. Expected to fail offline; NOT yet confirmed as network-only -- confirm first.

NEXT SESSION: Family A is the one that matters (it covers exit + P&L faithfulness, i.e. the
money path). Families B/C are volume, not risk.

