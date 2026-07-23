# Q2 -- Late-entry ceiling real-fills upgrade (2026-07-23)

Generated 2026-07-23T16:33:30.505389. Runner: `backtest/tools/late_entry_ceiling_realfills.py`. Pre-reg: `analysis/recommendations/late-entry-ceiling-realfills-prereg-2026-07-23.json`.

## VERDICT: **KEEP**

n=21 clears the raw-leg floor; aggregate real-fills P&L is $+43.80 but NOT clearly positive: one-sided p(mean>0)=0.4647 and win rate=0.2857 -- the ceiling is correctly avoiding a low-hit-rate cohort with no demonstrable edge.

**Decisive number:** aggregate real-fills P&L across n=21 replayed bear-only SKIP_LATE_ENTRY episodes = $+43.80, win rate 0.2857.

Population: 21 episodes total, 21 replayed, 0 excluded (no OPRA/SPY coverage).

## Per account

| account | n | total pnl | win rate |
|---|--:|--:|--:|
| bold | 9 | $+43.50 | 0.3333 |
| safe | 12 | $+0.30 | 0.25 |

## Per exit reason

| exit reason | n | total pnl |
|---|--:|--:|
| runner_stop | 2 | $+243.00 |
| time_stop_15:50 | 7 | $+468.00 |
| ribbon_flip_back | 1 | $-27.00 |
| premium_stop | 9 | $-268.20 |
| structure_stop | 2 | $-372.00 |

## Episode detail

| date | account | block time | n fires | SPY | strike | trigger | entry prem | pnl | exit reason |
|---|---|---|--:|--:|--:|--:|--:|--:|---|
| 2026-07-13 | bold | 15:16 | 2 | 749.29 | 00749000 | None | 0.45 | $+121.50 | runner_stop @ 0.77 |
| 2026-07-13 | bold | 15:20 | 6 | 749.29 | 00749000 | None | 0.6 | $-48.00 | time_stop_15:50 |
| 2026-07-14 | bold | 15:02 | 6 | 752.17 | 00752000 | None | 0.45 | $-27.00 | ribbon_flip_back |
| 2026-07-17 | bold | 15:06 | 1 | 743.845 | 00744000 | 744.22 | 1.07 | $-72.00 | time_stop_15:50 |
| 2026-07-17 | bold | 15:11 | 5 | 743.38 | 00743000 | None | 0.95 | $-57.00 | premium_stop @ 0.76 |
| 2026-07-20 | bold | 15:43 | 1 | 742.92 | 00743000 | None | 0.46 | $+147.00 | time_stop_15:50 |
| 2026-07-21 | bold | 15:10 | 1 | 748.285 | 00748000 | None | 0.3 | $-18.00 | premium_stop @ 0.24 |
| 2026-07-23 | bold | 15:36 | 5 | 737.145 | 00737000 | None | 0.73 | $+183.00 | time_stop_15:50 |
| 2026-07-23 | bold | 15:47 | 3 | 736.27 | 00736000 | 736.7 | 0.7 | $-186.00 | structure_stop @ 736.7 |
| 2026-07-07 | safe | 15:46 | 5 | 746.53 | 00747000 | None | 0.44 | $-26.40 | premium_stop @ 0.35 |
| 2026-07-13 | safe | 15:16 | 5 | 749.29 | 00749000 | None | 0.45 | $+121.50 | runner_stop @ 0.77 |
| 2026-07-14 | safe | 15:06 | 5 | 751.98 | 00752000 | None | 0.48 | $-28.80 | premium_stop @ 0.38 |
| 2026-07-17 | safe | 15:06 | 1 | 743.845 | 00744000 | 744.22 | 1.07 | $-72.00 | time_stop_15:50 |
| 2026-07-17 | safe | 15:11 | 5 | 743.38 | 00743000 | None | 0.95 | $-57.00 | premium_stop @ 0.76 |
| 2026-07-17 | safe | 15:41 | 5 | 742.81 | 00743000 | None | 0.37 | $-22.20 | premium_stop @ 0.3 |
| 2026-07-20 | safe | 15:41 | 5 | 742.92 | 00743000 | None | 0.46 | $+147.00 | time_stop_15:50 |
| 2026-07-21 | safe | 15:00 | 1 | 748.29 | 00748000 | None | 0.33 | $-19.80 | premium_stop @ 0.26 |
| 2026-07-21 | safe | 15:06 | 5 | 748.285 | 00748000 | None | 0.35 | $-21.00 | premium_stop @ 0.28 |
| 2026-07-21 | safe | 15:14 | 2 | 748.15 | 00748000 | None | 0.3 | $-18.00 | premium_stop @ 0.24 |
| 2026-07-23 | safe | 15:36 | 5 | 737.145 | 00737000 | None | 0.73 | $+183.00 | time_stop_15:50 |
| 2026-07-23 | safe | 15:47 | 3 | 736.27 | 00736000 | 736.7 | 0.7 | $-186.00 | structure_stop @ 736.7 |

## Reconciliation vs the 2026-07-21 chef study

strategy/candidates/2026-07-21-202600-late-entry-ceiling-reconsider.md used a SPY-spot-direction proxy on 19 ALL-DIRECTION episodes (10-31% favorable-direction rate depending on ceiling tested) and found REJECTED (do not loosen). This study restricts to n=21 BEAR-ONLY episodes (larger/fresher window, 07-07..07-23 vs that study's 07-07..07-21) and replays REAL option P&L via exit_manager_walk instead of a spot proxy.

## Disclosed limitations

- Strike convention: ATM (round(SPY spot at first block-fire)) uniformly for BOTH accounts -- the blocked entries never reached strike selection. Matches Safe's real V15_SAFE_TIERS convention exactly; Bold's real convention is OTM-2, so Bold-episode P&L here is a same-methodology-as-Safe approximation, not Bold's actual tier -- disclosed, not hidden.
- qty=3 (Rule 6 floor) uniformly -- blocked entries never reached position sizing.
- trigger_level used only where directly logged in the live decision (trigger_level_exact, 2/21 episodes); all others fall back to stop_mode=='premium' (premium_stop_pct=-0.20) identically to how a real entry with no recoverable level resolves live -- never a fabricated level.
- C6 fill-mark convention (exit_manager_walk.py): market-style stages fill at that bar's close minus $0.02 slippage; limit-style stages fill exactly at the triggered premium level. Frictionless beyond that.
- 2026-07-23's SPY 5-min series comes from a same-session supplemental fetch (spy_5m_2026-07-23_supplement.csv, read-only market data, same _alpaca_creds.py pattern as tools/fetch_option_data.py) -- the shared cache stops at 2026-07-22.

---
_Source: `backtest/tools/late_entry_ceiling_realfills.py`. Full per-episode detail in the companion `.json`._
