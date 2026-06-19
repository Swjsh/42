# J's Real Webull WINNERS — Journaled Ground Truth

> **Data rules:** these are J's REAL winning Webull fills (2021-2023), journaled in the canonical `trades.csv` schema as first-class ground truth — the foundation the automation is built from.
> Canonical CSV: [`journal/j-real-winners.csv`](j-real-winners.csv) (schema-identical to `trades.csv`; `account_id=j_webull_hist` so it NEVER pollutes the live journal).
> Source ledger: `analysis/webull-j-trades/j_roundtrips.csv`. Setup context: SPY 5m IEX bars (SPX/SPY ~10:1), reconstructed look-ahead-free at J's entry bar via `backtest/autoresearch/webull_winner_setups.py`.
> Generated 2026-06-19. Propose-only — touches no live engine / params (Rule 9).

## Scope + honesty

- **313 SPX/SPY-family winners** journaled (total realized +$37,974).
- **294 are 1-2 lot** — J's genuine edge (per L168), the ground truth to replicate. **19 are 3+ lot** — flagged `size_class=3plus_lot` (less representative; J's documented losing zone).
- Setup context reconstructed for **313**; **0** marked `candles_unavailable` (SPY bars unreachable; trade still journaled with its fields).
- **Era caveat:** 2021-23 SPX-scale options, SPY-proxy candles, no chain greeks (delta is an ITM/ATM/OTM moneyness tag, not a real greek). Validate any derived rule on the full population first (lesson C24 — anchor winners can be one-off exceptions).

## The signature of J's winners (profile)

### Size class

| size | n | share |
|---|---|---|
| 1-2_lot | 294 | 94% |
| 3plus_lot | 19 | 6% |

### Direction

| direction | n | share |
|---|---|---|
| bull (calls) | 161 | 51% |
| bear (puts) | 152 | 49% |

### Time-of-day (entry)

| tod_bucket | n | share |
|---|---|---|
| MORNING | 185 | 59% |
| MIDDAY | 95 | 30% |
| AFTERNOON | 33 | 11% |

### Archetype  (of 313 reconstructed)

| archetype | n | share |
|---|---|---|
| momentum-breakout | 127 | 41% |
| pullback-continuation | 82 | 26% |
| reversal-off-extreme | 60 | 19% |
| trend-continuation | 44 | 14% |

### Trigger

| trigger | n | share |
|---|---|---|
| breakout | 129 | 41% |
| pullback | 82 | 26% |
| reclaim | 61 | 19% |
| rejection | 41 | 13% |

### VWAP alignment at entry

| vwap_side | n | share |
|---|---|---|
| below | 164 | 52% |
| above | 149 | 48% |

## Per-trade digest (sorted by P&L)

| Date | Underlier | Dir | Qty | Entry→Exit ET | Hold | Entry→Exit px | P&L | Archetype | Trigger | VWAP | Nearest lvl | Ctx |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2023-06-01 | SPXW | bull | 1 | 10:31->10:47 | 16m | 2.25->7.5 | +$525 | pullback-continuation | pullback | above | ROUND@418 | OK |
| 2022-03-14 | SPXW | bear | 1 | 11:20->11:43 | 23m | 4.9->9.9 | +$500 | reversal-off-extreme | rejection | above | ROUND@422 | OK |
| 2022-05-02 | SPXW | bull | 1 | 10:25->10:31 | 6m | 4.1->8.7 | +$460 | momentum-breakout | breakout | above | ROUND@414 | OK |
| 2023-06-02 | SPXW | bull | 1 | 10:10->11:02 | 52m | 2->6.5 | +$450 | trend-continuation | reclaim | above | ROUND@426 | OK |
| 2022-06-06 | SPXW | bear | 1 | 11:11->11:18 | 7m | 2.55->7 | +$445 | pullback-continuation | pullback | below | SESSION_OPEN@414.8 | OK |
| 2022-07-22 | SPXW | bear | 1 | 13:18->13:35 | 17m | 3.2->7.2 | +$400 | momentum-breakout | breakout | below | ROUND@396 | OK |
| 2022-05-12 | SPXW | bear | 1 | 11:16->11:54 | 38m | 4.2->8.1 | +$390 | reversal-off-extreme | rejection | above | ROUND@394 | OK |
| 2022-07-27 | SPXW | bull | 2 | 14:21->14:35 | 14m | 2.35->4.3 | +$390 | trend-continuation | reclaim | above | ROUND@396 | OK |
| 2023-05-30 | SPXW | bear | 1 | 10:57->11:21 | 24m | 3.5->7.4 | +$390 | trend-continuation | rejection | below | ROUND@421 | OK |
| 2022-06-03 | SPXW | bull | 1 | 11:26->13:04 | 98m | 2.4->6.1 | +$370 | reversal-off-extreme | reclaim | below | ROUND@410 | OK |
| 2022-07-22 | SPXW | bear | 1 | 11:23->11:37 | 15m | 2.3->6 | +$370 | momentum-breakout | breakout | below | ROUND@397 | OK |
| 2022-06-06 | SPXW | bear | 1 | 11:11->11:17 | 6m | 2.55->6.1 | +$355 | pullback-continuation | pullback | below | SESSION_OPEN@414.8 | OK |
| 2022-08-01 | SPXW | bull | 1 | 14:48->14:58 | 10m | 1->4.5 | +$350 | reversal-off-extreme | reclaim | below | ROUND@410 | OK |
| 2022-08-01 | SPXW | bull | 1 | 09:50->10:06 | 16m | 3.2->6.6 | +$340 | momentum-breakout | breakout | above | ROUND@411 | OK |
| 2022-08-30 | SPXW | bear | 1 | 09:47->10:05 | 19m | 4.9->8.3 | +$340 | momentum-breakout | breakout | below | IDL@402.48 | OK |
| 2022-04-07 | SPXW | bull | 1 | 12:15->14:03 | 108m | 1.7->5 | +$330 | reversal-off-extreme | reclaim | below | ROUND@445 | OK |
| 2023-06-01 | SPXW | bull | 2 | 10:12->10:42 | 29m | 3.4->5.05 | +$330 | momentum-breakout | breakout | above | IDH@418.26 | OK |
| 2023-06-01 | SPXW | bull | 1 | 10:12->10:46 | 34m | 3.4->6.7 | +$330 | momentum-breakout | breakout | above | IDH@418.26 | OK |
| 2022-05-06 | SPXW | bear | 1 | 09:36->09:47 | 11m | 4.6->7.6 | +$300 | momentum-breakout | breakout | below | ROUND@408 | OK |
| 2022-05-09 | SPXW | bear | 3 | 09:34->10:00 | 26m | 3->4 | +$300 | reversal-off-extreme | breakout | above | ROUND@405 | OK |
| 2022-05-11 | SPXW | bear | 2 | 09:33->09:34 | 2m | 4.4->5.9 | +$300 | momentum-breakout | breakout | below | ROUND@397 | OK |
| 2022-05-27 | SPXW | bull | 1 | 13:50->15:06 | 76m | 1.8->4.8 | +$300 | trend-continuation | reclaim | above | ROUND@412 | OK |
| 2022-04-22 | SPXW | bear | 1 | 11:11->11:55 | 44m | 1.6->4.5 | +$290 | trend-continuation | rejection | below | ROUND@433 | OK |
| 2022-09-13 | SPXW | bear | 1 | 09:48->10:01 | 12m | 5.5->8.4 | +$290 | trend-continuation | rejection | below | SESSION_OPEN@401.8 | OK |
| 2022-06-02 | SPXW | bull | 1 | 09:56->10:14 | 18m | 1.9->4.7 | +$280 | reversal-off-extreme | reclaim | below | ROUND@408 | OK |
| 2022-06-03 | SPXW | bull | 2 | 11:26->12:56 | 90m | 2.4->3.8 | +$280 | reversal-off-extreme | reclaim | below | ROUND@410 | OK |
| 2022-04-08 | SPXW | bull | 1 | 10:56->11:04 | 8m | 3.2->5.9 | +$270 | momentum-breakout | breakout | above | ROUND@450 | OK |
| 2022-06-01 | SPXW | bear | 1 | 10:01->10:09 | 8m | 4.2->6.9 | +$270 | momentum-breakout | breakout | below | IDL@414.04 | OK |
| 2022-07-28 | SPXW | bull | 2 | 10:59->11:14 | 15m | 1.95->3.3 | +$270 | pullback-continuation | pullback | above | SESSION_OPEN@401.88 | OK |
| 2022-07-20 | SPXW | bull | 1 | 10:29->10:48 | 19m | 2.4->5 | +$260 | momentum-breakout | breakout | above | ROUND@394 | OK |
| 2022-05-04 | SPXW | bull | 1 | 11:48->12:42 | 53m | 3.3->5.8 | +$250 | pullback-continuation | pullback | below | ROUND@415 | OK |
| 2022-06-02 | SPXW | bull | 1 | 10:24->11:13 | 49m | 1->3.5 | +$250 | reversal-off-extreme | reclaim | below | IDL@407.32 | OK |
| 2022-06-28 | SPXW | bear | 1 | 10:29->10:47 | 18m | 1.9->4.4 | +$250 | pullback-continuation | pullback | below | ROUND@390 | OK |
| 2022-07-05 | SPXW | bull | 1 | 11:55->12:26 | 31m | 3.2->5.7 | +$250 | pullback-continuation | pullback | above | ROUND@375 | OK |
| 2022-07-22 | SPXW | bear | 1 | 11:23->11:44 | 21m | 2.3->4.8 | +$250 | momentum-breakout | breakout | below | ROUND@397 | OK |
| 2022-08-01 | SPXW | bull | 2 | 14:37->14:57 | 20m | 2.35->3.6 | +$250 | pullback-continuation | pullback | below | ROUND@411 | OK |
| 2023-05-31 | SPXW | bear | 1 | 09:36->10:26 | 50m | 3.1->5.6 | +$250 | reversal-off-extreme | rejection | above | IDH@418.77 | OK |
| 2023-09-15 | SPXW | bear | 1 | 10:25->10:59 | 34m | 0.9->3.4 | +$250 | trend-continuation | rejection | below | ROUND@446 | OK |
| 2022-02-24 | SPY | bull | 1 | 12:19->15:51 | 213m | 0.8->3.25 | +$245 | trend-continuation | reclaim | above | ROUND@416 | OK |
| 2022-06-06 | SPXW | bear | 1 | 11:11->11:17 | 6m | 2.55->5 | +$245 | pullback-continuation | pullback | below | SESSION_OPEN@414.8 | OK |
| 2022-01-14 | SPY | bull | 10 | 09:38->09:56 | 17m | 0.31->0.55 | +$240 | momentum-breakout | breakout | above | ROUND@463 | OK |
| 2022-04-27 | SPXW | bear | 1 | 14:48->14:59 | 11m | 1.6->4 | +$240 | pullback-continuation | pullback | above | ROUND@421 | OK |
| 2022-05-05 | SPXW | bear | 1 | 11:01->11:09 | 8m | 4->6.4 | +$240 | pullback-continuation | pullback | below | ROUND@416 | OK |
| 2022-05-10 | SPXW | bear | 2 | 09:35->09:46 | 10m | 4.7->5.85 | +$230 | momentum-breakout | breakout | below | ROUND@404 | OK |
| 2022-06-22 | SPXW | bull | 1 | 10:03->10:14 | 11m | 2.7->5 | +$230 | pullback-continuation | pullback | above | ROUND@373 | OK |
| 2022-07-19 | SPXW | bull | 1 | 10:27->10:50 | 23m | 3.6->5.9 | +$230 | momentum-breakout | breakout | above | ROUND@388 | OK |
| 2022-05-27 | SPXW | bull | 1 | 09:36->09:55 | 19m | 2.55->4.8 | +$225 | momentum-breakout | breakout | above | ROUND@410 | OK |
| 2022-07-08 | SPXW | bull | 1 | 09:58->10:27 | 29m | 2.45->4.7 | +$225 | reversal-off-extreme | reclaim | below | ROUND@386 | OK |
| 2022-02-23 | SPXW | bear | 1 | 10:12->10:26 | 14m | 3.8->6 | +$220 | pullback-continuation | pullback | below | ROUND@430 | OK |
| 2022-04-06 | SPXW | bull | 1 | 13:15->13:45 | 30m | 2->4.2 | +$220 | reversal-off-extreme | reclaim | below | ROUND@445 | OK |
| 2022-07-27 | SPXW | bull | 1 | 14:21->14:36 | 15m | 2.35->4.5 | +$215 | trend-continuation | reclaim | above | ROUND@396 | OK |
| 2022-07-28 | SPXW | bull | 1 | 11:32->11:53 | 21m | 1.9->4 | +$210 | momentum-breakout | breakout | above | IDH@403.84 | OK |
| 2022-09-30 | SPXW | bull | 1 | 10:48->11:09 | 21m | 3.7->5.8 | +$210 | pullback-continuation | pullback | above | ROUND@364 | OK |
| 2023-06-01 | SPXW | bull | 1 | 10:12->10:45 | 33m | 3.4->5.5 | +$210 | momentum-breakout | breakout | above | IDH@418.26 | OK |
| 2023-06-06 | SPXW | bear | 1 | 12:29->12:41 | 11m | 4.3->6.4 | +$210 | reversal-off-extreme | rejection | above | ROUND@428 | OK |
| 2022-05-02 | SPXW | bull | 1 | 10:25->10:35 | 10m | 4.1->6.1 | +$200 | momentum-breakout | breakout | above | ROUND@414 | OK |
| 2022-05-05 | SPXW | bear | 1 | 11:01->11:07 | 6m | 4->6 | +$200 | pullback-continuation | pullback | below | ROUND@416 | OK |
| 2022-05-13 | SPXW | bull | 2 | 09:51->10:03 | 12m | 2.5->3.5 | +$200 | momentum-breakout | breakout | above | ROUND@399 | OK |
| 2022-06-01 | SPXW | bear | 1 | 10:28->10:37 | 10m | 4.3->6.3 | +$200 | momentum-breakout | breakout | below | PDL@410.03 | OK |
| 2022-06-02 | SPXW | bull | 1 | 10:35->11:13 | 38m | 1.3->3.3 | +$200 | trend-continuation | reclaim | above | ROUND@409 | OK |
| 2022-06-13 | SPXW | bear | 2 | 11:00->11:04 | 4m | 4.5->5.5 | +$200 | momentum-breakout | breakout | below | IDL@375.48 | OK |
| 2022-07-14 | SPXW | bull | 1 | 10:23->11:11 | 48m | 3->5 | +$200 | reversal-off-extreme | reclaim | below | ROUND@372 | OK |
| 2023-06-08 | SPXW | bull | 2 | 10:46->11:04 | 18m | 2.4->3.4 | +$200 | momentum-breakout | breakout | above | IDH@427.65 | OK |
| 2022-03-11 | SPY | bear | 3 | 09:49->10:01 | 12m | 0.985->1.65 | +$200 | reversal-off-extreme | rejection | above | SESSION_OPEN@428.15 | OK |
| 2022-06-23 | SPXW | bull | 3 | 09:50->10:57 | 67m | 1.55->2.2 | +$195 | reversal-off-extreme | reclaim | below | ROUND@375 | OK |
| 2022-07-29 | SPXW | bull | 1 | 14:00->15:39 | 99m | 1.45->3.4 | +$195 | pullback-continuation | pullback | above | ROUND@411 | OK |
| 2022-04-21 | SPXW | bear | 1 | 10:20->11:40 | 80m | 2.6->4.5 | +$190 | momentum-breakout | breakout | below | IDL@448.15 | OK |
| 2022-05-06 | SPXW | bear | 1 | 09:36->10:00 | 24m | 4.6->6.5 | +$190 | momentum-breakout | breakout | below | ROUND@408 | OK |
| 2022-07-12 | SPXW | bear | 1 | 09:51->10:00 | 9m | 3->4.9 | +$190 | trend-continuation | rejection | below | ROUND@385 | OK |
| 2022-07-26 | SPXW | bear | 1 | 10:55->11:32 | 37m | 3.6->5.5 | +$190 | momentum-breakout | breakout | below | ROUND@393 | OK |
| 2022-09-01 | SPXW | bear | 1 | 09:40->10:51 | 72m | 3.8->5.7 | +$190 | reversal-off-extreme | rejection | above | SESSION_OPEN@392.84 | OK |
| 2022-07-05 | SPXW | bear | 1 | 09:46->09:56 | 10m | 1.75->3.6 | +$185 | momentum-breakout | breakout | below | ROUND@374 | OK |
| 2022-05-05 | SPXW | bear | 1 | 09:57->10:05 | 8m | 5.9->7.7 | +$180 | momentum-breakout | breakout | below | IDL@421.78 | OK |
| 2022-07-27 | SPXW | bull | 1 | 14:32->14:37 | 5m | 1.7->3.5 | +$180 | trend-continuation | reclaim | above | ROUND@396 | OK |
| 2022-04-27 | SPXW | bear | 1 | 09:50->10:05 | 15m | 4.5->6.2 | +$170 | reversal-off-extreme | rejection | above | ROUND@421 | OK |
| 2022-07-13 | SPXW | bull | 1 | 12:32->13:02 | 30m | 1.4->3.1 | +$170 | pullback-continuation | pullback | above | ROUND@380 | OK |
| 2022-08-25 | SPXW | bull | 2 | 13:18->13:23 | 4m | 2.75->3.6 | +$170 | reversal-off-extreme | reclaim | below | ROUND@416 | OK |
| 2022-07-29 | SPXW | bull | 1 | 14:00->15:04 | 64m | 1.45->3.1 | +$165 | pullback-continuation | pullback | above | ROUND@411 | OK |
| 2022-09-26 | SPXW | bull | 1 | 10:13->10:16 | 3m | 2.35->4 | +$165 | momentum-breakout | breakout | above | IDH@368.97 | OK |
| 2022-02-22 | SPY | bear | 8 | 13:40->13:49 | 9m | 0.5->0.7 | +$160 | momentum-breakout | breakout | below | ROUND@428 | OK |
| 2022-05-09 | SPXW | bear | 1 | 11:10->11:33 | 23m | 2.3->3.9 | +$160 | trend-continuation | rejection | below | ROUND@401 | OK |
| 2022-05-10 | SPXW | bear | 1 | 11:22->11:26 | 4m | 3.5->5.1 | +$160 | pullback-continuation | pullback | below | ROUND@397 | OK |
| 2022-05-23 | SPXW | bear | 1 | 09:53->10:02 | 9m | 2.15->3.7 | +$155 | reversal-off-extreme | rejection | above | SESSION_OPEN@392.94 | OK |
| 2022-06-07 | SPXW | bull | 1 | 10:34->10:38 | 5m | 1.6->3.1 | +$150 | momentum-breakout | breakout | above | ROUND@412 | OK |
| 2022-07-13 | SPXW | bull | 1 | 10:27->10:31 | 5m | 2.3->3.8 | +$150 | reversal-off-extreme | reclaim | below | ROUND@377 | OK |
| 2023-05-30 | SPXW | bear | 1 | 10:57->11:16 | 19m | 3.5->5 | +$150 | trend-continuation | rejection | below | ROUND@421 | OK |
| 2023-06-02 | SPXW | bull | 1 | 10:10->10:49 | 39m | 2->3.5 | +$150 | trend-continuation | reclaim | above | ROUND@426 | OK |
| 2022-05-27 | SPXW | bull | 1 | 09:36->09:49 | 12m | 2.55->4 | +$145 | momentum-breakout | breakout | above | ROUND@410 | OK |
| 2022-01-10 | SPY | bull | 4 | 10:59->11:18 | 19m | 0.63->0.99 | +$144 | reversal-off-extreme | reclaim | below | ROUND@458 | OK |
| 2022-05-26 | SPXW | bull | 1 | 10:35->11:16 | 42m | 2.5->3.9 | +$140 | pullback-continuation | pullback | above | IDH@403.99 | OK |
| 2022-06-07 | SPXW | bull | 1 | 10:32->10:37 | 5m | 2->3.4 | +$140 | momentum-breakout | breakout | above | ROUND@412 | OK |
| 2022-06-09 | SPXW | bear | 1 | 10:07->10:11 | 4m | 3.3->4.7 | +$140 | pullback-continuation | pullback | below | ROUND@410 | OK |
| 2022-06-30 | SPXW | bear | 1 | 09:54->10:03 | 10m | 3.5->4.9 | +$140 | momentum-breakout | breakout | below | IDL@373.84 | OK |
| 2022-08-16 | SPXW | bull | 1 | 13:38->14:03 | 24m | 3.5->4.9 | +$140 | momentum-breakout | breakout | above | ROUND@431 | OK |
| 2022-09-19 | SPXW | bull | 1 | 10:07->10:13 | 6m | 4->5.4 | +$140 | pullback-continuation | pullback | above | ROUND@384 | OK |
| 2023-05-25 | SPXW | bull | 1 | 13:18->13:27 | 9m | 2.8->4.2 | +$140 | trend-continuation | reclaim | above | ROUND@414 | OK |
| 2023-06-07 | SPXW | bear | 1 | 10:34->10:36 | 2m | 3.4->4.8 | +$140 | pullback-continuation | pullback | below | ROUND@428 | OK |
| 2023-09-15 | SPXW | bear | 2 | 10:14->10:52 | 38m | 1.35->2.05 | +$140 | momentum-breakout | breakout | below | ROUND@446 | OK |
| 2023-06-21 | SPXW | bull | 1 | 11:16->11:44 | 28m | 1.6->2.95 | +$135 | reversal-off-extreme | reclaim | below | IDL@434.37 | OK |
| 2022-05-10 | SPXW | bear | 1 | 09:39->09:53 | 14m | 3.9->5.2 | +$130 | momentum-breakout | breakout | below | ROUND@404 | OK |
| 2022-05-26 | SPXW | bull | 1 | 09:41->10:01 | 20m | 2.7->4 | +$130 | momentum-breakout | breakout | above | IDH@401.49 | OK |
| 2023-05-31 | SPXW | bear | 1 | 14:12->14:50 | 38m | 2.2->3.5 | +$130 | reversal-off-extreme | rejection | above | SESSION_OPEN@418.26 | OK |
| 2022-06-07 | SPXW | bull | 1 | 10:34->10:39 | 6m | 1.6->2.85 | +$125 | momentum-breakout | breakout | above | ROUND@412 | OK |
| 2022-08-18 | SPXW | bull | 1 | 10:17->10:49 | 32m | 2.55->3.8 | +$125 | trend-continuation | reclaim | above | ROUND@426 | OK |
| 2022-04-01 | SPXW | bear | 1 | 10:19->10:21 | 2m | 3.1->4.3 | +$120 | pullback-continuation | pullback | below | PDL@451.59 | OK |
| 2022-04-05 | SPXW | bear | 1 | 11:04->11:40 | 36m | 3.5->4.7 | +$120 | trend-continuation | rejection | below | ROUND@455 | OK |
| 2022-05-24 | SPXW | bear | 1 | 09:52->10:00 | 8m | 2.3->3.5 | +$120 | momentum-breakout | breakout | below | IDL@391.26 | OK |
| 2022-05-24 | SPXW | bear | 1 | 10:01->10:18 | 16m | 1.05->2.25 | +$120 | momentum-breakout | breakout | below | ROUND@390 | OK |
| 2022-10-03 | SPXW | bull | 1 | 10:09->10:33 | 24m | 2.6->3.8 | +$120 | momentum-breakout | breakout | above | ROUND@363 | OK |
| 2023-06-02 | SPXW | bull | 1 | 10:10->10:46 | 36m | 2->3.2 | +$120 | trend-continuation | reclaim | above | ROUND@426 | OK |
| 2023-06-06 | SPXW | bull | 2 | 10:16->10:37 | 21m | 3.5->4.1 | +$120 | pullback-continuation | pullback | above | IDH@427.62 | OK |
| 2023-06-07 | SPXW | bull | 1 | 09:36->09:40 | 3m | 3.6->4.8 | +$120 | momentum-breakout | breakout | above | IDH@429.04 | OK |
| 2023-06-07 | SPXW | bear | 1 | 10:19->10:25 | 7m | 2.8->4 | +$120 | momentum-breakout | breakout | below | PDH@428.56 | OK |
| 2022-06-06 | SPXW | bear | 1 | 11:11->11:14 | 3m | 2.55->3.7 | +$115 | pullback-continuation | pullback | below | SESSION_OPEN@414.8 | OK |
| 2022-06-23 | SPXW | bear | 3 | 12:06->12:36 | 30m | 2.217->2.6 | +$115 | momentum-breakout | breakout | below | IDL@374.01 | OK |
| 2023-06-02 | SPXW | bull | 1 | 13:17->13:23 | 7m | 2.85->4 | +$115 | momentum-breakout | breakout | above | ROUND@427 | OK |
| 2022-05-31 | SPXW | bear | 1 | 09:33->09:41 | 8m | 3.4->4.5 | +$110 | momentum-breakout | breakout | below | IDL@411.46 | OK |
| 2022-06-22 | SPXW | bull | 2 | 09:40->09:53 | 13m | 2.2->2.75 | +$110 | pullback-continuation | pullback | above | IDH@372.44 | OK |
| 2023-05-31 | SPXW | bear | 1 | 09:36->10:23 | 48m | 3.1->4.2 | +$110 | reversal-off-extreme | rejection | above | IDH@418.77 | OK |
| 2023-05-31 | SPXW | bear | 1 | 11:00->11:06 | 6m | 3.9->5 | +$110 | trend-continuation | rejection | below | ROUND@417 | OK |
| 2023-06-07 | SPXW | bear | 1 | 10:34->10:35 | 1m | 3.4->4.5 | +$110 | pullback-continuation | pullback | below | ROUND@428 | OK |
| 2023-06-09 | SPXW | bull | 1 | 09:45->09:54 | 9m | 3.1->4.2 | +$110 | pullback-continuation | pullback | above | IDH@430.98 | OK |
| 2023-09-18 | SPXW | bull | 1 | 11:23->11:31 | 9m | 2.1->3.2 | +$110 | momentum-breakout | breakout | above | ROUND@444 | OK |
| 2022-03-08 | SPY | bull | 1 | 12:11->12:17 | 6m | 1.83->2.89 | +$106 | momentum-breakout | breakout | above | ROUND@423 | OK |
| 2022-05-03 | SPXW | bull | 1 | 10:57->11:06 | 9m | 1.95->3 | +$105 | trend-continuation | reclaim | above | ROUND@415 | OK |
| 2022-05-26 | SPXW | bull | 1 | 09:35->09:51 | 17m | 1.75->2.8 | +$105 | momentum-breakout | breakout | above | ROUND@401 | OK |
| 2022-08-17 | SPXW | bull | 1 | 09:34->09:36 | 2m | 2.25->3.3 | +$105 | momentum-breakout | breakout | above | IDH@426.79 | OK |
| 2022-09-21 | SPXW | bull | 1 | 13:35->13:59 | 25m | 2.95->4 | +$105 | trend-continuation | reclaim | above | SESSION_OPEN@386.12 | OK |
| 2023-06-14 | SPY | bull | 6 | 10:31->11:33 | 61m | 0.77->0.94 | +$102 | trend-continuation | reclaim | above | ROUND@438 | OK |
| 2022-03-16 | SPXW | bull | 1 | 10:16->10:18 | 1m | 2.9->3.9 | +$100 | momentum-breakout | breakout | above | ROUND@434 | OK |
| 2022-04-04 | SPXW | bull | 1 | 13:28->14:29 | 61m | 2.1->3.1 | +$100 | trend-continuation | reclaim | above | ROUND@455 | OK |
| 2022-04-12 | SPY | bear | 1 | 12:08->13:59 | 111m | 0.88->1.88 | +$100 | pullback-continuation | pullback | below | ROUND@443 | OK |
| 2022-04-22 | SPXW | bear | 2 | 09:40->10:19 | 39m | 2.3->2.8 | +$100 | momentum-breakout | breakout | below | ROUND@434 | OK |
| 2022-04-25 | SPXW | bear | 1 | 09:43->09:44 | 1m | 2.8->3.8 | +$100 | momentum-breakout | breakout | below | IDL@421.84 | OK |
| 2022-04-26 | SPXW | bear | 1 | 10:53->11:09 | 15m | 3.8->4.8 | +$100 | pullback-continuation | pullback | below | ROUND@421 | OK |
| 2022-05-03 | SPXW | bear | 1 | 10:08->10:10 | 2m | 3.8->4.8 | +$100 | pullback-continuation | pullback | below | ROUND@414 | OK |
| 2022-05-06 | SPXW | bear | 1 | 09:36->09:37 | 2m | 4.6->5.6 | +$100 | momentum-breakout | breakout | below | ROUND@408 | OK |
| 2022-05-10 | SPXW | bull | 2 | 13:44->13:51 | 7m | 2->2.5 | +$100 | pullback-continuation | pullback | above | ROUND@401 | OK |
| 2022-05-31 | SPXW | bear | 1 | 09:33->09:44 | 11m | 3.4->4.4 | +$100 | momentum-breakout | breakout | below | IDL@411.46 | OK |
| 2022-06-02 | SPXW | bull | 1 | 09:55->10:13 | 18m | 2.5->3.5 | +$100 | reversal-off-extreme | reclaim | below | ROUND@408 | OK |
| 2022-06-07 | SPXW | bull | 1 | 14:10->14:15 | 4m | 2.7->3.7 | +$100 | momentum-breakout | breakout | above | IDH@414.27 | OK |
| 2022-06-17 | SPXW | bull | 1 | 16:06->10:03 | 5396m | 2.4->3.4 | +$100 | reversal-off-extreme | reclaim | below | ROUND@366 | OK |
| 2022-06-21 | SPXW | bear | 1 | 11:40->12:13 | 33m | 7->8 | +$100 | pullback-continuation | pullback | above | ROUND@375 | OK |
| 2022-07-05 | SPXW | bear | 1 | 09:46->09:53 | 7m | 1.75->2.75 | +$100 | momentum-breakout | breakout | below | ROUND@374 | OK |
| 2022-07-07 | SPXW | bull | 2 | 09:34->09:49 | 15m | 2.25->2.75 | +$100 | momentum-breakout | breakout | above | IDH@386.49 | OK |
| 2022-07-08 | SPXW | bull | 1 | 13:08->13:11 | 4m | 3.2->4.2 | +$100 | reversal-off-extreme | reclaim | below | SESSION_OPEN@387.27 | OK |
| 2022-07-12 | SPXW | bear | 1 | 09:44->10:01 | 17m | 0.9->1.9 | +$100 | reversal-off-extreme | rejection | above | ROUND@385 | OK |
| 2022-07-14 | SPXW | bull | 1 | 10:23->11:00 | 37m | 3->4 | +$100 | reversal-off-extreme | reclaim | below | ROUND@372 | OK |
| 2022-07-21 | SPXW | bull | 1 | 12:27->12:34 | 7m | 3.7->4.7 | +$100 | momentum-breakout | breakout | above | ROUND@397 | OK |
| 2022-07-26 | SPXW | bear | 1 | 10:55->11:35 | 40m | 3.6->4.6 | +$100 | momentum-breakout | breakout | below | ROUND@393 | OK |
| 2022-08-12 | SPXW | bull | 1 | 14:38->15:10 | 32m | 2.7->3.7 | +$100 | momentum-breakout | breakout | above | IDH@425.79 | OK |
| 2022-08-31 | SPXW | bear | 1 | 10:02->10:19 | 17m | 3.4->4.4 | +$100 | pullback-continuation | pullback | below | ROUND@399 | OK |
| 2022-09-12 | SPXW | bull | 1 | 09:45->09:52 | 7m | 3.7->4.7 | +$100 | momentum-breakout | breakout | above | IDH@409.55 | OK |
| 2022-09-27 | SPXW | bear | 1 | 10:06->10:10 | 4m | 3.8->4.8 | +$100 | momentum-breakout | breakout | below | IDL@366.36 | OK |
| 2023-05-25 | SPXW | bull | 1 | 14:42->15:32 | 50m | 1.1->2.1 | +$100 | trend-continuation | reclaim | above | ROUND@414 | OK |
| 2023-06-06 | SPXW | bear | 1 | 12:51->12:57 | 7m | 2.6->3.6 | +$100 | pullback-continuation | pullback | below | ROUND@427 | OK |
| 2023-06-07 | SPXW | bear | 1 | 10:19->10:24 | 5m | 2.8->3.8 | +$100 | momentum-breakout | breakout | below | PDH@428.56 | OK |
| 2023-06-08 | SPXW | bull | 1 | 10:46->11:12 | 26m | 2.4->3.4 | +$100 | momentum-breakout | breakout | above | IDH@427.65 | OK |
| 2023-06-15 | SPXW | bull | 1 | 09:42->09:45 | 3m | 4->5 | +$100 | momentum-breakout | breakout | above | IDH@437.16 | OK |
| 2023-09-18 | SPXW | bull | 1 | 11:23->11:31 | 8m | 2.1->3.1 | +$100 | momentum-breakout | breakout | above | ROUND@444 | OK |
| 2022-05-25 | SPXW | bull | 1 | 09:48->10:19 | 31m | 2.05->3 | +$95 | reversal-off-extreme | breakout | below | ROUND@393 | OK |
| 2022-06-13 | SPXW | bear | 1 | 10:04->10:19 | 15m | 2.45->3.4 | +$95 | trend-continuation | rejection | below | IDL@379.22 | OK |
| 2022-07-01 | SPXW | bull | 1 | 14:32->14:47 | 15m | 2.65->3.6 | +$95 | pullback-continuation | pullback | above | IDH@379.96 | OK |
| 2022-07-06 | SPXW | bull | 1 | 13:04->14:05 | 61m | 2.05->3 | +$95 | pullback-continuation | pullback | below | ROUND@381 | OK |
| 2022-08-23 | SPXW | bear | 1 | 11:19->12:03 | 45m | 2.45->3.4 | +$95 | pullback-continuation | pullback | below | ROUND@413 | OK |
| 2022-01-13 | SPY | bear | 1 | 14:59->15:50 | 51m | 0.62->1.54 | +$92 | trend-continuation | rejection | below | ROUND@467 | OK |
| 2021-07-23 | SPY | bear | 10 | 09:34->09:57 | 23m | 0.32->0.41 | +$90 | momentum-breakout | breakout | below | IDL@437.23 | OK |
| 2022-03-14 | SPXW | bear | 1 | 11:46->12:22 | 36m | 1.45->2.35 | +$90 | pullback-continuation | pullback | below | ROUND@420 | OK |
| 2022-04-25 | SPXW | bear | 1 | 09:43->09:48 | 5m | 2.8->3.7 | +$90 | momentum-breakout | breakout | below | IDL@421.84 | OK |
| 2022-05-26 | SPXW | bull | 1 | 10:07->11:05 | 58m | 3.2->4.1 | +$90 | momentum-breakout | breakout | above | IDH@402.95 | OK |
| 2022-06-02 | SPXW | bull | 1 | 12:17->12:40 | 23m | 0.75->1.65 | +$90 | pullback-continuation | pullback | above | ROUND@413 | OK |
| 2022-06-03 | SPXW | bull | 1 | 11:26->13:15 | 109m | 2.4->3.3 | +$90 | reversal-off-extreme | reclaim | below | ROUND@410 | OK |
| 2022-06-22 | SPXW | bull | 1 | 10:01->10:13 | 12m | 3.1->4 | +$90 | pullback-continuation | pullback | above | ROUND@373 | OK |
| 2022-06-23 | SPXW | bear | 1 | 12:02->12:05 | 3m | 2.7->3.6 | +$90 | momentum-breakout | breakout | below | ROUND@374 | OK |
| 2022-07-28 | SPXW | bull | 1 | 10:59->11:21 | 22m | 1.95->2.85 | +$90 | pullback-continuation | pullback | above | SESSION_OPEN@401.88 | OK |
| 2022-08-22 | SPXW | bear | 2 | 09:57->10:00 | 3m | 1.75->2.2 | +$90 | pullback-continuation | pullback | below | ROUND@416 | OK |
| 2022-08-26 | SPXW | bear | 1 | 10:38->11:08 | 29m | 2.3->3.2 | +$90 | momentum-breakout | breakout | below | ROUND@412 | OK |
| 2022-09-07 | SPXW | bear | 1 | 09:59->10:15 | 16m | 3.1->4 | +$90 | trend-continuation | rejection | below | ROUND@392 | OK |
| 2022-09-09 | SPXW | bull | 2 | 10:08->10:44 | 36m | 2.15->2.6 | +$90 | momentum-breakout | breakout | above | IDH@405.06 | OK |
| 2022-09-12 | SPXW | bull | 1 | 10:09->10:19 | 10m | 2.7->3.6 | +$90 | pullback-continuation | pullback | above | ROUND@411 | OK |
| 2022-09-15 | SPXW | bull | 2 | 11:20->11:35 | 15m | 2.1->2.55 | +$90 | reversal-off-extreme | reclaim | below | ROUND@392 | OK |
| 2023-05-25 | SPXW | bull | 1 | 14:42->15:32 | 50m | 1.1->2 | +$90 | trend-continuation | reclaim | above | ROUND@414 | OK |
| 2023-06-15 | SPXW | bull | 1 | 09:51->09:52 | 1m | 3.1->4 | +$90 | momentum-breakout | breakout | above | ROUND@439 | OK |
| 2022-03-08 | SPY | bear | 1 | 13:02->13:30 | 28m | 1.31->2.17 | +$86 | reversal-off-extreme | rejection | above | ROUND@427 | OK |
| 2022-08-19 | SPXW | bear | 2 | 14:59->15:02 | 2m | 1.35->1.78 | +$86 | momentum-breakout | breakout | below | IDL@421.76 | OK |
| 2022-05-25 | SPXW | bull | 1 | 09:44->10:18 | 35m | 2.35->3.2 | +$85 | pullback-continuation | pullback | above | IDH@394.93 | OK |
| 2022-06-10 | SPXW | bear | 1 | 09:56->10:23 | 27m | 2.65->3.5 | +$85 | momentum-breakout | breakout | below | IDL@393.06 | OK |
| 2022-06-10 | SPXW | bear | 2 | 09:56->10:31 | 35m | 2.425->2.85 | +$85 | momentum-breakout | breakout | below | IDL@393.06 | OK |
| 2022-07-21 | SPXW | bull | 1 | 10:42->11:00 | 17m | 1.55->2.4 | +$85 | reversal-off-extreme | reclaim | below | ROUND@393 | OK |
| 2022-09-02 | SPXW | bear | 1 | 09:45->10:05 | 19m | 2.95->3.8 | +$85 | pullback-continuation | pullback | below | ROUND@398 | OK |
| 2022-03-07 | SPY | bear | 2 | 10:13->10:55 | 42m | 0.74->1.15 | +$82 | momentum-breakout | breakout | below | ROUND@427 | OK |
| 2022-04-08 | SPXW | bear | 1 | 13:29->13:46 | 17m | 2.1->2.9 | +$80 | pullback-continuation | pullback | above | ROUND@449 | OK |
| 2022-05-06 | SPXW | bear | 2 | 13:50->13:54 | 3m | 2.25->2.65 | +$80 | pullback-continuation | pullback | below | ROUND@410 | OK |
| 2022-05-25 | SPXW | bull | 1 | 14:11->14:17 | 6m | 1.25->2.05 | +$80 | reversal-off-extreme | reclaim | below | ROUND@395 | OK |
| 2022-06-01 | SPXW | bear | 2 | 10:16->10:20 | 4m | 2.8->3.2 | +$80 | momentum-breakout | breakout | below | ROUND@411 | OK |
| 2022-09-06 | SPXW | bear | 1 | 09:32->09:33 | 1m | 3.7->4.5 | +$80 | momentum-breakout | breakout | below | SESSION_OPEN@393.15 | OK |
| 2023-06-12 | SPXW | bull | 1 | 11:35->12:41 | 66m | 4.4->5.2 | +$80 | trend-continuation | reclaim | above | ROUND@431 | OK |
| 2022-02-18 | SPY | bear | 2 | 11:51->12:03 | 13m | 0.93->1.32 | +$78 | pullback-continuation | pullback | below | ROUND@434 | OK |
| 2022-05-23 | SPXW | bear | 1 | 09:53->10:05 | 12m | 2.15->2.9 | +$75 | reversal-off-extreme | rejection | above | SESSION_OPEN@392.94 | OK |
| 2022-06-02 | SPXW | bull | 1 | 12:17->12:36 | 19m | 0.75->1.5 | +$75 | pullback-continuation | pullback | above | ROUND@413 | OK |
| 2022-08-19 | SPXW | bear | 1 | 14:59->15:08 | 9m | 1.35->2.1 | +$75 | momentum-breakout | breakout | below | IDL@421.76 | OK |
| 2022-03-08 | SPY | bear | 1 | 11:03->11:34 | 31m | 1.21->1.93 | +$72 | reversal-off-extreme | rejection | above | PDL@419.39 | OK |
| 2023-06-14 | SPY | bull | 4 | 10:31->11:18 | 47m | 0.77->0.95 | +$72 | trend-continuation | reclaim | above | ROUND@438 | OK |
| 2022-04-07 | SPXW | bear | 1 | 11:02->11:13 | 11m | 3.5->4.2 | +$70 | trend-continuation | rejection | below | SESSION_OPEN@445.71 | OK |
| 2022-04-22 | SPXW | bear | 1 | 10:26->11:44 | 78m | 2.4->3.1 | +$70 | momentum-breakout | breakout | below | ROUND@433 | OK |
| 2022-06-28 | SPXW | bear | 1 | 10:05->10:07 | 2m | 3.7->4.4 | +$70 | momentum-breakout | breakout | below | SESSION_OPEN@390.16 | OK |
| 2022-07-22 | SPXW | bear | 1 | 13:01->13:19 | 18m | 1.9->2.6 | +$70 | momentum-breakout | breakout | below | ROUND@396 | OK |
| 2022-08-11 | SPXW | bull | 1 | 10:11->10:17 | 6m | 2.6->3.3 | +$70 | momentum-breakout | breakout | above | IDH@424.22 | OK |
| 2022-09-22 | SPXW | bear | 1 | 09:37->09:44 | 7m | 4.2->4.9 | +$70 | momentum-breakout | breakout | below | ROUND@376 | OK |
| 2023-06-09 | SPXW | bull | 1 | 10:12->10:17 | 5m | 2.9->3.6 | +$70 | pullback-continuation | pullback | above | IDH@431.65 | OK |
| 2023-06-15 | SPXW | bull | 1 | 09:51->09:53 | 2m | 3.1->3.8 | +$70 | momentum-breakout | breakout | above | ROUND@439 | OK |
| 2022-03-11 | SPY | bear | 1 | 09:49->10:11 | 22m | 0.985->1.67 | +$68 | reversal-off-extreme | rejection | above | SESSION_OPEN@428.15 | OK |
| 2022-04-26 | SPXW | bear | 1 | 09:35->09:45 | 10m | 2.35->3 | +$65 | momentum-breakout | breakout | below | IDL@425.1 | OK |
| 2022-08-22 | SPXW | bear | 1 | 10:18->11:00 | 42m | 1.75->2.4 | +$65 | momentum-breakout | breakout | below | IDL@415.51 | OK |
| 2022-03-31 | SPY | bull | 4 | 10:44->10:51 | 6m | 0.66->0.82 | +$64 | pullback-continuation | pullback | above | ROUND@458 | OK |
| 2021-07-12 | SPY | bear | 10 | 11:28->11:33 | 5m | 0.33->0.392 | +$62 | reversal-off-extreme | rejection | above | IDH@436.74 | OK |
| 2022-04-01 | SPXW | bull | 1 | 13:58->14:08 | 9m | 1.45->2.05 | +$60 | pullback-continuation | pullback | below | ROUND@451 | OK |
| 2022-04-14 | SPXW | bull | 1 | 13:00->14:01 | 61m | 1.1->1.7 | +$60 | reversal-off-extreme | reclaim | below | ROUND@440 | OK |
| 2022-05-24 | SPXW | bear | 1 | 09:52->09:55 | 3m | 2.3->2.9 | +$60 | momentum-breakout | breakout | below | IDL@391.26 | OK |
| 2022-05-25 | SPXW | bear | 1 | 14:05->14:07 | 2m | 0.6->1.2 | +$60 | trend-continuation | rejection | below | ROUND@394 | OK |
| 2022-07-19 | SPXW | bull | 1 | 09:41->10:01 | 20m | 2.3->2.9 | +$60 | reversal-off-extreme | reclaim | below | ROUND@386 | OK |
| 2022-07-21 | SPXW | bull | 1 | 09:38->09:51 | 13m | 1.9->2.5 | +$60 | trend-continuation | reclaim | above | SESSION_OPEN@394.14 | OK |
| 2022-08-05 | SPXW | bull | 1 | 10:04->10:15 | 11m | 0.7->1.3 | +$60 | momentum-breakout | breakout | above | ROUND@413 | OK |
| 2022-08-26 | SPXW | bear | 1 | 10:45->11:12 | 27m | 1.9->2.5 | +$60 | pullback-continuation | pullback | below | ROUND@413 | OK |
| 2022-08-29 | SPXW | bull | 1 | 12:03->12:19 | 15m | 1.5->2.1 | +$60 | pullback-continuation | pullback | above | ROUND@404 | OK |
| 2022-09-12 | SPXW | bull | 1 | 10:09->10:22 | 13m | 2.7->3.3 | +$60 | pullback-continuation | pullback | above | ROUND@411 | OK |
| 2022-03-03 | SPY | bear | 1 | 10:21->11:20 | 59m | 1.17->1.74 | +$57 | momentum-breakout | breakout | below | ROUND@438 | OK |
| 2022-06-09 | SPXW | bear | 1 | 10:32->10:44 | 12m | 1.7->2.25 | +$55 | pullback-continuation | pullback | above | ROUND@411 | OK |
| 2022-09-09 | SPXW | bull | 1 | 10:12->10:47 | 35m | 1.6->2.15 | +$55 | momentum-breakout | breakout | above | ROUND@405 | OK |
| 2022-09-13 | SPY | bear | 2 | 10:35->10:50 | 15m | 1.3->1.56 | +$52 | momentum-breakout | breakout | below | ROUND@399 | OK |
| 2021-12-03 | SPY | bear | 1 | 11:11->12:02 | 50m | 0.97->1.48 | +$51 | pullback-continuation | pullback | below | ROUND@452 | OK |
| 2022-02-22 | SPY | bear | 1 | 13:40->14:07 | 27m | 0.5->1.01 | +$51 | momentum-breakout | breakout | below | ROUND@428 | OK |
| 2022-07-12 | SPY | bear | 1 | 15:58->09:30 | 1051m | 0.49->1 | +$51 | trend-continuation | rejection | below | ROUND@381 | OK |
| 2021-11-22 | SPY | bull | 5 | 09:37->09:55 | 18m | 0.1->0.2 | +$50 | momentum-breakout | breakout | above | IDH@471.4 | OK |
| 2022-05-10 | SPXW | bull | 1 | 13:41->13:44 | 3m | 4.9->5.4 | +$50 | pullback-continuation | pullback | above | ROUND@401 | OK |
| 2022-05-17 | SPXW | bear | 1 | 09:51->09:55 | 4m | 3.1->3.6 | +$50 | momentum-breakout | breakout | below | IDL@404.88 | OK |
| 2022-05-27 | SPXW | bull | 1 | 09:52->09:57 | 5m | 1.2->1.7 | +$50 | momentum-breakout | breakout | above | ROUND@411 | OK |
| 2022-06-27 | SPXW | bear | 1 | 09:36->09:43 | 7m | 3.4->3.9 | +$50 | momentum-breakout | breakout | below | IDL@389.3 | OK |
| 2022-07-28 | SPXW | bull | 1 | 11:32->11:58 | 26m | 1.9->2.4 | +$50 | momentum-breakout | breakout | above | IDH@403.84 | OK |
| 2022-08-24 | SPXW | bull | 1 | 10:48->11:02 | 14m | 3.6->4.1 | +$50 | trend-continuation | reclaim | above | ROUND@413 | OK |
| 2022-09-06 | SPXW | bear | 1 | 09:50->09:57 | 7m | 1.75->2.25 | +$50 | momentum-breakout | breakout | below | ROUND@391 | OK |
| 2022-09-13 | SPXW | bear | 1 | 10:50->10:52 | 2m | 3.2->3.7 | +$50 | momentum-breakout | breakout | below | IDL@398.27 | OK |
| 2023-06-05 | SPXW | bull | 1 | 09:37->09:42 | 5m | 3.6->4.1 | +$50 | reversal-off-extreme | reclaim | below | ROUND@429 | OK |
| 2023-06-06 | SPXW | bull | 1 | 14:31->15:08 | 37m | 1.25->1.75 | +$50 | trend-continuation | reclaim | above | ROUND@427 | OK |
| 2023-06-09 | SPXW | bull | 1 | 10:12->10:21 | 8m | 2.9->3.4 | +$50 | pullback-continuation | pullback | above | IDH@431.65 | OK |
| 2022-02-08 | SPY | bull | 3 | 11:44->12:39 | 55m | 0.46->0.61 | +$45 | momentum-breakout | breakout | above | IDH@449.83 | OK |
| 2022-05-10 | SPXW | bull | 1 | 11:30->11:41 | 11m | 1.25->1.7 | +$45 | reversal-off-extreme | reclaim | below | ROUND@397 | OK |
| 2022-06-07 | SPXW | bull | 1 | 09:37->09:51 | 14m | 1.95->2.4 | +$45 | momentum-breakout | breakout | above | ROUND@409 | OK |
| 2022-06-07 | SPXW | bull | 1 | 12:48->13:16 | 29m | 1.1->1.55 | +$45 | pullback-continuation | pullback | above | PDL@412.78 | OK |
| 2022-06-29 | SPXW | bear | 1 | 09:32->09:41 | 9m | 1.65->2.1 | +$45 | momentum-breakout | breakout | below | IDL@379.23 | OK |
| 2022-09-12 | SPXW | bull | 1 | 12:21->13:10 | 50m | 0.9->1.35 | +$45 | reversal-off-extreme | reclaim | below | ROUND@410 | OK |
| 2023-05-30 | SPY | bear | 3 | 09:46->10:05 | 19m | 0.6->0.74 | +$42 | momentum-breakout | breakout | below | IDL@421.61 | OK |
| 2022-02-23 | SPY | bull | 10 | 11:27->11:51 | 25m | 0.26->0.3 | +$40 | reversal-off-extreme | reclaim | below | ROUND@427 | OK |
| 2022-06-23 | SPXW | bear | 1 | 12:02->12:06 | 4m | 2.7->3.1 | +$40 | momentum-breakout | breakout | below | ROUND@374 | OK |
| 2022-07-26 | SPXW | bear | 1 | 10:12->10:14 | 2m | 1.55->1.95 | +$40 | pullback-continuation | pullback | below | ROUND@393 | OK |
| 2022-02-18 | SPY | bear | 1 | 10:59->11:05 | 6m | 0.35->0.72 | +$37 | pullback-continuation | pullback | below | IDL@435.25 | OK |
| 2022-02-22 | SPY | bear | 1 | 13:40->13:56 | 16m | 0.5->0.87 | +$37 | momentum-breakout | breakout | below | ROUND@428 | OK |
| 2022-07-06 | SPY | bear | 1 | 09:34->09:38 | 4m | 0.78->1.15 | +$37 | reversal-off-extreme | rejection | above | ROUND@383 | OK |
| 2022-02-18 | SPY | bear | 1 | 12:12->12:43 | 30m | 0.81->1.16 | +$35 | pullback-continuation | pullback | below | ROUND@434 | OK |
| 2022-04-19 | SPXW | bull | 1 | 11:08->11:29 | 21m | 2.4->2.75 | +$35 | trend-continuation | reclaim | above | ROUND@443 | OK |
| 2022-07-06 | SPXW | bull | 1 | 11:58->13:56 | 118m | 2.3->2.65 | +$35 | reversal-off-extreme | reclaim | below | ROUND@381 | OK |
| 2023-06-08 | SPY | bull | 3 | 12:13->12:23 | 9m | 0.25->0.36 | +$33 | trend-continuation | reclaim | above | ROUND@428 | OK |
| 2022-03-29 | SPXW | bull | 1 | 10:23->10:33 | 11m | 1->1.3 | +$30 | reversal-off-extreme | reclaim | below | ROUND@458 | OK |
| 2022-04-26 | SPXW | bear | 2 | 09:50->10:20 | 30m | 0.8->0.95 | +$30 | momentum-breakout | breakout | below | ROUND@424 | OK |
| 2022-05-10 | SPXW | bear | 1 | 11:22->11:27 | 5m | 3.5->3.8 | +$30 | pullback-continuation | pullback | below | ROUND@397 | OK |
| 2022-06-07 | SPXW | bull | 1 | 14:32->14:35 | 3m | 0.9->1.2 | +$30 | momentum-breakout | breakout | above | IDH@414.67 | OK |
| 2022-09-08 | SPXW | bull | 1 | 13:11->13:41 | 30m | 0.6->0.9 | +$30 | pullback-continuation | pullback | above | ROUND@399 | OK |
| 2023-06-05 | SPXW | bull | 1 | 09:37->09:43 | 6m | 3.6->3.9 | +$30 | reversal-off-extreme | reclaim | below | ROUND@429 | OK |
| 2021-07-21 | SPY | bull | 2 | 09:51->09:56 | 5m | 0.56->0.7 | +$28 | momentum-breakout | breakout | above | IDH@433.28 | OK |
| 2021-12-02 | SPY | bull | 4 | 09:43->15:36 | 353m | 0.23->0.3 | +$28 | momentum-breakout | breakout | above | ROUND@454 | OK |
| 2022-08-23 | SPXW | bear | 1 | 11:19->12:07 | 48m | 2.45->2.7 | +$25 | pullback-continuation | pullback | below | ROUND@413 | OK |
| 2022-04-12 | SPY | bear | 2 | 12:08->12:55 | 47m | 0.88->1 | +$24 | pullback-continuation | pullback | below | ROUND@443 | OK |
| 2022-04-18 | SPY | bear | 2 | 09:34->09:53 | 19m | 1.08->1.2 | +$24 | reversal-off-extreme | rejection | above | IDH@438.86 | OK |
| 2022-06-30 | SPY | bull | 1 | 10:43->10:54 | 11m | 0.57->0.81 | +$24 | pullback-continuation | pullback | below | ROUND@374 | OK |
| 2021-12-08 | SPY | bull | 1 | 11:03->11:32 | 29m | 1.05->1.26 | +$21 | reversal-off-extreme | reclaim | below | IDL@467.02 | OK |
| 2021-07-07 | SPY | bear | 2 | 10:22->10:28 | 6m | 0.21->0.31 | +$20 | trend-continuation | rejection | below | SESSION_OPEN@433.67 | OK |
| 2022-03-15 | SPXW | bull | 1 | 10:21->10:26 | 4m | 4.8->5 | +$20 | pullback-continuation | pullback | above | ROUND@421 | OK |
| 2022-04-04 | SPXW | bull | 2 | 10:21->10:34 | 13m | 0.85->0.95 | +$20 | pullback-continuation | pullback | above | IDH@454.69 | OK |
| 2022-05-03 | SPXW | bear | 1 | 10:08->10:11 | 3m | 3.8->4 | +$20 | pullback-continuation | pullback | below | ROUND@414 | OK |
| 2022-05-03 | SPXW | bear | 1 | 12:06->12:09 | 4m | 1->1.2 | +$20 | pullback-continuation | pullback | above | ROUND@416 | OK |
| 2022-05-24 | SPXW | bear | 1 | 09:33->09:40 | 6m | 2.65->2.85 | +$20 | momentum-breakout | breakout | below | ROUND@392 | OK |
| 2022-06-06 | SPXW | bull | 2 | 13:42->13:43 | 1m | 1.75->1.85 | +$20 | reversal-off-extreme | reclaim | below | ROUND@413 | OK |
| 2022-06-07 | SPXW | bull | 1 | 14:10->14:16 | 6m | 2.7->2.9 | +$20 | momentum-breakout | breakout | above | IDH@414.27 | OK |
| 2022-06-10 | SPXW | bear | 2 | 10:58->11:44 | 46m | 2.3->2.4 | +$20 | trend-continuation | rejection | below | ROUND@391 | OK |
| 2023-06-08 | SPXW | bull | 2 | 10:46->11:17 | 32m | 2.4->2.5 | +$20 | momentum-breakout | breakout | above | IDH@427.65 | OK |
| 2022-01-18 | SPY | bear | 2 | 10:15->10:23 | 8m | 0.49->0.57 | +$16 | trend-continuation | rejection | below | ROUND@458 | OK |
| 2022-04-04 | SPY | bull | 2 | 13:29->14:02 | 33m | 0.36->0.44 | +$16 | trend-continuation | reclaim | above | ROUND@455 | OK |
| 2022-04-22 | SPY | bear | 1 | 13:40->14:10 | 31m | 0.41->0.57 | +$16 | momentum-breakout | breakout | below | IDL@429.51 | OK |
| 2022-04-21 | SPY | bear | 1 | 14:01->14:06 | 5m | 1.06->1.2 | +$14 | momentum-breakout | breakout | below | ROUND@441 | OK |
| 2022-04-29 | SPY | bear | 1 | 14:51->15:08 | 18m | 0.66->0.8 | +$14 | momentum-breakout | breakout | below | PDL@415.02 | OK |
| 2022-02-03 | SPY | bear | 1 | 14:40->15:05 | 25m | 2.37->2.48 | +$11 | momentum-breakout | breakout | below | ROUND@448 | OK |
| 2022-03-18 | SPY | bull | 2 | 10:22->10:31 | 9m | 0.55->0.6 | +$10 | pullback-continuation | pullback | above | ROUND@440 | OK |
| 2022-03-31 | SPXW | bull | 2 | 10:54->11:03 | 8m | 1.75->1.8 | +$10 | pullback-continuation | pullback | above | ROUND@458 | OK |
| 2022-04-14 | SPXW | bear | 1 | 10:24->11:45 | 82m | 1.9->2 | +$10 | pullback-continuation | pullback | below | ROUND@441 | OK |
| 2022-05-31 | SPXW | bear | 1 | 10:24->10:27 | 3m | 2.6->2.7 | +$10 | reversal-off-extreme | rejection | above | ROUND@412 | OK |
| 2022-06-07 | SPXW | bull | 1 | 14:33->14:36 | 3m | 0.9->1 | +$10 | momentum-breakout | breakout | above | IDH@414.67 | OK |
| 2022-06-10 | SPXW | bear | 1 | 11:48->13:14 | 85m | 3->3.1 | +$10 | pullback-continuation | pullback | below | ROUND@390 | OK |
| 2022-07-13 | SPXW | bear | 1 | 09:41->10:18 | 37m | 1.5->1.6 | +$10 | reversal-off-extreme | rejection | above | ROUND@376 | OK |
| 2022-07-20 | SPXW | bull | 1 | 13:24->13:37 | 12m | 0.65->0.75 | +$10 | reversal-off-extreme | reclaim | below | ROUND@393 | OK |
| 2022-08-22 | SPXW | bear | 1 | 10:18->11:02 | 43m | 1.75->1.85 | +$10 | momentum-breakout | breakout | below | IDL@415.51 | OK |
| 2023-06-02 | SPXW | bull | 1 | 13:17->13:31 | 14m | 2.85->2.95 | +$10 | momentum-breakout | breakout | above | ROUND@427 | OK |
| 2023-06-09 | SPXW | bull | 1 | 09:45->09:56 | 11m | 3.1->3.2 | +$10 | pullback-continuation | pullback | above | IDH@430.98 | OK |
| 2022-01-31 | SPY | bull | 4 | 09:37->11:58 | 141m | 0.1->0.12 | +$8 | momentum-breakout | breakout | above | ROUND@442 | OK |
| 2022-07-06 | SPY | bull | 1 | 14:36->15:26 | 50m | 0.22->0.3 | +$8 | momentum-breakout | breakout | above | ROUND@384 | OK |
| 2022-04-13 | SPY | bear | 1 | 11:34->11:42 | 8m | 0.5->0.56 | +$6 | reversal-off-extreme | rejection | above | IDH@441.66 | OK |
| 2022-07-21 | SPY | bull | 1 | 14:02->14:22 | 20m | 0.31->0.37 | +$6 | trend-continuation | reclaim | above | PDH@396.25 | OK |
| 2022-05-23 | SPXW | bull | 1 | 14:01->14:23 | 21m | 0.5->0.55 | +$5 | pullback-continuation | pullback | above | ROUND@396 | OK |
| 2022-05-25 | SPXW | bear | 1 | 14:03->14:04 | 1m | 0.65->0.7 | +$5 | reversal-off-extreme | rejection | above | PDH@395.15 | OK |
| 2022-08-22 | SPXW | bear | 1 | 09:57->10:04 | 7m | 1.75->1.8 | +$5 | pullback-continuation | pullback | below | ROUND@416 | OK |
| 2022-02-24 | SPY | bull | 1 | 15:10->09:38 | 1109m | 0.09->0.13 | +$4 | pullback-continuation | pullback | above | IDH@424.74 | OK |
| 2022-04-13 | SPY | bear | 1 | 11:34->11:43 | 9m | 0.5->0.54 | +$4 | reversal-off-extreme | rejection | above | IDH@441.66 | OK |
| 2023-05-02 | SPY | bear | 1 | 10:33->10:54 | 22m | 0.02->0.06 | +$4 | momentum-breakout | breakout | below | ROUND@410 | OK |
| 2021-08-04 | SPY | bull | 1 | 09:52->10:02 | 10m | 0.31->0.32 | +$1 | reversal-off-extreme | reclaim | below | SESSION_OPEN@439.76 | OK |

## What feeds the engine (recommendations, not ratified)

- These journaled winners are the **real-fill ground-truth anchor set** for validating the diversified/regime book on J's actual edge — richer than the 3 bearish OP-16 source-of-truth trades.
- The 1-2 lot subset is the canonical replication target; the 3+ lot rows are retained for completeness but excluded from any edge-capture target (per L168 sizing finding).
- Cross-reference `docs/J-WEBULL-EDGE-2021-2023.md` for the full style analytics (time-of-day, sizing, call/put expectancy).
