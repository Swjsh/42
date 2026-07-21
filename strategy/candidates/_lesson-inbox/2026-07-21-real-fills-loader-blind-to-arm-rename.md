# Lesson candidate: a "real fills" anchor can go synthetic-by-omission when the account/arm lineup moves on

**Date filed:** 2026-07-21 (conductor, AFTERHOURS)
**Class:** C14 (dead/translated-but-unapplied knobs) + C7 (silent success is failure) — new angle

## Symptom

`backtest/tools/exit_shape_parity_study.py::load_fleet_engine_fills()` hardcoded its arm scope
to `FLEET_REST_ARMS = ("safe-1","safe-3","risky-1","risky-3")` back in the 2026-07-09
HANDOFF-TRUTH-AND-EXITS build. Every downstream real-fills-anchor study reused this loader
verbatim (`structure_stop_study.py`, `structure_stop_zone_band_ab.py`,
`structure_stop_reference_level_ab.py`, `ribbon_ride_strike_exit_ab.py`,
`p5_topcell_real_fills_confirm.py`, `t4_exit_matrix.py`, `t5_confirmatory_matrix.py`,
`recency_sizing_ab.py`, `ssb_certification_study.py`, `entry_runback_20260708.py` — ~14 call
sites, all zero-arg calls). Fleet_rest went dark 2026-07-09 (0 fills since, confirmed by
PROFIT-P1-FLEET-EXIT-PARITY), while ALL real trading since has happened on the CORE production
arms (`safe-2`/`bold-2` in `fills-ledger.jsonl`, current through today, 200 fills and growing).
Every study built on this loader was therefore structurally BLIND to the exact exhibits that
motivated re-running them — including a `git`-confirmed, twice-disclosed "0/0 exhibit fills
recoverable" gap on 2026-07-20 (STRUCTURE-STOP-ZONE-BAND / STRUCTURE-STOP-REFERENCE-LEVEL both
flagged this and left it unfixed as "worth a future fire's attention"), and every
`trade_autopsy.py`-generated hypothesis's "confirm on fresh OPRA slice" proposed test coming up
empty for at least 12 days running (07-09 through 07-21 filings, same recommended action text,
never once executable).

## Root cause

The loader's "which population counts as real" filter was a point-in-time snapshot of the
account lineup, not a derived/live-read fact. When the account lineup moved on (fleet_rest went
dark, core arms became the only live trading), nobody had to touch this file for it to keep
"working" — it kept returning SOME fills (the frozen fleet-rest population up to 2026-07-09),
so it never threw, never returned empty-looking output, never tripped an obvious "this is
broken" signal. It just quietly stopped tracking reality. A "real fills" anchor is only as real
as its account/arm scope; that scope needs the same producer-freshness discipline as any other
data feed (C7's "audit outputs, not exit codes" applies to WHICH population a tool reads, not
just whether it ran).

## Fix (this fire)

Added `CORE_ARMS = ("safe-2", "bold-2")` + `ALL_LIVE_ARMS = FLEET_REST_ARMS + CORE_ARMS`;
`load_fleet_engine_fills` gained an `arms=` parameter. **Deliberately did NOT change the
default** — 127 real core-arm fills predate `structure_stop_study.ANCHOR_END_DATE`
(2026-07-08), so a default-scope widening would have silently shifted every already-frozen
anchor pin (e.g. `test_control_anchor_reproduces_established_baseline_live`'s `-757.1`), which
is itself the re-pick-after-seeing-results hazard the no_repick_clause discipline exists to
prevent. The fix is purely additive: `arms=ALL_LIVE_ARMS` is available, opt-in, for any FUTURE
study that wants current-day coverage, and must be its own separately-frozen pre-registration —
not a silent extension of an already-verdicted one.

## Suggested generalization (for lesson-author to judge)

Any tool whose docstring says "real fills" / "real trading" / "live population" and hardcodes
an account or arm identifier list should be re-verified against the CURRENT account roster
(`automation/state/fleet/accounts.json`) whenever that roster changes materially (a repoint, a
retirement, a new arm going live) — not just when someone happens to notice the gap. Candidate
guard: a drift-ratchet test (same shape as `v25_filter_gates.py`'s presence guard) that fails if
`fills-ledger.jsonl`'s most dominant recent arm (by fill count in the last N days) is NOT a
member of any hardcoded arm-scope constant across `backtest/tools/`. Not built this fire —
flagged for lesson-author/skill-author to size.
