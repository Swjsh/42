# CAPTURE-GAP-2026-09-05 -- fleet capture-gap mechanism attribution

GOAL-FLEET-CAPTURE-GAP-2026-09-05 F2. 46 missed (wave, arm) pairs classified, 46 join rows (MATCH).

## Mechanism vocabulary

1. fleet gate_override refused it (min_triggers 2 / require_confluence_or_sequence) -- or, for the two core (non-gate_override) arms, this account's OWN entry gate (structure veto / quality-lock / time-window filter) blocked it on this account's own tick while the OTHER core account's ribbon fired
2. settlement / same-day-entries cap
3. NOT_FLAT -- still holding a prior position
4. risk_gate deny (a named risk/veto code)
5. the arm's fleet tick did not run within 2 min of the core ENTER (scheduler cadence / outage)
6. sizing SIZE_BELOW_MIN / affordability
7. took it late (>2 ticks) and it no longer cleared 1.3x from the late entry -- or was SKIPPED outright as too-late to qualify
8. NO EVIDENCE -- no gate/risk/NOT_FLAT/sizing/lateness row found in-window on any source AND the fleet tick was confirmed ticking every minute (ruling out mechanism 5's literal cadence-outage reading); the fleet strategy registry itself never recognized this setup. Does not cleanly match 1-7 -- reported honestly as its own bucket rather than force-fit.

## Per-arm x mechanism dollar table

| Arm | Mechanism | N missed | Dollar estimate |
|---|---|---|---|
| safe-2 | 1 (fleet gate_override refused it (min_triggers 2 / require_con...) | 4 | $2,399.36 |
| safe-2 | 2 (settlement / same-day-entries cap...) | 1 | $203.25 |
| safe-2 | 7 (took it late (>2 ticks) and it no longer cleared 1.3x from t...) | 2 | $1,224.09 |
| bold-2 | 1 (fleet gate_override refused it (min_triggers 2 / require_con...) | 6 | $2,522.49 |
| bold-2 | 3 (NOT_FLAT -- still holding a prior position...) | 1 | $344.77 |
| bold-2 | 4 (risk_gate deny (a named risk/veto code)...) | 3 | $677.20 |
| bold-2 | 6 (sizing SIZE_BELOW_MIN / affordability...) | 4 | $1,664.00 |
| safe-3 | 1 (fleet gate_override refused it (min_triggers 2 / require_con...) | 12 | $2,140.48 |
| safe-3 | 3 (NOT_FLAT -- still holding a prior position...) | 1 | $235.59 |
| safe-3 | 8 (NO EVIDENCE -- no gate/risk/NOT_FLAT/sizing/lateness row fou...) | 2 | $740.78 |
| risky-1 | 1 (fleet gate_override refused it (min_triggers 2 / require_con...) | 7 | $2,214.44 |
| risky-1 | 3 (NOT_FLAT -- still holding a prior position...) | 1 | $459.70 |
| risky-1 | 8 (NO EVIDENCE -- no gate/risk/NOT_FLAT/sizing/lateness row fou...) | 2 | $1,445.43 |

## Mechanism totals (book-wide)

| Mechanism | Total dollars |
|---|---|
| 1 | $9,276.77 |
| 2 | $203.25 |
| 3 | $1,040.06 |
| 4 | $677.20 |
| 6 | $1,664.00 |
| 7 | $1,224.09 |
| 8 | $2,186.21 |

## Every missed row, with quoted evidence

- **2026-08-04 2026-08-04T12:26:03 / bold-2** -> mechanism 4 (`RISK_DENY_PDT`): `RISK_DENY_PDT: BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)`
- **2026-08-05 2026-08-05T11:46:03 / bold-2** -> mechanism 4 (`VETOED_BY_MODELS`): `VETOED_BY_MODELS: BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates (tier TRENDLINE)`
- **2026-08-05 2026-08-05T11:46:03 / safe-3** -> mechanism 1 (`GATE`): `GATE: gate: 1 triggers < 2`
- **2026-08-06 2026-08-06T10:31:03 / bold-2** -> mechanism 1 (`SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY`): `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY: blocked by entry gate require_bearish_fill_bar`
- **2026-08-06 2026-08-06T10:31:03 / safe-3** -> mechanism 1 (`GATE`): `GATE: gate: 1 triggers < 2`
- **2026-08-07 2026-08-07T09:46:03 / bold-2** -> mechanism 4 (`RISK_DENY_PDT`): `RISK_DENY_PDT: BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier SUPER)`
- **2026-08-11 2026-08-11T11:51:04 / safe-3** -> mechanism 1 (`GATE`): `GATE: gate: 1 triggers < 2`
- **2026-08-11 2026-08-11T13:31:05 / safe-3** -> mechanism 1 (`GATE`): `GATE: gate: 1 triggers < 2`
- **2026-08-12 2026-08-12T13:16:05 / safe-2** -> mechanism 1 (`SKIP_STRUCTURE_VETO`): `SKIP_STRUCTURE_VETO: structure-veto: P entry blocked — price structure is 'uptrend' (wrong-way entry)`
- **2026-08-12 2026-08-12T13:16:05 / safe-3** -> mechanism 1 (`GATE`): `GATE: gate: 1 triggers < 2`
- **2026-08-12 2026-08-12T14:16:04 / bold-2** -> mechanism 1 (`SKIP_CONF_LVL_REC_AFTERNOON`): `SKIP_CONF_LVL_REC_AFTERNOON: blocked by entry gate block_conf_lvl_rec_afternoon`
- **2026-08-12 2026-08-12T14:16:04 / safe-2** -> mechanism 2 (`RISK_DENY_SETTLEMENT`): `RISK_DENY_SETTLEMENT: BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)`
- **2026-08-13 2026-08-13T11:41:04 / safe-2** -> mechanism 1 (`SKIP_BULL_1100_1200`): `SKIP_BULL_1100_1200: blocked by entry gate block_bull_1100_1200`
- **2026-08-13 2026-08-13T14:36:04 / bold-2** -> mechanism 1 (`SKIP_CONF_LVL_REC_AFTERNOON`): `SKIP_CONF_LVL_REC_AFTERNOON: blocked by entry gate block_conf_lvl_rec_afternoon`
- **2026-08-14 2026-08-14T12:14:04 / risky-1** -> mechanism 1 (`GATE`): `GATE: gate: 1 triggers < 2`
- **2026-08-14 2026-08-14T12:14:04 / safe-3** -> mechanism 1 (`GATE`): `GATE: gate: 1 triggers < 2`
- **2026-08-17 2026-08-17T13:06:04 / risky-1** -> mechanism 1 (`GATE`): `GATE: gate: 1 triggers < 2`
- **2026-08-17 2026-08-17T13:06:04 / safe-2** -> mechanism 1 (`SKIP_STRUCTURE_VETO`): `SKIP_STRUCTURE_VETO: structure-veto: P entry blocked — price structure is 'uptrend' (wrong-way entry)`
- **2026-08-17 2026-08-17T13:06:04 / safe-3** -> mechanism 1 (`GATE`): `GATE: gate: 1 triggers < 2`
- **2026-08-17 2026-08-17T15:01:03 / bold-2** -> mechanism 1 (`SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY`): `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY: blocked by entry gate require_bearish_fill_bar`
- **2026-08-17 2026-08-17T15:01:03 / risky-1** -> mechanism 8 (`NO_ROW`): `no matching fleet decision row found (fail-open)`
- **2026-08-17 2026-08-17T15:01:03 / safe-2** -> mechanism 7 (`SKIP_LATE_ENTRY`): `SKIP_LATE_ENTRY: BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates (tier TRENDLINE)`
- **2026-08-17 2026-08-17T15:01:03 / safe-3** -> mechanism 8 (`NO_ROW`): `no matching fleet decision row found (fail-open)`
- **2026-08-18 2026-08-18T14:36:03 / risky-1** -> mechanism 1 (`GATE`): `GATE: gate: 1 triggers < 2`
- **2026-08-18 2026-08-18T14:36:03 / safe-3** -> mechanism 1 (`GATE`): `GATE: gate: 1 triggers < 2`
- **2026-08-18 2026-08-18T15:31:03 / bold-2** -> mechanism 1 (`SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY`): `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY: blocked by entry gate require_bearish_fill_bar`
- **2026-08-18 2026-08-18T15:31:03 / risky-1** -> mechanism 8 (`NO_ROW`): `no matching fleet decision row found (fail-open)`
- **2026-08-18 2026-08-18T15:31:03 / safe-2** -> mechanism 7 (`SKIP_LATE_ENTRY`): `SKIP_LATE_ENTRY: BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates (tier TRENDLINE)`
- **2026-08-18 2026-08-18T15:31:03 / safe-3** -> mechanism 8 (`NO_ROW`): `no matching fleet decision row found (fail-open)`
- **2026-08-20 2026-08-20T12:56:03 / risky-1** -> mechanism 1 (`GATE`): `GATE: gate: 1 triggers < 2`
- **2026-08-20 2026-08-20T12:56:03 / safe-3** -> mechanism 1 (`GATE`): `GATE: gate: 1 triggers < 2`
- **2026-08-20 2026-08-20T14:01:04 / risky-1** -> mechanism 1 (`GATE`): `GATE: gate: 1 triggers < 2`
- **2026-08-20 2026-08-20T14:01:04 / safe-3** -> mechanism 1 (`GATE`): `GATE: gate: 1 triggers < 2`
- **2026-08-20 2026-08-20T14:56:03 / bold-2** -> mechanism 1 (`SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY`): `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY: blocked by entry gate require_bearish_fill_bar`
- **2026-08-20 2026-08-20T14:56:03 / risky-1** -> mechanism 1 (`GATE`): `GATE: gate: 1 triggers < 2`
- **2026-08-20 2026-08-20T14:56:03 / safe-3** -> mechanism 1 (`GATE`): `GATE: gate: 1 triggers < 2`
- **2026-08-21 2026-08-21T12:26:03 / bold-2** -> mechanism 6 (`SKIP_MIN_PREMIUM_FLOOR`): `SKIP_MIN_PREMIUM_FLOOR: BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)`
- **2026-08-21 2026-08-21T13:34:04 / bold-2** -> mechanism 6 (`SKIP_MIN_PREMIUM_FLOOR`): `SKIP_MIN_PREMIUM_FLOOR: BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)`
- **2026-08-21 2026-08-21T13:34:04 / safe-2** -> mechanism 1 (`SKIP_STRUCTURE_VETO`): `SKIP_STRUCTURE_VETO: structure-veto: C entry blocked — price structure is 'downtrend' (wrong-way entry)`
- **2026-08-25 2026-08-25T13:16:03 / bold-2** -> mechanism 6 (`SKIP_MIN_PREMIUM_FLOOR`): `SKIP_MIN_PREMIUM_FLOOR: BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)`
- **2026-08-27 2026-08-27T12:31:03 / bold-2** -> mechanism 3 (`NOT_FLAT`): `NOT_FLAT: BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)`
- **2026-08-27 2026-08-27T12:31:03 / risky-1** -> mechanism 3 (`NOT_FLAT`): `NOT_FLAT: risk_gate denied: PA3S9N1IV0A4: position already open (status='open') — flatten before a new entry (Rule 4: no adding without a new trigger)`
- **2026-08-27 2026-08-27T12:31:03 / safe-3** -> mechanism 3 (`NOT_FLAT`): `NOT_FLAT: risk_gate denied: PA32T7Q1O20H: position already open (status='open') — flatten before a new entry (Rule 4: no adding without a new trigger)`
- **2026-09-01 2026-09-01T13:21:03 / risky-1** -> mechanism 1 (`GATE`): `GATE: gate: 1 triggers < 2`
- **2026-09-01 2026-09-01T13:21:03 / safe-3** -> mechanism 1 (`GATE`): `GATE: gate: 1 triggers < 2`
- **2026-09-02 2026-09-02T13:06:03 / bold-2** -> mechanism 6 (`SKIP_MIN_PREMIUM_FLOOR`): `SKIP_MIN_PREMIUM_FLOOR: BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier SUPER)`

## Standard notional per arm (used in dollar figures)

- safe-2: $406.50
- bold-2: $360.00
- safe-3: $246.00
- risky-1: $480.00

## F3 -- defects found and fixed (this session, non-frozen files only)

`setup/scripts/right_tail_capture.py` is NOT in `FROZEN_TRADING_PATH` (it is a read-only
analysis instrument, not the trading path) -- both fixes below were made directly, with
RED-proof tests, rather than filed as preregs.

1. **Gate-rejection rows were silently discarded.** Root cause: `_refusal_reason`'s filter
   `risk_code not in (None, "ALLOW")` excluded every `gate:`/`A+ gate:` rejection because
   `fleet_executor.py`'s gate_override check never sets `risk_code` (only the later
   `risk_gate.py` path does) -- e.g. the real row
   `{"risk_code": None, "reason": "gate: 1 triggers < 2"}`. This silently mislabeled 938
   real gate-rejection rows across safe-3+risky-1 as "no matching fleet decision row
   found," which is precisely the goal's own opening-paragraph "dominant refusal bucket"
   framing being an artifact of this filter, not the ground truth. Fix: also admit a
   reason starting with `gate:`/`a+ gate:` regardless of `risk_code`, tagged `GATE`.
   Guard: `test_right_tail_capture_gate_reason_recovery`,
   `test_a_plus_gate_reason_recovered` in
   `backtest/tests/test_right_tail_capture_gap_fixes.py`.
2. **Core arms (safe-2/bold-2) never read their own decision source.** Root cause:
   `_fleet_decisions_for_arm_day` unconditionally read
   `automation/state/fleet/<arm>/decisions.jsonl`, a file that only exists for
   `fleet_rest`-executed arms -- safe-2/bold-2 are `mcp_heartbeat`-executed and that path
   is empty for them, so every missed wave for these two arms fell through to the generic
   fail-open label regardless of what `core-decisions.jsonl` actually recorded at that
   tick. A second, deeper bug was found while fixing this: the first version of the
   core-decisions reshape used the row's `verdict` field as the risk_code proxy, which
   mislabels a real risk_gate denial as a clean ALLOW whenever the SIGNAL layer still
   said `ENTER_BULL`/`ENTER_BEAR` -- confirmed against the real row
   `account=bold, ts_et=2026-08-04T12:26:55, verdict=ENTER_BULL,
   reason="...passed scoring + all entry gates (tier ELITE)", action=RISK_DENY_PDT,
   exec.status=RISK_DENY_PDT, exec.reason="bold: 3 day-trades in 5d at equity $5,478 <
   $25,000 -- PDT rule blocks a 4th day-trade"` -- verdict says clean entry, `action` says
   PDT denial. Fix: read `core-decisions.jsonl` filtered by `account` for these two arms,
   and use the row's `action` field (not `verdict`) as the risk_code proxy -- `action` is
   the authoritative post-gate outcome (`HOLD` / `SKIP_<gate>` / `RISK_DENY_<code>` /
   `PLACE_FAIL` / `PLACED` / `VETOED_BY_MODELS`). Guard:
   `test_core_account_arms_read_core_decisions_not_empty_fleet_dir`,
   `test_core_reshape_uses_action_not_verdict_pdt_deny_real_row`.

Both fixes recovered real, specific evidence for 40 of the 43 rows that previously read
"no matching fleet decision row found (fail-open)" (43 -> 4 remaining, see mechanism 8
below). `analysis/right-tail/ledger.jsonl` was regenerated via
`scratchpad/backfill_right_tail.py` after both fixes (same 46 missed / 144 scored pairs,
same 20-session per-arm capture rates as SUMMARY.md -- only the `refused_by_gate` text
changed).

## Mechanism 1 is two structurally different things, split out honestly

The $9,276.77 mechanism-1 total bundles two unrelated fixes into one number:
- **safe-3 + risky-1 ($2,140.48 + $2,214.44 = $4,354.92):** a real, single-knob
  `gate_override` setting (`min_triggers: 2`, `require_confluence_or_sequence: true`,
  `automation/state/fleet/accounts.json`) -- this IS an expansion candidate, prereg filed
  (mechanism-1 prereg below).
- **safe-2 + bold-2 ($2,399.36 + $2,522.49 = $4,921.85):** these are core-engine ticks
  where THIS account's own structure-veto/quality-lock/time-window gate
  (`SKIP_STRUCTURE_VETO` / `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY` /
  `SKIP_CONF_LVL_REC_AFTERNOON` / `SKIP_BULL_1100_1200`) fired on this account's own tick
  while the OTHER core account's ribbon fired a few seconds apart -- there is no single
  override knob for this (safe-2/bold-2 both run `gate_override: {}`; the divergence is
  per-account signal timing inside `heartbeat_core.py`/`filters.py`, both FROZEN). NO
  prereg filed for this slice -- there is nothing to loosen without touching a FROZEN
  file, and it is not a defect (the two accounts are legitimately independent tick
  streams, not a shared signal with one bug in it).

## Mechanism 8 (no evidence) -- checked against engine_gaps, ruled NOT a cadence outage

The 4 remaining rows (safe-3 + risky-1, both 2026-08-17T15:01:03 and
2026-08-18T15:31:03 -- the SAME two waves missed by ALL FOUR arms) show a fleet tick
firing on-schedule every minute through that window (`automation/state/fleet/safe-3/
decisions.jsonl`: `2026-08-17T15:01:04...HOLD...no qualifying setup (no strategy
fired)`) -- `_fleet_tick_ran_near` confirms a row within 2 min for both. This rules out
mechanism 5's literal "tick did not run" reading. The fleet strategy registry
(`strategies.py`, FROZEN) simply never recognized a qualifying setup at these ticks even
though the core account's own wave anchor fired -- a genuine strategy-coverage gap
between `heartbeat_core.py`'s detection and `strategies.py`'s two registered strategies
(`ribbon_ride`, `vwap_continuation`), not a race or an outage. Both waves are late-day
(15:01/15:31 ET, near the 15:50 hard time-stop) small dollar figures ($740.78 +
$1,445.43 = $2,186.21, both PROXY off peak_multiple_on_tape since no arm captured either
wave). Not filed as a prereg (fix lives in FROZEN `strategies.py`) and not filed as a
09-29 kill-type prereg either -- $2,186.21 over 2 waves in a 25-day window is below this
goal's own $1,000-per-mechanism bar when correctly scoped as "coverage gap," and the
fix would require adding a new strategy definition (an EXPANSION of strategies.py, not a
tightening), which is out of this goal's scope. Flagged here for the next strategies.py
review, not actioned.
