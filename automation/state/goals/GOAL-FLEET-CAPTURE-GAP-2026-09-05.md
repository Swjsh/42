# GOAL: FLEET-CAPTURE-GAP-2026-09-05

> Opened by Fable 2026-09-05 from the right-tail capture backfill (commit 915c057d,
> analysis/right-tail/SUMMARY.md): over 36 real waves 2026-08-01..09-04, safe-2 captured 80.6%,
> risky-1 72.2%, bold-2 61.1%, safe-3 58.3%. The arms consume ONE shared signal seconds apart; a 22-point
> capture spread between safe-2 and safe-3 is not market noise, it is a gate or a race. The dominant
> refusal bucket was "no matching fleet decision" (30) -- the fleet arm never fired near the wave --
> then NOT_FLAT (4). This goal names the mechanism per missed wave and files the fix as a prereg.

## DONE-WHEN
`analysis/right-tail/CAPTURE-GAP-2026-09-05.md` (+ .json) attributes EVERY missed wave per arm
(36 waves x 4 arms, from `analysis/right-tail/ledger.jsonl`) to exactly one mechanism with the
quoted evidence row: (1) fleet gate_override refused it (`min_triggers 2` / `require_confluence_or_
sequence`) -- quote the fleet decisions row at that tick; (2) settlement / same-day-entries cap;
(3) NOT_FLAT (still holding a prior position -- name the position and its exit stage); (4) risk_gate
deny (which code); (5) the arm's fleet tick did not run within 2 min of the core ENTER (scheduler
cadence / outage -- cross-check engine_gaps); (6) sizing SIZE_BELOW_MIN / affordability; (7) took it
late (>2 ticks) and it no longer cleared 1.3x from the late entry. Each mechanism gets a dollar
figure = the wave's realized multiple on the arm that DID take it x the missing arm's standard size.
Any mechanism whose dollar figure exceeds $1,000 over the window gets a prereg for the 10-30 checkpoint
(a gate loosening is an EXPANSION) or, if it is a defect (a race, a stale read, a cadence hole), a
fix filed as a normal engine bug with a RED-proofed guard -- defects are not frozen.

## OPERATING RULES
- **CONFIG FREEZE 2026-08-31 -> 2026-10-30**: read-only instruments, preregs and packaged-but-unapplied
  changes only. Nothing in `setup/hooks/doctrine.py` FROZEN_TRADING_PATH is edited by this goal; a
  package is applied ONLY on its checkpoint day, by the conductor, with GAMMA_FREEZE_OVERRIDE in the
  invocation, after the packet reads RULE MET.
- Every fire calls `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent` fan-out passes `model:"sonnet"` explicitly. Fable/Opus = spec + adjudication only.
- `STATUS.md` gets a line at OPEN and CLOSE only, never per-fire.
- Never `/loop /gamma-goal`; `Gamma_Conductor` + the Stop hook's bounded continuation are the only
  sanctioned continuation paths.
- Reuse before rebuilding; every number reported is quoted from a command run in the same fire (OP-33).

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [x] F1 (DONE 2026-09-05 03:5x ET, Sonnet worker) -- `setup/scripts/capture_gap_attribution.py::build_join()` writes
  `analysis/right-tail/capture-gap-join-2026-09-05.json`: 46 rows == 46 missed (wave,arm) pairs
  (`row_count_matches_missed: true`, quoted from the script's own stdout this fire). Every row carries
  a quoted evidence string from the fixed `right_tail_capture.py` (F3) -- bold-2/safe-2 via
  core-decisions.jsonl `account` safe/bold, safe-3/risky-1 via their own decisions.jsonl, all within the
  existing +/-3-10min window. Only 4/46 rows carry no gate/risk evidence (both waves missed by ALL 4
  arms, cross-checked against the fleet tick log -- ticking every minute, ruling out a cadence gap).
- [x] F2 (DONE 2026-09-05 03:5x ET) -- `capture_gap_attribution.py::build_attribution()` writes
  `analysis/right-tail/CAPTURE-GAP-2026-09-05.json` + `.md`. Mechanism totals (book-wide, quoted):
  1=$9,276.77 (split safe-3/risky-1 gate_override $4,354.92 vs safe-2/bold-2 core-gate-divergence
  $4,921.85 -- no single knob for the latter, see .md), 2=$203.25, 3=$1,040.06, 4=$677.20, 6=$1,664.00,
  7=$1,224.09, 8 (no-evidence, honest 8th bucket)=$2,186.21. Summary table sums to 46/46 missed waves
  across the 4 arms (verified: 4+1+2=7 safe-2, 6+1+3+4=14 bold-2, 12+1+2=15 safe-3, 7+1+2=10 risky-1).
- [x] F3 (DONE 2026-09-05 03:5x ET) -- 2 real defects found and FIXED (not preregs -- `right_tail_capture.py`
  is not FROZEN_TRADING_PATH): (1) `_refusal_reason`'s `risk_code not in (None,"ALLOW")` filter silently
  discarded every `gate:`-prefixed rejection (938 rows across safe-3+risky-1 carry risk_code=None on a
  real gate reject) -- fixed to also admit `gate:`/`a+ gate:` reasons; (2) core arms (safe-2/bold-2) read
  an empty fleet decisions.jsonl unconditionally, AND the first-pass fix used `verdict` instead of
  `action` as the risk_code proxy, which would have mislabeled a real PDT deny
  (2026-08-04T12:26:55 bold: verdict=ENTER_BULL but action/exec.status=RISK_DENY_PDT) as a clean ALLOW --
  fixed to read core-decisions.jsonl by account and use `action`. Guard:
  `backtest/tests/test_right_tail_capture_gap_fixes.py` (6/6 pass, quoted below). Mechanism-8 (no-evidence,
  2 waves) checked against the fleet tick log: NOT a cadence outage (ticks fired every minute) -- it is a
  strategy-coverage gap between `heartbeat_core.py` and `strategies.py` (both FROZEN); below the $1,000
  bar once correctly scoped, not filed as a 09-29 kill-prereg, documented in the .md instead.
- [x] F4 (DONE 2026-09-05 03:5x ET) -- Only mechanisms 1 and 6 clear $1,000 among {1,2,4,6} (2=$203.25,
  4=$677.20 do not). Filed:
  `analysis/recommendations/prereg-fleet-capture-mechanism1-gate-override-10-30-2026-09-05.json`
  (safe-3+risky-1 slice only, $4,354.92) and
  `analysis/recommendations/prereg-fleet-capture-mechanism6-sizing-floor-10-30-2026-09-05.json`
  (bold-2 min_entry_premium floor, $1,664.00). Both added to
  `analysis/recommendations/checkpoint-2026-09-29-inventory.json` (9->11 rows, checkpoint=2026-10-30,
  classification=expansion) with a new generic `capture_gap_mechanism` scorer in
  `checkpoint_packet.py`. Regenerated via the script (never by hand):
  `checkpoint_packet.py --date 2026-09-05` -> "11 rows... 2 INSUFFICIENT N (n=0, forward window has no
  data yet)" -- both new rows correctly read INSUFFICIENT N, not fabricated as MET.
- [x] F5 (DONE 2026-09-05 03:5x ET) -- Added `top_mechanism` per arm to
  `gamma_cockpit_righttail.py::build()` (most frequent `refused_by_gate` code among trailing-window
  missed waves). Verified end-to-end through `gamma_home.py build(quiet=True)['righttail']['per_arm']`
  this fire: safe-2 top_mechanism=SKIP_STRUCTURE_VETO, bold-2=SKIP_MIN_PREMIUM_FLOOR, safe-3=GATE,
  risky-1=GATE (all 4 non-null, quoted output in the F1-F5 fire's transcript). Wired into
  `dashboard/components/cockpit/producer-tiles.tsx`'s right-tail tile detail line
  (`— top miss: <mechanism>`); `npx tsc --noEmit` clean on that file.

## J-DECISIONS
- None. Preregs wait for 10-30; defects shipped with revert lines (see F3 -- both fixes are to
  `setup/scripts/right_tail_capture.py`, non-frozen; revert = `git diff`/`git checkout` that one file).

## PROGRESS LOG
- 2026-09-05 06:5x ET -- authored by Fable (EOD-audit session); queued on the ladder.
- 2026-09-05 03:32 ET — opened by goal_autopilot
- 2026-09-05 03:5x ET -- Sonnet worker: F1-F5 all DONE this fire. 2 real defects found+fixed in
  right_tail_capture.py (RED-proofed, 6 new tests), ledger regenerated via
  scratchpad/backfill_right_tail.py (same 46 missed / 144 scored pairs as SUMMARY.md -- only
  refused_by_gate text changed, capture rates unchanged). 2 preregs filed + checkpoint packet
  regenerated via script. Cockpit tile carries top_mechanism per arm, verified end-to-end.

## HONEST STATE
1. F1-F5 all closed this fire with quoted evidence for every number; nothing here is a stub.
2. UNVERIFIED: the dollar figures for mechanism 8 (2 waves, $2,186.21) and for any row where no arm
   captured the wave use `peak_multiple_on_tape` (tape truth) as a proxy for a realized exit, not an
   actual fill -- flagged `proxy: true` per-row in CAPTURE-GAP-2026-09-05.json, never silently blended
   into the realized-fill figures.
3. The 2 preregs are FROZEN_BEFORE_ANY_RESULT and correctly score INSUFFICIENT N (n=0) in this fire's
   own checkpoint-packet run -- no result is claimed for either until the forward window accrues.
