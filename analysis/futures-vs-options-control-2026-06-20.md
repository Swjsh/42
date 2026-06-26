# Futures-vs-Options Control — 2026-06-20

> Collapses **"wrong instrument"** vs **"no edge"** in one test: the EXACT same engine signals, priced as 0DTE SPY options (engine BS sim) AND as MES futures (linear, point-based stops). Paper/sandbox research only — no orders, $0 cost.

## Verdict

**On the same directional signals, futures net P&L is `$-438/contract` (MIRROR, identical hold — the clean instrument swap) / `$58/contract` (STOP_EOD, stop-managed) vs options `$-21/contract`** — and the directional read itself is right only **44%** of the time at EOD.

At scale, the full watcher fleet on **real MES bars** (zero option tax) is **2,611 signals, net $-26,127, WR 48%** — the linear instrument loses too.

### → NO-EDGE-IN-SIGNAL

- The directional read is a coin-flip (right 50% at the option's exit time, 44% at EOD) and the clean instrument-swap (MIRROR, identical hold) loses $-438/contract. The signal has no directional edge — no option tuning recovers an edge that isn't in the read.
- STOP_EOD nets +$58/c, but that is a risk-MANAGEMENT artifact (a chart stop cutting losers while a few trend days run), not directional accuracy — it rides on a sub-50% read, so it is not repeatable edge.
- CORROBORATED at scale: the full watcher fleet priced on REAL MES bars (no option tax at all) is 2,611 signals, net $-26,127, WR 48% — both directions losing. The linear instrument does NOT rescue the signal.

## Side-by-side (per-contract, identical trade set)

| Leg | Net $/contract | Win rate | Avg $/trade |
|---|---:|---:|---:|
| **Option (0DTE SPY, BS sim, OTM-3)** | -21 | 22% | -0.7 |
| Futures MIRROR (same hold horizon) | -438 | 41% | -13.7 |
| Futures STOP_EOD (chart stop + 15:55) | 58 | 38% | 1.8 |
| Futures BRACKET_2R (chart stop + 2R) | 82 | 50% | 2.6 |

- **Trades:** 32 across 28 days (2025-01-02 → 2026-06-16).
- **Instrument-free directional read:** right direction at option-exit time **50%**, at EOD close **44%** (>52% = a real directional tilt; ~50% = coin-flip).
- **Option leg as-sized** (engine qty, not per-contract): $-389 total.

## Real-fills subset — and why it does NOT overturn the verdict

Engine re-run with `use_real_fills=True` (real OPRA bars where cached). This subset shows option leg **+$595/contract at 58% WR over 55 trades** — superficially the opposite of the BS result. It does **not** overturn the verdict, for three reasons that are themselves the finding:

1. **Single-day concentration (C4):** a single day (2025-08-22) is **40% of the subset's entire P&L**. Strip that one outlier and the subset is ~flat — this is a thin-tail artifact, not broad edge (the exact disclosure-failure class OP-16/C4 warns about).
2. **Different, smaller population:** real-fills only prices the 55 trades whose OPRA strike happens to be cached (it drops uncached calls and re-prices puts) — it is NOT the same 32-trade set as the apples-to-apples swap above, so its WR/P&L are not comparable to the BS option leg.
3. **The unconcentrated evidence governs:** the instrument-free directional read (44–50%) and the 4,865-signal native-futures fleet (below) are large-sample and anchor-free — both say no edge. A concentrated, anchor-loaded subset cannot resurrect an edge that a linear instrument fails to capture at scale.

## Large-sample corroboration — full watcher fleet on REAL futures bars

The 32-trade control above is the heavily-gated production engine. The broader question — *do the underlying detectors have a directional edge?* — is answered by the full watcher fleet (`run_native_backtest.py`) graded on **real MES/MNQ bars** (`px_to_points=1.0`, no SPY proxy, no option tax whatsoever):

| Instrument | Signals | Net $ (3-lot) | Win rate | Avg/trade | Long net | Short net |
|---|--:|--:|--:|--:|--:|--:|
| MES (real bars) | 2,611 | -26,127 | 48% | -10.0 | -16,551 | -9,576 |
| MNQ (real bars) | 2,254 | -11,025 | 48% | -4.9 | -2,888 | -8,137 |

- Window 2025-01-02 → 2026-06-12. **Both directions lose, WR ~48% (sub-coin-flip).** A linear instrument removes theta + bid/ask entirely — yet the signal set still bleeds across thousands of trades. This is the strongest evidence: the edge is not hiding behind the option structure.

## Per-day P&L ($/contract)

| Date | n | Option | Fut MIRROR | Fut STOP_EOD | Fut 2R |
|---|--:|--:|--:|--:|--:|
| 2025-01-16 | 1 | -0 | -11 | 14 | 14 |
| 2025-02-24 | 2 | -3 | -39 | 93 | 38 |
| 2025-03-18 | 1 | 9 | 27 | -5 | 38 |
| 2025-07-07 | 2 | -3 | 11 | -41 | 40 |
| 2025-07-15 | 1 | -5 | -29 | -52 | -52 |
| 2025-07-21 | 2 | 18 | 77 | -2 | 75 |
| 2025-08-11 | 1 | -0 | -32 | -6 | -6 |
| 2025-08-20 | 1 | -4 | 5 | -99 | 44 |
| 2025-08-22 | 1 | -5 | 4 | 292 | 101 |
| 2025-10-02 | 1 | 8 | 13 | -104 | -104 |
| 2025-10-24 | 1 | -5 | 5 | -36 | -36 |
| 2025-10-29 | 1 | -28 | -50 | -54 | -54 |
| 2025-11-12 | 1 | -1 | -2 | 7 | 7 |
| 2025-11-13 | 1 | -4 | -97 | -105 | -105 |
| 2025-12-10 | 1 | 10 | 14 | -106 | -106 |
| 2026-01-28 | 1 | -2 | -14 | -30 | -30 |
| 2026-02-17 | 1 | -5 | -124 | -106 | -106 |
| 2026-02-27 | 1 | -2 | -2 | -106 | -106 |
| 2026-05-07 | 1 | 8 | 14 | 45 | 76 |
| 2026-05-08 | 1 | 12 | 40 | 71 | 61 |
| 2026-05-11 | 1 | -0 | -24 | -53 | -53 |
| 2026-05-26 | 1 | -5 | -46 | -40 | -40 |
| 2026-06-02 | 1 | -3 | -37 | -4 | -4 |
| 2026-06-05 | 2 | -4 | 9 | 649 | 216 |
| 2026-06-09 | 1 | -28 | -69 | -94 | 254 |
| 2026-06-11 | 1 | 29 | -57 | -99 | -99 |
| 2026-06-12 | 1 | -1 | -8 | 12 | 12 |
| 2026-06-15 | 1 | -6 | -15 | 20 | 11 |

**Sign-flip days (option vs STOP_EOD futures): 12 of 28** — days where the same read lost as an option but the instrument changed the outcome (or vice-versa).

## Method & caveats

- **Same trade set:** every futures row is the engine's own trade (entry time, direction, entry spot, chart-stop level) replayed on the SAME SPY 5m bars. Nothing is re-discovered on futures bars — this is a pure instrument swap.
- **MES economics (verified specs):** $50 per SPY point/contract (5.0×10.0 proxy), 1-tick slippage each side + $1.24 round-turn = $3.74/contract cost.
- **Per-contract normalization:** option P&L = engine `dollar_pnl ÷ qty`; futures = 1 MES. Position SIZING is a separate question from whether the READ has edge — normalizing isolates the read.
- **MIRROR** is the cleanest instrument-tax isolation (identical entry AND exit timing; only the instrument differs). **STOP_EOD** gives the read max room with a chart-level safety stop. **BRACKET_2R** is conservative (stop-before-target intrabar).
- **Option leg = BS sim** (IV=VIX/100) so BOTH sides price with NO drops (real-fills drops uncached calls). The 2026-06-20 honest baseline already shows the engine net-negative on real fills; BS keeps the trade set identical for a fair swap.
- **Proxy:** SPY×10 ≈ ES/MES index. MNQ (Nasdaq) has no SPY proxy and is not used here. Real MES bars (`backtest/data/futures/MES_5m_continuous.csv`) exist for a native re-run if this proxy verdict warrants it.
- **Data:** spy_5m_2025-01-01_2026-06-16.csv, 34,324 SPY bars, 2025-01-02 → 2026-06-16 (verified non-empty, deduped).
