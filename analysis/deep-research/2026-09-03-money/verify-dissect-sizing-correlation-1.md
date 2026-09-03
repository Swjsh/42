# VERIFY — dissect-sizing-correlation (D6 sizing/correlation), pass 1

Stamp: 2026-09-03T11:50 ET (`et_clock.py`, verified fresh this session). Sonnet, read-only,
no broker/market-data/network calls. Skeptic pass against
[`dissect-sizing-correlation.md`](dissect-sizing-correlation.md) /
[`.json`](dissect-sizing-correlation.json) and its tool
(`backtest/tools/dissect_sizing-correlation.py` + `-part2.py` + `-part3.py`).

**Verdict: NOT REFUTED on its core numeric claims — independently reproduced bit-exact.
One real gap found and closed: the flat-3 counterfactual, when actually checked against the
four named winning days + today's 11:06 wave (as the report's own `kills_winners` field flagged
as unverified), comes back UNAMBIGUOUSLY NEGATIVE on all five — the report's headline "+$320
net positive, +31%" is not robust and flips to −$389 when just 3 outlier trades are excluded.**
This does not overturn the finding's SUPPORTED verdict (that book was never a validated proposal
and is already labeled "not shippable"/APPROXIMATE) but it substantially sharpens the caution and
should be surfaced, not left as an unresolved question mark.

---

## 1. Independent reproduction — every FACT-labeled number checks out exactly

Wrote a fresh FIFO matcher from scratch (different code, same ledger) against
`automation/state/fills-ledger.jsonl` (979 option/engine rows, 564 matched legs, 0 unmatched
sells). Results, compared to the report:

| Claim | Report | My independent recompute | Match |
|---|---|---|---|
| Today's book trough | −$1,045.00 @ 10:37:07.812088 ET | −$1,045.00 @ 10:37:07.812088 ET | **exact** |
| Today's book final (11:34 read) | +$836.00 | +$836.00 | **exact** |
| Per-arm trough: safe-2/bold-2/safe-3/risky-1 | −210/−155/−335/−345 | −210/−155/−335/−345 | **exact** |
| Wave 1 loss (09:41-10:03) | −$779.00 | −$779.00 (bold-2 −85, safe-3 −270, risky-1 −280, safe-2 −144) | **exact** |
| Wave 2 loss (10:16-10:37) | −$266.00 | −$266.00 (safe-2 −66, bold-2 −70, safe-3 −65, risky-1 −65) | **exact** |
| Per-day per-arm table since 08-06 (19 rows × 5 arms) | see Table 1 | identical to the dollar, all 95 cells | **exact** |
| Correlation matrix (5×5) | rho matrix in §2 | identical to 3 decimals, every cell | **exact** |
| Avg pairwise rho / effective N | 0.489 / 1.692 | 0.489 / 1.692 | **exact** |
| Rule 6 % / kill-switch % on the 5 sized positions in §4 | table | recomputed from raw fills, matches every % | **exact** |
| H10 design-note correlation (0.30 / 0.50 zone) | 0.736 / 0.950 | 0.736 / 0.950 (recomputed from `retest-entry-variant-walked*.json` day-sums) | **exact** |
| H8 citations (`structure_or_time_loss` 50.6%, `cap_hit` 13.4%, 79.1%) | quoted | confirmed verbatim in `loss-size-math.md` lines 95-102 | **exact** |
| Doctrine citations (`min_contracts=3/5`, `max_contracts_per_entry=5`, `daily_loss_kill_switch_pct` 0.30/0.50, `-$400`/arm stop) | quoted | confirmed verbatim in `automation/state/params.json` + `aggressive/params.json` | **exact** |

Nothing in the "FACT" bucket is fabricated, mis-transcribed, or stale beyond what the report
itself already disclosed (the 11:40 ET snapshot caveat). The method (FIFO per (arm,symbol),
`is_option=true AND attribution=='engine'`, safe globally because 0DTE symbols self-encode
expiry) is sound and I'd use the identical approach.

---

## 2. WINNER-KILLER / CONCENTRATION lens — the flat-3 counterfactual against the 4 named days + today's 11:06 wave

The report's own `kills_winners` field already named this exact gap: *"the flat-3 counterfactual,
if it were ever proposed, would need to be checked against 08-13/08-27/08-28 specifically... this
was not separately verified per-day in this pass."* I ran it (all 4 named winning days + this
morning's own 11:06-11:07 recovery wave, same linear-scaling method as the original tool's
`_part2.py`):

| Day / wave | Actual $ | Flat-3 $ | Δ | Δ as % of actual |
|---|---:|---:|---:|---:|
| **08-06** | +1,465.00 | +827.85 | **−637.15** | −43.5% |
| **08-13** | +1,748.00 | +1,270.40 | **−477.60** | −27.3% |
| **08-27** | +1,897.00 | +1,536.20 | **−360.80** | −19.0% |
| **08-28** | +1,304.00 | +1,155.40 | **−148.60** | −11.4% |
| **Sum, 4 named days** | +6,414.00 | +4,789.85 | **−1,624.15** | −25.3% |
| **Today's 11:06-11:07 wave** (the wave that recovered the −$1,045 trough) | +1,049.00 | +629.40 | **−419.60** | −40.0% |

**Every single one of the five benchmarks the lens asked about is hurt, by double digits.** This
directly answers the "would the proposed change have hurt 08-06/08-13/08-27/08-28 or today's
11:06 wave" question with a clean **yes, materially, on all five** — the report's own population-
level framing ("book total actual $1,040 vs counterfactual $1,360, +$320/+31%") never surfaces this
because those four winning days already sit inside the wider 20-day sample it's averaging over,
diluted by 08-07 (see below).

### 2a. The report's own "+$320 net positive" headline is not robust — it inverts under a 3-trade exclusion

Drilling into *why* the book-level flat-3 delta reads positive despite hurting every named winning
day: safe-3's +$577 arm-level delta (the single biggest driver of the book's net positive) is
**122.9% concentrated in its top 3 entries**:

| Date | Symbol | Qty | Actual $ | Flat-3 Δ | % of safe-3's total delta |
|---|---|---:|---:|---:|---:|
| 08-07 | 773C | 8 | −488 | +305 | 52.9% |
| 08-07 | 772C | 8 | −384 | +240 | 41.6% |
| 08-14 | 778C | 7 | −287 | +164 | 28.4% |

All three are **losing-day, oversized (qty 7-8) entries from BEFORE the current
`max_contracts_per_entry=5` cap was ratified (2026-08-29)** — i.e., they are a pre-ladder-freeze
artifact, not something the current 5-contract regime could reproduce. Today's own two safe-3
winning legs (11:07 wave, qty 5) contribute **−$376** to the same delta (flat-3 would have cut
them), partially offsetting the three drivers above.

Removing just those top-3 entries and recomputing the **whole book's** flat-3 delta:

| | Actual $ | Flat-3 $ | Δ |
|---|---:|---:|---:|
| Full book (222 entries, as reported) | 1,040.00 | 1,360.15 | **+320.15** |
| Book excl. top-3 safe-3 drivers (219 entries) | 2,199.00 | 1,810.15 | **−388.85** |

**The sign flips.** A "net positive" conclusion carried by 3 of 222 entries (1.4% of the
population), all from before the current sizing regime existed, is not a result that should be
read as "flat-3 nets positive" in any form — even a hedged one. The report already labels this
section "not a shippable result" with "no bootstrap CI" and a disclosed directional bias, which is
honest, but it stops short of running the exact check its own caveat calls for, and the actual
check comes back considerably worse than the "small, mixed, sign-uncertain" framing suggests: it's
not mixed-and-uncertain, it's **negative on every named benchmark and inverts on a 3-trade
exclusion**. I'd upgrade the report's own caveat from "not shippable" to "actively misleading if
read as directionally positive."

---

## 3. Correlation/effective-N robustness — concentration-checked, VIX-banded

### 3a. Remove top-3 |book P&L| days and recompute

| Days removed | n remaining | avg pairwise rho | effective N |
|---|---:|---:|---:|
| none (as reported) | 19 | 0.489 | 1.692 |
| top-1 (08-07, −$2,687) | 18 | 0.440 | 1.811 |
| top-2 (+08-27, +$1,897) | 17 | 0.442 | 1.808 |
| top-3 (+08-14, −$1,837) | 16 | **0.381** | **1.981** |
| top-5 (+08-13, +08-06) | 14 | **0.219** | **2.664** |

The point estimate does move — dropping the single worst day (08-07) alone knocks rho from 0.489
to 0.440, and dropping the 5 most extreme days nearly doubles the effective-independent-bets count
(1.69 → 2.66). rho=0.381 still sits inside the report's own bootstrap 95% CI [0.301, 0.633], so
this isn't a contradiction of a stated interval — but it does show the "1.4-2.3 independent bets"
framing leans on a handful of outlier days, mostly one very bad one (08-07, every arm red
simultaneously). Also checked: dropping the highest-correlated pair (risky-1/safe-3, r=+0.895)
and recomputing on the remaining 3 arms (bold-2, risky-1... wait, correctly: bold-2, safe-2, plus
risky-1 or safe-3 alone) still gives rho≈0.67 — the correlation is not solely an artifact of that
one pair either; it's broad-based.

### 3b. VIX-band split

Pulled per-day VIX from `core-decisions.jsonl` + fleet `decisions.jsonl` (54 files scanned,
19/19 days covered, 742-774 readings/day). Result the report doesn't mention:

**The entire 19-day sample sits inside a 1.45-point VIX band (14.46-15.91) — one calm regime,
no elevated-VIX day in the population at all.** Splitting at the median (15.32):

| | n days | avg pairwise rho | effective N |
|---|---:|---:|---:|
| Low-VIX half (<15.32) | 9 | 0.517 | 1.630 |
| High-VIX half (≥15.32) | 10 | 0.445 | 1.799 |

Both halves land close to the full-sample 0.489 — no VIX-conditional correlation effect inside
this narrow band, so the correlation finding is internally consistent. But the report presents
"5 arms trade like 1.4-2.3 independent bets" without flagging that **this has never been tested in
an actual elevated-VIX regime** (this project's own memory log flags "calm regime, no null" as a
standing, unresolved limitation — `project_full_audit_2026_09_01_decisions.md`). Worth a one-line
caveat addition to the living report; not a refutation of what was measured, only of how far it
generalizes.

---

## 4. Other checks (no issues found)

- `min_contracts`/`max_contracts_per_entry` doctrine citations verified verbatim in
  `automation/state/params.json` (safe path) and `aggressive/params.json` (bold path) — confirmed
  bold-2's own live floor is `min_contracts=5` (not 3), which the flat-3 counterfactual silently
  overrides for bold-2 too. Minor footnote only, since the report never proposes shipping this — it
  does mean "flat-3-everywhere" as modeled isn't even a coherent single-knob policy change (it
  would require lowering bold-2's separately-validated floor, not just capping a ceiling).
- H8 loss-taxonomy citations (`structure_or_time_loss` 50.6%/-0.37R, `cap_hit` 13.4%/-1.05R, "121
  (79.1%) already exit earlier") verified verbatim in `loss-size-math.md` lines 95-102.
- PREREG-TIGHT-LADDER's own 382-trade evidence table (−$200/−$400/−$600 stop tiers, loss-count
  throttle net −$306) verified verbatim in `automation/state/params.json`'s inline doc comment for
  `daily_loss_kill_switch_dollars`.
- H10 design-note fidelity caveat ("SIGN-ONLY except safe-2") verified verbatim in
  `retest-entry-variant.md`/`.json`; its correlation numbers (0.736 / 0.950) independently
  recomputed from the raw walked JSON files and match to 3 decimals.
- No trading-path files were touched; only read. No new files outside the allowed
  `analysis/deep-research/2026-09-03-money/` path plus scratch scripts under this session's
  scratchpad (not committed, not under `backtest/tools/`, since this is a verify pass not a new
  dissect task).

---

## 5. What should change in the living report

1. **§4 flat-3 counterfactual**: add the per-named-day and today's-wave breakdown above (§2 here)
   — the current text says "sign is not uniform across arms" but the correct, sharper statement is
   "sign is negative on every one of the four named benchmark winning days and on today's own
   recovery wave, and the book-level positive figure inverts on excluding 3 outlier legs." This is
   a materially different message from "small, mixed effect."
2. **§2 correlation section**: add a one-line caveat that the 19-day sample spans a single
   1.45-point VIX band (14.46-15.91) — the correlation/effective-N finding is untested outside a
   calm regime.
3. Everything else in the report stands as verified.

## Caveats on this verification itself

- All figures here are computed fresh from the same on-disk ledgers the original report used
  (`fills-ledger.jsonl`, `core-decisions.jsonl`, fleet `decisions.jsonl`, `retest-entry-variant-
  walked*.json`) — no network/broker calls, market still open, so anything stamped "today" is
  frozen at this session's own read (same 11:34 ET last-fill snapshot as the original report; I did
  not re-poll the ledger a second time after my first read).
- The flat-3 counterfactual (both the original report's and mine) inherits the same disclosed
  linear-scaling bias (ignores the TP1-split nonlinearity between qty-3 and qty-5 exits) — my
  finding that the sign flips under a 3-trade exclusion does not fix that bias, it just shows the
  reported point estimate is fragile *in addition to* being biased.
- I did not re-derive the wave-2 "5m close 767.96 vs trigger 768.00" structure-stop mechanism from
  raw core-decisions.jsonl bar data (out of scope for this lens; the dollar amounts that depend on
  it were independently reproduced regardless of the stated mechanism).
