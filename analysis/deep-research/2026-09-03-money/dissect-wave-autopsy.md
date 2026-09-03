# D1 — WAVE-BY-WAVE AUTOPSY OF 2026-09-03 (through 11:39 ET, stamp 11:40 ET)

**Slug:** `wave-autopsy` · **Data:** cached ledgers only, no broker/network calls.
**Companion JSON:** [`dissect-wave-autopsy.json`](dissect-wave-autopsy.json) (full per-position dump).
**Script:** `backtest/tools/dissect_wave_autopsy.py` (rerunnable, reads only pre-filtered scratch
copies of `core-decisions.jsonl` / fleet `decisions.jsonl` / `fills-ledger.jsonl`, plus
`key-levels.json` and `analysis/pain-ledger/mae-mfe.json`-derived `entry-location-rows.json`).

**Critical caveat, stated once, applies everywhere below:** each wave is **ONE shared engine
signal** (`build_shared_signal.py`) routed near-simultaneously to 3–4 arms at different sizes.
The 3–4 "positions" per wave are **not independent trials** — same underlying, same trigger,
same minute. Do not read wave-to-wave or arm-to-arm dispersion within a wave as a sample; it's
one bet sized four ways. All population comparisons below (entry-location.md, mae-mfe.json) use
the actual independent-day population, not today's 3 waves, for that reason.

---

## Wave map (FACT, from `fills-ledger.jsonl` + `core-decisions.jsonl` + fleet `decisions.jsonl`)

| Wave | Entries (ET) | Symbol(s) | Arms | Exits (ET) | Net wave $ |
|---|---|---|---|---|---|
| 1 | 09:41:04–09:42:08 | 770C ×3, 772C ×1 (bold) | safe-2, bold-2, safe-3, risky-1 | 09:58:04–10:03:03 | **−$779.00** |
| 2 | 10:16:08–10:17:09 | 768C ×3, 770C ×1 (bold) | safe-2, bold-2, safe-3, risky-1 | 10:36:04–10:37:08 | **−$266.00** |
| 3 | 11:06:05–11:07:15 | 772C (bold), 770C ×2 | bold-2, safe-3, risky-1 (**safe-2 blocked**) | 11:14:07–11:21:07 | **+$1,049.00** |
| **3-wave net** | | | | | **+$4.00** |

A **wave 4** (772C bold-2 @0.39 11:27, 774C-strike variants) was already open and one leg
(bold-2 774C) had premium-stopped by 11:34 (`premium_stop @ 0.62`, entered 0.39, HWM 0.74) —
**out of scope for this D1** (task cutoff was wave 3 / 11:19–11:27), noted only so the +$4.00
three-wave net is not mistaken for the session total.

---

## WAVE 1 (09:41–10:03) — all four arms, same signal, same outcome shape

### Entry (all four arms, byte-identical signal — `core_tick_id` shared)

| Feature | Value | Source |
|---|---|---|
| SPY at entry | 769.735 | core-decisions PLACED row |
| Session range so far | 765.13–769.735 (12–13 ticks since 09:30 open) | computed, session-so-far methodology (H1-identical) |
| **range_position (session-so-far)** | **1.0000** (session HIGH) | computed |
| range_position (conviction, prior-day-union envelope) | 0.966 | `conviction.components.range_position` |
| Ribbon | BULL, ≥10.9–12.0 min (since-session-open lower bound — pre-market state unknown) | core-decisions tape |
| htf_15m | BULL, same lower bound as ribbon | core-decisions tape |
| VIX | 15.02 | core-decisions |
| Trigger level | 769.36 (`SHELF_768.56_770.16`, zone_width **0.8**, i.e. zone = [768.56, 770.16]) | key-levels.json |
| Distance from level | **+$0.375 = 0.469 zone-widths** into the zone (entry sits well inside its own level's zone, typical reclaim-and-go) | computed |
| Conviction total | 5/8 (structure component degraded: `unknown:insufficient_bars`) | core-decisions |
| Spread | 97.6¢ | core-decisions |
| Bar freshness | 6.06–7.09 min | core-decisions |
| Setup | BULLISH_RECLAIM_RIDE_THE_RIBBON, quality ELITE (fleet) | both sources |

**Entry qty:** safe-2 3 (tight-ladder $1,000/position cap: 3×0.98×100=$294 vs 8-contract cap would be $784, ladder still caps by contract count not $ here), bold-2/safe-3/risky-1 5 each (contract-count cap, `qty capped 8->5`).

### Premium path + exit (FACT, from `exit_pass.best_premium/worst_premium` + fills)

| Arm | Entry px | HWM | t→HWM | MAE (worst) | Exit px | Exit stage | Realized $ | % premium | % equity |
|---|---:|---:|---:|---:|---:|---|---:|---:|---:|
| safe-2 (3x 770C) | 0.98 | 1.15 (09:48) | 7.0 min | 0.47 (10:03) | 0.50 | `premium_stop @ 0.49` | **−$144.00** | **−48.98%** | −2.55% |
| bold-2 (5x 772C) | 0.37 | 0.38 (09:52) | 10.0 min | 0.18 (09:58) | 0.20 | `premium_stop @ 0.18` | **−$85.00** | **−45.95%** | −1.52% |
| safe-3 (5x 770C) | 1.11 | 1.14 (09:52) | 10.0 min | 0.55 (10:01) | 0.57 | `premium_stop @ 0.56` | **−$270.00** | **−48.65%** | −4.79% |
| risky-1 (5x 770C) | 1.08 | 1.15 (09:52) | 9.9 min | 0.49 (10:02) | 0.52 | `premium_stop @ 0.54` | **−$280.00** | **−51.85%** | −4.55% |

All four ran to essentially the exact same shape: a small HWM ~5–8 min in, then a straight bleed
to the **−50% catastrophe cap** (Rule 3 mechanical stop, no discretion). MAE happened at (or one
tick from) the actual exit in every case — the stop fired at the position's own worst point, not
a premature trigger on a noise wick that then recovered.

### SPY path during and after (FACT)

SPY at entry 769.735 → SPY at exit 769.54–769.59 (a **$0.145–0.195** net move over the whole
20-minute hold). SPY then continued down to **767.78** by 10:11–10:15 (12 min after the last
exit), round-tripped through 768–769 chop, and was back to **769.265** by 11:01–11:03 (60 min
after safe-2's exit) — i.e. **roughly flat to the entry price**, not a reclaim, not a breakdown.

**The level never came into play.** The trigger zone's lower edge (768.56) was not touched
during any of the four holds (min SPY while positions were open ≈ 769.5). This was a pure
**premium decay** loss, not a level/structure loss.

### J's three questions — Wave 1

**(1) Bad entry?** Range_position (session-so-far) = **1.0000**, session-high entry. Population
comparison (`entry-location-rows.json`, BULLISH_RECLAIM_RIDE_THE_RIBBON calls, n=113): mean
range_position of **winners is 0.824**, of **losers is 0.8431** — statistically the same
(H1's own finding). Wave 1's rp=1.0 is on the extreme tail of both distributions, but so are the
named winners: 08-13's and 08-27's blocked-cluster wins (the trades that make 0.75/0.25 "avoid
chase" rule kill a $1,748 day) were **also all rp=1.0**. **Location alone did not distinguish
this trade from a winner — H1's conclusion holds today.** Distance-from-level (0.469 zone-widths
into the zone) was unremarkable, not a stretch entry.

**(2) Losers too big?** No, by every sizing yardstick: −$144 to −$280 is **1.52%–4.79% of that
arm's own equity**, nowhere near the 30%/50% per-trade cap (safe-2 cap ≈$1,696; bold-2 cap
≈$2,797), and cost basis ($185–$555) is nowhere near the tight-ladder $1,000/position cap. **The
loss was correctly small in dollar terms — the -50% catastrophe cap did its job.** But: at
1-minute SPY resolution, SPY moved only **$0.145–$0.195** between entry and the stop while
premium fell **45.9%–51.85%**. That implies a "realized delta" of **1.17× to 2.87×** notional
(`q2_spy_points_at_stop` in the JSON) — **physically impossible for a single option** (delta is
bounded [0,1]). This means most of Wave 1's loss was **theta/IV-crush, not delta** — an ATM
0DTE call bleeding time value while the underlying barely moved. **APPROXIMATE, flagged
explicitly:** 1-minute snapshots may understate true intraminute SPY range, so the true implied
delta could be somewhat lower than 1.17–2.87×, but it cannot be plausibly pushed down to a sane
≤1.0 given the tiny observed net SPY move — the qualitative finding (decay-dominated, not
delta-dominated) is robust to that resolution caveat.

**(3) Should we have held?** For Wave 1, the **catastrophe cap was the only active stop** — SPY
never approached the trigger zone's edge (768.56) during the hold, so a zone-edge-stop rule
would have behaved identically (no earlier or later trigger point — the catastrophe cap alone
determined the exit). Removing/widening the cap is out of scope (H8, `loss-size-math.md`,
**REFUTED** book-wide: tightening the cap is net-negative at every level tested; this task's own
hard constraints also forbid touching `premium_stop_pct`). Holding past the actual stop (no
catastrophe cap at all) would have ridden the same 770C contract down further — **bold-2's own
wave-2 770C entry 25 min later (10:16) printed only 0.48**, i.e. *below* Wave 1's stop-out price
of 0.50–0.57 — before recovering to **2.32–2.38 by 11:19** (wave-3's real print on the same
strike). The honest read: holding through the trough to 11:19 would eventually have paid (2.32
vs 0.98–1.11 entry, **≈+110%**), but the path included a deeper drawdown first (≈0.34–0.37 at
10:36, worse than the actual −50% exit) — **this is the "orphan band" pattern from H4/SYNTHESIS
(45.5% of losers have ≥+10% MFE before capping)**, not a case where the stop was simply wrong.
**Hold-to-15:20 is UNKNOWABLE as of this stamp (11:40 ET, market open, latest tick 11:49 ET
SPY=772.58)** — not evaluated, not guessed.

---

## WAVE 2 (10:16–10:37) — the 4-cent, inside-the-zone stop

### Entry

| Feature | Value |
|---|---|
| SPY at entry | 768.37 |
| Session range so far | 765.13–769.79 (47–48 ticks) |
| **range_position (session-so-far)** | **0.6953** — mid-upper band |
| range_position (conviction, prior-day-union envelope) | **0.336** — materially different reading from the same trade; the two envelopes disagree by 0.36, illustrating entry-location.md's own note that conviction's envelope (prior-day-union-today) and this study's (session-so-far) are not interchangeable |
| Ribbon / htf_15m | BULL, ≥46–47 min (since-open lower bound) |
| VIX | 15.00 |
| Trigger level | 768.00 (`INTRADAY_PMH`, zone_width **0.384**, zone = [767.616, 768.384]) |
| Distance from level | **+$0.37 = 0.964 zone-widths** — entry sits almost exactly at the far (upper) edge of its own level's zone |
| Conviction total | 4/8 (`range_position` 0.336 scored low; `would_block: true` in the shadow ratchet — logged only, not gating) |
| Spread | 169.3¢ |
| Bar freshness | 6.07–6.14 min |
| Setup | BULLISH_RECLAIM_RIDE_THE_RIBBON, ELITE |

**Entry qty:** safe-2 3x (768C), bold-2/safe-3/risky-1 5x each (bold-2 took the 770C strike, the
other three took 768C).

### Premium path + exit

| Arm | Entry px | HWM | t→HWM | MAE | Exit px | Exit stage | Realized $ | % premium | % equity |
|---|---:|---:|---:|---:|---:|---|---:|---:|---:|
| safe-2 (3x 768C) | 1.40 | 1.62 (10:21) | 4.6 min | 0.97 (10:35) | 1.18 | `structure_stop @ 768.0` | **−$66.00** | **−15.71%** | −1.17% |
| bold-2 (5x 770C) | 0.48 | 0.56 (10:20) | 4.0 min | 0.29 (10:35) | 0.34 | `structure_stop @ 768.0` | **−$70.00** | **−29.17%** | −1.25% |
| safe-3 (5x 768C) | 1.31 | 1.60 (10:28) | 11.0 min | 1.02 (10:35) | 1.18 | `structure_stop @ 768.0` | **−$65.00** | **−9.92%** | −1.15% |
| risky-1 (5x 768C) | 1.31 | 1.59 (10:21) | 3.9 min | 0.98 (10:35) | 1.18 | `structure_stop @ 768.0` | **−$65.00** | **−9.92%** | −1.06% |

None of these were anywhere close to the −50% catastrophe floor (MAE was −24% to −31% of
premium at worst) — **this was a level/structure exit, not a decay exit**, the opposite
mechanism from Wave 1.

### The exact stop mechanics (FACT — `exit_pass.last_closed_5m_close`)

```
trigger_level          = 768.00
zone_width              = 0.384   (zone = [767.616, 768.384])
last_closed_5m_close    = 767.96  (the 5m bar the structure stop fired on)
breach of RAW level     = 768.00 - 767.96 = $0.04
breach of ZONE EDGE     = 767.616 - 767.96 = -$0.344  ->  NOT BREACHED
```

**The stop fired on a 4-cent breach of the bare level price. The 5-minute close that triggered
it (767.96) never crossed the level's own zone edge (767.616) — it was still $0.344 *inside* the
zone.** Per doctrine (`feedback_levels_are_zones_2026_07_17`: "a stop belongs beyond the zone
edge, not at the level's exact price"), this stop mechanism is currently implemented on the
**raw level**, not the **zone edge**, for `stop_mode: "structure"` positions — a direct,
concrete instance of the doctrine/implementation gap the memory flags, caught in the act on a
real trade.

### SPY path after (FACT)

SPY at the structure-stop exit: 767.96. Over the next 55 minutes SPY rallied to **772.93**
(11:31), a **+$4.97** move — the level didn't just hold, it was the exact local low of the whole
morning session so far.

### J's three questions — Wave 2

**(1) Bad entry?** range_position (session-so-far) 0.6953 sits inside the **0.40–0.65 "mid-band"
window entry-location.md flagged as the single best-performing bucket in the whole population**
(n=32, mean +$51.69/trade, WR 40.6%, PF 2.14, though CI still crosses zero at that n) — Wave 2's
entries are close to, if slightly above, that band. Not a chase entry by any threshold tested in
H1. **Entry location was not the problem.**

**(2) Losers too big?** No — −$65 to −$70 is **1.06%–1.25% of equity**, far under any per-trade
cap, and premium loss (9.9%–29.2%) is well inside the −50% floor with room to spare. Implied
realized delta from the SPY/premium relationship here is **0.317–0.537** (`q2_spy_points_at_stop`
in the JSON) — a **physically sane number** for a near-ATM/1-strike-OTM 0DTE call, unlike Wave
1's decay-dominated collapse. This loss is real, delta-driven, level-driven — and small.

**(3) Should we have held?** **Yes, mechanically, by the engine's own zone doctrine.** The 5m
close that triggered the stop (767.96) never breached the level's zone edge (767.616) — a
zone-edge-adjusted structure stop would **not have fired at 10:36**. SPY's subsequent 55-minute
path (767.96 → 772.93, +$4.97) is a hard, directly-observed fact, not a proxy. **APPROXIMATE
continuation:** the same 770C strike (bold-2's contract) reappeared in Wave 3's real fills
40 minutes later (11:07 entry 1.17–1.18, 11:19 print 2.37–2.38) — the exact contract that
structure-stopped at 0.34 on 10:36 was trading **2.37–2.38 by 11:19**, a swing of roughly
**+$1,000 notional on that single 5-lot** had the zone-edge-adjusted rule kept it open and it
were later managed the same way Wave 3's identical strike was (TP1 + trail). This is the
single cleanest "should have held" instance in the three waves: a documented doctrine gap
(raw-level vs zone-edge stop basis) with a directly observed, large dollar consequence.
**Hold-to-15:20 is UNKNOWABLE as of this stamp** — the above is bounded to what happened through
11:39 ET only.

---

## WAVE 3 (11:06–11:21) — safe-2 vetoed, three arms paid

### Entry (bold-2, safe-3, risky-1 — safe-2 never got in)

| Feature | Value |
|---|---|
| SPY at entry | 770.445 |
| Session range so far | 765.13–770.445 (97–98 ticks) |
| **range_position (session-so-far)** | **1.0000** — session high again |
| range_position (conviction envelope) | 1.0 (agrees this time) |
| Ribbon / htf_15m | BULL, ≥96–97 min (since-open lower bound) |
| VIX | 14.95 |
| Trigger level | 769.36 (`SHELF_768.56_770.16`, zone_width 0.8, zone = [768.56, 770.16]) |
| Distance from level | **+$1.085 = 1.356 zone-widths — entry is PAST the level's own zone entirely** (zone upper edge 770.16, entry SPY 770.445, $0.285 beyond it) |
| Conviction total | 5/8; `structure_reason: "range"` (bold-2's own shadow classifier read the same-day structure as "range", not "downtrend", at the moment of this entry) |
| Spread | 162.2¢ |
| Bar freshness | 6.07–6.08 min |
| Setup | BULLISH_RECLAIM_RIDE_THE_RIBBON, ELITE (fleet) |

**Entry qty:** all 5x. bold-2 took 772C (0.37), safe-3/risky-1 took 770C (1.17/1.18).

### Premium path + exit — the winners

| Arm | Entry px | HWM | t→HWM | MAE | TP1 (qty@px) | Runner (qty@px) | Realized $ | % premium | % equity |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| bold-2 (5x 772C) | 0.37 | 0.99 (11:20) | 14.0 min | 0.32 (11:07) | `tp1 @ +100%`: 3 @ 0.78 | `trail @ 0.84`→fill 0.75: 2 @ 0.75 | **+$199.00** | **+107.57%** | +3.56% |
| safe-3 (5x 770C) | 1.17 | 2.37 (11:19) | 11.8 min | 1.32 (11:08) | `tp1 @ +100%`: 3 @ 2.32 | `trail @ 2.01`→fill 1.98: 2 @ 1.98 | **+$507.00** | **+86.67%** | ≈+8.99% (start-of-day) |
| risky-1 (5x 770C) | 1.18 | 2.38 (11:19) | 11.9 min | 1.31 (11:08) | `tp1 @ +50%`: 3 @ 1.81 | `trail @ 2.02`→fill 1.95: 2 @ 1.95 | **+$343.00** | **+58.14%** | ≈+5.58% (start-of-day) |

(safe-3/risky-1's TP1 rule fires at a lower %-of-premium than bold-2's +100% — per-arm exit
config difference, not measured further here; both are documented, non-frozen fleet configs.)

Note the small live slippage on the runner trail: bold-2's stop was placed at 0.84, filled 0.75
(−$0.09/ct); safe-3's placed 2.01, filled 1.98 (−$0.03); risky-1's placed 2.02, filled 1.95
(−$0.07). Real, small, consistent with fast-market fills on a trailing stop — not a mispricing.

### safe-2's refusal (FACT — `core-decisions.jsonl`)

```
11:06:03–11:10:04  SKIP_BULL_1100_1200      reason: "blocked by entry gate block_bull_1100_1200"
                    (SAFE-ONLY gate, params.json:215; SPY flat at 770.445 through this window)
11:11:04–11:35:04  SKIP_STRUCTURE_VETO      reason: "structure-veto: C entry blocked — price
                    structure is 'downtrend' (wrong-way entry)"
                    SPY over this window: 770.73 -> 771.5 -> 772.02 -> 772.11 -> 772.93 -> 772.93
```

**Root cause, confirmed by direct config read (read-only):**
`automation/state/params.json:314` → `"structure_veto_enabled": true` (safe-2).
`automation/state/aggressive/params.json:52` → `"structure_veto_enabled": false` (bold-2,
**explicit since 2026-08-12**, doc string: *"Live proof: over 25,821 ledger rows
SKIP_STRUCTURE_VETO fired 116 times for account=safe and ZERO times for bold"*). No fleet arm
sets this key, so it defaults False for safe-3/risky-1 too. **safe-2 was blocked on wave 3 by a
gate no other arm runs**, while SPY rallied **+$2.20** (770.73→772.93) through the veto window,
and bold-2's own conviction sidecar *simultaneously logged* `structure_reason: "range"` at
entry (11:06) and `"downtrend"` at 11:27 — i.e. the SAME classifier bold's own shadow reads was
telling a different story tick-to-tick, and bold traded through it because the veto isn't wired
for that account, not because the classifier agreed with bold's entry.

**Estimated opportunity cost (APPROXIMATE, not a real fill):** safe-3 (same 770C strike, same
5-lot, same entry window) realized **+$507**. If safe-2 had gotten an identical fill at the same
5 contracts (its risk caps do not bind at this premium — 5×1.17×100=$585 is under both the 30%
equity cap and the $1,000/position tight-ladder cap), the **plausible opportunity cost of the
veto on this one wave is ≈+$500**, using safe-3 as the closest same-instrument proxy. Not
booked, not certain (safe-2's own exit_managed config could differ from safe-3's TP1 fraction),
but directionally the single largest dollar item in this whole autopsy.

### J's three questions — Wave 3

**(1) Bad entry?** range_position (session-so-far) = **1.0000** again, and entry is **1.36
zone-widths past** the trigger level's own zone (chasing further than Wave 1's 0.469
zone-widths). By H1's naive threshold test this is deep in "chase" territory — yet this was the
best wave of the day (+$1,049 across 3 positions). This is exactly H1/H2's documented mechanism:
`BULLISH_RECLAIM_RIDE_THE_RIBBON` calls print range_position near 1.0 *by construction* (the
trigger fires after the push that makes the new high), so "chase" and "fresh continuation" are
not separable on this feature alone. **Location did not predict outcome here either — in either
direction.**

**(2) Losers too big?** N/A — all three filled positions were winners. The one "loss" this wave
produced is safe-2's **foregone** ≈+$500 (opportunity cost, not a booked loss, not counted
against any cap).

**(3) Should we have held?** These already ran the full TP1+trail cycle to a clean close by
11:21 — nothing left on the table by the "hold" framing (contrast with Wave 1/2, which were
stopped early). The only "hold" question that applies to Wave 3 is safe-2's: it never got the
position to hold. **Hold-to-15:20 not applicable** (all three positions already flat by 11:21).

---

## Cross-wave synthesis

| | Wave 1 | Wave 2 | Wave 3 |
|---|---|---|---|
| Mechanism | Theta/IV-crush decay into −50% cap | 4-cent raw-level breach, inside own zone | Clean TP1+trail winners; safe-2 vetoed |
| range_position (session-so-far) | 1.0000 | 0.6953 | 1.0000 |
| Distance from level (zone-widths) | 0.469 (inside zone) | 0.964 (at zone edge) | 1.356 (past zone) |
| Implied realized delta at stop | 1.17×–2.87× (impossible — decay-dominated) | 0.32×–0.54× (sane — delta-dominated) | n/a (won) |
| Loss/gain vs equity | −1.5% to −4.8% | −1.1% to −1.3% | +3.6% to +9.0% |
| Vs 30/50% per-trade cap | Nowhere close | Nowhere close | n/a |
| "Should have held" verdict | Ambiguous near-term, positive by 11:19 (orphan-band shape) | **Yes — stop fired inside its own zone, doctrine gap confirmed** | N/A — already held to plan |

**One same-day, same-signal thread ties all three waves together**: the identical 770.16-edge
zone (SHELF_768.56_770.16 / 769.36 level) that Wave 1 entered comfortably inside of (0.469 zone-
widths) is the SAME zone Wave 3 entered 1.36 zone-widths *past* 96 minutes later, after SPY had
broken clean through it. The book's net result across the three waves is **+$4.00** — roughly
breakeven — with Wave 3's real gains (+$1,049) almost exactly offsetting Wave 1+2's decay/stop
losses (−$1,045), which matches the SYNTHESIS.md finding that day-level P&L is dominated by
whether a trend leg pays, not by any single entry-tick feature.

---

## Data sources (all read-only, no trading-path or generated-surface file touched)

- `automation/state/fills-ledger.jsonl` (today's rows, broker-truth fills)
- `automation/state/core-decisions.jsonl` (today's rows — safe/bold per-minute tape, PLACED/SKIP
  rows, `exit_pass`, `conviction`, `context_bundle`)
- `automation/state/fleet/{safe-3,risky-1}/decisions.jsonl` (today's rows)
- `automation/state/key-levels.json` (zone widths, level labels)
- `automation/state/params.json` line 314, `automation/state/aggressive/params.json` line 52
  (`structure_veto_enabled` — read-only confirmation of the safe/bold config divergence)
- `analysis/deep-research/2026-09-03-money/entry-location-rows.json` (n=191 population,
  range_position by outcome, built earlier today by a sibling H1 investigation — reused, not
  rebuilt)
- `analysis/deep-research/2026-09-03-money/SYNTHESIS.md`, `entry-location.md`, `loss-size-math.md`
  (cross-referenced, not reproduced)
- `backtest/lib/engine/engine_cli.py` lines 192–226 (`_classify_sameday_5m`) and 626–645
  (structure-veto application) — read-only, confirms the gate mechanics quoted above

## What this does NOT claim

- No causal delta model — the "implied realized delta" figures use 1-minute SPY snapshots, not
  option-chain Greeks or tick data; they are a diagnostic bound, not a priced delta.
- No statistical test on wave-level dispersion — n=3-4 per wave are correlated draws on one
  signal, not an independent sample (stated at top, repeated here per doctrine).
- No "hold to 15:20" outcome — the market was open and 15:20 ET had not happened as of the
  11:40 ET stamp (latest known tick 11:49 ET, SPY 772.58). Anything past that boundary is
  UNKNOWABLE today, not modeled, not guessed.
- The Wave-3 opportunity-cost figure (≈+$500 for safe-2) is a same-instrument proxy, not a
  fill — safe-2's own exit_managed config (TP1 fraction, trail arm threshold) could differ from
  safe-3's and was never tested because the position never opened.
