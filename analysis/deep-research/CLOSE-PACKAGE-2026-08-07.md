# CLOSE PACKAGE — 2026-08-07 (staged during market hours, applies ≥ 15:55 ET)

> Prepared by Lane 5 while `market_hours=True` (verified `setup/scripts/et_clock.py`:
> **2026-08-07 12:01:24 Friday EDT** at lane start; re-checked through the session).
> **Zero trading-path files were edited by this lane** — verification block at the end.
> The orchestrator applies each item below AFTER re-verifying the clock (≥ 15:55 ET)
> and re-running the quoted guards. Ordered by evidence class:
> **A. DEFECT fixes → B. cleared-battery cells → C. preregs.**
>
> Day context (broker-verified 11:46 ET): day −$629.46, all arms flat since 10:02, ONE
> trade per arm, one stop, **zero re-entries — the Wednesday spiral shape did NOT
> recur.** risky-3's 12x 774C@0.62 was the first live fill under last night's OTM-2
> tier revert. Then 10:15–11:45: **182 verdicts, all HOLD; 70 ticks carried live bull
> triggers** (level_reclaim + confluence, bull_score 10/11) refused by exactly the
> rotating volume doors: **sole-[10] ×54, sole-[7] ×10, [7,10] ×6** (re-counted from
> `core-decisions.jsonl` this session, not quoted from memory) while SPY ran
> 770.50 → 773.17. Monday's directive — "make sure nothing is gated that actually
> works" — is the package's charter.

---

## Lane-1 deliverable folded in: filter 7's bull-side identity (named from source)

`backtest/lib/filters.py:1352 _bullish_volume_divergence_failed` — **bull filter 7 =
"volume-divergence recovery" veto**: a green breakout bar followed within 1–2 bars by a
red bar that closes down with volume ≥ the breakout bar's volume ⇒ setup invalidated
(mirror of the bearish volume_divergence check). It is a **bar-vs-bar volume
comparison** — which makes it feed-sensitive in exactly the way measured below. Today
was its first material sole-block day (10 sole-[7] trigger ticks; prior max was 2 on
07-29).

---

## NEW MEASURED EVIDENCE (this lane, committed `0a45d396`)

**The live engine's volume filters are partly reading feed lottery, not market
volume.** `heartbeat_core._fetch_spy_5m` (line 287) fetches `feed=iex` — one fetch, so
bar and baseline are same-feed (the strong "different feeds for bar vs baseline"
suspicion is **REFUTED**; provenance traced, not assumed). But the ratifying backtest
population is SIP-scale, and the IEX fraction of consolidated volume is small and
**unstable**: mean 3.4–4.5%/day, bar-to-bar 1.3–8.2%. Re-scoring the SAME rule on both
feeds (`backtest/tools/feed_divergence_f10_f7.py`, mirror-guarded, 46/46):

| Day | bars | f10 verdict flips | f7 verdict flips | direction (f10 over-block/over-pass) |
|---|--:|--:|--:|---|
| 08-03 | 77 | 11 (14%) | 10 | 6 / 5 |
| 08-04 | 77 | **20 (26%)** | 9 | 11 / 9 |
| 08-05 | 77 | 9 | **19 (25%)** | 8 / 1 |
| 08-06 | 77 | 9 | 9 | 4 / 5 |
| 08-07* | 30 | 3 | 5 | **3 / 0 (one-way)** |

*partial day to ~12:00 ET; full-day re-run is step 2 of the evening addendum.

- **Honest split:** across the week the noise is **bidirectional** — a variance
  defect, not a systematic winner-suppressor. Today it happened to be one-way.
- **The 11:05 exhibit:** SIP printed 987,522 (a ~2× baseline surge — real buying) while
  IEX printed 12,799 (**1.3%**). The surge scored as a dead bar. Live ticks
  **11:15–11:18 and 11:30 were sole-[10]** with level_reclaim+confluence — the
  **+$70.8/entry PAY-cohort shape** (ENTRY-QUALITY-2026-08-06, n=55) — and under SIP
  volume both become **ENTER_BULL (@773.02 and @773.54)**. Priced EST only until the
  evening addendum re-prices on real OPRA.
- **Also refuted:** "f10 collapsed when the IEX tail shipped 08-03" — per-day f10 block
  rate was already 62–72% on 07-28..07-31 vs 52–83% after; no discontinuity. The engine
  has been IEX-fed all along; 08-03 changed the level pipeline, not this.

---

## A. DEFECT-CLASS FIX (applies unconditionally at ≥ 15:55)

### A1 — bull f10 knob threading (C14 dead-knob defect; behavior-neutral plumbing)

**Defect, one sentence:** the frozen prereg
`bull-f10-buyer-pressure-prereg-2026-08-04.json` varies `f10_vol_mult` ONLY, but in
BOTH engines that knob does not exist independently — live
(`heartbeat_core.py:647-654`) and backtest (`orchestrator.py:1030,1075`) hard-tie
`f10_vol_mult = filter_9_vol_multiplier` — so the prereg is **un-shippable as tested**:
flipping the shared key would silently relax bear f9 too, a cell no battery ever ran.

**(a) Exact diff:** [`analysis/staged/f10-bull-knob-threading-2026-08-07.diff`](../staged/f10-bull-knob-threading-2026-08-07.diff)
(5,447 bytes, `git apply --check` CLEAN against HEAD, quoted this session).
- `setup/scripts/heartbeat_core.py`: new module-level `_bull_f10_vol_mult(account_params)`
  → `filter_10_vol_multiplier_bull` if present else `filter_9_vol_multiplier` (default
  0.7); `bull_kwargs` routes through it.
- `backtest/lib/orchestrator.py`: `_params_to_kwargs` maps the new params key; new
  `run_backtest(f10_vol_mult_bull: Optional[float] = None)` param; both bull call sites
  (primary + engine-score assert-agree mirror) use
  `f10_vol_mult=(f10_vol_mult_bull if f10_vol_mult_bull is not None else f9_vol_mult)`.
- **Byte-identical when the key is absent** (it is absent in both params files today) —
  the fallback expression reproduces the exact current tie; both patched files
  py-compile clean.

**(b) Guard test (IS the RED-proof), written + run this session:**
`backtest/tests/test_f10_bull_knob_threading_2026_08_07.py` (committed `0a45d396`;
env-gated `GAMMA_STAGED_2026_08_07=1` so the standing suite stays green pre-apply —
without the env it reports `8 skipped`).
- **RED (pre-apply, live tree):** `7 failed, 1 passed` — quoted:
  `FAILED ...::TestHeartbeatCoreHelper::test_key_absent_falls_back_to_f9_knob` (+5
  more) and `AssertionError: expected the bull f10 fallback expression at exactly 2
  call sites, found 0`. The 1 pass (`test_params_to_kwargs_absent_stays_absent`) is a
  no-regression pin legitimately true in both states — disclosed.
- **GREEN (patched copies, sys.modules shadow — no live file touched):** `8 passed in
  0.12s`, module provenance asserted in-run (imports resolved to the patched
  scratchpad copies, printed and checked).
- Activation: `analysis/staged/f10-guard-activation-2026-08-07.diff` (845 B, apply-check
  CLEAN) deletes the env gate so the guard runs unconditionally from apply-time on.

**Apply checklist (~2 min, zero judgment):**
1. `python setup/scripts/et_clock.py` — confirm ≥ 15:55 ET.
2. `git apply analysis/staged/f10-bull-knob-threading-2026-08-07.diff`
3. `git apply analysis/staged/f10-guard-activation-2026-08-07.diff`
4. `backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_f10_bull_knob_threading_2026_08_07.py backtest/tests/test_feed_divergence_tool_2026_08_07.py` → expect **8 passed + 46 passed**.
5. `backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_engine_gates_parity.py backtest/tests/test_audit_fix_heartbeat.py` (regression net around the touched surfaces) → unchanged counts vs pre-apply.
6. `python setup/scripts/commit_scoped.py "feat(engine): thread bull-only filter_10_vol_multiplier_bull knob (behavior-neutral; enables frozen f10 prereg)" setup/scripts/heartbeat_core.py backtest/lib/orchestrator.py backtest/tests/test_f10_bull_knob_threading_2026_08_07.py`
7. `git show --stat HEAD` — exactly those 3 files (C35/L247).

**(c) One-line revert:** `git revert <sha>` (pure addition + two expression edits; no
other commit touches these hunks — nothing else calls `_bull_f10_vol_mult` /
`f10_vol_mult_bull` yet).

**(d) Kill criterion (frozen n):** n = **1** — any live tick after apply where bull
`f10_vol_mult` ≠ `filter_9_vol_multiplier` while `filter_10_vol_multiplier_bull` is
absent from that account's params (detectable via the engine-score assert-agree, which
runs the same expression on both paths, plus the guard suite) → revert same evening.

**(e) REVOKE line (append to `automation/overnight/STATUS.md`):**
```
### SHIPPED (REVOKE-eligible): 2026-08-07 evening — f10-bull knob threading
- Threaded filter_10_vol_multiplier_bull (live heartbeat_core + backtest orchestrator, OP#4 both-sides). BEHAVIOR-NEUTRAL: key absent in both params files, fallback = the exact old f9 tie; guards 8+46 green, RED-proofed pre-apply. Enables the frozen 2026-08-04 f10 prereg without touching bear f9. Revert: git revert <sha>. J: REVOKE = say the word, one revert, zero residue.
```

---

## B. CLEARED-BATTERY CELLS (conditional — mechanical either way)

### B1 — `filter_10_vol_multiplier_bull` value flip (ONLY if Lane 2's battery cleared)

Lane 2 (task L2-3) owns executing the **frozen 2026-08-04 prereg battery**: cells
{0.7 baseline, 0.5, 0.35, 0.0} × full 391-day real-OPRA population, added-cohort gates
frozen in the prereg (OOS-positive AND WF ≥ 0.70-or-disclosed-null AND sub-window
stable AND anchor-no-regression AND drop-best AND **added-cohort n ≥ 20**). At package
freeze the battery result **had not landed** — the orchestrator resolves this at 15:55+
by reading Lane 2's committed verdict artifact (expected under
`analysis/recommendations/`, rule_id `bull-f10-buyer-pressure-relax`):

- **IF exactly one non-baseline cell clears ALL frozen gates:** after A1 is applied and
  green, add `"filter_10_vol_multiplier_bull": <winning_cell_value>` to
  `automation/state/params.json` AND `automation/state/aggressive/params.json`
  (prereg's kill rule names both files), commit via
  `commit_scoped.py "feat(gate): bull f10 vol_mult -> <val> per cleared 2026-08-04 prereg battery" automation/state/params.json automation/state/aggressive/params.json`.
  **Kill criterion (frozen in the prereg, restated):** n ≥ 10 fills/account or 10
  sessions, net added-cohort < 0 → restore 0.7 (delete the key — one-line revert).
  **REVOKE line:** `### SHIPPED (REVOKE-eligible): f10_vol_mult_bull -> <val> (cleared frozen battery <artifact>); kill: n>=10 fills/10 sessions net<0 -> delete key.`
- **IF no cell clears, gates fail, or the battery did not run:** **nothing ships.**
  Record in STATUS.md: `f10 value flip NOT applied — <gate that failed / battery not landed>; prereg stays frozen, runner re-queued (BULL-F10-PREREG-RUNNER, automation/overnight/queue.md line 14, now 4th exhibit).`
- **Never liftable via this package:** filter 11 (Rule 2 firewall, per the prereg).

### B2 — bull f7 relax — **NO cell exists to clear tonight**

Filter 7 has **never had a prereg** (today is its first material sole-block day,
n=10 ticks — n-small). Lane 2's L2-4 freezes it; my feed evidence (5/28 bars
f7-divergent today, 9–19/77 across the week) goes in as mechanism evidence. **Nothing
f7 ships tonight by construction** — prereg-before-evidence discipline holds even
under Monday's directive.

---

## C. PREREGS COMMITTED TONIGHT (forward clocks, nothing armed)

1. **`analysis/recommendations/feed-consolidated-volume-prereg-2026-08-07.json`**
   (NEW, this lane) — consolidated-scale volume for the volume filters (f10/f7/f9).
   4 cells frozen (status-quo / yfinance-consolidated / delayed-SIP-baseline hybrid /
   threshold-recalibration=the existing f10 prereg, not duplicated). Full gate battery
   + sim-accuracy gate. **Forward clock: weekend grind 08-08/09; auto-STALE
   2026-08-14.** Gate status tonight: **not run — runner does not exist yet** (stated
   plainly; that is the build).
2. **BULL-F10-PREREG-RUNNER** (queue.md line 14) — if Lane 2's L2-3 lands tonight this
   closes; else it is the queue's 4th exhibit and rides the same weekend clock.
3. **GATE-EXPIRY-SOLE-BLOCKER-MINER** (queue.md line 13) — queued 08-03, still not
   built; today is its 3rd exhibit. Build target `backtest/autoresearch/
   gate_expiry_check.py` is OUTSIDE this lane's market-hours writable set —
   stays queued for the evening/weekend, explicitly NOT silently dropped.
4. **F7 prereg** — owned by Lane 2 (L2-4); if it does not land tonight, the owed item
   is recorded here: freeze BEFORE any relax cell is ever run (graveyard discipline).

---

## D. Evening re-price addendum (MANDATORY before anything in B applies)

Today's 0DTE OPRA lands ~16:21 ET. **Every intraday counterfactual number for today in
this package and in Lanes 2/3's artifacts is EST until then.** One command:

```
backtest/.venv/Scripts/python.exe backtest/tools/reprice_close_package_2026_08_07.py
```

(committed `0a45d396`; clock-gated ≥ 16:21 with `--force` test override — refusal path
verified live this session, rc=3 with the correct message at 12:22 ET). It runs (1)
`postfix_gate_costing --start 2026-08-07 --end 2026-08-07` → real-OPRA pricing of
today's sole-[10]/sole-[7]/joint refusal cohorts incl. the named 11:15 @773.02 and
11:30 @773.54 events, (2) full-day `feed_divergence_f10_f7 --date 2026-08-07`
(supersedes the PARTIAL-DAY artifact), then prints CONFIRM/CORRECT lines vs the lanes'
EST artifacts (missing artifacts print SKIPPED — C7, never silent). **Supersession
rule: the real-OPRA numbers replace every EST cell; if a sign flips, the affected
package item is OFF and the STATUS line says which.**

---

## E. Honest negatives / what did NOT happen (they matter)

- **The Wednesday spiral did not recur.** One entry per arm, one stop, zero
  re-entries, kill switches untouched. The engine's morning behavior was disciplined;
  the day's damage is one −$629 stop cluster on a PDH push that pulled back.
- **The refusal window was NOT all defect.** 25/28 bars agree on f10 across feeds
  today; midday volume genuinely sagged. Under SIP the 10:15–11:00 refusals stand;
  only the 11:15/11:30 events convert. The A/B (B1) — not this package — decides
  whether 0.7x itself is miscalibrated.
- **Feed noise is bidirectional across the week** — fixing it is a variance/quality
  play, not a guaranteed P&L lift; the prereg says so in its own against-section.
- **bold is PDT-dark until 2026-08-12** (3/3 day-trades, risk gate correctly refused 8
  ENTERs today per STATUS.md self-check) — Monday-readiness for bold is a PDT fact,
  not a gate fact.
- **Graveyard untouched:** nothing here re-proposes filter-5 deletion, filter-8 relax,
  stop-width changes, standdowns, or cooldowns.

---

## Verification block (this lane)

```
$ git status --short -- setup/scripts/heartbeat_core.py backtest/lib/orchestrator.py \
    backtest/lib/filters.py automation/state/params.json automation/state/aggressive/params.json \
    automation/state/fleet/accounts.json
(empty -- zero trading-path modifications)
```

Files created by this lane, all committed via `commit_scoped.py` (bare git banned):
`0a45d396` = 2 staged diffs + 2 guard-test files + 2 tools + 5 feed-divergence
artifacts; this document + the feed prereg follow in the package commit. RED-proof and
GREEN-proof runs quoted in §A1 were executed fresh this session (12:0x–12:2x ET).
`analysis/staged/` diffs apply-checked against HEAD at generation time; the 15:55
orchestrator re-runs `git apply --check` before applying (another lane may move HEAD —
if a diff no longer applies clean, STOP and re-generate from the committed generator
logic rather than force).
```
GAMMA_STAGED_2026_08_07=1 pytest backtest/tests/test_f10_bull_knob_threading_2026_08_07.py -> 7 failed, 1 passed (RED, pre-apply)
green_proof_driver (patched copies via sys.modules) -> 8 passed in 0.12s (GREEN, post-apply-equivalent)
pytest backtest/tests/test_feed_divergence_tool_2026_08_07.py -> 46 passed (live drift guard)
```
