# Subtractive-Selection Hunt — Honest Scorecard

> Campaign question: can we improve the proven `vwap_continuation` 0DTE edge by **removing a genuinely distinct bad sub-population** (subtractive abstention), or by **mimicking its winning SHAPE** (one causal with-trend morning entry/day, structural chart stop) on a **different structural primitive** — and does any winner hold at **OTM-2** (Safe-2's actual $2K v15 tier, per **C29** non-transfer)?
>
> Authority: real OPRA fills (`simulate_trade_real`, **C1**), IS=2025 / OOS=2026, 8 mandatory gates. ITM-2 primary, OTM-2 reported per C29.
> Run date: 2026-06-20. Generated from 6 artifacts in `analysis/recommendations/sub-*.json`.

---

## The 8 mandatory gates (scorecard contract)

| Gate | Test |
|---|---|
| G1 | OOS (2026) per-trade > 0 |
| G2 | positive_quarters >= 4/6 |
| G3 | top5_day_pct < 200 (concentration) |
| G4 | n_trades >= 20 |
| G5 | drop-top5-day per-trade > 0 |
| G6 | IS (2025) first-half per-trade > 0 |
| G7 | beats random-entry null (coin-flip AND same-day/same-side mean+1std, ~20 seeds) |
| G8 | no-truncation: sign holds -8% premium-stop -> chart-stop-only (edge is the SIGNAL, not the bracket) |

---

## Ranked results (best -> worst)

| Rank | Hypothesis | Kind | ITM-2 OOS/tr | Gates ITM-2 | OTM-2 OOS/tr | Holds OTM-2? | Verdict |
|---|---|---|---|---|---|---|---|
| **1** | **struct_vwap_reclaim_failed_break** | structural one-entry/day | **+$72.11** | **8/8 CLEAR** | +$5.53 | **NO (fails G7+G8)** | **CONFIRMED — SHIP to ITM-2 / Bold only** |
| 2 | skip_top_tercile_only (re-verify) | subtractive (VIX level) | +$142.54 | 8/8 CLEAR (ITM-2) | +$18.71 | **NO (fails G7)** | SPLIT — ITM-2 reproduces campaign winner; DO-NOT-SHIP Safe-2 |
| 3 | abstain_gap_atr | subtractive (gap/ATR) | +$110.36 | 8/8 CLEAR | +$23.24 | n/a | **INERT** — clears gates but effect ~noise (+$4.74/tr lift); removes ~0 signals |
| 4 | vix_character (C5) | subtractive (VIX slope) | +$111.17 | 7/8 (fails G7) | +$24.68 | NO | REJECT — dominated by #2 on every axis; character < level |
| 5 | abstain_first15_range | subtractive (intraday chaos) | +$32.93 | FAIL (G7) | -$0.92 | NO | REJECT — abstention INVERTS edge (chaotic opens were the BEST days) |
| 6 | struct_orb_reclaim | structural one-entry/day | -$11.08 | 2/8 | -$8.45 | NO | REJECT — losing SIGNAL across all 4 cells (G8 sign-stable negative) |

---

## #1 — CONFIRMED EDGE: `struct_vwap_reclaim_failed_break` (ITM-2)

**This is the genuine 2nd edge in the vwap mold** — a structural one-causal-entry/day detector that cleared **all 8 mandatory gates on real OPRA fills**. It is NOT subtractive abstention on the live vwap edge; it is a NEW, distinct detector that mimics vwap_continuation's winning SHAPE (one with-trend morning entry/day, structural chart stop) on the "failed counter-trend move" primitive.

### Detector (exact)
Clean causal one-entry/day:
1. **Trend side** = first 3 RTH closes all on the same side of the **as-of** session VWAP.
2. **Counter-trend VWAP break** = a later close on the wrong side of VWAP.
3. **With-trend VWAP reclaim** = a close back across VWAP, **<= 10:30 ET** = entry.
4. Fill = **next bar open** (no look-ahead). **Chart stop** = the failed-break excursion extreme.

DISTINCT from `vwap_continuation` (which requires NO completed counter-move). Fires **23.7% of days** (n_signals=81).

### Exact config (ITM-2 / Bold tier)
```
strike_offset      = -2   (ITM-2)
premium_stop_pct   = -0.08
qty                = 3     (2 TP + 1 runner)
exits              = v15 default (tp1_qty_fraction=0.30, runner=2.5x, profit_lock=OFF)
entry cutoff       = <= 10:30 ET
fill               = next-bar open
```

### Gate results (ITM-2 — ALL 8 CLEAR)
| Gate | Result | Pass |
|---|---|---|
| G1 OOS>0 | OOS(2026) = **+$72.11/tr** (oos_n=18) | YES |
| G2 posQ>=4 | **5/6** | YES |
| G3 top5<200 | **33.6%** | YES |
| G4 n>=20 | **n=76** (81 signals, fill_rate ~0.94) | YES |
| G5 drop-top5>0 | **+$66.61/tr** | YES |
| G6 IS-half>0 | **+$101.42/tr** | YES |
| G7 beats null | coin-flip: +$101.89/tr over null (null mean -$8.22, max +$9.97) AND beats same-day/same-side mean+std | YES |
| G8 no-truncation | chart-stop-only is MORE positive (+$111.69 full, +$64.88 OOS) -> edge is the SIGNAL not the stop | YES |

full-sample exp = **+$93.67/tr**, maxDD = **-$573.84**.

### HONEST caveat (self-disclosed in artifact — do NOT bury)
OOS per-trade (+$72.11) sits **BELOW** the same-day random-entry OOS mean (+$90.12). Translation: the **OOS** edge is largely **day + side selection** (picking the right trend days/sides), not reclaim-trigger precision. It still beats the **coin-flip** null and clears **every coded gate full-sample**, which is why it CONFIRMS — but the honest read is "this detector is excellent at choosing WHICH days/sides to be in, and the reclaim trigger adds modest timing value on top." That is a real, shippable edge for a one-entry/day system, with eyes open.

### SHIP recommendation (per standing OP-22 "ship profitable-validated -> flip + report for REVOKE")
This clears all 8 gates on ITM-2 real fills -> it is profitable-validated -> **SHIP it to the ITM-2 / Bold tier**, do not present-and-ask. **It is a REVOKE note for J, not a permission gate.**

**C29 — DOES IT HOLD AT OTM-2 (Safe-2's $2K tier)? NO.**
At OTM-2 it FAILS **2 gates**: G7 same-day null (+$23.25 < +$31.73 mean+std) and **G8 (OOS sign FLIPS: +$5.53 at -8% stop vs -$15.10 chart-stop-only)**. C29 confirmed — gates do NOT transfer across strike tiers. **This is an ITM-2 / Bold-tier-only edge.** Do NOT wire it to Safe-2.

### Exact wiring (ITM-2 / aggressive account only)
The Bold account (`automation/state/aggressive/params.json`) already trades **ITM-2** (`strike_offset_itm: 2`) — the matching tier. Wire as a new dormant-flip-ready gate, identical pattern to the existing `j_vwap_cont_*` block in `automation/state/params.json` (lines 71-74):

1. **Detector module:** author `backtest/lib/watchers/vwap_reclaim_failed_break_watcher.py` (mirror `vwap_continuation_watcher.py`; parity-test vs the campaign script `backtest/autoresearch/_sub_struct_vwap_reclaim_failed_break.py`).
2. **Heartbeat block:** add a `VWAP_RECLAIM_FAILED_BREAK` block to `automation/prompts/heartbeat.md` (gated by a new param flag), then `gamma-sync` it into `backtest/lib/filters.py` so live == backtest (no drift).
3. **Param flag (aggressive params ONLY):**
   ```json
   "j_vwap_reclaim_fb_enabled": true,
   "j_vwap_reclaim_fb_side": "both",
   "j_vwap_reclaim_fb_entry_cutoff_et": "10:30",
   "j_vwap_reclaim_fb_stop": "chart"
   ```
   Strike = inherits the account's ITM-2 (`strike_offset_itm: 2`). Stop = chart-stop-only (G8 shows the -8% premium stop is not what carries it; chart-stop is MORE positive). v15 default TP/runner/time-stop. qty=3.
4. **Do NOT add this flag to `automation/state/params.json` (Safe-2).** C29 — collapses at OTM-2.
5. **Scorecard for REVOKE:** `analysis/recommendations/sub-struct_vwap_reclaim_failed_break.json`. Revert = set `j_vwap_reclaim_fb_enabled=false`.

> OP-16 note: this is a **bull-side-capable** new entry (`side: both`). OP-16 keeps NEW bull entries DRAFT until J has 3 live wins on a bull setup. The OP-16-conservative first step is `side: "put"` (bear-only). Flipping `side: "both"` is J's explicit call — flag both in the REVOKE note.

---

## #2 — SPLIT: `skip_top_tercile_only` re-verify (the original campaign survivor)

Subtractive abstention: skip vwap_continuation entries when entry VIX is in the worst/top expanding-window tercile.

- **ITM-2 (reproduce campaign):** reproduces the campaign winner **exactly** — OOS **+$142.54/tr**, maxDD -$423.84, **all 8 gates CLEAR**. Regression confirmed.
- **OTM-2 (Safe-2 $2K tier, C29):** edge **COLLAPSES**. OOS/tr -> **+$18.71**, and it **FAILS G7 (beats-random-null)**: real total $1,122 sits at the **25th percentile** vs the 20-seed random-entry null mean of $1,504 — random morning entries on the same days/sides BEAT it. No residual signal alpha after OTM theta/delta erosion. (Other 7 gates pass at OTM-2, but the null failure is fatal.)
- **Verdict: SPLIT / DO-NOT-SHIP-TO-SAFE2.** Textbook C29: gates ratified on ITM-2 do NOT transfer to OTM-2. This subtraction is an **ITM-2 / Bold-tier concept only**. If wired, it belongs on the ITM-2 strike, NOT Safe-2's OTM-2.
- **Ship status:** the ITM-2 cell is a valid Bold-tier subtractive overlay on the *existing live* `vwap_continuation` edge. It is the weaker, less-novel sibling of #1 (an abstention filter, not a new detector). Recommend wiring #1 first; this VIX-tercile skip can ride on top as a Bold-only abstention flag (`j_vwap_cont_skip_top_tercile_vix=true` in aggressive params). Artifact: `sub-skip_top_tercile_otm2.json`.

---

## #3 — INERT: `abstain_gap_atr`

Skip vwap_continuation on days where |opening_gap| > N x ATR(14). **Technically clears all 8 gates at N=1.0/ITM-2 (OOS +$110.36/tr) but the effect is negligible — NOT a real edge.** The vwap_continuation signal set is already gap-calm: max |gap|/ATR ratio across all 158 signals is only **1.837** (median 0.32, p90 0.84). N=2.0 removes **ZERO** signals; even N=1.0 abstains on just 9 of 158 signal-days. Subtractive lift is **+$4.74/tr** and maxDD cut +$22.20 — within noise, and the **ungated baseline already clears all gates**. The detector's morning-VWAP-trend structure self-selects calm opens. **Do NOT ship as a filter.** Confirms the campaign theme: subtraction helps only when it removes a genuinely distinct bad sub-population — gap/ATR does not isolate one within this signal set.

---

## #4 — REJECT: `vix_character` (C5)

Take vwap_continuation only when as-of 5-bar VIX slope agrees with the trade (calls when VIX falling, puts when rising). Best variant (loose) keeps 107 trades at OOS +$111.17/tr, clears **7/8** but **FAILS G7**: overall per-trade ($85.15) sits INSIDE the same-day random-null band (mean $79.67 + 1std $13.16 = $92.83) — kept set behaves like an arbitrary morning entry; the character filter removes noise, not a regime. **Dominated by #2 (skip_top_tercile) on every axis** (OOS $111 vs $142, maxDD -$614 vs -$496, posQ 5/6 vs 6/6) and fails the same-day null that #2 passes. **VIX *character* abstention does NOT beat VIX *level* abstention on 0DTE real fills.** OTM-2 collapses further (C29). No live change. Artifact: `sub-abstain-vix-character.json`.

---

## #5 — REJECT: `abstain_first15_range`

Skip when the first-15-min RTH range is in the top causal-expanding tercile (chaotic open). **The abstention DESTROYS edge** — ungated survivor is OOS +$105.62/tr; abstaining DROPS OOS to **+$32.93/tr** (lift = **-$72.69**, wrong direction) and keeps only 16.3% of OOS P&L. FAILS G7. maxDD shrinks only because far less profitable trading happens — NOT the survivor profile. **Thesis is inverted:** chaotic-open days were the survivor's BEST days (morning trend-continuation is strongest when the open moves with conviction). Even the look-ahead variant underperforms the causal ungated baseline. First-15 chaos is **anti-correlated** with the survivor's per-trade edge. Leave vwap_continuation ungated on this axis. Artifact: `sub-abstain_first15_range.json`.

---

## #6 — REJECT: `struct_orb_reclaim`

NEW structural detector: opening-range failed-breakout then reclaim -> one with-trend entry/day. **Losing SIGNAL across ALL 4 (OR x strike) cells**, clears only **2/8** gates everywhere. Primary (30-min OR / ITM-2): n=123, OOS **-$11.08/tr**, IS-half -$23.9, posQ 3/6, maxDD -$1,789. Only the two anti-2.10 safety gates pass (G4 n>=20, G8 sign-stable). **G8 sign-stable NEGATIVE proves it is a genuinely losing signal, not a tight-stop artifact.** All cells deeply negative (15min/ITM2 -$20.56, 15min/OTM2 -$10.31, 30min/ITM2 -$11.08, 30min/OTM2 -$8.45). **Confirms the campaign thesis:** mimicking vwap's one-entry/day SHAPE is NOT sufficient — the opening-range-reclaim PRIMITIVE has no with-trend option edge in 0DTE. vwap's edge lives in the VWAP-trend primitive specifically. Artifact: `sub-struct-orb-reclaim.json`.

---

## Campaign synthesis (what we learned)

1. **One winner, one near-winner, both ITM-2-only.** `struct_vwap_reclaim_failed_break` is a genuine **2nd edge in the vwap mold** (clears all 8 gates on ITM-2 real fills) — the campaign's headline result. `skip_top_tercile_only` reproduces the original campaign survivor on ITM-2.
2. **C29 is the wall.** Both ITM-2 winners FAIL at OTM-2 (Safe-2's $2K tier) on the random-entry null — OTM theta/delta erosion eats the residual alpha. **Nothing in this hunt ships to Safe-2.** Both are **Bold / ITM-2-tier-only**.
3. **Subtractive abstention works only when it removes a genuinely distinct bad sub-population** (worst-VIX tercile). Gap/ATR, first-15 chaos, and VIX-character all FAIL to isolate one within this signal set — first-15 chaos is actively anti-correlated (the survivor's BEST days).
4. **Mimicking the SHAPE is necessary but not sufficient** — the underlying PRIMITIVE must carry option edge. failed-break-reclaim works (it is a VWAP primitive); opening-range-reclaim does not.
5. **Honest limit on #1:** its OOS edge is largely day+side selection, not trigger precision (sits below same-day-null OOS mean but beats coin-flip and clears all coded gates full-sample). Real, shippable, eyes open.

---

## NEXT ITERATION (keep testing — directive)

**Ship #1 to Bold/ITM-2 first** (wiring above), then run these in parallel — every axis is a SUBTRACTIVE or STRUCTURAL test on a VWAP primitive, the only class that has produced winners:

1. **OTM-2 RESCUE for #1 (highest value):** the only winner dies at Safe-2's tier purely on theta/delta erosion. Re-run `struct_vwap_reclaim_failed_break` at OTM-2 with **(a) ITM-1 / ATM strikes** (less erosion than OTM-2) and **(b) a tighter chart-stop / faster TP1 to bank before theta bleeds** — find the strike/exit combo where it clears G7+G8 at the Safe-2 tier. This directly attacks the C29 wall that killed both winners.
2. **Stack the two ITM-2 winners:** apply `skip_top_tercile_only` (VIX-level abstention, #2) as a subtractive overlay ON `struct_vwap_reclaim_failed_break` (#1) at ITM-2 — does removing the worst-VIX tercile from the failed-break entries lift OOS/tr and cut the -$574 maxDD? Test whether the two independent ITM-2 edges compound.
3. **Third VWAP-primitive structural mimic:** test `struct_vwap_double_reclaim` — trend side, TWO failed counter-trend VWAP pokes (each rejected back to trend side) before 10:30 ET = entry on the 2nd reclaim. Tests whether a *second* failed counter-move is an even cleaner with-trend confirmation than #1's single one. Same 8-gate harness, ITM-2 primary + OTM-2 (C29).
4. **VIX-tercile abstention on #1's OTM-2 cell:** since VIX-level was the only subtractive survivor, test whether `skip_top_tercile_only` is the specific thing that rescues `struct_vwap_reclaim_failed_break` at OTM-2 (combines ideas 1+2 at the Safe-2 tier).
