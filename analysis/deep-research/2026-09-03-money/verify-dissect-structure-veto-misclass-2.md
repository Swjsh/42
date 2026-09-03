# VERIFY (skeptic, REPRODUCTION lens) — dissect-structure-veto-misclass

Stamp: 2026-09-03T11:53 ET (market open, live engine ticking; read-only pass).
Target: `analysis/deep-research/2026-09-03-money/dissect-structure-veto-misclass.md`
Target script: `backtest/tools/dissect_structure_veto_misclass.py`
My script: `backtest/tools/dissect_verify_structure_veto_misclass_2.py`
My raw output: `analysis/deep-research/2026-09-03-money/verify-dissect-structure-veto-misclass-2.json`

## Verdict: REFUTED (material disagreement in the population reconstruction)

The code-level defect mechanism and today's specific episode data are **confirmed accurate** —
I independently re-derived them from source and they match byte-for-byte. But the report's
**historical/population section (its §3)** rests on a data-loading bug in its own script that
silently discarded 87% of the ledger's rows, then reported the resulting emptiness as a
"disclosed gap" rather than as what it actually is: a bug. Re-running the *same* methodology
against the *full* available data reverses the strength of the population-level claim.

---

## What I independently CONFIRMED (not refuted)

1. **`_classify_sameday_5m` / `_veto_side`** (`backtest/lib/engine/engine_cli.py:177-224`) — read
   the live file directly. Matches the report's quoted code verbatim: `_veto_side` blocks C on
   `trend=='downtrend'` unconditionally; `_classify_sameday_5m` calls `find_swing_points(bars,
   window=2, inclusive_right=True)` → `label_swings` → `classify_trend`, with no call to
   `walk_structure` anywhere in the function.
2. **`grep -n "walk_structure" backtest/lib/engine/engine_cli.py setup/scripts/heartbeat_core.py`**
   → zero matches, confirmed independently.
3. **`crypto/lib/market_structure.py`** docstrings and `classify_trend` body match the report's
   quotes exactly: `classify_trend` is self-labeled "Tentative trend... Used as the fallback...
   `walk_structure` gives the authoritative trend."
4. **`crypto/lib/trendlines.py:find_swing_points`** — `for i in range(window, n - window)` with
   `window=2` confirmed: the last 2 bars fed in (indices `n-2`, `n-1`) can never be `i`, so they
   can never register as a pivot. Structural blind spot confirmed, not an approximation.
5. **Today's raw ledger rows** — I pulled `automation/state/core-decisions.jsonl` (read-only)
   myself: exactly **17** `SKIP_STRUCTURE_VETO` rows for `account=safe, date=2026-09-03`, all
   `side=C`, all `structure_reason=downtrend`, at the exact timestamps and SPY prices the report
   lists (11:11:04→11:35:04, SPY 770.73→772.93). Dedupes to the same 5 episodes.
6. **`automation/state/gate-registry-status.json`** — `structure_veto_enabled` block matches the
   report's quote exactly: `overall: "YELLOW"`, safe n=5, wr=40%, exp_per_trade=+$69.7,
   total=+$348.50, `sign: "POSITIVE"`, reason text verbatim `"refused cohort positive ($69.7/tr)
   but n=5 < floor 10 -- watch, not yet actionable"`, `replay_soundness: "sound"`.
7. **`analysis/recommendations/structure-veto-lift-prereg-2026-08-04.json`** and
   **`structure-veto-ab-2026-06-26.json`** — read both directly; the report's quoted numbers
   (RED/n=11/+$38.97/tr; full_vetoes=107, 2 trades affected, 0 winners/2 losers removed, $0 OOS
   delta) match the files exactly.
8. **`automation/state/params.json`** — `structure_veto_enabled: true` confirmed current, read-only.

None of the code-level or single-document claims are refuted. The problem is entirely in the
report's own **derived historical population** (§3 of the target report).

---

## What I REFUTE — the ledger "retention window" and "n=2" claims

### The retention claim is false

The report states: *"`automation/state/core-decisions.jsonl` (READ-ONLY) currently retains
2026-08-26 through 2026-09-03 only — 7 full sessions + today. It does not reach back to
2026-06-26 when the veto shipped... that history has rolled off under the ledger's retention
policy (OP-22)."*

I read the same file directly:

```
total rows in ledger: 37659
ts_et range: 2026-06-25T13:48:17 .. 2026-09-03T11:53:04
```

The file physically contains **37,659 rows spanning 2026-06-25 to 2026-09-03** — more than two
months, reaching back to *before* the veto's 2026-06-26 ship date. It has not "rolled off."

### The mechanism of the report's error

Of the 37,659 rows, only 4,918 (13%) carry an explicit `"date"` key; the other 32,739 (87%,
everything roughly before 2026-08-26) predate that schema field but *do* carry a full `ts_et`
(e.g. `"2026-07-06T13:11:27"`) from which the date is trivially derivable (`ts_et[:10]`). The
target script's history-filter line is:

```python
veto_rows = [r for r in all_safe_rows if r.get("verdict") == "SKIP_STRUCTURE_VETO"
             and r.get("date", "") >= VETO_SHIP_DATE]
```

`r.get("date", "")` returns `""` for every one of those 32,739 older rows (the key is simply
absent), and `"" >= "2026-06-26"` is `False` — so **every pre-08-26 row is silently dropped**,
including 211 of the ledger's own 228 `SKIP_STRUCTURE_VETO` rows for the safe account. The
report never surfaces this filter as lossy; it instead concludes the data doesn't exist and
labels that "disclosed." A silently-dropped 87% of the source file is a bug in the reproduction,
not a disclosed limitation of the source.

### The "2026-08-06 / 2026-08-13 cannot be checked" claim is also false

The report says those two named winning days "cannot be checked from it; this gap is disclosed
rather than filled with an assumption." Both days are fully present:

```
2026-08-06: total_decision_rows=388 veto_rows=1   (04:16:32 ET, PRE-MARKET, side field null)
2026-08-13: total_decision_rows=386 veto_rows=0
```

2026-08-13 shows **zero** `SKIP_STRUCTURE_VETO` fires — directly checkable, not a gap — the
*same* zero-effect conclusion the report reached (correctly, from data it did have) for
2026-08-27 and 2026-08-28. 2026-08-06 has exactly one fire, at 04:16 ET premarket with no side
recorded — essentially a non-event for RTH trading, but it exists and was claimed not to.

### Recount: n=2 (report) vs n=23 (full history, same methodology)

Backfilling `date` from `ts_et[:10]` and re-running the report's own dedup rule (consecutive
same-side same-date rows, gap ≤120s → one episode) and its own +30-min-forward-SPY-move
"would the blocked side have won" test, against the **full** retained ledger instead of the
89%-truncated one:

| | Report | My reproduction (same file, same rule, dates backfilled) |
|---|---|---|
| Raw `SKIP_STRUCTURE_VETO` rows, account=safe | 17 (today only) | **228** (2026-07-06 → 2026-09-03) |
| Deduped episodes (C or P side) | 5 (today only) | **27** across history (12 C + 15 P), 5 of them today |
| Episodes with a completed +30m readout | 2 | **23** |
| Blocked side "would have won" | 0/2 (0%) | **13/23 (56.5%)** |
| 95% bootstrap CI on win rate (n≥8) | not reported (n too small) | **[34.8%, 78.3%]** — straddles 50% |

Full per-episode table and raw counts: `verify-dissect-structure-veto-misclass-2.json`.

A 95% CI that spans 50% means the full ledger's own history does **not** give statistically
distinguishable evidence that the structure veto systematically refuses net-favorable entries —
contrary to the impression left by "0/2, veto wrong both times." (Two of the 23 completed
readouts are 15:31/15:46 ET entries whose nominal "+30m" sample lands after the day's tape ends,
i.e. a degraded near-EOD readout, not a clean 30-minute window; dropping those two: n=21,
13/21 = 61.9% WR, still not something I compute a materially different CI for here, still not a
clean population claim either way — noted as a caveat, not a fix.)

**Note in the report's favor**: by the time I ran this check (11:53 ET vs. the report's 11:40-11:50
finalization), a third of today's own episodes (11:21 entry) had crossed its own +30m mark and
also came in favorable (+0.915 SPY) — so today's own in-session pattern, now 3/3 completed and
favorable rather than 2/2, is *not* weakened by this check. What's refuted is the report's
implicit generalization from that small today-only sample plus a falsely-claimed absence of
older data, when the older data was sitting in the same file the whole time and doesn't back the
same strength of conclusion.

---

## What this does and does not affect in the original finding

- **Does not refute**: the code-level defect mechanism (non-authoritative fallback classifier,
  hard-coded 10-minute pivot-confirmation blind spot) — confirmed directly from source, no
  ambiguity.
- **Does not refute**: today's specific 5-episode, 17-row ledger read, or the independent
  `gate_expiry_check.py` / prereg / AB-study document quotes — all byte-matched.
- **Refutes**: the report's claim that the ledger "does not reach back to 2026-06-26... rolled
  off" (false — it reaches back to 2026-06-25), its claim that 2026-08-06/2026-08-13 "cannot be
  checked" (false — both are fully present, one shows zero fires, exactly like the two days that
  could be checked), and — the load-bearing one for the REPRODUCTION lens — its implied
  population-level "the veto is currently misfiring against a favorable direction" argument built
  from n=2. The same file, same rule, correctly parsed, gives n=23 and a win rate not
  distinguishable from a coin flip (CI spans 50%). This is a **material disagreement** on
  population size and effect strength, not a difference of interpretation.

## Caveats on my own check

- My date-backfill (`ts_et[:10]`) assumes the pre-08-26 rows' `ts_et` values are already in ET
  (they read as ET-formatted timestamps consistent with the rest of the file; I did not
  independently re-verify timezone provenance for that older schema era beyond that consistency
  check).
- Same +30-min raw-SPY-direction proxy the target script used — not a $-P&L replay (that's what
  the separately-cited `gate_expiry_check.py` instrument does, at n=5, "watch not yet actionable"
  per its own verdict, which I did not re-derive, only re-read).
- n=23/n=21 is still a modest sample; I report the bootstrap CI as computed, not as a claim that
  the veto is "fine" — only that the report's own "0/2 both wrong" framing does not survive
  contact with the rest of the same file.
