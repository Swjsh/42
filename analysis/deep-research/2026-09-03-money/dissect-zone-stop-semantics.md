# D2 STRUCTURE STOP vs THE ZONE RULE (2026-09-03)

Stamp: 2026-09-03T11:40 ET, data refreshed through the run at 2026-09-03T11:51 ET.
Full machine-readable data + citations:
[`dissect-zone-stop-semantics.json`](dissect-zone-stop-semantics.json). Builder (read-only
on `automation/state`/`journal`/`analysis/quote-tape`, cached data only, no
network/broker calls): [`backtest/tools/dissect_zone-stop-semantics.py`](../../../backtest/tools/dissect_zone-stop-semantics.py),
which reuses `money_structure_stop_buffer_sim.py`'s option-bar/catastrophe-cap/bootstrap
machinery by IMPORT, unmodified. Prior art extended:
[`structure-stop-whipsaw.md`](structure-stop-whipsaw.md) (H5, 79-event population,
5 fixed-buffer variants, all REFUTED).

## VERDICT: REFUTED, same mechanism as H5. change_class: NONE.

The zone-edge buffer (each trigger's own recorded `zone_width`, not an arbitrary
constant) reproduces H5's exact finding: **net positive headline (+$4,076, n=79), but
106.7% of that net sum comes from 3 of 79 positions — the identical 2026-08-04
`SPY260804C00768000` cluster the whipsaw study already flagged for `BUF-0.25`/`BUF-ATR0.5x`
— and dropping the single best day (2026-08-04) flips the whole population net NEGATIVE
(-$841).** A stop sized to the level's own real-world width is not a different animal
from a fixed-dollar buffer here; it inherits the same rare-event, arm-replicated
concentration problem.

**TODAY is a split result and the clearest illustration of WHY the aggregate is unstable:**

- **Wave 1 (09:41 entries, trigger 769.36):** zone-edge changes NOTHING — the actual -50%
  premium cap fired first because the chart level was never within a mile of being
  touched (SPY only drifted $0.20 against the position). FACT.
- **Wave 2 (10:16 entries, trigger 768.00):** zone-edge would have let all 4 legs ride
  straight through the 10:36 whipsaw and into the SAME rally the 11:06 third-wave
  re-entries captured for real — turning a realized **-$266** into a counterfactual **at
  least +$563 to +$638 on the bold-2 leg alone** (bounded by real market prints of the
  same contract, not a proxy) plus a materially positive but only APPROXIMATE (BS-proxy,
  demonstrated to UNDERESTIMATE) outcome on the other three legs.

Both are true at once: the zone-edge rule would have been a clear win TODAY, and it is a
net LOSER (once concentration is corrected for) over the last 17 real trading days it was
tested against. That is exactly the whipsaw study's own conclusion restated with a
different buffer shape — the fix that would have saved today's specific whipsaw is not
distinguishable from noise over the population that already exists.

---

## PART A — Today's two waves under a ZONE-EDGE stop

Reconstructed from `automation/state/core-decisions.jsonl`'s own per-tick
`last_closed_5m_close` field — this is the EXACT value the live engine's structure check
consulted each tick (verified byte-for-byte against the `exit_pass` legs' own
`last_closed_5m_close`), not a re-derived proxy. **FACT** unless labeled otherwise.

### Wave 1 — 09:41-09:42 entries, trigger 769.36 (SHELF_768.56_770.16, `zone_width` 0.8,
`shelf_band_observed`), zone edge 768.56

| ts (5m close) | SPY |
|---|--:|
| 09:41-09:45 | 769.735 |
| 09:46-09:50 | 769.79 |
| 09:51-09:55 | 769.64 |
| 09:56-10:00 | 769.59 |
| 10:01-10:05 | 769.54 |

Minimum 5m close while ANY leg was open: **769.54** — above the raw trigger (769.36) and
$0.98 above the zone edge (768.56). **Neither the raw structure rule nor the zone-edge
rule ever fires.** All four legs exited via the -50% premium catastrophe cap exactly as
they actually did:

| Arm | Symbol | Entry | Exit | $P&L |
|---|---|--:|--:|--:|
| safe-2 | 770C | 0.98 | 0.50 (premium_stop) | -144.00 |
| bold-2 | 772C | 0.37 | 0.20 (premium_stop) | -85.00 |
| safe-3 | 770C | 1.11 | 0.57 (premium_stop) | -270.00 |
| risky-1 | 770C | 1.08 | 0.52 (premium_stop) | -280.00 |
| **Total** | | | | **-779.00** |

**Catastrophe cap vs. zone width, in SPY terms:** SPY net-moved only **$0.20** against the
position (769.735 → 769.54, 5m-close terms) over the ~20 minutes these legs were open —
25% of the $0.80 zone_width, and it never even reached the RAW $0.00-buffer trigger.
Every leg's premium still cratered 46-52%. **The -50% cap is far tighter than the zone
width here because it is firing on theta/vega chop bleed, not on a price move that came
anywhere near covering the zone's own width** — a chart-level buffer of any size is
irrelevant to what actually stopped this wave out.

### Wave 2 — 10:16-10:17 entries, trigger 768.00 (INTRADAY_PMH_2026-09-03, `zone_width`
0.384, provenance **`default_pre_ab`** — disclosed: this is NOT an observed shelf band,
it is the same near-constant ~$0.37-0.39 default every `INTRADAY_*`/`PRIOR_DAY_*` label
carries), zone edge 767.616

| ts (5m close) | SPY | breach vs raw (768.00) | breach vs zone edge (767.616) |
|---|--:|:--|:--|
| 10:31-10:35 | 768.67 | no | no |
| **10:36-10:40** | **767.96** | **YES ($0.04) — RAW FIRES HERE** | no |
| 10:41-10:45 | 768.20 | reclaimed | no |
| 10:46-11:00 | 768.19 → 768.62 | reclaimed | no |
| 11:01-11:31 | 769.265 → 772.93 | reclaimed, rallying | no |
| latest tick read (11:51) | 772.935 | — | never breached |

The raw rule fires on the 10:31-10:35 bar's close (767.96), matching the real exits
exactly. **The zone-edge rule never breaches 767.616 at any point through the latest tick
this session read (11:51 ET, SPY 772.94)** — the very next bar after the raw stop already
reclaimed to 768.20, and price ran to 772.93 by 11:31. **RIGHT-CENSORED**: the session is
still open, so "never fires" means "has not fired as of the last tick read," not "could
never fire later today."

| Arm | Symbol | Entry | Actual exit | Actual $P&L |
|---|---|--:|--:|--:|
| safe-2 | 768C | 1.40 | 1.18 (structure_stop) | -66.00 |
| bold-2 | 770C | 0.48 | 0.34 (structure_stop) | -70.00 |
| safe-3 | 768C | 1.31 | 1.18 (structure_stop) | -65.00 |
| risky-1 | 768C | 1.31 | 1.18 (structure_stop) | -65.00 |
| **Total** | | | | **-266.00** |

**Counterfactual — bold-2's 770C leg (FACT, bounded by real market prints, not proxied):**
`SPY260903C00770000` was re-held by risky-1/safe-3 from 11:07 (same symbol, same market —
option premium is a public price, not an arm-specific quantity). TP1 (+100% = 0.96,
confirmed live rule from today's own `tp1 @ +100%` reason string) had ALREADY been cleared
by the first real print after the gap (11:07:20, mid 1.145 = +138% vs. this leg's own 0.48
entry). Using that literal first post-gap print as a conservative (late) TP1 fill for 3 of
5 contracts, and marking the 2-contract runner at the SAME real range other arms actually
realized (1.95-2.32, still trailing live as of the last observed tick):

| | Low bound | High bound |
|---|--:|--:|
| TP1 leg (3ct @ 1.145) | +$199.50 | +$199.50 |
| Runner leg (2ct @ 1.95 / 2.32) | +$294.00 | +$368.00 |
| Counterfactual P&L (TP1 + runner) | +$493.50 | +$567.50 |
| Actual realized P&L | -$70.00 | -$70.00 |
| **Improvement vs. actual (Δ$)** | **+$563.50** | **+$637.50** |

**Counterfactual — 768C legs (safe-2/safe-3/risky-1, APPROXIMATE):** 768C was never
re-held after the real 10:36-10:37 exit, so unlike 770C there is no later real print to
bound it. Black-Scholes proxy (r=0, 0DTE t-to-16:00 ET), sigma implied from the last real
quote before the gap (mid 1.225 @ 10:36:58, SPY 767.96). **Cross-check**: the identical
calibration method run on 770C's own real gap (10:35 mid 0.275 → 11:07 real mid 1.145)
UNDERESTIMATES the real print by $0.17 (~18%) at the matching SPY level — a one-directional
bias (proxy low, real high), so treat every 768C proxy premium below as a floor and every
proxy timestamp as a late/conservative bound on when it was actually crossed:

| ts (5m close) | SPY | proxy 768C price |
|---|--:|--:|
| 10:36 (stop bar) | 767.96 | 1.227 (real: 1.225 — proxy validated at the anchor) |
| 11:01 | 769.265 | 1.936 |
| **11:06** | **770.445** | **2.791 — clears safe-3/risky-1's TP1 (2.62, entry 1.31)** |
| 11:11 | 770.73 | 3.014 — clears safe-2's TP1 (2.80, entry 1.40) |
| 11:31 (peak so far) | 772.93 | 4.979 |

Illustrative, full-qty-at-first-TP1-print ballpark (APPROXIMATE, a conservative floor —
real strategy sells only a fraction at TP1 and lets a runner ride the same rally further,
and the proxy itself understates by ~18%): safe-3/risky-1 each ~ (2.62-1.31)×5×100 =
**+$655** vs. their actual -$65 each; safe-2 ~ (2.80-1.40)×3×100 = **+$420** vs. its actual
-$66. **Directionally: the same rally that produced +$563 to +$638 on the one leg we can
bound with real data almost certainly produced a comparable positive swing on these three
— net effect of zone-edge on wave 2 as a whole is strongly positive, not close to flat.**

**Catastrophe cap vs. zone width, wave 2:** N/A as realized — no leg reached -50% (worst
print at the stop bar was -10% to -29%). The inverse of wave 1: the raw $0.00-buffer chart
trigger fired first here because SPY's real move ($0.90-1.00 from the wave's high) was
large relative to a zero buffer, even though it never covered the $0.384 zone width either.

---

## PART B — Historical ZONE-EDGE variant (extends H5, same 79-event population)

Same population, matching, option-bar loading, catastrophe-cap/time-stop resolution,
slippage convention (close - $0.02), and bootstrap CI (4,000 resamples) as
[`structure-stop-whipsaw.md`](structure-stop-whipsaw.md) — reused by import, not
modified. New: buffer = **the trigger level's own recorded `zone_width`** instead of a
fixed constant.

### Zone-width sourcing (flagged per row in the JSON)

| Source | n | Notes |
|---|--:|---|
| `archived_same_day` (nearest `automation/state/key-levels-history/<date>/<bucket>.json` ≤ event time, matched to the trigger price within $0.10, zero ambiguous matches at this tolerance) | 21 (26.6%) | 17 events at ~$0.37-0.39 (`default_pre_ab` provenance — a near-constant default, not an observed band); 4 events (2026-08-19, one shared trigger) at $0.80 (`shelf_band_observed`) |
| `default_0.30_fallback` | 58 (73.4%) | 12 of these predate the archive's own start (2026-08-04); the other 46 have an archive directory for that date but no level within $0.10 of the recorded `trigger_level` — the live entry trigger is frequently a computed reclaim/rejection point, not one of the tracked reference/shelf levels |

**A "current file, same label" fallback was attempted and discarded**: matching an old
trigger price against TODAY's (2026-09-03) unrelated active levels by price alone
produced a spurious hit (the 2026-08-04 11:25 event at 767.48 matched today's
`INTRADAY_RTH_LOW_2026-09-03` purely by coincidence of price) on exactly the event that
turned out to dominate the top-3 concentration below. Discarded before the final run —
verified the fix does not move the population's `sum` (the honest $0.30 default and the
spurious $0.3837 match happen to produce the identical fire/no-fire outcome for that
specific event, confirmed by rerun).

### Aggregate result

| | Value |
|---|--:|
| n | 79 |
| mean Δ$ | +$51.59 (95% CI −$14.36, +$130.88) — **CI crosses zero** |
| sum Δ$ | +$4,076 (95% CI −$1,135, +$10,340) |
| helped / hurt / flat | 10 / 45 / 24 |
| **drop-best-day** (2026-08-04, +$4,917) | **−$841** |
| **top-3 concentration** | top 3 (all 2026-08-04, `SPY260804C00768000`, bold-2/risky-1/risky-3, +$1,450 each) = **106.7% of net**; excluding them: **−$274** |

Same shape as H5's `BUF-0.25`/`BUF-ATR0.5x`: a positive headline that is not statistically
distinguishable from zero on the pooled CI, flips negative on drop-best-day, and is
carried by 3 arm-replicated legs off ONE underlying SPY signal-day — the true
independent-evidence count behind the positive number is close to 1, not 79.

### Per-arm

| Arm | n | mean Δ$ | 95% CI | sum Δ$ |
|---|--:|--:|---|--:|
| bold-2 | 16 | +$122.34 | (−38.28, 344.06) | +$1,957.50 |
| risky-1 | 18 | +$72.36 | (−78.19, 278.89) | +$1,302.50 |
| risky-3 | 7 | +$136.07 | (−166.79, 607.14) | +$952.50 |
| safe-3 | 20 | +$6.97 | (−69.53, 120.00) | +$139.50 |
| **safe-2** | **18** | **−$15.33** | (−50.58, 37.08) | **−$276.00** |

No arm clears a CI that excludes zero on the positive side. safe-2 is the only arm with a
negative point estimate.

### Per-VIX regime

| Bucket | n | mean Δ$ | 95% CI | sum Δ$ |
|---|--:|--:|---|--:|
| vix<15 | 29 | −$3.43 | (−53.64, 60.45) | −$99.50 |
| **vix15-17** | **39** | **+$133.82** | **(11.15, 284.60) — CI excludes zero** | **+$5,219.00** |
| vix>17 | 11 | −$94.86 | **(−161.82, −45.05) — CI excludes zero, negative** | −$1,043.50 |

The one clean positive regime cell (vix15-17) is confirmed (via the concentrated event's
own `vix`=16.23 / `vix_from_archetype`=16.42) to be **the same 2026-08-04 cluster** driving
the top-3 concentration above, not an independent regime finding — identical to H5's own
disclosure for `BUF-0.25`'s vix15-17 cell. The only regime cell that clears significance
independently of that cluster is vix>17, and it is negative.

### The four named winning days

| Day | Exposure |
|---|---|
| 2026-08-06 | Zero `structure_stop` exits — untouched by this study, exactly as H5 found |
| 2026-08-28 | Zero `structure_stop` exits — untouched |
| **2026-08-13** | 5 legs, net **+$1,215.50** (3 call legs on `SPY260813C00776000` +$1,235 combined [bold-2/risky-1 +$475 each, safe-3 +$285], 2 put legs on `SPY260813P00776000` −$19.50 [safe-2] and $0.00 [bold-2, fired same bar as control] — consistent with H5's own 08-13 finding) |
| **2026-08-27** | 1 leg (bold-2, `SPY260827C00771000`), **−$35** |
| **Combined 08-13 + 08-27** | **+$1,180.50** |

None of these deltas would have flipped either winning day to a loss (matches H5's own
conclusion, reproduced independently under a level-sized buffer instead of a fixed one).

### Catastrophe-cap diagnostic

Under the CURRENT raw (zero-buffer) rule, none of these 79 positions ever reaches the -50%
catastrophe cap by construction — the tighter chart exit always fires first (or the
position exits some other way before -50%). Loosening the stop to each level's own
`zone_width` lets **28/79 (35.4%)** ride down into the -50% floor instead of the tighter
chart exit — a materially larger fraction than any of H5's fixed-dollar candidates
(GRACE-1BAR 10%, TWO-CLOSES 23%, BUF-0.15 18%, BUF-0.25/ATR0.5x 29-30%) because the level's
own real-world zone widths (mostly $0.37-0.39, one cluster at $0.80) are on the wider end
of what H5 tested. This is the direct, mechanical, disclosed cost side of "catching more
whipsaws": some fraction of the delayed stops are not whipsaws, and the buffer just lets a
real breakdown run further before the -50% floor finally catches it.

---

## Methodology and disclosed limitations

- **No look-ahead** in either part: Part A's structure-stop checks use only the closed 5m
  bar available at that tick (the field the live engine itself read); Part B inherits H5's
  own no-look-ahead guarantee verbatim (import, unmodified).
- **Part A's SPY tape is FACT, not a proxy**: `core-decisions.jsonl`'s `spy` field is
  bitwise-identical to the `exit_pass` legs' own `last_closed_5m_close` at every shared
  timestamp (spot-checked across both wave windows) — it is the literal input the live
  structure-stop check consulted this morning, reconstructed by dedup, not re-derived from
  a different feed.
- **The 770C wave-2 counterfactual is bounded by REAL market data**, not a model: the same
  option contract was re-held by other arms from 11:07 onward, so its actual traded price
  is known almost continuously; only the 10:36:59-11:06:xx window (no arm held it) is
  unlogged, and the first post-gap real print is used as a deliberately conservative
  (late, low) TP1 fill.
- **The 768C wave-2 counterfactual is APPROXIMATE**: Black-Scholes, r=0, constant
  calibrated sigma, no skew/smile, no rate/dividend adjustment. Cross-validated against
  770C's own real gap and found to UNDERESTIMATE by ~18% over a comparable window —
  disclosed as a one-directional (conservative) bias, not corrected for, so every 768C
  dollar figure in this report is a floor.
- **Part B's zone-width match tolerance ($0.10) was chosen for zero ambiguity**: at $0.25
  eight events already have >1 candidate level within tolerance; $0.10 was the widest
  tolerance with a single unambiguous match on every hit (tested explicitly before
  finalizing, see the tolerance-sensitivity check in this session's own working notes).
- **73.4% of the 79 events fall to the $0.30 default**, not because the archive is
  incomplete (only 12/79 predate archive coverage) but because most recorded
  `trigger_level`s do not correspond to a tracked reference/shelf level within $0.10 on
  that day's own snapshot — the live entry trigger is frequently a computed
  reclaim/rejection point. This is a disclosed, load-bearing limitation on how much of
  Part B's population is genuinely "the level's own width" vs. an arbitrary constant that
  happens to equal the task's specified default.
- **Every number is UNVERIFIED against a live re-fill** — paper/analysis-only replay of
  cached bars and archived snapshots, per this session's hard constraints (no broker or
  market-data calls were made). Part A's session is still in progress (last tick read
  2026-09-03T11:51 ET) — every "never fires" / "still open" statement is right-censored,
  not a claim about the rest of the day.
- **change_class: NONE.** No trading-path edit is proposed or licensed by this study,
  consistent with H5.
