# LEVER 3 — THE CATASTROPHE CAP AND THE PER-TRADE LOSS TAIL

**Clock verified this session, first action, before anything else:**
`python setup/scripts/et_clock.py` → **`2026-08-06 16:45:22 Thursday EDT`, `market_hours=False`.**
After-hours. Analysis-only: no file under `automation/state/`, `setup/scripts/`, `backtest/lib/`
or any `params*.json` was modified.

**Frozen pre-registration:** `analysis/recommendations/prereg-lever-catcap-2026-08-06.json`,
commit **`089beb50`**, committed **before** the runner existed
(`git merge-base --is-ancestor 089beb50 HEAD` → true).

---

## VERDICT — one sentence

> ### The lane's PRIME LEAD is a graveyard collision AND its premise is backwards: for a `stop_mode="structure"` position the catastrophe cap **IS** `ExitState.premium_stop_pct` (`exit_manager.py:224-225,237`), so "tighten the cap" is the graveyarded stop-tightening item wearing a costume — and when run anyway it **saves $543 on Wednesday and costs $1,698 on Thursday**, i.e. the cap is **too tight, not too loose**. Across a 22-cell grid on two populations, **zero cells clear all six pre-registered gates**, and the only cells that pass Tuesday, Thursday, the 391-day population and the runner anchor are the ones that **WIDEN** the cap to −60%/−70%.

**Verdict: `GRAVEYARD_COLLISION`** on axis A and axis C; **`NULL`** on axes B and D.

---

## 0. Answering the brief's own instruction first

> *"if on inspection they are the SAME knob in this codebase, say so and stop rather than
> relabelling a dead result."*

**They are the same knob. Saying so, with the code.** `automation/state/fleet/exit_manager.py`,
`ExitState.from_entry`:

```python
cat_pct = exit_shape.get("catastrophe_stop_pct")          # line 219
...
if resolved_structure:
    stop_pct = cat_pct                                    # line 225  <-- the cap BECOMES the stop
    mode = "structure"
else:
    stop_pct = exit_shape.get("premium_stop_pct")         # line 228
...
    premium_stop_pct=stop_pct,                            # line 237  <-- stored in ONE field
    runner_stop_premium=round(float(entry_premium) * (1.0 + stop_pct), 4),   # line 244
```

and the single downstream test, `plan_exit_actions` line 440: `if worst_premium <= runner_stop:`.

For a structure-mode position **the shape's own `premium_stop_pct` is discarded entirely** and
the catastrophe cap is the operative premium stop. `ribbon_ride` ships `stop_mode="structure"`
(`test_six_account_exit_shapes.py:163-164`), so **every** ribbon position is in this branch.
The brief's framing — "the premium stop is the primary intraday stop; the catastrophe cap is the
backstop of last resort" — describes the *doctrine*, not this code path. In the code there is one
stop field and the cap fills it.

**The brief's second factual claim is also wrong.** "The ribbon family's catastrophe cap is
PINNED at −50% and no study has ever varied it" — two studies have:

| prior study | what it varied | cells | verdict |
|---|---|---|---|
| `backtest/tools/catastrophe_stop_shakeout_ab.py` → `analysis/recommendations/catastrophe-stop-shakeout-2026-07-23.{json,md}` | `catastrophe_stop_pct`, same 387-RTH-day pinned population used here | −0.70, −0.99 | **CONTROL_HOLDS** (agg +$2,146.55 / +$3,626.05 but gate2-days and gate4-OOS both FAIL) |
| `backtest/tools/stopped_then_paid_2026_08_04.py` (run earlier the SAME day) line 365 `out["catastrophe_stop_pct"] = width_pct` | `catastrophe_stop_pct` for ribbon_ride on 08-04, 08-05, and the 391-day gap-fade slice | −.10 −.12 −.15 −.20 −.25 −.30 −.50 | ribbon_ride a **drag at every width** (−$217.90) |

Genuinely unfilled before tonight: **−0.35, −0.40, −0.60** only. They are filled below and they
do not rescue the axis.

**Axis C is a FIFTH iteration of a four-times-dead cell.** `pre_tp1_be_floor_arm_pct` was built,
run and refuted on 2026-08-02 (`pretp1-be-floor-isolated-ab-2026-08-02.md`, iteration 4, ARM
NOTHING) at arm thresholds 0.30/0.50/0.70, with published dose-response
`monotonic_improving_with_higher_arm_pct`. The brief requested {0.15, 0.20, 0.25, 0.30, 0.40} —
four of five on the **worse** side of that monotone. Pre-registered prediction: they would be
worse than 0.30. **They are** (see §3).

**What DOES differ mechanically, stated as the brief demanded.** An MFE-triggered breakeven floor
is *not* `arm_scope="full"`. `arm_scope="full"` (lines 389-395) does three things — sets
`profit_lock_armed=True`, raises the stop to breakeven, and (in trailing mode) ratchets to
`hwm*(1-trail_pct)`, which climbs **above** breakeven. `pre_tp1_be_floor_arm_pct` (lines 403-405)
does exactly one — raises the stop to breakeven, never trails, never sets `profit_lock_armed`, so
the post-TP1 chandelier ride is byte-identical to control. **No mechanism collision. The collision
is on the result: it has already been run and it already failed.**

---

## 1. Harness trust — established before any interpretation

**Population A CONTROL reconciles to the pinned source population with 0 / 191 mismatches.**
Then, without tuning, this session's from-scratch harness reproduces **five independently
published numbers to the cent**:

| this run | published, elsewhere, earlier | value |
|---|---|---|
| `A_cat-70` popA delta | catastrophe-stop-shakeout-2026-07-23 CAND-WIDE70 | **+$2,146.55** ✓ |
| `C_be30` popA delta | pretp1-be-floor-isolated-ab-2026-08-02 P1 G1 | **−$1,105.85** ✓ |
| `C_be30` runner delta | pretp1-be-floor-isolated-ab-2026-08-02 P1 G4 | **−$3,650.45** ✓ |
| `D_tp1_50` popA delta | exit-armscope-tp1-ab-2026-07-28 E2 G1 | **−$2,491.55** ✓ |
| `D_tp1_50` runner delta | exit-armscope-tp1-ab-2026-07-28 E2 G4 | **−$5,615.70** ✓ |

**Population B CONTROL reconciles to the real broker book exactly:** Tue **+$3,624.00**,
Wed **−$1,935.00**, Thu **+$1,465.00** — matching Lane 0's independently-derived options-only
day totals to the cent, from a fresh `fleet_broker.load_creds()` + `GET /v2/orders` pull of all
5 arms across the three dates (25 / 14 / 4 round-trip positions).

### 1a. A methodological correction this study makes to its own predecessor

`stopped_then_paid_2026_08_04.py` differences every cell against the **real broker book**, which
silently folds *replay divergence* into every reported knob effect. Measured here for the first
time by adding a `CONTROL_WALK` cell (the **unchanged** shape pushed through the same harness):

| | Tue 08-04 | Wed 08-05 | Thu 08-06 |
|---|---:|---:|---:|
| CONTROL (real broker fills) | $3,624.00 | −$1,935.00 | $1,465.00 |
| CONTROL_WALK (harness, knob unchanged) | $5,616.00 | −$1,482.06 | $1,257.40 |
| **replay divergence — NOT a knob effect** | **+$1,992.00** | **+$452.94** | **−$207.60** |

Point-sampled 1-min bar OPENs do not land on the exact historical stop-touch minute. **Every
Population-B delta in this report is measured against `CONTROL_WALK`, not against the book**, so
the +$1,992 of Tuesday divergence is not miscredited to any lever. Read against the raw book,
`A_cat-20` would have looked like a **+$1,992 Tuesday win**; it is actually **$0.00**.

---

## 2. THE SCORECARD — all 22 cells, all 6 gates, failures included

Population A = 191 trades / 387 RTH days, entries frozen, exits re-walked through the real
`exit_manager.plan_exit_actions`. Population B = the real 3-day broker book, sequential per
arm-day. Deltas vs `CONTROL_WALK`.

Gate order: **`HG_TUE` · `G1` popA agg · `G2` runner anchor · `G3` Wed · `G4` Thu · `G5` drop-best**

| cell | popA Δ | drop-best | runner Δ | **Tue** | **Wed** | **Thu** | week Δ | gates |
|---|---:|---:|---:|---:|---:|---:|---:|:--|
| `A_cat-20` | −2,999 | −3,233 | −2,170 | **0** | **+543** | **−1,698** | −1,155 | `Y n n Y n n` |
| `A_cat-25` | −3,322 | −3,517 | −1,755 | **0** | +452 | −1,799 | −1,347 | `Y n n Y n n` |
| `A_cat-30` | −2,370 | −2,561 | −1,155 | **0** | +362 | −1,900 | −1,538 | `Y n n Y n n` |
| `A_cat-35` † | −2,696 | −2,887 | −1,200 | **0** | +271 | −1,530 | −1,258 | `Y n n Y n n` |
| `A_cat-40` † | −777 | −968 | −638 | **0** | +181 | −1,564 | −1,383 | `Y n n Y n n` |
| **`A_cat-60`** † | **+747** | −198 | **0** | **0** | −181 | **0** | −181 | `Y Y Y n Y n` |
| **`A_cat-70`** | **+2,147** | **+705** | **0** | **0** | −2 | **0** | −2 | `Y Y Y n Y Y` |
| `B_give30` | −2,822 | −3,191 | **−8,060** | +1,987 | +1,056 | −1,293 | +1,750 | `Y n n Y n n` |
| `B_give40` | −3,121 | −3,427 | −7,667 | +2,085 | +792 | −1,293 | +1,584 | `Y n n Y n n` |
| `B_give50` | −3,423 | −3,729 | −7,880 | +2,085 | +792 | −1,293 | +1,584 | `Y n n Y n n` |
| `B_give60` | −3,940 | −4,246 | −8,397 | +2,085 | +792 | −1,293 | +1,584 | `Y n n Y n n` |
| `C_be15` | −1,942 | −2,248 | −5,585 | **0** | +904 | −1,293 | −389 | `Y n n Y n n` |
| `C_be20` | −2,375 | −2,681 | −5,585 | **0** | +904 | −1,293 | −389 | `Y n n Y n n` |
| `C_be25` | −2,182 | −2,488 | −5,167 | **0** | +904 | −1,037 | −132 | `Y n n Y n n` |
| `C_be30` ‡ | −1,106 | −1,412 | −3,650 | **0** | +904 | −1,037 | −132 | `Y n n Y n n` |
| `C_be40` | −1,487 | −1,793 | −3,103 | **0** | +904 | −1,037 | −132 | `Y n n Y n n` |
| `D_tp1_20` | −4,095 | −4,564 | **−10,114** | **−3,821** | +1,186 | −868 | −3,503 | `n n n Y n n` |
| `D_tp1_25` | −3,257 | −3,749 | −9,461 | **−3,668** | +1,269 | −740 | −3,140 | `n n n Y n n` |
| `D_tp1_30` | −1,733 | −2,247 | −8,355 | **−3,516** | +1,352 | −677 | −2,841 | `n n n Y n n` |
| `D_tp1_40` | −1,767 | −2,326 | −7,070 | **−3,211** | +1,517 | −550 | −2,244 | `n n n Y n n` |
| `D_tp1_50` ‡ | −2,492 | −3,095 | −5,616 | **−2,906** | **+1,683** | −399 | −1,622 | `n n n Y n n` |

† genuinely new cell (never run before tonight) ‡ exact replication of published prior art

**ZERO of 22 cells clear all six gates.** The closest is `A_cat-70`, which fails only `G3`
(Wednesday) — by **$2.50**.

---

## 3. The four findings that matter

### 3.1 THE INVERSION — the catastrophe cap is TOO TIGHT, not too loose

Tightening it is the brief's prime lead. Run on real data it is a **Wednesday-for-Thursday
trade at a terrible price**:

| cap | Wed saves | Thu costs | net week | 391-day popA | runner anchor |
|---|---:|---:|---:|---:|---:|
| −20% | +$543 | **−$1,698** | −$1,155 | −$2,999 | −$2,170 |
| −30% | +$362 | −$1,900 | −$1,538 | −$2,370 | −$1,155 |
| −40% | +$181 | −$1,564 | −$1,383 | −$777 | −$638 |
| **−50% (live)** | — | — | — | — | — |
| −60% | −$181 | **$0** | −$181 | **+$747** | **$0** |
| −70% | −$2 | **$0** | −$2 | **+$2,147** | **$0** |

**Thursday is the discriminator the brief asked for and it kills the axis.** Thursday's book is
three winning puts (`safe-2` +$375, `risky-1` +$296, `risky-3` +$830). A −20% cap stops all of
them out of their run for **−$1,698** — **3.1× more than the $543 it rescues on Wednesday**.
This is not a marginal call; every tightening cell loses money across the week AND on 387
independent days AND on the runner cohort.

Meanwhile widening costs Tuesday **$0.00**, Thursday **$0.00**, the runner anchor **$0.00**, and
pays **+$747 / +$2,147** on the population. It just doesn't help Wednesday.

### 3.2 THE PRICE OF THE LEFT TAIL, QUANTIFIED — the number that has never been published

The brief asks: *"how much of the left tail does a reachable partial remove?"* Population A's
CONTROL left tail is **$15,469.30** across 135 losing trades. Splitting every cell's delta into
loss-side and win-side gives an **exchange rate: win dollars destroyed per loss dollar removed.**

| cell | removes | = % of the left tail | costs in wins | **rate** |
|---|---:|---:|---:|---:|
| **`A_cat-70` (WIDEN)** | **+$2,317** | 15.0% | −$1,288 | **0.56** |
| `D_tp1_30` | **+$8,142** | **52.6%** | −$10,993 | 1.35 |
| `A_cat-60` (WIDEN) | +$917 | 5.9% | −$1,288 | 1.40 |
| `D_tp1_40` | +$6,547 | 42.3% | −$9,432 | 1.44 |
| `C_be30` | +$4,000 | 25.9% | −$6,224 | 1.56 |
| `B_give30` | +$6,723 | 43.5% | −$10,664 | 1.59 |
| `A_cat-20` (TIGHTEN) | +$1,704 | 11.0% | −$5,821 | **3.42** |
| `A_cat-35` (TIGHTEN) | +$699 | 4.5% | −$4,513 | **6.45** |

**Read the top row.** The ONLY cell in the entire grid with an exchange rate **below 1.0** — the
only lever that removes more loss dollars than it destroys in win dollars — is **widening the
catastrophe cap**. Mechanism, already documented in the 2026-07-23 shakeout and unchanged here:
of the four trades where the −50% cap fired, **4/4 recovered past the exit price by EOD and 3/4
reached the +100% TP1**. The cap is not catching disasters; it is *creating* them.

Every genuine loss-capper prices between **1.35 and 6.45**. Best case, a reachable +30% TP1 buys
away **half the left tail** — and hands back $1.35 of winnings for every $1.00 it saves.

### 3.3 NO LEVER MOVES THE PER-TRADE MAXIMUM — Lane 0 corroborated from a second direction

| | CONTROL | best cell | worst cell |
|---|---:|---:|---:|
| median loss | $90.40 | $90.40 | $90.40 |
| p90 loss | $242.00 | $160.00 (`A_cat-20`) | $249.00 |
| **max single-trade loss** | **$579.00** | **$579.00** | **$579.00** |

**The maximum single-trade loss is $579.00 in all 22 cells and in CONTROL — it does not move by
one cent under any exit knob at any setting.** A position that never trades above its entry can
never arm a floor, and no partial can fill. Lane 0 concluded from the distribution that the loss
lives at the *day* level, not the trade level; this study reaches the same place from the
opposite direction — by exhausting the per-trade instruments and finding none of them touches
the tail. **Combined with Lane 0, the per-trade exit knob is now a closed question.**

### 3.4 The give-back cap is worse than the five-times-dead cell it resembles

Pre-registered prediction (before running): `arm_scope="full"` hard-codes a BE floor at the
arming instant, and the trail floor `hwm*(1-trail_pct)` only exceeds it above +43%/+67%/+100%/
+150% MFE, so wide-trail cells would degenerate to the refuted BE-floor behaviour. **Confirmed:**
Wednesday is +$1,056/+$792/+$792/+$792 — essentially flat across trail widths 0.30→0.60, i.e. the
BE floor is doing the work and the trail width is nearly a dead knob. And the runner anchor lands
at **−$8,060 to −$8,397**, *worse* than the already-graveyarded E1 cell's −$7,758.85.

**Do not be fooled by `B_give30`'s +$1,750 week.** Its week-split shows **13 of 43 positions
suppressed** (held positions blocking later real entries) versus 8-9 for the other axes — the
apparent win is largely a re-entry cap in an exit-knob costume, and re-entry capping belongs to
the cap-3 lane, measured separately.

---

## 4. TP1 reachability — and a number in the brief I could not reproduce

Descriptive, no gate. Population A, n=191:

| threshold | +20% | +25% | +30% | +40% | +50% | +100% |
|---|---:|---:|---:|---:|---:|---:|
| fraction of entries whose post-entry max reaches it | 79.6% | 75.9% | 73.8% | 71.7% | 65.5% | **45.0%** |

**Median post-entry MFE = +83.8%.**

⚠️ **This does not reconcile with the brief and I am not going to paper over it.** The brief
states *"Only 14% of 124 ribbon_ride entries EVER reach +100%; median MFE is +16.3%."* I measure
45.0% and +83.8% on the 391-day population. Two reasons, both real, neither resolved here:
(1) **different measure** — mine is the *unconditional* post-entry maximum over the remainder of
the session, ignoring where the position actually exited (an upper bound on reachability), and
the brief's is very likely MFE *while still in the trade*; (2) **different population** — 391
historical days versus the recent live book. Whoever consumes the "+100% TP1 is unreachable"
claim should re-derive it on a stated population with a stated measure first. **My 45.0% is
labelled an upper bound and must not be quoted as a live reachability rate.**

---

## 5. What Wednesday's ceiling actually is

Independent cross-check worth recording: Lane 0 computed the Wednesday exit-config lever at
**+$1,682.40** standalone by substituting a sibling arm's *actual realized fills*. This study,
by a completely different route — a `walk_exit_manager` policy replay of `tp1_premium_pct=0.5` —
gets **+$1,683.25**. Two independent methods, **$0.85 apart.**

That is the ceiling. Wednesday's exit-config damage is worth about **$1,683**, it lives entirely
in the `772P` put, and the only lever that captures it costs Tuesday **−$2,906**.

Note also that Wednesday's **776C 5× spiral is `VWAP_CONTINUATION`** (`setup_name` verified in
`risky-1`/`risky-3` `decisions.jsonl`, `trigger_level=None`, premium mode at −6%) — **not**
ribbon_ride. Axis A structurally cannot touch it. Any claim that the catastrophe cap could have
saved Wednesday's spiral is false on the wiring.

---

## 6. Artifacts

| path | what |
|---|---|
| `analysis/recommendations/prereg-lever-catcap-2026-08-06.json` | frozen pre-reg, commit `089beb50` |
| `analysis/deep-research/LEVER-CATCAP-2026-08-06.md` | this file |
| `analysis/deep-research/LEVER-CATCAP-2026-08-06.json` | all 22 cells, per-trade rows, splits, tails |
| `backtest/tools/lever_catcap_2026_08_06.py` | the runner |
| `backtest/tools/_pull_week_broker_fills_2026_08_06.py` | read-only 3-day broker pull |
| `backtest/tools/_week_positions_2026_08_06.py` | broker orders → round-trip positions |

---

## 7. Caveats — stated, not buried

1. **Population B is 3 days and 43 positions.** Tuesday/Wednesday/Thursday deltas are anecdote-
   scale. They are decision-relevant only because they *agree in sign* with the 387-day
   population on every axis, and because the brief made Tuesday no-harm a hard gate.
2. **Population A is ONE arm at qty 3, one strategy family.** It cannot express fleet effects and
   its worst day in 387 RTH days is −$825 — it structurally cannot produce a Wednesday.
3. **The runner-anchor cohort TOTAL differs from the published anchor.** n = 35 matches exactly and
   every delta reproduces to the cent, but my CONTROL sum is **$15,497.25** against the published
   **$15,774.05** (a $276.80 gap). The cohort *selection rule* is therefore not byte-identical to
   EXIT-LEAK's. Deltas — the gated quantity — are unaffected and verified.
4. **Two positions are held at their real P&L in every cell** (`safe-2` `SPY260805C00777000`,
   `safe-2` `SPY260806C00769000`, −$84 and −$36). Neither the fleet ledgers nor
   `core-decisions.jsonl` carry a `setup_name` for them. Holding them constant makes them
   arithmetically incapable of moving any delta; guessing their strategy would not have been.
5. **Population-B `A_cat-60`/`A_cat-70` show Thursday $0.00** because a wider cap cannot fire
   where the −50% cap did not. That is a structural zero, not evidence of safety on unseen days.
6. **Suppression counts differ by axis** (8-9 for A/C/D vs 13 for B). Any cell that changes hold
   time also changes which later real entries survive; that re-entry effect is entangled with
   the exit knob and is not separated here.
7. **The 2026-08-06 SPY 5-minute series** comes from `spy_5m_2026-05-19_2026-08-06.csv`; 08-05
   option bars were re-parsed from the legacy-schema `highres` cache (UTC `timestamp` column) —
   the same defect and same fix as `stopped_then_paid_2026_08_04.py`. 08-06 option bars are a
   live Alpaca REST fetch (396 rows each, real OPRA).
8. **No ORACLE column appears anywhere in this study.** Every number is live-executable under
   the real exit engine.

---

## 8. The one honest recommendation

**Do not tighten the catastrophe cap.** It is the graveyarded stop-tightening knob, it is
refuted in the requested direction on both populations, and it costs 3.1× more on Thursday than
it saves on Wednesday.

**There is a real, separate, positive finding buried in the refutation** — and it is a
*loss-reducer*, just not the one anyone was looking for: **widening the cap to −60%/−70% is the
only lever in a 22-cell grid whose loss-side gain exceeds its win-side cost** (rate 0.56), costs
**$0.00** on Tuesday and Thursday, does **zero** damage to the runner anchor, and pays
**+$747/+$2,147** on 387 independent days. It fails `G3` only because it does not help Wednesday.
It is **not** shippable on this evidence — the 2026-07-23 shakeout already failed it on
gate2-days and gate4-OOS with n=27, and nothing here fixes that n. It belongs in a **separate
pre-registered widening study with a proper OOS split**, framed as what it is: *the cap is
shaking us out of trades that recover.*
