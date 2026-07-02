# analysis/j-webull — Fresh-eyes re-analysis of J's WeBull history (2021–2023)

> Generated 2026-07-01 per J's directive: "Revisit my traits from my WeBull history with a
> fresh set of eyes." Everything here is RE-DERIVED from the raw CSVs — nothing inherited
> from the 2026-06-19 Opus pass (`markdown/0dte/J-WEBULL-EDGE-2021-2023.md`), which is used
> only as a contrast baseline. P&L in this dataset is J's ACTUAL fills (real money) — it is
> its own authority; only counterfactual replays need OPRA real-fills (C1).

## Files

| File | What |
|---|---|
| `trades-normalized.csv` | **The engine-consumable dataset.** One row per flat→flat round-trip (all 1,099 episodes, all underliers) with market context at entry. |
| `traits.json` | Full machine-readable trait statistics (population = 567 closed SPX/SPY-family episodes). |
| `TRAITS-REPORT.md` | Human-readable fresh trait profile + confirm/revise verdicts vs the prior analysis. |
| `EXPERIMENTS.md` | Ranked fine-tuning experiments the project can run next (specs only, not run). |
| `cache/spy_5m_2021-06-01_2023-10-31.csv` | SPY 5m bars (Alpaca IEX, raw, 52,599 bars) used for the context join. |
| `cache/spy_daily_2021-06-01_2023-10-31.csv` | SPY daily bars (610) for prior-day levels. |
| `scripts/` | Reproduction pipeline (see below). |

## Reproduce

```powershell
cd C:\Users\jackw\Desktop\42
backtest\.venv\Scripts\python.exe analysis\j-webull\scripts\fetch_spy_bars.py     # idempotent (cache hit)
backtest\.venv\Scripts\python.exe analysis\j-webull\scripts\build_normalized.py  # -> trades-normalized.csv
backtest\.venv\Scripts\python.exe analysis\j-webull\scripts\traits_report.py     # -> traits.json
```

## Round-trip definition (differs from the prior miner — deliberately)

A row = a **position episode**: first buy from flat → back to flat (FIFO per option symbol).
The prior miner counted one round-trip per SELL fill and banded by the *sell-fill* qty. That
definition credits partial exits of BIG positions to the small-size band — see
`TRAITS-REPORT.md` §"The +$4,576 artifact". Reconciliation: replicating the prior method on
this parse reproduces its numbers to the dollar (1-2 band +$4,576, 3-5 band −$13,975, 6-10
band −$3,486), so the raw parse is identical; only the unit of analysis changed.

- Leftover 0DTE lots with no sell = expired worthless (full premium loss, closed).
- Leftover longer-dated lots = `closed=False` (P&L NaN, excluded from stats). 20 rows.
- 10 anomalies (sell-without-open / sell-overflow) skipped/clipped, not counted as trades.

## trades-normalized.csv schema

| Column | Meaning |
|---|---|
| `episode_id` | Stable index, ordered by entry time |
| `entry_ts_et`, `exit_ts_et` | First buy fill / flattening sell fill, naive ET |
| `underlying`, `strike`, `right`, `expiry` | OCC contract fields (right: C/P) |
| `dte`, `is_0dte` | Days to expiry at entry |
| `is_family` | underlying ∈ {SPY, SPX, SPXW, XSP} — the analysis population |
| `bias` | bull (calls) / bear (puts) |
| `qty` | **Max open contracts** during the episode (the honest size measure) |
| `n_adds`, `scaled_in`, `n_buy_fills`, `n_sell_fills` | Add/scale-out structure |
| `entry_px` | Weighted average buy price; `exit_px` weighted average sell price |
| `premium_at_risk` | buy_cost × 100 ($) |
| `pnl` | Realized $ (actual fills); `ret_pct` premium return %; `hold_min` minutes |
| `size_band` | 1-2 / 3-5 / 6-10 / 11+ on `qty` |
| `tod_bucket` (30-min ET), `dow` | Entry timing |
| `ctx_ok` | Market-context join succeeded (SPY family + a completed 5m bar before entry) |
| `spy_px` | SPY close of last COMPLETED 5m bar before entry (C6: no look-ahead) |
| `vwap`, `vwap_side`, `vwap_dist_pct` | Session-cumulative VWAP (RTH, IEX volume) |
| `ribbon_state`, `ribbon_dist_pct` | EMA8 vs EMA21 on RTH-continuous 5m closes |
| `sess_range_pos` | (spy−LOD)/(HOD−LOD) so far, 0=low 1=high |
| `prior_30m_pct`, `mins_since_open`, `open_gap_pct` | Momentum/timing context |
| `nearest_level`, `nearest_level_dist_pct`, `pdh/pdl/pdc` | Prior-day levels from daily bars |
| `moneyness_pct` | (strike/spot_equiv − 1)×100; `otm_pct` signed so +=OTM for the trade's direction |

## Data-quality caveats

1. **The "2023" export embeds 1,890 exact rows of 2022 data** — cross-file dedup is mandatory
   (4,818 raw → 2,928 rows → 2,414 filled). Zero within-file duplicates.
2. **IEX feed is thin in 2021–2022** (some o=h=l=c bars); VWAP uses IEX volume and is an
   approximation of tape VWAP. Directionally sound, not tick-accurate.
3. **SPX/XSP spot is approximated** as 10×SPY / 1×SPY for moneyness (drift ~±0.3%);
   `moneyness_pct` for non-SPY rows is coarse — use bands, not point values.
4. **No option price paths** — MAE/MFE and stop-touch counterfactuals from this dataset alone
   are bounds, not sims. Real counterfactuals need the OPRA replay (see EXPERIMENTS.md).
5. Context-join coverage: **95.6%** of closed family episodes (`ctx_ok=True`); misses are
   entries before the first completed 5m bar or bars missing from IEX.
6. This is a **different era and instrument scale** (2021–2023 SPX/XSP, mostly) than the
   live 2026 SPY engine — port setup STRUCTURE, never absolute levels/premiums (cf. C22).
