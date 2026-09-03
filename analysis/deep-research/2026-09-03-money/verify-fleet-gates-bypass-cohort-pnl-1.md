# VERIFY (ledger lens) — fleet-gates-bypass-cohort-pnl (G3)

Stamp: 2026-09-03T14:40 ET, market open, read-only, no broker/network calls. Independent
re-derivation, own script: `backtest/tools/fleetgates_verify_bypass-cohort-pnl_1.py` (does NOT
import `fleetgates_bypass-cohort-pnl.py` — re-implements core-index build, cohort
classification, and the P&L join from raw ledgers). Full JSON:
`analysis/deep-research/2026-09-03-money/fleetgates-verify-bypass-cohort-pnl-1.json`.

## Verdict: REFUTED

The original report's P&L join has a **reproducible, money-non-conserving bug**: whenever a
fleet arm re-enters the **same option symbol more than once on the same day**, the join
matches **every** decision row hitting that (arm, date, symbol) key to the **same one**
`mae-mfe.json` trade (chronologically the first), instead of pairing each decision to its own
distinct round-trip. This is not a rounding-level discrepancy — it corrupts several of the
finding's own headlined numbers by 2x-9x, flips the sign of the "control cohort" claim at the
population level, and falsifies a specific quoted statistic (risky-3 cohort A "0% WR, 0-for-9").
Independently rebuilding the same join with the fix in place changes enough of the report's
own facts array that "SUPPORTED" cannot stand as scored.

## The bug, mechanically

Original `join_arm()` (`backtest/tools/fleetgates_bypass-cohort-pnl.py:250-259`):

```python
elif len(candidates) > 1:
    same_qty = [c for c in candidates if c.get("qty") == qty]
    matched = same_qty[0] if same_qty else candidates[0]
```

Every same-day re-entry into an identical strike/expiry almost always carries the **same
contract qty** (position sizing is set by the arm's tier, not by which re-entry number it is),
so `same_qty` matches every candidate, and `same_qty[0]` resolves to the chronologically first
trade **for every decision row that shares the key** — there is no per-row consumption of the
candidate list. One real trade's P&L gets assigned to N different decision rows; the other
N-1 real trades' P&L is silently dropped from every cohort.

**Scope**: I found **33 `(arm, date, symbol)` keys** across the 4 fleet arms, all on/after
2026-08-03 (the join-key start date), where `mae-mfe.json` carries more than one trade for that
key — i.e. 33 same-day same-strike re-entries. Across the **92 placed decision rows** that land
on one of those 33 keys, the true distinct realized P&L of the underlying trades sums to
**-$542**; the original script's matching logic, applied to those same 92 rows, assigns a total
of **-$4,687** — a **$4,145 non-conserved discrepancy** (money invented/destroyed by the join,
not by the market). Verified by direct computation against `mae-mfe.json` and every fleet arm's
`decisions.jsonl`, independent of either script (`Bash` inline, not committed).

This bug affects the `mae-mfe.json`-sourced path only (all dates through 2026-09-02). The
fallback path for entries the pre-built ledger doesn't cover (today, 2026-09-03) uses a
**different, nearest-timestamp matching rule** (`join_arm()` lines 260-291) that is NOT
affected — confirmed below, today's 4 safe-3 fills hand-verify exactly against both reports.

### Two concrete before/after examples

**risky-1, 2026-08-12, `SPY260812P00773000`** — 8 placed decision rows that day (3
`VWAP_CONTINUATION`, 5 `BEARISH_REJECTION_RIDE_THE_RIBBON`) against 8 real round-trip trades.
Original assigns **-$55.00 to all 8 rows** (the first trade, entered 09:46 ET). Correct
chronological pairing (decision ts_et <-> trade entry_ts_utc, both monotonic, decision-count ==
candidate-count exactly for this key) gives the 5 ribbon rows -$20, -$20, +$10, $0, +$5 — two of
which are this report's own `A_BYPASS` cohort (both mis-priced at -$55 instead of -$20 in the
original).

**risky-3, 2026-08-21, `SPY260821C00768000`** — 3 `A_BYPASS` decision rows (all
`block_bull_1100_1200`/`SKIP_BULL_1100_1200`). Original assigns -$90 to all 3 (repeating the
first trade). Correct pairing: -$90, -$110, **+$220** — the third entry is a **winner**, not a
loser. This directly falsifies the finding's claim that risky-3's cohort A is "0-for-9 ... the
one cell in this table where the bootstrap CI does NOT cross zero" and "PF 0.00": corrected,
risky-3 cohort A is **1-for-9** (WR 11.1%, PF 0.292, not 0.00/0%).

## Recomputed headline numbers (corrected join vs. original report)

| Cut | Original $ (n) | Corrected $ (n) | Δ$ | WR orig -> corrected | PF orig -> corrected |
|---|---:|---:|---:|---|---|
| safe-3 A (bypass) | +752 (13) | **+775 (13)** | +23 | 30.8% -> 46.2% | 2.08 -> 1.99 |
| safe-3 B (control) | **-203 (20)** | **+67 (20)** | +270 (sign flip) | 20.0% -> 30.0% | 0.885 -> 1.036 |
| risky-1 A (bypass) | +104 (16) | **+516 (16)** | +412 (5x) | 25.0% -> 37.5% | 1.09 -> 1.48 |
| risky-1 B (control) | **-146 (19)** | **+916 (19)** | +1,062 (sign flip) | 21.1% -> 33.3% | 0.928 -> 1.488 |
| risky-3 A (bypass) | -823 (9), **"0-for-9", PF 0.00** | **-533 (9), 1-for-9, PF 0.292** | +290 | **0% -> 11.1%** | 0.00 -> 0.292 |
| risky-3 B (control) | -976 (21) | **-118 (21)** | +858 | 23.8% -> 28.6% | 0.548 -> 0.944 |
| safe-1 (all, unclassifiable) | -300 (24) | -242 (24) | +58 | n/a | n/a |
| **Population A (bypass)** | +33 (38) | **+758 (38)** | +725 | 21.1% -> 34.2% | 1.01 -> 1.29 |
| **Population B (control)** | **-1,325 (60)** | **+865 (60)** | +2,190 **(sign flip)** | 21.7% -> 30.5% | 0.777 -> 1.148 |

n (trade counts) match exactly between original and corrected in every row — the cohort
classification logic itself (safe/bold verdict comparison, ribbon-only scope, placed-only
filter) checks out and is **not** in dispute. Only the P&L attached to each row is wrong in the
original wherever a decision hits one of the 33 duplicate-symbol-day keys.

**Gate breakdown** (cohort A, all arms, grouped by `safe_verdict`) — n identical, dollars not:

| Gate | n (both) | Original $ | Corrected $ |
|---|---:|---:|---:|
| `SKIP_BULL_1100_1200` | 28 | +179 | **+984** |
| `SKIP_STRUCTURE_VETO` | 9 | -1 | -81 |
| `SKIP_DOJI_ENTRY_BAR` | 1 | -145 | -145 (unaffected, unique key) |

The finding's own conclusion — *"`block_bull_1100_1200` is ... roughly breakeven in
aggregate. Neither gate shows a clean directional edge"* — does not survive: at $984 over 28
trades (mean +$35/trade), the dominant bypass gate looks like a real positive contributor, not
a breakeven one, under the corrected join. (Still descriptive/small-n — see caveats — but the
finding's own characterization of its own gate-breakdown table is now wrong on its face.)

## What DOES hold up under the corrected join

- **`core_tick_id` first appears 2026-08-03T09:30:04 ET** — confirmed by direct scan of
  `automation/state/core-decisions.jsonl` (37,991 rows; first non-null `core_tick_id` at line
  index 19,639, exact timestamp match).
- **safe-1 is fully unclassifiable** (all 24 real-fills rows predate the join key) — confirmed;
  net P&L differs slightly (-$242 corrected vs -$300 claimed, no dup-key issue here — see
  caveats) but the qualitative claim stands.
- **Today's 4 safe-3 fills** (09:42 -$270, 10:17 -$65, 11:07 +$507, 11:22 +$433) — hand-verified
  directly against `automation/state/fills-ledger.jsonl` round-trip legs (independent of both
  scripts), exact match to the finding's numbers. Today is not affected by the join bug because
  it uses the (correct) nearest-timestamp fallback path, not the buggy `mae-mfe.json` primary
  path.
- **Four named winning days + September, summed across safe-3/risky-1/risky-3**: mostly
  unaffected (08-13 -$325/+$1,029 both match exactly; 08-27 +$616/+$745 both match exactly;
  08-06 zero-trades matches). Small ($18-$40) discrepancies on 08-28 and September (risky-3
  08-28, safe-3/risky-1 09-02) trace to duplicate keys on those specific dates but don't flip
  any qualitative claim there — the corrected September/named-day numbers tell essentially the
  same story the finding tells for those specific cuts.
- **`structure_veto_enabled` bypass gate stays roughly flat** (-$1 original vs -$81 corrected —
  both small relative to n=9's spread), consistent with the finding's "dead flat" read for that
  specific gate, even though the underlying per-trade dollars changed.

So the bug's damage is concentrated in the **all-time population and per-arm roll-ups** (which
happen to be the numbers used for "has the bypass helped / is the control cohort also a
loser" — the finding's central comparison) and largely spares the **named-days/September**
sections, which is exactly the part of the report already flagged there as small-n and
today-dominated. The parts of the finding that were already hedged turn out to be the reliable
parts; the parts stated as flat unhedged facts (population $, risky-3 WR, gate-breakdown
dollars) are the ones that broke.

## Why this changes the verdict, not just the numbers

The finding's central rhetorical move is: *"the non-bypass control cohort loses money
everywhere too ... this is not bypass bad control good, both cohorts lose money."* That claim
is built on safe-3 B = -$203 and population B = -$1,325. Under the corrected join, **safe-3 B is
+$67 and population B is +$865** — the control cohort is a net winner at the population level,
not a net loser. The finding's own "not bypass-bad/control-good" framing is the one thing the
corrected numbers most directly contradict — it's not just that a total moved, it's that the
specific comparison the finding uses to argue "both cohorts are equally unreliable" flips to
"the control cohort actually did better than the bypass cohort at the population level, once
correctly priced" (population A +$758 vs B +$865 — both now positive, closer together, but B
edges A, which is a different conclusion than "both lose").

## Caveats on this verification itself

- **Positional pairing is an inference, not a byte-exact replay.** I pair decision rows to
  trade candidates by sorting both lists chronologically within each `(arm, date, symbol)` key
  and zipping 1:1. I validated this assumption two ways: (a) decision-row count equals
  mae-candidate count for 32 of the 33 duplicate keys exactly (the 1 exception, risky-1
  2026-08-11 773P, 3 decisions vs 2 candidates, falls through to the fallback path); (b) a
  manual UTC/ET conversion check on the risky-1 08-12 773P group shows decision `ts_et` and
  trade `entry_ts_utc` line up within seconds for all 8 rows in order. I did not verify every
  one of the 33 keys by hand — the two worked examples above and the count-parity check are the
  evidence for the general rule, not an exhaustive trade-by-trade audit.
- **safe-1's small ($58) discrepancy is NOT from the duplicate-key bug** (safe-1 has zero
  duplicate keys in this dataset) — its source is unexplained by this check and is flagged, not
  resolved, here.
- **I did not rebuild the candidate (a)/(b) costing tables** under the corrected join — the
  underlying per-trade dollars feeding those computations are shown here to be wrong in several
  cases (notably risky-role's `SKIP_BULL_1100_1200`-heavy population), so those costings should
  be treated as **UNVERIFIED pending a rebuild**, not re-affirmed by this note.
- **This remains a descriptive read** — small n, no OOS split, no walk-forward — the corrected
  numbers are not a stronger basis for ratifying any gate change than the original's were; they
  are simply different numbers, and in the one place they change the finding's own narrative
  (control cohort sign), they change it toward "not resolved either way," not toward "ship it."
- Fixed script available for re-run/audit at
  `backtest/tools/fleetgates_verify_bypass-cohort-pnl_1.py`; raw output at
  `analysis/deep-research/2026-09-03-money/fleetgates-verify-bypass-cohort-pnl-1.json`
  (includes a full per-trade dump of safe-3's cohort A and the risky-1 08-12 bug example for
  hand-audit).
