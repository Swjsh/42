# MIDDAY AUTOPSY — why the 33 midday trades bleed (real fills only, no BS_FALLBACK)

**32 midday real-fills trades**, WR 0.25, -8.5/trade (total -271/c)

## Trigger profile: winners vs losers
| metric | winners (n=8) | losers (n=24) |
|---|---|---|
| avg triggers | 1.38 | 1.25 |
| % with confluence | 12% | 12% |

## Selectivity gate applied to midday ONLY
- midday with confluence: n=4, total +65/c
- midday without confluence: n=28, total -336/c
- midday >=2 triggers: n=8, total +52/c
- midday 1-trigger: n=24, total -323/c

## Midday WINNERS (all real fills)
| time | setup | triggers | px | pc | exit |
|---|---|---|---|---|---|
| 13:15 | BEARISH_REJECTION_RIDE_TH | level_rejection|conf | 2.83 | +126.9 | TP1_THEN_RUNNER_TIME |
| 13:10 | BEARISH_REJECTION_RIDE_TH | level_rejection|ribb | 2.72 | +51.9 | TP1_THEN_RUNNER_RIBBON |
| 12:45 | BEARISH_REJECTION_RIDE_TH | trendline_rejection | 1.83 | +36.6 | TP1_THEN_RUNNER_RIBBON |
| 12:30 | BEARISH_REJECTION_RIDE_TH | trendline_rejection | 1.07 | +26.8 | TP1_THEN_RUNNER_RIBBON |
| 12:00 | BEARISH_REJECTION_RIDE_TH | trendline_rejection | 2.72 | +24.0 | EXIT_ALL_RIBBON_FLIP_BACK |
| 13:50 | BEARISH_REJECTION_RIDE_TH | trendline_rejection | 2.05 | +6.0 | EXIT_ALL_RIBBON_FLIP_BACK |
| 13:10 | BEARISH_REJECTION_RIDE_TH | trendline_rejection | 2.01 | +5.0 | EXIT_ALL_RIBBON_FLIP_BACK |
| 13:40 | BEARISH_REJECTION_RIDE_TH | trendline_rejection | 2.22 | +1.0 | EXIT_ALL_RIBBON_FLIP_BACK |

## Midday LOSERS (all real fills)
| time | setup | triggers | px | pc | exit |
|---|---|---|---|---|---|
| 11:35 | BEARISH_REJECTION_RIDE_TH | trendline_rejection | 6.49 | -51.9 | EXIT_ALL_PREMIUM_STOP |
| 13:45 | BEARISH_REJECTION_RIDE_TH | trendline_rejection | 3.9 | -31.2 | EXIT_ALL_PREMIUM_STOP |
| 11:40 | BEARISH_REJECTION_RIDE_TH | trendline_rejection | 3.31 | -26.5 | EXIT_ALL_PREMIUM_STOP |
| 12:15 | BEARISH_REJECTION_RIDE_TH | trendline_rejection | 3.15 | -25.2 | EXIT_ALL_PREMIUM_STOP |
| 11:35 | BEARISH_REJECTION_RIDE_TH | level_rejection | 2.99 | -23.9 | EXIT_ALL_PREMIUM_STOP |
| 11:45 | BULLISH_RECLAIM_RIDE_THE_ | level_reclaim|conflu | 2.87 | -23.0 | EXIT_ALL_PREMIUM_STOP |
| 12:35 | BEARISH_REJECTION_RIDE_TH | trendline_rejection | 2.85 | -22.8 | EXIT_ALL_PREMIUM_STOP |
| 13:15 | BEARISH_REJECTION_RIDE_TH | trendline_rejection | 2.83 | -22.6 | EXIT_ALL_PREMIUM_STOP |
| 13:05 | BEARISH_REJECTION_RIDE_TH | level_rejection | 2.81 | -22.5 | EXIT_ALL_PREMIUM_STOP |
| 13:25 | BEARISH_REJECTION_RIDE_TH | ribbon_flip|trendlin | 2.81 | -22.5 | EXIT_ALL_PREMIUM_STOP |
| 12:50 | BEARISH_REJECTION_RIDE_TH | ribbon_flip|trendlin | 2.8 | -22.4 | EXIT_ALL_PREMIUM_STOP |
| 12:50 | BEARISH_REJECTION_RIDE_TH | trendline_rejection | 2.76 | -22.1 | EXIT_ALL_PREMIUM_STOP |
| 13:20 | BEARISH_REJECTION_RIDE_TH | trendline_rejection | 2.67 | -21.4 | EXIT_ALL_PREMIUM_STOP |
| 12:35 | BULLISH_RECLAIM_RIDE_THE_ | level_reclaim|conflu | 2.64 | -21.1 | EXIT_ALL_PREMIUM_STOP |
| 13:10 | BEARISH_REJECTION_RIDE_TH | level_rejection|ribb | 2.62 | -21.0 | EXIT_ALL_PREMIUM_STOP |
| 11:30 | BEARISH_REJECTION_RIDE_TH | trendline_rejection | 2.53 | -20.2 | EXIT_ALL_PREMIUM_STOP |
| 11:50 | BEARISH_REJECTION_RIDE_TH | trendline_rejection | 2.44 | -19.5 | EXIT_ALL_PREMIUM_STOP |
| 13:20 | BEARISH_REJECTION_RIDE_TH | trendline_rejection | 2.42 | -19.4 | EXIT_ALL_PREMIUM_STOP |
| 13:05 | BEARISH_REJECTION_RIDE_TH | level_rejection | 2.4 | -19.2 | EXIT_ALL_PREMIUM_STOP |
| 12:15 | BEARISH_REJECTION_RIDE_TH | trendline_rejection | 2.37 | -19.0 | EXIT_ALL_PREMIUM_STOP |
| 12:20 | BEARISH_REJECTION_RIDE_TH | trendline_rejection | 2.36 | -18.9 | EXIT_ALL_PREMIUM_STOP |
| 12:45 | BEARISH_REJECTION_RIDE_TH | trendline_rejection | 2.26 | -18.1 | EXIT_ALL_PREMIUM_STOP |
| 13:20 | BEARISH_REJECTION_RIDE_TH | trendline_rejection | 2.21 | -17.7 | EXIT_ALL_PREMIUM_STOP |
| 12:55 | BEARISH_REJECTION_RIDE_TH | level_rejection|conf | 2.18 | -17.4 | EXIT_ALL_PREMIUM_STOP |