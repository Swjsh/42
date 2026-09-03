# VERIFY — dissect-wave-autopsy.md (REPRODUCTION lens, pass 2)

**Verdict on the finding: NOT REFUTED (SUPPORTED, independently confirmed).**
**Confidence: high.**

**Method:** rebuilt the wave map, every P&L figure, every entry feature, the wave-2
zone-edge doctrine-gap claim, and the population comparison stats **from the primary
ledgers directly** (`automation/state/fills-ledger.jsonl`, `automation/state/core-decisions.jsonl`,
`automation/state/fleet/{safe-3,risky-1}/decisions.jsonl`, `automation/state/key-levels.json`,
`analysis/deep-research/2026-09-03-money/entry-location-rows.json`) — **not** by reading the
original script's scratchpad copies (`{SCRATCH}/core-decisions-today.jsonl` etc.), which live
in a different agent session's temp directory this session cannot access. This is a genuine
independent rebuild, not a re-run of the same code against the same cached inputs.
Script: [`backtest/tools/dissect_verify_wave-autopsy_2.py`](../../../backtest/tools/dissect_verify_wave-autopsy_2.py)
(full stdout below each section). Read-only throughout; no network; no trading-path or
generated-surface file touched.

---

## 1. P&L — rebuilt from `fills-ledger.jsonl` alone, independent of `core-decisions.jsonl`

Grouped fills by (arm, wave time-window), matched buy-qty to sell-qty, computed
`(sell_proceeds - buy_cost) * 100`:

| Wave | Arm | Buy qty | Avg entry | Sell qty | Rebuilt P&L | Report P&L | Match |
|---|---|---:|---:|---:|---:|---:|---|
| 1 | safe-2 | 3 | 0.98 | 3 | −$144.00 | −$144.00 | ✅ |
| 1 | bold-2 | 5 | 0.37 | 5 | −$85.00 | −$85.00 | ✅ |
| 1 | safe-3 | 5 | 1.11 | 5 | −$270.00 | −$270.00 | ✅ |
| 1 | risky-1 | 5 | 1.08 | 5 | −$280.00 | −$280.00 | ✅ |
| 2 | safe-2 | 3 | 1.40 | 3 | −$66.00 | −$66.00 | ✅ |
| 2 | bold-2 | 5 | 0.48 | 5 | −$70.00 | −$70.00 | ✅ |
| 2 | safe-3 | 5 | 1.31 | 5 | −$65.00 | −$65.00 | ✅ |
| 2 | risky-1 | 5 | 1.31 | 5 | −$65.00 | −$65.00 | ✅ |
| 3 | bold-2 | 5 | 0.37 | 5 | +$199.00 | +$199.00 | ✅ |
| 3 | safe-3 | 5 | 1.17 | 5 | +$507.00 | +$507.00 | ✅ |
| 3 | risky-1 | 5 | 1.18 | 5 | +$343.00 | +$343.00 | ✅ |

**Wave totals:** wave1 −$779.00 ✅, wave2 −$266.00 ✅, wave3 +$1,049.00 ✅.
**3-wave net: +$4.00 ✅** — matches the report exactly, computed from raw qty×price
arithmetic on the broker-truth fills ledger, no dependency on the original script at all.

Also confirmed from the raw fills scan: **35 option fills today, buys=15, sells=20** — the
report's 3-wave scope covers 26 of those 35 fills; the remaining 9 (two 772C buys at
11:22:07/08, four sells 11:27–11:34 on that leg, plus a 774C buy/sell 11:27–11:34) belong to a
**wave 4** with a *different* trigger_level (771.88, vs wave3's 769.36) and a different shared
`core_tick_id` (11:21:02.58 vs wave3's 11:06:02.74) — confirming the report's own footnote that
a 4th wave was already in flight and correctly excluded from the 3-wave scope, not silently
dropped.

## 2. Entry features — rebuilt independently from `core-decisions.jsonl`

`range_position` (session-so-far), recomputed from the `safe`-account per-minute SPY tape
(146 ticks today, 09:30:06–11:55:05):

| Wave | Entry ts | SPY | Session hi/lo | n ticks | Rebuilt rp | Report rp | Match |
|---|---|---:|---|---:|---:|---:|---|
| 1 | 09:41:03 | 769.735 | 769.735 / 765.13 | 12 | 1.0000 | 1.0000 | ✅ |
| 2 | 10:16:03 | 768.37 | 769.79 / 765.13 | 47 | 0.6953 | 0.6953 | ✅ |
| 3 | 11:06:04 | 770.445 | 770.445 / 765.13 | 97 | 1.0000 | 1.0000 | ✅ |

Trigger level / zone-width / distance-in-zone-widths, recomputed from `key-levels.json`:

| Wave | Trigger | Label | zone_width | Distance $ | Ratio | Report | Match |
|---|---:|---|---:|---:|---:|---|---|
| 1 | 769.36 | SHELF_768.56_770.16 | 0.8 | +0.375 | 0.469 | 0.8 / 0.469 | ✅ |
| 2 | 768.00 | INTRADAY_PMH | 0.384 | +0.37 | 0.964 | 0.384 / 0.964 | ✅ |
| 3 | 769.36 | SHELF_768.56_770.16 | 0.8 | +1.085 | 1.356 | 0.8 / 1.356 | ✅ |

Conviction totals and shadow fields, read directly off the entry-tick rows: wave1 `total=5`,
`components.range_position=0.966`; wave2 `total=4`, `components.range_position=0.336`,
`would_block=True`, `shadow_only=True`; wave3 `total=5`, `components.range_position=1.0`,
`structure_reason="range"` at 11:06 vs `"downtrend"` at 11:27 (checked directly, both match the
report verbatim). All ✅.

## 3. HWM/MAE premium paths — rebuilt from `exit_pass` series in `core-decisions.jsonl` / fleet ledgers

Wave 1 (4 arms) and Wave 3 (3 arms) HWM/MAE values, timestamps included, all recomputed by
scanning every `exit_pass` tick for the matching symbol between entry-fill and last-sell-fill:

- safe-2 770C w1: HWM 1.15@09:48:03, MAE 0.47@10:03:03 — report 1.15/0.47 ✅
- bold-2 772C w1: HWM 0.38@09:52:04, MAE 0.18@09:58:04 — report 0.38/0.18 ✅
- safe-3 770C w1: HWM 1.14@09:52:05, MAE 0.55@10:01:05 — report 1.14/0.55 ✅
- risky-1 770C w1: HWM 1.15@09:52:05, MAE 0.49@10:02:06 — report 1.15/0.49 ✅
- bold-2 772C w3: HWM 0.99@11:20:07, MAE 0.32@11:07:04 — report 0.99/0.32 ✅
- safe-3 770C w3: HWM 2.37@11:19:05, MAE 1.32@11:08:05 — report 2.37/1.32 ✅
- risky-1 770C w3: HWM 2.38@11:19:05, MAE 1.31@11:08:05 — report 2.38/1.31 ✅

## 4. Implied realized delta (the theta/decay-vs-delta claim) — rebuilt from `spy` snapshots

Recomputed `(exit_premium − entry_premium) / (SPY_at_exit − SPY_at_entry)` for all 8 stopped
positions using the same `safe`-account 1-minute SPY tape, independent of the original script:

| Position | ΔSPY | ΔPremium | Implied delta | Report | Match |
|---|---:|---:|---:|---:|---|
| safe-2/770C w1 | −0.195 | −0.48 | 2.462 | 2.462 | ✅ |
| bold-2/772C w1 | −0.145 | −0.17 | 1.172 | 1.172 | ✅ |
| safe-3/770C w1 | −0.195 | −0.54 | 2.769 | 2.769 | ✅ |
| risky-1/770C w1 | −0.195 | −0.56 | 2.872 | 2.872 | ✅ |
| safe-2/768C w2 | −0.41 | −0.22 | 0.537 | 0.537 | ✅ |
| bold-2/770C w2 | −0.41 | −0.14 | 0.341 | 0.341 | ✅ |
| safe-3/768C w2 | −0.41 | −0.13 | 0.317 | 0.317 | ✅ |
| risky-1/768C w2 | −0.41 | −0.13 | 0.317 | 0.317 | ✅ |

All four Wave-1 ratios are `>1.0` (physically impossible for a single option's delta),
confirming the decay-dominated read; all four Wave-2 ratios are in `[0.32, 0.54]`, a sane
band. Both patterns independently reproduce.

## 5. Wave-2 structure-stop zone-edge claim — the report's headline doctrine-gap finding

Pulled the `structure_stop`-tagged `exit_pass` rows directly (safe, bold, and both fleet arms
share the identical `last_closed_5m_close=767.96` at the firing tick):

```
trigger_level        = 768.00
zone_width            = 0.384  ->  zone_edge_lower = 767.616
last_closed_5m_close  = 767.96
breach of RAW level   = 768.00 - 767.96 = $0.04   (breached)
breach of ZONE EDGE   = 767.616 - 767.96 = -$0.344 (NOT breached — still $0.344 inside zone)
```

Confirmed identically for safe (`10:36:03`), bold (`10:36:05`), and both fleet arms
(`10:37:05`). **The report's claim is exact and reproduces bit-for-bit.**

SPY path 55 minutes after the stop (rebuilt from the same `safe`-tape, 61 ticks scanned):
max = **772.93 @ 11:31:03**, matching the report's "+$4.97 rally" claim exactly (767.96 →
772.93 = +4.97).

## 6. Population comparison stats — rebuilt from `entry-location-rows.json`, not re-cited

This is the part of the reproduction that matters most: the report explicitly says the
population figures are "built earlier today by a sibling H1 investigation — reused, not
rebuilt." I rebuilt them myself, independently, straight from the row-level JSON:

- `BULLISH_RECLAIM_RIDE_THE_RIBBON` calls: **n=113** (rebuilt) vs report's n=113 ✅
- Winners: **n=36, mean range_position=0.824** (rebuilt) vs report's 36 / 0.824 ✅
- Losers: **n=70, mean range_position=0.8431** (rebuilt) vs report's 70 / 0.8431 ✅
- Mid-band (0.40–0.65) check across the full 191-row population: **n=32, mean
  $51.69/trade, WR=0.406, PF=2.139** (rebuilt) vs report's (via `entry-location.md`) n=32 /
  $51.69 / WR 0.406 / PF 2.14 ✅ — and cross-checked the outside-band population too:
  **n=154, mean $0.86/trade**, matching `entry-location.md`'s cited "n=154" figure.

All four independently reproduce to the specified precision.

## 7. Equity-percentage figures — recomputed from the CLAUDE.md-stated start-of-day equities

Using safe-2 $5,653.81 / bold-2 $5,593.52 / safe-3 $5,639.10 / risky-1 $6,149.12: every single
`% equity` cell in the report's Wave 1/2/3 tables (−2.55%, −1.52%, −4.79%, −4.55%, −1.17%,
−1.25%, −1.15%, −1.06%, +3.56%, +8.99%, +5.58%) recomputes to within rounding of the stated
figure. No discrepancy found.

---

## Issues found (both minor, neither changes a dollar figure or the headline conclusion)

**(a) "Continuous" SKIP_STRUCTURE_VETO framing overstates continuity.** The report's code
block presents `11:11:04–11:35:04 SKIP_STRUCTURE_VETO` as if that single action fired for the
entire 25-minute span. Pulling every `safe`-account row in that window shows the true pattern
alternates: **17 of 25 minutes were `SKIP_STRUCTURE_VETO`, but 8 minutes (11:14, 11:15, 11:19,
11:20, 11:24, 11:25, 11:29, 11:30) were `HOLD` — "no setup passed scoring (neither bear nor
bull)"**, i.e. no bull candidate existed for the veto to act on at all in those ticks. This
does not change the substantive finding (safe-2 got zero fills across the whole span while the
other three arms got one profitable fill each at 11:06–11:07, and the `structure_veto_enabled`
config divergence is independently confirmed via a direct read of both params files), but the
report's specific "continuously blocked by the veto" wording is not literally accurate for 8 of
the 25 minutes it covers — those minutes had no bull signal to veto in the first place.

**(b) Factual error in the Wave-3 TP1 parenthetical.** The report states: *"safe-3/risky-1's
TP1 rule fires at a lower %-of-premium than bold-2's +100%"*. This is wrong for safe-3: pulling
`safe-3/decisions.jsonl` directly shows safe-3's TP1 action tagged **`tp1 @ +100%`** — the
*same* threshold as bold-2, not lower. Only **risky-1** fires lower, at `tp1 @ +50%`. The
report's own Wave-3 table two lines above the parenthetical already shows this correctly
(`safe-3 ... tp1 @ +100%`, `risky-1 ... tp1 @ +50%`) — the parenthetical prose directly
underneath contradicts the table it's annotating. A trivial internal inconsistency, not a
numeric error, and it doesn't affect any P&L, equity%, or the wave's headline dollar totals.

Neither issue is material: no dollar figure, entry-feature number, population statistic, or
causal-mechanism claim (structure_veto config divergence; zone-edge-vs-raw-level stop basis)
changes as a result of either correction.

---

## What was NOT re-verified (scope boundary, stated for honesty)

- The `analysis/pain-ledger/mae-mfe.json`-sourced "45.5% of losers have ≥+10% MFE before
  capping" figure attributed to H4/SYNTHESIS — cited by the original report as background, not
  computed by it; out of scope for a reproduction of *this* report's own claims.
- `backtest/lib/engine/engine_cli.py` lines 192–226/626–645 (`_classify_sameday_5m` mechanics)
  — read by the original report to confirm the veto's existence; I independently confirmed the
  *config* divergence (`structure_veto_enabled: true` vs `false`, read fresh from both
  `params.json` files) and the *behavioral* divergence (safe blocked, bold/fleet not, on the
  identical entry tick), which is the load-bearing claim; I did not re-derive the classifier's
  internal 5m-bar lookback logic from source, since the config-level and ledger-level evidence
  already independently pins the causal claim.
- The safe-2 wave-3 opportunity-cost estimate (~+$500) — the original report already labels
  this APPROXIMATE/not-a-fill; nothing to "reproduce" beyond confirming safe-3's own +$507 fill
  is real (done, §1 above).

## Files

- Verification script (new): `backtest/tools/dissect_verify_wave-autopsy_2.py`
- This note: `analysis/deep-research/2026-09-03-money/verify-dissect-wave-autopsy-2.md`
- No trading-path or generated-surface file read for write, or written to, at any point.
