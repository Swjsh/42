# D3 — LOSS-SIZE: were the losers too big?

**Stamp:** 2026-09-03T11:40 ET · **Slug:** `loss-size` · **Author:** Sonnet subagent, read-only pass
**Data:** cached only, no broker/market-data calls made or needed.
**Companion JSON:** [`dissect-loss-size.json`](dissect-loss-size.json)
**Script:** `backtest/tools/dissect_loss-size.py` (rerun any time; deterministic, seed=20260903)

---

## Verdict

**Mixed, and the split is informative.** Today's four **cap-hit** losses (wave1: bold-2 −$85,
safe-3 −$270, risky-1 −$280, safe-2 −$144) *were* unusually large for their arms — 76th–93rd
percentile of severity against each arm's own losses since 2026-08-06. Today's four
**structure-stop** losses (wave2, all −$65 to −$70) were completely typical — 29th–63rd
percentile, indistinguishable from an ordinary loss.

The mechanism check confirms this split is real, not noise: during wave1's ~22-minute hold, SPY's
own tape-visible range was **0.25 points** — *below the 25th percentile of ordinary first-hour
10-minute chop* (p25 = 0.55, median = 0.73, n=988 windows/19 days) and dramatically inside every
zone width in force today (0.384–0.80) — yet the option lost 46–52% of its premium. A
Black-Scholes decomposition (implied vol calibrated to each leg's real entry price, not VIX, which
overpriced these options 2.5–3×) attributes only **16–18% of wave1's collapse to tape-visible
delta+theta**; the other **71–79% is an unexplained residual** — almost certainly real intra-bar
SPY movement invisible at 5-minute-close resolution, since VIX barely moved (15.02→14.95) so vol
crush isn't the driver either. **The −50% cap fires inside the zone for wave1 specifically, and
does so by catching something a 5-minute-close chart stop structurally cannot see in time — not
because the position needed a large SPY move to lose that much.**

Wave2 is the opposite case: tape-visible delta+theta explains 73–166% of its move (SPY genuinely
traveled 0.41 net / 0.91 range, near/above typical noise), and it exited via the **real** structure
stop — a 4-cent breach of the raw trigger price (768.00→767.96) that is *itself* inside the zone
band (767.62–768.38, half-width 0.384) rather than at the zone's true edge, and reclaimed to 769+
minutes later — the exact whipsaw pattern this morning's H5 report already found in 79 real
structure-stop exits (56%/71%/79% reclaim within 15/30/60 min).

**Neither proposed alternative clears a bar on this evidence.** (i) smaller size + wider cap shows
a promising point estimate (+$168 to +$260 vs −$644 actual, on the reducible slice) but it is
**driven almost entirely by shrinking size on the largest, worst-performing clips** (cap-hit
losers' mean qty 6.43 vs winners' 5.12 — the C31 sizing lesson reproducing itself live), not by the
wider cap itself (−70% vs −80% differ by only $92); it **flips negative when the single best day is
dropped**, costs all 4 named winning days $260–$637 each, and is **unavailable on 47% of the
cohort** (already at the rule-6 floor of 3 — including every one of today's own safe-2 legs). (ii)
zone-edge-primary chart stop cannot be swept historically at all — the zone width in force at each
past trigger isn't persisted (the exact F3 gap this morning's SYNTHESIS already named) — and the
one population-level proxy available (delta-implied SPY move at exit vs. today's observed zone
widths) shows today's wave1 mechanism does **not** generalize: only 15% of *all* historical cap-hit
losses have a delta-implied move that small; fully 50% already exceed even the widest zone (0.80),
meaning a zone-edge stop would likely have fired around the same time as the cap in half of cases,
not clearly earlier.

---

## 1. Data, population, and equity sourcing

| Source | Role |
|---|---|
| `analysis/pain-ledger/mae-mfe.json`, filtered `date >= 2026-08-06` | n=191 scored engine round trips (123 losers, 64 winners, 4 scratch), broker-truth P&L |
| `automation/state/fills-ledger.jsonl` | today's fills, cross-checked against `analysis/journal/calendar-data.json` (exact match on safe-2's two losing legs, confirms the fills reconstruction) |
| `automation/state/core-decisions.jsonl` (`account=='safe'`) | today's per-minute SPY + VIX tape |
| `analysis/quote-tape/2026-09-03.jsonl` | today's option NBBO mid tape |
| `automation/state/key-levels.json` + `key-levels-history/2026-09-03/0930.json` | zone widths (the 09:30 snapshot confirms 769.36's 0.8-wide shelf band was already in force *before* the 09:41 entry — not a post-hoc artifact) |
| `backtest/data/spy_sip_cache/spy_1m_*.json`, `spy_5m_*.json` | historical SPY 1-min/5-min bars, 19 dates ≥08-06 with cache coverage |
| `backtest/data/highres/SPY*C*_1m_*.csv` | historical option 1-min bars, 20 call-strike files ≥08-06 |
| `automation/state/fleet/{risky-1,risky-3,safe-3}/decisions.jsonl` | per-tick `equity` field, ground truth |

**Equity-by-arm-date sourcing (task asked to state the source):**
- **risky-1, safe-3:** direct — first `equity` row per ET date in the arm's own `decisions.jsonl`. Exact.
- **risky-3:** direct through 2026-08-28 15:54 ET, where the file **stops** (confirmed by tail read —
  a real outage, not a data-pull artifact; consistent with the standing memory note on quiet-hold
  outages). Dates after that are **forward-filled** from cumulative `realized_pnl` (mae-mfe.json,
  arm==risky-3) anchored at the last known real equity ($4,283.92). Labeled APPROXIMATE for those
  dates in the JSON (`_eq_flag`); this only affects risky-3's equity% column, not its $ or premium% columns.
- **safe-2, bold-2:** no `equity` field exists anywhere in `core-decisions.jsonl` (checked directly —
  absent from every row). **Reconstructed backward** from the 2026-09-03 SOD equity anchors given in
  this task (safe-2 $5,653.81, bold-2 $5,593.52) using `analysis/journal/calendar-data.json`'s
  fee-adjusted daily `pnl_net` per date, walking `SOD(d) = SOD(d_next) - pnl_net(d_next)`. This is
  exact, not approximate, **because 0DTE closes flat every session** (Rule: "all flat by EOD") — there
  is no overnight equity carry to miss, so the only way this reconstruction could be wrong is a
  non-engine cash flow (deposit/withdrawal) mid-window, none of which is evidenced in the data touched.
- safe-1 has zero trades since 2026-06-26 (retired arm) — excluded, not part of this population.

---

## 2. Loss distribution since 2026-08-06 — three units, per arm

n=123 losers. Bootstrap 95% CIs on the mean, 3,000 resamples, in the JSON (`loss_distribution`).

| Arm | n | $ mean | $ median | $ p90 | prem% mean | prem% median | eq% mean | eq% median |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **BOOK** | 123 | −$106.70 | −$80.00 | −$24.00 | −25.5% | −20.4% | −2.005% | −1.563% |
| bold-2 | 19 | −$130.95 | −$105.00 | −$31.00 | −32.6% | −33.3% | −2.491% | −1.984% |
| risky-1 | 27 | −$123.44 | −$85.00 | −$20.00 | −23.6% | −18.7% | −2.215% | −1.617% |
| risky-3 | 29 | −$90.55 | −$80.00 | −$50.00 | −22.8% | −22.7% | −1.831% | −1.696% |
| safe-2 | 30 | −$81.60 | −$57.00 | −$23.40 | −25.0% | −18.1% | −1.476% | −1.050% |
| safe-3 | 18 | −$123.83 | −$64.50 | −$21.30 | −25.7% | −22.2% | −2.341% | −1.309% |

Full p10/p25/p75/p95/min/max per arm/unit in the JSON.

### Today's 8 losing legs, placed on each arm's PRIOR (pre-09-03) loss distribution

Severity percentile: 100 = the single worst prior loss for that arm since 08-06, 0 = the mildest,
mid-rank on ties. "book$ pctile" = same, pooled across all arms' prior losers (n=115).

| Leg | $ | prem% | eq% | arm-$ pctile | arm-prem% pctile | arm-eq% pctile | book-$ pctile | n prior (arm) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **wave1** risky-1 | −$280.00 | −51.9% | −4.554% | **89** | 89 | 89 | **93** | 27 |
| **wave1** safe-3 | −$270.00 | −48.6% | −4.788% | **83** | 89 | 83 | **93** | 18 |
| **wave1** safe-2 | −$144.00 | −49.0% | −2.547% | **83** | 87 | 80 | **76** | 30 |
| **wave1** bold-2 | −$85.00 | −45.9% | −1.520% | 39 | 68 | 37 | 54 | 19 |
| wave2 bold-2 | −$70.00 | −29.2% | −1.251% | 29 | 42 | 32 | 43 | 19 |
| wave2 safe-2 | −$66.00 | −15.7% | −1.167% | 57 | 40 | 57 | 41 | 30 |
| wave2 safe-3 | −$65.00 | −9.9% | −1.153% | 50 | 17 | 33 | 41 | 18 |
| wave2 risky-1 | −$65.00 | −9.9% | −1.057% | 37 | 30 | 33 | 41 | 27 |

**Read:** three of wave1's four legs sit at the 76th–93rd percentile of severity for their own arm
— genuinely large losses, not ordinary ones (bold-2's wave1 leg is the exception, mid-pack at the
39th–54th percentile, because bold-2's own loss distribution runs bigger on average — its book-wide
mean loss is already −$130.95, the largest of any arm). Every wave2 leg sits within the 29th–63rd
percentile band — unremarkable by this arm's own history. Today's total −$1,045 across these 8 legs
matches the SYNTHESIS trigger quote exactly (cross-check).

---

## 3. Mechanism — delta, the −50% cap, and the zone

### 3a. Delta: three independent estimates, one is unreliable

1. **Empirical, today's quote-tape vs SPY tape — REJECTED.** `core-decisions.jsonl`'s `spy` field is
   a 5-minute-bar-close series repeated across the per-minute log (confirmed: 5 consecutive identical
   SPY values, e.g. 769.79 at 09:46–09:50, while option mid genuinely swings 0.705–1.125 within that
   *same* repeated-SPY window). An OLS slope against this tape (1.66, 0.32) is dominated by real
   intra-bar SPY moves the coarse tape can't see, not a valid delta. Disclosed and not used further.
2. **Black-Scholes, VIX-based sigma — REJECTED as miscalibrated.** `sigma=VIX/100` prices these 0DTE
   near-ATM calls at $1.87–$2.92 against real entry premiums of $0.37–$1.40 (2.5–3× over). Backing
   out implied vol from the real entry price gives **5.8%–6.7%**, a fraction of the day's 15.0% VIX —
   the standard 0DTE-discount-to-VIX effect, but too large a gap to trust VIX-sigma deltas directly.
3. **Black-Scholes, implied-vol-calibrated — used as the entry-tick delta.** Deltas: 0.22 (bold-2's
   772C, 2.3pts OTM) to 0.55 (768C legs, near-ATM). **-50% cap implies SPY moves of 0.84–1.27 points**
   at these deltas — i.e. if the loss had been purely delta-driven, SPY would have needed to travel
   *farther than even the widest zone (0.80)* to produce it.
4. **Historical empirical, cached 1-min option bars vs cached 1-min SPY bars, near-ATM calls entered
   09:40–10:20, since 08-06 — the trusted cross-check.** n=19 days (every date with both caches
   available), regression R² 0.76–0.99 (median 0.90+). **Mean delta 0.501, median 0.501, stdev
   0.088.** This matches the implied-vol-calibrated delta for today's near-ATM (K=770/768) legs well
   (0.46–0.55) and confirms the ATM-0DTE-call-delta-≈0.5 prior independently of any vol assumption.

### 3b. What actually happened: BS decomposition (theta vs tape-visible delta vs residual)

Using implied vol calibrated to each leg's real entry price (so the model matches reality at t=0 by
construction), then re-pricing at the tape-visible SPY move + elapsed time:

| Leg | theta effect | tape-delta effect | **residual** | actual move | residual % |
|---|---:|---:|---:|---:|---:|
| bold-2 wave1 | −$0.018 | −$0.030 | **−$0.121** | −$0.170 | 71% |
| safe-3 wave1 | −$0.031 | −$0.088 | **−$0.420** | −$0.540 | 78% |
| risky-1 wave1 | −$0.032 | −$0.088 | **−$0.440** | −$0.560 | 79% |
| safe-2 wave1 | −$0.032 | −$0.087 | **−$0.360** | −$0.480 | 75% |
| bold-2 wave2 | −$0.027 | −$0.102 | +$0.010 | −$0.140 | −7% |
| safe-2 wave2 | −$0.035 | −$0.214 | +$0.030 | −$0.220 | −14% |
| safe-3 wave2 | −$0.033 | −$0.215 | +$0.118 | −$0.130 | −91% |
| risky-1 wave2 | −$0.033 | −$0.215 | +$0.118 | −$0.130 | −91% |
| **Pooled (n=8)** | −$0.243 (10%) | −$1.041 (44%) | **−$1.086 (46%)** | −$2.370 | |

**Wave1: 71–79% of the collapse is unexplained by tape-visible delta+theta.** Since VIX barely moved
(15.02→14.95, ruling out vol crush), the residual is almost certainly real SPY movement inside the
5-minute bars the coarse tape can't resolve — the option-side quote tape (~1-min/20-sec cadence)
caught it; the 5-minute-close-sampled SPY series and any chart stop keyed to 5m closes structurally
cannot react to it within the same bar.

**Wave2: tape-visible delta alone over- or fully explains the move** (73–166% before residual, which
runs *positive*, i.e. the option held up slightly better than the tape-visible move implies) —
consistent with wave2 being a genuine, visible SPY-driven move that ended in the real structure stop.

### 3c. Comparing to the zone and to typical noise

- **Zone widths in force:** 769.36 (wave1 trigger) — 0.80 half-width shelf band [768.56, 770.16],
  **confirmed already in force at the 09:30 snapshot**, before the 09:41 entry (not a post-hoc read).
  768.00 (wave2 trigger) — 0.384 half-width intraday-marker band [767.62, 768.38] (11:38 snapshot;
  no intraday archive exists between 09:30 and 10:16 to pin the exact in-force value at 10:16, but
  this class of level is computed from static session data and is stable intraday — disclosed as the
  best-available read, not a verified point-in-time snapshot).
- **Typical 10-min SPY noise, first hour, since 08-06:** n=988 rolling 10-minute windows across 19
  cached days — mean 0.809, median 0.730, p25 0.550, p90 1.380. **A zone's half-width (0.384–0.80) is
  roughly the same size as ordinary 10-minute chop, not meaningfully wider than it.**
- **Today's actual tape-visible range:** wave1 (09:41–10:03, 22 min) = **0.250** (net −0.195) — below
  the 25th percentile of ordinary first-hour 10-min noise. wave2 (10:16–10:37, 21 min) = **0.910**
  (net −0.410) — between the 75th and 90th percentile, a genuinely larger, visible move.

**Conclusion: the cap fires inside the zone for wave1, decisively — SPY was unusually calm by its
own recent-history standard while the option lost half its value.** This is not a distance-to-zone-
edge story; the BS decomposition (3b) shows why: most of wave1's loss is a residual the coarse tape
can't attribute to visible SPY movement at all. Wave2, in contrast, is a real SPY-driven move that
correctly tripped the structure stop — but at the **raw trigger price** (768.00, breached by 4 cents
to 767.96), which sits *inside* the zone band [767.62, 768.38] rather than at its outer edge, and
reclaimed to 769+ afterward — the exact whipsaw pattern H5 already quantified in 79 real structure-
stop exits this morning (56%/71%/79% reclaim within 15/30/60 min; buffer variants don't fix it and
owe 97–117% of their apparent gains to 3/79 positions).

### 3d. Does wave1's mechanism generalize? Population-level check (APPROXIMATE)

Using the trusted historical delta (0.501, §3a.4) to translate every loser's realized %-loss into an
implied SPY-point move, bucketed against today's two observed zone widths (0.384, 0.80):

| Population | inside narrow (0.384) | between | exceeds wide (0.80) |
|---|---:|---:|---:|
| **All 123 losers since 08-06** | 72 (59%) | 32 (26%) | 19 (15%) |
| **Cap-hit only (current −50% cohort, n=20)** | 3 (15%) | 7 (35%) | **10 (50%)** |

Most losses of any kind (59%) correspond to a delta-implied move smaller than even the narrowest
zone — consistent with §3c's "zone ≈ typical noise" finding generally. But **cap-hit losses
specifically skew larger**: half of them already imply a SPY move exceeding even the widest zone. **So
today's wave1 is not the typical cap-hit case** — it is an outlier where the visible SPY move was
tiny; the *typical* historical cap-hit loss corresponds to a larger implied move that a zone-edge
stop would plausibly have caught around the same time, not clearly earlier. This bucketing uses a
single population-average delta (0.501, measured on genuinely-ATM 09:40–10:20 entries) applied to
losers at all times of day and moneyness — disclosed APPROXIMATE, biased toward understating the
implied move for more-OTM losers (lower true delta than 0.501).

---

## 4. Alternative (i): smaller size + wider premium stop, same $ risk

**Methodology and its hard limit:** widening the cap for trades that were *actually* stopped at −50%
cannot be tested from this ledger — `mae_pct` is walked only through the position's real final-exit
bar (per the frozen `PREREG-2026-08-01.md` convention), so nothing is known about what a real −50%-
cap-hit trade's price would have done afterward. This is **right-censoring**, not a gap that can be
closed by assumption. What follows separates the two effects honestly: the pure size-down effect
(fully computable, no censoring) and the wider-cap effect (computable only on trades that never
actually hit −50%, where the full realized window is uncensored).

**Cohort:** current −50% cap, since 08-06, n=139. **73 reducible** (qty>3, can shrink to the rule-6
floor of 3). **66 already at the floor (47%)** — alternative (i) has **no room to operate** on
these without accepting *more* $ risk than today, not less. **Every one of today's 4 safe-2/wave
legs and both safe-2 losing legs today used qty=3** — this alternative is structurally unavailable
for safe-2 at its current sizing.

Reducible population by real outcome: 24 winners, 33 structure/time losers, 14 cap-hit (right-
censored), 2 scratch.

| Candidate | n | actual $ (full size) | size-only $ (floor-3, cap unchanged) | size-only + wider-cap-where-computable | 95% CI | 4 winning days (Δ vs actual) | drop-best-day |
|---|---:|---:|---:|---:|---|---|---:|
| **−70%** | 73 | −$644.00 | +$260.25 | **+$168.15** | [−$1,956, +$2,430] | 08-06 −$637, 08-13 −$260, 08-27 −$417, 08-28 −$378 | **−$457.05** |
| **−80%** | 73 | −$644.00 | +$260.25 | **+$260.25** | [−$1,836, +$2,588] | same | **−$364.95** |

**The apparent flip from −$644 to positive is driven almost entirely by the size cut, not the wider
cap** (−70% and −80% differ by only $92; 0–1 non-cap-hit trades ever newly breach a wider threshold).
The size cut works because **cap-hit losers carry more size than winners** — mean qty 6.43 (2 of 14
at qty=8, 2 at qty=12) vs winners' mean qty 5.12 (23 of 24 at exactly qty=5) — the live engine's own
recent history is reproducing CLAUDE.md's own C31 lesson ("killer is sizing-up/adding, not flat
count") in real time.

**This point estimate is not robust.** The 95% CI is enormous and straddles zero by a wide margin
(n=73 is thin). **Dropping the single best day (08-27, +$625 of the total) flips both candidates
negative** (−$457 / −$365). And it costs real money on every one of the 4 named winning days
(−$260 to −$637 each — winners at qty 5–8 get cut to 3, shrinking their dollar payout proportionally
even though none of them were ever near the cap). **The 14 right-censored cap-hit trades are held at
their real dollar-per-contract outcome, scaled only by size** — a neutral, not optimistic, assumption;
if a wider stop would have let some of them keep bleeding toward −70%/−80% before their own natural
exit (which this data cannot rule out either way), the true number is worse than shown.

---

## 5. Alternative (ii): same size, zone-edge chart stop primary, cap as backstop only

**Cannot be swept historically with rigor.** The zone width actually in force at each historical
trigger is not persisted anywhere in this repo's ledgers — this is the exact **F3 gap** this
morning's SYNTHESIS.md already flagged ("persist the zone width in force per trigger... forward
≥20 sessions"). Fabricating a per-trade historical zone width would violate the no-fabricated-data
rule; it is not attempted here.

What the evidence *does* support, without extending beyond what's known:

- **Today's worked example (§3c) is real, not fabricated**, and shows wave1 would plausibly have
  survived a genuine zone-edge stop (SPY's actual range, 0.25 pts, never approached the 0.80-wide
  zone's outer edge) — but §3d shows this specific pattern (tiny visible SPY move, large %-loss) is
  **not the typical cap-hit case historically** (only 15% of cap-hit losses share it; half already
  imply a move past even the widest zone, where a zone-edge stop would plausibly fire around the same
  time as the cap, not clearly earlier).
- **The realized structure stop, as currently implemented, already fires on the raw trigger price
  breach, not the zone's outer edge** — today's wave2 exit (768.00 vs close 767.96) is a 4-cent
  breach *inside* the 0.384-wide zone band, not at its edge. This is precisely the exit shape H5
  studied this morning across 79 real structure-stop exits and found whipsaw-prone (56/71/79%
  reclaim within 15/30/60 min) with **no buffer variant that survives drop-best-day** (the two
  buffer variants with positive headlines owe 97–117% of their total to 3 of 79 positions). Moving
  the structure stop to a genuine zone edge is the same class of change H5 already tested and could
  not validate — this report adds the mechanism explanation (§3c) for *why* it fires early, but does
  not overturn H5's population-level refutation.

**Net read: alternative (ii) is not supported by today's specific mechanism generalizing, and the
version of it already tested this morning (buffered structure stops) failed on its own population.**
A rigorous test of "true zone-edge stop, cap as pure backstop" requires the F3 instrument (persist
zone width per trigger going forward) before it can be evaluated at all — this is a forward
instrument to build, not a historical claim to make today.

---

## 6. Caveats & limitations

- **Right-censoring (§4):** cap-hit trades' fate under a wider stop is fundamentally unknowable from
  this ledger. Any number describing "wider cap" effects excludes this population and is disclosed
  as such at every table above — do not read the +$168/+$260 point estimates as "proven safe."
- **F3 gap (§5):** no historical per-trigger zone width exists; alternative (ii) cannot be swept.
- **Today's SPY tape resolution (§3a.1):** `core-decisions.jsonl`'s `spy` field is a 5-minute-close
  series, not true 1-minute ticks — confirmed by the repeated-value pattern. This is why the BS/
  historical-delta route (not the naive quote-tape regression) is the trusted mechanism read, and why
  the "residual" in §3b cannot be split further into "real intra-bar SPY move" vs "IV change" without
  tick-level SPY data this task is not permitted to fetch.
- **Population-average delta (§3d):** 0.501 is measured on genuinely-ATM 09:40–10:20 entries only;
  applying it to all losers (any time of day, any moneyness) is an approximation, disclosed to bias
  toward *understating* the implied move for more-OTM losers.
- **Small-n tails:** cap-hit-only bucketing (n=20) and per-arm today's-leg percentiles (n_prior 18–30)
  are thin; treat as directional, not conclusive, consistent with the rest of this money-leak audit's
  standing caveat that the book (n=239 current-cap cohort per this morning's H8) is not yet
  distinguishable from breakeven.
- **No live rule change proposed or made.** Config freeze in force until 2026-10-30; this is a
  read-only analysis, consistent with the standing recommendation in `loss-size-math.md` (H8, this
  morning) that any future stop-width work needs a pre-registered regime classifier, not a bare
  width sweep in either direction.
