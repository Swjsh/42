# OOS SEGMENTATION — where the bleed is (production v15, real fills)

68 trades over 60 OOS days. Overall: WR 0.32, +272/c total (+4.0/trade).

## By SIDE (the OP-16 question)
| bucket | n | WR | total/c | per-trade/c |
|---|---|---|---|---|
| BEAR_put | 57 | 0.32 | +144 | +2.5 |
| BULL_call | 11 | 0.36 | +128 | +11.7 |

## By setup
| bucket | n | WR | total/c | per-trade/c |
|---|---|---|---|---|
| BEARISH_REJECTION_RIDE_THE_RIBBON::BS_FALLBACK | 7 | 0.71 | +462 | +66.0 |
| BULLISH_RECLAIM_RIDE_THE_RIBBON | 11 | 0.36 | +128 | +11.7 |
| BEARISH_REJECTION_RIDE_THE_RIBBON | 50 | 0.26 | -318 | -6.4 |

## By time-of-day
| bucket | n | WR | total/c | per-trade/c |
|---|---|---|---|---|
| OPEN_DRIVE | 16 | 0.44 | +396 | +24.7 |
| MORNING | 8 | 0.5 | +161 | +20.1 |
| AFTERNOON | 5 | 0.4 | +14 | +2.8 |
| POWER_HOUR | 6 | 0.17 | -15 | -2.5 |
| MIDDAY | 33 | 0.24 | -283 | -8.6 |

## By VIX regime
| bucket | n | WR | total/c | per-trade/c |
|---|---|---|---|---|
| UNK | 68 | 0.32 | +272 | +4.0 |

## By trigger count
| bucket | n | WR | total/c | per-trade/c |
|---|---|---|---|---|
| 2trig | 18 | 0.39 | +372 | +20.7 |
| 3trig | 6 | 0.5 | +147 | +24.5 |
| 4trig | 1 | 0.0 | -19 | -19.0 |
| 1trig | 43 | 0.28 | -228 | -5.3 |

## By confluence
| bucket | n | WR | total/c | per-trade/c |
|---|---|---|---|---|
| has_confluence | 19 | 0.42 | +490 | +25.8 |
| no_confluence | 49 | 0.29 | -217 | -4.4 |

## By exit reason
| bucket | n | WR | total/c | per-trade/c |
|---|---|---|---|---|
| TP1_THEN_RUNNER_TARGET | 2 | 1.0 | +437 | +218.4 |
| TP1_THEN_RUNNER_RIBBON | 7 | 1.0 | +312 | +44.6 |
| TP1_THEN_RUNNER_TIME | 2 | 1.0 | +293 | +146.7 |
| TP1_THEN_RUNNER_BE_STOP | 3 | 1.0 | +106 | +35.4 |
| EXIT_ALL_TIME_STOP | 1 | 1.0 | +100 | +100.0 |
| EXIT_ALL_LEVEL_STOP | 2 | 1.0 | +65 | +32.5 |
| EXIT_ALL_RIBBON_FLIP_BACK | 6 | 0.83 | +35 | +5.8 |
| EXIT_ALL_PREMIUM_STOP | 45 | 0.0 | -1076 | -23.9 |
