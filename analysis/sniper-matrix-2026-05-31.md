# SNIPER MATRIX — entry x stop x profit-lock (real fills, FAITHFUL to engine)

Signal universe derived from run_backtest itself (V0 reproduces the engine; D1/D2 re-time the same triggers). Per-contract $. Strike 0=ATM, 2=ITM2. D1=retest-reclaim, D2=no-retest momentum, D1_or_D2=D1 else D2. PLoff=trailing profit-lock disabled.

_Guard: engine V0 green=4 reproduced by re-sim. Signals=5._

## Min stop for 4/4 green, per entry-variant (smaller = better entry = J's metric)
| variant | strike | PL | min stop 4/4 | per-c@min | worst/c | n |
|---|---|---|---|---|---|---|
| V0 | ATM | PLoff | **-50%** | +135.8 | 0.0 | 5 |
| V0 | ATM | PLon | none (<4/4) | — | — | — |
| V0 | ITM2 | PLoff | none (<4/4) | — | — | — |
| V0 | ITM2 | PLon | none (<4/4) | — | — | — |
| D1 | ATM | PLoff | none (<4/4) | — | — | — |
| D1 | ATM | PLon | none (<4/4) | — | — | — |
| D1 | ITM2 | PLoff | none (<4/4) | — | — | — |
| D1 | ITM2 | PLon | none (<4/4) | — | — | — |
| D2 | ATM | PLoff | none (<4/4) | — | — | — |
| D2 | ATM | PLon | none (<4/4) | — | — | — |
| D2 | ITM2 | PLoff | none (<4/4) | — | — | — |
| D2 | ITM2 | PLon | none (<4/4) | — | — | — |
| D1_or_D2 | ATM | PLoff | none (<4/4) | — | — | — |
| D1_or_D2 | ATM | PLon | none (<4/4) | — | — | — |
| D1_or_D2 | ITM2 | PLoff | none (<4/4) | — | — | — |
| D1_or_D2 | ITM2 | PLon | none (<4/4) | — | — | — |

## RANKED by smallest stop for 4/4 green
| rank | min stop | variant | strike | PL | per-c | worst/c | n |
|---|---|---|---|---|---|---|---|
| 1 | -50% | V0 | ATM | PLoff | +135.8 | 0.0 | 5 |

## Anchor preservation (top-5 smallest-stop winners on bear-put anchor window)
| variant | strike | PL | stop | 5/04 cap | anchor total/c | worst put/c | n |
|---|---|---|---|---|---|---|---|
| V0 | ATM | PLoff | -50% | +31.2 | +66.4 | -58.0 | 7 |

**OP-16 decision rule:** best = smallest missed-week stop that ALSO keeps a 5/04 capture and a shallow worst-put-loss. That entry fixes the week without breaking the bear book or needing a -50% stop.

## HEADLINE: **V0 @ ATM/PLoff -> 4/4 green at -50% stop** (+135.8/c, worst 0.0/c). Baseline V0 needs -50%. Smaller stop = entry closer to the move = J's sniper thesis.