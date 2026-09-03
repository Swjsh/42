# PRE-REGISTRATION — ENTRY-LOCATION x TREND-QUALITY (F2), 2026-09-03

**Status: FROZEN before this test is ever read as a verdict.** Commit timestamp of this file
is the freeze proof. `setup/scripts/entry_location_trend_shadow.py` (ledger/summary builder)
and `setup/install-entry-location-trend-shadow.ps1` (scheduled task) are committed alongside
this file. Section 4's bar happens to already be met at freeze time (see §6) — that does NOT
advance this file's own decision rule to a read; see §6 for why.

Slug: `F2-entry-location-trend`. Descends from
`analysis/deep-research/2026-09-03-money/entry-location.md` (H1 ENTRY LOCATION, verdict
**INCONCLUSIVE**, no live rule proposed), whose own "Proposed change" section named this
exact instrument as its recommended next step (quoted in
`setup/scripts/entry_location_trend_shadow.py`'s docstring).

---

## 1. What is being judged

Whether **`minutes_since_ribbon_flip`** — a trend-quality co-signal, not itself a rule — can
separate H1's "chase" bucket (`range_position>=0.75` for calls, the definition H1 froze and
this instrument reuses unmodified via `money_entry_location_stats.classify_chase`) into two
populations with different realized outcomes, within **`BULLISH_RECLAIM_RIDE_THE_RIBBON`**
only (58% of H1's population, the setup carrying H1's single largest point-estimate gap and
also the setup behind the 08-13/08-27 blocked-winner clusters that disqualified H1's naive
global rule):

> **Hypothesis:** chase entries within the first **15 minutes** after the ribbon stack flips
> into the trade's own direction are **paying breakouts** (a fresh continuation, riding a move
> that just started). Chase entries more than **45 minutes** after that flip are **exhaustion
> chases** (the move is old; price sitting at the session extreme is more likely near its end
> than its start). The 15-45 minute band is a named gray zone, excluded from the primary
> comparison — the hypothesis only makes a claim about the two tails.

This is the mechanism H1's own report proposed (quoted verbatim in the builder script's
docstring): *"require the chase bucket to be conditioned on a trend-quality co-signal ... so
a fresh-breakout continuation can be told apart from an exhaustion chase before any gate is
proposed."* `minutes_since_ribbon_flip` is the most direct available proxy for "how old is
this move" — `entry_location_trend_shadow.py` computes it from `core-decisions.jsonl`'s own
`ribbon` field (BULL/BEAR/MIXED), walking backward from entry through a no-lookahead prefix
to find when the current streak in the trade's direction began.

## 2. Population and measurement (frozen)

- **Scope:** `BULLISH_RECLAIM_RIDE_THE_RIBBON` rows in
  `analysis/recommendations/entry-location-trend-ledger.jsonl` where
  `chase_extreme_0.75_0.25 is True` (i.e. `side=='C' and range_position>=0.75`, H1's own
  threshold, reused not re-derived).
- **Fresh bucket:** `minutes_since_ribbon_flip <= 15` (and not None — a trade whose ribbon at
  entry doesn't match its own direction, or whose flip is unobservable, carries no
  `minutes_since_ribbon_flip` value at all and is excluded from BOTH tails, counted separately
  as `ribbon_flip_unavailable_or_not_matching_direction`).
- **Stale bucket:** `minutes_since_ribbon_flip > 45`.
- **Gray zone (excluded from the primary comparison):** `15 < minutes_since_ribbon_flip <= 45`
  — reported for transparency (`gray_15_45min_excluded_from_primary_comparison` in the
  summary) but never blended into either tail.
- **Left-censored rows** (`ribbon_flip_left_censored=True` — the matching streak covers the
  entire visible prefix for that date, so the TRUE flip time may be earlier than observed) are
  **included** in whichever bucket their observed (possibly understated) minutes value lands
  in — excluding them entirely would silently shrink an already-thin population, and a
  left-censored streak understates `minutes_since_ribbon_flip`, which if anything biases
  toward the "fresh" bucket, not away from it (a conservative direction for this hypothesis,
  disclosed not hidden).
- **Metric:** `mean(realized_pnl | fresh) - mean(realized_pnl | stale)`, 5,000-resample
  nonparametric percentile bootstrap (`money_entry_location_stats.bootstrap_diff_ci`, reused
  unmodified — same method, same 2.5/97.5 percentile convention H1 itself used).
- **No look-ahead:** every input (`range_position`, `minutes_since_ribbon_flip`, and every
  other co-signal in the ledger) is computed from ticks with `ts_et <= entry_ts` only —
  verified by `test_entry_location_trend_shadow_2026_09_03.py`'s synthetic-ledger test (a tick
  recorded after entry must never change an already-computed row).

## 3. Bar (frozen — not softened at read time)

Both conditions required before this test may be **read**:

- **`n_chase >= 150`** for `BULLISH_RECLAIM_RIDE_THE_RIBBON` (the combined chase-bucket
  population across fresh + gray + stale + unavailable — the floor named in this task's own
  instruction, tracked nightly in the summary's `prereg_readiness` block).
- **`n_fresh >= 30` AND `n_stale >= 30`** — the combined floor does not guarantee either named
  tail has adequate power on its own; a 150-trade chase bucket that is 140 stale and 10 fresh
  cannot support a fresh-vs-stale comparison regardless of the combined count. This is the
  same lesson `GATE-DESIGN-FIXED-CALENDAR-WINDOWS-STARVE-LOW-FIRE-RATE-KNOBS` generalized
  (cited by the sibling `tp1_r50_forward_shadow` prereg): a comparison needs its OWN adequate
  n on both sides, not a shared aggregate floor.

## 4. Decision rule (frozen — cannot be softened after data starts arriving)

Once the bar in §3 is met, the hypothesis becomes **SUPPORTED** only if ALL THREE hold:

1. **`ci_lower_2.5(mean_diff_fresh_minus_stale) > 0`** — the 2.5th-percentile of the bootstrap
   CI on `mean(fresh) - mean(stale)` is strictly positive (fresh reliably beats stale, not
   just on the point estimate).
2. **`top3_concentration_share < 0.50`** in BOTH the fresh and stale buckets independently —
   the 3 largest-magnitude `|realized_pnl|` trades in each bucket explain less than half of
   that bucket's own total `|realized_pnl|`. A verdict carried by 1-2 outsized trades in
   either tail is not a verdict (same guard `stop_mode_shadow_ledger.py` and
   `tp1_r50_forward_shadow.py` both apply to their own populations).
3. **`n_fresh >= 30` AND `n_stale >= 30`** still holds at read time (re-verified, not assumed
   from §3's gate check — the population can shift between the gate check and the read if this
   file is consulted more than once).

Any single failure = **the hypothesis is not supported by data as measured** — the co-signal
does not usefully separate fresh breakouts from exhaustion chases at this granularity, full
stop. This decision rule is not re-opened after the fact (no loosening the 15/45-minute bands,
no re-cutting the gray zone into either tail, no dropping the concentration or power checks).

**A SUPPORTED read is still not a rule.** It is permission for a SEPARATE, later proposal to
cite this ledger as its evidence base for a real gate — never automatic, and never live before
the freeze lifts (§6).

## 5. What this instrument is not

Descriptive and shadow-only. `entry_location_trend_shadow.py` flips no knob, places no order,
and proposes no gate. `analysis/recommendations/entry-location-trend-summary.json`'s
`prereg_cut_diagnostic` block previews this exact cut every night purely for transparency
(OP-33) — it is explicitly labeled **not the official verdict** in its own `note` field, and
this file (not the nightly summary) is the sole authority on when/whether a read has occurred.

## 6. Expansion-class — nothing before 2026-10-30

Per this task's own instruction, this whole line of work is **expansion-class**: no proposal,
no gate, no live change of any kind before **2026-10-30**, independent of when §3's bar is
met or what §4's rule would say if read today. This is also mechanically enforced twice over —
the September config freeze (through 2026-10-30, `markdown/doctrine/` project notes) and this
build task's own trading-path-file lock both separately block any live rule change regardless.

**Disclosure (not a read):** at this file's freeze time, the FIRST backfill run of
`entry_location_trend_shadow.py` already populated `n_chase=152` for
`BULLISH_RECLAIM_RIDE_THE_RIBBON` (above §3's 150 floor) because this instrument — unlike the
sibling `tp1_r50_forward_shadow` — backfills all of `mae-mfe.json`'s existing history rather
than starting from an empty forward clock (§7 of the build task explains why: this
instrument's job is building the population a later read will consume, not itself
adjudicating a knob against a frozen bar the way `tp1_r50_forward_shadow` does). Meeting the
combined floor on day one does **not** advance this file to a read — §6's expansion-class
freeze still applies, and §3's *own* n_fresh/n_stale floors are the ones that actually gate a
read, not the combined count alone. For transparency only, the current diagnostic split
(`prereg_cut_diagnostic` in the summary, generated 2026-09-03) reads:
`fresh_leq_15min` n=36, mean **-$6.97**/trade; `stale_gt_45min` n=83, mean **+$7.47**/trade;
`mean_diff_fresh_minus_stale_ci95 = [-$14.44, -$71.17, +$43.16]`. This is the **opposite
direction** of the hypothesis on the current point estimate, and the CI crosses zero. This is
disclosed exactly as observed — it is not a read under §4 (n_fresh=36 and n_stale=83 both
already clear §3's 30-trade floor, so a formal read is not blocked by power; it is blocked
solely by §6's expansion-class freeze), and no interpretation or action follows from it here.

## 7. Build step (structured, for machine reference)

```json
{
  "build_step": {
    "id": "F2-entry-location-trend",
    "descends_from": "analysis/deep-research/2026-09-03-money/entry-location.md",
    "frozen_date": "2026-09-03",
    "backfill": "full history, analysis/pain-ledger/mae-mfe.json, no date cutoff",
    "in_sample_cutoff": "2026-09-02",
    "target_setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
    "cosignal": "minutes_since_ribbon_flip",
    "bands": {"fresh_max_minutes": 15, "stale_min_minutes": 45, "gray_zone": "excluded from primary comparison"},
    "bar": {"n_chase_min": 150, "n_fresh_min": 30, "n_stale_min": 30},
    "decision_rule": {
      "ci_lower_2p5_gt_zero": true,
      "top3_concentration_share_lt_both_buckets": 0.50,
      "power_reverified_at_read": true,
      "all_required": true,
      "softenable": false
    },
    "expansion_class": true,
    "no_action_before": "2026-10-30",
    "artifacts": {
      "ledger": "analysis/recommendations/entry-location-trend-ledger.jsonl",
      "summary": "analysis/recommendations/entry-location-trend-summary.json",
      "builder": "setup/scripts/entry_location_trend_shadow.py",
      "scheduled_task": "Gamma_EntryLocationTrendShadow",
      "install_script": "setup/install-entry-location-trend-shadow.ps1"
    },
    "do_not": [
      "propose or ship any live gate before 2026-10-30",
      "loosen the 15/45-minute bands or re-cut the gray zone after seeing data",
      "treat the combined n_chase>=150 floor as sufficient without n_fresh/n_stale>=30 each",
      "treat prereg_cut_diagnostic in the nightly summary as an official read"
    ]
  }
}
```

## 8. Revert

Whole instrument, one shot: `Unregister-ScheduledTask -TaskName
Gamma_EntryLocationTrendShadow -Confirm:$false` + delete
`setup/scripts/entry_location_trend_shadow.py` +
`setup/install-entry-location-trend-shadow.ps1` +
`analysis/recommendations/entry-location-trend-ledger.jsonl` +
`analysis/recommendations/entry-location-trend-summary.json` + this file. Nothing on the
trading path depends on this instrument — analysis-only leaf, same class as
`Gamma_LadderRungShadow` / `Gamma_Tp1R50ForwardShadow`.
