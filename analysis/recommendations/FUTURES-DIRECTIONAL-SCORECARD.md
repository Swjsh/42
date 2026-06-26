# Futures Directional Scorecard — the theta-free arena (MNQ/MES)

> **Question:** ~27 strategies died on 0DTE SPY OPTIONS. The documented failure mode
> (C3 / L58, L74, L100-101, L112, L136, L148-149 — ~20 lessons) is **0DTE theta + premium-stop
> misfire eating real DIRECTIONAL edges**. Futures have NO theta — a point move IS P&L and
> winners can RUN. This re-runs the SAME signals on real micro-futures 5m bars with a pure
> point-P&L model (`pnl=(exit-entry)*point_value*qty-costs`), intraday-only, ATR trailing
> stops so trend winners run. Honest gates: OOS per-trade>0 AND beats random-null AND positive
> in >=60% quarters AND survives real costs.

**Model:** 1 micro, commission $1.24 RT, 1 tick slippage each side. Point values: MNQ $2.0/pt, MES $5.0/pt. Signal math ported byte-identical from the option harnesses; only the P&L model changed.

## MES  (367 days, 2025-01-02 → 2026-06-12; OOS from 2026-01-07, 111 OOS days)

| Strategy | Exit | N | WR% | Full $ | /trade | OOS N | OOS /trade | Null /trade | Beats null | +Q | /week $ | MaxDD | PF | Verdict |
|---|---|--:|--:|--:|--:|--:|--:|--:|:-:|:-:|--:|--:|--:|:-:|
| vwap_continuation | atr_trail | 158 | 34.2 | -468.0 | -2.96 | 49 | -14.93 | -11.0 | n | 2/6 | -6.16 | -1281.0 | 0.93 | **FAIL** |
| bull_tilt | atr_trail | 366 | 32.5 | -1726.0 | -4.71 | 111 | -2.83 | -8.1 | Y | 2/6 | -22.71 | -1880.0 | 0.88 | **FAIL** |
| ema_adx | atr_trail | 135 | 31.1 | -1379.0 | -10.22 | 37 | -21.07 | -7.63 | n | 0/6 | -18.14 | -1639.0 | 0.66 | **FAIL** |
| orb | atr_trail | 224 | 37.5 | -871.0 | -3.89 | 69 | -2.0 | 1.62 | n | 2/6 | -11.46 | -1309.0 | 0.89 | **FAIL** |
| rsi2 | atr_target | 1120 | 30.4 | -4130.0 | -3.69 | 337 | -3.69 | -3.73 | Y | 1/6 | -54.34 | -4129.0 | 0.75 | **FAIL** |

## MNQ  (367 days, 2025-01-02 → 2026-06-12; OOS from 2026-01-07, 111 OOS days)

| Strategy | Exit | N | WR% | Full $ | /trade | OOS N | OOS /trade | Null /trade | Beats null | +Q | /week $ | MaxDD | PF | Verdict |
|---|---|--:|--:|--:|--:|--:|--:|--:|:-:|:-:|--:|--:|--:|:-:|
| vwap_continuation | atr_trail | 158 | 35.4 | 518.0 | 3.28 | 39 | -11.91 | -3.71 | n | 3/6 | 6.82 | -1446.0 | 1.05 | **FAIL** |
| bull_tilt | atr_trail | 366 | 33.3 | -1750.0 | -4.78 | 111 | -11.77 | -6.82 | n | 2/6 | -23.03 | -3116.0 | 0.93 | **FAIL** |
| ema_adx | atr_trail | 120 | 35.0 | -409.0 | -3.41 | 33 | 3.72 | -3.66 | Y | 3/6 | -5.38 | -1487.0 | 0.94 | **FAIL** |
| orb | atr_trail | 207 | 38.2 | 15.0 | 0.07 | 66 | 19.6 | 5.5 | Y | 2/6 | 0.2 | -1686.0 | 1.0 | **FAIL** |
| rsi2 | atr_target | 1080 | 33.0 | -1647.0 | -1.53 | 332 | 3.23 | -2.52 | Y | 4/6 | -21.67 | -4189.0 | 0.94 | **FAIL** |

## Verdict

**No directional strategy clears the honest gates on either MES or MNQ.** Removing theta did NOT, by itself, rescue these signals after realistic micro-futures costs — the trailing-stop trend exits still net out at-or-below the random-entry null on OOS data. See per-strategy rows above for where each one fails (OOS sign, null, quarters).

---

## Did we condemn the thesis on one arbitrary exit? No — we swept it.

The headline table uses one exit config (1.5-ATR stop / 2.5-ATR trail). To avoid killing the
"let winners run" thesis on a single param choice, we swept **(ATR-stop × ATR-trail)** over the
grid {0.75, 1.0, 1.5, 2.0} × {1.0, 1.5, 2.0, 3.0} for all four trend strategies on both symbols,
and **(stop × target)** for RSI(2) mean-reversion. Full results in the console log; the decisive
facts:

**MES (S&P micro): negative in EVERY cell, every strategy, full-period.** Not one (stop, trail)
combination prints positive over 17 months for any signal. MES intraday range is too small relative
to its $5/pt cost structure — the $5/pt multiplier means the same point move costs 2.5× the slippage
drag of MNQ. MES is dead for these signals regardless of exit tuning.

**MNQ (Nasdaq micro): a few cells go OOS-positive, but they are a BULL-REGIME ARTIFACT, not edge.**
The only positive cells require a **wide 3.0-ATR trail** (which barely ever triggers intraday, so
most exits are EOD) AND they share one fatal tell — **the in-sample (2025) half is negative or zero**:

| MNQ cell (best-looking) | IS /trade (2025) | OOS /trade (2026) | OOS−null | full /trade | by-quarter |
|---|--:|--:|--:|--:|---|
| vwap stop2.0/trail3.0 | **−$0.4** | +$53.0 | +$3.5 | +$12.8 | 25Q1 **−1868**, 25Q2 +1709, 25Q3 −287, 25Q4 +402, 26Q1 +913, 26Q2 +1152 |
| orb stop1.0/trail3.0 | **−$4.4** | +$25.1 | +$6.4 | +$5.0 | 25Q3 −421, **26Q2 +1393** (≈ all of it) |
| ema_adx stop1.5/trail1.5 | **−$5.3** | +$9.4 | **−$15.3** (fails null) | −$1.2 | mixed, full negative |
| bull_tilt stop2.0/trail3.0 | **−$0.1** | +$13.5 | **−$1.4** (fails null) | +$4.0 | 25Q1 **−2074**, swingy |

Read the IS column. **Every "winner" earned nothing (or lost) on 2025 data and only "worked" in the
last 30% of the sample** — Jan–Jun 2026, when the Nasdaq trended hard up. A wide trailing stop on a
long-biased signal will always flatter a trending OOS window: it's measuring "Nasdaq went up while I
held longs with a loose leash," not a repeatable entry edge. Two of the four also **fail their own
random-long null** (ema_adx, bull_tilt), and the two that "beat" it (vwap +$3.5, orb +$6.4) beat a
null that is itself riding the same bull regime — a margin inside the noise of a 30-replicate null.
This is the exact IS-negative / OOS-positive / single-quarter-concentration pattern the anti-2.10
gates exist to reject (C4 / L01, L04, L05, L22, L122; C22 regime-fragility).

**RSI(2) mean-reversion (small ATR target):** MES negative in every (stop, target) cell; MNQ
full-period negative in every cell (best −$0.7/trade) with the same small OOS-only positive
concentrated in 2026. The mean-reversion class fails too.

## Why theta-removal did not rescue them — the real diagnosis

The signals DO behave like trend-following on futures: avg win ≈ 2× avg loss (MNQ vwap: +$200 win /
−$105 loss), winners ran ~18–30 bars. **The killer is not the payoff ratio — it's the hit rate.**
Win rate sits at **30–38%** across the trend strats, and a 2:1 payoff at a 33% hit rate is a
coin-flip *before* costs; after $1.24 commission + 1-tick slippage each side it tips negative. The
signals are simply **not selective enough** — the entries fire on too much noise. 0DTE theta was one
tax that killed them; on futures the tax is gone, but **the underlying signals never had a positive
raw directional expectancy to begin with** on these 5m bars. Removing theta exposed that the entry
edge was thin-to-absent, not merely theta-masked.

This is consistent with — and sharpens — the doctrine: the documented J-edge is **one specific
high-selectivity setup** (vwap_continuation, BEARISH_REJECTION_RIDE_THE_RIBBON), not a generic
EMA-cross / ORB / RSI(2) firing daily. Those generic textbook signals don't carry an edge on SPX/NDX
intraday in either instrument wrapper.

## Tradeability on the $2K micro account

Moot — nothing is tradeable, but for the record: 1 MNQ micro day-trade margin runs ≈ $50–$1,500
depending on broker/regime; 1 MES ≈ $40–$1,300. A $2K account could hold 1 micro comfortably. Even
the cherry-picked MNQ vwap cell at +$12.8/trade × ~9 trades/week ≈ **+$115/week** — but its IS half
is flat and it's regime-dependent, so paper-forwarding it would most likely give back to the mean.
**Recommendation: do NOT allocate the $2K micro account to any of these directional signals.** They
are not edges; they are a loose long leash in a bull tape.

## Bottom line (LOUD, both directions)

- **The theta-rescue hypothesis is FALSIFIED for this signal set.** Trend-following did *not* print
  on futures where 0DTE theta killed it. On MES it's negative everywhere; on MNQ the only positives
  are an IS-negative, single-regime, wide-trail artifact that fails or barely-beats its own
  random-long null.
- **This is still valuable:** it tells us the 0DTE deaths were **not purely a theta problem** — the
  generic directional signals (EMA-cross, ORB, RSI2, morning bull-tilt) lack raw entry edge on 5m
  index bars, period. Theta was a second tax on top of a weak signal, not the sole cause.
- **Where the real money question still lives:** the *selective* J-edge setups (vwap_continuation as
  a discretionary pattern, bearish-rejection-ride-the-ribbon) on futures with a trend-riding exit are
  the only thing worth a future look — but they need J's actual entry discipline (confluence /
  sequence rejection), not the daily-firing mechanical proxy tested here. A mechanical daily signal
  is the wrong unit; the edge is in the selection, which this test deliberately did not encode.

> Reproduce: `backtest/.venv/Scripts/python.exe backtest/autoresearch/_futures_directional.py`
> Raw JSON (all metrics, by-quarter, nulls): `analysis/recommendations/futures-directional-2026-06-21.json`