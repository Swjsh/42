# G4 — Fleet divergence (Phase 1) — REVIEW SPEC (BLOCK-NEEDS-REVIEW)

**Status: BLOCKED-NEEDS-REVIEW (J nod, entry-path fleet-producer keystone).** Written by the
overnight loop 2026-07-08. This is a change to what the 4 live-paper fleet arms TRADE — it
ships under supervised review + an A/B, not an autonomous overnight edit (loop rule 4).

## The keystone bug
`automation/state/fleet/build_shared_signal.py` derives each arm's `passed` from the
**production ACTION** off the SAFE ledger (`build()` default: `passed = verdict.startswith
("ENTER_")`, `build_shared_signal.py:195-197`). Consequence: an arm can only ever be **TIGHTER**
than production — when Safe HOLDs, `passed=false` for every arm, so **the whole fleet is inert
exactly when Safe sits out.** The 4 loose arms (safe-1, safe-3, risky-1, risky-3) exist to be
LOOSER (one-gate-away, scoring-peak) and structurally cannot be.

Compounding (from the G10 recovered audit + replay_fleet_arms header): the live producer reads
the **DEAD LLM ledger** `decisions.jsonl` (not `core-decisions.jsonl`, the deterministic brain),
falls through to the beacon, emits `production_action=HOLD`, and benches all 4 arms.

## The divergence lever (already exists, default OFF)
`SCORING_PEAK_LIVE` + `_bold_passed_blocks()` (`build_shared_signal.py:287`) derive `passed` off
the **BOLD perception's scoring peak** (the `bold` core row), so loose arms read `signal['bold']`
and can enter when Safe HOLDs-but-scored-high. This is the intended Phase-1 divergence path.

## The TRAP (frame-fix in the SAME commit)
`backtest/tests/test_fleet_producer_keystone.py::test_scoring_peak_off_reverts_fleet_to_inert_BITE`
(L140) PINS the inert default — it asserts that with `scoring_peak=False` a gated A+ produces NO
bold entry. Enabling divergence **must frame-fix this test** (it currently encodes the bug as
correct behavior): keep a bite that scoring_peak=OFF is inert, but ADD the bite that scoring_peak=
ON produces the expected divergent bold entry. (L197 lesson.)

## The change (two parts) — DO NOT SHIP UNSUPERVISED
1. Drive the fleet producer off `core-decisions.jsonl` (the deterministic brain) instead of the
   dead `decisions.jsonl`. (Wiring change replay_fleet_arms REPORTS at the end — not applied.)
2. Enable `SCORING_PEAK_LIVE` so the loose arms read the bold scoring-peak perception + diverge.
3. Frame-fix the keystone BITE test in the same commit.

## Validation (required BEFORE ship)
`backtest/.venv/Scripts/python.exe backtest/replay_fleet_arms.py` — per-arm entry-fidelity gate;
PASS = MATCHED==ground-truth, EXTRA==0, MISSED==0 for each arm. It touches NO production file and
places NO orders. **Overnight-loop run result: <PENDING — folded in on completion; first run
produced no verifiable stdout (pipe/reaper), re-running clean>.**

## Why review, not auto-ship
Entry-path change to 4 live-paper arms + frame-fixing a keystone guard + a producer wiring change.
Even with a clean replay, this alters what the fleet trades and should get J's eyes. Revert =
single git revert of the wiring + flag flip. Recommended: J runs the replay in a supervised
session, confirms per-arm PASS, then flips `SCORING_PEAK_LIVE` + the core-decisions wiring.
