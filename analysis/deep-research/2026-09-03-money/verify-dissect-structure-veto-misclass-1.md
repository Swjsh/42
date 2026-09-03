# Verify pass 1 — dissect-structure-veto-misclass (D7)

Stamp: 2026-09-03T11:54 ET (market open, live engine ticking; read-only pass, no trading-path
edits, no network calls). Skeptic mandate: default to refuted unless independently confirmed.

## Verdict: REFUTED

The **code-level mechanism claim is TRUE and independently reconfirmed** (see §1) — that part of
the finding survives. But the finding's headline verdict (`SUPPORTED`) and its `proposed_change`
#1 (flip `structure_veto_enabled` to `false` because it's "ready to ship for a month" and "kills
winners") are **refuted by evidence already sitting in this repo that the original report never
found**:

1. **Fatal flaw**: a newer, more rigorous, already-shipped full-statistics revalidation
   (`analysis/recommendations/gate-revalidation-structure_veto-2026-08-23-extended.json`,
   generated 2026-08-23 — 11 days before this report, and explicitly built to supersede the
   2026-08-04 prereg the report cites) already ran the exact proposed flip through a real
   trade-level replay and returned **`verdict: "NOT-UNBLOCK-ELIGIBLE"`**, `drop_top3: -$588`,
   `one_sample_p: 0.8361`, and `"recommendation": "DO NOT FLIP -- fails G_drop3/G_bhfdr"`. The
   report's #1 proposed action is not merely weak — it is the exact thing this newer, on-point,
   already-computed analysis says not to do.
2. The report's central historical claim ("the ledger only retains 2026-08-26 onward, so
   2026-08-06/08-13 can't be checked, and every fire in the retained window is from today") is
   **factually false**, root-caused to a bug in its own script: `veto_rows = [... if
   r.get("date", "") >= VETO_SHIP_DATE]` silently drops the 135 of 152 SKIP_STRUCTURE_VETO rows
   that predate a schema change and carry no top-level `date` key (only `ts_et`). The real ledger
   goes back to 2026-06-25 — before the veto even shipped — and shows fires on 17 different
   session-days between 07-06 and 08-21 alone.
3. The n=5 YELLOW figure the report leans on (`+$69.7/tr`, `total_dollar: 348.5`) is a
   concentration artifact the **same JSON object already flags**, unquoted by the report: dropping
   the single best day of the 5 (`drop_top1`) leaves `$45.5`; dropping the (2 of 5) winning days
   (`drop_top3`, `n_dropped_for_drop_top3: 2`) flips the total to **`-$189.0`**. `win_days: 2,
   loss_days: 3` — 3 of 5 days are net losers for the refused cohort; the positive mean is carried
   entirely by 2 outsized days.

Not refuted: the classifier-mechanism defect is real (§1). Refuted: that this translates into an
actionable, statistically supported "kills winners" case for lifting the veto today — the
codebase's own more-rigorous, more-recent instrument already checked that exact question and
came back negative.

---

## 1. Code-level claims — CONFIRMED (re-verified independently)

Re-read the actual source, not the report's excerpts:

- `_classify_sameday_5m` (`backtest/lib/engine/engine_cli.py:192-224`) calls `classify_trend` +
  `label_swings` + `find_swing_points(bars, window=2, inclusive_right=True)` — byte-match to the
  report's quoted snippet.
- `crypto/lib/market_structure.py`'s own docstrings: `classify_trend` = *"Tentative trend...
  fallback... walk_structure gives the authoritative trend"*; `walk_structure` = *"the
  authoritative BOS/CHoCH state machine"*. Verbatim match.
- `grep -n "walk_structure" backtest/lib/engine/engine_cli.py setup/scripts/heartbeat_core.py` →
  **zero matches**, reconfirmed.
- `find_swing_points` (`crypto/lib/trendlines.py:41-72`): `for i in range(window, n - window)` —
  confirmed, the newest `window` (=2) bars structurally cannot be pivots.
- `bar_freshness` on today's veto ticks: spot-checked 11:10-11:14, all `stale: False`, `age_min`
  6.08-10.08 — matches the report's "not a staleness bug" claim.
- New (not in the report): the same tick that logs `SKIP_STRUCTURE_VETO` also blocks the
  account-wide extra-setup dispatch lane (`heartbeat_core.py:1995-2002`,
  `rec["extra_exec_blocked_by"] = "structure_veto"`) — the blast radius of one bad classifier read
  is wider than just the primary ribbon path. Doesn't change the verdict, just a fact the report
  omitted.

## 2. The ledger-retention claim — REFUTED, root cause identified

```
$ python -c "... dates=set(r.get('date') or r.get('ts_et','')[:10] for r in rows) ..."
['2026-06-25', '2026-06-26', ..., '2026-08-06', '2026-08-13', ..., '2026-09-03']
```

`automation/state/core-decisions.jsonl` retains **2026-06-25 through today** — not "2026-08-26
onward" as the report states. Of 152 `SKIP_STRUCTURE_VETO` rows for `account=safe`, 135 have no
top-level `date` key (only `ts_et`) — a schema addition partway through the ledger's life. The
report's own scratch script, `backtest/tools/dissect_structure_veto_misclass.py:171-172`:

```python
all_safe_rows = load_rows(account="safe")
veto_rows = [r for r in all_safe_rows if r.get("verdict") == "SKIP_STRUCTURE_VETO"
             and r.get("date", "") >= VETO_SHIP_DATE]
```

`r.get("date", "")` returns `""` for those 135 rows; `"" >= "2026-06-26"` is `False` in Python
string comparison, so every one of them is silently dropped. That's the entire mechanism behind
"every single SKIP_STRUCTURE_VETO row in the retained window is from today" — it isn't a
retention-policy fact, it's an artifact of an unguarded `.get("date", "")` filter on a field that
doesn't exist on 89% of the rows it's filtering.

(A sibling verify pass — `verify-dissect-structure-veto-misclass-0.md`, already on disk — found
the identical bug independently and reached the same root cause. `verify-dissect-structure-veto-
misclass-2.md` also found it but argued it "strengthens, not refutes" the conclusion because more
fires still skew wrong-way. §3-4 below is where this pass parts ways with that reading.)

## 3. Independent population reconstruction (armed=true only, all history)

The 16 SKIP_STRUCTURE_VETO rows with `armed: false` are off-hours dry-run noise (`spy: 751.0`,
`spread_cents: 10`, `vix: 16.0` constant sentinel values, firing at 20:16 Tuesday night, etc.) —
excluded. Deduped into same-day/same-side/≤2.5-min-gap episodes, `account=safe`, `armed=True`:

**26 real episodes total** (06-25 through today), **20 with a completed same-day +30min SPY
readout**:

| Metric | Value |
|---|---|
| n completed | 20 |
| veto wrong (blocked side gained) | 12/20 (60%) |
| veto right (blocked side lost) | 8/20 (40%) |
| sum of SPY move for blocked side | +3.655 |
| mean | **+0.183** |
| bootstrap 95% CI (5000 resamples) | **[-0.273, +0.586]** — crosses zero |

This SPY-point proxy (not $, no options mechanics) is **not statistically distinguishable from
zero** at n=20. It is directionally consistent with the report's "veto tends to be wrong" framing
but does not itself support "SUPPORTED" at the confidence the verdict implies — which is exactly
why the report leaned on the `gate_expiry_check.py` instrument instead (§4).

**Top-3-by-magnitude removed**: sum 3.655→2.885, mean 0.183→0.170 — barely moves. This particular
20-episode SPY-move sample is *not* itself concentration-fragile the way the $-based instrument
below is; the concentration problem lives in the $-P&L numbers (§4), not in this cruder proxy.

**VIX-band split** — the sign flips:

| VIX band | n | mean SPY move (blocked side) |
|---|---|---|
| <15 | 7 | **+0.578** |
| 15-18 | 9 | +0.289 |
| 18-22 | 4 | **-0.749** (veto right on average) |

Today's VIX ran 14.84-14.91 during the veto episodes — squarely in the band where this proxy says
the veto is most wrong. The report's 5-episode sample today is drawn from exactly the regime where
history says this classifier struggles most; it is not necessarily representative of how the gate
performs at VIX 18-22, where the same data says it's net *helpful*.

## 4. The $-P&L instrument's own concentration check — the fatal flaw

`automation/state/gate-registry-status.json` → `gates.structure_veto_enabled.pnl_check.combined`
(quoted in full, not selectively):

```json
{"window":"2026-07-29..2026-09-01","n":5,"wr_pct":40.0,"exp_per_trade":69.7,
 "total_dollar":348.5,"sign":"POSITIVE","best_day":303.0,"worst_day":-168.0,
 "win_days":2,"loss_days":3,
 "drop_top1":45.5,"n_dropped_for_drop_top1":1,
 "drop_top3":-189.0,"n_dropped_for_drop_top3":2,
 "verdict":"YELLOW","reason":"refused cohort positive ($69.7/tr) but n=5 < floor 10 -- watch, not yet actionable"}
```

The report quoted `exp_per_trade`, `total_dollar`, `sign`, and the `reason` string verbatim — but
never mentioned `drop_top1` / `drop_top3`, sitting in the same object. `drop_top_n` (`backtest/lib/
concentration.py`) only ever drops **winning** days: with `win_days: 2`, dropping the single best
day (`drop_top1`) takes the $348.5 total down to **$45.5**; dropping both winning days
(`drop_top3`, capped at `n_dropped_for_drop_top3: 2` since there are only 2 to drop) flips it to
**-$189.0**. The entire "refused cohort is net positive" read is carried by 2 of 5 days.

This is not a novel objection — it is the **documented, named failure mode** this codebase already
fixed once. `backtest/lib/concentration.py`'s own docstring names `structure_veto_enabled` as
**instance #1** of "a monitoring instrument computes a verdict from a raw mean over a small sample
with no concentration guard, so a handful of outlier trades... flips the label" — fixed in commit
`71c39545` (2026-08-23):

> "Two independent full G-battery revalidations this weekend proved the nightly gate-expiry
> checker wrong both times it fired RED (**structure_veto_enabled n=10 +$2.15/tr naive vs battery
> drop-top3=-$588 BH-FDR p=0.836 NOT-UNBLOCK-ELIGIBLE**...)"

And the full-battery artifact that commit refers to is still on disk and still the most recent
revalidation of this exact gate:
`analysis/recommendations/gate-revalidation-structure_veto-2026-08-23-extended.json`
(`generated_at: 2026-08-23T02:05:20`, mtime confirmed newest of the 4 structure-veto recommendation
files, explicitly `"supersedes_for_recency"` the 2026-08-08 one). It replays the SAME cohort
through the real production core (`walk_exit_manager` / `exit_manager.plan_exit_actions`, n=15
actual simulated trades with real entry premiums / exit reasons / per-trade $ P&L, window
2026-06-26..2026-08-21) and returns:

```json
"cohort": {"n":15,"total":111.5,"mean":7.43,"wr_pct":40.0,
           "drop_top3":-588.0,"n_dropped_for_drop_top3":3,"best":303.0,"worst":-174.0},
"g_battery": {"gates":{"G_mean":true,"G_oos":true,"G_drop3":false,"G_bhfdr":false,"G_n":true},
              "verdict":"NOT-UNBLOCK-ELIGIBLE","pval":0.8361},
"params_diff": {"key":"structure_veto_enabled","current":true,"proposed":false,
                "recommendation":"DO NOT FLIP -- fails G_drop3/G_bhfdr"}
```

`one_sample_p: 0.8361` — indistinguishable from chance. This is the **exact proposed flip** in the
D7 report's `proposed_change` #1, already tested by the codebase's own more rigorous instrument,
11 days before the report was written, with an explicit "DO NOT FLIP" recommendation — and the
report never surfaced it. (The JSON's `guard_test_snippet` field proposes a pytest that pins
`structure_veto_enabled is True`; I could not find that snippet actually materialized as a live
test file under `backtest/tests/` — flagging that as UNVERIFIED rather than claiming it exists.)

The 2026-08-04 lift-prereg the report calls "ready to ship for a month" was itself built on the
naive n=11 mean-only read this same commit's message says was **proven wrong** by that weekend's
battery run. Citing the 2026-08-04 prereg as current, actionable evidence — without checking
whether it had since been superseded — is the report's load-bearing error.

## 5. WINNER-KILLER / CONCENTRATION lens, as instructed

**Would disabling the veto have hurt 08-06, 08-13, 08-27, or 08-28?** No — confirmed **zero**
`armed=true` `SKIP_STRUCTURE_VETO` fires on all four dates, using the corrected full-history read
(§2-3). This *is* consistent with the report's conclusion for 08-27/08-28 — but the report claimed
08-06/08-13 were **unknowable** ("outside the retained window"); they are not, and the direct
answer is the same as the other two: zero fires, zero effect, on all four.

**Would it have hurt today's 11:06 wave?** No — but not for the reason implied. The 11:06-11:10
wave was blocked by a **different, unrelated gate**: `SKIP_BULL_1100_1200` (`block_bull_1100_1200`,
Safe-only time-of-day gate), confirmed directly from `core-decisions.jsonl` (`11:06:03` through
`11:10:04`, all `verdict: SKIP_BULL_1100_1200`). `SKIP_STRUCTURE_VETO` only starts at `11:11:04`.
**The proposed fix would not have touched the 11:06 wave at all** — it only bears on the separate,
later 11:11-11:35 cluster the report analyzed. The task's framing ("today's 11:06 wave") and the
report's episodes are two different gates; conflating them would overstate the fix's reach.

**Remove the top-3 contributors and recompute, split by arm and VIX band:**
- By arm: `SKIP_STRUCTURE_VETO` is **architecturally exclusive to `account=safe` (safe-2)**.
  `grep -c STRUCTURE_VETO` on `automation/state/fleet/{safe-3,risky-1,risky-3,safe-1}/
  decisions.jsonl` → **0** in every file. `automation/state/aggressive/params.json` sets
  `structure_veto_enabled: false` explicitly (2026-08-12, documented: "116 times for
  account=safe and ZERO times for bold" — now 152/0 as of today). **Whatever this defect costs or
  saves, it is 100% concentrated in one of five live arms; zero blast radius to bold-2, safe-3,
  risky-1, risky-3, or safe-1's P&L.** This is the single biggest scope-limiter the report doesn't
  state plainly.
- By VIX band: sign flips at VIX 18-22 (§3 table) — the "veto is wrong" pattern is not uniform
  across regimes.
- Top-3 removed (SPY-move proxy, §3): mean barely moves (0.183→0.170) — this proxy isn't itself
  outlier-driven. The $-P&L instrument (§4) *is* outlier-driven (2 of 5 days carry the entire
  positive total) — that's the more decisive number because it's real trade P&L, not a raw SPY
  delta, and it's the one the report actually cited.

## 6. What this does NOT overturn

- The classifier mechanism defect (§1) — real, independently reconfirmed, and orthogonal to the
  P&L question. `classify_trend`'s structural 10-15 min blind spot on the newest price action is a
  fact regardless of whether lifting the veto would help or hurt today.
- That today's 5 episodes (11:11-11:35) did, in fact, fire while SPY continued rallying — the raw
  ledger rows and the +30m SPY readouts (770.73→772.465, 771.50→772.58, 772.02→772.935, all
  re-verified against fresh ticks through 11:54 ET) are accurate.
- That the ratifying 2026-06-26 A/B's "$0 OOS delta, 2 losers removed, 0 winners removed" claim,
  re-read directly from `structure-veto-ab-2026-06-26.json`, is quoted correctly.

## 7. What is refuted

- "Ready to ship for a month" / "sitting unarmed" as a reason to flip the switch now — refuted by
  a newer, on-point, already-computed full-battery verdict saying the opposite (§4).
- "2026-08-06 and 2026-08-13... cannot be checked... this gap is disclosed" — refuted; they can be
  checked, and the ledger's actual retention window (06-25 onward) was misreported due to a
  reproducible bug in the report's own script (§2).
- The implicit strength of "SUPPORTED" as a population-level P&L claim — refuted at the
  statistical level my own reconstruction can reach (CI crosses zero, n=20, §3) and refuted more
  decisively by the codebase's own concentration-guarded instrument, which already ran this exact
  test and returned NOT-UNBLOCK-ELIGIBLE (§4).
- Any framing that "today's 11:06 wave" was a casualty of the structure veto — it wasn't; a
  different gate blocked that wave (§5).

## Caveats

- The n=20/n=26 episode reconstruction here is a SPY-price proxy (not $, no option mechanics, no
  entry/exit simulation) — cruder than `gate_expiry_check.py`'s own trade-level replay. Where the
  two disagree in magnitude (my n=20-26 vs the battery's n=15), the battery is authoritative (real
  production `exit_manager` replay); this pass's numbers are corroborating, not a substitute.
  Disclosed as APPROXIMATE, consistent with this task's proxy-labeling requirement.
- I did not re-run `gate_expiry_check.py` or `gate_revalidation_structure_veto_extended_2026_08_23.py`
  myself (would touch a >5min-risk grind and isn't necessary — their output files are already on
  disk, dated, and internally consistent with the commit history that produced them). I read their
  outputs, not their code line-by-line; the concentration math is independently checkable by hand
  from the numbers themselves (348.5 - 303.0 = 45.5, exact) and matches.
- No trading-path files touched. No network calls. Read-only throughout.
