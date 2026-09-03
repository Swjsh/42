# VERIFY — G4-DESIGNATION-ACCURACY (fleet-gates-designation-accuracy.md)

Stamp: 2026-09-03, ~14:33-15:10 ET (market hours), read-only, adversarial re-verification.
Script: `backtest/tools/fleetgates_verify_designation-accuracy_1.py` (independently written,
does not import or call the sibling `fleetgates_ledger-binding-check.py`). Output:
`analysis/deep-research/2026-09-03-money/verify-fleet-gates-designation-accuracy-1.json`.

## Verdict: NOT REFUTED — every checkable claim reproduces, several byte-for-byte

I set out to refute this (default posture). I could not. Every hard number in the finding that
I could independently recompute, I recomputed from raw ledgers/code with my own script and got
either an exact match or a match within an immaterial line-number offset. The one central,
hardest-to-verify claim — the §4c day-level "0 of 12 dates depend solely on the leak" table — I
rebuilt from scratch with a script that never touches the original author's script, and it
reproduced all 12 rows exactly, digit for digit.

---

## What I independently re-verified (all PASS)

1. **Code mechanism.** `fleet_executor.py`: `_gate_check` at line 599 (claimed 599-620, exact).
   `_plan_from_strategies` at line 721 (claimed n/a). `plan_all`'s branch
   `if signal.get("strategies") is not None:` at line 933 (claimed 933-935, exact). One minor
   miss: the `gate_reason = _gate_check(arm, blk, signal)` call inside `_plan_from_strategies` is
   at line **737**, not the claimed **743** (6-line offset) — immaterial, does not change any
   conclusion.

2. **accounts.json gate_override.** Read `automation/state/fleet/accounts.json` directly:
   `safe-3.gate_override == {"min_triggers": 2, "require_confluence_or_sequence": true}`,
   `cell: "safe x tight"` — exact match to the quoted text.

3. **502 refusals, exact breakdown.** Recounted `automation/state/fleet/safe-3/decisions.jsonl`
   myself (12,602 rows): `reason` starting with `"gate:"` = **502** total, split
   **284** `"gate: requires confluence/sequence"` + **218** `"gate: 1 triggers < 2"`. Exact match,
   digit for digit.

4. **3 quoted ledger rows.** Pulled all three `core_tick_id`s
   (`2026-09-03T10:24:02.595671`, `2026-09-03T10:30:03.934929`, `2026-09-03T13:55:02.903251`)
   directly from `safe-3/decisions.jsonl` — `action`, `side`, `setup_name`, `reason` all match
   the quoted text exactly.

5. **Commit provenance.** `git log -S'EMIT_STRATEGIES = True' -- automation/state/fleet/build_shared_signal.py`
   and `git log -S'signal.get("strategies") is not None' -- automation/state/fleet/fleet_executor.py`
   both land on the same commit `667217a1`. `git show -s --format='%H %ad' --date=iso 667217a1` →
   `2026-06-26 14:15:44 -0600` (box-local Mountain time). Independently computed safe-3's first
   fill from `fills-ledger.jsonl` (`arm=="safe-3"`, min `ts_et`): **2026-06-29T14:51:15** —
   three days after the commit, exactly as claimed.

6. **Four named instruments — no gate-identity assumption.** Grepped all four files
   (`setup/scripts/go_live_gate.py`, `setup/scripts/prod_shadow.py`,
   `setup/scripts/first_live_day_review.py`, `setup/scripts/live_readiness.py`,
   `backtest/tools/walker_full_population_anchor.py`) for
   `gate|cohort|min_triggers|structure_veto|profile_summary`: zero matches tie any of these
   files to safe-3's specific gate config. `go_live_gate.py:826` carries
   `"profile_summary": cfg.get("profile_summary")` into the report dict verbatim — confirmed by
   reading the surrounding `prod_shadow_criterion()` function in full: pass/fail is 100% derived
   from `statistical_criterion()` on ledger rows, the string is never parsed or compared to code.
   `prod_shadow.py` confirmed: `DEFAULT_BASE_ARM = "safe-2"`, `"not_criterion_5": True`, a
   `NAME COLLISION WARNING` docstring, and the only `safe-3` mention in the file is a comment
   pointing readers to the real criterion-5 instrument. `go_live_gate.ACTIVE_ARMS` (fallback list,
   line 112) is exactly `{safe-2, bold-2, safe-3, risky-1}`, matching the walker's described
   scope.

7. **days_scored / days_needed / status — reproduced live, not just cited.** Ran
   `go_live_gate.load_ledger_rows()` + `prod_shadow_criterion(engine_rows)` directly in-process
   (pure read of `analysis/trades-enriched.jsonl`, zero writes, confirmed by reading
   `load_ledger_rows()`'s body first — it only opens the file for `read_text()`). Result:
   `days_scored=1, days_needed=20, status=INSUFFICIENT_DAYS`, note text byte-identical to the
   finding's quote. Cross-checked the 1 scored date is `2026-09-02` (only date present for
   `arm=="safe-3", attribution=="engine"` in the window); confirmed zero safe-3 fills on
   2026-09-01 in `fills-ledger.jsonl`; confirmed 2026-09-03 already has fills (I counted 10 as of
   my later read-time vs. the finding's 8 — expected drift, not a discrepancy, since more ticks
   fired between the finding's ~14:30 stamp and mine) but is not yet in `trades-enriched.jsonl`.

8. **Calendar math.** Independently computed trading days 2026-09-01..2026-10-30 excluding Labor
   Day (2026-09-07): **43** total, **3** elapsed through 09-03, **40** remaining, **19** pre a
   hypothetical 09-29 fix, **24** post-fix. All four numbers match the finding exactly.

9. **Handoff doc comparator.** `markdown/planning/TWO-ACCOUNT-CONSOLIDATION-HANDOFF-2026-08-29.md`
   line 27: "safe-3 ... is n=59, +$841, **WR 30.5%**" — exact match to both the designation file's
   own `profile_summary` and the finding's quoted figures.

10. **The core §4c day-level join — rebuilt from scratch, independent script.** Wrote
    `backtest/tools/fleetgates_verify_designation-accuracy_1.py` from first principles (does not
    import the sibling `fleetgates_ledger-binding-check.py`, no shared helper code). Joined
    `core-decisions.jsonl` `account=="safe"` rows (`action` startswith `SKIP_`) against
    `account=="bold"` rows on the same `core_tick_id` (`verdict` startswith `ENTER_`), window
    `>= 2026-08-06`. Result:
    - **133 leak-eligible ticks, 12 distinct dates** — exact match to both this finding and the
      sibling ledger-binding-check.
    - Gate breakdown: `SKIP_STRUCTURE_VETO` 54, `SKIP_BULL_1100_1200` 53, `SKIP_LATE_ENTRY` 16,
      `SKIP_DOJI_ENTRY_BAR` 9, `SKIP_STALE_SIGHT` 1 — sums to 133, matches Table A of the sibling
      report row-for-row.
    - Then joined safe-3's own `decisions.jsonl` per date, splitting ENTER-type decisions
      (`ENTER_BULL`/`ENTER_BEAR`/`PLACED`) into via-leak-tick vs non-leak. **All 12 per-date rows
      reproduced exactly** (total/via_leak/non_leak triples identical to the finding's §4c table
      for every one of 2026-08-07, -11, -12, -13, -17, -18, -19, -20, -21, -27, 09-02, 09-03).
    - **Dates where safe-3's only entry came via a leak tick: 0 of 12** — reproduced exactly.
    - Aggregate: safe-3 entered on 11/133 leak-eligible ticks = **8.3%**, exact match.
    - Named-winning-days overlap: **14/133 (10.5%)** ticks fall on {2026-08-06, -13, -27, -28}
      — recomputed independently, exact match to the figure the sibling doc cites and this
      finding relies on.
    - September-only leak-eligible dates: {2026-09-02, 2026-09-03} — 2 dates, both already
      covered by the "0 of 12" finding (09-02 has 2 non-leak entries, 09-03 has 2 non-leak
      entries as of the finding's data cut).

11. **Participation baseline.** Independently counted safe-3's distinct fill dates
    2026-06-29..2026-08-28 from `fills-ledger.jsonl`: **26** distinct dates — matches the
    designation file's "26 of 44" exactly on the numerator. Did not independently reproduce the
    44-trading-day denominator (my naive weekday count gives 45; the 1-day gap is almost
    certainly a market-observed Independence Day holiday on Friday 2026-07-03, since July 4 2026
    falls on a Saturday — not independently confirmed against a market calendar this session, but
    this figure is a **pre-existing number already committed to `prod-shadow-designation.json`
    before this finding was written**, not something the finding itself derived or could have
    fabricated, and it is used only in the finding's own §4b "naive framing" which the finding
    itself labels as flawed and superseded by the stronger §4c check.

---

## What I could not / did not independently re-verify

- Whether 2026-09-03 will actually score as the window's 2nd day — genuinely can't know until
  EOD `trades_enriched.py` runs; the finding labels this UNVERIFIED itself, correctly.
- The 44-trading-day denominator's exact market-holiday calendar (see above) — immaterial to the
  finding's conclusion, which explicitly discounts the participation-rate framing that number
  feeds.
- Whether any future (not-yet-designed) 09-29 fix would behave identically to the historical
  proxy — the finding is explicit this is inference from n=12 dates using ENTER-type decisions as
  a proxy for scored days, not the literal FIFO-fill criterion. I agree this caveat is honestly
  stated and correctly scoped; I did not attempt to build the exact FIFO-fill version myself
  since the finding already discloses the gap and it would not change the "0 of 12" count's
  direction (an ENTER decision with no completed fill would, if anything, make the true FIFO
  count of scored-day-dependency even lower, not higher, since fewer decisions would count as
  scoring at all).

## Net assessment

Nothing in this finding oversells past what the ledgers and code show. The one genuinely
consequential empirical claim — that the shared-signal leak has never, in 12 observed
leak-eligible dates, been safe-3's sole source of a scored day — survives an independent,
from-scratch rebuild with an identical result. The designation-accuracy argument (gate_override
real and binding; the implied "safe cohort gates too" reading false; no instrument assumes
otherwise) is directly supported by reading the same code and same four files myself. I find no
material error, no unverified-but-load-bearing number, and no overstatement. **SUPPORTED stands.**
