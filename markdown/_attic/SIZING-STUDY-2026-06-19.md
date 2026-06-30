# Principled SIZING study — answering J's two open sizing decisions with his own data (2026-06-19)

**Status: PROPOSE-ONLY (Rule 9).** Nothing live changed. This is analysis + a throttle DESIGN.
No edit to `risk_gate.py`, `params.json`, or either heartbeat. Market closed (post-Juneteenth
weekend window) — a legit doctrine-research window, but ratification of any change is a separate step.

- **Analysis script:** `backtest/autoresearch/sizing_study.py` (pure Python + pandas; `$0`; deterministic)
- **Machine-readable scorecard:** `analysis/recommendations/sizing-study-2026-06-19.json`
- **Source ledger:** `analysis/webull-j-trades/j_roundtrips.csv` — 1,221 reconstructed round-trips from
  J's 2021–2023 Webull options history (SPX/SPY family + single names, bull + bear, long premium only).
  We analyse the **1,182 `closed` (realized)** round-trips for P&L purity. (39 `unclosed`/`expired_worthless`
  excluded from the headline; the 16 `expired_worthless` are genuine −100% losses, noted as a sensitivity.)

This answers L168 (the weekend's #1 practical finding) and the two open calls J left on sizing.

---

## TL;DR — the two decisions

| Decision | Recommendation | Why (J's numbers) |
|---|---|---|
| **(a) min-3 vs flat-2** | **KEEP MIN 3 as the floor.** Do not lower it; do not raise it. Pair it with a premium ceiling so 3 contracts never exceeds ~6% of equity. | The damage is NOT at the floor — it is everything **above** the floor. flat-3+ is already a loser (−$6,930, WR 26.7%), but the floor itself (min-3 at cheap OTM-3) is only 4.5–6% of $2K. The right lever is a **ceiling**, not a smaller floor. |
| **(b) post-loss throttle** | **ADD it** (design below). Highest-value sizing change available from J's data. | His ledger shows mild-but-real revenge-sizing (size rises after a loss) and that the larger-lot bands are exactly where the account bleeds. A throttle that holds size at the floor while underwater neutralises both. |

---

## 1. Empirical sizing curve — the 1-2 vs 3+ cliff, quantified

Realized `closed` round-trips, by lot band:

| Lot band | n | Win rate | Total P&L | Expectancy/trade | Profit factor |
|---|---|---|---|---|---|
| **1–2** | 1,013 | **47.0%** | **+$436** | **+$0.4** | **1.01** |
| 3–5 | 135 | 23.3% | **−$17,322** | −$128.3 | 0.15 |
| 6+ | 34 | 23.5% | −$4,663 | −$137.2 | 0.16 |

The cliff is real and brutal. Win rate **halves** (47% → ~23%) the moment size crosses 2 contracts,
and profit factor collapses from break-even (1.01) to ruin (0.15). At 1–2 lots J is a break-even-to-slightly-positive
trader; at 3+ he hemorrhages. This reproduces the L168 headline from the raw ledger.

> Note: the 1–2 band is ~break-even on *all underliers*. On the **SPX/SPY family + flat-entry** subset
> it is meaningfully positive (see §2 — flat 1–2 is **+$4,294**). The single-names and the scaled-in
> entries are what drag the blended 1–2 number down to +$436.

---

## 2. THE key untangle — is it flat-size or sizing-UP that kills?

This is the question behind J's min-3 decision. We split every trade into **flat** (`n_entry_fills == 1`,
a single entry, no adds) vs **scaled-in** (`n_entry_fills > 1`, added-to / averaged / revenge-sized).

| Slice | n | Win rate | Total P&L | Expectancy/trade |
|---|---|---|---|---|
| **flat 1–2** (the edge) | 989 | **47.8%** | **+$4,294** | **+$4.3** |
| **flat 3+** | 118 | 26.7% | **−$6,930** | −$58.7 |
| **scaled-in (any size)** | 75 | 14.7% | **−$18,912** | −$252.2 |
| single-entry (any size) | 1,107 | 45.6% | −$2,636 | −$2.4 |

Within-band (flat | scaled):

| Band | flat | scaled-in |
|---|---|---|
| 1–2 | n=989, +$4,294, exp +$4 | n=24, −$3,857, exp −$161 |
| 3–5 | n=92, −$6,084, exp −$66 | n=43, −$11,237, exp −$261 |
| 6+ | n=26, −$845, exp −$32 | n=8, −$3,818, exp −$477 |

### The finding (both things are true, in this order of severity)

1. **Scaling-in is catastrophic at EVERY size.** 75 scaled-in trades lost −$18,912 at −$252/trade,
   WR 14.7%. Even in the "safe" 1–2 band, the 24 scaled-in trades lost −$3,857 (−$161/trade) — they
   single-handedly drag the blended 1–2 band from +$4,294 down to +$436. **Averaging-down / adding to
   losers is J's single most destructive behaviour.**

2. **But flat-3+ is ALSO a loser** — it is not merely a revenge artifact. The 118 single-entry trades
   at 3+ contracts lost −$6,930 (−$59/trade, WR 26.7%). Crucially this holds **across every slice**, so
   it is not one confounded bucket:

   | flat-3+ sub-slice | n | Total P&L | Expectancy | WR |
   |---|---|---|---|---|
   | bias = bear | 35 | −$3,360 | −$96 | 22.9% |
   | bias = bull | 83 | −$3,570 | −$43 | 27.7% |
   | 0DTE = true | 68 | −$6,060 | −$89 | 25.0% |
   | 0DTE = false | 50 | −$869 | −$17 | 28.0% |

   Same WR collapse (≈26%) on both biases and both DTEs. The most plausible mechanism: **when J commits
   more size he enters with worse discipline** (wider implicit stops, chasing, lower-conviction setups) —
   the size itself coincides with a degraded process.

### Honest limit of the data

J's 3+ data is **confounded with the revenge-adds** — the population of "trades J chose to size up on"
overlaps with "trades placed in a worse emotional/structural state." The ledger therefore **cannot fully
isolate** "a disciplined, mechanical flat-3 would also lose" from "the trades he happened to size to 3
were bad for other reasons." What it CAN decide:
- **Scaled-in is a hard NO at any size** (clean, large, unambiguous).
- **Flat-3+ is empirically a loser across all slices** — so there is no evidence that *raising* the floor
  toward larger size is safe, and meaningful evidence it is dangerous.
- It **cannot** prove a *mechanical, consistent, well-stopped* flat-3 would lose. The engine's flat-3
  (atomic bracket, chart-stop, never adds) is structurally different from J's discretionary flat-3.

This is why the recommendation is **keep the floor + add a ceiling**, not "trust flat-3" and not "drop to 2."

---

## 3. Revenge signal — does size correlate with a prior loss?

Chronological, per-session. We compare size **after a same-day loss** vs **after a same-day win**:

| Context | n | avg qty | % qty ≥ 3 | % scaled-in | Total P&L | Win rate |
|---|---|---|---|---|---|---|
| after same-day **loss** | 492 | **1.72** | **15.4%** | 6.1% | **−$11,304** | 36.8% |
| after same-day **win** | 414 | 1.68 | 11.1% | 4.8% | +$356 | 51.5% |

**Verdict: mild but real revenge-sizing.** After a loss, average size ticks up (1.68 → 1.72) and the
probability of a 3+ lot rises by ~40% relative (11.1% → 15.4%). More importantly, the **outcome** of
trades placed after a same-day loss is sharply negative (−$11,304 total, WR 36.8% vs 51.5% when not
chasing a loss). J both sizes up *and* trades worse after a loss. This is precisely the behaviour the
throttle in §5 is designed to interdict.

---

## 4. Fractional-Kelly bounds — the small-account, full-premium-at-risk reality

Computed from the **winning band only** (flat 1–2 — the band with a real edge), per-contract:

- `p_win` = **0.4742**
- avg win/contract = **+$101.7**, avg loss/contract = **−$76.9**, mean entry premium = **$1.94**

A long 0DTE option can expire **worthless the same day** — full premium at risk, no overnight recovery.
So two Kelly framings bracket the truth:

| Basis | payoff `b` | Full Kelly | Half Kelly | Quarter Kelly |
|---|---|---|---|---|
| **J-realized payoff** (he cut losers at ~42% of premium) | 1.324 | **7.7%** | **3.9%** | 1.9% |
| **Conservative binary** (loss = 100% of premium) | 0.524 | **−52.9%** | — | — |

**The gap between these IS the lesson.** On J's *realized* exits (the optimistic bound, which assumes
the disciplined chart-stop always holds) the edge is thin: full Kelly is just 7.7% of bankroll, so the
*prudent* half-Kelly is **3.9%**. But on the *conservative binary* (a loss = the whole premium, the genuine
0DTE-to-zero outcome if a stop fails to fire) the Kelly fraction is **negative** — i.e. **there is no edge
to bet at all unless the tight exit holds.** The truth lives between: **the edge exists only because J cuts
losers**, so the position must be the **smallest viable size**, sized at **≤ ½ Kelly on the optimistic basis**.

Half-Kelly (3.9% of $2K ≈ **$78**) translates to roughly:

| OTM-3 premium | Half-Kelly contracts at $2K |
|---|---|
| $0.30 | 2.6 |
| $0.40 | 1.9 |
| $0.50 | 1.5 |

So **half-Kelly is ~2 contracts** at typical OTM-3 premiums. The doctrine **min-3 floor sits just above
half-Kelly** — defensible, but only at the cheap end of the premium band (see §5).

---

## 5. Account math — is min-3 prudent on a $2K account?

3 contracts at OTM-3 (~$0.30–$0.50) with full premium at risk:

| Premium | 1 contract | 2 contracts | **3 contracts (floor)** |
|---|---|---|---|
| $0.30 | $30 (1.5%) | $60 (3.0%) | **$90 (4.5%)** |
| $0.40 | $40 (2.0%) | $80 (4.0%) | **$120 (6.0%)** |
| $0.50 | $50 (2.5%) | $100 (5.0%) | **$150 (7.5%)** |

- **min-3 = 4.5–7.5% of $2K** at full risk. That is **prudent at $0.30–$0.40** (≤6%), and **borderline at
  $0.50** (7.5%). Half-Kelly on the optimistic basis is 3.9% (~$78 ≈ 2 contracts), so min-3 is a slightly-
  larger-than-Kelly bet — acceptable for a structure that *requires* 2 TP + 1 runner, **provided the premium
  is capped** so the dollar risk stays in the prudent band.
- The existing `v15_max_premium_pct_of_account` for $0–2K is **40%** ($800) — that is a *leverage* cap (it
  stops 15× ITM disasters) but it is **far too loose to bound the per-trade risk of the floor**. 3 contracts
  never approaches 40%; the binding constraint should be a per-trade premium ceiling around **6% of equity**.

### Recommendation (a): min-3 vs flat-2 — **KEEP MIN 3**

- **Do not lower to flat-2.** Flat-2 is marginally more Kelly-prudent (≈ half-Kelly) but it **breaks the
  2-TP + 1-runner structure** that the entire exit doctrine (TP1 fraction, runner, profit-lock) is built on.
  A 2-lot can do 1 TP + 1 runner but loses the staged-scale-out that the chart-stop-primary exits assume.
- **Do not raise the floor.** flat-3+ is already a loser; there is zero evidence larger base size is safe.
- **The fix is a CEILING, not a smaller floor.** Keep `min_contracts = 3`, and **tighten the per-trade
  premium cap to ~6% of equity** at the $0–2K tier so 3 contracts at OTM-3 stays in the prudent zone and
  the account can never put 3 *expensive* contracts (e.g. $0.50+) at >7% risk. (This is a tightening of
  `v15_max_premium_pct_of_account[$0-2K]` from 0.40 → ~0.06, evaluated separately — flagged here, not changed.)

---

## 6. Recommendation (b): the POST-LOSS THROTTLE — design (propose-only)

**ADD it.** It is the single highest-value sizing change J's data supports: it directly neutralises the
revenge-sizing of §3 and caps the larger-lot bands of §1–§2 where the account bleeds — *without* touching
the floor that the exit structure needs.

### Behaviour

While the account is **underwater on the session OR coming off a loss**, size is **clamped to the floor**
(`min_contracts`). It cannot be sized up into a losing streak. Size restores automatically on the **next
session** (counters reset at start-of-day) and after **any win** (the consecutive-loss counter resets).

### Inputs (new — all fail-closed like every other `check_order` input)

| Input | Meaning |
|---|---|
| `consecutive_losses_today: int` | Losing round-trips since the last win, this session. |
| `realized_pnl_today: float` | Session realized P&L (negative ⇒ underwater). |
| `equity`, `start_of_day_equity` | Already inputs — the trajectory vs SoD. |

### Proposed params (`params.json`, both accounts, symmetric per C9/L42/L49)

| Param | Default | Meaning |
|---|---|---|
| `post_loss_throttle_enabled` | `true` | Master switch. |
| `throttle_after_consecutive_losses` | `1` | Clamp after the **first** loss of the session. |
| `throttle_underwater_pct` | `0.0` | Any red session (equity < SoD) ⇒ clamp. |
| `throttle_to_contracts` | `= min_contracts` | The floor is the clamp target. |

### Rule (pure)

```
qty_ceiling = +inf
if post_loss_throttle_enabled and (
        consecutive_losses_today >= throttle_after_consecutive_losses
     or equity <= start_of_day_equity * (1 - throttle_underwater_pct)):
    qty_ceiling = throttle_to_contracts          # = the floor (min_contracts)

if proposed_qty > qty_ceiling:
    # LIVE GATE: Deny(POST_LOSS_THROTTLE, ...)
    # ENGINE:    clamp proposed_qty = qty_ceiling (so backtest stays continuous)
```

### Reference signature (NOT implemented)

```python
def post_loss_qty_ceiling(
    *,
    equity: float,
    start_of_day_equity: float,
    consecutive_losses_today: int,
    realized_pnl_today: float,
    min_contracts: int,
    params: Mapping[str, Any],
) -> Optional[int]:
    """Per-order contract CEILING from loss state + equity trajectory.

    Returns the ceiling (an int), or None for 'no throttle active'. Pure: no I/O,
    no mutation. Fails closed in the caller — unreadable new inputs => deny.
    """
    ...
```

### Slot-in point in `backtest/lib/risk_gate.py` `check_order`

A **new section between the `FIRST_ENTRY_LOCK` block (§4) and the `MIN_CONTRACTS` block (§5)**:

1. Add `CODE_POST_LOSS_THROTTLE = "POST_LOSS_THROTTLE"` to the stable `CODE_*` set.
2. Add the three new inputs to `check_order`'s keyword args, screened by `_is_bad_number` /
   integer-domain checks **before** any rule reads them (same fail-closed discipline as `equity`,
   `proposed_qty`, etc. — uncertainty ⇒ deny).
3. Compute `qty_ceiling = post_loss_qty_ceiling(...)`. If `qty_ceiling is not None and proposed_qty >
   qty_ceiling` ⇒ `Deny(CODE_POST_LOSS_THROTTLE, ...)`. Then fall through to the existing `MIN_CONTRACTS`
   floor check (so floor and ceiling compose: ceiling clamps *down*, floor rejects *under*).
4. The engine path (orchestrator / `simulator_real`) consumes the **ceiling** as a **clamp** (reduce qty),
   so backtests stay continuous; only the live gate hard-denies.

### Invariant (OP-32 scar — load-bearing)

The throttle is **order-only**. Like every other rule in `risk_gate`, it returns a `RiskDecision` value
and **never** touches a session, process, or the scheduler. `_assert_never_locks_human` stays true. The
human always holds the off-switch.

### Why default-on (engine) but conservative defaults

`throttle_after_consecutive_losses = 1` + `throttle_underwater_pct = 0.0` is the **strongest** form
(clamp the moment you are red or have taken one loss). That is the right default given §3 shows trades
**after a same-day loss are −$11,304 / WR 36.8%**. If validation (a forward A/B on the engine, separate
step) shows the clamp leaves edge on the table, loosen `throttle_after_consecutive_losses` to 2 — a single
knob, no structural change.

---

## 7. What changes live? — NOTHING (this is the propose step)

| Artifact | Touched? |
|---|---|
| `risk_gate.py` `check_order` | **No** — throttle is designed, not wired. |
| `params.json` (Safe + Bold) | **No** — `min_contracts`, premium caps unchanged. |
| `heartbeat.md` / `heartbeat_aggressive` | **No.** |

**Next steps (separate ratification, after-hours):**
1. Implement `post_loss_qty_ceiling` as a pure function + unit tests (each branch + fail-closed inputs),
   wire into `check_order` behind `post_loss_throttle_enabled`.
2. Forward A/B the **clamp** on the engine (real-fills) to confirm it does not regress edge_capture
   (J-edge no-regression gate) before turning the live deny on.
3. Tighten `v15_max_premium_pct_of_account[$0-2K]` 0.40 → ~0.06 (per §5) as its own scorecard.

These are J's open calls answered with his own ledger, not guesswork.
